# -*- coding: utf-8 -*-
"""LFL Group 评论 API 抓取脚本（Leon's / The Brick 通用）。

LFL Group 的两个零售站（Leon's 和 The Brick）用同一个评论 API:
    POST https://ecom.api.lflgroup.ca/ecom/item/reviews/get
    Header: x-shopify-shop-domain: www.leons.ca 或 www.thebrick.com
    Body: {"sku": "<shopify_product_id>", "page": 1, "pageSize": 100, "sort": "dateDesc"}

关键：sku 参数是 Shopify 产品 ID（JSON-LD Product.sku），不是 URL slug 或 model name。
需要先从商品页提取 JSON-LD sku，再调 API。

用法:
    py -3.12 scripts/crawl_lfl_reviews.py --site thebrick_ca --db <db_path> [--max-products 10] [--max-pages 30]
    py -3.12 scripts/crawl_lfl_reviews.py --site leons_ca --db <db_path> --model 75U88QG
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request

API_URL = "https://ecom.api.lflgroup.ca/ecom/item/reviews/get"
SHOP_DOMAINS = {
    "leons_ca": "www.leons.ca",
    "thebrick_ca": "www.thebrick.com",
}
BASE_URLS = {
    "leons_ca": "https://www.leons.ca",
    "thebrick_ca": "https://www.thebrick.com",
}


def fetch_jsonld_sku(url: str, proxy: str) -> str | None:
    """获取商品页 HTML，提取 JSON-LD 中的 Product.sku。

    先试 HTTP（快），失败后用 Playwright 浏览器（慢但能过 429/JS 渲染）。
    """
    # ---- 1) 先试 HTTP ----
    proxy_handler = urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy}
    )
    opener = urllib.request.build_opener(proxy_handler)
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        ("Accept", "text/html,application/xhtml+xml"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    html = ""
    try:
        resp = opener.open(url, timeout=20)
        html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    [HTTP] {e}")

    # 如果 HTTP 拿到了足够大的 HTML，直接解析
    if html and len(html) > 5000:
        sku = _extract_sku_from_html(html)
        if sku:
            return sku

    # ---- 2) HTTP 失败 → 用 Playwright 浏览器 ----
    print(f"    [HTTP] 失败或无 sku，回退浏览器...")
    try:
        sku = _extract_sku_via_browser(url, proxy)
        if sku:
            print(f"    [浏览器] 获取到 sku: {sku}")
            return sku
        else:
            print(f"    [浏览器] 未找到 JSON-LD sku")
            return None
    except Exception as e:
        import traceback
        print(f"    [浏览器] 异常: {e}")
        traceback.print_exc()
        return None


def _extract_sku_from_html(html: str) -> str | None:
    """从 HTML 中提取 LFL API 所需的 sku（品牌内部产品编号，如 1467588Q）。

    优先级：
    1. <input id="product-sku" value="...">  ← 最可靠
    2. window.ProductDataForBV = { sku:"..." }  ← JS 变量
    3. JSON-LD Product.sku  ← 有时存在
    4. <meta itemprop="sku" content="...">  ← 兜底
    """
    # 1. <input id="product-sku" value="1467588Q">
    m = re.search(
        r'<input[^>]*id=["\']product-sku["\'][^>]*value=["\']([^"\']+)["\']',
        html, re.I,
    )
    if m:
        return m.group(1)

    # 2. window.ProductDataForBV = { sku:"1467588Q", ... }
    m = re.search(
        r'ProductDataForBV\s*=\s*\{[^}]*sku\s*:\s*["\']([^"\']+)["\']',
        html, re.I,
    )
    if m:
        return m.group(1)

    # 3. JSON-LD Product.sku
    scripts = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.S,
    )
    for s in scripts:
        try:
            data = json.loads(s)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        sku = item.get("sku", "")
                        if sku:
                            return str(sku)
            elif isinstance(data, dict) and data.get("@type") in ("Product", ["Product"]):
                sku = data.get("sku", "")
                if sku:
                    return str(sku)
        except Exception:
            pass

    # 4. <meta itemprop="sku" content="...">
    m = re.search(
        r'<meta[^>]*itemprop=["\']sku["\'][^>]*content=["\']([^"\']+)["\']',
        html,
    )
    if m:
        return m.group(1)
    return None


def _extract_sku_via_browser(url: str, proxy: str) -> str | None:
    """用 Playwright 浏览器打开页面提取 JSON-LD sku。"""
    from playwright.sync_api import sync_playwright
    import time

    p = sync_playwright().start()
    pkw = {
        "headless": True,
        "proxy": {"server": proxy},
        "args": ["--disable-blink-features=AutomationControlled"],
    }
    # 非持久化 context（更快，不锁目录）
    b = None
    for ch in ["msedge", "chrome", None]:
        try:
            if ch:
                b = p.chromium.launch(channel=ch, **pkw)
            else:
                b = p.chromium.launch(**pkw)
            break
        except Exception as e:
            print(f"    [浏览器] channel={ch} 失败: {e}")
            continue
    if b is None:
        p.stop()
        return None

    pg = b.new_page()
    pg.set_default_navigation_timeout(60000)
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(10)  # 等待 JS 渲染 ProductDataForBV
        html = pg.content()
    except Exception as e:
        print(f"    [浏览器] goto 失败: {e}")
        b.close()
        p.stop()
        return None

    # 用统一的 HTML 提取逻辑（已更新支持 product-sku input）
    sku = _extract_sku_from_html(html)

    # 兜底：JS 变量 ProductDataForBV.sku
    if not sku:
        try:
            bv_sku = pg.evaluate("""
                () => {
                    if (window.ProductDataForBV && window.ProductDataForBV.sku)
                        return window.ProductDataForBV.sku;
                    const inp = document.getElementById('product-sku');
                    if (inp && inp.value) return inp.value;
                    return null;
                }
            """)
            if bv_sku:
                sku = bv_sku
        except Exception:
            pass

    b.close()
    p.stop()
    return str(sku) if sku else None


def fetch_lfl_reviews(
    sku: str, shop_domain: str, proxy: str,
    page: int = 1, page_size: int = 100, sort: str = "dateDesc",
) -> dict:
    """调 LFL Group 评论 API，返回 JSON。"""
    proxy_handler = urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy}
    )
    opener = urllib.request.build_opener(proxy_handler)
    body = json.dumps(
        {"sku": sku, "page": page, "pageSize": page_size, "sort": sort}
    ).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-shopify-shop-domain", shop_domain)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = opener.open(req, timeout=15)
    return json.loads(resp.read().decode("utf-8"))


def parse_lfl_review(r: dict, product_url: str) -> tuple[str, dict]:
    """把 LFL API 返回的评论转成 DB 字段（含图片/视频）。"""
    rid = str(r.get("id") or r.get("reviewId") or "")
    rating = r.get("rating") or r.get("score")
    title = str(r.get("title") or "").strip()
    body = str(r.get("body") or r.get("content") or r.get("review") or "").strip()
    author = str(r.get("author") or r.get("name") or r.get("reviewerName") or "").strip()
    date = str(r.get("date") or r.get("createdAt") or r.get("publishedAt") or "").strip()

    # 图片/视频提取（LFL API 的 photos/videos 字段，多种变体名兼容）
    images = []
    for key in ("photos", "images", "pictures", "mediaPhotos"):
        items = r.get(key)
        if isinstance(items, list):
            for item in items:
                url = ""
                if isinstance(item, str):
                    url = item
                elif isinstance(item, dict):
                    url = str(item.get("url") or item.get("src") or
                              item.get("original") or item.get("large") or
                              item.get("thumbnail") or "")
                if url:
                    images.append(url)
            break

    videos = []
    for key in ("videos", "video", "mediaVideos"):
        items = r.get(key)
        if isinstance(items, list):
            for item in items:
                url = ""
                if isinstance(item, str):
                    url = item
                elif isinstance(item, dict):
                    url = str(item.get("url") or item.get("src") or
                              item.get("videoUrl") or item.get("hlsUrl") or "")
                if url:
                    videos.append(url)
            break

    return rid, {
        "rating": float(rating) if rating else None,
        "title": title[:300],
        "body": body[:5000],
        "author": author[:120],
        "review_date": date[:80],
        "review_url": product_url,
        "image_urls": images,
        "image_count": len(images),
        "video_urls": videos,
        "has_video": 1 if videos else 0,
    }


def crawl_site(
    site_code: str, db_path: str, proxy: str,
    max_products: int = 0, model_filter: str = "",
    max_pages: int = 30, page_size: int = 100,
):
    """对某站点批量抓评论。"""
    shop_domain = SHOP_DOMAINS.get(site_code, "")
    base_url = BASE_URLS.get(site_code, "")
    if not shop_domain:
        print(f"不支持站点: {site_code}（支持: {list(SHOP_DOMAINS)}）")
        return

    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # 查已入库产品
    if model_filter:
        cur.execute(
            """SELECT p.id, p.sku, p.url FROM product p
               JOIN site s ON p.site_id=s.id
               WHERE s.code=? AND p.model=?""",
            (site_code, model_filter),
        )
    else:
        cur.execute(
            """SELECT p.id, p.sku, p.url FROM product p
               JOIN site s ON p.site_id=s.id
               WHERE s.code=?""",
            (site_code,),
        )
    products = cur.fetchall()
    if max_products > 0:
        products = products[:max_products]
    print(f"[{site_code}] 待处理产品: {len(products)} 个")

    total_new = 0
    for pid, sku, url in products:
        full_url = url if url.startswith("http") else base_url + url
        print(f"\n  product_id={pid} url={full_url[:80]}")

        # 1. 获取 Shopify 产品 ID（从 JSON-LD）
        shopify_sku = fetch_jsonld_sku(full_url, proxy)
        if not shopify_sku:
            print(f"    无法获取 JSON-LD sku，跳过")
            continue
        print(f"    JSON-LD sku: {shopify_sku}")

        # 2. 翻页抓评论
        known_keys = set()
        cur.execute(
            "SELECT review_key FROM review WHERE product_id=?", (pid,)
        )
        for row in cur.fetchall():
            known_keys.add(str(row[0]))
        print(f"    已入库: {len(known_keys)} 条")

        product_new = 0
        for page in range(1, max_pages + 1):
            try:
                result = fetch_lfl_reviews(
                    shopify_sku, shop_domain, proxy, page=page, page_size=page_size
                )
            except Exception as e:
                print(f"    p{page} API 错误: {e}")
                break

            reviews = result.get("reviews", [])
            if not reviews:
                print(f"    p{page} 无评论，停止")
                break

            new_count = 0
            for r in reviews:
                rid, fields = parse_lfl_review(r, full_url)
                if not rid or rid in known_keys:
                    continue
                known_keys.add(rid)
                cur.execute(
                    """INSERT INTO review (product_id, review_key, rating, title, body,
                       author, review_date, review_url, image_urls, image_count,
                       video_urls, has_video, captured_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?, '')""",
                    (pid, rid, fields["rating"], fields["title"], fields["body"],
                     fields["author"], fields["review_date"], fields["review_url"],
                     " | ".join(fields["image_urls"]), fields["image_count"],
                     " | ".join(fields["video_urls"]), fields["has_video"]),
                )
                new_count += 1
            con.commit()
            product_new += new_count
            print(f"    p{page}: {len(reviews)} 条，新增 {new_count} 条")

            # 全是已知评论 → 停
            if new_count == 0 and page > 1:
                print(f"    本页无新增，停止")
                break
            time.sleep(0.5)  # 限速

        total_new += product_new
        print(f"    本产品新增: {product_new} 条")

    con.close()
    print(f"\n[{site_code}] 完成！总新增评论: {total_new} 条")


def main():
    ap = argparse.ArgumentParser(description="LFL Group 评论抓取")
    ap.add_argument("--site", required=True, choices=list(SHOP_DOMAINS))
    ap.add_argument("--db", required=True)
    ap.add_argument("--model", default="", help="只抓该型号")
    ap.add_argument("--max-products", type=int, default=0)
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--proxy", default="http://127.0.0.1:7877")
    args = ap.parse_args()

    crawl_site(
        args.site, args.db, args.proxy,
        max_products=args.max_products,
        model_filter=args.model,
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
