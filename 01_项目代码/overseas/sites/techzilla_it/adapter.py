"""TechZilla（意大利）媒体评测适配器 — JSON-LD Review 模式。

结构（2026-09）：
- 评测列表 https://www.techzilla.it/recensioni/
- 列表页列各评测文章链接 (href含 review/test/recensione)
- 评测文章页含 schema.org JSON-LD：
  - @type=Review: reviewRating.ratingValue (0-10)，无 positiveNotes/negativeNotes
- 纯HTTP可达，无需浏览器。
- 评分量表: 0-10 (10=最好)
"""
from __future__ import annotations

import json
import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L1_MILD

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")


class TechzillaItAdapter(SiteAdapter):
    code = "techzilla_it"
    name = "TechZilla（意大利）"
    base_url = "https://www.techzilla.it"
    country = "意大利"
    channel = "TechZilla"
    protection = L1_MILD
    requires_browser = False
    suggested_interval = 3.0
    supports_media = True
    extract_mode = "jsonld_review"
    rating_scale = "0-10"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        path = category or "recensioni"
        if page and page > 1:
            # TechZilla 列表分页规则（如存在）；保守用 /page/N
            return f"{self.base_url}/{path}/page/{page}/"
        return f"{self.base_url}/{path}/"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(r'href="([^"]*(?:review|test|recensione)[^"]*)"', html, re.I)
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
        """从评测文章页提取 MediaReview（JSON-LD Review 模式，无优缺点）。

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
                if t == "Review":
                    review_obj = item
                elif t == "Product":
                    product_obj = item
                elif t in ("Article", "NewsArticle"):
                    article_obj = item

        if not review_obj and not product_obj:
            return None

        # 评分（reviewRating.ratingValue，0-10）
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

        # TechZilla 无 positiveNotes/negativeNotes，留空
        positive_notes = []
        negative_notes = []

        # 产品
        product_name = ""
        product_brand = ""
        if product_obj:
            product_name = product_obj.get("name", "")
            b = product_obj.get("brand", {})
            product_brand = b.get("name", "") if isinstance(b, dict) else ""
            ar = product_obj.get("aggregateRating", {})
            if isinstance(ar, dict) and not rating_value:
                try:
                    rating_value = float(ar.get("ratingValue")) or None
                except (TypeError, ValueError):
                    pass
                try:
                    best_rating = float(ar.get("bestRating")) or best_rating
                except (TypeError, ValueError):
                    pass

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
