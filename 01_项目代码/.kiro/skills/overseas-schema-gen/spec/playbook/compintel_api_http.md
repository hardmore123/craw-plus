# 套路：第三方合规数据库 API 抓取（compintel_api_http）

> 状态：✅ **固定程序已实现**（`overseas/compintel/`，2026-10-25 扩展）
> 目标站点：FCC（fccid.io 聚合）、EPREL（eprel.ec.europa.eu 官方 API）、ENERGY STAR（Socrata）、ANATEL（巴西 ZIP-CSV）、IC/ISED（加拿大 Spring WebFlow）、TÜV Rheinland（Certipedia）、VDE/CB（Solr）
> 真实抓取已验证：FCC 310 条、EPREL 4 条、ENERGY STAR 585 条、ANATEL 2457 条、IC/ISED 38 条、TÜV 89 条、UL/CB 162 条 = 3645 条记录 / 1053 条信号
> 注：compintel **不走 spec_crawl 引擎**，是独立固定程序（无逐站 schema/adapter 配置）。

---

## 为什么不用 spec_crawl 引擎（compintel 与 spec/retail 的本质区别）

spec/retail 抓的是**品牌官网 lineup**（每站结构不同，需 schema+adapter 配置驱动）。
compintel 抓的是**第三方合规数据库**（FCC/EPREL），特点：

| | spec/retail | compintel |
|---|---|---|
| 数据源 | 品牌官网（逐站结构各异） | 合规数据库（接口固定，全站统一） |
| 配置需求 | 每站一份 schema.json | 无需逐站配置，代码即配置 |
| 目的 | 抓全型号规格/价评 | 抓竞品上市领先指标 |
| 抓取模式 | 发现已知型号 → 抓规格 | 抓全量 → 去重 → 变化检测 |
| 引擎 | spec_crawl / retail_crawl | 独立 orchestrator |

结论：FCC/EPREL 接口固定、字段稳定、无逐站适配需求，固定程序比套引擎更直接。
强行套 spec_crawl 会很别扭（引擎白名单字段对不上、discover.mode 无匹配项）。

---

## 识别信号（什么时候用这个套路）

| 信号 | 说明 |
|---|---|
| 数据源是政府/合规数据库（FCC/EPREL/FDA/CE） | 非品牌官网，是第三方权威库 |
| 数据在 JSON API 或聚合站 HTML | 纯 HTTP 可达，无需浏览器 |
| 目的是竞品预警/合规监控 | 非抓全规格，是抓"新出现的 source_id" |
| 需要跨次抓取做变化检测 | 时序快照 + 字段对比 |

---

## FCC：官方被 Akamai 封 → 走聚合站（纯 HTTP）

### 关键决策：apps.fcc.gov 不可用
`apps.fcc.gov/oetcf/eas/reports/GreerSearch.cfm` 返回 403 + `errors.edgesuite.net`（Akamai 硬封）。
HTTP 和 Playwright 都被封。改走 `fccid.io` 聚合站，纯 HTTP 可拿。

### 抓取结构（三种页面）
| 页面 | URL | 用途 |
|---|---|---|
| 搜索页 | `/search?q=<kw>` | Company Results 表格（公司+授权码）+ panel 列表 |
| **授权码页** | **`/<GC>`** | **该授权码下全部 FCC ID（100/页，分页 `/<GC>/page/N`）** |
| 详情页 | `/<FCCID>` | 文件清单（保密到期检测，`data-label` 属性） |

### ⚠ 最重要的教训：公司名搜索会严重截断
| 方式 | TCL 记录数 | 说明 |
|---|---|---|
| 搜 "TCL Communication" | 33 条 | **被截断** |
| 授权码 2ACCJ 页面 | **508 条**（6 页） | **全量** |

**必须走"搜索发现授权码 → 遍历授权码所有分页"，不能只靠公司名搜索。**

### 授权码自动发现（两条路径并用，缺一不可）
1. **Company Results 表格** → `parse_company_results()`
   - `<td data-label="Company"><a href="/PY7">Sony Corporation</a></td>` 共 4 列
   - 缺点：只覆盖公司名前缀匹配的，漏子公司
2. **搜索 panel 的 "Registered Grantee"** → `parse_search_results()` 已有 `grantee_code`
   - 优点：**能发现子公司**（搜 "Hisense" 的面板里有 Hisense Ronshen 的 2A4A3）

### 授权码页解析（`parse_grantee_page`）
```html
<h2>...Applications by 2ACCJ (TCL Communication Ltd.) - Page 1 of 6</h2>
<table class="table grantee-applications-table">
  <tr><td data-label="FCC ID / Date"><b><a href="/2ACCJB247">2ACCJB247</a></b><br>2026-08-17</td>
      <td data-label="Product / Type">Projector<br>Original Equipment</td></tr>
```
- 标题 "Page X of Y" 给出总页数 → 循环到 Y
- 记录含 fcc_id / app_date / product（=description）/ app_type

