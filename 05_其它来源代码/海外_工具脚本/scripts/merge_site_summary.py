# -*- coding: utf-8 -*-
"""按 网站汇总表.csv 更新 爬取进度.csv（全量合并 / 保持 7 列 / 媒体站挪到末尾）。

规则：
1. 汇总表内先按 (域名, 国家, 任务类型) 去重；无域名的按 (国家, 品牌, 任务类型) 去重。
   重复组优先保留「有网址」的一条；都有网址则保留先出现的一条。
2. 输出行序 = 汇总表顺序；旧台账的状态/备注按「域名优先、其次 国家+品牌」承接。
3. 汇总表没有、旧台账有的行（媒体评测等）追加到末尾并标注。
4. 产品线/产品经理 不单独建列，以尾注形式写进「问题/备注」。
"""
import csv
import collections
import io
import os
import re
import shutil

ROOT = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
SUM = ROOT + r"\网站汇总表.csv"          # 原始表为 GB18030，脚本内自行解码
CUR = ROOT + r"\爬取进度.csv"
BAK = ROOT + r"\爬取进度_备份_20260924_按网站汇总表合并前.csv"
REPORT = ROOT + r"\合并报告_网站汇总表_20260924.md"

SUF = (r"(uk|de|fr|it|es|jp|ca|us|mx|pe|ec|co|cl|bo|ar|eu|germany|france|italy|spain|poland|sweden|"
       r"switzerland|austria|belgium|netherlands|denmark|norway|finland|greece|turkey|portugal|russia|"
       r"ukraine|bulgaria|croatia|hungary|serbia|slovakia|slovenia|latvia|lithuania|estonia|romania|"
       r"czech|bosnia|japan|china)")


def strip_md(u, keep_text=False):
    """去掉 markdown 链接外壳。keep_text=True 时保留方括号里的显示文本（用于品牌名）。
    注意要处理 `[X](Y) 后缀` 这种带尾巴的写法，所以不能用首尾锚定。"""
    u = (u or "").strip()

    def _rep(m):
        return m.group(1).strip() if keep_text else m.group(2).strip()

    u = re.sub(r"\[([^\[\]]*?)\]\(([^()]*?)\)", _rep, u)
    return re.sub(r"\s+", " ", u).strip()


def clean_url(u):
    """清理网址：去 markdown 外壳；把占位符统一成空串。"""
    u = strip_md(u)
    if not u or u in ("未提供", "暂未提供", "-", "—", "无"):
        return ""
    if "暂未提供" in u or "未提供" in u or "." not in u:
        return ""
    return u


def host(u):
    u = clean_url(u).lower()
    u = re.sub(r"^https?://", "", u)
    h = u.split("/")[0].split("?")[0].replace("www.", "")
    return "" if h in ("未提供", "暂未提供", "-", "—", "无", "n/a", "na") else h


def nb(b):
    b = (b or "").lower()
    b = re.sub(r"\[|\]|\(|\)", " ", b)
    b = re.sub(r"com|co|net|org", " ", b)
    b = re.sub(r"\.", " ", b)
    b = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", b)
    return re.sub(SUF + r"$", "", b)


def nc(c):
    c = (c or "").strip()
    m = re.match(r"^.*?（(.+?)）$", c)
    return (m.group(1) if m else c).replace(" ", "")


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


# 汇总表自身的字段纠错：(域名, 品牌关键字) -> 正确国家
COUNTRY_FIX = {("philips.de", "philips"): "德国"}


# ---------- 读汇总表 ----------
sh, srows = (lambda r: (r[0], r[1:]))(list(csv.reader(
    open(SUM, "rb").read().decode("gb18030", errors="replace").splitlines())))
si = {h: i for i, h in enumerate(sh)}
S = []
for r in srows:
    g = lambda n: (r[si[n]].strip() if si[n] < len(r) else "")
    if not (g("品牌/渠道") and g("任务类型")):
        continue
    brand = strip_md(g("品牌/渠道"), keep_text=True)
    u = clean_url(g("网址"))
    country = g("国家/地区")
    for (h, bk), cc in COUNTRY_FIX.items():
        if h == host(u) and bk in brand.lower():
            if country != cc:
                print("  [纠错] 汇总表把 %s/%s 标成「%s」，按域名改为「%s」" % (brand, h, country, cc))
            country = cc
    S.append({"no": g("序号"), "line": g("产品线"), "region": g("区域"), "country": country,
              "brand": brand, "task": g("任务类型").replace("Spec规格", "Spec"),
              "pm": g("产品经理"), "url": u,
              "date": g("最后更新日期"), "by": g("修改人")})

