# -*- coding: utf-8 -*-
"""回补：把 readiness 结果里「浏览器中途崩溃」的行改判为 ENV_ERROR（看门狗会重跑）。

依据：该站最新日志 data/sandbox/logs/<site>.log 含 TargetClosedError。
只改**每站最新一行**（日志对应的就是最新一次运行），原文件先备份为 .bak。
用法：py -3.12 scripts/mark_env_errors.py [--since "10-10 13:42"]
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    a = ap.parse_args()
    files = sorted(glob.glob("data/sandbox/readiness_*.csv"))
    latest = {}
    for p in files:
        for i, r in enumerate(csv.DictReader(open(p, encoding="utf-8-sig"))):
            if (r.get("time") or "") >= a.since:
                latest[r["site"]] = (p, i)
    targets = {}
    for site, (p, i) in latest.items():
        log = f"data/sandbox/logs/{site}.log"
        if os.path.exists(log) and "TargetClosedError" in open(log, encoding="utf-8", errors="replace").read():
            targets.setdefault(p, set()).add(i)
    n = 0
    for p, idx in targets.items():
        shutil.copy2(p, p + ".bak")
        rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
        cols = list(rows[0].keys())
        for i in idx:
            if rows[i]["verdict"] != "READY":
                rows[i]["verdict"] = "ENV_ERROR"
                rows[i]["gaps"] = "浏览器中途崩溃（TargetClosedError），环境问题，待重跑；原判定作废"
                n += 1
        with open(p, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    print(f"改判 ENV_ERROR：{n} 站")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
