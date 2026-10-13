# Requirements Document

## Introduction

在现有「海外电视数据采集」项目（`overseas/`，已跑通日本线）基础上，**增量开发北美洲墨西哥（MX）电视数据采集线**。只做 TV。整体沿用日本线的三条业务线结构（SPEC / 价格 / 网评）、插件式站点适配器、声明式抽取、域名级限速与反爬识别、SQLite 时序快照、以及通用导出模板。

墨西哥线相对日本线的**关键区别**（决定本 spec 的设计重点）：

1. **SPEC 来源是各品牌墨西哥官网**（TCL / Samsung / LG / Hisense 四个品牌），每个品牌一个官网 SPEC 站点，与日本线「品牌 code == 官网站点 code」的模式一致。
2. **价格与网评来源是多个电商零售站**（Amazon / Liverpool / Sams / Palacio / Walmart / Coppel 六个），而**不是**日本线那种单一聚合站（kakaku.com）。因此「品牌 × 零售站」是多对多：同一个型号要在每个零售站各搜一次。
3. **价格与网评在同一个商品页同步抓取**：访问某零售站的某商品详情页时，一次抓取即取到该商品的价格与用户评价（不再像日本线那样价格线、评论线分两次抓）。
4. **先不接入翻译和大模型**：网评导出模板中的「翻译 / 提炼优点 / 提炼缺点」三列留空、留接口（沿用日本线 `NULL_HOOKS`）。
5. **执行顺序有先后依赖**：先抓 SPEC 产出型号全集清单，再以型号清单为输入去各零售站抓价格与网评。

本功能**不改变**日本线既有语义与产物：日本线的站点、脚本、导出模板、数据库表继续可用；墨西哥线通过新增站点适配器目录、在集中区域配置 `regions_config.py` 中补充 `mx` 线、复用既有场景与导出层来实现，尽量不改核心框架。

### 核心约束（继承自现有实现，不得破坏）

- **新增站点只建目录，不改核心**：每个新站点仅新增 `sites/<code>/{__init__.py, adapter.py, schema.json}`，由 `SiteRegistry` 自动发现。字段抽取写在 `schema.json`，DOM 改版只改 JSON。
- **导出列定义只在三个导出文件里**：SPEC 宽表、通用网评模板（20 列）、价格监控模板（19 列）的列定义分别只在 `spec_export.py` / `review_export.py` / `price_export.py`，墨西哥线复用同模板，只按需调整「所属国家/区域」「货币」等取值。
- **AI 三列留空留接口**：网评导出的翻译 / 提炼优点 / 提炼缺点三列由 `review_export.AiHooks` 产生，本线用 `NULL_HOOKS` 全空，抓取与导出流程不变。
- **空/失败不得静默**：`empty`（请求成功但无数据）与 `failed`（404/超时/解析异常/被拦截）必须落审计（`crawl_run` / `crawl_error` / 状态表），不能用空表覆盖。
- **相对链接必须补成绝对 URL**，否则 `goto` 静默失败。
- **型号匹配**必须遵循「以型号开头 > 独立词 > 子串 > 兜底」优先级，纯子串会命中配件/旧机型。
- **强防护零售站默认先关**：Amazon / Walmart 等强防护站在适配器实现 + 低频小样本验证通过前，`retail_site.enabled=False`，不纳入批量抓取。
- **礼貌抓取**：域名级限速，强防护站建议间隔 ≥8s，官网 ≥4s；`BlockDetector` 识别反爬，404 优先于 blocked 判断。

## Glossary

