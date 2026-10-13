"""诊断：打印零售站 PDP 的关键字段（型号/价格/评分/评价数）与容器命中数。

用法：
    py -3.12 scripts/diag_retail_pdp.py --site costco_ca --url <PDP URL> --dump data/_smoke
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.infra import BlockDetector, DiskCache, RateLimiter      # noqa: E402
from overseas.fetchers import BrowserFetcher                          # noqa: E402
from overseas.retail_common import jsonld_blocks, find_product_node   # noqa: E402
from overseas.retail_spec import load_retail_spec                     # noqa: E402
from overseas.scenarios import open_dom                               # noqa: E402
from overseas.sites import SiteRegistry                               # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="零售站 PDP 字段诊断")
    p.add_argument("--site", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--spec", default="")
    p.add_argument("--scroll", type=int, default=14)
    p.add_argument("--wait", type=int, default=5000)
    p.add_argument("--dump", default="")
    args = p.parse_args()

    adapter = SiteRegistry.get(args.site)
    spec = load_retail_spec(args.spec) if args.spec else None
    fetcher = BrowserFetcher(
        site_code=adapter.code,
        rate_limiter=RateLimiter(min_interval=8.0),
        detector=BlockDetector(
            ignore_markers=getattr(adapter, "block_marker_allowlist", None)),
        cache=DiskCache())
    try:
        with open_dom(adapter, fetcher, args.url,
                      wait_selector=getattr(adapter, "retail_page_wait", "body"),
                      scroll_passes=args.scroll, extra_wait_ms=args.wait) as (res, dom, html):
            print(f"[RES] ok={res.ok} status={res.status} blocked={res.blocked} "
                  f"reason={res.block_reason} len={len(html or '')}")
            if args.dump and html:
                out = Path(args.dump)
                out.mkdir(parents=True, exist_ok=True)
                f = out / f"pdp_{args.site}.html"
                f.write_text(html, encoding="utf-8")
                print(f"[DUMP] {f}")
            if dom is None:
                return 1
            report: dict = {"url": args.url}
            try:
                report["h1"] = str(dom.text("h1") or "")[:200]
            except Exception as e:
                report["h1"] = f"ERR {e}"
            for name, sel in [
                ("model_automation", "div[automation-id='modelNumber']"),
                ("model_class", ".model-number"),
                ("title_automation", "h1[automation-id='productName']"),
                ("price_value", "div.price span.value"),
                ("price_output", "span[automation-id='productPriceOutput']"),
                ("bv_avg", ".bv_avgRating_component_container"),
                ("bv_count", ".bv_numReviews_text"),
                ("bv_items", "ol.bv-content-list li.bv-content-item"),
                ("review_prop", "div[itemprop='review']"),
            ]:
                try:
                    report[name] = " | ".join(
                        str(t)[:80] for t in dom.texts(sel)[:5])
                    report[name + "_n"] = dom.count(sel)
                except Exception as e:
                    report[name] = f"ERR {type(e).__name__}: {e}"
            # JSON-LD
            blocks = jsonld_blocks(html or "")
            node = find_product_node(blocks)
            if node:
                report["jsonld_keys"] = sorted(node.keys())
                report["jsonld_name"] = str(node.get("name") or "")[:200]
                report["jsonld_model"] = str(node.get("model") or node.get("mpn") or "")
                report["jsonld_sku"] = str(node.get("sku") or "")
                off = node.get("offers")
                if isinstance(off, list):
                    off = off[0] if off else None
                report["jsonld_offers"] = (
                    {k: off.get(k) for k in ("price", "priceCurrency", "availability")}
                    if isinstance(off, dict) else None)
                agg = node.get("aggregateRating")
                report["jsonld_aggregate"] = (
                    {k: agg.get(k) for k in ("ratingValue", "reviewCount", "ratingCount")}
                    if isinstance(agg, dict) else None)
                rv = node.get("review")
                report["jsonld_review_n"] = len(rv) if isinstance(rv, list) else (1 if rv else 0)
            else:
                report["jsonld"] = "no Product node"
            report["jsonld_blocks_n"] = len(blocks)
            # 规格表里的型号行
            for m in re.finditer(r"(?:Model|型号)[^<]{0,40}", html or ""):
                report.setdefault("model_text_hits", []).append(m.group(0)[:80])
                if len(report["model_text_hits"]) >= 5:
                    break
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        fetcher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
