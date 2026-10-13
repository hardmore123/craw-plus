# Samsung 55M70H TCP分析报告 - 幻灯片文本（解密后提取）

> 来源：美国市场竞品TCP分析报告 - Samsung 55M70H.eml 内附件 Samsung_55M70H_TCP_Analysis_Report_-202605-发布.pptx
> 解密：经解密服务器 http://10.18.87.51:8500/parse_file format=file 解密后提取
> 仅供本项目"生成调研报告"部分学习参考，非对外交付。

---

## Slide 1 - 封面
Samsung 55M70H | TCP Analysis Report | 2026-05

## Slide 2 - 目录
Contents | 1 Overview | 2 Key Features | 3 PQ Comparisons | 4 ME Design | 5 HW Design | 6 LCM Design | 7 SW Design | 8 Summary and Actions

## Slide 3 - 1. Overview（概述）
**产品定位**：三星2026年新增的一档M70H入门产品，4K 60Hz，售价$449，主卖点宣传Mini LED，开机画面显示Mini LED，但无LD分区、无峰值亮度、无Local Dimming画质效果，宣传Mini LED从方案看仅仅是因为背光使用的LED单晶片尺寸0.5mm比普通常规LED晶片小，宣传存在误导性。
**对标**：海信55QD6SF (内部: 55Q60SUF(01))，QLED 4K 60Hz Fire TV。应产品规划需求，规格上有一并对标海信128 LD分区真Mini LED的55M7SR (内部: 55K80SUR(01))。
**规格差异**：
- 结构外观：三星黑色前壳，背板F折弯，几字型小后壳，双腿一字形塑料底座，整机厚度78.8mm；海信QD6SF黑色前壳，背板C折弯，几字型小后壳，整机厚度72.8mm，装箱量比竞品高5.9%；海信M7SR黑色前壳，背板F折弯，一体大后壳，整机厚度63.2mm，装箱量比竞品高5.9%。
- 硬件配置：三星Tizen TV，SDP23405方案，1.5+8GB存储，WiFi5，无远场语音，带光感，2.0声道；海信QD6SF Fire TV，MT9603方案，2+32GB存储，WiFi5，无远场语音，带光感，2.0声道；海信M7SR Roku TV，TR964方案，1+0.5GB存储，WiFi5，无远场语音，无光感，2.0声道。
- 显示性能：对标海信QD6SF，三星亮度规格与QD6SF相当，海信亮场景表现更好，暗场景表现比三星差，可视角比三星好；对标海信M7SR，带128背光分区真Mini LED，亮度规格比三星高，亮/暗场景表现比三星更好。
- 软件功能：三星Tizen OS实现统一卡片化Settings设计、集中化AI入口及系统级安全管理，系统级安全管理机制尤其值得借鉴。
- 成本方面(O/C外)：对标海信55QD6SF，竞品方案成本低￥48.09，主要差异是海信储存规格高，硬件方案成本高。

**成本差额表(HX-JP)**：
| 版块 | 竞品 | 海信 | 差额 | 差异说明 |
| 结构 | * | * | -11.66 | 海信结构方案成本有优势，竞品后壳/底座/结构小件成本高 |
| 硬件 | * | * | 68.45 | 海信Fire TV储存规格高，硬件成本高 |
| 光学 | * | * | -8.7 | 海信光学方案成本有优势，竞品三层贴合膜DPP成本高 |
| 合计 | * | * | 48.09 | 竞品方案成本有优势 |

## Slide 4 - 2. Key Features Comparison (1)
| Item | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| Retail Price | $449 | $259 | 未上市预估$339 |
| OS | Tizen TV | Fire TV | Roku TV |
| Display Technology | DLED | DLED | DLED |
| LD zones | No | No | 128分区 |
| Panel Refresh Rate | 60Hz | 60Hz | 60Hz |
| MEMC | Yes | Yes | No |
| Wide Color Gamut | KSF | QD | QD-Mini |
| 4K HDR | HDR10/HLG/HDR10+ | HDR10/HLG/HDR10+/Dolby Vision | HDR10/HLG/Dolby Vision |
| Filmmaker Mode | Yes | Yes | Yes |
| Anti-Glare | No | No | No |
| Connectivity | 1*Tuner 3*HDMI 1*Ethernet 1*USB | 1*Tuner 3*HDMI 1*SPDIF 2*USB 1*Ethernet | 1*Tuner 3*HDMI 1*SPDIF 1*USB 1*Ethernet |
| ATSC 3.0 | No | No | No |
| Wifi 6 | No | No | No |
Summary：竞品不支持Dolby Vision；竞品无SPDIF端子对老音频设备兼容性较弱。

