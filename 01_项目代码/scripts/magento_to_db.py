#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Magento 站 Playwright 搜索页抓取 → SQLite 入库。

对有契约的 Magento 站，用 Playwright 渲染搜索页，
提取产品卡片 + 价格 + 商品名，写入 overseas.db。

用法:
    python scripts/magento_to_db.py [--sites code1,code2] [--dry-run]

选择器来源: hiraoka_pe 契约（已验证）:
  搜索容器: li.product-item a.product.photo.product-item-photo
  商品名:   .product-item-link
  价格:     [data-price-amount] 属性
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

from overseas.fetchers import BrowserFetcher
from overseas.retail_spec import load_retail_spec

DB_PATH = "data/overseas.db"

# Magento 站配置（有契约 + 已连通）
# 注: coral_ec 搜索路径正确但选择器结构不同(.item 而非 li.product-item)，需单独适配
# 注: dismac_bo 是非标准 Magento (product-item-pdc class)，搜索相关性差
MAGENTO_SITES = {
    "hiraoka_pe":     ("hiraoka.com.pe",        "Hiraoka",        "PEN", "Peru",     "/catalogsearch/result/?q={q}"),
    "laganga_ec":     ("laganga.com",           "L-Ganga",        "USD", "Ecuador",  "/catalogsearch/result/?q={q}"),
    "panafoto_pa":    ("panafoto.com",          "Panafoto",       "USD", "Panama",   "/catalogsearch/result/?q={q}"),
    "raenco_pa":      ("www.raenco.com",        "Raenco",         "USD", "Panama",   "/catalogsearch/result/?q={q}"),
    "efe_pe":         ("www.efe.com.pe",        "Efe",            "PEN", "Peru",     "/catalogsearch/result/?q={q}"),
}

SEARCH_KW = "televisor LG"
# 按站定制搜索词（有些站 "televisor LG" 返回空，但 "televisor" 有结果）
SITE_SEARCH_KW = {
    "panafoto_pa": "televisor",
    "efe_pe": "televisor",
}
CONTAINER = "li.product-item a.product.photo.product-item-photo"
TITLE_SEL = ".product-item-link"
PRICE_SEL = "[data-price-amount]"


def model_from_title(t: str) -> str:
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", (t or "").upper())
    return m[-1] if m else ""


def size_from_title(t: str) -> str:
    m = re.findall(r"\b(\d{2})\s*[\" pulgadas inch]+\b", (t or "").lower())
    return m[0] if m else ""


def crawl_magento_site(bf: BrowserFetcher, host: str, search_path: str,
                       currency: str, max_products: int = 50,
                       settle_ms: int = 2000, scroll_passes: int = 2,
                       site_code: str = "") -> list[dict]:
    """用 Playwright 渲染搜索页，提取产品卡片 + 价格。"""
    kw = SITE_SEARCH_KW.get(site_code, SEARCH_KW)
    url = f"https://{host}{search_path}".replace("{q}", kw.replace(" ", "+"))
    items = []
    with bf.page(url, wait_selector="body", nav_timeout_ms=30000,
                 settle_ms=settle_ms, scroll_passes=scroll_passes) as (res, dom):
        if not dom:
            return items
        # 每个产品卡片是一个 li.product-item，在卡片内找标题和价格
        product_items = dom.sub("li.product-item")
        for pi in product_items:
            # 卡片内的商品链接
            link_els = pi.sub("a.product.photo.product-item-photo")
            if not link_els:
                continue
            href = link_els[0].self_attr("href") or ""
            if not href:
                continue
            # 卡片内的标题（多种选择器兜底）
            title = ""
            for title_sel in [".product-item-link", ".product-item-name a",
                              ".product.name a", ".product-name a", "h2 a", "a.product-item-link"]:
                title_els = pi.sub(title_sel)
                for te in title_els:
                    t = te.self_text().strip()
                    if len(t) > 5:
                        title = t
                        break
                if title:
                    break
            # 如果标题为空，用 URL slug 推导
            if not title and href:
                slug = href.rstrip("/").split("/")[-1]
                title = slug.replace("-", " ").title()
            if not title:
                continue
            # 卡片内的价格
            price = None
            price_els = pi.sub("[data-price-amount]")
            if price_els:
                pval = price_els[0].self_attr("data-price-amount")
                if pval:
                    try:
                        price = float(pval)
                    except Exception:
                        pass
            if not href.startswith("http"):
                href = f"https://{host}{href}"
            # 用 URL slug 作为 SKU
            slug = href.rstrip("/").split("/")[-1]
            sku = re.sub(r"[^a-zA-Z0-9]", "", slug)[:50] or slug
            items.append({
                "sku": sku,
                "url": href,
                "title": title,
                "brand": title.split()[0] if title else "",
                "model": model_from_title(title),
                "size": size_from_title(title),
                "price": price,
                "list_price": None,
                "available": True,
            })
            if len(items) >= max_products:
                break
    return items