### 6 家竞品实测授权码数（共 ~72 个）
| 品牌 | 授权码数 | 关键词 |
|---|---|---|
| Samsung | 13 | samsung / Samsung Display / Samsung Electro / Samsung SDI |
| LG | 9~17 | LG Electronics / LG Innotek / LG Display / Goldstar |
| Hisense | 12+ | hisense / Hisense Visual / Qingdao Hisense / Hisense Ronshen / Qingdao Intelligent |
| TCL | 9~10 | TCL Overseas / TCL Communication / Shenzhen TCL / TCL Entertainment / TCL Technology / TCL Industrial |
| Sony | 8 | sony / Sony Group / Sony Semiconductor |
| Panasonic | 12 | panasonic / Panasonic Industrial / Automotive / Avionics / Connect |

### 品牌过滤（防关键词误匹配，关键坑）
搜 "TCL E" 会匹配到 "Netclearance Systems"（非 TCL）；搜 "LG" 会匹配到 "AdoModel Tech"/"Panda Wireless"（非 LG）。
**公司名搜索会产生假阳性**（实测旧数据里 20 条"LG/Panasonic"实际申请人是别家）。
必须按品牌 token 过滤公司名（`_BRAND_TOKENS`）；公司名不含 token 的子公司用显式别名（`_GRANTEE_ALIASES`，如 Hisense → 2AJVQ Qingdao Intelligent）。

### 意外收获：ODM 代工厂授权码能提前暴露竞品动向
搜索面板发现的授权码可能属于**代工厂**，其公司名不含品牌 token，但 FCC 页面注册网站就是品牌官网。
实测：`ZVA` = Tonly Technology Co., Ltd.，其 grantee 页 `grantee-website-link` 指向 `https://tcl.com/`
→ Tonly 是 TCL 的代工厂，其 FCC 申报（Soundbar/Wireless Speaker 等）就是 TCL 的产品。
**结论**：面板发现的授权码不加 token 过滤（保留 ODM），这样能抓到代工厂提前曝光的竞品产品线。

### 其他实测坑
| 症状 | 修法 |
|---|---|
| 同一 FCC ID 挂多个授权码 → `UNIQUE constraint failed` | 抓取循环内维护 `seen_in_run` 集合，同 ID 只入一次（修后 fail 从 9 → 0） |
| FCC ID 格式差异 | 授权码页给的带横线(`2AJVQ-MWH568S`)是权威格式；搜索页给的不带横线是残缺版 |

### 命令
```bash
# 推荐：增量抓取（默认增量，遇整页已知ID即停翻，已知记录不重复入库）
py -3.12 -m overseas.cli compintel-fcc-full --brands Samsung LG Hisense TCL Sony Panasonic

# 日常任务：今天抓过的授权码整码跳过（秒回）
py -3.12 -m overseas.cli compintel-fcc-full --brands Samsung LG --refresh-days 1

# 周度深度：全量重查全部页 + 抓详情页（检测保密到期/字段变化）
py -3.12 -m overseas.cli compintel-fcc-full --brands Samsung LG --full-refresh --details

# 查看抓取进度（哪些授权码抓过/何时抓/翻了几页）
py -3.12 -m overseas.cli compintel-states --source fcc

# 调试：每授权码只抓 1 页
py -3.12 -m overseas.cli compintel-fcc-full --brands TCL --max-pages 1

# 旧方式（公司名搜索，会截断+假阳性，仅兼容保留）
py -3.12 -m overseas.cli compintel-fcc --applicants "TCL Overseas"
```

### 增量抓取（核心机制）
**问题**：每次全量抓取 85 个授权码 ~200 请求 ≈ 10 分钟，数据没变也重抓重入。

**方案**：`compintel_crawl_state` 表记录每个授权码上次抓到哪 + 已知 FCC ID 集合。
- 授权码页按日期倒序 → 遇整页全是已知 ID 即停翻（后续页必然更旧）
- 已知记录不重复入库（增量模式只 INSERT 新记录，避免快照堆积）
- `--refresh-days N`：N 天内抓过的授权码整码跳过（0 请求）

**实测效果**：
| 场景 | 耗时 | 请求 | 新增 |
|---|---|---|---|
| 首次（空库） | ~10 分钟 | ~200 页 | 310 条 |
| 增量（无变化） | ~2 秒 | ~95 页（85个第1页+少量第2页早停） | 0 |
| `--refresh-days 1`（今天抓过） | ~2 秒 | 0 页（85个全跳过） | 0 |

