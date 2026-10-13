# -*- coding: utf-8 -*-
"""按新版 网站汇总表_数据表 (1).csv 更新 爬取进度.csv（保持 7 列）。

规则沿用上一版：
1. 新表内部先按 (域名, 国家, 任务) 去重；认证+评测 再带品牌（同一政策页承载多个认证）；
   无域名按 (国家, 品牌, 任务)。重复组优先保留"有网址且先登记"的那条。
2. 输出行序 = 新表顺序；旧台账的状态/备注按「域名优先、其次 国家+品牌」承接（不看任务类型，
   以承接 媒体评测 → 认证+评测 这类改分类）。
3. 新表没有、旧台账有的行追加到末尾并标注。
4. 不加产品线/产品经理等列，也不写这类尾注（沿用你之前的决定）。
"""
import csv
import collections
import io
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
NEW = os.path.join(ROOT, "网站汇总表_数据表 (1).csv")
CUR = os.path.join(ROOT, "爬取进度.csv")
BAK = os.path.join(ROOT, "爬取进度_备份_20260929_按新汇总表合并前.csv")
REPORT = os.path.join(ROOT, "合并报告_网站汇总表v2_20260929.md")

SUF = r"(uk|de|fr|it|es|jp|ca|us|mx|pe|ec|co|cl|bo|ar|eu|germany|france|italy|spain|pl|se|ch|at|be|nl|dk|no|fi|gr|tr|pt|ru|ua|bg|hr|hu|rs|sk|si|lv|lt|ee|ro|cz|ba)"


def strip_md(u, keep_text=False):
    u = (u or "").strip()

    def rep(m):
        return m.group(1).strip() if keep_text else m.group(2).strip()
    return re.sub(r"\[([^\[\]]*?)\]\(([^()]*?)\)", rep, u).strip()


def host(u):
    u = strip_md(u).lower()
    u = re.sub(r"^https?://", "", u)
    h = u.split("/")[0].split("?")[0].replace("www.", "")
    return "" if h in ("未提供", "暂未提供", "-", "—", "无") else h


def nbrand(b):
    b = (b or "").lower()
    b = re.sub(r"[\[\]()]", " ", b)
    b = re.sub(r"com|co|net|org|\.", " ", b)
    b = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", b)
    return re.sub(SUF + r"$", "", b)


def ncountry(c):
    c = (c or "").strip()
    m = re.match(r"^.*?（(.+?)）$", c)
    if m:
        c = m.group(1)
    c = c.replace(" ", "")
    # 新表把认证/政策类的国家留空，旧台账写「未指定」——同一含义，必须归一否则匹配不上
    return "未指定" if not c else c


def ntask(t):
    t = (t or "").strip()
    return "Spec" if t in ("Spec规格", "Spec") else t


# 汇总表字段纠错：(域名) -> 正确品牌。新表把 alkostoplus.com 标成「Multicenter」，
# 与 multicenter.com 撞名；该站实际是 Alkosto+（对应 regions_config 的 alkostoplus_bo）。
BRAND_FIX = {"alkostoplus.com": "Alkosto+"}


def region_of(region, country):
    r, c = (region or "").strip(), (country or "").strip()
    if r == "日本":
        return "日本线"
    if r == "南美":
        return "南美线"
    if r == "欧洲":
        return "欧洲线"
    if r == "北美":
        if c == "加拿大":
            return "北美线-加拿大"
        if c == "美国":
            return "北美线-美国"
        if c == "墨西哥":
            return "北美线-墨西哥"
        return "北美线"
    return r or "未指定"


# ---------- 读新表 ----------
rows = list(csv.reader(open(NEW, encoding="utf-8-sig", errors="replace").read().splitlines()))
hdr, recs = rows[0], rows[1:]
idx = {h: i for i, h in enumerate(hdr)}
g = lambda r, nn: (r[idx[nn]].strip() if idx[nn] < len(r) else "")

