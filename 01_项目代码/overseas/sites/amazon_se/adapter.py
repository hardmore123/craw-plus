"""Amazon Sweden 适配器（价格 + 网评同页同步抓取，schema 驱动）。

防护等级 L3（强）：必须真实浏览器，且要低频。与 amazon_de/es/fr/it/uk 前端同构，
data-hook 站内稳定属性，抽取规则全在 schema.json（六段：anchor/search/product/
price/specs/summary/reviews），本适配器只负责 URL 规则与搜索候选解析。

实测要点：
- 搜索页 https://www.amazon.se/s?k=<kw> → HTTP 200，div[data-asin] 候选
- 商品页 https://www.amazon.se/dp/<ASIN> → HTTP 200，价格/评分/评价同一页
- 货币：SEK（价格文本如 "12 990,00 kr"，空格千分位+逗号小数点；t_money 已兼容）
- model 标签：amazon.se 的 detailBullets 保留英文 "Item model number"（瑞典语亦作 Modellnummer）
注意：单次探测通过不代表批量安全，规模化后大概率触发验证码，需低频 + 代理。
"""
from __future__ import annotations

import urllib.parse

from ...models import L3_STRONG, SearchHit
from .. import SiteAdapter


class AmazonSeAdapter(SiteAdapter):
    code = "amazon_se"
    name = "Amazon Sweden"
    base_url = "https://www.amazon.se"
    country = "Sweden"
    channel = "Amazon"
    protection = L3_STRONG
    requires_browser = True
    supports_retail = True
    retail_page_wait = "#productTitle, #dp, .a-price"
    suggested_interval = 8.0        # 强防护站点，宁慢不封

    def search_url(self, keyword: str, page: int = 1) -> str:
        q = urllib.parse.urlencode({"k": keyword}, safe="")
        url = f"{self.base_url}/s?{q}"
        if page and page > 1:
            url += f"&page={int(page)}"
        return url

    def product_url(self, sku: str) -> str:
        v = str(sku or "").strip()
        if v.startswith("http"):
            return v
        if v.startswith("/"):
            return self.base_url.rstrip("/") + v
        return f"{self.base_url}/dp/{v}"

    def reviews_url(self, sku: str, page: int = 1) -> str:
        """不使用独立评价页：/product-reviews/<ASIN> 对代理/无会话返回空壳（实测）。
        PDP 内嵌评价区（[data-hook='review'] 首屏）才是可靠来源。
        返回空串禁用翻页，框架改用 collect_detail 已抓到的 PDP 首屏评价。
        """
        return ""

    def parse_search(self, dom, html: str = "", limit: int = 40) -> list[SearchHit]:
        if dom is None:
            return []
        hits: list[SearchHit] = []
        seen: set[str] = set()
        for block in dom.sub("div[data-asin]:not([data-asin=''])", limit=limit * 2):
            asin = (block.self_attr("data-asin") or "").strip()
            if not asin or asin in seen:
                continue
            seen.add(asin)
            title = ""
            for sel in ("h2 span:not([class])", "a[class*='s-line-clamp']",
                        "span.a-size-medium", "h2 span",
                        "[data-cy='title-recipe'] span"):
                title = block.text(sel)
                if title:
                    break
            if not title:
                title = " ".join((block.self_text() or "").split()[:15])
            hits.append(SearchHit(sku=asin, url=self.product_url(asin),
                                  title=title, rank=len(hits) + 1))
            if len(hits) >= limit:
                break
        return hits
