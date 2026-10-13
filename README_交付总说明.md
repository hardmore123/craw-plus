# 海外电视零售与 SPEC 爬取项目 · 交付总说明（2026-10-12）

本交付包是「海外电视」爬取项目当前可部署的完整快照：所有国家站点的 schema（RetailSpec）与 adapter、
全量抓取入口代码、探索/运维 skill（经验库）、已抓取的全部数据（已合并进唯一主库），以及部署所需的依附条件说明。

- `01_项目代码/` 是**可直接运行的完整项目**（含 git 历史，分支 `merge/haiwai-20261008`，提交 `5e1581d`），
  已带主库 `data/overseas.db` 和 41 国型号清单；代码里不再有写死的本机路径，放到任何目录都能跑。
- 项目历史上分在三处：`海外`（早期主线）、`海外电视爬取项目`（v3.0 打包版）、`海外数据爬取_部署包`（当前主线）。
  三处的差异已逐文件比对：可运行的增量（amazon_nl 完整适配器、TCP 报告生成器、skill 新案例与套路）已并入主线；
  compintel 竞品认证预警线也已并入主线（代码、命令、数据）；一次性工具归档在 `05_其它来源代码/`；所有文档归在 `06_文档/`。
- **不含**：浏览器登录目录（14GB，含个人会话）、DB 历史备份、缓存、旧版 zip 包。部署时按 §4 补齐。
- 「待完善 / 未实现」单独见 `04_待完善与未实现.md`，站点逐个状态见 `03_清单与报表/`。

---

## 1. 目录结构

```
交付包_海外电视_20261012/
├─ 快速启动.md                  ← 只看这一页就能装环境、跑全量、起两个下游应用
├─ README_交付总说明.md          ← 本文件（完整说明）
├─ 04_待完善与未实现.md          ← 缺口清单（按优先级）
├─ 01_项目代码/                  ← 可直接运行的项目根目录（= 部署包，含 .git 历史）
│  ├─ data/overseas.db           ★ 唯一主库（所有已抓数据 + 对阵分析表，见 §3）
│  ├─ data/<中文国名>/SPEC_型号汇总_<rc>_*.csv   41 国型号清单（全量入口默认从这里取型号）
│  ├─ overseas/                  核心包：抓取器/抽取器/存储/区域配置/各站 adapter
│  │  ├─ sites/<code>/adapter.py   283 个站点适配器（多数是「薄适配器」，字段由 spec 驱动）
│  │  ├─ sites/<code>/schema.json  旧六段式 schema（Amazon 等适配器路径仍在用，勿删）
│  │  ├─ regions_config.py + regions_auto.py   区域/国家 → 品牌、零售站注册
│  │  ├─ extract.py / retail_spec.py / mx_retail.py   spec 执行端
│  │  ├─ bv_reviews.py / mms_reviews.py              接口型评价采集（BazaarVoice / MediaMarkt 集团）
│  │  └─ storage.py / config.py / infra.py / fetchers.py
│  ├─ schemas/
│  │  ├─ retail_specs/<code>.retail.json   ★ 259 份，每站唯一权威 spec
│  │  └─ retail_allowlist.json             合规白名单（143 个 host）
│  ├─ scripts/                   全量入口、检验、修复、合并、导出脚本（见 §5、§6）
│  ├─ .kiro/skills/overseas-schema-gen/   ★ 探索经验库 skill（见 §7）
│  ├─ docs/                      历史技术方案、规范、交接文档（30 余份）
│  ├─ CRAWL_CONFIG.json          全量抓取硬编码配置导出
│  ├─ requirements.txt / pyproject.toml
│  └─ DEPLOY.md / README.md / CHANGELOG.md / MASTER_INVENTORY.md
├─ 02_数据/
│  ├─ db/overseas.db             唯一主库的副本（与 01_项目代码/data/overseas.db 同一份；程序实际读后者）
│  ├─ 按国家导出_主库/<国家>/     由主库导出：价格最新.csv / 价格历史.csv / 评价明细.csv / 评分汇总.csv
│  ├─ 按国家导出/<中文国家名>/    抓取当次产出的 CSV（价格监控_/网评汇总_）
│  ├─ 历史导出_海外线/            早期主线的最终版导出：全量导出_改进版_20260928、日本线导出、北美在售全量、各品牌 SPEC 表、网站汇总表
│  └─ spec_exports/              品牌官网 SPEC 表导出（xlsx/csv）
└─ 03_清单与报表/
   ├─ spec_adapter_清单.csv      259 份 spec：区域/币种/能力/评价源/价格可疑/封锁标记
   ├─ readiness最新.csv          最近一轮小样实测判定（READY/PARTIAL/FAIL/NO_SAMPLE）
   ├─ 数据覆盖_按国家.md          主库按国家统计
│  ├─ 逐站状态.md               259 份 spec 逐站：能力 / 实测判定 / 缺口原文 / 备注
│  └─ MMS集团实测.log            MediaMarkt/Saturn 各国站实测日志
├─ 07_竞品对阵分析/              下游应用一的代码副本 + `交接说明.md`（运行仍用 01_项目代码；见 §3.4）
├─ 08_竞品认证预警_compintel/    下游应用二的代码副本 + `交接说明.md` + compintel 专题文档
├─ 09_参考网站与完成度/          站点清单(含网址)、各版进度表、逐站实测状态、按国家覆盖 + `交接说明.md`
├─ 05_其它来源代码/              非主线代码归档（不参与全量运行）
│  ├─ 海外_工具脚本/              进度矩阵、台账扫描、站点汇总合并、schema 盘点等一次性工具
│  ├─ 工作区根目录_连通性与站点探测/  代理/TLS/站点连通性探测脚本与结果（.mjs/.ps1/.json）
│  └─ 51服务器部署辅助/           SSH 辅助脚本（凭据已改为环境变量 DEPLOY_SSH_*）
└─ 06_文档/                      全部文档（00_文档索引.md 有分类说明）
   ├─ 交接文档/  海外_历史报告与日志/  海外电视项目_增量报告/  海外电视项目_调研报告/
   ├─ 进度表/  Kiro_spec_墨西哥电视线/  代码评审记录/  部署包专题/  工作区根目录文档/
   └─ （技术方案与规范在 01_项目代码/docs/，随代码走）
```

