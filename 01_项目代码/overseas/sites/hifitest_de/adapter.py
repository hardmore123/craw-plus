"""HiFi Test（德国）媒体评测适配器 — HTML fallback + 需浏览器。

结构（2026-09）：
- 评测列表 https://www.hifitest.de/ （首页即评测列表）
- 评测文章页无 JSON-LD；评分量表未知（先抓结构，评分正则通用匹配）。
- 需浏览器（L2_MEDIUM）。
- 评分量表: 未知

特殊：无 JSON-LD，评分用通用 x out of y / x/y 形式兜底。
"""
from __future__ import annotations

import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L2_MEDIUM

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")
# 通用评分：x out of y / x/y / x von y / x sur y
_GENERIC_RATING_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:out\s*of|/|von|sur)\s*(\d+(?:[.,]\d+)?)",
    re.I,
)
# 德国 1-5 反序兜底
_DE_RATING_RE = re.compile(r"\b([1-5]),([0-9])\b")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

_BRANDS = [
    "Samsung", "LG", "Sony", "Panasonic", "Philips", "TCL", "Hisense",
    "Sharp", "Grundig", "Telefunken", "Loewe", "Metz", "Toshiba",
    "JVC", "Skyworth", "Haier",
]


class HifitestDeAdapter(SiteAdapter):
    code = "hifitest_de"
    name = "HiFi Test（德国）"
    base_url = "https://www.hifitest.de"
    country = "德国"
    channel = "HiFi Test"
    protection = L2_MEDIUM
    requires_browser = True
    suggested_interval = 5.0
    supports_media = True
    extract_mode = "html"
    rating_scale = "未知"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        # 首页即评测列表
        return f"{self.base_url}/"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(
            r'href="([^"]*(?:test|testbericht|review)[^"]*)"',
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
        """从评测文章页 HTML 提取 MediaReview（无 JSON-LD，通用评分）。

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

        # 评分：通用 x out of y / x/y；兜底德国 [1-5],[0-9]
        rating_value = None
        best_rating = None
        worst_rating = None
        gm = _GENERIC_RATING_RE.search(html)
        if gm:
            try:
                rating_value = float(gm.group(1).replace(",", "."))
                best_rating = float(gm.group(2).replace(",", "."))
                worst_rating = 0.0
            except (TypeError, ValueError):
                pass
        if rating_value is None:
            dm = _DE_RATING_RE.search(html)
            if dm:
                try:
                    rating_value = float(f"{dm.group(1)}.{dm.group(2)}")
                    best_rating = 5.0
                    worst_rating = 1.0
                except (TypeError, ValueError):
                    pass

        # 日期
        date_published = ""
        dm2 = _DATE_RE.search(html)
        if dm2:
            date_published = dm2.group(1)

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