### 限速
`FCC_RATE = 2.0s`（RateLimiter）；首次全量 6 家 ~200 请求 ≈ 10 分钟；增量 ~95 页。

### 保密到期检测
详情页能抓到 Internal/External Photos / Users Manual = 保密期已结束（FCC 保密最长 180 天）。
关键词：`internal photos` / `external photos` / `id label` / `users manual`（小写包含匹配）。

---

## EPREL：Angular SPA → 官方 JSON API（纯 HTTP）

### 关键决策：screen/* 页面是 SPA，数据在 /api/
`eprel.ec.europa.eu/screen/product/electronicdisplays` 返回 Angular app-root（无数据）。
数据全在 `/api/` JSON 接口，纯 HTTP 可拿，无需浏览器。

### 抓取结构
```
列表：GET https://eprel.ec.europa.eu/api/products/electronicdisplays
  返回 {size: 37509, hits: [25 条]}
  必带头：Accept: application/json, Origin, Referer
详情：GET https://eprel.ec.europa.eu/api/product/<regNumber>
  返回 ~3.3KB JSON
```

### 关键坑（实测）
| 坑 | 现象 | 解法 |
|---|---|---|
| 产品组标识 | `electronicdisplays2021` 是法规号 → "Model not found" | 用 `electronicdisplays`（产品组 URL） |
| 翻页参数全被忽略 | from/size/page/pageSize/limit/offset 都返回同 25 条 | 轮询 + 注册号去重 |
| 大偏移触发 403 | from ≥ 370000 → 403 | 不能一次拉全量，靠轮询逐步覆盖 |
| POST 被 403 | POST /api/products/... → 403 | 只接受 GET |
| **注册号跨产品组混编** | reg=100 是 televisions，reg=1000 是 ovens，reg=410000+ 是 tyres | scan 时按 productGroup 字段过滤，不能假设号段对应单一组 |
| **televisions ≠ electronicdisplays** | 竞品电视(Sony/Samsung/LG)在 `televisions` 组(8424条)，非 `electronicdisplays`(37467条) | scan_range 同时接受 televisions + electronicdisplays |
| **列表接口返回最旧非最新** | 列表 25 条的 market_start 都是 2019-2023(最旧注册)，不是近期新品 | 近期新品只能靠注册号 scan 找，不能靠列表接口 |

### 限速
`EPREL_RATE = 1.2s`，必带 `Accept/Origin/Referer` 头否则可能被拒。

### 抓全量策略（列表不可翻页）
1. 定期调列表接口（每次 25 条样本）。
2. 按 `eprelRegistrationNumber` 去重，新号入库 + 产 eprel_new_reg 信号。
3. **注册号全量扫描**（`scan_range`）：按注册号区间遍历 `/api/product/<reg>`，
   过滤 productGroup ∈ {televisions, electronicdisplays} + 竞品品牌 + since 日期。
   注册号上限约 402201(electronicdisplays 最后一批),410000+ 是 tyres/lamps 等其他组。
4. 抓具体产品：用注册号直查 `/api/product/<reg>`（稳定）。

### EPREL scan 命令（`compintel-eprel-scan`）
```
# 抽样扫描(step=1000,约 8 分钟,覆盖 400 号)
py -3.12 -m overseas.cli compintel-eprel-scan --brands Samsung LG Hisense TCL Sony Panasonic --step 1000
# 密集扫描(step=500,约 16 分钟,覆盖 800 号)
py -3.12 -m overseas.cli compintel-eprel-scan --brands Samsung LG Hisense TCL Sony Panasonic --step 500
# 带时间限制(只留 2024+ 上市的)
py -3.12 -m overseas.cli compintel-eprel-scan --brands Samsung LG --since 2024-01-01 --step 500
```

---

## 变化检测（compintel 核心：时序快照 + 跨次对比）

### 数据模型：时序快照（不覆盖历史）
每次抓取 INSERT 新快照到 `compintel_record`，同一 source_id 保留多份快照。
`compintel_record` 表 UNIQUE 约束是 `(source, source_id, captured_at)`——时间维度唯一。

### before_captured_at 截点（关键，否则 bug）
变化检测在插入本次快照**后**运行，但查"上次快照"时必须用：
```python
cidb.last_record(source, sid, before_captured_at=run_started_at)
```
若不加 `before_captured_at`，会查到刚插入的本次自己 → supplier_change/field_change 恒不触发。
orchestrator 用 `crawl_run.started_at`（本次 run 开始时间）作为截点传给所有 detector。

