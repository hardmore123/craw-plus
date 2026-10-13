# -*- coding: utf-8 -*-
"""Magento/HTML 站全目录在售电视价格抓取（panafoto/raenco/espana/coral 等）。

对每个站：搜索 "televisor" 收集商品卡（标题+URL），抓前 N 个商品页 JSON-LD 拿价格。
Magento SSR 站 HTTP 直抓即可。输出每站 CSV + 合并文件。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from urllib.parse import quote

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml",
}

# site -> (host, 国家, 币种, 搜索路径 {q})
SITES = {
    "falabella_pe": ("www.falabella.com.pe", "秘鲁", "PEN", "/buscar?q={q}"),
    "espana_ec": ("almacenesespana.ec", "厄瓜多尔", "USD", "/catalogsearch/result/?q={q}"),
    "coral_ec": ("coralhipermercados.com", "厄瓜多尔", "USD", "/catalogsearch/result/?q={q}"),
    "artefacta_ec": ("www.artefacta.com", "厄瓜多尔", "USD", "/catalogsearch/result/?q={q}"),
    "falabella_co": ("www.falabella.com.co", "哥伦比亚", "COP", "/search?q={q}"),
    "falabella_cl": ("www.falabella.com", "智利", "CLP", "/buscador?q={q}"),
    "panafoto_pa": ("panafoto.com", "巴拿马", "USD", "/catalogsearch/result/?q={q}"),
    "raenco_pa": ("www.raenco.com", "巴拿马", "USD", "/catalogsearch/result/?q={q}"),
    "evision_pa": ("www.evisionstore.com", "巴拿马", "USD", "/buscar?q={q}"),
    "unicomer_gt": ("www.lacuracaonline.com", "危地马拉", "GTQ", "/catalogsearch/result/?q={q}"),
}


def get(url: str) -> tuple[int, str]:
    try:
        r = requests.get(url, proxies=PROXY, headers=HDR, timeout=20, verify=False,
                         allow_redirects=True)
        return r.status_code, r.text or ""
    except Exception:
        return 0, ""


def extract_cards(html: str, host: str) -> list[dict]:
    """Magento 卡提取：URL + 标题。去重，过滤非商品链接。"""
    cards = []
    seen = set()
    # 1) product-item-link（Magento 标准）
    for m in re.finditer(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*product-item-link'
            r'[^"\']*["\'][^>]*>\s*([^<]{5,200})<', html, re.I):
        u, t = m.group(1).strip(), re.sub(r"\s+", " ", m.group(2).strip())
        if not u.startswith("http"):
            u = f"https://{host}{u}"
        u = u.split("?")[0].split("#")[0]
        if u not in seen and t:
            seen.add(u)
            cards.append({"url": u, "title": t})
    # 2) 通用商品链接（含 /p/ /product /xxx.html）
    if not cards:
        esc = re.escape(host)
        for m in re.finditer(
                rf'<a[^>]+href=["\'](https?://{esc}/[^"\']+)["\'][^>]*>\s*([^<]{{6,180}})</a>',
                html, re.S):
            url, title = m.group(1), re.sub(r"\s+", " ", m.group(2).strip())
            low = url.lower()
            if any(x in low for x in (".css", ".js", ".png", ".jpg", ".webp",
                                      "login", "cart", "cuenta", "facebook",
                                      "youtube", "instagram", "whatsapp")):
                continue
            if not any(x in title.lower() for x in ("televis", "tv", "qled",
                                                    "oled", "uled", "smart")):
                continue
            url = url.split("?")[0]
            if url not in seen:
                seen.add(url)
                cards.append({"url": url, "title": title})
    return cards


def page_price(html: str):
    """从商品页 JSON-LD 或正则提取价格。"""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>',
                         html, re.S):
        s = m.group(1).strip()
        if '"Product"' not in s and '"product"' not in s[:40]:
            continue
        try:
            d = json.loads(s)
        except Exception:
            continue
        off = d.get("offers")
        if isinstance(off, list):
            off = off[0] if off else {}
        if isinstance(off, dict) and off.get("price"):
            return off["price"]
    # 正则兜底：S/ 或 $ 或数字
    m = re.search(r'(?:s/|S/|Q|USD|[$])\s?([\d][\d.,]{2,})', html)
    if m:
        return m.group(1)
    m2 = re.search(r'class="[^"]*price[^"]*"[^>]*>\s*(?:[^\d]*)([\d.,]{4,})', html, re.I)
    return m2.group(1) if m2 else None


def main() -> int:
    os.makedirs("data/在售全量", exist_ok=True)
    out_rows = []
    for site, (host, cc, cur, spath) in SITES.items():
        print(f"=== {site} ({host}) ===")
        cards = []
        for kw in ("televisor", "smart tv", "televisores"):
            url = f"https://{host}{spath.format(q=quote(kw))}"
            code, html = get(url)
            if code in (200, 206) and len(html) > 2500 and _not_404(html):
                cards = extract_cards(html, host)
                if cards:
                    print(f"  搜 '{kw}' 得 {len(cards)} 卡")
                    break
        if not cards:
            print("  搜索无结果/404/被拦，跳过")
            continue
        n_priced = 0
        for c in cards[:40]:
            code, ph = get(c["url"])
            p = page_price(ph) if code == 200 else None
            if p:
                n_priced += 1
            out_rows.append({
                "零售站": site, "国家": cc, "币种": cur, "商品名": c["title"][:120],
                "URL": c["url"], "价格": "" if p is None else p,
                "抓取时间": "2026-09-19 16:00:00",
            })
        print(f"  抓 {len(cards[:40])} 卡，有价 {n_priced}")
    if not out_rows:
        print("无任何结果")
        return 0
    out = "data/在售全量/Magento全量价格_合并.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"[OUT] {out} rows={len(out_rows)}")
    from collections import Counter
    print(f"按站: {dict(Counter(r['零售站'] for r in out_rows))}")
    print(f"有价: {sum(1 for r in out_rows if r['价格'])}")
    return 0


def _not_404(html: str) -> bool:
    low = html.lower()[:800]
    return "404" not in low and "no se encontrar" not in low and "ups!" not in low


if __name__ == "__main__":
    raise SystemExit(main())