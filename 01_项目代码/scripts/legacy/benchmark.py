"""可行性基准测试：连续采集 N 个商品，统计字段抽取成功率与封禁阈值。

与正式 CLI 分开，专用于评估：
- 各字段抽取成功率（title/brand/model/price/rating/specs/reviews）
- 首次被拦截发生在第几个商品（封禁阈值）
- 每个商品耗时与状态

用法（本地 Windows）：
    python benchmark.py --site amazon_ca --keyword "hisense tv" --count 25 --interval 6
    python benchmark.py --site amazon_ca --keyword "tcl tv" --count 25 --interval 8 --headed

结果写入 data/benchmark_<时间戳>.json，控制台打印汇总。
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime

from overseas import config
from overseas.scenarios import collect_detail, make_fetcher, open_dom
from overseas.sites import SiteRegistry


def _has(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True


def run(site_code: str, keyword: str, count: int, interval: float,
        pages: int, want_reviews: bool) -> dict:
    os.environ["OVERSEAS_MIN_INTERVAL"] = str(interval)
    os.environ["OVERSEAS_CACHE_ENABLED"] = "false"   # 基准测试必须打真实请求
    # 重新加载配置里依赖环境变量的值
    config.MIN_INTERVAL = interval
    config.CACHE_ENABLED = False

    adapter = SiteRegistry.get(site_code)
    fetcher = make_fetcher(adapter)
    report: dict = {
        "site": site_code, "keyword": keyword, "target_count": count,
        "interval": interval, "started_at": datetime.now().isoformat(timespec="seconds"),
        "search_ok": False, "items": [],
    }
    field_hit = {k: 0 for k in
                 ("title", "brand", "model", "category", "price", "currency",
                  "in_stock", "rating", "total_count")}
    specs_ok = reviews_ok = 0
    first_block_at = None
    blocked_count = 0
    detail_ok = 0

    try:
        # ---- 1) 搜索取 SKU ----
        sku_list: list[str] = []
        for page in range(1, pages + 1):
            if len(sku_list) >= count:
                break
            surl = adapter.search_url(keyword, page)
            sel = (adapter.schema.get("search") or {}).get("container", "")
            print(f"[搜索] p{page} {surl}", flush=True)
            with open_dom(adapter, fetcher, surl, wait_selector=sel) as (res, dom, html):
                if res.blocked:
                    report["search_block_reason"] = res.block_reason
                    print(f"       搜索被拦截: {res.block_reason}", flush=True)
                    break
                if not res.ok or dom is None:
                    print(f"       搜索失败 status={res.status} {res.error}", flush=True)
                    break
                hits = adapter.parse_search(dom, html, limit=count - len(sku_list))
                sku_list.extend(h.sku for h in hits)
                print(f"       命中 {len(hits)} 个（累计 {len(sku_list)}）", flush=True)
        report["search_ok"] = bool(sku_list)
        report["skus_found"] = len(sku_list)
        sku_list = sku_list[:count]

        # ---- 2) 逐个详情采集，记录每条结果 ----
        print(f"\n[详情] 开始采集 {len(sku_list)} 个商品，间隔 {interval}s\n", flush=True)
        for idx, sku in enumerate(sku_list, 1):
            t0 = time.time()
            payload, res = collect_detail(adapter, fetcher, sku,
                                          want_reviews=want_reviews)
            dt = round(time.time() - t0, 1)
            rec: dict = {"n": idx, "sku": sku, "status": res.status,
                         "blocked": res.blocked, "block_reason": res.block_reason,
                         "error": res.error, "elapsed": dt}
            if res.blocked:
                blocked_count += 1
                if first_block_at is None:
                    first_block_at = idx
                print(f"  {idx:>2}/{len(sku_list)} {sku} 被拦截 [{res.block_reason}] {dt}s",
                      flush=True)
            elif payload is None:
                print(f"  {idx:>2}/{len(sku_list)} {sku} 失败 "
                      f"status={res.status} {res.error} {dt}s", flush=True)
            else:
                detail_ok += 1
                pf, pr = payload.product, payload.price
                vals = {
                    "title": pf.title, "brand": pf.brand, "model": pf.model,
                    "category": pf.category,
                    "price": pr.price if pr else None,
                    "currency": pr.currency if pr else None,
                    "in_stock": pr.in_stock if pr else None,
                    "rating": payload.summary.avg_rating if payload.summary else None,
                    "total_count": payload.summary.total_count if payload.summary else None,
                }
                for k, v in vals.items():
                    if _has(v):
                        field_hit[k] += 1
                if payload.specs:
                    specs_ok += 1
                if payload.reviews:
                    reviews_ok += 1
                rec["fields"] = {k: (v if not isinstance(v, str) else v[:40])
                                 for k, v in vals.items()}
                rec["n_specs"] = len(payload.specs)
                rec["n_reviews"] = len(payload.reviews)
                print(f"  {idx:>2}/{len(sku_list)} {sku} ok "
                      f"model={pf.model or '-':14} price={pr.price if pr else '-'} "
                      f"specs={len(payload.specs)} reviews={len(payload.reviews)} {dt}s",
                      flush=True)
            report["items"].append(rec)
    finally:
        fetcher.close()

    n = len(report["items"])
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["summary"] = {
        "attempted": n,
        "detail_ok": detail_ok,
        "detail_ok_rate": round(detail_ok / n, 3) if n else 0,
        "blocked_count": blocked_count,
        "first_block_at": first_block_at,
        "specs_ok_rate": round(specs_ok / detail_ok, 3) if detail_ok else 0,
        "reviews_ok_rate": round(reviews_ok / detail_ok, 3) if detail_ok else 0,
        "field_hit_rate": {k: (round(v / detail_ok, 3) if detail_ok else 0)
                           for k, v in field_hit.items()},
        "rate_limiter_factor": fetcher.rate.state(),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="海外采集可行性基准测试")
    ap.add_argument("--site", default="amazon_ca")
    ap.add_argument("--keyword", default="hisense tv")
    ap.add_argument("--count", type=int, default=25)
    ap.add_argument("--interval", type=float, default=6.0)
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--no-reviews", action="store_true")
    args = ap.parse_args()

    config.ensure_dirs()
    report = run(args.site, args.keyword, args.count, args.interval,
                 args.pages, not args.no_reviews)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(config.DATA_DIR, f"benchmark_{ts}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    s = report["summary"]
    print("\n" + "=" * 60)
    print("基准测试汇总")
    print("=" * 60)
    print(f"  站点/关键词      : {report['site']} / {report['keyword']}")
    print(f"  抓取间隔         : {report['interval']}s")
    print(f"  尝试 / 成功      : {s['attempted']} / {s['detail_ok']} "
          f"(成功率 {s['detail_ok_rate']:.0%})")
    print(f"  被拦截次数       : {s['blocked_count']}")
    print(f"  首次拦截发生在   : "
          f"{('第 %d 个' % s['first_block_at']) if s['first_block_at'] else '未发生'}")
    print(f"  规格抽取成功率   : {s['specs_ok_rate']:.0%}")
    print(f"  评价抽取成功率   : {s['reviews_ok_rate']:.0%}")
    print("  字段抽取成功率   :")
    for k, v in s["field_hit_rate"].items():
        print(f"      {k:12} {v:.0%}")
    print(f"  限速退避倍数     : {s['rate_limiter_factor']}")
    print(f"\n详细结果: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
