# Playbook: JSON-LD Product 嵌套 Review 模式

> 适用站：techradar_uk
> 特征：JSON-LD 中 `@type=Product` 内嵌 `review` 对象，无顶层 `@type=Review`

## 结构

```json
{"@type": "Product",
 "name": "Samsung QD-OLED S99H",
 "brand": {"name": "Samsung"},
 "review": {
   "@type": "Review",
   "reviewRating": {"@type": "Rating", "ratingValue": "5", "bestRating": "5", "worstRating": "0"},
   "datePublished": "2026-08-03",
   "author": {"name": "..."}}}
```

## 提取逻辑

```python
# ★ 关键：检查 Product.review（不只是顶层 @type=Review）
if t == "Product":
    review = item.get("review", item.get("reviews", []))
    if isinstance(review, dict):
        review = [review]
    for rv in review:
        rr = rv.get("reviewRating", {})
        rating_value = rr.get("ratingValue")
        best_rating = rr.get("bestRating")
```

## 坑

- **只检查顶层 `@type=Review` 会漏**：techradar 的 Review 嵌在 Product 里
- 需 Playwright（纯HTTP超时），`nav_timeout_ms=25000`
- 列表页含分页 `/page/2`，需翻页收集文章链接
- 仅部分文章有 Review 结构（4/15 → 2/4 有评分）

## adapter 模板

```python
class TechradarUkAdapter(MediaAdapter):
    code = "techradar_uk"
    extract_mode = "jsonld_product"
    requires_browser = True  # 纯HTTP超时
    nav_timeout_ms = 25000
    
    def review_list_url(self, page: int = 1) -> str:
        if page == 1:
            return f"{self.base_url}/televisions/reviews"
        return f"{self.base_url}/televisions/reviews/page/{page}"
```

## 评分量表

techradar_uk: 0-5 (5=最好)
