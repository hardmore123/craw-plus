"""松下 VIERA（日本）TV 官网 SPEC 适配器（多级流程）。

实测结构（2026-09）：
- 产品总览 https://panasonic.jp/viera/products.html 列各系列页 /viera/<系列>.html
  （如 W97C / Z95C / W95C / W93C / Z95B / Z90B / W90B / W80C / MR770 / N50C）
- 系列页 /viera/<系列>.html 列该系列各尺寸型号的 SPEC 页
  /viera/products/TV-<尺寸><系列>/spec.html（也有 TH- 前缀的旧机型）
- SPEC 页 = 单表 table.c-prd007__table，多层 rowspan 分类结构，单机型单值。

一个系列有多个尺寸型号（各自一页），采集时抓齐后横排合并成一张多机型表。
走框架的多级 SPEC 流程：series_entries + parse_spec_model + model_from_url。
"""
from __future__ import annotations

import re

from ...models import L1_MILD, SpecSheet
from ...spec_parser import parse_panasonic_table
from ...fetchers import Dom
from .. import SiteAdapter

# 系列码：字母开头且必须含数字（如 W97C / Z95C / MR770 / N50C / LF2 / LW2），
# 借此排除 PRODUCTS / OPTION / SUPPORT 等纯字母导航链接。
# 兼容 -series 后缀（如 LF2-series.html / LW2-series.html）。
_SERIES_HREF = re.compile(r"/viera/([A-Z]{1,3}\d{1,4}[A-Z]?(?:-series)?)\.html$", re.I)
# 型号 spec 链接有两种格式：
#   /viera/products/((?:TH|TV)-xxx)/spec.html  (标准格式)
#   /viera/p-db/((?:TH|TV)-xxx)_spec.html      (p-db 格式，如 MR770)
_MODEL_HREF = re.compile(r"/viera/(?:products/((?:TH|TV)-[0-9A-Za-z]+)/spec|p-db/((?:TH|TV)-[0-9A-Za-z]+)_spec)\.html", re.I)


class PanasonicJpAdapter(SiteAdapter):
    code = "panasonic_jp"
    name = "松下 VIERA（日本）"
    base_url = "https://panasonic.jp"
    country = "日本"
    channel = "Panasonic 官网"
    protection = L1_MILD
    requires_browser = True
    suggested_interval = 4.0
    supports_spec = True
    spec_entry_wait = "a[href*='/viera/']"
    # 总览系列链接由脚本延迟注入，入口额外等待后再读取完整列表。
    spec_entry_extra_wait_ms = 5000
    spec_page_wait = "table.c-prd007__table"
    # 松下页面完整加载很慢（分析脚本多），用 commit 尽早拿到 DOM，靠 wait_selector 等内容
    spec_wait_until = "commit"

    PRODUCTS = "https://panasonic.jp/viera/products.html"

    def spec_entry_url(self) -> str:
        return self.PRODUCTS

    # ---- 多级流程 ----
    def series_entries(self, open_dom):
        """products.html → 各系列页 → 各型号 SPEC 页 URL。"""
        # 1) 产品总览取系列页
        series_pages: list[tuple[str, str]] = []   # (系列名, 系列页URL)
        with open_dom(self.PRODUCTS, "a[href*='/viera/']") as (res, dom, html):
            if dom is None or not res.ok:
                return []
            hrefs = dom.attr_list("a[href*='/viera/']", "href", limit=400)
            hrefs += re.findall(r'href="([^"]*/viera/[^"]*)"', html or "")
            seen: set[str] = set()
            for h in hrefs:
                m = _SERIES_HREF.search(h or "")
                if not m:
                    continue
                code = m.group(1).upper()
                if code in seen:
                    continue
                seen.add(code)
                # 归一化URL: 保留原始大小写(/viera/LF2-series.html)
                # 用正则匹配到的原始href构造,否则用base_url+原始href
                url = h if h.startswith("http") else self.base_url + h
                series_pages.append((code, url))

        # 2) 逐系列页取型号 SPEC URL
        entries: list[tuple[str, list[str]]] = []
        for code, spurl in series_pages:
            model_urls: list[str] = []
            try:
                with open_dom(spurl, "a[href*='/viera/']") as (res, dom, html):
                    # W80C等系列页可能返回ok=False(重定向),但html仍在,放宽到dom可用
                    if dom is None:
                        continue
                    hrefs = dom.attr_list("a[href*='/viera/']", "href", limit=400)
                    hrefs += re.findall(r'href="([^"]*/viera/[^"]*)"', html or "")
                    seen_m: set[str] = set()
                    for h in hrefs:
                        m = _MODEL_HREF.search(h or "")
                        if not m:
                            continue
                        # 取两个捕获组中非None的(标准格式 vs p-db格式)
                        model = (m.group(1) or m.group(2) or "").upper()
                        if not model or model in seen_m:
                            continue
                        seen_m.add(model)
                        # 用原始href构造完整URL(保留两种格式)
                        full = h if h.startswith("http") else self.base_url + h
                        model_urls.append(full)
            except Exception:
                pass
            if model_urls:
                entries.append((code, model_urls))
        return entries

    def model_from_url(self, url: str) -> str:
        m = _MODEL_HREF.search(url or "")
        if m:
            return (m.group(1) or m.group(2) or "").upper()
        return url

    def parse_spec_model(self, dom: Dom | None, series: str, model: str,
                         url: str = "") -> SpecSheet:
        empty = SpecSheet(brand=self.code, brand_name=self.name, series=series,
                          url=url, models=[model])
        if dom is None:
            return empty
        tables = dom.sub("table.c-prd007__table", limit=1)
        if not tables:
            tables = dom.sub("table", limit=1)
        if not tables:
            return empty
        return parse_panasonic_table(tables[0], self.code, self.name, series, model, url)
