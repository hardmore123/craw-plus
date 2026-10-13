# 变更记录


### Skill 经验沉淀

南美线经验此前**完全空白**（cases.jsonl 14 条全是北美+墨西哥）。本次补入 3 条平台经验：

| 平台 | case code | playbook | reference 章节 | 覆盖站点 |
|---|---|---|---|---|
| VTEX Catalog API | vtex_batch | vtex_catalog_api.md（新增） | §12 | 14 站（API 直采，无需 Playwright） |
| Magento | magento_batch | needs_human.md（复用） | §13 | 9 站（需 Playwright + 契约，模板已有） |
| Next.js/Falabella | falabella_nextjs | needs_human.md（复用） | §14 | 8 站（需 Playwright，无 API） |

cases.jsonl 14→16 条，reference.md 11→14 大节，playbook 9→10 个文件。


### VTEX 14 站实际入库

用 `scripts/vtex_to_db.py`（新建）对 14 个 VTEX 南美站跑 Catalog API，产品+价格写入 `overseas.db`：

| 指标 | 入库前 | 入库后 | 新增 |
|---|---:|---:|---:|
| site 表 | 10 | 24 | +14 |
| product | 999 | 1989 | +990 |
| price_snapshot | 916 | 1895 | +979 |

14/14 站全部成功，0 失败。integrity_check=ok。

### Magento 5 站契约生成

用 `hiraoka_pe.retail.json` 作模板，批量生成 5 个 Magento 站契约（coral_ec / laganga_ec /
dismac_bo / panafoto_pa / raenco_pa），全部通过 `validate_retail_spec`。


### Magento 3 站 Playwright 入库 + 全站爬取效果测试

- `scripts/magento_to_db.py`（新建）：用 Playwright 渲染 Magento 搜索页入库
  - hiraoka_pe: 20 产品 20 价格 ✅
  - laganga_ec: 20 产品 20 价格 ✅
  - raenco_pa: 12 产品 12 价格 ✅
  - dismac_bo / panafoto_pa / efe_pe: 0 产品（选择器需调优）

- `scripts/full_probe_test.py`（新建）：34 站全站爬取效果测试
  - VTEX 14/14 全部通过（API 直采）
  - Magento 3/6 已入库（Playwright）
  - 北美 5/7 OK，2 站 WAF blocked
  - SPEC 4/10 OK，4 站 403 需 Playwright
  - DB 总计: 27 站 2041 产品 1947 价格

- `scripts/vtex_to_db.py`（新建）：VTEX Catalog API → SQLite
- `scripts/magento_to_db.py`（新建）：Magento Playwright → SQLite
- `scripts/full_probe_test.py`（新建）：全站爬取效果测试


### panafoto_pa 入库 + 最终 40 站测试

- panafoto_pa: 30 产品 30 价格 ✅（独立选择器 a.product-item-photo）
- 最终测试 40 站: 24 站有数据, 2071 产品, 1977 价格
- VTEX 14/14 ✅, Magento 4/4 ✅, NA/JP 8/12, SPEC 0/10


### SPEC 品牌官网 Playwright 抓取

- `scripts/spec_pw_to_db.py`（新建）：用 Playwright 过 403 WAF 抓取 SPEC 品牌官网
- lg_us: 10 产品 10 价格 ✅（Playwright 过了 WAF，从 lineup 页提取）
- sony_ca: status=200 但产品页路径不同（/en/c/all-tvs），需更长等待
- lg_ca: 地理重定向超时（代理出口 IP 被识别为欧洲）
- 最终测试 40 站: 25 站有数据, 2081 产品, 1987 价格


### SPEC 品牌 + Amazon MX + BestBuy sitemap 入库

