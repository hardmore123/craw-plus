# -*- coding: utf-8 -*-
"""最终统一交付表：合并 VTEX 全量 + Magento 全量 + 引擎已抓，输出总表+问题汇总。"""
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

COLS = ["国家", "零售站", "网站", "品牌", "商品名", "型号", "尺寸", "价格",
        "币种", "原价", "库存", "sku", "URL", "状态", "评价数", "抓取时间", "来源"]


def s(v):
    return "" if v is None else str(v)


def main() -> None:
    rows: list[dict] = []

    # 1) VTEX 全量在售（含补抓）——直接读各 _catalog_v2.csv 合并
    vtex_meta = {
        "oechsle_pe": ("秘鲁", "PEN", "Oechsle"), "plazavea_pe": ("秘鲁", "PEN", "PlazaVea"),
        "estilos_pe": ("秘鲁", "PEN", "Estilos"), "metro_pe": ("秘鲁", "PEN", "Metro"),
        "carsa_pe": ("秘鲁", "PEN", "Carsa"), "credivargas_pe": ("秘鲁", "PEN", "Credivargas"),
        "japon_ec": ("厄瓜多尔", "USD", "Japon EC"), "orvehogar_ec": ("厄瓜多尔", "USD", "Orvehogar EC"),
        "marcimex_ec": ("厄瓜多尔", "USD", "Marcimex EC"), "comandato_ec": ("厄瓜多尔", "USD", "Comandato EC"),
        "exito_co": ("哥伦比亚", "COP", "Exito"), "jumbo_co": ("哥伦比亚", "COP", "Jumbo"),
        "multicenter_bo": ("玻利维亚", "BOB", "Multicenter"), "elektra_gt": ("危地马拉", "GTQ", "Elektra"),
    }
    os.makedirs("data/在售全量", exist_ok=True)
    vtex_count = 0
    for site, (cc, cur, web) in vtex_meta.items():
        f = f"data/在售全量/{site}_catalog_v2.csv"
        if not os.path.exists(f):
            continue
        with open(f, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                p = s(r.get("price")).strip()
                if not p:
                    continue
                rows.append({
                    "国家": cc, "零售站": site, "网站": web,
                    "品牌": r.get("brand", ""), "商品名": s(r.get("name"))[:120],
                    "型号": r.get("model", ""), "尺寸": "",
                    "价格": p, "币种": cur, "原价": "", "库存": "",
                    "sku": s(r.get("sku_id")), "URL": s(r.get("url")),
                    "状态": "ok", "评价数": "0",
                    "抓取时间": "2026-09-19 15:00:00",
                    "来源": "VTEX全量目录",
                })
                vtex_count += 1
    print(f"VTEX 全量: {vtex_count} 条")

    # 2) Magento 全量（coral/panafoto/raenco）
    magento_file = "data/在售全量/Magento全量价格_合并.csv"
    mag_count = 0
    if os.path.exists(magento_file):
        with open(magento_file, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                p = s(r.get("价格")).strip()
                rows.append({
                    "国家": r.get("国家", ""), "零售站": r.get("零售站", ""),
                    "网站": r.get("零售站", ""), "品牌": "", "商品名": r.get("商品名", ""),
                    "型号": "", "尺寸": "", "价格": p, "币种": r.get("币种", ""),
                    "原价": "", "库存": "", "sku": "", "URL": s(r.get("URL")),
                    "状态": "ok" if p else "no_price", "评价数": "0",
                    "抓取时间": r.get("抓取时间", ""), "来源": "Magento全目录",
                })
                mag_count += 1
    print(f"Magento 全量: {mag_count} 条")

    # 3) 引擎已抓（Hiraoka_全量_v2.csv + 秘鲁全量批次 efe/lacuracao）
    if os.path.exists("Hiraoka_全量_v2.csv"):
        with open("Hiraoka_全量_v2.csv", encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                rows.append({
                    "国家": "秘鲁", "零售站": "hiraoka_pe", "网站": "Hiraoka",
                    "品牌": r.get("品牌", ""), "商品名": "", "型号": r.get("型号", ""),
                    "尺寸": r.get("尺寸", ""), "价格": s(r.get("价格")).strip(),
                    "币种": "PEN", "原价": r.get("原价", ""), "库存": r.get("库存", ""),
                    "sku": r.get("sku", ""), "URL": r.get("URL", ""),
                    "状态": r.get("状态", ""), "评价数": r.get("评价数", "0"),
                    "抓取时间": r.get("抓取时间", ""), "来源": "Magento引擎",
                })
    # efe/lacuracao 全量批次（取最新）
    for site, web in (("efe_pe", "Efe"), ("lacuracao_pe", "La Curacao")):
        import glob
        newest = None
        for f in sorted(glob.glob("data/秘鲁/全量/价格监控_*.csv"), reverse=True):
            with open(f, encoding="utf-8-sig", newline="") as fh:
                tr = list(csv.DictReader(fh))
            if any(s(r.get("零售站")) == site for r in tr):
                newest = tr
                break
        if newest:
            for r in newest:
                if s(r.get("零售站")) != site:
                    continue
                rows.append({
                    "国家": "秘鲁", "零售站": site, "网站": web,
                    "品牌": r.get("品牌", ""), "商品名": "", "型号": r.get("型号", ""),
                    "尺寸": r.get("尺寸", ""), "价格": s(r.get("价格")).strip(),
                    "币种": "PEN", "原价": r.get("原价", ""), "库存": r.get("库存", ""),
                    "sku": r.get("sku", ""), "URL": r.get("URL", ""),
                    "状态": r.get("状态", ""), "评价数": r.get("评价数", "0"),
                    "抓取时间": r.get("抓取时间", ""), "来源": "Magento引擎",
                })
    print(f"引擎已抓并入完成")

    # ---- 去重（零售站+型号+URL 非空时） ----
    seen = set()
    dedup = []
    for r in rows:
        key = (r["零售站"], r["型号"], r["商品名"][:40], r["URL"][:40])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)

    out = "data/南美欧洲价格全量_最终交付.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in dedup:
            w.writerow({c: r[c] for c in COLS})
    printed = [r for r in dedup if r["价格"].strip()]
    no_item = [r for r in dedup if r["状态"] == "no_item" or not r["价格"].strip()]
    print(f"\n[OUT] {out}")
    print(f"去重后总行: {len(dedup)} | 有价 {len(printed)} | 无价/no_item {len(no_item)}")
    print(f"按站(有价): {dict(Counter(r['零售站'] for r in printed))}")
    print(f"按国家(有价): {dict(Counter(r['国家'] for r in printed))}")

    # 有价子表
    out2 = "data/南美欧洲价格全量_有价_最终交付.csv"
    with open(out2, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in printed:
            w.writerow({c: r[c] for c in COLS})
    print(f"[OUT] {out2} rows={len(printed)}")


if __name__ == "__main__":
    main()