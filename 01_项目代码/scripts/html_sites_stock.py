# -*- coding: utf-8 -*-
"""可达 HTML 平台站：抓在售 TV 目录 → 与 SPEC 短码交叉 → 输出价格。

对每个可达站（alkosto/rodelag/crecos/multimax 等），抓电视分类/搜索页 N 页，
从商品标题提取型号短码，与本区域 SPEC 短码做子串匹配，输出可抓价格。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "es,en;q=0.9",
}

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
}

# (site, host, region, url_tmpl 用 {q})
HTML_CATALOG = [
    ("alkosto_co", "https://www.alkosto.com", "co",
     "/tv/smart-tv/c/BI_120_ALKOS?q={q}"),
    ("rodelag_pa", "https://rodelag.com", "", "/search?q={q}"),
    ("crecos_ec", "https://www.crescos.com", "ec", "/buscar?q={q}"),
    ("multimax_pa", "https://www.multimax.net", "", "/search?q={q}"),
    ("max_gt", "https://www.max.com.gt", "", "/search?q={q}"),
    ("tecnofacil_gt", "https://www.tecnofacil.com.gt", "", "/buscar?q={q}"),
]


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def load_models(region: str) -> list[dict]:
    p = REGION_MODELS.get(region, "")
    if not p or not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if m:
                out.append({"orig": m, "short": norm(m),
                            "brand": (r.get("brand_name") or "")[:24]})
    return out


def fetch_titles(url: str) -> list[dict]:
    """抓一个商品列表页，提取 (标题, 链接, 价格?) 候选。"""
    try:
        r = requests.get(url, proxies=PROXY, headers=HDR, timeout=20,
                         verify=False, allow_redirects=True)
        html = r.text or ""
    except Exception:
        return []
    if r.status_code not in (200, 206):
        return []
    low = html.lower()
    # 通用商品卡提取：z 找 title + href
    cards = []
    # <a href=...>title</a> 且 href 像商品
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>\s*([^<]{6,180})<', html,
                         re.I):
        href, text = m.group(1), m.group(2).strip()
        if not text or len(text) < 6:
            continue
        if any(x in href.lower() for x in ("css", "js", "png", "jpg", "login",
                                           "cart", "cuenta", "facebook", "youtube")):
            continue
        # 商品链接特征
        if any(x in href.lower() for x in ("/p/", "/product", "/prod-", ".html",
                                           "/item", "/products/")):
            cards.append({"title": text, "url": href})
    return cards


def main() -> None:
    all_rows = []
    for site, host, region, tmpl in HTML_CATALOG:
        if region and region in REGION_MODELS:
            models = load_models(region)
        else:
            models = []
        print(f"=== {site} ({host}) region={region or '-'} 型号{len(models)} ===")
        # 用每个 SPEC 型号直接搜，看返回是否含目标（比拿全目录更直接）
        hits = []
        probed = 0
        if models:
            for m in models:
                if probed >= 5 or (hits and len(hits) >= 2):
                    break
                url = host + tmpl.format(q=m["orig"])
                cards = fetch_titles(url)
                probed += 1
                for c in cards:
                    if m["short"] in norm(c["title"]):
                        hits.append({"model": m["orig"], "title": c["title"][:100],
                                     "url": c["url"][:140]})
                        break
        # 若该地区无型号(巴拿马/危地马拉)或未命中，仍抓目录看整体
        if not models or len(hits) == 0:
            cards = fetch_titles(host + tmpl.format(q="tv"))
            print(f"  目录页抓取 {len(cards)} 卡片")
            if models:
                for c in cards:
                    cn = norm(c["title"])
                    for m in models:
                        if m["short"] in cn:
                            hits.append({"model": m["orig"],
                                         "title": c["title"][:100],
                                         "url": c["url"][:140]})
                            break
        print(f"  命中 SPEC 型号 {len(hits)}")
        for h in hits[:5]:
            print(f"    {h['model']:18} <- {h['title'][:60]}")
            all_rows.append({"站": site, "地区": region, "型号": h["model"],
                             "标题": h["title"], "URL": h["url"]})
        print()

    out = "data/html_stock.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "地区", "型号", "标题", "URL"])
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"[OUT] {out} rows={len(all_rows)}")


if __name__ == "__main__":
    main()