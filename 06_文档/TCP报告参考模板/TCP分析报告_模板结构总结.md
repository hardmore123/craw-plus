# 海外市场竞品TCP分析报告 - 模板结构学习总结

> 本文档总结自 `海外/参考信息模板/` 下三份 TCP 分析报告模板（解密后逐页提取），供"生成调研报告"模块复用。
> 三份样本：
> - **TCL 85X11L**（2026-04，旗舰旗舰对标，单一对标机型，无成本对比章节）
> - **Samsung 55M70H**（2026-05，入门对标，双对标机型，含成本对比章节）
> - **TCL 55QM64L**（2026-06，中端对标，单一对标机型，含成本对比章节）
> 逐页文本见 `_decrypted/` 下三个 `*_幻灯片文本.md`。

---

## 一、报告整体框架（8 大章节，三份样本完全一致）

| # | 章节标题（英文/PPT 页眉） | 中文含义 | 是否含成本对比子页 |
|---|--------------------------|----------|---------------------|
| 1 | Overview | 概述（产品定位+对标+各板块差异） | — |
| 2 | Key Features Comparison | 关键规格对比（2 页：基础规格 + 游戏/音频） | — |
| 3 | PQ Comparisons | 画质对比（Rtings/亮度/Peaking/色域/对比度 + 亮暗场景主观对比多页） | — |
| 4 | ME Design | 结构设计（包装/内部泡棉/ID细节/底座后壳/配件） | 入门/中端有 |
| 5 | HW Design | 硬件设计（布局/主板电源板/电源线/扬声器/Wifi） | 入门/中端有 |
| 6 | LCM Design | 模组设计（Overview/背光设计 + 成本对比） | 入门/中端有 |
| 7 | SW Design | 软件设计（性能/功能/隐私/AI/UI/遥控/升级/Setting/Game Bar/开机画面） | — |
| 8 | Summary & Actions | 借鉴点表格 | — |

- 封面页（Slide 1）：`{品牌 型号} | TCP Analysis Report | {YYYY-MM}`
- 目录页（Slide 2）：`Contents | 1 Overview | 2 Key Features | ... | 8 Summary and Actions`
- 末页：`Thanks`

## 二、三种样本差异（按对标机型数与成本章节区分）

| 维度 | TCL 85X11L（旗舰） | Samsung 55M70H / TCL 55QM64L（入门/中端） |
|------|-------------------|-------------------------------------------|
| 对标海信机型数 | 1（85UR9S） | 2（Samsung：QD6SF + M7SR；TCL：仅1个但表格按双对标样式） |
| 成本对比章节 | 无 | 有（ME/HW/LCM 各含 Cost Comparison 子页，按 物料/竞品/海信/差额/(HX-JP)/差异说明/对应部门 列） |
| Overview 成本表 | 仅功耗对比 | 含 结构/硬件/光学/合计 差额表 |
| Summary 表列数 | 5 列：No. / TCP solutions and learn / Sections / Owner | 6 列：No. / TCP solutions and learn(或 TCP Reference Practices) / Sections / Department / Owner |

## 三、章节内容数据模式（用于从爬取数据生成报告时的字段映射）

### 1. Overview 页（核心信息密度最高，可由爬取数据直接填充）
- **产品定位**：品牌 + 市场档位 + 技术（如 SQD-MiniLED / QD-Mini Fire TV）+ OS + 上市售价 + Rtings 评分（若有）
- **对标海信机型**：型号 + 内部代号 + 技术规格 + 售价
- **规格差异**（4-5 段一句话总结）：结构外观 / 硬件配置 / 显示性能 / 软件功能 / 成本方面
- **功耗对比表**（旗舰版）/ **成本差额表(HX-JP)**（入门/中端版）

### 2. Key Features Comparison（2 页）
**第 1 页基础规格表**（列：Item / 竞品 / 海信，双对标则 3 列竞品）：
Retail Price | OS | Display Technology | LD zones | Panel Refresh Rate | MEMC | Wide Color Gamut | 4K HDR | Filmmaker Mode | Anti-Glare | Connectivity | ATSC 3.0 | Wifi

**第 2 页游戏/音频表**：
Game Features: ALLM | VRR | Freesync | G-Sync Compatible | HGiG | 4K 144Hz | Game Bar | Input Lag 4K@60Hz
Audio: Speaker Channel | Audio Technology | Sub Woofer | Sound Room Optimization

### 3. PQ Comparisons（多页，旗舰版更详细）
- **规格总表**：Rtings Score | Local Dimming | Full White Brightness(@Movie/Standard/Vivid) | HDR max Peaking(2%/5%/10% Win) | Color Checker ΔE2000(Avg/Max) | Grayscale ΔE2000(Avg/Max) | Avg. Gamma | Color Gamut(REC709/DCI P3/BT2020 @1931) | Color Temperature(Avg) | Contrast Native/Dynamic | Full white uniformity
- **主观对比页**（每页 1 句 Summary）：亮场景 / 暗场景 / 局部高亮 / 色彩 / 肤色 / 可视角 / Motion / 模组面板 / 对比度测试
- **Peaking 亮度对比表**（窗口 1%-100% + 实际场景 Hallway/Yellow/Landscape）
- **对比度测试表**（W1/W2/B1-B4 白场黑场均值 → Native/Dynamic 对比度，条件 LD=Off / LD=High）