## 2. 项目在做什么

两条数据线，共用一套引擎：

| 线 | 数据 | 来源 | 入口 |
|---|---|---|---|
| 零售线 | 每个型号在各国零售站的**价格**（含原价/库存）与**用户评价**（明细+评分汇总） | 各国电商/零售站 | `scripts/crawl_ca_retail.py` |
| SPEC 线 | 品牌官网的**规格表**（按系列×机型×项目） | 海信/TCL/三星/LG/索尼/飞利浦等官网 | `python -m overseas.cli spec-crawl` |
| 日本线 | kakaku.com 多店铺价格 + 口碑 | kakaku | `scripts/crawl_kakaku_prices.py` / `crawl_kakaku_reviews.py` |

### 2.1 主流程：agent 探索 → skill 积累经验 → 产出 schema/adapter → 硬编码全量

```
 ① agent 探索（Kiro + skill）            ② 产物（纯配置/薄代码）              ③ 硬编码全量（无 LLM）
 ─────────────────────────────          ───────────────────────────          ──────────────────────────
 激活 .kiro/skills/overseas-schema-gen   schemas/retail_specs/<code>.json     scripts/crawl_ca_retail.py
   retail/ 零售站  spec/ 品牌官网          overseas/sites/<code>/adapter.py      python -m overseas.cli spec-crawl
   media/ 评测站   ops/ 运维               （多数是薄适配器，字段由 spec 驱动）     scripts/crawl_kakaku_*.py
 读 reference.md / playbook / cases     ──►  gen_regions_from_specs.py 注册 ──►   读 spec 执行：搜索→匹配→详情→
 probe.py 实测 → 生成 spec 草稿              selfcheck.py / 静态门禁                价格/评价→写主库 data/overseas.db
 readiness_check 小样验证                     readiness 达 READY                    按国家导出 CSV
        ▲                                                                            │
        └──────── 新教训写回 cases.jsonl / reference.md（成功失败都记） ◄────────────┘
                   全量中暴露的问题（被拦、匹配错、错价）回到 ① 修 spec
```

- **探索阶段**才用 agent/LLM：看页面、找搜索入口、定选择器、找评价接口、判断反爬。经验沉淀进 skill，
  下一个同平台站直接套用（例：MediaMarkt 只实测 1 站，规则批量落到 11 国）。
- **全量阶段**只跑代码：同一份 spec 每周/每天重复执行，不依赖 LLM，结果可复现。
- skill 怎么用见 §7；全量命令见 §5；新站接入后的验收见 §6。

设计原则：
- **探索用 skill，全量用硬编码**：新站由 agent 借 skill 探索，产出 `schemas/retail_specs/<code>.retail.json`
  （+ 必要时一个薄 adapter）；全量抓取完全由代码按 spec 执行，不再需要 LLM。
- **一站一份 spec**：`schemas/retail_specs` 是唯一权威；`crawl_ca_retail` 自动加载。
- **红线**：型号匹配宁缺毋滥（`match.on_no_match` 必须 `skip`，负样本必须判不存在）；价格「缺价 > 错价」。

