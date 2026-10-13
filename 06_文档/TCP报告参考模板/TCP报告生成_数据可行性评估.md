# TCP 分析报告生成 — 数据可行性评估

> 评估目标：现有爬取数据（SPEC / 价格 / 网评 / 评测网站）+ 现有报告生成模型，能否支撑生成"美国市场竞品 TCP 分析报告"（对标模板见 `参考信息模板/`）。
> 评估时间：2026-10
> 主数据库：`海外/overseas_v4_20260929.db`（116 MB）

---

## 一、现有数据资产盘点

### 1.1 主数据库（overseas_v4_20260929.db，23 表）
| 表 | 行数 | 说明 |
|----|------|------|
| product | 14,822 | 产品（按 site+sku 唯一） |
| product_spec | 136,496 | 产品级规格（key-value） |
| spec_series | 915 | 品牌官网系列（brand+series） |
| spec_row | 158,386 | 系列级规格行（item_ja/item_zh + values_json{型号:值}） |
| price_snapshot | 13,479 | 价格快照（含 currency/in_stock） |
| price_shop_snapshot | 1,441 | 店铺维度价格（kakaku 多店铺） |
| review | 84,095 | 用户评论（rating/title/body） |
| review_summary | 2,749 | 评论汇总（avg_rating/星级分布） |
| site | 260 | 站点（含美国/日本/南美/欧洲零售 + 品牌官网） |

### 1.2 美国市场 SPEC 数据（TCP 报告核心数据源）
spec_series 美国品牌覆盖：
| 品牌 code | 系列数 | 备注 |
|-----------|--------|------|
| lg_us | 99 | LG 美国官网 |
| samsung_us | 66 | Samsung 美国官网 |
| hisense_us | 35 | Hisense 美国官网 |
| sony_us | 33 | Sony 美国官网 |
| tcl_us | 6 | TCL 美国官网 |

字段覆盖（实测样本）：Screen Size / Display Technology(QD-Mini LED/QLED/DLED) / Panel Refresh Rate / VRR / HDR / OS / Smart Platform / Dimensions(含/不含底座) / Weight / Connectivity(HDMI/USB/SPDIF) / Audio / Power / Wi-Fi 等。

### 1.3 美国市场价格数据
USD 价格快照 1,544 条，覆盖 1,225 个产品。来源站点：bestbuy_us / amazon_us / costco_us / walmart_us / lg_us / samsung_us / sony_us / hisense_us / tcl_us 等。

### 1.4 美国市场网评数据
| 站点 | 评论数 |
|------|--------|
| leons_ca | 15,515（加拿大，同北美） |
| bestbuy_us | 1,855 |
| lg_us | 1,357 |
| amazon_us | 793 |
| costco_us | 747 |

### 1.5 评测网站（编辑评测/榜单）— 关键缺口
- **欧洲线媒体评测站 30 站**：2026-09-24 新增需求，**全部 ❌ 未开始**（schema/adapter/抓取均无）。
  - 专业评测站 9：What Hi-Fi? / Les Numériques / Trusted Reviews / Expert Reviews / AVForums / AVPasion / HIFITEST.DE / HIFI.DE / FWD
  - 科技媒体 16：TechRadar / Clubic / Frandroid / connect / COMPUTER BILD / CHIP / JVTECH / Everyeye / Multiplayer.it / Hardware Upgrade / Techzilla / TechBit / PCGuia / TechFi / Tweakers / Xataka
  - 消费者组织付费墙 3：Which? / Stiftung Warentest / Consumentenbond
- **Rtings（TCP 报告引用的评测站）**：不在任何已规划/已抓取站点列表中。
- **skill 无 MEDIA 分支**：现有 skill 只有 SPEC/RETAIL/OPS 三分支，RetailSpec 契约围绕"给定型号→抓价"设计，套不上"爬评测文章→提取评分/榜单"。

---

## 二、TCP 报告各章节 vs 现有数据 — 逐章匹配

