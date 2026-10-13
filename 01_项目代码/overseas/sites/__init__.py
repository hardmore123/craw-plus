"""站点适配插件层：基类 + 自动发现注册中心。

注册机制借鉴 Crawl4AI 的 hub.py：约定 sites/<code>/adapter.py 目录结构，
动态 import 并把 SiteAdapter 子类登记进来。新增一个站点只要建目录，
不需要改核心代码（cert_verify 里是手写 ProviderRouter，扩展性差一些）。

新增站点最小步骤：
    sites/<code>/__init__.py       空文件
    sites/<code>/adapter.py        继承 SiteAdapter，给出 URL 规则
    sites/<code>/schema.json       声明式抽取规则（选择器写这里）
"""
from __future__ import annotations

import importlib
import os

from ..extract import Extractor, load_schema
from ..fetchers import Dom
from ..models import L2_MEDIUM, SearchHit

_HERE = os.path.dirname(os.path.abspath(__file__))


class SiteAdapter:
    """站点适配器基类。

    职责边界：适配器只负责「URL 怎么拼」和「列表页怎么取商品」，
    字段抽取全部交给 schema.json + Extractor，保持站点代码极薄。
    """

    code: str = ""
    name: str = ""
    base_url: str = ""
    country: str = ""          # 所属国家（导出表「所属国家」列），如 Canada
    channel: str = ""          # 渠道（导出表「渠道」列），如 Amazon
    protection: str = L2_MEDIUM
    requires_browser: bool = True
    # 建议的抓取间隔（秒）；场景层会取 max(全局配置, 本值)
    suggested_interval: float = 6.0
    # 能力标记：SPEC 采集站点（如日本各品牌官网）置 True
    supports_spec: bool = False
    # 能力标记：零售站（价格 + 网评来源，同一商品页同步抽取）置 True
    supports_retail: bool = False
    # 能力标记：媒体评测站（编辑评测文章 → 评分/优缺点/品牌）置 True
    supports_media: bool = False
    # 媒体评测提取模式：jsonld_review / jsonld_product / jsonld_product_only / html
    extract_mode: str = ""
    # 评分量表标注（如 "0-10" / "0-5" / "1-5反序"），必填
    rating_scale: str = ""
    # 零售商品页等待锚点（浏览器路径用）
    retail_page_wait: str = "body"

    def __init__(self):
        self.schema: dict = {}
        # 用适配器所在模块的文件路径定位同目录 schema.json
        mod = importlib.import_module(self.__class__.__module__)
        d = os.path.dirname(os.path.abspath(mod.__file__))
        sp = os.path.join(d, "schema.json")
        if os.path.exists(sp):
            self.schema = load_schema(sp)

    # ---- URL 规则（子类实现）----
    def search_url(self, keyword: str, page: int = 1) -> str:
        raise NotImplementedError(f"{self.code} 未实现 search_url")

    def product_url(self, sku: str) -> str:
        raise NotImplementedError(f"{self.code} 未实现 product_url")

    def reviews_url(self, sku: str, page: int = 1) -> str:
        """独立评价页；返回空串表示评价只在商品页上取。"""
        return ""

    # ---- 抽取器 ----
    def extractor(self, html: str = "") -> Extractor:
        return Extractor(self.schema, html=html, base_url=self.base_url)

    def anchor(self) -> str:
        return self.schema.get("anchor") or ""

    # ---- SPEC 能力（仅 supports_spec 的站点实现）----
    def list_series(self, dom: Dom | None, html: str = "") -> list[tuple[str, str]]:
        """从入口页解析系列列表，返回 [(系列名, SPEC页URL), ...]。"""
        raise NotImplementedError(f"{self.code} 未实现 list_series")

    def spec_entry_url(self) -> str:
        """SPEC 系列入口页 URL。"""
        raise NotImplementedError(f"{self.code} 未实现 spec_entry_url")

    # 入口页等待锚点：JS 渲染的列表页需等此选择器出现再取 HTML。空则等 body。
    spec_entry_wait: str = "body"
    # SPEC 页等待锚点，默认等 table。
    spec_page_wait: str = "table"
    # 入口页动态遍历配置：启用后滚动到目标链接集合稳定，最大次数仅作安全阀。
    spec_entry_scroll_until_stable: bool = False
    spec_entry_scroll_growth_selector: str = ""
    spec_entry_scroll_max_passes: int = 80
    spec_entry_scroll_stable_rounds: int = 2
    spec_entry_click_selectors: list[str] | None = None
    spec_entry_click_repeats: int = 0
    spec_entry_click_wait_ms: int = 2500
    spec_entry_click_growth_selector: str = ""
    # 用户/页面诊断给出的参考值，不参与准入和终止判断；实际数量以审计为准。
    spec_entry_expected_model_count: int | None = None
    spec_entry_expected_series_count: int | None = None
    last_entry_audit: dict = {}

    def parse_spec(self, dom: Dom | None, series: str, url: str = ""):
        """解析某系列 SPEC 页为 SpecSheet。"""
        raise NotImplementedError(f"{self.code} 未实现 parse_spec")

    # ---- 多级 SPEC 采集（可选，用于「入口→系列页→多型号页」的站点，如松下）----
    # 适配器实现 series_entries 后，spec_crawl 会改走「一系列抓多型号页并横排合并」的
    # 流程；不实现则走默认「一系列一页」流程。
    def series_entries(self, open_dom) -> list[tuple[str, list[str]]] | None:
        """返回 [(系列名, [该系列各型号的 SPEC 页 URL, ...]), ...]。

        open_dom(url, wait_selector) 是一个上下文管理器，产出 (res, dom, html)，
        供适配器在需要时抓取中间页（如系列列表页）。返回 None 表示不使用多级流程。
        """
        return None

    def parse_spec_model(self, dom: Dom | None, series: str, model: str, url: str = ""):
        """解析单个型号的 SPEC 页为单机型 SpecSheet（多级流程用）。"""
        raise NotImplementedError(f"{self.code} 未实现 parse_spec_model")

    def model_from_url(self, url: str) -> str:
        """从型号 SPEC 页 URL 提取机型号（多级流程用）。默认取末段目录名。"""
        import re as _re
        m = _re.search(r"/([A-Za-z0-9\-]+)/spec", url or "")
        return m.group(1) if m else url

    # ---- 零售站能力（价格 + 网评同步抽取；仅 supports_retail 的站点实现）----
    def parse_product(self, dom, sku: str = "", url: str = ""):
        """从同一个商品页同步抽取价格与评价，返回 ProductPayload。

        这是加拿大等「多零售站、价格与评价同源」线的核心：一次打开商品页，
        既取当前售价（PriceSnapshot），又取评分聚合（ReviewSummary）和评价列表
        （list[Review]），避免价格线和网评线各访问一次。子类按各站 DOM 实现。

        约定：dom 为 None 或页面无效时返回仅含 Product 骨架的空 payload。
        """
        raise NotImplementedError(f"{self.code} 未实现 parse_product")

    # ---- 媒体评测站能力（仅 supports_media 的站点实现）----
    def review_list_url(self, category: str = "", page: int = 1) -> str:
        """评测列表页 URL。category 可选品类筛选（如 'televisies'）。"""
        raise NotImplementedError(f"{self.code} 未实现 review_list_url")

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页解析评测文章 URL 列表。"""
        raise NotImplementedError(f"{self.code} 未实现 parse_review_list")

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页提取 MediaReview（评分/优缺点/品牌/型号/日期）。

        返回 dict 或 dataclass，字段对齐 media_review 表：
        product_name, product_model, product_brand, rating_value, best_rating,
        positive_notes, negative_notes, headline, date_published, author。
        提取不到返回 None。
        """
        raise NotImplementedError(f"{self.code} 未实现 parse_review")

    def find_product(self, dom, html: str = "", model: str = "",
                     query: str = ""):
        """从搜索结果页挑出最匹配给定型号的商品 (SearchHit)，找不到返回 None。

        默认用 parse_search 取候选，优先「型号归一化后出现在候选标题/sku」的命中；
        没有任何候选真正包含型号时返回 None（宁缺毋滥，避免把无关商品/配件当成匹配，
        导致价格/评价张冠李戴）。站点可覆盖以适配自有匹配逻辑。
        """
        hits = self.parse_search(dom, html, limit=40)
        if not hits:
            return None
        import re as _re

        def _norm(s: str) -> str:
            return _re.sub(r"[^a-z0-9]+", "", (s or "").lower())

        want = _norm(model)
        if not want:
            return hits[0]
        # 精确：型号整体出现在候选文本中
        for hit in hits:
            if want in _norm(hit.sku + " " + (hit.title or "")):
                return hit
        # 宽松：型号去掉尾部字母/尺寸后的主干出现（如 55QD8SF-PRO → QD8SF）
        core = _re.sub(r"^\d{2,3}", "", want)
        core = _re.sub(r"(pro|max)$", "", core)
        if len(core) >= 4:
            for hit in hits:
                if core in _norm(hit.sku + " " + (hit.title or "")):
                    return hit
        # 都不含型号 → 视为未匹配，返回 None（不再盲取第一个）
        return None

    # ---- 列表页解析（默认由 schema["search"] 驱动，可覆盖）----
    def parse_search(self, dom: Dom | None, html: str = "",
                     limit: int = 50) -> list[SearchHit]:
        cfg = self.schema.get("search") or {}
        container = cfg.get("container") or ""
        if dom is None or not container:
            return []
        ex = self.extractor(html)
        tmpl = cfg.get("url_template") or ""
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for i, block in enumerate(dom.sub(container, limit=max(limit * 3, limit))):
            sku = str(ex.raw(block, cfg.get("sku") or {})).strip()
            if not sku or sku in seen:
                continue
            seen.add(sku)
            title = ""
            if cfg.get("title"):
                title = str(ex.value(block, cfg["title"]) or "")
            url = ""
            if cfg.get("url"):
                url = str(ex.raw(block, cfg["url"]) or "")
                if url.startswith("/"):
                    url = self.base_url.rstrip("/") + url
            if not url and tmpl:
                url = tmpl.format(sku=sku)
            hits.append(SearchHit(sku=sku, url=url, title=title, rank=len(hits) + 1))
            if len(hits) >= limit:
                break
        return hits

    def meta(self) -> dict:
        return {"code": self.code, "name": self.name, "base_url": self.base_url,
                "protection": self.protection,
                "requires_browser": self.requires_browser,
                "suggested_interval": self.suggested_interval,
                "has_schema": bool(self.schema),
                "supports_search": bool((self.schema or {}).get("search"))}