## 3. 数据：唯一主库 `01_项目代码/data/overseas.db`

SQLite 单文件（约 135MB），路径由 `OVERSEAS_DB_PATH` 覆盖，默认 `<项目>/data/overseas.db`。

### 3.1 2026-10-12 合并
项目历史上数据散落在 40 多个库里（`data/na|sa|eu|japan|asia/*.db`、`data/national_db/<国家>/*.db`、
`海外/overseas_v4_20260929.db`、`海外/data/mx/overseas_mx.db`、`data/sandbox/readiness.db` 等）。
已用 `scripts/consolidate_db.py` 全部并入主库，规则：
- 只增不改：已有行不覆盖，只补空字段（品牌/型号/尺寸/标题/URL）。
- 去重键：商品 `(站点, sku)`；价格 `(商品, 时间, 价格)`；评价 `(商品, review_key)`；SPEC 行 `(系列, 项目, 区分, 周)`。
- 与 10-05 主库清洗同口径：配件/非电视标题、无型号且无价的商品不带回；0 价/坏值不带回；
  与主库同商品已有价中位数偏离 3 倍以上的价视为旧库残留错价，不带回（共拦 5300 余条，主要是南美库欧式小数误解析）。
- 合并前自动备份：`data/overseas_before_consolidate_20261012_223848.bak`（在部署包里，未放进本交付包）。

| 表 | 合并前 | 合并后 | 净增 |
|---|---|---|---|
| product 商品 | 14,228 | 14,643 | +415 |
| price_snapshot 价格快照 | 13,357 | 15,894 | +2,537 |
| review 评价明细 | 83,923 | 95,207 | +11,284 |
| review_summary 评分汇总 | 3,519 | 3,965 | +446 |
| product_spec 商品规格 | 137,114 | 138,069 | +955 |
| spec_series / spec_row 官网 SPEC | 1,091 / 175,655 | 1,098 / 179,249 | +7 / +3,594 |

合并后 `pragma integrity_check = ok`。`foreign_key_check` 有 58 条，全部在运行日志表 `retail_task_status`
（引用已清理的商品/运行记录），合并前就存在，不影响业务表。

另用 `scripts/import_benchmark_tables.py` 把竞品对阵分析线的 6 张表从 `海外/overseas_v4_20260929.db` 整表导入
（这些表只互相引用，不依赖 product/spec_series 的 id）：`dim_spec_parameter` 18、`dim_product_model` 6,493、
`dim_spec_item_map` 1,974、`dim_spec_normalization_map` 9、`fact_spec_value` 52,636、`fact_benchmark_comparison` 4。
对阵分析服务（`启动竞品对阵分析.bat` / `run_benchmark_server.py`）和维护脚本现在都读写主库。

再用 `scripts/import_compintel_data.py` 把 compintel 数据从 `海外/data/overseas.db` 并入（主库 schema 随之升到 v9）：
`compintel_record` 851、`compintel_alert` 980、`compintel_crawl_state` 85。合并后主库 35 张表，是目前**最全**的一份：已逐库比对 `海外数据爬取_部署包`、`海外`、`海外电视爬取项目` 下全部 .db，除备份表 `dim_product_model_bak` 外，没有哪张表只存在于别的库里。

### 3.2 覆盖面
158 个站有数据，覆盖 39 个国家；有价商品 11,134 个；评价 95,207 条；官网 SPEC 39 个品牌 1,098 个系列。
按国家明细见 `03_清单与报表/数据覆盖_按国家.md`。

### 3.3 结构文档
- **`01_项目代码/docs/数据库结构说明.md`**：表族与业务线、写入方/读取方、ER 图、无外键的值关联、**使用误区（7 类 36 条，均为库里实测）**、常用查询。
- **`01_项目代码/docs/数据库表结构明细.md`**：35 张表逐列（类型/非空/主键/默认/注释）、外键、索引、CHECK、行数。改表后 `py -3.12 scripts\gen_db_doc.py` 重新生成。

