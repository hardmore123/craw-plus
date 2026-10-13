# 竞品上市定时预警方案

> FCC + EPREL 定时抓取 → 变化检测 → 预警信号的完整闭环。
> 目标:每天自动跑,有竞品新动作(新认证/能效升级/下架/换供应商)就出信号。

## 一、为什么不需要频繁抓取

FCC/EPREL 都是**合规数据库**,更新节奏是"天级"不是"分钟级"。信号本身有提前量:

| 信号 | 提前量(早于产品发布) | 合理频率 | 过频的代价 |
|---|---|---|---|
| FCC 新认证授权 | **1-3 个月**(保密期最长 180 天) | 每天 1 次 | 每小时抓只是重复拿相同数据,浪费请求配额,增被封风险 |
| FCC 保密文件到期 | 到期当天才变公开 | 每天 1 次 | 到期是离散事件,天级粒度足够 |
| EPREL 新注册 | **数天到数周** | 每天 1 次 | 注册号递增,每天 25 条样本已能捕捉新品 |
| 能效等级跃升 | 跨季度 | 每周 1 次 | 技术迭代慢,周度足够 |

**结论:每天 1 次足够捕捉所有领先指标。** 这是"前瞻性信号系统"而非实时监控——领先指标的价值在于"比新闻稿早",不在于"比对手早 1 小时"。

## 二、分层抓取策略(降本 + 降噪)

| 层级 | 频率 | 命令 | 抓什么 | 产出信号 |
|---|---|---|---|---|
| **日常层** | 每天 06:00 | `compintel-run`(无 --details) | FCC 全竞品搜索 + EPREL 25 条样本 | new_fcc_id / eprel_new_reg / supplier_change / field_change / eprel_delisted |
| **深度层** | 每周一 07:00 | `compintel-run --details` | 上面 + FCC 每个 ID 详情页文件清单 | + confidential_expired(保密到期) |
| **能效分析层** | 每月 1 日 | `compintel-eprel --brands <重点竞品>` | 重点竞品 EPREL 全量对比 | energy_class_jump(能效跃升) |

分层理由:`--details` 每多抓一个 FCC ID 详情页(20 文档),多 1 次请求 + 2s 限速,5 个竞品 ~500 ID 要 ~17 分钟。日常不需要,每周一次即可。

## 三、数据更新机制(时序快照 + 变化检测)

这是"保存数据 + 更新数据"的核心。**不覆盖历史**,每次抓取 INSERT 新快照:

```
compintel_record 表(时序):
  第1天抓 → INSERT 快照1 (source_id=X, applicant=A, energy=E, cap=day1)
  第2天抓 → INSERT 快照2 (source_id=X, applicant=A, energy=D, cap=day2)  ← 能效升级了
                ↓ 变化检测:对比快照1 vs 快照2
                ↓ 产出 field_change 信号(energy: E→D)
                ↓ 产出 energy_class_jump 信号(+1级)
```

7 类信号(变化检测维度):

| 信号 | 检测逻辑 | 时序依赖 |
|---|---|---|
| `new_fcc_id` | source_id 首次出现 | 首次抓 |
| `eprel_new_reg` | 注册号首次出现 | 首次抓 |
| `confidential_expired` | 详情页能抓到内部照片/手册 = 保密期结束 | 详情页 |
| `supplier_change` | 同 source_id 历次快照 applicant 变了 | 跨快照 |
| `field_change` | 同 source_id 历次快照任意语义字段变了(能效/频段/上市日等) | 跨快照 |
| `energy_class_jump` | 同品牌新记录能效比历史最佳高 ≥2 级 / 同产品本次比上次高 | 跨快照 |
| `eprel_delisted` | status 变非在售 / onMarketEnd 近30天 / 上次在售本次下架 | 跨快照 |

关键设计:`before_captured_at` 截点——变化检测在插入本次快照后运行,但用"本次 run 开始时间"作为截点查"上一次快照",避免查到刚插入的本次自己。

## 四、定时任务安装(Windows 计划任务)

### 4.1 一键安装
```powershell
# 以管理员身份运行(计划任务需管理员权限)
cd C:\Users\likunyuan\Desktop\爬取项目\海外
powershell -ExecutionPolicy Bypass -File scripts\compintel_install_task.ps1
```
安装后:
- `compintel_daily` — 每天 06:00 自动跑 `compintel_daily.ps1`
- `compintel_weekly` — 每周一 07:00 自动跑 `compintel_weekly.ps1`(带 --details)

### 4.2 管理命令
```powershell
# 查看任务状态
Get-ScheduledTask -TaskName compintel_*

# 手动立即触发(不等到 06:00)
Start-ScheduledTask -TaskName compintel_daily

# 查看上次运行结果
Get-ScheduledTaskInfo -TaskName compintel_daily

# 卸载
powershell -ExecutionPolicy Bypass -File scripts\compintel_install_task.ps1 -Uninstall
```

### 4.3 维护竞品清单
编辑 `scripts/compintel_daily.ps1` 和 `compintel_weekly.ps1` 顶部的数组:
```powershell
$APPLICANTS = @("Samsung", "LG", "Hisense", "TCL", "Sony")  # FCC 按公司名搜索
$EPREL_BRANDS = @("Samsung", "LG", "Hisense", "TCL", "Sony") # EPREL 按品牌过滤
```
建议 3-5 家核心竞品(英文公司名,与 FCC 申请人名一致)。

## 五、查看预警信号

```powershell
# 全部信号
py -3.12 -m overseas.cli compintel-alert

# 只看新认证信号(最重要)
py -3.12 -m overseas.cli compintel-alert --type new_fcc_id --limit 20

# 只看今天的信号
py -3.12 -m overseas.cli compintel-alert --since 2026-10-08T00:00

# 库统计
py -3.12 -m overseas.cli compintel-stats

# 查某竞品最新状态(只看最新快照,不查历史)
py -3.12 -m overseas.cli compintel-search --applicant Samsung --source fcc --limit 10
```

## 六、预警信号分级与行动建议

| level | 信号 | 行动 |
|---|---|---|
| **alert** | new_fcc_id | 竞品新硬件已完成美国认证,1-3 个月内上市。触发产品团队竞品分析 |
| **alert** | eprel_new_reg | 竞品新品完成欧盟合规,即将入欧。调整欧洲市场定位 |
| **alert** | energy_class_jump | 竞品技术迭代完成,能效竞争力提升。评估自身产品能效差距 |
| **watch** | confidential_expired | 竞品技术细节将公开。可获取内部照片/测试报告分析硬件方案 |
| **watch** | field_change | 竞品某字段变化(频段/上市日等)。持续追踪 |
| **watch** | supplier_change | 竞品可能换代工/调整供应链。关注供应链动态 |
| **watch** | eprel_delisted | 竞品可能停产/推替代型号。关注后续新品 |

## 七、日志与运维

- 日志:`海外/data/logs/compintel_daily_<日期>.log` 和 `compintel_weekly_<日期>.log`
- 每次抓取前自动备份 DB:`overseas.db.bak_compintel_<日期>`
- 失败处理:网络异常重试 2 次(计划任务内置),失败记 `crawl_error` 表
- DB 增长:时序快照会增长,历史快照可按月归档(后续可加清理脚本)

## 八、环境要求
```
OVERSEAS_PROXY=http://127.0.0.1:7877   # 出口代理
PYTHONIOENCODING=utf-8
PYTHON=py -3.12
计划任务运行账户:当前用户(无需 SYSTEM,需能访问项目目录)
```