## Slide 5 - 2. Key Features Comparison (2) - Game & Audio
| Item | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| ALLM | Yes | Yes | Yes |
| VRR | Yes, 4K 60Hz, 2K 120Hz | Yes, 4K 60Hz, 2K 120Hz | Yes, 4K 60Hz, 不支持HSR |
| Freesync | No | No | No |
| G-Sync Compatible | 实测支持 | 实测支持 | 实测不支持 |
| HGiG | Yes | No | No |
| 4K 144Hz | No | No | No |
| Game Bar | No, 有Gaming Hub | No | No |
| Input Lag 4K@60Hz | 9.9ms | 9.7ms | 11.0ms |
| Speaker Channel | 2.0 | 2.0 | 2.0 |
| Audio Technology | DTS Virtual X | Dolby Atmos | DTS Virtual X |
| Sub Woofer | No | No | No |
| Sound Room Optimization | No | No | No |
Summary：三星55M70H规格与55QD6SF相当，55M7SR为Roku TV不支持HSR/G-Sync Compatible。

## Slide 6 - 3. PQ Comparison
| Item | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| Rtings评分 | 无 | 无 | 无 |
| Local Dimming | No LD | No LD | 128 LD Zones |
| Full White Max Brightness | 312nits | 317nits | 477nits |
| HDR max Peaking | No LD | No LD | 瞬态725nits 稳态580nits |
| Color Checker ΔE2000 | Avg:3.11 Max:5.28 | Avg:2.43 Max:5.17 | Avg:2.31 Max:6.24 |
| Grayscale ΔE2000 | Avg:3.3 Max:5.5 | Avg:2.7 Max:4.2 | Avg:3.0 Max:4.3 |
| Avg. Gamma | Movie:2.322(BT1886) | Movie:2.158(2.2) | Movie:2.179(2.2) |
| Color Gamut(1931 xy) | REC709:99.9% DCI P3:94.5% BT2020:72.4% | REC709:98.7% DCI P3:90.2% BT2020:66.5% | REC709:99.6% DCI P3:93.2% BT2020:71.5% |
| Color Temperature(Avg) | Movie:6820 Std:10906 | Movie:6940 Std:11050 | Movie:6280 Std:9770 |
| Contrast Native(W/o LD) | 5710:1 | 1310:1 | 1380:1 |
| Contrast Dynamic(W/LD) | N/A | N/A | 1895:1 |
| Full white uniformity | 74.5% | 69.2% | 82.2% |
Summary：三星55M70H亮度规格与海信55QD6SF相当，与海信55M7亮度规格差距大。

## Slide 7 - PQ - SS 55M70H vs 55QD6SF 亮场景
亮场景下三星高亮过饱和，高亮细节缺少，表现比海信差。

## Slide 8 - PQ - SS 55M70H vs 55QD6SF 暗场景
暗场景下海信使用IPS面板，暗场对比度、景深表现比三星差。

## Slide 9 - PQ - SS 55M70H vs 55QD6SF 可视角
海信使用IPS面板，可视角比三星好。

## Slide 10 - PQ - SS 55M70H vs 55M7SR MiniLED 亮场景
亮场景下三星高亮过饱和，海信55M7带LD分区，高光更亮，画面更有层次感和通透感。

## Slide 11 - PQ - SS 55M70H vs 55M7SR MiniLED 暗场景
暗场景下海信55M7带LD分区，有更高对比度，在暗场保留高光亮度和暗部细节，画面层次更清晰。

