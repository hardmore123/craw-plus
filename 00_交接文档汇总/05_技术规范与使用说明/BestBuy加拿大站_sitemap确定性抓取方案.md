# Best Buy 加拿大站（bestbuy.ca）价格 + 网评抓取方案

> 参照加拿大 Amazon 线经验，与美国站方案并列
> 日期：2026-09-20
> 结论依据：本机实测（robots.txt / sitemap / 真实浏览器探测）+ `overseas/sites/bestbuy_ca/adapter.py`、
> `overseas/retail_common.py`、`scripts/bestbuy_ca_catalog.py`、`scripts/crawl_bestbuy_direct.py`
> 逐一核查，**不含推测**。姊妹文档：`BestBuy美国站_参照加拿大Amazon经验_方案与红线.md`。

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 该站此前有没有 RetailSpec？ | **没有**。任务表 `docs/零售线现状问题与北美抓取任务表.md` 把 `bestbuy_ca` 列在 **C 层（完全没有 RetailSpec）**。本次已补齐 `docs/retail_specs/bestbuy_ca.retail.json` |
| 能不能照抄美国站方案？ | **不能**。两家是不同公司、不同后台，URL 参数、评价后端、被封方式、robots 规则都不同（见 §1） |
| 合规上有没有问题？ | **有**。`robots.txt` 明确 `Disallow: /en-ca/search`（站内搜索禁抓），但**显式放行** `/en-ca/product/`、`/en-ca/category/`、`/en-ca/brand/`，并提供 sitemap。→ **改走 sitemap，合规问题即解** |
| 页面能不能抓？ | **本机不能**。sitemap 全部 200 可下载，但 `/en-ca`、`/en-ca/category/…`、`/en-ca/product/…` **连真实浏览器也是 403 Access Denied**（正文仅 297~324 字节）→ 需加拿大可通行出口 IP |
| ★"某些型号搜不到"怎么解决？ | **该站可以彻底绕开这个问题**。sitemap 给出确定性商品目录，型号在不在目录里是**存在性问题**，不是搜索相关性问题。已交付 `bestbuy_ca_catalog.py` + `crawl_bestbuy_direct.py` |
| 能不能避免误抓 / 死循环？ | **能**，而且比搜索路径更强：目录匹配（型号→唯一 SKU）+ PDP 权威型号校验双闸；流程里根本没有搜索重试 |

> ★ 一句话：**美国站是"合规上不该搜、技术上搜不准"；加拿大站多一个好处——sitemap 能把
> 整个商品目录拿下来，于是"某型号有没有上架"从模糊判断变成确定性判断。**

---

## 1. 与 bestbuy.com 的关键差异（**不要照抄**）

| 维度 | bestbuy.ca | bestbuy.com |
|---|---|---|
| 运营主体 | Best Buy Canada（独立公司） | Best Buy US |
| 搜索 URL | `/en-ca/search?search=<kw>&page=<n>` | `/site/searchpage.jsp?st=<kw>&cp=<n>&intl=nosplash` |
| 搜索页 robots | **`Disallow: /en-ca/search`** | **`Disallow: */site/searchpage.jsp?st=*`** |
| 商品页 URL | `/en-ca/product/<slug>/<sku>` | `/site/<slug>/<skuId>.p?skuId=` 与 `/product/<slug>/<BSIN>/sku/<skuId>` |
| 放行路径 | `Allow: /en-ca/product/`、`/en-ca/category/`、`/en-ca/brand/` | AI 发现组 `Allow: /site/` |
| sitemap | `https://www.bestbuy.ca/sitemap_index.xml`（38 个子图，**本机实测可下载**） | `sitemaps.bestbuy.com/sitemaps_pdp.xml` / `_bsin`（★未实测） |
| 本机被封方式 | **应用页 403 Access Denied**（纯 HTTP 与真实浏览器都一样，边缘按 IP/ASN 硬拦）；robots/sitemap 却放行 | **公司内网网关**拦截（`10.18.0.250/disable.htm`）+ 出口 IP 非美国；非美国 IP 返回 **HTTP 200 国际选择页** |
| 评价后端 | adapter 旧注释称 **BazaarVoice**（★**未验证**） | 已排除 BV（2022-12 后再无 BV 域名请求） |
| 价格抽取 | JSON-LD `offers.price` 为主（`retail_common.jsonld_product_payload`） | 服务端渲染 DOM + SSR Apollo 载荷 `productBySkuId.price.customerPrice` |
| 市场形态 | **marketplace**（同商品可能有第三方卖家报价） | 自营 + 第三方，且有 Open-Box/翻新 SKU |