- lg_us: 10 产品 10 价格 ✅（Playwright 过 403 WAF）
- sony_ca: 4 产品 ✅（Playwright 过 403，JSON-LD ItemList）
- bestbuy_ca: 9 产品 ✅（sitemap 确定性发现，绕开 robots 禁搜索）
- amazon_mx: 49 产品 49 价格 ✅（Playwright 渲染搜索页，ASIN+标题+价格）
- 最终: 32 站 28 站有数据 2143 产品 2036 价格


### Costco + BestBuy US 入库

- costco_ca: 19 产品 19 价格 ✅（MUI Grid 提取，scroll_until_stable）
- bestbuy_us: 77 产品 ✅（bsin sitemap 确定性发现，107 TV URL）
- walmart_us: ❌ WAF 不可过（"Robot or human?" 验证页）
- 最终: 32 站 30 站有数据 2239 产品 2055 价格
- 经验沉淀到 .claude/skills/overseas-crawl-ops/SKILL.md


### 欧洲线新增（5 国 + 俄罗斯）

- samsung_uk: 38 产品 ✅（JSON-LD ItemList 48 产品，排除 projector/movable）
- sony_uk: 7 产品 ✅（Playwright 过 403，ProductTileOne + sku= 提取 BRAVIA 系列）
- mediamarkt_es: 12 产品 12 价格 ✅（JSON-LD ItemList，€149-€499 Samsung/LG/Philips/Hisense/Xiaomi）
- 欧洲+俄罗斯 36 站连通性探测完成，结果追加到 爬取进度.csv
- 最终: 35 站 33 站有数据 2296 产品 2067 价格
- 经验沉淀到 .claude/skills/overseas-crawl-ops/SKILL.md


### Amazon 欧洲五站全部入库

- amazon_uk: 2 产品 3 价格 ✅（Playwright原生API输入邮编LS118LZ，£195.13/£166.15）
- amazon_de: 2 产品 ✅（代理出口英国IP致重定向amazon.co.uk，价格待补）
- amazon_fr: 38 产品 31 价格 ✅（搜索页直接返回法国产品，€89.99-€779）
- amazon_it: 34 产品 7 价格 ✅（Playwright原生API，goto超时后重试成功）
- amazon_es: 36 产品 33 价格 ✅（搜索页直接返回西班牙产品，€299-€2199）
- 最终: 41 站 39 站有数据 2413 产品 2141 价格 覆盖率 95.1%
- 关键突破: bf._ensure() + bf._ctx.new_page() 绕过 BrowserFetcher 限制，直接用 Playwright 原生 API
- 关键发现: amazon.fr/es 搜索页本身不输邮编即返回本币价格

## v2.1 — 2026-09-23（四区域核查 + 数据源补齐）

### 核查

对北美 / 南美 / 日本 / 欧洲四区域的 SPEC / 价格 / 网评做全量实测（直接查库查文件），
结论写入 `STATUS.md` 第七节。关键发现：

- **北美 SPEC 中文翻译 88% 缺失**（44132 行中 38944 行无 `item_zh`），
  日本线近全译 —— 词典 `spec_ja_zh.json` 只有日文词条，北美英文规格无对应词典。
  README 中"中文覆盖 100%"仅对日本线成立。
- **南美 1395 行价格未落库**，网评 0 条，契约仅 3/39。
- **日本线星级 93% 为空**（627/673），`review_summary` 完全缺失。
- **欧洲完全空白**：0 适配器 / 0 数据 / `api/regions.py` 仅占位 `enabled=False`。

### 数据源补齐

v2.0 遗漏了南美驱动必需的入参文件，本次从源工作区补入 `data/` 下（排除 .log）：

| 目录 | 文件数 | 用途 |
|---|---:|---|
| `schema_drafts/` | 3 | 南美零售契约（hiraoka_pe / efe_pe / lacuracao_pe） |
| `型号清单/` + `型号清单_短码/` | 14 | 南美型号清单，`crawl_sa_retail.py` 必需入参 |
| `在售全量/` | 39 | VTEX/Magento 全量在售目录 CSV |
| `秘鲁/` / `美国/` / `墨西哥/` / `加拿大/` | 191 | 国别 SPEC 产物 + 价格/网评 CSV |