### 3.4 基于本库的两个下游应用
| 应用 | 用到的表 | 启动 | 说明 |
|---|---|---|---|
| 竞品对阵分析 | dim_* / fact_* + product / price_snapshot / spec_row / product_spec / review / media_review | `启动竞品对阵分析.bat` 或 `py -3.12 run_benchmark_server.py`（http://127.0.0.1:8090）；维护映射 `py -3.12 maintain_benchmark_tables.py`；TCP 报告 `python -m overseas.report.generate_tcp_report --hisense <型号> --competitor <型号>` | 10-12 实测 `/api/health`、`/api/countries`、`/api/sizes` 均 200。AI 解读依赖本地 xinghai 转换代理 `http://127.0.0.1:8082/v1`（不开也能看规格对比，AI 按钮不可用）。报告参照模板在 `06_文档/TCP报告参考模板/` |
| 竞品认证预警 compintel | compintel_record / alert / crawl_state / doc / skip | `py -3.12 -m overseas.cli compintel-run-extended`、`compintel-fcc-full --brands ...`、`compintel-alert`；看板 `compintel-web`（8088）；定时 `scripts\compintel_daily.ps1`（`compintel_install_task.ps1` 注册） | 10-12 实测 `compintel-stats`：FCC 310、EPREL 53、信号 980。LLM 解读用聚好看内网接口，需内网 + `COMPINTEL_LLM_API_KEY`/`COMPINTEL_LLM_USER_KEY` 变量。说明见 `docs/compintel_交付说明.md` |

> 两个应用与爬虫主程序是**同一个 Python 包**（都在 `overseas/` 下，共用 `overseas/db.py` 和同一个主库），
> **运行用 `01_项目代码/`**（自带主库和依赖）。为便于单独交接，各自的文件又复制了一份到独立文件夹：
> **`07_竞品对阵分析/`** 和 **`08_竞品认证预警_compintel/`**，每个带 `交接说明.md`（功能、文件清单、数据来源网址、启动、完成度、待完善）。
> 这两个副本不能脱离主包单独 `python` 运行（缺 `overseas/db.py` 等基础模块），只作查阅与交接。
> 参考网站清单（260 站网址）与完成度表在 **`09_参考网站与完成度/`**。下面也列出各自的全部文件，交接时按此核对。

**竞品对阵分析——文件清单（全部在 `01_项目代码/`）**
- 启动：`run_benchmark_server.py`、`启动竞品对阵分析.bat`（Windows 双击）
- 后端：`overseas/benchmark_server.py`（HTTP 服务 + 全部 `/api/*` 路由，端口 8090）
- 前端：`overseas/benchmark_static/index.html`、`overseas/benchmark_static/echarts.min.js`
- 维护：`maintain_benchmark_tables.py`（原始数据 → dim_*/fact_* 映射重算）、`overseas/backfill.py`（规格回溯补全）
- 报告：`overseas/report/generate_tcp_report.py`、`overseas/report/generate_report.py`、`overseas/report/__init__.py`
- 数据：主库 `data/overseas.db` 的 `dim_product_model`、`dim_spec_parameter`、`dim_spec_item_map`、
  `dim_spec_normalization_map`、`fact_spec_value`、`fact_benchmark_comparison` + 零售/SPEC/评价/媒体表
- 一键验证：`py -3.12 run_benchmark_server.py` 后浏览器开 http://127.0.0.1:8090

**竞品认证预警 compintel——文件清单（全部在 `01_项目代码/`）**
- 包目录 `overseas/compintel/`：`__init__.py`、`orchestrator.py`（总调度）、`compintel_db.py`（落库）、
  `fcc_crawler.py`、`eprel_crawler.py`、`energystar_crawler.py`、`anatel_crawler.py`、`ic_ised_crawler.py`、
  `cert_crawler.py`（TÜV/VDE）、`alert.py`（信号）、`llm_analyze.py`（内网 LLM 解读）、
  `web_api.py` + `dashboard.html`（看板，端口 8088）
- 命令：`overseas/cli.py` 的 `compintel-fcc / fcc-full / eprel / eprel-scan / eprel-supplier / alert / analyze /
  stats / states / search / run / run-extended / energystar / anatel / ic-ised / certs / web`
- 定时：`scripts/compintel_daily.ps1`、`compintel_weekly.ps1`、`compintel_install_task.ps1`
- 数据与建表/迁移：主库 `compintel_*` 表；建表在 `overseas/schema.sql`，v8→v9 迁移在 `overseas/db.py`
- 文档：`docs/compintel_交付说明.md`、`docs/compintel_定时预警方案.md`
- 一键验证：`py -3.12 -m overseas.cli compintel-stats`

### 3.5 主要表
| 表 | 含义 |
|---|---|
| site | 站点（code 唯一，如 `amazon_ca`） |
| product | 商品，`(site_id, sku)` 唯一；`model` 为厂商型号，跨站比价用 |
| price_snapshot | 价格时序（只增），price/list_price/currency/in_stock |
| price_shop_snapshot | 聚合站（kakaku）各店铺价格 |
| review / review_summary | 评价明细（review_key 增量去重，含图片/视频 URL）/ 评分汇总（星级分布） |
| spec_series / spec_row | 官网 SPEC：系列 → 行（`values_json` 为 {机型: 值}，按 ISO 周） |
| product_spec | 零售站详情页上的规格键值 |
| media_review | 媒体评测站文章 |
| crawl_run / crawl_error / retail_task_status | 运行日志、错误、型号级任务状态 |
| dim_* / fact_* | 对阵分析：归一化机型、规格参数字典、术语映射、参数取值、对阵结论 |
| compintel_* | 竞品认证预警：认证/能效注册快照、预警信号、增量断点 |

