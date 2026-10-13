# -*- coding: utf-8 -*-
"""Shopify 站全量 TV 抓取：products.json API 直接返回标题+价格。

Shopify 公开端点 /products.json?limit=250 返回在售全部商品（含价格/链接），
过滤电视商品后直接产出价格表，无需搜索/PDP。

用法：py scripts/shopify_full_catalog.py
输出：data/在售全量/shopify_<site>.csv + 汇总
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
import time

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

# site -> (host, 国家, 币种)
SITES = {
    "rodelag_pa": ("rodelag.com", "巴拿马", "USD"),
    "multimax_pa": ("www.multimax.net", "巴拿马", "USD"),
    "max_gt": ("www.max.com.gt", "危地马拉", "GTQ"),
}

EXCLUDE = ("soporte", "rack", "cable", "antena", "cafetera", "licuadora",
           "microond", "parrilla", "freidora", "extractor", "horno", "adorno",
           "camara", "control remoto", "funda", "hdmi", "barras mes", "cargador",
           "protector", "toma tv", "tecnolog", "combo", "juego", "accesorio",
           "lavadora", "refrig", "lavavajilla", "cocina", "aspiradora", "plancha",
           "silla", "mueble", "escritorio", "monitor", "proyector", "bombillo",
           "lampara", "aire acondicionado", "reloj", "mochila", "bocina",
           "parlante", "celular", "teclado", "mause", "audifonos", "camara web",
           "ventilador", "licuadora", "secadora", "batidora", "freidora de aire",
           "tostador", "purificador", "aspiradora", "robot", "tablet", "phone")


def is_tv(t: str) -> bool:
    """只收真正的电视：标题含 televisor / "tv Xx" 尺寸或 QLED/OLED/SMART TV 明确指电视。"""
    low = t.lower()
    if any(x in low for x in EXCLUDE):
        return False
    tv_word = "televisor" in low or "television" in low or "tv " in low or " tv" in low
    panel = ("qled" in low or "oled" in low or "uled" in low or "nano" in low
             or "neo qled" in low or "mini led" in low or "smart tv" in low)
    return tv_word and panel


def model_of(t: str) -> str:
    up = t.upper()
    toks = re.split(r"[^A-Z0-9]+", up)
    for tok in toks:
        if re.fullmatch(r"(?:QN|UN|RN|UA|MR|AU|QE)[A-Z0-9]{6,14}", tok):
            return tok
    for tok in toks:
        if re.fullmatch(r"\d{2,3}[A-Z][A-Z0-9]{2,9}", tok) and len(tok) >= 4:
            if re.fullmatch(r"\d{2,3}HZ", tok, re.I):
                continue
            return tok
    m = re.findall(r"\b(\d{2,3}[A-Z][A-Z0-9]{2,9})\b", up)
    return m[-1] if m else ""


def fetch_all_pages(host: str) -> list[dict]:
    """翻页拉取全部 products。"""
    all_products = []
    url = f"https://{host}/products.json?limit=250"
    while url:
        try:
            r = requests.get(url, proxies=PROXY, headers=HDR, timeout=20, verify=False)
            if r.status_code != 200:
                print(f"  HTTP {r.status_code}")
                break
            data = r.json()
            prods = data.get("products", [])
            all_products.extend(prods)
            link = r.headers.get("Link", "")
            m = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = m.group(1) if m else None
            if len(prods) < 250:
                break
        except Exception as e:
            print(f"  ERR {type(e).__name__}: {e}")
            break
    return all_products


def main() -> int:
    os.makedirs("data/在售全量", exist_ok=True)
    all_rows = []
    for site, (host, cc, cur) in SITES.items():
        print(f"=== {site} ({host}) ===")
        prods = fetch_all_pages(host)
        print(f"  Shopify 商品总数: {len(prods)}")
        tv = []
        for p in prods:
            t = (p.get("title") or "").strip()
            ptype = (p.get("product_type") or "").lower()
            tlow = t.lower()
            # product_type 明确含 televis → 100% 是电视（标题里的 HDMI/USB/WiFi 是功能说明，不是配件）
            if "televis" in ptype:
                pass
            # 标题判定路径才用排除词（避免 HDMI 这类功能词误杀电视）
            elif not is_tv(t):
                continue
            v = (p.get("variants") or [{}])[0]
            price = v.get("price")
            tv.append({
                "site": site, "host": host, "国家": cc, "币种": cur,
                "title": t[:110], "model": model_of(t),
                "price": price, "url": f"https://{host}/products/{p.get('handle')}",
                "抓取时间": "2026-09-19 17:00:00",
            })
        print(f"  电视商品: {len(tv)}")
        # 写每站文件
        fname = f"data/在售全量/shopify_{site}.csv"
        with open(fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(tv[0].keys())) if tv else None
            if w:
                w.writeheader()
                w.writerows(tv)
        # 汇总
        all_rows.extend(tv)
        for x in tv[:5]:
            print(f"    {x['model']:<18}{x['price']:>9} {cur}  {x['title'][:50]}")
    # 汇总文件
    out = "data/在售全量/shopify全量.csv"
    os.makedirs("data/在售全量", exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        if all_rows:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
    print(f"\n[OUT] {out} rows={len(all_rows)}")
    from collections import Counter
    print(f"按站: {dict(Counter(r['site'] for r in all_rows))}")
    print(f"总计: {len(all_rows)} 条 TV 价格")
    return 0


if __name__ == "__main__":
    main()