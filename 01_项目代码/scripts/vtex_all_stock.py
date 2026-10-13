# -*- coding: utf-8 -*-
"""VTEX 全部站在售目录扫描 → 与 SPEC 短码交叉 → 价格。

对每个 VTEX 站先试目录 Catalog API（www.<domain>/api/catalog_system/pub/products/search/<cat>），
目录 API 不通(CF/404)的站回退到 HTML 首页/分类页解析。输出 data/vtex_all_stock.csv。
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
HTML_HEADERS = dict(HEADERS)
HTML_HEADERS["Accept"] = "text/html,application/xhtml+xml"

# site, host, region, currency
VTEX_SITES = [
    ("metro_pe", "www.metro.pe", "pe", "PEN"),
    ("carsa_pe", "www.carsa.pe", "pe", "PEN"),
    ("credivargas_pe", "www.credivargas.pe", "pe", "PEN"),
    ("oechsle_pe", "www.oechsle.pe", "pe", "PEN"),
    ("plazavea_pe", "www.plazavea.com.pe", "pe", "PEN"),
    ("estilos_pe", "www.estilos.com.pe", "pe", "PEN"),
    ("cresa_ec", "www.cresa.com", "ec", "USD"),
    ("japon_ec", "www.almacenesjapon.com", "ec", "USD"),
    ("orvehogar_ec", "www.orvehogar.com", "ec", "USD"),
    ("marcimex_ec", "www.marcimex.com", "ec", "USD"),
    ("comandato_ec", "www.comandato.com", "ec", "USD"),
    ("exito_co", "www.exito.com", "co", "COP"),
    ("jumbo_co", "www.jumbocolombia.com", "co", "COP"),
    ("multicenter_bo", "www.multicenter.com", "bo", "BOB"),
    ("elektra_gt", "www.elektra.com.gt", "gt", "GTQ"),
]

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
    "gt": "",  # 危地马拉无 SPEC 型号
}

CATS = ["televisores", "televisores/smart-tv", "televisiones", "tv",
        "tecnologia/televisores", "electro/televisores"]


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
                            "brand": (r.get("brand_name") or "")[:24],
                            "bc": (r.get("brand_code") or "")[:30]})
    return out


def cat_items(host: str, cat: str) -> list[dict]:
    """拉一个分类的若干页目录 JSON。"""
    items = []
    for pg in range(0, 30, 10):
        url = (f"https://{host}/api/catalog_system/pub/products/search/{cat}"
               f"?_from={pg}&_to={pg + 9}")
        try:
            r = requests.get(url, proxies=PROXY, headers=HEADERS, timeout=18,
                             verify=False)
        except Exception:
            break
        if r.status_code not in (200, 206):
            break
        try:
            data = r.json()
        except Exception:
            break
        if not isinstance(data, list) or not data:
            break
        for it in data:
            name = it.get("productName") or ""
            low = name.lower()
            if "televisor" not in low and "tv" not in low[:6]:
                continue
            skus = (it.get("items") or [{}])[0]
            sellers = (skus.get("sellers") or [{}])[0]
            offer = sellers.get("commertialOffer") or {}
            items.append({"name": name, "link": it.get("link") or "",
                          "price": offer.get("Price"),
                          "sku_id": skus.get("itemId")})
        if len(data) < 10:
            break
    return items


def main() -> None:
    results = []
    all_rows = []
    for site, host, region, cur in VTEX_SITES:
        spec = load_spec(region)
        if not spec:
            print(f"{site}: 无 SPEC 型号清单，跳过")
            continue
        print(f"=== {site} ({host}) region={region} 型号{len(spec)} ===")
        seen = {}
        api_ok = False
        for cat in CATS:
            for it in cat_items(host, cat):
                key = it["name"]
                if key not in seen:
                    seen[key] = it
            if seen:
                api_ok = True
                break
        print(f"  目录商品 {len(seen)} 个 (API可用={api_ok})")
        # 交叉
        hit = {}
        for name, it in seen.items():
            blob = norm(name)
            for m in spec:
                if m["short"] in blob and m["short"] not in hit:
                    hit[m["short"]] = {"m": m, "it": it}
                    break
        print(f"  命中 SPEC 型号 {len(hit)}")
        for short, h in list(hit.items())[:8]:
            print(f"    {h['m']['orig']:16} {h['it']['price']} <- {h['it']['name'][:60]}")
        # 记录
        for short, h in hit.items():
            all_rows.append({
                "零售站": site, "国家": region.upper(), "品牌code": h["m"]["bc"],
                "品牌": h["m"]["brand"], "型号": h["m"]["orig"], "短码": short,
                "价格": h["it"]["price"], "货币": cur,
                "商品名": h["it"]["name"][:120], "URL": h["it"]["link"][:150],
            })
        results.append({"site": site, "cat_items": len(seen),
                        "hits": len(hit), "api_ok": api_ok})
        print()

    out_path = "data/vtex_all_stock.csv"
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["零售站", "国家", "品牌code", "品牌",
                                          "型号", "短码", "价格", "货币",
                                          "商品名", "URL"])
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"[OUT] {out_path} rows={len(all_rows)}")
    for site in VTEX_SITES:
        for r in results:
            if r["site"] == site[0]:
                print(f"  {site[0]:<16} cat={r['cat_items']} hits={r['hits']} api={r['api_ok']}")


if __name__ == "__main__":
    main()