### 4. ME Design
- **Carton Solution 表**：Product Size(w/wo Stand) | Net Weight | Package Size | Container Load 40H | Shipping weight | Carton Material | Open box design | Corner protect | Screen protect board | Screen cover | Screen protection tape | Anti-crumb screen cover | Layers stack | 前壳材质 | 后壳样式
- **Insider Foam**（一段话）：上下 EPS + 蜂窝板规格
- **ID details**：前壳材质 / 中框 / 后壳 / 底座 / 整机厚度 / 生产组装地（墨西哥）
- **Stand & Backcover** / **Accessories**：遥控器规格 / 电源线（长×线径×V）/ 底座螺钉数
- **Cost Comparison**（入门/中端）：按 物料/竞品/海信/差额/差异说明/价格差异原因/差额对应部门(PM 质量 研发 采购 工艺) 列，逐项到背板/前壳/后壳/底座/结构小件/包装

### 5. HW Design
- **Layer out**（一段话）：主板/Tcon 二合一、理线胶带数
- **Mainboard and Power board 表**：Mainboard PCB size | Powerboard PCB size | Localdimming units(BLU) | TCON | FRC | SOC | Power Guide($) | Max power in full white | SOC Heatsink size | DDR | EMMC/NAND | WiFi | AMP
- **Speaker**：功率(配置) + 尺寸(Main/Sur/Sub/Sky) + 频响曲线评价
- **Wifi** / **Power Cord**：型号 / 规格 / 天线类型 / 接口类型(C14/C10)
- **Cost Comparison**（入门/中端）：电源 / 主板 / 端子 / 散热器 / 辅料 / 遥控 / 音响 / 无线 / TCON / 线材类 / 驱动板 → 合计

### 6. LCM Design
- **Overview 表**：Open cell Model No. | Low reflection | Native Refresh rate | 白场最大亮度 | 白场最大功率 | Number of LEDs | LED type | Size of Lens | Backlight PCB size | 背板厚度 | 背板抗扭强度 | 光学膜片(贴合膜类型/厚度) | 反射片 | 支架数量 | 扩散板(厚度/类型) | High Color Gamut Film | OD(mm)
- **Backlight design**（多页）：无边框形态 / 膜片方案 / 灯条数量驱动IC / 模组外观尺寸(D1/D2/D3/H1/H/BM/Bg/Ba/B0)
- **Cost Comparison**：模组光学 贴合膜/反射片/LED/灯条转接板/扩散板/灯条线 → 总计

### 7. SW Design（多页，每页一个主题 + "启发"段）
Performance / Remote / Update / Setting / Gaming / 开机画面 / UI / AI / Privacy / Policy&Security / Feature(Gemini/Game Bar/TCL tv+)
- 入门/中端版每页带 **"启发："** 段（对海信的建议），旗舰版无此段（借鉴点集中在 Summary 表）

### 8. Summary & Actions（借鉴点表格，报告核心输出）
- 表头：`No. | TCP solutions and learn(或 TCP Reference Practices) | Sections | [Department] | Owner`
- Sections 取值：PQ / LCM / HW / SW / VIDAA / 面板规划 / 遥控器 / AM产品线 等
- Department 取值（入门/中端版）：结构研发部 / 显示研发部 / 硬件研发部 / 产品经理部 / AM产品线 等
- 每条 = 竞品设计亮点 + 借鉴建议（海信需…）

## 四、配套邮件封面说明（Email Cover Note）

每份 PPTX 报告附带的邮件正文（即 `.eml` 文件 / `.md` 文件）是报告的**精简版导读**，结构固定：
1. 一句话产品定位 + 售价 + OS + 关键卖点
2. 对标海信机型 + 内部代号 + 规格 + 售价
3. 各板块一句话对标总结（1 结构外观 / 2 硬件配置 / 3 显示性能 / 4 软件功能 / 5 成本方面）
4. 借鉴点表格（与 PPTX Summary 表一致）
5. 落款：Kogan 区可坚 / Hisense USA Corporation / Hisense USA Multimedia R&D Center Inc. / 地址 / 网站

> 邮件封面说明 = PPTX 的"摘要版"，可作为生成报告时的先导输出（先生成封面说明，再扩展为 PPTX 全量）。

## 五、生成调研报告时的数据来源映射建议

本项目海外爬取系统已采集的 SPEC / 价格 / 网评数据可映射到报告各章节：

| 报告章节 | 数据来源（overseas.db） |
|----------|------------------------|
| Overview 产品定位 | SPEC 系列 + 零售价格快照 + 系列状态 |
| Key Features Comparison | SPEC 规格数据（LD zones / Refresh Rate / HDR / OS 等） |
| PQ Comparisons | SPEC 规格 + 网评评分（Amazon/Rtings 类） |
| ME/HW/LCM Design | SPEC 规格（尺寸/重量/包装/SOC/DDR/扬声器/面板/背光） |
| SW Design | SPEC 规格 + 网评（功能提及频率） |
| Summary & Actions | 需人工/AI 分析（竞品亮点 → 海信借鉴建议），非纯数据填充 |

> 注：成本对比(HX-JP)为内部成本数据，非爬取可得，生成报告时该部分需留空或标注"需内部成本数据补充"。

## 六、解密服务器使用要点（生成报告时如需读取加密模板/参考文件）

- 服务器：`http://10.18.87.51:8500`（健康检查 GET `/` 返回 200）
- 解密并取文件流：`POST /parse_file` form-data `file=@加密.pptx` + `format=file` → 直接返回明文二进制
- 解密并取文本：`format=json`（Word/PDF 返回 content 字符串）或 `format=markdown`
- 服务器每次请求后**自动清理 files/ 目录**，无需手动删除服务端临时文件
- 本地解密后的文件用完应删除（避免明文留存）
