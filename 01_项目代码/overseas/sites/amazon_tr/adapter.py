"""Amazon TR 适配器：URL 规则 + 能力标记，字段抽取由 RetailSpec 驱动。

探测日期 2026-09-25：
- HTTP 状态: 200
- 产品数: 30
- 状态: reachable
- 同构品牌：复用 amazon_common（Amazon 各国前端同构：div[data-asin] 候选 + data-hook 价格/评论）

注：Amazon 各国前端同构，商品页抽取走 schema.json（spec_driven_detail=True），
    schema.json 复用 amazon_us/se 的实测选择器（#productTitle / #corePrice_feature_div /
    [data-hook='review'] 等）。独立评价页翻页走 reviews_url（/product-reviews/<ASIN>），
    与 amazon_mx/ca/us 同构。
"""
from __future__ import annotations

import re
import urllib.parse

from ...models import L3_STRONG
from .. import SiteAdapter

_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})(?:[/?#]|$)", re.I)


class AmazonTrAdapter(SiteAdapter):
    code = "amazon_tr"
    name = "Amazon TR"
    base_url = "https://www.amazon.com.tr"
    country = "Turkey"
    channel = "Amazon"
    protection = L3_STRONG
    requires_browser = True
    supports_retail = True
    spec_driven_detail = True
    retail_page_wait = "#productTitle, #dp, .a-price"
    suggested_interval = 8.0
    SEARCH_PATH = "/s?k={q}"

    @classmethod
    def _asin(cls, value: str) -> str:
        text = str(value or "").strip()
        m = _ASIN_RE.search(text)
        if m:
            return m.group(1).upper()
        if re.fullmatch(r"[A-Z0-9]{10}", text, re.I):
            return text.upper()
        return ""

    def search_url(self, keyword: str, page: int = 1) -> str:
        q = urllib.parse.urlencode({"k": str(keyword or "").strip()}, safe="")
        url = self.base_url.rstrip("/") + "/s?" + q
        if page and page > 1:
            url += f"&page={int(page)}"
        return url

    def product_url(self, sku: str) -> str:
        asin = self._asin(sku)
        if asin:
            return f"{self.base_url}/dp/{asin}"
        v = str(sku or "").strip()
        if v.startswith("http"):
            return v
        if v.startswith("/"):
            return self.base_url.rstrip("/") + v
        return v

    def reviews_url(self, sku: str, page: int = 1) -> str:
        """独立评价页。Amazon 对未登录用户的评价翻页深度有限制。

        与 amazon_mx 同构：/product-reviews/<ASIN>/?reviewerType=all_reviews[&pageNumber=N]。
        schema.json 的 paginate.reviews 已配 query_param 型分页，这里保留方法
        供 _fetch_reviews_paginated / review_page_url 的 adapter 回落分支使用。
        """
        asin = self._asin(sku) or str(sku or "").strip()
        url = f"{self.base_url}/product-reviews/{asin}/?reviewerType=all_reviews"
        if page and page > 1:
            url += f"&pageNumber={int(page)}"
        return url