### 8 类信号
| 信号 | 检测逻辑 | 时序依赖 |
|---|---|---|
| new_fcc_id | source_id 首次出现 | 首次抓 |
| eprel_new_reg | 注册号首次出现 | 首次抓 |
| confidential_expired | 详情页能抓到保密类文档 | 详情页 |
| supplier_change | 同 source_id 历次快照 applicant 变了 | 跨快照 |
| field_change | 同 source_id 任意语义字段变了 | 跨快照 |
| energy_class_jump | 同品牌比历史最佳高 ≥2 级 / 同产品本次比上次高 | 跨快照 |
| eprel_delisted | status 变非在售 / onMarketEnd 近30天 / 上次在售本次下架 | 跨快照 |
| **launch_warning** | new_* 信号上叠加:产品类型过滤(TV/display 关键词)+ 在售比对 + 提前量(lead_days) | 首次抓 |

### launch_warning 上市预警(核心预警信号)
把 new_fcc_id(645 条噪声)升级为真正可用的上市预警(约 27 条):
1. **产品类型过滤**:FCC description 字段匹配 TV_DISPLAY_KEYWORDS(tv/television/display/monitor/oled/qled/lcd tv/smart tv/uhd/4k/8k),排除 EXCLUDE_KEYWORDS(remote/charger/phone/watch/glasses/lock)
2. **在售状态比对**:EPREL 看 market_start 是否已过;FCC 查 product 表有无同品牌型号
3. **提前量计算**:认证/注册日期距今天数(lead_days),量化"比上市早多少天"
只对 `is_new=True` 的记录触发(首次抓取时才有,重跑不重复触发)。

---

## 时间限制(只抓新品,不堆旧认证)

竞品预警只关心**近期新品**,旧认证/旧注册无预警价值。两个数据源都加 `--since` 参数:

| 数据源 | 默认截止 | 依据 | 命令示例 |
|---|---|---|---|
| FCC | 近 365 天(auth_date >= 365天前) | FCC 认证到发布 1-3 月,1 年窗口覆盖所有待发新品 | `compintel-fcc --since 2025-10-01` |
| EPREL scan | 近 730 天(market_start >= 730天前) | EPREL 注册到发布数天-数月,2 年窗口更宽 | `compintel-eprel-scan --since 2024-01-01` |

不带 `--since` 时各子函数自动用默认值(FCC=365天,EPREL=730天)。
时间过滤在 orchestrator 层做:抓到的记录 auth_date/market_start < since 直接跳过不入库。

### 清理旧数据(已有库)
若库里已堆了大量旧认证(如 1999-2026 全量),清理脚本:
```python
# 删 FCC 1 年前的 + EPREL 2 年前的 + 孤儿信号
c.execute("DELETE FROM compintel_record WHERE source='fcc' AND auth_date < '2025-10-01'")
c.execute("DELETE FROM compintel_record WHERE source='eprel' AND market_start < '2024-01-01'")
c.execute("DELETE FROM compintel_alert WHERE source_id NOT IN (SELECT source_id FROM compintel_record)")
```

---

## 定时预警（分层抓取）

### 频率：每天 1 次足够（不要过频）
FCC/EPREL 是合规数据库，天级更新。信号提前量：FCC 认证到发布 1-3 月、EPREL 注册到发布数天。
过频（每小时）只是重复拿相同数据 + 浪费请求配额 + 增被封风险。

### 分层
| 层 | 频率 | 命令 | 产出 |
|---|---|---|---|
| 日常 | 每天 06:00 | `compintel-run`（无 --details） | new/reg/supplier/field/delist |
| 深度 | 每周一 07:00 | `compintel-run --details` | + confidential_expired |

### 安装
`scripts/compintel_install_task.ps1` 一键注册两个 Windows 计划任务。
带 StartWhenAvailable（错过补跑）+ 30 分钟超时 + 失败重试 2 次。

---

## 常见失败与修法

