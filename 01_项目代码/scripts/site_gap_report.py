# -*- coding: utf-8 -*-
"""详细盘点：52 站探索/抓取状态 + 可解决问题归类，输出 CSV + 汇总。"""
from __future__ import annotations

import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

REGION_SPEC = {"pe": 56, "ec": 21, "co": 17, "cl": 37, "bo": 4, "pa": 0, "gt": 0}
SITE_REGION = {
    "hiraoka_pe": "pe", "lacuracao_pe": "pe", "efe_pe": "pe", "sodimac_pe": "pe",
    "falabella_pe": "pe", "oechsle_pe": "pe", "plazavea_pe": "pe", "estilos_pe": "pe",
    "metro_pe": "pe", "carsa_pe": "pe", "credivargas_pe": "pe", "tottus_pe": "pe",
    "ripley_pe": "pe", "mercadolibre_pe": "pe",
    "japon_ec": "ec", "orvehogar_ec": "ec", "marcimex_ec": "ec", "comandato_ec": "ec",
    "espana_ec": "ec", "coral_ec": "ec", "artefacta_ec": "ec", "cresa_ec": "ec",
    "jaher_ec": "ec", "sukasa_ec": "ec", "todohogar_ec": "ec", "ferrisariato_ec": "ec",
    "megamaxi_ec": "ec", "laganga_ec": "ec",
    "alkosto_co": "co", "exito_co": "co", "falabella_co": "co", "jumbo_co": "co",
    "olimpica_co": "co",
    "hites_cl": "cl", "abc_cl": "cl", "lider_cl": "cl", "paris_cl": "cl",
    "ripley_cl": "cl", "falabella_cl": "cl", "mercadolibre_cl": "cl",
    "multicenter_bo": "bo", "multicenterplus_bo": "bo", "dismac_bo": "bo",
    "panafoto_pa": "pa", "evision_pa": "pa", "multimax_pa": "pa", "rodelag_pa": "pa",
    "raenco_pa": "pa", "max_gt": "gt", "tecnofacil_gt": "gt", "unicomer_gt": "gt",
    "elektra_gt": "gt",
}


def main() -> None:
    summary = json.load(open("data/explore/_summary.json", encoding="utf-8"))
    price_rows = []
    if os.path.exists("data/南美价格监控_全量_20260919_最终.csv"):
        with open("data/南美价格监控_全量_20260919_最终.csv", encoding="utf-8-sig") as f:
            price_rows = list(csv.DictReader(f))
    price_by_site = defaultdict(int)
    for r in price_rows:
        if (r.get("价格") or "").strip():
            price_by_site[r.get("零售站", "")] += 1

    rows = []
    for s in sorted(summary, key=lambda x: x["site"]):
        site = s["site"]
        items = s.get("items", 0)
        http = s.get("http", 0)
        platform = s.get("platform", "")
        region = SITE_REGION.get(site, "?")
        n_spec = REGION_SPEC.get(region, 0)
        got = price_by_site.get(site, 0)
        if got > 0:
            issue = f"OK 已抓{got}"
        elif items > 0 and n_spec > 0:
            issue = f"可解: 在售{items} 有SPEC{n_spec} 匹配0"
        elif items > 0:
            issue = f"有在售{items} 但region={region}无SPEC"
        elif http == 200:
            issue = "可达但未挖到商品(JS/反爬/无电视)"
        else:
            issue = f"不可达 http={http}"
        rows.append({"站点": site, "region": region, "平台": platform, "在售": items,
                     "SPEC": n_spec, "已抓": got, "问题": issue})

    out = "data/逐站问题清单.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[OUT] {out} rows={len(rows)}")
    print()
    for r in rows:
        print(f"{r['站点']:<18}{r['region']:<4}{r['平台']:<12}{r['在售']:<5}"
              f"{r['SPEC']:<5}{r['已抓']:<4}{r['问题']}")

    print("\n=== 可解缺口 ===")
    solvable = [r for r in rows if r["已抓"] == 0 and r["在售"] > 0 and r["SPEC"] > 0]
    print(f"1) 有在售+有SPEC 但匹配失败: {len(solvable)} 站")
    for r in solvable:
        print(f"   {r['站点']} ({r['平台']}, 在售{r['在售']})")
    nospec = [r for r in rows if r["已抓"] == 0 and r["在售"] > 0 and r["SPEC"] == 0]
    print(f"\n2) 有在售但无本国 SPEC 型号清单: {len(nospec)} 站（可抓在售全目录）")
    for r in nospec:
        print(f"    {r['站点']} ({r['平台']}, 在售{r['在售']})")
    js = [r for r in rows if r["已抓"] == 0 and "未挖到" in r["问题"] and r["平台"] == "shopify"]
    print(f"\n3) Shopify/JS 渲染（需浏览器）: {len(js)} 站")


if __name__ == "__main__":
    main()