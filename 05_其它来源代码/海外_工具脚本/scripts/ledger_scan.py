# -*- coding: utf-8 -*-
"""扫描 爬取进度.csv 的重复/冲突行，输出清单报告（只报告不改动）。"""
import csv
import collections
import os
import re

ROOT = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
CSV = os.path.join(ROOT, "爬取进度.csv")
REPORT = os.path.join(ROOT, "台账重复冲突清单_20260924.md")

PLACEHOLDER = {"", "未提供", "暂未提供", "-", "—"}


def norm(u):
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    return u.split("?")[0].rstrip("/")


def host(u):
    return norm(u).split("/")[0]


raw = open(CSV, "rb").read().decode("gb18030", errors="replace")
rows = list(csv.reader(raw.splitlines()))
recs = []
for i, r in enumerate(rows[1:], start=2):
    if not r or not any(c.strip() for c in r):
        continue
    r = r + [""] * (7 - len(r))
    recs.append({"line": i, "region": r[0].strip(), "country": r[1].strip(), "brand": r[2].strip(),
                 "task": r[3].strip(), "url": r[4].strip(), "status": r[5].strip(),
                 "has_url": r[4].strip() not in PLACEHOLDER})

url_recs = [r for r in recs if r["has_url"]]
no_url = [r for r in recs if not r["has_url"]]

by_url = collections.defaultdict(list)
by_host = collections.defaultdict(list)
by_key = collections.defaultdict(list)
for r in url_recs:
    by_url[norm(r["url"])].append(r)
    by_host[host(r["url"])].append(r)
for r in recs:
    by_key[(r["country"], r["brand"], r["task"])].append(r)

dup_url = {k: v for k, v in by_url.items() if len(v) > 1}
dup_key = {k: v for k, v in by_key.items() if len(v) > 1}
host_diff = {k: v for k, v in by_host.items() if len({r["brand"] for r in v}) > 1}

# 品牌名与域名明显不符（域名关键词不包含品牌名）
# 已知的合法缩写/别名白名单：品牌 -> 允许出现的域名关键词
ALIAS = {
    "cresa": ["crecos"], "unicomer": ["lacuracaonline"], "walmart": ["walmart", "lider"],
    "jlp": ["johnlewis"], "msd": ["mediamarkt", "mediaworld"], "eci": ["elcorteingles"],
    "stiftung warentest": ["test.de"], "jvtech": ["jeuxvideo"], "hardware upgrade": ["hwupgrade"],
    "jornal record": ["record.pt"], "exame informática": ["visao"], "multicenter": ["multicenter"],
    # 监管/政策页（域名是政府站，与品牌名天然不同）与连锁改名，非遗漏
    "fcc": ["ecfr"], "bets-7": ["ised-isde"], "ices-003": ["ised-isde"], "nrcan": ["nrcan"],
    "cec": ["energy"], "energy guide": ["energy"], "energy star": ["energy"], "freesync": ["amd"],
    "hdr 10+": ["hdr10plus"], "杜比": ["dolby"], "潘通": ["pantone"], "蓝牙": ["bluetooth"],
    "rtv euro agd": ["euro.com.pl"], "nay extra": ["nay.sk"], "rd electronics": ["rdveikals"],
}


def brand_ok(brand, h):
    b = re.sub(r"[^a-z0-9]", "", brand.lower())
    hh = re.sub(r"[^a-z0-9]", "", h)
    # 白名单优先（含中文品牌名，需单独处理）
    for key, allowed in ALIAS.items():
        k = re.sub(r"[^a-z0-9]", "", key)
        if k and (b.startswith(k[:6]) or brand.strip().startswith(key)):
            return any(re.sub(r"[^a-z0-9]", "", a) in hh for a in allowed)
    if not b or len(b) < 3:
        return True
    # 通用启发式：品牌前 4 字符与域名前 4 字符互含即视为对得上
    return b[:4] in hh or hh[:4] in b


brand_mismatch = [(r, host(r["url"])) for r in url_recs
                  if any(ch.isalpha() for ch in r["brand"]) and not brand_ok(r["brand"], host(r["url"]))]

# 国家归属与域名 TLD 不符
TLD = {"co.uk": "英国", "de": "德国", "fr": "法国", "it": "意大利", "es": "西班牙", "pt": "葡萄牙",
       "nl": "荷兰", "ru": "俄罗斯", "com.mx": "墨西哥", "com.pe": "秘鲁", "com.ec": "厄瓜多尔",
       "com.co": "哥伦比亚", "com.bo": "玻利维亚", "com.ar": "阿根廷", "cl": "智利",
       "com.gt": "危地马拉", "com.pa": "巴拿马", "ca": "加拿大", "com.br": "巴西"}


def tld_country(u):
    h = host(u)
    for t, c in sorted(TLD.items(), key=lambda kv: -len(kv[0])):
        if h.endswith("." + t):
            return c
    return ""


tld_bad = [(r, tld_country(r["url"])) for r in url_recs
           if tld_country(r["url"]) and r["country"] and tld_country(r["url"]) not in r["country"]]

# 逻辑冲突：聚合行「未提供URL」，但同区域+同任务下已有带 URL 的具体站点行
logical = []
for r in no_url:
    if r["brand"] in ("全品牌", "全渠道", "全渠道零售"):
        # 必须同区域 + 同国家 + 同任务才算逻辑冲突（同区域不同国家不算）
        same = [x for x in url_recs if x["region"] == r["region"] and x["country"] == r["country"]
                and x["task"] == r["task"]]
        if same:
            logical.append((r, same))

