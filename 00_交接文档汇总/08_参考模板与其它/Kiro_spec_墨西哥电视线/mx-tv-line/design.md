# Design Document

## Overview

墨西哥（MX）电视数据采集线是「海外电视数据采集」项目在日本线之后的第二条国家线。它**复用**日本线已有的核心框架（配置、抓取、抽取、存储、导出、审计、API），只通过三类增量落地：

1. 在 `overseas/regions_config.py` 中新增一条 `mx` 线（纯数据声明）；
2. 在 `overseas/sites/` 下新增 10 个站点适配器目录（4 个品牌官网 SPEC 站 + 6 个电商零售站）；
3. 新增/复用任务脚本，先跑 SPEC 产出型号全集，再按「型号 × 零售站」在同一商品页同步抓价格与网评，最后用现有导出模板导出（币种 MXN、渠道为墨西哥零售站）。

设计的核心取舍：**能复用就不新增**。SPEC 采集直接复用 `scenarios.spec_crawl`；价格+网评同步抓取直接复用 `scenarios.collect_detail`（它本就在一次抽取里同时产出 `product / specs / price / summary / reviews`）；导出复用 `spec_export / review_export / price_export`。墨西哥线与日本线最大的结构差异——「价格/网评来自多个零售站而非单一聚合站」——通过 `regions_config` 的多对多声明 + 逐零售站循环解决，不改核心场景函数。

### 与日本线的关键差异对照

| 维度 | 日本线 | 墨西哥线 |
|---|---|---|
| SPEC 来源 | 6 品牌官网（`*_jp`） | 4 品牌墨西哥官网（`tcl_mx / samsung_mx / lg_mx / hisense_mx`） |
| 价格/网评来源 | 单一聚合站 `kakaku_jp` | 6 个零售站（`amazon_mx / liverpool_mx / sams_mx / palacio_mx / walmart_mx / coppel_mx`） |
| 价格与网评抓取 | 分两条线两次抓（价格线 / 评论线） | **同一商品页一次抽取同步取**（复用 `collect_detail`） |
| 型号×来源关系 | 型号 → kakaku 单站 | 型号 × 每个启用零售站（多对多，逐站各搜一次） |
| 货币 | JPY | MXN |
| 导出「所属国家/区域」 | Japan | Mexico / 墨西哥 |
| 翻译/AI 三列 | `NULL_HOOKS`（空） | `NULL_HOOKS`（空，本阶段同样不接入） |

## Architecture

```
┌───────────────────── SPEC 线（先跑）────────────────────┐
 品牌官网入口页 ── spec_crawl ── spec_series/spec_row(SQLite)
 (tcl/samsung/lg/hisense_mx)          │
                                       └─ spec_export → SPEC_*.xlsx
                                       └─ export_spec_models → 型号全集清单(csv)
                                                        │
                                                        ▼ 输入
┌──────────── 价格 + 网评线（后跑，按 型号 × 零售站）──────────────┐
 型号全集 ── 逐零售站：search_url → 定位商品 → product_url
              → collect_detail（一次抽取同时取 价格 + 评价 + 汇总）
                     │                                   │
                     ▼                                   ▼
             price_snapshot / price_shop_snapshot     review / review_summary
                     │                                   │
                     ▼                                   ▼
             价格监控 CSV/XLSX（MXN，渠道=6零售站）    网评汇总 CSV/XLSX（20列，AI列空）
                     └──────── 型号×零售站 状态表（ok/no_item/…）────────┘
```

限速/反爬/缓存/浏览器均沿用 `infra.py`（`RateLimiter` 按域名+状态码退避、`BlockDetector` 反爬识别、`DiskCache`）与 `fetchers.py`（`BrowserFetcher`/`HttpFetcher` 统一 `Dom` 接口）。所有运行写 `crawl_run`/`crawl_error` 审计。

## Components and Interfaces

### 1. 区域配置（`overseas/regions_config.py`）

在现有 `_CA` 之后新增 `_MX`，并加入 `REGIONS`。纯数据，不 import 适配器，避免循环依赖。