S = []
for r in recs:
    if not (g(r, "品牌/渠道") and g(r, "任务类型")):
        continue
    S.append({"no": g(r, "序号"), "region": g(r, "区域"), "country": g(r, "国家/地区"),
              "brand": strip_md(g(r, "品牌/渠道"), True), "task": ntask(g(r, "任务类型")),
              "url": strip_md(g(r, "网址"))})
print("新表有效站行: %d" % len(S))

# ---------- 新表内部去重 ----------
seen, dedup, dropped = {}, [], []
for s in S:
    h = host(s["url"])
    if not h:
        key = ("", ncountry(s["country"]), nbrand(s["brand"]), s["task"])
    elif s["task"] in ("认证+评测", "媒体评测"):
        key = (h, ncountry(s["country"]), s["task"], nbrand(s["brand"]))
    else:
        key = (h, ncountry(s["country"]), s["task"])
    if key in seen:
        prev = seen[key]
        if prev["url"] or not s["url"]:
            dropped.append((s, prev))
            continue
        dedup[dedup.index(prev)] = s
        seen[key] = s
        dropped.append((prev, s))
        continue
    seen[key] = s
    dedup.append(s)
print("内部去重: %d -> %d（合并 %d）" % (len(S), len(dedup), len(dropped)))

# 第二轮：合并"同国家+同品牌+同任务，只是一条有 URL 一条没有"的行。
# 关键：必须排除"同品牌但不同站点"的情况——新表里 Multicenter 同时指向
# multicenter.com 与 alkostoplus.com，若只按品牌合并会把后者整行丢掉。
g2 = collections.defaultdict(list)
for s in dedup:
    g2[(ncountry(s["country"]), nbrand(s["brand"]), s["task"])].append(s)
final, seen_ids = [], set()
for s in dedup:
    k = (ncountry(s["country"]), nbrand(s["brand"]), s["task"])
    grp = g2.get(k, [])
    keep = s
    if len(grp) > 1:
        hosts_in_grp = {host(x["url"]) for x in grp if host(x["url"])}
        if len(hosts_in_grp) <= 1:          # 同域名（或都无域名）才视为同一站
            with_url = [x for x in grp if x["url"]]
            keep = with_url[0] if with_url else grp[0]
            if s is not keep:
                dropped.append((s, keep))
                if s["url"] and not keep["url"]:
                    keep["url"] = s["url"]
    if id(keep) in seen_ids:
        continue
    seen_ids.add(id(keep))
    final.append(keep)
dedup = final
print("二轮去重后: %d" % len(dedup))

# ---------- 读旧台账 ----------
crows = [r for r in csv.reader(open(CUR, "rb").read().decode("gb18030", "replace").splitlines())
         if any(c.strip() for c in r)]
crecs = crows[1:]
C = []
for i, r in enumerate(crecs, start=2):
    r = r + [""] * 7
    C.append({"line": i, "region": r[0].strip(), "country": r[1].strip(), "brand": r[2].strip(),
              "task": ntask(r[3]), "url": r[4].strip(), "status": r[5].strip(), "note": r[6].strip()})

by_host = collections.defaultdict(list)
for c in C:
    if host(c["url"]):
        by_host[host(c["url"])].append(c)
by_key = collections.defaultdict(list)
for c in C:
    by_key[(ncountry(c["country"]), nbrand(c["brand"]))].append(c)

