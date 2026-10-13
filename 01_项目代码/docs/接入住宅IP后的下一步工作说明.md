# 接入住宅 IP 后的下一步工作说明

> 适用对象：拿到**住宅/移动**出口线路之后，负责把北美零售线（价格 + 网评）跑通的人。
> 前置阅读：`docs/北美零售站反爬分类_2026-09-20.md`（18 站逐个判定与归因）、
> `docs/零售线现状问题与北美抓取任务表.md`、`跨国家线复用与开发指南.md`（红线）。
>
> **一句话**：先花 10 分钟证明"线路真的改变准入"，再花 1–2 天校准 2 个站的
> RetailSpec，最后才谈全量。**不要拿到代理就直接跑全量。**

---

## 0. 现状交接（你接手时的起点）

| 项 | 状态 |
|---|---|
| 需住宅/移动代理的站 | **7 个**：`walmart_us` `walmart_ca` `walmart_mx` `sams_mx` `bestbuy_ca` `visions_ca` `coppel_mx` |
| 无需代理（已验证可抓） | 9 个：`amazon_ca/us/mx` `costco_ca` `thebrick_ca` `leons_ca` `canadiantire_ca` `liverpool_mx` `palacio_mx` |
| 有配置遗留 | `bestbuy_us`（缺 `supports_retail` / `parse_search`）、`costco_us`（scroll 已修） |
| 型号清单 | `data/美国/SPEC_型号汇总_US_20260914.csv`（405）、`data/加拿大/SPEC_型号汇总_ca.csv`（621）、`data/墨西哥/SPEC_型号汇总_MX_20260915.csv`（204） |
| 准入诊断工具 | `scripts/probe_na_retail_access.py`（含 `--selftest` 离线自检 6 用例） |

**拦截形态回顾**（决定"换什么线路"）：

| 站 | 形态 |
|---|---|
| `walmart_us` / `walmart_ca` / `walmart_mx` / `sams_mx` | PerimeterX 人机挑战（标题即 `Robot or human?` / `Verify Your Identity` / `Verifica tu identidad`） |
| `bestbuy_ca` / `coppel_mx` | 403 + 300 字节级 `Access Denied`（CDN/WAF 机房段拒绝） |
| `visions_ca` | 403 + Cloudflare `Just a moment...` |

---

## 1. 第一步：把代理接对（30 分钟，别跳）

### 1.1 配置方式

抓取器解析代理的优先级（`overseas/infra.py::resolve_proxy`）：

```
显式参数  >  OVERSEAS_PROXY  >  HTTPS_PROXY / HTTP_PROXY / ALL_PROXY
```

**统一用 `OVERSEAS_PROXY`**（HTTP 与浏览器两条抓取路径都会读它）：

```powershell
# HTTP 代理
$env:OVERSEAS_PROXY = "http://<user>:<pass>@<住宅代理域名>:<port>"
# SOCKS5（Playwright 支持；注意 HttpFetcher 走 urllib，SOCKS 需 PySocks）
$env:OVERSEAS_PROXY = "socks5://<user>:<pass>@<host>:<port>"
```

### 1.2 ★ 必须检查"系统代理"这个坑（本次会话踩过）

Windows 的系统代理若被 VPN 客户端残留设置成 `127.0.0.1:7877`，而该客户端已退出，
则 **Chromium 会走系统代理 → 全部请求报 `ERR_PROXY_CONNECTION_FAILED`**，
且直连也不通（DNS 正常但 TCP 全挂）。排查与处置：

```powershell
# 查系统代理
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" |
  Select-Object ProxyEnable, ProxyServer, AutoConfigURL
```

- 若住宅 IP 是**系统级 VPN**：让系统代理指向它即可，**不要**再设 `OVERSEAS_PROXY`
  （设了会变成"代理套代理"）。
- 若住宅 IP 是**HTTP/SOCKS 代理**：设 `OVERSEAS_PROXY`，并**清掉系统代理残留**
  （`ProxyEnable=0`），避免 Chromium 用错线路。

> 本会话**没有改动**用户的系统代理设置。改注册表前请先与设备 owner 确认。

### 1.3 验证线路（不碰目标站，先看出口）

```powershell
$env:PYTHONIOENCODING='utf-8'
py -3.12 -c "import urllib.request,json;print(json.load(urllib.request.urlopen('https://ipinfo.io/json')))"
```

**要确认两件事**：

