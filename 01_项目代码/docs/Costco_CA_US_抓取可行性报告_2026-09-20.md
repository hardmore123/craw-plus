# Costco（加拿大 / 美国）价格与网评抓取可行性报告

日期：2026-09-20
结论：**可行，且已按加拿大 Amazon 的既有经验落地。** Costco 与 Amazon 的差别在
「型号怎么认」和「评价从哪来」，不在流程骨架——搜索 → 匹配 → 商品页同页取
价格 + 评分 + 评价 → 型号级状态与导出这套骨架完全复用。

---

## 一、先说结论（TL;DR）

| 问题 | 结论 |
|---|---|
| 能不能照搬加拿大 Amazon 的经验？ | **能**。复用 `crawl_ca_retail.py` + RetailSpec 六段 + `match_product` + 站级熔断 + 评价上限/翻页安全阀，一行流程没改。 |
| 价格拿得到吗？ | **能**。商品页服务端渲染，JSON-LD `offers.price` 直接可读（纯 HTTP 即可，不需要浏览器）。 |
| 网评拿得到吗？ | **能**。DOM 里没有评价明细，但 BazaarVoice 的客户端 JSON 接口可直接调（也不需要登录/passkey）。 |
| 「某些型号搜索不到」怎么办？ | 确实存在，而且有两种完全不同的原因，必须分开处理（见第四节）。已做到**搜不到就记 no_item、绝不猜**，并且**抓取失败绝不写成 no_item**。 |
| 会不会误抓？ | 已封死两条路径：系列主干匹配的尺寸守卫 + 商品页自报型号的精确相等校验。 |
| 会不会死循环？ | 已有 4 道闸：评价分页安全阀、站级熔断、品牌搜索失败熔断、候选数下限。 |

实测里程碑（本机，经本地 Clash 代理，出口为北美 IP）：

| 站点 | 搜索结果 | 商品页（HTTP） | 网评 |
|---|---|---|---|
| costco.ca | 24 条候选（Hisense tv） | 55" U7SG：**$1197.99 CAD**，JSON-LD InStock | 8 条（BV 接口） |
| costco.com | 24 条候选（Hisense tv） | 55" QD7：**$279.99 USD** | 18 条（BV 接口） |

---

## 二、Costco 和 Amazon 到底哪里不一样

| 维度 | Amazon CA（已有经验） | Costco CA/US（本次实测） |
|---|---|---|
| 搜索页 | 服务端渲染，静态 HTML 就有 ASIN 卡片 | **Next.js 客户端渲染**，静态 HTML 里 0 个商品链接（`Hisense` 字样出现 0 次），必须浏览器 + 滚动 + 等待 |
| 商品页 | 服务端渲染，选择器可用 | **服务端渲染，纯 HTTP 可取**；但价格选择器全部 0 命中，只能走 JSON-LD |
| 标题里的型号 | `Hisense 55U7SG ...`（含完整型号） | `Hisense 55" Class - U7SG Series ...`（**只有系列，没有完整型号**） |
| 权威型号在哪 | 详情表 `model number` | 页头 `Item 8987855 \| Model 55U78SG` + 规格表 `Model` 行（`55U7SG`） |
| 评价来源 | 商品页首屏 `[data-hook='review']`，翻页靠 `sortBy/filterByStar` 组合扫描 | 商品页 **0 条**；走 BazaarVoice BFD JSON 接口 |
| 评价口径 | 按 ASIN | **按系列聚合**（用 55" 的商品号查，返回的可能是 75" 的评价） |

一句话：**骨架相同，站点知识完全不同**。这正是 RetailSpec 存在的意义——新站只加
适配器 + spec，不动主流程。

---

## 三、价格：走 JSON-LD，别再写价格选择器

商品页（`/<slug>.product.<productId>.html`）是服务端渲染的，一次纯 HTTP 请求就能拿到：

```json
{"@type": "Product",
 "name": "Hisense 55\" Class - U7SG Series - 4K QLED Mini LED TV",
 "sku": "8987855",
 "offers": {"price": 1197.99, "priceCurrency": "CAD",
            "availability": "https://schema.org/InStock"},
 "aggregateRating": {"ratingValue": 4.38, "ratingCount": 8}}
```

实测命中/未命中：

