# -*- coding: utf-8 -*-
"""整体 schema/adapter 就绪总览：静态自检 × 最新实测 × autofix，按区域汇总。

数据源：
  - 静态：scripts/full_readiness_static.py 的最新 CSV（不联网的 G1~G10 门禁）
  - 实测：data/sandbox/readiness_*.csv 中每站最新一行（--since 起算，默认看全部）
  - 修复：data/sandbox/autofix_search_*.csv 中每站最新一行
产出：data/sandbox/整体就绪总览_<日期>.md（逐站明细 + 区域汇总），终端打印汇总
用法：py -3.12 scripts/overall_status.py [--since "10-10 13:42"]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

EU = {"uk", "de", "fr", "it", "es", "pt", "nl", "be", "at", "ch", "pl", "cz", "sk", "hu", "ro",
      "bg", "gr", "tr", "ru", "ua", "se", "no", "dk", "fi", "ee", "lv", "lt", "hr", "rs", "si", "ba"}


def area(rc: str) -> str:
    if rc in ("ca", "us", "mx"):
        return "北美"
    if rc in ("pe", "ec", "co", "cl", "bo", "ar"):
        return "南美"
    if rc in ("gt", "pa"):
        return "中美"
    if rc in EU:
        return "欧洲"
    return "其他"


def latest(pattern: str, since: str) -> dict:
    out = {}
    for p in sorted(glob.glob(pattern)):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if (r.get("time") or "") >= since:
                out[r["site"]] = r
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    a = ap.parse_args()
    subprocess.run([sys.executable, "scripts/full_readiness_static.py"], capture_output=True)
    static_csv = sorted(glob.glob("data/sandbox/full_readiness_static_*.csv"))[-1]
    static = {r["site"]: r for r in csv.DictReader(open(static_csv, encoding="utf-8-sig"))}
    live = latest("data/sandbox/readiness_*.csv", a.since)
    fix = latest("data/sandbox/autofix_search_*.csv", "")
    rows = []
    for code, s in sorted(static.items()):
        rc = s["region"] or code.rsplit("_", 1)[-1]
        lv = live.get(code, {})
        fx = fix.get(code, {})
        sv = s["verdict"]
        lvd = lv.get("verdict", "")
        if sv in ("SPEC_LINE", "DEDICATED"):
            final = sv
        elif sv == "EXCLUDED":
            final = "EXCLUDED"
        elif sv == "GAP":
            final = "STATIC_GAP"
        elif lvd == "READY":
            final = "READY"
        elif lvd in ("PARTIAL", "NO_SAMPLE"):
            final = lvd
        elif lvd == "FAIL":
            final = "FAIL"
        else:
            final = "未实测"
        rows.append({"area": area(rc), "region": rc, "site": code, "spec_status": s["spec_status"],
                     "static": sv, "live": lvd or "-", "live_time": lv.get("time", ""),
                     "autofix": fx.get("result", ""), "final": final,
                     "gaps": (lv.get("gaps") or s.get("gaps") or fx.get("note") or "")[:120]})
    order = ["READY", "PARTIAL", "NO_SAMPLE", "FAIL", "未实测", "STATIC_GAP", "EXCLUDED", "SPEC_LINE", "DEDICATED"]
    by = collections.defaultdict(collections.Counter)
    for r in rows:
        by[r["area"]][r["final"]] += 1
    L = [f"# 整体 schema/adapter 就绪总览（{dt.datetime.now():%Y-%m-%d %H:%M}）\n",
         f"> 静态：{os.path.basename(static_csv)}；实测取每站最新一次{('（' + a.since + ' 之后）') if a.since else ''}\n",
         "| 区域 | " + " | ".join(order) + " | 合计 |", "|---" * (len(order) + 2) + "|"]
    tot = collections.Counter()
    for ar in ("北美", "南美", "中美", "欧洲", "其他"):
        c = by.get(ar)
        if not c:
            continue
        tot.update(c)
        L.append(f"| {ar} | " + " | ".join(str(c.get(k, 0)) for k in order) + f" | {sum(c.values())} |")
    L.append("| **合计** | " + " | ".join(str(tot.get(k, 0)) for k in order) + f" | {sum(tot.values())} |")
    L.append("\n## 逐站\n")
    L.append("| 区域 | 站点 | spec | 静态 | 实测 | 实测时间 | autofix | 结论 | 缺口 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: (x["area"], order.index(x["final"]), x["site"])):
        L.append(f"| {r['area']} | {r['site']} | {r['spec_status']} | {r['static']} | {r['live']} | "
                 f"{r['live_time']} | {r['autofix'] or '-'} | {r['final']} | {r['gaps']} |")
    out = f"data/sandbox/整体就绪总览_{dt.date.today():%Y%m%d}.md"
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L[:12]))
    print("[OUT]", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
