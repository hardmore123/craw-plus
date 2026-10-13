# 无 RetailSpec 的站点说明（283 站点 − 259 RetailSpec = 24 站）

更新：2026-10-12。说明 `overseas/sites/` 下 283 个站点目录中，为什么有 24 个没有对应的
`schemas/retail_specs/<code>.retail.json`。

**结论：这 24 个站点不是漏写，而是按业务线分工，本就不走 RetailSpec（零售契约）**：

- 品牌官网 SPEC 站 → 走 `python -m overseas.cli spec-crawl`（官网规格表），适配器在 `sites/<code>/adapter.py`，不抓价格/网评，故无 RetailSpec。
- 媒体评测站 → 走 `scripts/crawl_media_reviews.py`（media 线），写入 `media_review` 表，不抓零售价格，故无 RetailSpec。
- 通用工具站 → 通用 JSON-LD 抽取器，非具体站点，按需调用，无 RetailSpec。

---

## 一、品牌官网 SPEC 站（15 个，走 spec-crawl，无零售 spec）

这些在 `overseas/regions_auto.py` 里作为 SPEC 品牌注册，用官网 SPEC 适配器抓规格表（`spec_series`/`spec_row`），
不抓价格/评价。其余国家的同名品牌（如 `hisense_de`、`philips_de`）如有零售价抓取需求才配 RetailSpec。

| code | 品牌 | 国家 | 说明 |
|---|---|---|---|
| lg_de | LG | 德国 | 官网 SPEC，多级流程 + Next.js/Coveo |
| lg_fr | LG | 法国 | 同上 |
| lg_it | LG | 意大利 | 同上 |
| samsung_de | Samsung | 德国 | 官网 SPEC，Next.js 站 |
| samsung_fr | Samsung | 法国 | 同上 |
| samsung_it | Samsung | 意大利 | 同上 |
| sony_de | Sony | 德国 | 官网 SPEC，Hybris/SPA 站 |
| sony_fr | Sony | 法国 | 同上 |
| sony_it | Sony | 意大利 | 同上 |
| tcl_de | TCL | 德国 | 官网 SPEC，多级流程 + JSON 规格端点 |
| tcl_fr | TCL | 法国 | 同上 |
| tcl_it | TCL | 意大利 | 同上 |
| philips_fr | Philips | 法国 | 官网 SPEC，多级流程 |
| philips_it | Philips | 意大利 | 同上 |

> 注：`hisense_de/fr/it`、`panasonic_jp`、`sharp_jp`、`regza_jp`、`philips_de/it` 等品牌官网站
> 有的是 SPEC-only（仅有 SPEC 适配器，无零售），有的配了 RetailSpec（走零售线）。本表只列**有 sites 目录但无 retail spec** 的。

## 二、媒体评测站（9 个，走 media 线，写入 media_review 表）

这些站抓取媒体评测文章，数据入 `media_review` 表，供 TCP 报告引用。不抓零售价格，故无 RetailSpec。

| code | 站点 | 国家 | 评分来源 |
|---|---|---|---|
| chip_de | CHIP | 德国 | JSON-LD @type=Review，reviewRating |
| computerbild_de | Computer Bild | 德国 | 媒体评测 |
| connect_de | connect.de | 德国 | HTML fallback，德国量表 1-5 反序 |
| hifitest_de | Hifi Test | 德国 | 媒体评测 |
| hwupgrade_it | HWUpgrade | 意大利 | 媒体评测 |
| techfi_nl | TechTotaal | 荷兰 | JSON-LD @type=Review，8/10 制 |
| techradar_uk | TechRadar | 英国 | JSON-LD @type=Product + review |
| techzilla_it | TechZilla | 意大利 | JSON-LD @type=Review，0-10 制 |
| which_uk | Which? | 英国 | 评分在付费墙后 |

## 三、通用工具站（1 个）

| code | 说明 |
|---|---|
| generic_jsonld | 通用 JSON-LD 抽取器：面向商品页内嵌 `<script type="application/ld+json">` 的站点，按需调用（sku 传商品页 URL），非具体站点，无 RetailSpec。适合「已知商品 URL」场景，不支持关键词搜索。 |

---

## 与其他清单的关系

- `spec_adapter_清单.csv`（259 行）= 有 RetailSpec 的零售站点清单（本文档的 24 个不在其中，因无 spec）。
- `逐站状态.md`（259 站）= 同 259 个零售站的实测判定。
- 本文档补充的是**不在上述两份清单里的 24 个站点**的归属说明。
- 283 个站点目录 = 259（有 RetailSpec）+ 15（官网SPEC）+ 9（媒体评测）+ 1（通用工具）− 1（`__pycache__` 非站点目录）。