| 症状 | 修法 |
|---|---|
| FCC apps.fcc.gov 403 | 已知，改走 fccid.io，不要回头试官方 |
| FCC 存库失败 `&amp;` 等实体 | fcc_crawler.py 加 `import html as _html` + `_html.unescape()`(注意:参数名 `html` 会遮盖模块,必须用别名) |
| **TCL 搜 "TCL" 返回 0 条** | fccid.io 全文搜索不匹配短缩写;必须搜 "TCL Electronics"+"TCL Technology"+"TCL Overseas"+"TCL Communication"+"TCL Industrial"(5 个变体) |
| **抓取严重不全(核心问题)** | 公司名搜索被截断(TCL 33 条 vs 授权码 2ACCJ 508 条);必须用 `compintel-fcc-full` 走"授权码发现 + 分页遍历" |
| **子公司漏抓** | 只解析 Company Results 表格会漏子公司(Hisense Ronshen 2A4A3);必须同时解析搜索面板的 grantee code |
| **关键词误匹配假阳性** | 搜 "LG" 会命中 AdoModel/Panda Wireless;按 `_BRAND_TOKENS` 过滤公司名 |
| **同一 FCC ID 重复入库** | 一个 ID 可能挂多个授权码 → `UNIQUE constraint failed`;循环内用 `seen_in_run` 去重 |
| **每次都重抓旧数据(慢+DB膨胀)** | 默认增量模式:遇整页已知ID停翻+已知记录不重复入库;`--refresh-days N`跳过N天内抓过的授权码;`--full-refresh`强制全量重查 |
| **LLM 恒降级到规则式摘要** | httpx2 `trust_env` 走系统代理;必须**先**设 `NO_PROXY`+清代理**再**建 OpenAI client(client 构造时缓存代理) |
| **brand 不归一化** | 搜 "TCL Electronics" 时 brand 存为 "TCL Electronics" 而非 "TCL";用 `_normalize_brand()` 归一化(映射表含所有 TCL/Samsung/LG 变体) |
| **launch_warning 恒 0 条** | `_is_on_market` 对 FCC 用 "品牌在 product 表有记录" 判定在售——错!所有竞品品牌在 spec 库都有记录,导致全部被误判为"已在售"过滤;FCC 认证≠在售,改为只看 FCC ID==product.model(极少见) |
| **TCL launch_warning 只有投影仪** | TCL 近 1 年 FCC 认证多为 Sound Bar/Projector/手机/门锁,无 TV;TV 可能用其他公司名或走其他认证途径 |
| EPREL 返回 "Model not found" | 产品组写成了 `electronicdisplays2021`，改 `electronicdisplays` |
| EPREL 列表只给 25 条 | 翻页参数被忽略，靠轮询+注册号去重或 `scan_range` 逐号扫描 |
| EPREL scan 扫到 0 条竞品 | 检查 `scan_range` 的 productGroup 过滤是否含 `televisions`(不只 `electronicdisplays`) |
| EPREL scan 全是旧记录 | 加 `--since` 时间过滤,列表接口返回最旧非最新 |
| `new=0` 但实际有新记录 | seen_source_id 在 add_record 后查恒为 True，必须插入前预判 is_new |
| supplier_change 恒不触发 | last_record 没加 before_captured_at，查到本次自己 |
| launch_warning 不产生 | 只对 is_new=True 触发,重跑不重复;或 description 字段为空/batch 未传 description |
| `TypeError: naive vs aware datetime` | alert.py 的 lead_days 计算用 `datetime.utcnow()`(naive),ref_date 也转 naive 后再减 |
| 测试数据污染正式库 | config 只认 `OVERSEAS_DB_PATH`，不认 `COMPINTEL_DB`；测试用它 |
| PowerShell 数组变 System.Object[] | `--applicants $ARR` 传外部命令需用 `@()+ $ARR` 展开 |
| PowerShell `py -c` 嵌套引号失败 | 写到 .py 文件再执行,不要在 `-c` 里嵌复杂引号 |

---

## 已知边界（记缺口，别硬凑）

| 情况 | 处理 |
|---|---|
| EPREL 列表接口不可翻页 | from 参数实质无效(翻 10 页全相同),靠 scan_range 逐号扫描 |
| EPREL 列表返回最旧非最新 | 列表 25 条的 market_start 是 2019-2023(最旧),近期新品只能 scan 找 |
| EPREL 全量 37467+8424 条 | 不可一次拉全,step=1000 抽样约 8 分钟,step=1 全量约 12 小时 |
| EPREL 竞品近期记录少 | 6 家竞品 2023+ 上市的 EPREL 记录极少(注册非每新品都更新),FCC 是主预警源 |
| FCC 详情页 --details 较慢 | 每 ID +1 请求 +2s，500 ID ~17 分钟，放 weekly 层 |
| 接口限频严格 | 走 RateLimiter 别绕过；仍不行降频 |

参考实现：`overseas/compintel/fcc_crawler.py`、`eprel_crawler.py`、`alert.py`、`orchestrator.py`、`llm_analyze.py`。

---

## LLM 解读接入（聚好看内网接口）

### 关键决策：用海信内网聚好看接口，不走外网代理
聚好看接口是海信内网(`inner-apisix.hisense.com`)，DNS 在公司内网解析(10.19.64.234)。
**走外网代理(127.0.0.1:7877)时连接失败**——内网域名不能走外网代理。

### ⚠ 最大的坑：httpx2 的 trust_env 代理缓存（顺序问题）
现象：`call_llm` 恒返回空（降级到规则式摘要），手动调报
`httpx2.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]`，traceback 里出现 `httpcore2/_sync/http_proxy.py`。

**根因**：`httpx2`(2.13.0) 默认 `trust_env=True`，会读系统代理。而且——
**client 在构造时就缓存代理配置，事后改环境变量无效**。

