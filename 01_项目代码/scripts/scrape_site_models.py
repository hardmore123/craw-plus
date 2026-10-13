# -*- coding: utf-8 -*-
"""通用：抓一个零售站某个分类页的 在售商品卡片，保存 (标题, URL) 清单。

用法：py scripts/scrape_site_models.py <site_key>
site_key 决定分类页 URL 与输出路径（先内置 Hiraoka，后续按站加）。
"""
from __future__ import annotations

import io
import json
import re
import sys
from urllib.parse import quote

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
}

# 各站点分类页（商品列表）抓取配置
SITE_CATALOG = {
    "hiraoka_pe": {
        "name": "Hiraoka",
        "pages": [
            "https://hiraoka.com.pe/televisores/televisores/smart-tv?p={page}",
        ],
        "title_re": r'class="[^"]*product-item-link[^"]*"[^>]*>([^<]{5,200})</a>',
        "pdp_re": r'href="(https://hiraoka\.com\.pe/[^"]+)"',
        "pdp_filter": lambda h: "televisor" in h.lower() and "/catalogsearch/" not in h,
    },
}


def _session() -> requests.Session:
    s = requests.Session()
    s.proxies = PROXY
    s.headers = HEADERS
    return s


def fetch_catalog(site_key: str, pages: int = 4) -> list[dict]:
    cfg = SITES_CATALOG[site_key]
    sess = _session()
    cards: list[dict] = []
    seen_urls: set[str] = set()
    for page_no in range(1, pages + 1):
        tmpl = cfg["pages"][0]
        url = tmpl.format(page=page_no)
        try:
            r = sess.get(url, timeout=30, verify=False)
            html = r.text or ""
        except Exception as e:
            print(f"  p{page_no} FAIL {type(e).__name__}: {e}")
            continue
        titles = re.findall(cfg["pdp_re"], html, re.I)
        hrefs = re.findall(cfg["pdp_re"], html)
        pdps = [h for h in hrefs if cfg["pdp_excl"](h)]
        print(f"  p{page_no}: titles={len(titles)} pdps={len(pdps)}")
        for t, h in zip(titles, pdps if len(pdps) >= len(titles) else titles):
            t = re.sub(r"\s+", " ", t).strip()
            if not t or h in seen_urls:
                continue
            seen_urls.add(h)
            cards.append({"title": t, "url": h})
    return cards


if __name__ == "__main__":
    pass