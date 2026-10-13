# -*- coding: utf-8 -*-
"""Magento 平台批量探测：验证每站 /catalogsearch/result/?q=<短码> 搜索能否命中在售商品。

输出每站的：
  - search_url 可达性
  - 搜索某 SPEC 短码是否返回含该型号的商品（列表/直达PDP）
  - 抽 1 个在售商品的 PDP JSON-LD（价格/评价）
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
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

# (site, host, region, probe_model)
MAGENTO_SITES = [
    ("hiraoka_pe", "hiraoka.com.pe", "pe", "65UR8SG"),
    ("lacuracao_pe", "www.lacuracao.pe", "pe", "55UR8SG"),
    ("efe_pe", "www.efe.com.pe", "pe", "55UR8SG"),
    ("sodimac_pe", "www.sodimac.com.pe", "pe", "65UR8SG"),   # CF?
    ("falabella_pe", "www.falabella.com.pe", "pe", "55UR8SG"),  # CF?
    ("marcimex_ec", "www.marcimex.com", "ec", "55Q6QV"),     # VTEX 但试
    ("artefacta_ec", "www.artefacta.com", "ec", "55Q6QV"),
    ("espana_ec", "almacenesespana.ec", "ec", "55Q6QV"),
    ("coral_ec", "coralhipermercados.com", "ec", "55Q6QV"),
    ("falabella_co", "www.falabella.com.co", "co", "50QNED70BSA"),
    ("falabella_cl", "www.falabella.com", "cl", "65C6K"),
    ("panafoto_pa", "panafoto.com", "pa", ""),
    ("evision_pa", "www.evisionstore.com", "pa", ""),
    ("raenco_pa", "www.raenco.com", "pa", ""),
    ("unicomer_gt", "www.lacuracaonline.com", "gt", ""),
]

REGION_MODELS = {
    "pe": "data/型号清单_短码/models_秘鲁_short.csv",
    "ec": "data/型号清单_短码/models_厄瓜多尔_short.csv",
    "co": "data/型号清单_短码/models_哥伦比亚_short.csv",
    "cl": "data/型号清单_短码/models_智利_short.csv",
    "bo": "data/型号清单_短码/models_玻利维亚_short.csv",
}


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def load_spec(region: str) -> list[dict]:
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


def probe_search(host: str, model: str) -> dict:
    url = f"https://{host}/catalogsearch/result/?q={model}"
    try:
        r = requests.get(url, proxies=PROXY, headers=HEADERS, timeout=20,
                         verify=False, allow_redirects=True)
        html = r.text or ""
    except Exception as e:
        return {"http": 0, "err": f"{type(e).__name__}: {e}"}
    low = html.lower()
    # 是否命中目标型号
    want = norm(model)
    ids_in = len(re.findall(r'class="[^"]*product-item[^"]*"', html, re.I))
    titles = re.findall(r'<a[^>]*class="[^"]*product-item-link[^"]*"[^>]*>\s*([^<]{5,200})<', html, re.I)
    hit = any(want in norm(t) for t in titles)
    # JSON-LD
    ld_price = None
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        s = m.group(1)
        if '"Product"' in s or '"ItemList"' in s:
            try:
                d = json.loads(s)
                if d.get("@type") == "Product":
                    off = d.get("offers")
                    if isinstance(off, list):
                        off = off[0]
                    ld_price = (off or {}).get("price")
                    break
            except Exception:
                pass
    return {"http": r.status_code, "cards": len(titles), "hit_model": hit,
            "ld_price": ld_price, "final_url": r.url[:100],
            "cf": "challenge-platform" in low or "just a moment" in low}


def main() -> None:
    results = []
    for site, host, region, probe_model in MAGENTO_SITES:
        spec = load_spec(region)
        if not probe_model and spec:
            probe_model = spec[0]["orig"]
        print(f"=== {site} ({host}) probe={probe_model} ===")
        if probe_model:
            res = probe_search(host, probe_model)
            print(f"  search: http={res.get('http')} cards={res.get('cards')} "
                  f"hit={res.get('hit_model')} cf={res.get('cf')}")
            # 若搜索失败试分类页
            if res.get("http") in (0, 403) or res.get("cards", 0) == 0:
                cat_hit = probe_category(host)
                print(f"  分类页: {cat_hit}")
            results.append({"site": site, "host": host, "region": region,
                            **res})
        else:
            results.append({"site": site, "host": host, "region": region,
                            "note": "无探模特型"})
        print()
    with open("data/_magento_probe.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("[OUT] data/_magento_probe.json")


def probe_category(host: str) -> dict:
    """试分类页 /televisores 之类的。"""
    for path in ["/televisores", "/televisores/televisores/smart-tv", "/tv"]:
        try:
            r = requests.get(f"https://{host}{path}", proxies=PROXY,
                             headers=HEADERS, timeout=18, verify=False)
            if r.status_code == 200:
                cards = len(re.findall(r'class="[^"]*product-item[^"]*"', r.text, re.I))
                if cards:
                    return {"path": path, "cards": cards}
        except Exception:
            continue
    return {"path": "", "cards": 0}


if __name__ == "__main__":
    main()