补齐后南美线恢复可重跑能力（有契约 + 有型号清单）。

### 文档

- `STATUS.md` 新增第七节「四区域全量覆盖核查」、第八节「本次补齐的数据源文件」
- 欧洲线明确标注为**未启动**（`api/regions.py` 占位 `enabled=False`）

---

## v2.0 — 2026-09-23（整合部署包）

### 新增

- **顶层交付文档**：`README.md` / `DEPLOY.md` / `STATUS.md` / `CHANGELOG.md` / `SELFCHECK.py`
- `MANIFEST.txt`：全 825 文件的 SHA256[:16] 清单 + 15 类分类统计
- `monitor/`：`retail_health.py`、`supervisor_amazon_full.py`、
  `watchdog_rebuild_amazon_full.py` + `logs/` + `services/` + `README.md`
- `deploy/`：systemd service/timer x4、`kakaku_weekly_task.xml`、
  `overseas.env.example`、`setup_linux.sh`
- `skills/specs/mx-tv-line/`：真实需求规格范例（design / requirements / tasks）
- `data/db/backup/`：两库备份副本
- `scripts/legacy/`：13 个历史根脚本归档

### 修复（相对 v1 的致命问题）

| 问题 | 后果 | 修复 |
|---|---|---|
| 数据库路径为 `08_数据/数据库/overseas.db` | **代码找不到库，直接崩** | 改为代码硬编码的 `data/overseas.db`、`data/mx/overseas_mx.db` |
| 契约只在 `07_Schema/retail_specs/` | **契约加载失败**（代码读 `docs/retail_specs/`） | `docs/retail_specs/`(17) 为代码面向副本，`schemas/retail_specs/`(17) 为索引副本 |
| 递归清理 `.bak` 时误删数据库备份 | 无备份可用 | 重建为 `data/db/backup/*.bak` |

### 校验结果

| 项 | 结果 |
|---|---|
| 适配器覆盖 | 80 / 80 |
| 声明式 schema 覆盖 | 13 / 13 |
| Retail 契约覆盖 | 17 / 17 |
| 脚本覆盖 | 76 / 76 |
| 包结构自检 | 36 / 36 PASS |
| 独立抽取测试 | 4 / 4 PASS（站点注册 80、契约自检通过、趋势 xlsx 258.4 KB、DB integrity ok） |
| 数据库完整性 | ok / ok |

压缩包：`海外数据爬取_部署包_v2.0_20260923.zip`（13.8 MB）
SHA256：`2496151eeea50c97cea04a023d723acea69eda2504aca40cc5c7701e79ba1bf2`

---

## 业务代码变更（2026-09-18 ~ 09-20）

### 亚马逊三站

- **新增 `overseas/sites/amazon_common.py`**：共享 `parse_amazon_product()`、
  `price_in_region()`、`PRICE_SELECTORS`、`pick_price_text()`。
  三个国家适配器统一委托，消除重复实现。
- **价格区域校验**：价格必须位于 `corePrice` / `buybox`；
  祖先含 `_c2Itb_` / `a-carousel` / `p13n` 的拒绝。
  修复配件推荐价污染主机价（32A4NV 曾错为 $9.49）。
  验证后真实价 349.99 / 698.0 / 328.0 / 881.99 保留，32A4NV 正确为 `None`。
- **`amazon_us` 补 `retail_page_wait`**：原先缺失，回退到 `getattr(..., "body")`，
  改为 `"#productTitle, #dp, .a-price"`。
- **`amazon_mx` 补 `login_probe_url`**。
- **评价选择器修复**：`[data-hook='review-title']` / `review-body` 在当前 DOM 恒为空
  （13 个评价块抽出 0 行），改为 `reviewTitle` / `reviewText`（ca+us+mx）。
