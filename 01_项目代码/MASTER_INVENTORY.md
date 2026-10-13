# 海外爬取项目 Master Inventory（永久性资产清单）

> ⚠️ **本文件统计数字已过时**（生成于站点 74 / RetailSpec 91 / Adapter 116 的早期阶段），仅供历史追溯。
> 当前实际规模见上一层目录 **`../README_交付总说明.md`** §8 与 `../03_清单与报表/spec_adapter_清单.csv`：
> 283 适配器 / 259 RetailSpec / 260 站点注册（158 站有数据）。需要最新逐站清单/数据覆盖时，
> 以 `../03_清单与报表/` 与 `../09_参考网站与完成度/` 为准；需要重建本清单可改 `_gen_master.py`
> 的数据源后重跑（数据源口径见文末附录）。

> 本文档由 `_gen_master.py` 自动生成，汇总所有站点的 schema / adapter / 数据覆盖 / 评价后端 / 抓取方式，作为后续硬编码抓取的权威参考。数据来源：`data/overseas.db` + `schemas/retail_specs/*.retail.json` + `overseas/sites/*/adapter.py`。

**生成时间**：自动 ｜ **DB 站点数**：74 ｜ **RetailSpec 数**：91 ｜ **Adapter 数**：116

---

## 一、总览统计

| 指标 | 数值 |
|---|---|
| 站点总数（DB） | 74 |
| RetailSpec 文件数 | 91 |
| Adapter 文件数 | 116 |
| 有产品记录的站 | 68 |
| 有价格记录的站 | 65 |
| 有评价记录的站 | 37 |
| 商品总数（product） | 9373 |
| 价格快照总数（price_snapshot） | 143169 |
| 评价总数（review） | 146189 |
| 评价汇总总数（review_summary） | 146372 |

**平台分布**：

| 平台 | 站数 |
|---|---|
| VTEX | 17 |
| Amazon | 8 |
| Magento | 11 |
| Brand | 25 |
| Other | 58 |

**区域分布**：

| 区域 | 站数 |
|---|---|
| NA（北美线） | 18 |
| SA（南美线） | 42 |
| EU（欧洲线） | 30 |
| JP（日本线） | 1 |
| Other（其他） | 28 |

## 二、站点矩阵（按区域分组）

> 列：code ｜ 名称 ｜ 平台 ｜ 国家 ｜ 货币 ｜ 商品数 ｜ 价格数 ｜ 评价数 ｜ 汇总数 ｜ 评价后端 ｜ 保护 ｜ 住宅IP

### 北美线

| code | 名称 | 平台 | 国家 | 货币 | 商品 | 价格 | 评价 | 汇总 | 评价后端 | 保护 | 住宅IP |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|:---:|
| `amazon_ca` | Amazon | Amazon | Canada | CAD | 169 | 3052 | 3188 | 3194 | — | L3 |  |
| `amazon_mx` | Amazon | Amazon | Mexico | MXN | 49 | 345 | 355 | 355 | — | L3 |  |
| `amazon_us` | Amazon | Amazon | USA | USD | 134 | 1025 | 1282 | 1296 | — | L3 |  |
| `bestbuy_ca` | Best Buy | Other | Canada | CAD | 9 | 0 | 253 | 261 | bazaarvoice_bfd | L3 |  |
| `bestbuy_us` | Best Buy | Other | USA | USD | 77 | 764 | 1855 | 1868 | — | L3 |  |
| `canadiantire_ca` | Canadian Tire | Other | Canada | CAD | 28 | 2065 | 2727 | 2730 | — | L3 |  |
| `coppel_mx` | Coppel | Other | Mexico | MXN | 0 | 0 | 0 | 0 | — | L2 |  |
| `costco_ca` | Costco Canada | Other | Canada | CAD | 19 | 407 | 391 | 391 | bazaarvoice_bfd | L2 |  |
| `costco_us` | Costco | Other | USA | USD | 24 | 547 | 675 | 647 | bazaarvoice_bfd | L3 |  |
| `leons_ca` | Leon's（加拿大） | Other | Canada | CAD | 136 | 15537 | 15515 | 15515 | lflgroup_api | L3 |  |
| `lg_us` | LG（美国） | Brand | USA | USD | 10 | 1357 | 1357 | 1357 | bazaarvoice_bfd | L2 |  |
| `liverpool_mx` | Liverpool | Other | Mexico | MXN | 0 | 0 | 0 | 0 | — | L2 |  |
| `palacio_mx` | Palacio | Other | Mexico | MXN | 0 | 0 | 0 | 0 | — | L2 |  |
| `sams_mx` | Sam's | Other | Mexico | MXN | 0 | 0 | 0 | 0 | — | L2 |  |
| `sony_ca` | Sony（加拿大） | Brand | Canada | CAD | 4 | 4 | 0 | 0 | bazaarvoice_bfd | L3 |  |
| `thebrick_ca` | The Brick（加拿大） | Other | Canada | CAD | 202 | 1069 | 814 | 1069 | — | L3 | ✅ |
| `walmart_mx` | Walmart | Other | Mexico | MXN | 0 | 0 | 0 | 0 | — | L3 |  |
| `walmart_us` | Walmart | Other | USA | USD | 0 | 0 | 0 | 0 | — | L3 |  |

### 南美线

| code | 名称 | 平台 | 国家 | 货币 | 商品 | 价格 | 评价 | 汇总 | 评价后端 | 保护 | 住宅IP |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|:---:|
| `abc_cl` | ABC | Other | Chile | CLP | 41 | 1291 | 1242 | 1242 | powerreviews_api | L2 |  |
| `alkosto_co` | Alkosto | Magento | Colombia | COP | 25 | 1992 | 1992 | 1992 | reviews_io_api | L2 |  |
| `alkostoplus_bo` | Multicenter+ | Magento | Bolivia | BOB | 151 | 481 | 0 | 481 | aggregate_only | L2 |  |
| `artefacta_ec` | Artefacta | Magento | Ecuador | USD | 41 | 41 | 0 | 0 | unknown_blocked | L2 |  |
| `carsa_pe` | Carsa | VTEX | Peru | PEN | 108 | 109 | 0 | 0 | vtex_reviews_graphql | L2 |  |
| `comandato_ec` | Comandato | VTEX | Ecuador | USD | 34 | 34 | 0 | 0 | none | L2 |  |
| `coral_ec` | Coral | Magento | Ecuador | USD | 8 | 8 | 0 | 0 | none | L2 | ✅ |
| `credivargas_pe` | Credivargas | VTEX | Peru | PEN | 53 | 45 | 0 | 0 | vtex_reviews_graphql | L2 |  |
| `cresa_ec` | Cresa EC | VTEX | Ecuador | USD | 156 | 314 | 0 | 0 | none | L2 |  |
| `cresa_ec_more` | Cresa More | VTEX | Ecuador | USD | 20 | 20 | 0 | 0 | vtex_graphql | L2 |  |
| `dismac_bo` | Dismac | Magento | Bolivia | BOB | 20 | 23 | 4 | 4 | mageplaza_ajaxsort_http | L2 |  |
| `elektra_gt` | Elektra | VTEX | Guatemala | GTQ | 60 | 60 | 2 | 2 | yotpo | L2 |  |
| `estilos_pe` | Estilos | VTEX | Peru | PEN | 49 | 49 | 0 | 0 | vtex_reviews_graphql | L2 |  |
| `evision_pa` | Evision | Other | Panama | USD | 40 | 49 | 24 | 24 | jsonld | L2 |  |
| `exito_co` | Exito | VTEX | Colombia | COP | 3274 | 2581 | 353 | 383 | vtex_reviews_rw | L2 |  |
| `falabella_cl` | Falabella | Other | Chile | CLP | 46 | 3871 | 3870 | 3870 | bazaarvoice_bfd | L2 |  |
| `ferrisariato_ec` | Ferrisariato | Other | Ecuador | USD | 50 | 50 | 0 | 0 | none | L2 |  |
| `hiraoka_pe` | Hiraoka | Magento | Peru | PEN | 20 | 20 | 0 | 0 | none | L2 |  |
| `hites_cl` | Hites | Other | Chile | CLP | 34 | 354 | 336 | 336 | verificado_ai_api | L2 |  |
| `jaher_ec` | Jaher | Other | Ecuador | USD | 0 | 0 | 0 | 0 | unknown | L2 |  |
| `japon_ec` | Japon EC | VTEX | Ecuador | USD | 145 | 145 | 0 | 0 | none | L2 |  |
| `jumbo_co` | Jumbo | VTEX | Colombia | COP | 62 | 121 | 0 | 0 | vtex_reviews_graphql | L2 |  |
| `laganga_ec` | L-Ganga | Other | Ecuador | USD | 20 | 20 | 0 | 0 | none | L2 |  |
| `laganga_ec2` | L-Ganga | Magento | Ecuador | USD | 20 | 20 | 0 | 0 | none | L2 |  |
| `lider_cl` | Lider | Other | Chile | CLP | 102 | 302 | 242 | 242 | next_data_inline | L2 |  |
| `marcimex_ec` | Marcimex | VTEX | Ecuador | USD | 94 | 185 | 0 | 0 | none | L2 |  |
| `max_gt` | Max | Other | Guatemala | GTQ | 59 | 54 | 0 | 0 | none | L2 |  |
| `mercadolibre_pe` | Mercado Libre | Other | Peru | PEN | 0 | 0 | 0 | 0 | ml_reviews_api | L2 |  |
| `metro_pe` | Metro | VTEX | Peru | PEN | 33 | 43 | 0 | 0 | vtex_reviews_graphql | L2 |  |
| `multicenter_bo` | Multicenter | VTEX | Bolivia | BOB | 6 | 6 | 0 | 0 | vtex_graphql | L2 |  |
| `oechsle_pe` | Oechsle | VTEX | Peru | PEN | 150 | 452 | 322 | 322 | bazaarvoice_bfd | L2 |  |
| `olimpica_co` | Olimpica | VTEX | Colombia | COP | 197 | 197 | 0 | 0 | none | L2 |  |
| `orvehogar_ec` | Orvehogar | VTEX | Ecuador | USD | 147 | 147 | 2 | 2 | vtex_reviews_graphql | L2 |  |
| `panafoto_pa` | Panafoto | Magento | Panama | USD | 41 | 43 | 0 | 0 | none | L2 |  |
| `paris_cl` | Paris | Other | Chile | CLP | 54 | 1352 | 1273 | 1271 | jsonld | L2 |  |
| `plazavea_pe` | Plaza Vea | VTEX | Peru | PEN | 1927 | 2384 | 0 | 0 | none | L2 |  |
| `raenco_pa` | Raenco | Magento | Panama | USD | 12 | 12 | 0 | 12 | none | L2 |  |
| `ripley_cl` | Ripley | Other | Chile | CLP | 0 | 0 | 0 | 0 | unknown_blocked | L2 | ✅ |
| `sukasa_ec` | Sukasa | Other | Ecuador | USD | 50 | 49 | 0 | 50 | none | L2 |  |
| `tecnofacil_gt` | Tecnofacil | Other | Guatemala | GTQ | 61 | 61 | 0 | 0 | none | L2 |  |
| `todohogar_ec` | Todohogar | Other | Ecuador | USD | 44 | 44 | 0 | 0 | none | L2 |  |
| `unicomer_gt` | Unicomer | Magento | Guatemala | GTQ | 37 | 37 | 0 | 0 | none | L2 |  |

