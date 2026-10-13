#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BestBuy US sitemap TV 产品入库（bsin sitemap 方案）。"""
import sys, os, re, sqlite3
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = "data/overseas.db"
SITEMAP_CACHE = "data/bestbuy_us_sitemap_bsin0.xml"
CODE = "bestbuy_us"
NAME = "Best Buy US"
BASE_URL = "https://www.bestbuy.com"
CURRENCY = "USD"

def model_from_slug(slug):
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", slug.upper())
    return m[-1] if m else ""

def size_from_slug(slug):
    m = re.findall(r"\b(\d{2})\s*[\" inch class]+\b", slug.lower())
    return m[0] if m else ""

xml = open(SITEMAP_CACHE, encoding="utf-8").read()
urls = re.findall(r"<loc>([^<]+)</loc>", xml)

# 筛选真实 TV
BRANDS = ["hisense", "lg-", "samsung", "tcl", "sony", "sharp", "panasonic",
          "philips", "toshiba", "jvc", "hyundai", "haier"]
tv_urls = []
for u in urls:
    low = u.lower()
    if not any(b in low for b in BRANDS):
        continue
    if "tv" not in low and "televis" not in low:
        continue
    if any(k in low for k in ["mount", "stand", "cable", "remote", "soundbar",
           "speaker", "hdmi", "antenna", "cover", "recast", "shield",
           "open-box", "refurbished", "case", "zerodamage", "carryin"]):
        continue
    tv_urls.append(u)

print(f"真实 TV URL: {len(tv_urls)}", flush=True)

items = []
for u in tv_urls:
    # URL 格式: https://www.bestbuy.com/product/<slug>/<sku> 或 /site/<slug>/<sku>.p?skuId=<id>
    path = u.split("?")[0].rstrip("/")
    parts = path.split("/")
    slug = parts[-2] if len(parts) >= 2 else parts[-1]
    sku = parts[-1]
    brand = ""
    for b in BRANDS:
        if b.rstrip("-") in slug.lower():
            brand = b.rstrip("-").title()
            break
    items.append({
        "sku": re.sub(r"[^a-zA-Z0-9]", "", sku)[:50] or slug[:20],
        "url": u,
        "title": slug.replace("-", " ").title(),
        "brand": brand or "Unknown",
        "model": model_from_slug(slug),
        "size": size_from_slug(slug),
        "price": None,
        "list_price": None,
        "available": True,
    })

# 去重
seen = set()
unique = []
for it in items:
    if it["sku"] in seen:
        continue
    seen.add(it["sku"])
    unique.append(it)

print(f"产品: {len(unique)}", flush=True)
for it in unique[:10]:
    print(f"  {it['brand']:<10} {it['size']:>3}\"  {it['model']:<15}  SKU={it['sku'][:15]}", flush=True)

# 入库
con = sqlite3.connect(DB_PATH)
row = con.execute("SELECT id FROM site WHERE code = ?", (CODE,)).fetchone()
if row:
    site_id = row[0]
else:
    cur = con.execute(
        "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
        (CODE, NAME, BASE_URL, "L2", datetime.now(timezone.utc).isoformat()))
    site_id = cur.lastrowid

now = datetime.now(timezone.utc).isoformat()
new_p = 0
for it in unique:
    if not it["sku"]:
        continue
    row = con.execute("SELECT id FROM product WHERE site_id=? AND sku=?",
                      (site_id, it["sku"])).fetchone()
    if row:
        continue
    con.execute(
        "INSERT INTO product (site_id, sku, url, title, brand, model, "
        "category, first_seen, last_seen, size) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (site_id, it["sku"], it["url"], it["title"], it["brand"],
         it["model"], "TV", now, now, it["size"]))
    new_p += 1
con.commit()
ok = con.execute("PRAGMA integrity_check").fetchone()[0]
total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
total_s = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
print(f"\n入库: 新品{new_p} (价格待 Playwright 抓 PDP)", flush=True)
print(f"integrity={ok}  site={total_s}  product={total_p}", flush=True)
con.close()
