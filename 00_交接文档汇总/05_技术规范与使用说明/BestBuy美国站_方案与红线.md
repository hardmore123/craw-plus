# Best Buy 美国站（bestbuy.com）价格 + 网评抓取方案

> 主题：**能否参照加拿大 Amazon 线的经验，处理美国 Best Buy 的网评与价格抓取**
> 日期：2026-09-20
> 结论依据：`overseas/retail_spec.py`、`scripts/crawl_ca_retail.py`、`overseas/bv_reviews.py`、
> `overseas/sites/amazon_common.py`、`docs/retail_specs/{amazon_ca,costco_us,bestbuy_us}.retail.json`、
> `overseas/sites/bestbuy_us/{adapter.py,schema.json}` 逐一核查，**不含推测**。

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 能否参照加 Amazon 的经验？ | **能，约 70% 框架级直接复用**（spec 执行层 / 三段匹配 / 增量去重 / 熔断 / 导出格式） |
| 需要重做的部分 | **3 处**：网络出口、网评后端、搜索与 PDP 选择器（现有 bestbuy_us spec 从未在真实 DOM 校准过） |
| "某些型号搜不到"能否避免误抓？ | **能**，但要靠"四类归因 + 四道闸"，核心是把 **no_item 与 failed 严格分开**（见 §3、§4） |
| 能否避免死循环？ | **能**，复用已落地的终止条件表 + 为 Best Buy 增补 3 条（见 §5） |
| ★合规上有没有问题？ | **有，需要业务方拍板**：`robots.txt` 明确 **`Disallow: */site/searchpage.jsp?st=*`**（站内搜索页禁抓），ToS 亦禁止用自动化工具导航/搜索其站点——而本方案的批量搜索正依赖该路径。**建议改走官方 sitemap（`sitemaps_bsin`/`sitemaps_pdp`）做确定性 SKU 发现**，既绕开冲突又更准。详见 **§2.4** |
| 现在能不能开抓？ | **不能**。★根因已查明并**不是 Best Buy 反爬**：本机所在的**公司内网准入网关**（`10.18.0.250/disable/disable.htm`，白名单名"工业设计白名单"）直接拦掉了 bestbuy.com，HTTPS 还被企业根证书做中间人（`SEC_E_UNTRUSTED_ROOT`），出口 IP 是中国（27.223.99.190）。硬前置是**能出网的美国住宅 IP**（见 §2.1） |

> ★ 一句话：**经验和代码可以直接搬，卡点有三层：① 合规（搜索页被 robots 禁抓，需业务方决定走
> sitemap 还是授权）；② 网络（本机出不了网且出口 IP 不是美国）；③ 校准（选择器全部未验证）。
> 在拿到美国线路之前，只做"零网络"的部分（spec v0.2 + 校准脚本 + 本文档），
> 不做无谓的连通性重试，更不要拿本机的失败去调 Best Buy 的反爬策略。**

---

## 1. 加拿大 Amazon 线到底积累了哪些经验（可迁移清单）

