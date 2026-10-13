#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Samsung UK SPEC 品牌官网 → SQLite 入库。

Samsung UK all-tvs 页有 JSON-LD ItemList（48 产品），纯 HTTP 可达。
产品名含型号（S95H, QN80H 等），URL 含产品路径。
价格需后续从 PDP 页提取（ItemList 不含价格）。
"""
import sys, os, re, json, sqlite3, urllib.request, ssl, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = "data/overseas.db"
URL = "https://www.samsung.com/uk/tvs/all-tvs/"
CODE = "samsung_uk"
NAME = "Samsung UK"
BASE_URL = "https://www.samsung.com"
CURRENCY = "GBP"

def html_unescape(s):
    return s.replace("&#39;","'").replace("&amp;","&").replace("&quot;",'"').replace("&lt;","<").replace("&gt;",">")

def extract_model(name):
    # Samsung 型号: S95H, QN80H, R95H, Q7F5, LS03HW 等
    m = re.findall(r'\b([A-Z]{1,3}\d{2,4}[A-Z0-9]{0,4})\b', name)
    return m[-1] if m else ""

def extract_size(name):
    m = re.findall(r'(\d{2})\s*[\"\'\u2019]', name)
    return m[0] if m else ""

# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_sam_uk_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

# 抓取
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
PROXY = os.environ.get("OVERSEAS_PROXY","")
ph = urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})
op = urllib.request.build_opener(ph, urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"

print(f"=== {CODE} ===", flush=True)
req = urllib.request.Request(URL, headers={"User-Agent":UA,"Accept-Language":"en-GB,en"})
html = op.open(req, timeout=20).read().decode("utf-8","replace")
print(f"  HTTP {len(html)} bytes", flush=True)

# 提取 ItemList
items = []
jsonld_blocks = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
for blk in jsonld_blocks:
    try:
        d = json.loads(blk.strip())
        if d.get("@type") == "ItemList":
            elems = d.get("itemListElement", [])
            print(f"  ItemList: {len(elems)} products", flush=True)
            for e in elems:
                item = e.get("item", e)
                name = html_unescape(item.get("name",""))
                url2 = item.get("url","")
                if not name or not url2:
                    continue
                # 跳过非 TV（projector, movable screen 等）
                low = name.lower()
                if any(k in low for k in ["freestyle","movingstyle","projector","movable"]):
                    continue
                items.append({
                    "sku": extract_model(name) or re.sub(r"[^a-zA-Z0-9]","",name)[:30],
                    "url": url2 if url2.startswith("http") else BASE_URL + url2,
                    "title": name,
                    "brand": "Samsung",
                    "model": extract_model(name),
                    "size": extract_size(name),
                    "price": None,
                    "list_price": None,
                    "available": True,
                })
            break
    except:
        pass

print(f"  提取: {len(items)} TV 产品", flush=True)
for it in items[:10]:
    print(f"    {it['model']:<12} {it['size']:>3}\"  {it['title'][:45]}", flush=True)

# 入库
if items:
    con = sqlite3.connect(DB_PATH)
    row = con.execute("SELECT id FROM site WHERE code = ?", (CODE,)).fetchone()
    if row:
        site_id = row[0]
    else:
        cur = con.execute(
            "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
            (CODE, NAME, BASE_URL, "L1", datetime.now(timezone.utc).isoformat()))
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
    print(f"\n  入库: 新品{new_p} (价格待 PDP)", flush=True)
    print(f"  integrity={ok}  site={total_s}  product={total_p}", flush=True)
    con.close()
