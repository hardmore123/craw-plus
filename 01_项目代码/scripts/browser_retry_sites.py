# -*- coding: utf-8 -*-
"""第一部分：用 Playwright 浏览器渲染重试 JS渲染/反爬/搜索无结果站。

对每站：
  1. 先试搜索页（q=televisor），等 JS 渲染
  2. 若搜索不给力，试分类路径（/televisores 等）
  3. 从渲染后 HTML 提取商品卡（标题/链接/价格）
  4. 判定可抓 + 抽 1-3 个商品页确认价格/评价

执行方式（渲染较慢，逐站跑）：
  python -u scripts/browser_retry_sites.py [--site X] [--all]
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault("OVERSEAS_PROXY", "http://127.0.0.1:7877")

from overseas.fetchers import BrowserFetcher  # noqa: E402

# site -> (host, 国家, 币种, 搜索路径{qq}, 分类路径备选)
SITES = {
    "max_gt": ("www.max.com.gt", "gt", "GTQ", "/search?q={q}", ["/televisores", "/tv", "/televisiones"]),
    "tecnofacil_gt": ("www.tecnofacil.com.gt", "gt", "GTQ", "/buscar?q={q}", ["/televisores", "/tv"]),
    "tottus_pe": ("www.tottus.com.pe", "pe", "PEN", "/buscar?q={q}", ["/busca", "/televisores"]),
    "sodimac_pe": ("www.sodimac.com.pe", "pe", "PEN", "/catalogsearch/result/?q={q}", ["/televisores"]),
    "cresa_ec": ("www.crescos.com", "ec", "USD", "/buscar?q={q}", ["/televisores"]),
    "sukasa_ec": ("www.sukasa.com", "ec", "USD", "/buscar?q={q}", ["/televisores"]),
    "todohogar_ec": ("www.todohogar.com", "ec", "USD", "/buscar?q={q}", ["/televisores"]),
    "ferrisariato_ec": ("www.ferrisariato.com", "ec", "USD", "/buscar?q={q}", ["/televisores"]),
    "jaher_ec": ("www.jaher.com.ec", "ec", "USD", "/buscar?q={q}", ["/televisores"]),
    "lider_cl": ("www.lider.cl", "cl", "CLP", "/search?q={q}", ["/televisores", "/seccion/tv"]),
    "unicomer_gt": ("www.lacuracaonline.com", "gt", "GTQ", "/catalogsearch/result/?q={q}", ["/televisores"]),
    "falabella_pe": ("www.falabella.com.pe", "pe", "PEN", "/buscar?q={q}", ["/category/cat2501/televisores"]),
    "falabella_co": ("www.falabella.com.co", "co", "COP", "/search?q={q}", ["/category/cat2501/televisores"]),
    "falabella_cl": ("www.falabella.com", "cl", "CLP", "/buscador?q={q}", ["/category/cat2501/televisores"]),
    "artefacta_ec": ("www.artefacta.com", "ec", "USD", "/catalogsearch/result/?q={q}", ["/electrohogar/televisores"]),
    "espana_ec": ("almacenesespana.ec", "ec", "USD", "/catalogsearch/result/?q={q}", ["/televisores"]),
    "evision_pa": ("www.evisionstore.com", "pa", "USD", "/buscar?q={q}", ["/televisores", "/tv"]),
}


def extract_from_rendered(url: str, fetcher: BrowserFetcher, wait_sel: str = "",
                          settle: int = 5000) -> dict:
    """渲染一页，返回 {http, blocked, cards}[卡=title/href]。"""
    try:
        with fetcher.page(url, wait_selector=wait_sel, settle_ms=settle,
                          scroll_passes=2) as (res, dom):
            html = dom.html() if dom else ""
            status = getattr(res, "status", 0)
            blocked = getattr(res, "blocked", False)
            if dom is None or not html:
                return {"http": status, "url": url, "blocked": blocked, "cards": []}
            cards = []
            seen = set()
            # 渲染后抓 <a> + <img alt> 组合/卡片类
            all_links = dom.attr_list("a[href]", "href", limit=300) if dom else []
            for href in all_links:
                h = (href or "").strip()
                if not h.startswith("http"):
                    continue
                low = h.lower()
                if any(x in low for x in (".css", ".js", ".png", ".jpg", "login",
                                          "cart", "cuenta", "facebook", "youtube",
                                          "/search", "/account")):
                    continue
                if any(x in low for x in ("/p/", "/product", "/prod-", "/itm/",
                                          "/dp/", ".html", "-p-", "/sku")):
                    if h not in seen:
                        seen.add(h)
                        # 取该卡标题（img alt 或自身文本）
                        title = ""
                        try:
                            blk = dom.sub(f"a[href='{h}']", limit=1)
                            if blk:
                                title = (blk[0].self_text() or "")[:120]
                            if not title:
                                alt = dom.attr(f"a[href='{h}'] img", "alt")
                                title = (alt or "")[:120]
                        except Exception:
                            title = ""
                        cards.append({"url": h, "title": title.strip()})
                        if len(seen) >= 40:
                            break
            return {"http": status, "url": url, "blocked": blocked, "cards": cards}
    except Exception as e:
        return {"http": 0, "url": url, "error": f"{type(e).__name__}: {e}", "cards": []}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="", help="只跑一个站（可选）")
    ap.add_argument("--all", action="store_true", help="跑全部站")
    args = ap.parse_args()

    results = []
    fetcher = BrowserFetcher()
    try:
        sites = [args.site] if args.site else list(SITES.keys())
        for site in sorted(sites):
            if site not in SITES:
                print(f"未知站: {site}"); continue
            host, cc, cur, spath, cats = SITES[site]
            print(f"=== {site} ({host}) ===")
            found = {}
            # 1) 搜索页
            url = f"https://{host}{spath.format(q=quote('televisor'))}"
            r = extract_from_rendered(url, fetcher)
            cards = r.get("cards", [])
            if cards:
                found["method"] = "search"
                found["url"] = url
                found["cards"] = cards[:10]
                print(f"  搜索渲染得 {len(cards)} 商品卡")
            else:
                # 2) 分类页
                for cat in cats:
                    cu = f"https://{host}{cat}"
                    r2 = extract_from_rendered(cu, fetcher)
                    c2 = r2.get("cards", [])
                    if c2:
                        found["method"] = "category:" + cat
                        found["url"] = cu
                        found["cards"] = c2[:10]
                        print(f"  分类页 {cat} 得 {len(c2)} 卡")
                        break
                if not found:
                    print(f"  未渲染出商品卡 (http={r.get('http')} blocked={r.get('blocked')})")
            if found:
                results.append({"site": site, "host": host, "country": cc, **found})
                for c in found["cards"][:3]:
                    print(f"    {c['title'][:50] or '(无标题)'} | {c['url'][:70]}")
    finally:
        fetcher.close()

    with open("data/_browser_retry.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n[OUT] data/_browser_retry.json rows={len(results)}")
    return 0


if __name__ == "__main__":
    main()