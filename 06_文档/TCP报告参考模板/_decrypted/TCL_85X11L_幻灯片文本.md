# TCL 85X11L TCP分析报告 - 幻灯片文本（解密后提取）

> 来源：TCL 85X11L TCP Analysis Report-202604-发布.pptx（经解密服务器 http://10.18.87.51:8500/parse_file format=file 解密后提取）
> 仅供本项目"生成调研报告"部分学习参考，非对外交付。

---

## Slide 1 - 封面
TCL 85X11L | TCP Analysis Report | 2026-04

## Slide 2 - 目录
Contents | 1 Overview | 2 Key Features | 3 PQ Comparisons | 4 ME Design | 5 HW Design | 6 LCM Design | 7 SW Design | 8 Summary and Actions

## Slide 3 - 1. Overview（概述）
**产品定位**：TCL美国市场定位最高档的X11L系列，SQD-MiniLED，Google TV，上市售价$7999，Rtings评测8.6分，是目前LCD产品得分最高的机型。
**对标**：海信85UR9S (内部: 85U85SUA(02))，RGB MiniLED，Google TV，上市售价$3999。
**规格差异**：
- 结构外观：竞品前出音铝挤下前壳，一体平整板材后壳，双腿单跨距/高度不可调底座，整机厚度(含前壳)24.7mm，包装厚，装柜只堆码一层；海信铝挤下前壳，一体平整塑料后壳，中间立柱高度可调底座，整机厚度47.8mm，装柜堆码两层，装柜量高223%。
- 硬件配置：竞品MT9655方案，2.5+64GB存储(软件读取)，WiFi 6+BT5.4，带远场语音，带光感，5.2声道音响，功耗高；海信MT9655方案，4+32GB存储，WiFi 6E+BT5.4，带远场语音，带光感，4.1.2声道音响。
- 显示性能：竞品优势是分区数14400个和峰值亮度接近10000nits，OD3mm小，画面对比度和Blooming表现好，Rtings得分高主要原因；海信85UR9S全白场亮度和色域值比竞品高，画面色彩更透亮，层次感更强，Motion表现更优，刷新率180Hz比竞品高。
- 软件功能：竞品已通过ISO/IEC 27001、ISO/IEC 27701及TRUSTe认证，建立完善隐私管理体系；TCL TV+通过清晰信息架构+分类导航+点播能力，体验更简洁高效灵活。

**功耗对比表**：
| 项目 | Hisense 85UR9S | TCL 85X11L | 备注 |
| 全白亮度700nits下功率 | 205W | 512W | UR9功率低60% |
| 全白亮度500nits下功率 | 161W | 380W | UR9功率低58% |

**关键规格表**：
| 项目 | Hisense 85UR9S | TCL 85X11L |
| Rtings Score预估 | 8.5 | 8.6 |
| Display Technology | RGB-Mini LED | SQD-Mini LED |
| Native Refresh Rate | 180Hz | 144Hz |
| Local Dimming zones | 1320 Zones x3 | 14400 Zones |
| Typical Brightness | Movie:1193nits | Movie:725nits |
| Peak Brightness 2% | Movie:4061nits | Movie:9622nits |
| Peak Brightness 5% | Movie:4765nits | Movie:8841nits |
| Color Gamut BT.2020 1931 | 92.5% | 89.0% |
| Color Gamut BT.2020 1976 | 93.9% | 91.8% |
| SOC+DDR+EMMC | MT9655 4G+32G | MT9655 2.5G+64G |
| VRR | 4K 180z VRR, 2K 330Hz | 4K 144z, 2K 288Hz |

## Slide 4 - 2. Key Features Comparison (1)
| Item | TCL 85X11L | Hisense 85UR9S |
| Retail Price | $7999 | $3999 |
| OS | Google TV | Google TV |
| Display Technology | DLED | DLED |
| LD zones | 14400 | 1320 |
| Panel Refresh Rate | 144Hz | 180Hz |
| MEMC | Yes | Yes |
| Wide Color Gamut | Yes, SQD-Mini | Yes, RGB-Mini |
| 4K HDR | HDR10/HLG/HDR10+/Dolby Vision IQ | HDR10/HLG/HDR10+/Dolby Vision IQ |
| Filmmaker Mode | Yes | Yes |
| Anti-Glare | 超低反LR | 超低反LR |
| Connectivity | 1*Tuner 4*HDMI 1*SPDIF 1*AV 2*USB 1*Ethernet | 1*Tuner 3*HDMI 1*SPDIF 2*USB 1*Ethernet 1*DP |
| ATSC 3.0 | Yes | Yes |
| Wifi 6 | Yes | Yes, 6E |
Summary：TCL最高端产品，LD分区14400个，峰值亮度接近10000nits；TCL最高刷新率144Hz，海信支持180Hz；TCL侧边USB，海信侧边DP接口（支持更高分辨率刷新率）。