| # | 经验 | 代码落点 | 对 Best Buy US |
|---|---|---|---|
| 1 | **spec 驱动的统一执行层**：搜索 → 候选匹配 → PDP → 同步抽价格+评价 → 增量去重 → 归国导出 | `crawl_ca_retail.py --region us --spec bestbuy_us.retail.json` | ✅ **直接复用**，一行命令换区换站 |
| 2 | **三段匹配**：精确（词边界）→ 主干（尺寸守卫）→ None | `retail_spec.match_product` | ✅ 直接复用，需补 `core_size_tokens` |
| 3 | **reject 配件词表**：先剔 mount/stand/case/bracket/adapter | `match.reject.title_contains_any` | ✅ 复用并**加开盒/翻新词**（§4.1） |
| 4 | **尺寸守卫**：`65" Class - U7SG Series` 这类分隔式写法也要认，防 55 吋价记到 75 吋头上 | `match.verify.core_size_tokens` + `_candidate_sizes` | ✅ **必须配**（Best Buy 标题同样写法） |
| 5 | **详情页权威型号校验**：`product.model_candidates` 非空时**只认精确相等**，不等直接否，不退回标题子串 | `_payload_matches_model` | ✅ 复用；需给 Best Buy 补 model_candidates 抽取（§4.3） |
| 6 | **品牌级批量搜索**：一个品牌只搜一次"`{brand} tv`"，型号从候选池里映射；池里没有 → no_item，**不再为该型号单独搜索** | `search.batch{force, fallback_per_model:false}` | ✅ **强烈建议**。Best Buy 搜索页慢，405 个型号逐个搜等于自杀 |
| 7 | **"搜不到"四类归因**：无候选 / 该系列没有 / 同系列尺寸不符 / 全被 reject 排除 | `explain_no_match` | ✅ **直接复用**，这是本任务的核心工具 |
| 8 | **增量去重**：`review_key` + `page_all_known`，全已知即停 | `collect_reviews_paged` | ✅ 直接复用 |
| 9 | **评价翻页四型**：`url_page` / `query_param` / `click_more` / `none`，外加 Amazon 专用 `filter_sweep`（sortBy×filterByStar 组合扫，突破首屏） | `collect_reviews_paged` | ⚠️ **类型待定**，取决于 Best Buy 后端（§2.2） |
| 10 | **BazaarVoice 接口取评价**：`apps.bazaarvoice.com/bfd/v1/...`，只要 `Bv-Bfd-Token` + `Origin` 两条就能通，纯 HTTP 可取 | `bv_reviews.py` | ⚠️ **待确认是否适用**；若适用则零成本接入 |
| 11 | **BV 按系列聚合的串尺寸风险**：用 55 吋商品号查会返回 75 吋的评价 | `cross_product` + `#bv-src-product=` 溯源 | ✅ **教训直接适用**：任何评价来源都要能溯源到真实商品号 |
| 12 | **价格区校验（32A4NV 事故）**：buybox 无主价时，页面 18 个 `.a-price` 全来自配件轮播，兜底选择器把配件价当电视价（$9.49，且每次跑都漂移） | `amazon_common.price_in_region` | ✅ **教训直接适用**：Best Buy 同样有推荐位/配件轮播价，必须做祖先链校验，**拿不到判定时保守拒绝** |
| 13 | **站级熔断**：连续 5 个型号被拦即跳过该站剩余型号 | `blocked_streak_limit` | ✅ 直接复用（405 型号的必需品） |
| 14 | **登录墙 ≠ 反爬**：`not_logged_in` 单独计数并提示补登录态，不撞熔断 | `crawl_site` 内 `login_wall_streak` | ⚠️ Best Buy 评价是否需要登录待验 |
| 15 | **评价条数上限**：单型号单站 ≤50 条（`DEFAULT_MAX_REVIEWS`），四级优先级 CLI > spec > env > 默认 | `resolve_max_reviews` | ✅ 直接复用 |

**结论**：第 1~9、12~15 项是**框架级资产，换站即可用**；只有第 10、11 项的"BV 具体形态"和
第 9 项的"翻页类型"需要按 Best Buy 真实后端定。

---

## 2. 三处必须重做（不能照搬）

### 2.1 网络出口：Amazon CA 是"能连但怕封"，Best Buy US 是"本机根本出不了网"

| 站点 | 当前环境的表现 | 需要的条件 |
|---|---|---|
| `amazon_ca` | 可抓（有登录态，低频） | 低频 + 登录态（已解决） |
| `bestbuy_us` | **本地网关白名单直接拦掉**；且出口 IP 是中国 | **能出网的美国出口 IP** |

**★根因必须分清，否则会往错误方向调优（本机 2026-09-20 实测）**：

| 现象 | 真实原因 |
|---|---|
| 请求被 302 到 `http://10.18.0.250/disable/disable.htm?url_type=访问网站/工业设计白名单` | **公司内网准入网关白名单**，与 Best Buy 无关 |
| `curl` HTTPS 报 `schannel: SEC_E_UNTRUSTED_ROOT`，`http_code=000` | 企业根证书**中间人**，与 Best Buy 无关 |
| 出口 IP `27.223.99.190`（中国） | 即使网关放行，也是**非美国 IP** |

> ★ **不要用本机的失败去推断 Best Buy 的防护强度**。本机的超时/TLS 失败是公司网络
> 造成的，不是 Akamai、不是 403、不是验证码。据此调"反爬处理"是无效工作。

**★★ 非美国 IP 的真实表现是 HTTP 200，不是 403**（外部实测证据，urlscan 存档的
德国/瑞士/捷克节点扫描）：同一个 bestbuy.com URL 返回
**HTTP 200** + `<title>Best Buy International: Select your Country - Best Buy</title>`。

这带来一个必须处理的后果：
**只判状态码会漏判**，会把"拿到国际选择页"当成"搜索页选择器失效"，进而把 405 个型号
全判成 `no_item`（静默丢数据）。已落地的两个应对：

1. `overseas/infra.py` 的 `_BLOCK_MARKERS` 增加 `best buy international`
   → 该页会被识别为 `blocked`（`marker:best buy international`），触发正确的站级熔断，
   而不是伪装成"0 候选"。（已验证：国际页 → `blocked=True`，正常 PDP → 不拦截）
2. `overseas/sites/bestbuy_us/adapter.py` 提供 `is_country_splash(title, html)`，
   以及搜索 URL 带 `intl=nosplash`（抑制国际选择页插屏）。