### 欧洲线

| code | 名称 | 平台 | 国家 | 货币 | 商品 | 价格 | 评价 | 汇总 | 评价后端 | 保护 | 住宅IP |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|:---:|
| `alternate_de` | Alternate | Other | Germany | EUR | 23 | 0 | 0 | 0 | none | L2 |  |
| `amazon_de` | Amazon | Amazon | Germany | EUR | 2 | 0 | 13 | 13 | — | L3 |  |
| `amazon_es` | Amazon | Amazon | Spain | EUR | 36 | 226 | 238 | 240 | — | L3 |  |
| `amazon_fr` | Amazon | Amazon | France | EUR | 38 | 238 | 297 | 298 | — | L3 |  |
| `amazon_it` | Amazon | Amazon | Italy | EUR | 34 | 138 | 543 | 543 | — | L3 |  |
| `amazon_uk` | Amazon | Amazon | United Kingdom | GBP | 2 | 34 | 34 | 34 | — | L3 |  |
| `carrefour_es` | Carrefour | Other | Spain | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `cdiscount_fr` | Cdiscount | Other | France | EUR | 57 | 190 | 171 | 171 | jsonld | L2 |  |
| `citilink_ru` | Citilink | Other | Russia | RUB | 0 | 0 | 0 | 0 | none | L3 | ✅ |
| `cyberport_de` | Cyberport | Other | Germany | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `darty_fr` | Darty | Other | France | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `ebay_fr` | eBay France | Other | France | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `eldorado_ru` | Eldorado | Other | Russia | RUB | 0 | 0 | 0 | 0 | none | L3 | ✅ |
| `elgiganten_dk` | Elgiganten Denmark | Other | Denmark | DKK | 0 | 0 | 0 | 0 | none | L3 | ✅ |
| `expert_de` | Expert DE | Other | Germany | EUR | 100 | 51 | 0 | 0 | bazaarvoice_blocked | L3 |  |
| `fnac_fr` | Fnac | Other | France | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `hughes_uk` | Hughes UK | Other | United Kingdom | GBP | 171 | 89388 | 89318 | 89322 | feefo | L2 |  |
| `komplett_no` | Komplett Norway | Other | Norway | NOK | 0 | 0 | 0 | 0 | none | L3 | ✅ |
| `markselectrical_uk` | Marks Electrical | Magento | United Kingdom | GBP | 12 | 271 | 271 | 271 | feefo_api | L2 |  |
| `mediamarkt_de` | MediaMarkt | Other | Germany | EUR | 12 | 92 | 78 | 78 | bazaarvoice_private | L2 |  |
| `mediamarkt_es` | MediaMarkt | Other | Spain | EUR | 12 | 127 | 127 | 127 | bazaarvoice_private | L2 |  |
| `otto_de` | OTTO | Other | Germany | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `pccomponentes_es` | PCComponentes | Other | Spain | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `proshop_dk` | Proshop Denmark | Other | Denmark | DKK | 0 | 0 | 0 | 0 | none | L3 | ✅ |
| `samsung_uk` | Samsung UK | Brand | United Kingdom | GBP | 38 | 3811 | 3803 | 3810 | bazaarvoice_data | L2 |  |
| `saturn_de` | Saturn | Other | Germany | EUR | 12 | 24 | 0 | 0 | dom | L2 | ✅ |
| `sony_uk` | Sony UK | Brand | United Kingdom | GBP | 7 | 4329 | 4329 | 4329 | bazaarvoice_bfd | L2 |  |
| `tcl_uk` | TCL UK | Brand | United Kingdom | GBP | 108 | 1 | 8085 | 8085 | feefo | L2 |  |
| `worten_es` | Worten | Other | Spain | EUR | 0 | 0 | 0 | 0 | none | L2 | ✅ |
| `yandex_market_ru` | Yandex Market | Other | Russia | RUB | 0 | 0 | 0 | 0 | none | L3 | ✅ |

### 日本线

| code | 名称 | 平台 | 国家 | 货币 | 商品 | 价格 | 评价 | 汇总 | 评价后端 | 保护 | 住宅IP |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|:---:|
| `kakaku_jp` | 価格.com（日本，聚合站） | Other | Japan | JPY | 357 | 1011 | 808 | 135 | — | L1 |  |

### 其他 / 未分类

| code | 名称 | 平台 | 国家 | 货币 | 商品 | 价格 | 评价 | 汇总 | 评价后端 | 保护 |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|
| `efe_pe` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `espana_ec` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `falabella_co` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `generic_jsonld` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `hisense_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `hisense_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `hisense_mx` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `hisense_us` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `lacuracao_pe` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `lg_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `lg_mx` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `megamaxi_ec` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `mercadolibre_cl` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `panasonic_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `philips_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `regza_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `samsung_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L3 |
| `samsung_mx` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `samsung_us` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L3 |
| `sharp_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `sony_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L1 |
| `sony_us` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `tcl_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `tcl_jp` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `tcl_mx` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `tcl_us` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `visions_ca` | — | Brand | — | — | 0 | 0 | 0 | 0 | — | L2 |
| `walmart_ca` | — | Other | — | — | 0 | 0 | 0 | 0 | — | L3 |

## 三、平台分类与抓取策略

> 按平台分组，列出每站的关键抓取策略：是否需浏览器、价格提取方式、搜索容器选择器、搜索 URL 模式、评价后端。

### VTEX 站（17 站）

VTEX 站统一特征：价格走 Catalog API（`/api/catalog_system/pub/products/search`，纯 HTTP JSON，无需浏览器），PDP 评价区懒加载需浏览器渲染确认 app 安装；搜索页 JS 渲染，container 选 `a[href*='/p']`。评价后端多为 `vtex_reviews_graphql` / `vtex_reviews_rw`（自研 RW 实体走 public GraphQL 端点）。

