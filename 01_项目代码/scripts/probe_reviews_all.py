# -*- coding: utf-8 -*-
"""探测各可抓站商品页是否有网评：JSON-LD review / aggregateRating / 评价块。

对每站抽样最多 5 个商品 URL，统计：
  - 含 aggregateRating（评分聚合）
  - 含真实评价条目（reviewBody / review-item / 评价列表）
输出 data/_review_probe.csv
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}


def collect_urls() -> dict[str, list[str]]:
    """从各已抓文件收集每站商品 URL（每站上限 5）。"""
    urls: dict[str, list[str]] = {}
    f1 = "data/在售全量/Magento全量价格_合并.csv"
    if os.path.exists(f1):
        with open(f1, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                site = r.get("零售站", "")
                u = (r.get("URL") or "").strip()
                if site and u:
                    urls.setdefault(site, [])
                    if len(urls[site]) < 5:
                        urls[site].append(u)
    for site in ("oechsle_pe", "metro_pe", "japon_ec", "exito_co", "comandato_ec",
                 "carsa_pe", "credivargas_pe", "orvehogar_ec", "marcimex_ec",
                 "plazavea_pe", "estilos_pe", "jumbo_co", "multicenter_bo",
                 "elektra_gt"):
        f2 = f"data/在售全量/{site}_catalog_v2.csv"
        if os.path.exists(f2):
            with open(f2, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    u = (r.get("url") or "").strip()
                    if u:
                        urls.setdefault(site, [])
                        if len(urls[site]) < 5:
                            urls[site].append(u)
    # hiraoka/efe/lacuracao（Magento 引擎）
    for site, host in (("hiraoka_pe", "hiraoka.com.pe"), ("efe_pe", "www.efe.com.pe"),
                       ("lacuracao_pe", "www.lacuracao.pe")):
        urls.setdefault(site, [f"https://{host}/catalogsearch/result/?q=televisor"])
    return urls


def probe_page(url: str) -> dict:
    try:
        r = requests.get(url, proxies=PROXY, headers=HDR, timeout=12, verify=False)
        html = r.text or ""
    except Exception:
        return {"http": 0, "review_block": False, "agg_rating": 0, "review_items": 0}
    low = html.lower()
    agg = len(re.findall(r"aggregateRating", low))
    review_items = len(re.findall(
        r'(?:itemprop=["\']reviewBody["\']|class=["\'][^"\']*(?:review-item|'
        r"review-content|review-card|customer-review|pr-rd-description)[^\"']*[\"']|"
        r'"review":\s*\[)', low, re.I))
    has_block = bool(re.search(r'(?:reviews-tab|product-reviews|review-list|opiniones|'
                               r'customer__review|data-.*review)', low))
    return {"http": r.status_code if hasattr(r, "status_code") else 0,
            "review_block": has_block, "agg_rating": agg > 0,
            "review_items": review_items}


def main() -> None:
    global session
    session = requests.Session()
    session.proxies = PROXY
    session.headers = HDR

    urls_map = collect_urls()
    rows = []
    for site, urls in sorted(urls_map.items()):
        n_url = len(urls)
        agg = 0
        items = 0
        block = 0
        for u in urls:
            if "/search" in u and "televisor" in u:  # 搜索页不算
                continue
            p = probe_page(u)
            if p["agg_rating"]:
                agg += 1
            if p["review_items"]:
                items += p["review_items"]
            if p["review_block"]:
                block += 1
        verdict = "有评价" if items > 0 else ("有评分" if agg > 0 else "无网评")
        rows.append({"站": site, "抽样数": n_url, "评分聚合": agg,
                     "评价条目": items, "评价块": block, "结论": verdict})
        print(f"{site:<18} 抽样{n_url} 评分{agg} 评价条目{items} 块{block} → {verdict}")

    out = "data/_review_probe.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n[OUT] {out}")
    # 汇总
    from collections import Counter
    print("结论分布:", dict(Counter(r["结论"] for r in rows)))


if __name__ == "__main__":
    main()