1. **国家**：`walmart_us`/`bestbuy_us` 要 US，`walmart_ca`/`bestbuy_ca`/`visions_ca` 要 CA，
   `walmart_mx`/`sams_mx`/`coppel_mx` 要 MX。
2. **类型**：`org` 不能是机房/云厂商（前一版线路是 `AS46844 Sharktech`，就是机房段，
   被整段拒绝）。住宅线路的 `org` 通常是本地 ISP（Comcast / Bell / Telmex 等）。

### 1.4 ★ 先验证"一条 US 住宅线路能否解开全部 7 站"

**建议顺序：先只拿一条美国住宅线路，复测全部 7 站。** 依据是：加拿大/墨西哥的
**其他站在美国 IP 下完全正常**（`thebrick_ca`/`leons_ca`/`costco_ca` 等），
说明这些国家**普遍不做地理封锁**，那 7 站被拦更可能是**机房 IP 信誉**问题。

- 若 7 站全部解开 → **一条美国住宅线路就够**，成本最低。
- 若 CA/MX 站仍被拦 → 再补 CA / MX 住宅线路（此时才需要分国家线路）。

---

## 2. 第二步：复测准入（10 分钟，**不要直接跑全量**）

```powershell
$env:PYTHONIOENCODING='utf-8'
# 先跑离线自检，确认工具本身没问题
py -3.12 scripts/probe_na_retail_access.py --selftest

# 再复测 7 个站（workers=1 最稳；≥2 会因并发抖动出假拦截）
py -3.12 scripts/probe_na_retail_access.py `
  --sites walmart_us walmart_ca walmart_mx sams_mx bestbuy_ca visions_ca coppel_mx `
  --phase browser --workers 1 --scroll 12 --wait-ms 12000
```

**验收口径**（逐站）：

| 期望 | 说明 |
|---|---|
| `OK` 或 `OK_NO_CONTENT` | 页面通了。`OK_NO_CONTENT` 表示站点解析器 0 候选 → 去 §3 校准选择器 |
| 不再出现 `BLOCKED(...)` | 仍 `BLOCKED` 的站说明该线路无效，**别硬跑** |
| `HTTP_403` | 线路仍被拒 |
| `SUSPECT_FALSE_POSITIVE` | 多半是选择器/marker 误报，按工具打印的**命中偏移 + 上下文**判断 |

> **建议跑 2–3 轮**：站点会间歇（`palacio_mx` 曾一轮 Cloudflare 403、其余轮正常）。
> 单轮结论不足以定案。

---

## 3. 第三步：分成两条路走（**关键决策点**）

7 个站不是一个抓法。

### 3.1 Best Buy 系（`bestbuy_ca` / `bestbuy_us`）→ **走 sitemap 确定性路径，不要走搜索**

**原因**：两家 Best Buy 的 `robots.txt` **都禁抓站内搜索**
（`bestbuy.ca: Disallow: /en-ca/search`、`bestbuy.com: Disallow: */site/searchpage.jsp?st=*`），
而 `crawl_ca_retail.py` 的主路径正是"搜品牌 → 匹配候选 → 开 PDP"。

项目已为此建好确定性链路（**优先用它**）：

```powershell
# 1) sitemap → 本地商品目录（确定性："这个型号有没有上架"）
py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca build
py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca match

# 2) 直连 PDP 抓价格 + 网评（不经过搜索）
py -3.12 scripts/crawl_bestbuy_direct.py --site bestbuy_ca `
  --match-csv data/加拿大/bestbuy_ca_match_all.csv --limit 5
```

这条路顺带解决了原始需求里的两个痛点：
- **不会误抓**：候选来自目录里型号**完全匹配**的那条 SKU，不是"搜索前几条"；
- **没有"搜不到"歧义**：型号不在目录 = 确实没上架，是确定性结论；
- **没有死循环**：无搜索重试，只有 PDP 级失败计数 + 站级熔断。

> **合规提醒**：`bestbuy_ca/adapter.py` 里有 `search_allowed_by_robots = False`，
> 但 **`crawl_ca_retail.py` 目前并不读取这个标志**（`ensure_allowed` 只在
> `mx_retail.crawl_model_on_site` 里被调用，CA/US 线**没有合规闸**）。
> 在补上硬校验之前，**请用人/流程保证** Best Buy 不走搜索路径。

### 3.2 Walmart 系 + `sams_mx` + `coppel_mx` + `visions_ca` → **走搜索路径 + RetailSpec 校准**

这些站可用常规链路（搜品牌 → 候选匹配 → 同页抽价格+网评）：

```powershell
py -3.12 scripts/crawl_ca_retail.py --region us --sites walmart_us `
  --spec docs/retail_specs/walmart_us.retail.json `
  --models-csv "data/美国/SPEC_型号汇总_US_20260914.csv" `
  --limit-models 3 --max-reviews 20
```

