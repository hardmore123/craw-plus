---
name: overseas-schema-gen-media
description: 给一个媒体评测站（科技媒体/消费者组织/影音评测），探结构、产出 MediaAdapter（评测列表→评测文章→评分/优缺点/品牌），交给媒体评测引擎抓该站全部评测。当用户要求「接入新的媒体评测站」「生成媒体评测站的 schema / 适配器」「诊断某媒体站为什么抓不到评分」时使用。
---

# 媒体评测站 MediaAdapter 生成

给一个媒体评测站（techfi / techradar / connect / which / techzilla ...），
用**文章驱动的探测**产出一份经真实页面验证的 `MediaAdapter`，交给硬编码引擎
抓该站全部评测文章的评分/优缺点/品牌。

**与 SPEC/RETAIL 的根本区别**：媒体站是**文章驱动**（列表页→文章页→评分），
不是型号驱动。没有 search_url/product_url，不抓价格/用户网评。
一篇评测 = 一条 media_review 记录。

---

## 与现有分支的边界

| 分支 | 驱动模式 | 产出 | 核心接口 |
|---|---|---|---|
| SPEC | 品牌→系列→型号→规格 | SpecSheet | `list_series()` / `parse_spec()` |
| RETAIL | 型号→搜索→PDP→价格+网评 | ProductPayload | `search_url()` / `parse_product()` |
| **MEDIA** | **列表页→文章→评分/优缺点** | **MediaReview** | **`review_list_url()` / `parse_review()`** |
| OPS | 已有adapter的运维 | CSV/DB | supervisor/监控 |

---

## 铁律（违反即返工）

1. **先判 JSON-LD 类型。** 打开文章页，查 `<script type="application/ld+json">`：
   - 有 `@type=Review` → JSON-LD 模式（最简，只需选 `@graph` 路径）
   - 有 `@type=Product` 内嵌 `review`/`aggregateRating` → JSON-LD 嵌套模式
   - 仅有 `@type=Article` → HTML fallback 模式（需写选择器提取评分）
   - 无 JSON-LD → HTML 模式（评分在页面 CSS/正文中）
2. **评分量表必须标注。** techfi=0-10, techradar=0-5, connect_de=1-5(德国反序), which=付费墙。
   不同量表不能直接比较，`rating_scale` 字段必填。
3. **优缺点用 JSON 数组存。** schema.org 的 `positiveNotes.itemListElement[].name`
   提取为 `["优点1","优点2",...]`，HTML 的 `<ul class="pros">` 也提取为列表。
4. **型号从产品名/标题正则提取。** `\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b`，
   从 `Product.name` 或 `<h1>` 提取。提取不到留空，不强造。
5. **WAF 硬封(403/CF)标 blocked。** Playwright 可突破部分 WAF（hwupgrade_it 成功），
   但 clubic_fr/tweakers_nl/avforums_uk 仍需住宅 IP。
6. **强制收尾沉淀。** 每次任务结束追加 `cases.jsonl` + 必要时更新 `reference.md`。

---

## 主流程

### Step 0 — 查经验库

```powershell
Select-String -Path .kiro/skills/overseas-schema-gen/media/cases.jsonl -Pattern "<域名特征|jsonld|html|waf>"
```

### Step 1 — 探测（判 JSON-LD 模式 + 评分位置）

```powershell
py -3.12 .kiro/skills/overseas-schema-gen/media/probe.py --entry "<评测列表URL>" --code <code>
```

看四个信号：
- `jsonld_type`: Review / Product / Article / 无
- `rating_location`: reviewRating / aggregateRating / HTML选择器 / 付费墙
- `review_list_selector`: 评测文章链接的容器选择器
- `waf_status`: ok / blocked / cloudflare / datadome

### Step 2 — 写 adapter.py + schema.json

按 `task_template.md` 填，核心选三模式之一：

**模式 A — JSON-LD Review（techfi_nl 标杆）**：
```python
class TechfiNlAdapter(MediaAdapter):
    code = "techfi_nl"
    extract_mode = "jsonld_review"  # @graph 中 @type=Review
    rating_path = "reviewRating.ratingValue"
    pros_path = "positiveNotes.itemListElement"
    cons_path = "negativeNotes.itemListElement"
```

**模式 B — JSON-LD Product 嵌套（techradar_uk）**：
```python
class TechradarUkAdapter(MediaAdapter):
    code = "techradar_uk"
    extract_mode = "jsonld_product"  # Product.review.reviewRating
    rating_path = "review.reviewRating.ratingValue"
```

**模式 C — HTML fallback（connect_de）**：
```python
class ConnectDeAdapter(MediaAdapter):
    code = "connect_de"
    extract_mode = "html"
    rating_selector = "span.rating-value"  # per-site 选择器
    pros_selector = "ul.pros li"
    cons_selector = "ul.cons li"
```

### Step 3 — 校验 + 小样实测

```powershell
py -3.12 .kiro/skills/overseas-schema-gen/media/probe.py --verify sites/<code>/adapter.py --entry "<评测列表URL>"
```

达标后 sandbox db 抓取：
```powershell
$env:OVERSEAS_DB = "data/sandbox_<code>.db"
py -3.12 -m overseas.cli media-crawl --site <code>
```

### Step 4 — 转正 + 沉淀

adapter.py 放到 `overseas/sites/<code>/adapter.py`，追加 `cases.jsonl` 一条。

---

## 结构型 playbook 索引

| 套路 | 文件 | 适用站 |
|---|---|---|
| JSON-LD @graph Review | [playbook/jsonld_review.md](playbook/jsonld_review.md) | techfi_nl |
| JSON-LD Product 嵌套 | [playbook/jsonld_product.md](playbook/jsonld_product.md) | techradar_uk |
| JSON-LD Product only | [playbook/jsonld_product_only.md](playbook/jsonld_product_only.md) | which_uk |
| HTML fallback | [playbook/html_fallback.md](playbook/html_fallback.md) | connect_de, chip_de |
| WAF 突破 | [playbook/waf_playwright.md](playbook/waf_playwright.md) | hwupgrade_it |
