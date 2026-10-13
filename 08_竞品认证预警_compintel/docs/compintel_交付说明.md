# 竞品上市预警系统（compintel）交付说明

> FCC 认证数据库 + EPREL 能效注册库 的爬取与预警信号识别。
> 代码位置：`overseas/compintel/`，与电视 spec/retail 业务解耦。

## 一、架构

```
overseas/compintel/
├── __init__.py
├── compintel_db.py     # compintel_* 表族读写封装（复用 Database + crawl_run）
├── fcc_crawler.py      # FCC 认证记录爬虫（fccid.io 聚合站，纯 HTTP）
├── eprel_crawler.py    # EPREL 电子显示器能效注册爬虫（官方 JSON API，纯 HTTP）
├── alert.py            # 6 类上市预警信号识别
└── orchestrator.py     # 抓取编排：建 run → 调爬虫 → 落库 → 调信号 → 收尾

overseas/schema.sql     # 末尾新增 compintel_record / compintel_doc / compintel_alert 三表
overseas/cli.py         # 新增 5 个 CLI 子命令
```

数据源选择（实测）：
- **FCC**：官方 `apps.fcc.gov` 被 Akamai 硬封（403 + errors.edgesuite.net），改走 `fccid.io` 聚合站，纯 HTTP 可拿。
- **EPREL**：官方站是 Angular SPA，数据全在 `/api/` JSON 接口，纯 HTTP 可拿，无需浏览器。

## 二、数据库表（schema.sql 末尾）

| 表 | 用途 | 时序 |
|---|---|---|
| `compintel_record` | 一行=一个 FCC ID 或 EPREL 注册号的一份快照 | 每次抓取 INSERT 新行 |
| `compintel_doc` | FCC 文件清单（测试报告/内部照片等） | 随 record |
| `compintel_alert` | 预警信号，每行一个 | 按信号类型+source_id+时间唯一 |

## 三、CLI 用法

### 抓 FCC 认证记录（按竞品公司名）
```powershell
# 基础：按公司名搜索 fccid.io，落库 + 产生 new_fcc_id 信号
py -3.12 -m overseas.cli compintel-fcc --applicants Samsung LG Hisense

# 同时抓每个 FCC ID 详情页文件清单（用于保密到期检测，较慢：每 ID +1 请求）
py -3.12 -m overseas.cli compintel-fcc --applicants Samsung --details

# 输出 JSON
py -3.12 -m overseas.cli compintel-fcc --applicants Samsung --json
```

### 抓 EPREL 电子显示器能效注册
```powershell
# 全量落库列表返回的 25 条（每次抽样不同）
py -3.12 -m overseas.cli compintel-eprel

# 只保留 supplier 含指定品牌的记录
py -3.12 -m overseas.cli compintel-eprel --brands Samsung Hisense
```

### 查看预警信号
```powershell
py -3.12 -m overseas.cli compintel-alert                # 全部
py -3.12 -m overseas.cli compintel-alert --type new_fcc_id
py -3.12 -m overseas.cli compintel-alert --since 2026-09-30T00:00 --limit 20
```

### 库统计 / 检索
```powershell
py -3.12 -m overseas.cli compintel-stats
py -3.12 -m overseas.cli compintel-search --applicant Samsung --source fcc --limit 10
```

## 四、6 类预警信号（alert.py）

| 信号类型 | 来源 | 判据 | level |
|---|---|---|---|
| `new_fcc_id` | FCC | source_id（FCC ID）首次出现 | alert |
| `confidential_expired` | FCC | 详情页能抓到 Internal/External Photos/Users Manual（保密期已结束） | watch |
| `eprel_new_reg` | EPREL | registration_number 首次出现 | alert |
| `energy_class_jump` | EPREL | 同品牌新记录能效比历史最佳高 ≥2 级 | alert |
| `eprel_delisted` | EPREL | status 变非在售 / onMarketEnd 近30天 | watch |
| `supplier_change` | 两者 | 同 source_id 历史快照 applicant 与本次不同 | watch |

## 五、实测结果（sandbox DB）

```
FCC  (Samsung 1 applicant, --details):
  ok=125 fail=0 new=125
  文档 5665 条（20 文档/ID）
  信号 249 条：new_fcc_id 125 + confidential_expired 124

EPREL (电子显示器全量):
  ok=25 fail=0 new=25  total=37509
  信号 25 条：eprel_new_reg 25

第二次 FCC 跑（去重验证）: ok=125 new=0 signals=[]   ← 正确，无新记录
```

## 六、环境要求
- `OVERSEAS_PROXY=http://127.0.0.1:7877`（两站都走代理，FCC 直连被封）
- `PYTHONIOENCODING=utf-8`
- 无需 Playwright（两站均纯 HTTP），无需浏览器登录态
- Python 3.12，依赖 `overseas.fetchers.HttpFetcher` + `overseas.db.Database`

## 七、定时预警建议
- FCC：每天/每周跑一次 `compintel-fcc --applicants <竞品1> <竞品2> ...`，对比上次产生 new_fcc_id 信号。
- EPREL：每天跑一次 `compintel-eprel`（25条样本轮询），新注册号产生 eprel_new_reg 信号。
- 信号查 `compintel-alert` 命令或 `compintel_alert` 表，接 BI/邮件/Slack。
- 抓全量 EPREL 需长期轮询（API 不可翻页），注册号去重逐步覆盖。
