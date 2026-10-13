"""用 Playwright 打开一个有界面的浏览器（优先 Edge），仅验证能弹出窗口。

不涉及任何业务流程。优先用本机已装的 Edge，其次 Chrome，最后 Playwright 自带 Chromium。

用法:
    python open_edge_demo.py
    python open_edge_demo.py https://open.cqccms.com.cn/open-dev/index.html
"""
from __future__ import annotations

import sys


def main(url: str = "about:blank") -> None:
    try:
        from playwright.sync_api import Error as PWError
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("需要 Playwright：pip install playwright")

    channels = ["msedge", "chrome", "chromium"]
    with sync_playwright() as p:
        browser = None
        used = None
        last = None
        for ch in channels:
            kw = {"headless": False, "args": ["--start-maximized"]}
            if ch != "chromium":
                kw["channel"] = ch
            try:
                browser = p.chromium.launch(**kw)
                used = ch
                break
            except PWError as e:
                last = e
                continue
        if browser is None:
            raise SystemExit(f"无法启动浏览器（试过 {channels}）：{last}")

        print(f"已用 {used} 打开浏览器，版本 {browser.version}", flush=True)
        ctx = browser.new_context(no_viewport=True)
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded")
        print(f"已打开页面：{url}", flush=True)
        input("浏览器窗口已弹出。按回车关闭...")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "about:blank")
