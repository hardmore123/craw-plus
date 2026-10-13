# -*- coding: utf-8 -*-
"""南美零售站在售库存发现：抓各站 TV 商品目录，提取在售型号，与 SPEC 短码交叉。

对每个站点，用「站点品牌搜索 + 分类页」两种方式抓商品卡（用 requests 服务端渲染，
解析不到的站标记 js_only 跳过），提取标题中的型号 token，与本国 SPEC 短码做子串匹配，
得到「该站在售且 SPEC 需要的型号」清单 → 输出 data/<site>_stock.csv。

这是"哪些型号能抓"的判定器：只有在此清单里的 (site, model) 才继续走 spec+抓取。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
from urllib.parse import quote

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
    "Accept-Language": "es,P;q=0.9,en;q=0.8",
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

# 每个国家 SPEC 短码清单
REGION_MODELS_CSV = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
}

# 每国用哪些品牌词做目录/搜索 抓取关键词
BRAND_TERMS = ["samsung", "lg", "tcl", "hisense", "sony", "philips"]


def load_spec_models(region: str) -> list[dict]:
    path = REGION_MODELS_CSV.get(region, "")
    if not path or not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if m:
                out.append({"short": m, "brand_code": r.get("brand_code") or "",
                            "brand": r.get("brand_name") or ""})
    return out


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def product_links_from_html(html: str) -> list[str]:
    """从商品卡片HTML里提取候选链接（多个形态）。"""
    pats = [
        r'href="([^"]*(?:/p/|/producto/|/product/|/dp/|/televisor|/prod-)[^"]*)"',
        r'href="(https://[^"]+/[a-z0-9-]+\.html)"',
    ]
    out = []
    seen = set()
    for pat in pats:
        for m in re.finditer(pat, html, re.I):
            h = m.group(1).split("?")[0]
            if h in seen:
                continue
            if any(x in h.lower() for x in (".css", ".js", ".png", ".jpg", ".webp",
                                            "login", "carrito", "cuenta", "ayuda",
                                            "contact", "facebook", "youtube", "api.")):
                continue
            seen.add(h)
            out.append(h)
    return out[:60]


def fetch_catalog(site_code: str, model: str) -> list[dict]:
    """抓一个站点上搜索某型号的结果页，返回命中的商品条目列表。"""
    from overseas.sites import SiteRegistry
    adapter = SiteRegistry.get(site_code)
    url = adapter.search_url(model)
    sess = requests.Session()
    sess.proxies = PROXY
    sess.headers = HEADERS
    try:
        r = sess.get(url, timeout=22, verify=False, allow_redirects=True)
        html = r.text or ""
    except Exception:
        return []
    if r.status_code != 200 or len(html) < 2000:
        return []
    # VTEX 渲染壳（无服务端商品）→ 一次性返回
    if "product-summary" not in html.lower() and "/p/" in html:
        pass
    # 提取标题候选（各类卡片通用）
    titles = re.findall(r'class="[^"]*(?:product-item-link|product-card-title|productName'
                        r'|product-name|card-title|vtex-product-summary-2-x-productName'
                        r'|product-summary-2-x-productName)[^"]*"[^>]*>\s*([^<]{5,200})<', html, re.I | re.S)
    if not titles:
        titles = re.findall(r'<a[^>]+href=["\']([^"\']+)"[^>]*>([^<]{5,200})</a>', html, re.I)
        titles = [t for _, t in titles]
    # 去重
    seen = set()
    cards = []
    for t in titles:
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in seen:
            seen.add(t)
            cards.append({"title": t})
    return cards


def match_cards(cards: list[dict], spec_models: list[dict]) -> list[dict]:
    """卡片标题里的型号是否命中 SPEC 短码（子串）。返回命中的 (型号, 标题)。"""
    out = []
    matched = set()
    for c in cards:
        tn = norm(c["title"])
        if len(tn) < 8:
            continue
        for sp in spec_models:
            want = norm(sp["short"])
            if want and want in tn and want not in matched:
                matched.add(want)
                out.append({"model": sp["short"], "brand": sp["brand"],
                            "title": c["title"][:120]})
    return out


def main() -> None:
    # 目标站点：全 39 站里 "可访问" 且已知型号的国家
    results = {}
    all_stock: list[dict] = []
    # 站点→站内在售（搜索每个品牌词一遍找卡片）
    for site_code, region in SITE_REGION.items():
        models_r = load_spec_models(region)
        if not models_r:
            continue
        # 合并：把该国所有 SPEC 型号搜一遍（对每个站逐个型号搜太贵，改为抓分类页/搜索词）
        found = {}
        for brand in BRAND_QUERY:
            cards = fetch_cards(site_code, brand)
            if not cards:
                continue
            hit = search_cards(cards, models_r)
            for h in hit:
                found.setdefault(h["model"], h)
        n = len(found)
        print(f"{site_code:<18} region={region} 命中 SPEC 在售型号 {n}")
        for h in list(found.values())[:5]:
            print(f"    {h['model']}  <- {h['title'][:60]}")
        results[site_code] = {"region": region, "in_stock_spec_models": n,
                              "models": list(found.values())}
        for h in found.values():
            all_stock.append({"site": site_code, "region": region, **h})

    os.makedirs("data/inventory", exist_ok=True)
    with open("data/inventory/stock.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    with open("data/inventory/stock_flat.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "region", "model", "brand", "title"])
        w.writeheader()
        for r in all_stock:
            w.writerow(r)
    print("\n[OUT] data/inventory/stock.json + stock_flat.csv")
    print(f"总计在售命中: {len(all_stock)} 条")


if __name__ == "__main__":
    main()