# ---------- 汇总表内部去重 ----------
# 去重键：
#   - 有真实域名：普通任务按 (域名, 国家, 任务) —— 同一零售站在不同国家是不同站点，必须带国家；
#   - 认证+评测：同一认证机构的"政策页"可能被多个认证共用（如 ised-isde.canada.ca 同时是
#     BETS-7 与 ICES-003），必须再带品牌，否则会把不同认证误并；
#   - 无域名：按 (国家, 品牌, 任务) 区分（如巴拿马 Hisense/TCL/Samsung/LG 四行都是空 URL）。
seen, deduped, dropped = {}, [], []
for s in S:
    h = host(s["url"])
    if not h:
        key = ("", nc(s["country"]), nb(s["brand"]), s["task"])
    elif s["task"] == "认证+评测":
        key = (h, nc(s["country"]), s["task"], nb(s["brand"]))
    else:
        key = (h, nc(s["country"]), s["task"])
    if key in seen:
        prev = seen[key]
        # 优先保留"先登记且有网址"的那条（先登记的一批带产品经理，且命名与旧台账一致）；
        # 仅当旧的没有网址、新的有网址时才用新的替换（如 boulanger 第一批缺 URL）。
        if prev["url"] or not s["url"]:
            dropped.append((s, prev))
            continue
        deduped[deduped.index(prev)] = s
        seen[key] = s
        dropped.append((prev, s))
        continue
    seen[key] = s
    deduped.append(s)

print("汇总表有效 %d 行 -> 一轮去重后 %d 行（合并掉 %d 行）" % (len(S), len(deduped), len(dropped)))

# ---------- 第二遍去重：合并"同国家+同品牌+同任务，只是一条有 URL 一条没有"的行 ----------
# 例：第一批 Boulanger 网址写"暂未提供"、第二批写了 https://www.boulanger.com；
# 第一遍因一条 host 为空、一条非空而没撞上，这里按 (国家, 品牌, 任务) 再合一。
g2 = collections.defaultdict(list)
for s in deduped:
    g2[(nc(s["country"]), nb(s["brand"]), s["task"])].append(s)
final, drop2 = [], 0
for s in deduped:
    k = (nc(s["country"]), nb(s["brand"]), s["task"])
    grp = g2.get(k, [])
    if len(grp) > 1:
        with_url = [x for x in grp if x["url"]]
        keep = with_url[0] if with_url else grp[0]
        if s is not keep:
            drop2 += 1
            dropped.append((s, keep))
            if s["url"] and not keep["url"]:
                keep["url"] = s["url"]
    final.append(s)
# 同一 keep 会被 append 多次，去重
ordered, seen_ids = [], set()
for s in final:
    k = (nc(s["country"]), nb(s["brand"]), s["task"])
    grp = g2.get(k, [])
    if len(grp) > 1:
        with_url = [x for x in grp if x["url"]]
        keep = with_url[0] if with_url else grp[0]
        if id(keep) in seen_ids:
            continue
        seen_ids.add(id(keep))
        ordered.append(keep)
    else:
        if id(s) in seen_ids:
            continue
        seen_ids.add(id(s))
        ordered.append(s)
deduped = ordered
print("二轮去重后 %d 行（再合并 %d 行）" % (len(deduped), drop2))

# ---------- 读旧台账 ----------
ch, crows = (lambda r: (r[0], r[1:]))(list(csv.reader(
    open(CUR, "rb").read().decode("gb18030", "replace").splitlines())))
C = []
for i, r in enumerate(crows, start=2):
    r = r + [""] * 7
    if not any(x.strip() for x in r):
        continue
    C.append({"line": i, "region": r[0].strip(), "country": r[1].strip(), "brand": r[2].strip(),
              "task": r[3].strip(), "url": r[4].strip(), "status": r[5].strip(), "note": r[6].strip()})

by_host = collections.defaultdict(list)
for c in C:
    if host(c["url"]):
        by_host[host(c["url"])].append(c)
by_key = collections.defaultdict(list)
for c in C:
    by_key[(nc(c["country"]), nb(c["brand"]), c["task"])].append(c)