| 报告章节 | 需要的数据 | 现有数据 | 可生成性 |
|----------|-----------|----------|----------|
| 1. Overview 产品定位 | 技术+OS+售价+Rtings评分 | SPEC(技术/OS) ✅ + 价格(售价) ✅ + Rtings ❌ | 🟡 部分（Rtings 缺） |
| 1. Overview 对标海信机型 | 海信美国规格+售价 | hisense_us 35系列 ✅ + 价格 ✅ | ✅ 可 |
| 1. Overview 规格差异总结 | 各板块一句话 | SPEC ✅ + 网评 ✅ | ✅ 可 |
| 2. Key Features 基础规格表 | 15+ 规格字段 | SPEC ✅（字段名需归一化） | 🟡 需字段映射 |
| 2. Key Features 游戏音频表 | VRR/Freesync/Game Bar/Input Lag/扬声器 | SPEC 部分 ✅ + Input Lag ❌ | 🟡 部分 |
| 3. PQ Rtings 评分/亮度/Peaking/色域/对比度 | Rtings 测试数据 | ❌ 完全缺失 | ❌ 不可 |
| 3. PQ 亮暗场景主观对比 | 实机主观评价 | ❌ 缺失（需人工/AI 生成） | ❌ 不可 |
| 4. ME 包装/尺寸/重量/装箱量 | SPEC 尺寸重量 ✅ + 装柜量(需算) | ✅ 尺寸重量可，装箱量需计算 | 🟡 装柜量可算 |
| 4. ME ID/底座/后壳/配件细节 | 拆机级结构细节 | ❌ SPEC 无此粒度 | ❌ 不可 |
| 4. ME 成本对比(HX-JP) | 内部成本数据 | ❌ 非爬取可得 | ❌ 不可 |
| 5. HW 主板/电源板/SOC/DDR/WiFi | SPEC 部分有(SOC/DDR/WiFi) | 🟡 SOC/DDR/WiFi ✅，PCB尺寸/电源板细节 ❌ | 🟡 部分 |
| 5. HW 电源线接口(C14/C10) | SPEC 无 | ❌ 不可 | ❌ |
| 5. HW 成本对比 | 内部成本 | ❌ 不可 | ❌ |
| 6. LCM 面板/背光/LED/分区/OD/膜片 | SPEC 部分(背光方式/分区) | 🟡 背光方式/分区数 ✅，OD/膜片/灯条 ❌ | 🟡 部分 |
| 6. LCM 成本对比 | 内部成本 | ❌ 不可 | ❌ |
| 7. SW 性能/功能/隐私/AI/UI | SPEC(SW功能) + 网评(提及) | 🟡 SW 功能 ✅，性能实测/AI 细节 ❌ | 🟡 部分 |
| 8. Summary 借鉴点 | 竞品亮点→海信建议 | 需 AI 分析（非纯数据） | 🟡 可 AI 生成 |

---

## 三、现有报告生成模型评估

现有模型：`海外电视爬取项目/主程序/overseas/report/generate_report.py`
- **DeepResearch 6-Agent 架构**：ChiefArchitect(规划) → DataMiner(采集) → TrendAnalyst(分析) → CompetitorAnalyst(竞品) → ReportWriter(撰写) → CriticMaster(审核)
- **生成的是"市场级调研报告"**（品牌分布/区域/价格区间/评分/SPEC 覆盖/新系列预警/价格波动），即 `海外电视市场深度调研报告.md`
- **锚定 DB 真实数据，每条标注信源 `[来源:Sx]`，防幻觉**

**可复用性**：
- ✅ 6-Agent 协作架构、信源锚定防幻觉机制、DB 查询封装 — 可直接复用
- ❌ 报告大纲/章节是"市场总览"导向，与 TCP 报告"单产品对标分析"结构完全不同 — 需重写大纲与 ReportWriter
- ❌ DataMiner 采集的是市场级聚合统计，TCP 需要的是"指定竞品型号 + 指定海信型号 → 逐字段对比" — 需重写采集逻辑

---

## 四、综合结论

