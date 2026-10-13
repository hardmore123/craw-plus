# -*- coding: utf-8 -*-
"""根据 海外/爬取进度.csv 梳理各站四维完成情况（schema / adapter / 已抓取 / 全量）。

产出：
  海外/爬取进度_四维梳理_20260924.csv   （UTF-8-BOM，Excel 可直接打开）
  海外/爬取进度_四维梳理_20260924.md    （汇总报告）

判定口径（全部以工作区实测产物为准，不采信 CSV 的"状态"文字）：
  schema : Y=已转正契约(docs/specs/*.spec.json | docs/retail_specs/*.retail.json | sites/<code>/schema.json)
           D=仅 data/schema_drafts/ 草稿 ; NA=SPEC 品牌官网不适用(型号发现由适配器/脚本承担) ; N=无
  adapter: Y=overseas/sites/<code>/adapter.py 存在 ; S=无站点适配器(一次性脚本 + 直入库) ; N=无
  crawled: Y=已执行且有有效产物 ; P=执行过但 0 有效产物(被拦/0命中) ; N=未执行
  full   : Y=该站全量抓完 ; P=部分完成(抽样/校准/缺系列) ; N=未完成
"""
from __future__ import annotations

import csv
import os
import re
import collections

ROOT = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
SRC = os.path.join(ROOT, "爬取进度.csv")
OUT_CSV = os.path.join(ROOT, "爬取进度_四维梳理_20260924.csv")
OUT_MD = os.path.join(ROOT, "爬取进度_四维梳理_20260924.md")