| code | 名称 | 需浏览器 | 价格提取 | 搜索容器 | search_url 模式 | 评价后端 | base_url |
|---|---|:---:|---|---|---|---|---|
| `carsa_pe` | Carsa | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.carsa.pe |
| `comandato_ec` | Comandato | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.comandato.com |
| `credivargas_pe` | Credivargas | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.credivargas.pe |
| `cresa_ec` | Cresa EC | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.crecos.com |
| `cresa_ec_more` | Cresa More | 否 | jsonld | `body` | `q = urllib.parse.quote(keyword.strip())` | vtex_graphql | https://www.crecos.com |
| `elektra_gt` | Elektra | 是 | jsonld | `a[href*='/p']` | `q = urllib.parse.quote(keyword.strip())` | yotpo | https://www.elektra.com.gt |
| `estilos_pe` | Estilos | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.estilos.com.pe |
| `exito_co` | Exito | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_rw | https://www.exito.com |
| `japon_ec` | Japon EC | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.almacenesjapon.com |
| `jumbo_co` | Jumbo | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.jumbocolombia.com |
| `marcimex_ec` | Marcimex | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.marcimex.com |
| `metro_pe` | Metro | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.metro.pe |
| `multicenter_bo` | Multicenter | 否 | jsonld | `a[href*='/p'], .vtex-product-summary` | `q = urllib.parse.quote(keyword.strip())` | vtex_graphql | https://www.multicenter.com |
| `oechsle_pe` | Oechsle | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_bfd | https://www.oechsle.pe |
| `olimpica_co` | Olimpica | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.olimpica.com |
| `orvehogar_ec` | Orvehogar | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | vtex_reviews_graphql | https://www.orvehogar.com |
| `plazavea_pe` | Plaza Vea | 是 | jsonld | `a[href*='/p'], a[href*='/pdp/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.plazavea.com.pe |

### Amazon 站（8 站）

Amazon 站统一特征：搜索页 `/s?k=<kw>` 返回 `/dp/<ASIN>` 链接；PDP 同页同步抽取价格 + 概要评分 + 评价；防护 L3，需真实浏览器 + 低频 + 代理。价格走 buybox `a-offscreen`，评价 `data-hook` 选择器。评价翻页 `filter_sweep`（sortBy × filterByStar 组合扫描）；amazon.com 实测每型号硬上限 8 条。

| code | 名称 | 需浏览器 | 价格提取 | 搜索容器 | search_url 模式 | 评价后端 | base_url |
|---|---|:---:|---|---|---|---|---|
| `amazon_ca` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.ca |
| `amazon_de` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.de |
| `amazon_es` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.es |
| `amazon_fr` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.fr |
| `amazon_it` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.it |
| `amazon_mx` | Amazon | 是 | selectors | `a[href*='/dp/']` | `q = urllib.parse.urlencode({"k": str(keyword or "").strip()}, safe="")` | — | https://www.amazon.com.mx |
| `amazon_uk` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.co.uk |
| `amazon_us` | Amazon | 是 | selectors | `div[data-asin]:not([data-asin=''])` | `q = urllib.parse.urlencode({"k": keyword}, safe="")` | — | https://www.amazon.com |

### Magento 站（11 站）

Magento 站多为 L2/L3，价格通常在 JSON-LD Product.offers 或 DOM 选择器；评价后端多样（BazaarVoice / Reviews.io / Feefo / Mageplaza）。Magento 站常带 Fastly/Varnish CDN，对 IP 有风控（405/403/54113）。

| code | 名称 | 需浏览器 | 价格提取 | 搜索容器 | search_url 模式 | 评价后端 | base_url |
|---|---|:---:|---|---|---|---|---|
| `alkosto_co` | Alkosto | 是 | jsonld | `li.product-item, .product-item-link` | `q = urllib.parse.quote(keyword.strip())` | reviews_io_api | https://www.alkosto.com |
| `alkostoplus_bo` | Multicenter+ | 否 | jsonld | `a[href*='/tienda/producto/'], .product-card` | `q = urllib.parse.quote(keyword.strip())` | aggregate_only | https://alkostoplus.com |
| `artefacta_ec` | Artefacta | 是 | jsonld | `a.product-item-link, .product-item` | `q = urllib.parse.quote(keyword.strip())` | unknown_blocked | https://www.artefacta.com |
| `coral_ec` | Coral | 是 | jsonld | `li.product-item, .product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://coralhipermercados.com |
| `dismac_bo` | Dismac | 否 | jsonld | `div.product-item-pdc, .product-item-link` | `q = urllib.parse.quote(keyword.strip())` | mageplaza_ajaxsort_http | https://www.dismac.com.bo |
| `hiraoka_pe` | Hiraoka | 是 | jsonld | `li.product-item, .product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://hiraoka.com.pe |
| `laganga_ec2` | L-Ganga | 是 | selectors | `li.product-item a.product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://laganga.com |
| `markselectrical_uk` | Marks Electrical | 是 | jsonld | `a[href*='.html']` | `q = urllib.parse.quote(keyword.strip())` | feefo_api | https://www.markselectrical.co.uk |
| `panafoto_pa` | Panafoto | 是 | jsonld | `li.product-item a.product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.panafoto.com |
| `raenco_pa` | Raenco | 是 | jsonld | `li.product-item a.product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.raenco.com |
| `unicomer_gt` | Unicomer | 是 | jsonld | `li.product-item a.product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.lacuracaonline.com |

### Brand 站（25 站）

品牌官网（TV 厂商自有站）：做 SPEC（lineup → 型号 → 规格），价格/网评由零售站适配器负责。多为 Next.js / Coveo / Hybris OCC。注：另有更多品牌站（lg_ca/lg_mx、samsung_us/samsung_ca/samsung_mx、sony_us/sony_jp、tcl_us/tcl_ca/tcl_mx/tcl_jp、hisense_*、panasonic_jp、sharp_jp、regza_jp、visions_ca）以 SPEC-only adapter 形式存在，不在 retail_specs 中。

| code | 名称 | 需浏览器 | 价格提取 | 搜索容器 | search_url 模式 | 评价后端 | base_url |
|---|---|:---:|---|---|---|---|---|
| `hisense_ca` | — | 是 | — | `—` | `` | — | — |
| `hisense_jp` | — | 是 | — | `—` | `` | — | https://www.hisense.co.jp |
| `hisense_mx` | — | 是 | — | `—` | `` | — | — |
| `hisense_us` | — | 是 | — | `—` | `` | — | https://www.hisense-usa.com |
| `lg_ca` | — | 是 | — | `—` | `` | — | — |
| `lg_mx` | — | 是 | — | `—` | `` | — | — |
| `lg_us` | LG（美国） | 是 | jsonld | `a[href*='/us/tvs/lg-'], a[href*='/us/lifestyle-products/lg-']` | `` | bazaarvoice_bfd | https://www.lg.com |
| `panasonic_jp` | — | 是 | — | `—` | `` | — | https://panasonic.jp |
| `philips_ca` | — | 是 | — | `—` | `` | — | — |
| `regza_jp` | — | 是 | — | `—` | `` | — | https://www.regza.com |
| `samsung_ca` | — | 是 | — | `—` | `` | — | — |
| `samsung_mx` | — | 是 | — | `—` | `` | — | — |
| `samsung_uk` | Samsung UK | 是 | jsonld | `a[href*='/uk/tvs/']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_data | https://www.samsung.com |
| `samsung_us` | — | 是 | — | `—` | `` | — | https://www.samsung.com |
| `sharp_jp` | — | 是 | — | `—` | `` | — | https://www.sharp.co.jp |
| `sony_ca` | Sony（加拿大） | 是 | jsonld | `a[href*='/all-tvs/p/'], a[href*='/p/']` | `` | bazaarvoice_bfd | https://www.sony.ca |
| `sony_jp` | — | 是 | — | `—` | `` | — | https://www.sony.jp |
| `sony_uk` | Sony UK | 是 | selectors | `a[href*='/bravia/products/']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_bfd | https://www.sony.co.uk |
| `sony_us` | — | 是 | — | `—` | `` | — | https://electronics.sony.com |
| `tcl_ca` | — | 是 | — | `—` | `` | — | — |
| `tcl_jp` | — | 是 | — | `—` | `` | — | https://www.tcl.com |
| `tcl_mx` | — | 是 | — | `—` | `` | — | — |
| `tcl_uk` | TCL UK | 是 | — | `a[href*='/uk/en/tvs/']` | `q = urllib.parse.quote(keyword.strip())` | feefo | https://www.tcl.com |
| `tcl_us` | — | 是 | — | `—` | `` | — | https://us.tcl.com |
| `visions_ca` | — | 是 | — | `—` | `q = urllib.parse.urlencode({"q": keyword})` | — | https://www.visions.ca |

### Other 站（58 站）

其他独立站：Demandware/SFCC（falabella/paris/hites/abc）、Next.js（ripley/lider/max/sukasa/ferrisariato/todohogar）、PWA/React（mediamarkt_es）、Costco/BestBuy/Walmart/eBay/Mercado Libre/kakaku/Yandex 等自研或比价架构，无统一抓取模式。

| code | 名称 | 子架构 | 需浏览器 | 价格提取 | 搜索容器 | search_url 模式 | 评价后端 | base_url |
|---|---|---|:---:|---|---|---|---|---|
| `abc_cl` | ABC | Demandware/SFCC | 是 | jsonld | `a.product-item-link, .product-tile` | `q = urllib.parse.quote(keyword.strip())` | powerreviews_api | https://www.abc.cl |
| `alternate_de` | Alternate | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[href*='/p/'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.alternate.de |
| `bestbuy_ca` | Best Buy | BestBuy 自研 | 是 | jsonld | `a[href*='/product/']` | `"""★robots.txt 明确 Disallow: /en-ca/search —— 不要用于生产抓取。` | bazaarvoice_bfd | https://www.bestbuy.ca |
| `bestbuy_us` | Best Buy | BestBuy 自研 | 是 | jsonld | `ol.sku-item-list > li.sku-item, li.sku-item, div.shop-sku-list-item` | `"""搜索页。带 intl=nosplash 抑制国际选择页插屏；翻页参数是 cp。` | — | https://www.bestbuy.com |
| `canadiantire_ca` | Canadian Tire | — | 是 | selectors | `a[href*='/pdp/']` | `q = urllib.parse.urlencode({"q": keyword})` | — | https://www.canadiantire.ca |
| `carrefour_es` | Carrefour | — | 是 | jsonld | `a[href*='/p/'], .product-item` | `` | none | https://www.carrefour.es |
| `cdiscount_fr` | Cdiscount | — | 是 | jsonld | `a[href*='/f-']` | `q = urllib.parse.quote(keyword.strip())` | jsonld | https://www.cdiscount.com |
| `citilink_ru` | Citilink | — | 是 | jsonld | `a[href*='/product/'], a[href*='/cat/detail/'], a[href*='/catalog/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.citilink.ru |
| `coppel_mx` | Coppel | — | 是 | jsonld | `a.cpl-card__body[href*='/pdp/']` | `q = urllib.parse.quote(str(keyword or "").strip(), safe="")` | — | https://www.coppel.com |
| `costco_ca` | Costco Canada | Costco 自研 | 是 | jsonld | `a[href*='.product.']` | `q = urllib.parse.urlencode({"keyword": keyword})` | bazaarvoice_bfd | https://www.costco.ca |
| `costco_us` | Costco | Costco 自研 | 是 | jsonld | `a[href*='.product.']` | `q = urllib.parse.urlencode({"keyword": keyword})` | bazaarvoice_bfd | https://www.costco.com |
| `cyberport_de` | Cyberport | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[href*='/p/'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.cyberport.de |
| `darty_fr` | Darty | — | 是 | jsonld | `a.product_name, a[href*='/produits/'], a[href*='/p']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.darty.com |
| `ebay_fr` | eBay France | eBay | 是 | jsonld | `a.s-item__link, a[href*='/itm/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.ebay.fr |
| `efe_pe` | — | — | 否 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.efe.com.pe |
| `eldorado_ru` | Eldorado | — | 是 | jsonld | `a[href*='/product/'], a[href*='/cat/detail/'], a[href*='/catalog/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.eldorado.ru |
| `elgiganten_dk` | Elgiganten Denmark | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.elgiganten.dk |
| `espana_ec` | — | — | 是 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://almacenesespana.ec |
| `evision_pa` | Evision | — | 是 | selectors | `a[href*='/products/']` | `q = urllib.parse.quote(keyword.strip())` | jsonld | https://www.evisionstore.com |
| `expert_de` | Expert DE | — | 是 | selectors | `a[href*='/shop/']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_blocked | https://www.expert.de |
| `falabella_cl` | Falabella | Next.js | 是 | jsonld | `script[type='application/json']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_bfd | https://www.falabella.com |
| `falabella_co` | — | — | 是 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.falabella.com.co |
| `ferrisariato_ec` | Ferrisariato | — | 是 | jsonld | `a.product-item-link, .product-card` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.ferrisariato.com |
| `fnac_fr` | Fnac | — | 是 | jsonld | `a.Article-title, a[href*='/a'], a[class*='ArticleItem']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.fnac.com |
| `generic_jsonld` | — | — | 否 | — | `—` | `raise NotImplementedError(` | — | — |
| `hites_cl` | Hites | Demandware/SFCC | 否 | jsonld | `a.product-item-link, .product-tile` | `q = urllib.parse.quote(keyword.strip())` | verificado_ai_api | https://www.hites.com |
| `hughes_uk` | Hughes UK | — | 是 | selectors | `a[href*='/product/']` | `q = urllib.parse.quote(keyword.strip())` | feefo | https://www.hughes.co.uk |
| `jaher_ec` | Jaher | — | 是 | jsonld | `a[href*='/producto'], .product-item-link, .product-card` | `q = urllib.parse.quote(keyword.strip())` | unknown | https://www.jaher.com.ec |
| `kakaku_jp` | 価格.com（日本，聚合站） | kakaku 比价 | 否 | selectors | `.p-product_name a, a[href*='/item/']` | `kw = urllib.parse.quote(keyword.strip())` | — | https://kakaku.com |
| `komplett_no` | Komplett Norway | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.komplett.no |
| `lacuracao_pe` | — | — | 否 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.lacuracao.pe |
| `laganga_ec` | L-Ganga | — | 是 | jsonld | `li.product-item, .product-item-link` | `q = urllib.parse.quote(keyword.strip())` | none | https://laganga.com |
| `leons_ca` | Leon's（加拿大） | — | 是 | jsonld | `a[href*='/products/']` | `q = urllib.parse.urlencode({"q": keyword})` | lflgroup_api | https://www.leons.ca |
| `lider_cl` | Lider | Next.js | 否 | jsonld | `script#__NEXT_DATA__` | `q = urllib.parse.quote(keyword.strip())` | next_data_inline | https://www.lider.cl |
| `liverpool_mx` | Liverpool | — | 是 | selectors | `a[data-testid$='-card-card-link']` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.liverpool.com.mx |
| `max_gt` | Max | Next.js | 是 | jsonld | `a[href*='/p']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.max.com.gt |
| `mediamarkt_de` | MediaMarkt | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[href*='/p/'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_private | https://www.mediamarkt.de |
| `mediamarkt_es` | MediaMarkt | PWA/React | 是 | jsonld | `a[href*='/es/product/']` | `q = urllib.parse.quote(keyword.strip())` | bazaarvoice_private | https://www.mediamarkt.es |
| `megamaxi_ec` | — | — | 是 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.megamaxi.com |
| `mercadolibre_cl` | — | — | 是 | — | `—` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.mercadolibre.cl |
| `mercadolibre_pe` | Mercado Libre | Mercado Libre | 是 | jsonld | `a.ui-search-link, .ui-search-item` | `q = urllib.parse.quote(keyword.strip())` | ml_reviews_api | https://www.mercadolibre.com.pe |
| `otto_de` | OTTO | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[href*='/p/'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.otto.de |
| `palacio_mx` | Palacio | — | 是 | selectors | `a[href$='.html']` | `q = urllib.parse.quote(str(keyword or "").strip())` | — | https://www.elpalaciodehierro.com |
| `paris_cl` | Paris | Demandware/SFCC | 是 | jsonld | `a.product-item-link, .product-tile` | `q = urllib.parse.quote(keyword.strip())` | jsonld | https://www.paris.cl |
| `pccomponentes_es` | PCComponentes | — | 是 | jsonld | `a[href*='/p/'], .product-item` | `` | none | https://www.pccomponentes.com |
| `proshop_dk` | Proshop Denmark | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.proshop.dk |
| `ripley_cl` | Ripley | Next.js | 是 | jsonld | `a[href*='/producto/'], .product-card` | `q = urllib.parse.quote(keyword.strip())` | unknown_blocked | https://simple.ripley.cl |
| `sams_mx` | Sam's | — | 是 | jsonld | `[data-testid*='product'], article[class*='product'], li[class*='product']` | `"""站内搜索。路由是 `/search?q=`。` | — | https://www.sams.com.mx |
| `saturn_de` | Saturn | — | 是 | jsonld | `a[href*='/product'], a[href*='/produkt'], a[href*='/p/'], a[class*='product']` | `q = urllib.parse.quote(keyword.strip())` | dom | https://www.saturn.de |
| `sukasa_ec` | Sukasa | Next.js | 是 | jsonld | `a[href*='/productos/'], .product-card` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.sukasa.com |
| `tecnofacil_gt` | Tecnofacil | Next.js | 是 | jsonld | `a[href*='/p']` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.tecnofacil.com.gt |
| `thebrick_ca` | The Brick（加拿大） | — | 是 | jsonld | `a[href*='/products/']` | `q = urllib.parse.urlencode({"q": keyword})` | — | https://www.thebrick.com |
| `todohogar_ec` | Todohogar | Next.js | 是 | jsonld | `a[href*='/productos/'], .product-card` | `q = urllib.parse.quote(keyword.strip())` | none | https://www.todohogar.com |
| `walmart_ca` | — | — | 是 | — | `—` | `q = urllib.parse.urlencode({"q": keyword})` | — | https://www.walmart.ca |
| `walmart_mx` | Walmart | Walmart 自研 | 是 | jsonld | `[data-item-id], [data-testid*='product'], div[data-automation-id*='product']` | `q = urllib.parse.quote(keyword.strip())` | — | https://www.walmart.com.mx |
| `walmart_us` | Walmart | Walmart 自研 | 是 | jsonld | `div[data-item-id], div[data-testid='list-view'] > div` | `q = urllib.parse.urlencode({"q": keyword})` | — | https://www.walmart.com |
| `worten_es` | Worten | — | 是 | jsonld | `a[href*='/p/'], .product-item` | `` | none | https://www.worten.es |
| `yandex_market_ru` | Yandex Market | Yandex Market | 是 | jsonld | `a[href*='/product/'], a[href*='/cat/detail/'], a[href*='/catalog/']` | `q = urllib.parse.quote(keyword.strip())` | none | https://market.yandex.ru |

## 四、评价后端汇总

共 23 种评价后端（含 `none`/`unknown`/`*_blocked`/`aggregate_only` 等无评价/被封锁标记）；剔除标记后约 18 种真实评价后端。

| 评价后端 | 站数 | 站点 |
|---|---:|---|
| none | 33 | `alternate_de`, `carrefour_es`, `citilink_ru`, `comandato_ec`, `coral_ec`, `cresa_ec`, `cyberport_de`, `darty_fr`, `ebay_fr`, `eldorado_ru`, `elgiganten_dk`, `ferrisariato_ec`, `fnac_fr`, `hiraoka_pe`, `japon_ec`, `komplett_no`, `laganga_ec`, `laganga_ec2`, `marcimex_ec`, `max_gt`, `olimpica_co`, `otto_de`, `panafoto_pa`, `pccomponentes_es`, `plazavea_pe`, `proshop_dk`, `raenco_pa`, `sukasa_ec`, `tecnofacil_gt`, `todohogar_ec`, `unicomer_gt`, `worten_es`, `yandex_market_ru` |
| bazaarvoice_bfd | 8 | `bestbuy_ca`, `costco_ca`, `costco_us`, `falabella_cl`, `lg_us`, `oechsle_pe`, `sony_ca`, `sony_uk` |
| vtex_reviews_graphql | 6 | `carsa_pe`, `credivargas_pe`, `estilos_pe`, `jumbo_co`, `metro_pe`, `orvehogar_ec` |
| jsonld | 3 | `cdiscount_fr`, `evision_pa`, `paris_cl` |
| unknown_blocked | 2 | `artefacta_ec`, `ripley_cl` |
| vtex_graphql | 2 | `cresa_ec_more`, `multicenter_bo` |
| feefo | 2 | `hughes_uk`, `tcl_uk` |
| bazaarvoice_private | 2 | `mediamarkt_de`, `mediamarkt_es` |
| powerreviews_api | 1 | `abc_cl` |
| reviews_io_api | 1 | `alkosto_co` |
| aggregate_only | 1 | `alkostoplus_bo` |
| mageplaza_ajaxsort_http | 1 | `dismac_bo` |
| yotpo | 1 | `elektra_gt` |
| vtex_reviews_rw | 1 | `exito_co` |
| bazaarvoice_blocked | 1 | `expert_de` |
| verificado_ai_api | 1 | `hites_cl` |
| unknown | 1 | `jaher_ec` |
| lflgroup_api | 1 | `leons_ca` |
| next_data_inline | 1 | `lider_cl` |
| feefo_api | 1 | `markselectrical_uk` |
| ml_reviews_api | 1 | `mercadolibre_pe` |
| bazaarvoice_data | 1 | `samsung_uk` |
| dom | 1 | `saturn_de` |

## 五、硬编码抓取入口表

> 每站的硬编码入口：adapter 路径 + base_url + search_url 模式 + 平台 + 价格提取 + 评价后端 + 保护等级 + 是否需住宅IP。后续硬编码抓取以此表为准。

| code | adapter | 平台 | base_url | search_path | 价格 | 评价后端 | 保护 | 浏览器 | 住宅IP |
|---|---|---|---|---|---|---|---|:---:|:---:|
| `abc_cl` | overseas/sites/abc_cl/adapter.py | Other | https://www.abc.cl | `/buscar?q={q}` | jsonld | powerreviews_api | L2 | ✓ |  |
| `alkosto_co` | overseas/sites/alkosto_co/adapter.py | Magento | https://www.alkosto.com | `/search?q={q}` | jsonld | reviews_io_api | L2 | ✓ |  |
| `alkostoplus_bo` | overseas/sites/alkostoplus_bo/adapter.py | Magento | https://alkostoplus.com | `/tienda?s={q}` | jsonld | aggregate_only | L2 | ✗ |  |
| `alternate_de` | overseas/sites/alternate_de/adapter.py | Other | https://www.alternate.de | `/Alle-Fernseher/{q}` | jsonld | none | L2 | ✓ |  |
| `amazon_ca` | overseas/sites/amazon_ca/adapter.py | Amazon | https://www.amazon.ca | `—` | selectors | — | L3 | ✓ |  |
| `amazon_de` | overseas/sites/amazon_de/adapter.py | Amazon | https://www.amazon.de | `—` | selectors | — | L3 | ✓ |  |
| `amazon_es` | overseas/sites/amazon_es/adapter.py | Amazon | https://www.amazon.es | `—` | selectors | — | L3 | ✓ |  |
| `amazon_fr` | overseas/sites/amazon_fr/adapter.py | Amazon | https://www.amazon.fr | `—` | selectors | — | L3 | ✓ |  |
| `amazon_it` | overseas/sites/amazon_it/adapter.py | Amazon | https://www.amazon.it | `—` | selectors | — | L3 | ✓ |  |
| `amazon_mx` | overseas/sites/amazon_mx/adapter.py | Amazon | https://www.amazon.com.mx | `—` | selectors | — | L3 | ✓ |  |
| `amazon_uk` | overseas/sites/amazon_uk/adapter.py | Amazon | https://www.amazon.co.uk | `—` | selectors | — | L3 | ✓ |  |
| `amazon_us` | overseas/sites/amazon_us/adapter.py | Amazon | https://www.amazon.com | `—` | selectors | — | L3 | ✓ |  |
| `artefacta_ec` | overseas/sites/artefacta_ec/adapter.py | Magento | https://www.artefacta.com | `/catalogsearch/result/?q={q}` | jsonld | unknown_blocked | L2 | ✓ |  |
| `bestbuy_ca` | overseas/sites/bestbuy_ca/adapter.py | Other | https://www.bestbuy.ca | `—` | jsonld | bazaarvoice_bfd | L3 | ✓ |  |
| `bestbuy_us` | overseas/sites/bestbuy_us/adapter.py | Other | https://www.bestbuy.com | `—` | jsonld | — | L3 | ✓ |  |
| `canadiantire_ca` | overseas/sites/canadiantire_ca/adapter.py | Other | https://www.canadiantire.ca | `—` | selectors | — | L3 | ✓ |  |
| `carrefour_es` | — | Other | https://www.carrefour.es | `—` | jsonld | none | L2 | ✓ | ✓ |
| `carsa_pe` | overseas/sites/carsa_pe/adapter.py | VTEX | https://www.carsa.pe | `/buscar?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `cdiscount_fr` | overseas/sites/cdiscount_fr/adapter.py | Other | https://www.cdiscount.com | `/search/10/{q}.html` | jsonld | jsonld | L2 | ✓ |  |
| `citilink_ru` | overseas/sites/citilink_ru/adapter.py | Other | https://www.citilink.ru | `/catalog/televizory/` | jsonld | none | L3 | ✓ | ✓ |
| `comandato_ec` | overseas/sites/comandato_ec/adapter.py | VTEX | https://www.comandato.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `coppel_mx` | overseas/sites/coppel_mx/adapter.py | Other | https://www.coppel.com | `—` | jsonld | — | L2 | ✓ |  |
| `coral_ec` | overseas/sites/coral_ec/adapter.py | Magento | https://coralhipermercados.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ | ✓ |
| `costco_ca` | overseas/sites/costco_ca/adapter.py | Other | https://www.costco.ca | `—` | jsonld | bazaarvoice_bfd | L2 | ✓ |  |
| `costco_us` | overseas/sites/costco_us/adapter.py | Other | https://www.costco.com | `—` | jsonld | bazaarvoice_bfd | L3 | ✓ |  |
| `credivargas_pe` | overseas/sites/credivargas_pe/adapter.py | VTEX | https://www.credivargas.pe | `/search?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `cresa_ec` | overseas/sites/cresa_ec/adapter.py | VTEX | https://www.crecos.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `cresa_ec_more` | overseas/sites/cresa_ec_more/adapter.py | VTEX | https://www.crecos.com | `/api/catalog_system/pub/products/search?ft={q}` | jsonld | vtex_graphql | L2 | ✗ |  |
| `cyberport_de` | overseas/sites/cyberport_de/adapter.py | Other | https://www.cyberport.de | `/?suche={q}` | jsonld | none | L2 | ✓ | ✓ |
| `darty_fr` | overseas/sites/darty_fr/adapter.py | Other | https://www.darty.com | `/nav/recherche/{q}.html` | jsonld | none | L2 | ✓ | ✓ |
| `dismac_bo` | overseas/sites/dismac_bo/adapter.py | Magento | https://www.dismac.com.bo | `/buscar?q={q}` | jsonld | mageplaza_ajaxsort_http | L2 | ✗ |  |
| `ebay_fr` | overseas/sites/ebay_fr/adapter.py | Other | https://www.ebay.fr | `/sch/i.html?_nkw={q}` | jsonld | none | L2 | ✓ | ✓ |
| `efe_pe` | overseas/sites/efe_pe/adapter.py | Other | https://www.efe.com.pe | `/catalogsearch/result/?q={q}` | — | — | L2 | ✗ |  |
| `eldorado_ru` | overseas/sites/eldorado_ru/adapter.py | Other | https://www.eldorado.ru | `/catalog/televizory/` | jsonld | none | L3 | ✓ | ✓ |
| `elektra_gt` | overseas/sites/elektra_gt/adapter.py | VTEX | https://www.elektra.com.gt | `/buscar?q={q}` | jsonld | yotpo | L2 | ✓ |  |
| `elgiganten_dk` | overseas/sites/elgiganten_dk/adapter.py | Other | https://www.elgiganten.dk | `/search?SearchTerm={q}` | jsonld | none | L3 | ✓ | ✓ |
| `espana_ec` | overseas/sites/espana_ec/adapter.py | Other | https://almacenesespana.ec | `/buscar?q={q}` | — | — | L2 | ✓ |  |
| `estilos_pe` | overseas/sites/estilos_pe/adapter.py | VTEX | https://www.estilos.com.pe | `/busqueda?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `evision_pa` | overseas/sites/evision_pa/adapter.py | Other | https://www.evisionstore.com | `/category-brand/all/televisores` | selectors | jsonld | L2 | ✓ |  |
| `exito_co` | overseas/sites/exito_co/adapter.py | VTEX | https://www.exito.com | `/buscar?q={q}` | jsonld | vtex_reviews_rw | L2 | ✓ |  |
| `expert_de` | overseas/sites/expert_de/adapter.py | Other | https://www.expert.de | `/shop/search?query={q}` | selectors | bazaarvoice_blocked | L3 | ✓ |  |
| `falabella_cl` | overseas/sites/falabella_cl/adapter.py | Other | https://www.falabella.com | `/search?q={q}` | jsonld | bazaarvoice_bfd | L2 | ✓ |  |
| `falabella_co` | overseas/sites/falabella_co/adapter.py | Other | https://www.falabella.com.co | `/search?q={q}` | — | — | L2 | ✓ |  |
| `ferrisariato_ec` | overseas/sites/ferrisariato_ec/adapter.py | Other | https://www.ferrisariato.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `fnac_fr` | overseas/sites/fnac_fr/adapter.py | Other | https://www.fnac.com | `/SearchResult/ResultList.aspx?Search={q}` | jsonld | none | L2 | ✓ | ✓ |
| `generic_jsonld` | overseas/sites/generic_jsonld/adapter.py | Other | — | `—` | — | — | L1 | ✗ |  |
| `hiraoka_pe` | overseas/sites/hiraoka_pe/adapter.py | Magento | https://hiraoka.com.pe | `/catalogsearch/result/?q={q}` | jsonld | none | L2 | ✓ |  |
| `hisense_ca` | overseas/sites/hisense_ca/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `hisense_jp` | overseas/sites/hisense_jp/adapter.py | Brand | https://www.hisense.co.jp | `—` | — | — | L1 | ✓ |  |
| `hisense_mx` | overseas/sites/hisense_mx/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `hisense_us` | overseas/sites/hisense_us/adapter.py | Brand | https://www.hisense-usa.com | `—` | — | — | L1 | ✓ |  |
| `hites_cl` | overseas/sites/hites_cl/adapter.py | Other | https://www.hites.com | `/buscar?q={q}` | jsonld | verificado_ai_api | L2 | ✗ |  |
| `hughes_uk` | overseas/sites/hughes_uk/adapter.py | Other | https://www.hughes.co.uk | `/search?query={q}` | selectors | feefo | L2 | ✓ |  |
| `jaher_ec` | overseas/sites/jaher_ec/adapter.py | Other | https://www.jaher.com.ec | `/buscar?q={q}` | jsonld | unknown | L2 | ✓ |  |
| `japon_ec` | overseas/sites/japon_ec/adapter.py | VTEX | https://www.almacenesjapon.com | `/search?q={q}` | jsonld | none | L2 | ✓ |  |
| `jumbo_co` | overseas/sites/jumbo_co/adapter.py | VTEX | https://www.jumbocolombia.com | `/buscar?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `kakaku_jp` | overseas/sites/kakaku_jp/adapter.py | Other | https://kakaku.com | `—` | selectors | — | L1 | ✗ |  |
| `komplett_no` | overseas/sites/komplett_no/adapter.py | Other | https://www.komplett.no | `/search?q={q}` | jsonld | none | L3 | ✓ | ✓ |
| `lacuracao_pe` | overseas/sites/lacuracao_pe/adapter.py | Other | https://www.lacuracao.pe | `/catalogsearch/result/?q={q}` | — | — | L2 | ✗ |  |
| `laganga_ec` | overseas/sites/laganga_ec/adapter.py | Other | https://laganga.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `laganga_ec2` | overseas/sites/laganga_ec2/adapter.py | Magento | https://laganga.com | `/catalogsearch/result/?q={q}` | selectors | none | L2 | ✓ |  |
| `leons_ca` | overseas/sites/leons_ca/adapter.py | Other | https://www.leons.ca | `—` | jsonld | lflgroup_api | L3 | ✓ |  |
| `lg_ca` | overseas/sites/lg_ca/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `lg_mx` | overseas/sites/lg_mx/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `lg_us` | overseas/sites/lg_us/adapter.py | Brand | https://www.lg.com | `—` | jsonld | bazaarvoice_bfd | L2 | ✓ |  |
| `lider_cl` | overseas/sites/lider_cl/adapter.py | Other | https://www.lider.cl | `/buscar?q={q}` | jsonld | next_data_inline | L2 | ✗ |  |
| `liverpool_mx` | overseas/sites/liverpool_mx/adapter.py | Other | https://www.liverpool.com.mx | `—` | selectors | — | L2 | ✓ |  |
| `marcimex_ec` | overseas/sites/marcimex_ec/adapter.py | VTEX | https://www.marcimex.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `markselectrical_uk` | overseas/sites/markselectrical_uk/adapter.py | Magento | https://www.markselectrical.co.uk | `/catalogsearch/result/?q={q}` | jsonld | feefo_api | L2 | ✓ |  |
| `max_gt` | overseas/sites/max_gt/adapter.py | Other | https://www.max.com.gt | `/search?q={q}` | jsonld | none | L2 | ✓ |  |
| `mediamarkt_de` | overseas/sites/mediamarkt_de/adapter.py | Other | https://www.mediamarkt.de | `/de/search.html?query={q}` | jsonld | bazaarvoice_private | L2 | ✓ |  |
| `mediamarkt_es` | overseas/sites/mediamarkt_es/adapter.py | Other | https://www.mediamarkt.es | `/es/search.html?query={q}` | jsonld | bazaarvoice_private | L2 | ✓ |  |
| `megamaxi_ec` | overseas/sites/megamaxi_ec/adapter.py | Other | https://www.megamaxi.com | `/buscar?q={q}` | — | — | L2 | ✓ |  |
| `mercadolibre_cl` | overseas/sites/mercadolibre_cl/adapter.py | Other | https://www.mercadolibre.cl | `/listado/{q}` | — | — | L2 | ✓ |  |
| `mercadolibre_pe` | overseas/sites/mercadolibre_pe/adapter.py | Other | https://www.mercadolibre.com.pe | `/listado/{q}` | jsonld | ml_reviews_api | L2 | ✓ |  |
| `metro_pe` | overseas/sites/metro_pe/adapter.py | VTEX | https://www.metro.pe | `/busca?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `multicenter_bo` | overseas/sites/multicenter_bo/adapter.py | VTEX | https://www.multicenter.com | `/buscar?q={q}` | jsonld | vtex_graphql | L2 | ✗ |  |
| `oechsle_pe` | overseas/sites/oechsle_pe/adapter.py | VTEX | https://www.oechsle.pe | `/buscar?q={q}` | jsonld | bazaarvoice_bfd | L2 | ✓ |  |
| `olimpica_co` | overseas/sites/olimpica_co/adapter.py | VTEX | https://www.olimpica.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `orvehogar_ec` | overseas/sites/orvehogar_ec/adapter.py | VTEX | https://www.orvehogar.com | `/buscar?q={q}` | jsonld | vtex_reviews_graphql | L2 | ✓ |  |
| `otto_de` | overseas/sites/otto_de/adapter.py | Other | https://www.otto.de | `/suche/{q}/` | jsonld | none | L2 | ✓ | ✓ |
| `palacio_mx` | overseas/sites/palacio_mx/adapter.py | Other | https://www.elpalaciodehierro.com | `—` | selectors | — | L2 | ✓ |  |
| `panafoto_pa` | overseas/sites/panafoto_pa/adapter.py | Magento | https://www.panafoto.com | `/catalogsearch/result/?q={q}` | jsonld | none | L2 | ✓ |  |
| `panasonic_jp` | overseas/sites/panasonic_jp/adapter.py | Brand | https://panasonic.jp | `—` | — | — | L1 | ✓ |  |
| `paris_cl` | overseas/sites/paris_cl/adapter.py | Other | https://www.paris.cl | `/buscar?q={q}` | jsonld | jsonld | L2 | ✓ |  |
| `pccomponentes_es` | — | Other | https://www.pccomponentes.com | `—` | jsonld | none | L2 | ✓ | ✓ |
| `philips_ca` | overseas/sites/philips_ca/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `plazavea_pe` | overseas/sites/plazavea_pe/adapter.py | VTEX | https://www.plazavea.com.pe | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `proshop_dk` | overseas/sites/proshop_dk/adapter.py | Other | https://www.proshop.dk | `/search?q={q}` | jsonld | none | L3 | ✓ | ✓ |
| `raenco_pa` | overseas/sites/raenco_pa/adapter.py | Magento | https://www.raenco.com | `/catalogsearch/result/?q={q}` | jsonld | none | L2 | ✓ |  |
| `regza_jp` | overseas/sites/regza_jp/adapter.py | Brand | https://www.regza.com | `—` | — | — | L1 | ✓ |  |
| `ripley_cl` | overseas/sites/ripley_cl/adapter.py | Other | https://simple.ripley.cl | `/search?q={q}` | jsonld | unknown_blocked | L2 | ✓ | ✓ |
| `sams_mx` | overseas/sites/sams_mx/adapter.py | Other | https://www.sams.com.mx | `—` | jsonld | — | L2 | ✓ |  |
| `samsung_ca` | overseas/sites/samsung_ca/adapter.py | Brand | — | `—` | — | — | L3 | ✓ |  |
| `samsung_mx` | overseas/sites/samsung_mx/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `samsung_uk` | overseas/sites/samsung_uk/adapter.py | Brand | https://www.samsung.com | `/uk/tvs/?q={q}` | jsonld | bazaarvoice_data | L2 | ✓ |  |
| `samsung_us` | overseas/sites/samsung_us/adapter.py | Brand | https://www.samsung.com | `—` | — | — | L3 | ✓ |  |
| `saturn_de` | overseas/sites/saturn_de/adapter.py | Other | https://www.saturn.de | `/de/search.html?query={q}` | jsonld | dom | L2 | ✓ | ✓ |
| `sharp_jp` | overseas/sites/sharp_jp/adapter.py | Brand | https://www.sharp.co.jp | `—` | — | — | L2 | ✓ |  |
| `sony_ca` | overseas/sites/sony_ca/adapter.py | Brand | https://www.sony.ca | `—` | jsonld | bazaarvoice_bfd | L3 | ✓ |  |
| `sony_jp` | overseas/sites/sony_jp/adapter.py | Brand | https://www.sony.jp | `—` | — | — | L1 | ✓ |  |
| `sony_uk` | overseas/sites/sony_uk/adapter.py | Brand | https://www.sony.co.uk | `/search?query={q}` | selectors | bazaarvoice_bfd | L2 | ✓ |  |
| `sony_us` | overseas/sites/sony_us/adapter.py | Brand | https://electronics.sony.com | `—` | — | — | L2 | ✓ |  |
| `sukasa_ec` | overseas/sites/sukasa_ec/adapter.py | Other | https://www.sukasa.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `tcl_ca` | overseas/sites/tcl_ca/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `tcl_jp` | overseas/sites/tcl_jp/adapter.py | Brand | https://www.tcl.com | `—` | — | — | L2 | ✓ |  |
| `tcl_mx` | overseas/sites/tcl_mx/adapter.py | Brand | — | `—` | — | — | L2 | ✓ |  |
| `tcl_uk` | overseas/sites/tcl_uk/adapter.py | Brand | https://www.tcl.com | `/uk/en/search?q={q}` | — | feefo | L2 | ✓ |  |
| `tcl_us` | overseas/sites/tcl_us/adapter.py | Brand | https://us.tcl.com | `—` | — | — | L2 | ✓ |  |
| `tecnofacil_gt` | overseas/sites/tecnofacil_gt/adapter.py | Other | https://www.tecnofacil.com.gt | `/search?q={q}` | jsonld | none | L2 | ✓ |  |
| `thebrick_ca` | overseas/sites/thebrick_ca/adapter.py | Other | https://www.thebrick.com | `—` | jsonld | — | L3 | ✓ | ✓ |
| `todohogar_ec` | overseas/sites/todohogar_ec/adapter.py | Other | https://www.todohogar.com | `/buscar?q={q}` | jsonld | none | L2 | ✓ |  |
| `unicomer_gt` | overseas/sites/unicomer_gt/adapter.py | Magento | https://www.lacuracaonline.com | `/catalogsearch/result/?q={q}` | jsonld | none | L2 | ✓ |  |
| `visions_ca` | overseas/sites/visions_ca/adapter.py | Brand | https://www.visions.ca | `—` | — | — | L2 | ✓ |  |
| `walmart_ca` | overseas/sites/walmart_ca/adapter.py | Other | https://www.walmart.ca | `—` | — | — | L3 | ✓ |  |
| `walmart_mx` | overseas/sites/walmart_mx/adapter.py | Other | https://www.walmart.com.mx | `—` | jsonld | — | L3 | ✓ |  |
| `walmart_us` | overseas/sites/walmart_us/adapter.py | Other | https://www.walmart.com | `—` | jsonld | — | L3 | ✓ |  |
| `worten_es` | — | Other | https://www.worten.es | `—` | jsonld | none | L2 | ✓ | ✓ |
| `yandex_market_ru` | overseas/sites/yandex_market_ru/adapter.py | Other | https://market.yandex.ru | `/catalog/televizory/` | jsonld | none | L3 | ✓ | ✓ |

## 六、需住宅 IP 的站

共 18 站需住宅 IP（当前出口 IP 被封 / 403 / 429 / 503，或 `reviews.source=none/blocked` 因封锁拿不到评价，需住宅代理校验）。

| code | 名称 | 平台 | 区域 | 国家 | 评价后端 | 封锁原因（来自 spec `_block_note`） |
|---|---|---|---|---|---|---|
| `carrefour_es` | Carrefour | Other | EU | Spain | none | （spec 标注 reviews.source=none/blocked） |
| `citilink_ru` | Citilink | Other | EU | Russia | none | 当前出口IP(非俄罗斯)被拦截: HTTP 429 Too Many Requests（反爬限流，非俄IP触发） |
| `coral_ec` | Coral | Magento | SA | Ecuador | none | （spec 标注 reviews.source=none/blocked） |
| `cyberport_de` | Cyberport | Other | EU | Germany | none | 探测时被拦: http_403 |
| `darty_fr` | Darty | Other | EU | France | none | 探测时被拦: http_403 |
| `ebay_fr` | eBay France | Other | EU | France | none | 探测时被拦: http_403 |
| `eldorado_ru` | Eldorado | Other | EU | Russia | none | 当前出口IP(非俄罗斯)被拦截: HTTP 503 Service Unavailable（地理封锁，非俄罗斯出口IP被拒） |
| `elgiganten_dk` | Elgiganten Denmark | Other | EU | Denmark | none | 探测时被拦: HTTP 429（已知 Elgiganten 用 Vercel 挑战 + 速率限制） |
| `fnac_fr` | Fnac | Other | EU | France | none | 探测时被拦: http_403 |
| `komplett_no` | Komplett Norway | Other | EU | Norway | none | 探测时 HTTP 200 可达但产品提取失败: 站点用 Algolia + algonomy-product-cards 客户端渲染，且首页是 Google Consent Mode v2 + cookieinformation.com 同 |
| `otto_de` | OTTO | Other | EU | Germany | none | 探测时被拦: not_logged_in |
| `pccomponentes_es` | PCComponentes | Other | EU | Spain | none | （spec 标注 reviews.source=none/blocked） |
| `proshop_dk` | Proshop Denmark | Other | EU | Denmark | none | 探测时被拦: HTTP 403 |
| `ripley_cl` | Ripley | Other | SA | Chile | unknown_blocked | （spec 标注 reviews.source=none/blocked） |
| `saturn_de` | Saturn | Other | EU | Germany | dom | （spec 标注 reviews.source=none/blocked） |
| `thebrick_ca` | The Brick（加拿大） | Other | NA | Canada | — | （spec 标注 reviews.source=none/blocked） |
| `worten_es` | Worten | Other | EU | Spain | none | （spec 标注 reviews.source=none/blocked） |
| `yandex_market_ru` | Yandex Market | Other | EU | Russia | none | 当前出口IP(非俄罗斯)被拦截: HTTP 403 Forbidden（地域限制，需俄罗斯IP+Yandex账号态） |

## 七、安全机制配置

> 按保护等级分组。`L1`=温和(纯HTTP) `L2`=中等(真实浏览器) `L3`=强防(浏览器+低频+代理/人工)。

### L1 温和（7 站）

| code | 名称 | 平台 | 需浏览器 | 评价后端 | base_url |
|---|---|---|:---:|---|---|
| `generic_jsonld` | — | Other | ✗ | — | — |
| `hisense_jp` | — | Brand | ✓ | — | https://www.hisense.co.jp |
| `hisense_us` | — | Brand | ✓ | — | https://www.hisense-usa.com |
| `kakaku_jp` | 価格.com（日本，聚合站） | Other | ✗ | — | https://kakaku.com |
| `panasonic_jp` | — | Brand | ✓ | — | https://panasonic.jp |
| `regza_jp` | — | Brand | ✓ | — | https://www.regza.com |
| `sony_jp` | — | Brand | ✓ | — | https://www.sony.jp |

### L2 中等（85 站）

| code | 名称 | 平台 | 需浏览器 | 评价后端 | base_url |
|---|---|---|:---:|---|---|
| `abc_cl` | ABC | Other | ✓ | powerreviews_api | https://www.abc.cl |
| `alkosto_co` | Alkosto | Magento | ✓ | reviews_io_api | https://www.alkosto.com |
| `alkostoplus_bo` | Multicenter+ | Magento | ✗ | aggregate_only | https://alkostoplus.com |
| `alternate_de` | Alternate | Other | ✓ | none | https://www.alternate.de |
| `artefacta_ec` | Artefacta | Magento | ✓ | unknown_blocked | https://www.artefacta.com |
| `carrefour_es` | Carrefour | Other | ✓ | none | https://www.carrefour.es |
| `carsa_pe` | Carsa | VTEX | ✓ | vtex_reviews_graphql | https://www.carsa.pe |
| `cdiscount_fr` | Cdiscount | Other | ✓ | jsonld | https://www.cdiscount.com |
| `comandato_ec` | Comandato | VTEX | ✓ | none | https://www.comandato.com |
| `coppel_mx` | Coppel | Other | ✓ | — | https://www.coppel.com |
| `coral_ec` | Coral | Magento | ✓ | none | https://coralhipermercados.com |
| `costco_ca` | Costco Canada | Other | ✓ | bazaarvoice_bfd | https://www.costco.ca |
| `credivargas_pe` | Credivargas | VTEX | ✓ | vtex_reviews_graphql | https://www.credivargas.pe |
| `cresa_ec` | Cresa EC | VTEX | ✓ | none | https://www.crecos.com |
| `cresa_ec_more` | Cresa More | VTEX | ✗ | vtex_graphql | https://www.crecos.com |
| `cyberport_de` | Cyberport | Other | ✓ | none | https://www.cyberport.de |
| `darty_fr` | Darty | Other | ✓ | none | https://www.darty.com |
| `dismac_bo` | Dismac | Magento | ✗ | mageplaza_ajaxsort_http | https://www.dismac.com.bo |
| `ebay_fr` | eBay France | Other | ✓ | none | https://www.ebay.fr |
| `efe_pe` | — | Other | ✗ | — | https://www.efe.com.pe |
| `elektra_gt` | Elektra | VTEX | ✓ | yotpo | https://www.elektra.com.gt |
| `espana_ec` | — | Other | ✓ | — | https://almacenesespana.ec |
| `estilos_pe` | Estilos | VTEX | ✓ | vtex_reviews_graphql | https://www.estilos.com.pe |
| `evision_pa` | Evision | Other | ✓ | jsonld | https://www.evisionstore.com |
| `exito_co` | Exito | VTEX | ✓ | vtex_reviews_rw | https://www.exito.com |
| `falabella_cl` | Falabella | Other | ✓ | bazaarvoice_bfd | https://www.falabella.com |
| `falabella_co` | — | Other | ✓ | — | https://www.falabella.com.co |
| `ferrisariato_ec` | Ferrisariato | Other | ✓ | none | https://www.ferrisariato.com |
| `fnac_fr` | Fnac | Other | ✓ | none | https://www.fnac.com |
| `hiraoka_pe` | Hiraoka | Magento | ✓ | none | https://hiraoka.com.pe |
| `hisense_ca` | — | Brand | ✓ | — | — |
| `hisense_mx` | — | Brand | ✓ | — | — |
| `hites_cl` | Hites | Other | ✗ | verificado_ai_api | https://www.hites.com |
| `hughes_uk` | Hughes UK | Other | ✓ | feefo | https://www.hughes.co.uk |
| `jaher_ec` | Jaher | Other | ✓ | unknown | https://www.jaher.com.ec |
| `japon_ec` | Japon EC | VTEX | ✓ | none | https://www.almacenesjapon.com |
| `jumbo_co` | Jumbo | VTEX | ✓ | vtex_reviews_graphql | https://www.jumbocolombia.com |
| `lacuracao_pe` | — | Other | ✗ | — | https://www.lacuracao.pe |
| `laganga_ec` | L-Ganga | Other | ✓ | none | https://laganga.com |
| `laganga_ec2` | L-Ganga | Magento | ✓ | none | https://laganga.com |
| `lg_ca` | — | Brand | ✓ | — | — |
| `lg_mx` | — | Brand | ✓ | — | — |
| `lg_us` | LG（美国） | Brand | ✓ | bazaarvoice_bfd | https://www.lg.com |
| `lider_cl` | Lider | Other | ✗ | next_data_inline | https://www.lider.cl |
| `liverpool_mx` | Liverpool | Other | ✓ | — | https://www.liverpool.com.mx |
| `marcimex_ec` | Marcimex | VTEX | ✓ | none | https://www.marcimex.com |
| `markselectrical_uk` | Marks Electrical | Magento | ✓ | feefo_api | https://www.markselectrical.co.uk |
| `max_gt` | Max | Other | ✓ | none | https://www.max.com.gt |
| `mediamarkt_de` | MediaMarkt | Other | ✓ | bazaarvoice_private | https://www.mediamarkt.de |
| `mediamarkt_es` | MediaMarkt | Other | ✓ | bazaarvoice_private | https://www.mediamarkt.es |
| `megamaxi_ec` | — | Other | ✓ | — | https://www.megamaxi.com |
| `mercadolibre_cl` | — | Other | ✓ | — | https://www.mercadolibre.cl |
| `mercadolibre_pe` | Mercado Libre | Other | ✓ | ml_reviews_api | https://www.mercadolibre.com.pe |
| `metro_pe` | Metro | VTEX | ✓ | vtex_reviews_graphql | https://www.metro.pe |
| `multicenter_bo` | Multicenter | VTEX | ✗ | vtex_graphql | https://www.multicenter.com |
| `oechsle_pe` | Oechsle | VTEX | ✓ | bazaarvoice_bfd | https://www.oechsle.pe |
| `olimpica_co` | Olimpica | VTEX | ✓ | none | https://www.olimpica.com |
| `orvehogar_ec` | Orvehogar | VTEX | ✓ | vtex_reviews_graphql | https://www.orvehogar.com |
| `otto_de` | OTTO | Other | ✓ | none | https://www.otto.de |
| `palacio_mx` | Palacio | Other | ✓ | — | https://www.elpalaciodehierro.com |
| `panafoto_pa` | Panafoto | Magento | ✓ | none | https://www.panafoto.com |
| `paris_cl` | Paris | Other | ✓ | jsonld | https://www.paris.cl |
| `pccomponentes_es` | PCComponentes | Other | ✓ | none | https://www.pccomponentes.com |
| `philips_ca` | — | Brand | ✓ | — | — |
| `plazavea_pe` | Plaza Vea | VTEX | ✓ | none | https://www.plazavea.com.pe |
| `raenco_pa` | Raenco | Magento | ✓ | none | https://www.raenco.com |
| `ripley_cl` | Ripley | Other | ✓ | unknown_blocked | https://simple.ripley.cl |
| `sams_mx` | Sam's | Other | ✓ | — | https://www.sams.com.mx |
| `samsung_mx` | — | Brand | ✓ | — | — |
| `samsung_uk` | Samsung UK | Brand | ✓ | bazaarvoice_data | https://www.samsung.com |
| `saturn_de` | Saturn | Other | ✓ | dom | https://www.saturn.de |
| `sharp_jp` | — | Brand | ✓ | — | https://www.sharp.co.jp |
| `sony_uk` | Sony UK | Brand | ✓ | bazaarvoice_bfd | https://www.sony.co.uk |
| `sony_us` | — | Brand | ✓ | — | https://electronics.sony.com |
| `sukasa_ec` | Sukasa | Other | ✓ | none | https://www.sukasa.com |
| `tcl_ca` | — | Brand | ✓ | — | — |
| `tcl_jp` | — | Brand | ✓ | — | https://www.tcl.com |
| `tcl_mx` | — | Brand | ✓ | — | — |
| `tcl_uk` | TCL UK | Brand | ✓ | feefo | https://www.tcl.com |
| `tcl_us` | — | Brand | ✓ | — | https://us.tcl.com |
| `tecnofacil_gt` | Tecnofacil | Other | ✓ | none | https://www.tecnofacil.com.gt |
| `todohogar_ec` | Todohogar | Other | ✓ | none | https://www.todohogar.com |
| `unicomer_gt` | Unicomer | Magento | ✓ | none | https://www.lacuracaonline.com |
| `visions_ca` | — | Brand | ✓ | — | https://www.visions.ca |
| `worten_es` | Worten | Other | ✓ | none | https://www.worten.es |

### L3 强防（27 站）

| code | 名称 | 平台 | 需浏览器 | 评价后端 | base_url |
|---|---|---|:---:|---|---|
| `amazon_ca` | Amazon | Amazon | ✓ | — | https://www.amazon.ca |
| `amazon_de` | Amazon | Amazon | ✓ | — | https://www.amazon.de |
| `amazon_es` | Amazon | Amazon | ✓ | — | https://www.amazon.es |
| `amazon_fr` | Amazon | Amazon | ✓ | — | https://www.amazon.fr |
| `amazon_it` | Amazon | Amazon | ✓ | — | https://www.amazon.it |
| `amazon_mx` | Amazon | Amazon | ✓ | — | https://www.amazon.com.mx |
| `amazon_uk` | Amazon | Amazon | ✓ | — | https://www.amazon.co.uk |
| `amazon_us` | Amazon | Amazon | ✓ | — | https://www.amazon.com |
| `bestbuy_ca` | Best Buy | Other | ✓ | bazaarvoice_bfd | https://www.bestbuy.ca |
| `bestbuy_us` | Best Buy | Other | ✓ | — | https://www.bestbuy.com |
| `canadiantire_ca` | Canadian Tire | Other | ✓ | — | https://www.canadiantire.ca |
| `citilink_ru` | Citilink | Other | ✓ | none | https://www.citilink.ru |
| `costco_us` | Costco | Other | ✓ | bazaarvoice_bfd | https://www.costco.com |
| `eldorado_ru` | Eldorado | Other | ✓ | none | https://www.eldorado.ru |
| `elgiganten_dk` | Elgiganten Denmark | Other | ✓ | none | https://www.elgiganten.dk |
| `expert_de` | Expert DE | Other | ✓ | bazaarvoice_blocked | https://www.expert.de |
| `komplett_no` | Komplett Norway | Other | ✓ | none | https://www.komplett.no |
| `leons_ca` | Leon's（加拿大） | Other | ✓ | lflgroup_api | https://www.leons.ca |
| `proshop_dk` | Proshop Denmark | Other | ✓ | none | https://www.proshop.dk |
| `samsung_ca` | — | Brand | ✓ | — | — |
| `samsung_us` | — | Brand | ✓ | — | https://www.samsung.com |
| `sony_ca` | Sony（加拿大） | Brand | ✓ | bazaarvoice_bfd | https://www.sony.ca |
| `thebrick_ca` | The Brick（加拿大） | Other | ✓ | — | https://www.thebrick.com |
| `walmart_ca` | — | Other | ✓ | — | https://www.walmart.ca |
| `walmart_mx` | Walmart | Other | ✓ | — | https://www.walmart.com.mx |
| `walmart_us` | Walmart | Other | ✓ | — | https://www.walmart.com |
| `yandex_market_ru` | Yandex Market | Other | ✓ | none | https://market.yandex.ru |

---

## 附录：数据来源与口径

- **数据矩阵**：`data/overseas.db` 的 `site` 表（74 站）LEFT JOIN `product`/`price_snapshot`/`review`/`review_summary`，按 `site_id` 聚合计数。DB 的 `site.name` 列存在编码损坏（mojibake），名称以 `schemas/retail_specs/*.retail.json` 的 `name` 字段为准。
- **平台**：无显式 `platform` 字段，按以下优先级推断：Amazon 代码前缀 → Brand 官网前缀（lg_/samsung_/sony_/tcl_/hisense_/panasonic_/sharp_/philips_/regza_/visions_）→ VTEX（`generated_by` 含「VTEX 站/VTEX 14/VTEX(/ektguatemala」 或 `discovery.catalog_api` 存在 或 `reviews._vtex_*` 存在 或 `reviews.source` 以 vtex 开头）→ Magento（`generated_by` 含 Magento）→ Other（Demandware/SFCC、Next.js、PWA/React、Costco/BestBuy/Walmart/eBay/Mercado Libre/kakaku/Yandex 等自研架构，子架构见 Other 表）。
- **评价后端**：取 spec 的 `reviews.source`；共 73 种，常见：`bazaarvoice_bfd`、`vtex_reviews_graphql`、`jsonld`、`feefo`/`feefo_api`、`powerreviews_api`、`reviews_io_api`、`yotpo`、`mageplaza_ajaxsort_http`、`ml_reviews_api`、`dom`、`none`（被封锁/无评价）等。
- **价格提取**：`jsonld`（JSON-LD Product.offers）/ `selectors`（DOM 选择器）/ `catalog_api`（VTEX Catalog API 直采）。
- **住宅IP判定**：spec 的 `_block_note` 含 403/429/503/封锁/住宅 字样，或 `reviews.source=none/unknown_blocked/blocked` 且有 block note。
- **区域**：由 spec 的 `region`（国家代码）映射，NA=us/ca/mx，SA=cl/co/pe/ec/bo/gt/pa/br/ar，EU=uk/de/es/fr/it/dk/no/ru，JP=jp。

---

*本文档为永久性资产清单，硬编码抓取的权威参考。*