```python
_MX = Region(
    code="mx", name="墨西哥", currency="MXN", locale="es-MX",
    enabled=False,  # 全部适配器接入并小样验证通过后置 True
    note="北美洲墨西哥 TV 线：SPEC 走 4 品牌官网，价格+网评在零售站同一商品页同步抓",
    brands=[
        Brand("tcl_mx", "TCL"),
        Brand("samsung_mx", "Samsung"),
        Brand("lg_mx", "LG"),
        Brand("hisense_mx", "Hisense"),
    ],
    spec_sites=[
        SpecSite("tcl_mx", "tcl_mx", "TCL", "https://www.tcl.com/mx/es/tvs"),
        SpecSite("samsung_mx", "samsung_mx", "Samsung", "https://www.samsung.com/mx/tvs/all-tvs/"),
        SpecSite("lg_mx", "lg_mx", "LG", "https://www.lg.com/mx/televisores"),
        SpecSite("hisense_mx", "hisense_mx", "Hisense", "https://hisense.com.mx/televisores"),
    ],
    retail_sites=[
        RetailSite("amazon_mx",    "Amazon",   "https://www.amazon.com.mx/", enabled=False),  # L3 强防护先关
        RetailSite("liverpool_mx", "Liverpool","https://www.liverpool.com.mx/tienda/home", enabled=True),
        RetailSite("sams_mx",      "Sam's",    "https://www.sams.com.mx/", enabled=True),
        RetailSite("palacio_mx",   "Palacio",  "https://www.elpalaciodehierro.com/buscar?q=tv", enabled=True),
        RetailSite("walmart_mx",   "Walmart",  "https://www.walmart.com.mx/", enabled=False),  # L3 强防护先关
        RetailSite("coppel_mx",    "Coppel",   "https://www.coppel.com/sd/TV", enabled=True),
    ],
)
REGIONS = {"ca": _CA, "mx": _MX}
```

> 注：`probe_url` 用给定官网 URL 的落地页；具体 SPEC 入口 URL 以适配器 `spec_entry_url()` 为准（开发时实测校正，如 TCL/LG 的墨西哥路径）。强防护站 `enabled` 初始为 `False`，实测低频通过后逐个开启。

### 2. SPEC 站点适配器（4 个，`supports_spec=True`）

每个目录结构：`sites/<brand>_mx/{__init__.py, adapter.py, schema.json?}`。继承 `SiteAdapter`，`country="墨西哥"`、`channel="<品牌> 官网"`、`requires_browser=True`（官网多为 JS 渲染）、`protection=L1_MILD`、`suggested_interval≈4.0`。

两种实现路径，按官网结构择一（复用 `spec_crawl` 现有编排，不改核心）：

- **单级**（入口页直接列出系列/型号链接，如 Hisense 日本模式）：实现 `spec_entry_url()` + `list_series(dom, html) -> [(系列名, SPEC页URL)]` + `parse_spec(dom, series, url) -> SpecSheet`。
- **多级**（入口→系列页→多型号页，如松下日本模式）：实现 `series_entries(open_dom) -> [(系列名, [型号SPEC页URL...])]` + `parse_spec_model(dom, series, model, url)` + `model_from_url(url)`。

各品牌预判（开发时以实测为准）：

| 站点 | 官网入口 | 结构预判 | 备注 |
|---|---|---|---|
| `hisense_mx` | hisense.com.mx/televisores | 单级或多级 | 参考 `hisense_jp` 表解析思路 |
| `tcl_mx` | tcl.com/mx 电视频道 | 多级（产品列表→详情规格） | 日本 TCL 用 JSON 端点，墨西哥站需实测 |
| `samsung_mx` | samsung.com/mx/tvs/all-tvs/ | 多级（列表→型号页 Specs 区） | Samsung 规格常在详情页「Especificaciones」块，可能有 JSON-LD |
| `lg_mx` | lg.com/mx/televisores | 多级（列表→型号页 Specs 区） | LG 规格页常有结构化表 |

规格页解析：优先复用 `extract.py` 声明式表解析（`schema.json` 的 `specs`），必要时在适配器内自定义 `parse_spec`/`parse_spec_model`（类似 `spec_parser.parse_hisense_table`）。中文列翻译沿用 `dict/spec_*_zh.json` 词典机制；西班牙语→中文词典（`spec_es_zh.json`）**本阶段可留空/最小**，缺词进 `spec_untranslated`，不阻塞抓取。

导出复用 `spec_export`（宽表 + 顶部「上市时间」行；官网无上市时间时该行留空，后续可由零售站补采）。

### 3. 零售站适配器（6 个，价格+网评同步）

每个目录：`sites/<retailer>_mx/{__init__.py, adapter.py, schema.json}`。继承 `SiteAdapter`，`country="Mexico"`、`channel="<零售站名>"`、`requires_browser` 与 `protection` 按站点定，`suggested_interval` 强防护站 ≥8s、其余 ≥5s。

