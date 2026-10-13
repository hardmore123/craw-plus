# 海外数据爬取 · 整合部署包 v2.0

> ⚠️ **本文件为 v2.0 历史版本（2026-09-23），数字与路径已过时**。
> 当前权威说明请读上一层目录的 **`../README_交付总说明.md`** 与 **`../快速启动.md`**。
> 本 README 描述的是「80 站点 / 21 表 / 20MB 库」的早期状态，引用的 `STATUS.md`、`MANIFEST.txt`、
> `SELFCHECK.py`、`docs/retail_specs/`、`backup_code/`、`data/mx/overseas_mx.db`、`data/db/backup/`
> 等文件**在本包中已不存在**。当前实际规模：283 适配器 / 259 RetailSpec / 35 表 / 142MB 主库，
> 详见 `../README_交付总说明.md`。本文件保留仅为追溯历史架构思路（§2~§7 的设计说明仍大体适用）。
> 数据库结构以 `docs/数据库结构说明.md` + `docs/数据库表结构明细.md` 为准。

> 生成日期：2026-09-23 · 825 个文件 / 62.3 MB · 单文件夹自包含，可直接部署

本包是「海外电商数据采集」项目的**唯一权威副本**。所有文件均为当前最新且已验证可用的版本：
每条业务线的代码、契约（schema）、适配器（adapter）、技能（skill）、监视器（monitor）、
数据库（database）都在这里，不存在「包外还有一版更新的」情况。

---

## 0. 30 秒上手

```bash
# 1) 依赖（核心库零第三方依赖；Playwright 仅 L2/L3 站点需要）
pip install -r requirements.txt

# 2) 环境变量
export OVERSEAS_PROXY=http://127.0.0.1:7877     # 出海代理，必需
export OVERSEAS_USE_PROFILE=1                    # 复用登录态浏览器 profile
export PYTHONIOENCODING=utf-8

# 3) 初始化并自检
python -m overseas.cli init-db
python -m overseas.cli sites                     # 应输出 80 个站点
python SELFCHECK.py                              # 36 项结构自检

# 4) 跑一次亚马逊加拿大站（小样验证）
python scripts/crawl_ca_retail.py --site amazon_ca --limit 3 --save-db
```

部署到服务器见 `DEPLOY.md`；当前各线完成度见 `STATUS.md`。

---

## 1. 这个项目做什么

自主搜索产品，采集**价格 / 评价 / 规格**，按时间序列入 SQLite，产出周度报表。

两条业务线共用同一套底座，**红线不同**：

| 业务线 | 契约 | 红线 | 一句话 |
|---|---|---|---|
| **SPEC 线** | `AdapterSpec` | 找全率 >= 95% | 抓品牌官网规格表，横向导出 Excel，中文 100% 覆盖 |
| **Retail 线** | `RetailSpec` | 匹配准确率 **100%** / 评价去重率 **0** | 抓电商站价格与评价，**宁可 skip 也不能错一条** |

Retail 线的严格性体现在：型号匹配用 `match.reject` 拒绝词表双向校验，
一旦不确定就放弃该候选，绝不写入脏数据。

---

## 2. 核心设计：契约与执行分离

这是整个项目的架构基石，也是「新增站点 0 行代码」能成立的原因。

```text
        JSON 契约（人/AI 写）             固定引擎（不随站点变）
   +--------------------------+      +--------------------------+
   | docs/retail_specs/*.json |----->| overseas/retail_spec.py  |
   | schemas/declarative/*.json|----->| overseas/extract.py      |
   +--------------------------+      +--------------------------+
```

- **声明式 schema**（`schemas/declarative/`，13 个）：选择器、字段、兜底链。
  DOM 改版只改 JSON，不动代码、不重新部署。
- **Retail 契约**（`docs/retail_specs/`，17 个）：搜索策略、翻页策略、型号匹配与拒绝词、
  登录探测 URL。**这是代码实际读取的路径**，不要挪动。

> 注意：路径是代码硬编码的 —— `data/overseas.db`、`data/mx/overseas_mx.db`、
> `docs/retail_specs/*.retail.json`。整理目录时**不要移动这三个位置**。