重新导出按国家 CSV：`py -3.12 scripts/export_by_country.py --out <目录>`。

## 4. 依附条件（部署前必须满足）

### 4.1 运行环境
| 项 | 要求 | 说明 |
|---|---|---|
| 操作系统 | Windows 10/11（已验证）；Linux 可用 | Linux 需离线 Chrome + 系统库，见 4.2 |
| Python | **3.12**（Windows 用 `py -3.12`） | 核心代码只用标准库 + 下列可选包 |
| playwright | `>=1.49.0`，只装 Python 包 | **不需要** `playwright install`：Windows 直接用系统 Edge |
| openpyxl | `3.1.5` | 导出 xlsx 时需要 |
| argostranslate | `1.11.0`（可选） | 日文 SPEC 离线翻译；另需 `scripts/install_argos_models.py` 下模型 |
| 浏览器 | Microsoft Edge / Chrome | 通道顺序 `OVERSEAS_BROWSER_CHANNELS=msedge,chrome,chromium` |
| 内存 | 建议 ≥16GB；8GB 可跑但需关掉其它大程序 | 剩余 < `OVERSEAS_MIN_FREE_MB`(默认 800MB) 时检验脚本会等待；不足时浏览器崩溃（TargetClosedError） |
| 磁盘 | ≥10GB 可用 | 主库 ~135MB；浏览器 profile 会长到 10GB+；每次批量建议先备份库 |

安装：
```powershell
cd 01_项目代码
py -3.12 -m pip install -r requirements.txt
py -3.12 -m overseas.cli config        # 打印生效配置，确认 DB 路径/浏览器通道/代理
git log --oneline -5                   # 改动历史可追溯
```
主库与型号清单已在 `data/` 下，不用另拷。若要把库放到别处，设 `OVERSEAS_DB_PATH`（所有脚本都认这个变量）。
`.gitignore` 忽略了 `data/`，主库不进 git；改动代码/spec 用 git 管，数据靠 DB 备份。

```powershell
# 三条自检，全过即环境就绪（不联网）
py -3.12 .kiro\skills\overseas-schema-gen\retail\selfcheck.py
py -3.12 .kiro\skills\overseas-schema-gen\spec\selfcheck.py
py -3.12 scripts\retail_spec_tests.py
```

### 4.2 Linux 服务器
- `pip install playwright` 后，解压 `chrome-linux64.zip`，设 `OVERSEAS_BROWSER_EXECUTABLE=/path/chrome`。
- 缺系统库：`sudo python -m playwright install-deps chromium`。
- 已有部署参考：`51服务器开机自启服务汇总_已部署核实版.md`（工作区根目录）与 `01_项目代码/deploy/`、`DEPLOY.md`。

### 4.3 网络出口（决定能抓到哪些站，最关键）
- **必须走代理**：设 `OVERSEAS_PROXY=http://127.0.0.1:7877`（本机 Clash），并设 `OVERSEAS_PROXY_REQUIRED=1`：
  代理不可用时直接停止，绝不回落直连（防止用公司出口 IP 撞站被封）。`OVERSEAS_PROXY_WAIT` 设等待代理恢复的秒数。
- 出口国家决定可达站点：
  - 当前常用美国节点（LA / Sharktech 机房 IP）：北美、南美大部分、欧洲约一半站可达。
  - 英国节点「UK - 英国 02」：另有 10 个站只在英国出口可达（见 04 文档 §2）。
  - 约 21 个站对机房 IP 一律 403/验证码（Akamai/PerimeterX/Cloudflare 等），**需要目标国住宅 IP**。
  - 俄罗斯站全部需要俄罗斯 IP。
- Clash 没有开机自启，部署机重启后必须先手动开 Clash，否则 `PROXY_REQUIRED` 会让任务全部停住。
- 同一出口下反爬是间歇的（同站时 200 时 403），单次 403 不代表 spec 坏了。

### 4.4 登录态（Amazon 系）
- Amazon 各站（us/ca/mx/uk/de/fr/it/es）评价页需要登录态，用持久化浏览器目录：
  `OVERSEAS_USE_PROFILE=1`，`OVERSEAS_PROFILE_DIR`（默认 `data/browser_profile`）。
- 新机器需重新登录一次：`py -3.12 -m overseas.cli login --site amazon_us`（会打开有头浏览器，人工登录），
  `login-status` 查看。登录目录**未放进交付包**（14GB，且含个人会话）。