used, out, new_cnt, carry_cnt = set(), [], 0, 0
for s in deduped:
    tag = "（产品线=%s；产品经理=%s）" % (s["line"] or "—", s["pm"] or "—")
    m = None
    h = host(s["url"])
    if h and len(by_host.get(h, [])) == 1:
        m = by_host[h][0]
    if m is None:
        cand = by_key.get((nc(s["country"]), nb(s["brand"]), s["task"]), [])
        if len(cand) == 1:
            m = cand[0]
    if m is not None and m["line"] not in used:
        used.add(m["line"])
        st = m["status"]
        note = (m["note"] + "；" if m["note"] else "") + tag
        # 合并后补上了网址，原来"未提供URL"的判定已不成立，重置为未抓取
        if st.startswith("不可抓取丨未提供URL") and s["url"]:
            st = "未开始丨未抓取"
            note = "2026-09-24 按 网站汇总表.csv 补上原缺失网址，状态由「不可抓取丨未提供URL」重置；" + note
        carry_cnt += 1
    else:
        st = "未开始丨未抓取"
        note = "2026-09-24 由 网站汇总表.csv 补录（原表 开发状态与进展 为空）；" + tag
        new_cnt += 1
    out.append([region_of(s["region"], s["country"]), s["country"] or "未指定", s["brand"],
                s["task"], s["url"] or "未提供", st, note])

leftover = [c for c in C if c["line"] not in used]
media = [c for c in leftover if c["task"] == "媒体评测"]
others = [c for c in leftover if c["task"] != "媒体评测"]
for c in others:
    out.append([c["region"], c["country"], c["brand"], c["task"], c["url"], c["status"],
                (c["note"] + "；" if c["note"] else "") + "【不在网站汇总表内】"])
for c in media:
    out.append([c["region"], c["country"], c["brand"], c["task"], c["url"], c["status"],
                (c["note"] + "；" if c["note"] else "") + "【不在网站汇总表内·媒体评测，先不抓取探索】"])

# ---------- 写盘 ----------
shutil.copyfile(CUR, BAK)
buf = io.StringIO()
w = csv.writer(buf, lineterminator="\n")
w.writerow(["区域", "国家/地区", "品牌/渠道", "任务类型", "网址", "状态", "问题/备注"])
w.writerows(out)
open(CUR, "wb").write(buf.getvalue().encode("gb18030"))

# ---------- 报告 ----------
L = ["# 按 网站汇总表.csv 合并 爬取进度.csv —— 合并报告\n",
     "> 生成：2026-09-24　备份：`%s`\n" % os.path.basename(BAK),
     "| 项 | 数量 |", "|---|---|",
     "| 汇总表原始行 | %d |" % len(srows),
     "| 汇总表有效站行（有品牌+任务） | %d |" % len(S),
     "| 汇总表内部去重后 | %d |" % len(deduped),
     "| 汇总表内部合并掉的重复行 | %d |" % len(dropped),
     "| 承接旧台账状态/备注的行 | %d |" % carry_cnt,
     "| 新补入（未开始丨未抓取） | %d |" % new_cnt,
     "| 旧台账未匹配、追加到末尾（非媒体） | %d |" % len(others),
     "| 旧台账媒体评测站，挪到最末尾 | %d |" % len(media),
     "| **合并后总行数** | **%d** |" % len(out), ""]

L.append("## 一、汇总表内部被合并掉的重复行（%d 行）\n" % len(dropped))
L.append("| 被丢弃序号 | 品牌 | 国家 | 域名 | 保留序号 | 保留品牌 | 原因 |")
L.append("|---|---|---|---|---|---|---|")
for s, p in dropped:
    L.append("| %s | %s | %s | %s | %s | %s | 同一站点重复登记 |"
             % (s["no"], s["brand"], s["country"], host(s["url"]) or "无URL", p["no"], p["brand"]))

L.append("\n## 二、旧台账未匹配、追加到末尾的非媒体行（%d 行）\n" % len(others))
if others:
    L.append("| 行号 | 区域 | 国家 | 品牌 | 任务 | 网址 | 状态 |")
    L.append("|---|---|---|---|---|---|---|")
    for c in others:
        L.append("| %d | %s | %s | %s | %s | %s | %s |" % (c["line"], c["region"], c["country"],
                                                          c["brand"], c["task"], c["url"] or "—", c["status"]))
else:
    L.append("**无**")

L.append("\n## 三、挪到最末尾的媒体评测站（%d 站）\n" % len(media))
L.append("、".join("%s(%s)" % (c["brand"], c["country"]) for c in media))

L.append("\n## 四、合并后 区域×任务类型 分布\n")
L.append("| 区域 | 任务类型 | 行数 |")
L.append("|---|---|---|")
for k, v in sorted(collections.Counter((r[0], r[3]) for r in out).items()):
    L.append("| %s | %s | %d |" % (k[0], k[1], v))

open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")

print("承接 %d 行 / 新增 %d 行 / 末尾追加非媒体 %d 行 / 媒体 %d 站"
      % (carry_cnt, new_cnt, len(others), len(media)))
print("合并后总行数 %d -> %s" % (len(out), CUR))
print("报告 ->", REPORT)