- **Region（线）**：一条国家/地区采集线，如 `mx`（墨西哥）。在 `regions_config.py` 里声明其品牌、SPEC 官网站点、零售站清单。
- **SPEC 站点**：某品牌官网，提供规格表，`supports_spec=True`，对应 `sites/<code>/adapter.py`。墨西哥线为 `tcl_mx / samsung_mx / lg_mx / hisense_mx`。
- **零售站（RetailSite）**：价格 + 网评来源，同一商品页同步抓取。墨西哥线为 `amazon_mx / liverpool_mx / sams_mx / palacio_mx / walmart_mx / coppel_mx`。
- **型号全集清单**：SPEC 线产出的 `SPEC_型号汇总_*.csv`，是价格线和网评线的输入。
- **同步抓取（价格+网评）**：访问零售站商品详情页时，一次抽取同时得到该商品的价格快照与用户评价。
- **NULL_HOOKS**：网评导出的 AI 三列（翻译/提炼优点/提炼缺点）占位钩子，全部返回空，保留接入点。
- **防护等级**：L1（温和，品牌官网）/ L2（中等）/ L3（强，大型电商，需真实浏览器 + 低频）。

## Requirements

### 需求 1：墨西哥线在集中区域配置中注册

**用户故事：** 作为开发者，我希望墨西哥线的品牌、SPEC 官网站点、零售站清单集中声明为数据，这样脚本和 API 按 region 读取，新增线不再到处复制硬编码。

#### 验收标准

1. WHEN 读取 `regions_config.REGIONS` THEN 系统 SHALL 包含一条 `code="mx"` 的 `Region`，`name="墨西哥"`、`currency="MXN"`、`locale="es-MX"`。
2. THE `mx` 线 SHALL 声明 4 个品牌：`tcl_mx`（TCL）、`samsung_mx`（Samsung）、`lg_mx`（LG）、`hisense_mx`（Hisense）。
3. THE `mx` 线 SHALL 声明 4 个 SPEC 官网站点，`site` 与对应品牌 `code` 一致（`tcl_mx / samsung_mx / lg_mx / hisense_mx`），并带各自官网 `probe_url`。
4. THE `mx` 线 SHALL 声明 6 个零售站：`amazon_mx`（Amazon）、`liverpool_mx`（Liverpool）、`sams_mx`（Sam's Club）、`palacio_mx`（El Palacio de Hierro）、`walmart_mx`（Walmart）、`coppel_mx`（Coppel），并带各自 `probe_url`。
5. WHERE 某零售站为强防护（Amazon / Walmart）THE 系统 SHALL 将其 `RetailSite.enabled` 默认置 `False`，待适配器实现并小样验证后再逐个置 `True`。
6. WHILE 所有 SPEC 站点与零售站适配器尚未全部接入并验证 THE `Region(mx).enabled` SHALL 保持 `False`，全部就绪后置 `True`。
7. WHEN 调用 `region_meta("mx")` THEN 系统 SHALL 返回可 JSON 序列化的地区元数据（品牌 / SPEC 站点 / 零售站及其 enabled 状态），供前端与 API 使用。

### 需求 2：从各品牌墨西哥官网采集 SPEC

**用户故事：** 作为数据分析人员，我希望从 TCL / Samsung / LG / Hisense 的墨西哥官网抓取电视规格表，这样能得到墨西哥在售型号的完整规格与型号全集。

#### 验收标准

1. THE 系统 SHALL 为四个品牌各提供一个 SPEC 站点适配器：`sites/tcl_mx`、`sites/samsung_mx`、`sites/lg_mx`、`sites/hisense_mx`，每个含 `__init__.py`、`adapter.py`（继承 `SiteAdapter`、`supports_spec=True`）、必要时 `schema.json`。
2. WHEN 运行 `spec-crawl --site <brand>_mx` THEN 系统 SHALL 从该品牌官网 TV 入口页解析系列/型号列表，逐个抓规格页解析为 `SpecSheet` 入库（`spec_series` / `spec_row`），并按 ISO 周做快照。
3. THE 每个 SPEC 适配器 SHALL 实现 `spec_entry_url()` 与 `list_series()`（单级）或 `series_entries()` + `parse_spec_model()`（多级：入口→系列页→多型号页），复用 `scenarios.spec_crawl` 现有编排，不改核心。
4. WHERE 官网页面为 JS 渲染 THE 适配器 SHALL 设置合适的 `spec_entry_wait` / `spec_page_wait` 等待锚点与 `requires_browser=True`。
5. WHEN 某系列规格页返回 404 或解析为空 THEN 系统 SHALL 将该系列记为 `empty`/`failed` 写入 `spec_series_status` 与 `crawl_error`，不触发品牌熔断，也不用空表覆盖既有数据。
6. WHEN 官网页面出现连续瞬时失败（网络/超时/429/5xx/拦截）达到阈值 THEN 系统 SHALL 熔断当前品牌剩余系列并逐系列补写失败审计。
7. WHEN 运行 `spec-export --site <brand>_mx --format xlsx` THEN 系统 SHALL 复用现有 SPEC 宽表模板导出（`区分 | 项目 | 项目(中文) | 机型1..N`），顶部保留「上市时间」行（官网无上市时间时该行留空或由零售站/后续补采）。
8. WHEN 运行型号汇总脚本 THEN 系统 SHALL 产出墨西哥线的型号全集清单（`brand_code, model_raw, model_normalized, series, …`），作为价格线与网评线的输入。

