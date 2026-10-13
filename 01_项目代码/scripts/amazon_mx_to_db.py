#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Amazon MX 搜索页 Playwright 抓取 → SQLite 入库。

Amazon MX 搜索结果在 data-component-type="s-search-result" 的 div 里，
ASIN 在 data-asin 属性，标题在 h2 内，价格在 .a-price .a-offscreen。
"""
import sys, os, re, sqlite3, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from overseas.fetchers import BrowserFetcher

DB_PATH = "data/overseas.db"
URL = "https://www.amazon.com.mx/s?k=televisor+LG"
CODE = "amazon_mx"
NAME = "Amazon Mexico"
CURRENCY = "MXN"


def model_from_title(t):
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", (t or "").upper())
    return m[-1] if m else ""

def size_from_title(t):
    m = re.findall(r"\b(\d{2})\s*[\" pulgadas inch]+\b", (t or "").lower())
    return m[0] if m else ""

def extract_amazon_products(html):
    """从 Amazon 搜索页 HTML 提取产品。"""
    items = []
    # 找所有 data-asin 的 div
    asin_blocks = re.findall(
        r'data-asin="([A-Z0-9]{10})"(.*?)(?=data-asin="[A-Z0-9]{10}"|data-component-type="s-pagination"|$)',
        html, re.S)
    for asin, blk in asin_blocks:
        if not asin or asin == "0000000000":
            continue
        # 标题: h2 > span
        title = ""
        tm = re.search(r'<h2[^>]*>.*?<span[^>]*>([^<]{10,100})</span>', blk, re.S)
        if tm:
            title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
        if not title or len(title) < 10:
            continue
        # 价格: .a-price .a-offscreen
        price = None
        pm = re.search(r'a-price[^>]*>.*?a-offscreen[^>]*>([^<]+)<', blk, re.S)
        if pm:
            pval = re.sub(r'[^\d.]', '', pm.group(1))
            if pval:
                try: price = float(pval)
                except: pass
        # URL
        href = ""
        um = re.search(r'href="(/[^"]*dp/' + asin + r'[^"]*)"', blk)
        if um:
            href = "https://www.amazon.com.mx" + um.group(1)
        items.append({
            "sku": asin,
            "url": href,
            "title": title,
            "brand": "LG" if "LG" in title.upper() else title.split()[0],
            "model": model_from_title(title),
            "size": size_from_title(title),
            "price": price,
            "list_price": None,
            "available": True,
        })
    return items


# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_amzmx_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

print(f"=== {CODE} ===", flush=True)
bf = BrowserFetcher(site_code=CODE, headless=True)
items = []
try:
    with bf.page(URL, wait_selector="body", nav_timeout_ms=20000,
                 settle_ms=3000, scroll_passes=3) as (res, dom):
        print(f"  status={res.status} blocked={res.blocked}", flush=True)
        if dom and res.status == 200 and not res.blocked:
            html = dom.html()
            items = extract_amazon_products(html)
except Exception as e:
    print(f"  ERR: {type(e).__name__}: {str(e)[:60]}", flush=True)
finally:
    bf.close()

print(f"  提取: {len(items)} 产品, 有价: {sum(1 for i in items if i['price'])}", flush=True)
for it in items[:8]:
    print(f"    {it['title'][:45]:<45}  {str(it['price'] or '?'):>10}  {it['sku']}", flush=True)

if items:
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT id FROM site WHERE code = ?", (CODE,)).fetchone()
    if row:
        site_id = row[0]
    else:
        cur = con.execute(
            "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
            (CODE, NAME, "https://www.amazon.com.mx", "L2",
             datetime.now(timezone.utc).isoformat()))
        site_id = cur.lastrowid
    now = datetime.now(timezone.utc).isoformat()
    new_p = new_s = 0
    for it in items:
        if not it["sku"]:
            continue
        row = con.execute("SELECT id FROM product WHERE site_id=? AND sku=?",
                          (site_id, it["sku"])).fetchone()
        if row:
            pid = row[0]
        else:
            cur = con.execute(
                "INSERT INTO product (site_id, sku, url, title, brand, model, "
                "category, first_seen, last_seen, size) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (site_id, it["sku"], it["url"], it["title"], it["brand"],
                 it["model"], "TV", now, now, it["size"]))
            pid = cur.lastrowid
            new_p += 1
        if it["price"] is not None:
            con.execute(
                "INSERT INTO price_snapshot (product_id, price, list_price, currency, "
                "in_stock, raw_text, captured_at) VALUES (?,?,?,?,?,?,?)",
                (pid, it["price"], None, CURRENCY, 1,
                 f"AMZ MX: {it['title'][:60]}", now))
            new_s += 1
    con.commit()
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
    total_s = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
    print(f"\n  入库: 新品{new_p} 价{new_s}", flush=True)
    print(f"  integrity={ok}  product={total_p}  price_snapshot={total_s}", flush=True)
    con.close()
