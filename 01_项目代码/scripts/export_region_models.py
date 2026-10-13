# -*- coding: utf-8 -*-
"""按区域导出零售全量用的型号清单（来源：主库官网 SPEC 结果 spec_series）。

规则：
  - 北美/拉美：本国有官网 SPEC（spec_series.brand = <品牌>_<国家码>）→ 用本国型号；
  - 欧洲各国：统一用欧洲那一份 SPEC（de/fr/it/uk… 同品牌型号并集）。
    欧洲电视型号全区基本通用（43PUS7200_12 这类后缀差异由匹配层主干规则兜住），
    这是欧洲唯一可用的型号来源；
  - 北美/南美各国仅用本国 SPEC（各国型号码差异大，不做跨国回落）；
  - 危地马拉/巴拿马没有任何官网 SPEC：用拉美各国同品牌型号并集兜底。
产出：data/<区域中文名>/SPEC_型号汇总_<code>_<YYYYMMDD>.csv
      列 brand_code, brand_name, model_raw, search_query, source
      crawl_ca_retail.py 不给 --models-csv 时按区域自动取最新一份。

用法：py -3.12 scripts/export_region_models.py [--region de --region uk] [--db data/overseas.db]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from overseas.regions_config import REGIONS  # noqa: E402

BRANDS = [("hisense", "Hisense"), ("samsung", "Samsung"), ("tcl", "TCL"),
          ("lg", "LG"), ("sony", "Sony"), ("philips", "Philips")]
EU = {"uk", "de", "fr", "it", "es", "pt", "nl", "be", "at", "ch", "pl", "cz", "sk", "hu", "ro",
      "bg", "gr", "tr", "ru", "ua", "se", "no", "dk", "fi", "ee", "lv", "lt", "hr", "rs", "si", "ba"}
CENTRAL_AM = {"gt", "pa"}
LATAM = ("mx", "co", "pe", "ec", "cl", "bo")
MODEL_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9][A-Za-z0-9\-_/.]{2,30}$")


def spec_models(con, brand_code: str) -> list[str]:
    out, seen = [], set()
    for (raw,) in con.execute("select models from spec_series where brand=?", (brand_code,)):
        if not raw:
            continue
        try:
            items = json.loads(raw)
            items = items if isinstance(items, list) else [items]
        except ValueError:
            items = re.split(r"[,|;]", raw)
        for m in items:
            m = str(m or "").strip().strip('"[]')
            if m and MODEL_RE.match(m) and m.upper() not in seen:
                seen.add(m.upper())
                out.append(m)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", action="append", default=[])
    ap.add_argument("--db", default="data/overseas.db")
    args = ap.parse_args()
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    have = {b for (b,) in con.execute("select distinct brand from spec_series")}
    stamp = dt.date.today().strftime("%Y%m%d")
    targets = args.region or [c for c in REGIONS if c not in ("jp",)]
    for rc in targets:
        reg = REGIONS.get(rc)
        if reg is None or not reg.retail_sites:
            continue
        rows, src_count = [], {}
        for b, name in BRANDS:
            local = f"{b}_{rc}"
            if rc not in EU and local in have:
                ms, src = spec_models(con, local), local
            elif rc in EU:
                # 欧洲各国一律用欧洲那份 SPEC（各国同品牌型号并集），本国有也并进去
                ms, src, seen = [], "", set()
                for cc in sorted(EU):
                    code = f"{b}_{cc}"
                    if code in have:
                        for m in spec_models(con, code):
                            if m.upper() not in seen:
                                seen.add(m.upper())
                                ms.append(m)
                        src += ("+" if src else "") + code
                src = f"EU:{src}" if src else ""
            elif rc in CENTRAL_AM:
                # 中美洲（危地马拉/巴拿马）没有任何官网 SPEC：用拉美各国同品牌型号并集兜底
                # （中美零售站在售的是拉美区型号，如 UN55U8000FPXPA / 55A6N）
                ms, src, seen = [], "", set()
                for cc in LATAM:
                    code = f"{b}_{cc}"
                    if code in have:
                        for m in spec_models(con, code):
                            if m.upper() not in seen:
                                seen.add(m.upper())
                                ms.append(m)
                        src += ("+" if src else "") + code
                src = f"LATAM:{src}" if src else ""
            else:
                ms, src = [], ""
            for m in ms:
                rows.append((f"{b}_{rc}", name, m, f"{name} {m}", src))
            if ms:
                src_count[name] = f"{len(ms)}({src})"
        if not rows:
            print(f"[SKIP] {rc} {reg.name}: 无可用 SPEC 型号")
            continue
        out_dir = os.path.join("data", reg.name)
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"SPEC_型号汇总_{rc}_{stamp}.csv")
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["brand_code", "brand_name", "model_raw", "search_query", "source"])
            w.writerows(rows)
        print(f"[OUT] {out} {len(rows)} 型号 {src_count}")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
