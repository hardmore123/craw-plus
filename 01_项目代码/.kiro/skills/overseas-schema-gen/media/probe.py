#!/usr/bin/env python3
"""媒体评测站探测工具 — 判 JSON-LD 模式 + 评分位置 + WAF 状态。

用法：
  python media/probe.py --entry <评测列表URL> --code <站点代码>
  python media/probe.py --verify sites/<code>/adapter.py --entry <URL>
"""
from __future__ import annotations
import argparse, json, re, sys, os, ssl, urllib.request

# ---- HTTP fetch ----
def fetch_http(url, timeout=20):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    h = urllib.request.ProxyHandler({
        "http": os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877"),
        "https": os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877"),
    })
    opener = urllib.request.build_opener(h)
    opener.addheaders = [("User-Agent", "Mozilla/5.0 Chrome/120")]
    resp = opener.open(urllib.request.Request(url), timeout=timeout)
    return resp.read(400000).decode("utf-8", "replace"), resp.getcode()

def fetch_browser(url, timeout=25000):
    sys.path.insert(0, os.getcwd())
    from overseas.fetchers import BrowserFetcher
    fetcher = BrowserFetcher(
        proxy=os.environ.get("OVERSEAS_PROXY", "http://127.0.0.1:7877"),
        headless=True, site_code="media_probe",
    )
    try:
        with fetcher.page(url, wait_selector="body", nav_timeout_ms=timeout, settle_ms=4000) as (res, dom):
            if res.ok and dom:
                return dom.html(), res.status
            return "", res.status
    finally:
        fetcher.close()

