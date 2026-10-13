# -*- coding: utf-8 -*-
"""重新检查"问题站"：探测 平台API 通道，判断是否能用 API 绕过反爬。

对每个待解决站，尝试多种通道：
  1. VTEX Catalog API（很多南美站其实是 VTEX，只是 HTML 有 WAF）
  2. Magento catalogsearch（SSR 站）
  3. 搜索结果 JSON（?format=json / /suggestions 等）
  4. 分类页直达
判定：哪些站其实有公开 API 通道可用。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from urllib.parse import quote

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
    "Accept": "application/json",
}
HDR_HTML = {"User-Agent": HDR["User-Agent"], "Accept": "text/html,application/xhtml+xml"}

# 待解决站: site -> (host, 国家)
SITES = {
    "sodimac_pe": ("www.sodimac.com.pe", "秘鲁"),
    "max_gt": ("www.max.com.gt", "危地马拉"),
    "tecnofacil_gt": ("www.tecnofacil.com.gt", "危地马拉"),
    "tottus_pe": ("www.tottus.com.pe", "秘鲁"),
    "cresa_ec": ("www.crescos.com", "厄瓜多尔"),
    "sukasa_ec": ("www.sukasa.com", "厄瓜多尔"),
    "todohogar_ec": ("www.todohogar.com", "厄瓜多尔"),
    "ferrisariato_ec": ("www.ferrisariato.com", "厄瓜多尔"),
    "jaher_ec": ("www.jaher.com.ec", "厄瓜多尔"),
    "lider_cl": ("www.lider.cl", "智利"),
    "unicomer_gt": ("www.lacuracaonline.com", "危地马拉"),
    "falabella_pe": ("www.falabella.com.pe", "秘鲁"),
    "falabella_co": ("www.falabella.com.co", "哥伦比亚"),
    "falabella_cl": ("www.falabella.com", "智利"),
    "artefacta_ec": ("www.artefacta.com", "厄瓜多尔"),
    "espana_ec": ("almacenesespana.ec", "厄瓜多尔"),
    "evision_pa": ("www.evisionstore.com", "巴拿马"),
}


def try_vtex_api(host: str) -> dict:
    """VTEX Catalog API 探测。"""
    seeds = {
        "api/catalog_system/pub/products/search/?q=televisor&_from=0&_to=9",
        "api/catalog_system/pub/products/search/televisores?_from=0&_to=9",
    }
    for seed in seeds:
        try:
            r = requests.get(f"https://{host}/{seed}", proxies=PROXY, headers=HDR,
                             timeout=12, verify=False)
            if r.status_code in (200, 206):
                try:
                    data = r.json()
                    if isinstance(data, list):
                        name = (data[0].get("productName") or "") if data else ""
                        return {"ok": True, "items": len(data), "sample": name[:60]}
                except Exception:
                    continue
        except Exception:
            continue
    return {"ok": False}


def test_magento(host: str) -> dict:
    try:
        r = requests.get(f"https://{host}/catalogsearch/result/?q=televisor",
                         proxies=PROXY, headers=HDR_HTML, timeout=12, verify=False)
        if r.status_code == 200:
            html = r.text or ""
            cards = len(re.findall(r'class="[^"]*product-item[^"]*"', html, re.I))
            return {"ok": cards > 0, "cards": cards}
    except Exception:
        pass
    return {"ok": False}


def test_shopify(host: str) -> dict:
    try:
        r = requests.get(f"https://{host}/products.json?limit=5",
                         proxies=PROXY, headers=HDR, timeout=12, verify=False)
        if r.status_code == 200:
            try:
                data = r.json()
                n = len(data.get("products", []))
                return {"ok": n > 0, "products": n}
            except Exception:
                pass
        return {"ok": False}
    except Exception:
        return {"ok": False}


def test_ml_api(country: str) -> dict:
    site_map = {"秘鲁": "MPE", "智利": "MLC", "哥伦比亚": "MCO",
                "厄瓜多尔": "MEC", "玻利维亚": "MBO", "危地马拉": "MGT",
                "巴拿马": "MPA"}
    site = site_map.get(country)
    if not site:
        return {"ok": False}
    try:
        r = requests.get(f"https://api.mercadolibre.com/sites/{site}/search?q=televisor&limit=5",
                         proxies=PROXY, headers=HDR, timeout=12, verify=False)
        if r.status_code == 200:
            data = r.json()
            n = len(data.get("results", []))
            titles = [d.get("title", "")[:50] for d in data.get("results", [])[:2]]
            return {"ok": n > 0, "products": n, "sample": titles}
        return {"ok": False}
    except Exception:
        return {"ok": False}


def main() -> None:
    results = {}
    for site, (host, cc) in SITES.items():
        print(f"=== {site} ({host}) ===")
        found = {}
        # 1) VTEX API
        v = try_vtex_api(host)
        if v.get("ok"):
            found["vtex_api"] = v
            print(f"  ✓ VTEX API: {v['items']} items")
        # 2) Magento
        m = test_magento(host)
        if m.get("ok"):
            found["magento"] = m
            print(f"  ✓ Magento: {m['cards']} cards")
        # 3) Shopify
        s = test_shopify(host)
        if s.get("ok"):
            found["shopify"] = s
            print(f"  ✓ Shopify: {s['products']} products")
        # 4) MercadoLibre API
        ml = test_ml_api(cc)
        if ml.get("ok"):
            found["mercadolibre"] = ml
            print(f"  ✓ MercadoLibre({cc}): {ml['products']} prods {ml.get('sample')}")
        if not found:
            print("  ✗ 无可通 API")
        results[site] = {"host": host, "channels": found}
        print()

    with open("data/_blocked_recheck.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/_blocked_recheck.json")


if __name__ == "__main__":
    main()