## Slide 5 - 2. Key Features Comparison (2) - Game & Audio
| Item | TCL 85X11L | Hisense 85UR9S |
| ALLM | Yes | Yes |
| VRR | Yes, 4K 144Hz VRR, 2K 288Hz | Yes, 4K 180Hz VRR, 2K 330Hz |
| Freesync | FreeSync premium Pro 144Hz | FreeSync premium Pro 180Hz |
| G-Sync Compatible | Yes | Yes |
| HGiG | Yes | No |
| 4K 144Hz | Yes | Yes |
| Game Bar | Yes | Yes |
| Input Lag 4K@60Hz | 14.5ms | 12.1ms |
| Speaker Channel | 5.2 | 4.1.2 |
| Audio Technology | Dolby Atmos | Dolby Atmos, DTS VX |
| Audio out power | 39W(3*3W+2*10W+2*5W) | 90W(2*15W+20W+2*10W+2*10W) |
| Sound Room Optimization | / | / |
Summary：海信比TCL支持更高VRR范围；TCL不支持DTS Virtual:X音效，扬声器输出功率低。

## Slide 6 - 3. PQ Comparison
| Item | TCL 85X11L | Hisense 85UR9S |
| Rtings Score | Actual 8.6 | Estimated 8.5 |
| Local Dimming | 14400 zones | 1320 zones x3 |
| Full White Brightness | 725/717/712nits | 1193/1236/1083nits |
| HDR max Peaking(2/5/10%) | Movie:9622/8841/5845; Standard:8407/8504/6058; Vivid:8276/8044/5539 | Movie:4061/4765/3744 |
| Color Checker ΔE2000 | Avg:1.43, Max:3.79 | Avg:1.33, Max:4.31 |
| Grayscale ΔE2000 | Avg:1.9, Max:3.1 | Avg:1.2, Max:1.6 |
| Avg. Gamma | Movie:2.34 | Movie:2.433 |
| Color Gamut(1931 xy) | REC709:98.2% DCI P3:95.22% BT2020:88.99% | REC709:100% DCI P3:99.23% BT2020:92.47% |
| Color Temperature(Avg) | Movie:6428 Standard:9102 Vivid:15757 | Movie:6485 Standard:10334 Vivid:17862 |
| Contrast Native(W/o LD) | 4235:1 | 7211:1 |
| Contrast Dynamic(W/LD) | 6298057:1 | 241192:1 |
Summary：TCL全白场亮度约700nits但Peaking亮度高；color accuracy/gamma好；BT2020色域88.99%低于海信；native对比度差但dynamic对比度因小OD高LD分区优于85UR9S。

## Slide 7 - PQ - TCL 85X11L HDR EOTF
TCL在10%窗口下EOTF比较准确，APL10窗口下EOTF存在较大波动，判断做了窗口识别但不准确。

## Slide 8 - PQ - Peaking Brightness
TCL在1-5%小窗口Peaking亮度接近10000nits；全白场及25%以上大面积窗口海信亮度高；TCL Real scene亮度好。
| 窗口 | 85UR9S | TCL 85X11L |
| Hallway Lights(~1950) | 2095 | 1200 |
| Yellow Skyscraper(~700) | 1492 | 670 |
| Landscape Pool(~300) | 597 | 495 |
| Win 1% | 4642 | 8366 |
| Win 2% | 5297 | 9622 |
| Win 5% | 5928 | 8841 |
| Win 10% | 4512 | 5845 |
| Win 25% | 3736 | 2711 |
| Win 50% | 2608 | 1440 |
| Win 100% | 1372 | 735 |

## Slide 9 - PQ - 亮场景对比
海信85UR9S RGB mini全白场亮度比TCL高，亮场景下85UR9S主观亮度高、色彩透亮、层次感强、细节丰富。