**正确顺序（缺一不可）**：
```python
# ① 先改环境
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ[k] = ""
# 必须设 NO_PROXY（只清 HTTP_PROXY 不够！）
np = "inner-apisix.hisense.com,10.18.217.60,localhost,127.0.0.1"
os.environ["NO_PROXY"] = np
os.environ["no_proxy"] = np
# ② 再建 client（此时才读到无代理配置）
client = OpenAI(base_url=..., api_key=...)
# ③ 调完恢复环境
```
验证：`call_llm("回复四个字")` 应返回非空字符串；返回 `''` 即代理未绕过。
必须临时清空 `HTTP_PROXY/HTTPS_PROXY` 直连内网。

### 可用模型
| 模型 | base_url | 状态 |
|---|---|---|
| `deepseek-v4-flash` | `https://inner-apisix.hisense.com/higpt-new/v1` | ✅ 已验证可用 |
| `qwen3-5-397b` | 同上 | ✅ 同接口 |
| `deepseek-v3-jhk` | `https://inner-apisix.hisense.com/compatible-openai/v1` | ❌ No model permission |

### 接入方式
```python
from openai import OpenAI  # openai 库已装，兼容 OpenAI 接口
client = OpenAI(base_url="https://inner-apisix.hisense.com/higpt-new/v1",
                api_key="<api_key>")
# 关键：清空代理环境变量，否则走外网代理导致内网不可达
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"):
    os.environ.pop(k, None)
# 调用(内部用 stream=True，部分接口强制流式)
response = client.chat.completions.create(
    model="deepseek-v4-flash",
    messages=[{"role":"system","content":"..."},{"role":"user","content":"..."}],
    extra_query={"user_key": "<user_key>"},  # 聚好看需要 user_key
    stream=True)
```

### 三个分析功能（`llm_analyze.py`）
| 功能 | 函数 | 用途 |
|---|---|---|
| 单条解读 | `analyze_launch_warning(alert)` | 解读一条上市预警：产品品类推测 + 上市时间预测 + 行动建议 |
| 趋势简报 | `analyze_competitor_trend(alerts, brand)` | 按竞品汇总近期动态：品牌分组 + 类型分类 + 整体建议 |
| 批量解读 | `batch_analyze(alerts)` | 批量解读，每条加 llm_analysis 字段 |

### 优雅降级
LLM 调用失败时(内网不通/超时)，返回规则式摘要(不抛异常，不阻塞)：
```python
# LLM 失败时的降级摘要
f"[规则式摘要] {brand} 新{ptype} #{sid}，{desc}。认证日{auth_date}，提前{lead_days}天，{'尚未在售' if not on_market else '已上市'}。"
```

### CLI + 看板接入
```bash
# CLI 逐条解读
py -3.12 -m overseas.cli compintel-analyze --limit 5
# CLI 趋势简报
py -3.12 -m overseas.cli compintel-analyze --trend --limit 10
# 看板：点击"★ AI 趋势简报"按钮，调 /api/analyze?mode=trend
```

### 常见失败
| 症状 | 修法 |
|---|---|
| `Connection error` | 在走代理环境调用内网接口；清空 HTTP_PROXY/HTTPS_PROXY 直连 |
| `No model permission` | deepseek-v3-jhk 无权限，改用 deepseek-v4-flash |
| LLM 超时/空响应 | 降级为规则式摘要，不阻塞主流程 |

---

## 扩展数据源（ENERGY STAR / ANATEL / IC-ISED / TÜV+CB）

> 状态：✅ **固定程序已实现**（`overseas/compintel/`，2026-10-25）
> 数据源：ENERGY STAR（Socrata API）、ANATEL（ZIP-CSV）、IC/ISED（Spring WebFlow）、TÜV Rheinland（Certipedia）、VDE/CB（Solr）
> Schema v9：source CHECK 扩展为 `('fcc','eprel','energystar','ul','tuv','ic_ised','anatel')`

### 整体架构

```
orchestrator.py
  ├─ crawl_energystar()      → energystar_crawler.py
  ├─ crawl_anatel()          → anatel_crawler.py
  ├─ crawl_ic_ised()         → ic_ised_crawler.py
  ├─ crawl_certs()           → cert_crawler.py (TUV + VDE,复用 cert_verify 包)
  └─ crawl_all_extended()     → 一键全量
```

信号类型映射（`alert.py`）：`energystar/anatel/ic_ised/tuv/ul → new_cert`，`fcc → new_fcc_id`，`eprel → eprel_new_reg`。

### Schema v8→v9 迁移（SQLite CHECK 约束变更）

SQLite **不能 ALTER 列的 CHECK 约束**，必须重建表：