## Slide 12 - 4. ME Design--Carton Solution
| Items | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| Product Size(w/ Stand) | 48.21"x29.92"x7.83" | 48.6"x29.6"x11.7" | 48.3"x29.8"x11.7" |
| Product Size(w/o Stand) | 48.21"x27.87"x3.02" | 48.6"x28.1"x2.9" | 48.3"x28.1"x2.6" |
| Net Weight(w/ Stand) | 22.71lbs | 20.9lbs | 28.0lbs |
| Net Weight(w/o Stand) | 22.05lbs | 20.5lbs | 27.6lbs |
| Package Size | 53.31"x31.89"x5.00" | 53.5"x33.3"x4.9" | 53.5"x33.3"x4.9" |
| Container Load 40H | 408 | 432 | 432 |
| Shipping weight | 31.97lbs | 20.3lbs | 36.6lbs |
| Carton Material | 单面贴彩箱 | 单面贴彩箱 | 单面贴彩箱 |
| Open box design | 叠盖箱 | 叠盖箱 | 叠盖箱 |
| Corner protect | 无 | 无 | 无 |
| Screen protect board | 无 | 10mm蜂窝板 | 10mm蜂窝板 |
| Screen cover覆膜 | 有 | 有 | 有 |
| Screen protection tape | 上下左右 | 上下左右 | 上下左右 |
| Anti-crumb screen cover | 无 | 有 | 有 |
| Layers stack | 6 | 6 | 6 |
| 前壳材质 | 塑料下前壳 | 塑料下前壳 | 塑料下前壳 |
| 后壳样式 | 塑料几字后壳 | 塑料几字后壳 | 塑料大后壳 |
Summary：海信装箱量比竞品高5.9%。

## Slide 13 - 4. ME Design--Insider Foam
竞品上下EPS无蜂窝板顶屏；海信上下EPS 10mm蜂窝板顶屏。根据海信55Q60QUV无蜂窝板和有蜂窝屏碎数据对比，无蜂窝板屏碎率翻近一倍，蜂窝板暂时不会去掉。

## Slide 14 - 4. ME Design--ID details
竞品无边框非悬浮屏，背板F折弯，注塑前壳，几字小后壳，双腿一字形塑料底，底座安装无螺钉；生产组装地墨西哥。对于三星底座无螺钉方案，总部研发已完成双腿底座插入式无螺钉方案预研，需采用新接口立柱，成本比传统锁螺钉方案高，且底座需全新开模、接口无法通用，方案暂不可行。

## Slide 15 - 4. ME Design--Cost Comparison-55QD6SF 结构方面
海信较竞品成本低￥11.66元，差异：
- 背板+胶框：-2.53，竞品背板0.5T带喷涂下边条硬胶框+上下密封件，海信0.5T带喷涂无胶框密封件支持面板，竞品带下胶框M8壁挂螺母柱成本高
- 前壳：-0.64，竞品PC+ABS-ED18FR(40)/94g，海信ABS+GF10/130g，竞品材料单价高
- 后壳：-5.52，竞品几字后壳HIPS(PCM35%) HB/1270g+绝缘片，海信上部PC+ABS V0/469g+下部ABS，海信用料少
- 底座：-3.16，竞品PP-(GF35+PD7.5)/131g，海信PP GF40/162g，竞品材料单价高尺寸大加工费高
- 结构小件：-2.86，竞品有底座滑轨柱6个，海信无
- 包装：3.05，竞品无顶屏防蜂窝板
结构件合计：-11.66，海信K1平台结构方案成本有优势

## Slide 16 - 4. ME Design--Accessories
三星入门机型通用遥控器，电源线长1.55m线径2x18AWG 300V；三星底座安装无螺钉，用户安装底座便捷。

## Slide 17 - 5. HW Design--Layer out
竞品TCON主板二合一，遥控WiFi二合一，主板和电源板插座直连，内部布局较简洁。

## Slide 18 - 5. HW Design--Mainboard and Power board
| Items | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| Mainboard PCB size | 200x160x1.6mm | 190x180x1.6mm | 145x145x1.6mm |
| Powerboard PCB size | 125x160x1.6mm | / | 234x165x1.6mm |
| BLU | / | / | 110x38x1.2mm |
| TCON | / | 133x47x1.2mm | 133x47x1.2mm |
| SOC | SDP23405 | MT9603E | TR964 |
| Power Guide | $30 | $27 | /(开发中) |
| Max power in full white | 98W | 84W | 143W |
| SOC Heatsink size | 120x95x1.6mm | 80x68x3mm | 80x68x3mm |
| DDR | 内置1GB+外置0.5GB | 南亚DDR3-2133 2GB | 1GB |
| EMMC/NAND | 8GB | Skyhigh 32GB | 0.5GB |
| WiFi | MT7668 | MT7663 | RTL8812 |
| AMP | AD82120S | TAS5805 | NTP8928 |
Summary：三星芯片规格内置1GB DDR，其他规格同72691，当前EOL。

## Slide 19 - 5. HW Design--Speaker
55QD6SF扬声器24W(2*12W) Main 140x60x30mm；竞品20W(2*10W) Main 120x95x35mm。三星频响曲线比较平整，整体调音风格均衡，无低音炮低频不足，伴音曲线增长平缓。

