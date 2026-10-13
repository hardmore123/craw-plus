# 海外电商采集框架（overseas）

自主搜索产品，采集**价格 / 评价 / 规格**入数据库。面向多站点、可扩展、可在 Linux 服务器定时运行。

架构模式借鉴 Crawl4AI（插件自动发现、Strategy 分层、域名级调度、大字段外置），
但**不引入该包**：它有 30+ 重依赖且是 async+LLM 中心设计，与本项目「标准库优先、
可离线部署」的取向冲突。本框架核心零第三方依赖，Playwright 为可选依赖。

> **新接手请先读 [`项目总说明.md`](项目总说明.md)**：日本线 SPEC / 价格 / 评论三条业务线的
> 代码地图、数据字典、前后端构建缺口与服务器部署指南都在那里。
> 本 README 只讲框架本身；操作命令见 `使用说明.md`，运维部署见 `部署说明.md`，
> **前端对接见 [`接口说明.md`](接口说明.md)**。

后端 API（零依赖，标准库实现）：

```bash
python -m overseas.api.server --port 8000 --cors "*"
curl -s http://127.0.0.1:8000/api/health
```

## 快速开始

```bash
pip install playwright          # 仅抓 L2/L3 站点需要；Windows 直接用已装的 Edge

python -m overseas.cli init-db
python -m overseas.cli sites
python -m overseas.cli search --site amazon_ca --keyword "hisense tv" --limit 3
python -m overseas.cli products
python -m overseas.cli monitor --site amazon_ca --from-db     # 后续定时跑这个
python -m overseas.cli history --product-id 1                 # 看价格时序
```

实测结果（本地 Windows + Edge，2026-09）：

```text
[搜索] p1 https://www.amazon.ca/s?k=hisense+tv
  1/3 B0GPHMTMLC specs=5 price=Y reviews=8
  2/3 B0GQD6F41Q specs=4 price=Y reviews=8
  3/3 B0DYS29P6M specs=6 price=Y reviews=13
完成: ok=3 fail=0 blocked=0 products=3 prices=3 reviews_new=29
```

## 分层架构

```text
scenarios   场景编排：S1 搜索采集 / S2 型号监控 / S2b 按SKU监控 / S3 详情直采 / S4 评价增量
   ↓
sites       站点适配插件（自动发现）+ schema.json 声明式抽取规则
   ↓
extract     抽取引擎：多选择器兜底链、kv 列表、重复块、transforms、JSON-LD 兜底
   ↓
fetchers    HttpFetcher（标准库）/ BrowserFetcher（Playwright，浏览器复用）
            统一 Dom 接口，上层不关心页面怎么拿到
   ↓
infra       域名级 RateLimiter（按状态码自适应退避）/ BlockDetector / DiskCache / 代理探活
   ↓
db          SQLite 存储；价格与评分按**时序快照只增不改**
```

## 核心设计取舍

**抽取规则写在 schema.json，不写进 Python。**
DOM 一变只改配置，不动代码、不重新部署。这不是过度设计 —— 开发期间实测就撞到两次：
`#productDetails_techSpec_section_1` 在部分模板不存在（型号实际在 `#detailBullets_feature_div`）；
Amazon 评价的 `data-hook` 已从 `review-title` 改成驼峰 `reviewTitle`。多选择器兜底链让新旧模板都能命中。

**价格和评分是时序数据，用快照表只增不改。**
`price_snapshot` / `review_summary` 只 INSERT 不 UPDATE，天然形成价格曲线与口碑趋势。
若用单表覆盖更新，历史就没了。

**评价按站内 `review_key` 唯一约束做增量去重。**
重跑不会重复入库；并且已存在的记录会「只补空字段」——修好选择器后重跑可回填历史空值，不用清库重采。

**规格用 KV 表而非宽表。**
电视、冰箱、手机的规格字段差异太大，宽表会退化成几百列。

## 站点防护分级

框架按站点声明的等级自动选 Fetcher 与抓取间隔。

| 等级 | 含义 | Fetcher | 本次实测 |
|---|---|---|---|
| L1 | 温和 | HttpFetcher 即可 | Samsung / TCL / Philips（200） |
| L2 | 中等 | 需真实浏览器 | LG / Sony（403 Access Denied） |
| L3 | 强防护 | 浏览器 + 低频 + 可能需代理 | Amazon / Walmart / BestBuy |

## 新增一个站点

只需建目录，不改核心代码：

```text
overseas/sites/<code>/__init__.py     空文件
overseas/sites/<code>/adapter.py      继承 SiteAdapter，给出 URL 规则
overseas/sites/<code>/schema.json     选择器写这里
```

`SiteRegistry` 会自动发现并注册（借鉴 Crawl4AI 的 `hub.py`）。

## 维护选择器

DOM 改版时先跑自检定位坏掉的选择器，再改 schema.json：

```bash
python -m overseas.cli probe --site amazon_ca --url https://www.amazon.ca/dp/B0GPHMTMLC
```

输出每个字段命中了哪个选择器、抽到什么值，以及规格/评价的块数。

## SPEC 采集（日本站规格表）

除电商评价采集外，框架还支持采集品牌官网的产品规格表，按品牌导出为 Excel
（列：区分 | 项目 | 项目（中文） | 机型1 | 机型2 | ...，中文列紧挨项目右侧）。

