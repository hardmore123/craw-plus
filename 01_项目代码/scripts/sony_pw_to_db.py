#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Sony CA/US 官网 Playwright 抓取 → SQLite 入库。

Sony 用 SAP Commerce Cloud + JSON-LD ItemList，
产品链接格式: /tv-video/televisions/all-tvs/p/<model>
"""
import sys, os, re, json, sqlite3, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from overseas.fetchers import BrowserFetcher

DB_PATH = "data/overseas.db"

SITES = [
    ("sony_ca", "https://www.sony.ca/en/c/all-tvs", "Sony CA", "CAD", "www.sony.ca"),
    ("sony_us", "https://www.sony.com/electronics/televisions", "Sony US", "USD", "www.sony.com"),
]


def model_from_title(t):
    m = re.findall(r"\b([A-Z]{2}\d[A-Z0-9]+)\b", (t or "").upper())
    return m[0] if m else ""

def size_from_title(t):
    m = re.findall(r"\b(\d{2})\s*[\" inch]+\b", (t or "").lower())
    return m[0] if m else ""

def extract_products(html, host):
    """从 JSON-LD ItemList 提取产品。"""
    items = []
    for blk in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        if '"ItemList"' not in blk:
            continue
        try:
            d = json.loads(blk.strip())
        except:
            continue
        for el in d.get("itemListElement", []):
            p = el.get("item", el)
            name = p.get("name", "").strip()
            url = p.get("url", "")
            if not name or not url:
                continue
            # 清理 HTML 标签
            name = re.sub(r'<[^>]+>', '', name).strip()
            if not url.startswith("http"):
                url = f"https://{host}{url}"
            price = None
            offers = p.get("offers", {})
            if isinstance(offers, dict):
                pval = offers.get("price") or offers.get("lowPrice")
                if pval:
                    try: price = float(pval)
                    except: pass
            sku = url.rstrip("/").split("/")[-1]
            items.append({
                "sku": re.sub(r"[^a-zA-Z0-9]", "", sku)[:50] or sku,
                "url": url, "title": name,
                "brand": "SONY",
                "model": model_from_title(name),
                "size": size_from_title(name),
                "price": price, "list_price": None, "available": True,
            })
    return items


def ensure_site(con, code, name, base_url):
    row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
    if row:
        return row[0]
    cur = con.execute(
        "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
        (code, name, base_url, "L2", datetime.now(timezone.utc).isoformat()))
    return cur.lastrowid


# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_sony_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

con = sqlite3.connect(DB_PATH)

for code, url, name, currency, host in SITES:
    print(f"=== {code} ===", flush=True)
    bf = BrowserFetcher(site_code=code, headless=True)
    items = []
    try:
        with bf.page(url, wait_selector="body", nav_timeout_ms=45000,
                     settle_ms=6000, scroll_passes=4) as (res, dom):
            print(f"  status={res.status} title={res.title[:40]}", flush=True)
            if dom and res.status == 200:
                html = dom.html()
                items = extract_products(html, host)
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {str(e)[:60]}", flush=True)
    finally:
        bf.close()

    print(f"  提取: {len(items)} 产品", flush=True)
    for it in items[:5]:
        print(f"    {it['title'][:45]:<45}  {it.get('price','?')}  {it['model']}", flush=True)

    if items:
        site_id = ensure_site(con, code, name, f"https://{host}")
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
                    (pid, it["price"], None, currency, 1,
                     f"SPEC PW: {it['title'][:60]}", now))
                new_s += 1
        con.commit()
        print(f"  入库: 新品{new_p} 价{new_s}", flush=True)
    time.sleep(1)

ok = con.execute("PRAGMA integrity_check").fetchone()[0]
total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
total_s = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
total_sites = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
print(f"\n=== 最终 ===")
print(f"integrity={ok}  site={total_sites}  product={total_p}  price_snapshot={total_s}")
con.close()
