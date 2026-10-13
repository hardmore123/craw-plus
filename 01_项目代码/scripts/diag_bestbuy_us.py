"""诊断：Best Buy 美国站（bestbuy.com）开抓前六项体检。

存在意义
--------
`overseas/sites/bestbuy_us/schema.json` 与 `schemas/retail_specs/bestbuy_us.retail.json`
里的选择器**从未在真实 DOM 上校准过**（本机直连 bestbuy.com 恒超时，见
`docs/北美零售站连通性与反爬汇报_2026-09-18.md`）。在拿到美国出口 IP 之后，
必须先跑本脚本把这六件事逐项确认，再谈"开抓"：

  1. `ip`      出口 IP 是否美国 / 是否仍被 302 到国际选择页
  2. `search`  搜索页能否解析出候选（`data-sku-id`），滚动几轮才够
  3. `pdp`     PDP 能否抽到**权威型号**（决定"防张冠李戴"闸三是否成立）
  4. `reviews` 网评后端属哪一类（BV / 自有 API / SSR / click_more）
  5. `price`   PDP 上的价格候选及其**祖先容器**（决定主价选择器与价格区校验）
  6. `miss`    ★"某些型号搜不到"的真实表现：不存在的型号会不会被模糊命中

用法
----
    $env:OVERSEAS_PROXY = "http://<美国住宅代理>:<port>"
    py -3.12 scripts/diag_bestbuy_us.py --brand Hisense `
        --model-exists 65U8N --model-absent 999ZZZZ --dump data/_smoke

    # 只跑其中几项
    py -3.12 scripts/diag_bestbuy_us.py --only ip,search,miss

设计红线（与项目既有约定一致）
------------------------------
- **只读、不写业务产物**：除 `--dump` 的 HTML 与 `_smoke/bestbuy_us_diag.json` 外不落任何文件。
- **不猜选择器**：脚本只报告"页面上有什么"，不替 spec 决定选择器。
- **不重试被拦页面**：命中 blocked/captcha 立即如实汇报并结束该项。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                                    # noqa: E402
from overseas.fetchers import BrowserFetcher, HttpFetcher       # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.mx_retail import _parse_search_with_spec          # noqa: E402
from overseas.retail_spec import (explain_no_match,             # noqa: E402
                                  load_retail_spec, match_product)
from overseas.scenarios import open_dom                         # noqa: E402
from overseas.sites import SiteRegistry                         # noqa: E402

SITE = "bestbuy_us"
DEFAULT_SPEC = PROJECT_ROOT / "schemas" / "retail_specs" / "bestbuy_us.retail.json"
SMOKE_DIR = PROJECT_ROOT / "data" / "_smoke"

# 站内原生评价页（外部资料：20 条/页，页面写 "Page 1 Showing 1-20 of 47"）。
# ★注意它与 adapter.reviews_url() 的 /site/reviews/<sku>?page=N 不同形：
#   实测形态是 /site/reviews/<slug>/<skuId>，sku-only 形态能否 302 到位需现场确认。
NATIVE_REVIEW_URL = "https://www.bestbuy.com/site/reviews/{sku}"

ALL_CHECKS = ("ip", "search", "pdp", "reviews", "price", "miss")


def _sku_from_url(url: str) -> str:
    """从两种 PDP URL 形态里取 skuId。

    旧形态 /site/<slug>/<skuId>.p?skuId=<skuId>
    新形态 /product/<slug>/<10 位码>/sku/<skuId>
    """
    u = str(url or "")
    m = re.search(r"[?&]skuId=(\d{5,})", u) or re.search(r"/sku/(\d{5,})", u) \
        or re.search(r"/(\d{5,})\.p", u)
    return m.group(1) if m else ""

# 网评后端的判定特征（命中哪个 → 走哪条接入路径，见方案文档 §2.2）
REVIEW_MARKERS: dict[str, str] = {
    "bazaarvoice": r"bazaarvoice|apps\.bazaarvoice\.com",
    "bv_token": r"bv-bfd-token",
    "bv_widget": r"bv-content-item|bv_main_container|bv_avgRating|bv_numReviews",
    "bv_product_attr": r"data-bv-product-id",
    "site_ugc": r"/ugc/|ugc-|ugc\.",
    "review_api": r"/reviews?(/|\?|\")|reviews\.json|reviewapi|/review/",
    "graphql": r"graphql",
    "review_dom": r"review-item|review-content|ugc-review|\[data-testid=.review",
}

# 只在页面 HTML 里找这些词，用来判断"价格区是否被推荐位污染"
PRICE_CONTEXT_HINT = (
    "related", "carousel", "recommend", "accessor", "bundle",
    "frequently", "also-viewed", "alsoviewed", "sponsored", "ad-",
)

_JSONLD_JS = r"""() => {
  const out = [];
  document.querySelectorAll("script[type='application/ld+json']").forEach(s => {
    try { out.push(JSON.parse(s.textContent)); }
    catch (e) { out.push({_parse_error: String(e), _head: (s.textContent || '').slice(0, 120)}); }
  });
  return out;
}"""

_PRICE_JS = r"""() => {
  const money = /^\$?[\d,]+\.\d{2}$/;
  const out = [];
  const all = document.querySelectorAll('span,div,p,strong');
  for (const e of all) {
    const t = (e.textContent || '').trim();
    if (!t || t.length > 14 || !money.test(t)) continue;
    if (e.querySelector('span,div,p,strong')) continue;      // 只取叶子节点，避免父容器重复
    const chain = [];
    let p = e;
    for (let k = 0; k < 10 && p; k++) {
      const id = p.id || '';
      const cls = (typeof p.className === 'string') ? p.className : '';
      const tip = p.getAttribute ? (p.getAttribute('data-testid') || '') : '';
      if (id || cls || tip) {
        const parts = cls.trim().split(/\s+/).slice(0, 3).join('.');
        chain.push(p.tagName.toLowerCase()
                   + (id ? '#' + id : '')
                   + (parts ? '.' + parts : '')
                   + (tip ? "[data-testid='" + tip + "']" : ''));
      }
      p = p.parentElement;
    }
    out.push({text: t, testid: e.getAttribute('data-testid') || '', chain: chain});
  }
  return out.slice(0, 60);
}"""

_MODEL_JS = r"""() => {
  const grab = (sel) => [...document.querySelectorAll(sel)]
      .map(e => (e.innerText || e.textContent || '').trim())
      .filter(Boolean).slice(0, 8);
  const specRows = [];
  document.querySelectorAll('tr, li, div').forEach(e => {
    const t = (e.innerText || '').trim();
    if (!t || t.length > 90) return;
    if (/^model(\s*(number|no\.?|#))?\s*[:\-]/i.test(t)) specRows.push(t);
  });
  return {
    h1: grab('h1'),
    dataTestIdModel: grab("[data-testid*='model' i]"),
    dataTestIdSku: grab("[data-testid*='sku' i]"),
    classModel: grab(".model span.product-data-value, div.model, .product-data-value"),
    specRows: specRows.slice(0, 8),
    htmlHasModelRow: /model\s*(number|no\.?|#)?\s*[:\-]/i.test(document.body.innerText || ''),
  };
}"""


def _js(dom, script: str):
    """在 Playwright 页面上执行 JS；非浏览器 DOM / 异常一律返回 None。"""
    root = getattr(dom, "_root", None)
    if root is None or not hasattr(root, "evaluate"):
        return None
    try:
        return root.evaluate(script)
    except Exception:
        return None


def _scan_markers(html: str) -> dict[str, int]:
    low = (html or "").lower()
    return {name: len(re.findall(pat, low)) for name, pat in REVIEW_MARKERS.items()}


def _save_html(dump: str, name: str, html: str) -> str:
    if not dump or not html:
        return ""
    out = Path(dump)
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"bestbuy_us_{name}.html"
    try:
        f.write_text(html, encoding="utf-8")
    except OSError:
        return ""
    return str(f)


class Ctx:
    def __init__(self, args) -> None:
        self.args = args
        self.adapter = SiteRegistry.get(SITE)
        self.spec = load_retail_spec(args.spec) if args.spec else None
        interval = max(config.MIN_INTERVAL, self.adapter.suggested_interval)
        shared = {
            "rate_limiter": RateLimiter(min_interval=interval),
            "detector": BlockDetector(
                ignore_markers=getattr(self.adapter, "block_marker_allowlist", None)),
            "cache": DiskCache(),
        }
        self.fetcher = BrowserFetcher(site_code=self.adapter.code, **shared)
        self.report: dict = {"site": SITE, "proxy": config.PROXY or "(直连)",
                             "spec": str(args.spec or ""), "checks": {}}

    # ---------- 1. 出口 IP ----------
    def check_ip(self) -> dict:
        out: dict = {}
        # 1a) 出口 IP 归属（best effort：取不到不算失败）
        try:
            res = HttpFetcher().get("https://ipinfo.io/json", use_cache=False)
            if res.status == 200 and res.html:
                data = json.loads(res.html)
                out["ip"] = data.get("ip", "")
                out["country"] = data.get("country", "")
                out["org"] = data.get("org", "")
        except Exception as e:
            out["ip_error"] = f"{type(e).__name__}: {e}"
        # 1b) 真信号：bestbuy.com 首页的实际返回
        # ★★ 判"非美国"绝不能只看状态码：非美国 IP 返回的是 **HTTP 200** +
        #    <title>Best Buy International: Select your Country - Best Buy</title>，
        #    不是 403、不是重定向。只判 final_url 会漏掉，必须同时看标题与正文。
        # ★★ 还要区分"本地网关白名单拦截"：本机所在网络有内网准入网关
        #    （10.18.0.250/disable/disable.htm），那既不是 Best Buy 反爬、也不是
        #    出口 IP 问题，别据此去调反爬策略。
        with open_dom(self.adapter, self.fetcher, self.adapter.base_url,
                      wait_selector="body", scroll_passes=1,
                      extra_wait_ms=self.args.wait) as (res, dom, html):
            final_url = str(res.meta.get("final_url") or "")
            title = (res.title or "")[:200]
            head = (html or "")[:6000]
            local_gateway = bool(re.search(r"10\.18\.0\.250|/disable/disable\.htm",
                                           final_url + head, re.I))
            country_splash = bool(
                re.search(r"international|select[- ]?your[- ]?country|country[- ]?selector",
                          title, re.I)
                or re.search(r"Best Buy International", head, re.I)
                or re.search(r"international|country|select-your", final_url, re.I))
            out.update({
                "status": res.status, "blocked": bool(res.blocked),
                "block_reason": res.block_reason or "",
                "final_url": final_url,
                "title": title,
                "html_len": len(html or ""),
                "local_gateway_block": local_gateway,
                "country_splash": country_splash,
            })
            out["dump"] = _save_html(self.args.dump, "home", html)
        if local_gateway:
            out["verdict"] = ("★FAIL 本地网关白名单拦截（10.18.0.250/disable.htm）——"
                              "这不是 Best Buy 反爬，是公司网络准入；换网络或走代理再试")
        elif country_splash or not res.ok or res.blocked:
            out["verdict"] = ("★FAIL 拿到的是国际选择页/被拦（非美国出口 IP 的典型表现："
                              "HTTP 200 + 'Best Buy International: Select your Country'）")
        else:
            out["verdict"] = "OK 首页可达且是美国站"
        if not out.get("country"):
            out["verdict"] += "｜出口 IP 归属未取到（ipinfo 不可达，不据此判失败）"
        self.report["checks"]["ip"] = out
        return out

    # ---------- 2. 搜索候选 ----------
    def _search_hits(self, keyword: str, scroll: int, wait: int):
        s_cfg = (self.spec or {}).get("search") or {}
        url = self.adapter.search_url(keyword)
        with open_dom(self.adapter, self.fetcher, url,
                      wait_selector=s_cfg.get("container") or "a",
                      scroll_passes=scroll, extra_wait_ms=wait) as (res, dom, html):
            hits = (_parse_search_with_spec(self.spec, self.adapter, dom, html,
                                            limit=self.args.limit)
                    if (self.spec and dom is not None) else [])
            raw = {}
            if self.spec and dom is not None:
                container = s_cfg.get("container") or ""
                if container:
                    raw[container] = len(dom.sub(container, limit=200))
            return res, html, hits, raw, url

    def check_search(self) -> dict:
        keyword = self.args.brand_keyword or f"{self.args.brand} tv"
        res, html, hits, raw, url = self._search_hits(
            keyword, self.args.scroll, self.args.wait)
        out = {
            "keyword": keyword, "url": url, "status": res.status,
            "blocked": bool(res.blocked), "block_reason": res.block_reason or "",
            "final_url": str(res.meta.get("final_url") or ""),
            "n_hits": len(hits), "container_counts": raw,
            "first_hits": [{"sku": h.sku, "title": (h.title or "")[:90],
                            "url": (h.url or "")[:120]} for h in hits[:12]],
            "dump": _save_html(self.args.dump, "search", html),
        }
        out["verdict"] = (
            "FAIL 搜索页被拦/未打开" if (res.blocked or not res.ok) else
            ("FAIL 0 候选：选择器失效或渲染未等到（★不要据此判 no_item）"
             if not hits else f"OK 解析出 {len(hits)} 个候选"))
        self.report["checks"]["search"] = out
        return out

    # ---------- 3./4./5. PDP：型号 / 网评后端 / 价格区 ----------
    def _open_pdp(self):
        """打开一个真实 PDP：优先用 --pdp-url，其次用搜索第一个候选。"""
        if self.args.pdp_url:
            return self.args.pdp_url
        keyword = self.args.brand_keyword or f"{self.args.brand} tv"
        _res, _html, hits, _raw, _url = self._search_hits(
            keyword, self.args.scroll, self.args.wait)
        if not hits:
            return ""
        return hits[0].url or self.adapter.product_url(hits[0].sku)

    def _open_pdp_page(self, pdp_url: str, capture: bool):
        """返回 (res, dom, html)。capture=True 时顺带抓 review 相关响应体。"""
        wait = getattr(self.adapter, "retail_page_wait", "body")
        if capture:
            pattern = (r"review|ugc|bazaarvoice|bv-|rating|/api/|graphql")
            with self.fetcher.page(pdp_url, wait_selector=wait,
                                   scroll_passes=self.args.scroll,
                                   extra_wait_ms=self.args.wait,
                                   capture_response_pattern=pattern,
                                   capture_response_limit=4000) as (res, dom):
                html = dom.html() if dom is not None else ""
            return res, dom, html
        with open_dom(self.adapter, self.fetcher, pdp_url, wait_selector=wait,
                      scroll_passes=self.args.scroll,
                      extra_wait_ms=self.args.wait) as (res, dom, html):
            return res, dom, html

    def check_pdp(self, pdp_url: str = "") -> dict:
        pdp_url = pdp_url or self._open_pdp()
        if not pdp_url:
            out = {"verdict": "SKIP 没有可用 PDP（搜索无候选，先把 search 项跑通）"}
            self.report["checks"]["pdp"] = out
            return out
        res, dom, html = self._open_pdp_page(pdp_url, capture=False)
        out: dict = {"pdp_url": pdp_url, "status": res.status,
                     "blocked": bool(res.blocked),
                     "block_reason": res.block_reason or "",
                     "final_url": str(res.meta.get("final_url") or "")}
        if dom is None or not res.ok:
            out["verdict"] = "FAIL PDP 打不开（blocked/超时）"
            self.report["checks"]["pdp"] = out
            return out
        out["dom"] = _js(dom, _MODEL_JS) or {}
        jsonld = _js(dom, _JSONLD_JS) or []
        out["jsonld_types"] = []
        for node in jsonld:
            for item in (node if isinstance(node, list) else [node]):
                if not isinstance(item, dict):
                    continue
                t = item.get("@type")
                if not t:
                    continue
                out["jsonld_types"].append(t)
                if str(t).lower() == "product":
                    offers = item.get("offers") or {}
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    rating = item.get("aggregateRating") or {}
                    out["jsonld_product"] = {
                        "name": str(item.get("name") or "")[:120],
                        "sku": str(item.get("sku") or ""),
                        "mpn": str(item.get("mpn") or ""),
                        "model": str(item.get("model") or "")[:60],
                        "brand": str((item.get("brand") or {}).get("name")
                                     if isinstance(item.get("brand"), dict)
                                     else item.get("brand") or "")[:60],
                        "price": (offers or {}).get("price"),
                        "currency": (offers or {}).get("priceCurrency"),
                        "ratingValue": (rating or {}).get("ratingValue"),
                        "reviewCount": (rating or {}).get("reviewCount"),
                        "availability": (offers or {}).get("availability"),
                    }
        dm = out["dom"]
        pm = (out.get("jsonld_product") or {})
        authoritative = bool(
            (dm.get("dataTestIdModel") or []) or (dm.get("specRows") or [])
            or pm.get("mpn") or pm.get("model"))
        out["authoritative_model_found"] = authoritative
        out["dump"] = _save_html(self.args.dump, "pdp", html)
        out["verdict"] = ("OK 抽到权威型号（闸三可用）" if authoritative else
                          "★FAIL 没抽到权威型号——只能靠标题匹配，误抓风险高，"
                          "需改 sites/bestbuy_us 的 model 抽取")
        self.report["checks"]["pdp"] = out
        return out

    def check_reviews(self, pdp_url: str = "") -> dict:
        pdp_url = pdp_url or self._open_pdp()
        if not pdp_url:
            out = {"verdict": "SKIP 没有可用 PDP"}
            self.report["checks"]["reviews"] = out
            return out
        res, dom, html = self._open_pdp_page(pdp_url, capture=True)
        bodies = list(getattr(res, "response_bodies", None) or [])
        out: dict = {
            "pdp_url": pdp_url, "status": res.status,
            "blocked": bool(res.blocked), "block_reason": res.block_reason or "",
            "captured_responses": int(res.meta.get("captured_response_count") or 0),
            "html_markers": _scan_markers(html),
            "captured_urls": [],
        }
        # 从抓到的响应体里找接口形态（只看前 200 字符，不落全文）
        for body in bodies[:12]:
            head = (body or "")[:200].replace("\n", " ")
            out["captured_urls"].append({"head": head})
        # 响应体里的 BV 配置特征
        joined = "\n".join(bodies)[:200000]
        out["response_markers"] = _scan_markers(joined)
        bv_client = re.findall(r"clients/([A-Za-z0-9_\-]+)/", joined)[:5]
        if bv_client:
            out["bv_clients_seen"] = bv_client
        dm = _js(dom, r"""() => {
          const q = (s) => document.querySelectorAll(s).length;
          const attr = document.querySelector('[data-bv-product-id]');
          return {
            review_items: q("[data-testid*='review' i], li.review-item, .review-item-content, [itemprop='review']"),
            bv_items: q(".bv-content-item, ol.bv-content-list li"),
            bv_main: q(".bv_main_container, .bv_avgRating_component_container"),
            bv_product_id: attr ? attr.getAttribute('data-bv-product-id') : '',
            review_like_buttons: [...document.querySelectorAll('button,a')]
                .map(e => (e.innerText || '').trim())
                .filter(t => /review|rating|write a review/i.test(t)).slice(0, 10),
          };
        }""") or {}
        out["dom"] = dm
        out["dump"] = _save_html(self.args.dump, "pdp_reviews", html)
        # ★ 原生评价页探测：外部资料显示 Best Buy 用的是站内评价页
        #   https://www.bestbuy.com/site/reviews/<slug>/<skuId>（20 条/页，
        #   页面会写 "Page 1 Showing 1-20 of 47"），且**没有 BazaarVoice 证据**。
        #   这里直接打一次只看形态，确认它是 DOM 渲染还是另有 JSON 接口。
        sku = _sku_from_url(pdp_url) or _sku_from_url(
            str(res.meta.get("final_url") or ""))
        if sku:
            nurl = NATIVE_REVIEW_URL.format(sku=sku)
            try:
                with open_dom(self.adapter, self.fetcher, nurl,
                              wait_selector="body",
                              scroll_passes=max(6, self.args.scroll // 2),
                              extra_wait_ms=self.args.wait) as (r2, d2, h2):
                    paging = ""
                    if d2 is not None:
                        try:
                            body_text = d2.text("body")
                        except Exception:
                            body_text = ""
                        m = re.search(r"Showing\s+[\d,]+\s*[-–]\s*[\d,]+\s+of\s+[\d,]+",
                                      body_text or "", re.I)
                        paging = m.group(0) if m else ""
                    out["native_review_page"] = {
                        "url": nurl, "status": r2.status,
                        "blocked": bool(r2.blocked),
                        "block_reason": r2.block_reason or "",
                        "final_url": str(r2.meta.get("final_url") or ""),
                        "paging_text": paging,
                        "review_items": (_js(d2, r"""() => document.querySelectorAll(
                            "[data-testid*='review' i], .review-item, [itemprop='review'], li.ugc-review").length""")
                            if d2 is not None else 0),
                        "dump": _save_html(self.args.dump, "native_reviews", h2),
                    }
            except Exception as e:
                out["native_review_page"] = {"url": nurl,
                                             "error": f"{type(e).__name__}: {e}"}
        backend = classify_backend(out)
        out["backend_guess"] = backend
        out["verdict"] = f"后端初判 = {backend}（按方案文档 §2.2 选接入路径）"
        self.report["checks"]["reviews"] = out
        return out

    def check_price(self, pdp_url: str = "") -> dict:
        pdp_url = pdp_url or self._open_pdp()
        if not pdp_url:
            out = {"verdict": "SKIP 没有可用 PDP"}
            self.report["checks"]["price"] = out
            return out
        res, dom, html = self._open_pdp_page(pdp_url, capture=False)
        if dom is None or not res.ok:
            out = {"pdp_url": pdp_url, "status": res.status,
                   "blocked": bool(res.blocked),
                   "verdict": "FAIL PDP 打不开，无法定位价格区"}
            self.report["checks"]["price"] = out
            return out
        cands = _js(dom, _PRICE_JS) or []
        # 给每个价格候选标出"祖先链里是否出现推荐位/配件线索"
        for c in cands:
            blob = " ".join(c.get("chain") or []).lower()
            c["suspicious_container"] = any(h in blob for h in PRICE_CONTEXT_HINT)
        out = {
            "pdp_url": pdp_url,
            "n_price_candidates": len(cands),
            "candidates": cands[:25],
            "suspicious_count": sum(1 for c in cands if c.get("suspicious_container")),
            "jsonld_price": (self.report.get("checks", {}).get("pdp", {})
                             .get("jsonld_product", {}) or {}).get("price"),
        }
        out["verdict"] = (
            "★FAIL 页面上 0 个价格候选（价格是客户端渲染？需先点开/等待）"
            if not cands else
            f"待人工判定：{len(cands)} 个候选，其中 {out['suspicious_count']} 个"
            f"疑似落在推荐位/配件容器内 —— 取主价的那条写进 spec.price.price，"
            f"其余用作价格区校验（闸四）")
        self.report["checks"]["price"] = out
        return out

    # ---------- 6. "某些型号搜不到"的真实表现 ----------
    def check_miss(self) -> dict:
        out: dict = {"exists": None, "absent": None}
        keyword_tmpl = self.args.brand_keyword or f"{self.args.brand} tv"
        for label, model in (("exists", self.args.model_exists),
                             ("absent", self.args.model_absent)):
            if not model:
                continue
            # 用型号的"主干"去搜，模拟真实逐型号检索
            kw = f"{self.args.brand} {model}"
            res, _html, hits, _raw, url = self._search_hits(
                kw, self.args.scroll, self.args.wait)
            target = match_product(self.spec or {}, hits, brand=self.args.brand,
                                   model=model) if hits else None
            out[label] = {
                "model": model, "keyword": kw, "url": url,
                "status": res.status, "blocked": bool(res.blocked),
                "n_candidates": len(hits),
                "matched": bool(target),
                "matched_sku": getattr(target, "sku", "") if target else "",
                "matched_title": (getattr(target, "title", "") or "")[:100] if target else "",
                "explain": explain_no_match(self.spec or {}, hits,
                                            brand=self.args.brand, model=model),
                "candidates": [{"sku": h.sku, "title": (h.title or "")[:80]}
                               for h in hits[:8]],
            }
        # 品牌级搜索模式（批量）也验一遍：这是实际会走的路径
        if self.args.verify_batch:
            res, _html, hits, _raw, url = self._search_hits(
                keyword_tmpl, self.args.scroll_batch, self.args.wait)
            out["batch"] = {
                "keyword": keyword_tmpl, "url": url, "status": res.status,
                "blocked": bool(res.blocked), "n_candidates": len(hits),
                "absent_matched": bool(
                    match_product(self.spec or {}, hits, brand=self.args.brand,
                                  model=self.args.model_absent)
                    if (self.args.model_absent and hits) else False),
                "explain_absent": explain_no_match(
                    self.spec or {}, hits, brand=self.args.brand,
                    model=self.args.model_absent) if self.args.model_absent else "",
            }
        # 判定：不存在的型号**绝不能被匹配上**（这就是误抓红线）
        absent = out.get("absent") or {}
        batch = out.get("batch") or {}
        false_positive = bool(absent.get("matched")) or bool(batch.get("absent_matched"))
        out["false_positive"] = false_positive
        out["verdict"] = (
            "★★ 误抓：不存在的型号被匹配上了！必须收紧 reject / 尺寸守卫 / 闸三，"
            "否则价格会张冠李戴" if false_positive else
            "OK 不存在的型号未被误匹配（no_item 语义成立）")
        self.report["checks"]["miss"] = out
        return out


def classify_backend(out: dict) -> str:
    """按证据把网评后端归到 A/B/C/D 四类（对应方案文档 §2.2）。

    ★先验证据（截到 2026-09）：Best Buy 页面出现 bazaarvoice 域名的最后记录在
    2022-12；urlscan 里 `domain:api.bazaarvoice.com AND page.domain:www.bestbuy.com`
    为 0 命中。所以**默认不该假设是 BV**，站内原生评价页才是主线。
    """
    native = out.get("native_review_page") or {}
    hm = out.get("html_markers") or {}
    rm = out.get("response_markers") or {}
    dom = out.get("dom") or {}
    # A) BazaarVoice：只在拿到正面证据时才判（域名/token/client 三者之一）
    if rm.get("bazaarvoice") or rm.get("bv_token") or out.get("bv_clients_seen"):
        return "A bazaarvoice_bfd（复用 overseas/bv_reviews.py，零成本）"
    # B) 站点自有 JSON 接口：评价页 DOM 空但抓到评价相关 JSON
    if (rm.get("review_api") or rm.get("graphql")) and not (native.get("review_items") or 0):
        return "B 站点自有 JSON 接口（需新写 source 分支）"
    # C/D) 站内原生评价页
    if (native.get("review_items") or 0) > 0 or (dom.get("review_items") or 0) > 0:
        paging = native.get("paging_text") or ""
        extra = f"；分页文案「{paging}」" if paging else ""
        return (f"C 服务端渲染的站内原生评价页（走 url_page/query_param 翻页）{extra}")
    if (dom.get("bv_main") or 0) > 0:
        return "D 客户端挂件需点击展开（走 click_more）"
    return "未判定：没有抓到任何评价证据（可能需登录/需点开 Reviews 标签）"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Best Buy 美国站开抓前体检")
    p.add_argument("--spec", default=str(DEFAULT_SPEC),
                   help="RetailSpec 路径；传空字符串则不加载 spec（只看页面）")
    p.add_argument("--brand", default="Hisense")
    p.add_argument("--brand-keyword", default="", help="品牌级搜索词，缺省 '{brand} tv'")
    p.add_argument("--model-exists", default="",
                   help="已知在美国站有货的型号（用于对照）")
    p.add_argument("--model-absent", default="",
                   help="★确认不存在的型号（用于验证不会误抓）")
    p.add_argument("--pdp-url", default="", help="直接指定 PDP，跳过搜索")
    p.add_argument("--only", default=",".join(ALL_CHECKS),
                   help=f"只跑指定项，逗号分隔，可选：{','.join(ALL_CHECKS)}")
    p.add_argument("--limit", type=int, default=60, help="搜索候选上限")
    p.add_argument("--scroll", type=int, default=12, help="搜索/PDP 滚动次数")
    p.add_argument("--scroll-batch", type=int, default=20,
                   help="品牌级批量搜索的滚动次数（美国站要更多）")
    p.add_argument("--wait", type=int, default=10000, help="额外等待 ms")
    p.add_argument("--verify-batch", action="store_true",
                   help="miss 项额外验证品牌级批量模式")
    p.add_argument("--dump", default="", help="把渲染后 HTML 落到该目录")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    only = [c.strip() for c in (args.only or "").split(",") if c.strip()]
    bad = [c for c in only if c not in ALL_CHECKS]
    if bad:
        print(f"[ERROR] 未知检查项: {bad}（可选 {ALL_CHECKS}）", file=sys.stderr)
        return 2
    if not config.PROXY:
        print("[WARN] 未设置 OVERSEAS_PROXY：bestbuy.com 在非美国出口 IP 下会超时或"
              "跳国际选择页，本次结果不可用于校准。", file=sys.stderr)

    ctx = Ctx(args)
    pdp_url = ""
    try:
        if "ip" in only:
            ctx.check_ip()
        if "search" in only:
            ctx.check_search()
        # pdp 是 reviews/price 的前置：先跑一次，缓存 URL
        if "pdp" in only or "reviews" in only or "price" in only:
            pdp = ctx.check_pdp()
            pdp_url = pdp.get("pdp_url", "") if isinstance(pdp, dict) else ""
        if "reviews" in only:
            ctx.check_reviews(pdp_url)
        if "price" in only:
            ctx.check_price(pdp_url)
        if "miss" in only:
            ctx.check_miss()
    except KeyboardInterrupt:
        print("\n[中断] 用户取消", file=sys.stderr)
    finally:
        try:
            ctx.fetcher.close(save_state=False)
        except Exception:
            pass

    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    dest = SMOKE_DIR / "bestbuy_us_diag.json"
    dest.write_text(json.dumps(ctx.report, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    print("\n" + "=" * 72)
    print("Best Buy 美国站体检结论")
    print("=" * 72)
    for name, item in ctx.report["checks"].items():
        print(f"[{name:8s}] {item.get('verdict', '')}")
    print(f"\n[报告] {dest}")
    if args.dump:
        print(f"[HTML] {args.dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
