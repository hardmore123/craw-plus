#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SPEC 品牌官网 Playwright 抓取 → SQLite 入库（lg_us / sony_ca）。

LG/SONY 官网用 Playwright 过 403 WAF，从 lineup 页提取产品列表。
"""
import sys, os, re, sqlite3, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from overseas.fetchers import BrowserFetcher

DB_PATH = "data/overseas.db"

SITES = [
    {
        "code": "lg_us",
        "url": "https://www.lg.com/us/tvs/",
        "name": "LG US",
        "currency": "USD",
        "card_sel": ".product-card-wrapper.mh-product-card",
        "title_sel": ".product-card-title",
        "link_pattern": r'href="(/us/tvs/lg-[a-z0-9\-]+)"',
        "price_pattern": r'"price"\s*:\s*"?([0-9.]+)',
    },
    {
        "code": "sony_ca",
        "url": "https://www.sony.ca/electronics/tv",
        "name": "Sony CA",
        "currency": "CAD",
        "card_sel": None,  # 用正则提取
        "title_sel": None,
        "link_pattern": r'href="(/electronics/[^"]*tv[^"]*)"[^>]*>([^<]+)',
        "price_pattern": None,
    },
]


def model_from_title(t):
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", (t or "").upper())
    return m[-1] if m else ""

def size_from_title(t):
    m = re.findall(r"\b(\d{2})\s*[\" pulgadas inch]+\b", (t or "").lower())
    return m[0] if m else ""


def ensure_site(con, code, name, base_url):
    row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
    if row:
        return row[0]
    cur = con.execute(
        "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
        (code, name, base_url, "L2", datetime.now(timezone.utc).isoformat()))
    return cur.lastrowid


def write_to_db(con, code, name, base_url, currency, items):
    site_id = ensure_site(con, code, name, base_url)
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
    return new_p, new_s


# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_spec_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

con = sqlite3.connect(DB_PATH)

for site in SITES:
    code = site["code"]
    print(f"=== {code} ===", flush=True)
    bf = BrowserFetcher(site_code=code, headless=True)
    items = []
    try:
        with bf.page(site["url"], wait_selector="body", nav_timeout_ms=25000,
                     settle_ms=4000, scroll_passes=3) as (res, dom):
            print(f"  status={res.status} title={res.title[:40]}", flush=True)
            if not dom:
                continue
            html = dom.html()
            # 提取产品链接
            if site["link_pattern"]:
                matches = re.findall(site["link_pattern"], html, re.I)
                # 去重保持顺序
                seen = set()
                products = []
                for m in matches:
                    if isinstance(m, tuple):
                        path, title = m[0], m[1].strip()
                    else:
                        path, title = m, ""
                    if path in seen:
                        continue
                    seen.add(path)
                    if not title:
                        # 从 URL slug 推导标题
                        slug = path.rstrip("/").split("/")[-1]
                        title = slug.replace("-", " ").title()
                    full_url = path if path.startswith("http") else f"https://{site['url'].split('/')[2]}{path}"
                    sku = re.sub(r"[^a-zA-Z0-9]", "", path.rstrip("/").split("/")[-1])[:50]
                    products.append({"url": full_url, "title": title, "sku": sku})
                # 提取价格
                prices = []
                if site["price_pattern"]:
                    prices = re.findall(site["price_pattern"], html)
                # 配对
                for i, p in enumerate(products):
                    price = None
                    if i < len(prices):
                        try: price = float(prices[i])
                        except: pass
                    p["price"] = price
                    p["brand"] = code.split("_")[0].upper()
                    p["model"] = model_from_title(p["title"])
                    p["size"] = size_from_title(p["title"])
                items = products
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {str(e)[:60]}", flush=True)
    finally:
        bf.close()

    print(f"  提取: {len(items)} 产品, 有价: {sum(1 for i in items if i.get('price'))}", flush=True)
    for it in items[:5]:
        print(f"    {it['title'][:40]:<40}  {it.get('price','?'):>8}  {it['url'][:45]}", flush=True)

    if items:
        new_p, new_s = write_to_db(con, code, site["name"],
                                   site["url"], site["currency"], items)
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