**其他已确认的 URL 事实**（外部实测，本地待现场确认）：搜索翻页用 `cp=N`（`?cp=2`/`?cp=3`），
每页 18 条、页码上限 100；PDP 新增 `/product/<slug>/<10 位码>/sku/<skuId>` 形态，
旧形态 `/site/<slug>/<skuId>.p?skuId=<skuId>` 仍可用。

配置方式已就绪：`OVERSEAS_PROXY=http://...`（`config.PROXY` / `deploy/overseas.env.example`），
`diag_retail_network.py` 已支持把代理传给浏览器。

### 2.2 网评后端：**不要假设是 BazaarVoice**，主线是站内原生评价页

现有 `bestbuy_us.retail.json` 的 `reviews` 段是**从未验证的草案**（`status: candidate`）。
开工前必须用 `scripts/diag_bestbuy_us.py --only reviews` 实测定类。

**先验证据（外部，截至 2026-09）**：

| 证据 | 结论 |
|---|---|
| urlscan 里 `domain:api.bazaarvoice.com AND page.domain:www.bestbuy.com` → **0 命中** | 评价**没有**走 BV 的 `api.bazaarvoice.com` |
| `apps.bazaarvoice.com` → 0 命中；页面出现 bazaarvoice 域名的最后记录是 **2022-12** | 历史用过、现在大概率不用了 |
| 存在站内原生评价页 `https://www.bestbuy.com/site/reviews/<slug>/<skuId>`，20 条/页，页面写 `Page 1 Showing 1-20 of 47` | ★**主线路径** |

> ★ 所以 §1 清单里的第 10 项（复用 `bv_reviews.py`）**用不上**。这不是坏消息：
> 最佳路径是**一手 JSON 接口**（纯 HTTP、不用渲染浏览器），比 BV 还省事。

判定表（四类，决定 spec 怎么填）：

| 类型 | 判定特征 | 接入方式 |
|---|---|---|
| **B 站内一手 JSON 接口（首选候选）** | `https://www.bestbuy.com/ugc/v2/reviews?page=1&pageSize=20&sku=<SKU>&sort=MOST_RECENT`，返回 `totalPages` / `topics`，**不需要渲染 JS** | 需新写一个 source 分支（结构参考 `bv_reviews.fetch_bv_reviews`）。★响应 schema 与 `pageSize` 上限**未实测**；`/ugc/v1/` 无任何证据，不要用 |
| **C 站内原生评价页（兜底，且最稳）** | `/site/reviews/<slug>/<skuId>`，SSR，20 条/页，页面写 `Page 1 Showing 1-20 of 47 reviews`；`?rating=1-5` 已实测；排序 `Most Relevant/Most Helpful/Most Recent/Oldest/Highest Rating/Lowest Rating` | `url_page` 或 `query_param`。★翻页参数名中等把握是 `page`+`pageSize`；**不要复用 `cp`（那是搜索页的参数）**。★此页**未被 robots 禁抓** |
| A `bazaarvoice_bfd` | 仅当实测抓到 `apps.bazaarvoice.com/bfd/v1/clients/<client>/...` 且带 `Bv-Bfd-Token` | 复用 `bv_reviews.py`（**当前证据下几乎不可能**） |
| D 客户端挂件需点击 | 首屏有、滚动或点击后增长 | `click_more`（配 `click_selector` + `click_repeats`） |

**三条已确认的运营事实**：
- **评价不需要登录** —— 游客态就能看到完整评价正文、用户名、`Verified Purchase` 徽章、星级直方图与 AI 摘要。
- **但必须美国 IP** —— Akamai Bot Manager（`ak_bmsc`/`bm_s`/`bm_so`/`_abck`）+ Google reCAPTCHA（`_GRECAPTCHA`）；
  数据中心 IP 通常几个请求内就被挑战。且**不能只靠 IP**：有美国 IP 也被送国际选择页的实例，
  必须同时带 `intl=nosplash` 并按标题识别。
- **聚合评分来源**：首选 SSR Apollo 载荷 `product-info.reviewInfo = {averageRating, reviewCount}`（实测样本 4.9 / 2913）；
  网格卡片用 `div.c-ratings-reviews p.visually-hidden` + 正则 `Rating ([\d.]+) out of \d+ stars with ([\d,]+) reviews?`，
  无评分哨兵文案是 `Not Yet Reviewed`。**JSON-LD `aggregateRating` 证据互相冲突，未实测前不要依赖。**

> ★ 在确认之前**不要往 spec 里写死任何评价选择器**——项目既有红线：
> "未验证的配置有害"（`amazon_ca.retail.json` 里 `_summary_extra` 已明确写过"不写入未验证的选择器"）。

