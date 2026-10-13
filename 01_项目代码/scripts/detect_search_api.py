# -*- coding: utf-8 -*-
"""探测零售站是否提供可用的公开搜索接口（目前：VTEX Catalog API），并可回写到 spec。

为什么：VTEX 站搜索页客户端渲染，服务端 HTML 里只有导航/推荐位，spec 用 DOM 选择器
抓搜索候选会全部落空（readiness 实测 oechsle_pe 等「在售型号全部未匹配」）。
接口返回商品名/链接/参考码，型号匹配稳定。

判定：GET {base}/api/catalog_system/pub/products/search/?ft=tv&_from=0&_to=1
     → HTTP 200 且 JSON list 且首项含 productName/link → vtex_catalog 可用

用法：
  py -3.12 scripts/detect_search_api.py                    # 只探测，输出报告
  py -3.12 scripts/detect_search_api.py --apply            # 探测并给命中的 spec 写入 search.api
  py -3.12 scripts/detect_search_api.py --sites oechsle_pe metro_pe
产出：data/sandbox/search_api_detect.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def probe_vtex(base: str, proxy: str) -> tuple[bool, str]:
    url = base.rstrip("/") + "/api/catalog_system/pub/products/search/?ft=tv&_from=0&_to=1"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy} if proxy else {}))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with opener.open(req, timeout=20) as r:
            body = r.read(400000).decode("utf-8", "replace")
            if r.status not in (200, 206):
                return False, f"http {r.status}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {str(e)[:60]}"
    try:
        data = json.loads(body)
    except ValueError:
        return False, "非 JSON"
    if isinstance(data, list) and data and isinstance(data[0], dict) \
            and ("productName" in data[0] or "link" in data[0]):
        return True, str(data[0].get("productName") or "")[:60]
    return False, f"JSON 但无商品（{type(data).__name__} len={len(data) if hasattr(data, '__len__') else '-'}）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="*", default=[])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--status", default="approved,candidate")
    ap.add_argument("--proxy", default=os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877"))
    args = ap.parse_args()
    want = set(args.status.split(","))
    rows = []
    for f in sorted(glob.glob("schemas/retail_specs/*.retail.json")):
        s = json.load(open(f, encoding="utf-8"))
        code = s["code"]
        if args.sites and code not in args.sites:
            continue
        if not args.sites and s.get("status") not in want:
            continue
        if code.split("_")[0] in {"hisense", "samsung", "tcl", "lg", "sony", "philips"}:
            continue                      # 品牌官网商城另议
        ok, info = probe_vtex(s.get("base_url", ""), args.proxy)
        had = ((s.get("search") or {}).get("api") or {}).get("type", "")
        applied = ""
        if ok and args.apply:
            s.setdefault("search", {})["api"] = {
                "type": "vtex_catalog",
                "_note": "detect_search_api.py 2026-10-08 实测接口可用；搜索候选走 VTEX Catalog API，"
                         "详情页仍按 product/price 段抽取",
            }
            # VTEX 全文检索按商品名分词：「Samsung tv」在多数拉美店 0 结果（商品名写的是
            # Televisor），「Samsung」又会混进手机家电。品牌池关键词统一用「{brand} televisor」
            # （实测 credivargas_pe 0→16、oechsle_pe 50 条全是电视）。
            batch = s["search"].setdefault("batch", {})
            if batch.get("keyword_template") in (None, "", "{brand} tv"):
                batch["keyword_template"] = "{brand} televisor"
            with open(f, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(s, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            applied = "Y"
        rows.append({"site": code, "status": s.get("status"), "vtex_api": "Y" if ok else "",
                     "info": info, "already": had, "applied": applied})
        print(f"{code:24} {'VTEX' if ok else '-':5} {info}", flush=True)
    os.makedirs("data/sandbox", exist_ok=True)
    with open("data/sandbox/search_api_detect.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["site"])
        w.writeheader()
        w.writerows(rows)
    print(f"[OUT] data/sandbox/search_api_detect.csv  VTEX={sum(1 for r in rows if r['vtex_api'])}/{len(rows)}"
          f"  applied={sum(1 for r in rows if r['applied'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
