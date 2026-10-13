# Playbook: JSON-LD @graph Review 模式

> 适用站：techfi_nl, techzilla_it
> 特征：`<script type="application/ld+json">` 中 `@graph` 数组含 `@type=Review` 对象

## 结构

```json
{"@graph": [
  {"@type": "Review",
   "reviewRating": {"ratingValue": 8, "bestRating": 10, "worstRating": 0},
   "positiveNotes": {"@type": "ItemList", "itemListElement": [
     {"@type": "ListItem", "name": "优点1"}, ...]},
   "negativeNotes": {"@type": "ItemList", "itemListElement": [
     {"@type": "ListItem", "name": "缺点1"}, ...]},
   "datePublished": "2026-09-25",
   "author": {"@id": "#person"}},
  {"@type": "Product", "name": "TCL 65C7L", "brand": {"name": "TCL"},
   "aggregateRating": {"ratingValue": 8, "bestRating": 10}},
  {"@type": "Article", "headline": "...", "description": "...", "datePublished": "..."},
  {"@type": "Person", "name": "Eric Beeckmans"}
]}
```

## 提取逻辑

```python
def extract_jsonld_review(data, article_url):
    items = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    review_obj = product_obj = article_obj = None
    for item in items:
        t = item.get("@type", "")
        if t == "Review": review_obj = item
        elif t == "Product": product_obj = item
        elif t in ("Article", "NewsArticle"): article_obj = item
    
    # 评分
    rr = review_obj.get("reviewRating", {})
    rating_value = rr.get("ratingValue")
    best_rating = rr.get("bestRating")
    
    # 优缺点
    pos = [el["name"] for el in review_obj.get("positiveNotes", {}).get("itemListElement", []) if "name" in el]
    neg = [el["name"] for el in review_obj.get("negativeNotes", {}).get("itemListElement", []) if "name" in el]
    
    # 产品
    product_name = product_obj.get("name", "")
    brand = product_obj.get("brand", {}).get("name", "")
    
    # 型号
    model = re.search(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b", product_name)
```

## adapter 模板

```python
class XxxAdapter(MediaAdapter):
    code = "xxx"
    name = "XXX"
    base_url = "https://xxx"
    country = "国家"
    channel = "媒体名"
    extract_mode = "jsonld_review"
    supports_media = True
    requires_browser = False  # techfi_nl纯HTTP可达; techzilla_it也HTTP
    
    def review_list_url(self, category: str = "") -> str:
        return f"{self.base_url}/{category}"
    
    def parse_review(self, html: str, article_url: str) -> MediaReview | None:
        # 从 JSON-LD @graph 提取
```

## 评分量表

- techfi_nl: 0-10 (10=最好)
- techzilla_it: 0-10

## 已知站

| 站点 | 浏览器 | 评分 | 优缺点 | 评测数 |
|------|--------|------|--------|--------|
| techfi_nl | ❌ HTTP | ✅ 100% | ✅ 100% | 84 |
| techzilla_it | ❌ HTTP | ✅ 100% | ❌ 无 | 10 |
