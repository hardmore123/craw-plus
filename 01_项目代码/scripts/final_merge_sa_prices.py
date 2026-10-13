# -*- coding: utf-8 -*-
"""最终合并：Hiraoka + efe/lacuracao + VTEX 在售 → 南美价格监控最终表。

统一格式（地区/国家/零售站/网站/品牌/品牌code/型号/尺寸/价格/币种/原价/
库存/sku/URL/状态/评价数/抓取时间）。
币种按国家映射：秘鲁 PEN / 厄瓜多尔 USD / 哥伦比亚 COP / 玻利维亚 BOB。
"""
from __future__ import annotations

import csv
import glob
import io
import os
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

COLS = ["地区", "国家", "零售站", "网站", "品牌", "品牌code", "型号", "尺寸",
        "价格", "币种", "原价", "库存", "sku", "URL", "状态", "评价数", "抓取时间"]
CUR = {"秘鲁": "PEN", "厄瓜多尔": "USD", "哥伦比亚": "COP", "玻利维亚": "BOB", "智利": "CLP"}
WEB = {
    "metro_pe": "Metro", "carsa_pe": "Carsa", "credivargas_pe": "Credivargas",
    "oechsle_pe": "Oechsle", "plazavea_pe": "PlazaVea", "estilos_pe": "Estilos",
    "japon_ec": "Japon EC", "orvehogar_ec": "Orvehogar EC", "marcimex_ec": "Marcimex EC",
    "comandato_ec": "Comandato EC", "hiraoka_pe": "Hiraoka", "efe_pe": "Efe",
    "lacuracao_pe": "La Curacao",
}
CCISO = {"PE": "秘鲁", "EC": "厄瓜多尔", "CO": "哥伦比亚", "BO": "玻利维亚", "GT": "危地马拉"}


def cl(r, c):
    return r.get(c, "") if r else ""


def main() -> None:
    rows_all = []

    # 1) Hiraoka 全量（已抓）
    if os.path.exists("Hiraoka_全量_v2.csv"):
        with open("Hiraoka_全量_v2.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                nr = {c: cl(r, c) for c in COLS}
                nr["地区"] = "南美"
                nr["国家"] = "秘鲁"
                nr["币种"] = "PEN"
                rows_all.append(nr)
    print("Hiraoka:", sum(1 for r in rows_all if r.get("零售站", "").startswith("hiraoka")))

    # 2) efe / lacuracao 最新批次（秘鲁）
    for site, web in (("efe_pe", "Efe"), ("lacuracao_pe", "La Curacao")):
        files = sorted(glob.glob("data/秘鲁/价格监控_秘鲁_20260919_*.csv"), reverse=True)
        found = None
        for f in files:
            with open(f, encoding="utf-8-sig", newline="") as fh:
                for r in csv.DictReader(fh):
                    if cl(r, "零售站") == site:
                        found = {c: cl(r, c) for c in COLS}
                        break
            if found:
                break
        if found:
            found["地区"] = "南美"
            found["国家"] = "秘鲁"
            found["币种"] = "PEN"
            rows_all.append(found)
            print(f"{site}: {found['型号']} {found['价格']}")
        else:
            print(f"{site}: 未找到最新批次")

    # 3) VTEX 全站在售（vtex_all_stock.csv）
    if os.path.exists("data/vtex_all_stock.csv"):
        with open("data/vtex_all_stock.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                iso = str(r.get("国家", "") or "").upper()
                cc = CCISO.get(iso, iso)
                site = r.get("零售站") or ""
                nr = {
                    "地区": "南美", "国家": cc,
                    "零售站": site, "网站": WEB.get(site, site),
                    "品牌": cl(r, "品牌"), "品牌code": cl(r, "品牌code"),
                    "型号": cl(r, "型号"), "尺寸": "",
                    "价格": cl(r, "价格"), "币种": CUR.get(cc, ""),
                    "原价": "", "库存": "", "sku": "",
                    "URL": cl(r, "URL"), "状态": "in_stock", "评价数": "0",
                    "抓取时间": "2026-09-19 00:55:00",
                }
                rows_all.append(nr)
    print("VTEX 并入:", sum(1 for r in rows_all if r.get("状态") == "in_stock"))

    # 4) 旧的 24 条 VTEX 汇总补缺
    if os.path.exists("data/价格_VTEX_南美汇总.csv"):
        existing = {(r.get("零售站"), r.get("型号")) for r in rows_all}
        with open("data/价格_VTEX_南美汇总.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                site = r.get("零售站") or ""
                if (site, r.get("型号")) in existing:
                    continue
                cc = r.get("国家") or ""
                nr = {"地区": "南美", "国家": cc, "零售站": site,
                      "网站": WEB.get(site, site),
                      "品牌": cl(r, "品牌"), "品牌code": cl(r, "品牌code"),
                      "型号": cl(r, "型号"), "尺寸": "", "价格": cl(r, "价格"),
                      "币种": CUR.get(cc, ""), "原价": "", "库存": "", "sku": "",
                      "URL": cl(r, "URL"), "状态": "in_stock", "评价数": "0",
                      "抓取时间": "2026-09-18 19:40:00"}
                rows_all.append(nr)

    # 去重：按 (零售站, 型号) 有价格优先
    merged = {}
    for r in rows_all:
        key = (r.get("零售站", ""), r.get("型号", ""))
        cur = merged.get(key)
        if cur is None:
            merged[key] = r
        elif cl(r, "价格").strip() and not cl(cur, "价格").strip():
            merged[key] = r
    final = list(merged.values())

    out = "data/南美价格监控_20260919_最终.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in final:
            w.writerow({c: cl(r, c) for c in COLS})
    print(f"\n[OUT] {out} rows={len(final)}")
    print("有价格:", sum(1 for r in final if cl(r, "价格").strip()))
    print("按国家:", dict(Counter(r.get("国家", "") for r in final)))
    print("按站:", dict(Counter(r.get("零售站", "") for r in final)))
    print("\n有价格记录样例:")
    for r in final:
        if cl(r, "价格").strip():
            print(f"  {r['零售站']:<18}{r['型号']:<14}{r['价格']:<9}{r['币种']:<5}{r['抓取时间']}")


if __name__ == "__main__":
    main()