| 选择器 | 命中数 |
|---|---|
| `span[automation-id='productPriceOutput']` | 0 |
| `[data-testid*='price']` | 0 |
| `div.price span.value` | 0 |
| JSON-LD `offers.price` | ✅ 1197.99 |

两个坑：
1. **`aggregateRating.reviewCount` 是 `null`，条数在 `ratingCount`**。`jsonld_product_payload`
   已有的 `reviewCount or ratingCount` 兜底正好救了这个，不要改掉。
2. costco.com 用同一套 JSON-LD，货币是 USD。CA 的 slug 在 US 站会 404（商品号不通用），
   必须用各自站点的候选 URL。

因为商品页不需要浏览器，spec 里开了 `fetch.detail_http: true`：**搜索用浏览器、详情页走
HTTP**，单个 PDP 从 10~20 秒降到 1~2 秒。

---

## 四、型号匹配：这是本次最关键的改动

### 4.1 问题：Costco 的标题把尺寸和系列拆开了

Costco CA 实际在售的 Hisense 候选（`Hisense tv` 搜出来 24 条）长这样：

```
hisense-55-class---u7sg-series---4k-qled-mini-led-tv.product.4201009218.html
hisense-75-class---u7sg-series---4k-qled-mini-led-tv.product.4201004539.html
hisense-65-class---u88qg-series---4k-qled-mini-led-tv.product.4000374511.html
```

注意：出现的是 `55 Class - U7SG Series`，**不存在 `55U7SG` 这个字符串**。这会让原有两条
匹配路径同时出错：

| 路径 | 行为 | 后果 |
|---|---|---|
| 精确子串（`55U7SG` 出现在标题里） | 永不命中 | **正确商品被拒**（假阴性） |
| 主干匹配（`U7SG` 出现即可） | 命中 55"/75" 任意一条 | **65 吋被记成 75 吋的价**（假阳性，张冠李戴） |
| 旧尺寸守卫 `(\d{2,3})U7SG` | 因为中间夹着 `Class - `，永远匹配不到尺寸 | 守卫失效，**等于没有守卫** |

### 4.2 修法一：尺寸-系列解耦的尺寸守卫（配置化）

`RetailSpec.match.verify` 新增 `core_size_tokens`，声明「尺寸与系列之间允许的分隔词」：

```json
"verify": {
  "core_size_tokens": ["class", "inch", "in", "\"", "series"]
}
```

`retail_spec._candidate_sizes()` 同时认三种写法：
- 紧贴式 `75U6SV`（老站，行为不变）
- 分隔式 `65" Class - U7SG Series`、`65 inch U7SG`
- 无空格式 `65classu7sg`

不配这个 key 时走原来的紧贴式逻辑，**其它站零影响**。

### 4.3 修法二：商品页自报型号的精确相等校验

商品页其实自己标注了真实型号，两处：

```
页头：<div data-testid="Text_item-number">Item 8987855 | Model 55U78SG</div>
规格表：<th>Model</th><td>55U7SG</td>
```

`sites/costco_common.py` 把两处都收进 `Product.model_candidates`，`_payload_matches_model`
遇到非空 `model_candidates` 时**只认精确相等**，不再退回宽松的标题子串：

```python
if candidates:
    return any(_model_norm(c) == want for c in candidates if c)
```

为什么两处不一致还要都收：Costco 会把系列型号（`55U7SG`）和实际售卖型号（`55U78SG`）
分开写。只收一个就会漏。收两个做「任一精确命中」，比任何模糊匹配都安全。
为避免页面上的「对比/相关商品」模块串味，`extract_models` 还做了两道收口：页头只取
第一个、规格表最多取 2 个，且其余候选必须与第一个同尺寸。

### 4.4 实测结果

| 目标型号 | 结果 | 说明 |
|---|---|---|
| 55U7SG | ✅ $1197.99 + 8 条评价 | 正确命中 55" |
| 75U7SG | ✅ $1997.99 + 20 条评价 | 正确命中 75" |
| 85UR9SG | ✅ $3997.99 + 20 条评价 | 正确命中 85" |
| 65U7SG | ⛔ no_item | `同系列(U7SG)有货但尺寸不符：站上只有 55/75"，目标 65"` |
| 116UX / 100UX | ⛔ no_item | `该站没有这个系列（候选 22 条，核心串 UX 未出现）` |