### 2.4 ★合规问题（必须由业务方拍板，不能埋在技术方案里）

**这是本次调研最需要抬头看的一条，与抓取技术无关，但会决定项目能不能做。**

| 项 | 事实 |
|---|---|
| `robots.txt` | 通用爬虫组（`*` / `googlebot` / `bingbot` …）明确有 **`Disallow: */site/searchpage.jsp?st=*`** —— **站内搜索页被禁抓**；另有 `Disallow: /api/*.json`、`/browse-api/*`、`/pricing/*`、`/availability/*`、`/fulfillment/*`。**`/site/reviews/<slug>/<skuId>` 展示页未被禁；`/ugc/` 下没有任何规则** |
| 无 Crawl-delay | 未声明爬取间隔 → 需自行保守设置（本 spec 用 10 秒） |
| **使用条款** | Best Buy ToS 明确禁止使用任何引擎/软件/工具/代理/爬虫/机器人来导航或搜索其站点（第三方归档将其标注为 CFAA 相关条款） |

**由此产生一个直接冲突**：本方案 §3/§5 的"品牌级批量搜索"依赖 `/site/searchpage.jsp`，**而它正是 robots 明确禁止的路径**。

**三种处置，必须选一个并留痕**：

1. **改走确定性索引（技术上最优，且绕开 robots 冲突）**：
   Best Buy 自己发布站点地图 —— `sitemaps.bestbuy.com/sitemaps_bsin.xml`、`sitemaps_pdp.xml`
   （索引 → gzip 的 `sitemaps_pdp.NNNN.xml.gz`，每个 `<loc>` 就是一个规范 PDP URL），
   以及 `sitemaps_rnr`（ratings & reviews）。**用"sitemap 里有没有这个 SKU/BSIN"来判定
   "该站是否上架"，比模糊搜索更准、更省请求、也不碰被禁的搜索路径。**
2. 由业务方对 bestbuy.com 出具抓取授权。
3. 明确接受该风险并书面留痕。

> ★ 附带好处：走 sitemap 还能**同时解决** §3 的核心痛点 —— "某些型号搜不到"不再依赖
> Best Buy 的模糊搜索，而是"这个 SKU/BSIN 在不在官方索引里"的确定性问题。
> 建议优先验证这条路径（`scripts/diag_bestbuy_us.py` 的 `search` 项可扩展为 sitemap 探测）。

### 2.3 搜索与 PDP 选择器：现有 spec 是"反抽象草案"

- `overseas/sites/bestbuy_us/schema.json` 第 2 行自己写着：
  > "Best Buy 美国站抽取规则（**草案**）。需美国代理访问真实 PDP 后按实测 DOM 校准选择器"
- `bestbuy_us.retail.json` 的 `generated_by` 是 `"反抽象: sites/bestbuy_us/adapter.py + schema.json"`，
  即**从草案反推出来的配置**，从未命中过真实页面。
- 处理原则：保留这些选择器作为**候选链的第一项**，但显式标注 `_unverified`，
  校准后用实测值覆盖。**不在未验证的情况下宣称"已支持"**。

**★ 一条重要的正面证据（外部实测，urlscan 存档）**：Best Buy PDP 的**型号是服务端渲染**的，
HTML 里能找到 `Model:75Q651G` 与紧邻的 `SKU:6579448`，且型号会拼进 `<title>`
（`"... 75Q651G - Best Buy"`）。

这条证据直接决定了两件事：
1. **闸三（PDP 权威型号精确校验）可行** —— 不需要等 JS 渲染就能拿到权威型号，
   这也是 §4.5 把「闸三不可省略」定为结论的前提；
2. spec 里 `product.model` 的**整页 `regex` 兜底在这里是安全的**
   （`Model\s*[:：]\s*([A-Za-z0-9...]+)`）——注意这与"`search.sku` 不能配 regex"
   并不矛盾：PDP 是一个型号一页，整页正则只会命中那一个型号；搜索页是一页多型号，
   整页正则会让所有卡片退化成同一个 SKU（见 §4.6 陷阱二）。

---

## 3. "某些型号搜不到"——本任务的核心风险，必须分类处置

这是用户明确点出的问题。**"搜不到"不是一种情况，是五种**，混在一起就会误抓或静默丢数据。

