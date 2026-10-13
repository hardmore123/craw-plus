"""Sony 德国官网 TV SPEC 适配器（多级流程，Hybris/SPA 站）。

实测结构（2026-09，https://www.sony.de/）：
- 入口页 /bravia/gallery 列各产品链接，格式
  /bravia/products/<series-slug>?sku=<model>
  series-slug 如 bravia-3-ii / z9k-series / x80l-x81bl-series / bravia-5；
  SKU（型号）在 ?sku= 参数中，如 k43xr35m2pb.cei / xr75z9kaep / kd65x80laep。
- 同一 series-slug 下有多个尺寸型号，各自一页；按 series-slug 归组，逐型号
  抓产品页 JSON 后横排合并成多机型表。
- 产品页规格在内嵌产品状态 JSON 的 "classifications" 里：
  [{code,name,features:[{code,name,featureValues:[{value}]}]}]，
  与 sony_us / sony_ca 同源（Sony 全球 Hybris 站统一结构）。

只做 SPEC；价格/网评由零售站适配器负责。
"""
from __future__ import annotations

import json
import re
import urllib.parse

from ...fetchers import Dom
from ...models import L2_MEDIUM, SpecSheet
from ...spec_parser import GENERIC_SPEC_JS, parse_en_kv_pairs
from .. import SiteAdapter

# 产品链接：/bravia/products/<series-slug>?sku=<model>
_PRODUCT_RE = re.compile(
    r"/bravia/products/([a-z0-9-]+)\?sku=([^\"'#&\s]+)", re.I)


def _balanced_json_text(text: str, start: int) -> str:
    """从 start 起按括号配平返回一段 JSON 文本（用于内嵌转义 JSON）。"""
    stack: list[str] = []
    closing = {"}": "{", "]": "["}
    for index in range(start, len(text)):
        char = text[index]
        if char in "[{":
            stack.append(char)
        elif char in closing:
            if not stack or stack[-1] != closing[char]:
                return ""
            stack.pop()
            if not stack:
                return text[start:index + 1]
    return ""


def _embedded_json_values(text: str, field: str) -> list | dict:
    """从内嵌状态 JSON 中按字段名摘出子结构（如 classifications）。"""
    markers = [(f'"{field}":', False), (f'\\"{field}\\":', True)]
    decoder = json.JSONDecoder()
    for marker, escaped in markers:
        offset = 0
        while True:
            position = text.find(marker, offset)
            if position < 0:
                break
            start = text.find("[" if field == "classifications" else "{",
                              position + len(marker))
            if start < 0:
                break
            try:
                if escaped:
                    raw = _balanced_json_text(text, start)
                    value = json.loads(json.loads('"' + raw + '"')) if raw else None
                else:
                    value, _ = decoder.raw_decode(text[start:])
                if isinstance(value, (list, dict)):
                    return value
            except (ValueError, json.JSONDecodeError):
                pass
            offset = position + len(marker)
    return [] if field == "classifications" else {}


def _classification_triples(html: str) -> list[list[str]]:
    """从产品页内嵌 classifications JSON 提取 [(区分, 项目, 值), ...] 三元组。"""
    classifications = _embedded_json_values(html, "classifications")
    if not isinstance(classifications, list):
        return []
    triples: list[list[str]] = []
    for group in classifications:
        if not isinstance(group, dict):
            continue
        category = str(group.get("name") or group.get("code") or "").strip()
        for feature in group.get("features") or []:
            if not isinstance(feature, dict):
                continue
            item = str(feature.get("name") or "").strip()
            if not item:
                continue
            values = []
            for entry in feature.get("featureValues") or []:
                if isinstance(entry, dict):
                    value = str(entry.get("value") or "").strip()
                    if value and value not in values:
                        values.append(value)
            triples.append([category, item, " / ".join(values)])
    return triples


