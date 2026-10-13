"""Samsung 法国 TV 官网 SPEC 适配器（多级流程，Next.js 站）。

实测结构（2026-09，https://www.samsung.com/fr/）：
- TV 列表页 /fr/tvs/all-tvs/ 含各型号链接 /fr/tvs/<type>/<slug>-<sku>/。
  欧洲产品 URL 的 SKU 在末尾段（如 gq75qn990ftxzg），无美国站的 -sku- 分隔符。
- 完整规格表由客户端 XHR 异步加载，无头浏览器不渲染，初始 __NEXT_DATA__ 只有
  概要（modelCode / attributes / additionalSpecs / keySummary）与 JSON-LD
  ProductGroup(hasVariant 各尺寸 + aggregateRating)。
- 入口页显示的是结果卡数量；每张卡内部还有多个尺寸控件和重复 SKU 链接。入口适配器
  按卡片记录尺寸、按系列码归一后只保留一个代表规格页，避免把同系列尺寸当成多个系列。
- 因此本适配器产出「概要 SPEC」：型号/尺寸/面板/VESA/重量/关键特性/评分等，
  足以跑通与导出；完整规格待后续用带头浏览器或 Samsung 规格 API 增强。
- 一个产品页的 hasVariant 已含该系列全部尺寸，故一页即可出该系列全部尺寸概要表。

与美国站（samsung_us）的差异：
- URL 格式：欧洲 /fr/tvs/<type>/<slug>-<sku>/（SKU 在末尾，无 -sku- 分隔符）；
  美国 /us/tvs/<type>/<slug>-sku-<sku>/（有 -sku- 分隔符）。
- 产品 URL 末尾段含具体型号，分类页 URL（如 /fr/tvs/oled-tv/）只有类型名、
  不含数字。以末尾段是否含数字区分产品页 vs 分类页。
- 欧洲 SKU 系列提取规则不同：法国 GQ75QN990FTXZG → 前缀 GQ + 尺寸 75 + 系列码
  QN990F + 后缀 TXZG；去掉前缀（2-3 字母）+ 尺寸（2-3 数字）+ 常见后缀得系列码。
- 入口分页按钮文案为法语（Voir plus / Tout afficher）。

只做 SPEC；价格/网评由零售站适配器负责。
"""
from __future__ import annotations

import re

from ...models import L3_STRONG, SpecSheet
from ...spec_parser_us import parse_samsung_us_html, parse_samsung_us_fullspecs
from ...fetchers import Dom
from .. import SiteAdapter

# 排除非 TV 品类与辅助页。
_EXCLUDE = ("accessor", "highlights", "buying-guide", "why-samsung",
            "offers", "monitor", "soundbar", "projector",
            "audio-devices", "movable-screens", "wireless-speaker")
# 只保留电视品类路径（普通 TV 与 lifestyle-tvs），排除音箱/便携屏等非 TV。
_TV_PATH = ("/fr/tvs/", "/fr/lifestyle-tvs/")
# Samsung 当前产品卡是该类名；属性选择器兼容 class 名附加哈希或状态类。
_CARD_SELECTOR = "[class*='pd21-product-card__item']"
_SIZE_RE = re.compile(
    r"(?<![a-z0-9])(\d{2,3})\s*(?:[\"”]|(?:-?\s*)inch(?:es)?\b|\bin\b)",
    re.I)
_SERIES_TOKEN_RE = re.compile(r"^[a-z]{1,4}\d[a-z0-9]{0,8}$", re.I)
_SERIES_IGNORES = {
    "4K", "8K", "TV", "TVS", "SMART", "CLASS", "INCH", "OLED", "QLED",
    "NEO", "LED", "MINI", "MICRO", "RGB", "UHD", "FHD", "HD", "CRYSTAL",
    "VISION", "AI", "THE", "FRAME", "PRO", "FULL", "SAMSUNG", "PLUS",
}
# 欧洲 SKU 常见尾码（德国 TXZG、英国 ATXXU/AUXZG 等）；优先长尾码避免误删系列末尾。
# 列表需按长度降序，否则短尾码（如 TXXU）会先匹配掉 ATXXU 末尾把 S99HATXXU → S99HA。
_EU_SKU_SUFFIXES = (
    "EUXZG", "ATXXU", "AUXZG", "TXZG", "ENXX", "TXXU", "XZG", "XXU",
)
# 产品链接：欧洲格式 /fr/tvs/<type>/<slug>-<sku>/，SKU 在末尾段。
_PRODUCT_RE = re.compile(
    r"href=[\"'](?:https?://[^/\"']+)?"
    r"(/fr/(?:tvs|lifestyle-tvs)/[a-z0-9\-]+/[a-z0-9\-]+/?)",
    re.I)