（`--spec` 提供后：搜索候选走配置化 `match_product`，匹配"宁缺毋滥"。）

---

## 4. 第四步：校准 RetailSpec（主要工作量在这里）

目标：把 `docs/retail_specs/<site>.retail.json` 的 `status` 从 `candidate` 升到
**`validated`**。**所有校准都是只读的，不写正式库。**

### 4.1 校准搜索页

```powershell
py -3.12 scripts/diag_retail_search.py --site walmart_us `
  --spec docs/retail_specs/walmart_us.retail.json `
  --keyword "Hisense tv" --scroll 20 --wait 10000 --dump data/_smoke
```

看三行输出：

| 输出 | 判读 |
|---|---|
| `[RES] ok=True blocked=False` | 准入通过 |
| `[RAW] container=... count=N` | **N=0 → 选择器失效（我们的 bug）**，不是"站上没有" |
| `[HITS] > 0` 且有合理标题 | `search.container` / `sku` / `title` 校准完成 |

`N=0` 时工具会打印前 10 个候选的 `href`/属性，据此改写 `spec.search.container`。

### 4.2 校准商品页（价格 / 评分 / 评价）

```powershell
py -3.12 scripts/diag_retail_pdp.py --site walmart_us `
  --url "<一个真实 PDP URL>" --spec docs/retail_specs/walmart_us.retail.json `
  --scroll 14 --wait 5000 --dump data/_smoke
```

**取价红线（已踩过，务必遵守）**：

> `Extractor` 是「**选择器优先、JSON-LD 兜底**」。若 `price.price` 里留了 CSS 选择器，
> 页面上的**推荐位/配件轮播价会先命中**并绕过价格区校验——
> 这正是 Amazon `32A4NV` 把 $9.49 配件价记成电视价的同一形态。
>
> **约定**：`price.price` **只写 `jsonld`**；CSS 兜底交给
> `overseas/sites/walmart_common.py::pick_price_text()`（强制过祖先链价格区校验，
> 拿不到判定就留空——**缺价优于错价**）。
> `walmart_us.retail.json` 已是这个写法，照它抄。

同理：`summary` 不要用 `[itemprop='ratingValue']` / `[itemprop='reviewCount']`——
评价卡内部也用这两个属性，而 Extractor 取**文档顺序第一个**，会把某条评价的星级
当成整机均分。

### 4.3 评价拿不到时：先找接口，再改 DOM

商品页 DOM 里没有评价明细时，别急着调选择器：

```powershell
py -3.12 scripts/diag_retail_network.py     # 捕获真实网络请求，定位评价/价格接口
py -3.12 scripts/diag_bv_api.py             # BazaarVoice 站（Costco 系）
py -3.12 scripts/diag_costco_reviews.py     # Costco 评价专项
```

若确认走接口，在 spec 里配 `reviews.source`（项目已有 `bazaarvoice_bfd` 分支，
见 `overseas/bv_reviews.py` 与 `crawl_ca_retail._collect_reviews`）。

### 4.4 评价翻页与去重

```jsonc
"paginate": { "reviews": { "type": "click_more", "click_selector": "button[aria-label*='more']",
                           "click_repeats": 10 } },
"incremental": { "stop_when": "page_all_known" }
```

- `type` 可选：`url_page` / `query_param` / `click_more` / `none`（白名单见 `retail_spec.py`）。
- `reviews.fields.review_key` **必填**（校验红线）：没有站内 id 就用 `self_attr` 取 id，
  取不到时 `Extractor` 会退化成**内容哈希**——同一用户改个标点就会重复入库。
  Walmart 当前就是这种退路，**校准时要确认是否有稳定的站内评价 id**。

### 4.5 改完跑回归

```powershell
py -3.12 scripts/retail_spec_tests.py        # 全绿才能继续（含"真实 spec 逐个静态校验"）
```

---

## 5. 第五步：小样本验证（**必须先过这一关**）