---

## 3. 分层架构

```text
scenarios   场景编排：S1 搜索采集 / S2 型号监控 / S2b 按SKU监控 / S3 详情直采 / S4 评价增量
   |
sites       站点适配插件（自动发现，共 80 个）+ schema.json 声明式抽取规则
   |
extract     抽取引擎：多选择器兜底链、kv 列表、重复块、transforms、JSON-LD 兜底
   |
fetchers    HttpFetcher（标准库）/ BrowserFetcher（Playwright，持久化 profile 复用登录态）
   |
infra       域名级 RateLimiter / BlockDetector / login_wall_hit / DiskCache / 代理探活
   |
db          SQLite；价格与评分按**时序快照只增不改**
```

### 三个关键取舍

1. **规则写在 JSON，不写进 Python。** 开发期实测撞到两次改版：`#productDetails_techSpec_section_1`
   在部分模板不存在；Amazon 评价 `data-hook` 从 `review-title` 改成驼峰 `reviewTitle`。
   多选择器兜底链让新旧模板同时命中。
2. **价格和评分是时序数据，只增不改。** `price_snapshot` / `review_summary` 只 INSERT，
   天然形成价格曲线与口碑趋势。单表覆盖更新会丢历史。
3. **评价按站内 `review_key` 唯一约束增量去重。** 重跑不重复入库，已存在记录「只补空字段」
   —— 修好选择器后重跑可回填历史空值，无需清库重采。

---

## 4. 双入口：Skill 与 CLI

同一件事有两种驱动方式，产物完全一致：

| 入口 | 位置 | 适用 |
|---|---|---|
| **Skill**（给人/AI 助手的操作手册） | `skills/spec-schema-gen/`、`skills/retail-schema-gen/` | 新站点接入、契约编写、自检 |
| **程序化 CLI** | `python -m overseas.cli spec-onboard` / `retail-onboard` | 批量、CI、无人值守 |

Skill 内自带 `selfcheck.py`、`playbook/README.md`、`cases.jsonl`（历史案例库）、
`reference.md`（经验教训）。新站点接入时**先读 skill 再动手**。

`skills/specs/mx-tv-line/` 是一份真实的历史需求规格（design/requirements/tasks），
作为 skill 产出的范例保留。

---

## 5. 目录导航

| 目录 | 文件数 | 内容 | 权威性 |
|---|---:|---|---|
| `overseas/` | 226 | 核心库：cli / db / extract / fetchers / infra / retail_spec / sites(80) / api | 唯一权威 |
| `docs/` | 48 | 全部文档 + **代码读取的** `retail_specs/*.retail.json`(17) | 契约权威 |
| `scripts/` | 77 | 业务脚本；`scripts/legacy/` 为历史归档 | 在用权威 |
| `schemas/` | 32 | `declarative/`(13) + `retail_specs/`(17 索引副本) + 2 份规范 | 索引副本 |
| `skills/` | 32 | 两套 skill + 范例 specs | 权威 |
| `data/` | 127 | 数据库、各站产物 CSV/XLSX | 数据权威 |
| `monitor/` | 8 | `retail_health.py` + supervisor + watchdog + systemd 单元 | 见下方注 |
| `deploy/` | 8 | systemd service/timer、env 模板、`setup_linux.sh` | 权威 |
| `backup_code/` | 1 | 历史代码备份 | 仅留档 |

> **`monitor/retail_health.py` 是副本**：权威版在 `overseas/retail_health.py`
> （CLI 命令 `retail-health`）。`monitor/` 下的副本用于快速查阅与 systemd 引用。

### 数据库

| 文件 | 大小 | 内容 |
|---|---:|---|
| `data/overseas.db` | 20.3 MB | 主库，21 表。product 999 / price_snapshot 916 / price_shop_snapshot 1441 / review 5230 |
| `data/mx/overseas_mx.db` | 3.0 MB | 墨西哥独立库，21 表。product 133 / price_snapshot 229 / review 420 |
| `data/db/backup/*.bak` | 23.3 MB | 上述两库的备份副本 |