## Slide 20 - 5. HW Design--Wifi
竞品WiFi采用7668，WiFi5规格，板载3陶瓷天线，带遥控光感。

## Slide 21 - 5. HW Design--Cost Comparison-55QD6SF 硬件电源
- 电源：-12.29，竞品独立电源板125x160x1.6mm CEM-1，55Q60SUF三合一主板190x180.6x1.6mm电源板算95x180
- -0.54，55Q60SUF反激方案OB2271+OB3375，竞品PFC+LLC方案
- -8.25，电解电容竞品方案不同器件数量多
- -1.6，其他散件竞品体积大

## Slide 22 - 5. HW Design--Cost Comparison-55QD6SF 硬件主板
- 主板：79.14，竞品SDP23405主芯片(规格同NT72691 EOL)，海信MT9603E；竞品DDR 1.5GB/海信2GB；竞品8GB EMMC/海信32GB
- 79.91 功放及电感(规格相同无差异)
- 0.13 其他集成电路

## Slide 23 - 5. HW Design--Cost Comparison-55QD6SF 端子/散热器/辅料
- 端子：0.7，竞品比55Q60SUF少一个spdif一个usb，海信多2个端子
- 散热器：-0.2，竞品面积大
- 辅料：-1.4，竞品7颗导电泡棉海信无
- 遥控：0，竞品带光感无麦克风

## Slide 24 - 5. HW Design--Cost Comparison-55QD6SF 音响/无线/TCON
- 音响：-0.42，55Q60SUF扬声器腔体大功率高，竞品风管设计复杂模具成本高
- 无线：-1.2，竞品MT7668贴片陶瓷天线，海信MT7663/RTL8812板载PCB天线，竞品陶瓷天线成本高
- TCON：1.93，竞品DA2545，海信G2734P+G2794A，竞品PCB包含在主板中

## Slide 25 - 5. HW Design--Cost Comparison-55QD6SF 线材/合计
- 线材类：1.29，屏线FFC-108KP1-360-Z2(108pin 360mm)，WiFi FFC-30KP1-550-Z2(30pin 550mm)
- 合计：68.45(72.08-3.63)，竞品电源板PFC+LLC，55Q60SUF反激，55K80SUR带OCP电路内置中控

## Slide 26 - 6. LCM--Overview
| Items | Samsung 55M70H | Hisense 55QD6SF | Hisense 55M7SR |
| Open cell Model No. | HKC P550GT06-8 | BOE HV550QUB-F74 | BOE HF550QUB-F21 |
| Low reflection | No | No | No |
| Native Refresh rate | 60Hz | 60Hz | 60Hz |
| 白场最大亮度 | 312nits | 317nits | 477nits |
| 白场最大功率 | 98W | 84W | 143W |
| Number of LEDs | 36=18 LEDs*2 bars | 40=20 LEDs*2 bars | 128=16 LEDs*8 bars |
| LED type | 反射式Lens 3433六晶并2.86V KSF 700mA | 反射式Lens 3030单晶 KSF 530mA | 折射式Lens 3030双晶串 KSF |
| Size of Lens | d=17.4mm | d=15.8mm | d=15.8mm |
| Backlight PCB size | 铝基板1.0mm 1040*12.5*2bars=26000mm² | 铝基板1.0mm 1146*12*2bars=27504mm² | 铝基板0.8mm 1122*14*8bars=125664mm² |
| 背板厚度 | 0.5mm | 0.5mm | 0.5mm |
| 背板抗扭强度 | 良好 | 良好 | 良好 |
| 光学膜片 | 1*贴合膜DPP 0.4mm | 1*贴合膜MOP 0.3mm | 1*贴合膜MOP 0.3mm |
| 反射片 | 0.188mm带印刷 | 0.188mm无印刷 | 0.188mm无印刷 |
| 支架数量 | 4个粘贴固定 | 12个螺钉固定 | 17个螺钉固定 |
| 扩散板 | 1.2T普通扩散板 | 1.5T量子点扩散板 | 1.5T量子点扩散板 |
| OD(mm) | OD40 | OD27 | OD20 |

## Slide 27 - 6. LCM--Backlight design
Samsung三边无边框，与去年U8000F同一套模具，带下边条胶框，左上区域有密集磨伤和异物小点；Hisense三边无边框，无下边条胶框，使用密封件替代。

