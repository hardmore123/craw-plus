"""诊断：把一个零售站搜索页的候选原样打印出来（回答"某型号到底搜不搜得到"）。

用法：
    py -3.12 scripts/diag_retail_search.py --site costco_ca \
        --spec schemas/retail_specs/costco_ca.retail.json \
        --keyword "Hisense tv" --scroll 20 --wait 10000 --dump data/_smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.infra import BlockDetector, DiskCache, RateLimiter      # noqa: E402
from overseas.fetchers import BrowserFetcher                          # noqa: E402
from overseas.mx_retail import _parse_search_with_spec                # noqa: E402
from overseas.retail_spec import load_retail_spec                     # noqa: E402
from overseas.scenarios import open_dom                               # noqa: E402
from overseas.sites import SiteRegistry                               # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="零售站搜索候选诊断")
    p.add_argument("--site", required=True)
    p.add_argument("--spec", default="")
    p.add_argument("--keyword", required=True)
    p.add_argument("--scroll", type=int, default=20)
    p.add_argument("--wait", type=int, default=10000)
    p.add_argument("--limit", type=int, default=60)
    p.add_argument("--dump", default="", help="把渲染后 HTML 落到该目录")
    p.add_argument("--wait-selector", default="a",
                   help="等待锚点；默认 a（几乎立刻返回）。传候选容器可对比差异")
    args = p.parse_args()

    adapter = SiteRegistry.get(args.site)
    spec = load_retail_spec(args.spec) if args.spec else None
    fetcher = BrowserFetcher(
        site_code=adapter.code,
        rate_limiter=RateLimiter(min_interval=8.0),
        detector=BlockDetector(
            ignore_markers=getattr(adapter, "block_marker_allowlist", None)),
        cache=DiskCache())
    url = adapter.search_url(args.keyword)
    print(f"[URL] {url}")
    try:
        with open_dom(adapter, fetcher, url, wait_selector=args.wait_selector,
                      scroll_passes=args.scroll, extra_wait_ms=args.wait) as (res, dom, html):
            print(f"[RES] ok={res.ok} status={res.status} blocked={res.blocked} "
                  f"reason={res.block_reason} final={getattr(res, 'url', '')} len={len(html or '')}")
            if args.dump and html:
                out = Path(args.dump)
                out.mkdir(parents=True, exist_ok=True)
                f = out / f"search_{args.site}_{abs(hash(args.keyword)) % 100000}.html"
                f.write_text(html, encoding="utf-8")
                print(f"[DUMP] {f}")
            if dom is None:
                return 1
            hits = (_parse_search_with_spec(spec, adapter, dom, html, limit=args.limit)
                    if spec else adapter.parse_search(dom, html, limit=args.limit))
            print(f"[HITS] {len(hits)}")
            for h in hits:
                print(json.dumps({"sku": h.sku, "title": h.title, "url": h.url},
                                 ensure_ascii=False))
            # 容器命中数（排查 spec 选择器是否失效）
            if spec:
                container = (spec.get("search") or {}).get("container") or ""
                blocks = dom.sub(container, limit=200)
                print(f"[RAW] container={container!r} count={len(blocks)}")
                if not hits:
                    print("[RAW_HREF] 候选容器命中但未解析出 sku，前 10 个 href/属性：")
                    for b in blocks[:10]:
                        print("   href=", b.self_attr("href"),
                              "| data-pdp-url=", b.self_attr("data-pdp-url"),
                              "| text=", (b.self_text() or "").strip()[:80])
    finally:
        fetcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