> ★ 结论：**加拿大站不要复用美国站的搜索参数、评价后端判断与选择器**。
> 可以复用的是**方法论**：四类"搜不到"归因、四道防误抓闸、死循环终止条件表。

---

## 2. 本机实测事实（2026-09-20）

```
GET https://www.bestbuy.ca/robots.txt              → 200（1395 字节，内容见 §6）
GET https://www.bestbuy.ca/sitemap_index.xml       → 200（5166 字节，38 个子 sitemap）
GET https://www.bestbuy.ca/sitemap1.xml.gz         → 200（解压后 30.0 MB，50,000 条 <loc>，
                                                          其中 /product/ 21,982 条）
GET https://www.bestbuy.ca/sitemap38.xml.gz        → 200（解压后 20.6 MB，35,771 条 <loc>，
                                                          其中 /product/ 13,482 条）
GET https://www.bestbuy.ca/en-ca                   → 403（真实浏览器 Edge 亦然）
GET https://www.bestbuy.ca/en-ca/category/...      → 403（真实浏览器 Edge 亦然）
```

403 正文：`Access Denied`，仅 297~324 字节，`h1` 就是 `Access Denied`，
`blocked=True / reason='http_403'`。

**★ 这个 403 的性质要说准**：它**不是**缺请求头、**不是**要 JS 渲染、**不是**验证码——
真实浏览器带 stealth 指纹同样被拒，说明是**站点边缘按出口 IP/ASN 的硬拦**。
因此本机**做不了 PDP 选择器校准**，需要加拿大可通行的出口 IP（住宅优先）。
sitemap 能下不代表页面能抓，这两件事在 Best Buy 加拿大站上是分开的。

**目录规模**：38 个子 sitemap，每个 1.3~2.2 万条商品 URL，全量约 **50~70 万条商品**。

---

## 3. 推荐路径：sitemap 确定性目录（已交付三个脚本）

```
scripts/bestbuy_ca_catalog.py build     # ① sitemap → 本地商品目录（可断点续传）
        ↓  data/_sitemap/bestbuy_ca/products.csv    (sku, slug, url, sitemap)
scripts/bestbuy_ca_catalog.py match     # ② 型号清单 → SKU + PDP URL（确定性映射）
        ↓  data/加拿大/bestbuy_ca_match_<brand>.csv  (found / not_found + url)
scripts/crawl_bestbuy_direct.py         # ③ 直连 PDP 抓价格 + 网评（不搜索）
```

### 3.1 为什么匹配用"分词拼接完全相等"，而不是子串包含

slug 是连字符分词的商品名。若用子串匹配，`U8N` 会命中 `XU8NX` 之类的伪命中——
**这与 specs 里那条"search.sku 不能配整页 regex"是同一类错误**（一处放宽，全盘污染）。

所以 `_slug_matches_model()` 的做法是：

```
tokens = slug.split("-")  →  每段归一化
相邻 k 段（k≤4）拼接后，与目标型号的归一化串**完全相等**才算命中
```

- `...,65,u8n,...` 命中 `65U8N` ✓（多段拼接容纳"尺寸与系列被连字符分开"的写法）
- `...,75,u8n,...` **不**命中 `65U8N` ✓（尺寸不同就是不同型号）
- 含 `u8n` 但**不构成独立分词**的串（如 `xu8nv`）**不**命中 ✓（完全相等而非子串包含）

> ★ **一个必须知道的行为**（实测确认，别按直觉猜）：如果型号本身写成**系列名**（如 `U8N`），
> 它会**同时命中 65 吋和 75 吋** —— 因为 slug 里确实存在独立的 `u8n` 分词。
> 这是设计使然（系列级入口本就对应多个具体型号），但它会把"系列"当成"型号"交付。
>
> **当前加拿大清单里不会发生**：实测 621 条型号中，归一化长度 ≤4 的有 **0 条**，
> 清单里全是带尺寸的完整型号（`65U8N`、`55S7N`、`OLED77B6EUA` …）。
> 若将来清单引入系列名条目，**必须先定义口径**（取最低价？还是全部列出？），
> 否则会出现"一个系列一行、价格含义不明"的数据。

### 3.2 抓取层（`crawl_bestbuy_direct.py`）如何防误抓 / 防死循环

**防误抓（双闸，且第一闸是"没有候选可比"）**：

1. **目录命中**：候选不是"搜索返回的前几条"，而是目录里型号完全匹配的那条 SKU。
   型号不在目录 = `no_item`，是**确定性结论**，不是搜索失败。
