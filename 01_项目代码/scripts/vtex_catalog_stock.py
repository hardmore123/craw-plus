# -*- coding: utf-8 -*-
"""VTEX Catalog API 全量在售电视目录抓取 + 与 SPEC 短码交叉。

对每个 VTEX 站，用分类 API 拉 "televisores"（和常见变体）前 N 页商品 JSON，
提取 (productName, link, price, brand)，从 productName/link 提取型号 token，
与本区域 SPEC 短码做子串匹配，输出该站 → 可抓 (型号, 价格样例)。

链路：VTEX API(纯JSON) → 短码匹配 → 若命中，交给零售引擎（spec 走
generic / JSON-LD）抓价格+网评。
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
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# site -> (api_host, region)
VTEX_SITES = {
    "metro_pe": ("www.metro.pe", "pe"),
    "carsa_pe": ("www.carsa.pe", "pe"),
    "credivargas_pe": ("www.credivargas.pe", "pe"),
    "comandato_ec": ("www.comandato.com", "ec"),
    "orvehogar_ec": ("www.orvehogar.com", "ec"),
    "marcimex_ec": ("www.marcimex.com", "ec"),
    "japon_ec": ("www.almacenesjapon.com", "ec"),
    "jumbo_co": ("www.jumbocolombia.com", "co"),
    "multicenter_bo": ("www.multicenter.com", "bo"),
    "laganga_ec": ("laganga.com", "ec"),
}

CATEGORIES = ["televisores", "televisores/smart-tv", "televisiones", "tv",
              "tecnologia/televisores"]

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def load_spec(region: str) -> list[dict]:
    p = REGION_MODELS.get(region, "")
    if not p or not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if m:
                out.append({"short": norm(m), "orig": m,
                            "brand": r.get("brand_name") or ""})
    return out


def crawl_catalog(host: str, cat: str, pages: int = 3) -> list[dict]:
    out = []
    for page in range(pages):
        url = (f"https://{host}/api/catalog_system/pub/products/search/{cat}"
               f"?_from={page * 10}&_to={page * 10 + 9}")
        try:
            r = requests.get(url, proxies=PROXY, headers=HEADERS, timeout=20,
                             verify=False)
        except Exception:
            continue
        if r.status_code not in (200, 206):
            continue
        try:
            data = r.json()
        except Exception:
            continue
        if not isinstance(data, list) or not data:
            break
        for d in data:
            name = d.get("productName") or ""
            skus = (d.get("items") or [{}])[0]
            sellers = (skus.get("sellers") or [{}])[0]
            offer = sellers.get("commertialOffer") or {}
            out.append({
                "name": name,
                "link": d.get("link") or "",
                "price": offer.get("Price"),
                "brand": d.get("brand") or "",
            })
    return out


def match(models: list[dict], items: list[dict]) -> list[dict]:
    hits = []
    used = set()
    for it in items:
        blob = norm((it.get("name") or "") + " " + (it.get("link") or ""))
        for m in models:
            if m["short"] in blob and m["short"] not in used:
                used.add(m["short"])
                hits.append({"model": m["orig"], "short": m["short"],
                             "name": it["name"][:110], "link": it["link"][:100],
                             "price": it["price"]})
    return hits


def main() -> None:
    results = {}
    all_rows = []
    for site, (host, region) in VTEX_SITES.items():
        spec = load_spec(region)
        if not spec:
            continue
        items: list[dict] = []
        seen = set()
        for cat in CATEGORIES:
            for it in crawl_catalog(host, cat):
                key = it["name"] + it["link"]
                if key in seen:
                    continue
                seen.add(key)
                items.append(it)
        hits = match(models=spec, items=items)
        print(f"=== {site} ({host})  拉取 {len(items)} 在售商品, SPEC 命中 {len(hits)} ===")
        for h in hits[:10]:
            print(f"   {h['model']:12} {h['price']}  <- {h['name'][:60]}")
        results[site] = {"region": region, "catalog_items": len(items),
                         "hits": len(hits), "hit_list": hits}
        for h in hits:
            all_rows.append({"site": site, "region": region, **h})
        print()
    with open("data/vtex_catalog_stock.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open("data/vtex_catalog_stock.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "region", "model", "short", "name", "link", "price"])
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print("[OUT] data/vtex_catalog_stock.json + .csv")


if __name__ == "__main__":
    main()