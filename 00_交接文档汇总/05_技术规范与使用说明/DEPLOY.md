# 部署与执行指南

本文件回答两个问题：**怎么在服务器上跑起来**、**怎么执行一次完整抓取**。

---

## 一、环境准备

### 1.1 依赖

核心库**零第三方依赖**（纯标准库）。按需安装可选能力：

```bash
pip install -r requirements.txt          # 全装
pip install playwright                   # 仅抓 L2/L3 站点需要
pip install openpyxl==3.1.5              # 仅导出 xlsx 需要
```

也可用 `pyproject.toml`：

```bash
pip install -e ".[browser,xlsx]"         # 可编辑安装 + 浏览器 + Excel
pip install -e ".[browser,xlsx,translate]"   # 再加离线翻译
```

### 1.2 环境变量

复制 `deploy/overseas.env.example` 为 `overseas.env` 并按实际填写。

**关键项**（其余见模板内注释）：

| 变量 | 说明 |
|---|---|
| `OVERSEAS_PROXY` | **出海代理，L3 站点必需**。实测服务器直连 amazon.ca 超时 |
| `OVERSEAS_BROWSER_EXECUTABLE` | 服务器访问不了 Playwright CDN，须指向离线 Chrome |
| `OVERSEAS_USE_PROFILE=1` | 复用持久化浏览器 profile（保留登录态） |
| `OVERSEAS_HEADLESS` | 服务器设 `true`；调试登录态时设 `false` 以便手动登录 |
| `OVERSEAS_NAV_TIMEOUT` | REGZA/TCL 页面重，默认 60 秒 |
| `OVERSEAS_SETTLE` | `networkidle` 稳定等待秒数，默认 4 |
| `LANG=C.UTF-8` / `LC_ALL=C.UTF-8` | systemd 下 LANG 为空会导致中文乱码 |
| `PYTHONIOENCODING=utf-8` | Windows 下必需 |

**不要把填好的 `overseas.env` 提交 Git**（含代理与 API 凭据）。

### 1.3 浏览器（服务器离线安装）

```bash
pip install playwright                     # 只装 Python 包，不下载 chromium
# 解压 chrome-linux64.zip 到 .browser/
export OVERSEAS_BROWSER_EXECUTABLE=/path/.browser/chrome-linux64/chrome
sudo python -m playwright install-deps chromium   # 缺系统库时
```

Windows 本机直接用已装的 Edge，无需额外下载。

---

## 二、首次部署自检

按顺序执行，任一步失败先解决再继续：

```bash
python -m overseas.cli init-db              # 建表
python -m overseas.cli sites                # 期望输出 80 个站点
python SELFCHECK.py                         # 期望 36/36 PASS
python -m overseas.cli retail-health        # 站点健康探针
```

抽取链路验证（4 项）：

```bash
python -m overseas.cli probe --site amazon_ca --url https://www.amazon.ca/dp/<ASIN>
```

输出每个字段命中了哪个选择器、抽到什么值，以及规格/评价块数。

**数据库完整性**：

```bash
python -c "import sqlite3;print(sqlite3.connect('data/overseas.db').execute('pragma integrity_check').fetchone())"
# 期望 ('ok',)
```

---

## 三、日常执行

### 3.1 通用采集

```bash
python -m overseas.cli search   --site amazon_ca --keyword "hisense tv" --limit 3
python -m overseas.cli products
python -m overseas.cli monitor  --site amazon_ca --from-db      # 定时任务跑这个
python -m overseas.cli history  --product-id 1                  # 价格时序
```

### 3.2 亚马逊三站零售抓取

> **必须带 `--save-db`**，否则只出 CSV 不落库。

```bash
export OVERSEAS_PROXY=http://127.0.0.1:7877
export OVERSEAS_USE_PROFILE=1
export PYTHONIOENCODING=utf-8

# 小样验证
python scripts/crawl_ca_retail.py --site amazon_us --limit 3 --save-db

# 全量（预计 ~10.5 小时：US 2.7h -> MX 1.9h -> CA 5.9h）
python scripts/crawl_ca_retail.py --site amazon_us --save-db
python scripts/crawl_ca_retail.py --site amazon_mx --save-db
python scripts/crawl_ca_retail.py --site amazon_ca --save-db
```

**串行执行，不要并行。** 实测三站并行 11.2 分钟 vs 串行 7.3 分钟（9 型号）——
并行更慢，且同站双进程会使浏览器 profile 加锁失败，并且三倍抬高出口 IP 请求速率。

### 3.3 守护式全量抓取

长跑用守护脚本，支持重启与断点续跑：

```bash
python monitor/supervisor_amazon_full.py
python monitor/watchdog_rebuild_amazon_full.py     # 另开一个终端/服务
```

日志：`monitor/logs/supervisor_amazon_full.log`、`monitor/logs/watchdog_rebuild_amazon_full.log`

### 3.4 SPEC 线（日本六品牌）

```bash
python -m overseas.cli spec-crawl  --site sharp_jp
python -m overseas.cli spec-export --site sharp_jp --format xlsx --out SPEC_夏普日本.xlsx
python scripts/refresh_spec.py                     # 六品牌统一刷新 + 校验
python scripts/refresh_spec.py --export-only       # 只重导出（补词典后用）
```