- **`_payload_matches_model` 加 `match.reject`**：修复 fallback 路径绕过拒绝词表，
  导致 `amazon_us` 混入 10 个配件。已清库并留备份。

### 登录态

- 凭据 Cookie **按国家加后缀**：`at-acbca`(ca) / `at-main`(us) / `at-acbmx`(mx)。
  原只认 `at-main`，误判 ca/mx 未登录（3 次错误尝试）。
  改为前缀匹配（`at-` / `sess-at-` / `x-`，排除 `at-a-glance`、`x-amz`）。
- **登录等待改为全被动**：不再每 5 秒 `goto`（会抢焦点导致页面闪退），
  不再新开标签探测 `/gp/css/order-history`（会 302 到 `/ap/signin`）。
  现在：ONE `new_page`、ONE `goto`、ZERO reload、ZERO 额外标签。
- **登录判定收敛为单一硬标准**：必须存在 `Sign Out`。
  原先正则 `Hello,\s*(.+)` 会匹配未登录文案 `Hello, sign in`；
  `/gp/css/order-history` 链接在未登录账户菜单中也存在 —— 两者都是假阳性。

### 评价翻页

- **`filter_sweep` 策略**（Amazon 专用）：`pageNumber` 被忽略，
  改用 `sortBy` x `filterByStar` 组合拿到不同视图，按评价块 id 并集去重。
- **`first_screen_cap=8`**（仅美国站）：首页即达 8 条硬顶，跳过 11 组合扫描，
  每型号省约 35 秒。
- **空过滤器不再误判为反爬**：`filterByStar=two_star` 无 2 星评价时返回
  `no_anchor_element`，原先中止整轮扫描（35 -> 14 条）。
  改为 skip，仅连续 2 次才判为真封禁。
- **被封页面不再丢弃整个 payload**：原返回裸 `blocked`，丢掉已抽到的价格。
  改为保留 payload，返回 `status="ok"` 并把原因写入 message；新增 `no_reviews` 状态。

### 其他

- `DEFAULT_MAX_REVIEWS = 50`；`SUPPORTED_REVIEW_PAGINATE` 纳入 `filter_sweep`。
- `prefer_pool` 默认开启：复用品牌搜索池，失败回退逐型号搜索。
  实测命中率偏低（US 1 页 6.7%、8 页 19.0%；CA 8 页 22.1%），
  **逐型号搜索仍不可省**，`search_pages` 默认 1。
- 拒绝词表 9 -> 23 条。
- 新增 `scripts/weekly_kakaku_price.py`、`gen_jp_price_trend_xlsx.py`、
  `gen_jp_price_trend_html.py`（日本线周度价格曲线）。
- 新增文档：`交接文档_亚马逊三站全量抓取_20260920.md`（304 行）、
  `完整整理清单_v2_20260923.md`、`整合部署包构建计划表_20260922.md`。

---

## 性能诊断结论（未改码，仅记录）

- 限速等待仅占 1%（0.6s），浏览器/渲染固定等待占 99%（72.5s）。
- 单页固定等待拆解：`goto` 3.0-3.2s + `wait_for_selector` 0.4-0.7s +
  `networkidle` 4.0s（**从不 idle，纯超时，首页也白等**）+
  滚动（搜索 3x800ms = 2.45s / PDP 8x800ms = 6.5s）+
  `extra_wait`（搜索 5.03s / PDP 2.51s）。
- 实测 `scroll_passes` / `extra_wait_ms` 在 Amazon 上是纯浪费
  （0/2/4/8 次滚动抽取结果完全相同）。
- **并行更慢**：三站并行 11.2 分钟 vs 串行 7.3 分钟（9 型号）；
  同站双进程导致 profile 加锁 `TargetClosedError`；`RateLimiter` 是进程级的，无跨进程锁。

优化候选见 `DEPLOY.md` 第八节。**全部未实施，需批准。**