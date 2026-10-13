# -*- coding: utf-8 -*-
"""最终全量合并（完整版）：Hiraoka全量 + Magento新批次 + VTEX全量在售 → 全量交付表。

- Hiraoka 全量：此前 56 型号全量抓取（含 18 有价 + 36 no_item）
- Magento 新批次：hiraoka 在售2 + efe/lacuracao 各1（max=50，含抓取时间）
- VTEX 全量在售：7 站 23 条（目录 API，含抓取时间）
去重：按 (零售站, 型号)，有价格优先、抓取时间新者优先。
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
        "价格", "币种", "原价", "库存", "sku", "URL", "状态", "评价数",
        "抓取时间", "来源"]


def cl(r, c):
    return r.get(c, "") if r else ""


def main() -> None:
    rows: list[dict] = []

    # ---- 1) Hiraoka 全量（此前抓的 54 行，含 no_item）----
    if os.path.exists("Hiraoka_全量_v2.csv"):
        with open("Hiraoka_全量_v2.csv", encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                nr = {c: cl(r, c) for c in COLS}
                nr["地区"] = "南美"
                nr["国家"] = "秘鲁"
                nr["网站"] = "Hiraoka"
                nr["币种"] = "PEN"
                nr["来源"] = "Hiraoka全量(max50)"
                rows.append(nr)
    print(f"Hiraoka 全量 54 行并入（含 no_item）")

    # ---- 2) Magento 最新全量批次（hiraoka在售2 / efe / lacuracao）----
    for f in sorted(glob.glob("data/秘鲁/全量/价格监控_*.csv"), reverse=True):
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                site = cl(r, "零售站")
                if not site:
                    continue
                nr = {c: cl(r, c) for c in COLS}
                nr["地区"] = "南美"
                nr["国家"] = "秘鲁"
                nr["币种"] = "PEN" if cl(r, "币种") in ("", "MXN") else cl(r, "币种")
                nr["来源"] = "Magento全量(max50)"
                rows.append(nr)

    # ---- 3) VTEX 全量在售（目录 API）----
    vtex_path = "data/价格_VTEX_全量_20260919.csv"
    if os.path.exists(vtex_path):
        with open(vtex_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                nr = {c: cl(r, c) for c in COLS}
                nr["地区"] = "南美"
                nr["来源"] = "VTEX目录API"
                rows.append(nr)
    print(f"VTEX 全量在售 并入 {sum(1 for r in rows if cl(r,'来源')=='VTEX目录API')} 条")

    # ---- 去重：按 (零售站, 型号)，有价优先、更新时间优先 ----
    merged: dict[tuple, dict] = {}
    for r in rows:
        key = (cl(r, "零售站"), cl(r, "国家"), cl(r, "型号"))
        cur = merged.get(key)
        if cur is None:
            merged[key] = r
            continue
        # 有价优先
        r_has_p = bool(cl(r, "价格").strip())
        c_has_p = bool(cl(cur, "价格").strip())
        if r_has_p and not c_has_p:
            merged[key] = r
        elif r_has_p == c_has_p and cl(r, "抓取时间") > cl(cur, "抓取时间"):
            merged[key] = r
    final = list(merged.values())
    # 按 国家/零售站/型号 排序
    final.sort(key=lambda r: (cl(r, "国家"), cl(r, "零售站"), cl(r, "型号")))

    priced = [r for r in final if cl(r, "价格").strip()]
    no_item = [r for r in final if cl(r, "状态") == "no_item"]

    out = "data/南美价格监控_全量_20260919.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in final:
            w.writerow({c: cl(r, c) for c in COLS})
    with open("data/南美价格监控_全量_有价_20260919.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in priced:
            w.writerow({c: cl(r, c) for c in COLS})

    print(f"\n[OUT] {out} rows={len(final)}")
    print(f"[OUT] data/南美价格监控_全量_有价_20260919.csv rows={len(priced)}")
    print(f"有价格: {len(priced)} | no_item: {len(no_item)} | 其他: {len(final)-len(priced)-len(no_item)}")
    print(f"\n按国家(有价): {dict(Counter(cl(r,'国家') for r in priced))}")
    print(f"按站(有价): {dict(Counter(cl(r,'零售站') for r in priced))}")
    print(f"\n=== 有价明细 ===")
    for r in priced:
        print(f"  {cl(r,'零售站'):<18}{cl(r,'型号'):<16}{cl(r,'价格'):<9}{cl(r,'币种'):<5}{cl(r,'抓取时间')}")


if __name__ == "__main__":
    main()