| 类别 | 现象 | 正确状态 | 为什么 |
|---|---|---|---|
| **A 该站确实没上架** | 品牌搜索候选池里没有这个系列 | `no_item` | 北美零售站普遍卖**渠道专供型号**（Costco 上架 `55QD75SFC`，品牌官网清单是 `55QD7QF`）。核心串匹配不上是**正常结果** |
| **B 同系列有货但尺寸不符** | 池里有 `55U7N`，目标是 `75U7N` | `no_item` + 写明"站上只有 55/65，目标 75" | 归因可核对，人工一眼能判 |
| **C 搜索页没渲染 / 被拦** | 滚动不足只拿到 8 个候选、或 403/超时 | **`failed` 或 `blocked`** | ★★ **绝不允许记 no_item**——那会把"抓取失败"伪装成"该站没上架"，静默丢数据 |
| **D 候选全被 reject 规则排除** | 池里 20 条全命中黑名单 | `no_item` + "可能误伤，需核对 spec" | 这是**配置问题**，不是数据结论，必须让人看见 |
| **E Best Buy 特有：模糊命中错商品** | 搜索把 soundbar / 挂架 / **开盒机 / 翻新机** / 同系列别尺寸排在前面 | 由四道闸拦下（§4） | Best Buy 站内搜索是模糊匹配且混排广告位，直接取首条必错 |

**归因工具已存在**：`retail_spec.explain_no_match()` 已实现 A/B/C/D 的区分，并在
`crawl_ca_retail._crawl_one_batch` 里落进 `no_item` 的 message。Best Buy 接进来即可用。

> ★ **判定红线**：
> - 只有 **A / B / D** 允许产出 `no_item`；
> - **C 必须是 `failed`/`blocked`**（站级熔断会因此正确触发）；
> - `no_item` 的 message **必须带归因文本**，不许只写"未匹配"。

### 3.1 Best Buy 的具体识别方法（实测证据支撑）

Best Buy 的搜索是**广召回、不是精确匹配**，而且会**把广告混排进结果中间**。
实测一次 `st=samsung` 的真实返回：结果数文案 `Results for "SAMSUNG" (22401)`，
页脚 `1-18 of 22401 items`，列表里夹着 `Sponsored` 条目、厂商展厅广告块、
`Related Searches` 条，以及一个 `SIMILAR PRODUCTS FROM OUTSIDE OF BEST BUY` 块。
**查询词会被原样回显在标题里，所以"标题里有我的关键词"完全不能作为命中证据。**

因此 Best Buy 的"搜不到"必须按下面这套信号判：

| 信号 | 含义 |
|---|---|
| 解析 `Results for "<Q>" (<N>)` 与 `X-Y of N items`，**N=0 或列表容器 `ol.sku-item-list` 不存在** | 视为**真 miss** |
| 卡片上的 Model/SKU（`div.sku-model span.sku-value` 第 1 个值=Model、第 2 个=SKU；`li.sku-item[data-sku-id]`）与目标型号比对 | 不一致即**模糊命中**，丢弃 |
| 命中 `Sponsored` / `Related Searches` / 跨零售商块 | **不算命中** |
| 数据里 `search_information.did_you_mean` 非空 | 说明**查询被改写**，结果不可信（★该字段的 DOM 选择器未验证） |

> ★ **零结果页的确切文案目前无任何可用样本**（调研期间所有归档/代理路径都取不到）。
> **绝对不要凭猜测写死 "No results found" / "Check your spelling" 之类的判据**——
> 猜错会让"真 miss"永远判不出来，或把正常页判成 miss。这条必须在拿到美国线路后实测补齐。

> ★★ **更稳的做法是不依赖搜索**：用 Best Buy 官方 sitemap（`sitemaps_bsin` / `sitemaps_pdp`）
> 判断"这个 SKU/BSIN 在不在索引里"，把"某型号搜不到"从一个**模糊检索问题**变成一个
> **确定性存在性问题**。详见 §2.4。

---

## 4. 误抓防线：四道闸（依次收紧，任一道不过即丢弃）

### 4.1 闸一：候选层 reject 词表

在 `amazon_ca` 已有词表基础上，**针对 Best Buy 增补**：

```jsonc
"reject": {
  "title_contains_any": [
    // ── 通用配件（沿用 CA Amazon 经验）──
    "wall mount", "mount", "bracket", "stand", "case", "cover",
    "cable", "adapter", "screen protector", "soundbar", "projector",
    // ── ★ Best Buy 特有：会污染价格监控的成色/套餐 ──
    "open-box", "open box", "refurbished", "pre-owned", "preowned",
    "geek squad certified", "renewed", "used"
  ]
}
```

> 为什么加第二条：Best Buy 大量销售 **Open-Box / Refurbished**，同一型号会有多个 SKU 与更低价格。
> 若不剔除，价格监控会抓到"开盒价"而不是新品价——**这是 Best Buy 版的"32A4NV 配件价事故"**。
> 注意：**不要**把 `protection plan` / `bundle` 一律 reject（Costco US 的教训：延保打包进标题仍可能是真电视）。

### 4.2 闸二：尺寸守卫（`core_size_tokens`）