# ---- 分析 ----
def analyze_jsonld(html):
    """判 JSON-LD 类型"""
    blocks = re.findall(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    types = set()
    has_review = has_product = has_article = False
    has_positive_notes = False
    product_has_review = False
    has_aggregate_rating = False
    
    for block in blocks:
        try:
            data = json.loads(block)
        except:
            continue
        items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type", "")
            if t: types.add(t)
            if t == "Review":
                has_review = True
                if "positiveNotes" in item:
                    has_positive_notes = True
            elif t == "Product":
                has_product = True
                if "review" in item or "reviews" in item:
                    product_has_review = True
                if "aggregateRating" in item:
                    has_aggregate_rating = True
            elif t in ("Article", "NewsArticle"):
                has_article = True
    
    return {
        "types": list(types),
        "has_review": has_review,
        "has_product": has_product,
        "has_article": has_article,
        "has_positive_notes": has_positive_notes,
        "product_has_review": product_has_review,
        "has_aggregate_rating": has_aggregate_rating,
    }

def detect_mode(jsonld_info):
    """判提取模式"""
    if jsonld_info["has_review"] and jsonld_info["has_positive_notes"]:
        return "jsonld_review", "JSON-LD @graph Review + positiveNotes"
    if jsonld_info["has_review"]:
        return "jsonld_review", "JSON-LD Review (无优缺点)"
    if jsonld_info["product_has_review"]:
        return "jsonld_product", "JSON-LD Product 嵌套 Review"
    if jsonld_info["has_aggregate_rating"]:
        return "jsonld_product_only", "JSON-LD Product aggregateRating (可能付费墙)"
    if jsonld_info["has_article"]:
        return "jsonld_article", "JSON-LD Article (无评分)"
    return "html", "无 JSON-LD Review → HTML fallback"

def find_review_links(html, base_url):
    """找评测文章链接"""
    patterns = [
        r'href="([^"]*(?:review|test|recension|analisis|testbericht|avis)[^"]*)"',
    ]
    links = set()
    for pat in patterns:
        for m in re.findall(pat, html, re.I):
            if m.startswith("http"):
                links.add(m)
            elif m.startswith("/"):
                base = "/".join(base_url.split("/")[:3])
                links.add(f"{base}{m}")
    links = {l for l in links if "?" not in l and "#" not in l and not any(ext in l for ext in [".css", ".js", ".png", ".jpg", ".ico"])}
    return list(links)[:20]

def detect_waf(html, status):
    """判 WAF 状态"""
    low = html.lower()[:3000]
    if "cloudflare" in low and "challenge" in low:
        return "cloudflare_challenge"
    if "datadome" in low:
        return "datadome"
    if status == 403:
        return "blocked_403"
    if "access denied" in low or "forbidden" in low:
        return "blocked"
    return "ok"

def probe(url, code, use_browser=False):
    print(f"\n=== 探测 {code}: {url} ===")
    
    # 抓取
    html = ""
    status = 0
    fetch_method = "browser" if use_browser else "http"
    try:
        if use_browser:
            html, status = fetch_browser(url)
            print(f"  抓取方式: Playwright浏览器")
        else:
            html, status = fetch_http(url)
            print(f"  抓取方式: HTTP")
        print(f"  HTTP状态: {status} | HTML长度: {len(html)}")
    except Exception as e:
        print(f"  ❌ {fetch_method} 抓取失败: {type(e).__name__}: {str(e)[:60]}")
        if not use_browser:
            print(f"  → 尝试 Playwright 浏览器...")
            try:
                html, status = fetch_browser(url)
                print(f"  ✅ 浏览器成功 | HTTP={status} | HTML={len(html)}")
                fetch_method = "browser"
            except Exception as e2:
                print(f"  ❌ 浏览器也失败: {str(e2)[:60]}")
                return None
        else:
            return None
    
    if not html or len(html) < 500:
        print(f"  ❌ HTML过短({len(html)}), 可能被拦截")
        return None
    
    # WAF
    waf = detect_waf(html, status)
    if waf != "ok":
        print(f"  ⚠️ WAF状态: {waf}")
    else:
        print(f"  ✅ WAF状态: ok")
    
    # JSON-LD
    jsonld = analyze_jsonld(html)
    mode, mode_desc = detect_mode(jsonld)
    print(f"  JSON-LD类型: {jsonld['types']}")
    print(f"  提取模式: {mode} ({mode_desc})")
    
    # 评分位置
    if mode == "jsonld_review":
        print(f"  评分位置: reviewRating.ratingValue")
    elif mode == "jsonld_product":
        print(f"  评分位置: Product.review.reviewRating.ratingValue")
    elif mode == "jsonld_product_only":
        print(f"  评分位置: Product.aggregateRating.ratingValue (可能付费墙)")
    elif mode == "jsonld_article":
        print(f"  评分位置: 无(JSON-LD Article无评分) → 需HTML fallback")
    else:
        print(f"  评分位置: HTML正文(需per-site选择器)")
    
    # 评测链接
    review_links = find_review_links(html, url)
    print(f"  评测文章链接: {len(review_links)}")
    for l in review_links[:5]:
        print(f"    → {l[:80]}")
    
    # 评分量表提示
    print(f"\n  === 建议 ===")
    print(f"  playbook: {mode}")
    print(f"  requires_browser: {use_browser or fetch_method == 'browser'}")
    if mode in ("jsonld_review", "jsonld_product"):
        print(f"  rating_scale: 0-10 (默认, 按实际确认)")
    elif mode == "html":
        print(f"  rating_scale: 需探查(per-site, 注意德国1-5反序)")
    
    return {
        "code": code, "url": url, "status": status, "html_len": len(html),
        "waf": waf, "jsonld_types": jsonld["types"], "mode": mode,
        "review_links": len(review_links), "requires_browser": use_browser or fetch_method == "browser",
    }


def main():
    ap = argparse.ArgumentParser(description="媒体评测站探测")
    ap.add_argument("--entry", required=True, help="评测列表页URL")
    ap.add_argument("--code", required=True, help="站点代码")
    ap.add_argument("--browser", action="store_true", help="强制用浏览器")
    args = ap.parse_args()
    
    result = probe(args.entry, args.code, use_browser=args.browser)
    if result:
        print(f"\n✅ 探测完成: {args.code} → 模式={result['mode']}")

if __name__ == "__main__":
    main()