2. **PDP 权威型号校验**：打开 PDP 后用 `overseas/retail_spec.py::payload_matches_model()`
   校验 —— 有权威型号（`product.model_candidates`）时**只认精确相等**，不等直接丢弃，
   **不退回宽松的标题/URL 子串匹配**；`no_item` 的 message 会写明"候选 PDP 均未校验到目标型号"。
   （该函数本次从 `crawl_ca_retail._payload_matches_model` 提到库里，避免新入口各写一份慢慢漂移。）

**防死循环**：

| 机制 | 设置 |
|---|---|
| 流程里**没有搜索重试** | 直连 PDP，不存在"搜索失败→重试"的循环 |
| 单型号候选数上限 | 目录里同型号多个 SKU 时最多试 5 个，之后判 `no_item` |
| 站级熔断 | 连续 5 个型号 `blocked` → 跳过剩余全部型号 |
| 评价翻页安全阀 | `max_pages`（默认 10）+ `page_all_known` + 目录未命中即停 |
| 评价被拦不丢价格 | 评价页被拦时保留已拿到的价格，只把原因写进 message（避免"被墙的站把价格全清空"） |

---

## 4. 与美国站共享的方法论（可直接复用）

| 复用项 | 落点 |
|---|---|
| 四类"搜不到"归因（无候选/系列没有/尺寸不符/被规则排除） | `overseas/retail_spec.py::explain_no_match`；`no_item` 必须带归因文本 |
| 配件 + 开盒/翻新 reject 词表 | `bestbuy_ca.retail.json` 的 `match.reject` |
| 尺寸守卫（`65" Class - U7SG Series` 分隔式写法） | `verify.core_size_tokens` |
| **`min_core_len: 3`** | 加拿大清单 621 条里有 26 条主干 ≤3 位（Hisense `S7N` 系列 24 条、`UX` 2 条）。沿用 4 会让主力系列主干匹配被整条跳过 |
| 价格区校验（防配件价） | 参照 `overseas/sites/amazon_common.py::price_in_region`，**校准前不要省** |
| 死循环终止条件表 | 美国站方案文档 §5 |

---

## 5. 仍然必须现场校准的部分（本机做不到）

| # | 待校准项 | 为什么重要 |
|---|---|---|
| 1 | **评价后端到底是不是 BazaarVoice** | adapter 旧注释称走 BV，但姊妹站已弃用；填错 source 会导致评价恒为 0 条 |
| 2 | **价格选择器 + 价格区校验** | JSON-LD `offers.price` 是否就是展示价、推荐位/配件价如何排除 |
| 3 | **marketplace 口径** | 同商品有第三方卖家报价：取 Best Buy 自营价还是最低价？**属业务口径，需明确** |
| 4 | **PDP 是否服务端渲染够用** | 够用则可加 `fetch.detail_http=true`，每个 PDP 从 10~20 秒降到 1~2 秒 |
| 5 | **评价是否需要登录** | 影响能否突破首屏（Amazon CA 的经验：登录后 8 → 35 条） |
| 6 | **页面对加拿大以外/数据中心 IP 的容忍度** | 决定能否用代理池，以及间隔该设多少 |

校准命令（拿到加拿大线路后）：

```powershell
py -3.12 scripts/diag_retail_network.py --url "<某个 PDP URL>" `
    --match bazaarvoice,review,/api/,ugc --xhr-only
