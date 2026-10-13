"""诊断：用真实浏览器加载页面并捕获网络请求，定位"评价/价格"走的接口。

用法：
    py -3.12 scripts/diag_retail_network.py --url <PDP> --match bazaarvoice,review,/api/
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
    p = argparse.ArgumentParser(description="页面网络请求诊断")
    p.add_argument("--url", required=True)
    p.add_argument("--match", default="bazaarvoice,review,/api/,rest/")
    p.add_argument("--wait", type=int, default=12000)
    p.add_argument("--scroll", type=int, default=12)
    p.add_argument("--click-text", default="", help="点开含该文字的按钮/标签（如 Reviews）")
    p.add_argument("--xhr-only", action="store_true",
                   help="只列 XHR/fetch 请求（找站点的数据接口）")
    args = p.parse_args()
    keys = [k.strip().lower() for k in args.match.split(",") if k.strip()]

    from playwright.sync_api import sync_playwright

    launch: dict = {"headless": config.HEADLESS, "args": config.BROWSER_ARGS}
    if config.BROWSER_EXECUTABLE:
        launch["executable_path"] = config.BROWSER_EXECUTABLE
    if config.PROXY:
        launch["proxy"] = {"server": config.PROXY}

    hits: list[dict] = []
    xhr_bodies: list[dict] = []
    with sync_playwright() as pw:
        browser = None
        ctx = None
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

        def on_response(resp):
            u = resp.url
            low = u.lower()
            matched = (resp.request.resource_type in ("xhr", "fetch")
                       if args.xhr_only else any(k in low for k in keys))
            if matched:
                rec = {"status": resp.status, "url": u[:300],
                       "type": resp.headers.get("content-type", "")}
                hits.append(rec)
                if any(t in rec["type"] for t in ("json", "text")):
                    try:
                        body = resp.text()
                        if body and len(body) > 40:
                            xhr_bodies.append({"url": u[:200], "len": len(body),
                                               "head": body[:400]})
                    except Exception:
                        pass

        def on_request(req):
            low = req.url.lower()
            if "bazaarvoice" in low and ("data" in low or "api" in low):
                hdrs = {k.lower(): v for k, v in req.headers.items()
                        if k.lower() in ("bv-bfd-token", "authorization", "cookie",
                                         "x-bv-client", "referer", "origin",
                                         "content-type", "accept")}
                print("[REQ]", req.method, req.url[:220])
                print("      headers:", json.dumps(hdrs, ensure_ascii=False)[:600])

        page.on("response", on_response)
        page.on("request", on_request)
        page.goto(args.url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        for _ in range(args.scroll):
            page.mouse.wheel(0, 2600)
            page.wait_for_timeout(900)
        if args.click_text:
            for sel in [f"text={args.click_text}", f"button:has-text('{args.click_text}')",
                        f"a:has-text('{args.click_text}')"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.click(timeout=5000)
                        page.wait_for_timeout(6000)
                        print(f"[CLICK] {sel} ok")
                        break
                except Exception as e:
                    print(f"[CLICK] {sel} -> {type(e).__name__}")
            for _ in range(6):
                page.mouse.wheel(0, 2600)
                page.wait_for_timeout(900)
        page.wait_for_timeout(args.wait)
        # 统计评价相关 DOM
        stats = page.evaluate("""() => {
            const q = (s) => document.querySelectorAll(s).length;
            return {
              bv_item: q('ol.bv-content-list li.bv-content-item, .bv-content-item'),
              bv_main: q('.bv_main_container'),
              bv_container: q('#CostcoBVReviewContainer'),
              tabs: [...document.querySelectorAll('[role=tab],button')].map(e=>e.innerText.trim()).filter(t=>t&&t.length<40).slice(0,40),
              productId: (document.querySelector('[data-bv-product-id]')||{}).dataset?.bvProductId || '',
            };
        }""")
        print("[DOM]", json.dumps(stats, ensure_ascii=False))
        try:
            page.screenshot(path=str(PROJECT_ROOT / "data" / "_smoke" / "pdp_shot.png"),
                            full_page=False)
        except Exception:
            pass
        ctx.close()
        browser.close()

    print(f"[NET] hits={len(hits)}")
    seen = set()
    for h in hits:
        key = h["url"].split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        print(json.dumps(h, ensure_ascii=False))
    print(f"[BODIES] {len(xhr_bodies)}")
    for b in xhr_bodies[:8]:
        print(json.dumps(b, ensure_ascii=False)[:600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