**3–5 个型号，且必须包含一个"确定该站没有"的型号**（这是验证匹配逻辑的唯一办法）。

```powershell
py -3.12 scripts/crawl_ca_retail.py --region us --sites walmart_us `
  --spec docs/retail_specs/walmart_us.retail.json `
  --brand hisense_us `
  --models "55U7SG" "65U8QG" "一个确定没有的型号" `
  --max-reviews 20 --out-dir data/_smoke
```

> `--models` 显式给型号时**必须同时给 `--brand`**（品牌 code，如 `hisense_us`）：
> 否则品牌为空，搜索关键词会退化成裸型号、且匹配阶段拿不到品牌词。
> 走 `--models-csv` 时品牌来自清单，不需要这个参数。

**验收清单（逐条打勾）**：

- [ ] **有货型号** → `ok`，价格非空，评价条数 > 0
- [ ] **没有的型号** → `no_item`，且 message 带可核对原因
      （`explain_no_match` 会区分：搜索页无候选 / 没有这个系列 / 尺寸不符 / 被 reject 规则误伤）
- [ ] **绝不能**把"抓取失败"记成 `no_item`；`failed` 必须如实记 `failed`
- [ ] **价格人工比对**：打开那个 PDP，肉眼核对标题型号与价格（**红线**）
- [ ] **无重复评价**：同一型号内 `review_key` 无重复
- [ ] **状态计数守恒**：`ok + no_item + no_price + no_reviews + failed + blocked == 输入型号数`
- [ ] 无 `blocked`

只要有一条不过，**回 §4 继续校准**，不要放大样本。

---

## 6. 第六步：全量（分批 + 熔断）

```powershell
py -3.12 scripts/crawl_ca_retail.py --region us --sites walmart_us `
  --spec docs/retail_specs/walmart_us.retail.json `
  --models-csv "data/美国/SPEC_型号汇总_US_20260914.csv" `
  --max-reviews 100 --save-db