class SamsungFrAdapter(SiteAdapter):
    code = "samsung_fr"
    name = "Samsung（法国）"
    base_url = "https://www.samsung.com"
    country = "法国"
    channel = "Samsung 官网"
    protection = L3_STRONG
    requires_browser = True
    suggested_interval = 6.0
    supports_spec = True
    spec_entry_wait = "a[href*='/fr/tvs/']"
    spec_page_wait = "body"
    # 完整规格区需滚动到底才渲染（实测 ~18 次滚动后出 200+ 项）。
    spec_page_scroll_passes = 20
    spec_page_extra_wait_ms = 3000
    # 入口懒加载：滚动到产品卡稳定；最大次数只是安全阀。
    spec_entry_scroll_passes = 16
    spec_entry_scroll_until_stable = True
    spec_entry_scroll_growth_selector = _CARD_SELECTOR
    spec_entry_scroll_max_passes = 30
    spec_entry_scroll_stable_rounds = 3
    # 法国站分页按钮文案为法语（Voir plus / Tout afficher）。
    spec_entry_click_texts = ["Voir plus", "Voir tout", "View more",
                              "Show all", "Mehr anzeigen"]
    spec_entry_click_selectors = [
        "button:has-text('Voir plus')", "a:has-text('Voir plus')",
        "button:has-text('Voir tout')", "a:has-text('Voir tout')",
        "button:has-text('View more')", "a:has-text('View more')",
        "button:has-text('Show all')", "a:has-text('Show all')",
    ]
    spec_entry_click_repeats = 4
    spec_entry_click_wait_ms = 3000
    spec_entry_click_growth_selector = _CARD_SELECTOR
    # Samsung 正常页面前段内嵌 "captcha" 脚本引用，会被通用反爬检测器误判为拦截。
    # 豁免该关键字（HTTP 403/429/503、正文过短、缺锚点等其它判据不受影响）。
    block_marker_allowlist = ("captcha",)

    ENTRY = "https://www.samsung.com/fr/tvs/all-tvs/"

    # 欧洲站规格结构：pdd32-product-spec__content-item 内含
    # pdd32-product-spec__content-item-title（项目名）+ pdd32-product-spec__content-item-desc（值）
    # 无分组容器（美国站用 specgroupContainer，欧洲站不用）。
    _SPEC_JS = (
        "() => {"
        " const out = [];"
        " const items = document.querySelectorAll(\"[class*='pdd32-product-spec__content-item']\");"
        " for (const it of items) {"
        "   const n = it.querySelector(\"[class*='content-item-title']\");"
        "   const v = it.querySelector(\"[class*='content-item-desc']\");"
        "   const name = n ? (n.innerText||'').replace(/\\s+/g,' ').trim() : '';"
        "   const val = v ? (v.innerText||'').replace(/\\s+/g,' ').trim() : '';"
        "   if (name && val) out.push(['', name, val]);"
        " }"
        " return JSON.stringify(out);"
        "}"
    )

    def spec_entry_url(self) -> str:
        return self.ENTRY

    def _sku_from_url(self, url: str) -> str:
        """从欧洲产品 URL 末尾段提取 SKU（如 gq75qn990ftxzg → GQ75QN990FTXZG）。

        欧洲 URL 末尾段是复合 slug（如 qn990f-75-inch-neo-qled-8k-mini-led-smart-tv-
        gq75qn990ftxzg），真正的 SKU 是其中以品牌前缀（GQ/QE/UE/TQ 等）开头的末尾段。
        取该段并大写；匹配不到时回退取末尾目录名。
        """
        path = (url or "").split("?")[0].split("#")[0].rstrip("/")
        if not path:
            return ""
        tail = path.rsplit("/", 1)[-1]
        for token in reversed(tail.split("-")):
            if re.match(r"^[a-z]{2,3}\d{2,3}[a-z0-9]+$", token, re.I):
                return token.upper()
        return tail.upper()

    def _series_from_sku(self, sku: str) -> str:
        """从欧洲 SKU 去掉品牌前缀 + 尺寸 + 地区尾码，取系列码主干。

        法国 SKU: GQ75QN990FTXZG → 前缀 GQ + 尺寸 75 + 系列码 QN990F + 后缀 TXZG
        英国 SKU: QE65S99HATXXU → 前缀 QE + 尺寸 65 + 系列码 S99H + 后缀 ATXXU
        规则: 去掉前缀(2-3 字母) + 尺寸(2-3 数字) → 剩余去掉常见后缀 → 得系列码。
        """
        value = (sku or "").upper()
        match = re.match(r"^[A-Z]{2,3}(\d{2,3})([A-Z0-9]+)$", value)
        if not match:
            return ""
        tail = match.group(2)
        for suffix in _EU_SKU_SUFFIXES:
            if tail.endswith(suffix) and len(tail) > len(suffix):
                candidate = tail[:-len(suffix)]
                if _SERIES_TOKEN_RE.fullmatch(candidate):
                    return candidate.upper()
        m2 = re.match(r"^([A-Z0-9]*[0-9][A-Z0-9]*?)[A-Z]{3,6}$", tail)
        if m2:
            candidate = m2.group(1)
            if candidate and _SERIES_TOKEN_RE.fullmatch(candidate):
                return candidate.upper()
        return tail

    def _series_from_text(self, text: str) -> str:
        """从产品卡标题取营销系列码，覆盖没有系列 slug 的卡片。"""
        for raw in re.findall(
                r"(?<![a-z0-9])([a-z]{1,4}\d[a-z0-9]{0,8})(?![a-z0-9])",
                text or "", re.I):
            token = raw.upper()
            if token in _SERIES_IGNORES:
                continue
            if token.startswith(("HDR", "HDMI", "ATSC")):
                continue
            if _SERIES_TOKEN_RE.fullmatch(token):
                return token
        return ""

    def _series_from_url(self, url: str) -> str:
        """从产品 URL 取系列码：优先 slug 中的营销系列码，否则从 SKU 提取。"""
        clean = (url or "").split("?")[0].split("#")[0].lower()
        match = re.search(r"/(?:tvs|lifestyle-tvs)/[a-z0-9\-]+/([^/]+)/?$", clean)
        if match:
            slug = match.group(1)
            parts = slug.split("-")
            for raw in reversed(parts[:-1]):  # 跳过末尾 SKU 段
                token = raw.upper()
                if token in _SERIES_IGNORES or not _SERIES_TOKEN_RE.fullmatch(token):
                    continue
                if token.startswith("TV") and len(token) > 2 and token[2].isalpha():
                    stripped = token[2:]
                    if _SERIES_TOKEN_RE.fullmatch(stripped):
                        token = stripped
                return token
        sku = self._sku_from_url(clean)
        return self._series_from_sku(sku) or sku or url

    def _series_from_card(self, url: str, text: str) -> str:
        return self._series_from_text(text) or self._series_from_url(url)

    def _clean_product_url(self, href: str) -> str:
        path = (href or "").split("?")[0].split("#")[0]
        if not path:
            return ""
        return path if path.startswith("http") else self.base_url + path

    def _is_tv_product_url(self, url: str) -> bool:
        """判断是否为 TV 产品页：含 /fr/tvs/ 或 /fr/lifestyle-tvs/，
        不含排除词，且末尾段含数字（区分产品页 vs 分类页）。

        分类页如 /fr/tvs/oled-tv/ 末尾段全是字母；产品页末尾段含型号数字。
        """
        low = (url or "").lower()
        if not any(segment in low for segment in _TV_PATH):
            return False
        if any(term in low for term in _EXCLUDE):
            return False
        path = low.split("?")[0].split("#")[0].rstrip("/")
        tail = path.rsplit("/", 1)[-1] if path else ""
        return bool(re.search(r"\d", tail))

    def _collect(self, dom: Dom | None, html: str) -> list[str]:
        """收集去重后的 TV SKU 链接；入口卡片审计另走 _collect_card_records。"""
        hrefs: list[str] = []
        if dom is not None:
            hrefs += dom.attr_list("a[href*='/fr/tvs/']", "href", limit=2000)
            hrefs += dom.attr_list("a[href*='/fr/lifestyle-tvs/']", "href",
                                   limit=2000)
        hrefs += _PRODUCT_RE.findall(html or "")
        out: list[str] = []
        seen: set[str] = set()
        for href in hrefs:
            url = self._clean_product_url(href)
            if not self._is_tv_product_url(url):
                continue
            sku = self._sku_from_url(url)
            if not sku or sku in seen:
                continue
            seen.add(sku)
            out.append(url)
        return out

    def _sizes_from_text(self, text: str) -> list[int]:
        return sorted({int(value) for value in _SIZE_RE.findall(text or "")
                       if 24 <= int(value) <= 120})

    def _collect_card_records(self, dom: Dom | None) -> list[dict]:
        """按真实产品卡读取代表 SKU、标题和尺寸控件。"""
        if dom is None:
            return []
        records: list[dict] = []
        seen_models: set[str] = set()
        seen_card_indexes: set[str] = set()
        for card in dom.sub(_CARD_SELECTOR, limit=200):
            hrefs = (card.attr_list("a[href*='/fr/tvs/']", "href", limit=60)
                     + card.attr_list("a[href*='/fr/lifestyle-tvs/']", "href",
                                      limit=60))
            if not hrefs:
                continue
            text = card.self_text()
            if len(hrefs) < 2 and not re.search(r"\bquick\s+view\b", text or "",
                                               re.I):
                continue
            urls: list[str] = []
            for href in hrefs:
                url = self._clean_product_url(href)
                if self._is_tv_product_url(url) and url not in urls:
                    urls.append(url)
            if not urls:
                continue
            url = urls[0]
            model = self._sku_from_url(url)
            card_index = card.self_attr("data-productidx")
            if card_index and card_index in seen_card_indexes:
                continue
            if not model or model in seen_models:
                continue
            seen_models.add(model)
            if card_index:
                seen_card_indexes.add(card_index)
            records.append({
                "card_index": card_index,
                "model": model,
                "series": self._series_from_card(url, text),
                "url": url,
                "sizes": self._sizes_from_text(text),
                "raw_href_count": len(hrefs),
            })
        return records

    def _result_count(self, dom: Dom | None, html: str) -> int | None:
        text = dom.self_text() if dom is not None else ""
        text = text or html or ""
        values = [int(value) for value in re.findall(
            r"\b(\d+)\s+Results?\b", text, re.I)]
        values += [int(value) for value in re.findall(
            r"\bResults?\s*\(\s*(\d+)\s*\)", text, re.I)]
        # 法语「résultats (41)」或「41 résultats」。
        values += [int(value) for value in re.findall(
            r"\b(\d+)\s+r[ée]sultats?\b", text, re.I)]
        values += [int(value) for value in re.findall(
            r"\br[ée]sultats?\s*\(\s*(\d+)\s*\)", text, re.I)]
        return max(values) if values else None

    def series_entries(self, open_dom):
        """读取结果卡，合并同系列卡片并记录每卡可见尺寸。"""
        entry_status: dict = {}
        raw_link_count = 0
        dom_card_count = 0
        result_count: int | None = None
        raw_urls: list[str] = []
        card_records: list[dict] = []
        try:
            with open_dom(self.ENTRY, self.spec_entry_wait) as (res, dom, html):
                entry_status = {
                    "status": res.status,
                    "blocked": res.blocked,
                    "block_reason": res.block_reason,
                    "error": res.error,
                    "meta": dict(getattr(res, "meta", {}) or {}),
                }
                if dom is None or not res.ok:
                    self.last_entry_audit = {
                        "requested_url": self.ENTRY,
                        "discovered_model_count": 0,
                        "discovered_series_count": 0,
                        "termination_reason": "entry_failed",
                        "details": {
                            "result_count": None,
                            "entry": entry_status,
                            "series": [],
                        },
                    }
                    return []
                raw_link_count = (dom.count("a[href*='/fr/tvs/']")
                                  + dom.count("a[href*='/fr/lifestyle-tvs/']"))
                dom_card_count = dom.count(_CARD_SELECTOR)
                body_text = dom.self_text() or ""
                entry_status["view_more_text_present"] = bool(
                    re.search(r"\b(view\s+more|voir\s+plus)\b", body_text,
                              re.I))
                entry_status["show_all_text_present"] = bool(
                    re.search(r"\b(show\s+all|voir\s+tout)\b", body_text,
                              re.I))
                result_count = self._result_count(dom, html)
                raw_urls = self._collect(dom, html)
                card_records = self._collect_card_records(dom)
                if not card_records:
                    card_records = [{
                        "card_index": "",
                        "model": self._sku_from_url(url),
                        "series": self._series_from_url(url),
                        "url": url,
                        "sizes": [],
                        "raw_href_count": 0,
                    } for url in raw_urls]
        except Exception as exc:
            self.last_entry_audit = {
                "requested_url": self.ENTRY,
                "discovered_model_count": len(card_records),
                "discovered_series_count": 0,
                "termination_reason": "entry_exception",
                "details": {
                    "result_count": result_count,
                    "raw_sku_link_count": raw_link_count,
                    "raw_unique_sku_count": len(raw_urls),
                    "dom_card_container_count": dom_card_count,
                    "product_card_count": len(card_records),
                    "entry": entry_status,
                    "error": f"{type(exc).__name__}: {exc}",
                    "series": [],
                },
            }
            return []

        groups: dict[str, dict] = {}
        for record in card_records:
            model = str(record.get("model") or "")
            url = str(record.get("url") or "")
            series = str(record.get("series") or self._series_from_url(url)
                         ).strip().upper()
            if not model or not url or not series:
                continue
            group = groups.setdefault(series, {
                "representative_url": url,
                "models": [],
                "urls": [],
                "sizes": set(),
                "cards": [],
            })
            if model not in group["models"]:
                group["models"].append(model)
            if url not in group["urls"]:
                group["urls"].append(url)
            group["sizes"].update(int(size) for size in record.get("sizes") or [])
            group["cards"].append(record)

        entries: list[tuple[str, list[str]]] = []
        details_series: list[dict] = []
        for series, info in groups.items():
            representative = str(info["representative_url"])
            entries.append((series, [representative]))
            details_series.append({
                "series": series,
                "models": list(info["models"]),
                "urls": list(info["urls"]),
                "representative_url": representative,
                "sizes": sorted(info["sizes"]),
                "card_count": len(info["cards"]),
            })

        meta = entry_status.get("meta") or {}
        self.last_entry_audit = {
            "requested_url": self.ENTRY,
            "discovered_model_count": len(card_records),
            "discovered_series_count": len(entries),
            "termination_reason": (
                str(meta.get("scroll_termination") or "entry_dom")
            ),
            "details": {
                "result_count": result_count,
                "raw_sku_link_count": raw_link_count,
                "raw_unique_sku_count": len(raw_urls),
                "unique_sku_count": len({str(x.get('model') or '') for x in card_records
                                         if x.get('model')}),
                "dom_card_container_count": dom_card_count,
                "product_card_count": len(card_records),
                "normalized_series_count": len(entries),
                "view_more_text_present": bool(entry_status.get("view_more_text_present")),
                "show_all_text_present": bool(entry_status.get("show_all_text_present")),
                "entry": entry_status,
                "cards": card_records,
                "series": details_series,
            },
        }
        return entries

    def model_from_url(self, url: str) -> str:
        return self._sku_from_url(url) or url

    def parse_spec_model(self, dom: Dom | None, series: str, model: str,
                         url: str = "") -> SpecSheet:
        empty = SpecSheet(brand=self.code, brand_name=self.name, series=series,
                          url=url)
        if dom is None:
            return empty
        # 1) 优先：滚动渲染后从规格分组容器结构化提取完整规格（单机型）。
        import json
        try:
            raw = dom.eval_js(self._SPEC_JS) or "[]"
            triples = json.loads(raw)
        except Exception:
            triples = []
        if triples:
            sheet = parse_samsung_us_fullspecs(triples, model, series,
                                               self.code, self.name, url)
            if sheet.rows:
                return sheet
        # 2) 回退：从 __NEXT_DATA__ + JSON-LD 提取概要规格。
        html = dom.html()
        if not html:
            return empty
        return parse_samsung_us_html(html, self.code, self.name, series, model,
                                    url)
