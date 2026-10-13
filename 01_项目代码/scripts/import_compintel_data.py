# -*- coding: utf-8 -*-
"""把 compintel（竞品认证预警线）数据并入唯一主库。

源默认 ../海外/data/overseas.db（compintel 线原先写的库）。先 init_schema 让主库升到 v9
（建 compintel_* 表），再按唯一键 INSERT OR IGNORE：
  compintel_record(source, source_id, captured_at) / compintel_alert(signal_type, source, source_id, detected_at)
  compintel_crawl_state(source, state_key) / compintel_skip(source, source_id)
  compintel_doc(record_id, doc_type, doc_name)——record_id 按 (source, source_id, captured_at) 重映射
run_id 引用的是源库的 crawl_run，主库里没有对应行，统一置 NULL。
用法：py -3.12 scripts/import_compintel_data.py [--src <库>]
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
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")


def cols(c, schema, t):
    return [r[1] for r in c.execute(f"pragma {schema}.table_info('{t}')")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="../海外/data/overseas.db")
    ap.add_argument("--target", default=os.environ.get("OVERSEAS_DB_PATH") or "data/overseas.db")
    a = ap.parse_args()
    bak = a.target.replace(".db", f"_before_compintel_{dt.datetime.now():%Y%m%d_%H%M%S}.bak")
    shutil.copy2(a.target, bak)
    print("备份 →", bak)
    from overseas.db import Database
    with Database(a.target) as db:
        print("schema_version →", db.init_schema())
    c = sqlite3.connect(a.target)
    c.execute("attach database ? as src", (a.src,))
    for t, null_run in (("compintel_record", True), ("compintel_alert", True),
                        ("compintel_crawl_state", False), ("compintel_skip", False)):
        cc = [x for x in cols(c, "src", t) if x != "id" and x in cols(c, "main", t)]
        sel = ", ".join("NULL" if (x == "run_id" and null_run) else x for x in cc)
        n = c.execute(f"insert or ignore into main.{t}({', '.join(cc)}) select {sel} from src.{t}").rowcount
        print(f"  {t}: +{n}")
    # doc：record_id 重映射
    n = c.execute("""
        insert or ignore into main.compintel_doc(record_id, doc_type, doc_name, url, doc_date, captured_at)
        select m.id, d.doc_type, d.doc_name, d.url, d.doc_date, d.captured_at
        from src.compintel_doc d join src.compintel_record s on s.id = d.record_id
        join main.compintel_record m on m.source = s.source and m.source_id = s.source_id
             and m.captured_at = s.captured_at""").rowcount
    print(f"  compintel_doc: +{n}")
    c.commit()
    c.execute("detach database src")
    print("integrity:", c.execute("pragma integrity_check").fetchone()[0])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
