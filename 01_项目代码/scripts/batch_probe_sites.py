# -*- coding: utf-8 -*-
"""批量探测南美零售站搜索入口形态。

对每个站点：用该国一个在售短型号构造搜索 URL（走 adapter.search_url），
返回结构化判定：搜索OK(有卡片/直达PDP) / 无结果 / HTTP错误 / 拦截。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}

PROBE_MODEL = {
    "pe": "55UR8SG",
    "ec": "55Q6QV",
    "co": "50QNED70BSA",
    "cl": "65C6K",
    "bo": "55C655",
}

SITE_REGION = {
    "hiraoka_pe": "pe", "carsa_pe": "pe", "estilos_pe": "pe", "metro_pe": "pe",
    "credivargas_pe": "pe", "efe_pe": "pe", "oechsle_pe": "pe", "lacuracao_pe": "pe",
    "plazavea_pe": "pe", "mercadolibre_pe": "pe",
    "cresa_ec": "ec", "japon_ec": "ec", "orvehogar_ec": "ec", "artefacta_ec": "ec",
    "marcimex_ec": "ec", "laganga_ec": "ec", "comandato_ec": "ec", "jaher_ec": "ec",
    "espana_ec": "ec", "megamaxi_ec": "ec", "sukasa_ec": "ec", "todohogar_ec": "ec",
    "coral_ec": "ec", "ferrisariato_ec": "ec",
    "alkosto_co": "co", "exito_co": "co", "falabella_co": "co", "jumbo_co": "co",
    "olimpica_co": "co",
    "falabella_cl": "cl", "paris_cl": "cl", "ripley_cl": "cl", "mercadolibre_cl": "cl",
    "lider_cl": "cl", "abc_cl": "cl", "hites_cl": "cl",
    "multicenter_bo": "bo", "dismac_bo": "bo", "alkostoplus_bo": "bo",
}


def detect(html: str, status: int) -> dict:
    low = html.lower()
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I)
    title = (title_m.group(1).strip()[:60] if title_m else "")
    return {
        "http": status,
        "title": title,
        "cards": len(re.findall(
            r'class=["\'][^"\']*(?:product-item|product-card|product-grid|product-tile'
            r'|search-result|grid-product|card-pdp)[^"\']*["\']', html, re.I)),
        "pdp_links": len(re.findall(
            r'<a[^>]+href=["\']([^"\']*(?:/p/|/producto/|/product/|/dp/|/televisor'
            r'|/item/|/prod-)[^"\']*)["\']', html, re.I)),
        "jsonld": any(
            "Product" in (m or "") or "ItemList" in (m or "")
            for m in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>',
                                html, re.S)),
        "cf": ("challenge-platform" in low) or ("just a moment" in low),
        "is_404": (status == 404) or ("ups! 404" in low) or ("no se encontrar" in low),
        "verification": ("verify your identity" in low or "verifica tu identidad" in low),
    }


def probe_one(site_code: str, model: str) -> dict:
    from overseas.sites import SiteRegistry
    try:
        adapter = SiteRegistry.get(site_code)
    except Exception as e:
        return {"site": site_code, "error": f"adapter:{type(e).__name__}:{e}"}
    url = adapter.search_url(model)
    t0 = time.time()
    try:
        r = requests.get(url, proxies=PROXY, headers=HEADERS, timeout=20, verify=False,
                         allow_redirects=True)
        res = detect(r.text or "", r.status_code)
        res.update({"site": site_code, "region": SITE_REGION.get(site_code, ""),
                    "url": url, "final_url": r.url[:110],
                    "elapsed": round(time.time() - t0, 1)})
        return res
    except Exception as e:
        return {"site": site_code, "region": SITE_REGION.get(site_code, ""),
                "http": 0, "error": f"{type(e).__name__}: {e}", "url": url}


def main() -> None:
    jobs = []
    for site_code, region in SITE_REGION.items():
        model = PROBE_MODEL.get(region, "")
        if model:
            jobs.append((site_code, model))
    print(f"=== 批量探测 {len(jobs)} 个站点 ===")
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(probe_one, code, m): code for code, m in jobs}
        for fut in as_completed(futs):
            res = fut.result()
            results.append(res)
            err = res.get("error", "")
            print(f"  {res.get('site','?'):<18} http={res.get('http')} "
                  f"cards={res.get('cards')} pdpl={res.get('pdp_links')} "
                  f"jsonld={res.get('jsonld')} cf={res.get('cf')} "
                  f"404={res.get('is_404')} ver={res.get('verification')} {err}")
    with open("data/_probe_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n[OUT] data/_probe_results.json rows={len(results)}")


if __name__ == "__main__":
    main()