- Amazon 欧洲站需邮编定位（代码已内置 Playwright 原生 API 输入邮编）。

### 4.5 其它
- 型号清单：零售线按 `data/<区域中文名>/SPEC_型号汇总_<rc>_*.csv`（由 SPEC 线产出）取型号；
  欧洲各国用「欧洲那一份 SPEC」（同品牌各 EU 国官网型号并集），北美/南美各国只用本国 SPEC。
  缺清单时用 `--models` 直接给型号，或先跑 `scripts/export_region_models.py`。
- 可选 LLM / 翻译服务凭据只走环境变量（`OVERSEAS_LLM_*`、`OVERSEAS_TRANSLATE_*`、`OVERSEAS_XINGHAI_*`），不写进文件。
- 计划任务 `OverseasBatchWatchdog`（每小时唤醒跑检验队列）在当前机器上已注册 14 天；新机器如需要，
  按 `scripts/batch_watchdog.py` 注释注册；不需要时 `schtasks /Delete /TN OverseasBatchWatchdog /F`。

## 5. 全量抓取怎么跑（硬编码入口）

所有命令在 `01_项目代码/` 下执行，先设环境：
```powershell
$env:PYTHONIOENCODING="utf-8"
$env:OVERSEAS_PROXY="http://127.0.0.1:7877"
$env:OVERSEAS_PROXY_REQUIRED="1"
```

### 5.1 零售线（价格 + 评价）
```powershell
# 一个区域全部启用的零售站，型号取该区域默认 SPEC 型号清单，写主库
py -3.12 scripts\crawl_ca_retail.py --region de --save-db
# 指定站 / 品牌 / 型号
py -3.12 scripts\crawl_ca_retail.py --region nl --sites mediamarkt_nl --brand samsung --models UE43U8000H QE65QN74FATXXN --save-db
```
- `--region` 用站点自己的区域码（`mediamarkt_nl` 是 `nl`）；区域与站的对应在 `overseas/regions_auto.py`
  （由 `scripts/gen_regions_from_specs.py` 从 spec 生成，改了 spec 的 region 要重跑）。
- 每站自动加载 `schemas/retail_specs/<code>.retail.json`；`--spec` 只能配单个 `--sites`。
- 搜索入口优先级：`search.api`（VTEX 接口）→ `search.search_url_template` → 适配器 `search_url`。
- 品牌级候选池：先搜「品牌 tv」建池，型号在池内匹配；池外型号是否逐型号回退由 spec `search.batch.fallback_per_model` 决定。
- 评价上限：CLI `--max-reviews` > spec `paginate.reviews.max_reviews` > 环境变量 `OVERSEAS_MAX_REVIEWS` > 默认 50。
- 输出：主库 + `data/<国家中文名>/价格监控_<国家>_<日期>.csv`、`网评汇总_<国家>_<日期>.csv`。
- 站级熔断：连续 5 个型号被拦截即跳过该站；品牌搜索拿不到候选记 `failed`（不会误记成「不存在」）。
- 标 `_price_suspect` 的站（当前 max_gt、tecnofacil_gt、mediaexpert_pl）全量时不写价格。

### 5.2 Amazon 三站接力（US → MX → CA）
`pythonw scripts\supervisor_amazon_full.py`：断点续抓、失败重试、完成后重建 CSV（`scripts/rebuild_amazon_csvs.py`）。
- 路径按项目根推导，三站都写主库（10-12 改；原先写死 `海外` 目录、墨西哥写独立库）。
- 型号清单自动取 `data/<美国|墨西哥|加拿大>/SPEC_型号汇总_<rc>_*.csv` 最新一份。
- 前提：已完成 §4.4 的 Amazon 登录；`watchdog_rebuild_amazon_full.py` 里 `WATCH_PIDS` 是要盯的 supervisor 进程号，用前改成实际值。
- 其它国家 Amazon（uk/de/fr/it/es/nl…）直接用 `crawl_ca_retail.py --region <rc> --sites amazon_<rc>`。

### 5.3 SPEC 线（官网规格）
```powershell
py -3.12 -m overseas.cli spec-crawl --site hisense_jp     # 单品牌站
py -3.12 -m overseas.cli spec-export --site hisense_jp    # 导出 xlsx
```
SPEC 站的 AdapterSpec 在各 `overseas/sites/<brand>_<cc>/`；新品牌用 `spec-onboard` + skill 的 spec 分支。

### 5.4 日本线（kakaku）
`py -3.12 scripts\crawl_kakaku_prices.py` / `scripts\crawl_kakaku_reviews.py`；周任务模板 `deploy/kakaku_weekly_task.xml`。