L = []
L.append("# 台账重复/冲突清单\n")
L.append("> 对象：`海外/爬取进度.csv`（去重修订后 %d 行数据，其中带 URL %d 行、未提供 URL %d 行）"
         % (len(recs), len(url_recs), len(no_url)))
L.append("> 生成：2026-09-24　**本清单只报告不改动**，等你确认后再批量处理\n")
L.append("> ✅ 已处理：原 42-46 / 144-148 重复块已合并（删除 144-148，状态按实测修正进 42-46）。"
         "备份 `爬取进度_备份_20260924_去重前.csv`。\n")

L.append("## 一、同一网址出现多行（真重复）\n")
if dup_url:
    L.append("| 网址 | 行号 | 区域/国家 | 品牌 | 任务 | 状态 |")
    L.append("|---|---|---|---|---|---|")
    for u, v in dup_url.items():
        for r in v:
            L.append("| %s | %d | %s / %s | %s | %s | %s |" % (u, r["line"], r["region"], r["country"], r["brand"], r["task"], r["status"]))
else:
    L.append("**无** —— URL 层面已无重复\n")

L.append("\n## 二、同一域名出现多个品牌名（命名不一致）\n")
if host_diff:
    L.append("| 域名 | 行号 | 品牌 | 区域/国家 | 状态 |")
    L.append("|---|---|---|---|---|")
    for h, v in host_diff.items():
        for r in v:
            L.append("| %s | %d | %s | %s / %s | %s |" % (h, r["line"], r["brand"], r["region"], r["country"], r["status"]))
else:
    L.append("**无**\n")

L.append("\n## 三、同「国家+品牌+任务」多行（多为同名不同站，需确认）\n")
if dup_key:
    L.append("| 国家 | 品牌 | 任务 | 行号 | 网址 | 状态 | 判定 |")
    L.append("|---|---|---|---|---|---|---|")
    for (c, b, t), v in sorted(dup_key.items(), key=lambda kv: kv[1][0]["line"]):
        hosts = {host(r["url"]) for r in v if r["has_url"]}
        conflicts = len({r["status"] for r in v}) > 1
        if len(hosts) == 1:
            verdict = "★ 同一站点重复"
        elif len(hosts) == 0:
            verdict = "均未提供 URL"
        elif conflicts:
            verdict = "★ 同名不同站·状态冲突"
        else:
            verdict = "同名不同站（非重复）"
        for r in v:
            L.append("| %s | %s | %s | %d | %s | %s | %s |" % (c, b, t, r["line"], r["url"] or "—", r["status"], verdict))
else:
    L.append("**无**\n")

L.append("\n## 四、品牌名与域名明显不符（已排除已知缩写别名）\n")
if brand_mismatch:
    L.append("| 行号 | 品牌 | 域名 | 网址 | 说明 |")
    L.append("|---|---|---|---|---|")
    for r, h in brand_mismatch:
        L.append("| %d | %s | %s | %s | 品牌名与站点域名对不上，疑标错 |" % (r["line"], r["brand"], h, r["url"]))
    L.append("")
    L.append("> 已按白名单排除的**合法缩写/别名**（非遗漏）："
             "Cresa=crecos.com、Unicomer=lacuracaonline.com、Walmart=lider.cl（智利）、JLP=johnlewis.com、"
             "MSD=mediamarkt/mediaworld、ECI=elcorteingles.es、Stiftung Warentest=test.de、"
             "JVTECH=jeuxvideo.com、Hardware Upgrade=hwupgrade.it、Jornal Record=record.pt、"
             "EXAME INFORMÁTICA=visao.pt。")
else:
    L.append("**无**（除已知缩写别名外无可疑项）\n")

L.append("\n## 五、国家归属与域名 TLD 不符\n")
if tld_bad:
    L.append("| 行号 | 台账国家 | 域名推断国 | 品牌 | 网址 |")
    L.append("|---|---|---|---|---|")
    for r, c in tld_bad:
        L.append("| %d | %s | %s | %s | %s |" % (r["line"], r["country"], c, r["brand"], r["url"]))
else:
    L.append("**无**\n")

L.append("\n## 六、逻辑冲突：聚合行写「未提供URL」，但同区域已有带 URL 的具体站点\n")
if logical:
    for r, same in logical:
        L.append("- **行 %d**（%s / %s / %s，状态「%s」，任务 %s）——同区域已有 %d 个带 URL 的行：%s"
                 % (r["line"], r["region"], r["country"], r["brand"], r["status"], r["task"], len(same),
                    "、".join("行%d %s" % (x["line"], x["brand"]) for x in same[:10])))
else:
    L.append("**无**\n")

L.append("\n## 七、未提供 URL 的行（客观无法开展，非重复）\n")
L.append("共 %d 行：" % len(no_url))
L.append("、".join("行%d(%s/%s/%s)" % (r["line"], r["country"], r["brand"], r["task"]) for r in no_url))

open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print("重复URL组 %d | 同域名异名 %d | 同国+品牌+任务 %d | 品牌域名不符 %d | TLD不符 %d | 逻辑冲突 %d | 无URL %d"
      % (len(dup_url), len(host_diff), len(dup_key), len(brand_mismatch), len(tld_bad), len(logical), len(no_url)))
print("报告 ->", REPORT)
