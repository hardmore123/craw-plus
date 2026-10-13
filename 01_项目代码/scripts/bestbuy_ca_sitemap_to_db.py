#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""BestBuy CA sitemap TV 产品入库。

从 sitemap1 提取真实 TV 产品 URL，用 sitemap 确定性发现，
入库 product + price_snapshot（价格需后续 Playwright 抓 PDP）。
"""
import sys, os, re, sqlite3
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = "data/overseas.db"
SITEMAP_CACHE = "data/bestbuy_sitemap1.xml"
CODE = "bestbuy_ca"
NAME = "Best Buy Canada"
BASE_URL = "https://www.bestbuy.ca"
CURRENCY = "CAD"

def model_from_slug(slug):
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", slug.upper())
    return m[-1] if m else ""

def size_from_slug(slug):
    m = re.findall(r"\b(\d{2})\s*[\" inch class]+\b", slug.lower())
    return m[0] if m else ""

# 读取 sitemap 缓存
xml = open(SITEMAP_CACHE, encoding="utf-8").read()
urls = re.findall(r"<loc>([^<]+/en-ca/product/[^<]+)</loc>", xml)

# 精确筛选真实 TV
BRANDS = ["hisense", "lg-", "samsung", "tcl", "sony", "sharp", "panasonic",
          "philips", "toshiba", "jvc", "hyundai", "haier"]
tv_urls = []
for u in urls:
    low = u.lower()
    if not any(b in low for b in BRANDS):
        continue
    if "tv" not in low:
        continue
    if any(k in low for k in ["monitor", "mount", "stand", "cable", "remote",
           "bracket", "antenna", "soundbar", "speaker", "hdmi", "adapter",
           "charger", "light", "open-box"]):
        continue
    tv_urls.append(u)

print(f"真实 TV URL: {len(tv_urls)}", flush=True)

# 提取产品信息
items = []
for u in tv_urls:
    parts = u.rstrip("/").split("/")
    slug = parts[-2]
    sku = parts[-1]
    # 品牌从 slug 提取
    brand = ""
    for b in BRANDS:
        if b.rstrip("-") in slug.lower():
            brand = b.rstrip("-").title()
            break
    items.append({
        "sku": sku,
        "url": u,
        "title": slug.replace("-", " ").title(),
        "brand": brand or "Unknown",
        "model": model_from_slug(slug),
        "size": size_from_slug(slug),
        "price": None,  # 价格需 Playwright 抓 PDP
        "list_price": None,
        "available": True,
    })

print(f"产品: {len(items)}", flush=True)
for it in items[:9]:
    print(f"  {it['brand']:<10} {it['size']:>3}\"  {it['model']:<15}  SKU={it['sku']}", flush=True)

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
con.commit()
ok = con.execute("PRAGMA integrity_check").fetchone()[0]
total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
total_s = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
print(f"\n入库: 新品{new_p} (价格待 Playwright 抓 PDP)", flush=True)
print(f"integrity={ok}  site={total_s}  product={total_p}", flush=True)
con.close()