```

---

## 6. 合规：robots.txt 原文要点（本机实测抓取，2026-09-20）

```
User-agent: *
Disallow: /account/          Disallow: /en-ca/Search      Disallow: /en-ca/search
Disallow: /fr-ca/chercher    Disallow: /en-ca/create-review/   Disallow: /order/
Disallow: /checkout/         Disallow: /identity/        Disallow: /en-ca/Basket
Disallow: /en-ca/product/*?icmp=*
Allow:    /en-ca/category/   Allow:    /en-ca/product/   Allow:    /en-ca/brand/
Allow:    /en-ca/event/      Allow:    /en-ca/services/  Allow:    /en-ca/about/
Allow:    /en-ca/help/
Sitemap:  https://www.bestbuy.ca/sitemap_index.xml
```

**读法**：

- **站内搜索（`/en-ca/search`）被明确禁抓** → 美国站方案里的"品牌级批量搜索"在加拿大站**不能用**。
- **商品页 `/en-ca/product/` 被明确放行** → 只要我们手里有 SKU/URL，抓 PDP 是在放行范围内的。
- **`create-review` 只禁写路径**，评价**读取**未受限。
- 唯一需要留意的产品页例外：`/en-ca/product/*?icmp=*`（带推广追踪参数的形态）被禁 →
  拼 PDP URL 时**不要带 `icmp` 参数**（本方案的 URL 形态天然不带）。

> ★ 与加拿大 Amazon 线相比，这里的合规面反而更清晰：**不搜、只抓已放行的商品页，且商品页清单来自
> 站点自己公布的 sitemap**。仍建议由业务方对 bestbuy.ca 的抓取范围做一次确认并留痕。

---

## 7. 落地步骤

### Step 1（本机可做，零页面依赖）✅ 已完成
| # | 产出 |
|---|---|
| 1 | `docs/retail_specs/bestbuy_ca.retail.json`（该站首份 RetailSpec，已过 `validate_retail_spec`） |
| 2 | `scripts/bestbuy_ca_catalog.py`（sitemap → 目录；断点续传；型号存在性比对） |
| 3 | `scripts/crawl_bestbuy_direct.py`（直连 PDP 抓价格 + 网评） |
| 4 | `overseas/retail_spec.py::payload_matches_model`（型号校验提到库里，供直连入口复用） |
| 5 | `overseas/sites/bestbuy_ca/adapter.py` 更新（robots 事实 + sitemap 路径 + 403 事实） |
| 6 | 本文档 |

### Step 2（本机可做）
```powershell
py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca build   # 38 个子图，可反复运行续传
py -3.12 scripts/bestbuy_ca_catalog.py --site bestbuy_ca match   # 621 个型号 → found / not_found
```
⚠️ **Step 2 不需要能打开商品页**——它就是用来回答"该站到底有没有这些型号"的。
这一步产出的 `not_found` 是**确定性结论**，可以直接交付给业务方，
不必等代理到位。

### Step 3（需加拿大可通行出口 IP）
```powershell
$env:OVERSEAS_PROXY = "http://<加拿大线路>:<port>"
py -3.12 scripts/diag_retail_network.py --url "<PDP>" --xhr-only   # 定评价后端
py -3.12 scripts/crawl_bestbuy_direct.py --site bestbuy_ca `
    --match-csv data/加拿大/bestbuy_ca_match_all.csv --limit 5     # 小样
# 校准 PDP 型号/价格选择器 → 覆盖 bestbuy_ca.retail.json → status 改 verified
# 抽检零误匹配 → 30 型号 → 全量
```

---

## 8. 未决项与风险（如实登记）

| # | 未决项 | 影响 | 何时能定 |
|---|---|---|---|
| 1 | 应用页 403（本机边缘硬拦） | PDP 选择器/价格/评价全部无法校准 | 加拿大线路 |
| 2 | 评价后端未确认（BV 说法无实测支撑） | 填错 source → 评价恒 0 条 | Step 3 |
| 3 | `retail_specs/bestbuy_ca.retail.json` 的 CSS 选择器**全部未校准** | 直接抓会静默 0 结果 | Step 3 |
| 4 | marketplace 价格口径（自营 vs 第三方最低） | 影响交付数字的含义 | 业务方定义 |
| 5 | 型号 slug 里可能不含型号码 → 目录比对漏判 | 会表现为 `not_found`（假阴性，不是误抓） | Step 2 抽出 matched/not_found 后抽检 20 个 |
| 6 | `crawl_ca_retail.py` 的搜索主路径对该站**不合规** | 若有人误用 `--sites bestbuy_ca` 会走被禁路径 | 已用 `search_allowed_by_robots=False` 显式标记；建议后续在 CA 线加硬校验 |

> ★ 第 5 条要留意：目录比对是**宁可漏判、不肯误判**。若抽检发现 `not_found` 里
> 有型号其实在售，应改进 slug 匹配（例如补充"系列名 + 尺寸"的组合规则），
> **而不是放宽成子串匹配**——那会把误抓放进来。

---

## 9. 与既有文档的关系

- 本文是 `docs/零售线现状问题与北美抓取任务表.md` 里 **C 层（`bestbuy_ca` 无 spec）** 的补齐与下钻。
- 方法论与 `BestBuy美国站_参照加拿大Amazon经验_方案与红线.md` 同源；两站**差异**见本文 §1。
- sitemap 目录这条路径同样适用于美国站（`sitemaps_bsin` / `sitemaps_pdp`），
  但美国站的 sitemap 可达性**尚未实测**，`bestbuy_ca_catalog.py --site bestbuy_us` 已预置入口，
  拿到美国线路后先验证再启用。
