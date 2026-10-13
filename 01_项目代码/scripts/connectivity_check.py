# -*- coding: utf-8 -*-
"""全量抓取前的连通性体检：按 爬取进度.csv 逐站经代理请求一次首页，分类可达性。

只做一次 GET（不翻页、不搜索），并发有限，单站超时 20s，不重试——低流量、不会卡死。

分类：
  ok              200 且非拦截页，内容像正常页面
  cloudflare      Cloudflare 挑战/封锁（Just a moment / cf-chl / Attention Required）
  perimeterx      PerimeterX（Robot or human / Verify your identity / px-captcha）
  akamai          Akamai Access Denied（Reference #）
  datadome        DataDome
  imperva         Imperva/Incapsula/Distil
  captcha         其它验证码页
  http_403/429/5xx 状态码拦截或服务端错误
  geo_redirect    被重定向到其它国家/域名（出口 IP 国家不匹配的信号）
  timeout / conn_error / dns_error  网络层失败

用法：
  py -3.12 scripts/connectivity_check.py [--proxy http://127.0.0.1:7877] [--workers 8]
        [--only 北美线,欧洲线] [--task 零售|SPEC|全部]
产出：
  data/连通性体检_<日期>.csv   逐站明细（UTF-8-BOM）
  data/连通性体检_<日期>.md    汇总
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import datetime as dt
import io
import os
import re
import sys
import time
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import requests
import urllib3

urllib3.disable_warnings()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HDR = {"User-Agent": UA,
       "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
       "Accept-Language": "en-US,en;q=0.9,es;q=0.8,de;q=0.7,fr;q=0.6"}

MARKERS = [
    ("cloudflare", re.compile(r"just a moment\.\.\.|cf-chl-|cf_chl_opt|attention required! \| cloudflare|"
                              r"cf-error-details|challenges\.cloudflare\.com", re.I)),
    ("perimeterx", re.compile(r"robot or human\?|px-captcha|perimeterx|_pxhd|verify your identity|"
                              r"verifica tu identidad", re.I)),
    ("akamai", re.compile(r"access denied.{0,200}reference\s*#|errors\.edgesuite\.net", re.I | re.S)),
    ("datadome", re.compile(r"datadome|dd_cookie_test|geo\.captcha-delivery\.com", re.I)),
    ("imperva", re.compile(r"incapsula|_incapsula_resource|pardon our interruption|distil_r_captcha", re.I)),
    ("captcha", re.compile(r"g-recaptcha|hcaptcha\.com/1/api|are you a robot|captcha-container", re.I)),
]


# 台账默认在本目录；部署包里没有台账时回落到同级「海外」目录（台账为 csv，不入库）
LEDGER_CANDIDATES = ["爬取进度.csv", os.path.join("..", "海外", "爬取进度.csv")]


def load_ledger(path: str = "") -> list[dict]:
    path = path or next((p for p in LEDGER_CANDIDATES if os.path.exists(p)), LEDGER_CANDIDATES[0])
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    for i, r in enumerate(rows[1:], start=2):
        r = r + [""] * (7 - len(r))
        url = r[4].strip()
        if not url.lower().startswith("http"):
            continue
        task = "SPEC" if "spec" in r[3].lower() else ("零售" if "价格" in r[3] else r[3])
        out.append({"line": i, "region": r[0], "country": r[1], "brand": r[2],
                    "task": task, "url": url, "status": r[5]})
    return out


def _host(u: str) -> str:
    h = urlsplit(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def _root_domain(h: str) -> str:
    parts = h.split(".")
    if len(parts) >= 3 and parts[-2] in ("com", "co", "net", "org", "gob", "gov"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def classify(status: int, html: str, req_url: str, final_url: str) -> str:
    head = (html or "")[:60000]
    for name, rx in MARKERS:
        if rx.search(head):
            # 正常页面里也可能引用 recaptcha 脚本：只在页面很短或状态非 200 时判 captcha
            if name == "captcha" and status == 200 and len(html) > 30000:
                continue
            return name
    if status in (403, 401):
        return "http_403"
    if status == 429:
        return "http_429"
    if status >= 500:
        return "http_5xx"
    if status == 404:
        return "http_404"
    if final_url and _root_domain(_host(final_url)) != _root_domain(_host(req_url)):
        return "geo_redirect"
    if status == 200 and len(html) < 1500:
        return "thin_page"
    if 200 <= status < 400:
        return "ok"
    return f"http_{status}"


def probe(item: dict, proxy: str, timeout: int) -> dict:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    t = time.time()
    res = dict(item)
    try:
        r = requests.get(item["url"], headers=HDR, proxies=proxies, timeout=timeout,
                         allow_redirects=True, verify=False)
        html = r.text or ""
        res.update(http=r.status_code, final_url=r.url, size=len(html),
                   verdict=classify(r.status_code, html, item["url"], r.url))
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        res["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:80] if m else ""
    except requests.exceptions.Timeout:
        res.update(http=0, verdict="timeout", final_url="", size=0, title="")
    except requests.exceptions.ProxyError as e:
        res.update(http=0, verdict="proxy_error", final_url="", size=0, title=str(e)[:80])
    except requests.exceptions.ConnectionError as e:
        msg = str(e)
        v = "dns_error" if ("NameResolution" in msg or "getaddrinfo" in msg) else "conn_error"
        res.update(http=0, verdict=v, final_url="", size=0, title=msg[:80])
    except Exception as e:  # noqa: BLE001
        res.update(http=0, verdict="error", final_url="", size=0, title=f"{type(e).__name__}"[:80])
    res["secs"] = round(time.time() - t, 1)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:7877")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--only", default="", help="逗号分隔的区域前缀，如 北美线,欧洲线")
    ap.add_argument("--task", default="全部", choices=["全部", "零售", "SPEC"])
    ap.add_argument("--ledger", default="", help="台账 CSV 路径（缺省自动查找）")
    ap.add_argument("--tag", default="",
                    help="输出文件名后缀（如 UK），避免同一天换节点重测时覆盖之前的结果")
    args = ap.parse_args()

    items = load_ledger(args.ledger)
    if args.only:
        pref = [p.strip() for p in args.only.split(",") if p.strip()]
        items = [x for x in items if any(x["region"].startswith(p) for p in pref)]
    if args.task != "全部":
        items = [x for x in items if x["task"] == args.task]
    # 同一 URL 只探一次
    seen, uniq = set(), []
    for x in items:
        if x["url"] not in seen:
            seen.add(x["url"])
            uniq.append(x)

    print(f"[CFG] 代理={args.proxy or '直连'} 站点={len(uniq)} 并发={args.workers} 超时={args.timeout}s",
          flush=True)
    results = []
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(probe, x, args.proxy, args.timeout) for x in uniq]
        for n, f in enumerate(cf.as_completed(futs), 1):
            r = f.result()
            results.append(r)
            if n % 20 == 0 or n == len(futs):
                print(f"  进度 {n}/{len(futs)}", flush=True)

    results.sort(key=lambda r: r["line"])
    stamp = dt.date.today().strftime("%Y%m%d") + (f"_{args.tag}" if args.tag else "")
    out_csv = f"data/连通性体检_{stamp}.csv"
    cols = ["line", "region", "country", "brand", "task", "status", "url", "verdict",
            "http", "final_url", "size", "secs", "title"]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(results)

    # 汇总
    L = [f"# 连通性体检（{stamp}）\n",
         f"> 代理：`{args.proxy or '直连'}`　站点：{len(results)}　单次 GET，不重试\n",
         "## 判定分布\n", "| 判定 | 数量 |", "|---|---|"]
    for k, v in Counter(r["verdict"] for r in results).most_common():
        L.append(f"| {k} | {v} |")
    L.append("\n## 按区域\n")
    by = defaultdict(Counter)
    for r in results:
        by[(r["region"], r["task"])][r["verdict"]] += 1
    L.append("| 区域 | 类型 | 总数 | ok | 主要问题 |")
    L.append("|---|---|---|---|---|")
    for (reg, tk), c in sorted(by.items()):
        tot = sum(c.values())
        bad = ", ".join(f"{k}={v}" for k, v in c.most_common() if k != "ok")
        L.append(f"| {reg} | {tk} | {tot} | {c.get('ok', 0)} | {bad or '-'} |")
    L.append("\n## 台账标「需代理」的站，本次结果\n")
    L.append("| 国家 | 站点 | 判定 | HTTP | 标题 |")
    L.append("|---|---|---|---|---|")
    for r in results:
        if "代理" in r["status"]:
            L.append(f"| {r['country']} | {r['brand']} | {r['verdict']} | {r['http']} | {r.get('title','')[:40]} |")
    out_md = f"data/连通性体检_{stamp}.md"
    open(out_md, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"[OUT] {out_csv}\n[OUT] {out_md}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
