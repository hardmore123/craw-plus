# -*- coding: utf-8 -*-
"""把某站某 URL 用该站真实抓取器（浏览器/HTTP，含代理与等待）打开并落盘，供人工/脚本分析 DOM。

用法：py -3.12 scripts/dump_page.py --site alkosto_co --url "<URL>" [--wait 12000] [--scroll 6]
产出：data/sandbox/dump/<site>.html，并打印：标题、长度、XHR/JSON 线索、含 /p/ 等 PDP 形态的链接样例
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import crawl_ca_retail as C  # noqa: E402
from overseas.scenarios import open_dom  # noqa: E402
from overseas.sites import SiteRegistry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--wait", type=int, default=8000)
    ap.add_argument("--scroll", type=int, default=4)
    a = ap.parse_args()
    ad = SiteRegistry.get(a.site)
    spec = C._resolve_site_spec(a.site, None) or {}
    sf, _ = C._make_fetcher(ad, spec)
    with open_dom(ad, sf, a.url, wait_selector="a", scroll_passes=a.scroll,
                  extra_wait_ms=a.wait) as (res, dom, html):
        os.makedirs("data/sandbox/dump", exist_ok=True)
        p = f"data/sandbox/dump/{a.site}.html"
        open(p, "w", encoding="utf-8").write(html or "")
        print("status", res.status, "blocked", res.blocked, res.block_reason, "len", len(html or ""), "->", p)
        t = re.search(r"<title[^>]*>(.*?)</title>", html or "", re.S | re.I)
        print("title:", (t.group(1).strip()[:100] if t else ""))
        hrefs = re.findall(r'href="([^"]+)"', html or "")
        for pat in (r"/p/\d", r"/p$", r"/p\?", r"\.html", r"/product", r"/producto", r"/dp/", r"/ip/"):
            ex = [h for h in hrefs if re.search(pat, h)]
            if ex:
                print(f"  {pat:12} {len(ex):4}  e.g. {ex[:3]}")
        for kw in ("algolia", "searchspring", "klevu", "doofinder", "constructor.io", "bloomreach",
                   "__NEXT_DATA__", "__NUXT__", "window.__INITIAL_STATE__", "application/ld+json"):
            if kw.lower() in (html or "").lower():
                print("  clue:", kw)
    sf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