```python
def _migrate_compintel_source_check(self):
    # 1. 关外键
    PRAGMA foreign_keys=OFF
    # 2. RENAME 旧表
    ALTER TABLE compintel_record RENAME TO _old_record
    # 3. CREATE 新表(新 CHECK)
    # 4. INSERT ... SELECT 从旧表
    # 5. DROP 旧表
    # 6. 重建索引
    # 7. 开外键
    PRAGMA foreign_keys=ON
```

⚠ **add_record() 的 source_id 是位置参数**，记录 dict 里也有 `source_id` 键时，`**dict` 展开会冲突报 `multiple values for argument 'source_id'`。必须先 `sid = r.pop("source_id")` 再 `add_record(run_id, src, sid, **r)`。

### ENERGY STAR（Socrata SODA API）

| 要点 | 说明 |
|---|---|
| API | `data.energystar.gov/resource/8wj2-sec8.json`（Model Index 统一全 47 品类） |
| 认证 | 无需 API key |
| 过滤 | SoQL `$where=brand_name='Samsung'`，空格用 `urllib.parse.quote` 编码 |
| 分页 | `$limit=1000` + `$offset` |

⚠ **空结果陷阱**：品牌无结果时 Socrata 返回空数组 `[]`，httpx `res.ok=False`（被 blocked detector 误判为被封）。必须判 `res.status != 200` 而非 `res.ok`。

```python
# ❌ 错误：空结果 res.ok=False 会被 blocked detector 吞
if not res.ok: return "blocked"

# ✅ 正确：直接判 HTTP 状态码
if res.status != 200: return "fail"
```

### ANATEL（巴西 ZIP-CSV 下载）

| 要点 | 说明 |
|---|---|
| 数据源 | ANATEL 官方 ZIP-CSV（53MB，191K 行） |
| 编码 | **UTF-8-sig**（非 cp1252），BOM `ï»¿` 在 headers 中 |
| 分隔符 | 分号 `;`（非逗号） |
| 品牌匹配 | `Nome do Fabricante` 列，`BRAND_FABRICANTE_MAP` 关键词匹配 |

三个关键陷阱：

1. **二进制下载不能用 HttpFetcher**（`read()` 做 UTF-8 decode 损坏 ZIP），必须用 `urllib.request`：
```python
import urllib.request
urllib.request.urlretrieve(zip_url, local_path)  # 直接下载二进制
```

2. **CSV 编码是 UTF-8-sig 非 cp1252**：
```python
csv_text = zip.read(name).decode("utf-8-sig")  # 自动去 BOM
```

3. **csv.reader 对含换行的未引用字段报错**：
```python
import io
reader = csv.reader(io.StringIO(csv_text, newline=""), delimiter=";")
# 必须加 newline="" 参数
```

### IC/ISED（加拿大 Spring WebFlow 表单）

| 要点 | 说明 |
|---|---|
| 数据源 | `sms-sgs.ic.gc.ca` Spring WebFlow（urllib + CookieJar） |
| execution 字段 | `name="execution"`（**无下划线**，非 `name="_execution"`） |
| 提交按钮 | `_eventId_search=Search` |
| 结果页 | "Processing…please wait" + `setTimeout(refreshpage, 5000)`，需轮询 `_eventId_refresh=Refresh` |
| 结果表 | `id="equipmentSearchResultTable"`（非 companyResultTable） |

⚠ **ISED 严重 rate limit（HTTP 500）**：同 IP 连续请求（公司搜索后立即 REL 搜索）返回 500。解决：

1. **缓存公司号**：`ISED_COMPANY_NUMBERS` 字典存已知公司号（Samsung=649A/649B, LG=2703A/2703C），跳过 `search_companies`
2. **每 REL 新建 crawler 实例**：`_reset_session()` 清 cookie + 重建 opener
3. **15s 延迟**：每公司之间 `time.sleep(15)`

```python
# 结果表解析：公司分组行 + 表头行 + 数据行混合
# <tr><th colspan=7>649A - SAMSUNG ELECTRONICS</th></tr>  ← 公司分组
# <tr><th>HVIN</th>...</tr>                                ← 表头(含hvin,跳过)
# <tr><td>SP-R936</td><td></td>...<td>6496652A</td>...    ← 数据行6单元格
```

### TÜV Rheinland + VDE/CB（cert_verify 包复用）

| 要点 | 说明 |
|---|---|
| TÜV | Certipedia 搜索页返回 `quality_marks` 链接含 `certificate_number=` 参数（非 `/certificates/` 路径） |
| VDE | Solr 接口 `companyName` 字段返回 400，必须用 `companyName_en:*<name>*` 通配符 |
| 代理 | cert_verify 读 `CERT_PROXY`/`VDE_PROXY`（非 `OVERSEAS_PROXY`），orchestrator 用 `os.environ` 设置 |

