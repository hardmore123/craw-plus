# -*- coding: utf-8 -*-
"""把 readiness 的 FAIL/PARTIAL 按根因归类（读每站最新日志），决定下一步走 autofix 还是换出口/放弃。

类别：
  反爬拦截     日志有 http_403/429、captcha、cloudflare 等且搜索从未拿到候选 → 换出口/住宅 IP，schema 改不动
  搜索层失效   品牌搜索未取到候选/候选过少/搜索被拦(no_anchor) → 跑 autofix_search
  正样本未匹配 搜索有候选但目标型号未命中 → 型号清单/匹配规则问题（或该站确实没上架）
  缺价格/缺评价 已命中但字段空 → 详情页规则问题
用法：py -3.12 scripts/classify_failures.py --since "10-10 22:33" [--out sites.txt --category 搜索层失效]
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def classify(site: str, row: dict) -> str:
    p = f"data/sandbox/logs/{site}.log"
    t = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else ""
    got_pool = re.search(r"得 \d+ TV", t) is not None
    if not got_pool and re.search(r"http_403|http_429|marker:|captcha|cloudflare|Access Denied", t, re.I):
        return "反爬拦截"
    if not got_pool and re.search(r"候选过少|搜索失败|搜索被拦截|未取到候选|搜索结果为空", t):
        return "搜索层失效"
    if re.search(r"未匹配到商品|不在该站品牌搜索结果|型号不匹配", t) and "price=" not in t:
        return "正样本未匹配"
    g = row.get("gaps") or ""
    if "价格" in g:
        return "缺价格"
    if "评价" in g:
        return "缺评价"
    if "命中" in g:
        return "正样本未匹配"
    return "其他"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    ap.add_argument("--category", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    rows = {}
    for p in sorted(glob.glob("data/sandbox/readiness_*.csv")):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if (r.get("time") or "") >= a.since:
                rows[r["site"]] = r
    cat = collections.defaultdict(list)
    for s, r in rows.items():
        if r["verdict"] in ("FAIL", "PARTIAL"):
            cat[classify(s, r)].append((s, r["verdict"]))
    for k, v in sorted(cat.items(), key=lambda x: -len(x[1])):
        print(f"{k} {len(v)}: " + " ".join(f"{s}({vd[0]})" for s, vd in sorted(v)))
    if a.out and a.category:
        open(a.out, "w", encoding="utf-8").write("\n".join(s for s, _ in cat.get(a.category, [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
