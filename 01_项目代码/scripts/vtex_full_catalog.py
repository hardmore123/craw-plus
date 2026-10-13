# -*- coding: utf-8 -*-
"""VTEX 全站在售电视目录全量价格抓取（所有在售 TV，不限于 SPEC 命中）。

对每个 VTEX 站：Catalog API 拉 televisores 类目全部在售商品（JSON），
提取 商品名/型号/价格/链接/尺寸，输出每站全量价格 CSV + 全站汇总。
同时探测商品是否有评价（JSON-LD aggregateRating / 评价 API）。
"""
from __future__ import annotations

import csv
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
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# VTEX 站：site -> (host, 国家, 币种, 平台)
VTEX_SITES = {
    "oechsle_pe": ("www.oechsle.pe", "秘鲁", "PEN"),
    "plazavea_pe": ("www.plazavea.com.pe", "秘鲁", "PEN"),
    "estilos_pe": ("www.estilos.com.pe", "秘鲁", "PEN"),
    "metro_pe": ("www.metro.pe", "秘鲁", "PEN"),
    "carsa_pe": ("www.carsa.pe", "秘鲁", "PEN"),
    "credivargas_pe": ("www.credivargas.pe", "秘鲁", "PEN"),
    "japon_ec": ("www.almacenesjapon.com", "厄瓜多尔", "USD"),
    "orvehogar_ec": ("www.orvehogar.com", "厄瓜多尔", "USD"),
    "marcimex_ec": ("www.marcimex.com", "厄瓜多尔", "USD"),
    "comandato_ec": ("www.comandato.com", "厄瓜多尔", "USD"),
    "exito_co": ("www.exito.com", "哥伦比亚", "COP"),
    "jumbo_co": ("www.jumbocolombia.com", "哥伦比亚", "COP"),
    "multicenter_bo": ("www.multicenter.com", "玻利维亚", "BOB"),
    "elektra_gt": ("www.elektra.com.gt", "危地马拉", "GTQ"),
}

CATS = ["televisores", "televisores/smart-tv", "televisiones",
        "tecnologia/televisores", "tv", "televisores-4k", "audio-y-video/televisores"]


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def model_from_title(t: str) -> str:
    """从商品名提取疑似型号（末尾 数字+字母 token）。"""
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", t.upper())
    return m[-1] if m else ""


def cat_items(host: str) -> list[dict]:
    items = []
    seen = set()
    for cat in CATS:
        for start in range(0, 60, 10):
            url = (f"https://{host}/api/catalog_system/pub/products/search/{cat}"
                   f"?_from={start}&_to={start + 9}")
            try:
                r = requests.get(url, proxies=PROXY, headers=HDR, timeout=18, verify=False)
            except Exception:
                break
            if r.status_code not in (200, 206):
                break
            try:
                data = r.json()
            except Exception:
                break
            if not isinstance(data, list) or not data:
                break
            for it in data:
                name = it.get("productName") or ""
                low = name.lower()
                if "televisor" not in low and "tv" not in low[:8] and "qned" not in low \
                        and "oled" not in low and "uled" not in low:
                    continue
                key = name
                if key in seen:
                    continue
                seen.add(key)
                items.append({"name": name, "url": it.get("link") or "",
                              "model": model_from_title(name),
                              "brand": it.get("brand") or ""})
            if len(data) < 10:
                break
    # 补充：价格/评分通过每种商品详情 API（用第一个 sku 查 sellers/offer）
    out = []
    for it in items:
        url = it["url"]
        if not url.startswith("http"):
            url = "https://" + host + url
        # VTEX 详情页 JSON-LD（简单抓一次确认价格/评价）
        price, rating, review_cnt = fetch_price_review(url)
        out.append({
            "name": it["name"], "url": url, "model": it["model"],
            "brand": it["brand"], "price": price, "rating": rating,
            "review_count": review_cnt,
        })
    return out


def fetch_price_review(url: str) -> tuple:
    """抓商品页 JSON-LD 拿价格/评分/评论数（VTEX 商品页通常有 Product JSON-LD）。"""
    price = rating = rcnt = None
    try:
        h = dict(HDR)
        h["Accept"] = "text/html,application/xhtml+xml"
        r = requests.get(url, proxies=PROXY, headers=h, timeout=15, verify=False)
        html = r.text or ""
        for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                             html, re.S):
            s = m.group(1).strip()
            if '"Product"' not in s and '"product"' not in s[:50]:
                continue
            try:
                d = json.loads(s)
            except Exception:
                continue
            offers = d.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                price = offers.get("price")
            agg = d.get("aggregateRating") or {}
            rating = agg.get("ratingValue")
            rcnt = agg.get("reviewCount")
            if price is not None:
                break
    except Exception:
        pass
    return price, rating, rcnt


def model_dim_title(t: str) -> str:
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", t.upper())
    return m[-1] if m else ""


def main() -> None:
    os.makedirs("data/在售全量", exist_ok=True)
    all_rows = []
    for site, (host, cc, cur) in VTEX_SITES.items():
        print(f"=== {site} ({host}) 拉取在售电视全量 ===")
        items = cat_items(host)
        print(f"  在售电视: {len(items)}")
        fname = f"data/在售全量/{site}_catalog.csv"
        with open(fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "url", "model", "brand",
                                              "price", "rating", "review_count"])
            w.writeheader()
            for it in items:
                w.writerow(it)
        print(f"  [OUT] {fname}")
        # 汇总行
        for it in items:
            all_rows.append({
                "零售站": site, "国家": cc, "币种": cur, "商品名": it["name"],
                "型号": it["model"], "价格": it["price"], "评分": it["rating"],
                "评论数": it["review_count"], "URL": it["url"],
                "抓取时间": "2026-09-19 06:00:00",
            })
        print()

    out = "data/在售全量/南美欧洲_VTEX在售全量.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["零售站", "国家", "币种", "商品名", "型号",
                                          "价格", "评分", "评论数", "URL", "抓取时间"])
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"[OUT] {out} rows={len(all_rows)}")
    # 汇总
    from collections import Counter
    print(f"\n每站商品数: {dict(Counter(r['零售站'] for r in all_rows))}")
    has_price = sum(1 for r in all_rows if r["价格"] not in (None, ""))
    print(f"有价格商品: {has_price}")
    has_rating = sum(1 for r in all_rows if r["评分"] not in (None, ""))
    print(f"有评分商品: {has_rating}")


if __name__ == "__main__":
    main()