# ---------- 合并 ----------
used, out, carry, newn = set(), [], 0, 0
reclass = []
for s in dedup:
    m = None
    h = host(s["url"])
    if h and len(by_host.get(h, [])) == 1:
        m = by_host[h][0]
    if m is None:
        cand = by_key.get((ncountry(s["country"]), nbrand(s["brand"])), [])
        cand = [x for x in cand if x["task"] == s["task"]] or cand
        if len(cand) == 1:
            m = cand[0]
    url = s["url"] or "未提供"
    brand = s["brand"]
    # 汇总表自身的字段纠错：新表把 alkostoplus.com 的品牌写成「Multicenter」，
    # 与 multicenter.com 撞名（该站实际是 Alkosto+，见 regions_config 的 alkostoplus_bo）。
    if h and h in BRAND_FIX:
        if brand != BRAND_FIX[h]:
            brand = BRAND_FIX[h]
    if m is not None and m["line"] not in used:
        used.add(m["line"])
        st, note = m["status"], m["note"]
        if m["task"] != s["task"]:
            reclass.append((brand, s["country"] or "未指定", m["task"], s["task"]))
            note = (note + "；" if note else "") + "2026-09-29 任务类型按新汇总表由「%s」改为「%s」" % (m["task"], s["task"])
        carry += 1
    else:
        st = "未开始丨未抓取"
        note = "2026-09-29 由 网站汇总表_数据表 (1).csv 补录"
        newn += 1
    out.append([region_of(s["region"], s["country"]), s["country"] or "未指定", brand,
                s["task"], url, st, note])

leftover = [c for c in C if c["line"] not in used]
for c in leftover:
    out.append([c["region"], c["country"], c["brand"], c["task"], c["url"], c["status"],
                (c["note"] + "；" if c["note"] else "") + "【不在新版网站汇总表内】"])

# ---------- 写盘 ----------
shutil.copyfile(CUR, BAK)
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n")
w.writerow(["区域", "国家/地区", "品牌/渠道", "任务类型", "网址", "状态", "问题/备注"])
w.writerows(out)
open(CUR, "wb").write(buf.getvalue().encode("gb18030"))

# ---------- 报告 ----------
L = ["# 按新汇总表更新 爬取进度.csv —— 合并报告\n",
     "> 源: `网站汇总表_数据表 (1).csv`（405 行，UTF-8）",
     "> 备份: `%s`\n" % os.path.basename(BAK),
     "| 项 | 数量 |", "|---|---|",
     "| 新表原始行 | %d |" % len(recs),
     "| 新表有效站行 | %d |" % len(S),
     "| 内部去重后 | %d |" % len(dedup),
     "| 内部合并掉的重复 | %d |" % len(dropped),
     "| 承接旧台账状态/备注 | %d |" % carry,
     "| 新补录（未开始丨未抓取） | %d |" % newn,
     "| 旧台账未匹配、追加末尾 | %d |" % len(leftover),
     "| **合并后总行数** | **%d** |" % len(out), ""]

L.append("## 一、任务类型改分类（%d 行）\n" % len(reclass))
if reclass:
    L.append("| 品牌 | 国家 | 原 | 新 |")
    L.append("|---|---|---|---|")
    for b, c, o, nw in reclass[:80]:
        L.append("| %s | %s | %s | %s |" % (b, c, o, nw))
else:
    L.append("**无**")

L.append("\n## 二、旧台账未匹配、追加末尾（%d 行）\n" % len(leftover))
if leftover:
    L.append("| 行号 | 区域 | 国家 | 品牌 | 任务 | 网址 | 状态 |")
    L.append("|---|---|---|---|---|---|---|")
    for c in leftover:
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (c["line"], c["region"], c["country"],
                                                          c["brand"], c["task"], c["url"][:40], c["status"]))
else:
    L.append("**无**")

L.append("\n## 三、合并后 区域 × 任务类型\n")
L.append("| 区域 | 任务类型 | 行数 |")
L.append("|---|---|---|")
for k, v in sorted(collections.Counter((r[0], r[3]) for r in out).items()):
    L.append("| %s | %s | %d |" % (k[0], k[1], v))

open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")

print()
print("承接 %d / 新增 %d / 末尾追加 %d / 改分类 %d" % (carry, newn, len(leftover), len(reclass)))
print("合并后总行数: %d -> %s" % (len(out), CUR))
print("报告 -> %s" % REPORT)
