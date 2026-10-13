"""CHIP（德国）媒体评测适配器 — JSON-LD Article 模式（无评分）。

结构（2026-09）：
- 评测列表 https://www.chip.de/bestenlisten/Bestenliste-Fernseher
- 评测文章页含 schema.org JSON-LD：
  - @type=Article: headline, author, datePublished（无 Review 评分）
- 纯HTTP可达，无需浏览器（L1_MILD）。
- 评分量表: 无（CHIP 用榜单形式，不给出数值评分）

特殊：JSON-LD 有 Article(headline/author/datePublished) 但无 Review 评分。
"""
from __future__ import annotations

import json
import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L1_MILD

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")

_BRANDS = [
    "Samsung", "LG", "Sony", "Panasonic", "Philips", "TCL", "Hisense",
    "Sharp", "Grundig", "Telefunken", "Loewe", "Metz", "Toshiba",
    "JVC", "Skyworth", "Haier",
]


class ChipDeAdapter(SiteAdapter):
    code = "chip_de"
    name = "CHIP（德国）"
    base_url = "https://www.chip.de"
    country = "德国"
    channel = "CHIP"
    protection = L1_MILD
    requires_browser = False
    suggested_interval = 3.0
    supports_media = True
    extract_mode = "jsonld_article"
    rating_scale = "无"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "bestenlisten/Bestenliste-Fernseher"
        cat = cat.strip("/")
        return f"{self.base_url}/{cat}/"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(
            r'href="([^"]*(?:test|review|bestenliste|fernseher)[^"]*)"',
            html, re.I,
        )
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
                continue
            if url in seen:
                continue
            seen.add(url)
            full.append(url)
        return full

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页提取 MediaReview（JSON-LD Article，无评分）。

        返回 dict 或 None。
        """
        blocks = re.findall(
            r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.S,
        )

        article_obj = None
        product_obj = None
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
                if t in ("Article", "NewsArticle") and not article_obj:
                    article_obj = item
                elif t == "Product" and not product_obj:
                    product_obj = item

        if not article_obj and not product_obj:
            return None

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
            elif isinstance(a, list) and a and isinstance(a[0], dict):
                author = a[0].get("name", "")

        # 产品（可能无）
        product_name = ""
        product_brand = ""
        if product_obj:
            product_name = product_obj.get("name", "")
            b = product_obj.get("brand", {})
            product_brand = b.get("name", "") if isinstance(b, dict) else ""

        # 品牌：JSON-LD 没有则从标题/正文匹配
        if not product_brand:
            for src in (headline, product_name, html):
                for b in _BRANDS:
                    if re.search(rf"\b{re.escape(b)}\b", src or "", re.I):
                        product_brand = b
                        break
                if product_brand:
                    break

        # 型号
        product_model = ""
        for src in (headline, product_name, article_url):
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
            "product_name": product_name or headline,
            "product_model": product_model,
            "product_brand": product_brand,
            "rating_value": None,  # CHIP 无数值评分
            "best_rating": None,
            "worst_rating": None,
            "rating_scale": self.rating_scale,
            "positive_notes": [],
            "negative_notes": [],
        }
