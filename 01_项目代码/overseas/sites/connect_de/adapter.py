"""connect.de（德国）媒体评测适配器 — HTML fallback 模式。

结构（2026-09）：
- 评测列表 https://www.connect.de/tv-heimkino/testbericht/
- 列表页列各评测文章链接 (href含 test/testbericht/review)
- 评测文章页无 JSON-LD；标题含型号（如 "Samsung GQ65S90H im Test"）；
  评分在 Fazit 段正文，德国量表 1=sehr gut, 5=mangelhaft（1-5反序）。
- 纯HTTP可达，无需浏览器（L1_MILD）。
- 评分量表: 1-5反序（德国，1=sehr gut 最好，5=mangelhaft 最差）

特殊：无 JSON-LD，评分正则匹配 [1-5],[0-9] 形式（如 2,3）。
"""
from __future__ import annotations

import re

from .. import SiteAdapter
from ...fetchers import Dom
from ...models import L1_MILD

_MODEL_RE = re.compile(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b")
# 德国评分：1-5 反序，常见写法 1,0 / 2,3 / 4,5 等
_DE_RATING_RE = re.compile(r"\b([1-5]),([0-9])\b")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")

# 常见电视品牌（用于 HTML 标题/正文品牌匹配）
_BRANDS = [
    "Samsung", "LG", "Sony", "Panasonic", "Philips", "TCL", "Hisense",
    "Sharp", "Grundig", "Telefunken", "Loewe", "Metz", "Toshiba",
    "JVC", "Hisense", "Skyworth", "Haier",
]


class ConnectDeAdapter(SiteAdapter):
    code = "connect_de"
    name = "connect.de（德国）"
    base_url = "https://www.connect.de"
    country = "德国"
    channel = "connect.de"
    protection = L1_MILD
    requires_browser = False
    suggested_interval = 4.0
    supports_media = True
    extract_mode = "html"
    rating_scale = "1-5反序"

    def review_list_url(self, category: str = "", page: int = 1) -> str:
        cat = category or "tv-heimkino/testbericht"
        cat = cat.strip("/")
        if page and page > 1:
            return f"{self.base_url}/{cat}/page/{page}/"
        return f"{self.base_url}/{cat}/"

    def parse_review_list(self, dom: Dom | None, html: str = "") -> list[str]:
        """从评测列表页提取评测文章 URL。"""
        links = re.findall(r'href="([^"]*(?:test|testbericht|review)[^"]*)"', html, re.I)
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
            if "/page/" in url:
                continue
            if url in seen:
                continue
            seen.add(url)
            full.append(url)
        return full

    def parse_review(self, html: str, article_url: str = ""):
        """从评测文章页 HTML 提取 MediaReview（无 JSON-LD，纯 HTML）。

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

        # 型号：从标题优先，回退 URL
        product_model = ""
        for src in (title, article_url):
            if not product_model and src:
                m = _MODEL_RE.search(src or "")
                if m:
                    product_model = m.group(1)

        # 评分：德国 1-5反序，正则 [1-5],[0-9]
        rating_value = None
        best_rating = 5.0
        worst_rating = 1.0  # 反序：1=最好
        # 先看 Fazit 段；找不到则全文
        fazit = ""
        fm = re.search(
            r"(?is)<[^>]*(?:fazit|gesamt|wertung)[^>]*>(.*?)(?:</section>|</div>)",
            html,
        )
        if fm:
            fazit = fm.group(1)
        search_text = fazit or html
        rm = _DE_RATING_RE.search(search_text)
        if rm:
            rating_value = float(f"{rm.group(1)}.{rm.group(2)}")

        # 日期
        date_published = ""
        dm = _DATE_RE.search(html)
        if dm:
            date_published = dm.group(1)

        # author：简单从 meta 或 byline 提取
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
