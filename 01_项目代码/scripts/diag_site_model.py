# -*- coding: utf-8 -*-
"""单站单型号逐步诊断：搜索 URL → 候选 → match_product → 详情页抽取 → 型号校验 → 价格。

与全量入口 crawl_ca_retail 用同一套函数（_search_url / _parse_search_with_spec /
_detail_payload / _payload_matches_model / _fill_api_price），只读不写库，用于定位
readiness 实测里的 FAIL/PARTIAL 根因。

用法：
  py -3.12 scripts/diag_site_model.py --site oechsle_pe --brand Samsung --model 55U8000FG
  py -3.12 scripts/diag_site_model.py --site x --brand B --model M --keyword "Samsung tv"   # 测品牌池
  可选覆盖：--container "<css>"  --search-api vtex_catalog  --detail 2（打开前 N 个候选）
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import crawl_ca_retail as C  # noqa: E402
from overseas.mx_retail import _parse_search_with_spec  # noqa: E402
from overseas.retail_spec import explain_no_match, match_product  # noqa: E402
from overseas.scenarios import open_dom  # noqa: E402
from overseas.sites import SiteRegistry  # noqa: E402


def discover_containers(html: str, base_url: str, brand: str, top: int = 5) -> list[tuple[str, int, list[str]]]:
    """从已渲染的搜索页 HTML 里反推「商品卡片链接」选择器（spec.search.container 候选）。

    思路：把所有 <a href> 按「锚点 class / 父节点 class / 路径首段」分组，
    组内链接的文字或 href 含品牌名且含数字（型号/尺寸）的**不同商品 URL** 越多，越像商品卡片。
    返回 [(selector, 命中数, 样例 href)]，按命中数降序。
    """
    import re
    from collections import defaultdict
    from urllib.parse import urlsplit
    try:
        from lxml import html as LH
    except ImportError:
        return []
    try:
        root = LH.fromstring(html or "<html/>")
    except Exception:  # noqa: BLE001
        return []
    host = urlsplit(base_url).netloc.lower().replace("www.", "")
    bl = (brand or "").lower()
    bad_path = re.compile(r"/(search|buscar|busca|pretraga|haku|login|account|cart|help|category|categor)",
                          re.I)
    groups: dict[str, set] = defaultdict(set)
    for a in root.iter("a"):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript", "mailto")):
            continue
        full = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")
        u = urlsplit(full)
        if host and host not in u.netloc.lower():
            continue
        if bad_path.search(u.path) or len(u.path) < 6:
            continue
        text = " ".join(a.itertext()).strip().lower()
        blob = text + " " + u.path.lower()
        if bl and bl not in blob:
            continue
        if not re.search(r"\d{2}", blob):
            continue
        keys = []
        cls = [c for c in (a.get("class") or "").split() if c and not re.search(r"\d{3,}", c)]
        if cls:
            keys.append("a." + cls[0])
        par = a.getparent()
        for _ in range(3):
            if par is None:
                break
            pc = [c for c in (par.get("class") or "").split() if c and not re.search(r"\d{3,}", c)]
            if pc:
                keys.append(f".{pc[0]} a[href]")
                break
            par = par.getparent()
        if re.search(r"/p/\d", u.path):
            keys.append("a[href*='/p/']")          # SAP Hybris 系（Alkosto 等）
        seg = [s for s in u.path.split("/") if s]
        if seg and len(seg) >= 2 and len(seg[0]) <= 12:
            keys.append(f"a[href*='/{seg[0]}/']")
        if u.path.rstrip("/").endswith("/p"):
            keys.append("a[href$='/p']")
        if re.search(r"\.html?$", u.path):
            keys.append("a[href$='.html']")
        for k in keys:
            groups[k].add(u.scheme + "://" + u.netloc + u.path)
    ranked = sorted(((k, len(v), sorted(v)[:3]) for k, v in groups.items()),
                    key=lambda x: -x[1])
    return ranked[:top]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--brand", default="")
    ap.add_argument("--model", required=True)
    ap.add_argument("--keyword", default="", help="搜索词（缺省 '<brand> <model>'）")
    ap.add_argument("--container", default="")
    ap.add_argument("--search-api", default="")
    ap.add_argument("--template", default="", help="覆盖 search.search_url_template，如 {base}/search?text={q}")
    ap.add_argument("--detail", type=int, default=1)
    ap.add_argument("--discover", action="store_true",
                    help="从搜索页反推商品卡片链接选择器（spec.search.container 候选）")
    a = ap.parse_args()

    ad = SiteRegistry.get(a.site)
    spec = C._resolve_site_spec(a.site, None) or {}
    if a.container:
        spec.setdefault("search", {})["container"] = a.container
    if a.search_api:
        spec.setdefault("search", {})["api"] = {"type": a.search_api}
    if a.template:
        spec.setdefault("search", {})["search_url_template"] = a.template
    sf, df = C._make_fetcher(ad, spec)
    kw = a.keyword or f"{a.brand} {a.model}".strip()
    url = C._search_url(ad, spec, kw)
    print("adapter.base_url:", ad.base_url, "| requires_browser:", ad.requires_browser)
    print("search_url:", url)
    s_cfg = spec.get("search") or {}
    hits = []
    try:
        with open_dom(ad, sf, url, wait_selector=s_cfg.get("wait_selector") or "a",
                      scroll_passes=int(s_cfg.get("scroll_passes") or 3),
                      extra_wait_ms=int(s_cfg.get("wait_ms", 0) or 5000)) as (res, dom, html):
            print(f"search: status={res.status} blocked={res.blocked}:{res.block_reason} "
                  f"err={res.error!r} html={len(html or '')}")
            if dom is not None or s_cfg.get("api"):
                hits = _parse_search_with_spec(spec, ad, dom, html, limit=20)
            if a.discover and html:
                print("discover (selector, 商品链接数, 样例):")
                for sel, n, ex in discover_containers(html, ad.base_url, a.brand):
                    print(f"  {n:3}  {sel}   e.g. {ex[:2]}")
    except Exception as e:  # noqa: BLE001
        print("search EXC:", type(e).__name__, str(e)[:200])
    print(f"candidates: {len(hits)}")
    for h in hits[:12]:
        print(f"  - {(h.title or '')[:80]!r} | {(h.url or h.sku)[:100]} | api_price={h.api_price}")
    t = match_product(spec, hits, brand=a.brand, model=a.model)
    print("match_product ->", getattr(t, "url", None))
    if t is None and hits:
        print("  why:", explain_no_match(spec, hits, brand=a.brand, model=a.model))
    for h in ([t] if t else hits[:a.detail]):
        pu = h.url or ad.product_url(h.sku)
        try:
            with open_dom(ad, df, pu, wait_selector=getattr(ad, "retail_page_wait", "body"),
                          scroll_passes=3, extra_wait_ms=2500) as (res, dom, html):
                print(f"PDP {pu[:110]} status={res.status} blocked={res.blocked}:{res.block_reason}")
                if dom is None:
                    continue
                p = C._detail_payload(ad, spec, dom, html, h.sku, pu)
                ok = C._payload_matches_model(a.model, p, spec)
                C._fill_api_price(p, h)
                print(f"   spec_drives={C._spec_drives_detail(ad, spec)} title={(p.product.title or '')[:80]!r}")
                print(f"   model={p.product.model!r} price={p.price.price if p.price else None} "
                      f"currency={p.price.currency if p.price else ''} reviews_on_page={len(p.reviews)}")
                print(f"   model_match={ok}")
        except Exception as e:  # noqa: BLE001
            print("PDP EXC:", type(e).__name__, str(e)[:200])
    sf.close()
    if df is not sf:
        df.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
