"""诊断：Costco PDP 点开 Member Reviews 标签后，评价是否渲染、能否解析。

用法：
    py -3.12 scripts/diag_costco_reviews.py --url <PDP> [--tab "Member Reviews"]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                                       # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Costco 评价标签诊断")
    p.add_argument("--url", required=True)
    p.add_argument("--tab", default="Member Reviews")
    args = p.parse_args()

    from playwright.sync_api import sync_playwright

    launch: dict = {"headless": config.HEADLESS, "args": config.BROWSER_ARGS}
    if config.BROWSER_EXECUTABLE:
        launch["executable_path"] = config.BROWSER_EXECUTABLE
    if config.PROXY:
        launch["proxy"] = {"server": config.PROXY}

    with sync_playwright() as pw:
        browser = None
        for channel in ["msedge", "chrome", "chromium"]:
            try:
                browser = pw.chromium.launch(channel=channel, **launch)
                break
            except Exception as e:
                print(f"[launch {channel}] {type(e).__name__}: {e}")
        if browser is None:
            browser = pw.chromium.launch(**launch)
        ctx = browser.new_context(locale="en-CA")
        page = ctx.new_page()
        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(5000)

        def try_click():
            for sel in [f"[role=tab]:has-text('{args.tab}')",
                        f"button:has-text('{args.tab}')",
                        f"a:has-text('{args.tab}')",
                        f"text={args.tab}"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.scroll_into_view_if_needed(timeout=5000)
                        el.click(timeout=8000)
                        return sel
                except Exception as e:
                    print(f"[CLICK] {sel} -> {type(e).__name__}: {e}")
            return ""

        used = try_click()
        print("[CLICK]", used or "NOT FOUND")
        page.wait_for_timeout(6000)
        for _ in range(10):
            page.mouse.wheel(0, 1800)
            page.wait_for_timeout(800)
        page.wait_for_timeout(4000)

        stats = page.evaluate("""() => {
            const q = (s) => document.querySelectorAll(s).length;
            const txt = (s) => { const e=document.querySelector(s); return e? e.innerText.trim().slice(0,120):''; };
            return {
              bv_item: q('.bv-content-item'),
              bv_list: q('ol.bv-content-list'),
              bv_main: q('.bv_main_container'),
              avg: txt('.bv_avgRating_component_container'),
              cnt: txt('.bv_numReviews_text, .bv_numReviews_component_container'),
              first_title: txt('.bv-content-title'),
              first_body: txt('.bv-content-summary-body-text'),
              first_author: txt('.bv-author'),
              body_snippet: document.body.innerText.slice(0, 0),
            };
        }""")
        print("[DOM]", json.dumps(stats, ensure_ascii=False))

        cookies = [{"name": c["name"], "domain": c["domain"]}
                   for c in ctx.cookies() if "bazaarvoice" in c["domain"]]
        print("[BV_COOKIES]", json.dumps(cookies, ensure_ascii=False))

        html = page.content()
        dest = PROJECT_ROOT / "data" / "_smoke" / "pdp_costco_ca_reviews.html"
        dest.write_text(html, encoding="utf-8")
        print(f"[DUMP] {dest} len={len(html)}")
        page.screenshot(path=str(PROJECT_ROOT / "data" / "_smoke" / "pdp_reviews_shot.png"))
        ctx.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