### 需求 3：从各零售站在同一商品页同步抓取价格与网评

**用户故事：** 作为数据分析人员，我希望以型号清单为输入，去各墨西哥电商站定位商品，并在同一个商品页一次性抓到价格和用户评价，这样价格与网评来源一致、抓取更省请求。

#### 验收标准

1. THE 系统 SHALL 为六个零售站各提供一个适配器：`sites/amazon_mx`、`sites/liverpool_mx`、`sites/sams_mx`、`sites/palacio_mx`、`sites/walmart_mx`、`sites/coppel_mx`，每个含 `__init__.py`、`adapter.py`（含 `search_url` / `product_url`，按需 `reviews_url`）、`schema.json`（含 `search` / `product` / `price` / `summary` / `reviews` 抽取规则）。
2. WHEN 以某型号在某零售站抓取 THEN 系统 SHALL 先站内搜索定位商品，按「以型号开头 > 独立词 > 子串 > 兜底」挑出该型号商品，再访问其商品详情页。
3. WHEN 访问到商品详情页 THEN 系统 SHALL 在**同一次抽取**中同时得到：价格（含最低价/现价、货币 MXN、是否有货）与该商品页可见的用户评价（评分、标题、正文、时间、赞同数、链接），即价格与网评同步抓取。
4. WHERE 某零售站的评价在独立评价页 THE 适配器 SHALL 提供 `reviews_url()`，系统在商品页抓价格后按需翻评价页补齐评价；WHERE 评价就在商品页 THE `reviews_url()` 返回空串，评价随商品页一并取。
5. WHEN 同一型号在多个零售站均有商品 THEN 系统 SHALL 对每个启用的零售站各抓一次，价格与评价按零售站分别记录/入库。
6. WHEN 某型号在某零售站搜索无结果或未匹配到该型号 THEN 系统 SHALL 记为对应状态（如 `no_item`/`no_match`）落审计，不把配件或其它型号的价格/评价错记到该型号。
7. WHEN 某零售站被反爬拦截 THEN 系统 SHALL 记 `blocked` 并按站点策略降频/跳过，404 优先按缺页处理而非拦截。
8. THE 价格抓取 SHALL 产出可入 `price_snapshot`（整体价）与（如站点提供多商家报价）`price_shop_snapshot`（商家维度价）的数据；THE 网评抓取 SHALL 产出可入 `review`（按 `(product_id, review_key)` 增量去重）与 `review_summary` 的数据。

### 需求 4：价格与网评导出（复用通用模板，币种为 MXN）

**用户故事：** 作为数据分析人员，我希望墨西哥线的价格和网评导出成与日本线一致的表格，这样多地区表头统一、便于比对。

#### 验收标准

