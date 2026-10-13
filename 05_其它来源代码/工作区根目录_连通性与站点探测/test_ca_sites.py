"""通过服务器远程浏览器（ws 端点）批量测试一批网站在服务器上的可达性。

前提：
- 服务器已用 `playwright launch-server --browser chromium --config ...` 起好服务；
- 本地已建立 SSH 隧道：ssh -N -L 9333:127.0.0.1:9333 hisense@10.18.87.51
- 本地用装了 Playwright 的 Python 运行本脚本。

用法（本地 Windows）：
    & "C:\\Users\\likunyuan\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" test_ca_sites.py ws://127.0.0.1:9333/xxxx
若不传 ws 参数，则用下面 DEFAULT_WS。
"""
from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright

DEFAULT_WS = "ws://127.0.0.1:9333/7709ba49f1d96d8e6b5bd483f0580883"

SITES = [
    ("Amazon",        "https://www.amazon.ca/"),
    ("Bestbuy",       "https://www.bestbuy.ca/en-ca"),
    ("Walmart",       "https://www.walmart.ca/en"),
    ("Costco",        "https://www.costco.ca/"),
    ("Brick",         "https://www.thebrick.com/"),
    ("Leons",         "https://www.leons.ca/"),
    ("Visions",       "https://www.visions.ca/"),
    ("CanadianTire",  "https://www.canadiantire.ca/en.html"),
    ("Hisense",       "https://www.hisense-canada.com/"),
    ("Samsung",       "https://www.samsung.com/ca/"),
    ("TCL",           "https://ca-en.tcl.com/"),
    ("LG",            "https://www.lg.com/ca_en"),
    ("Sony",          "https://www.sony.ca/"),
    ("Philips",       "https://www.philips.ca/"),
]

BLOCK_MARKERS = ("just a moment", "attention required", "checking your browser",
                 "access denied", "cloudflare", "验证", "robot")

NAV_TIMEOUT = 30000


def main(ws: str) -> int:
    print(f"ws 端点 : {ws}")
    print(f"待测站点: {len(SITES)} 个（服务器网络）\n", flush=True)
    failures = 0
    with sync_playwright() as p:
        b = p.chromium.connect(ws)
        ctx = b.new_context(ignore_https_errors=True, locale="en-CA")
        for name, url in SITES:
            print(f"-> {name} {url}", flush=True)
            pg = ctx.new_page()
            t0 = time.time()
            status = None
            title = ""
            note = ""
            ok = False
            try:
                r = pg.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
                status = r.status if r else None
                try:
                    title = (pg.title() or "").strip()
                except Exception:
                    title = ""
                low = title.lower()
                blocked = any(m in low for m in BLOCK_MARKERS)
                ok = (status is not None and status < 400 and not blocked)
                if blocked:
                    note = "疑似拦截/人机验证"
            except Exception as e:  # noqa: BLE001
                note = f"{type(e).__name__}: {str(e).splitlines()[0][:80]}"
            finally:
                pg.close()
            dt = time.time() - t0
            mark = "PASS" if ok else "FAIL"
            if not ok:
                failures += 1
            print(f"   [{mark}] HTTP={status} 用时={dt:.1f}s 标题={title[:50]!r}"
                  + (f" {note}" if note else ""), flush=True)
        b.close()
    print(f"\n结果：{len(SITES) - failures}/{len(SITES)} 可访问，{failures} 失败。")
    return failures


if __name__ == "__main__":
    ws = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_WS
    sys.exit(1 if main(ws) else 0)