**搜不到的型号现在会给出可核对的原因**，而不是一句笼统的"未匹配"。

> 说明：CA 的 `search.scroll_passes` 最终定为 **8**。实测滚 5 次时有几次只拿到 0 条候选，
> 滚 8 次稳定拿到 22~24 条；结合下面的候选数下限，即使偶发空壳也不会污染结论。

---

## 五、"某些型号搜索不到"：两种原因必须分开

这是本次最需要小心的地方，因为两种情况的处置完全相反：

| 情况 | 现象 | 正确处置 | 处置错了会怎样 |
|---|---|---|---|
| **A. 站上确实没有这个型号** | 搜索页正常（22~24 条候选），只是没有目标系列/尺寸 | 记 `no_item`，不抓价格 | — |
| **B. 抓取本身失败** | 搜索页没渲染出结果（0 条）、被拦、出口 IP 不对 | 记 `failed`，跳过该品牌，**绝不写 no_item** | 把失败伪装成"该站没上架"，**静默丢数据** |

情况 B 不是理论风险，是实测到的常态。同一个 URL、同样的请求头，连跑三次：

```
run 1: HTML 1,837,494 字节  → 0 条候选   ← 页面是空壳，搜索结果根本没渲染
run 2: HTML 2,428,200 字节  → 24 条候选  ← 正常
run 3: HTML 1,836,897 字节  → 0 条候选   ← 又是空壳
```

页面体积本身就分成了 1.83MB / 2.43MB 两档，**空壳版里连 `Hisense` 字样都没有**。

所以加了 `search.batch.min_candidates`（候选数下限）和 `retries`：

```json
"batch": {"min_candidates": 15, "retries": 3, "max_search_failures": 2}
```

- 候选数 < 下限 → 重试；重试仍不达标 → **判为搜索失败**，该品牌整批记 `failed`
- 连续 N 个品牌搜索失败 → 停止搜索其余品牌（不再空转）

实测这道闸门确实生效：US 站某轮只拿到 8~9 条候选时，输出是

```
品牌 Hisense: 候选过少(9 个，低于下限 15)（重试 3 次后仍不达标）→ 跳过该品牌，
不据此判定型号不存在
55U7SG 跳过: 品牌 Hisense 搜索候选缺失      ← 记 failed，不是 no_item
```

---

## 六、网评：DOM 里没有，走 BazaarVoice 接口

### 6.1 为什么不能用 DOM 选择器

商品页里 `ol.bv-content-list li.bv-content-item` 恒为 0；`.bv_avgRating_component_container`
命中 1 个但只给"4.4"、`.bv_numReviews_text` 只给"(8)"——**只有汇总，没有明细**。
点开页内 `Member Reviews` 标签、滚动 14 次，明细依然是 0 条。

### 6.2 实际可用的接口

BV 挂件会去调一条客户端 JSON 接口（实测纯 HTTP 可直连、无需登录、无需 passkey）：

```
GET https://apps.bazaarvoice.com/bfd/v1/clients/Costco-EN_CA
    /api-products/cv2/resources/data/reviews.json
    ?apiVersion=5.4&filter=productid:4201009218&limit=100&offset=0
    &include=products&contentlocale=en_CA
Headers:
    Bv-Bfd-Token: 20040_1_0,native_review_form,en_CA
    Origin: https://www.costco.ca        ← ★缺这个直接 401 Unauthorized
```

- `Bv-Bfd-Token` 的三段 = `<displayCode>,<site>,<locale>`，全部来自站点自己的
  `https://apps.bazaarvoice.com/deployments/<client>/native_review_form/production/<locale>/`
  下的 `*-config.js`，是**静态可推导**的，不用去逆向 JS。
- 两站的取值：

| 站点 | client | displayCode | site | locale |
|---|---|---|---|---|
| costco.ca | `Costco-EN_CA` | `20040_1_0` | `native_review_form` | `en_CA` |
| costco.com | `Costco` | `2070_2_0` | `native_review_form` | `en_US` |

同一路径下还有汇总接口，能拿到星级分布（JSON-LD 只有均分和总数）：

