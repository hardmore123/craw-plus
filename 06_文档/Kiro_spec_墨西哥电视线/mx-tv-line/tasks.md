# Implementation Plan

> 执行顺序总原则：先接入区域配置与 SPEC 线并跑通，产出型号全集清单后，再接入零售站做价格+网评同步抓取。强防护站（Amazon/Walmart）最后单独低频验证再开启。
> 固定 Python：`C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\python.exe`（下称 `$py`）。

- [ ] 1. 在集中区域配置中注册墨西哥线
  - 在 `overseas/regions_config.py` 中新增 `_MX = Region(code="mx", name="墨西哥", currency="MXN", locale="es-MX", enabled=False, ...)`，声明 4 品牌、4 个 SPEC 站点、6 个零售站；强防护站（`amazon_mx`/`walmart_mx`）`enabled=False`，其余零售站 `enabled=True`。
  - 把 `_MX` 加入 `REGIONS` 字典（`{"ca": _CA, "mx": _MX}`）。
  - 自测：`region_meta("mx")` 返回 4 品牌 / 4 SPEC 站 / 6 零售站及各自 enabled；`get_region("mx").retail_site_codes()` 只含启用站。
  - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

- [ ] 2. 搭建 4 个 SPEC 站点适配器骨架
  - 新建目录 `overseas/sites/{tcl_mx,samsung_mx,lg_mx,hisense_mx}/`，各含空 `__init__.py` 与 `adapter.py`（继承 `SiteAdapter`，`supports_spec=True`，`country="墨西哥"`，`channel="<品牌> 官网"`，`requires_browser=True`，`protection=L1_MILD`，`suggested_interval=4.0`，`code` 与目录名一致）。
  - 自测：`$py -m overseas.cli sites` 能列出 4 个新站点且加载无报错。
  - _需求: 2.1, 6.1_

- [ ] 3. 实现 hisense_mx SPEC 采集（先做结构最接近日本线的品牌）
  - 实现 `spec_entry_url()`（`https://hisense.com.mx/televisores`）与 `list_series()`；按官网实测选单级或多级（多级则实现 `series_entries()` + `parse_spec_model()` + `model_from_url()`）。
  - 写 `schema.json` 的 `specs` 表解析规则，或在适配器内自定义 `parse_spec`（参考 `spec_parser.parse_hisense_table`）。
  - 设置 `spec_entry_wait` / `spec_page_wait` 等待锚点。
  - 自测：`$py -m overseas.cli probe --site hisense_mx --url <入口页>` 可访问未被拦；`spec-crawl --site hisense_mx --only <一个系列>` 入库 `spec_series`/`spec_row`。
  - _需求: 2.2, 2.3, 2.4, 2.5, 6.2, 6.3_

- [ ] 4. 实现 tcl_mx / lg_mx / samsung_mx SPEC 采集
  - 逐品牌实现入口→系列/型号→规格页解析（多为多级），补 `schema.json` 规格抽取；Samsung/LG 详情页 Especificaciones 块优先用声明式表解析或 JSON-LD。
  - 每品牌确定性缺页（404/空）记 `empty`/`failed` 到 `spec_series_status`，不覆盖既有数据；连续瞬时失败触发熔断（复用 `spec_crawl`）。
  - 自测：每品牌 `spec-crawl --site <brand>_mx --only <一个系列>` 跑通并入库。
  - _需求: 2.2, 2.3, 2.4, 2.5, 2.6_

- [ ] 5. 打通 SPEC 导出与型号全集清单（按 region 读取）
  - 让 `spec-export` 对 4 个 `*_mx` 站点复用 SPEC 宽表模板导出（顶部「上市时间」行，官网无则留空）。
  - 让 `scripts/export_spec_models.py` 支持 `--region mx`，从 `regions_config` 读取墨西哥品牌产出型号全集清单（`SPEC_型号汇总_*.csv/xlsx/json`）。
  - 提供 `scripts/refresh_spec_mx.py`（或 `refresh_spec.py --region mx`）：采集→导出→状态汇总一键跑。
  - 自测：`$py scripts/export_spec_models.py --region mx --format all` 产出非空型号清单。
  - _需求: 2.7, 2.8, 5.1_

- [ ] 6. 西班牙语规格词典占位（不阻塞抓取）
  - 新增 `overseas/dict/spec_es_zh.json`（可最小/为空），接入 SPEC 中文列翻译；缺词照旧进 `spec_untranslated`，不报错。
  - 自测：`spec-export --site hisense_mx` 中文列缺词不报错，未命中项落 `spec_untranslated`。
  - _需求: 2.7, 7.1_

- [ ] 7. 搭建 6 个零售站适配器骨架
  - 新建目录 `overseas/sites/{amazon_mx,liverpool_mx,sams_mx,palacio_mx,walmart_mx,coppel_mx}/`，各含 `__init__.py`、`adapter.py`（`country="Mexico"`，`channel=<零售站名>`，`search_url`/`product_url`/`reviews_url` 骨架，防护等级与建议间隔按设计表）、`schema.json` 骨架（`anchor`/`search`/`product`/`price`/`summary`/`reviews`）。
  - 自测：`$py -m overseas.cli sites` 列出 6 个零售站且加载无报错。
  - _需求: 3.1, 6.1_