### 4.1 能生成什么（现有数据+模型直接支撑）
✅ **"精简版 TCP 封面说明"**（邮件导读版）— 可生成：
- 产品定位（SPEC 技术/OS + 价格售价）
- 对标海信机型（hisense_us 规格 + 价格）
- 规格差异一句话总结（SPEC 逐字段对比）
- 基础 Key Features 对比表（零售价/OS/显示技术/LD分区/刷新率/HDR/连接/WiFi）
- 借鉴点初稿（AI 基于 SPEC 差异 + 网评生成）

✅ **"市场级竞品监控报告"**（现有模型直接生成）— 已有产出 `海外电视市场深度调研报告.md`

### 4.2 不能生成什么（数据缺口阻塞）
❌ **完整版 TCP 分析报告 PPTX** — 缺三大块关键数据：
1. **Rtings 评测数据**（评分/亮度/Peaking/色域/对比度/EOTF/Motion）— 报告 PQ 章节核心，无数据源
2. **拆机级结构/硬件/模组细节**（PCB尺寸/电源板方案/背光OD/膜片/灯条/底座螺钉/包装蜂窝板）— SPEC 无此粒度
3. **内部成本对比(HX-JP)**（物料/竞品/海信/差额/部门）— 非爬取可得，需内部 ERP 成本数据

❌ **主观画质对比**（亮暗场景/色彩/肤色/Motion 实机评价）— 需人工样机评测，无法自动生成

### 4.3 评测网站的作用与现状
用户提到"最近新探索的评测网站抓取"——这部分对应**欧洲线媒体评测站 30 站**，目前**全部未开始**，且：
- 这 30 站是欧洲站（德/法/英/意/葡/荷/西），非美国站，与 TCP 报告（美国市场）地域不匹配
- 即使抓取完成，抓的是"编辑评测文章/评分/榜单"，可补充**PQ 章节的部分评测分数**，但仍无法替代 Rtings 的详细测试数据
- skill 需新增 MEDIA 分支才能接入

---

## 五、建议路径

### 方案 A：生成"精简版 TCP 封面说明 + 规格对比表"（现有数据直接可做，1-2 天）
- 复用现有 6-Agent 架构，重写大纲为 TCP 模板结构
- DataMiner 改为"给定竞品型号+海信型号→逐字段对比"
- 产出：Markdown 版封面说明 + Key Features 对比表 + 借鉴点初稿
- 缺口部分标注"需补充：Rtings 评测 / 拆机分析 / 内部成本"

### 方案 B：接入 Rtings 抓取，补齐 PQ 章节数据（需新增抓取，1-2 周）
- 新增 Rtings.com 站点接入（skill 新增 MEDIA 分支或扩展 RETAIL）
- 抓取：Rtings Score / 亮度 / Peaking / 色域 / 对比度 / EOTF 等测试数据
- 抓取后可生成完整 PQ Comparisons 章节

### 方案 C：生成完整 PPTX TCP 报告（需多源数据，长期）
- 需整合：SPEC 爬取 + 价格 + 网评 + Rtings 评测 + 拆机分析（人工）+ 内部成本（ERP）
- 拆机与成本部分无法自动化，需人工输入
- 可生成"骨架版"PPTX，留空待人工补充的章节

**推荐：先走方案 A 验证端到端流程，再按需推进方案 B 补 PQ 数据。方案 C 中成本/拆机部分建议保留为人工输入接口。**

---

## 六、数据质量注意点

1. **美国 SPEC 字段名未统一**：item_zh 多为空（英文未翻译），各品牌字段名不一致（如 samsung_us 用 "Display/Refresh Rate"，tcl_us 用 "Display/Panel Refresh Rate"，sony_us 用 hashed category），生成对比表前需做**字段归一化映射**。
2. **SPEC 值有空缺**：部分型号的某些字段值为空，需在报告中标注"无数据"。
3. **价格时间维度**：price_snapshot 是快照，TCP 报告用"上市售价"，需取最早快照或标注数据周期。
4. **网评与评测区分**：现有 review 表是 UGC 用户网评（Amazon/BestBuy），不是 Rtings 编辑评测，不能直接填 PQ 章节。