Best Buy 标题写法与 Costco 同构（`65" Class - U7N Series`），尺寸与系列被分隔词隔开，
紧贴式 `(\d{2,3})core` 永远不命中 → 守卫失效 → 65 吋被判成 75 吋。必须配：

```jsonc
"verify": {
  "core_size_tokens": ["class", "inch", "in", "\"", "series"]
}
```

### 4.3 闸三：详情页权威型号（防"看起来对"的错 SKU）

Best Buy 的商品页标题常只写营销名，**型号只出现在规格表 Model 行 / `data-testid`**。
所以必须走 `product.model_candidates` 精确相等（`_payload_matches_model` 已实现该语义）：
**有权威型号且都不等 → 直接否掉，不退回标题/URL 子串匹配。**

校准后需确认 Best Buy 的 model 抽取路径，可能的候选（**均为未验证，需实测**）：
`div.model span.product-data-value` / `[data-testid='model-number']` / 规格表 `Model` 行 / JSON-LD `mpn`。

### 4.4 闸四：价格区校验（防配件价 / 推荐位价 / 开盒价）

照搬 `amazon_common.price_in_region` 的思路，为 Best Buy 实现等价的祖先链校验：
**价格元素必须落在主价格容器内**（`priceView-hero-price` / `priceView-customer-price` 等），
祖先链里出现推荐位/配件轮播容器即拒绝。**拿不到判定时保守拒绝**——宁可判为空价，
也不把错价写进交付物（错数据比缺数据危害大）。

> 校准前的正确做法：先用诊断脚本把 PDP 上**所有**价格候选连同其祖先容器打印出来，
> 人工确认哪个是主价，再写成选择器。

### 4.5 Best Buy 特有的误抓入口：死 SKU 会 301 到**无关商品**

Best Buy 的旧形态 URL `/site/<skuId>.p?skuId=<skuId>` 会 301 到新形态
`/product/<slug>/<BSIN>/sku/<skuId>`。**但已下架/失效的 SKU 可能 301 到一个
完全不相关的商品，而不是返回 404。**

后果：如果代码把"URL 打开成功且有价格"当成"这个型号存在"，就会**把别的商品的
价格记到目标型号头上**——这是比"抓到配件价"更隐蔽的误抓。

**处置**：**"重定向成功"不能作为"型号存在"的证据**，唯一有效的是**闸三**——
PDP 上服务端渲染的 `Model:` 值与目标型号精确相等（或 `productBySkuId.skuId` 等于输入的 SKU）。
这正是为什么闸三在 Best Buy 上是**不可省略**的（也是 §4.6 允许 `min_core_len: 3` 的前提）。

### 4.6 离线实测发现的两个配置陷阱（本次已修，写在这里防止回退）

这两个坑**不需要网络就能复现**，是在把 spec 写出来、拿 405 条美国型号清单做离线匹配
验证时发现的。

#### 陷阱一：`min_core_len: 4` 会屏蔽 38/405 个美国型号（含主力系列）

用美国型号清单（`data/美国/SPEC_型号汇总_US_20260914.csv`，405 条）跑主干串长度分布：

```
主干长度 2 →  6 条   (hisense UX/MX 系列, samsung HW)
主干长度 3 → 32 条   (★ hisense 85U8N/75U8N/65U8N/…→ U8N、U7N、U6N)
主干长度 4 →104 条
主干长度 ≥5 → 其余
```

`match_product` 里有一条硬开关：`len(core) >= verify.min_core_len` 才会走主干匹配。
沿用加拿大 Amazon / Costco 的 `min_core_len: 4`，**U8N / U7N / U6N 这些 Hisense 主力
系列的主干匹配会被整条跳过**——而 Best Buy 标题恰好是分隔式写法
（`Hisense 65" Class U8N Series`），精确匹配也命中不了 → **这些型号会被大量误判为
no_item**。

**处置**：`bestbuy_us` 用 `min_core_len: 3`。

> ★ 为什么降到 3 是安全的：候选匹配放宽**只会多开一个 PDP**，不会直接产出错价——
> 价格真正落库前还要过**闸三**（PDP 权威型号精确相等）。也就是说
> **`min_core_len: 3` 的正确性依赖闸三成立**；若校准发现 PDP 抽不到权威型号，
> 就必须把 `min_core_len` 调回 4 并接受覆盖率下降。这是两个参数之间的强耦合，
> 不要单独改一个。
>
> 主干仅 2 位的 6 条（UX / MX / HW）**仍然不做主干匹配**，判 no_item 属预期行为，
> 不要为它们再放宽规则。

#### 陷阱二：`search.sku` 绝不能配 `regex` 兜底

`_parse_search_with_spec` 里 `Extractor` 是用**整页 HTML** 构造的
（`Extractor(retail_spec, html=html, ...)`），而卡片是逐个传进去的
（`ex.raw(block, cfg["sku"])`）。`Extractor.raw` 的兜底顺序是
`self_attr → self_text → selectors → **regex（整页）** → jsonld（整页）`。