def ensure_site(con: sqlite3.Connection, code: str, name: str, base_url: str) -> int:
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
    stats = {"site": site_code, "new_products": 0, "exist_products": 0,
             "new_prices": 0, "skip_no_price": 0}
    site_id = ensure_site(con, site_code, site_name, base_url)
    now = datetime.now(timezone.utc).isoformat()
    for it in items:
        if not it["sku"]:
            continue
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
        if it["price"] is not None:
            con.execute(
                "INSERT INTO price_snapshot (product_id, price, list_price, "
                "currency, in_stock, raw_text, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pid, it["price"], it["list_price"], currency,
                 1 if it["available"] else 0,
                 f"Magento PW: {it['title'][:60]}", now))
            stats["new_prices"] += 1
        else:
            stats["skip_no_price"] += 1
    return stats


def main():
    dry_run = "--dry-run" in sys.argv
    site_filter = ""
    if "--sites" in sys.argv:
        idx = sys.argv.index("--sites")
        site_filter = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""

    if not dry_run:
        import shutil
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"data/db/backup/overseas_before_magento_{stamp}.bak"
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
    # 共用一个浏览器实例跑所有站（减少启动开销）
    bf = BrowserFetcher(site_code="", headless=True)
    for code, (host, name, cur, country, spath) in MAGENTO_SITES.items():
        if site_filter and code not in site_filter.split(","):
            continue
        print(f"=== {code} ({host}) ===", flush=True)
        t0 = time.time()
        try:
            # 每站用独立 page 调用（共享浏览器上下文）
            bf.site_code = code
            # panafoto_pa 需要更长等待时间
            settle = 5000 if code == "panafoto_pa" else 2000
            scrolls = 3 if code == "panafoto_pa" else 2
            items = crawl_magento_site(bf, host, spath, cur, max_products=30,
                                       settle_ms=settle, scroll_passes=scrolls,
                                       site_code=code)
            ms = int((time.time() - t0) * 1000)
            has_price = sum(1 for i in items if i["price"] is not None)
            print(f"  TV: {len(items)}  有价: {has_price}  ({ms}ms)", flush=True)
            if not dry_run and con and items:
                stats = write_to_db(con, code, name, f"https://{host}", cur, items)
                con.commit()
                print(f"  入库: 新品{stats['new_products']} 已有{stats['exist_products']} "
                      f"价{stats['new_prices']}", flush=True)
            elif dry_run:
                for it in items[:3]:
                    print(f"    {it['brand']:<12} {it['price']} {cur}  {it['title'][:45]}",
                          flush=True)
        except Exception as e:
            print(f"  ERR: {type(e).__name__}: {str(e)[:80]}", flush=True)
            all_stats.append({"site": code, "error": str(e)[:80]})
            continue
        time.sleep(0.5)
    bf.close()

    if not dry_run and con:
        ok = con.execute("PRAGMA integrity_check").fetchone()[0]
        total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        total_s = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
        total_sites = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
        print(f"\n=== 入库后 ===")
        print(f"  integrity: {ok}")
        print(f"  site: {total_sites}  product: {total_p}  price_snapshot: {total_s}")
        con.close()

    print(f"\n完成: {len(MAGENTO_SITES)} 站, {'DRY RUN' if dry_run else '已入库'}")


if __name__ == "__main__":
    main()