已落地六个日本电视品牌 SPEC 适配器：海信、索尼、REGZA、松下、TCL、夏普。每个品牌按官网结构采集系列/型号，统一导出「区分 | 项目 | 项目（中文） | 机型…」横向 Excel，并按 ISO 周保存数据库快照。

| 品牌 | 系列 | 型号 | 导出行 | 中文覆盖 |
|---|---:|---:|---:|---:|
| 海信 `hisense_jp` | 13 | 44 | 101 | 100% |
| 索尼 `sony_jp` | 9 | 38 | 104 | 100% |
| REGZA `regza_jp` | 39 | 139 | 564 | 100% |
| 松下 `panasonic_jp` | 8 | 25 | 52 | 100% |
| TCL `tcl_jp` | 28 | 78 | 283 | 100% |
| 夏普 `sharp_jp` | 13 | 44 | 56 | 100% |

单品牌手工命令（Python 3.12）：

```powershell
$py = 'C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\python.exe'
& $py -m overseas.cli spec-crawl --site sharp_jp
& $py -m overseas.cli spec-export --site sharp_jp --format xlsx --out SPEC_夏普日本.xlsx
$env:PYTHONIOENCODING = 'utf-8'
& $py check_xlsx.py SPEC_夏普日本.xlsx
```

六品牌统一刷新（采集、导出、结构和中文覆盖率校验）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\refresh_spec.ps1
# 只重新导出数据库中的当前快照：
powershell -ExecutionPolicy Bypass -File .\scripts\refresh_spec.ps1 -ExportOnly
```

Linux 使用同一个 `scripts/refresh_spec.py`，配套 `deploy/overseas-spec.service` 和
`deploy/overseas-spec.timer`，每周执行一次。REGZA/TCL 页面较重，脚本默认导航超时 60 秒，
可用 `OVERSEAS_NAV_TIMEOUT` 覆盖；输出固定写到项目根目录的六个 `SPEC_*.xlsx`，数据库默认是
`data/overseas.db`。需要补词典时运行 `python -m overseas.cli spec-dict`，补充
`overseas/dict/spec_ja_zh.json` 后使用 `-ExportOnly` 重导出即可，无需重新采集。

中文翻译来自离线术语词典 `overseas/dict/spec_ja_zh.json`（日文项目名→中文），未命中项自动记入
`spec_untranslated` 表；刷新脚本默认把未翻译项目视为失败，避免周度报表静默降级。

## 数据表

| 表 | 说明 |
|---|---|
| `product` | 商品主体，`(site_id, sku)` 唯一 |
| `product_spec` | 规格 KV |
| `price_snapshot` | ★时序：价格、原价、货币、有货 |
| `review` | 评价，`(product_id, review_key)` 唯一 |
| `review_summary` | ★时序：平均分、总数、星级分布 |
| `ranking_snapshot` | ★时序：榜单排名 |
| `crawl_run` / `crawl_error` | 任务与错误审计 |
| `raw_page` | 原始 HTML 只存路径+哈希，正文落文件 |
| `spec_series` | SPEC 系列（品牌+系列+机型列表） |
| `spec_row` | ★时序：SPEC 行，按 ISO 周快照（区分/项目/中文/各机型值） |
| `spec_untranslated` | 词典未命中的日文项目，待补 |

## 已知限制

- **服务器出网是硬阻塞**：实测 `10.18.87.51` 直连 amazon.ca 超时，加拿大零售站 8/14 完全不通。
  没有出海线路时，L3 站点只能在能出网的机器上跑。
- **规模化会触发风控**：单次采集通过不代表批量安全。Amazon 对数据中心 IP 和高频访问会上验证码。
- **评价翻页深度有限**：Amazon 对未登录用户限制评价分页，拿不到全量历史评价。
- **合规**：Amazon ToS 禁止未授权抓取，评价数据官方 API 也不开放。用于竞品调研前请走内部确认，
  或评估第三方数据源（Keepa / Rainforest 等）。

## 相关文档

- `使用说明.md` — 日常采集、导出、词典、周度刷新、故障排查和回滚
- `部署说明.md` — Linux/Windows 部署、定时任务和回滚入口
- `工作日志.md` — 六品牌 SPEC 实现、问题修复和验收记录
- `交付说明.md` — 交付目录、验收标准和排除项
- `deploy/` — systemd service/timer、环境变量模板、一键自检脚本


## SPEC 系列状态审计

SPEC 采集对每个系列统一记录三种状态：`success`（至少一个型号和一行规格）、`empty`（请求成功但无可用 table/型号/JSON/规格行）、`failed`（HTTP、超时、浏览器/网络或解析失败；多型号部分失败也属于 failed）。状态写入 `spec_series_status`，底层 URL/入口错误写入 `crawl_error`；入口 `list_series`/`series_entries` 为空时会记录 `stage=entry,kind=empty` 并将运行标为 `failed`。

刷新后查看状态：

```powershell
$stamp = Get-Date -Format 'yyyyMMdd'
& $py scripts\export_spec_status.py --db data\overseas.db --format all --out "data\SPEC_系列状态_$stamp"
```

`refresh_spec.py` 会自动执行同样的状态导出。状态清单与 `scripts/export_spec_models.py` 的型号清单分开：`empty/failed` 系列不会生成伪造型号，旧库回溯成功数据会标记 `status_source=legacy`，不冒充本周成功。