class SonyDeAdapter(SiteAdapter):
    code = "sony_de"
    name = "Sony（德国）"
    base_url = "https://www.sony.de"
    country = "德国"
    channel = "Sony 官网"
    protection = L2_MEDIUM
    requires_browser = True
    # Sony gallery 页对持久化 profile 返回 403（182字节空页），
    # 但无 profile 的全新 context 能正常渲染（1.1MB + 39产品链接）。
    no_browser_profile = True
    # 临时context需要更长等待让gallery页JS加载完产品链接
    spec_entry_extra_wait_ms = 5000
    suggested_interval = 4.0
    supports_spec = True
    spec_entry_wait = "a[href*='/bravia/products/']"
    spec_page_wait = ".SpecificationsTable__Table"
    # spec 页规格表较长，需滚动到底部才能加载全部行
    spec_page_scroll_passes = 10
    # 入口页滚动配置：gallery 页产品卡片懒加载，滚动到链接稳定。
    spec_entry_scroll_until_stable = True
    spec_entry_scroll_growth_selector = "a[href*='/bravia/products/']"
    spec_entry_scroll_max_passes = 20
    spec_entry_scroll_stable_rounds = 2

    ENTRY = "https://www.sony.de/bravia/gallery"
    # 审计参考值，不参与准入和终止判断。
    spec_entry_expected_series_count = 12

    def spec_entry_url(self) -> str:
        return self.ENTRY

    def series_entries(self, open_dom):
        """从 gallery 页提取所有 /bravia/products/ 链接，按 series-slug 分组。

        返回 [(series-slug, [该系列各型号的产品页 URL, ...]), ...]。
        每个 URL 形如 https://www.sony.de/bravia/products/<slug>?sku=<model>。
        """
        series_map: dict[str, list[str]] = {}
        page_audit: list[dict] = []
        termination = "entry_failed"

        try:
            # 临时 context（no_browser_profile）在 headless 下不稳定，
            # 入口页可能首次加载失败，重试一次。
            for _attempt in range(2):
                with open_dom(self.ENTRY, self.spec_entry_wait) as (res, dom, html):
                    page_info: dict = {"url": self.ENTRY}
                    page_info["status"] = res.status
                    page_info["meta"] = dict(getattr(res, "meta", {}) or {})
                    # Sony gallery 页可能返回 403 但页面实际正常渲染（有产品链接），
                    # 所以只要 dom 存在就继续提取，不因 blocked 而中断。
                    if dom is None:
                        page_info["reason"] = res.error or res.block_reason or str(res.status)
                        page_audit.append(page_info)
                        termination = "entry_failed"
                        continue  # 重试
                    hrefs = dom.attr_list("a[href*='/bravia/products/']", "href", limit=800)
                    # 补充正则兜底（从HTML中提取完整URL）
                    hrefs += re.findall(r'href="([^"]*/bravia/products/[^"]+)"', html or "", re.I)
                    seen_urls: set[str] = set()
                    for href in hrefs:
                        if not href or not isinstance(href, str):
                            continue
                        # href 可能是相对或绝对 URL；统一解析出 series-slug 与 sku
                        full_url = self._normalize_url(href)
                        m = _PRODUCT_RE.search(full_url)
                        if not m:
                            continue
                        series_slug = m.group(1).lower()
                        sku_raw = m.group(2)
                        # URL 去重（同 series+sku 唯一）
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)
                        # 规格在独立 /spec 页：产品页 .../products/<slug>?sku=<model>
                        # → spec 页 .../products/<slug>/spec?sku=<model>
                        spec_url = full_url.replace(
                            f"/{series_slug}?", f"/{series_slug}/spec?")
                        series_map.setdefault(series_slug, []).append(spec_url)
                    page_info["series_count"] = len(series_map)
                    page_info["model_count"] = sum(len(v) for v in series_map.values())
                    page_audit.append(page_info)
                    termination = str(
                        page_info["meta"].get("scroll_termination") or "stable")
                    break  # 成功，退出重试循环
        except Exception as exc:
            page_audit.append({"url": self.ENTRY,
                               "error": f"{type(exc).__name__}: {exc}"})
            termination = "entry_exception"

        entries: list[tuple[str, list[str]]] = [
            (series, urls) for series, urls in series_map.items()
        ]

        self.last_entry_audit = {
            "requested_url": self.ENTRY,
            "expected_series_count": self.spec_entry_expected_series_count,
            "discovered_series_count": len(entries),
            "discovered_model_count": sum(len(urls) for _, urls in entries),
            "termination_reason": termination,
            "details": {
                "pages": page_audit,
                "series": [
                    {"series": series,
                     "models": [{"model": self.model_from_url(url), "url": url}
                                for url in urls]}
                    for series, urls in entries
                ],
            },
        }
        return entries

    def _normalize_url(self, href: str) -> str:
        """把相对/绝对 href 规整为带 base_url 的绝对 URL。"""
        href = (href or "").strip()
        if not href:
            return ""
        if href.startswith("http"):
            return href
        if href.startswith("/"):
            return self.base_url.rstrip("/") + href
        return self.base_url.rstrip("/") + "/" + href

    def model_from_url(self, url: str) -> str:
        """从产品页 URL 的 ?sku= 参数提取型号，保留原样大小写。"""
        parsed = urllib.parse.urlparse(url or "")
        qs = urllib.parse.parse_qs(parsed.query)
        sku = (qs.get("sku") or [""])[0]
        if sku:
            return sku
        # 兜底：正则从字符串中取 sku=
        m = re.search(r"[?&]sku=([^&#\s]+)", url or "", re.I)
        return m.group(1) if m else url

    # Sony spec 页规格表提取 JS（sku 嵌入字符串，因为 eval_js 不支持传参）
    _SPEC_JS_TMPL = (
        "() => {{"
        " const out = [];"
        " const table = document.querySelector('.SpecificationsTable__Table');"
        " if (!table) return JSON.stringify([]);"
        " const rows = table.querySelectorAll('tr');"
        " const skuLower = '{sku}';"
        " let targetCol = 1;"
        " for (let r = 0; r < Math.min(rows.length, 3); r++) {{"
        "   const cells = rows[r].querySelectorAll('th, td');"
        "   for (let i = 1; i < cells.length; i++) {{"
        "     if ((cells[i].textContent || '').toLowerCase().includes(skuLower)) {{"
        "       targetCol = i; break;"
        "     }}"
        "   }}"
        " }}"
        " let cat = '';"
        " for (let r = 1; r < rows.length; r++) {{"
        "   const cells = rows[r].querySelectorAll('th, td');"
        "   if (!cells.length) continue;"
        "   const key = (cells[0].textContent || '').trim().split('::')[0].trim();"
        "   if (cells.length === 1) {{ cat = key; continue; }}"
        "   let val = '';"
        "   if (targetCol < cells.length) {{"
        "     const inner = cells[targetCol].querySelector('.SpecificationsTable__TableCellInner');"
        "     val = (inner || cells[targetCol]).textContent.trim().split('::')[0].trim();"
        "   }}"
        "   if (key && val) out.push([cat, key, val]);"
        " }}"
        " return JSON.stringify(out);"
        "}}"
    )

    def parse_spec_model(self, dom: Dom | None, series: str, model: str,
                         url: str = "") -> SpecSheet:
        """从 Sony /spec 页提取规格表（.SpecificationsTable__Table 多列布局）。"""
        empty = SpecSheet(brand=self.code, brand_name=self.name, series=series,
                          url=url, models=[model])
        if dom is None:
            return empty
        eval_js = getattr(dom, "eval_js", None)
        if not callable(eval_js):
            return empty
        # 从 URL 提取 sku 参数，嵌入 JS 字符串
        sku = (self.model_from_url(url) if url else model).lower()
        js = self._SPEC_JS_TMPL.format(sku=sku)
        try:
            raw = eval_js(js) or "[]"
        except Exception:
            raw = "[]"
        try:
            triples = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            triples = []
        if not triples:
            return empty
        return parse_en_kv_pairs(triples, self.code, self.name, series, model, url)
