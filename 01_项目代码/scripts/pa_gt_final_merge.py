# -*- coding: utf-8 -*-
"""第二部分交付：把巴拿马/危地马拉在售电视整理进最终交付表（严格过滤配件/家电）。

先精筛（标题含 TV 关键词、排除家电/配件），再提取型号，写入：
  - data/在售全量/巴拿马危地马拉_在售电视_最终.csv
  - 追加到 data/南美欧洲价格全量_最终交付.csv
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

TV_IN = ("televisor", " tv ", "tv ", "qled", "oled", "uled", "smart tv", "nano",
         "neo qled", "mini", "bravia", "aquos")
EXCLUDE = ("soporte", "rack", "cable", "antena", "cafetera", "licuadora", "microond",
           "parrilla", "freidora", "extractor", "horno", "adorno", "camara",
           "control remoto", "funda", "hdmi", "barras", "cargador", "protector",
           "toma tv", "tecnolog", "combo", "juego", "accesorio", "lavadora",
           "refrig", "lavavajilla", "cocina", "aspiradora", "plancha", "termo")
HZ = re.compile(r"^\d{2,3}HZ$", re.I)

PA = ("panafoto_pa", "raenco_pa", "evision_pa", "multimax_pa", "rodelag_pa")
GT = ("elektra_gt", "unicomer_gt", "max_gt", "tecnofacil_gt")


def is_tv(t: str) -> bool:
    low = t.lower()
    if not any(k in low for k in TV_IN):
        return False
    return not any(x in low for x in EXCLUDE)


def model_of(t: str) -> str:
    """从标题提取真实TV型号（兼容 QN65Q7FAAPXPA / UN55U8000FPXPA / 43S5K / 43LM6370PSB）。"""
    up = t.upper()
    # 1) 优先：标题里显式的型号 token（含品牌字头 QN/UN/QE/OLED/65P/55/32/43 等）
    toks = re.split(r"[^A-Z0-9]+", up)
    for tok in toks:
        if len(tok) < 5 or HZ.fullmatch(tok):
            continue
        # 三星 QN/UN/RN 系：QN65Q7FAAPXPA / UN40F6000FPXPA
        if re.fullmatch(r"(?:QN|UN|RN|UA|MR|AU|QE)[A-Z0-9]{6,14}", tok):
            return tok
    for tok in toks:
        if len(tok) < 4 or HZ.fullmatch(tok):
            continue
        # 尺寸+系列：43S5K / 65P6K / 43LM6370PSB / 55UA8000 / 50UA8000
        if re.fullmatch(r"\d{2,3}[A-Z][A-Z0-9]{2,9}", tok):
            return tok
    # 2) 兜底：取最后一段"数字+字母"token
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{2,9})\b", up)
    return m[-1] if m else ""


def main() -> None:
    # 1) Magento 全目录
    rows = []
    if os.path.exists("data/在售全量/Magento全量价格_合并.csv"):
        with open("data/在售全量/Magento全量价格_合并.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                site = r.get("零售站", "")
                p = (r.get("价格") or "").strip()
                if not p or site not in PA + GT:
                    continue
                t = re.sub(r"&[a-zA-Z0-9#]+;", " ", r.get("商品名") or "")
                t = re.sub(r"\s+", " ", t).strip()
                if not is_tv(t):
                    continue
                # 具体化站
                rows.append({"site": site, "title": t[:90], "price": p,
                             "currency": r.get("币种", "")})
    # 2) VTEX elektra_gt
    f_el = "data/在售全量/elektra_gt_catalog_v2.csv"
    if os.path.exists(f_el):
        with open(f_el, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                p = (r.get("price") or "").strip()
                t = (r.get("name") or "").strip()
                if not p or not is_tv(t):
                    continue
                rows.append({"site": "elektra_gt", "title": t[:90], "price": p,
                             "currency": "GTQ"})

    # 型号提取 + 去重
    seen = set()
    kept = []
    for r in rows:
        r["model"] = model_of(r["title"])
        if not r["model"] or len(r["model"]) < 4:
            continue
        key = (r["site"], r["model"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)

    # 输出巴拿马/危地马拉在售电视
    out1 = "data/在售全量/巴拿马危地马拉_在售电视_最终.csv"
    with open(out1, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "model", "title", "price", "currency"])
        w.writeheader()
        for r in kept:
            w.writerow(r)
    print(f"[OUT] {out1} rows={len(kept)}")
    for r in kept:
        print(f"  {r['site']:<14}{r['model']:<20}{r['price']:>10} {r['currency']}  {r['title'][:45]}")

    # 追加到主交付表
    main_csv = "data/南美欧洲价格全量_最终交付.csv"
    if os.path.exists(main_csv):
        with open(main_csv, encoding="utf-8-sig", newline="") as f:
            main_rows = list(csv.DictReader(f))
        cols = list(main_rows[0].keys())
        country_of = {"pa": "巴拿马", "gt": "危地马拉"}
        added = 0
        for r in kept:
            cc = country_of.get(r["site"].split("_")[1], "")
            # 避免重复
            if any(m["零售站"] == r["site"] and m["型号"] == r["model"] for m in main_rows):
                continue
            main_rows.append({
                "国家": cc, "零售站": r["site"],
                "网站": {"panafoto_pa": "Panafoto", "raenco_pa": "Raenco",
                         "evision_pa": "Evision", "multimax_pa": "Multimax",
                         "rodelag_pa": "Rodelag", "elektra_gt": "Elektra"}.get(r["site"], r["site"]),
                "品牌": "", "商品名": r["title"], "型号": r["model"], "尺寸": "",
                "价格": r["price"], "币种": r["currency"], "原价": "", "库存": "",
                "sku": "", "URL": "", "状态": "ok", "评价数": "0",
                "抓取时间": "2026-09-19 16:30:00", "来源": "全目录抓取(PA/GT)",
            })
            added += 1
        with open(main_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(main_rows)
        print(f"\n[OUT] 已追加 {added} 条巴拿马/危地马拉在售 → {main_csv}（总行{len(main_rows)}）")

    # 同步有价表
    price_csv = "data/南美欧洲价格全量_有价_最终交付.csv"
    if os.path.exists(price_csv):
        with open(price_csv, encoding="utf-8-sig", newline="") as f:
            priced_rows = list(csv.DictReader(f))
        cols = list(priced_rows[0].keys())
        existing = {(m["零售站"], m["型号"]) for m in priced_rows}
        added = 0
        for r in kept:
            key = (r["site"], r["model"])
            if key in existing:
                continue
            cc = country_of.get(r["site"].split("_")[1], "")
            priced_rows.append({c: {
                "国家": cc, "零售站": r["site"], "网站": r["site"], "品牌": "",
                "商品名": r["title"], "型号": r["model"], "尺寸": "", "价格": r["price"],
                "币种": r["currency"], "原价": "", "库存": "", "sku": "", "URL": "",
                "状态": "ok", "评价数": "0", "抓取时间": "2026-09-19 16:30:00",
                "来源": "全站全量(PA/GT)",
            }.get(c, "") for c in cols})
            added += 1
        with open(price_csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(priced_rows)
        print(f"[OUT] 已追加到有价表 {added} 条（总{len(priced_rows)}）")


if __name__ == "__main__":
    main()