```

**运行纪律**：

1. **一个站一个站开**：`regions_config.py` 里逐站 `enabled=True`，每次只动一个，
   跑完看状态再开下一个。
2. **分批**：单批次控制在 **≤35 个型号**，批间加冷却
   （`liverpool_mx` 曾因连续 200+ 型号触发 `410 Gone`，IP 被临时拉黑）。
3. **不放宽限速**：`OVERSEAS_MIN_INTERVAL`（默认 6s）与站点 `suggested_interval`
   （Walmart/Amazon 是 8–10s）是反爬约束的下界，拦截后的退避代价远高于省下的等待。
4. **盯站级熔断**：连续 5 个型号 `blocked`/403/410/429 会自动跳过该站剩余型号。
   一旦触发 → **停手，换线路或降频**，不要重跑硬撞。
5. **不并发写同一个 SQLite**（写锁竞争 + 审计交叉污染）。

---

## 7. 第七步：验收与交付

- **状态计数守恒**（同 §5）。
- **抽检 20 个型号零误匹配**（红线）。
- **导出格式对齐日本线**：网评走 `review_export.COLUMNS`（20 列固定），
  价格走 `price_export` / `price_export_ca`。
- **产物落 `data/<国家>/`**（`data/美国/`、`data/加拿大/`、`data/墨西哥/`）。
- **审计只增不改**：不删历史 `running` 记录来"让统计变好看"。

---

## 8. 红线清单（本会话新增，违一条就会出数据事故）

1. **不要只用纯 HTTP 探测给站点定性。** 18 站里有 **9 站**在 HTTP 下表现为"被拦"、
   浏览器下完全正常（`amazon_ca/us/mx`、`canadiantire_ca`、`palacio_mx`、
   `thebrick_ca`、`leons_ca`、`costco_ca`、`costco_us`）。
   定性必须走浏览器 + 站点自己的 `BlockDetector`（含 allowlist）。
2. **不要只看 marker 命中。** `captcha` 在正常页里极常见（CSP 声明、reCAPTCHA 脚本）。
   必须看**命中偏移 + 上下文 + 页面体积 + 业务内容**交叉判断。
3. **★ 加 `block_marker_allowlist` 之前，先确认真实拦截仍能被别的标记抓到。**
   本会话实测：给 `sams_mx` 豁免 `captcha` 后，它的 PX 挑战页（标记 `px-captcha`，
   **`captcha` 是其子串**）被一起豁免，`blocked` 从 `True` 变 `False` → 真实拦截被
   "消音"，下一步会被记成 `no_item`（静默丢数据）。
   已补 `verify your identity` / `verifica tu identidad` 两条标题标记作为安全网。
4. **HTTP 404/410 优先于 blocked**（项目既有红线，本会话又踩一次）。
5. **并发会制造假拦截。** `workers≥2` + 大滚动时出现过 `len=0 / no_anchor_element`，
   `workers=1` 复测全部正常 → 那是抖动，不是站点拦截。
6. **站点会间歇**：`palacio_mx` 有一轮 Cloudflare 403、其余轮正常。关键站跑 2–3 轮。
7. **往 `_BLOCK_MARKERS` 加文案前，先确认它不会出现在正常页。**
   `perimeterx`/`datadome`/`captcha` 这类词都是正常页常客，直接加会造成误报。
8. **`parse_search` 必须在 `with open_dom(...)` 上下文内调用**。
   页面关闭后再解析会恒返回 0 候选（本会话工具踩过），进而把
   "选择器坏了"误判成"该站没有"。

---

## 9. 待补的工程项（与线路无关，可并行做）

| # | 项 | 位置 | 影响 |
|---|---|---|---|
| 1 | CA/US 线接**合规闸**（`ensure_allowed`） | `scripts/crawl_ca_retail.py` | 目前 CA/US 线不校验白名单/robots；`bestbuy_ca.search_allowed_by_robots=False` 也没被读取 |
| 2 | `bestbuy_us` 补 `supports_retail` + `parse_search` | `overseas/sites/bestbuy_us/adapter.py` | 否则启用后会被当"非零售站"**静默跳过**（打 `[SKIP]` 且不写状态） |
| 3 | `walmart_ca` 改用 `walmart_common` 护栏 | `overseas/sites/walmart_ca/adapter.py` | 它仍在用裸 `jsonld_product_payload`，没有取价护栏 |
| 4 | `sams_mx` 的 `supports_retail` | `overseas/sites/sams_mx/adapter.py` | 现走 MX 线（`mx_retail` 不检查该标志），暂无影响；若改走 CA/US 线会被跳过 |

---

## 10. 时间与顺序建议

| 阶段 | 内容 | 预估 |
|---|---|---|
| 0 | 接线路 + 验证出口 + 复测 7 站 | 0.5 天 |
| 1 | Best Buy 走 sitemap 路径，小样本跑通 1 个站 | 0.5 天（链路已建好） |
| 2 | Walmart 系选 1 个站（建议 `walmart_us`）校准 spec → `validated` | 1 天 |
| 3 | 小样本验证（含"确定没有"的型号） | 0.5 天 |
| 4 | 全量（405 型号，分批） | 1 天（含限速等待） |
| 5 | 其余 5 站复用同一套流程 | 每站 0.5–1 天 |

**不要**一上来就 7 站全量。先把 **1 个 Walmart 站**打到 `validated` 并跑出干净的小样本，
把 spec 写法与验收口径固定下来，后面 5 站就是复制。

---

## 11. 故障处置速查

| 现象 | 先查 | 处置 |
|---|---|---|
| 浏览器全报 `ERR_PROXY_CONNECTION_FAILED` | 系统代理残留 / 代理客户端是否在跑 | 清系统代理或重启客户端（§1.2） |
| 全部站点 `blocked` | 出口 IP 国家/类型 | 换住宅线路；机房段整段被拒 |
| 单站 `blocked` 但其他站正常 | 该站的挑战形态 | 该站需要更"干净"的住宅 IP 或更低频 |
| 搜索页 `0 候选` 且 `[RAW] count=0` | spec 选择器 | 按 dump 的 HTML 改 `search.container` |
| 有价格但价格明显偏低 | 取价走了 CSS | 改为 JSON-LD 优先（§4.2 红线） |
| 评价恒 0 条 | 评价是否走接口 / 是否懒加载 | 用 `diag_retail_network.py` 定位，或加大 `scroll_passes` |
| 连续 5 个型号 blocked | 站级熔断已触发 | 停手换线路/降频，别硬撞 |

---

*本文与 `docs/北美零售站反爬分类_2026-09-20.md` 配套：那份讲"是什么/为什么"，
本文讲"拿到线路后怎么做"。执行中若发现新的反爬形态或误判模式，
请补进本文 §8 红线与分类文档的对应章节。*
