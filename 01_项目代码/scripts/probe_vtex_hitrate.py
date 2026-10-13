# -*- coding: utf-8 -*-
"""VTEX 批量探测：用各国短码型号清单查询各 VTEX 站 Catalog API，统计命中率。

确定每个站真正在售哪些 SPEC 型号（这是能否用引擎抓价格+网评的前提）。
输出 data/vtex_hitrate.json：站 → {api_host, 命中型号, 匹配商品名/价格样例}。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}

# site_code -> VTEX API host（特例覆盖默认）
VTEX_API_HOST = {
    "carsa_pe": "www.carsa.pe",
    "metro_pe": "www.metro.pe",
    "credivargas_pe": "www.credivargas.pe",
    "comandato_ec": "www.comandato.com",
    "orvehogar_ec": "www.orvehogar.com",
    "marcimex_ec": "www.marcimex.com",
    "japon_ec": "www.almacenesjapon.com",
    "jumbo_co": "www.jumbocolombia.com",
    "multicenter_bo": "www.multicenter.com",
    "laganga_ec": "laganga.com",
    "ferrisariato_ec": "www.ferrisariato.com",   # 非VTEX, 试探
}

# site -> 对应型号清单csv
SITE_MODELS_CSV = {
    "carsa_pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "metro_pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "credivargas_pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "comandato_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "orvehogar_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "marcimex_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "japon_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "jumbo_co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "multicenter_bo": "data/型号清单_短码/models_玻利维亚_short.csv",
    "laganga_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "ferrisariato_ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
}


def load_models_csv(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if m:
                out.append({"model": m, "brand": r.get("brand_name") or "",
                            "brand_code": r.get("brand_code") or ""})
    return out


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def query_vtex(host: str, model: str) -> dict | None:
    """VTEX Catalog API 按关键词搜索商品。返回 (productName, link, price) 或 None。"""
    url = f"https://{host}/api/catalog_system/pub/products/search/?q={model}&_from=0&_to=5"
    try:
        r = requests.get(url, proxies=PROXY, headers=HEADERS, timeout=18, verify=False)
        if r.status_code not in (200, 206):
            return {"err": f"http{r.status_code}"}
        try:
            data = r.json()
        except Exception:
            return {"err": "not-json"}
        if not isinstance(data, list) or not data:
            return None
        first = data[0]
        name = first.get("productName") or ""
        link = first.get("link") or ""
        skus = (first.get("items") or [{}])[0]
        sellers = (skus.get("sellers") or [{}])[0]
        offer = sellers.get("commertialOffer") or {}
        return {
            "name": name[:110],
            "link": link,
            "price": offer.get("Price"),
            "n": len(data),
        }
    except Exception as e:
        return {"err": f"{type(e).__name__}:{e}"}


def main() -> None:
    results = {}
    for site, host in VTEX_API_HOST.items():
        csv_path = SITE_MODELS_CSV.get(site, "")
        if not os.path.exists(csv_path):
            print(f"{site}: 型号清单不存在 {csv_path}")
            continue
        models = load_models_csv(csv_path)
        print(f"=== {site} ({host}) —— {len(models)} 个型号 ===")
        hits = 0
        hit_list = []
        for m in models:
            got = query_vtex(host, m["model"])
            if got and not got.get("err"):
                # 校验返回商品是否真的包含型号（防碰巧命中其他商品）
                got_name = norm(got.get("name") or "")
                got_link = norm(got.get("link") or "")
                want = norm(m["model"])
                if want in got_name or want in got_link:
                    hits += 1
                    hit_list.append({"model": m["model"], **got})
            # 礼貌节流
            # (不做: VTEX API 允许较高频率)
        print(f"  命中 {hits}/{len(models)}")
        for h in hit_list[:8]:
            print(f"    {h['model']:12} -> {h.get('name','')[:70]} 价{h.get('price')}")
        results[site] = {
            "host": host, "total": len(models), "hits": hits,
            "hit_models": hit_list,
        }
        print()
    with open("data/vtex_hitrate.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/vtex_hitrate.json")


if __name__ == "__main__":
    main()