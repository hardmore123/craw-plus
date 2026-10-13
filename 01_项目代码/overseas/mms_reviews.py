# -*- coding: utf-8 -*-
"""MediaMarkt / Saturn / MediaWorld（MMS 集团 PWA）评价采集。

背景（2026-10 实测 mediamarkt_de，US 出口可达）：
- 评价底层是 BazaarVoice，但 BV 公开 BFD 接口 401；站方用自家 GraphQL 包了一层：
      GET {base}/api/v1/graphql?operationName=GetProductReviews
          &variables={"reviewPage":N,"id":"<pid>","sortingType":"nativeLocale",...}
          &extensions={"persistedQuery":{"sha256Hash":...},"pwa":{...}}
- 第 1 页评价随 SSR 内联在 window.__PRELOADED_STATE__.apolloState 里
  （GraphqlReview:<id> 实体），不会发请求；第 2 页起点评价区分页按钮才发请求。
- ★ 自己拼 URL 重放会被 WAF 拦（实测第 1 页 200，第 2 页起 429/403，即便带齐
  x-flow-id / apollographql-* 头、间隔 4s）。但**站方页面自己点分页**发出的请求
  全部 200。所以这里不重放，只在真实页面里点分页按钮、截获站方自己的响应。
  persisted query 的 hash 随前端发版会变，截获方式也不受影响。
- 每页 10 条；评价按「商品族」聚合（isProductFamilyReview，reviewProductId
  可能是同系列别的尺寸）。与 BV 一致：保留来源商品号到 review_url 锚点
  (#mms-src-product=<id>)，meta.cross_product 报告串尺寸条数，导出时可剔除/标注。
- cookie 同意层（#mms-consent-portal-container）会挡住点击，直接移除即可。

配置（RetailSpec.reviews 段）：
    "reviews": {"source": "mms_graphql", "limit": 40, ...}
选择器全部用 data-test（语言无关、非哈希类名），整个 MMS 集团各国站通用。
"""
from __future__ import annotations

import json
import re
import time

from .models import Review, ReviewSummary

MMS_SOURCE = "mms_graphql"

_CONSENT_JS = ("() => { const e = document.getElementById('mms-consent-portal-container');"
               " if (e) { e.remove(); return true } return false }")
_CARD = "[data-test='single-review-card']"
_PAGER_BTN = "[data-test='review-pagination-wrapper'] button"
_REVIEWS_SECTION = "[data-test='mms-reviews-content']"
_OP_RE = re.compile(r"operationName=GetProductReviews", re.I)


def is_mms_spec(spec: dict | None) -> bool:
    return str(((spec or {}).get("reviews") or {}).get("source") or "") == MMS_SOURCE


def product_id_from_url(url: str) -> str:
    m = re.search(r"-(\d{5,})\.html", url or "")
    return m.group(1) if m else ""


def _photo_urls(raw) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        sizes = item.get("sizes") or {}
        url = ""
        for key in ("large", "normal", "thumbnail"):
            node = sizes.get(key) if isinstance(sizes, dict) else None
            if isinstance(node, dict) and node.get("url"):
                url = str(node["url"])
                break
        if url:
            out.append(url)
    return out


def _video_urls(raw) -> list[str]:
    out: list[str] = []
    for item in raw or []:
        if isinstance(item, dict):
            url = str(item.get("url") or item.get("videoUrl") or item.get("videoId") or "")
            if url:
                out.append(url)
    return out


def _to_review(node: dict, product_url: str, pid: str,
               reviewers: dict | None = None) -> Review | None:
    if not isinstance(node, dict):
        return None
    rid = str(node.get("id") or "").strip()
    fb = node.get("feedback") or {}
    title = str(node.get("title") or "").strip()
    body = str((fb.get("full") if isinstance(fb, dict) else "") or "").strip()
    if not body and isinstance(fb, dict):
        body = "; ".join([*(fb.get("advantages") or []), *(fb.get("disadvantages") or [])])
    if not (rid or title or body):
        return None
    reviewer = node.get("reviewer") or {}
    if isinstance(reviewer, dict) and reviewer.get("__ref") and reviewers:
        reviewer = reviewers.get(reviewer["__ref"]) or {}
    try:
        rating = float(node["rating"]) if node.get("rating") is not None else None
    except (TypeError, ValueError):
        rating = None
    helpful = node.get("positiveFeedbackCount")
    review = Review(
        review_key=rid or f"mms:{title[:40]}",
        rating=rating,
        title=title,
        body=body,
        author=str((reviewer or {}).get("displayName") or "").strip(),
        review_date=str(node.get("date") or "").strip(),
        verified=node.get("isVerifiedPurchaser"),
        helpful_count=int(helpful) if isinstance(helpful, int) else None,
        review_url=product_url,
        image_urls=_photo_urls(node.get("photos")),
        video_urls=_video_urls(node.get("videos")),
    )
    src = str(node.get("reviewProductId") or "").strip()
    if src and pid and src != pid:
        review.review_url = (product_url or "") + f"#mms-src-product={src}"
    return review