1. WHEN 导出墨西哥线网评 THEN 系统 SHALL 复用 `review_export` 的 20 列通用模板，「所属国家」列填 `Mexico`、「渠道」列填对应零售站名（Amazon / Liverpool / Sam's / Palacio / Walmart / Coppel）、「价格」列货币为 MXN。
2. THE 网评导出的第 16–18 列（翻译 / 提炼优点(通过AI) / 提炼缺点(通过AI)）SHALL 留空，由 `NULL_HOOKS` 产生，保留接入点。
3. WHEN 导出墨西哥线价格 THEN 系统 SHALL 产出价格监控表，「所属区域」填墨西哥、「货币」填 `MXN`，店铺/渠道列对应墨西哥六个零售站（而非日本线的 8 家日本电商）。
4. THE 导出 SHALL 先写 CSV 再写 XLSX；XLSX 被占用时自动改写带时间戳文件，不丢数据。
5. WHERE 通用价格模板的店铺列为日本电商硬编码 THE 系统 SHALL 以数据驱动方式让墨西哥线的零售站作为渠道列（不破坏日本线既有列）。

### 需求 5：执行顺序、任务编排与状态可观测

**用户故事：** 作为运维/开发者，我希望先抓 SPEC 再抓价格与网评，并能看到每个型号在每个零售站的采集状态，这样能判断「哪些没抓到、为什么」。

#### 验收标准

1. THE 系统 SHALL 保证执行顺序：先运行 SPEC 采集产出型号全集清单，再以该清单为输入运行价格与网评抓取。
2. THE 系统 SHALL 提供墨西哥线的任务脚本（参考日本线 `scripts/`）：SPEC 采集/导出、型号汇总、以及「按型号 × 零售站」同步抓价格+网评并导出，可按 `--brand` / `--site` / `--year` / `--models` 过滤。
3. WHEN 抓取价格/网评 THEN 系统 SHALL 按型号 × 零售站维度记录采集状态（如 `ok / no_item / no_match / no_reviews / no_price / blocked / failed`）到状态表，供概览与明细查询。
4. WHEN 加 `--save-db` THEN 系统 SHALL 将型号登记为 `product`、价格入 `price_snapshot`（及可用时 `price_shop_snapshot`）、评价入 `review`（增量去重）、状态入状态表；不加 `--save-db` 时仅出 CSV/XLSX。
5. THE 系统 SHALL 复用现有数据库表结构（`schema.sql`），不为墨西哥线新增专用表；区域信息通过 `site.country` / 导出列「所属国家/区域」体现。

### 需求 6：通道验证与站点自检

**用户故事：** 作为开发者，我希望在批量抓取前先验证每个墨西哥站点可访问、选择器有效，这样能先发现被拦截或 DOM 改版的问题。

#### 验收标准

1. WHEN 运行 `sites` 命令 THEN 系统 SHALL 列出所有站点（含新增的 4 个 SPEC 站点与 6 个零售站）且加载无报错。
2. WHEN 运行 `probe --site <code> --url <页面>` THEN 系统 SHALL 报告该站点可访问性（HTTP / 浏览器模式）、是否被拦截。
3. WHEN 对某站点某真实页面运行选择器自检（`probe_selectors`）THEN 系统 SHALL 逐条报告 `schema.json` 里 product/price/summary/reviews/search 选择器的命中情况。
4. WHEN 调用 `/api/regions` THEN 系统 SHALL 返回包含 `mx` 线的地区→站点→能力元数据（在 `mx` 线 enabled 后）。

### 需求 7：暂不引入翻译与大模型依赖

**用户故事：** 作为项目负责人，我希望本阶段墨西哥线只做「抓取 + 结构化导出」，先不引入翻译/大模型，这样先把数据管道打通、后续再接入。

#### 验收标准

1. THE 墨西哥线抓取与导出流程 SHALL 不调用任何在线翻译或大模型服务。
2. THE 网评导出的翻译/提炼优点/提炼缺点三列 SHALL 恒为空（`NULL_HOOKS`），且抓取/导出代码保留 `AiHooks` 接入点以便后续一处接入。
3. THE 本线 SHALL 不新增 `deep-translator` / `argos-translate` / 大模型 SDK 等依赖到 `requirements.txt`。