### 5.5 抓完之后
```powershell
py -3.12 scripts\consolidate_db.py --dry-run     # 若有写到别的库的批次，先看能并入多少
py -3.12 scripts\consolidate_db.py --src <库>    # 自动备份后并入主库
py -3.12 scripts\export_by_country.py            # 按国家导出 CSV
```

## 6. 上线前检验（每次改 spec 或换出口后跑）

| 步骤 | 命令 | 判定 |
|---|---|---|
| spec 静态自检 | `py -3.12 .kiro\skills\overseas-schema-gen\retail\selfcheck.py` | 259 份全 PASS |
| 静态门禁 G1–G10 | `py -3.12 scripts\full_readiness_static.py` | 区域注册/白名单/搜索入口/评价源齐全 |
| 小样实测 | `py -3.12 scripts\readiness_check.py --sites <code...>` 或 `--region <rc>` | 2 正样本 + 负样本 `ZQ99X7NOEXIST`；写 `data/sandbox/readiness.db`，不碰主库 |
| 失败归因 | `py -3.12 scripts\classify_failures.py --since <日期>` | 被拦 / 候选为 0 / 匹配不上 / 缺价 / 缺评价 |
| 自动修搜索 | `py -3.12 scripts\autofix_search.py --sites <code...>` | 只有真实型号全链通过才写回 spec |
| 单站诊断 | `scripts\diag_site_model.py`、`scripts\dump_page.py` | 人工看 DOM / 接口 |
| 汇总 | `py -3.12 scripts\overall_status.py` | 每站最新判定 |

判定口径：READY = 正样本全中且有价、负样本判不存在、声明评价的站至少一个正样本有评价；
PARTIAL = 部分达标；FAIL = 被拦/搜索失败/负样本误中；NO_SAMPLE = 主库没有该站正样本可测。

## 7. 经验库 skill：`.kiro/skills/overseas-schema-gen/`

接新站、诊断「抓不全/匹配不到/价格不对」、全量运维都从这里进。Kiro 里说「接入新站 xxx」「诊断 xxx」会自动激活。

| 分支 | 文件 | 内容 |
|---|---|---|
| 总入口 | `SKILL.md` | 分支委派、路径、命令 |
| retail 零售 | `retail/SKILL.md`、`reference.md`（28 节判断经验）、`cases.jsonl`（每站一条成败案例）、`playbook/*.md`（12 种套路：VTEX 接口、第三方评价 API、sitemap 发现、单结果直达详情页、系列名列表页等）、`probe.py`、`selfcheck.py` | RetailSpec 生成与修复 |
| spec 官网 | `spec/…`（7 种套路：内嵌 JSON、懒加载、多级、数字分页、XHR 接口等） | AdapterSpec 生成 |
| media 媒体 | `media/…` | 评测站 JSON-LD |
| ops 运维 | `ops/crawl-ops.md`、`ops/cases.jsonl` | 长时爬取、反爬、代理、检验流水线 |

本轮（10-08 ~ 10-12）新沉淀：
- `retail/reference.md §28`：MediaMarkt/Saturn/MediaWorld 同平台 11 国站共享规则；JSON-LD `ProductGroup/hasVariant`
  按 canonical 选尺寸变体（修串尺寸价）；`jsonld_first`（DOM 首价是套餐价）；站方 GraphQL + WAF 时「点 UI 截获而非重放」。
- `retail/cases.jsonl`：`mediamarkt_saturn_mms_group` 案例。
- `ops/crawl-ops.md`「全量就绪检验与修复流水线」：唯一 spec 原则、搜索入口优先级、URL 只比 path + 负样本、
  价格红线与 price_sanity、检验工具链、环境稳定性（代理强制、ENV_ERROR、内存门限、间歇反爬、PowerShell 坑）。
- `ops/cases.jsonl`：`readiness_pipeline_20261012`。

接新站流程（简版）：skill 探索 → 产出 `schemas/retail_specs/<code>.retail.json`（必要时薄 adapter）→
`gen_regions_from_specs.py` 注册区域与白名单 → `selfcheck.py` → `readiness_check.py --sites <code>` 达 READY →
追加 `cases.jsonl` → git 提交。

## 8. 当前完成度（截至 2026-10-12）

| 维度 | 数量 |
|---|---|
| 站点适配器 | 283 |
| RetailSpec | 259（价格 179 / 价格+评价 56 / 仅 SPEC 21 / 仅评价 1 / 空 2），全部过静态自检 |
| 静态门禁 | 范围内 124 站，120 站通过 |
| 小样实测有记录 | 124 站：READY 27 / PARTIAL 31 / FAIL 51 / NO_SAMPLE 15 |
| MediaMarkt 集团（10-11 手修后） | 9 站（at/ch/de/es/hu/it/nl/pl/tr）价格+评价链路实测通；be/saturn_de 美国出口 403 |

