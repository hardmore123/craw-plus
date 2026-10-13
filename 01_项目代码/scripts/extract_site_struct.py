# -*- coding: utf-8 -*-
"""对可用零售站自动提取结构：搜索候选容器 / 商品URL形态 / PDP 价格与评价。

对每个传人的 site_code：
  1) 用该站搜索一个在售短型号（Q6QV 类最常见）拿搜索页 HTML
  2) 识别候选卡片容器候选选择器（按含/链接形态排名）
  3) 取首个商品 PDP URL，抓取分析：
       - JSON-LD (name/mpn/offers.price/aggregateRating/review)
       - 价格 DOM 选择器候选
       - 评价块容器候选
  输出合并 JSON 到 data/_site_struct.json
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "es-PE,es;q=0.9,en;q=0.8",
}

# 可用站点清单（批量探测 200 且有候选/JSON-LD 的）
SITES = {
    "carsa_pe": "55UR8SG",
    "metro_pe": "55UR8SG",
    "credivargas_pe": "55UR8SG",
    "comandato_ec": "55Q6QV",
    "orvehogar_ec": "55Q6QV",
    "marcimex_ec": "55Q6QV",
    "japon_ec": "55Q6QV",
    "jumbo_co": "50QNED70BSA",
    "abc_cl": "65C6K",
    "multicenter_bo": "55C655",
    "alkostoplus_bo": "50P755",
    "laganga_ec": "55Q6QV",
    "ferrisariato_ec": "55Q6QV",
}

_CARD_CLASS_PAT = re.compile(
    r'class=["\'][^"\']*((?:product|card|tile|item|grid)[-_][^\'"]{0,40})["\']', re.I)


def _ld_product(html: str) -> dict | None:
    """提取 JSON-LD 中 @type=Product 节点（含 offers/aggregateRating/reviews）。"""
    for m in re.finditer(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                         html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except Exception:
            continue

        def walk(n):
            if isinstance(n, dict):
                t = n.get("@type")
                types = [t] if isinstance(t, str) else (t or [])
                if any(str(x).lower() == "product" for x in types):
                    return n
                for v in n.values():
                    r = walk(v)
                    if r:
                        return r
            elif isinstance(n, list):
                for v in n:
                    r = walk(v)
                    if r:
                        return r
            return None
        node = walk(data)
        if node:
            return node
    return None


def top_hrefs(html: str, base: str) -> list[str]:
    """提取搜索页里的商品链接（去重，取前8个）。"""
    pats = [
        r'href="([^"]*(?:/p/|/producto/|/product/|/dp/|/televisor|/item/|/prod-)[^"]*)"',
        r'href="(https://[^"]+)"',
    ]
    out = []
    seen = set()
    for pat in pats:
        for m in re.finditer(pat, html, re.I):
            h = m.group(1).split("?")[0]
            if h in seen:
                continue
            # 过滤明显非商品的
            if any(x in h.lower() for x in (".css", ".js", ".png", ".jpg", "#", "login",
                                             "carrito", "cuenta", "ayuda", "contact")):
                continue
            seen.add(h)
            out.append(h)
            if len(out) >= 8:
                return out
    return out


def analyze(site_code: str, model: str) -> dict:
    from overseas.sites import SiteRegistry
    adapter = SiteRegistry.get(site_code)
    surl = adapter.search_url(model)
    sess = requests.Session()
    sess.proxies = PROXY
    sess.headers = HEADERS
    out = {"site": site_code, "search_url": surl}

    try:
        r = sess.get(surl, timeout=25, verify=False, allow_redirects=True)
        html = r.text or ""
        out["search_http"] = r.status_code
        out["final_url"] = r.url[:120]
    except Exception as e:
        out["search_http"] = 0
        out["search_err"] = f"{type(e).__name__}: {e}"
        return out

    # 候选容器选择器候选
    class_hits = _CARD_CLASS_PAT.findall(html)
    from collections import Counter
    cc = Counter(class_hits).most_common(8)
    out["card_classes"] = [{"class": c, "n": n} for c, n in cc]

    # 首个商品链接
    pdps = top_hrefs(html, adapter.base_url)
    out["pdp_links"] = pdps[:5]

    pdp_url = ""
    for h in pdps:
        if h.startswith("http"):
            pdp_url = h
            break
        pdp_url = adapter.base_url.rstrip("/") + h
        break
    if not pdp_url:
        out["pdp_note"] = "未找到商品链接"
        return out
    out["pdp"] = pdp_url

    try:
        r2 = sess.get(pdp_url, timeout=20, verify=False, allow_redirects=True)
        phtml = r2.text or ""
    except Exception as e:
        out["pdp_http"] = 0
        out["pdp_err"] = f"{type(e).__name__}: {e}"
        return out
    out["pdp_http"] = r2.status_code

    ld = _ld_product(phtml)
    if ld:
        offers = ld.get("offers")
        offers = offers[0] if isinstance(offers, list) and offers else offers
        mpn = ld.get("mpn") or (offers or {}).get("mpn") if isinstance(offers, dict) else ld.get("mpn")
        out["ld"] = {
            "name": (ld.get("name") or "")[:120],
            "mpn": ld.get("mpn"),
            "sku": ld.get("sku"),
            "brand": (ld.get("brand") or {}).get("name") if isinstance(ld.get("brand"), dict) else ld.get("brand"),
            "price": (offers or {}).get("price") if isinstance(offers, dict) else None,
            "currency": (offers or {}).get("priceCurrency") if isinstance(offers, dict) else None,
            "avgRating": (ld.get("aggregateRating") or {}).get("ratingValue"),
            "reviewCount": (ld.get("aggregateRating") or {}).get("reviewCount"),
            "review_cnt": len((ld.get("review") or []) if isinstance(ld.get("review"), list) else []),
        }

    # 价格 DOM 候选 + 评价容器候选
    low = phtml.lower()
    out["pdp_title"] = (re.search(r"<h1[^>]*>(.*?)</h1>", phtml, re.S | re.I)
                        and re.search(r"<h1[^>]*>(.*?)</h1>", phtml, re.S | re.I).group(1)[:80]
                        or (re.search(r"<title[^>]*>(.*?)</title>", phtml, re.S | re.I)
                            or [None, ""])[1][:80])
    price_markers = []
    for pat in ["data-price", "price-amount", 'class="price"', "price-box",
                "pdp-price", "product-price", ".precio"]:
        c = len(re.findall(re.escape(pat), phtml, re.I))
        if c:
            price_markers.append({"pat": pat, "n": c})
    out["price_markers"] = price_markers

    review_markers = []
    for pat in ["data-testid.*review", "product-reviews", "customer-review", "review-list",
                "aggregateRating", "rating-summary", "reseñas", "opiniones", "stars"]:
        c = len(re.findall(pat, phtml, re.I))
        if c:
            review_markers.append({"pat": pat, "n": c})
    out["review_markers"] = review_markers
    return out


def main() -> None:
    results = []
    for code, model in SITES.items():
        print(f"=== {code} ({model}) ===")
        try:
            r = analyze(code, model)
            print(f"  http={r.get('search_http')} final={r.get('final_url','')[:80]}")
            print(f"  卡片候选: {r.get('card_classes')[:4]}")
            print(f"  PDP链接: {r.get('pdp_links')[:3]}")
            ld = r.get("ld")
            if ld:
                print(f"  JSON-LD: name={ld.get('name')} mpn={ld.get('mpn')} "
                      f"price={ld.get('price')}{ld.get('currency')} "
                      f"rating={ld.get('avgRating')} cnt={ld.get('reviewCount')} "
                      f"review_list={ld.get('review_cnt')}")
            print(f"  价格标记: {r.get('price_markers')}")
            print(f"  评价标记: {r.get('review_markers')}")
        except Exception as e:
            print(f"  ERROR {type(e).__name__}: {e}")
            r = {"site": code, "error": f"{type(e).__name__}: {e}"}
        print()
        results.append(r)
    os.makedirs("data/site_struct", exist_ok=True)
    with open("data/site_struct/analyze.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/site_struct/analyze.json")


if __name__ == "__main__":
    main()