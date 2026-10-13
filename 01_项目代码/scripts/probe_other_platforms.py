# -*- coding: utf-8 -*-
"""批量探测 MercadoLibre + Shopify + 其他平台站 的可抓性。

MercadoLibre 用公共搜索 API；Shopify/其他 用搜索 URL + HTML 卡片/JSON-LD 判断。
输出 data/_other_platforms_probe.json。
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
    "Accept": "application/json",
}
HTML_HDR = dict(HDR)
HTML_HDR["Accept"] = "text/html,application/xhtml+xml"

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
}

# MercadoLibre: site -> (ml_site_id, region)
ML_SITES = {
    "mercadolibre_pe": ("MPE", "pe"),
    "mercadolibre_cl": ("MLC", "cl"),
}

# 其余平台: (site, host, kind, search_path_tmpl, region)
HTML_SITES = [
    ("multimax_pa", "https://www.multimax.net", "pa", "/search?q={q}"),
    ("rodelag_pa", "https://rodelag.com", "pa", "/search?q={q}"),
    ("max_gt", "https://www.max.com.gt", "gt", "/search?q={q}"),
    ("tecnofacil_gt", "https://www.tecnofacil.com.gt", "gt", "/buscar?q={q}"),
    ("alkosto_co", "https://www.alkosto.com", "co", "/search?q={q}"),
    ("lider_cl", "https://www.lider.cl", "cl", "/buscar?q={q}"),
    ("abc_cl", "https://www.abc.cl", "cl", "/buscar?q={q}"),
    ("hites_cl", "https://www.hites.com", "cl", "/buscar?q={q}"),
    ("dismac_bo", "https://www.dismac.com.bo", "bo", "/buscar?q={q}"),
    ("multicenterplus_bo", "https://alkostoplus.com", "bo", "/tienda?s={q}"),
    ("crecos_ec", "https://www.crecos.com", "ec", "/buscar?q={q}"),
    ("jaher_ec", "https://www.jaher.com.ec", "ec", "/buscar?q={q}"),
    ("sukasa_ec", "https://www.sukasa.com", "ec", "/buscar?q={q}"),
    ("todohogar_ec", "https://www.todohogar.com", "ec", "/buscar?q={q}"),
    ("ferrisariato_ec", "https://www.ferrisariato.com", "ec", "/buscar?q={q}"),
]


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def load_models(region: str) -> list[dict]:
    p = REGION_MODELS.get(region, "")
    if not p or not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if m:
                out.append({"orig": m, "short": norm(m)})
    return out


def probe_mercadolibre(site_code: str, ml_id: str, region: str) -> dict:
    models = load_models(region)
    if not models:
        return {"site": site_code, "note": "无型号"}
    hits = []
    for m in models[:6]:
        try:
            r = requests.get(
                f"https://api.mercadolibre.com/sites/{ml_id}/search?q={m['orig']}&limit=5",
                proxies=PROXY, timeout=15, verify=False)
            items = (r.json().get("results") or []) if r.status_code == 200 else []
        except Exception:
            continue
        for it in items:
            t = it.get("title") or ""
            if m["short"] in norm(t):
                hits.append({"model": m["orig"], "price": it.get("price"),
                             "currency": it.get("currency_id"), "title": t[:90],
                             "url": (it.get("permalink") or "")[:120]})
                break
    return {"site": site_code, "kind": "mercadolibre", "region": region,
            "models": len(models), "hit": len(hits), "hits": hits}


def probe_html(site: str, host: str, region: str, tmpl: str) -> dict:
    models = load_models(region)
    q = models[0]["orig"] if models else "55C6K"
    url = host + tmpl.format(q=q)
    try:
        r = requests.get(url, proxies=PROXY, headers=HTML_HDR, timeout=18,
                         verify=False, allow_redirects=True)
        html = r.text or ""
    except Exception as e:
        return {"site": site, "kind": "html", "http": 0,
                "err": f"{type(e).__name__}: {e}"}
    low = html.lower()
    return {
        "site": site, "kind": "html", "http": r.status_code, "url": r.url[:100],
        "cards": len(re.findall(r'class=["\'][^"\']*(?:product|tile|grid|search-result)[^"\']*["\']', html, re.I)),
        "pdp_links": len(re.findall(r'href=["\']([^"\']*(?:/p/|/product|/dp/|/prod-)[^"\']*)["\']', html, re.I)),
        "jsonld_product": ('"Product"' in html),
        "cf": "challenge-platform" in low or "just a moment" in low,
        "is_404": (r.status_code == 404) or ("404" in low[:500]),
    }


def main() -> None:
    results = []
    for site_code, (ml_id, region) in ML_SITES.items():
        res = probe_mercadolibre(site_code, ml_id, region)
        print(f"[ML] {site_code}: 型号{res.get('models')} 命中{res.get('hit')}")
        for h in res.get("hits", [])[:3]:
            print(f"     {h['model']:16} {h['price']} {h.get('currency','')} <- {h['title'][:50]}")
        results.append(res)

    for site, host, region, tmpl in HTML_SITES:
        res = probe_html(site, host, region, tmpl)
        print(f"[{res.get('kind')}] {site}: http={res.get('http')} cards={res.get('cards')} "
              f"pdp={res.get('pdp_links')} jsonld={res.get('jsonld_product')} "
              f"cf={res.get('cf')} 404={res.get('is_404')}")
        results.append(res)

    with open("data/_other_platforms_probe.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/_other_platforms_probe.json")


if __name__ == "__main__":
    main()