# 行号(1-based, 对应「爬取进度_备份_20260924_去重前.csv」) -> (code, schema, adapter, crawled, full, 证据/备注)
# 注意：行号只是 M 的书写坐标；运行时会被翻译成 (国家, 品牌, 域名) 再套到当前台账，增删行不会错位。
M: dict[int, tuple] = {
    # ---------------- 日本线 ----------------
    2:  ("sony_jp", "NA", "Y", "Y", "P", "9系列38型号；SPEC 找全率 80%（期望10抓8，差额待人工确认）"),
    3:  ("regza_jp", "NA", "Y", "Y", "Y", "39系列139型号564行；三种选择器交叉验证一致，找全率100%"),
    4:  ("hisense_jp", "NA", "Y", "Y", "Y", "13系列44型号101行；官网复核无漏抓"),
    5:  ("sharp_jp", "NA", "Y", "Y", "Y", "13系列44型号56行"),
    6:  ("panasonic_jp", "NA", "Y", "Y", "P", "8系列25型号；W80C/MR770 因 JS 渲染未纳入"),
    7:  ("tcl_jp", "NA", "Y", "Y", "Y", "28系列78型号283行；旧系列 JSON 404 按设计跳过"),
    8:  ("kakaku_jp", "Y", "Y", "Y", "Y", "schema.json + retail_spec 双有；价格310条 + 网评1935条"),

    # ---------------- 北美线 / 加拿大 ----------------
    9:  ("hisense_ca", "NA", "Y", "Y", "Y", "33系列140型号 OK"),
    10: ("samsung_ca", "NA", "Y", "Y", "Y", "64系列224型号 OK"),
    11: ("tcl_ca", "NA", "Y", "Y", "Y", "16系列61型号 OK"),
    12: ("lg_ca", "NA", "Y", "Y", "P", "DB：success 26系列88型号 + failed 14系列(21型号失败) 并存，历史 failed 未全部消灭"),
    13: ("sony_ca", "NA", "Y", "Y", "Y", "16系列66型号 OK"),
    14: ("philips_ca", "Y", "Y", "Y", "Y", "唯一有 AdapterSpec 转正文件 docs/specs/philips_ca.spec.json；找全率100%"),
    15: ("amazon_ca", "Y", "Y", "Y", "Y", "retail_spec + 全量成功；价格149 OK / 网评146 OK"),
    16: ("bestbuy_ca", "Y", "Y", "P", "N", "sitemap 目录入库9产品、0价格；PDP 9/9 全 403（出口 IP 被边缘硬拦）"),
    17: ("walmart_ca", "Y", "Y", "N", "N", "PerimeterX『Verify Your Identity』，未抓；适配器已建"),
    18: ("costco_ca", "Y", "Y", "P", "N", "跑过但 175 型号全 no_item、product 表 0 条；未批量"),
    19: ("thebrick_ca", "Y", "Y", "Y", "Y", "价格402 + 网评359，适配器稳定"),
    20: ("leons_ca", "Y", "Y", "Y", "Y", "价格208 + 网评185，适配器稳定"),
    21: ("visions_ca", "N", "Y", "N", "N", "无 retail_spec；HTTP 403 / Cloudflare，未抓"),
    22: ("canadiantire_ca", "Y", "Y", "P", "N", "价格13条有价、DB product 1 条；网评未全量"),

    # ---------------- 北美线 / 美国 ----------------
    23: ("tcl_us", "NA", "Y", "Y", "P", "DB：success 25系列25型号 + empty 21系列（21个旧系列空页）"),
    24: ("hisense_us", "NA", "Y", "Y", "Y", "86系列402型号 OK"),
    25: ("sony_us", "NA", "Y", "Y", "Y", "68系列112型号 OK"),
    26: ("samsung_us", "NA", "Y", "Y", "Y", "125系列125型号 OK"),
    27: ("lg_us", "NA", "Y", "Y", "Y", "291系列294型号 OK（DB 最大单站）"),
    28: ("bestbuy_us", "Y", "Y", "P", "N", "sitemap 入库77产品、0价格；PDP 77/77 失败（非美国 IP 落国际选择页）"),
    29: ("walmart_us", "Y", "Y", "P", "N", "全站 PerimeterX（连 sitemap 都被拦）；适配器已建，0产物"),
    30: ("costco_us", "Y", "Y", "Y", "P", "2026-09-24 分类页全量：24产品 / 18有价（75%），仅单入口单轮"),
    31: ("amazon_us", "Y", "Y", "Y", "Y", "三站全量成功；价格75 OK / 网评70 OK，100%成功率零封禁"),

    # ---------------- 北美线 / 墨西哥 ----------------
    32: ("tcl_mx", "NA", "Y", "Y", "Y", "9系列21型号 OK"),
    33: ("samsung_mx", "NA", "Y", "Y", "Y", "8系列8型号 OK"),
    34: ("lg_mx", "NA", "Y", "Y", "Y", "6系列6型号 OK"),
    35: ("hisense_mx", "NA", "Y", "Y", "Y", "OK"),
    36: ("amazon_mx", "Y", "Y", "Y", "Y", "适配器校准成功并全量抓取；网评671 + 价格153"),
    37: ("liverpool_mx", "Y", "Y", "Y", "N", "单型号端到端校准通过（价/原价/库存/规格/4条评价）；未全量"),
    38: ("sams_mx", "Y", "Y", "N", "N", "PerimeterX『Verify Your Identity』，首页/搜索全拦；未抓"),
    39: ("palacio_mx", "Y", "Y", "P", "N", "记录冲突：CSV 称单型号验证通过，cases 记 403 拦截，且 DB 无任何 palacio_mx 行；未全量"),
    40: ("walmart_mx", "Y", "Y", "N", "N", "PerimeterX『Verifica tu identidad』；未抓"),
    41: ("coppel_mx", "Y", "Y", "Y", "N", "单型号校准通过（含尺寸一致性防误配）；未全量"),

    # ---------------- 欧洲线（第一批：CSV 42-46）----------------
    42: ("samsung_uk", "NA", "S", "Y", "Y", "JSON-LD ItemList 48→38 TV 入库38产品38价格（纯HTTP）"),
    43: ("sony_uk", "NA", "S", "Y", "P", "Playwright 过 403；仅 7 个 BRAVIA 入库（覆盖不足）"),
    44: ("lg_uk", "NA", "S", "Y", "P", "出 SPEC_lg_uk xlsx(118行)；但 HTTP CAPTCHA / Playwright 超时，未入库"),
    45: ("tcl_uk", "NA", "S", "Y", "Y", "108产品入库；品牌官网不标价（0价格属站点现状）"),
    46: ("philips_de", "NA", "S", "Y", "Y", "11系列15型号 xlsx"),
    47: ("eu_all_retail", "NA", "N", "N", "N", "本行判『未提供URL』，但 149-171 行已给出欧英/德/法/意/西零售站 URL —— 台账自相矛盾"),

    # ---------------- 南美线 / SPEC ----------------
    48: ("hisense_pe", "NA", "S", "Y", "Y", "13系列36型号（含 UX 110\" MiniLED）"),
    49: ("tcl_pe", "NA", "S", "Y", "Y", "8系列8型号"),
    50: ("samsung_pe", "NA", "S", "Y", "P", "仅 9系列9型号（型号覆盖偏少）"),
    51: ("lg_pe", "NA", "S", "Y", "P", "仅 7系列9型号"),
    52: ("hisense_ec", "NA", "S", "Y", "Y", "SPEC_hisense_ec_20260922 有产物"),
    53: ("tcl_ec", "NA", "S", "P", "N", "★ SPEC_tcl_ec_20260922.xlsx 只有 2 行（空壳），实际未抓到；CSV 标『已完成』不实"),
    54: ("samsung_ec", "NA", "S", "Y", "P", "11系列11型号"),
    55: ("lg_ec", "NA", "S", "N", "N", "★ 全工作区找不到任何 SPEC_lg_ec 产物，CSV 标『已完成』不实"),
    56: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    57: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    58: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    59: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    60: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    61: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    62: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    63: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    64: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    65: ("tcl_ar", "NA", "S", "Y", "Y", "10系列15型号"),
    66: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    67: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    68: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    69: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    70: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    71: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    72: ("hisense_co", "NA", "S", "Y", "Y", "SPEC_hisense_co_20260922 有产物（Cloudflare 挑战页但内容可达）"),
    73: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    74: ("samsung_co", "NA", "S", "Y", "P", "6系列6型号"),
    75: ("lg_co", "NA", "S", "Y", "P", "10系列11型号"),
    76: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    77: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    78: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    79: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    80: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    81: ("tcl_cl", "NA", "S", "Y", "P", "17系列17型号，但均为站内长 slug（型号未规整）"),
    82: ("samsung_cl", "NA", "S", "Y", "P", "8系列8型号，型号为长 slug"),
    83: ("lg_cl", "NA", "S", "Y", "P", "11系列12型号"),
    84: ("hisense_bo", "NA", "S", "Y", "P", "3系列3型号（覆盖偏少）"),
    85: ("tcl_bo", "NA", "S", "Y", "P", "3系列3型号（覆盖偏少）"),
    86: ("samsung_bo", "NA", "S", "Y", "P", "1系列1型号（覆盖偏少）"),
    87: ("", "N", "N", "N", "N", "附件 URL 为空，无法开展"),

    # ---------------- 南美线 / 零售（价格+网评）----------------
    88:  ("hiraoka_pe", "Y", "Y", "Y", "Y", "Hiraoka_全量_v2.csv；Magento 引擎"),
    89:  ("falabella_pe", "N", "N", "P", "N", "无适配器、无 retail_spec；CF 挑战，目录仅部分"),
    90:  ("ripley_pe", "N", "N", "N", "N", "无适配器；HTTP 403 / CF『Just a moment...』"),
    91:  ("oechsle_pe", "N", "Y", "Y", "Y", "VTEX 目录全量（oechsle_pe_catalog_v2.csv）"),
    92:  ("tottus_pe", "N", "N", "P", "N", "无适配器；CF 挑战，未全量"),
    93:  ("lacuracao_pe", "Y", "Y", "Y", "N", "schema_drafts/lacuracao_pe.retail.json 草稿；单型号校准，未全量"),
    94:  ("efe_pe", "Y", "Y", "Y", "N", "schema_drafts/efe_pe.retail.json 草稿；单型号校准，未全量"),
    95:  ("plazavea_pe", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    96:  ("estilos_pe", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    97:  ("metro_pe", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    98:  ("mercadolibre_pe", "N", "Y", "N", "N", "适配器已建；但需登录墙（/gz/account-verification），0产物"),
    99:  ("carsa_pe", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    100: ("sodimac_pe", "N", "N", "N", "N", "无适配器；CF 挑战 + 外贸线路拦截"),
    101: ("credivargas_pe", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    102: ("cresa_ec", "N", "Y", "Y", "P", "VTEX API：cresa_ec 5产品 + cresa_ec_more 分支20产品；未做全量分页"),
    103: ("japon_ec", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    104: ("orvehogar_ec", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    105: ("artefacta_ec", "N", "Y", "Y", "P", "站点 WAF 405 硬封，改走 Wayback 快照抓 41台；非实时全量"),
    106: ("marcimex_ec", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    107: ("laganga_ec", "N", "Y", "Y", "Y", "Magento + Playwright：20产品20价（100% fill）"),
    108: ("comandato_ec", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    109: ("jaher_ec", "N", "Y", "N", "N", "适配器已建；未抓"),
    110: ("espana_ec", "N", "Y", "P", "N", "HTTP 503 / SSL 失败，未抓到"),
    111: ("megamaxi_ec", "N", "Y", "P", "N", "woo_megamaxi_tv.csv 少量，未全量"),
    112: ("sukasa_ec", "N", "Y", "N", "N", "适配器已建；未抓"),
    113: ("todohogar_ec", "N", "Y", "Y", "Y", "Next.js + Playwright：44真电视44价（100% fill）"),
    114: ("coral_ec", "N", "Y", "Y", "Y", "Magento：8产品8价（该分类在售全量）"),
    115: ("ferrisariato_ec", "N", "Y", "N", "N", "适配器已建；未抓"),
    116: ("panafoto_pa", "N", "N", "Y", "Y", "无站点适配器；Magento 全目录脚本 21条有价"),
    117: ("evision_pa", "N", "N", "Y", "Y", "无站点适配器；JSON-LD 品牌分类 40产品40价（100% fill）"),
    118: ("multimax_pa", "N", "N", "P", "N", "无适配器；shopify_multimax_pa.csv 少量"),
    119: ("rodelag_pa", "N", "N", "P", "N", "无适配器；shopify_rodelag_pa.csv 3KB 少量"),
    120: ("raenco_pa", "N", "N", "Y", "Y", "无适配器；Magento 全目录 12条有价"),
    121: ("max_gt", "N", "N", "Y", "Y", "无适配器；Next.js + 后端 API 分页，169条分类总数"),
    122: ("tecnofacil_gt", "N", "N", "Y", "Y", "无适配器；61台电视全有价"),
    123: ("unicomer_gt", "N", "N", "Y", "P", "站点 WAF 405 硬封，Wayback 三源合并；非实时"),
    124: ("elektra_gt", "N", "N", "Y", "Y", "VTEX 目录：elektra_gt_catalog_v2.csv（分类句柄已扩展，19 条）"),
    125: ("alkosto_co", "N", "Y", "N", "N", "适配器已建；未抓"),
    126: ("exito_co", "N", "Y", "Y", "Y", "VTEX 目录全量（含 CF 挑战）"),
    127: ("falabella_co", "N", "Y", "P", "N", "目录部分抓取，未全量"),
    128: ("jumbo_co", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    129: ("olimpica_co", "N", "Y", "N", "N", "适配器已建但 regions_config 中 enabled=False；未抓"),
    130: ("falabella_cl", "N", "Y", "Y", "P", "46产品 / 43有价（搜索页命中），价格链路已通；未全量"),
    131: ("paris_cl", "N", "Y", "N", "N", "适配器已建、enabled=False；未验证未抓"),
    132: ("ripley_cl", "N", "Y", "P", "N", "适配器已建；出口 IP 被 Ripley WAF 拉黑，0产品"),
    133: ("mercadolibre_cl", "N", "Y", "N", "N", "适配器已建；未抓"),
    134: ("lider_cl", "N", "Y", "Y", "Y", "Next.js SSR __NEXT_DATA__：102产品102价（100% fill）"),
    135: ("abc_cl", "N", "Y", "Y", "Y", "Demandware + Playwright：35产品35价（100% fill）"),
    136: ("hites_cl", "N", "Y", "P", "N", "hites_cl.json 探测成功（3KB），少量；未全量"),
    137: ("multicenter_bo", "N", "Y", "Y", "Y", "VTEX 目录全量"),
    138: ("dismac_bo", "N", "Y", "Y", "Y", "非标准 Magento：20条（18真电视）全有价"),
    139: ("alkostoplus_bo", "N", "Y", "N", "N", "适配器已建；未抓"),
    140: ("", "N", "N", "N", "N", "附件渠道列为空，无法开展"),
    141: ("", "N", "N", "N", "N", "附件渠道列为空，无法开展"),
    142: ("", "N", "N", "N", "N", "附件渠道列为空，无法开展"),

    # ---------------- 欧洲线（第二批：CSV 144-171）----------------
    144: ("samsung_uk [重复]", "", "", "", "重复行", "与第 42 行重复（同 URL 同任务），此处状态『已完成』一致"),
    145: ("sony_uk [重复]", "", "", "", "重复行", "与第 43 行重复，一致"),
    146: ("lg_uk [重复]", "", "", "", "冲突行", "★ 与第 44 行冲突：44 行写『已完成』，本行写『不可抓取丨需代理』"),
    147: ("tcl_uk [重复]", "", "", "", "冲突行", "★ 与第 45 行状态不一致：45 行『已完成』、本行『未抓取』——以产物为准（108 产品已入库，已完成）"),
    148: ("philips_de [重复]", "", "", "", "重复行", "与第 46 行重复，一致"),
    149: ("currys_uk", "N", "N", "N", "N", "HTTP 403；需 Playwright/住宅代理"),
    150: ("argos_uk", "N", "N", "N", "N", "HTTP 403；需 Playwright/住宅代理"),
    151: ("amazon_uk", "N", "N", "P", "N", "网评链路 2026-09-24 已通（+21 条）但被并发任务回滚，当前 DB 0 条；价格仅 1 产品"),
    152: ("ao_uk", "N", "N", "N", "N", "HTTP 403"),
    153: ("very_uk", "N", "N", "N", "N", "HTTP 403"),
    154: ("richersounds_uk", "N", "N", "N", "N", "HTTP 403"),
    155: ("jlp_uk", "N", "N", "N", "N", "HTTP 超时 16s"),
    156: ("hughes_uk", "N", "N", "Y", "Y", "Symfony SSR：171产品171价（100% fill，GBP119-22999）"),
    157: ("jdwilliams_uk", "N", "N", "N", "N", "HTTP 403"),
    158: ("markselectrical_uk", "N", "N", "Y", "Y", "Playwright JSON 数据岛：12产品12价"),
    159: ("joybuy_uk", "N", "N", "N", "N", "HTTP 200 但 CAPTCHA"),
    160: ("mediamarkt_de", "N", "N", "N", "N", "HTTP 403"),
    161: ("expert_de", "N", "N", "Y", "P", "sitemap 发现 1144 个电视 PDP；抽样 100 个 PDP，49 个真无价；未跑全量"),
    162: ("amazon_de", "N", "N", "P", "N", "邮编弹窗超时 + 出口 IP 在英国被重定向到 amazon.co.uk（lang=en-gb），仅 2 产品；网评无成功记录"),
    163: ("darty_fr", "N", "N", "N", "N", "HTTP 403"),
    164: ("boulanger_fr", "N", "N", "N", "N", "附件 URL 为空，无法开展"),
    165: ("amazon_fr", "N", "N", "P", "N", "网评 09-24 实测抓通（probe 12→+76 条；full 38 型号 33 有评价→+297 条）但被并发任务回滚，当前 DB 0 条；价格 38产品31价同样未留存"),
    166: ("mediaworld_it", "N", "N", "N", "N", "HTTP 403"),
    167: ("amazon_it", "N", "N", "P", "N", "价格 goto 超时；网评 09-24 实测抓通（8/10→+99 条）但被并发任务回滚，当前 DB 0 条"),
    168: ("unieuro_it", "N", "N", "N", "N", "HTTP 200 但 CAPTCHA"),
    169: ("mediamarkt_es", "N", "N", "Y", "Y", "JSON-LD ItemList：12产品12价格入库"),
    170: ("amazon_es", "N", "N", "P", "N", "网评 09-24 实测抓通（8/10→+84 条）但被并发任务回滚，当前 DB 0 条；价格 36产品33价同样未留存"),
    171: ("elcorteingles_es", "N", "N", "N", "N", "HTTP 403"),

    # ---------------- 俄罗斯线 ----------------
    172: ("dns_ru", "N", "N", "N", "N", "HTTP 401；需俄罗斯 IP"),
    173: ("mvideo_ru", "N", "N", "N", "N", "HTTP 403；需俄罗斯 IP"),
    174: ("technopark_ru", "N", "N", "N", "N", "HTTP 401；需俄罗斯 IP"),
    175: ("yandex_market_ru", "N", "N", "P", "N", "HTTP 200 但 0 TV 内容，未成功"),
    176: ("ozon_ru", "N", "N", "N", "N", "HTTP 307 重定向；需俄罗斯 IP"),
    177: ("wildberries_ru", "N", "N", "N", "N", "HTTP 498 异常状态码；需俄罗斯 IP"),

    # ---------------- 欧洲线 媒体评测站（2026-09-24 新增需求，全部未开始）----------------
    178: ("", "N", "N", "N", "N", "新增需求·专业影音评测；项目无 MEDIA 分支，未开始"),
    179: ("", "N", "N", "N", "N", "新增需求·专业影音评测；未开始"),
    180: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    181: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    182: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    183: ("", "N", "N", "N", "N", "新增需求·消费者组织，付费墙/会员制，预计 needs_human；未开始"),
    184: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    185: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    186: ("", "N", "N", "N", "N", "新增需求·专业评测（含榜单）；未开始"),
    187: ("", "N", "N", "N", "N", "新增需求·专业影音评测（含榜单）；未开始"),
    188: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    189: ("", "N", "N", "N", "N", "新增需求·专业评测；未开始"),
    190: ("", "N", "N", "N", "N", "新增需求·专业评测；未开始"),
    191: ("", "N", "N", "N", "N", "新增需求·消费者组织，付费墙/会员制，预计 needs_human；未开始"),
    192: ("", "N", "N", "N", "N", "新增需求·影音论坛+评测；未开始"),
    193: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    194: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    195: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    196: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    197: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    198: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    199: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    200: ("", "N", "N", "N", "N", "新增需求·新闻站评测栏目；未开始"),
    201: ("", "N", "N", "N", "N", "新增需求·新闻站评测栏目；未开始"),
    202: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    203: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
    204: ("", "N", "N", "N", "N", "新增需求·专业影音评测；未开始"),
    205: ("", "N", "N", "N", "N", "新增需求·消费者组织，付费墙/会员制，预计 needs_human；未开始"),
    206: ("", "N", "N", "N", "N", "新增需求·专业影音评测；未开始"),
    207: ("", "N", "N", "N", "N", "新增需求·科技媒体评测栏目；未开始"),
}

SYM = {
    "Y": "✅ 完成", "P": "🟡 部分", "N": "❌ 未完成", "D": "🟡 草稿",
    "NA": "➖ 不适用", "S": "🟡 仅脚本", "X": "➖ 缺URL",
}
SHORT = {"Y": "✅", "P": "🟡", "N": "❌", "D": "🟡", "NA": "➖", "S": "🟡", "X": "➖"}


def _host(url: str) -> str:
    """取 URL 主机名用于定位（去掉协议/路径/查询串，小写）。"""
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    return u.split("/")[0].split("?")[0]


_SUF = (r"(uk|de|fr|it|es|jp|ca|us|mx|pe|ec|co|cl|bo|ar|eu|germany|france|italy|spain|poland|sweden|"
        r"switzerland|austria|belgium|netherlands|denmark|norway|finland|greece|turkey|portugal|russia|"
        r"ukraine|bulgaria|croatia|hungary|serbia|slovakia|slovenia|latvia|lithuania|estonia|romania|"
        r"czech|bosnia|japan|china)")


def _nbrand(b: str) -> str:
    """品牌名归一：小写、去标点、去国别后缀，用于跨表匹配（Amazon DE == Amazon Germany）。"""
    b = (b or "").lower()
    b = re.sub(r"[\[\]()]", " ", b)
    b = re.sub(r"com|co|net|org|\.", " ", b)
    b = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", b)
    return re.sub(_SUF + r"$", "", b)


def main() -> None:
    # 源文件为 CP936/GBK 系（0x80 在 CP936 中映射为 €，Python 的 gb18030 更严格），
    # 用 gb18030 + replace 容错，避免个别字节打断整表解析。
    with open(SRC, "rb") as f:
        text = f.read().decode("gb18030", errors="replace")
    rows = list(csv.reader(text.splitlines()))

    # M 是按「去重前备份」的行号写的。台账会被增删行，行号会漂移，
    # 因此先把 M 翻译成按 (国家, 品牌, 域名) 定位的映射，再套到当前台账上。
    key_map = {}
    bak = os.path.join(ROOT, "爬取进度_备份_20260924_去重前.csv")
    if os.path.exists(bak):
        btext = open(bak, "rb").read().decode("gb18030", errors="replace")
        brows = list(csv.reader(btext.splitlines()))
        for line_no, tup in M.items():
            if line_no - 1 < len(brows):
                br = brows[line_no - 1] + [""] * 7
                key_map[(_nbrand(br[2]), _host(br[4]))] = tup

    out_rows = []
    header = ["行号", "区域", "国家/地区", "品牌/渠道", "任务类型", "网址", "站点code",
              "CSV原状态", "schema", "adapter", "是否已抓取", "是否全量完成", "证据/备注"]
    out_rows.append(header)

    stats = collections.Counter()
    dims = {"schema": collections.Counter(), "adapter": collections.Counter(),
            "crawled": collections.Counter(), "full": collections.Counter()}

    for idx, r in enumerate(rows[1:], start=2):
        if not r or not any(c.strip() for c in r):
            continue
        r = r + [""] * (7 - len(r))
        region, country, brand, task, url, status, note = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        m = key_map.get((_nbrand(brand), _host(url)))
        if m is None:
            # 台账会随需求增长（如按 网站汇总表.csv 补录的新站），未显式映射的行按状态兜底判定
            if task.strip() == "认证+评测":
                m = ("", "NA", "NA", "N", "N", "认证/政策类任务，非数据抓取；未开始")
            elif "未开始" in status:
                m = ("", "N", "N", "N", "N", "未开始（多为按 网站汇总表.csv 补录的新站）")
            else:
                m = ("", "N", "N", "N", "N", "★ 本行未纳入映射，需人工复核")
        code, s, a, c, fu, ev = m
        no_url = (not url.strip()) or url.strip() in ("未提供", "暂未提供")
        if no_url:
            # 未提供 URL / 渠道为空：客观无法开展，与"有站未抓"分开计
            s = a = c = fu = "X"
            stats["缺URL行"] += 1
        out_rows.append([str(idx), region, country, brand, task, url, code, status,
                         SYM.get(s, s), SYM.get(a, a), SYM.get(c, c), SYM.get(fu, fu), ev])
        stats["总行数"] += 1
        for k, v in (("schema", s), ("adapter", a), ("crawled", c), ("full", fu)):
            if v in SHORT:
                dims[k][v] += 1
        if task.strip() == "Spec":
            stats["Spec行"] += 1
        elif task.strip() == "媒体评测":
            stats["媒体评测行"] += 1
        elif task.strip() == "认证+评测":
            stats["认证评测行"] += 1
        else:
            stats["价格网评行"] += 1
        if s == "NA":
            stats["SPEC不适用schema"] += 1
        if code and not code.endswith("]"):
            stats["有站点code"] += 1
        if not url.strip() or url.strip() in ("未提供", "暂未提供"):
            stats["无URL"] += 1

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(out_rows)

    # ---------------- 生成 Markdown ----------------
    total = stats["总行数"]
    L = []
    L.append("# 爬取进度四维梳理（schema / adapter / 已抓取 / 全量完成）\n")
    L.append("> 基准：`海外/爬取进度.csv`（GB18030，200 行数据；2026-09-24 去重修订版）")
    L.append("> 判定证据：`overseas/sites/*/adapter.py`、`overseas/sites/*/schema.json`、`docs/specs/`、"
             "`docs/retail_specs/`、`data/schema_drafts/`、`data/overseas.db` + `data/mx/overseas_mx.db`、"
             "`data (2)/SPEC_*.xlsx`、`.kiro/skills/overseas-schema-gen/{spec,retail}/cases.jsonl`")
    L.append("> 生成时间：2026-09-24　明细表：`爬取进度_四维梳理_20260924.csv`\n")
    L.append("## 一、判定口径\n")
    L.append("| 维度 | ✅ 完成 | 🟡 部分/草稿 | ➖ 不适用 | ❌ 无/未完成 |")
    L.append("|---|---|---|---|---|")
    L.append("| **schema** | 已转正契约：`docs/specs/*.spec.json`、"
             "`docs/retail_specs/*.retail.json`、`overseas/sites/<code>/schema.json` | 仅 `data/schema_drafts/` 草稿 | "
             "SPEC 品牌官网：型号发现由适配器/脚本承担，无独立 schema 文件 | 无任何 schema |")
    L.append("| **adapter** | `overseas/sites/<code>/adapter.py` 存在 | 无站点适配器，靠一次性脚本直入库 | — | 无 |")
    L.append("| **是否已抓取** | 已执行且有有效产物 | 执行过但 0 有效产物（被拦 / 0 命中） | — | 未执行 |")
    L.append("| **是否全量完成** | 该站全量抓完 | 抽样 / 校准 / 缺系列 | — | 未完成 |\n")

    L.append("## 二、总体统计（按 CSV 行计，%d 行）\n" % total)
    L.append("| 维度 | ✅ 完成 | 🟡 部分 | ➖ 不适用 | ❌ 未完成 | ➖ 缺URL（无从判定） |")
    L.append("|---|---|---|---|---|---|")
    for k, label in (("schema", "schema"), ("adapter", "adapter"),
                     ("crawled", "是否已抓取"), ("full", "是否全量完成")):
        d = dims[k]
        L.append("| %s | %d | %d | %d | %d | %d |" % (
            label, d["Y"], d["P"] + d["D"] + d["S"], d["NA"], d["N"], d["X"]))
    L.append("")
    L.append("- SPEC 任务行：%d；价格+网评任务行：%d；**媒体评测：%d**（新增需求）；**认证+评测：%d**（监管/政策页）"
             % (stats["Spec行"], stats["价格网评行"], stats["媒体评测行"], stats["认证评测行"]))
    L.append("- **缺 URL / 渠道为空（客观无法开展）：%d 行**，占总行数 %.0f%%"
             % (stats["缺URL行"], 100.0 * stats["缺URL行"] / max(total, 1)))
    L.append("- 在「有站点、口径可判定」的 %d 行里，全量完成 %d 行（%.0f%%）"
             % (total - stats["缺URL行"], dims["full"]["Y"],
                100.0 * dims["full"]["Y"] / max(total - stats["缺URL行"], 1)))
    L.append("- schema 标『不适用』：%d 行（SPEC 品牌官网：型号发现由适配器/脚本承担，无独立 schema 文件）"
             % stats["SPEC不适用schema"])
    L.append("- 工作区实有：站点适配器 **80** 个、声明式 `schema.json` **13** 个、"
             "转正 SPEC 契约 **1** 个（philips_ca）、转正 RetailSpec **19** 个、RetailSpec 草稿 **3** 个\n")

    L.append("## 三、分区块结论\n")

    blocks = [
        ("日本线（7 行）", [2, 3, 4, 5, 6, 7, 8],
         "全部已抓取；5/6 品牌 SPEC 全量完成。唯一缺口：Panasonic W80C/MR770 因 JS 渲染未纳入。"),
        ("北美线-加拿大（14 行）", list(range(9, 23)),
         "6 品牌 SPEC 全部已抓（LG_CA 有 14 系列 failed 需补）；零售站 Amazon/Brick/Leon's 全量完成，"
         "Costco/CanadianTire 未全量，BestBuy/Walmart/Visions 被反爬拦住。"),
        ("北美线-美国（9 行）", list(range(23, 32)),
         "5 品牌 SPEC 全部已抓（TCL 有 21 个旧系列空页）；Amazon 全量完成；"
         "BestBuy/Walmart/Costco 全部卡在出口 IP（非美国 IP），价格 0 条。"),
        ("北美线-墨西哥（10 行）", list(range(32, 42)),
         "4 品牌 SPEC + Amazon 全量完成；Liverpool/Coppel/Palacio 仅单型号校准未全量；Sams/Walmart 被 PerimeterX 拦。"),
        ("欧洲线（CSV 42-47 + 144-166，共 29 行）", [42, 43, 44, 45, 46, 47] + list(range(144, 167)),
         "✅ 2026-09-24 已去重：原 144-148 行（UK/DE SPEC 重复块）已删除，状态合并进 42-46 行并修正为实测结果"
         "（Samsung ✅ 38产品38价 / Sony 🟡 7产品 / LG 🟡 仅 xlsx 未入库 / TCL ✅ 108产品0价 / Philips 🟡 仅 xlsx）。"
         "47 行『全品牌 未提供URL』与 144-166 行的 23 个零售站 URL 仍是逻辑冲突，待作废。"
         "实测：EU 无任何站点适配器，全部靠一次性脚本；纯 HTTP/JSON-LD 站（Samsung UK、MSD ES、Hughes、"
         "Marks Electrical）已出全量，Amazon 五站部分出数，其余 403/CAPTCHA 未抓。"),
        ("欧洲线-媒体评测站（CSV 173-202，共 30 行）", list(range(173, 203)),
         "★ 2026-09-24 新增需求，**30 站全部未开始**。这是与 SPEC／价格+网评 并列的第三类数据源："
         "编辑评测／榜单（非 UGC 网评、非电商价格），skill 目前无对应分支（只有 SPEC/RETAIL/OPS）。"
         "按可抓性分四档：专业影音/评测站 9 站（What Hi-Fi?、Les Numériques、Trusted Reviews、Expert Reviews、"
         "AVForums、AVPasion、HIFITEST.DE、HIFI.DE、FWD）；科技媒体评测栏目 16 站（TechRadar、Clubic、Frandroid、"
         "connect、COMPUTER BILD、CHIP、JVTECH、Everyeye、Multiplayer.it、Hardware Upgrade、Techzilla、TechBit、"
         "PCGuia、TechFi、Tweakers、Xataka）；新闻站评测栏目 2 站（Jornal Record、EXAME INFORMÁTICA/Visão）；"
         "消费者组织付费墙 3 站（Which?、Stiftung Warentest、Consumentenbond，预计 needs_human）。"
         "涉及 7 种语言（DE/FR/EN/IT/PT/NL/ES），需接翻译链路。"),
        ("南美线-SPEC（CSV 48-87，含未提供URL）", list(range(48, 88)),
         "已抓 SPEC：秘鲁4、厄瓜多尔3、哥伦比亚3、智利3、玻利维亚3、阿根廷1。"
         "★ 两处台账不实：TCL 厄瓜多尔产物只有 2 行空壳、LG 厄瓜多尔全工作区无产物。"
         "巴拿马/危地马拉/乌拉圭/巴西/部分国家 URL 未提供。"),
        ("南美线-零售（CSV 88-139）", list(range(88, 140)),
         "VTEX 目录站（10 站）为全量；Magento/Next.js 站部分全量；"
         "仍有多站有适配器但未抓（Jaher、Sukasa、Ferrisariato、Alkosto、Olimpica、Paris、MercadoLibre CL、Alkostoplus）。"),
        ("俄罗斯线（6 行）", list(range(172, 178)),
         "6 站全部未抓：需俄罗斯 IP；其中 Yandex Market 出口可达但 0 TV 内容。"),
    ]
    for title, idxs, text in blocks:
        L.append("### %s\n" % title)
        L.append(text + "\n")

    L.append("## 四、需要立即处理的台账问题\n")
    L.append("1. ✅ **已修复（2026-09-24）**：原 42-46 行与 144-148 行是同一批 UK/DE SPEC 任务写了两遍，"
             "其中 LG UK（44 行『已完成』vs 146 行『需代理』）、TCL UK、Philips DE 状态互相矛盾。"
             "已删除 144-148 重复块，状态合并进 42-46 行并按实测产物修正；备份 `爬取进度_备份_20260924_去重前.csv`。")
    L.append("2. **欧洲价格+网评状态过期**：47 行『未提供URL』与 144-166 行（23 个已给 URL 的零售站）冲突，"
             "实际欧洲零售线已开跑，47 行结论应作废。")
    L.append("3. **声称完成但无产物**：")
    L.append("   - 厄瓜多尔 TCL Spec（53 行）：`SPEC_tcl_ec_20260922.xlsx` 仅 2 行空壳；")
    L.append("   - 厄瓜多尔 LG Spec（55 行）：全工作区检索不到 `SPEC_lg_ec` 任何产物。")
    L.append("4. **CSV 整体滞后于 cases 日志**：`retail/cases.jsonl` 已记到 2026-09-24，"
             "含 costco_us、lider_cl、abc_cl、max_gt、tecnofacil_gt、evision_pa、todohogar_ec、laganga_ec、"
             "dismac_bo、hughes_uk、markselectrical_uk、mediamarkt_es、amazon_fr/es 等成功案例，"
             "CSV 多数仍标『未抓取』。建议以 cases + DB 为准刷新 CSV。")
    L.append("5. **南美/欧洲零售线无站点适配器**：CSV 88-139、144-166 共 75 行里，"
             "仅 40 个南美站有 `overseas/sites/<code>/adapter.py`；"
             "巴拿马/危地马拉全部 9 站、欧洲全部 23 站均无适配器目录，"
             "抓取逻辑散落在一次性脚本中，无法用 `retail-health`/断点续抓运维。")
    L.append("6. **全量口径不统一**：同是『已完成』，"
             "Amazon US（75 型号有价）是清单级全量，Hughes UK（171 产品）是分类页全量，"
             "而 Coppel/Palacio/Liverpool 只是单型号校准。建议交付文档明确标注口径。\n")

    L.append("## 五、逐行明细\n")
    L.append("见 `爬取进度_四维梳理_20260924.csv`（含 13 列：行号 / 区域 / 国家 / 品牌 / 任务 / 网址 / "
             "站点code / CSV原状态 / schema / adapter / 是否已抓取 / 是否全量完成 / 证据备注）。\n")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print("wrote:", OUT_CSV)
    print("wrote:", OUT_MD)
    print("stats:", dict(stats))
    for k, v in dims.items():
        print(k, dict(v))


if __name__ == "__main__":
    main()