两个关键优化：

1. **TÜV 批量提取**：逐证书查详情页 15s/张 × 50 = 12 分钟超时 → 改批量从搜索页提取所有证书号（1 次搜索）
2. **VDE 空格陷阱**：Solr q 参数含空格（Samsung Electronics）报 URL 控制字符错误或 400 → 取公司名首词即可（Samsung）

### CLI 命令

```bash
# 单数据源(必须传全 6 品牌)
py -3.12 -m overseas.cli compintel-energystar --brands Samsung,LG,Hisense,TCL,Sony,Panasonic
py -3.12 -m overseas.cli compintel-anatel --brands Samsung,LG,Hisense,TCL,Sony,Panasonic
py -3.12 -m overseas.cli compintel-ic-ised --brands Samsung,LG,Hisense,TCL,Sony,Panasonic
py -3.12 -m overseas.cli compintel-certs --brands Samsung,LG,Hisense,TCL,Sony,Panasonic

# EPREL 全量扫描(列表不可翻页,只能逐注册号 scan)
py -3.12 -m overseas.cli compintel-eprel-scan --brands Samsung,LG,Hisense,TCL,Sony,Panasonic --step 500

# 一键全量(所有新数据源)
py -3.12 -m overseas.cli compintel-run-extended --brands Samsung,LG,Hisense,TCL,Sony,Panasonic
py -3.12 -m overseas.cli compintel-run-extended --sources energystar,certs  # 指定源
```

### 全品牌覆盖矩阵（2026-10-25 更新）

| 数据源 | 国家 | Samsung | LG | Hisense | TCL | Sony | Panasonic | 合计 |
|---|---|---|---|---|---|---|---|---|
| FCC | 🇺🇸美国 | 93 | 72 | 28 | 64 | 27 | 26 | 310 |
| ENERGY STAR | 🇺🇸能效 | 208 | 317 | 28 | 23 | — | 9 | 585 |
| ANATEL | 🇧🇷巴西 | 1505 | 952 | 26 | 130 | 578 | 324 | 3515 |
| IC/ISED | 🇨🇦加拿大 | 22 | 16 | 1 | 1 | 38 | 8 | 86 |
| TÜV | 🇪🇺安全 | 24 | 11 | 19 | — | 24 | 14 | 92 |
| UL/CB | 🇪🇺CB | 50 | 20 | 1 | 11 | — | 50 | 132 |
| EPREL | 🇪🇺能效 | 待scan | | | | | | 0 |
| **合计** | | **1902** | **1388** | **103** | **229** | **667** | **431** | **4720** |

**正常缺口**（认证机构无对应品牌证书）：
- ENERGY STAR × Sony：Sony 在 TV/显示器类无 ENERGY STAR 认证
- TÜV × TCL：TCL 在 TÜV Rheinland 无安全认证
- UL/CB × Sony：Sony 在 VDE 无 CB 证书

### 全品牌覆盖踩坑

1. **ANATEL**：初版只跑 Samsung+LG。补齐需扩展 `BRAND_FABRICANTE_MAP` 关键词（Panasonic 加 `matsushita`/`sanyo`，LG 加 `lg electronics`/`lg innotek`/`lg do brasil`），CLI 传全 6 品牌
2. **IC/ISED**：每品牌需手动验证公司号并缓存到 `ISED_COMPANY_NUMBERS`（Hisense=11337A, TCL=11645A, Sony=4170B, Panasonic=216B），避免每次 `search_companies` 触发 500
3. **VDE/CB**：Solr 搜 LG 返回 50 条但 20 条是无关公司（Chemelex），orchestrator 入库前需过滤 `brand=""` 的记录
4. **EPREL**：`brand` 字段必须用 `_normalize_brand(rec.supplier_name)` 标准化，否则 Elo 等非竞品也入库

### 看板扩展

`dashboard.html` 新增：
- 信号类型下拉：`new_cert`（ENERGY STAR/ANATEL/ISED/UL/TÜV 合并）
- **数据源下拉**：按 FCC/EPREL/ENERGY STAR/ANATEL/ISED/TÜV/CB 筛选信号
- **数据源列**：国旗 emoji + 缩写（🇺🇸FCC/🇧🇷ANATEL/🇨🇦ISED/🇪🇺TÜV 等）
- 按 source 生成不同详情链接：FCC→fccid.io、IC/ISED→sms-sgs.ic.gc.ca、TÜV→certipedia、VDE→vde.com
- `stats()` 扩展：`source_counts`（各源唯一记录数）、`alerts_by_source`、`total_brands`
- `web_api.py` `/api/alerts` 路由：`last_record()` 按 alert 的 source 字段查对应源（不再硬编码 "fcc"）
