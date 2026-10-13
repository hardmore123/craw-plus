"""Best Buy 直连 PDP 抓取（不搜索）：价格 + 网评同步。

为什么需要它
------------
两家 Best Buy 的 robots.txt **都禁抓站内搜索**：

    bestbuy.ca :  Disallow: /en-ca/search  /en-ca/Search
    bestbuy.com:  Disallow: */site/searchpage.jsp?st=*

而 `crawl_ca_retail.py` 的主路径是"搜品牌 → 候选匹配 → 开 PDP"。
对 Best Buy 这条路径**既不合规，也正是"某些型号搜不到会误抓"的根源**。

本脚本改走确定性路径：

    scripts/bestbuy_ca_catalog.py build     # sitemap → 本地商品目录
        ↓
    scripts/bestbuy_ca_catalog.py match     # 型号清单 → SKU + PDP URL（确定性）
        ↓
    scripts/crawl_bestbuy_direct.py         # 直连 PDP 抓价格 + 网评（本脚本）

因为它不经过搜索结果，所以：
- **不会误抓**：候选不是"搜索返回的前几条"，而是目录里型号完全匹配的那条 SKU；
  再加一道 `payload_matches_model` 的 PDP 权威型号校验兜底；
- **不会有"搜不到"的歧义**：型号不在目录里 = 该站确实没上架，是确定性结论；
- **不会有死循环**：没有搜索重试，只有 PDP 级失败计数 + 站级熔断。

用法
----
    # 1) 建目录 + 比出型号对应关系
    py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca build
    py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca match

    # 2) 直连抓取（小样先跑）
    py -3.12 scripts/crawl_bestbuy_direct.py --site bestbuy_ca \
        --match-csv data/加拿大/bestbuy_ca_match_all.csv --limit 5

    # 3) 全量
    py -3.12 scripts/crawl_bestbuy_direct.py --site bestbuy_ca \
        --match-csv data/加拿大/bestbuy_ca_match_all.csv

★前置：能通行的出口 IP（本机实测 bestbuy.ca 应用页恒 403，真实浏览器亦然）。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                                       # noqa: E402
from overseas.fetchers import BrowserFetcher, HttpFetcher         # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.models import ProductPayload                        # noqa: E402
from overseas.price_export import PriceRecord                     # noqa: E402
from overseas.price_export import write_csv as price_write_csv    # noqa: E402
from overseas.price_export import write_xlsx as price_write_xlsx  # noqa: E402
from overseas.retail_spec import (collect_reviews_paged,          # noqa: E402
                                  load_retail_spec,
                                  payload_matches_model,
                                  resolve_max_review_pages,
                                  resolve_max_reviews)
from overseas.review_export import ReviewRecord                   # noqa: E402
from overseas.review_export import write_csv as review_write_csv  # noqa: E402
from overseas.review_export import write_xlsx as review_write_xlsx  # noqa: E402
from overseas.scenarios import open_dom                           # noqa: E402
from overseas.sites import SiteRegistry                           # noqa: E402

SITES = {
    "bestbuy_ca": {"spec": "schemas/retail_specs/bestbuy_ca.retail.json",
                   "cn_dir": "加拿大", "country": "Canada", "currency": "CAD"},
    "bestbuy_us": {"spec": "schemas/retail_specs/bestbuy_us.retail.json",
                   "cn_dir": "美国", "country": "USA", "currency": "USD"},
}

# 站级熔断：连续这么多个型号被拦就跳过该站剩余型号（防被墙时把 621 个型号逐个撞）
BLOCKED_STREAK_LIMIT = 5


@dataclass
class Row:
    brand_code: str = ""
    brand_name: str = ""
    model: str = ""
    status: str = "failed"      # ok / no_item / blocked / failed
    message: str = ""
    url: str = ""
    sku: str = ""
    price: float | None = None
    reviews: int = 0
    size: str = ""
    tried: list = field(default_factory=list)
    review_records: list = field(default_factory=list)


def _normalise_reviews(reviews) -> list:
    """为没有站内 ID 的评价生成内容指纹（与 crawl_ca_retail 同语义）。"""
    out = []
    for review in reviews or []:
        key = str(review.review_key or "").strip()
        if not key:
            material = "\x1f".join(str(v or "").strip() for v in (
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


def load_match_csv(path: Path, brands: set[str], only_found: bool
                   ) -> list[tuple[str, str, str, list[str], str]]:
    """读 catalog match 产出的 CSV → [(brand_code, brand_name, model, skus, url)]。"""
    out = []
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("brand_code") or "").strip()
            if brands and code not in brands:
                continue
            status = (row.get("status") or "").strip()
            if only_found and status != "found":
                continue
            model = (row.get("model") or "").strip()
            if not model:
                continue
            skus = [s.strip() for s in (row.get("all_skus") or "").split("|") if s.strip()]
            if not skus and (row.get("sku") or "").strip():
                skus = [(row.get("sku") or "").strip()]
            out.append((code, (row.get("brand_name") or code).strip(), model,
                        skus, (row.get("url") or "").strip()))
    return out


def _to_review_records(row: Row, payload: ProductPayload, channel: str,
                       country: str) -> list[ReviewRecord]:
    """把一次成功抓取的 payload 评价转成导出记录（关联价格/商品ID/尺寸）。"""
    price = "" if row.price is None else row.price
    out: list[ReviewRecord] = []
    for rv in payload.reviews or []:
        out.append(ReviewRecord(
            country=country, brand=row.brand_name, model=row.model,
            channel=channel, size=row.size or "",
            rating=rv.rating if rv.rating is not None else "",
            title=rv.title, body=rv.body,
            helpful=rv.helpful_count if rv.helpful_count is not None else "",
            review_time=rv.review_date, review_url=rv.review_url,
            image_count=rv.image_count,
            image_urls=" | ".join(rv.image_urls),
            has_video="是" if rv.has_video else "否",
            video_urls=" | ".join(rv.video_urls),
            item_id=row.sku, price=price))
    return out


def crawl_one(adapter, spec: dict | None, fetcher, entry, *, max_reviews: int,
              max_review_pages: int | None, country: str) -> Row:
    """直连 PDP：逐个候选 SKU 打开 → 校验型号 → 抽价格/评价。"""
    code, name, model, skus, url0 = entry
    row = Row(brand_code=code, brand_name=name, model=model)
    candidates = [adapter.product_url(s) for s in skus] or ([url0] if url0 else [])
    if not candidates:
        row.status = "no_item"
        row.message = "目录里没有该型号对应的 SKU（确定性结论：该站未上架）"
        return row

    failure = ""
    mismatch = 0
    for url in candidates[:5]:
        row.tried.append(url)
        try:
            with open_dom(adapter, fetcher, url,
                          wait_selector=getattr(adapter, "retail_page_wait", "body"),
                          scroll_passes=8, extra_wait_ms=2500) as (res, dom, html):
                if res.blocked:
                    row.status = "blocked"
                    row.message = res.block_reason or "blocked"
                    row.url = url
                    return row
                if dom is None or not res.ok:
                    failure = res.error or f"status={res.status}"
                    continue
                payload = adapter.parse_product(dom, sku=url.rstrip("/").split("/")[-1],
                                                url=url)
                if payload is None:
                    failure = "商品页解析为空"
                    continue
                # ★闸三：PDP 权威型号必须与目标型号精确一致，否则丢弃
                if not payload_matches_model(model, payload):
                    mismatch += 1
                    continue
                payload.reviews = _normalise_reviews(payload.reviews)
                if spec is not None and len(payload.reviews) < max(0, max_reviews):
                    payload.reviews, meta = collect_reviews_paged(
                        spec, adapter, fetcher, payload.product.sku or "",
                        payload.reviews, open_dom=open_dom, product_url=url,
                        max_reviews=max_reviews, max_pages=max_review_pages,
                        verbose=False)
                    if meta.get("blocked"):
                        # 评价被拦不丢弃已拿到的价格（与 CA 线同语义）
                        payload.reviews = _normalise_reviews(payload.reviews)
                        row.status = "ok"
                        row.url = url
                        row.sku = payload.product.sku
                        row.price = payload.price.price if payload.price else None
                        row.size = payload.product.size or ""
                        row.reviews = len(payload.reviews)
                        row.review_records = _to_review_records(
                            row, payload, adapter.channel or adapter.name, country)
                        row.message = f"评价页被拦截：{meta.get('block_reason')}"
                        return row
                payload.reviews = _normalise_reviews(payload.reviews)[:max(0, max_reviews)]
                row.status = "ok"
                row.url = url
                row.sku = payload.product.sku or url.rstrip("/").split("/")[-1]
                row.price = payload.price.price if payload.price else None
                row.size = payload.product.size or ""
                row.reviews = len(payload.reviews)
                row.review_records = _to_review_records(
                    row, payload, adapter.channel or adapter.name, country)
                if row.price is None and row.reviews == 0:
                    row.status = "no_price"
                    row.message = "页面无价格且无评价（可能缺货/仅第三方在售）"
                return row
        except Exception as e:
            failure = f"{type(e).__name__}: {e}"
            continue

    if failure and not mismatch:
        row.status = "failed"
        row.message = failure
    else:
        row.status = "no_item"
        row.message = (f"{len(candidates)} 个候选 PDP 均未校验到目标型号"
                       f"（权威型号不匹配 {mismatch} 次）——宁缺毋滥，不记价格")
    return row


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Best Buy 直连 PDP 抓取（不搜索）")
    p.add_argument("--site", default="bestbuy_ca", choices=sorted(SITES))
    p.add_argument("--match-csv", required=True,
                   help="bestbuy_ca_catalog.py match 产出的 CSV")
    p.add_argument("--brand", default="", help="只抓这些 brand_code，逗号分隔")
    p.add_argument("--limit", type=int, default=0, help="最多抓多少型号（0=不限）")
    p.add_argument("--max-reviews", type=int, default=None,
                   help="每型号最多评价数（缺省 spec/env/50）")
    p.add_argument("--max-review-pages", type=int, default=None,
                   help="评价翻页安全阀（缺省 spec/10）")
    p.add_argument("--out-dir", default="")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = SITES[args.site]
    adapter = SiteRegistry.get(args.site)
    spec_path = PROJECT_ROOT / cfg["spec"]
    spec = load_retail_spec(spec_path) if spec_path.exists() else None
    match_csv = Path(args.match_csv)
    if not match_csv.is_absolute():
        match_csv = PROJECT_ROOT / match_csv
    if not match_csv.exists():
        print(f"[ERROR] match CSV 不存在: {match_csv}\n"
              f"        先跑：py -3.12 scripts/bestbuy_ca_catalog.py --site "
              f"{args.site} build && ... match", file=sys.stderr)
        return 2

    brands = {b.strip() for b in (args.brand or "").split(",") if b.strip()}
    entries = load_match_csv(match_csv, brands, only_found=True)
    if args.limit > 0:
        entries = entries[:args.limit]
    if not entries:
        print("[ERROR] 没有可抓的型号（match CSV 里 status=found 的为空？）", file=sys.stderr)
        return 2

    eff_max_reviews = resolve_max_reviews(spec, args.max_reviews)
    eff_max_pages = resolve_max_review_pages(spec, args.max_review_pages)
    print(f"[START] {args.site} 型号 {len(entries)} 个｜评价上限 {eff_max_reviews} 条"
          f"｜翻页安全阀 {eff_max_pages}｜spec={'有' if spec else '无'}")
    if not config.PROXY:
        print("[WARN] 未设置 OVERSEAS_PROXY；若出口 IP 不被该站接受，会全部 blocked。",
              file=sys.stderr)

    interval = max(config.MIN_INTERVAL, adapter.suggested_interval)
    shared = {"rate_limiter": RateLimiter(min_interval=interval),
              "detector": BlockDetector(
                  ignore_markers=getattr(adapter, "block_marker_allowlist", None)),
              "cache": DiskCache()}
    fetcher = (BrowserFetcher(site_code=adapter.code, **shared)
               if adapter.requires_browser else HttpFetcher(**shared))

    rows: list[Row] = []
    blocked_streak = 0
    try:
        for i, entry in enumerate(entries, 1):
            if blocked_streak >= BLOCKED_STREAK_LIMIT:
                print(f"  ★连续 {blocked_streak} 个型号被拦 → 站级熔断，"
                      f"跳过剩余 {len(entries) - i + 1} 个型号")
                break
            row = crawl_one(adapter, spec, fetcher, entry,
                            max_reviews=eff_max_reviews,
                            max_review_pages=eff_max_pages,
                            country=cfg["country"])
            rows.append(row)
            if row.status == "blocked":
                blocked_streak += 1
            else:
                blocked_streak = 0
            if not args.quiet or row.status != "ok":
                pstr = f"{row.price}" if row.price is not None else "-"
                print(f"  [{i}/{len(entries)}] {row.brand_name} {row.model} "
                      f"{row.status} price={pstr} reviews={row.reviews}"
                      + (f" | {row.message[:70]}" if row.message else ""))
    finally:
        try:
            fetcher.close()
        except Exception:
            pass

    # ---- 汇总与导出 ----
    captured = datetime.now().strftime("%Y-%m-%d %H:%M")
    stamp = datetime.now().strftime("%Y%m%d")
    out_dir = Path(args.out_dir) if args.out_dir else (PROJECT_ROOT / "data" / cfg["cn_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    review_records: list[ReviewRecord] = []
    price_records: list[PriceRecord] = []
    for row in rows:
        review_records.extend(row.review_records)
        price_records.append(PriceRecord(
            region=cfg["country"], brand=row.brand_name, model=row.model,
            size=row.size, release="", currency=cfg["currency"],
            lowest_price=(row.price if row.price is not None else ""),
            channel=adapter.channel or adapter.name, item_id=row.sku,
            url=row.url, captured_at=captured))
    price_csv = out_dir / f"价格监控_{cfg['cn_dir']}_bestbuy_{stamp}.csv"
    review_csv = out_dir / f"网评汇总_{cfg['cn_dir']}_bestbuy_{stamp}.csv"
    price_write_csv(price_csv, price_records, blocked=False, spec=spec)
    try:
        price_write_xlsx(price_csv.with_suffix(".xlsx"), price_records,
                         blocked=False, spec=spec)
    except Exception as e:
        print(f"[WARN] 价格 XLSX 导出失败: {e}")
    review_write_csv(review_csv, review_records)
    try:
        review_write_xlsx(review_csv.with_suffix(".xlsx"), review_records)
    except Exception as e:
        print(f"[WARN] 网评 XLSX 导出失败: {e}")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    print(f"\n[RESULT] {len(rows)} 个型号：" + "，".join(
        f"{k}={v}" for k, v in sorted(counts.items())))
    print("  ★no_item = 目录里确实没有这个型号（确定性结论，不是搜索失败）")
    print(f"[SAVED] {price_csv.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
