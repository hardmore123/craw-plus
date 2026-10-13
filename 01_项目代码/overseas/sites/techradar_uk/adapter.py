"""TechRadar（英国）媒体评测适配器 — JSON-LD Product 嵌套 Review 模式。

结构（2026-09）：
- 评测列表 https://www.techradar.com/televisions/reviews （分页 /page/2 等）
- 评测文章页含 schema.org JSON-LD：
  - @type=Product: name, brand, review (嵌套 @type=Review), aggregateRating
  - 评分在 Product.review.reviewRating.ratingValue（0-5），非顶层 @type=Review
- 需浏览器（L2_MEDIUM）。
- 评分量表: 0-5 (5=最好)

特殊：评分取 Product.review.reviewRating（非顶层 Review），
并回退到 Product.aggregateRating。
"""
from __future__ import annotations

import json
import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L2_MEDIUM

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")


class TechradarUkAdapter(SiteAdapter):
    code = "techradar_uk"
    name = "TechRadar（英国）"
    base_url = "https://www.techradar.com"
    country = "英国"
    channel = "TechRadar"
    protection = L2_MEDIUM
    requires_browser = True
    suggested_interval = 5.0
    supports_media = True
    extract_mode = "jsonld_product"
    rating_scale = "0-5"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "televisions/reviews"
        cat = cat.strip("/")
        if page and page > 1:
            return f"{self.base_url}/{cat}/page/{page}/"
        return f"{self.base_url}/{cat}/"

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
            # 排除列表分页自身及锚点/查询串
            if "/page/" in url or "?" in url or "#" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            full.append(url)
        return full

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页提取 MediaReview（JSON-LD Product 嵌套 Review）。

        返回 dict 或 None。
        """
        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S,
        )

        product_obj = None
        article_obj = None
        top_review_obj = None
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
                elif t == "Review" and not top_review_obj:
                    top_review_obj = item
                elif t in ("Article", "NewsArticle") and not article_obj:
                    article_obj = item

        # TechRadar 关键：优先 Product 嵌套 review；回退顶层 Review
        review_obj = None
        if product_obj:
            nested = product_obj.get("review")
            if isinstance(nested, dict):
                review_obj = nested
            elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
                review_obj = nested[0]
        if not review_obj:
            review_obj = top_review_obj

        if not product_obj and not review_obj:
            return None

        # 评分：review.reviewRating（0-5），回退 aggregateRating
        rating_value = best_rating = worst_rating = None
        if review_obj:
            rr = review_obj.get("reviewRating", {})
            if isinstance(rr, dict):
                try:
                    rating_value = float(rr.get("ratingValue")) or None
                except (TypeError, ValueError):
                    rating_value = None
                try:
                    best_rating = float(rr.get("bestRating")) or None
                except (TypeError, ValueError):
                    best_rating = None
                try:
                    worst_rating = float(rr.get("worstRating")) or None
                except (TypeError, ValueError):
                    worst_rating = None
        if not rating_value and product_obj:
            ar = product_obj.get("aggregateRating", {})
            if isinstance(ar, dict):
                try:
                    rating_value = float(ar.get("ratingValue")) or None
                except (TypeError, ValueError):
                    pass
                try:
                    best_rating = float(ar.get("bestRating")) or best_rating
                except (TypeError, ValueError):
                    pass

        positive_notes = []
        negative_notes = []

        # 产品
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
        if review_obj:
            date_published = review_obj.get("datePublished", "") or date_published
            a = review_obj.get("author", {})
            if isinstance(a, dict):
                author = a.get("name", "")
            elif isinstance(a, str):
                author = a
        if article_obj:
            headline = article_obj.get("headline", "")
            description = article_obj.get("description", "")
            date_published = article_obj.get("datePublished", "") or date_published
            if not author:
                a = article_obj.get("author", {})
                if isinstance(a, dict):
                    author = a.get("name", "")

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
            "rating_value": rating_value,
            "best_rating": best_rating,
            "worst_rating": worst_rating,
            "rating_scale": self.rating_scale,
            "positive_notes": positive_notes,
            "negative_notes": negative_notes,
        }