def _decode_at(html: str, pos: int):
    """从 pos（'{' 处）解一个 JSON 对象；SSR 里偶有 JS 的 undefined，替换后再试。"""
    dec = json.JSONDecoder()
    try:
        return dec.raw_decode(html, pos)[0]
    except ValueError:
        pass
    # 粗略截取到括号平衡处，替换 undefined
    depth, i, in_str, esc = 0, pos, False, False
    while i < len(html):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    try:
        return json.loads(re.sub(r"\bundefined\b", "null", html[pos:i + 1]))
    except ValueError:
        return None


def _entities(html: str, prefix: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in re.finditer(r'"(' + re.escape(prefix) + r':[^"]+)":\{', html or ""):
        key = m.group(1)
        if key in out:
            continue
        obj = _decode_at(html, m.end() - 1)
        if isinstance(obj, dict):
            out[key] = obj
    return out


def ssr_reviews(html: str, product_url: str, pid: str) -> list[Review]:
    """第 1 页：SSR apolloState 内联的 GraphqlReview 实体。"""
    reviewers = _entities(html, "GraphqlReviewer")
    out = []
    for node in _entities(html, "GraphqlReview").values():
        r = _to_review(node, product_url, pid, reviewers)
        if r:
            out.append(r)
    return out


def _summary(rv: dict) -> ReviewSummary | None:
    if not isinstance(rv, dict):
        return None
    stars: dict[int, int] = {}
    for row in ((rv.get("rating") or {}).get("distribution") or []):
        try:
            stars[int(row.get("value"))] = int(row.get("count") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
    total = rv.get("totalResults")
    total = int(total) if isinstance(total, int) else (sum(stars.values()) or None)
    avg = None
    if stars and sum(stars.values()):
        avg = round(sum(k * v for k, v in stars.items()) / sum(stars.values()), 2)
    if avg is None and total is None:
        return None
    return ReviewSummary(avg_rating=avg, total_count=total, stars=stars)


def fetch_mms_reviews(spec: dict, product_url: str, *, fetcher, max_reviews: int = 100,
                      max_pages: int | None = None, verbose: bool = False
                      ) -> tuple[list[Review], ReviewSummary | None, dict]:
    """打开 PDP，取 SSR 第 1 页 + 点分页截获后续页。返回 (reviews, summary, meta)。"""
    meta: dict = {"ok": False, "pages": 0, "stop_reason": "", "cross_product": 0,
                  "total_expected": None, "error": "", "source": MMS_SOURCE}
    pid = product_id_from_url(product_url)
    page_fn = getattr(fetcher, "page", None)
    if not pid or not callable(page_fn):
        meta["stop_reason"] = "no_pid" if not pid else "no_browser"
        return [], None, meta
    cap = max(0, int(max_reviews or 0))
    pages_cap = max(1, int(max_pages or 20))
    reviews: list[Review] = []
    seen: set[str] = set()
    summary: ReviewSummary | None = None
    captured: list = []

    def add(batch) -> int:
        n = 0
        for r in batch:
            if r.review_key in seen or len(reviews) >= cap:
                continue
            seen.add(r.review_key)
            reviews.append(r)
            n += 1
        return n

    try:
        with page_fn(product_url, wait_selector="h1", scroll_passes=0,
                     extra_wait_ms=1500) as (res, dom):
            if getattr(res, "blocked", False) or dom is None:
                meta["stop_reason"] = "blocked" if getattr(res, "blocked", False) else "http_failed"
                meta["error"] = str(getattr(res, "block_reason", "") or "")
                return [], None, meta
            pg = getattr(dom, "_root", None)
            html = pg.content() if pg is not None else (dom.html() if hasattr(dom, "html") else "")
            add(ssr_reviews(html, product_url, pid))
            meta["pages"] = 1
            # SSR 汇总：ROOT_QUERY.reviews({...productId...}) 节点
            m = re.search(r'"reviews\(\{\\"productId\\":\\"' + pid + r'\\".{0,300}?\}\)":\{', html)
            if m:
                summary = _summary(_decode_at(html, m.end() - 1) or {})
            if summary and summary.total_count is not None:
                meta["total_expected"] = summary.total_count
            total = meta["total_expected"]
            if pg is None or len(reviews) >= cap or (total is not None and len(reviews) >= total):
                meta["stop_reason"] = "max_reviews" if len(reviews) >= cap else "exhausted"
            else:
                def on_resp(r):
                    try:
                        if _OP_RE.search(r.url) and "filterInput" not in r.url:
                            captured.append(r)
                    except Exception:
                        pass
                pg.on("response", on_resp)
                pg.evaluate(_CONSENT_JS)
                # 打开评价区（SSR 已把卡片放进 DOM 但折叠着，须看「可见」而非 count）。
                # 先滚动让懒加载区块挂载，再点评价区折叠头 / 顶部「(N 评价)」锚点按钮。
                def _cards_visible() -> bool:
                    try:
                        return pg.locator(_CARD).first.is_visible()
                    except Exception:
                        return False
                for _ in range(6):
                    pg.mouse.wheel(0, 2500)
                    pg.wait_for_timeout(500)
                # 顶部评分区的「(N Bewertungen)」按钮会把页面滚到评价区并把折叠的
                # 「Produktbewertungen」手风琴展开。候选按钮按优先级逐个尝试，
                # 每次点完都等卡片「可见」（SSR 已塞进 DOM，判 count 不够，须判 visible）。
                openers = (
                    "a[href='#reviews']",
                    "button[aria-label='Produktbewertungen']",
                    f"{_REVIEWS_SECTION} button[aria-expanded='false']",
                    f"{_REVIEWS_SECTION} [data-test='accordion-header']",
                )
                for sel in openers:
                    if _cards_visible():
                        break
                    try:
                        loc = pg.locator(sel).first
                        if not loc.count():
                            continue
                        loc.scroll_into_view_if_needed(timeout=4000)
                        loc.click(timeout=5000, force=True)
                        pg.wait_for_timeout(1500)
                        pg.locator(_CARD).first.wait_for(state="visible", timeout=8000)
                    except Exception:
                        continue
                meta["cards_visible"] = _cards_visible()
                meta["pager_buttons"] = pg.locator(_PAGER_BTN).count()
                while meta["pages"] < pages_cap and len(reviews) < cap:
                    nxt = pg.locator(_PAGER_BTN).last
                    if not nxt.count() or (nxt.get_attribute("aria-disabled") or "") == "true":
                        meta["stop_reason"] = "exhausted"
                        break
                    before = len(captured)
                    try:
                        nxt.scroll_into_view_if_needed(timeout=4000)
                        nxt.click(timeout=5000, force=True)
                    except Exception as e:
                        meta["stop_reason"] = "click_failed"
                        meta["error"] = f"{type(e).__name__}: {e}"[:200]
                        break
                    t0 = time.time()
                    while len(captured) == before and time.time() - t0 < 12:
                        pg.wait_for_timeout(300)
                    if len(captured) == before:
                        meta["stop_reason"] = "no_response"
                        break
                    resp = captured[-1]
                    meta["pages"] += 1
                    if resp.status != 200:
                        meta["stop_reason"] = f"http_{resp.status}"
                        break
                    try:
                        rv = (json.loads(resp.text()).get("data") or {}).get("reviews") or {}
                    except Exception:
                        meta["stop_reason"] = "bad_json"
                        break
                    if summary is None:
                        summary = _summary(rv)
                    new = add(r for r in (_to_review(n, product_url, pid)
                                          for n in rv.get("reviews") or []) if r)
                    if verbose:
                        print(f"    [MMS] p{meta['pages']} 新增 {new} 累计 {len(reviews)}")
                    if new == 0:
                        meta["stop_reason"] = "page_all_known"
                        break
                    pg.wait_for_timeout(1200)       # 礼貌间隔，避免触发 429
                else:
                    meta["stop_reason"] = meta["stop_reason"] or (
                        "max_reviews" if len(reviews) >= cap else "max_pages")
        meta["ok"] = True
    except Exception as e:
        meta["error"] = f"{type(e).__name__}: {e}"[:300]
        meta["stop_reason"] = meta["stop_reason"] or "exception"
    meta["total_reviews"] = len(reviews)
    meta["cross_product"] = sum(1 for r in reviews if "#mms-src-product=" in (r.review_url or ""))
    return reviews, summary, meta
