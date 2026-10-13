"""探测目标站点是否提供 JSON-LD 结构化数据（schema.org Product）。

若可用，则通用适配器可不依赖站点专属 CSS 选择器就拿到
name / sku / brand / model / price / aggregateRating，通用性大幅提升。
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

CANDIDATES = [
    ("amazon_ca_product", "https://www.amazon.ca/dp/B0GPHMTMLC"),
    ("samsung_ca_tv_list", "https://www.samsung.com/ca/televisions/all-televisions/"),
    ("tcl_ca_home", "https://ca-en.tcl.com/"),
    ("philips_ca_home", "https://www.philips.ca/"),
]

WANT = ("name", "sku", "mpn", "model", "brand", "offers", "aggregateRating", "review")


def walk_types(node, found):
    """递归收集所有 @type 与关注字段。"""
    if isinstance(node, dict):
        t = node.get("@type")
        if t:
            types = t if isinstance(t, list) else [t]
            for x in types:
                found.setdefault(str(x), set())
                for k in node:
                    if k.lower() in [w.lower() for w in WANT]:
                        found[str(x)].add(k)
        for v in node.values():
            walk_types(v, found)
    elif isinstance(node, list):
        for v in node:
            walk_types(v, found)


def probe(page, name, url):
    print(f"\n--- {name}  {url}")
    try:
        r = page.goto(url, wait_until="domcontentloaded", timeout=35000)
        print(f"    HTTP={r.status if r else None}  标题={(page.title() or '')[:50]!r}")
    except Exception as e:
        print(f"    打开失败: {type(e).__name__}: {str(e).splitlines()[0][:90]}")
        return
    try:
        blocks = page.locator('script[type="application/ld+json"]')
        n = blocks.count()
        print(f"    JSON-LD 块数 = {n}")
        found = {}
        parsed_ok = 0
        for i in range(n):
            try:
                raw = blocks.nth(i).inner_text(timeout=3000)
                data = json.loads(raw)
                parsed_ok += 1
                walk_types(data, found)
            except Exception:
                continue
        print(f"    可解析块 = {parsed_ok}")
        if found:
            for t, keys in sorted(found.items()):
                mark = " ★" if t.lower() in ("product", "offer", "aggregaterating") else ""
                print(f"      @type={t}{mark}  关注字段={sorted(keys) if keys else '-'}")
        else:
            print("      未发现可用 @type")
    except Exception as e:
        print(f"    解析异常: {type(e).__name__}: {str(e)[:90]}")


def main():
    urls = CANDIDATES
    if len(sys.argv) > 1:
        urls = [(f"arg{i}", u) for i, u in enumerate(sys.argv[1:], 1)]
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True,
                              args=["--disable-blink-features=AutomationControlled"])
        ctx = b.new_context(user_agent=UA, locale="en-CA",
                            viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        for name, url in urls:
            probe(pg, name, url)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
