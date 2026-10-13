#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""欧洲零售站 JSON-LD ItemList → SQLite 入库（通用）。

支持 mediamarkt_es 等有 JSON-LD ItemList 的站点。
产品名含品牌+型号+尺寸，价格在 offers.price。
"""
import sys, os, re, json, sqlite3, urllib.request, ssl, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

DB_PATH = "data/overseas.db"

SITES = [
    ("mediamarkt_es", "https://www.mediamarkt.es/es/category/televisi%C3%B3n-398.html",
     "MediaMarkt Spain", "EUR", "https://www.mediamarkt.es", "es-ES"),
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
PROXY = os.environ.get("OVERSEAS_PROXY","")
ph = urllib.request.ProxyHandler({"http":PROXY,"https":PROXY})
op = urllib.request.build_opener(ph, urllib.request.HTTPSHandler(context=CTX))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"

def html_unescape(s):
    return s.replace("&#39;","'").replace("&amp;","&").replace("&quot;",'"')

def extract_brand(name):
    name_low = name.lower()
    for b in ["samsung","lg","hisense","tcl","sony","philips","xiaomi","sharp","panasonic","toshiba","jvc","chiq","hyundai","haier","ok","grunding","telefunken"]:
        if b in name_low:
            return b.title()
    return ""

def extract_model(name):
    # 从产品名提取型号（如 TU43U8075HU, 43NU850B6LA, 55E7S）
    m = re.findall(r'\b(\d{2}[A-Z][A-Z0-9]{3,15})\b', name)
    return m[-1] if m else ""

def extract_size(name):
    m = re.findall(r'(\d{2})\s*[\"\'\u2019]', name)
    return m[0] if m else ""

# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_eu_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

con = sqlite3.connect(DB_PATH)
for code, url, name, currency, base, lang in SITES:
    print(f"=== {code} ===", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent":UA,"Accept-Language":lang})
        html = op.open(req, timeout=20).read(400000).decode("utf-8","replace")
        print(f"  HTTP {len(html)} bytes", flush=True)
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {str(e)[:50]}", flush=True)
        continue

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
                    nm = html_unescape(item.get("name",""))
                    if not nm:
                        continue
                    u2 = item.get("url","")
                    if u2 and not u2.startswith("http"):
                        u2 = base + u2
                    offers = item.get("offers",{})
                    price = None
                    if isinstance(offers, dict):
                        p = offers.get("price")
                        if p:
                            try: price = float(p)
                            except: pass
                    sku = item.get("sku","") or extract_model(nm) or re.sub(r"[^a-zA-Z0-9]","",nm)[:30]
                    items.append({
                        "sku": str(sku),
                        "url": u2,
                        "title": nm,
                        "brand": extract_brand(nm),
                        "model": extract_model(nm),
                        "size": extract_size(nm),
                        "price": price,
                        "list_price": None,
                        "available": True,
                    })
                break
        except:
            pass

    print(f"  提取: {len(items)} 产品, 有价: {sum(1 for i in items if i['price'])}", flush=True)
    for it in items[:8]:
        print(f"    {it['brand']:<10} {it['size']:>3}\"  {it['model']:<18}  €{it['price'] or '?':>7}  {it['title'][:35]}", flush=True)

    if items:
        row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
        if row:
            site_id = row[0]
        else:
            cur = con.execute(
                "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
                (code, name, base, "L1", datetime.now(timezone.utc).isoformat()))
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
                    (pid, it["price"], None, currency, 1,
                     f"EU: {it['title'][:60]}", now))
                new_s += 1
        con.commit()
        print(f"  入库: 新品{new_p} 价{new_s}", flush=True)
    time.sleep(0.5)

ok = con.execute("PRAGMA integrity_check").fetchone()[0]
total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
total_s = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
total_ps = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
print(f"\nintegrity={ok}  site={total_s}  product={total_p}  price_snapshot={total_ps}")
con.close()
