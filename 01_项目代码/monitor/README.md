# 监视器与健康探测（monitor/）

本目录集中放置**运行监控**相关资产：健康探测实现、长跑守护脚本、systemd 服务定义与历史日志。

---

## 一、文件清单

| 文件 | 类型 | 用途 |
|---|---|---|
| `retail_health.py` | 探测实现 | 零售站**小样健康探测**：抽 N 个型号验证选择器命中率与价格填充率，**骤降即告警** |
| `supervisor_amazon_full.py` | 守护脚本 | Amazon 全量抓取的**进程守护**：异常退出自动重启、记录状态 |
| `watchdog_rebuild_amazon_full.py` | 守护脚本 | 全量重建的**看门狗**：卡死检测与恢复 |
| `services/overseas-monitor.service` | systemd | 监视器服务单元 |
| `services/overseas-monitor.timer` | systemd | 监视器定时触发 |
| `logs/supervisor_amazon_full.log` | 日志 | 守护脚本历史输出 |
| `logs/watchdog_rebuild_amazon_full.log` | 日志 | 看门狗历史输出 |

> ⚠️ `retail_health.py` 的**权威副本在 `overseas/retail_health.py`**（CLI 从这里导入）。
> 本目录的副本仅为集中查阅，运行请用 `overseas/` 下的原件或 CLI。

---

## 二、健康探测怎么用

```bash
# 单站健康探测（抽 3 个型号）
python -m overseas.cli retail-health --spec docs/retail_specs/amazon_ca.retail.json --max-models 3

# 全仓库探测
python -m overseas.cli retail-health --all
```

**判据**：选择器命中率、价格填充率、评价条数。任一**骤降**（对比上次）即判定不健康，
退出码非 0 —— 便于接入告警。

**用途**：站点改版当天即可发现选择器失效，而不是等到下周出报表才发现数据为空。

---

## 三、部署监视器（systemd）

```bash
sudo cp monitor/services/overseas-monitor.service /etc/systemd/system/
sudo cp monitor/services/overseas-monitor.timer   /etc/systemd/system/
# 按实际路径修改 service 里的 WorkingDirectory / ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now overseas-monitor.timer
systemctl list-timers | grep overseas
```

查看运行情况：

```bash
systemctl status overseas-monitor.service
journalctl -u overseas-monitor.service -n 50
```

---

## 四、长跑守护脚本

全量抓取耗时长（Amazon 三站约 10.5 小时），容易被中断。两个脚本用于**无人值守**：

```bash
# 进程守护
python monitor/supervisor_amazon_full.py

# 看门狗（检测卡死并恢复）
python monitor/watchdog_rebuild_amazon_full.py
```

**注意**：这两个脚本面向 Amazon 全量场景，**改用其它站点前请先读源码确认参数**。

---

## 五、日志位置

| 来源 | 位置 |
|---|---|
| 守护/看门狗 | `monitor/logs/` |
| 抓取任务 | `data/logs/`（每站点单独文件） |
| 周度价格 | `data/logs/weekly_price_<stamp>.log` |
| 数据库审计 | 表 `crawl_run` / `crawl_error` |

**排查优先看数据库审计表**（结构化、可查询），日志用于看上下文：

```bash
python -c "
import sqlite3
c=sqlite3.connect('data/overseas.db')
for r in c.execute('SELECT id,status,ok_count,message FROM crawl_run ORDER BY id DESC LIMIT 5'):
    print(r)"
```
