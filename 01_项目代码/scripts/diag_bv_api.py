"""诊断：直接调 BazaarVoice 客户端接口，确认能否拿到 Costco 评价明细。

用法：
    py -3.12 scripts/diag_bv_api.py --client Costco-EN_CA --product-id 4201009218
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROXY = os.environ.get("OVERSEAS_PROXY", "").strip()
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

BASE = "https://apps.bazaarvoice.com/bfd/v1/clients/{client}/api-products/cv2/resources/data"


def get(url: str, timeout: int = 40) -> tuple[int, str]:
    r = requests.get(url, timeout=timeout, proxies=PROXIES, headers={
        "user-agent": UA, "accept": "application/json, text/plain, */*",
        "origin": "https://www.costco.ca", "referer": "https://www.costco.ca/",
    })
    return r.status_code, r.text


def main() -> int:
    p = argparse.ArgumentParser(description="BazaarVoice 接口诊断")
    p.add_argument("--client", default="Costco-EN_CA")
    p.add_argument("--product-id", required=True)
    p.add_argument("--locale", default="en_CA")
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    urls = [
        ("summary",
         f"{BASE.format(client=args.client)}/display/0.2alpha/product/summary"
         f"?productid={args.product_id}&contentType=reviews%2Cquestions"
         f"&reviewDistribution=primaryRating%2Crecommended&rev=0"
         f"&contentlocale={args.locale}%2Cen_US%2Cfr_CA"),
        ("products",
         f"{BASE.format(client=args.client)}/products.json?locale={args.locale}"
         f"&allowMissing=true&apiVersion=5.4&filter=id%3A{args.product_id}"),
        ("reviews-bfd",
         f"{BASE.format(client=args.client)}/reviews.json?apiVersion=5.4"
         f"&filter=productid%3A{args.product_id}&limit={args.limit}&offset=0"
         f"&include=products&contentlocale={args.locale}"),
        ("reviews-v5",
         f"{BASE.format(client=args.client)}/reviews.json?apiversion=5.4"
         f"&filter=ProductId%3A{args.product_id}&Limit={args.limit}&Offset=0"
         f"&Include=Products&contentlocale={args.locale}"),
    ]
    out = {}
    for name, url in urls:
        try:
            status, body = get(url)
        except Exception as e:
            out[name] = {"url": url, "error": f"{type(e).__name__}: {e}"}
            print(json.dumps(out[name], ensure_ascii=False))
            continue
        item: dict = {"url": url, "status": status, "len": len(body)}
        try:
            data = json.loads(body)
            item["top_keys"] = sorted(data.keys())[:20]
            if isinstance(data, dict):
                if "Results" in data:
                    item["n_results"] = len(data["Results"] or [])
                    if data["Results"]:
                        item["first_keys"] = sorted(data["Results"][0].keys())[:30]
                        item["first_sample"] = {
                            k: str(data["Results"][0].get(k))[:160]
                            for k in ("ReviewText", "Title", "Rating",
                                      "SubmissionTime", "Id", "ProductId")
                            if k in data["Results"][0]}
                    item["TotalResults"] = data.get("TotalResults")
                if "Includes" in data:
                    item["include_keys"] = sorted((data["Includes"] or {}).keys())
                    prods = ((data["Includes"] or {}).get("Products") or {})
                    item["n_products"] = len(prods)
                    for pid, pv in list(prods.items())[:1]:
                        item["product_sample"] = {
                            k: str(pv.get(k))[:120] for k in
                            ("Name", "ProductPageUrl", "ImageUrl", "ReviewCount",
                             "AverageOverallRating", "CategoryId", "EANs", "UPCs")
                            if k in pv}
                if "reviewStatistics" in data or "ReviewStatistics" in data:
                    stats = data.get("reviewStatistics") or data.get("ReviewStatistics")
                    item["stats"] = {k: stats.get(k) for k in
                                     ("TotalReviewCount", "AverageOverallRating",
                                      "OverallRatingRange") if k in stats}
                for k in ("reviewSummary", "productSummary"):
                    if k in data:
                        item[k] = str(data[k])[:300]
        except ValueError:
            item["head"] = body[:300]
        out[name] = item
        print(json.dumps(item, ensure_ascii=False, indent=2)[:2500])
    dest = PROJECT_ROOT / "data" / "_smoke" / "bv_probe.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVED] {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
