"""TechFi（荷兰）媒体评测适配器 — JSON-LD @graph Review 模式。

实测结构（2026-09）：
- 评测列表 https://techfi.nl/televisies (或其他品类如 /monitoren)
- 列表页列各评测文章链接 (href含 review/test)
- 评测文章页含完整 schema.org JSON-LD @graph:
  - @type=Review: reviewRating(8/10), positiveNotes(8-10条), negativeNotes(3-7条)
  - @type=Product: name="TCL 65C7L", brand="TCL", aggregateRating
  - @type=Article: headline, datePublished, author
- 纯HTTP可达，无需浏览器。
- 评分量表: 0-10 (10=最好)

数据已抓取 84 条（34品牌），100%有评分+优缺点。
"""
from __future__ import annotations

import json
import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L1_MILD

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")


class TechfiNlAdapter(SiteAdapter):
    code = "techfi_nl"
    name = "TechFi（荷兰）"
    base_url = "https://techfi.nl"
    country = "荷兰"
    channel = "TechFi"
    protection = L1_MILD
    requires_browser = False
    suggested_interval = 2.0
    supports_media = True
    extract_mode = "jsonld_review"
    rating_scale = "0-10"

    # 品类入口（用于 review_list_url）
    CATEGORIES = ["televisies", "monitoren", "audio", "laptops"]

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "televisies"
        return f"{self.base_url}/{cat}"

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
            if url in seen:
                continue
            if "?" in url or "#" in url:
                continue
            seen.add(url)
            full.append(url)
        return full

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页提取 MediaReview（JSON-LD @graph Review 模式）。

        返回 dict 或 None。
        """
        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S,
        )

        review_obj = product_obj = article_obj = None
        for block in blocks:
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, ValueError):
                continue
            items = (
                data.get("@graph", [data])
                if isinstance(data, dict)
                else (data if isinstance(data, list) else [])
            )
            for item in items:
                if not isinstance(item, dict):
                    continue
                t = item.get("@type", "")
                if t == "Review":
                    review_obj = item
                elif t == "Product":
                    product_obj = item
                elif t in ("Article", "NewsArticle"):
                    article_obj = item

        if not review_obj and not product_obj:
            return None

        # 评分
        rating_value = best_rating = worst_rating = None
        if review_obj:
            rr = review_obj.get("reviewRating", {})
            if isinstance(rr, dict):
                rating_value = float(rr.get("ratingValue", 0)) or None
                best_rating = float(rr.get("bestRating", 0)) or None
                worst_rating = float(rr.get("worstRating", 0)) or None

        # 优缺点
        positive_notes = []
        negative_notes = []
        if review_obj:
            pos = review_obj.get("positiveNotes", {})
            if isinstance(pos, dict) and "itemListElement" in pos:
                positive_notes = [
                    el["name"]
                    for el in pos["itemListElement"]
                    if isinstance(el, dict) and "name" in el
                ]
            neg = review_obj.get("negativeNotes", {})
            if isinstance(neg, dict) and "itemListElement" in neg:
                negative_notes = [
                    el["name"]
                    for el in neg["itemListElement"]
                    if isinstance(el, dict) and "name" in el
                ]

        # 产品
        product_name = ""
        product_brand = ""
        if product_obj:
            product_name = product_obj.get("name", "")
            b = product_obj.get("brand", {})
            product_brand = b.get("name", "") if isinstance(b, dict) else ""
            ar = product_obj.get("aggregateRating", {})
            if isinstance(ar, dict) and not rating_value:
                rating_value = float(ar.get("ratingValue", 0)) or None
                best_rating = float(ar.get("bestRating", 0)) or best_rating

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
        if product_name:
            m = _MODEL_RE.search(product_name)
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
