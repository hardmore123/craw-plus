# -*- coding: utf-8 -*-
"""VTEX 站价格直接抓取：分类目录 JSON → 在售 SPEC 型号 → price CSV。

不同于「引擎搜索→PDP」链路（VTEX 搜索 ?q= 不按型号过滤），本脚本：
  1) 用 VTEX 门户分类 API 拉该站 televisores 目录全部在售商品（JSON）
  2) 从商品名/链接提取型号，与本国 SPEC 短码交叉
  3) 命中 → 输出 (国家, 站点, 品牌, 型号, 价格, 币种, 商品名, URL)

这是 VTEX 平台站的「价格」产出。评价若需从 PDP 抓，评价少且多为外卖组件，
后续按 PDP JSON-LD 走 engine；本脚本先落价格。

用法: py scripts/vtex_direct_prices.py
产出: data/价格_VTEX_<国家>.csv
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

COUNTRIES = {
    "秘鲁": "pe",
    "厄瓜多尔": "ec",
    "哥伦比亚": "co",
    "智利": "cl",
    "玻利维亚": "bo",
}

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
}

CURRENCY = {"pe": "PEN", "ec": "USD", "co": "COP", "cl": "CLP", "bo": "BOB"}

# 沿用已验证的 VTEX 站
VTEX_SITES = {
    "metro_pe": "www.metro.pe",
    "carsa_pe": "www.carsa.pe",
    "credivargas_pe": "www.credivargas.pe",
    "comandato_ec": "www.comandato.com",
    "orvehogar_ec": "www.orvehogar.com",
    "marcimex_ec": "www.marcimex.com",
    "japon_ec": "www.almacenesjapon.com",
    "jumbo_co": "www.jumbocolombia.com",
    "multicenter_bo": "www.multicenter.com",
}

CATEGORIES = ["televisores", "televisores/smart-tv", "televisiones",
              "tecnologia/televisores"]


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
                            "brand": (r.get("brand_name") or "")[:20],
                            "brand_code": (r.get("brand_code") or "")[:30]})
    return out


def cat_items(host: str, cat: str, pages: int) -> list[dict]:
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
            if "televisor" not in name.lower() and "tv " not in name.lower() and not name.lower().startswith("tv"):
                continue
            skus = (d.get("items") or [{}])[0]
            sellers = (skus.get("sellers") or [{}])[0]
            offer = sellers.get("commertialOffer") or {}
            out.append({"name": name, "link": d.get("link") or "",
                        "price": offer.get("Price")})
    return out


def main() -> None:
    rows = []
    for site, host in VTEX_SITES.items():
        region = site.split("_")[1]
        model_rows = load_spec(region)
        if not model_rows:
            continue
        seen = {}
        for cat in CATEGORIES:
            for it in cat_items(host, cat, 3):
                key = it["name"]
                if key in seen:
                    continue
                seen[key] = it
        # 匹配
        hit = {}
        for name, it in seen.items():
            blob = norm(name)
            for m in model_rows:
                if m["short"] in blob and m["short"] not in hit:
                    hit[m["short"]] = {"m": m, "it": it}
        print(f"== {site}: 目录{len(seen)} 命中 {len(hit)}")
        for short, h in hit.items():
            rows.append({
                "国家": "秘鲁" if region == "pe" else
                       "厄瓜多尔" if region == "ec" else
                       "哥伦比亚" if region == "co" else
                       "玻利维亚" if region == "bo" else "智利",
                "零售站": site,
                "品牌code": h["m"]["brand_code"],
                "品牌": h["m"]["brand"],
                "型号": h["m"]["orig"],
                "短码": short,
                "价格": h["it"]["price"],
                "货币": CURRENCY.get(region, ""),
                "商品名": h["it"]["name"][:120],
                "URL": h["it"]["link"][:150],
            })
    out_csv = "data/价格_VTEX_南美.csv"
    os.makedirs("data", exist_ok=True)
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [
            "region", "零售站", "品牌code", "品牌", "型号", "短码",
            "价格", "货币", "商品名", "URL"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\n[OUT] {out_csv} rows={len(rows)}")
    for r in rows[:20]:
        print(f"  {r['零售站']:<16} {r['型号']:10} {r['价格']}"
              f" {r['货币']}  <- {r['商品名'][:50]}")


def items_cat(host: str, cat: str, pages: int):
    return []  # 占位，运行时由 fetch_catalog 替换


if __name__ == "__main__":
    main()