Windows 包装：`scripts/refresh_spec.ps1`。中文翻译来自离线词典
`overseas/dict/spec_ja_zh.json`，未命中项记入 `spec_untranslated` 表，
刷新脚本默认把未翻译视为失败（避免周报静默降级）。

### 3.5 日本线周度价格趋势

```bash
python scripts/weekly_kakaku_price.py                       # 采集本周快照
python scripts/gen_jp_price_trend_xlsx.py                   # 生成 xlsx（含折线图）
python scripts/gen_jp_price_trend_html.py                   # 生成 html
```

> `price_shop_snapshot` 需要**连续多周运行**才能形成曲线。
> 目前库中只有 1 周（2026-09-09）。

---

## 四、定时任务（Linux / systemd）

`deploy/` 下已备好单元文件：

| 文件 | 作用 |
|---|---|
| `overseas-spec.service` + `.timer` | 每周刷新 SPEC 六品牌 |
| `overseas-monitor.service` + `.timer` | 站点健康监控 |
| `overseas-api.service` | 常驻后端 API |
| `kakaku_weekly_task.xml` | Windows 任务计划（周度 kakaku 价格） |
| `setup_linux.sh` | 一键安装脚本 |

安装：

```bash
sudo cp deploy/overseas-*.service deploy/overseas-*.timer /etc/systemd/system/
sudo cp deploy/overseas.env.example /etc/overseas.env   # 然后填入真实值
sudo systemctl daemon-reload
sudo systemctl enable --now overseas-spec.timer overseas-monitor.timer
systemctl list-timers --all | grep overseas
```

Windows 任务计划导入 `deploy/kakaku_weekly_task.xml`。

---

## 五、后端 API

```bash
python -m overseas.api.server --port 8000 --cors "*"
curl -s http://127.0.0.1:8000/api/health
```

接口清单见 `docs/接口说明.md`。

---

## 六、数据库运维

### 备份（必须用 SQLite backup API）

```bash
python - <<'PY'
import sqlite3, datetime
stamp = datetime.datetime.now().strftime('%Y%m%d')
for src, dst in [('data/overseas.db', f'data/db/backup/overseas_{stamp}.bak'),
                 ('data/mx/overseas_mx.db', f'data/db/backup/overseas_mx_{stamp}.bak')]:
    s = sqlite3.connect(src); d = sqlite3.connect(dst)
    with d: s.backup(d)
    d.close(); s.close(); print('ok', dst)
PY
```

**绝不直接 `cp` 数据库文件** —— WAL 模式下会漏掉未落盘事务，得到损坏副本。

### 恢复

```bash
systemctl stop overseas-api overseas-monitor.timer
cp data/db/backup/overseas_YYYYMMDD.bak data/overseas.db
rm -f data/overseas.db-wal data/overseas.db-shm     # 关键：清掉残留 WAL
python -c "import sqlite3;print(sqlite3.connect('data/overseas.db').execute('pragma integrity_check').fetchone())"
systemctl start overseas-api overseas-monitor.timer
```

### 回滚代码

本包是按日期整体快照的。回滚 = 用上一版 zip 解压覆盖，然后重跑第四节的自检。

---

## 七、故障排查

| 现象 | 排查 |
|---|---|
| 采集全部 `blocked` | 代理不通 / 出口 IP 被风控。先 `retail-health` |
| 登录态丢失 | 检查 `OVERSEAS_USE_PROFILE=1`；`data/browser_profile/` 是否被清 |
| 价格全为 `None` | 页面 buybox 不存在（"See All Buying Options"）。这是**正确行为**，非 bug |
| 评价 0 条 | 检查 `data-hook` 是否又改版（历史从 `review-title` 改成 `reviewTitle`） |
| 中文乱码 | `LANG=C.UTF-8`、`LC_ALL=C.UTF-8`、`PYTHONIOENCODING=utf-8` |
| 浏览器启动失败 | `OVERSEAS_BROWSER_EXECUTABLE` 是否指向存在的 chrome |
| profile 加锁失败 | 同站不要跑两个进程 |

DOM 改版时先 `probe` 定位坏掉的选择器，再改 JSON —— **不要改 Python**。

---

## 八、性能说明（仅记录，未实施）

当前每型号约 73 秒，其中**限速等待仅占 1%**，99% 是浏览器/渲染固定等待：

| 项 | 现状 | 候选优化 |
|---|---|---|
| `networkidle` 等待 | 固定 4s（首页也白等 4s） | 降到 1–1.5s |
| `scroll_passes` / `extra_wait_ms` | 全局值 | 按站点分级；Amazon 实测 0/2/4/8 次滚动抽取结果相同 |
| `filter_sweep` 翻页 | 11 个组合各付一次固定等待 | 复用同一 page |
| `interval_sec` 限速 | 实测仅占 1% | **不要动** |

三项落地预计 73s -> 30–35s，全量 10.5h -> 约 5h。
**以上均为候选，尚未修改代码。**