# -*- coding: utf-8 -*-
"""schema / adapter 完成度盘点：台账行 ↔ site code ↔ adapter/schema ↔ 库内数据 ↔ 可达性。

只读：不改台账、不写库。

判定口径（每个 SPEC / 零售 台账行）：
  探索产物  adapter    overseas/sites/<code>/adapter.py
            schema     sites/<code>/schema.json（六段）
            spec       docs/specs/<code>.spec.json（AdapterSpec，SPEC 线）
            retail     docs/retail_specs/<code>.retail.json（RetailSpec，零售线，已转正）
            draft      data/schema_drafts/<code>.*.json（未转正草稿）
            case       skill cases.jsonl 最新一条 verdict
  库内数据  SPEC：spec_series 系列数 / 型号数；零售：product / price / review 条数
  可达      美国出口（10-08 上午）/ 英国出口（10-08 下午）任一 ok
  阶段      A 可全量：有 adapter 或已转正 schema，且可达
            B 需完善：有探索产物但只有草稿 / 只有一次性脚本数据 / 案例 partial
            C 未探索：无任何 adapter/schema/草稿
            X 不可达：两个出口都打不开（先解决网络，再谈 schema）

用法：py -3.12 scripts/schema_inventory.py [--db overseas_v4_20260929.db]
产出：data/schema盘点_<日期>.csv、data/schema盘点_<日期>.md
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import io
import json
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SKILL = ".kiro/skills/overseas-schema-gen"

CC = {"日本": "jp", "加拿大": "ca", "美国": "us", "墨西哥": "mx", "秘鲁": "pe", "厄瓜多尔": "ec",
      "哥伦比亚": "co", "智利": "cl", "玻利维亚": "bo", "阿根廷": "ar", "巴拿马": "pa",
      "危地马拉": "gt", "英国": "uk", "德国": "de", "法国": "fr", "意大利": "it", "西班牙": "es",
      "葡萄牙": "pt", "荷兰": "nl", "比利时": "be", "奥地利": "at", "瑞士": "ch", "波兰": "pl",
      "捷克": "cz", "斯洛伐克": "sk", "匈牙利": "hu", "罗马尼亚": "ro", "保加利亚": "bg",
      "希腊": "gr", "土耳其": "tr", "俄罗斯": "ru", "乌克兰": "ua", "瑞典": "se", "挪威": "no",
      "丹麦": "dk", "芬兰": "fi", "爱沙尼亚": "ee", "拉脱维亚": "lv", "立陶宛": "lt",
      "克罗地亚": "hr", "塞尔维亚": "rs", "斯洛文尼亚": "si", "波黑": "ba"}


def host(u: str) -> str:
    h = urlsplit(u if "://" in u else "https://" + u).netloc.lower().split(":")[0]
    return h[4:] if h.startswith("www.") else h


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def read_ledger() -> list[dict]:
    text = open("爬取进度.csv", "rb").read().decode("gb18030", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    for i, r in enumerate(rows[1:], start=2):
        r = r + [""] * (7 - len(r))
        t = r[3].lower()
        task = "SPEC" if "spec" in t else ("零售" if "价格" in r[3] else "")
        if not task:
            continue
        out.append({"line": i, "region": r[0].strip(), "country": r[1].strip(),
                    "brand": r[2].strip(), "task": task, "url": r[4].strip(),
                    "status": r[5].strip(), "note": r[6].strip()})
    return out


def latest_cases() -> dict[str, tuple[str, str]]:
    """code -> (date, verdict)。retail cases 有乱码行，用正则抽字段。"""
    best: dict[str, tuple[str, str]] = {}
    for path in (f"{SKILL}/spec/cases.jsonl", f"{SKILL}/retail/cases.jsonl"):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8", errors="replace"):
            mc = re.search(r'"code"\s*:\s*"([^"]+)"', line)
            mv = re.search(r'"verdict"\s*:\s*"([^"]*)"', line)
            md = re.search(r'"date"\s*:\s*"([^"]*)"', line)
            if not mc or not mv or mc.group(1).startswith("_"):
                continue
            code, d = mc.group(1), (md.group(1) if md else "")
            if code not in best or d >= best[code][0]:
                best[code] = (d, mv.group(1))
    return best


def reach() -> dict[str, tuple[str, str]]:
    out: dict[str, list[str]] = defaultdict(lambda: ["", ""])
    p = "data/连通性体检_最终_20261008.csv"
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            out[r["url"]][0] = r["final"]
    p = "data/连通性对比_UK.csv"
    if os.path.exists(p):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            out[r["url"]][1] = r["UK_final"]
    return {k: (v[0], v[1]) for k, v in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="overseas_v4_20260929.db")
    args = ap.parse_args()

    # ---- 产物 ----
    adapters = {d for d in os.listdir("overseas/sites")
                if os.path.exists(f"overseas/sites/{d}/adapter.py")}
    schema6 = {d for d in adapters if os.path.exists(f"overseas/sites/{d}/schema.json")}
    specs = {os.path.basename(p).split(".")[0] for p in glob.glob("docs/specs/*.spec.json")}
    retail = {os.path.basename(p).split(".")[0] for p in glob.glob("docs/retail_specs/*.retail.json")}
    drafts = {os.path.basename(p).split(".")[0] for p in glob.glob("data/schema_drafts/*.json")}
    cases = latest_cases()

    # ---- 库 ----
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    site_url = dict(db.execute("select code, coalesce(base_url,'') from site"))
    prod = dict(db.execute("select s.code, count(p.id) from site s left join product p "
                           "on p.site_id=s.id group by s.code"))
    price = dict(db.execute("select s.code, count(ps.id) from site s join product p on p.site_id=s.id "
                            "join price_snapshot ps on ps.product_id=p.id group by s.code"))
    rev = dict(db.execute("select s.code, count(r.id) from site s join product p on p.site_id=s.id "
                          "join review r on r.product_id=p.id group by s.code"))
    spec_ser = {}
    for b, n, ms in db.execute("select brand, count(*), group_concat(models, '|') from spec_series group by brand"):
        nm = len({m for m in re.split(r"[|,;/\s]+", ms or "") if m})
        spec_ser[b] = (n, nm)

    # 适配器自带 base_url（库里 base_url 为空的站兜底）
    for d in adapters:
        if site_url.get(d):
            continue
        try:
            src = open(f"overseas/sites/{d}/adapter.py", encoding="utf-8").read()
            m = re.search(r'base_url\s*=\s*["\']([^"\']+)', src)
            if m:
                site_url[d] = m.group(1)
        except OSError:
            pass
    all_codes = set(site_url) | adapters | specs | retail | drafts
    by_host: dict[str, list[str]] = defaultdict(list)
    for c in all_codes:
        if site_url.get(c):
            by_host[host(site_url[c])].append(c)

    # 旧映射（09-24 四维梳理）按 URL
    old = {}
    if os.path.exists("爬取进度_四维梳理_20260924.csv"):
        for r in csv.DictReader(open("爬取进度_四维梳理_20260924.csv", encoding="utf-8-sig")):
            if r.get("站点code"):
                old[r["网址"].strip()] = r["站点code"].strip()

    def resolve(row: dict) -> tuple[str, str]:
        cc = CC.get(row["country"], "")
        if row["url"] in old and old[row["url"]] in all_codes:
            return old[row["url"]], "旧映射"
        cands = by_host.get(host(row["url"]), [])
        if len(cands) == 1:
            return cands[0], "host"
        if cands:
            hit = [c for c in cands if cc and c.endswith("_" + cc)]
            if len(hit) == 1:
                return hit[0], "host+国家"
            if hit:
                bs = slug(row["brand"].split()[0])
                hit2 = [c for c in hit if c.startswith(bs[:4])]
                if hit2:
                    return hit2[0], "host+国家+品牌"
        # 库里 base_url 为空的站：按 品牌slug_国家 猜
        bs = slug(re.sub(r"\.(com|net|ee|lv|lt|sk|cz)$", "", row["brand"].split()[0], flags=re.I))
        for c in all_codes:
            if cc and c == f"{bs}_{cc}":
                return c, "品牌slug"
        return "", ""

    rch = reach()
    out = []
    for row in read_ledger():
        code, how = resolve(row)
        us, uk = rch.get(row["url"], ("", ""))
        reachable = "ok" in (us, uk)
        cv = cases.get(code, ("", ""))[1] if code else ""
        has_ad, has_s6 = code in adapters, code in schema6
        has_spec, has_rt, has_dr = code in specs, code in retail, code in drafts
        if row["task"] == "SPEC":
            ns, nm = spec_ser.get(code, (0, 0))
            data = f"系列{ns}/型号{nm}"
            has_data = ns > 0
            formal = has_ad or has_spec
        else:
            p, pr, rv = prod.get(code, 0), price.get(code, 0), rev.get(code, 0)
            data = f"产品{p}/价{pr}/评{rv}"
            has_data = p > 0
            formal = has_ad or has_rt
        explored = formal or has_dr or has_s6 or cv in ("success", "partial", "no_reviews")
        if "." not in host(row["url"]) or "未提供" in row["url"]:
            stage = "N无URL"      # 台账没给网址，需先找入口
        elif not us and not uk:
            stage = "?未测"
        elif not reachable:
            stage = "X不可达"
        elif formal and cv not in ("partial", "blocked"):
            stage = "A可全量"
        elif explored or has_data:
            stage = "B需完善"
        else:
            stage = "C未探索"
        reasons = []
        if stage == "B需完善":
            if not formal and has_data:
                reasons.append("只有一次性脚本数据，无 adapter/schema")
            if has_dr and not formal:
                reasons.append("只有草稿未转正")
            if cv == "partial":
                reasons.append("案例 partial")
            if cv == "blocked":
                reasons.append("案例记 blocked，但本次可达")
            if formal and not has_data:
                reasons.append("有 adapter 但库内无数据")
        out.append({**row, "code": code, "code来源": how, "adapter": "Y" if has_ad else "",
                    "schema6": "Y" if has_s6 else "", "spec": "Y" if has_spec else "",
                    "retail_spec": "Y" if has_rt else "", "draft": "Y" if has_dr else "",
                    "case": cv, "库内数据": data, "US": us, "UK": uk,
                    "阶段": stage, "说明": "；".join(reasons)})

    stamp = dt.date.today().strftime("%Y%m%d")
    cols = ["line", "region", "country", "brand", "task", "url", "status", "code", "code来源",
            "adapter", "schema6", "spec", "retail_spec", "draft", "case", "库内数据", "US", "UK",
            "阶段", "说明"]
    p_csv = f"data/schema盘点_{stamp}.csv"
    with open(p_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)

    # ---- 汇总 ----
    L = [f"# schema / adapter 完成度盘点（{stamp}）\n",
         "> 只统计台账 SPEC + 价格网评 行；可达 = 美国或英国出口任一 ok。\n",
         "## 阶段 × 线\n", "| 阶段 | SPEC | 零售 | 合计 |", "|---|---|---|---|"]
    cnt = Counter((r["阶段"], r["task"]) for r in out)
    for st in sorted({r["阶段"] for r in out}):
        a, b = cnt[(st, "SPEC")], cnt[(st, "零售")]
        L.append(f"| {st} | {a} | {b} | {a + b} |")
    L.append("\n## 按区域（零售）\n")
    L.append("| 区域 | A可全量 | B需完善 | C未探索 | X不可达 | N无URL |")
    L.append("|---|---|---|---|---|---|")
    reg = defaultdict(Counter)
    for r in out:
        if r["task"] == "零售":
            reg[r["region"]][r["阶段"]] += 1
    for k, c in sorted(reg.items()):
        L.append(f"| {k} | {c['A可全量']} | {c['B需完善']} | {c['C未探索']} | {c['X不可达']} | {c['N无URL']} |")
    unmapped = [r for r in out if not r["code"]]
    L.append(f"\n未映射到 code 的行：{len(unmapped)}\n")
    for st in ("A可全量", "B需完善", "C未探索"):
        L.append(f"\n## {st}\n")
        L.append("| 行 | 国家 | 站点 | 线 | code | 产物 | case | 库内数据 | 说明 |")
        L.append("|---|---|---|---|---|---|---|---|---|")
        for r in out:
            if r["阶段"] != st:
                continue
            arts = "+".join(k for k in ("adapter", "schema6", "spec", "retail_spec", "draft") if r[k])
            L.append(f"| {r['line']} | {r['country']} | {r['brand']} | {r['task']} | {r['code'] or '-'} | "
                     f"{arts or '-'} | {r['case'] or '-'} | {r['库内数据']} | {r['说明']} |")
    p_md = f"data/schema盘点_{stamp}.md"
    open(p_md, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[OUT] {p_csv}\n[OUT] {p_md}")
    print(dict(cnt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