## Slide 28 - 6. LCM--Backlight design 膜片方案
Samsung 1.2T普通扩散板+1张三层合膜DPP，膜片通过背板天侧折弯槽内嵌2个挂耳支架固定，无其他辅料；Hisense 1.5T量子点扩散板+1张贴合膜MOP，有5条扩散板胶带、2条膜片双面胶、背板三边C型槽8条胶条，海信辅料多。

## Slide 29 - 6. LCM--Backlight design 灯条
Samsung灯条2*18=36颗，无背光分区，反射透镜，灯条点胶固定，印刷反射片，4个弹性支架，反射片三边不搭在F折弯槽内；宣传Mini LED从方案看仅因LED单晶片尺寸0.5mm比常规LED晶片小，无实质Local Dimming画质效果。55QD6SF灯条2x20=40颗无背光分区；55M7SR灯条8x16=128颗一灯一区折射透镜，17个扩散板支架。

## Slide 30 - 6. LCM--Backlight design 模组外观尺寸
| 项目 | 位置 | 数值 |
| 外观厚度D1 | 第1层台厚度 | 8.3mm |
| 外观厚度D2 | 第2层台厚度 | 51.4mm |
| 整机厚度D3 | | 78.8mm |
| 后壳高度H1 | | 494mm |
| 模组屏高度H | | 705mm |
| BM宽度 | | 5.9mm |
| 闪缝间隙均值Bg | | 1.16mm(左1.3/天1.2/右1.0) |
| F折弯宽度Ba | | 1.5mm |
| B0 | | 8.56 (BM+Bg+Ba) |

## Slide 31 - 6. LCM--Cost Comparison 模组光学
海信方案成本比竞品低￥8.7：
- 贴合膜：-10.2，竞品DPP 0.4mm，海信MOP 0.3mm，竞品三层DPP成本高
- 反射片：-2.5，竞品带印刷，海信无印刷
- LED：-2.5，竞品多晶并灯珠成本高
- 扩散板：6.5，海信QD扩散板成本高
- 灯条线：0，端子成本相当
总计：-8.7，海信光学方案成本有优势

## Slide 32 - 7. SW Design--UI
1、Tizen OS在左上角集成Search、Settings与Connected Devices等入口，整体Settings UI风格更统一卡片化，支持便捷设备管理、功能导航与用户自定义操作；2、Tizen OS的Settings UI支持用户对图标编辑、排序、移动、隐藏及快捷布局管理；3、分类功能放置在home界面顶端，缩小图标半透显示，包含主界面、LiveTV、Games、Apps。

## Slide 33 - 7. SW Design--AI
1、三星TV的AI Version功能在Home页面提供独立入口；2、提供4个功能选项Spoken Responses、User Guide、Terms&Conditions、Summary，AI Response开关控制是否显示AI生成的智能回答、推荐内容与上下文信息；3、Vision AI助手提供各种主题探索功能，引导用户使用遥控器语音或SmartThings app交互；4、AI Version加入New Summary类功能，可对内容、搜索结果或信息进行AI摘要展示。

## Slide 34 - 7. SW Design--Policy&Security Center
Tizen的Policy & Security Center是一套完整安全管理系统，像"轻量Knox化的设备级安全控制中心"，用于统一管理设备安全策略执行、应用权限控制以及设备安全状态与合规性，确保系统在不同运行模式下按既定安全规则运行，对权限访问、系统配置变更和安全事件集中管控与记录。

## Slide 35 - 8. Summary & Actions
| No. | TCP solutions and learn | Sections | Department | Owner |
| 1 | 竞品扩散板支架数量少只有4个，请论证减少支架数量，降低成本和提升装配效率。 | LCM | 结构研发部 | 刘育伯 |
| 2 | 竞品扩散板比海信薄，请论证减薄扩散板厚度降低成本。 | LCM | 显示研发部 | 宗志豪 |
| 3 | 隐私安全：短期可通过安全能力展示向用户呈现隐私与安全认证信息，长期则逐步实现用户数据分离与更系统化的隐私保护能力，从而提升整体安全体验。 | SW | 产品经理部 | 周玲玉 |
| 4 | 竞品卡片化的Setting界面，且支持对设置图标进行编辑、排序、隐藏以及快捷布局管理，提升用户操作效率与使用便捷性。（VIDAA OS借鉴） | SW | 产品经理部 | 周玲玉 |

## Slide 36 - Thanks
Thanks