## Slide 10 - PQ - 局部高亮场景对比
TCL在小窗口信号Peaking亮度非常高，局部高亮实际场景中亮度高、主观较刺眼；吊灯等场景Peaking亮度高，对比度优于85UR9S。

## Slide 11 - PQ - 色彩对比
TCL色彩亮度低于85UR9S，红色表现为暗红，色彩层次感不如85UR9S透亮；肤色表现海信更自然真实。

## Slide 12 - PQ - 暗场景对比
TCL OD3、14400分区，LD控制优势，暗场景表现好；播放权游TCL对比度/Blooming表现好，海信暗场偏亮/Blooming明显；播放星空TCL同样有Blooming但OD小分区多，问题不明显。

## Slide 13 - PQ - 模组面板对比
TCL LD off时屏幕白团漏光严重，海信比较好；TCL LD High时光晕比较小。

## Slide 14 - PQ - Motion对比
25p@60Hz TCL未处理，海信比较好；TCL存在顿挫，海信未明显顿挫；预计影响Rtings得分+0.03分。

## Slide 15 - PQ - 对比度测试
| | TCL 85X11L | 85U85SUA02 |
| Test Date | 4/2/2026 | 4/2/2026 |
| Condition LD=Off W1 | 288 | 362 |
| Condition LD=Off W2 | 279 | 376 |
| B1(右上) | 0.0759 | 0.0447 |
| B2(右下) | 0.0613 | 0.0636 |
| B3(左上) | 0.0767 | 0.0463 |
| B4(左下) | 0.0539 | 0.0501 |
| 白场平均 | 283.5 | 369 |
| 黑场平均 | 0.06695 | 0.051175 |
| Native对比度 | 4235 | 7211 |
| Condition LD=High W1 | 2244 | 875 |
| Condition LD=High W2 | 2165 | 946 |
| B1 | 0.004 | 0.0043 |
| B2 | 0.003 | 0.0035 |
| B3 | 0.003 | 0.0036 |
| B4 | 0.004 | 0.0037 |
| 白场平均 | 2204.5 | 910.5 |
| 黑场平均 | 0.0035 | 0.003775 |
| Dynamic对比度 | 629857 | 241192 |

## Slide 16 - 4. ME Design--Carton Solution
| Items | TCL 85X11L | Hisense 85UR9SG |
| Product Size(w/ Stand) | 74.0"x45.3"x15.0" | 74.6"x44.1"x14.2" |
| Product Size(w/o Stand) | 74.0"x43.5"x0.8" | 74.6"x43.0"x1.9" |
| Net Weight(w/ Stand) | 116.00lbs | 114.6lbs |
| Net Weight(w/o Stand) | 112.90lbs | 103.6lbs |
| Package Size | 81.10"x50.70"x11.50" | 81.1"x49.6"x7.4" |
| Container Load 40H | 39(堆码一层) | 126 |
| Shipping weight | 168.20lbs | 148.2lbs |
| Carton Material | 黄皮箱 | 单面贴彩箱 |
| Open box design | 叠盖箱 | 叠盖箱 |
| Corner protect | 一根 | 无 |
| Screen protect board | 蜂窝板(粘EPE条)+日字EPE | 蜂窝板 |
| Screen cover覆膜 | 有 | 有 |
| Screen protection tape | 四边粘贴 | 四边粘贴 |
| Anti-crumb screen cover | 有 | 有 |
| Layers stack | 1 | 4 |
| 前壳材质 | 金属下前壳 | 金属下前壳 |
| 后壳样式 | 塑料大后壳 | 塑料大后壳 |
Summary：TCL纸箱标识只堆码一层，海信支持堆码4层，海信海运装柜量比竞品高223%。

## Slide 17 - 4. ME Design--Insider Foam
竞品采用上下两侧EPS，正面蜂窝板(粘EPE条)+日字EPE，背面蜂窝板(粘EPE条)+日字EPE，下部EPE条，两侧护角，包装复杂；海信采用上下两侧EPS，顶屏蜂窝板，下部EPE条。

## Slide 18 - 4. ME Design--ID details
竞品前出音金属下前壳，一体平整塑料后壳，双腿单跨距、高度不可调底座，整机厚度(含前壳)24.7mm，预装导线槽支架；生产组装地：墨西哥。

## Slide 19 - 4. ME Design—Stand & Backcover
竞品双腿单跨距底座，一体压铸底座，间距1.7m需长电视柜；底座高度不可调但后壳有高度可调螺钉孔定位孔，安装后上部螺钉孔可见影响美观；平整塑料大后壳主要通过双面胶带粘贴固定，简单但维修困难。

