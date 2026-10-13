# -*- coding: utf-8 -*-
"""第二轮补探：对"可达但未挖到商品"的站，尝试多种搜索路径/分类页/API，确认是否可抓。"""
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
    "Accept": "text/html,application/xhtml+xml,application/json",
}

SITES = {
    "artefacta_ec": ("www.artefacta.com", "magento"),
    "cresa_ec": ("www.crescos.com", "other"),
    "ferrisariato_ec": ("www.ferrisariato.com", "other"),
    "jaher_ec": ("www.jaher.com.ec", "other"),
    "lider_cl": ("www.lider.cl", "other"),
    "max_gt": ("www.max.com.gt", "shopify"),
    "sodimac_pe": ("www.sodimac.com.pe", "magento"),
    "sukasa_ec": ("www.sukasa.com", "other"),
    "tecnofacil_gt": ("www.tecnofacil.com.gt", "other"),
    "todohogar_ec": ("www.todohogar.com", "other"),
    "tottus_pe": ("www.tottus.com.pe", "other"),
    "falabella_cl": ("www.falabella.com", "magento"),
    "unicomer_gt": ("www.lacuracaonline.com", "magento"),
}

SEARCH_PATHS = [
    "/catalogsearch/result/?q={q}",
    "/search?q={q}",
    "/buscar?q={q}",
    "/busqueda?q={q}",
    "/catalog?q={q}",
    "/catalogsearch/result/?q={q}&product_list_limit=48",
    "/buscador?txtSearch={q}",
    "/televisores?q={q}",
    "/search-results?q={q}",
    "/api/catalog_system/pub/products/search/?q={q}",
]


def http_get(url: str, timeout: int = 18) -> tuple[int, str]:
    try:
        r = requests.get(url, proxies=PROXY, headers=HDR, timeout=timeout,
                         verify=False, allow_redirects=True)
        return r.status_code, r.text or ""
    except Exception:
        return 0, ""


def find_search_actions(html: str) -> list[str]:
    actions = []
    for m in re.finditer(r'<form[^>]*action=["\']([^"\']+)["\']', html, re.I):
        a = m.group(1).strip()
        if a and a not in actions and not any(x in a.lower() for x in
                                              ("login", "cart", "register", "checkout")):
            actions.append(a)
    return actions[:10]


def page_signals(html: str) -> dict:
    low = html.lower()
    return {
        "jsonld": bool(re.search(r'[@"]type["\s:\]]*["\']?(?:Product|ItemList)', html, re.I))
                  or bool(re.search(r'application/ld\+json[^>]*>', html)),
        "cards": len(re.findall(
            r'class=["\'][^"\']*(?:product-item|product-card|card-product|product-tile|'
            r'product-grid|search-result-item|galleryItem)[^"\']*["\']', html, re.I)),
        "pdp_links": len(re.findall(
            r'href=["\'][^"\']*(?:/p/|/product(?:o)?/|/prod-|/products/|/itm/|/dp/|\.html)'
            r'[^"\']*["\']', html, re.I)),
        "tv_in_title": bool(re.search(r"televis|smart\s*тv|\bTV\b", html[:2000], re.I)),
    }


def reprobe_one(site: str, host: str) -> dict:
    res = {"site": site, "host": host, "final": "未发现", "trial": [],
           "homepage_http": 0, "search_actions": []}

    # 1) 首页
    code, html = http_get(f"https://{host}/")
    res["homepage_http"] = code
    if code == 200:
        res["search_actions"] = find_search_actions(html)
        sig = scan_signals(html)
        if sig["cards"] > 0 or sig["jsonld"] or sig["pdp_links"]:
            res["final"] = "首页即有商品"
            res["detail"] = sig
            return res

    # 2) 搜索路径逐一试
    for sp in SEARCH_PATHS:
        url = f"https://{host}{sp.format(q=quote('televisor'))}"
        c, h = http_get(url)
        if c != 200:
            res["trial"].append({"path": sp, "http": c})
            continue
        sig = scan_signals(h)
        res["trial"].append({"path": sp, "http": c, **sig})
        if sig["cards"] > 0 or sig["jsonld"] or sig["pdp_links"]:
            res["final"] = "可抓"
            res["found_path"] = sp
            res["detail"] = sig
            return res

    # 3) 首页 action 兜底
    for a in res["search_actions"]:
        a = a.replace("{?}", "").rstrip("?")
        if "?q=" in a or "&q=" in a or a.endswith("search") or "buscar" in a or "search" in a:
            sep = "&" if "?" in a else "?"
            url = a if a.startswith("http") else f"https://{host}{a}"
            if "q=" not in url:
                url = f"{url}{sep}q=televisor"
            c, h = http_get(url)
            sig = scan_signals(h)
            if c == 200 and (sig["cards"] > 0 or sig["jsonld"]):
                res["final"] = "可抓(action)"
                res["found_path"] = a
                res["detail"] = sig
                return res
    return res


def scan_signals(html: str) -> dict:
    low = html.lower()
    cards = len(re.findall(
        r'class=["\'][^"\']*(?:product-item|product-card|card-product|product-tile|'
        r'product-grid|search-result-item|galleryItem)[^"\']*["\']', html, re.I))
    pdp = len(re.findall(
        r"href=[\"'][^\"']*(?:/p/|/product|/products/|/itm/|/dp/|\.html)[^\"']*[\"']",
        html, re.I))
    jsonld = bool(re.search(r'application/ld\+json', low))
    return {"cards": cards, "pdp_links": pdp, "jsonld": jsonld}


def main() -> None:
    results = []
    for site, (host, platform) in SITES.items():
        print(f"=== {site} ({host}, {platform}) ===")
        res = reprobe_one(site, host)
        print(f"  首页 http={res['homepage_http']} actions={res['search_actions'] or '(无)'}")
        if res["final"] == "可抓":
            print(f"  ✓ 可抓 @ {res.get('found_path')} cards={res['detail']['cards']} pdp={res['detail']['pdp_links']} jsonld={res['detail']['jsonld']}")
        else:
            print(f"  ✗ 未发现可抓商品路径")
            for t in res["trial"][:8]:
                if t.get("path"):
                    print(f"    {t['path']}: http={t['http']} cards={t.get('cards',0)} pdp={t.get('pdp_links',0)}")
        results.append(res)
        print()
    with open("data/_reprobe_zero.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/_reprobe_zero.json")


if __name__ == "__main__":
    main()