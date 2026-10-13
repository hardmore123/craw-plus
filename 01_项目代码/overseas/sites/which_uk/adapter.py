"""Which?（英国）媒体评测适配器 — JSON-LD Product only（付费墙）。

结构（2026-09）：
- 评测列表 https://www.which.co.uk/reviews/televisions
- 评测文章页含 schema.org JSON-LD：
  - @type=Product: name, brand（无 Review，评分在付费墙后不可见）
- 需浏览器 + 强防护（L3_STRONG）；评分因付费墙无法提取。
- 评分量表: 付费墙（无可见评分）

特殊：JSON-LD 有 Product(name+brand) 但无 Review，评分需订阅才能看到。
"""
from __future__ import annotations

import json
import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L3_STRONG

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")


class WhichUkAdapter(SiteAdapter):
    code = "which_uk"
    name = "Which?（英国）"
    base_url = "https://www.which.co.uk"
    country = "英国"
    channel = "Which?"
    protection = L3_STRONG
    requires_browser = True
    suggested_interval = 8.0
    supports_media = True
    extract_mode = "jsonld_product_only"
    rating_scale = "付费墙"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "televisions"
        cat = cat.strip("/")
        # Which? 列表无明确分页参数；保守追加 ?page=N
        if page and page > 1:
            return f"{self.base_url}/reviews/{cat}?page={page}"
        return f"{self.base_url}/reviews/{cat}"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(r'href="([^"]*(?:review|test)[^"]*)"', html, re.I)
        full = []
        seen = set()
        for l in links:
            if l.startswith("http"):
                url = l
            elif l.startswith("/"):
                url = f"{self.base_url}{l}"
            else:
                continue
            if "?" in url or "#" in url:
                # 保留带 ?page= 的列表分页链接本身之外的评测链接
                if "/page/" not in url:
                    # 去掉查询串再判断
                    base = url.split("?")[0].split("#")[0]
                    if base in seen:
                        continue
                    url = base
                    if not (re.search(r"review|test", url, re.I)):
                        continue
                    seen.add(url)
                    full.append(url)
                    continue
                continue
            if url in seen:
                continue
            seen.add(url)
            full.append(url)
        return full

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页提取 MediaReview（JSON-LD Product only，付费墙无评分）。

        返回 dict 或 None。
        """
        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S,
        )

        product_obj = None
        article_obj = None
        for block in blocks:
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]
            elif isinstance(data, list):
                items = data
            else:
                items = [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type", "")
                if isinstance(t, list):
                    t = t[0] if t else ""
                if t == "Product" and not product_obj:
                    product_obj = item
                elif t in ("Article", "NewsArticle") and not article_obj:
                    article_obj = item

        if not product_obj and not article_obj:
            return None

        # 产品（付费墙：无评分）
        product_name = ""
        product_brand = ""
        if product_obj:
            product_name = product_obj.get("name", "")
            b = product_obj.get("brand", {})
            product_brand = b.get("name", "") if isinstance(b, dict) else ""

        # 文章
        headline = ""
        description = ""
        date_published = ""
        author = ""
        if article_obj:
            headline = article_obj.get("headline", "")
            description = article_obj.get("description", "")
            date_published = article_obj.get("datePublished", "") or date_published
            a = article_obj.get("author", {})
            if isinstance(a, dict):
                author = a.get("name", "")
            elif isinstance(a, str):
                author = a

        # 型号
        product_model = ""
        for src in (product_name, headline, article_url):
            if not product_model and src:
                m = _MODEL_RE.search(src or "")
                if m:
                    product_model = m.group(1)

        return {
            "site_code": self.code,
            "article_url": article_url,
            "title": headline or product_name,
            "headline": headline,
            "description": description,
            "author": author,
            "date_published": date_published,
            "product_name": product_name,
            "product_model": product_model,
            "product_brand": product_brand,
            "rating_value": None,  # 付费墙，无可见评分
            "best_rating": None,
            "worst_rating": None,
            "rating_scale": self.rating_scale,
            "positive_notes": [],
            "negative_notes": [],
        }
