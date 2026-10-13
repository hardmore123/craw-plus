#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Costco CA/US 搜索页 Playwright 抓取 → SQLite 入库。

Costco 用 MUI (Material UI) 框架，产品在 .MuiGrid-root 里，
文本含 产品名 + 价格（$xxx.xx）。需长滚动 + scroll_until_stable 触发加载。
"""
import sys, os, re, sqlite3, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from overseas.fetchers import BrowserFetcher

DB_PATH = "data/overseas.db"

SITES = [
    ("costco_ca", "https://www.costco.ca/CatalogSearch?dept=All&keyword=televisor+LG",
     "Costco Canada", "CAD", "www.costco.ca"),
    ("costco_us", "https://www.costco.com/CatalogSearch?dept=All&keyword=televisor+LG",
     "Costco US", "USD", "www.costco.com"),
]


def model_from_title(t):
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", (t or "").upper())
    return m[-1] if m else ""

def size_from_title(t):
    m = re.findall(r"\b(\d{2})\s*[\" inch class]+\b", (t or "").lower())
    return m[0] if m else ""

def extract_costco_products(dom):
    """从 MuiGrid-root 提取产品。"""
    items = []
    grids = dom.sub(".MuiGrid-root")
    for g in grids:
        txt = g.self_text().strip()
        if not txt or len(txt) < 20:
            continue
        # 文本格式: "LG 75" Class - QNED7S Series - 4K UHD QNED Mini LED TV\nOnline Only\n$894.99\nAfter..."
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        if not lines:
            continue
        title = lines[0]
        # 必须含 TV 关键词
        if not any(k in title.lower() for k in ["tv", "televis", "oled", "qned", "4k", "uhd"]):
            continue
        # 排除非产品
        if any(k in title.lower() for k in ["mount", "stand", "cable", "remote", "soundbar", "speaker"]):
            continue
        # 找价格
        price = None
        for l in lines[1:]:
            pm = re.match(r"\$\s*([0-9,]+\.?[0-9]*)", l)
            if pm:
                try: price = float(pm.group(1).replace(",", ""))
                except: pass
                break
        if not title:
            continue
        items.append({
            "sku": re.sub(r"[^a-zA-Z0-9]", "", title)[:50] or title[:20],
            "url": "",  # Costco 不易从 grid 提取 URL
            "title": title,
            "brand": title.split()[0] if title else "",
            "model": model_from_title(title),
            "size": size_from_title(title),
            "price": price,
            "list_price": None,
            "available": True,
        })
    # 去重（按 title）
    seen = set()
    unique = []
    for it in items:
        if it["title"] in seen:
            continue
        seen.add(it["title"])
        unique.append(it)
    return unique


# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_costco_{stamp}.bak"
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
        with bf.page(url, wait_selector="body", nav_timeout_ms=30000,
                     settle_ms=8000, scroll_passes=6, scroll_wait_ms=2000,
                     scroll_until_stable=True) as (res, dom):
            print(f"  status={res.status}", flush=True)
            if dom and res.status == 200:
                items = extract_costco_products(dom)
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {str(e)[:60]}", flush=True)
    finally:
        bf.close()

    print(f"  提取: {len(items)} 产品, 有价: {sum(1 for i in items if i['price'])}", flush=True)
    for it in items[:5]:
        print(f"    {it['title'][:45]:<45}  {str(it['price'] or '?'):>10}", flush=True)

    if items:
        row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
        if row:
            site_id = row[0]
        else:
            cur = con.execute(
                "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
                (code, name, f"https://{host}", "L2",
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
                    (pid, it["price"], None, currency, 1,
                     f"Costco PW: {it['title'][:60]}", now))
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