分站明细（product/price）：

```text
kakaku_jp(site 4)    357/303      thebrick_ca(33)  202/202
amazon_ca(site 1)    169/159      leons_ca(34)     136/136
amazon_us(24)        134/115      walmart_us(36)     1/1
```

> 备份/迁移数据库**必须用 SQLite backup API**（或先 `VACUUM INTO`），
> 绝不直接复制 `.db` —— 会漏掉 `-wal` 里未落盘的事务。

---

## 6. 监视器

| 脚本 | 作用 | 用法 |
|---|---|---|
| `overseas/retail_health.py` | 站点健康探针，输出每站状态 | `python -m overseas.cli retail-health` |
| `monitor/supervisor_amazon_full.py` | 亚马逊三站全量抓取的进程守护（重启、断点续跑） | 见 `DEPLOY.md` |
| `monitor/watchdog_rebuild_amazon_full.py` | 看门狗：检测抓取停滞并重建任务 | 见 `DEPLOY.md` |

日志在 `monitor/logs/`。Linux 定时单元：`deploy/overseas-monitor.{service,timer}`。

---

## 7. 周度价格趋势（日本线，已可用）

目标是「每个渠道一条价格曲线」。基础设施已就绪：

- `price_shop_snapshot(product_id, shop, price, currency, is_lowest, captured_at)`
  只 INSERT，形成按渠道的价格时序。
- 8 个渠道：ビックカメラ.com / Joshin / ヤマダウェブコム / ノジマオンライン /
  ケーズデンキ / エディオンネットショップ / Amazon / ヨドバシ.com
- `scripts/weekly_kakaku_price.py` —— 周度调度，写 ISO 周键 `YYYY-Www`
- `scripts/gen_jp_price_trend_xlsx.py` / `gen_jp_price_trend_html.py` ——
  按品牌分 sheet，每个产品一块：周为行 x 8 渠道为列 + 原生折线图

> **待修**：`overseas/db.py::weekly_price_series()` 用 `strftime('%Y-W%W')`，
> 与调度器的 ISO 周键存在**恒定 1 周偏移**。修之前趋势图会错位一周。
>
> **数据现状**：`price_shop_snapshot` 目前只有 1 周数据
> （全部 `captured_at = 2026-09-09`，1441 行）—— 曲线需要**连续多周运行**才能成形。

---

## 7.5 定时溯源（竞品对阵分析 · 待维护自动补全）

竞品对阵分析服务（`启动竞品对阵分析.bat`，端口 8090）支持「待维护」参数的**三层自动溯源补全**：
当 SPEC 对比表出现缺失值时，系统自动按 **数据库回溯 → 官网重抓 → AI 推断** 三层递进寻找。

### 三种触发方式

| 方式 | 触发时机 | 适用 | 说明 |
|---|---|---|---|
| **对阵页面自动溯源** | 选型号点「生成对阵分析」 | 实时补全当前对阵 | 自动对缺失参数调三层回溯，补全值用紫色 `溯源` 标记 |
| **全库自动溯源** | 点页面「立即执行全库溯源」按钮 | 手动批量补全 | 调 `GET /api/auto-trace?max_models=50`，默认只走 db+site 快速层 |
| **定时溯源** | 每天凌晨 2 点 | 无人值守日常维护 | **默认不启动**，需加 `--enable-scheduled-trace` 参数 |

### 定时溯源如何启用

定时溯源**默认不启动**。需要时在启动命令加 `--enable-scheduled-trace`：

```bash
# 命令行启用
py -3.12 run_benchmark_server.py --port 8090 --enable-scheduled-trace

# 或修改 启动竞品对阵分析.bat，在 py 命令行末尾加上参数
py -3.12 run_benchmark_server.py --port 8090 --enable-scheduled-trace
```

启用后服务启动时会打印：
```
定时溯源已启用：每天凌晨2点自动执行，首次 2026-10-11 02:00
```

