"""媒体评测网站抓取脚本 — 抓取 techfi_nl 等评测站，写入 media_review 表。

用法:
    python scripts/crawl_media_reviews.py --site techfi_nl --db data/overseas.db
    python scripts/crawl_media_reviews.py --site techfi_nl --db data/overseas.db --category televisies

抓取流程:
  1. adapter.review_list_url(category) → 列表页 URL
  2. HTTP GET 列表页 → adapter.parse_review_list(html) → 评测文章 URL 列表
  3. 逐个 HTTP GET 文章页 → adapter.parse_review(html, url) → MediaReview dict
  4. INSERT OR REPLACE INTO media_review
"""
from __future__ import annotations
import sys, os, json, sqlite3, time, argparse, re

# Add parent to path so we can import overseas
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
sys.stdout.reconfigure(encoding="utf-8")

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Import the adapter registry
from overseas.sites import SiteRegistry


def fetch_url(url: str, timeout: int = 30) -> str:
    """HTTP GET with basic headers, return HTML text."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,nl;q=0.8,de;q=0.7",
    }
    # Use proxy if set
    proxy = os.environ.get("OVERSEAS_PROXY", "")
    if proxy:
        from urllib.request import ProxyHandler, build_opener
        proxy_handler = ProxyHandler({"http": proxy, "https": proxy})
        opener = build_opener(proxy_handler)
        req = Request(url, headers=headers)
        resp = opener.open(req, timeout=timeout)
    else:
        req = Request(url, headers=headers)
        resp = urlopen(req, timeout=timeout)
    data = resp.read()
    # Try decode as utf-8
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return data.decode("utf-8", errors="replace")


def crawl_media_reviews(site_code: str, db_path: str, category: str = "", max_articles: int = 200):
    """抓取评测站点的评测文章，写入 media_review 表。"""
    # Find adapter via SiteRegistry
    registry = SiteRegistry.discover()
    adapter = None
    for code, cls in registry.items():
        if code == site_code:
            adapter = cls()
            break
    if not adapter:
        print(f"❌ 未找到站点 {site_code}，可用: {list(registry.keys())}")
        return 0
    if not getattr(adapter, "supports_media", False):
        print(f"❌ 站点 {site_code} 不支持媒体评测（supports_media=False）")
        return 0

    print(f"{'='*70}")
    print(f"  抓取评测站: {site_code} ({adapter.name})")
    print(f"  DB: {db_path}")
    print(f"{'='*70}")

    # Step 1: Get review list URLs
    cats = [category] if category else getattr(adapter, "CATEGORIES", ["televisies"])
    all_article_urls = []
    for cat in cats:
        url = adapter.review_list_url(cat)
        print(f"\n[列表] {cat}: {url}")
        try:
            html = fetch_url(url)
            article_urls = adapter.parse_review_list(None, html)
            print(f"  → 发现 {len(article_urls)} 个评测文章链接")
            all_article_urls.extend(article_urls)
        except Exception as e:
            print(f"  ❌ 列表页抓取失败: {e}")
            continue
        time.sleep(1)

    # Dedupe
    seen = set()
    unique_urls = []
    for u in all_article_urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)
    print(f"\n去重后共 {len(unique_urls)} 个评测文章待抓取")
    if max_articles > 0:
        unique_urls = unique_urls[:max_articles]
        print(f"限制抓取前 {max_articles} 个")

    # Step 2: Fetch each article and parse
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    inserted = 0
    updated = 0
    skipped = 0
    errors = 0

    for i, article_url in enumerate(unique_urls, 1):
        try:
            html = fetch_url(article_url)
            review = adapter.parse_review(html, article_url)
            if not review:
                print(f"  [{i}/{len(unique_urls)}] SKIP (无评测数据): {article_url[:80]}")
                skipped += 1
                continue

            # Check if already exists
            cur.execute("SELECT id FROM media_review WHERE site_code=? AND article_url=?",
                        (review["site_code"], article_url))
            existing = cur.fetchone()

            # Build SQL
            cols = ["site_code","article_url","title","headline","description","author",
                    "date_published","date_modified","product_name","product_model","product_brand",
                    "rating_value","best_rating","worst_rating","rating_scale",
                    "positive_notes","negative_notes","article_type","captured_at","raw_jsonld"]
            vals = [
                review.get("site_code",""), article_url,
                review.get("title",""), review.get("headline",""),
                review.get("description",""), review.get("author",""),
                review.get("date_published",""), review.get("date_modified",""),
                review.get("product_name",""), review.get("product_model",""),
                review.get("product_brand",""),
                review.get("rating_value"), review.get("best_rating"), review.get("worst_rating"),
                review.get("rating_scale",""),
                json.dumps(review.get("positive_notes",[]), ensure_ascii=False) if review.get("positive_notes") else "[]",
                json.dumps(review.get("negative_notes",[]), ensure_ascii=False) if review.get("negative_notes") else "[]",
                review.get("article_type","review"),
                datetime_now(),
                "",
            ]
            placeholders = ",".join(["?"]*len(cols))
            col_str = ",".join(cols)

            if existing:
                # Update
                set_clause = ",".join(f"{c}=?" for c in cols if c not in ("site_code","article_url"))
                set_vals = [v for c, v in zip(cols, vals) if c not in ("site_code","article_url")]
                set_vals.extend([review["site_code"], article_url])
                cur.execute(f"UPDATE media_review SET {set_clause} WHERE site_code=? AND article_url=?", set_vals)
                updated += 1
                rating_str = f" {review.get('rating_value')}/10" if review.get("rating_value") else ""
                print(f"  [{i}/{len(unique_urls)}] UPDATE{rating_str}: {review.get('product_name','')[:40]}")
            else:
                # Insert
                cur.execute(f"INSERT OR REPLACE INTO media_review ({col_str}) VALUES ({placeholders})", vals)
                inserted += 1
                rating_str = f" {review.get('rating_value')}/10" if review.get("rating_value") else ""
                print(f"  [{i}/{len(unique_urls)}] INSERT{rating_str}: {review.get('product_name','')[:40]}")

            con.commit()
        except Exception as e:
            errors += 1
            print(f"  [{i}/{len(unique_urls)}] ❌ ERROR: {e} | {article_url[:60]}")

        # Rate limit
        time.sleep(getattr(adapter, "suggested_interval", 2.0))

    con.close()
    print(f"\n{'='*70}")
    print(f"  抓取完成: 新增={inserted} 更新={updated} 跳过={skipped} 错误={errors}")
    print(f"{'='*70}")
    return inserted + updated


def datetime_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description="媒体评测网站抓取")
    parser.add_argument("--site", required=True, help="站点代码，如 techfi_nl")
    parser.add_argument("--db", default="data/overseas.db")
    parser.add_argument("--category", default="", help="品类，如 televisies")
    parser.add_argument("--max", type=int, default=200, help="最大抓取文章数")
    args = parser.parse_args()
    crawl_media_reviews(args.site, args.db, args.category, args.max)


if __name__ == "__main__":
    main()
