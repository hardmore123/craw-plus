# -*- coding: utf-8 -*-
"""megamaxi_ec（WooCommerce）全量电视价格抓取：浏览器渲染分类页拿商品-价格对。

结论已验证：分类页渲染后卡片含 `woocommerce-loop-product__title` + `price`（$501.99 等），
一次渲染即可取该分类全部商品名+价格。多分类翻页累计全量。
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ.setdefault("OVERSEAS_PROXY", "http://127.0.0.1:7877")

from overseas.fetchers import BrowserFetcher  # noqa: E402

HOST = "www.megamaxi.com"
CATS = ["televisores", "televisores/", "tv", "categoria-producto/televisores"]


def model_of(t: str) -> str:
    up = t.upper()
    for tok in re.split(r"[^A-Z0-9]+", up):
        if re.fullmatch(r"(?:UN|QN|RN|UA|MR|AU|QE|OLED|LED)[A-Z0-9]{4,12}", tok):
            return tok
    m = re.findall(r"\b(\d{2,3}[A-Z][A-Z0-9]{2,9})\b", up)
    return m[-1] if m else ""


def parse_money(s: str):
    """归一金额到 float；失败/超界返回 None。支持 $501.99 / 1,234.56 / 1.234,56 / 560.08。"""
    if not s:
        return None
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):          # 1.234,56 -> 1234.56
            s = s.replace(".", "").replace(",", ".")
        else:                                     # 1,234.56 -> 1234.56
            s = s.replace(",", "")
    elif "," in s and len(s) - s.rfind(",") - 1 in (1, 2) and s.count(",") == 1:
        s = s.replace(",", ".")                   # 1,99 -> 1.99（小数）
    elif "," in s:
        s = s.replace(",", "")                    # 千分位 1,234
    try:
        v = float(s)
    except ValueError:
        return None
    if v > 10_000_000:                            # 防呆
        return None
    return v


def fetch_category(f: BrowserFetcher, cat: str) -> list[dict]:
    url = f"https://{HOST}/categoria-producto/{cat}"
    out = []
    seen: set[str] = set()
    try:
        with f.page(url, wait_selector="body", settle_ms=5000,
                    scroll_passes=2) as (res, dom):
            html = dom.html() if dom else ""
            # 商品名-价格对（结构已确认：h5.cf_api_regular_price 现价 + h2 标题）
            blocks = re.split(r'(?=<li )|(?<=</li>)', html)
            for blk in blocks:
                if "cf_api_regular_price" not in blk or "cf_api_loop_title" not in blk:
                    continue
                m_price = re.search(r'cf_api_regular_price[^>]*>\s*\$?([0-9][0-9.,]*)', blk)
                m_name = re.search(r'woocommerce-loop-product__title[^>]*title="([^"]+)"', blk) \
                    or re.search(r'woocommerce-loop-product__title[^>]*>([^<]+)<', blk)
                if not m_price or not m_name:
                    continue
                name = re.sub(r"&\w+;", " ", m_name.group(1)).strip()
                price = m_price.group(1).strip()
                fv = parse_money(price)
                if fv is None or fv > 500000:
                    continue
                if not name or name in seen:
                    continue
                seen.add(name)
                out.append({"title": name[:100], "price": f"{fv:g}",
                            "model": model_of(name)})
    except Exception as e:
        print(f"  {cat} ERR {type(e).__name__}: {e}")
    return out


def main() -> int:
    print(f"=== megamaxi_ec ({HOST}) WooCommerce 全量电视价格 ===")
    fetcher = BrowserFetcher()
    all_items: list[dict] = []
    seen = set()
    try:
        for cat in ("televisores", "televisores/tv-led",
                    "televisores/smart-tv", "televisores-4k",
                    "televisores/tvs"):
            items = fetch_category(fetcher, cat)
            print(f"  {cat}: {len(items)} 商品")
            for it in items:
                if it["title"] in seen:
                    continue
                seen.add(it["title"])
                all_items.append(it)
    finally:
        fetcher.close()

    # 写文件
    os.makedirs("data/在售全量", exist_ok=True)
    fname = "data/在售全量/woo_megamaxi_tv.csv"
    with open(fname, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["title", "model", "price"])
        w.writeheader()
        for it in all_items:
            w.writerow(it)
    print(f"\n[OUT] {fname} rows={len(all_items)}")
    for it in all_items[:12]:
        print(f"  {it['model']:<18}{it['price']:>9}USD  {it['title'][:48]}")
    return 0


if __name__ == "__main__":
    main()