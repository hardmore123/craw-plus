# -*- coding: utf-8 -*-
"""自动修复「搜索取不到候选」：探索搜索 URL 形态 + 反推商品卡片选择器，验证后写回唯一 spec。

readiness 实测大量拉美/欧洲站 FAIL 的共同根因是 spec 的搜索层失效：
  - 搜索参数不对（Alkosto 是 /search?text=，adapter 写的 ?q= → 页面只有导航）；
  - 品牌池关键词「{brand} tv」在西语站 0 结果（商品名写 Televisor）；
  - container 选择器随改版失效。
本脚本按 skill「每轮只动一个变量」逐项试，**只有验证通过才写回**：

  1) 关键词 ∈ {"{brand} tv", "{brand} televisor", "{brand}"} × 搜索 URL 模板（adapter 现行 + 常见形态）
     打开搜索页 → discover_containers 打分（含品牌且带数字的不同商品链接数）
  2) 取得分最高的 (模板, 关键词, 选择器)，要求 ≥ min_links 个商品链接
  3) 验证：用该配置做一次真实型号搜索（主库已入库型号），match_product 必须命中，
     且详情页型号校验 _payload_matches_model 通过
  4) 通过 → 写回 spec.search.{search_url_template, container, sku/url/title, batch.keyword_template}
     并在 spec._autofix_search 记录证据；不通过 → 只出报告，不改 spec（宁缺毋滥）

用法：
  py -3.12 scripts/autofix_search.py --sites alkosto_co lider_cl
  py -3.12 scripts/autofix_search.py --from-readiness data/sandbox/readiness_20261009.csv   # 取其中 FAIL 且为搜索失败的站
  加 --dry-run 只报告
产出：data/sandbox/autofix_search_<日期>.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import crawl_ca_retail as C  # noqa: E402
from diag_site_model import discover_containers  # noqa: E402
from overseas.mx_retail import _parse_search_with_spec  # noqa: E402
from overseas.retail_spec import match_product, retail_spec_path, validate_retail_spec  # noqa: E402
from overseas.scenarios import open_dom  # noqa: E402
from overseas.sites import SiteRegistry  # noqa: E402
from readiness_check import positives  # noqa: E402

TEMPLATES = [
    "{base}/search?q={q}", "{base}/search?text={q}", "{base}/search?query={q}",
    "{base}/buscar?q={q}", "{base}/busca?q={q}", "{base}/catalogsearch/result/?q={q}",
    "{base}/search/?q={q}", "{base}/s?k={q}", "{base}/?s={q}&post_type=product",
    "{base}/{q}?_q={q}&map=ft", "{base}/search?keyword={q}", "{base}/search?term={q}",
    # 欧洲常见非标搜索路径（10-11 实测：上面的通用形态在这些站全部 404）
    "{base}/de/search.html?query={q}", "{base}/fr/search.html?query={q}", "{base}/it/search.html?query={q}",
    "{base}/pl/search.html?query={q}", "{base}/de-ch/search.html?query={q}", "{base}/search.html?query={q}",
    "{base}/suche/{q}/", "{base}/suche?q={q}", "{base}/zoeken?query={q}", "{base}/zoeken?q={q}",
    "{base}/recherche?q={q}", "{base}/recherche/?text={q}", "{base}/ricerca?q={q}", "{base}/buscar/?q={q}",
    "{base}/listing.xhtml?q={q}", "{base}/fi/search?query={q}", "{base}/search?query[querystring]={q}",
    "{base}/sr?q={q}", "{base}/arama?q={q}", "{base}/search/?text={q}",
]
KEYWORDS = ["{brand} tv", "{brand} televisor", "{brand}"]


def adapter_template(ad) -> str:
    """把 adapter.search_url 反推成模板（作为首个候选，保持现行行为优先）。"""
    probe = "QQZZQQ"
    try:
        u = ad.search_url(probe)
    except Exception:  # noqa: BLE001
        return ""
    if probe not in u:
        return ""
    return u.replace(ad.base_url.rstrip("/"), "{base}", 1).replace(probe, "{q}")


def open_search(ad, fetcher, spec, url):
    """打开搜索页，返回 (res, 静态 DOM, html)。

    ★ Playwright 的 DOM 出了 open_dom 的 with 就随页面关闭而失效，不能带出去用；
    这里用渲染后的 HTML 重建 lxml DOM，供后续多次解析。
    """
    from overseas.fetchers import LxmlDom
    s_cfg = spec.get("search") or {}
    with open_dom(ad, fetcher, url, wait_selector=s_cfg.get("wait_selector") or "a",
                  scroll_passes=max(3, int(s_cfg.get("scroll_passes") or 3)),
                  extra_wait_ms=max(6000, int(s_cfg.get("wait_ms", 0) or 6000))) as (res, dom, html):
        html = html or ""
    return res, (LxmlDom.parse(html) if html else None), html


_MODEL_TOKEN = None


def _model_tokens(title: str) -> list[str]:
    """标题里像型号码的词：≥5 位、字母数字混合（55U8000FG / QN65Q7FAAGXPE / 43PUS7200）。"""
    import re
    toks = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]{4,20}", title or "")
    out = [t for t in toks if re.search(r"\d", t) and re.search(r"[A-Za-z]", t)
           and not re.fullmatch(r"\d+(hz|gb|w|cm|mm)", t, re.I)]
    return sorted(out, key=len, reverse=True)[:2]


def self_sample_verify(ad, sf, df, spec, tmpl, kw, brand, n: int = 2,
                       urls_out: list | None = None) -> list[str]:
    import urllib.parse as up
    url = tmpl.format(base=ad.base_url.rstrip("/"), q=up.quote(kw), page=1)
    res, dom, html = open_search(ad, sf, spec, url)
    hits = _parse_search_with_spec(spec, ad, dom, html, limit=20) if dom is not None else []
    ok = []
    for h in hits[:6]:
        if len(ok) >= n:
            break
        pu = h.url or ad.product_url(h.sku)
        with open_dom(ad, df, pu, wait_selector=getattr(ad, "retail_page_wait", "body"),
                      scroll_passes=2, extra_wait_ms=2000) as (r2, d2, h2):
            if d2 is None:
                continue
            p = C._detail_payload(ad, spec, d2, h2, h.sku, pu)
        if p is None:
            continue
        for tok in _model_tokens(f"{p.product.model or ''} {p.product.title or ''}"):
            u2 = tmpl.format(base=ad.base_url.rstrip("/"), q=up.quote(f"{brand} {tok}"), page=1)
            r3, d3, h3 = open_search(ad, sf, spec, u2)
            hits2 = _parse_search_with_spec(spec, ad, d3, h3, limit=20) if d3 is not None else []
            t = match_product(spec, hits2, brand=brand, model=tok)
            if t is None:
                continue
            pu2 = t.url or ad.product_url(t.sku)
            with open_dom(ad, df, pu2, wait_selector=getattr(ad, "retail_page_wait", "body"),
                          scroll_passes=2, extra_wait_ms=2000) as (r4, d4, h4):
                if d4 is None:
                    continue
                p2 = C._detail_payload(ad, spec, d4, h4, t.sku, pu2)
            if p2 is not None and C._payload_matches_model(tok, p2, spec):
                ok.append(f"{tok}:{p2.price.price if p2.price else None}(在售样本)")
                if urls_out is not None:
                    urls_out.append(pu2)
                break
    return ok


PRICE_RULES = [
    {"jsonld": "offers.price", "transform": "money"},
    {"jsonld": "offers.lowPrice", "transform": "money"},
    {"selectors": ["meta[itemprop='price']", "[itemprop='price']"], "attr": "content", "transform": "money"},
    {"selectors": ["meta[property='product:price:amount']"], "attr": "content", "transform": "money"},
    {"selectors": ["[data-price-amount]"], "attr": "data-price-amount", "transform": "money"},
    {"selectors": ["[data-price]"], "attr": "data-price", "transform": "money"},
    {"selectors": ["[itemprop='price']"], "transform": "money"},
    {"selectors": [".price-sales", ".product-price .sales .value", ".price .value", "span.price",
                   "[class*='price--current']", "[class*='currentPrice']", "[class*='sale-price']",
                   "[class*='finalPrice']", "[class*='best-price']", "[class*='price'] [class*='amount']",
                   "[class*='price']"], "transform": "money"},
]


def fix_price(ad, df, spec, urls: list[str], currency: str = "",
              models: list[str] | None = None) -> tuple[dict | None, list]:
    """详情页价格规则自动选择：候选规则逐条在已校验 PDP 上试。

    可用条件：每页都取到正数价，且通过 price_sanity（不低于币种电视下限、不同型号不同价）。
    """
    from overseas.price_sanity import check_prices
    from overseas.extract import Extractor
    pages = []
    for u in urls[:2]:
        with open_dom(ad, df, u, wait_selector=getattr(ad, "retail_page_wait", "body"),
                      scroll_passes=2, extra_wait_ms=3000) as (r, d, h):
            if d is not None:
                pages.append((d, h))
        # 注意：Playwright DOM 出了 with 即失效，只能用 HTML 版本复核
    if not pages:
        return None, []
    from overseas.fetchers import LxmlDom
    docs = [(LxmlDom.parse(h), h) for _, h in pages]
    for rule in PRICE_RULES:
        vals = []
        for dom, html in docs:
            trial = {"price": {"price": rule}}
            try:
                v = Extractor(trial, html=html, base_url=ad.base_url).fields(dom, "price").get("price")
            except Exception:  # noqa: BLE001
                v = None
            vals.append(v)
        if vals and all(isinstance(v, (int, float)) and v > 1 for v in vals):
            names = (models or [f"m{i}" for i in range(len(vals))])[:len(vals)]
            if check_prices(currency, list(zip(names, vals))):
                continue          # 数字取到了但不像电视价（月供/起价/配件），换下一条
            return rule, vals
    return None, []


def fix_site(code: str, min_links: int, dry: bool, budget: int) -> dict:
    out = {"site": code, "result": "", "template": "", "keyword": "", "container": "",
           "links": 0, "verified": "", "note": ""}
    ad = SiteRegistry.get(code)
    spec = C._resolve_site_spec(code, None)
    if spec is None:
        out.update(result="SKIP", note="无 spec（adapter 自带解析路径）")
        return out
    if (spec.get("search") or {}).get("api"):
        out.update(result="SKIP", note="已走搜索接口（search.api），不改 DOM 搜索")
        return out
    pos = positives(code, 2)
    if not pos:
        # 主库无该站正样本：用常见大品牌探索，验证只走「站上在售样本」（self_sample_verify）
        pos_brand = "Samsung"
        brand, model = pos_brand, ""
    else:
        brand, model = pos[0]
    sf, df = C._make_fetcher(ad, spec)
    tried = []
    best = None
    t_list = [t for t in [adapter_template(ad)] + TEMPLATES if t]
    t_list = list(dict.fromkeys(t_list))
    try:
        n = 0
        for kw_t in KEYWORDS:
            kw = kw_t.format(brand=brand)
            for tmpl in t_list:
                if n >= budget:
                    break
                n += 1
                import urllib.parse as up
                url = tmpl.format(base=ad.base_url.rstrip("/"), q=up.quote(kw), page=1)
                try:
                    res, dom, html = open_search(ad, sf, spec, url)
                except Exception as e:  # noqa: BLE001
                    tried.append((tmpl, kw, f"EXC {type(e).__name__}"))
                    continue
                if res.blocked:
                    tried.append((tmpl, kw, f"blocked {res.block_reason}"))
                    if str(res.block_reason).startswith(("http_403", "marker:")):
                        break           # 被拦就不必换模板了
                    continue
                cands = discover_containers(html or "", ad.base_url, brand, top=3)
                score = cands[0][1] if cands else 0
                tried.append((tmpl, kw, f"{res.status} links={score}"))
                if cands and (best is None or score > best[3]):
                    best = (tmpl, kw_t, cands[0][0], score)
                if score >= 12:
                    break
            if best and best[3] >= 12:
                break
        if not best or best[3] < min_links:
            out.update(result="NOFIX", note=f"最佳 {best[3] if best else 0} 个商品链接 < {min_links}；"
                                             + " | ".join(f"{t.split('/')[-1][:24]}[{k}]={r}" for t, k, r in tried[:8]))
            return out
        tmpl, kw_t, container, score = best
        out.update(template=tmpl, keyword=kw_t, container=container, links=score)
        # ---- 验证：真实型号搜索 → 匹配 → 详情页校验 ----
        trial = json.loads(json.dumps(spec))
        trial.setdefault("search", {})
        trial["search"].pop("api", None)
        trial["search"].update({"search_url_template": tmpl, "container": container,
                                "sku": {"self_attr": "href"}, "url": {"self_attr": "href"}})
        trial["search"].setdefault("title", {"self_text": True})
        ok_models = []
        verified_urls: list[str] = []
        import urllib.parse as up
        # 品牌池（与全量入口 batch 模式一致）先匹配；不中再逐型号搜索
        pool_url = tmpl.format(base=ad.base_url.rstrip("/"), q=up.quote(kw_t.format(brand=brand)), page=1)
        res, dom, html = open_search(ad, sf, trial, pool_url)
        pool = _parse_search_with_spec(trial, ad, dom, html, limit=60) if dom is not None else []
        for b, m in pos:
            t = match_product(trial, pool, brand=b, model=m)
            if t is None:
                url = tmpl.format(base=ad.base_url.rstrip("/"), q=up.quote(f"{b} {m}"), page=1)
                res, dom, html = open_search(ad, sf, trial, url)
                hits = _parse_search_with_spec(trial, ad, dom, html, limit=20) if dom is not None else []
                t = match_product(trial, hits, brand=b, model=m)
            if t is None:
                continue
            pu = t.url or ad.product_url(t.sku)
            with open_dom(ad, df, pu, wait_selector=getattr(ad, "retail_page_wait", "body"),
                          scroll_passes=3, extra_wait_ms=2500) as (r2, d2, h2):
                if d2 is None:
                    continue
                p = C._detail_payload(ad, trial, d2, h2, t.sku, pu)
                if p is not None and C._payload_matches_model(m, p, trial):
                    ok_models.append(f"{m}:{p.price.price if p.price else None}")
                    verified_urls.append(pu)
        if not ok_models:
            # 主库正样本可能已下架：改用「站上当前在售」的样本——从品牌池里取商品，
            # 读其详情页标题里的型号码，再按型号搜一次，走完 匹配→详情校验 全链路。
            ok_models = self_sample_verify(ad, sf, df, trial, tmpl, kw_t.format(brand=brand), brand,
                                           urls_out=verified_urls)
        out["verified"] = " ".join(ok_models)
        if not ok_models:
            out.update(result="UNVERIFIED", note="搜索页有商品链接，但正样本型号未能匹配+详情页校验通过")
            return out
        # ---- 价格：没抽到价，或抽到的数字不像电视价（price_sanity）→ 自动选价格规则 ----
        import re as _re
        from overseas.price_sanity import check_prices
        from overseas.regions_config import REGIONS
        cur = next((r.currency for r in REGIONS.values()
                    if any(s.site == code for s in r.retail_sites)), "")
        samples = []
        for x in ok_models:
            m, _, p = x.partition(":")
            p = _re.sub(r"\(.*", "", p)
            samples.append((m, None if p in ("None", "") else float(p)))
        price_problems = check_prices(cur, samples)
        price_note = ""
        if all(p is None for _, p in samples) or price_problems:
            rule, vals = fix_price(ad, df, trial, verified_urls, cur, [m for m, _ in samples])
            if rule is not None:
                trial.setdefault("price", {})["price"] = rule
                price_note = f"price 规则自动选定 {json.dumps(rule, ensure_ascii=False)[:90]} 实测值 {vals}"
                ok_models = [f"{x.split(':', 1)[0]}:{v}" for x, v in zip(ok_models, vals)] or ok_models
                trial.pop("_price_suspect", None)
            elif price_problems:
                # 搜索修好了，但价格不可信：spec 里显式标记，readiness/全量据此拦截价格入库
                trial["_price_suspect"] = {"date": dt.date.today().isoformat(),
                                           "problems": price_problems}
                price_note = "价格可疑且未找到可信规则：" + "；".join(price_problems)
            else:
                price_note = "价格规则候选均未取到正数价（商品页价格可能客户端渲染/需登录）"
        out["note"] = price_note
        out["verified"] = " ".join(ok_models)
        if validate_retail_spec(trial):
            out.update(result="INVALID", note="; ".join(validate_retail_spec(trial))[:200])
            return out
        trial["search"].setdefault("batch", {})["keyword_template"] = kw_t
        trial["_autofix_search"] = {
            "date": dt.date.today().isoformat(), "tool": "scripts/autofix_search.py",
            "evidence": {"links": score, "verified_models": ok_models},
            "tried": [f"{t} [{k}] {r}" for t, k, r in tried[:12]],
        }
        if not dry:
            with open(retail_spec_path(code), "w", encoding="utf-8", newline="\n") as fh:
                json.dump(trial, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        out["result"] = ("FIXED_PRICE_SUSPECT" if trial.get("_price_suspect") else "FIXED") \
            if not dry else "FIXABLE"
        return out
    finally:
        sf.close()
        if df is not sf:
            df.close()


def main() -> int:
    from readiness_check import keep_awake
    keep_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="*", default=[])
    ap.add_argument("--from-readiness", default="")
    ap.add_argument("--min-links", type=int, default=4)
    ap.add_argument("--budget", type=int, default=36, help="每站最多打开几次搜索页")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--site-timeout", type=int, default=900, help="多站时单站硬超时（秒）")
    ap.add_argument("--no-isolate", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    sites = list(a.sites)
    if a.from_readiness:
        latest = {}
        for r in csv.DictReader(open(a.from_readiness, encoding="utf-8-sig")):
            latest[r["site"]] = r
        sites += [s for s, r in latest.items()
                  if r["verdict"] in ("FAIL", "PARTIAL") and ("搜索" in r.get("gaps", "")
                                                             or r.get("hit", "").startswith("0/"))]
    sites = list(dict.fromkeys(sites))
    stamp = dt.date.today().strftime("%Y%m%d")
    out = f"data/sandbox/autofix_search_{stamp}.csv"
    new = not os.path.exists(out)
    cols = ["time", "site", "result", "template", "keyword", "container", "links", "verified", "note"]
    if len(sites) > 1 and not a.no_isolate:
        # 多站时每站一个子进程 + 硬超时：单站浏览器卡死（实测 exito_co 30+ 分钟无输出）
        # 不能拖住整批。子进程自己写 CSV 行。
        import subprocess
        for code in sites:
            cmd = [sys.executable, "-u", __file__, "--sites", code, "--no-isolate",
                   "--min-links", str(a.min_links), "--budget", str(a.budget)]
            if a.dry_run:
                cmd.append("--dry-run")
            try:
                subprocess.run(cmd, timeout=a.site_timeout)
            except subprocess.TimeoutExpired:
                print(f"[TIMEOUT   ] {code} 超过 {a.site_timeout}s，跳过", flush=True)
                with open(out, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                    if new:
                        w.writeheader()
                        new = False
                    w.writerow({"time": dt.datetime.now().strftime("%m-%d %H:%M"), "site": code,
                                "result": "TIMEOUT", "note": f">{a.site_timeout}s"})
            new = not os.path.exists(out)
        print(f"[OUT] {out}")
        return 0
    for code in sites:
        t0 = time.time()
        print(f"[RUN ] {code}", flush=True)
        try:
            r = fix_site(code, a.min_links, a.dry_run, a.budget)
        except Exception as e:  # noqa: BLE001
            r = {"site": code, "result": "ERROR", "note": f"{type(e).__name__}: {str(e)[:150]}"}
        r["time"] = dt.datetime.now().strftime("%m-%d %H:%M")
        print(f"[{r['result']:10}] {code} {r.get('template', '')} [{r.get('keyword', '')}] "
              f"{r.get('container', '')} links={r.get('links', 0)} ok={r.get('verified', '')} "
              f"{round(time.time() - t0)}s | {r.get('note', '')[:180]}", flush=True)
        with open(out, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            if new:
                w.writeheader()
                new = False
            w.writerow(r)
    print(f"[OUT] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
