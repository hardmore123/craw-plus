# -*- coding: utf-8 -*-
"""把竞品对阵分析线的维度/事实表（dim_* / fact_*）整表导入唯一主库。

这些表自成体系：fact_spec_value.model_id → dim_product_model，param_id → dim_spec_parameter，
不引用 product/spec_series 的 id，所以可以整表搬。主库已有同名表时跳过（不覆盖）。
来源默认 ../海外/overseas_v4_20260929.db（对阵分析维护脚本原先写的库）。
用法：py -3.12 scripts/import_benchmark_tables.py [--src <库>] [--replace]
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")
TABLES = ["dim_spec_parameter", "dim_product_model", "dim_spec_item_map",
          "dim_spec_normalization_map", "fact_spec_value", "fact_benchmark_comparison"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../海外/overseas_v4_20260929.db")
    ap.add_argument("--target", default=os.environ.get("OVERSEAS_DB_PATH") or "data/overseas.db")
    ap.add_argument("--replace", action="store_true", help="主库已有同名表时先删再导")
    a = ap.parse_args()
    bak = a.target.replace(".db", f"_before_benchmark_{dt.datetime.now():%Y%m%d_%H%M%S}.bak")
    shutil.copy2(a.target, bak)
    print("备份 →", bak)
    c = sqlite3.connect(a.target)
    c.execute("attach database ? as src", (a.src,))     # 只读源库，不写
    have = {n for (n,) in c.execute("select name from main.sqlite_master where type='table'")}
    for t in TABLES:
        row = c.execute("select sql from src.sqlite_master where type='table' and name=?", (t,)).fetchone()
        if not row:
            print(f"  源库无 {t}，跳过"); continue
        if t in have:
            if not a.replace:
                print(f"  主库已有 {t}，跳过（--replace 可覆盖）"); continue
            c.execute(f"drop table main.{t}")
        c.execute(row[0])
        c.execute(f"insert into main.{t} select * from src.{t}")
        for (isql,) in c.execute("select sql from src.sqlite_master where type='index' and tbl_name=? "
                                 "and sql is not null", (t,)).fetchall():
            c.execute(isql)
        print(f"  {t}: {c.execute(f'select count(*) from main.{t}').fetchone()[0]} 行")
    c.commit()
    c.execute("detach database src")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