所以如果给 `search.sku` 配 `regex`，**每张卡片都会从整页里正则出同一个 SKU**，
经 `seen` 去重后**只剩 1 个候选**——搜索页看起来"有结果"，实际退化成单候选，
后果是大量型号被误判 no_item，而且**极难排查**（没有任何报错）。

**处置**：`search.sku` 只用 `self_attr`（`data-sku-id`）+ 容器内 `selectors` 链；
需要从链接取 SKU 时，用 `url` 字段取 `href`，不要用整页 regex。spec 里已写明这条
`_note`。

#### 附带修复：`explain_no_match` 的归因会误导排查方向

原实现只分四类，遇到"主干串太短所以主干匹配被跳过"时会报成
**"同系列有货但尺寸不符：站上只有 65\"，目标 65\""**——自相矛盾，且把排查方向
指向尺寸，而真正原因是配置。已修（`overseas/retail_spec.py`）：

- 主干串短于 `min_core_len` → 明确报"主干串仅 N 位 < min_core_len=M，主干匹配被跳过"；
- 尺寸其实一致却仍未命中 → 报"请检查 reject 词表 / 主干长度 / 词边界"，不再谎报尺寸不符。

> 这条修复直接服务于本任务的核心要求：**"搜不到"的原因必须可核对**，
> 归因错了就等于没有归因。既有 64 项 `retail_spec_tests.py` 全部仍通过。

---

## 5. 防死循环：终止条件表（复用 §4.3 六条 + Best Buy 增补）

### 5.1 型号 × 站点级（任一命中即停，**不重试**）

| # | 终止条件 | 结果状态 |
|---|---|---|
| 1 | 累计评价数 ≥ `max_reviews`（50） | `ok`（达上限） |
| 2 | 本页/本组合无新评价（key 全已知） | `ok`（增量到底） |
| 3 | 翻页数 ≥ `max_pages`（10） | `ok`（安全阀） |
| 4 | 命中 blocked / captcha | `blocked`，记 `block_reason`，**立即跳过该站** |
| 5 | HTTP 403/404/5xx 连续 2 次 | `failed`，记状态码，跳过该型号 |
| 6 | **站级熔断**：单站连续 5 个 blocked/410/403/429 | 跳过该站**剩余全部型号** |

### 5.2 Best Buy 增补（针对 405 个型号的规模风险）

| # | 机制 | 配置 | 作用 |
|---|---|---|---|
| 7 | **品牌级搜索**：一个品牌只搜一次 | `search.batch{force:true, keyword_template:"{brand} tv"}` | 405 型号 → 5 个品牌 = **最多 5 次搜索**，而不是 405 次 |
| 8 | **禁止逐型号回退** | `fallback_per_model: false` | 池里没有的型号直接判 `no_item`，**不为它再发一次搜索** |
| 9 | **搜索失败熔断** | `max_search_failures: 2` | 连续 2 个品牌搜索失败（被拦/无候选）即停止其余品牌 |

> ★ 第 7~9 条来自 Costco US 的实测结论（`costco_us.retail.json` 的
> `_note`："美国站搜索页更慢…`force=true + fallback_per_model=false` 是避免 179 个
> Hisense 型号逐个搜的关键"），**Best Buy 情况相同或更严重**。

### 5.3 为什么这些开关就够

- **型号不会互相触发重试**：每个型号是独立任务，失败即记状态并 `continue`。
- **站点不会空转**：熔断三处（评价 blocked、HTTP 失败、站级 blocked_streak）。
- **搜索不会刷爆**：品牌级 + `fallback_per_model:false`。
- **翻页不会越界死循环**：`max_pages` + `page_all_known` + `no_new_combos_cap`（BV/组合扫时）。

---

## 6. 落地路径（三步，逐级放量）

### Step 1 — 现在就能做（零网络依赖）✅

| # | 产出 | 状态 |
|---|---|---|
| 1 | `docs/retail_specs/bestbuy_us.retail.json` v0.2：批量搜索 + 尺寸守卫 + `min_core_len=3` + 开盒 reject + 死循环安全阀（v0.1 已备份为 `.bak-20260920`） | 本次产出 |
| 2 | `scripts/diag_bestbuy_us.py`：六项体检（出口 IP / 搜索候选 / PDP 型号 / 网评后端 / 价格区 / **"搜不到"复现**） | 本次产出 |
| 3 | `overseas/retail_spec.py::explain_no_match` 归因修复（主干过短 / 尺寸一致仍未命中，不再误导） | 本次产出 |
| 4 | 本文档（经验迁移清单 + 误抓红线 + 终止条件表 + §4.6 两个配置陷阱） | 本次产出 |

