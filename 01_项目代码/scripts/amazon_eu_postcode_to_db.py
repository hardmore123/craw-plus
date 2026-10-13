#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Amazon 欧洲五站邮编输入 → 搜索 → 入库。

用 Playwright 原生 API 绕过 BrowserFetcher 限制：
1. 启动 BrowserFetcher 获取 BrowserContext
2. 用 bf._ctx.new_page() 创建原生 page
3. 点击 "Deliver to" → 输入邮编 → 点 Apply
4. 搜索 televisor LG → 提取产品
"""
import sys, os, re, sqlite3, time
from datetime import datetime, timezone
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.getcwd())
sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None
from overseas.fetchers import BrowserFetcher

DB_PATH = "data/overseas.db"

SITES = [
    ("amazon_uk", "https://www.amazon.co.uk", "LS118LZ", "£", "Amazon UK", "GBP", "en-GB"),
    ("amazon_de", "https://www.amazon.de", "96317", "€", "Amazon DE", "EUR", "de-DE"),
    ("amazon_fr", "https://www.amazon.fr", "75056", "€", "Amazon FR", "EUR", "fr-FR"),
    ("amazon_it", "https://www.amazon.it", "20080", "€", "Amazon IT", "EUR", "it-IT"),
    ("amazon_es", "https://www.amazon.es", "28058", "€", "Amazon ES", "EUR", "es-ES"),
]

def extract_amazon_products(html, currency_sym, base_url):
    """从 Amazon 搜索页 HTML 提取产品。"""
    items = []
    # 找 data-asin 的 div 块
    asin_blocks = re.findall(
        r'data-asin="([A-Z0-9]{10})"(.*?)(?=data-asin="[A-Z0-9]{10}"|data-component-type="s-pagination"|$)',
        html, re.S)
    for asin, blk in asin_blocks:
        if not asin or asin == "0000000000":
            continue
        # 标题: h2 > span
        title = ""
        tm = re.search(r'<h2[^>]*>.*?<span[^>]*>([^<]{10,120})</span>', blk, re.S)
        if tm:
            title = re.sub(r'<[^>]+>', '', tm.group(1)).strip()
        if not title or len(title) < 10:
            continue
        # 排除非产品
        low = title.lower()
        if any(k in low for k in ["star", "shortcut", "eligible", "sponsored", "results for"]):
            continue
        # 价格
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
            href = base_url + um.group(1)
        items.append({
            "sku": asin,
            "url": href,
            "title": title,
            "brand": "LG" if "LG" in title.upper() else title.split()[0],
            "model": "",
            "size": "",
            "price": price,
        })
    return items


# 备份
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = f"data/db/backup/overseas_before_amz_eu_{stamp}.bak"
os.makedirs("data/db/backup", exist_ok=True)
src = sqlite3.connect(DB_PATH)
dst = sqlite3.connect(bak)
with dst:
    src.backup(dst)
dst.close()
src.close()
print(f"备份: {bak}\n")

con = sqlite3.connect(DB_PATH)

for code, base_url, postcode, sym, name, currency, lang in SITES:
    print(f"=== {code} (邮编 {postcode}) ===", flush=True)
    bf = BrowserFetcher(site_code=code, headless=True)
    items = []
    try:
        # 启动 browser context
        bf._ensure()
        ctx = bf._ctx
        page = ctx.new_page()
        page.set_default_timeout(20000)

        # Step 1: 访问首页
        print(f"  Step1: 访问 {base_url}", flush=True)
        page.goto(base_url, wait_until="domcontentloaded")
        time.sleep(2)

        # Step 1.5: 关闭 cookie 弹窗（如有）
        try:
            page.click("#sp-cc-accept, #a-autoid-0-announce", timeout=3000)
            time.sleep(1)
        except:
            pass

        # Step 2: 点击 "Deliver to" / location popover
        print(f"  Step2: 点击 location popover", flush=True)
        try:
            page.click("#nav-global-location-popover-link", timeout=5000)
            time.sleep(2)
        except:
            print(f"  -> popover 点击失败", flush=True)

        # Step 3: 输入邮编（ID=GLUXZipUpdateInput）
        print(f"  Step3: 输入邮编 {postcode}", flush=True)
        try:
            postal_input = page.wait_for_selector("#GLUXZipUpdateInput", timeout=5000)
            if postal_input:
                postal_input.fill(postcode)
                time.sleep(1)
                # 点 Apply 按钮（ID=GLUXZipUpdate-announce）
                print(f"  Step4: 点 Apply", flush=True)
                try:
                    page.click("#GLUXZipUpdate-announce", timeout=3000)
                    time.sleep(3)
                except:
                    print(f"  -> Apply 失败", flush=True)
        except Exception as e:
            print(f"  -> 邮编输入失败: {type(e).__name__}: {str(e)[:50]}", flush=True)

        # Step 5: 搜索 televisor LG
        search_url = f"{base_url}/s?k=televisor+LG"
        print(f"  Step5: 搜索 {search_url}", flush=True)
        page.goto(search_url, wait_until="domcontentloaded")
        time.sleep(3)
        # 滚动加载
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(1)

        html = page.content()
        print(f"  html={len(html)}", flush=True)

        items = extract_amazon_products(html, sym, base_url)
        print(f"  提取: {len(items)} 产品, 有价: {sum(1 for i in items if i['price'])}", flush=True)
        for it in items[:6]:
            print(f"    {it['title'][:45]:<45}  {sym}{it['price'] or '?':>8}  {it['sku']}", flush=True)

        page.close()
    except Exception as e:
        print(f"  ERR: {type(e).__name__}: {str(e)[:60]}", flush=True)
    finally:
        bf.close()

    # 入库
    if items:
        row = con.execute("SELECT id FROM site WHERE code = ?", (code,)).fetchone()
        if row:
            site_id = row[0]
        else:
            cur = con.execute(
                "INSERT INTO site (code, name, base_url, protection, created_at) VALUES (?,?,?,?,?)",
                (code, name, base_url, "L2", datetime.now(timezone.utc).isoformat()))
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
                     f"AMZ EU: {it['title'][:60]}", now))
                new_s += 1
        con.commit()
        print(f"  入库: 新品{new_p} 价{new_s}", flush=True)
    time.sleep(1)

ok = con.execute("PRAGMA integrity_check").fetchone()[0]
total_p = con.execute("SELECT COUNT(*) FROM product").fetchone()[0]
total_s = con.execute("SELECT COUNT(*) FROM site").fetchone()[0]
total_ps = con.execute("SELECT COUNT(*) FROM price_snapshot").fetchone()[0]
print(f"\n=== 最终 ===")
print(f"integrity={ok}  site={total_s}  product={total_p}  price_snapshot={total_ps}")
con.close()