## Slide 20 - 4. ME Design--Accessories
遥控器正面金属装饰面板带背光，侧面3个按钮可调背光亮度和图像模式；电源线长1.8m线径2x18AWG 300V品型尾美二插；竞品底座6颗螺钉安装简单，海信中间立柱底座12颗螺钉。

## Slide 21 - 5. HW Design--Layer out
竞品两个主声道一个中置两个环绕两个重低音；竞品电源板分两部分，第一块滤波第二块变压。

## Slide 22 - 5. HW Design--Mainboard and Power board
| Items | TCL 85X11L | Hisense 85UR9S |
| Mainboard PCB size | 260x240x1.6mm | 291x170x1.6mm |
| Powerboard PCB size | 350x330x1.6 460x300x1.6 | 400x260x1.6mm |
| Localdimming units(BLU) | 170x75x1.6 | 285x250x1.6mm |
| TCON | 170x75x1.6 | 178x114x1.6mm |
| FRC | / | / |
| SOC | MT9655 | MT9655 |
| Power Guide | $125 | $69 |
| Max power in full white | 540W | 345W |
| SOC Heatsink size | 195x130x3mm | 231x127x3mm |
| DDR | 2.5GB(软件读取) | 4GB |
| EMMC/NAND | 64GB | 32GB |
| WiFi | MT7920 | MT7921 |
| AMP | 5815 | NTP8928 |
Summary：TCL整机厚度24.7mm使用标准电源线。

## Slide 23 - 5. HW Design--Power Cord
TCL整机厚度24.7mm仍使用C14标准电源接口，后壳突出9mm，用户可便捷找到通用电源线；海信使用C10接口电源，Reddit和渠道网评用户投诉电源线丢失或需延长时无法找到适配电源线，严重影响用户体验。

## Slide 24 - 5. HW Design--Speaker
竞品扬声器39W(3*3W+2*10W+2*5W)，Main(mid)277x30x12mm Sub410x335x7mm Sur270x40x7mm；海信90W(2*15W+20W+2*10W+2*10W) Main270x150x20mm Sur160x100x10mm Sub460x220x20mm Sky160x100x10mm。X11L频响曲线不平整分频点200左右，低音下潜不足高频延展不足，rtings最大声压级82.5实验室78.4。

## Slide 25 - 6. LCM--Overview
| Items | TCL 85X11L | Hisense 85UR9S |
| Open cell Model No. | CSOT ST846AD07-2 | HKC PT850GT04-9 |
| Low reflection | 超低反LR | 超低反LR |
| Native Refresh rate | 144Hz | 180Hz |
| 白场最大亮度 | 725nits | 1193nits |
| 白场最大功率 | 540W | 345W |
| Number of LEDs | 14400=45*40 LEDs*8分板 一灯一区 | 7920=660 LEDs*12分板 6灯一区共1320分区 |
| LED type | 1225芯片 18V RGB 3色芯片 3030 POB | |
| Size of Lens | 带透镜 d=5.6mm | POB无透镜 |
| LCM back cover thickness | 1.2mm | 1.0mm |
| 背板抗扭强度 | 良好 | 良好 |
| Film Design | 1*贴合膜CPP | 1*贴合膜CPP |
| Reflection Film | 热压成型立体反射片 | 灯板来料粘贴0.188mm反射片 |
| Plastic Bracket支架数量 | 无扩散板支架 热压成型立体反射片支撑膜片 | 42个支架螺钉固定 |
| Diffuse board | 无扩散板 POP均光膜0.3mm | 2.3mm普通扩散板 |
| High Color Gamut Film | SDQ膜 | RGB方案无QD膜 |
| OD(mm) | OD3.5 | OD12 |
备注：美研购买TCL 85X11L样机未拆机已退机，模组方案信息参考总部TCP分析内销TCL 85X11L样机。

## Slide 26 - 6. LCM--Backlight design
TCL光学方案技术亮点：使用热压成型立体反射片，背胶粘贴灯板上，每块灯板422个成型OD柱子支撑膜片，无扩散板支架但成本高，相比85UX常规反射片成本高约2.7倍；无扩散板，LED灯带透镜，使用二层贴合膜POP均光，立体反射片足够多OD柱子支撑膜片，进一步减小背光厚度。