```
GET .../display/0.2alpha/product/summary?productid=<id>&contentType=reviews,questions
    &reviewDistribution=primaryRating,recommended&rev=0&contentlocale=en_CA
→ {"reviewSummary": {"numReviews": 8,
     "primaryRating": {"average": 4.375,
       "distribution": [{"key":5,"count":5},{"key":4,"count":1},{"key":3,"count":2}...]}}}
```

实现落在 `overseas/bv_reviews.py`，由 spec 的 `reviews.source = "bazaarvoice_bfd"` 触发。

### 6.3 ★ 必须暴露的风险：BV 评价按系列聚合，会串尺寸

用 55" 的商品号（`4201009218`）去查，返回的 8 条评价 **`ProductId` 全是 75" 的商品号
（`4201004539`）**，`OriginalProductName` 写着 `Hisense 75" Class - U7SG Series`。
也就是说 Costco 把同系列评价共享给了每个尺寸。

处置（不隐藏、可追溯）：
- 每条评价保留来源商品号：`review_url` 追加 `#bv-src-product=<真实商品号>`
- 状态/日志里报数：`★8/8 条评价来自同系列其它商品（BV 按系列聚合）`

这样在导出表里能一眼区分「这条评价到底是不是这个尺寸的用户写的」，而不是默默把它
当成 55" 的评价交出去。US 站实测 18 条里 1 条跨商品。

---

## 七、防死循环 / 防空转：四道闸

| 闸门 | 位置 | 作用 |
|---|---|---|
| 评价分页安全阀 | `bv_reviews.fetch_bv_reviews` | `max_pages` + `max_reviews` + 空页即停 + 本页无新增即停（站点对越界 offset 回首页时立刻退出）+ 到 `TotalResults` 即停 |
| 站级熔断 | `crawl_ca_retail` | 连续 5 个型号 blocked / 403 / 410 / 429 → 跳过该站剩余型号 |
| 品牌搜索熔断 | 本次新增 | 连续 `max_search_failures` 个品牌搜不到候选 → 停止搜索其余品牌 |
| 候选数下限 | 本次新增 | 候选过少判为失败，不给"没上架"下结论，也不无意义地重试到天亮 |

外加 `search.batch.force=true` + `fallback_per_model=false`：**每个品牌只搜一次**，
候选里没有的型号直接判 no_item、不再逐型号发起搜索。CA 有 621 个型号、US 有 405 个，
若按逐型号搜索，慢站（每次 8~10 秒）会跑几小时并把站点刷爆。现在整站搜索次数 =
品牌数（CA 6 个、US 5 个）。

评价上限仍是既有的 `--max-reviews`（默认 100）与 `max_pages`（默认 10），Costco spec 里
显式写 `max_reviews: 100 / max_pages: 3`。

---

## 八、美国站的额外前提：出口 IP

`costco.com` 对非美国 IP 是 **403 Access Denied（IP 层，与请求头无关）**。本机实测：
- 直连（无代理）：TLS 层就被重置，连不上
- 经美国出口代理：首页 200、搜索页 200 且能渲染 24 条候选、商品页 200、BV 接口 200

另外 **costco.com 的搜索页抖动比 CA 更明显**（同一 URL 实测 24 / 9 / 0 三种结果），
所以 US 的 `scroll_passes` 设 20（滚 3 次只有 8~9 条候选）、`min_candidates` 设 15。
US 站要稳定跑量，需要一条**稳定的美国住宅线路**；机房 IP 时好时坏。

还有一点要提前对齐预期：**Costco US 卖的是渠道专供型号**。例如页面在售
`55QD75SFC`，而品牌官网清单里是 `55QD7QF`。核心串对不上就是 `no_item`——这是
**正确结果**，不要为了"提高命中率"放宽到系列匹配，那会把别的型号的价记到目标头上。

---

## 九、改了哪些文件

