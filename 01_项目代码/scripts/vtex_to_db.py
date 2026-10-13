#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""VTEX Catalog API → SQLite 入库脚本。

对 14 个 VTEX 南美站：用 Catalog API 拉 televisores 全量商品 JSON，
提取 价格/品牌/型号/标题，写入 overseas.db 的 site + product + price_snapshot 表。

用法:
    python scripts/vtex_to_db.py [--dry-run] [--limit N]

--dry-run  只打印不写库
--limit N  每站最多抓 N 个商品（测试用）
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import ssl
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

# ── 代理 ──
PROXY = os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
_ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
_opener = urllib.request.build_opener(_ph, urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# ── VTEX 14 站 ──
VTEX_SITES = {
    "oechsle_pe":      ("www.oechsle.pe",        "Oechsle",        "PEN"),
    "plazavea_pe":     ("www.plazavea.com.pe",   "PlazaVea",       "PEN"),
    "estilos_pe":      ("www.estilos.com.pe",    "Estilos",        "PEN"),
    "metro_pe":        ("www.metro.pe",          "Metro",          "PEN"),
    "carsa_pe":        ("www.carsa.pe",          "Carsa",          "PEN"),
    "credivargas_pe":  ("www.credivargas.pe",    "Credivargas",    "PEN"),
    "japon_ec":        ("www.almacenesjapon.com","Japon EC",       "USD"),
    "orvehogar_ec":    ("www.orvehogar.com",     "Orvehogar",      "USD"),
    "marcimex_ec":     ("www.marcimex.com",      "Marcimex",       "USD"),
    "comandato_ec":    ("www.comandato.com",     "Comandato",      "USD"),
    "exito_co":        ("www.exito.com",         "Exito",          "COP"),
    "jumbo_co":        ("www.jumbocolombia.com", "Jumbo",          "COP"),
    "multicenter_bo":  ("www.multicenter.com",   "Multicenter",    "BOB"),
    "elektra_gt":      ("www.elektra.com.gt",    "Elektra",        "GTQ"),
    "cresa_ec":        ("www.crecos.com",        "Cresa",          "USD"),
}

DB_PATH = "data/overseas.db"
PAGE_SIZE = 50  # VTEX API 每页最多 50 条
MAX_PAGES = 5   # 最多翻 5 页 = 250 个商品/站（实测 televisor 搜索一般 50-150 条）


def model_from_title(t: str) -> str:
    """从商品名提取疑似型号 token。"""
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", (t or "").upper())
    return m[-1] if m else ""


def size_from_title(t: str) -> str:
    """从商品名提取尺寸（英寸）。"""
    m = re.findall(r"\b(\d{2})\s*[\" pulgadas inch]+\b", (t or "").lower())
    return m[0] if m else ""


def fetch_vtex_page(host: str, keyword: str, page: int, retries: int = 2) -> list[dict]:
    """拉取 VTEX Catalog API 一页产品（含重试）。"""
    frm = page * PAGE_SIZE
    url = (f"https://{host}/api/catalog_system/pub/products/search"
           f"?ft={keyword}&_from={frm}&_to={frm + PAGE_SIZE - 1}")
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            resp = _opener.open(req, timeout=15)
            body = resp.read()
            return json.loads(body.decode("utf-8", "replace"))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0)
    raise last_err


def crawl_vtex_site(host: str, keyword: str = "televisor", limit: int = 0) -> list[dict]:
    """拉取一个 VTEX 站的全部 TV 产品。"""
    all_items = []
    for page in range(MAX_PAGES):
        try:
            data = fetch_vtex_page(host, keyword, page)
        except Exception as e:
            print(f"    page {page} err: {type(e).__name__}: {str(e)[:60]}")
            break
        if not isinstance(data, list) or not data:
            break
        for p in data:
            name = p.get("productName", "")
            low = name.lower()
            # 过滤非 TV 产品
            if not any(k in low for k in ("televis", "tv ", "tv\"", "smart tv",
                                          "uhd", "qled", "oled", "led tv")):
                continue
            items = p.get("items", [])
            price = list_price = None
            available = False
            if items:
                sellers = items[0].get("sellers", [])
                if sellers:
                    co = sellers[0].get("commertialOffer", {})
                    price = co.get("Price")
                    list_price = co.get("ListPrice")
                    available = co.get("Available", False)
            sku = str(p.get("productId", "")) or (items[0].get("itemId", "") if items else "")
            all_items.append({
                "sku": str(sku),
                "url": p.get("link", ""),
                "title": name,
                "brand": p.get("brand", "") or "",
                "model": model_from_title(name),
                "size": size_from_title(name),
                "price": float(price) if price is not None and price > 0 else None,
                "list_price": float(list_price) if list_price and list_price > 0 else None,
                "available": available,
            })
        if limit and len(all_items) >= limit:
            return all_items[:limit]
        if len(data) < PAGE_SIZE:
            break
        time.sleep(0.3)  # 限速
    return all_items


