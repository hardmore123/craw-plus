import sqlite3, sys, os, re, json, time
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("data/overseas.db")
from overseas.fetchers import BrowserFetcher

def extract_price(dom_html):
    for m in re.finditer(r'"price"\s*:\s*"?([0-9]+[.,]?[0-9]*)"?', dom_html):
        val = m.group(1).replace(",", ".")
        try:
            p = float(val)
            if 10 < p < 100000: return p
        except: pass
    return None

site_id = con.execute("SELECT id FROM site WHERE code='euronics_ee'").fetchone()[0]
products = con.execute("""SELECT p.id, p.url, p.sku FROM product p
    WHERE p.site_id=? AND p.url IS NOT NULL AND p.url!=''
    AND p.id NOT IN (SELECT product_id FROM price_snapshot)
    LIMIT 40""", (site_id,)).fetchall()
print(f"euronics_ee: {len(products)} 个缺价产品")

fetcher = BrowserFetcher()
success = 0; fail = 0
for i, (pid, url, sku) in enumerate(products):
    if i > 0 and i % 5 == 0:
        try: fetcher.close()
        except: pass
        fetcher = BrowserFetcher()
        time.sleep(1)
    try:
        with fetcher.page(url, human_like=True, nav_timeout_ms=15000,
                          wait_until="domcontentloaded", settle_ms=1500,
                          scroll_passes=1, scroll_wait_ms=500) as (res, dom):
            if res.status != 200 or not dom:
                fail += 1; continue
            dom_html = dom.html() if callable(dom.html) else dom.html
            if not dom_html:
                fail += 1; continue
            price = extract_price(dom_html)
            if price:
                con.execute("INSERT OR REPLACE INTO price_snapshot (product_id, price, currency, captured_at) VALUES (?,?,?,datetime('now'))",
                    (pid, price, "EUR"))
                success += 1
            else:
                fail += 1
    except:
        fail += 1
    time.sleep(1)
    if (i+1) % 5 == 0:
        con.commit()
        print(f"  {i+1}/{len(products)} 成功={success} 失败={fail}", flush=True)

con.commit()
fetcher.close()
total = con.execute("SELECT COUNT(*) FROM price_snapshot WHERE product_id IN (SELECT id FROM product WHERE site_id=?)", (site_id,)).fetchone()[0]
print(f"\neuronics_ee 完成: +{success} 新价格, 总={total}")
con.close()