未启用时打印提示：
```
定时溯源：未启用（加 --enable-scheduled-trace 启用，详见 README §定时溯源）
```

### 定时溯源执行内容

每天凌晨 2 点自动执行 `api_auto_trace(max_models=100, with_ai=False)`：

1. 扫描全库所有型号的缺失参数（`fact_spec_value` 表中无值的 param_code）
2. 三层递进溯源：
   - **第 1 层 数据库**（置信度 0.95）：用 18 参数宽泛关键词在原始 `spec_row`/`product_spec` 重新搜索，找回「有数据但抽值脚本没匹配上」的值
   - **第 2 层 官网**（置信度 0.5）：推断品牌 adapter（如 `K-65XR70`→`sony_jp`），标记可触发 `spec_crawl` 重抓
   - **第 3 层 AI**（置信度 0.6-0.8）：调 xinghai-ultra 根据已有规格推断缺失参数档位
3. 定时任务默认只走第 1+2 层（快速，4 秒/28 型号）；第 3 层 AI 推断在对阵页面即时溯源时用
4. 溯源结果写回 `fact_spec_value` 表，标注 `source_table='auto-trace-db|site|ai'` + 置信度

### 手动触发全库溯源（不等定时）

```bash
# 快速模式（只走 db+site，秒级）
curl "http://127.0.0.1:8090/api/auto-trace?max_models=50"

# 含 AI 推断模式（慢，逐参数调 xinghai-ultra）
curl "http://127.0.0.1:8090/api/auto-trace?max_models=20&with_ai=1"

# 按尺寸筛选
curl "http://127.0.0.1:8090/api/auto-trace?size=65&max_models=30"
```

### 注意事项

- 定时溯源需要服务**保持运行**（关闭服务后定时任务也停止）
- 第 2 层「官网重抓」只标记可重抓，不自动触发浏览器抓取（避免无人值守时跑浏览器）
- 第 3 层 AI 推断需要 xinghai-ultra 代理可用（`http://127.0.0.1:8082/v1`），未配置时该层自动跳过
- 溯源写回的值带 `source_table` 标注，可区分是原始数据还是溯源补全的

---

## 8. 敏感文件（不要外发）

| 路径 | 原因 |
|---|---|
| `data/session/*.state.json` | 含登录 Cookie |
| `data/browser_profile/` | 含持久化登录态 |

本包**已排除**这两类。`.gitignore` 已覆盖。

---

## 9. 已知限制

- **出网是硬阻塞**：数据中心直连 amazon.ca 超时。没有出海线路时 L3 站点跑不了。
- **规模化触发风控**：单次通过不等于批量安全，Amazon 对数据中心 IP 高频访问会上验证码。
- **Amazon 未登录评价分页受限**：美国站硬顶 8 条/型号（`li.a-last = 0`，9 条绕过路径全失败）；
  墨西哥 2-5 条；南美 0 条。这是平台限制，非代码缺陷。
- **合规**：Amazon ToS 禁止未授权抓取。用于竞品调研前请走内部确认，
  或评估第三方数据源（Keepa / Rainforest 等）。

---

## 10. 相关文档

| 文档 | 内容 |
|---|---|
| `DEPLOY.md` | 部署与执行：环境、定时任务、全量抓取命令、回滚 |
| `STATUS.md` | 各业务线完成度、数据现状、待办 |
| `CHANGELOG.md` | v1 -> v2 整合变更记录 |
| `MANIFEST.txt` | 全 825 文件的 SHA256[:16] 清单与分类统计 |
| `SELFCHECK.py` | 36 项包结构自检 |
| `docs/项目总说明.md` | 代码地图、数据字典、前后端构建缺口 |
| `docs/交接文档_亚马逊三站全量抓取_20260920.md` | 亚马逊三站完整交接说明（304 行） |
| `docs/接口说明.md` | 前端对接 API |
| `docs/部署说明.md` | 服务器部署与回滚入口 |
| `docs/完整整理清单_v2_20260923.md` | 13 类全量整理清单 |
| `docs/整合部署包构建计划表_20260922.md` | 构建计划与验收标准 |