# -*- coding: utf-8 -*-
"""第二部分收尾：巴拿马/危地马拉 TV 在售型号清单 + 并入最终交付。"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

TV_HINTS = ("televisor", " tv", "qled", "oled", "uled", "smart tv", "nano",
            "neo qled", "mini led", "bravia", "aquos")
EXCLUDE = ("soporte", "rack ", "cable", "antena", "cafetera", "licuadora",
           "microonda", "parrilla", "freidora", "extractor", "horno", "adorno",
           "camara", "control remoto", "funda", "hdmi", "barras", "cargador",
           "protector", "toma tv", "tecnolog", "combo", "juego", "accesorio",
           "lavadora", "refrig", "lavavajilla", "cocina", "aspiradora", "plancha")
HZ_NOISE = re.compile(r"^\d{2,3}HZ$", re.I)
PA_SITES = ("panafoto_pa", "raenco_pa", "evision_pa", "multimax_pa", "rodelag_pa")
GT_SITES = ("elektra_gt", "unicomer_gt", "max_gt", "tecnofacil_gt")


def is_tv(title: str) -> bool:
    low = title.lower()
    if not any(k in low for k in TV_HINTS):
        return False
    if any(x in low for x in EXCLUDE):
        return False
    return True


def model_of(title: str) -> str:
    toks = re.split(r"[^A-Z0-9]+", title.upper())
    for tok in toks:
        if re.fullmatch(r"\d{1,4}[A-Z]{1,3}[A-Z0-9]{0,6}", tok) and len(tok) >= 4:
            if HZ_NOISE.fullmatch(tok):
                continue
            return tok
    m = re.findall(r"\b(\d{1,4}[A-Z][A-Z0-9]{1,8})\b", title.upper())
    return m[-1] if m else ""


def main() -> int:
    pa = []
    gt = []

    # 1) Magento 全目录（panafoto/raenco/evision 等）
    if os.path.exists("data/在售全量/Magento全量价格_合并.csv"):
        with open("data/在售全量/Magento全量价格_合并.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                site = r.get("零售站", "")
                p = (r.get("价格") or "").strip()
                if not p or (site not in PA_SITES and site not in GT_SITES):
                    continue
                t = (r.get("商品名") or "").replace("&aacute;", "a").replace("&eacute;", "e")
                t = re.sub(r"&[a-zA-Z0-9#]+;", " ", t)
                t = re.sub(r"\s+", " ", t).strip()
                if not is_tv(t):
                    continue
                row = {"site": site, "title": t[:90], "price": p,
                       "currency": r.get("币种", "")}
                if site in PA_SITES:
                    pa.append(row)
                else:
                    gt.append(row)

    # 2) elektra_gt（VTEX 全目录）
    f_el = "data/在售全量/elektra_gt_catalog_v2.csv"
    if os.path.exists(f_el):
        with open(f_el, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                p = (r.get("price") or "").strip()
                t = r.get("name", "")
                if not p or not is_tv(t):
                    continue
                gt.append({"site": "elektra_gt", "title": t[:90], "price": p,
                           "currency": "GTQ"})

    # 提取型号 + 去重
    seen = set()
    out_rows = []
    for group in (pa, gt):
        for row in group:
            row["model"] = model_of(row["title"])
            if not row["model"]:
                continue
            key = (row["site"], row["model"])
            if key in seen:
                continue
            seen.add(key)
            out_rows.append(row)

    os.makedirs("data/型号清单_短码", exist_ok=True)
    for label, rows in (("巴拿马", [r for r in out_rows if r["site"] in PA_SITES]),
                        ("危地马拉", [r for r in out_rows if r["site"] in GT_SITES])):
        fname = f"data/型号清单_短码/models_{'巴拿马' if '巴拿马' in label else '危地马拉'}_short.csv"
        with open(fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["brand_name", "model_raw"])
            w.writeheader()
            for r in rows:
                w.writerow({"brand_name": "", "model_raw": r["model"]})
        print(f"[{label}] 在售电视 {len(rows)} 条 → {fname}")
        for r in rows:
            print(f"    {r['site']:<14}{r['model']:<20}{r['price']:>10} {r['currency']}  {r['title'][:42]}")

    # 写合并的 PA/GT 在售价格
    os.makedirs("data/在售全量", exist_ok=True)
    out_csv = "data/在售全量/巴拿马危地马拉_在售电视.csv"
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site", "model", "price", "currency", "title"])
        w.writeheader()
        for r in out_rows:
            w.writerow({"site": r["site"], "model": r["model"], "price": r["price"],
                        "currency": r["currency"], "title": r["title"]})
    print(f"\n[OUT] {out_csv} rows={len(out_rows)}")
    return 0


if __name__ == "__main__":
    main()