def ensure_site(con: sqlite3.Connection, code: str, name: str, base_url: str) -> int:
    """确保 site 表有该站点，返回 site_id。"""
    row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
    if row:
        return row[0]
    cur = con.execute(
        "INSERT INTO site (code, name, base_url, protection, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (code, name, base_url, "L2",
         datetime.now(timezone.utc).isoformat()))
    return cur.lastrowid


def write_to_db(con: sqlite3.Connection, site_code: str, site_name: str,
                base_url: str, currency: str, items: list[dict]) -> dict:
    """把一个站的产品和价格写入 DB。"""
    stats = {"site": site_code, "new_products": 0, "exist_products": 0,
             "new_prices": 0, "skip_no_price": 0}
    site_id = ensure_site(con, site_code, site_name, base_url)
    now = datetime.now(timezone.utc).isoformat()
    for it in items:
        if not it["sku"]:
            continue
        # upsert product（先查存在）
        row = con.execute(
            "SELECT id FROM product WHERE site_id = ? AND sku = ?",
            (site_id, it["sku"])).fetchone()
        if row:
            pid = row[0]
            stats["exist_products"] += 1
            con.execute("UPDATE product SET last_seen = ?, brand = ?, model = ?, "
                        "size = ? WHERE id = ?",
                        (now, it["brand"], it["model"], it["size"], pid))
        else:
            cur = con.execute(
                "INSERT INTO product (site_id, sku, url, title, brand, model, "
                "category, first_seen, last_seen, size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (site_id, it["sku"], it["url"], it["title"], it["brand"],
                 it["model"], "TV", now, now, it["size"]))
            pid = cur.lastrowid
            stats["new_products"] += 1
        # 写 price_snapshot（只 INSERT 不 UPDATE）
        if it["price"] is not None:
            con.execute(
                "INSERT INTO price_snapshot (product_id, price, list_price, "
                "currency, in_stock, raw_text, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, it["price"], it["list_price"], currency,
                 1 if it["available"] else 0,
                 f"VTEX API: {it['title'][:60]}", now))
            stats["new_prices"] += 1
        else:
            stats["skip_no_price"] += 1
    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 3

    if dry_run:
        print("[DRY RUN] 不写库\n")
    else:
        # 备份数据库
        import shutil
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"data/db/backup/overseas_before_vtex_{stamp}.bak"
        os.makedirs("data/db/backup", exist_ok=True)
        src = sqlite3.connect(DB_PATH)
        dst = sqlite3.connect(bak)
        with dst:
            src.backup(dst)
        dst.close()
        src.close()
        print(f"数据库已备份: {bak}\n")

    con = sqlite3.connect(DB_PATH) if not dry_run else None

    all_stats = []
    for code, (host, name, cur) in VTEX_SITES.items():
        print(f"=== {code} ({host}) ===")
        try:
            items = crawl_vtex_site(host, limit=limit)
        except Exception as e:
            print(f"  抓取失败: {type(e).__name__}: {e}")
            all_stats.append({"site": code, "error": str(e)[:80]})
            continue
        print(f"  TV 产品: {len(items)}")
        if not items:
            all_stats.append({"site": code, "error": "0 products"})
            continue
        has_price = sum(1 for i in items if i["price"] is not None)
        print(f"  有价格: {has_price}")
        if not dry_run and con:
            stats = write_to_db(con, code, name, f"https://{host}", cur, items)
            print(f"  入库: 新产品 {stats['new_products']}, "
                  f"已有 {stats['exist_products']}, "
                  f"价格快照 {stats['new_prices']}, "
                  f"无价跳过 {stats['skip_no_price']}")
            all_stats.append(stats)
        else:
            # dry-run 打印样例
            for it in items[:3]:
                print(f"    {it['brand']:<12} {it['price']} {cur}  {it['title'][:50]}")
            all_stats.append({"site": code, "items": len(items), "has_price": has_price})
        time.sleep(0.5)  # 站间限速

    if not dry_run and con:
        con.commit()
        # 验证
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        total_s = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
        total_sites = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
        print(f"\n=== 入库后 ===")
        print(f"  integrity: {ok}")
        print(f"  site 总数: {total_sites}")
        print(f"  product 总数: {total_p}")
        print(f"  price_snapshot 总数: {total_s}")
        # 按站统计
        print(f"  VTEX 站入库明细:")
        for r in con.execute(
            "SELECT s.code, COUNT(DISTINCT p.id), COUNT(ps.id) "
            "FROM site s LEFT JOIN product p ON p.site_id=s.id "
            "LEFT JOIN price_snapshot ps ON ps.product_id=p.id "
            "WHERE s.code LIKE '%_pe' OR s.code LIKE '%_ec' OR s.code LIKE '%_co' "
            "OR s.code LIKE '%_cl' OR s.code LIKE '%_bo' OR s.code = 'elektra_gt' "
            "GROUP BY s.code ORDER BY s.code"):
            print(f"    {r[0]:<18} product={r[1]:>4}  price={r[2]:>4}")
        con.close()

    print(f"\n{'='*60}")
    print(f"完成: {len(VTEX_SITES)} 站, {'DRY RUN' if dry_run else '已入库'}")


if __name__ == "__main__":
    main()