class SiteRegistry:
    """自动发现 sites/ 下的适配器。"""

    _cache: dict[str, type[SiteAdapter]] = {}

    @classmethod
    def discover(cls, force: bool = False) -> dict[str, type[SiteAdapter]]:
        if cls._cache and not force:
            return cls._cache
        cls._cache = {}
        for entry in sorted(os.listdir(_HERE)):
            d = os.path.join(_HERE, entry)
            if not os.path.isdir(d) or entry.startswith(("_", ".")):
                continue
            if not os.path.exists(os.path.join(d, "adapter.py")):
                continue
            try:
                mod = importlib.import_module(f"{__name__}.{entry}.adapter")
            except Exception as e:                       # 单个站点坏了不影响其它
                print(f"[warn] 加载站点 {entry} 失败: {type(e).__name__}: {e}")
                continue
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if (isinstance(obj, type) and issubclass(obj, SiteAdapter)
                        and obj is not SiteAdapter):
                    cls._cache[obj.code or entry] = obj
        return cls._cache

    @classmethod
    def get(cls, code: str) -> SiteAdapter:
        reg = cls.discover()
        if code not in reg:
            raise KeyError(f"未注册的站点: {code}（可用: {sorted(reg)}）")
        return reg[code]()

    @classmethod
    def codes(cls) -> list[str]:
        return sorted(cls.discover().keys())

    @classmethod
    def all_meta(cls) -> list[dict]:
        out = []
        for code in cls.codes():
            try:
                out.append(cls.get(code).meta())
            except Exception as e:
                out.append({"code": code, "error": f"{type(e).__name__}: {e}"})
        return out


__all__ = ["SiteAdapter", "SiteRegistry"]
