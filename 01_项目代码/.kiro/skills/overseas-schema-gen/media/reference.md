# 媒体评测站 reference.md — 信号→解法+坑

> 按信号查表找解法，避免重复踩坑。条目与 cases.jsonl 对齐。

---

## 一、JSON-LD 模式判别（第一步必做）

| 信号 | 判定 | 提取模式 | 代表站 |
|------|------|----------|--------|
| `<script ld+json>` 含 `"@type":"Review"` | JSON-LD Review 模式 | `jsonld_review` | techfi_nl, techzilla_it |
| 含 `"@type":"Product"` + `Product.review` | JSON-LD Product 嵌套模式 | `jsonld_product` | techradar_uk |
| 含 `"@type":"Product"` + `aggregateRating` 无 `review` | JSON-LD Product only | `jsonld_product_only` | which_uk |
| 含 `"@type":"Article"` 无 Product/Review | JSON-LD Article 模式 | `jsonld_article` | chip_de |
| 无任何 ld+json | HTML fallback 模式 | `html` | connect_de, hifitest_de, hwupgrade_it |

### @graph 结构（techfi_nl）
JSON-LD 是单个 JSON 对象，`@graph` 数组里含多个 `@type` 对象：
```json
{"@graph": [
  {"@type": "Review", "reviewRating": {...}, "positiveNotes": {...}, ...},
  {"@type": "Product", "name": "TCL 65C7L", "brand": {...}, "aggregateRating": {...}},
  {"@type": "Article", "headline": "...", "datePublished": "...", "author": {...}},
  {"@type": "Person", "name": "..."},
  {"@type": "BreadcrumbList", ...}
]}
```
提取时遍历 `@graph`，按 `@type` 分拣 Review/Product/Article。

### Product 嵌套 Review（techradar_uk）
评分不在顶层 `@type=Review`，而在 `Product.review` 内：
```json
{"@type": "Product", "review": {
  "@type": "Review",
  "reviewRating": {"ratingValue": "5", "bestRating": "5"}
}}
```
**坑**：只检查顶层 `@type=Review` 会漏。必须检查 `Product.review` 和 `Product.aggregateRating`。

---

## 二、评分提取优先级

1. **JSON-LD Review.reviewRating.ratingValue**（最准确，techfi_nl/techzilla_it）
2. **JSON-LD Product.aggregateRating.ratingValue**（which_uk，但付费墙）
3. **JSON-LD Product.review.reviewRating.ratingValue**（techradar_uk 嵌套）
4. **HTML 正则 fallback**（connect_de/hwupgrade_it）

### HTML 评分正则
```python
# 通用: x out of y / x/y / x von y / x%
r"(\d+(?:\.\d+)?)\s*out of\s*(\d+)"      # 英: 4.5 out of 5
r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+)\b"      # 通用: 8/10
r"(\d+(?:[.,]\d+)?)\s*von\s*(\d+)"      # 德: 8,5 von 10
r"(\d+(?:[.,]\d+)?)\s*%\s*"             # 百分比: 85%
# 意大利
r"(?:voto|giudizio|valutazione)\s*[:=]?\s*(\d+(?:[.,]\d+)?)"  # voto: 8.2
```

---

## 三、评分量表（必须标注，不可混用）

| 站点 | 量表 | 说明 | 转换 |
|------|------|------|------|
| techfi_nl | 0-10 | 10=最好 | 无需转换 |
| techzilla_it | 0-10 | 10=最好 | 无需转换 |
| hwupgrade_it | 0-10 | 10=最好 | 无需转换 |
| techradar_uk | 0-5 | 5=最好 | ×2 → 0-10 |
| connect_de | 1-5 | **1=sehr gut(最好), 5=mangelhaft(最差) — 德国反序** | `6 - rating` → 1-5正序 |
| which_uk | ? | 付费墙后 | 需会员 |

**坑**：connect_de 的德国评分是反序的（1=最好），不转换会误判。`rating_scale` 字段必填。

---

## 四、优缺点提取

### schema.org 结构（techfi_nl）
```json
"positiveNotes": {
  "@type": "ItemList",
  "itemListElement": [
    {"@type": "ListItem", "name": "Goede lokale dimming"},
    {"@type": "ListItem", "name": "Uitstekend contrast"}
  ]
}
```
提取：`[el["name"] for el in pos["itemListElement"] if "name" in el]`

### HTML 结构
```html
<h3>Pro</h3><ul><li>优点1</li><li>优点2</li></ul>
<h3>Contra</h3><ul><li>缺点1</li></ul>
```
提取：`re.findall(r"<li[^>]*>([^<]{5,80})</li>", section, re.I)`

---

## 五、型号提取

从产品名/标题正则提取：
```python
r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b"
```
- `TCL 65C7L` → `65C7L`
- `Samsung GQ65S90H` → `65S90H`（注意三星GQ前缀，正则取数字开始）
- `Sony K-65XR95M2` → `65XR95M2`
- `LG OLED65C54LA` → `65C54LA`

**坑**：从 URL slug 也可提取（connect_de）：
`samsung-gq65s90h-test` → 去掉 `-test` 后正则匹配 → `65S90H`

---

## 六、WAF 应对

| 站点 | WAF 类型 | 纯HTTP | Playwright | 解决 |
|------|----------|--------|------------|------|
| hwupgrade_it | Cloudflare | ❌ 403 | ✅ 突破 | 用浏览器 |
| clubic_fr | Cloudflare | ❌ | ❌ 挑战页 | 住宅IP |
| tweakers_nl | 自建 | ❌ 403 | ❌ blocked | 住宅IP |
| avforums_uk | 自建 | ❌ 403 | ❌ | 住宅IP |
| test_de | 付费墙 | ✅ | ✅ | 会员登录 |
| which_uk | 付费墙 | ✅ | ✅ | 会员登录 |

**Playwright 突破 WAF 条件**：
- 页面不是 JS Challenge（纯 403 可突破）
- 用持久化 profile（`OVERSEAS_USE_PROFILE=1`）
- stealth JS 注入（已有 `_STEALTH_JS`）

**无法突破**：JS Challenge 需要真实浏览器环境执行 JS 解题，住宅 IP 更可靠。

---

## 七、评测列表页发现

| 站点 | 列表页 URL | 文章链接模式 |
|------|-----------|-------------|
| techfi_nl | `/televisies` 等 | `href含review/test` |
| techradar_uk | `/televisions/reviews` 含分页 | `href=/televisions/*-review` |
| connect_de | `/tv-heimkino/testbericht/` | `href=testbericht/*.html` |
| hwupgrade_it | `/articoli/tv-video/` | `href含recensione` |
| which_uk | `/reviews/televisions` | `href=/reviews/televisions/*` |

**坑**：connect_de 的 URL 必须从列表页实际链接取，猜的 URL（如 `-3213161.html`）
会重定向到新闻页。正确 URL 是 `-3212642.html`。
