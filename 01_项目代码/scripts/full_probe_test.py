#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""全站爬取效果测试（80 站快速探活 + 小样抓取）。

对每个站：
1. L0 适配器导入检查
2. L1 网络连通性（HTTP/API 探活）
3. L2 小样抓取（取 1-3 个产品，验证价格能拿到）

输出表格 + 汇总统计。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import sqlite3
import urllib.request
import ssl
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

# ── 代理 ──
PROXY = os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
_ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
_opener = urllib.request.build_opener(_ph, urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

DB_PATH = "data/overseas.db"


def get_db_site_counts():
    """从数据库读取每个站已有的产品数和价格数。"""
    con = sqlite3.connect(f"file:{DB_PATH}?immutable=1", uri=True)
    counts = {}
    for r in con.execute(
        "SELECT s.code, COUNT(DISTINCT p.id), COUNT(ps.id) "
        "FROM site s LEFT JOIN product p ON p.site_id=s.id "
        "LEFT JOIN price_snapshot ps ON ps.product_id=p.id "
        "GROUP BY s.code"):
        counts[r[0]] = {"products": r[1], "prices": r[2]}
    con.close()
    return counts


def probe_vtex(host):
    """VTEX API 探活。"""
    url = f"https://{host}/api/catalog_system/pub/products/search?ft=televisor&_from=0&_to=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    resp = _opener.open(req, timeout=12)
    data = json.loads(resp.read().decode("utf-8", "replace"))
    if isinstance(data, list) and len(data) > 0:
        p = data[0]
        items = p.get("items", [])
        price = None
        if items:
            sellers = items[0].get("sellers", [])
            if sellers:
                price = sellers[0].get("commertialOffer", {}).get("Price")
        return {"ok": True, "n": len(data), "price": price,
                "brand": p.get("brand", ""), "name": str(p.get("productName", ""))[:40]}
    return {"ok": False, "n": 0}


def probe_http(url):
    """纯 HTTP 探活。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es"})
    resp = _opener.open(req, timeout=12)
    return resp.getcode(), resp.read(50000).decode("utf-8", "replace")


# VTEX 14 站
VTEX_SITES = {
    "oechsle_pe": "www.oechsle.pe", "plazavea_pe": "www.plazavea.com.pe",
    "estilos_pe": "www.estilos.com.pe", "metro_pe": "www.metro.pe",
    "carsa_pe": "www.carsa.pe", "credivargas_pe": "www.credivargas.pe",
    "japon_ec": "www.almacenesjapon.com", "orvehogar_ec": "www.orvehogar.com",
    "marcimex_ec": "www.marcimex.com", "comandato_ec": "www.comandato.com",
    "exito_co": "www.exito.com", "jumbo_co": "www.jumbocolombia.com",
    "multicenter_bo": "www.multicenter.com", "elektra_gt": "www.elektra.com.gt",
}

# Magento 站（搜索页 URL）
MAGENTO_SITES = {
    "hiraoka_pe": "https://hiraoka.com.pe/catalogsearch/result/?q=televisor",
    "laganga_ec": "https://laganga.com/catalogsearch/result/?q=televisor",
    "raenco_pa": "https://www.raenco.com/catalogsearch/result/?q=televisor",
}

# 北美/日本站（已有契约 + 适配器）
NA_JP_SITES = {
    "amazon_ca": "https://www.amazon.ca/s?k=televisor+LG",
    "amazon_us": "https://www.amazon.com/s?k=TV+LG",
    "amazon_mx": "https://www.amazon.com.mx/s?k=televisor+LG",
    "kakaku_jp": "https://kakaku.com/search_results/TV/",
    "thebrick_ca": "https://www.thebrick.com/search?q=TV+LG",
    "leons_ca": "https://www.leons.ca/search?q=TV",
    "canadiantire_ca": "https://www.canadiantire.ca/en/search.html?q=TV",
}

# SPEC 品牌官网
SPEC_SITES = {
    "hisense_ca": "https://www.hisense.com/ca/tv",
    "hisense_us": "https://www.hisense-usa.com/category/televisions",
    "samsung_ca": "https://www.samsung.com/ca/tvs/",
    "samsung_us": "https://www.samsung.com/us/tvs/",
    "lg_ca": "https://www.lg.com/ca/tvs",
    "lg_us": "https://www.lg.com/us/tvs",
    "sony_ca": "https://www.sony.ca/electronics/tv",
    "sony_us": "https://www.sony.com/electronics/tv",
    "tcl_ca": "https://www.tcl.com/ca/en/products/tv",
    "tcl_us": "https://www.tcl.com/us/en/products/tv",
}


def main():
    print("=" * 80)
    print("全站爬取效果测试（80 站）")
    print("=" * 80)

    db_counts = get_db_site_counts()
    results = []

    # ── 1. VTEX 14 站（API 探活）──
    print("\n[1/5] VTEX 14 站（Catalog API）")
    for code, host in VTEX_SITES.items():
        t0 = time.time()
        try:
            r = probe_vtex(host)
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "VTEX", "method": "API",
                "status": "OK" if r["ok"] else "EMPTY",
                "ms": ms, "probe_n": r.get("n", 0),
                "probe_price": r.get("price"), "probe_brand": r.get("brand", ""),
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} OK  {ms:>4}ms  n={r.get('n',0)}  "
                  f"brand={r.get('brand',''):<10}  DB:{db['products']}/{db['prices']}",
                  flush=True)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "VTEX", "method": "API",
                "status": "ERR", "ms": ms, "err": str(e)[:50],
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} ERR {ms:>4}ms  {type(e).__name__}: {str(e)[:40]}",
                  flush=True)
        time.sleep(0.3)

    # ── 2. Magento 站（HTTP 探活）──
    print("\n[2/5] Magento 站（HTTP 探活）")
    for code, url in MAGENTO_SITES.items():
        t0 = time.time()
        try:
            status, html = probe_http(url)
            ms = int((time.time() - t0) * 1000)
            cards = len(re.findall(r"product-item", html))
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "Magento", "method": "HTTP+PW",
                "status": "OK" if cards > 0 else "NEED_PW",
                "ms": ms, "probe_n": cards,
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} {'OK' if cards>0 else 'NEED_PW'}  {ms:>4}ms  "
                  f"cards={cards}  DB:{db['products']}/{db['prices']}", flush=True)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "Magento", "method": "HTTP+PW",
                "status": "ERR", "ms": ms, "err": str(e)[:50],
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} ERR {ms:>4}ms  {type(e).__name__}: {str(e)[:40]}",
                  flush=True)
        time.sleep(0.3)

    # ── 3. 北美/日本站（HTTP 探活）──
    print("\n[3/5] 北美/日本站（HTTP 探活）")
    for code, url in NA_JP_SITES.items():
        t0 = time.time()
        try:
            status, html = probe_http(url)
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            blocked = "blocked" in html.lower() or "captcha" in html.lower()
            results.append({
                "code": code, "platform": "NA/JP", "method": "HTTP+PW",
                "status": "BLOCKED" if blocked else ("OK" if status == 200 else str(status)),
                "ms": ms,
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} {'BLOCKED' if blocked else 'OK'}  {ms:>4}ms  "
                  f"status={status}  DB:{db['products']}/{db['prices']}", flush=True)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "NA/JP", "method": "HTTP+PW",
                "status": "ERR", "ms": ms, "err": str(e)[:50],
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} ERR {ms:>4}ms  {type(e).__name__}: {str(e)[:40]}",
                  flush=True)
        time.sleep(0.3)

    # ── 4. SPEC 品牌官网（HTTP 探活）──
    print("\n[4/5] SPEC 品牌官网（HTTP 探活）")
    for code, url in SPEC_SITES.items():
        t0 = time.time()
        try:
            status, html = probe_http(url)
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "SPEC", "method": "HTTP+PW",
                "status": "OK" if status == 200 else str(status),
                "ms": ms,
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} {'OK' if status==200 else status}  {ms:>4}ms  "
                  f"DB:{db['products']}/{db['prices']}", flush=True)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            db = db_counts.get(code, {"products": 0, "prices": 0})
            results.append({
                "code": code, "platform": "SPEC", "method": "HTTP+PW",
                "status": "ERR", "ms": ms, "err": str(e)[:50],
                "db_products": db["products"], "db_prices": db["prices"],
            })
            print(f"  {code:<18} ERR {ms:>4}ms  {type(e).__name__}: {str(e)[:40]}",
                  flush=True)
        time.sleep(0.3)

    # ── 5. 数据库已有数据站汇总 ──
    print("\n[5/5] 数据库已有数据站汇总")
    for code, cnt in sorted(db_counts.items(), key=lambda x: -x[1]["products"]):
        if cnt["products"] > 0:
            print(f"  {code:<18} product={cnt['products']:>4}  price={cnt['prices']:>4}")

    # ── 汇总统计 ──
    print("\n" + "=" * 80)
    print("汇总统计")
    print("=" * 80)
    from collections import Counter
    status_count = Counter(r["status"] for r in results)
    plat_count = Counter(r["platform"] for r in results)
    has_db_data = sum(1 for c in db_counts.values() if c["products"] > 0)
    total_p = sum(c["products"] for c in db_counts.values())
    total_s = sum(c["prices"] for c in db_counts.values())
    print(f"  探活站点数: {len(results)}")
    print(f"  状态分布: {dict(status_count)}")
    print(f"  平台分布: {dict(plat_count)}")
    print(f"  DB 有数据站: {has_db_data}")
    print(f"  DB 总产品: {total_p}")
    print(f"  DB 总价格: {total_s}")

    # 写 JSON 结果
    out = "data/session/full_probe_results.json"
    os.makedirs("data/session", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  详细结果: {out}")


if __name__ == "__main__":
    main()
