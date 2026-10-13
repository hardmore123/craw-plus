# -*- coding: utf-8 -*-
"""VTEX 全站在售电视全量价格（快速版）：Catalog API 直接返回价格，过滤配件，不抓 PDP。

相比 vtex_full_catalog.py（从 PDP JSON-LD 抓价失败）：
  - 价格直接从 catalog 响应的 items[].sellers[].commertialOffer.Price 拿
  - 过滤非电视（支架/灯带/遥控器/线缆等配件）
  - 全站一次跑完，快
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
        "tecnologia/televisores", "tv", "audio-y-video/televisores"]

# 配件/非电视关键词（过滤）
_ACCESSORY = ("soporte", "rack", "giratorio", "montaje", "adaptador", "cable",
              "control remoto", "barras de luz", "funda", "stand", "wall", "cargador",
              "antena", "hdmi", "limpiador", "protector")
_ALIAS = ("televisor", "smart", "tv", "qned", "oled", "uled", "qled", "nano", "neo")


def is_tv(name: str) -> bool:
    low = name.lower()
    if any(a in low for a in _ACCESSORY):
        return False
    return "tv" in low or "televisor" in low or "qned" in low or "oled" in low or "uled" in low


def model_from(name: str) -> str:
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,10})\b", name.upper())
    return m[-1] if m else ""


def fetch_catalog(host: str) -> list[dict]:
    items = []
    seen = set()
    for cat in CATS:
        for start in range(0, 80, 10):
            url = (f"https://{host}/api/catalog_system/pub/products/search/{cat}"
                   f"?_from={start}&_to={start + 9}")
            try:
                r = requests.get(url, proxies=PROXY, headers=HDR, timeout=18,
                                 verify=False)
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
                if not is_tv(name):
                    continue
                key = name
                if key in seen:
                    continue
                seen.add(key)
                # 从 items[0].sellers[0].commertialOffer 拿价格
                skus = (it.get("items") or [{}])
                sku0 = skus[0] if skus else {}
                sellers = sku0.get("sellers") or [{}]
                offer = (sellers[0] if sellers else {}).get("commertialOffer") or {}
                items.append({
                    "name": name,
                    "model": model_from(name),
                    "brand": it.get("brand") or "",
                    "price": offer.get("Price"),
                    "sku_id": sku0.get("itemId"),
                    "url": it.get("link") or "",
                })
            if len(data) < 10:
                break
    return items


def main() -> None:
    os.makedirs("data/在售全量", exist_ok=True)
    all_rows = []
    for site, (host, cc, cur) in VTEX_SITES.items():
        print(f"=== {site} ({host}) ===")
        items = fetch_catalog(host)
        n_price = sum(1 for i in items if i["price"] is not None)
        print(f"  在售电视 {len(items)} | 有价 {n_price}")
        fname = f"data/在售全量/{site}_catalog_v2.csv"
        with open(fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "model", "brand", "price",
                                              "sku_id", "url"])
            w.writeheader()
            for i in items:
                w.writerow(i)
        for i in items:
            p = i["price"]
            all_rows.append({"零售站": site, "国家": cc, "币种": cur,
                             "商品名": i["name"], "型号": i["model"],
                             "品牌": i["brand"], "价格": "" if p is None else p,
                             "sku": i["sku_id"], "URL": i["url"],
                             "抓取时间": "2026-09-19 15:00:00"})
        print()
    out = "data/在售全量/南美欧洲_VTEX在售全量_v2.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print(f"[OUT] {out} rows={len(all_rows)}")
    from collections import Counter
    print(f"按站: {dict(Counter(r['零售站'] for r in all_rows))}")
    print(f"有价: {sum(1 for r in all_rows if r['价格'] not in (None, ''))}")


if __name__ == "__main__":
    main()