- [ ] 8. 实现价格 transform 归一 MXN
  - 在 `extract.py` 的 `currency`/`money` transform 中识别墨西哥比索（`$` + `MXN`/`M.N.` 上下文），`price.currency` 归一为 `MXN`；不影响日本线 JPY / 加拿大 CAD。
  - 自测：对样例价格文本单测/实测确认归一 MXN。
  - _需求: 3.3, 4.1, 4.3_

- [ ] 9. 实现 liverpool_mx 价格+网评同步抓取（首个低防护零售站，打通链路）
  - 补全 `search_url`/`product_url`/`parse_search`（型号匹配）与 `schema.json`（`product`/`price`/`summary`/`reviews`）；评价在商品页则 `reviews_url` 返回空串，随商品页同步抽取；在独立评价页则实现 `reviews_url`。
  - 自测：`probe_selectors` 核对选择器；用 1 个已知型号验证 `collect_detail` 一次同时取到价格与评价。
  - _需求: 3.2, 3.3, 3.4, 6.2, 6.3_

- [ ] 10. 新增零售抓取编排脚本 `scripts/crawl_mx_retail.py`
  - 读取墨西哥型号全集，按「型号 × 启用零售站」循环：`search_url`→`parse_search`→复用 `scenarios._pick_by_model` 定位型号→`collect_detail`（同步取价格+评价）→需要更多评价时复用 `s4` 增量翻页补齐。
  - 记录型号×零售站状态（`ok/no_item/no_match/no_reviews/no_price/blocked/failed`）；支持 `--brand/--site/--year/--models/--limit-models/--save-db`。
  - 未匹配到型号时不记价格/评价（宁缺勿错）；`--save-db` 时复用 `save_payload` 落库并增量去重。
  - 自测：`crawl_mx_retail --site liverpool_mx --models <1型号>` 产出价格与网评记录，状态正确。
  - _需求: 3.2, 3.5, 3.6, 3.7, 3.8, 5.2, 5.3, 5.4_

- [ ] 11. 价格导出适配墨西哥渠道与 MXN（方案 A）
  - 给 `price_export` 导出函数增加可选 `columns`/`region` 入参：日本线不传保持原 8 家日本店铺列；墨西哥线传入 6 个零售站作为渠道列，「所属区域」=墨西哥、「货币」=MXN。
  - 先写 CSV 再写 XLSX，占用时改写时间戳文件。
  - 自测：墨西哥价格导出列为 6 零售站、币种 MXN；日本线导出不变（回归）。
  - _需求: 4.3, 4.4, 4.5, 5.5_

- [ ] 12. 网评导出适配墨西哥（复用 20 列模板，AI 三列空）
  - 用 `review_export.COLUMNS`，`ReviewRecord.country="Mexico"`、`channel=<零售站名>`、`price`=MXN 价；`translation/ai_pros/ai_cons` 由 `NULL_HOOKS` 恒空。
  - 自测：网评汇总表 20 列齐全、AI 三列为空、所属国家=Mexico、渠道正确。
  - _需求: 4.1, 4.2, 7.1, 7.2_

- [ ] 13. 实现其余低防护零售站：sams_mx / palacio_mx / coppel_mx
  - 参考 `liverpool_mx` 逐站补 `schema.json` 与型号匹配；确认价格+评价同步抓取。
  - 同型号多站均命中时各站分别记录（多对多）。
  - 自测：每站 1 个型号小样跑通，导出核对。
  - _需求: 3.1, 3.2, 3.3, 3.5_

- [ ] 14. 实现强防护零售站：amazon_mx / walmart_mx（低频验证后开启）
  - `amazon_mx` 的 `schema.json` 以 `sites/amazon_ca/schema.json` 为蓝本，`base_url` 换 `amazon.com.mx`，价格归一 MXN；`walmart_mx` 按实测补规则。
  - 单页低频 `probe` + 小样验证未被拦截后，将 `regions_config` 中对应 `RetailSite.enabled` 置 `True`。
  - 自测：单型号低频验证同步取到价格与评价，无验证码拦截。
  - _需求: 1.5, 3.1, 3.7, 6.2_

- [ ] 15. 型号×零售站状态落库（复用现有表，不新增专用表）
  - 状态写入复用 `kakaku_task_status` 结构（把零售站 code 纳入状态键/上下文），提供概览与明细查询；`site.country="Mexico"`。
  - 自测：`--save-db` 后能按型号×零售站查到状态计数与明细。
  - _需求: 3.6, 5.3, 5.4, 5.5_

- [ ] 16. 开启墨西哥线并做端到端小样验证
  - 全部 SPEC 站点与已实现零售站验证通过后，将 `Region(mx).enabled=True`（强防护站按其自身 enabled 控制）。
  - 端到端：`refresh_spec_mx` → `export_spec_models --region mx` → `crawl_mx_retail`（选启用站，小样）→ 检查 SPEC/价格/网评三类产物与状态；`/api/regions` 能看到 `mx` 线。
  - 自测：三类产物列正确、币种 MXN、AI 三列空、状态无静默缺口、日本线回归不受影响。
  - _需求: 1.6, 4.1, 4.3, 5.1, 6.4, 7.2, 7.3_