READY（27）：
- 美洲 23：amazon_us artefacta_ec comandato_ec credivargas_pe cresa_ec cresa_ec_more elektra_gt estilos_pe
  falabella_pe hisense_co jumbo_co laganga_ec2 leons_ca lg_ec marcimex_ec metro_pe multimax_pa orvehogar_ec
  panafoto_pa plazavea_pe rodelag_pa tcl_cl thebrick_ca
- 欧洲 4：jlp_uk klick_ee digitec_ch ldlc_fr

MediaMarkt 集团实测样例（10-12，美国出口）：DE GU55M70H 479€ / GU65M70H 629€，51/51 条评价；
NL UE43U8000H 399€ / QE65QN74FATXXN 999€；HU 139,899 / 169,899 Ft；TR 45,199 / 56,599 TL；
PL QE55QN77FAT 3,299 zł（修 jsonld_first 前误抓 3,899 套餐价）。这批站的 readiness CSV 判定是修复前的旧结果，需重跑刷新。

PARTIAL/FAIL 的逐站原因与修复方向见 `04_待完善与未实现.md`；每站最新一行见 `03_清单与报表/readiness最新.csv`。

## 9. 关键文档索引（`01_项目代码/docs/`）
- `RetailSpec_schema规范.md`、`AdapterSpec_schema规范.md`：spec 字段规范与白名单。
- `零售线多国自动适配技术方案.md`、`跨国家线复用与开发指南.md`：架构与复用方式。
- `接入住宅IP后的下一步工作说明.md`：换住宅 IP 后先跑哪些站。
- `北美零售站反爬分类_2026-09-20.md`、`Costco_CA_US_抓取可行性报告_2026-09-20.md`、`BestBuy*`：难站专项。
- `交接文档_亚马逊三站全量抓取_20260920.md`：Amazon 全量。
- `项目总说明.md`、`部署说明.md`、`接口说明.md`（API 服务 `deploy/overseas-api.service`）。

## 10. 交接包是怎么生成的 / 如何更新

- 可运行项目：`py -3.12 scripts\build_handoff.py --dst <交接包>\01_项目代码`（拷代码、skill、docs、.git、主库、型号清单）。
- 数据合并：`scripts\consolidate_db.py`（各分区/旧库 → 主库）、`scripts\import_benchmark_tables.py`（对阵分析表）。
- 按国家导出：`scripts\export_by_country.py --out <交接包>\02_数据\按国家导出_主库`。
- 三处来源的比对结论（10-12）：
  - `海外数据爬取_部署包` 为主线（259 spec / 283 adapter）。
  - `海外电视爬取项目/主程序`：除 `amazon_nl` 适配器与 `overseas/report/generate_tcp_report.py` 较新（已并入）外，其余是主线的旧版本。
  - `海外`：较新的是 skill 的 spec 案例/compintel 一节，以及 compintel 线（代码 + `cli.py` 子命令 + `db.py` v8→v9 迁移 + `schema.sql` 表）。
    10-12 已全部并入主线：先在主库副本上验证迁移（业务表行数不变、integrity ok），再升级真库并导入 compintel 数据
    （`scripts/import_compintel_data.py`）。`docs/retail_specs` 是已废弃的 spec 副本，未收。
  - 数据文件：`海外` 根目录 9-28 有 8 个「全量导出_*」迭代版，只收最后的「改进版」；其余为中间版，内容已在主库。
    `海外/data/_sitemap/bestbuy_ca/products.csv`（620MB，BestBuy CA 全站全品类 sitemap 清单，可由 sitemap 脚本重新生成）未收。
- 明文凭据处理：工作日志里的 LLM API Key 已打码；SSH 辅助脚本改为读 `DEPLOY_SSH_HOST/USER/PASS` 环境变量。
  compintel 的聚好看内网 LLM 接口凭据原先明文写在 `overseas/compintel/llm_analyze.py`，已改为环境变量
  `COMPINTEL_LLM_API_KEY` / `COMPINTEL_LLM_USER_KEY`（`COMPINTEL_LLM_BASE_URL` 可选）。
  **必须轮换**这三处凭据（LLM API Key、51 服务器口令、聚好看接口 Key）。聚好看 Key 仍在 git 提交 `ace365d` 与 `海外` 目录历史中；它们此前以明文存在于多个目录和旧 zip 包里，且该 API Key 仍在 `01_项目代码/.git`
  历史的基线提交 `1218a11` 中（未改写 git 历史）。若交接对象不应看到，先轮换 Key，或删掉 `.git` 后再交付。