适配器只负责「URL 怎么拼 + 列表页怎么取商品」：
- `search_url(keyword, page)`：站内搜索 URL（型号作为关键词）。
- `product_url(sku)`：商品详情页 URL。
- `reviews_url(sku, page)`：评价页 URL；**若评价就在商品页则返回空串**，评价随商品页一并抽取（这实现「价格+网评同步抓取」）。
- `parse_search`：默认由 `schema["search"]` 驱动（container/sku/title/url），必要时覆盖以做型号匹配。

字段抽取全部写 `schema.json`（DOM 改版只改 JSON），至少含：

```json
{
  "anchor": "<商品页关键锚点>",
  "search":  { "container": "...", "sku": {...}, "title": {...}, "url_template": "..." },
  "product": { "title": {...}, "brand": {...}, "model": {...}, "size": {...} },
  "price":   { "price": {...}, "list_price": {...}, "currency": {...}, "in_stock": {...} },
  "summary": { "avg_rating": {...}, "total_count": {...} },
  "reviews": { "container": "...", "fields": { "rating":..,"title":..,"body":..,
               "author":..,"review_date":..,"helpful_count":..,"review_url":.. },
               "media": { "images": {...}, "videos": {...} } }
}
```

`price.currency` 的 `transform` 需识别墨西哥比索（`$`/`MXN`/`M.N.`），归一到 `MXN`。

各零售站防护/实现预判：

| 站点 | 防护 | Fetcher | 评价位置预判 | 建议间隔 | 初始 enabled |
|---|---|---|---|---|---|
| `amazon_mx` | L3 强 | 浏览器 | 独立评价页（同 amazon_ca 结构，可大量复用其 schema） | 8s | False |
| `walmart_mx` | L3 强 | 浏览器 | 商品页/异步接口 | 8s | False |
| `liverpool_mx` | L2 | 浏览器 | 商品页评价块（PowerReviews/BV 常见） | 5s | True |
| `sams_mx` | L2 | 浏览器 | 商品页评价块 | 5s | True |
| `palacio_mx` | L2 | 浏览器 | 商品页评价块 | 5s | True |
| `coppel_mx` | L2 | 浏览器 | 商品页评价块 | 5s | True |

> `amazon_mx` 的 `schema.json` 以 `sites/amazon_ca/schema.json` 为蓝本改造（Amazon 各国站 DOM 高度一致），`base_url` 换 `amazon.com.mx`，价格 transform 归一 MXN。

### 4. 同步抓取编排（复用 `scenarios.collect_detail`）

`collect_detail(adapter, fetcher, sku, want_reviews=True)` 已在一次 `open_dom` + 一次抽取里同时产出 `product / specs / price / summary / reviews`——这正是「同一商品页同步抓价格与网评」的现成能力，无需新写场景。墨西哥线新增一个薄编排脚本，按「型号 × 启用零售站」循环：

```
for retail_site in region.retail_sites (enabled):
    adapter = SiteRegistry.get(retail_site.site)
    for model in 型号全集(region):
        surl = adapter.search_url(model)
        hits = adapter.parse_search(open(surl))
        payload, res, target = _pick_by_model(adapter, fetcher, model, hits)  # 复用 scenarios 的型号匹配
        if payload is None: 记 no_item/no_match 状态; continue
        # payload 已同时含 price 与 reviews（同步抓取）
        if reviews_url 非空且需要更多评价: 翻评价页补齐（复用 s4 增量逻辑）
        累计到 价格记录 / 网评记录 / 状态记录
        --save-db 时: save_payload(db, site_id, payload, stats)  # 复用现有落库
```

型号匹配复用 `scenarios._pick_by_model` / `_norm_model`（「以型号开头 > 独立词 > 子串 > 详情页 model 权威校验 > 兜底不记」），避免把配件价记成整机价。

### 5. 导出层（复用现有模板，适配 MXN 与墨西哥渠道）

- **网评**：直接用 `review_export.COLUMNS`（20 列）。`ReviewRecord.country="Mexico"`、`channel=<零售站名>`、`price` 填 MXN 价、`translation/ai_pros/ai_cons` 由 `NULL_HOOKS` 恒空。无需改导出层。
- **价格**：`price_export.py` 现将 8 家日本店铺列硬编码（`SHOP_COLUMN_NAMES`）。墨西哥线采取**数据驱动的渠道列**：新增一个「区域→渠道列」的取值来源（可选方案 A：在 `price_export` 增加按 region 传入 `shop_column_names` 的参数，默认仍为日本 8 家；方案 B：墨西哥价格用「一行=型号，每个零售站一列价格」的宽表，列由 `region.retail_sites` 生成）。**采用方案 A**：给导出函数增加可选 `columns`/`region` 入参，日本线不传保持原样，墨西哥线传入 6 个零售站列名。这样不破坏日本线既有列，符合「导出列定义只在导出文件里」的约束。

