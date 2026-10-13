# -*- coding: utf-8 -*-
"""对比两次连通性体检（如美国出口 vs 英国出口），输出逐站对照。

新一轮的最终判定 = HTTP 判定 ok 则 ok，否则取浏览器复测判定（有超时复测文件时再覆盖）。

用法：
  py -3.12 scripts/connectivity_compare.py --base data/连通性体检_最终_20261008.csv
        --http data/连通性体检_20261008_UK.csv
        --browser data/连通性体检_浏览器复测_20261008_UK.csv
        [--browser2 data/连通性体检_超时复测_20261008_UK.csv] --tag UK
产出：data/连通性对比_<tag>.csv（只含 SPEC + 零售）并在终端打印汇总
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def _read(path: str) -> list[dict]:
    return list(csv.DictReader(open(path, encoding="utf-8-sig"))) if path else []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--http", required=True)
    ap.add_argument("--browser", default="")
    ap.add_argument("--browser2", default="")
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()

    base = {r["url"]: r for r in _read(args.base)}
    new: dict[str, dict] = {}
    for r in _read(args.http):
        new[r["url"]] = dict(r, final=r["verdict"], via="http")
    for src, via in ((args.browser, "browser"), (args.browser2, "browser60s")):
        for r in _read(src):
            if r["url"] in new and r.get("b_verdict"):
                new[r["url"]].update(final=r["b_verdict"], via=via,
                                     b_title=r.get("b_title", ""))

    rows = []
    for url, n in new.items():
        if n["task"] not in ("SPEC", "零售"):
            continue
        b = base.get(url, {})
        old, cur = b.get("final", ""), n["final"]
        change = ("均可达" if old == "ok" and cur == "ok" else
                  "新增可达" if cur == "ok" else
                  "变为不可达" if old == "ok" else "均不可达")
        rows.append({"line": n["line"], "region": n["region"], "country": n["country"],
                     "brand": n["brand"], "task": n["task"], "status": n["status"],
                     "url": url, "base_final": old, f"{args.tag}_final": cur,
                     f"{args.tag}_via": n["via"], "change": change,
                     "title": n.get("b_title") or n.get("title", "")})
    rows.sort(key=lambda r: int(r["line"]))
    out = f"data/连通性对比_{args.tag}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print(f"SPEC+零售 {len(rows)} 站：", dict(Counter(r["change"] for r in rows)))
    for tk in ("SPEC", "零售"):
        sub = [r for r in rows if r["task"] == tk]
        print(f"  {tk}: base可达 {sum(r['base_final'] == 'ok' for r in sub)}"
              f" / {args.tag}可达 {sum(r[f'{args.tag}_final'] == 'ok' for r in sub)} / 共 {len(sub)}")
    for ch in ("新增可达", "变为不可达", "均不可达"):
        print(f"\n[{ch}]")
        for r in rows:
            if r["change"] == ch:
                print(f"  {r['country']}|{r['brand']}|{r['task']}|{r['base_final']}->"
                      f"{r[f'{args.tag}_final']}")
    print(f"\n[OUT] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