**离线验证证据（本次已跑）**：
```
16 份 RetailSpec 全量校验          → 0 失败
scripts/retail_spec_tests.py       → 64 PASS / 0 FAIL
新 spec 匹配行为离线回归（4 类应拒 + 3 类应中）→ 全部符合预期
```

### Step 2 — 拿到美国代理后（约 30 分钟）

```powershell
$env:OVERSEAS_PROXY = "http://<美国住宅代理>:<port>"
py -3.12 scripts/diag_bestbuy_us.py --brand Hisense `
    --model-exists 65U8N --model-absent 999ZZZZ --dump data/_smoke
```
逐项判定：
1. 出口 IP 是否美国、**标题里有没有 "Best Buy International"**（★别看状态码，非美国是 200）；
   若是 `10.18.0.250/disable.htm` → 本地网关拦截，不是反爬，换网络；
2. `data-sku-id` 候选能否解析出 ≥20 个 TV 候选（滚动 20 次；不足会误判 no_item）；
3. PDP 能否抽到权威型号（`Model:...` / `<title>` 里的型号）——决定闸三是否成立；
4. 网评后端属 A/B/C/D 哪一类（**预期是 C：站内原生评价页**），并记下真实分页文案
   （`Page 1 Showing 1-20 of 47`）与翻页参数；
5. 价格候选的祖先容器，确认主价选择器（决定闸四）；
6. **`--model-absent` 的返回必须是"0 相关候选"而不是"首页若干广告"**——若后者，说明必须靠闸一/闸三兜住。

### Step 3 — 校准通过后，逐级放量

```
5 型号（单品牌） → 抽检零误匹配 → 30 型号 → 全量 405 型号
每级都要：零误抓抽检 + 价格填充率 + 覆盖归因计数
```

---

## 7. 验收指标（沿用墨西哥线标准，红线一致）

```
✓ 型号覆盖率有数字：找到 / 未找到分别计数，每条 no_item 必须带 explain_no_match 归因
✓ 每型号评价 ≤ 50 条且无重复（(item_id, review_key) 零重复）
✓ 价格填充率 ≥ 95%（缺货不计分母）
✓ 匹配准确率抽检 20 个零误匹配                      ★红线
✓ 抽检的每个价格都能用 item_id 回到 PDP 复核          ★红线（防"看起来对"的错 SKU）
✓ 产物落 data/美国/，网评 20 列 / 价格表列结构与日本线一致
✓ 零"把 failed 写成 no_item"：日志里 failed 与 no_item 计数可交叉核对
```

---

## 8. 风险与未决项（如实登记）

| # | 未决项 | 影响 | 何时能定 |
|---|---|---|---|
| 1 | **本机出不了网 + 出口 IP 非美国** | 以上 5 类校准全部无法进行 | 拿到能出网的美国线路 |
| 2 | 网评后端未现场确认（首选 `/ugc/v2/reviews` 一手接口，`/site/reviews/<slug>/<skuId>` 为兜底；已排除 BV） | 决定 §2.2 的接入路径与 `paginate.reviews.type` | Step 2 第 4 项 |
| 3 | 现有 spec 选择器**全部未验证** | 直接用会静默 0 结果 | Step 2 |
| 4 | Best Buy 是否区分 Open-Box SKU（同型号多 SKU） | 决定价格取"最低"还是"新品价" | Step 2 第 5 项 |
| 5 | `robots.txt` 本机取不到（网关拦截） | 合规校验 `ensure_allowed` 需真实可达后才能生效 | 拿到美国线路 |
| 6 | 评价是否需要登录 | 影响能否突破 20 条/页（Amazon CA 的经验：登录后 8 → 35 条） | Step 2 |
| 7 | 站内原生评价页的**翻页参数名**未知（`page` / `offset` / `cp`） | 决定走 `url_page` 还是 `query_param` | Step 2 第 4 项 |
| 8 | 搜索页 `id=pcat17071` 是否必需、`intl=nosplash` 是否足够 | 影响搜索 URL 形态 | Step 2 第 2 项 |

> 外部证据（urlscan 存档、BV 域名命中统计等）**只能用来"排除方向"，不能替代现场实测**。
> 上面第 2、7、8 项都属于"外部看着像、本地没验过"，一律以 Step 2 的实测输出为准。

---

## 9. 与既有文档的关系

- 本文是 `docs/零售线现状问题与北美抓取任务表.md` 里 **R4（美国阶段）** 的下钻方案。
- 美国 4 站的通用前置（美国代理）与本文 §2.1 一致，不重复主张。
- `bestbuy_us.retail.json` v0.1 保留为 `.bak-20260920`，便于对照回退。