## Slide 27 - 7. SW Design--Performance
TCL STR开关机进入Launcher和HDMI信号源速度较慢2.5s(最低2s)；网络应用快进快退较慢2.2-2.8s(最低2s)。TCL HDMI响应优势：ARC连接信号正常后1秒输出声音(海信5.5秒)，HDMI返回主页0.7秒(海信1.2秒)。对比海信3G DRR 9655GTV平台，高负载相同场景播放Youtube 4K Live，X11L无掉帧，海信掉帧严重性能不足。

## Slide 28 - 7. SW Design--Feature
TCL 85X11L作为Google TV机型，MT9655平台，2.5GB内存(软件读取)与Android 14系统，支持Google Gemini智能交互，配合SQD Mini LED显示技术，实现高亮度高对比度及AI画质优化。

## Slide 29 - 7. SW Design--Feature 隐私安全
TCL新增Privacy Protect Certification功能，用户可查看已认证信息，提升隐私安全透明度与信任度。海信需优化构建类似隐私管理能力，支持认证状态查询，扩展查看设备隐私权限及数据使用情况。

## Slide 30 - 7. SW Design--Feature Gemini
Google在2026年4月对Google TV中Gemini能力升级，引入可视化AI回答、Deep Dive深度讲解、体育快报；TCL 85X11L于TCP分析期间升级。海信MT9655平台TV已完成Gemini升级，由于Gemini依赖Android 14，需尽快推动MT9618完成大版本升级扩展更多机型Gemini支持。

## Slide 31 - 7. SW Design--Feature Game Bar
TCL 85X11L Game bar顶部状态栏新增"FreeSync Premium Pro"标识，增加高级感。VRR最高支持4K@144Hz 2K@288Hz，低于85UR9S的4K@180Hz 2K@330Hz。

## Slide 32 - 7. SW Design—TCL tv+
TCL Live TV Channel各时间段节目展示采用网格化布局，简洁清晰(海信和SS采用时间轴，信息呈现杂乱)；左侧边栏支持分类区分，用户可快速定位Favorites等内容(海信Channel左侧布局缺乏分类)；TCL TV+除Live TV外还提供"Your TV+"模块支持点播无广告，体验灵活(海信Channel仅Live Channels缺少点播)。

## Slide 33 - 8. Summary & Actions
| No. | TCP solutions and learn | Sections | Owner |
| 1 | TCL暗场对比度高、Blooming非常轻微。 | PQ | 沈海杰 |
| 2 | TCL在小窗口Peaking亮度很高，并在实际场景中有效果，值得借鉴。 | PQ | 沈海杰 |
| 3 | TCL采用OD3背光设计，可以实现较小blooming并提高暗场对比度，值得借鉴。 | LCM | 张登印 |
| 4 | TCL采用立体反射片和无扩散板设计，建议论证竞品方案的优势和可行性，建立技术储备。 | LCM | 张登印 |
| 5 | TCL可视角较好，测试浮白现象明显好于海信85UR9S，中高端面板需要规划提高可视角。 | 面板规划 | 李威 |
| 6 | TCL整机薄，电源线仍使用C14标准接口，海信使用C10接口电源线，用户无法找到和买到适配电源线，严重影响使用体验。 | HW | 胡贵红 |
| 7 | TCL建立了完善隐私管理体系，海信需梳理现有隐私安全认证，增加隐私安全展示功能，支持认证状态查询。 | SW | 宋媛媛、周玲玉 |
| 8 | TCL Game bar顶部状态栏新增了"FreeSync Premium Pro"标识，增加了高级感。 | SW | 宋媛媛、周玲玉 |
| 9 | 在高负载相同场景下播放Youtube 4K Live节目，TCL无掉帧，海信3G DRR 9655GTV平台掉帧严重，性能明显不足，需要分析优化。 | SW | 于清晓 |
| 10 | TCL Live TV Channel在各时间段的节目展示上采用网格化布局，整体更加简洁清晰。 | VIDAA | Henry Shang、Simon Zhao |
| 11 | TCL左侧边栏支持分类区分，用户可以快速定位到Favorites（收藏）等内容，海信没有区分左侧边框。 | VIDAA | Henry Shang、Simon Zhao |
| 12 | TCL除了Live TV外，还提供"Your TV+"模块，支持用户进行点播观看。 | VIDAA | Henry Shang、Simon Zhao |

## Slide 34 - Thanks
Thanks