| 文件 | 改动 |
|---|---|
| `overseas/bv_reviews.py` | **新增**。BazaarVoice BFD 接口取评价 + 评分分布，含全套分页安全阀与跨商品溯源 |
| `overseas/sites/costco_common.py` | **新增**。CA/US 共用的商品页增强：页头/规格表型号 → `model_candidates`，尺寸、BV 商品号 |
| `overseas/sites/costco_ca/adapter.py` | 搜索 URL 改 `/s?keyword=`；`parse_product` 走 JSON-LD + 增强；`block_marker_allowlist` |
| `overseas/sites/costco_us/adapter.py` | 补 `supports_retail` / `parse_search` / `parse_product`（原来缺这三个，跑起来会直接报错） |
| `overseas/models.py` | `Product` 增 `model_candidates`、`bv_product_id` |
| `overseas/retail_spec.py` | `match_product` 尺寸守卫支持 `core_size_tokens`；新增 `explain_no_match` 给失配原因；`paginate.reviews.type` 支持 `bv_api` |
| `overseas/extract.py` | 抽取规则支持 `self_text`（搜索卡片没有稳定标题类名时取卡片文本） |
| `scripts/crawl_ca_retail.py` | 详情页可走 HTTP；品牌搜索关键词修正；`search.batch` 配置化（候选下限/重试/熔断）；BV 评价接入；失配原因透出 |
| `docs/retail_specs/costco_ca.retail.json` | 重写 |
| `docs/retail_specs/costco_us.retail.json` | 重写 |
| `scripts/diag_retail_search.py` / `diag_retail_pdp.py` / `diag_retail_network.py` / `diag_bv_api.py` | **新增**诊断脚本，新站接入前先跑这几个 |

其中一处顺手修掉的旧 bug：品牌级搜索原来用型号清单里的展示名拼关键词，CA 的展示名是
`Hisense（加拿大）`，会拼成 `Hisense（加拿大） tv` 送进搜索框。现在从 `search_query`
里减掉型号前缀取品牌名（`Hisense`）。

---

## 十、怎么用

```bash
cd 海外
export OVERSEAS_PROXY=http://127.0.0.1:7877      # 必须北美出口

# 0) 接入前先确认站点这次是好的（搜索页渲染、候选数）
py -3.12 scripts/diag_retail_search.py --site costco_ca \
    --spec docs/retail_specs/costco_ca.retail.json --keyword "Hisense tv" \
    --scroll 8 --wait 8000

# 1) 小样本验证（先指定型号，别一上来跑全量）
py -3.12 scripts/crawl_ca_retail.py --region ca --sites costco_ca \
    --brand hisense_ca --models 55U7SG 65U7SG 75U7SG \
    --max-reviews 30 --spec docs/retail_specs/costco_ca.retail.json

# 2) 全量（batch 模式：每个品牌只搜一次）
py -3.12 scripts/crawl_ca_retail.py --region ca --sites costco_ca \
    --brand hisense_ca --spec docs/retail_specs/costco_ca.retail.json --save-db
```

美国站把 `--region us --sites costco_us --spec docs/retail_specs/costco_us.retail.json`
换上去即可。

`regions_config.py` 里 `costco_ca` / `costco_us` 仍是 `enabled=False`——**这是有意的**：
它们依赖北美出口线路，没配代理就跑会得到一堆 403。要用就显式 `--sites costco_ca`。
等线路常态化后再把 `enabled` 打开。

---

## 十一、还没有做到的（别当成已完成）

1. **评价明细只有 BV 给的那部分**。Costco 的 BV 按系列聚合，单尺寸的评价可能只有零星几条，
   拿不到"这个尺寸独有的全部评价"——这是数据源本身的限制，不是抓取缺失。
2. **costco.com 稳定性不够**。同一出口 IP 时好时坏，跑量前建议先用诊断脚本确认；
   长期跑量需要稳定的美国住宅线路。
3. **搜索页没有找到可直接调的 JSON 接口**。截图显示它是 Next.js 应用，但抓不到明确的
   数据接口（`/api/` 前缀会被 Costco 打到 `/GenericError`）。目前每个品牌一次浏览器搜索
   是可接受的（6 个品牌 6 次），所以没有继续逆向。
4. **`model_candidates` 只用于校验，没有落库**。数据库 `product` 表暂时只存
   `model`（页头那个），候选列表和 BV 商品号目前只在内存/状态消息里。要做跨站型号归一
   时再补迁移。
5. **Costco 的会员价 / 选仓价没有单独处理**。未登录能拿到 JSON-LD 价格，但 Costco 部分
   商品的会员价需要登录才显示；缺价时按 `no_price` 记，没有用别的字段硬凑。
