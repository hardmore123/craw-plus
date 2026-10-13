"""HWUpgrade（意大利）媒体评测适配器 — HTML fallback + WAF 需浏览器。

结构（2026-09）：
- 评测列表 https://www.hwupgrade.it/articoli/tv-video/
- 列表页列各评测文章链接 (href含 recensione/test/review/articoli)
- 评测文章页无 JSON-LD；意大利评分 voto x/10；
  需 Playwright 突破 Cloudflare（L2_MEDIUM）。
- 评分量表: 0-10 (10=最好)

特殊：无 JSON-LD，评分正则 (?:voto|giudizio)\\s*[:=]?\\s*(\\d+(?:[.,]\\d+)?)。
"""
from __future__ import annotations

import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L2_MEDIUM

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")
# 意大利评分：voto/giudizio x/10
_IT_VOTO_RE = re.compile(
    r"(?:voto|giudizio)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*(?:/\s*10)?",
    re.I,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_BRANDS = [
    "Samsung", "LG", "Sony", "Panasonic", "Philips", "TCL", "Hisense",
    "Sharp", "Grundig", "Telefunken", "Loewe", "Metz", "Toshiba",
    "JVC", "Skyworth", "Haier",
]


class HwupgradeItAdapter(SiteAdapter):
    code = "hwupgrade_it"
    name = "HWUpgrade（意大利）"
    base_url = "https://www.hwupgrade.it"
    country = "意大利"
    channel = "HWUpgrade"
    protection = L2_MEDIUM
    requires_browser = True
    suggested_interval = 5.0
    supports_media = True
    extract_mode = "html"
    rating_scale = "0-10"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "articoli/tv-video"
        cat = cat.strip("/")
        return f"{self.base_url}/{cat}/"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(
            r'href="([^"]*(?:recensione|test|review|articoli)[^"]*)"',
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
        """从评测文章页 HTML 提取 MediaReview（无 JSON-LD，意大利 voto）。

        返回 dict 或 None。
        """
        if not html:
            return None

        # 标题：<title> 或 <h1>
        title = ""
        m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
        h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S | re.I)
        if h1:
            h1t = re.sub(r"<[^>]+>", "", h1.group(1)).strip()
            h1t = re.sub(r"\s+", " ", h1t).strip()
            if h1t:
                title = title or h1t

        # 品牌
        product_brand = ""
        for b in _BRANDS:
            if re.search(rf"\b{re.escape(b)}\b", title, re.I):
                product_brand = b
                break
            if re.search(rf"\b{re.escape(b)}\b", html, re.I):
                product_brand = b
                break

        # 型号
        product_model = ""
        for src in (title, article_url):
            if not product_model and src:
                m = _MODEL_RE.search(src or "")
                if m:
                    product_model = m.group(1)

        # 评分：voto/giudizio x/10
        rating_value = None
        best_rating = 10.0
        worst_rating = 0.0
        rm = _IT_VOTO_RE.search(html)
        if rm:
            try:
                rating_value = float(rm.group(1).replace(",", "."))
            except (TypeError, ValueError):
                rating_value = None

        # 日期
        date_published = ""
        dm = _DATE_RE.search(html)
        if dm:
            date_published = dm.group(1)

        # author
        author = ""
        am = re.search(
            r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.I,
        )
        if am:
            author = am.group(1)

        if not product_model and not rating_value:
            return None

        return {
            "site_code": self.code,
            "article_url": article_url,
            "title": title,
            "headline": title,
            "description": "",
            "author": author,
            "date_published": date_published,
            "product_name": title,
            "product_model": product_model,
            "product_brand": product_brand,
            "rating_value": rating_value,
            "best_rating": best_rating,
            "worst_rating": worst_rating,
            "rating_scale": self.rating_scale,
            "positive_notes": [],
            "negative_notes": [],
        }
