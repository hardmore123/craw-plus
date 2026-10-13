# -*- coding: utf-8 -*-
"""对 HTTP 体检未通过的站，用真实浏览器（Playwright + 代理）复测一次首页。

与真实抓取一致：msedge 通道、headless、AutomationControlled 关闭、同一代理。
每站：打开首页 → 等 8s 让 Cloudflare/JS 挑战自行完成 → 判定。单站 45s 硬超时，不重试。
并发 4 个上下文，避免对代理/站点造成压力。

用法：
  py -3.12 scripts/connectivity_browser_recheck.py [--in data/连通性体检_YYYYMMDD.csv]
        [--proxy http://127.0.0.1:7877] [--concurrency 4]
产出：data/连通性体检_浏览器复测_<日期>.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import glob
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from connectivity_check import classify  # noqa: E402  复用同一套判定规则

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0")
NAV_TIMEOUT_MS = 30000


async def probe(browser, row: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        out = dict(row)
        t = time.time()
        ctx = await browser.new_context(user_agent=UA, locale="en-US",
                                        viewport={"width": 1440, "height": 900},
                                        ignore_https_errors=True)
        page = await ctx.new_page()
        try:
            async def run():
                resp = await page.goto(row["url"], wait_until="domcontentloaded",
                                       timeout=NAV_TIMEOUT_MS)
                status = resp.status if resp else 0
                await page.wait_for_timeout(8000)   # 给 CF/JS 挑战时间自动通过
                html = await page.content()
                return status, html
            status, html = await asyncio.wait_for(run(), timeout=NAV_TIMEOUT_MS / 1000 + 20)
            title = await page.title()
            # 挑战通过后页面会刷新为 200，最终状态以当前内容判定
            v = classify(status, html, row["url"], page.url)
            if v in ("http_403", "http_429") and len(html) > 30000 and not any(
                    k in title.lower() for k in ("denied", "forbidden", "blocked",
                                                 "just a moment", "attention", "security")):
                v = "ok"   # 首个响应 403 但挑战后渲染出完整页面
            out.update(b_verdict=v, b_http=status, b_size=len(html),
                       b_title=re.sub(r"\s+", " ", title)[:80], b_final=page.url)
        except asyncio.TimeoutError:
            out.update(b_verdict="timeout", b_http=0, b_size=0, b_title="", b_final="")
        except Exception as e:  # noqa: BLE001
            msg = str(e).split("\n")[0][:80]
            v = "conn_error"
            if "ERR_NAME_NOT_RESOLVED" in msg:
                v = "dns_error"
            elif "ERR_PROXY" in msg or "ERR_TUNNEL" in msg:
                v = "proxy_error"
            elif "Timeout" in msg:
                v = "timeout"
            out.update(b_verdict=v, b_http=0, b_size=0, b_title=msg, b_final="")
        finally:
            out["b_secs"] = round(time.time() - t, 1)
            await ctx.close()
        print(f"  {out['b_verdict']:12} {out['country']:6} {out['brand'][:22]}", flush=True)
        return out


async def amain(args) -> int:
    from playwright.async_api import async_playwright

    global NAV_TIMEOUT_MS
    NAV_TIMEOUT_MS = args.nav_timeout * 1000
    src = args.inp or sorted(glob.glob("data/连通性体检_2*.csv"))[-1]
    rows = list(csv.DictReader(open(src, encoding="utf-8-sig")))
    if args.verdicts:
        # 复测指定判定（如上一轮浏览器复测的 timeout），读的是浏览器复测结果文件
        want = set(args.verdicts.split(","))
        key = "b_verdict" if "b_verdict" in rows[0] else "verdict"
        todo = [r for r in rows if r.get(key) in want]
        rows = [{k: v for k, v in r.items() if not k.startswith("b_")} for r in rows]
        todo = [{k: v for k, v in r.items() if not k.startswith("b_")} for r in todo]
    else:
        todo = [r for r in rows if r["verdict"] != "ok"]
    print(f"[CFG] 来源 {src}；需复测 {len(todo)}/{len(rows)}；代理 {args.proxy}", flush=True)

    sem = asyncio.Semaphore(args.concurrency)
    async with async_playwright() as pw:
        browser = None
        for ch in ("msedge", "chrome", None):
            try:
                kw = dict(headless=True, proxy={"server": args.proxy},
                          args=["--disable-blink-features=AutomationControlled"])
                if ch:
                    kw["channel"] = ch
                browser = await pw.chromium.launch(**kw)
                print(f"[CFG] 浏览器通道 {ch or 'chromium'}", flush=True)
                break
            except Exception as e:  # noqa: BLE001
                print(f"[CFG] 通道 {ch} 启动失败: {str(e)[:80]}", flush=True)
        if browser is None:
            print("[ERR] 无可用浏览器")
            return 2
        results = await asyncio.gather(*(probe(browser, r, sem) for r in todo))
        await browser.close()

    stamp = dt.date.today().strftime("%Y%m%d")
    out = args.out or f"data/连通性体检_浏览器复测_{stamp}.csv"
    cols = list(rows[0].keys()) + ["b_verdict", "b_http", "b_size", "b_secs", "b_title", "b_final"]
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(results, key=lambda r: int(r["line"])))
    print(f"[OUT] {out}", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="")
    ap.add_argument("--proxy", default="http://127.0.0.1:7877")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--nav-timeout", type=int, default=30, help="页面导航超时（秒）")
    ap.add_argument("--verdicts", default="",
                    help="只复测这些判定（逗号分隔），如 timeout,conn_error")
    ap.add_argument("--out", default="")
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
