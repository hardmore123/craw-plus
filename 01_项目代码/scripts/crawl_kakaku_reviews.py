"""在 価格.com（kakaku.com）抓取指定品牌电视的用户评价，按通用网评模板导出。

默认针对海信（hisense_jp），型号清单来自 SPEC 型号汇总 CSV（scripts/export_spec_models.py 产出）。
流程（每个型号）：
    型号 → search.kakaku.com 定位商品 item id
         → 商品页读发售日 + 最安价格 + 尺寸，仅保留目标上市年份（默认 2026）机型
         → 优先 レビュー（结构化评价，翻页抓全）
         → レビュー 404/为空时回退 クチコミ（讨论板）：先抓列表页帖，再逐个进入
           讨论主题（SortID）抓全部帖/回帖，主题标题填入「网评标题」
         → 每条评价/帖一行

输出模板：overseas/review_export.py 的通用 20 列（与 Amazon 网评表前 15 列一致，
扩展 翻译 / 提炼优点(通过AI) / 提炼缺点(通过AI) / 商品ID / 价格）。多地区/多站点共用。

「翻译 / 提炼优点 / 提炼缺点」三列默认留空，仅保留可插拔 AI 接口（review_export.AiHooks）。

加 --save-db 时同时写入数据库（供后端 API 查询）：
    product              机型登记为商品（sku=kakaku item id）
    review               评价明细，按 (product_id, review_key) 增量去重
    kakaku_task_status   型号级状态，空/失败不静默
review_key：レビュー 用 `ReviewCD=NNN`，クチコミ 用 `bbs:書込番号`，取不到时用正文哈希。

示例：
    python scripts/crawl_kakaku_reviews.py
    python scripts/crawl_kakaku_reviews.py --year 2026 --limit-models 5
    python scripts/crawl_kakaku_reviews.py --models 65U8S 55U8S --out data/海信评价.xlsx
    python scripts/crawl_kakaku_reviews.py --no-threads         # 只抓讨论板列表页，不进主题
    python scripts/crawl_kakaku_reviews.py --models 65U8S --save-db   # 同时入库
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                       # noqa: E402
from overseas.db import Database                  # noqa: E402
from overseas.fetchers import BrowserFetcher      # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.models import Product, Review       # noqa: E402
from overseas.review_export import (              # noqa: E402
    NULL_HOOKS, AiHooks, ReviewRecord, write_csv, write_xlsx,
)
from overseas.scenarios import open_dom           # noqa: E402
from overseas.sites import SiteRegistry           # noqa: E402

# 品牌 code → 模板「品牌」列展示名
BRAND_DISPLAY = {
    "hisense_jp": "Hisense",
    "sony_jp": "SONY",
    "regza_jp": "REGZA",
    "panasonic_jp": "Panasonic",
    "tcl_jp": "TCL",
    "sharp_jp": "SHARP",
}

DEFAULT_MODELS_CSV = PROJECT_ROOT / "data" / "SPEC_型号汇总_20260908.csv"


# ==================== 数据结构 ====================

@dataclass
class RawReview:
    """从站点解析出的一条原始评价，随后转成通用 ReviewRecord。"""
    body: str
    source: str            # レビュー / クチコミ
    rating: str = ""
    title: str = ""
    date: str = ""
    url: str = ""
    author: str = ""
    key: str = ""          # 站内稳定唯一标识：レビュー=ReviewCD、クチコミ=書込番号
    image_urls: list[str] = field(default_factory=list)   # 评论内用户上传图片（原图）
    video_urls: list[str] = field(default_factory=list)   # 评论内用户视频链接


@dataclass
class ModelStats:
    """单型号抓取的耗时/请求度量（7.8 可观测性）。

    这些数据只用于分析与验证降耗效果，不改变抓取正确性。写入
    data/logs/review_timing_<brand>_<date>.csv，也可在 verbose 时打印。
    """
    model: str = ""
    requests: int = 0             # 实际发起的页面导航次数（不含缓存命中）
    cache_hits: int = 0           # 命中磁盘缓存、未真正导航的次数
    nav_seconds: float = 0.0      # 页面导航累计耗时（FetchResult.elapsed 之和）
    wait_seconds: float = 0.0     # 型号处理墙钟耗时（含限速等待）
    review_pages: int = 0         # 抓取的レビュー页数
    bbs_pages: int = 0            # 抓取的クチコミ列表页数
    threads_seen: int = 0         # 列表页发现的讨论主题数
    threads_entered: int = 0      # 实际进入解析的主题数
    threads_skipped: int = 0      # 因增量判断未更新而跳过的主题数
    fallback: str = ""            # review / bbs / none：命中评价的来源
    skipped_reason: str = ""      # 被预筛/已知无商品等跳过时的原因

    def as_row(self) -> dict:
        return {
            "model": self.model,
            "status": "",
            "requests": self.requests,
            "cache_hits": self.cache_hits,
            "nav_seconds": round(self.nav_seconds, 2),
            "wait_seconds": round(self.wait_seconds, 2),
            "review_pages": self.review_pages,
            "bbs_pages": self.bbs_pages,
            "threads_seen": self.threads_seen,
            "threads_entered": self.threads_entered,
            "threads_skipped": self.threads_skipped,
            "fallback": self.fallback,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class ModelResult:
    model: str
    item_id: str = ""
    release_text: str = ""
    release_year: int | None = None
    price: str = ""
    size: str = ""
    status: str = ""       # ok / no_item / no_release / not_target_year / no_reviews / blocked / failed / skipped_by_release_cache
    message: str = ""
    transient: bool = False  # 是否因网络/超时/拦截等瞬时故障失败
    reviews: list[RawReview] = field(default_factory=list)
    stats: ModelStats = field(default_factory=ModelStats)


@dataclass
class RunTuning:
    """一次运行的可调节流/等待/增量/缓存参数（可来自命令行或前端）。

    默认值保持与既有全局行为一致：不显式传参时行为不变。等待类参数为 None
    时表示沿用 config 默认（settle/scroll）。
    """
    settle_ms: int | None = None          # networkidle 等待上限（毫秒），评价/讨论页可显式调小
    scroll_passes: int | None = None      # 滚动次数，评价/讨论页可设 0
    scroll_wait_ms: int | None = None     # 每次滚动等待（毫秒）
    nav_timeout_ms: int | None = None     # 评价/讨论页导航超时（毫秒）
    entry_nav_timeout_ms: int | None = None  # 搜索/商品入口页更短的导航超时
    min_interval: float | None = None     # 覆盖域名级最小间隔（秒）
    page_cache: bool = False              # 是否启用浏览器页磁盘缓存（7.3）
    thread_incremental: bool = True       # 主题级增量（7.2）
    thread_recheck_days: int = 7          # 超期强制回查主题
    skip_known_no_item: bool = False      # 跳过已知无商品型号（7.6）
    release_cache: str = "off"            # off / prefer / refresh（7.1）
    release_cache_max_age_days: int = 30


# ==================== 型号清单 ====================

def load_models(models_csv: Path, brand: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        return [m.strip() for m in explicit if m.strip()]
    if not models_csv.exists():
        raise SystemExit(f"[ERROR] 型号清单不存在: {models_csv}")
    out: list[str] = []
    seen: set[str] = set()
    with models_csv.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if (row.get("brand_code") or "").strip() != brand:
                continue
            raw = (row.get("model_raw") or "").strip()
            model = raw.split("|")[0].strip()      # 合并写法取第一个用于搜索
            key = model.upper()
            if model and key not in seen:
                seen.add(key)
                out.append(model)
    return out


# ==================== 解析 ====================

def _clean(text: str) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


# 评论用户上传图片的 CDN 特征：revimgNN.kakaku.k-img.com/images/Review/...
# 站点 UI 图标走 img1.kakaku.k-img.com，必须靠该特征过滤，避免把图标当成评论图片。
_REVIEW_IMG_RE = re.compile(r"kakaku\.k-img\.com/images/(?:Review|Bbs)/", re.I)
# 评论用户视频：kakaku 站内 movie 链接或外链 youtube。
_REVIEW_VIDEO_RE = re.compile(r"(youtube\.com/watch|youtu\.be/|kakaku\.com/.*movie)", re.I)


def _dedup_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        it = (it or "").strip()
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _thumb_to_original(url: str) -> str:
    """把 kakaku 评论缩略图还原为原图：.../815636_s.jpg → .../815636.jpg。"""
    return re.sub(r"_s(\.(?:jpg|jpeg|png|gif|webp))$", r"\1", url, flags=re.I)


def _extract_media(block) -> tuple[list[str], list[str]]:
    """从一条评价/帖子块里提取用户上传的图片与视频链接。

    只保留评论 CDN 特征的图片，过滤站点 UI 图标；缩略图还原为原图。
    视频严格匹配站内 movie / youtube 链接，匹配不到则视为无视频，不臆造。
    """
    images: list[str] = []
    for src in block.attr_list("img", "src", limit=60):
        if src and _REVIEW_IMG_RE.search(src):
            images.append(_thumb_to_original(src))
    # 少数懒加载图片把真实地址放在 data-src。
    for src in block.attr_list("img", "data-src", limit=60):
        if src and _REVIEW_IMG_RE.search(src):
            images.append(_thumb_to_original(src))

    videos: list[str] = []
    for href in block.attr_list("a", "href", limit=60):
        if href and _REVIEW_VIDEO_RE.search(href):
            videos.append(href)
    for src in block.attr_list("iframe", "src", limit=20):
        if src and _REVIEW_VIDEO_RE.search(src):
            videos.append(src)
    for src in block.attr_list("video", "src", limit=10):
        if src:
            videos.append(src)
    for src in block.attr_list("video source", "src", limit=10):
        if src:
            videos.append(src)
    return _dedup_keep_order(images), _dedup_keep_order(videos)


def parse_reviews(dom) -> list[RawReview]:
    """レビュー一覧页当前页的所有结构化评价。"""
    if dom is None:
        return []
    out: list[RawReview] = []
    for block in dom.sub(".reviewBoxWt", limit=200):
        body = _clean(block.text("p.revEntryCont"))
        if not body:
            continue
        title = _clean(block.text(".reviewTitle a"))
        date = _clean(block.text("p.entryDate"))
        rating = _clean(block.text(".revRateBox table.total td"))
        if not rating:
            cls = block.attr(".revRateBox table.total td", "class")
            m = re.search(r"rate(\d+)", cls or "")
            rating = m.group(1) if m else ""
        url = block.attr("a[href*='ReviewCD=']", "href")
        # review_key 用 ReviewCD（站内评价唯一号）；取不到时退回日期串里的 [2032727-1]
        key = ""
        m = re.search(r"ReviewCD=(\d+)", url or "")
        if m:
            key = f"ReviewCD={m.group(1)}"
        else:
            m = re.search(r"\[(\d+-\d+)\]", date or "")
            if m:
                key = f"rev:{m.group(1)}"
        images, videos = _extract_media(block)
        out.append(RawReview(body=body, source="レビュー", rating=rating,
                             title=title, date=date, url=url, key=key,
                             image_urls=images, video_urls=videos))
    return out


def parse_bbs_posts(dom, page_url: str, thread_title: str = "") -> list[RawReview]:
    """讨论板页面（列表页或主题页）当前页的所有帖子/回帖。

    thread_title 非空时（进入具体主题）作为「网评标题」。列表页各帖分属不同主题，
    标题留空由调用方决定是否补。
    """
    if dom is None:
        return []
    out: list[RawReview] = []
    for block in dom.sub("div.box06", limit=200):
        body = ""
        for p in block.sub(".boxIn > p", limit=6):
            txt = _clean(p.self_text())
            if txt and "書込番号" not in txt and txt[-1:] != "点":
                body = txt
                break
        if not body:
            continue
        block_text = block.self_text() or ""
        m = re.search(r"(\d{4}/\d{1,2}/\d{1,2})", block_text)
        date = m.group(1) if m else ""
        author = _clean(block.text(".title a.impact05"))
        # review_key 用「書込番号」（帖子站内唯一号）
        key = ""
        m = re.search(r"書込番号[：:]\s*(\d+)", block_text)
        if m:
            key = f"bbs:{m.group(1)}"
        images, videos = _extract_media(block)
        out.append(RawReview(body=body, source="クチコミ", rating="",
                             title=thread_title, date=date, url=page_url,
                             author=author, key=key,
                             image_urls=images, video_urls=videos))
    return out


def _fetch_is_transient(res) -> bool:
    """404/其它确定性 4xx 不参与品牌熔断；网络、超时、429/5xx/拦截参与。"""
    if res.blocked:
        return True
    status = int(res.status or 0)
    if status == 404 or 400 <= status < 500:
        return status in (408, 429)
    if status <= 0:
        return True
    return 500 <= status <= 599


def _exception_is_transient(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(token in text for token in (
        "timeout", "timed out", "connection", "target closed", "playwright",
        "browser", "net::",
    ))


def _items_fingerprint(items: list[RawReview], extra: list[str] | None = None) -> str:
    values = list(extra or [])
    for item in items:
        values.append(item.key or hashlib.sha1(
            item.body.strip().encode("utf-8", "replace")
        ).hexdigest())
    return hashlib.sha1("\n".join(sorted(values)).encode("utf-8", "replace")).hexdigest()


# ==================== 单型号抓取 ====================

def _thread_recheck_expired(last_seen: str, recheck_days: int) -> bool:
    """主题状态是否已超过回查窗口（超期则强制进入，防止字段漂移导致漏抓）。"""
    if recheck_days <= 0:
        return True
    try:
        dt = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return (datetime.utcnow() - dt).days >= recheck_days


def crawl_model(adapter, fetcher, brand: str, model: str, target_year: int,
                max_pages: int, dig_threads: bool, verbose: bool,
                tuning: "RunTuning | None" = None,
                db=None, item_hint: str = "") -> ModelResult:
    tuning = tuning or RunTuning()
    result = ModelResult(model=model)
    stats = result.stats
    stats.model = model
    t_start = time.time()

    # 入口页（搜索/商品）用更短超时；评价/讨论页用较长超时。
    entry_nav = tuning.entry_nav_timeout_ms or tuning.nav_timeout_ms
    review_wait = dict(settle_ms=tuning.settle_ms, scroll_passes=tuning.scroll_passes,
                       scroll_wait_ms=tuning.scroll_wait_ms,
                       nav_timeout_ms=tuning.nav_timeout_ms)
    entry_wait = dict(settle_ms=tuning.settle_ms, scroll_passes=tuning.scroll_passes,
                      scroll_wait_ms=tuning.scroll_wait_ms,
                      nav_timeout_ms=entry_nav)

    def _track(res) -> None:
        stats.requests += 1
        try:
            stats.nav_seconds += float(getattr(res, "elapsed", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass

    # 1) 搜索定位 item id（不传业务锚点 wait_selector，避免翻到尽头被误判拦截）
    #    7.6：同批型号内命中过的 item_hint 可直接复用，跳过搜索页导航。
    item_id = (item_hint or "").strip()
    if not item_id:
        with open_dom(adapter, fetcher, adapter.search_url(model), **entry_wait) as (res, dom, html):
            _track(res)
            if res.blocked:
                result.status, result.message = "blocked", res.block_reason or "搜索被拦截"
                result.transient = True
                return result
            if not res.ok or dom is None:
                result.status, result.message = "failed", res.error or f"搜索 status={res.status}"
                result.transient = _fetch_is_transient(res)
                return result
            item_id = adapter.first_item_id(dom, want_model=model)
        if not item_id:
            result.status, result.message = "no_item", "搜索无匹配商品"
            return result
    result.item_id = item_id

    # 2) 商品页：发售日 + 价格 + 尺寸
    with open_dom(adapter, fetcher, adapter.item_url(item_id), **entry_wait) as (res, dom, html):
        _track(res)
        if res.blocked:
            result.status, result.message = "blocked", res.block_reason or "商品页被拦截"
            result.transient = True
            return result
        if not res.ok or dom is None:
            result.status, result.message = "failed", res.error or f"商品页 status={res.status}"
            result.transient = _fetch_is_transient(res)
            return result
        release_text = adapter.release_text(dom)
        result.price = adapter.lowest_price(dom)
        page_text = dom.self_text() if dom else ""
    result.release_text = release_text
    result.release_year = adapter.release_year(release_text)
    result.size = adapter.size_inch(model, page_text)
    if not release_text:
        result.status, result.message = "no_release", "未找到发售日"
        return result
    if result.release_year != target_year:
        result.status = "not_target_year"
        result.message = f"上市年份={result.release_year}，非 {target_year}"
        return result

    page_limit = min(max(1, int(max_pages)), config.MAX_REVIEW_PAGES)
    collected: list[RawReview] = []
    seen: set[str] = set()

    def _add(items: list[RawReview]) -> int:
        n = 0
        for it in items:
            key = it.key or f"body:{hashlib.sha1(
                it.body.strip().encode("utf-8", "replace")
            ).hexdigest()}"
            if key in seen:
                continue
            seen.add(key)
            collected.append(it)
            n += 1
        return n

    # 3) 优先 レビュー，翻页抓全；同时防重复 URL/重复页内容。
    review_ok = False
    review_transient = False
    review_urls: set[str] = set()
    review_fingerprints: set[str] = set()
    for page in range(1, page_limit + 1):
        rurl = adapter.review_url(item_id, page)
        if rurl in review_urls:
            break
        review_urls.add(rurl)
        with open_dom(adapter, fetcher, rurl, **review_wait) as (res, dom, html):
            _track(res)
            if res.status == 404:
                break
            if res.blocked:
                result.status, result.message = "blocked", res.block_reason or "レビュー页被拦截"
                result.transient = True
                return result
            if not res.ok or dom is None:
                review_transient = review_transient or _fetch_is_transient(res)
                break
            items = parse_reviews(dom)
        stats.review_pages += 1
        if not items:
            break
        fingerprint = _items_fingerprint(items)
        if fingerprint in review_fingerprints:
            break
        review_fingerprints.add(fingerprint)
        review_ok = True
        new = _add(items)
        if verbose:
            print(f"      レビュー p{page}: {len(items)} 条，新增 {new}")
        if new == 0:
            break
    if review_ok:
        stats.fallback = "review"

    # 4) レビュー为空则回退 クチコミ
    #    先取讨论板列表页的主题清单，再优先逐个进入主题抓全（帖+回帖，带主题标题）；
    #    主题标题填「网评标题」。为保证标题版本优先，先抓主题，最后用列表页兜底
    #    补齐未归入任何主题的散帖（此时标题留空是合理的）。
    bbs_transient = False
    thread_transient = False
    if not review_ok:
        # 7.2：主题级增量需要历史主题状态；仅在开启且有 db 时启用。
        use_incremental = bool(tuning.thread_incremental and db is not None)
        prior_states: dict = db.thread_states(item_id) if use_incremental else {}
        thread_urls: list[tuple] = []   # (url, title, post_count, last_key)
        thread_url_seen: set[str] = set()
        landing_doms: list[tuple[str, list[RawReview]]] = []
        bbs_urls: set[str] = set()
        bbs_fingerprints: set[str] = set()
        for page in range(1, page_limit + 1):
            burl = adapter.bbs_url(item_id, page)
            if burl in bbs_urls:
                break
            bbs_urls.add(burl)
            with open_dom(adapter, fetcher, burl, **review_wait) as (res, dom, html):
                _track(res)
                if res.status == 404:
                    break
                if res.blocked:
                    result.status, result.message = "blocked", res.block_reason or "クチコミ页被拦截"
                    result.transient = True
                    return result
                if not res.ok or dom is None:
                    bbs_transient = bbs_transient or _fetch_is_transient(res)
                    break
                page_threads = (adapter.bbs_threads(dom, with_meta=True)
                                if dig_threads else [])
                landing_items = parse_bbs_posts(dom, burl)
            stats.bbs_pages += 1
            fingerprint = _items_fingerprint(
                landing_items, [t[0] for t in page_threads]
            )
            if fingerprint in bbs_fingerprints:
                break
            bbs_fingerprints.add(fingerprint)
            for t in page_threads:
                turl = t[0]
                if turl in thread_url_seen or len(thread_urls) >= config.MAX_REVIEW_THREADS:
                    continue
                thread_url_seen.add(turl)
                # 兼容 with_meta 返回四元组
                title = t[1] if len(t) > 1 else ""
                post_count = t[2] if len(t) > 2 else 0
                last_key = t[3] if len(t) > 3 else ""
                thread_urls.append((turl, title, post_count, last_key))
            if not landing_items and not page_threads:
                break
            landing_doms.append((burl, landing_items))
            if verbose:
                print(f"      クチコミ列表 p{page}: 帖 {len(landing_items)}，主题 {len(page_threads)}")

        stats.threads_seen = len(thread_urls)

        # 4a) 先进入各讨论主题抓全（标题优先）。
        #     7.2：仅当「有历史状态 + 本次解析到的帖数>0 且与历史一致 + 未超回查窗口」
        #     才跳过；帖数未知(0) 一律进入，保证不漏。
        if dig_threads:
            for turl, ttitle, post_count, _last_key in thread_urls:
                prior = prior_states.get(turl)
                if (use_incremental and prior is not None and post_count > 0
                        and int(prior["post_count"] or 0) == post_count
                        and not _thread_recheck_expired(
                            prior["last_seen"], tuning.thread_recheck_days)):
                    stats.threads_skipped += 1
                    if verbose:
                        print(f"      主题「{ttitle[:16]}」: 帖数未变({post_count})，增量跳过")
                    continue
                with open_dom(adapter, fetcher, turl, **review_wait) as (res, dom, html):
                    _track(res)
                    if res.blocked:
                        result.status, result.message = "blocked", res.block_reason or "主题页被拦截"
                        result.transient = True
                        return result
                    if not res.ok or dom is None:
                        thread_transient = thread_transient or _fetch_is_transient(res)
                        continue
                    items = parse_bbs_posts(dom, turl, thread_title=ttitle)
                stats.threads_entered += 1
                new = _add(items)
                # 记录主题状态，供下次增量比较（best-effort）。
                if use_incremental:
                    last_post = ""
                    for it in items:
                        if it.key:
                            last_post = it.key
                    db.upsert_thread_state(
                        item_id, turl, thread_title=ttitle,
                        last_post_key=last_post,
                        post_count=post_count if post_count > 0 else len(items))
                if verbose and items:
                    print(f"      主题「{ttitle[:16]}」: {len(items)} 帖，新增 {new}")

        # 4b) 列表页散帖兜底（未被任何主题覆盖的才会新增）
        for burl, landing_items in landing_doms:
            _add(landing_items)
        if collected:
            stats.fallback = "bbs"

    stats.wait_seconds = time.time() - t_start

    if not collected:
        result.status = "no_reviews"
        if review_transient or bbs_transient or thread_transient:
            result.transient = True
            result.message = "レビュー/クチコミ存在瞬时请求失败，已停止并保留回退结果"
        else:
            result.message = "无レビュー与クチコミ"
        return result
    result.reviews = collected
    if review_transient or bbs_transient or thread_transient:
        result.status = "failed"
        result.transient = True
        result.message = "已采集部分评价，但后续页面发生瞬时失败，结果不完整"
    else:
        result.status = "ok"
    return result


# ==================== 记录转换 ====================

def to_records(brand: str, r: ModelResult) -> list[ReviewRecord]:
    display = BRAND_DISPLAY.get(brand, brand)
    country = SiteRegistry.get("kakaku_jp").country
    channel = SiteRegistry.get("kakaku_jp").channel
    release_disp = SiteRegistry.get("kakaku_jp").release_display(r.release_text)
    out: list[ReviewRecord] = []
    for rv in r.reviews:
        out.append(ReviewRecord(
            country=country,
            brand=display,
            model=r.model,
            channel=channel,
            size=r.size,
            rating=rv.rating,
            title=rv.title,
            body=rv.body,
            helpful="",
            review_time=rv.date or release_disp,
            review_url=rv.url,
            image_count=len(rv.image_urls),
            image_urls=" | ".join(rv.image_urls),
            has_video=("是" if rv.video_urls else "否"),
            video_urls=" | ".join(rv.video_urls),
            item_id=r.item_id,
            price=r.price,
        ))
    return out


# ==================== 入库 ====================

def _review_rating(raw: str) -> float | None:
    try:
        return float(raw) if raw not in ("", None) else None
    except (TypeError, ValueError):
        return None


def save_to_db(db: Database, adapter, site_id: int, run_id: int | None,
               brand: str, r: ModelResult) -> int | None:
    """把一个型号的评价结果写库，返回 product_id（无商品时 None）。

    落点：
      - product            ：kakaku 机型登记为商品，sku=item_id
      - review             ：评价明细，按 (product_id, review_key) 增量去重
      - kakaku_task_status ：型号级状态，空/失败不静默

    review_key：レビュー 用 `ReviewCD=NNN`，クチコミ 用 `bbs:書込番号`；
    两者都取不到时退回 `hash:<正文前80字的稳定哈希>`，保证仍能去重且不会误合并。
    """
    display = BRAND_DISPLAY.get(brand, brand)
    if run_id is not None and (r.status in {"failed", "blocked"} or r.transient):
        error_url = adapter.item_url(r.item_id) if r.item_id else adapter.search_url(r.model)
        error_kind = "blocked" if r.status == "blocked" else (
            "transient" if r.transient else "failed"
        )
        try:
            db.log_error(run_id, error_url, "review", error_kind,
                         r.message or r.status)
        except Exception:
            # 失败审计不能阻塞 CSV/XLSX 和型号状态的 best-effort 落盘。
            pass
    product_id: int | None = None
    total = 0
    new_count = 0

    if r.item_id:
        product = Product(
            site_code=adapter.code,
            sku=r.item_id,
            url=adapter.item_url(r.item_id),
            title=f"{display} {r.model}".strip(),
            brand=display,
            model=r.model,
            category="TV",
            size=r.size,
        )
        product_id = db.upsert_product(product, site_id)

        reviews: list[Review] = []
        for rv in r.reviews:
            key = rv.key
            if not key:
                digest = hashlib.sha1(rv.body[:80].encode("utf-8", "replace")).hexdigest()[:16]
                key = f"hash:{digest}"
            reviews.append(Review(
                review_key=key,
                rating=_review_rating(rv.rating),
                title=rv.title,
                body=rv.body,
                author=rv.author,
                review_date=rv.date,
                review_url=rv.url,
                image_urls=list(rv.image_urls),
                video_urls=list(rv.video_urls),
            ))
        total = len(reviews)
        if reviews:
            new_count = db.add_reviews(product_id, reviews)

    db.record_kakaku_status(
        task="review", brand=brand, model=r.model, status=r.status,
        run_id=run_id, brand_name=display, item_id=r.item_id,
        product_id=product_id, release_text=r.release_text,
        release_year=r.release_year, size=r.size,
        row_count=total, new_count=new_count, message=r.message,
    )
    return product_id


# ==================== 主流程 ====================

def make_fetcher(adapter, min_interval: float | None = None,
                 rate_limiter: "RateLimiter | None" = None):
    """构造网评抓取用的浏览器 fetcher。

    min_interval 显式传入时覆盖站点建议间隔（7.4）；rate_limiter 传入时复用同一
    限速器实例（7.5 多品牌并发共享，保证不放大单域请求频率）。
    """
    if rate_limiter is None:
        interval = (float(min_interval) if min_interval is not None
                    else max(config.MIN_INTERVAL, adapter.suggested_interval))
        rate_limiter = RateLimiter(min_interval=interval)
    return BrowserFetcher(rate_limiter=rate_limiter,
                          detector=BlockDetector(), cache=DiskCache())


def _write_timing_csv(brand: str, results: list[ModelResult], verbose: bool) -> None:
    """7.8：把每型号的抓取度量写到 data/logs/review_timing_<brand>_<date>.csv。

    纯观测用途，写失败不影响主流程。列包含 status + ModelStats 各字段。
    """
    if not results:
        return
    stamp = datetime.now().strftime("%Y%m%d")
    out = Path(config.LOG_DIR) / f"review_timing_{brand}_{stamp}.csv"
    fields = ["model", "status", "requests", "cache_hits", "nav_seconds",
              "wait_seconds", "review_pages", "bbs_pages", "threads_seen",
              "threads_entered", "threads_skipped", "fallback", "skipped_reason"]
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in results:
                row = r.stats.as_row()
                row["status"] = r.status
                row["model"] = r.model
                w.writerow(row)
        if verbose:
            total_req = sum(r.stats.requests for r in results)
            total_nav = sum(r.stats.nav_seconds for r in results)
            skipped = sum(r.stats.threads_skipped for r in results)
            print(f"[TIMING] {out} 型号={len(results)} 总请求={total_req} "
                  f"导航累计={total_nav:.1f}s 主题增量跳过={skipped}")
    except OSError as e:
        if verbose:
            print(f"[TIMING] 写入失败(忽略): {type(e).__name__}: {e}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="価格.com 用户评价抓取（按型号，仅指定上市年份，通用网评模板）")
    p.add_argument("--brand", default="hisense_jp", help="品牌 code，默认 hisense_jp")
    p.add_argument("--brands", nargs="*",
                   help="多个品牌 code（7.5 多品牌并发用）；给出时覆盖 --brand，"
                        "每个品牌各自导出/入库，配合 --concurrency 并发")
    p.add_argument("--concurrency", type=int, default=1,
                   help="并发抓取的品牌数（仅多品牌时生效，默认 1=串行）；"
                        "所有并发线程共享同一域名级限速器，不放大单域请求频率")
    p.add_argument("--models-csv", default=str(DEFAULT_MODELS_CSV),
                   help=f"型号清单 CSV，默认 {DEFAULT_MODELS_CSV}")
    p.add_argument("--models", nargs="*", help="直接指定型号（覆盖 CSV）")
    p.add_argument("--year", type=int, default=2026, help="只抓该上市年份的机型，默认 2026")
    p.add_argument("--limit-models", type=int, default=0, help="最多处理多少个型号（0=不限）")
    p.add_argument("--max-pages", type=int, default=20, help="评价/讨论板列表最多翻页数")
    p.add_argument("--no-threads", action="store_true", help="クチコミ只抓列表页，不进入各讨论主题")
    p.add_argument("--format", choices=("xlsx", "csv", "all"), default="all")
    p.add_argument("--out", help="输出路径主干；缺省写到 data/ 带时间戳")
    p.add_argument("--save-db", action="store_true",
                   help="同时写入数据库：product / review / kakaku_task_status"
                        "（评价按 review_key 增量去重，供后端 API 查询）")
    p.add_argument("--db", help="SQLite 路径，缺省用 OVERSEAS_DB_PATH 或 data/overseas.db")
    p.add_argument("--release-map", help="额外输出「型号→上市时间」JSON（供 SPEC 上市时间列）；"
                   "缺省写到 data/发售日_<brand>.json")
    p.add_argument("--all-years", action="store_true",
                   help="发售日映射收录所有年份的机型（评价仍只抓目标年份）")
    p.add_argument("--quiet", action="store_true")

    # ---- 翻译/AI（可选） ----
    g_ai = p.add_argument_group("翻译/AI（可选）")
    g_ai.add_argument(
        "--translate",
        action="store_true",
        help="勾选后翻译网评正文；不传则不调用翻译回调",
    )
    g_ai.add_argument(
        "--extract-pros",
        action="store_true",
        help="勾选后提炼网评优点；需使用已配置 xinghai 引擎",
    )
    g_ai.add_argument(
        "--extract-cons",
        action="store_true",
        help="勾选后提炼网评缺点；需使用已配置 xinghai 引擎",
    )
    g_ai.add_argument(
        "--translate-engine",
        choices=("nllb", "argos", "xinghai"),
        default="nllb",
        help="翻译/AI 引擎：nllb（默认）、argos 或 xinghai-ultra（失败回退离线引擎）",
    )

    # ---- 7.4 每页等待时间可控（前端可传）；不传则沿用全局默认 ----
    g_wait = p.add_argument_group("等待/节流（降耗，可前端控制）")
    g_wait.add_argument("--settle-ms", type=int, default=None,
                        help="评价/讨论页 networkidle 等待上限(毫秒)，缺省沿用 OVERSEAS_SETTLE")
    g_wait.add_argument("--scroll-passes", type=int, default=None,
                        help="评价/讨论页滚动次数，缺省沿用 OVERSEAS_SCROLL_PASSES；建议 0")
    g_wait.add_argument("--scroll-wait-ms", type=int, default=None,
                        help="每次滚动等待(毫秒)，缺省沿用 OVERSEAS_SCROLL_WAIT")
    g_wait.add_argument("--nav-timeout-ms", type=int, default=None,
                        help="评价/讨论页导航超时(毫秒)，缺省沿用 OVERSEAS_NAV_TIMEOUT")
    g_wait.add_argument("--entry-nav-timeout-ms", type=int, default=None,
                        help="搜索/商品入口页更短的导航超时(毫秒)，缺省与评价页一致")
    g_wait.add_argument("--min-interval", type=float, default=None,
                        help="域名级最小抓取间隔(秒)，缺省 max(OVERSEAS_MIN_INTERVAL, 站点建议值)")

    # ---- 7.1 目标年份预筛 ----
    g_pre = p.add_argument_group("目标年份预筛（7.1）")
    g_pre.add_argument("--release-cache", choices=("off", "prefer", "refresh"),
                       default="off",
                       help="off=每型号都访问站点确认年份(默认)；prefer=用发售日/库缓存"
                            "跳过明确非目标年份；refresh=忽略缓存并回写")
    g_pre.add_argument("--release-cache-max-age-days", type=int, default=30,
                       help="prefer 模式下缓存最大有效天数，超期回退为访问站点")

    # ---- 7.2 讨论主题增量 ----
    g_inc = p.add_argument_group("讨论主题增量（7.2）")
    g_inc.add_argument("--thread-incremental", choices=("on", "off"), default="off",
                       help="on=主题帖数未变则跳过进入(需 --save-db 记录状态)；默认 off")
    g_inc.add_argument("--thread-recheck-days", type=int, default=7,
                       help="主题状态超过该天数强制回查一次，防止字段漂移")

    # ---- 7.6 失败路径压缩 ----
    g_fail = p.add_argument_group("失败路径压缩（7.6）")
    g_fail.add_argument("--skip-known-no-item", action="store_true",
                        help="跳过历史确认过 no_item 的型号(需库中已有记录)，只写审计不访问站点")

    # ---- 7.3 浏览器入口页结构化缓存 ----
    g_cache = p.add_argument_group("入口页缓存（7.3）")
    g_cache.add_argument("--page-cache", choices=("off", "on"), default="off",
                         help="on=对搜索/商品入口页启用结构化缓存(型号→item_id/发售日/价格/尺寸)，"
                              "同日重跑近乎零成本；默认 off，正式周度不依赖缓存")
    g_cache.add_argument("--page-cache-ttl-hours", type=float, default=24.0,
                         help="入口页缓存有效期(小时)，默认 24")
    return p


def _tuning_from_args(args) -> "RunTuning":
    return RunTuning(
        settle_ms=args.settle_ms,
        scroll_passes=args.scroll_passes,
        scroll_wait_ms=args.scroll_wait_ms,
        nav_timeout_ms=args.nav_timeout_ms,
        entry_nav_timeout_ms=args.entry_nav_timeout_ms,
        min_interval=args.min_interval,
        page_cache=(args.page_cache == "on"),
        thread_incremental=(args.thread_incremental == "on"),
        thread_recheck_days=max(0, int(args.thread_recheck_days)),
        skip_known_no_item=bool(args.skip_known_no_item),
        release_cache=args.release_cache,
        release_cache_max_age_days=max(0, int(args.release_cache_max_age_days)),
    )


def _entry_cache_path(brand: str) -> Path:
    return Path(config.CACHE_DIR) / f"kakaku_entry_{brand}.json"


def _load_entry_cache(brand: str) -> dict:
    p = _entry_cache_path(brand)
    if not p.exists():
        return {}
    try:
        with p.open(encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_entry_cache(brand: str, cache: dict) -> None:
    p = _entry_cache_path(brand)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def crawl_model_with_prefilter(adapter, fetcher, brand, model, args, tuning,
                               db, verbose, release_lookup, no_item_set,
                               search_memo, entry_cache):
    """在 crawl_model 外套一层 7.1/7.6/7.3 的跳过与提示逻辑。

    返回 ModelResult。所有跳过都会带明确 status/stats.skipped_reason，型号总数守恒。
    """
    key = model.upper()

    # 7.6：历史确认无对应商品的型号，直接跳过（不访问站点）。
    if tuning.skip_known_no_item and key in no_item_set:
        r = ModelResult(model=model, status="skipped_known_no_item",
                        message="已知无对应商品(历史 no_item)，跳过")
        r.stats.model = model
        r.stats.skipped_reason = "known_no_item"
        return r

    # 7.1：命中缓存且明确非目标年份 → 跳过；命中且目标年份 → 复用 item_id 跳过搜索页。
    item_hint = ""
    if tuning.release_cache in ("prefer",):
        info = _lookup_release(release_lookup, entry_cache, key,
                               tuning.release_cache_max_age_days)
        if info is not None:
            ry = info.get("release_year")
            if ry is not None and int(ry) != int(args.year):
                r = ModelResult(model=model, status="skipped_by_release_cache",
                                release_year=int(ry),
                                message=f"缓存发售年份={ry}，非 {args.year}，跳过")
                r.stats.model = model
                r.stats.skipped_reason = "release_cache_non_target"
                return r
            if ry is not None and int(ry) == int(args.year) and info.get("item_id"):
                item_hint = str(info["item_id"])   # 目标年份：复用 item_id 跳过搜索页

    # 进程内搜索结果记忆（7.6）：同一关键词此前搜到的 item_id 直接复用。
    if not item_hint and key in search_memo:
        item_hint = search_memo[key]

    r = crawl_model(adapter, fetcher, brand, model, args.year,
                    args.max_pages, not args.no_threads, verbose,
                    tuning=tuning, db=db, item_hint=item_hint)

    # 回写进程内记忆与入口缓存（7.3）：拿到 item_id 且非缓存跳过时更新。
    if r.item_id:
        search_memo[key] = r.item_id
        if tuning.page_cache or tuning.release_cache in ("prefer", "refresh"):
            entry_cache[key] = {
                "item_id": r.item_id,
                "release_text": r.release_text,
                "release_year": r.release_year,
                "size": r.size,
                "price": r.price,
                "ts": time.time(),
            }
    return r


def _lookup_release(release_lookup: dict, entry_cache: dict, key: str,
                    max_age_days: int):
    """合并「入口 JSON 缓存 + 库内 release_year」两处来源，返回最可信的一条。

    entry_cache（本地 JSON，带 ts）优先且受 max_age_days 约束；否则回退库内记录
    （库内无 ts，按存在即用；库内是历史抓取沉淀，通常仍可信）。找不到返回 None。
    """
    now = time.time()
    ec = entry_cache.get(key)
    if ec and ec.get("release_year") is not None:
        ts = ec.get("ts") or 0
        if max_age_days <= 0 or (now - ts) <= max_age_days * 86400:
            return {"release_year": ec.get("release_year"),
                    "item_id": ec.get("item_id", "")}
    lk = release_lookup.get(key)
    if lk and lk.get("release_year") is not None:
        return {"release_year": lk.get("release_year"),
                "item_id": lk.get("item_id", "")}
    return None


def run_brand(args, brand: str, adapter, tuning: "RunTuning", verbose: bool,
              shared_rate: "RateLimiter | None" = None,
              db_lock=None) -> int:
    """抓取单个品牌，返回该品牌退出码（0 正常 / 1 品牌熔断 / 2 无型号）。

    多品牌并发时：shared_rate 传入同一域名级限速器（不放大单域频率）；db_lock
    串行化所有数据库写入（SQLite 单写）。每个品牌用独立 Database 连接，避免跨
    线程复用同一 sqlite3 连接。
    """
    models = load_models(Path(args.models_csv), brand, args.models)
    if args.limit_models > 0:
        models = models[:args.limit_models]
    if not models:
        print(f"[ERROR] 品牌 {brand} 没有可抓取的型号")
        return 2
    print(f"[KAKAKU] 品牌={brand} 型号数={len(models)} 目标上市年份={args.year} "
          f"进入讨论主题={not args.no_threads} release_cache={tuning.release_cache} "
          f"thread_incremental={tuning.thread_incremental} page_cache={tuning.page_cache}")

    import threading as _threading
    lock = db_lock or _threading.Lock()

    # 入库准备（--save-db）
    db: Database | None = None
    site_id: int | None = None
    run_id: int | None = None
    if args.save_db:
        db = Database(args.db)
        db.init_schema()
        with lock:
            site_id = db.upsert_site(adapter.code, adapter.name, adapter.base_url,
                                     adapter.protection)
            run_id = db.start_run("kakaku_review", adapter.code,
                                  {"brand": brand, "year": args.year,
                                   "models": len(models)})
        print(f"[DB] {db.path} site_id={site_id} run_id={run_id}")

    # 7.1/7.6/7.3 预筛数据来源：库内 release_year、历史 no_item、本地入口缓存。
    release_lookup: dict = {}
    no_item_set: set[str] = set()
    if db is not None:
        with lock:
            if tuning.release_cache == "prefer":
                release_lookup = db.release_year_lookup(brand=brand, task="review")
            if tuning.skip_known_no_item:
                no_item_set = db.known_no_item_models(brand=brand, task="review")
    entry_cache = ({} if tuning.release_cache == "refresh"
                   else _load_entry_cache(brand))
    search_memo: dict[str, str] = {}

    fetcher = make_fetcher(adapter, min_interval=tuning.min_interval,
                           rate_limiter=shared_rate)
    results: list[ModelResult] = []
    all_records: list[ReviewRecord] = []
    consecutive_transient_failures = 0
    threshold_triggered = False

    def _persist_result(r: ModelResult, label: str) -> None:
        results.append(r)
        all_records.extend(to_records(brand, r))
        if db is not None and site_id is not None:
            try:
                with lock:
                    save_to_db(db, adapter, site_id, run_id, brand, r)
            except Exception as e:          # 入库失败不影响文件输出
                print(f"      [WARN] 入库失败 {r.model}: {type(e).__name__}: {e}")
                if run_id is not None:
                    try:
                        with lock:
                            db.log_error(run_id, adapter.search_url(r.model), "review",
                                         "db", f"{type(e).__name__}: {e}")
                    except Exception:
                        pass
        if verbose:
            print(f"      [{brand}] {label} → {r.status} {r.message} 评价={len(r.reviews)} "
                  f"item={r.item_id} 价格={r.price} 尺寸={r.size} 发售={r.release_text}")

    try:
        for i, model in enumerate(models, 1):
            if verbose:
                print(f"[{i}/{len(models)}] {model} ...")
            try:
                r = crawl_model_with_prefilter(
                    adapter, fetcher, brand, model, args, tuning, db, verbose,
                    release_lookup, no_item_set, search_memo, entry_cache)
            except Exception as e:
                r = ModelResult(model=model, status="failed",
                                message=f"{type(e).__name__}: {e}",
                                transient=_exception_is_transient(e))
                r.stats.model = model
            _persist_result(r, "结果")

            if r.transient:
                consecutive_transient_failures += 1
            else:
                # 成功、no_item、not_target_year、no_release、各类 skipped 等确定性
                # 结果不应该把品牌熔断计数带到下一个型号。
                consecutive_transient_failures = 0
            if consecutive_transient_failures < config.MAX_CONSECUTIVE_MODEL_FAILURES:
                continue

            threshold_triggered = True
            message = (
                f"连续 {config.MAX_CONSECUTIVE_MODEL_FAILURES} 个型号发生瞬时失败，"
                "品牌熔断；剩余型号未执行"
            )
            if db is not None and run_id is not None:
                try:
                    db.log_error(run_id, f"brand:{brand}", "review",
                                 "threshold_skip", message)
                except Exception:
                    pass
            for skipped_model in models[i:]:
                skipped = ModelResult(
                    model=skipped_model,
                    status="failed",
                    message="brand_threshold_skip: " + message,
                )
                skipped.stats.model = skipped_model
                _persist_result(skipped, "跳过")
            break
    finally:
        fetcher.close()

    # 7.3：回写入口缓存（仅当启用缓存或预筛，避免无谓写盘）。
    if tuning.page_cache or tuning.release_cache in ("prefer", "refresh"):
        _save_entry_cache(brand, entry_cache)

    # 7.8：写每型号耗时/请求度量，供分析与验证降耗效果（不影响抓取正确性）。
    _write_timing_csv(brand, results, verbose)

    from collections import Counter
    status_counts = Counter(r.status for r in results)
    ok = [r for r in results if r.status == "ok"]
    print(f"\n[汇总] 型号={len(results)} 命中评价型号={len(ok)} "
          f"评价总行数={len(all_records)} 状态={dict(status_counts)}")
    for r in results:
        if r.status != "ok":
            print(f"  - {r.model}: {r.status} {r.message}")

    # 结束运行记录并汇报入库结果
    if db is not None:
        with lock:
            if run_id is not None:
                db.finish_run(
                    run_id,
                    "failed" if threshold_triggered else "completed",
                    len(ok),
                    len(results) - len(ok),
                    f"brand={brand} rows={len(all_records)} "
                    f"threshold_triggered={threshold_triggered}",
                )
            counts = db.kakaku_status_counts(task="review", brand=brand)
        print(f"[DB] {brand} 评论状态入库统计={counts}")
        db.close()

    # 翻译/AI 默认不启用；三个字段由独立 CLI 选项控制，未选择的回调不会执行。
    hooks: AiHooks = NULL_HOOKS
    ai_requested = args.translate or args.extract_pros or args.extract_cons
    if ai_requested and all_records:
        try:
            from overseas.review_translation import build_translation_hooks
            base_hooks, translator = build_translation_hooks(engine=args.translate_engine)
            hooks = AiHooks(
                translate=base_hooks.translate if args.translate else None,
                extract_pros=base_hooks.extract_pros if args.extract_pros else None,
                extract_cons=base_hooks.extract_cons if args.extract_cons else None,
            )
            labels = {
                "nllb": "本地 NLLB",
                "argos": "本地 Argos",
                "xinghai": "HiGPT xinghai-ultra",
            }
            selected = []
            if args.translate:
                selected.append("翻译")
            if args.extract_pros:
                selected.append("提炼优点")
            if args.extract_cons:
                selected.append("提炼缺点")
            print(
                f"[AI] 已选择：{'、'.join(selected)}；引擎={labels[args.translate_engine]}，"
                f"缓存上限={translator.cache_size}"
            )
            unavailable = []
            if args.extract_pros and base_hooks.extract_pros is None:
                unavailable.append("提炼优点")
            if args.extract_cons and base_hooks.extract_cons is None:
                unavailable.append("提炼缺点")
            if unavailable:
                print(
                    f"[AI] 当前引擎未提供：{'、'.join(unavailable)}；"
                    "优缺点提炼请选择已配置的 xinghai 引擎"
                )
        except Exception as exc:
            # 翻译/AI 不可用不丢失原始网评；明确写日志，未成功的列保持空白。
            print(f"[AI] 不可用，跳过所选处理：{type(exc).__name__}: {exc}")
    elif ai_requested:
        print("[AI] 本次没有可导出的网评，跳过模型加载")

    stamp = datetime.now().strftime("%Y%m%d")
    # 多品牌模式下忽略 --out（每品牌各写默认文件，避免互相覆盖）。
    multi = bool(getattr(args, "_multi_brand", False))
    base = (Path(args.out) if (args.out and not multi)
            else (PROJECT_ROOT / "data" / f"网评汇总_{brand}_kakaku_{stamp}"))
    # 先写 CSV 再写 XLSX：即使 XLSX 因文件被 Excel 占用失败，CSV 也已落盘。
    formats = ("csv", "xlsx") if args.format == "all" else (args.format,)
    for fmt in formats:
        path = base if base.suffix.lower() == f".{fmt}" else base.with_suffix(f".{fmt}")
        try:
            if fmt == "xlsx":
                write_xlsx(path, all_records, hooks)
            else:
                write_csv(path, all_records, hooks)
            print(f"[OUT] {fmt}: {path} rows={len(all_records)}")
        except PermissionError:
            # 目标文件被占用（如在 Excel 中打开）：改写带时间戳的备用文件，不丢数据。
            alt = path.with_name(f"{path.stem}_{datetime.now():%H%M%S}{path.suffix}")
            if fmt == "xlsx":
                write_xlsx(alt, all_records, hooks)
            else:
                write_csv(alt, all_records, hooks)
            print(f"[OUT] {fmt}: 原文件被占用，已改写 {alt} rows={len(all_records)}")

    # 额外输出「型号→上市时间」映射，供 SPEC 导出增加「上市时间」行（用于上市时间筛选）。
    # 收录所有能读到发售日的机型（含非目标年份），只要有 release_text 即记录。
    import json as _json
    release_map: dict[str, dict] = {}
    for r in results:
        if not r.release_text:
            continue
        release_map[r.model] = {
            "release": adapter.release_display(r.release_text),
            "release_raw": r.release_text,
            "year": r.release_year,
            "item_id": r.item_id,
        }
    rel_path = (Path(args.release_map) if (args.release_map and not multi)
                else (PROJECT_ROOT / "data" / f"发售日_{brand}.json"))
    rel_path.parent.mkdir(parents=True, exist_ok=True)
    # 与已有映射合并再写：用 --models 只跑子集时不会把其它型号的发售日冲掉。
    merged: dict[str, dict] = {}
    if rel_path.exists():
        try:
            with rel_path.open(encoding="utf-8") as handle:
                old = _json.load(handle)
            if isinstance(old, dict):
                merged.update(old)
        except (OSError, _json.JSONDecodeError):
            pass
    merged.update(release_map)
    with rel_path.open("w", encoding="utf-8") as handle:
        _json.dump(merged, handle, ensure_ascii=False, indent=2)
    print(f"[OUT] release-map: {rel_path} 本次={len(release_map)} 累计={len(merged)}")
    return 1 if threshold_triggered else 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verbose = not args.quiet
    config.ensure_dirs()
    tuning = _tuning_from_args(args)

    try:
        adapter = SiteRegistry.get("kakaku_jp")
    except KeyError as e:
        print(f"[ERROR] {e}")
        return 2

    brands = [b.strip() for b in (args.brands or []) if b.strip()]
    if not brands:
        # 单品牌：完全沿用既有行为。
        return run_brand(args, args.brand, adapter, tuning, verbose)

    # 多品牌（7.5）：共享域名级限速器 + 数据库单写锁；concurrency 控制并发品牌数。
    args._multi_brand = True
    import threading as _threading
    interval = (float(tuning.min_interval) if tuning.min_interval is not None
                else max(config.MIN_INTERVAL, adapter.suggested_interval))
    shared_rate = RateLimiter(min_interval=interval)
    db_lock = _threading.Lock()
    concurrency = max(1, int(args.concurrency))
    print(f"[KAKAKU] 多品牌={brands} 并发={concurrency} "
          f"共享限速间隔={interval:.1f}s")

    codes: dict[str, int] = {}
    if concurrency <= 1:
        for b in brands:
            codes[b] = run_brand(args, b, adapter, tuning, verbose,
                                 shared_rate=shared_rate, db_lock=db_lock)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futs = {ex.submit(run_brand, args, b, adapter, tuning, verbose,
                              shared_rate, db_lock): b for b in brands}
            for fut in futs:
                b = futs[fut]
                try:
                    codes[b] = fut.result()
                except Exception as e:      # 单品牌异常不影响其它品牌
                    print(f"[ERROR] 品牌 {b} 异常: {type(e).__name__}: {e}")
                    codes[b] = 1
    print(f"[KAKAKU] 多品牌完成 退出码={codes}")
    return 0 if all(c == 0 for c in codes.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())