"""多地区零售线：按 SPEC 型号同步抓取价格与网评。

加拿大线是当前主用场景：同一型号在每个零售站搜索一次，打开命中的商品页
同步抽取价格、评分汇总和评价。结果既保持原有 CSV/XLSX 导出，也可通过
``--save-db`` 写入通用 product/price_snapshot/review 表，并写入独立的
retail_task_status 型号级状态表。

日本价格/评价仍由各自的 kakaku 脚本负责，本脚本不写 kakaku_task_status。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                            # noqa: E402
from overseas.db import Database                      # noqa: E402
from overseas.fetchers import BrowserFetcher, HttpFetcher  # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.models import ProductPayload               # noqa: E402
from overseas.price_export_ca import CaPriceRecord     # noqa: E402
from overseas.price_export_ca import write_csv as price_write_csv  # noqa: E402
from overseas.price_export_ca import write_xlsx as price_write_xlsx  # noqa: E402
from overseas.regions_config import get_region         # noqa: E402
from overseas.retail_spec import (collect_reviews_paged,  # noqa: E402
                                  load_retail_spec,
                                  resolve_max_review_pages,
                                  resolve_max_reviews)
from overseas.review_export import ReviewRecord        # noqa: E402
from overseas.review_export import write_csv as review_write_csv  # noqa: E402
from overseas.review_export import write_xlsx as review_write_xlsx  # noqa: E402
from overseas.scenarios import RunStats, open_dom, save_payload  # noqa: E402
from overseas.sites import SiteRegistry                # noqa: E402

DEFAULT_MODELS_CSV = PROJECT_ROOT / "data" / "加拿大" / "SPEC_型号汇总_ca.csv"


# ==================== 型号清单 ====================

def _default_models_csv(region_code: str) -> Path:
    """按区域选择默认型号清单（R1-8：归国目录 + 日期戳通配）。

    优先在 data/<国家中文名>/ 找 SPEC_型号汇总_<region>_*.csv；找不到回落旧路径。
    三国目录：ca→加拿大、us→美国、mx→墨西哥。
    """
    # 其余区域（南美/欧洲…）目录名 = 区域中文名；清单由 scripts/export_region_models.py 生成
    _reg = get_region(region_code)
    cn_dir = {"ca": "加拿大", "us": "美国", "mx": "墨西哥"}.get(
        region_code, _reg.name if _reg else "")
    if cn_dir:
        d = PROJECT_ROOT / "data" / cn_dir
        if d.is_dir():
            # 日期戳通配（最新的优先）
            matches = sorted(d.glob(f"SPEC_型号汇总_{region_code}_*.csv"), reverse=True)
            if matches:
                return matches[0]
            legacy = d / f"SPEC_型号汇总_{region_code}.csv"
            if legacy.exists():
                return legacy
    # 回落旧路径（data/ 根）
    return PROJECT_ROOT / "data" / f"SPEC_型号汇总_{region_code}.csv"


# 型号清单里的国别后缀（「Hisense（美国）」）会把中文全角括号带进搜索框。
# ★这不是排版问题：品牌级批量搜索一旦用了脏关键词，搜索页候选池会整体失效，
# 而失效的表现是"所有型号都判 no_item"——静默丢数据，且没有任何报错。
# 加拿大清单的 search_query 恰好是干净的（"Hisense 55U7SG"），美国清单不是
# （"Hisense（美国） 100U8QG"），所以这个坑只在换国家时才暴露。
_CJK_RE = re.compile(r"[\u3000-\u9fff\uff00-\uffef]+")


def _clean_search_text(text: str) -> str:
    """清掉清单里的中文国别后缀与残余中日韩字符，得到可直接搜索的关键词。"""
    s = str(text or "")
    # 只删「含中日韩字符的括号段」，不动型号里可能有意义的半角括号
    s = re.sub(r"[（(][^）)]*[）)]",
               lambda m: " " if _CJK_RE.search(m.group(0)) else m.group(0), s)
    s = _CJK_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_models(models_csv: Path, brands: list[str],
                explicit: list[str] | None,
                brand_names: dict[str, str] | None = None
                ) -> list[tuple[str, str, str, str]]:
    """读型号汇总 CSV，返回 [(brand_code, brand_name, model_raw, search_query), ...]。

    explicit 指定型号时，品牌取传入 brands 的首个；品牌展示名来自区域集中配置。
    search_query 会清掉中文国别后缀（见 _clean_search_text），保证送进搜索框的
    是纯 ASCII 的「品牌 + 型号」。
    """
    brand_names = brand_names or {}
    if explicit:
        code = brands[0] if brands else ""
        name = brand_names.get(code, code)
        return [
            (code, name, model.strip(),
             _clean_search_text(f"{name} {model.strip()}"))
            for model in explicit if model.strip()
        ]
    if not models_csv.exists():
        raise FileNotFoundError(
            f"型号清单不存在: {models_csv}（先跑 export_spec_models.py --region ca）")
    want = set(brands) if brands else None
    out: list[tuple[str, str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    with models_csv.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("brand_code") or "").strip()
            if want is not None and code not in want:
                continue
            model = (row.get("model_raw") or "").strip().split(" | ")[0]
            if not model:
                continue
            key = (code, model)
            if key in seen:
                continue
            seen.add(key)
            name = (row.get("brand_name") or brand_names.get(code) or code).strip()
            query = _clean_search_text(
                row.get("search_query") or f"{name} {model}")
            out.append((code, name, model, query))
    return out


# ==================== 零售站选择 ====================

def resolve_sites(region_code: str, explicit: list[str] | None) -> list[str]:
    region = get_region(region_code)
    if region is None:
        raise SystemExit(f"未知区域: {region_code}")
    if explicit:
        valid = {r.site for r in region.retail_sites}
        bad = [s for s in explicit if s not in valid]
        if bad:
            raise SystemExit(f"区域 {region_code} 不含零售站: {bad}")
        return list(dict.fromkeys(explicit))
    return region.retail_site_codes(only_enabled=True)


def _make_fetcher(adapter, retail_spec: dict | None = None):
    """构造抓取器。返回 (search_fetcher, detail_fetcher)。

    多数站搜索页和商品页用同一个抓取器；但 Costco 这类站是「搜索页客户端渲染
    （必须浏览器）、商品页服务端渲染（纯 HTTP 就够）」的混合形态。此时按
    ``adapter.detail_http`` 或 ``spec.fetch.detail_http`` 给详情页单独配一个
    HttpFetcher：每个 PDP 从 10~20 秒降到 1~2 秒，且不占浏览器并发。
    """
    interval = max(config.MIN_INTERVAL, adapter.suggested_interval)
    rate = RateLimiter(min_interval=interval)
    # 读 adapter.block_marker_allowlist 豁免误报关键字（与 scenarios.make_fetcher 一致）：
    # Shopify 站（leons_ca/thebrick_ca）正常页面含 captcha-bootstrap 脚本，
    # 不豁免会被 BlockDetector 误判拦截。
    ignore_markers = getattr(adapter, "block_marker_allowlist", None)
    shared = {"rate_limiter": rate, "detector": BlockDetector(
        ignore_markers=ignore_markers), "cache": DiskCache()}
    if adapter.requires_browser:
        # site_code → 自动读写 data/session/<code>.state.json（登录态复用）
        main = BrowserFetcher(site_code=getattr(adapter, "code", ""), **shared)
    else:
        main = HttpFetcher(**shared)
    detail_http = bool(getattr(adapter, "detail_http", False)) or bool(
        ((retail_spec or {}).get("fetch") or {}).get("detail_http"))
    # 搜索走 JSON 接口（spec.search.api）时必须用 HttpFetcher：浏览器会把 JSON 包进
    # <pre>，且无需渲染。详情页仍按原逻辑选择抓取器。
    from overseas.mx_retail import search_api_cfg
    if search_api_cfg(retail_spec):
        detail = HttpFetcher(**shared) if detail_http else main
        return HttpFetcher(**shared), detail
    if detail_http and isinstance(main, BrowserFetcher):
        return main, HttpFetcher(**shared)
    return main, main


def _search_url(adapter, retail_spec: dict | None, keyword: str, page: int = 1) -> str:
    """搜索 URL：spec 声明了搜索接口（search.api）就用接口，否则用 adapter 的搜索页。"""
    from overseas.mx_retail import search_api_cfg, search_api_url
    api = search_api_cfg(retail_spec)
    if api:
        return search_api_url(api, adapter, keyword, page)
    # spec 声明的搜索页 URL 模板优先于 adapter 内置规则（站点改版只改 spec，不改代码）
    tmpl = ((retail_spec or {}).get("search") or {}).get("search_url_template") or ""
    if tmpl:
        import urllib.parse as _up
        url = tmpl.format(base=adapter.base_url.rstrip("/"), q=_up.quote(keyword.strip()),
                          page=max(1, int(page or 1)))
        page_param = ((retail_spec or {}).get("search") or {}).get("page_param") or ""
        if page and page > 1 and page_param and "{page}" not in tmpl:
            url += ("&" if "?" in url else "?") + f"{page_param}={int(page)}"
        return url
    return adapter.search_url(keyword, page) if page and page > 1 else adapter.search_url(keyword)


@dataclass
class CrawlOutcome:
    payload: ProductPayload | None = None
    status: str = "failed"       # ok / no_item / blocked / failed
    message: str = ""
    url: str = ""


# ==================== 商品页抽取分派 ====================

def _spec_drives_detail(adapter, retail_spec: dict | None) -> bool:
    """该站这一次是否用 RetailSpec 六段驱动商品页抽取。

    双重前提，缺一不可：
      1) adapter 显式声明 `spec_driven_detail = True`——Amazon 这类站必须保留
         适配器路径，否则会丢掉 amazon_common 的价格区校验（32A4NV 配件价事故：
         页面无 buybox 主价时，兜底选择器抓到的是配件轮播价）；
      2) 本次确实传了带抽取段的 spec，否则回落到适配器。
    """
    if not retail_spec:
        return False
    if not (retail_spec.get("product") or retail_spec.get("price")):
        return False
    if getattr(adapter, "spec_driven_detail", False):
        return True
    # 薄 adapter（只给 URL 规则、没实现 parse_product）只能靠 spec 抽取。
    # 原先这里直接回落 adapter.parse_product → NotImplementedError，87 个零售站
    # （南美全部、欧洲多数）在通用全量入口上整站崩溃（2026-10-08 readiness 实测 liverpool_mx）。
    # 实现了自己 parse_product 的站（Amazon 等）不受影响，仍走适配器路径。
    from overseas.sites import SiteAdapter
    return type(adapter).parse_product is SiteAdapter.parse_product


def _fill_api_price(payload: ProductPayload, hit) -> None:
    """搜索接口给了这一商品的有货成交价（VTEX commertialOffer）→ 以接口价为准。

    只在**详情页型号校验已通过**之后调用，且价格来自同一个候选商品，不是猜测；
    接口里无货/无价时不动页面抽取结果（缺价 > 错价）。
    VTEX IO 店面的价格是客户端渲染的，服务端 HTML 常常没有价格节点（readiness 实测
    carsa_pe / plazavea_pe 命中 2/2 但价格 0/2）。
    """
    api_price = getattr(hit, "api_price", None)
    if api_price is None or payload is None or payload.price is None:
        return
    page_price = payload.price.price
    # 接口价是平台结构化的成交价（commertialOffer.Price），比 DOM 抠出来的数字可靠：
    # 实测 cresa_ec 页面选择器取到 905.17（划线原价），接口成交价 787.10。
    # 页面价高于接口价时把它记作原价，不丢信息。
    payload.price.price = api_price
    payload.price.raw_text = "vtex_catalog_api"
    lp = getattr(hit, "api_list_price", None)
    if lp is None and page_price is not None and page_price > api_price:
        lp = page_price
    if payload.price.list_price is None or (lp and lp > api_price):
        payload.price.list_price = lp
    payload.price.in_stock = True


def _resolve_site_spec(site_code: str, explicit: dict | None) -> dict | None:
    """该站本次用哪份 spec。

    - 显式 --spec：照用（只允许单站，见 main）；
    - 未给 --spec：
        * 适配器自带 parse_product 且未声明 spec_driven_detail（Amazon 等）→ 不加载，
          保持原适配器路径（这些站的全量已在该路径上调通，见 recrawl_amazon.py）；
        * 其余（薄 adapter / spec 驱动站）→ 自动加载唯一 spec
          schemas/retail_specs/<code>.retail.json。否则薄 adapter 无从抽取商品页。
    """
    if explicit is not None:
        return explicit
    from overseas.retail_spec import find_retail_spec
    from overseas.sites import SiteAdapter
    try:
        adapter = SiteRegistry.get(site_code)
    except Exception:
        return None
    own_parse = type(adapter).parse_product is not SiteAdapter.parse_product
    if own_parse and not getattr(adapter, "spec_driven_detail", False):
        return None
    return find_retail_spec(site_code)


def _payload_from_spec(adapter, retail_spec: dict, dom, html: str,
                       sku: str, url: str) -> ProductPayload:
    """用 RetailSpec 的六段定义从**已打开**的商品页抽取 payload。

    抽取口径与 scenarios.collect_detail 完全一致，区别只在于不重新打开页面——
    这里 dom 已在调用方的 open_dom 上下文里，重开会多一次请求，在 L3 站上代价很高。
    """
    from overseas.extract import Extractor
    from overseas.models import PriceSnapshot, Product

    ex = Extractor(retail_spec, html=html, base_url=adapter.base_url)
    pf = ex.fields(dom, "product")
    prf = ex.fields(dom, "price")
    product = Product(
        site_code=adapter.code,
        sku=sku,
        url=url,
        title=str(pf.get("title") or "")[:500],
        brand=str(pf.get("brand") or "")[:200],
        model=str(pf.get("model") or "")[:200],
        category=str(pf.get("category") or "")[:200],
        size=str(pf.get("size") or "")[:80],
    )
    in_stock = prf.get("in_stock")
    payload = ProductPayload(
        product=product,
        specs=ex.specs(dom),
        price=PriceSnapshot(
            price=prf.get("price"),
            list_price=prf.get("list_price"),
            currency=str(prf.get("currency") or "")[:8],
            in_stock=in_stock if isinstance(in_stock, bool) else None,
            raw_text=str(prf.get("raw_text") or "")[:120],
        ),
        summary=ex.summary(dom),
        reviews=ex.reviews(dom),
    )
    # 抽取后钩子：让适配器补 spec 拿不到的站点知识（如 Walmart 的权威型号候选
    # 与价格区校验）。没有它，spec 路径下 model_candidates 恒为空，详情页校验
    # 会退化成宽松的标题/URL 子串匹配，55 吋有被记到 75 吋头上的风险。
    hook = getattr(adapter, "enrich_payload", None)
    if callable(hook):
        try:
            payload = hook(payload, dom=dom, html=html, url=url) or payload
        except Exception:
            pass          # 钩子失败不影响主抽取结果
    return payload


def _detail_payload(adapter, retail_spec: dict | None, dom, html: str,
                    sku: str, url: str) -> ProductPayload:
    """商品页抽取分派：spec 驱动（JSON-LD 稳定的站）或适配器（Amazon 类站）。"""
    if _spec_drives_detail(adapter, retail_spec):
        payload = _payload_from_spec(adapter, retail_spec, dom, html, sku, url)
    else:
        payload = adapter.parse_product(dom, sku=sku, url=url)
    # spec 被标记价格可疑（autofix/readiness 实测抽到月供/起价等）：价格一律不入库，
    # 缺价 > 错价；型号/评价照常。修好价格规则后删掉 _price_suspect 即恢复。
    if (retail_spec or {}).get("_price_suspect") and payload is not None and payload.price:
        payload.price.price = None
        payload.price.list_price = None
        payload.price.raw_text = "price_suspect"
    return payload


# ==================== 状态与抓取 ====================

def _record_pair(db: Database | None, run_id: int | None, save_db: bool,
                 region_code: str, site_code: str, site_name: str,
                 brand_code: str, brand_name: str, model: str,
                 status: str, message: str = "", item_id: str = "",
                 product_id: int | None = None, size: str = "",
                 price: float | None = None, currency: str = "",
                 review_count: int = 0, review_new_count: int = 0,
                 summary_count: int | None = None,
                 summary_rating: float | None = None) -> None:
    """同一商品页结果写入 price/review 两条独立状态。"""
    if not save_db or db is None or run_id is None:
        return
    price_status = status
    review_status = status
    price_rows = 0
    review_rows = 0
    review_new = 0
    if status == "ok":
        price_status = "ok" if price is not None else "no_price"
        has_summary = summary_count is not None or summary_rating is not None
        review_status = ("ok" if review_count else
                         "summary_only" if has_summary else "no_reviews")
        if review_status == "summary_only" and not message:
            message = "页面有评分汇总，但未提供可入库的评价明细"
        price_rows = 1 if price is not None else 0
        review_rows = review_count
        review_new = review_new_count
    db.record_retail_status(
        region=region_code, task="price", site_code=site_code,
        site_name=site_name, brand=brand_code or brand_name or "unknown",
        brand_name=brand_name, model=model, status=price_status,
        run_id=run_id, item_id=item_id, product_id=product_id, size=size,
        price=price, currency=currency, row_count=price_rows, new_count=0,
        message=message,
    )
    db.record_retail_status(
        region=region_code, task="review", site_code=site_code,
        site_name=site_name, brand=brand_code or brand_name or "unknown",
        brand_name=brand_name, model=model, status=review_status,
        run_id=run_id, item_id=item_id, product_id=product_id, size=size,
        price=price, currency=currency, row_count=review_rows,
        new_count=review_new, message=message,
    )


def _normalise_reviews(reviews) -> list:
    """为没有站内 ID 的评价生成内容指纹，过滤完全无内容的伪评价。"""
    out = []
    for review in reviews or []:
        key = str(review.review_key or "").strip()
        if not key:
            material = "\x1f".join(str(value or "").strip() for value in (
                review.review_date, review.title, review.body, review.author,
                review.rating, review.review_url))
            if not material.replace("\x1f", "").strip():
                continue
            digest = hashlib.sha1(material.encode("utf-8", "replace")).hexdigest()
            review.review_key = f"derived:{digest}"
        else:
            review.review_key = key
        out.append(review)
    return out


def _model_norm(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _payload_matches_model(model: str, payload: ProductPayload,
                           spec: dict | None = None) -> bool:
    """详情页必须以型号为准，禁止按首条候选盲取。

    校验顺序（从严到宽）：
    0) **配件排除**（spec.match.reject）：标题命中 case/wall mount/remote 等
       配件词直接否掉。★ 必须在这里也做一次：`match_product` 的 reject 只作用于
       **搜索候选**，而逐型号回退路径（_crawl_one）拿到的 PDP 从未过硬性 reject，
       实测导致 "Wall Mount Bracket"、"Voice Remote Control" 被当成电视入库。
    1) **权威型号精确相等**：Costco 这类站商品页自己标注了 Model 字段
       （页头 `Item <n> | Model <code>`、规格表 `Model` 行），标题里反而没有完整
       型号。`product.model_candidates` 非空时只认精确相等——这是防张冠李戴最
       可靠的一路（`55U7SG` 不会命中 `55U78SG`）。
    2) product.model > product.title > product.url（URL 兜底：canadiantire 等站
       标题不含型号代码，但 URL slug 里含，如 ...-32-qd4sv-0436032p.html）。
    """
    want = _model_norm(model)
    if len(want) < 4:
        return False
    # ---- 0) 配件排除 ----
    if spec:
        rj = ((spec.get("match") or {}).get("reject") or {})
        words = [str(w).lower() for w in (rj.get("title_contains_any") or [])]
        title_low = (payload.product.title or "").lower()
        if words and title_low:
            for w in words:
                if w and w in title_low:
                    return False
    candidates = list(getattr(payload.product, "model_candidates", None) or [])
    if candidates:
        if any(_model_norm(c) == want for c in candidates if c):
            return True
        # 有权威型号但都不等 → 这条详情页不是目标型号，直接否掉，
        # 不再退回宽松的标题/URL 子串匹配（否则权威型号形同虚设）。
        return False
    # URL 兜底只看 path：搜索结果链接的 query 里常带着搜索词本身（Amazon 的
    # ...?keywords=<型号>&ref=sr_1_5），整串匹配会让「任何被搜索的型号」都命中
    # 第一个候选——2026-10-08 实测 amazon_mx 把 LG 回音壁记成不存在型号 ZQ99X7NOEXIST。
    url_path = urllib.parse.urlsplit(payload.product.url or "").path
    for value in (payload.product.model, payload.product.title, url_path):
        got = _model_norm(value)
        if want in got:
            return True
    return False


def _collect_reviews(spec: dict | None, adapter, fetcher, product_url: str,
                     sku: str, payload: ProductPayload, max_reviews: int,
                     max_review_pages: int | None) -> tuple[dict, bool]:
    """取评价明细。返回 (review_meta, reused_payload_reviews)。

    两条来源，按 spec 选择：
      - ``reviews.source == "bazaarvoice_bfd"``（Costco 等）：走 BV 客户端接口
        （HTTP，见 overseas/bv_reviews.py）。商品页 DOM 里没有评价明细，
        用 DOM 选择器永远只能拿到 0 条。
      - 其它：走 spec 驱动的评价翻页 ``collect_reviews_paged``。
    拿到的评分为准的汇总也会回填（BV 的汇总带星级分布，比 JSON-LD 更全）。
    """
    from overseas.bv_reviews import fetch_bv_reviews, is_bv_spec
    from overseas.mms_reviews import fetch_mms_reviews, is_mms_spec
    meta: dict = {}
    if is_mms_spec(spec):
        # MediaMarkt/Saturn/MediaWorld：SSR 首页 + 真实页面点分页截获 GraphQL（见模块说明）
        reviews, summary, meta = fetch_mms_reviews(
            spec or {}, product_url, fetcher=fetcher, max_reviews=max_reviews,
            max_pages=max_review_pages, verbose=False)
        if reviews or meta.get("ok"):
            payload.reviews = reviews
        if summary is not None and (summary.avg_rating is not None
                                    or summary.total_count is not None):
            payload.summary = summary
        return meta, True
    if is_bv_spec(spec):
        product_id = (getattr(payload.product, "bv_product_id", "") or
                      _product_id_from_url(product_url) or sku)
        reviews, summary, meta = fetch_bv_reviews(
            spec or {}, product_id, product_url=product_url,
            fetcher=fetcher, max_reviews=max_reviews,
            max_pages=max_review_pages, verbose=False)
        payload.reviews = reviews
        if summary is not None and (summary.avg_rating is not None
                                    or summary.total_count is not None):
            payload.summary = summary
        return meta, True
    if spec is not None and len(payload.reviews) < max(0, max_reviews):
        payload.reviews, meta = collect_reviews_paged(
            spec, adapter, fetcher, sku, payload.reviews,
            open_dom=open_dom, product_url=product_url,
            max_reviews=max_reviews, max_pages=max_review_pages,
            verbose=False)
    return meta, False


def _review_message(meta: dict, max_reviews: int) -> str:
    """把评价 meta 变成给人看的一句话（含"评价串尺寸"这类必须暴露的风险）。"""
    if not meta:
        return ""
    if meta.get("blocked"):
        return f"评价页被拦截：{meta.get('block_reason')}"
    parts: list[str] = []
    stop = str(meta.get("stop_reason") or "")
    if stop:
        parts.append(f"评价停止原因={stop}")
    if meta.get("error"):
        parts.append(f"评价异常={meta['error']}")
    cross = int(meta.get("cross_product") or 0)
    total = int(meta.get("total_reviews") or 0)
    if cross:
        # BV 按系列聚合：用 55" 的商品号查，返回的可能是 75" 的评价。
        # 这不是抓取错误，但必须让汇报看得见，否则会被当成"该型号的用户评价"。
        parts.append(f"★{cross}/{total} 条评价来自同系列其它商品（BV 按系列聚合，"
                     f"review_url 已带 #bv-src-product=<商品号> 溯源）")
    if total >= max_reviews > 0:
        parts.append(f"已达上限 {max_reviews} 条")
    return "；".join(parts)


def _product_id_from_url(url: str) -> str:
    m = re.search(r"\.product\.(\d+)\.html", url or "", re.I)
    return m.group(1) if m else ""


def _crawl_one(adapter, fetcher, model: str, query: str,
               max_reviews: int, *, retail_spec: dict | None = None,
               max_review_pages: int | None = None,
               detail_fetcher=None) -> CrawlOutcome:
    """搜索候选后逐个打开详情页，以详情页型号/标题做权威校验。"""
    detail_fetcher = detail_fetcher or fetcher
    search_url = _search_url(adapter, retail_spec, query)
    s_cfg = (retail_spec or {}).get("search") or {}
    with open_dom(adapter, fetcher, search_url,
                  wait_selector=s_cfg.get("wait_selector") or "a",
                  scroll_passes=int(s_cfg.get("scroll_passes") or 3),
                  extra_wait_ms=int(s_cfg.get("wait_ms", 0) or 5000)) as (res, dom, html):
        if res.blocked:
            return CrawlOutcome(status="blocked", message=res.block_reason or "blocked",
                                url=search_url)
        if dom is None or not res.ok:
            return CrawlOutcome(status="failed",
                                message=res.error or f"status={res.status}", url=search_url)
        # 有 spec 时用 spec 驱动的 match_product 匹配候选（配置化匹配，含 reject/尺寸校验）；
        # 无 spec 回落到 adapter.parse_search + find_product（向后兼容）。
        if retail_spec is not None:
            from overseas.mx_retail import _parse_search_with_spec
            from overseas.retail_spec import explain_no_match, match_product
            hits = _parse_search_with_spec(retail_spec, adapter, dom, html, limit=10)
            if not hits:
                return CrawlOutcome(status="no_item", message="搜索结果为空",
                                    url=search_url)
            # 品牌从型号清单传入（_crawl_one 没有 brand 参数，从 query 提取）
            brand = query.rsplit(model, 1)[0].strip() if model in query else ""
            target = match_product(retail_spec, hits, brand=brand, model=model)
            if target is not None:
                ordered = [target] + [h for h in hits if h.sku != target.sku]
            else:
                # spec 匹配未命中，用全部候选走详情页校验（给不精确匹配一次机会）
                ordered = list(hits)
        else:
            hits = adapter.parse_search(dom, html, limit=8)
            if not hits:
                return CrawlOutcome(status="no_item", message="搜索结果为空",
                                    url=search_url)
            preferred = adapter.find_product(dom, html, model=model, query=query)
            ordered = []
            if preferred is not None:
                ordered.append(preferred)
            ordered.extend(hit for hit in hits if not preferred or hit.sku != preferred.sku)
    detail_failure = ""
    mismatch = 0
    for hit in ordered[:5]:
        product_url = hit.url or adapter.product_url(hit.sku)
        with open_dom(adapter, detail_fetcher, product_url,
                      wait_selector=getattr(adapter, "retail_page_wait", "body"),
                      scroll_passes=8, extra_wait_ms=2500) as (res, dom, html):
            if res.blocked:
                return CrawlOutcome(status="blocked", message=res.block_reason or "blocked",
                                    url=product_url)
            if dom is None or not res.ok:
                detail_failure = res.error or f"status={res.status}"
                continue
            payload = _detail_payload(adapter, retail_spec, dom, html,
                                      hit.sku, product_url)
            if payload is None:
                detail_failure = "商品页解析为空"
                continue
            if not _payload_matches_model(model, payload, retail_spec):
                mismatch += 1
                continue
            _fill_api_price(payload, hit)
            payload.reviews = _normalise_reviews(payload.reviews)
            # R1-4/R1-5：spec 驱动评价抓取，总量按 max_reviews 封顶（默认 100）。
            review_meta, _ = _collect_reviews(
                retail_spec, adapter, detail_fetcher, product_url, hit.sku,
                payload, max_reviews, max_review_pages)
            if review_meta.get("blocked"):
                # ★ 评价页被拦不等于整条抓取失败：商品页的价格/评分已经拿到，
                # 丢弃 payload 会把可用价格一起扔掉（Amazon 的评价页恒被鉴权
                # 拦，会把 621 个型号的价格全部清空）。保留 payload，把拦截
                # 原因写进 message 供站级熔断与汇报使用。
                payload.reviews = _normalise_reviews(payload.reviews)
                return CrawlOutcome(
                    payload=payload, status="ok", url=product_url,
                    message=f"评价页被拦截：{review_meta.get('block_reason')}")
            payload.reviews = _normalise_reviews(payload.reviews)
            # 兜底封顶：确保入库与导出条数一致，且不超上限。
            payload.reviews = list(payload.reviews[:max(0, max_reviews)])
            message = str(review_meta.get("stop_reason") or "")
            detail_msg = _review_message(review_meta, max_reviews)
            return CrawlOutcome(payload=payload, status="ok", url=product_url,
                                message=detail_msg or message)

    if detail_failure and not mismatch:
        return CrawlOutcome(status="failed", message=detail_failure, url=search_url)
    return CrawlOutcome(status="no_item",
                        message="搜索候选详情页未校验到目标型号", url=search_url)


def _resolve_brand_candidates(adapter, detail_fetcher, retail_spec: dict | None,
                              hits: list, limit: int, max_reviews: int,
                              max_review_pages: int | None,
                              verbose: bool = False,
                              site_code: str = "") -> dict:
    """把候选 PDP 逐个打开，建立「权威型号 → 已抓好的 payload」映射。

    为什么需要（Costco Samsung 实测）：
      列表页只写系列名 —— `Samsung 55" Class - M70H Series`；
      而型号清单里是厂商全码 —— `UN55M70HAFXZC`。
      候选级匹配（拿型号去撞标题/URL）必然全 miss，224 个 Samsung 型号全被判
      "该站没有"，但站上其实有。商品页自己在页头/规格表写了权威型号
      （实测该页 = `UN55M70HAFXZC`），所以先花 N 个请求把候选的权威型号解出来，
      再用**精确相等**去匹配。

    安全性：映射的 key 是商品页自报型号的归一化串，匹配是精确相等，
      没有放宽任何规则；错的 PDP 只会解出别的型号，进不了映射。
    预算：上限是**候选数**（每品牌 ~24 个），与该品牌的型号数（Samsung CA 224 个）
      无关；比"逐型号开 PDP"省一个数量级。
    顺带：解析时把价格+评价一起抓了存进 payload，命中后直接复用，不重复打开。

    返回 dict，另含两个下划线开头的元信息键（调用方据此判断结论可信度）：
      `_opened` / `_total` / `_truncated`
      ★ `_truncated=True` 表示候选没解析完（受 resolve_limit 限制）。
        此时"型号不在映射里"**不能**等同于"该站没有这个型号"——必须在
        no_item 的说明里写清楚，否则又是一次静默的假阴性。
    """
    resolved: dict[str, ProductPayload] = {}
    if not hits or limit <= 0:
        return resolved
    targets = hits[:limit] if limit else hits
    opened = 0
    for hit in targets:
        url = hit.url or adapter.product_url(hit.sku)
        try:
            with open_dom(adapter, detail_fetcher, url,
                          wait_selector=getattr(adapter, "retail_page_wait", "body"),
                          scroll_passes=2, extra_wait_ms=1500) as (res, dom, html):
                if res.blocked or dom is None or not res.ok:
                    continue
                payload = _detail_payload(adapter, retail_spec, dom, html,
                                          hit.sku, url)
                if payload is None:
                    continue
                models = [m for m in (getattr(payload.product, "model_candidates", None)
                                      or []) if m]
                if not models:
                    continue
                # 顺手把评价也取了：命中后无需再打开这个 PDP
                payload.reviews = _normalise_reviews(payload.reviews)
                review_meta, _ = _collect_reviews(
                    retail_spec, adapter, detail_fetcher, url, hit.sku,
                    payload, max_reviews, max_review_pages)
                payload.reviews = _normalise_reviews(payload.reviews)
                payload.reviews = list(payload.reviews[:max(0, max_reviews)])
                for m in models:
                    resolved.setdefault(_model_norm(m), (payload, hit, review_meta))
                opened += 1
        except Exception:
            continue
    truncated = len(hits) > len(targets)
    if verbose:
        print(f"  [{site_code}] 候选型号解析：打开 {opened}/{len(targets)} 个 PDP，"
              f"解出 {len(resolved)} 个权威型号"
              + (f"；★候选共 {len(hits)} 个，未解析完（受 resolve_limit={limit} 限制）"
                 f"——未覆盖的型号不能判定为'该站没有'" if truncated else ""))
    resolved["_opened"] = opened                       # type: ignore[assignment]
    resolved["_total"] = len(hits)                     # type: ignore[assignment]
    resolved["_truncated"] = truncated                 # type: ignore[assignment]
    return resolved


def _outcome_from_resolved(model: str, entry, max_reviews: int) -> CrawlOutcome:
    """用「候选解析」阶段已经抓好的 payload 直接产出结果（不再发请求）。"""
    import copy
    payload, hit, review_meta = entry
    payload = copy.deepcopy(payload)
    url = hit.url or ""
    if not _payload_matches_model(model, payload, retail_spec):
        return CrawlOutcome(status="no_item", url=url,
                            message="候选解析出的商品页型号不匹配（精确校验未过）")
    return CrawlOutcome(
        payload=payload, status="ok", url=url,
        message=_review_message(review_meta or {}, max_reviews))


def _crawl_one_batch(adapter, fetcher, model: str, query: str,
                     max_reviews: int, *, retail_spec: dict | None = None,
                     max_review_pages: int | None = None,
                     cached_hits: list | None = None,
                     detail_fetcher=None,
                     resolved: dict | None = None,
                     fallback_fn=None,
                     verbose: bool = True) -> CrawlOutcome:
    """品牌级搜索模式：用已缓存的「品牌 tv」搜索结果逐个PDP匹配，不逐型号搜索。

    避免型号不存在时搜索页返回广告/无关商品被误匹配。型号不存在时返回 no_item，
    不抓价格（不输出错误结果）。

    resolved：候选 PDP 的「权威型号 → 已抓好 payload」映射（可选）。
      列表页只有系列名、型号清单是厂商全码的站（Costco Samsung），候选级匹配
      必然 miss；这里先用映射做**精确相等**兜底，命中就直接复用已抓好的结果。
    """
    from overseas.retail_spec import explain_no_match, match_product
    detail_fetcher = detail_fetcher or fetcher
    entry = (resolved or {}).get(_model_norm(model))
    if entry is not None:
        return _outcome_from_resolved(model, entry, max_reviews)
    if not cached_hits:
        return CrawlOutcome(status="no_item", message="品牌搜索无候选", url="")
    # 用缓存的候选做型号匹配
    brand = query.rsplit(model, 1)[0].strip() if model in query else ""
    target = match_product(retail_spec or {}, cached_hits, brand=brand, model=model)
    if target is None:
        # 池内没有 → 交给回退（通常是一次逐型号精确搜索）。
        # 必要性实测：品牌搜索池受 Amazon **相关性排序**限制，133 个候选并不覆盖
        # 全部在售型号（如 Hisense U8QG 系列不在"Hisense tv"前 8 页里，但逐型号
        # 搜"Hisense 55U8QG"能精确命中）。纯池化会把这类型号误判 no_item。
        if fallback_fn is not None:
            if verbose and fallback_fn is not None:
                print(f"       池内未命中 {model} → 回退逐型号搜索")
            return fallback_fn()
        # 无回退：型号不在这个站 → 不抓价格，避免误匹配广告。
        # 带上可核对的原因（同系列不同尺寸 / 整个系列都没有 / 规则全排除）。
        return CrawlOutcome(
            status="no_item", url="",
            message="型号不在该站品牌搜索结果中：" + explain_no_match(
                retail_spec or {}, cached_hits, brand=brand, model=model))
    # 打开PDP抓价格+评价
    product_url = target.url or adapter.product_url(target.sku)
    try:
        with open_dom(adapter, detail_fetcher, product_url,
                      wait_selector=getattr(adapter, "retail_page_wait", "body"),
                      scroll_passes=8, extra_wait_ms=2500) as (res, dom, html):
            if res.blocked:
                return CrawlOutcome(status="blocked", message=res.block_reason or "blocked",
                                    url=product_url)
            if dom is None or not res.ok:
                return CrawlOutcome(status="failed",
                                    message=res.error or f"status={res.status}", url=product_url)
            payload = _detail_payload(adapter, retail_spec, dom, html,
                                      target.sku, product_url)
            if payload is None:
                return CrawlOutcome(status="no_item", message="商品页解析为空", url=product_url)
            if not _payload_matches_model(model, payload, retail_spec):
                return CrawlOutcome(status="no_item", message="详情页型号不匹配", url=product_url)
            _fill_api_price(payload, target)
            payload.reviews = _normalise_reviews(payload.reviews)
            review_meta, _ = _collect_reviews(
                retail_spec, adapter, detail_fetcher, product_url, target.sku,
                payload, max_reviews, max_review_pages)
            if review_meta.get("blocked"):
                # 同 _crawl_one：评价页被拦不丢弃已拿到的价格
                payload.reviews = _normalise_reviews(payload.reviews)
                return CrawlOutcome(
                    payload=payload, status="ok", url=product_url,
                    message=f"评价页被拦截：{review_meta.get('block_reason')}")
            payload.reviews = _normalise_reviews(payload.reviews)
            payload.reviews = list(payload.reviews[:max(0, max_reviews)])
            return CrawlOutcome(
                payload=payload, status="ok", url=product_url,
                message=_review_message(review_meta, max_reviews))
    except Exception as e:
        return CrawlOutcome(status="failed", message=f"{type(e).__name__}: {e}", url=product_url)


def crawl_site(site_code: str, models: list[tuple[str, str, str, str]],
               max_reviews: int, verbose: bool = True, *,
               retail_spec: dict | None = None,
               max_review_pages: int | None = None,
               blocked_streak_limit: int = 5,
               region_code: str = "ca", country_name: str = "Canada",
               currency: str = "CAD", db: Database | None = None,
               run_id: int | None = None, save_db: bool = False,
               stats: RunStats | None = None,
               model_sizes: dict[tuple[str, str], str] | None = None,
               search_pages: int = 0
               ) -> tuple[dict[tuple[str, str], float], list[ReviewRecord]]:
    """在一个零售站抓所有型号的价格与评价（同一商品页同步）。

    不带 ``save_db`` 时保持原有纯导出行为；带上后每个型号×站点都会写两条
    retail_task_status，命中商品则复用 scenarios.save_payload() 写通用表。

    model_sizes：可选的可变字典，用于回传 {(brand_code, model): 尺寸}，
    供价格表"尺寸"列使用（跨站共享同一份，先抓到的尺寸优先生效）。
    """
    adapter = SiteRegistry.get(site_code)
    if not getattr(adapter, "supports_retail", False):
        if verbose:
            print(f"[SKIP] {site_code} 非零售站")
        return {}, []
    site_name = adapter.channel or adapter.name
    site_id = None
    if save_db and db is not None:
        site_id = db.upsert_site(adapter.code, adapter.name, adapter.base_url,
                                 adapter.protection)
    prices: dict[tuple[str, str], float] = {}
    reviews: list[ReviewRecord] = []
    # 尺寸回传目标：优先用调用方传入的共享字典（跨站复用），否则退化为本地区。
    sizes: dict[tuple[str, str], str] = (model_sizes if isinstance(model_sizes, dict)
                                         else {})
    search_fetcher, detail_fetcher = _make_fetcher(adapter, retail_spec)

    # ---- 品牌级搜索模式（R2: 防型号不存在时误匹配广告）----
    # 对每个品牌先搜一次「品牌 tv」，把该站该品牌的全部 PDP 拿到，再用型号去映射；
    # 型号不在候选里 → 记 no_item、不抓价格（宁缺毋滥，避免把广告/配件当命中）。
    #
    # spec 可用 search.batch 控制（Costco 这类慢 SPA 站务必打开 fallback_per_model=false）：
    #   "search": {"batch": {"threshold": 40, "force": true,
    #                        "fallback_per_model": false, "max_search_failures": 2}}
    # force=true 时无论型号数多少都走批量（型号多的品牌也不逐型号搜）；
    # fallback_per_model=false 时，批量候选里没有的型号直接判 no_item，
    # 不再为它发起一次搜索——这是"避免 621 个型号把慢站刷爆"的关键开关。
    search_cfg = (retail_spec or {}).get("search") or {}
    batch_cfg = search_cfg.get("batch") or {}
    batch_threshold = int(batch_cfg.get("threshold") or 20)
    batch_force = bool(batch_cfg.get("force"))
    batch_fallback = bool(batch_cfg.get("fallback_per_model", True))
    batch_keyword_tmpl = str(batch_cfg.get("keyword_template") or "{brand} tv")
    batch_limit = int(batch_cfg.get("max_candidates") or 60)
    max_search_failures = int(batch_cfg.get("max_search_failures") or 2)
    # ★候选数下限（min_candidates）：客户端渲染的搜索页会「时好时坏」——
    # 同一 URL、同一请求头，实测 Costco US 一轮 24 个候选、下一轮 9 个、再下一轮 0 个。
    # 若把这种被截断的候选当成"该站没有这些型号"，就会把抓取失败静默写成
    # "该站确实没上架"，正是"某些型号搜不到"的假象来源。
    # 低于下限 → 记 failed 并跳过该品牌，绝不据此写 no_item；0 = 不启用。
    min_candidates = int(batch_cfg.get("min_candidates") or 0)
    search_retries = int(batch_cfg.get("retries") or 0)
    # 品牌搜索翻几页（1 = 只第 1 页）。
    # ★实测：扩页收益极低 —— US 8 页命中率仅 19.0%、CA 8 页 22.1%，
    # 而建 8 页池要多花 ~40s，净亏。故默认 1（复用首屏免一次重复搜索），
    # 池内未命中的型号由 fallback 逐型号搜索兜住覆盖率。
    search_pages = int(batch_cfg.get("search_pages") or search_pages or 1)
    # ★候选型号解析：列表页只有系列名、型号清单是厂商全码的站（Costco Samsung）
    # 必开。预算 = 候选数/品牌（~24），与该品牌型号数（224）无关；0 = 关闭。
    resolve_models = bool(batch_cfg.get("resolve_models"))
    resolve_limit = int(batch_cfg.get("resolve_limit") or 40)
    search_wait_ms = int(search_cfg.get("wait_ms", 0) or 5000)
    # 搜索页的等待锚点与滚动次数必须可配：Costco 的候选是滚动后才懒加载出来的，
    # 所以 wait_selector 只能用「页面上立刻就有」的东西（默认 "a"），
    # **不能**填候选容器本身——wait_for_selector 会先白等 8 秒超时，
    # 而滚动次数才是真正决定能拿到多少候选的参数（US 滚 3 次只有 8~9 个，
    # 滚 20 次才 24 个；候选不全就会把在售型号误判成 no_item）。
    search_wait_selector = search_cfg.get("wait_selector") or "a"
    # 默认保持 3（原行为，避免拖慢逐型号搜索的老站）；
    # 懒加载重的站才在 spec 里加大（Costco：CA 8 / US 20）。
    search_scroll_passes = int(search_cfg.get("scroll_passes") or 3)

    # 按品牌分组型号
    brand_groups: dict[str, list[tuple[str, str, str, str]]] = {}
    for entry in models:
        code, name, model, query = entry
        brand_groups.setdefault(name, []).append(entry)

    def _brand_keyword(entries: list[tuple[str, str, str, str]], fallback: str) -> str:
        """品牌搜索关键词里的品牌名。

        ★ 不能用型号清单的展示名：CA 的 brand_name 是「Hisense（加拿大）」，
        直接拼成「Hisense（加拿大） tv」会把中文括号送进搜索框。
        从 search_query 里减掉型号前缀最稳（清单里就是 "Hisense 55U7SG"）。
        """
        for _, _, model, query in entries:
            if model and model in query:
                prefix = query.rsplit(model, 1)[0].strip(" -_")
                if prefix:
                    return prefix
        return fallback

    # ---- 每个品牌：搜一次"品牌 tv"，拿候选，决定批量还是逐型号 ----
    rejected_words = ((retail_spec or {}).get("match", {}).get("reject", {})
                      or {}).get("title_contains_any", []) or []
    batch_pdp_cache: dict[str, list] = {}   # brand -> [SearchHit, ...]
    brand_mode: dict[str, str] = {}         # brand -> "batch" | "per_model" | "unavailable"
    search_failures = 0
    for brand_name, brand_models in brand_groups.items():
        if search_failures >= max(1, max_search_failures):
            brand_mode[brand_name] = "unavailable"
            continue
        if retail_spec is None:
            brand_mode[brand_name] = "per_model"
            continue
        if not batch_force and len(brand_models) > batch_threshold:
            brand_mode[brand_name] = "per_model"
            continue
        keyword = batch_keyword_tmpl.format(
            brand=_brand_keyword(brand_models, brand_name))
        search_url = _search_url(adapter, retail_spec, keyword)
        from overseas.mx_retail import _parse_search_with_spec
        tv_hits: list = []
        failure = ""
        # 重试是必要的：客户端渲染的搜索页会偶发只出部分候选，重开一次常常就正常。
        for attempt in range(max(0, search_retries) + 1):
            try:
                with open_dom(adapter, search_fetcher, search_url,
                              wait_selector=search_wait_selector,
                              scroll_passes=search_scroll_passes,
                              extra_wait_ms=search_wait_ms) as (res, dom, html):
                    if res.blocked:
                        failure = f"搜索被拦截({res.block_reason})"
                        continue
                    if not res.ok or dom is None:
                        failure = f"搜索失败({res.error or res.status})"
                        continue
                    hits = _parse_search_with_spec(retail_spec, adapter, dom, html,
                                                   limit=batch_limit)
                    tv_hits = [h for h in hits
                               if not any(w in (h.title or "").lower()
                                          for w in rejected_words)]
                    if len(tv_hits) >= max(1, min_candidates):
                        failure = ""
                        break
                    failure = (f"候选过少({len(tv_hits)} 个"
                               + (f"，低于下限 {min_candidates}" if min_candidates
                                  else "") + ")")
            except Exception as e:
                failure = f"搜索异常 {type(e).__name__}: {e}"
        if failure:
            # ★关键：候选缺失/过少时**不能**把该品牌的型号写成 no_item。
            # no_item 的语义是"站上确实没上架"，用错会把抓取失败静默伪装成
            # "该站没有这个型号"（这就是"某些型号搜不到"的假象）。
            search_failures += 1
            brand_mode[brand_name] = "unavailable"
            if verbose:
                print(f"  [{site_code}] 品牌 {brand_name}: {failure}"
                      f"（重试 {search_retries} 次后仍不达标）→ 跳过该品牌，"
                      f"不据此判定型号不存在；"
                      f"请先跑 scripts/diag_retail_search.py 确认渲染/出口 IP")
            continue
        search_failures = 0
        batch_pdp_cache[brand_name] = tv_hits
        # ---- 搜索翻页：把候选池从"第 1 页"扩到"足够覆盖型号清单" ----
        # 动机：品牌搜索首屏很小（实测 amazon_us 仅 16 个），而型号清单可达
        # 405 个；只看第 1 页会让大量真实在售型号匹配不到、被误记成 no_item。
        # 实测搜索页支持 &page=N（CA 4 页 48→192 候选，US 16→66），故翻页扩池。
        # 说明：翻页失败不影响第 1 页结果，仅少拿候选，不改变语义。
        if search_pages > 1 and retail_spec is not None:
            seen_sku = {h.sku for h in tv_hits}
            for _p in range(2, int(search_pages) + 1):
                page_url = _search_url(adapter, retail_spec, keyword, _p)
                try:
                    with open_dom(adapter, search_fetcher, page_url,
                                  wait_selector=search_wait_selector,
                                  scroll_passes=search_scroll_passes,
                                  extra_wait_ms=search_wait_ms) as (r2, d2, h2):
                        if r2.blocked or not r2.ok or d2 is None:
                            break
                        more = _parse_search_with_spec(retail_spec, adapter, d2, h2,
                                                       limit=batch_limit)
                except Exception:
                    break
                fresh = [h for h in more if h.sku not in seen_sku]
                if not fresh:
                    break
                for h in more:
                    seen_sku.add(h.sku)
                tv_hits.extend(fresh)
                if verbose:
                    print(f"      搜索翻页 p{_p}: 新增 {len(fresh)} 候选"
                          f"（累计 {len(tv_hits)}）")
        # ---- 模式决策 ----
        # prefer_pool（默认 true）：只要有候选池就用池子匹配，不再逐型号搜索。
        # 动机：逐型号搜索是单型号最大的一笔固定开销（实测 ~13s/型号，占
        # 31s 的 42%），而品牌搜索池已经把该品牌在售 PDP 都拿到了，重复搜索
        # 纯属浪费；405 型号就是 ~1.5 小时白花。全量时收益更大。
        # 代价：池子里没有的型号会记 no_item（宁缺毋滥，不编造价格）；
        # 想要更全覆盖可调大 search_pages / max_candidates 扩池。
        # 置 false 可恢复旧行为（型号数超阈值即逐型号搜索）。
        prefer_pool = bool(batch_cfg.get("prefer_pool", True))
        if batch_force or prefer_pool or len(tv_hits) <= batch_threshold:
            brand_mode[brand_name] = "batch"
            if verbose:
                why = ("force" if batch_force else
                       ("prefer_pool" if prefer_pool else "候选数<=阈值"))
                print(f"  [{site_code}] 品牌 {brand_name}: 搜'{keyword}'得 "
                      f"{len(tv_hits)} TV → 候选池匹配模式（{why}）"
                      + ("" if batch_fallback else "（不做逐型号回退）"))
        else:
            brand_mode[brand_name] = "per_model"
            if verbose:
                print(f"  [{site_code}] 品牌 {brand_name}: 搜'{keyword}'得 "
                      f"{len(tv_hits)} TV → 逐型号搜索模式")
    if search_failures >= max(1, max_search_failures) and verbose:
        print(f"  [{site_code}] 连续 {search_failures} 个品牌搜索失败 → "
              f"停止搜索其余品牌（站级熔断，避免空转）")

    # ---- 候选型号解析（只在需要的站/品牌上做）----
    # 列表页只写系列名、型号清单是厂商全码的站（Costco Samsung：列表 M70H /
    # 清单 UN55M70HAFXZC），候选级匹配必然全 miss。开这个开关后，把批量候选的
    # PDP 各打开一次解出权威型号，建立「权威型号 → 已抓好 payload」映射，
    # 匹配退化为精确相等。预算 = 候选数（~24/品牌），与型号数（224）无关。
    resolved_by_brand: dict[str, dict] = {}
    if resolve_models:
        for brand_name, mode in brand_mode.items():
            if mode != "batch" or brand_name not in batch_pdp_cache:
                continue
            resolved_by_brand[brand_name] = _resolve_brand_candidates(
                adapter, detail_fetcher, retail_spec, batch_pdp_cache[brand_name],
                resolve_limit, max_reviews, max_review_pages,
                verbose=verbose, site_code=site_code)

    # ---- 逐型号抓取（含品牌级搜索模式的优化）----
    # R1-12 站级熔断：连续 N 个型号被拦截即跳过该站剩余型号，防止被墙的站
    # 把整份型号清单（CA 有 621 个）逐个撞一遍。
    blocked_streak = 0
    login_wall_streak = 0
    try:
        for code, name, model, query in models:
            if blocked_streak >= max(1, blocked_streak_limit):
                if verbose:
                    print(f"  [{site_code}] 连续 {blocked_streak} 个型号被拦截，"
                          f"站级熔断，跳过该站剩余 {len(models)} 个型号中的未处理项")
                break

            # 品牌级搜索模式：用缓存的PDP候选匹配，不逐型号搜索
            if brand_mode.get(name) == "unavailable":
                # 该品牌的搜索页没拿到候选（被拦/渲染失败/0 结果）。
                # 这里必须记 failed 而不是 no_item：no_item 的含义是"站上确实没上架"，
                # 用错会把抓取失败伪装成"该站没有"，静默丢数据。
                if stats:
                    stats.fail += 1
                _record_pair(db, run_id, save_db, region_code, site_code, site_name,
                             code, name, model, "failed",
                             message="品牌搜索未取到候选（搜索页被拦/未渲染），"
                                     "未逐型号重试以免空转")
                if verbose:
                    print(f"  [{site_code}] {model} 跳过: 品牌 {name} 搜索候选缺失")
                continue
            if brand_mode.get(name) == "batch" and name in batch_pdp_cache:
                # 池优先；池内未命中时按 fallback_per_model 决定是否回退逐型号搜索。
                # 回退保证覆盖率（池受相关性排序限制，不覆盖全部在售型号）；
                # 关掉回退可省 ~13s/型号，但会丢覆盖率——两种口径都要能选。
                _fb = None
                if batch_fallback:
                    def _fb(adapter=adapter, model=model, query=query,
                            max_reviews=max_reviews,
                            retail_spec=retail_spec,
                            max_review_pages=max_review_pages,
                            detail_fetcher=detail_fetcher):
                        return _crawl_one(adapter, search_fetcher, model, query,
                                          max_reviews, retail_spec=retail_spec,
                                          max_review_pages=max_review_pages,
                                          detail_fetcher=detail_fetcher)
                outcome = _crawl_one_batch(adapter, search_fetcher, model, query, max_reviews,
                                           retail_spec=retail_spec,
                                           max_review_pages=max_review_pages,
                                           cached_hits=batch_pdp_cache[name],
                                           detail_fetcher=detail_fetcher,
                                           resolved=resolved_by_brand.get(name),
                                           fallback_fn=_fb,
                                           verbose=verbose)
            else:
                try:
                    outcome = _crawl_one(adapter, search_fetcher, model, query, max_reviews,
                                         retail_spec=retail_spec,
                                         max_review_pages=max_review_pages,
                                         detail_fetcher=detail_fetcher)
                except Exception as e:
                    message = f"{type(e).__name__}: {e}"
                    if stats:
                        stats.fail += 1
                    if save_db:
                        _record_pair(db, run_id, save_db, region_code, site_code, site_name,
                                     code, name, model, "failed", message=message)
                        if db is not None and run_id is not None:
                            db.log_error(run_id, "", "detail", "parse", message)
                    if verbose:
                        print(f"  [{site_code}] {model} 失败: {message}")
                    blocked_streak += 1
                    continue

            if outcome.payload is None:
                if stats:
                    if outcome.status == "blocked":
                        stats.blocked += 1
                    elif outcome.status == "failed":
                        stats.fail += 1
                # 站级熔断：blocked 或 HTTP 403/410/429 连续失败都算（和 MX 线一致）。
                # no_item（该站确实没上架）是正常结果，不触发熔断。
                # 例外：not_logged_in 是"会话失效"而非反爬，撞熔断会把整站型号
                # 静默全跳过，因此单独计数并提示补登录态。
                is_login_wall = "not_logged_in" in (outcome.message or "")
                is_block_like = (not is_login_wall) and (
                    outcome.status == "blocked"
                    or (outcome.status == "failed"
                        and any(c in (outcome.message or "")
                                for c in ("403", "410", "429"))))
                if is_login_wall:
                    login_wall_streak += 1
                    if login_wall_streak == 1 and verbose:
                        print(f"  [{site_code}] 命中登录墙（会话失效/未登录）→ "
                              f"先补登录态：python -m overseas.cli login "
                              f"--site {site_code}")
                else:
                    login_wall_streak = 0
                if is_block_like:
                    blocked_streak += 1
                else:
                    blocked_streak = 0
                _record_pair(db, run_id, save_db, region_code, site_code, site_name,
                             code, name, model, outcome.status,
                             message=outcome.message)
                if verbose:
                    label = "被拦截" if outcome.status == "blocked" else (
                        "未匹配到商品" if outcome.status == "no_item" else "失败")
                    print(f"  [{site_code}] {model} {label}: {outcome.message}")
                continue

            blocked_streak = 0
            payload = outcome.payload
            payload.product.site_code = adapter.code
            payload.product.model = payload.product.model or model[:200]
            payload.product.brand = payload.product.brand or name[:200]
            payload.product.category = payload.product.category or "TV"
            if payload.price is not None:
                payload.price.currency = payload.price.currency or currency
            price = payload.price.price if payload.price else None
            product_id = None
            new_reviews = 0
            if save_db and db is not None and site_id is not None:
                old_product = db.find_product(adapter.code, payload.product.sku)
                old_keys = (db.existing_review_keys(int(old_product["id"]))
                            if old_product else set())
                db_stats = stats or RunStats()
                product_id = save_payload(db, site_id, payload, db_stats)
                new_keys = db.existing_review_keys(product_id)
                new_reviews = len(new_keys - old_keys)

            review_count = len(payload.reviews or [])
            # 状态要如实反映"价格成功但评价未取到"的部分成功：
            # 报 ok 会掩盖评价缺口，报 blocked 又会丢掉已拿到的价格。
            msg = outcome.message or ""
            if price is None and review_count == 0:
                row_status = "no_price"
            elif review_count == 0 and ("被拦截" in msg or "not_logged_in" in msg):
                row_status = "no_reviews"
            elif price is None:
                row_status = "no_price"
            elif review_count == 0:
                row_status = "no_reviews"
            else:
                row_status = "ok"
            _record_pair(db, run_id, save_db, region_code, site_code, site_name,
                         code, name, model, row_status, item_id=payload.product.sku,
                         product_id=product_id, size=payload.product.size or "",
                         price=price, currency=(payload.price.currency
                                                if payload.price else currency),
                         review_count=review_count, review_new_count=new_reviews,
                         summary_count=(payload.summary.total_count
                                        if payload.summary else None),
                         summary_rating=(payload.summary.avg_rating
                                          if payload.summary else None))
            if verbose and row_status != "ok":
                print(f"  [{site_code}] {model} {row_status}: {msg[:60]}")
            if stats:
                stats.ok += 1
            if price is not None:
                prices[(code, model)] = price
            # 记录该型号的尺寸（商品页标题/规格得来），供价格表"尺寸"列使用。
            # 之前这里只回传价格，build_price_records 又没有 size 入参，
            # 导致尺寸列永远为空。
            if payload.product.size:
                sizes[(code, model)] = payload.product.size
            for rv in payload.reviews:
                reviews.append(ReviewRecord(
                    country=country_name, brand=name, model=model,
                    channel=site_name, size=payload.product.size or "",
                    rating=rv.rating if rv.rating is not None else "",
                    title=rv.title, body=rv.body,
                    helpful=rv.helpful_count if rv.helpful_count is not None else "",
                    review_time=rv.review_date, review_url=rv.review_url,
                    image_count=rv.image_count,
                    image_urls=" | ".join(rv.image_urls),
                    has_video="是" if rv.has_video else "否",
                    video_urls=" | ".join(rv.video_urls),
                    item_id=payload.product.sku,
                    price="" if price is None else price,
                ))
            if verbose:
                pstr = f"{price}" if price is not None else "-"
                print(f"  [{site_code}] {model} price={pstr} reviews={review_count}")
    finally:
        search_fetcher.close()
        if detail_fetcher is not search_fetcher:
            detail_fetcher.close()
    return prices, reviews


# ==================== 汇总 ====================

def build_price_records(models: list[tuple[str, str, str, str]],
                        site_prices: dict[str, dict[tuple[str, str], float]],
                        captured: str, country: str = "Canada",
                        currency: str = "CAD",
                        model_sizes: dict[tuple[str, str], str] | None = None
                        ) -> list[CaPriceRecord]:
    """把各零售站价格按 (brand, model) 汇总成一行一机型。

    model_sizes：{(brand_code, model): '65"'} —— 尺寸来自商品页抽取；
    缺省时尺寸列为空（与改动前一致）。
    """
    sizes = model_sizes or {}
    records: list[CaPriceRecord] = []
    for code, name, model, _ in models:
        retail_prices: dict[str, object] = {}
        for site, pmap in site_prices.items():
            p = pmap.get((code, model))
            if p is not None:
                retail_prices[site] = p
        records.append(CaPriceRecord(
            country=country, brand=name, model=model, currency=currency,
            size=sizes.get((code, model), ""),
            retail_prices=retail_prices, captured_at=captured))
    return records


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="多地区零售线：价格+网评同步抓取")
    p.add_argument("--region", default="ca")
    p.add_argument("--brand", action="append", help="只抓指定品牌 code，可重复")
    p.add_argument("--models", nargs="*", help="直接指定型号（仅单品牌时用，覆盖 CSV）")
    p.add_argument("--models-csv", default="",
                   help=f"型号清单 CSV，缺省按区域选择（CA 默认 {DEFAULT_MODELS_CSV}）")
    p.add_argument("--sites", nargs="*",
                   help="指定零售站 code；缺省用 regions_config 中 enabled 的零售站")
    p.add_argument("--limit-models", type=int, default=0, help="每次最多抓多少型号（0=不限）")
    p.add_argument("--max-reviews", type=int, default=None,
                   help="每型号每站最多取多少条评价（含翻页累积）。"
                        "缺省按 spec.paginate.reviews.max_reviews > 环境变量 "
                        "OVERSEAS_MAX_REVIEWS > 默认 100 解析")
    p.add_argument("--max-review-pages", type=int, default=None,
                   help="评价翻页页数安全阀（缺省 spec 或默认 10），防死循环")
    p.add_argument("--search-pages", type=int, default=0,
                   help="品牌搜索翻几页建候选池（0=用 spec 或默认 1）。"
                        "实测扩页收益极低（8 页也只覆盖约 20%% 型号），默认 1；"
                        "池内未命中的型号走逐型号回退搜索")
    p.add_argument("--spec", default="",
                   help="RetailSpec JSON 路径；提供后评价翻页按 spec 的 "
                        "paginate.reviews 执行（url_page/query_param/click_more/none）")
    p.add_argument("--out-dir", default="",
                   help="输出目录；缺省按区域归到 data/<国家中文名>/（ca→加拿大/us→美国/mx→墨西哥）")
    p.add_argument("--save-db", action="store_true", help="同时写入通用数据库和零售型号级状态")
    p.add_argument("--db", default="", help="SQLite 路径；缺省使用 config.DB_PATH")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    region = get_region(args.region)
    if region is None:
        print(f"[ERROR] 未知区域: {args.region}", file=sys.stderr)
        return 2
    brands = args.brand or []
    brand_names = {b.code: b.name for b in region.brands}
    models_csv = Path(args.models_csv) if args.models_csv else _default_models_csv(args.region)
    try:
        models = load_models(models_csv, brands, args.models, brand_names)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    if args.limit_models and args.limit_models > 0:
        models = models[:args.limit_models]
    if not models:
        print("[ERROR] 型号清单为空", file=sys.stderr)
        return 2
    sites = resolve_sites(args.region, args.sites)
    if not sites:
        print("[ERROR] 没有可用零售站（regions_config 中该区域零售站均 enabled=False，"
              "或用 --sites 显式指定）", file=sys.stderr)
        return 2

    print(f"[RETAIL] region={args.region} 型号={len(models)} 零售站={sites}")
    captured = datetime.now().strftime("%Y-%m-%d %H:%M")
    country_name = "Canada" if region.code == "ca" else region.name
    site_prices: dict[str, dict[tuple[str, str], float]] = {}
    # 跨站共享的型号→尺寸映射，供价格表"尺寸"列使用
    model_sizes: dict[tuple[str, str], str] = {}
    all_reviews: list[ReviewRecord] = []
    # RetailSpec（可选）：提供后评价翻页按 spec 的 paginate.reviews 执行
    # spec 是**逐站**的：一份 --spec 套到多个站会让 B 站用 A 站的选择器（静默错抽）。
    explicit_spec: dict | None = None
    if getattr(args, "spec", ""):
        if len(sites) > 1:
            print("[ERROR] --spec 只能配单个 --sites；多站请省略 --spec，"
                  "各站自动加载 schemas/retail_specs/<code>.retail.json", file=sys.stderr)
            return 2
        explicit_spec = load_retail_spec(args.spec)
    site_specs = {s: _resolve_site_spec(s, explicit_spec) for s in sites}
    first_spec = site_specs[sites[0]]
    # 上限解析优先级：CLI > spec > 环境变量 > 默认（后续改默认值只动一处）
    eff_max_reviews = resolve_max_reviews(first_spec, args.max_reviews)
    eff_max_pages = resolve_max_review_pages(first_spec, args.max_review_pages)
    print(f"[CFG] 评价上限 {eff_max_reviews} 条/型号，翻页安全阀 {eff_max_pages} 页，spec="
          + ",".join(f"{s}:{'有' if site_specs[s] else '无'}" for s in sites))

    run_stats = RunStats()
    db: Database | None = None
    run_id: int | None = None
    if args.save_db:
        db = Database(args.db or config.DB_PATH)
        db.init_schema()
        run_id = db.start_run(
            "ca_retail", args.region,
            {"region": args.region, "sites": sites, "models": len(models),
             "max_reviews": eff_max_reviews},
        )

    try:
        for site in sites:
            print(f"[SITE] {site} 开始（{len(models)} 型号）")
            s_spec = site_specs[site]
            prices, reviews = crawl_site(
                site, models, resolve_max_reviews(s_spec, args.max_reviews),
                region_code=args.region, retail_spec=s_spec,
                max_review_pages=resolve_max_review_pages(s_spec, args.max_review_pages),
                country_name=country_name, currency=region.currency,
                db=db, run_id=run_id, save_db=args.save_db, stats=run_stats,
                model_sizes=model_sizes,
                search_pages=int(getattr(args, "search_pages", 0) or 0),
            )
            site_prices[site] = prices
            all_reviews.extend(reviews)
            print(f"[SITE] {site} 完成：命中价格 {len(prices)}，评价 {len(reviews)} 条")

        price_records = build_price_records(
            models, site_prices, captured, country=country_name,
            currency=region.currency, model_sizes=model_sizes,
        )
        out_dir = Path(args.out_dir) if args.out_dir else (
            PROJECT_ROOT / "data" / region.name)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")
        price_csv = out_dir / f"价格监控_{region.name}_{stamp}.csv"
        price_xlsx = out_dir / f"价格监控_{region.name}_{stamp}.xlsx"
        review_csv = out_dir / f"网评汇总_{region.name}_{stamp}.csv"
        review_xlsx = out_dir / f"网评汇总_{region.name}_{stamp}.xlsx"
        price_write_csv(price_csv, price_records, args.region)
        try:
            price_write_xlsx(price_xlsx, price_records, args.region)
        except Exception as e:
            print(f"[WARN] 价格 XLSX 导出失败（缺 openpyxl?）: {e}")
        review_write_csv(review_csv, all_reviews)
        try:
            review_write_xlsx(review_xlsx, all_reviews)
        except Exception as e:
            print(f"[WARN] 网评 XLSX 导出失败: {e}")

        if db is not None and run_id is not None:
            db.finish_run(run_id, "completed", run_stats.ok,
                          run_stats.fail + run_stats.blocked, run_stats.summary())
        n_prices = sum(1 for r in price_records if r.retail_prices)
        print(f"[OK] 价格记录 {len(price_records)} 行（有价 {n_prices}）→ {price_csv.name}")
        print(f"[OK] 网评记录 {len(all_reviews)} 条 → {review_csv.name}")
        if db is not None:
            print(f"[DB] {db.path} run_id={run_id} {run_stats.summary()}")
        return 0
    except Exception as e:
        if db is not None and run_id is not None:
            db.finish_run(run_id, "failed", run_stats.ok,
                          run_stats.fail + run_stats.blocked,
                          f"{type(e).__name__}: {e}")
        raise
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