### 6. 任务脚本（`scripts/`，参考日本线）

- `refresh_spec_mx.py`（或复用 `refresh_spec.py` 加 `--region mx`）：按 region 读取 SPEC 站点 → `spec-crawl` 各品牌 → `spec-export` → 状态汇总。
- `export_spec_models.py`：加 `--region mx` 产出墨西哥型号全集清单（复用现有脚本的 region 读取）。
- `crawl_mx_retail.py`：**核心新脚本**。按「型号 × 启用零售站」跑第 4 节编排，同步抓价格+网评，导出价格监控表与网评汇总表；支持 `--brand / --site / --year / --models / --limit-models / --save-db`。

执行顺序（满足需求 5.1）：先 SPEC（`refresh_spec_mx` + `export_spec_models --region mx`），产出型号全集后再 `crawl_mx_retail`。

### 7. 状态与审计

- 复用 `crawl_run` / `crawl_error`（每次运行 / 单条错误）。
- 型号 × 零售站状态：复用 `kakaku_task_status` 表结构（其 `task/brand/model` 维度通用），墨西哥线把 `site`（零售站 code）纳入状态记录键；若现表无 `site` 维度，则在状态写入时把零售站 code 编入 `run_id`/`brand` 上下文或复用现成列，**不新增专用表**（需求 5.5）。状态取值：`ok / no_item / no_match / no_reviews / no_price / blocked / failed`。
- API：`api/regions.py` 已从 `regions_config` 读取，`mx` 线 enabled 后 `/api/regions` 自动可见。

## Data Models

复用现有 `models.py` 与 `schema.sql`（17 表），不新增表：

- `SpecSheet` / `SpecRow`：SPEC 采集产物，入 `spec_series` / `spec_row`。
- `Product`：`site_code=<retailer>_mx`、`sku`=站内商品号、`model`=型号、`size`=尺寸。`(site_id, sku)` 唯一。
- `PriceSnapshot`：`price / list_price / currency=MXN / in_stock`，只 INSERT（时序）。
- `PriceShopSnapshot`：如零售站页含多商家报价则写（多为单一自营，通常一条）。
- `ReviewRecord`（导出）/ `review` 表：`review_key` 取站点评价唯一 id（无则正文哈希），`(product_id, review_key)` 增量去重。
- `ReviewSummary`：均分/总数，只 INSERT。

`site.country` 记 `Mexico`，导出「所属国家/区域」据此填。

## Error Handling

沿用日本线运维红线：

- **404 优先于 blocked**：确定性缺页走回退/跳过，不当反爬。
- **空/失败不静默**：`empty`（成功但无数据）与 `failed`（404/超时/解析异常/拦截）必落审计，不用空表覆盖。
- **相对链接补绝对 URL** 后再 `goto`。
- **型号匹配**严格按优先级，未匹配则不记（宁缺勿错）。
- **SPEC 熔断**：连续瞬时失败达阈值熔断当前品牌剩余系列并逐系列补审计（`spec_crawl` 已内置）。
- **强防护站**低频；批量前先 `probe`；单次探测通过不代表批量安全。
- **导出**先 CSV 后 XLSX，XLSX 占用时改写时间戳文件不丢数据。

## Testing Strategy

分层、以真实小样为主（抓取项目难做纯单测）：

1. **站点自检**：`sites` 命令确认 10 个新站点加载无报错；对每站真实页面跑 `probe` 与 `probe_selectors`，核对 schema 选择器命中。
2. **SPEC 小样**：每品牌 `spec-crawl --site <brand>_mx --only <一个系列>` 跑通，`spec-export` 出表核对区分/机型对齐。
3. **零售小样**：`crawl_mx_retail --site liverpool_mx --models <1个已知型号>`，确认同一商品页同时取到价格与评价，导出两表列正确、币种 MXN、AI 三列空。
4. **型号匹配回归**：构造「型号命中配件」场景，确认 `_pick_by_model` 不误记。
5. **增量去重**：同一型号重跑，确认 `review` 按 `review_key` 不重复。
6. **强防护站**：`amazon_mx` / `walmart_mx` 先单页低频验证，通过后再置 `enabled=True`。
7. **区域配置**：`region_meta("mx")` 返回 4 品牌 / 4 SPEC 站 / 6 零售站及 enabled 状态。

固定 Python：`C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\python.exe`。
