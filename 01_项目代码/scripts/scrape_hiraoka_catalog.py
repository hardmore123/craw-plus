# -*- coding: utf-8 -*-
"""抓 Hiraoka 电视分类页，列出全部在售 TV 标题/URL，供与 SPEC 型号求交。"""
from __future__ import annotations

import io
import re
import sys
import urllib3
import requests

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
}


def main() -> None:
    all_titles: list[str] = []
    all_pdps: list[str] = []
    for page_no in range(1, 4):
        url = f"https://hiraoka.com.pe/televisores/televisores/smart-tv?p={page_no}"
        try:
            r = requests_get(url)
            html = r.text or ""
            titles = re.findall(
                r'class="[^"]*product-item-link[^"]*"[^>]*>([^<]{5,150})</a>',
                html, re.I)
            hrefs = re.findall(r'href="(https://hiraoka\.com\.pe/[^"]+)"', html)
            pdps = [h for h in hrefs
                    if "televisor" in h.lower() and "/catalogsearch/" not in h]
            print(f"p{page_no}: 标题{len(titles)} 商品链{len(pdps)}")
            all_titles.extend(titles)
            all_pdps.extend(pdps)
        except Exception as e:
            print(f"p{page_no} FAIL {type(e).__name__}: {e}")

    seen: list[str] = []
    for t in all_titles:
        t = re.sub(r"&#x1[0-9a-fA-F]+;?|&quot;", "", t)
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in seen:
            seen.append(t)
    print(f"\n=== Hiraoka 在售电视标题 {len(seen)} 个 ===")
    for t in seen:
        print(" ", t[:110])
    print(f"\n商品URL {len(set(all_pdps))} 个（样例5）:")
    for h in list(dict.fromkeys(all_pdps))[:5]:
        print(" ", h)


def requests_get(url: str):
    global _session
    if _session is None:
        _session = requests.Session()
        _session.proxies = PROXY
        _session.headers = HEADERS
    return _session.get(url, timeout=25, verify=False)


_session = None

if __name__ == "__main__":
    main()