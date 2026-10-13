# 判断经验库

> 每条都来自真实站点的实测教训，不是推测。新增经验请注明来源站点。
> 初始内容来自 `docs/LLM自动适配器技术方案.md` §9.13 / §11.4 / §12.4 的沉淀。

---

## 一、选产品链接选择器

### 1.1 看纯度，不要只看命中数 ★核心

品牌站的导航栏、页脚常用宽泛结构（`li a[href]`），命中数天然比真实产品选择器高，
但绝大多数是分类页/其它品类/导航链接。

实测对比（来源：Hisense US / 秘鲁 Hisense）：

| 站点 | 泛选择器 | 产品选择器 | 结果 |
|---|---|---|---|
| Hisense US | `li a[href]` 命中 66~94，纯度 0.42 | `a[href*='/product-page/']` 命中 29，纯度 **0.97** | 产品选择器胜出 |
| 秘鲁 Hisense | `li a[href]` 纯度 0.56 | `a[href*='/tv/']` 纯度 **0.69** | 产品选择器胜出 |

`probe.py --entry` 的 `link_selector_ranking` 已按纯度排序，直接看 `model_like_ratio`。

### 1.2 宽泛路径在"全站产品共用路径"的站会混入非电视

| 站点 | 坑 | 解法 |
|---|---|---|
| Sony JP | `/products/` 是全站共用，会混进耳机 WH-1000XM6、相机 ILCE-7RM6、手机 | 收窄到 `a[href*='/bravia/products/']` |
| REGZA JP | 站内既有 `/tv/lineup/` 也有 `/bd-dvd/lineup/`（蓝光录像机） | 收窄到 `a[href*='/tv/lineup/']` |

**规律**：优先用"电视/品牌专属的精确路径"，靠纯度排序自然胜出。

### 1.3 型号 URL 的判据

`_looks_like_model_url` 要求末段含"字母紧邻 ≥2 位数字"（如 `75u7sg`、`65OLED759`）。
这能排掉 `4k-uled`、`4k-uhd`、`smart-tv-platforms` 这类只有孤立单数字的导航词。

---

## 二、分页与动态加载

### 2.1 只有"编号页码"是可靠分页信号 ★核心坑

| 信号 | 可靠性 | 处理 |
|---|---|---|
| 编号页码（`aria-label='Show page N of results'`） | **可靠** | 判为分页站，配 `snippet_ref` |
| 孤立的"下一页 / next"按钮，无编号页码 | **不可靠** | 极可能是轮播/推荐区按钮，**忽略** |

翻车案例（Sony BRAVIA JP）：静态列全的站，推荐区轮播有 next 按钮 → 被误判成分页 →
LLM 加了 `numbered_pages_generic` → 实抓时点错按钮把页面导航走了 → **发现 0~1 个型号**。
去掉分页配置后立刻 8/8。

`spec_probe.build_probe_report` 已修正此判定，但**智能体仍要自己把关**：
`load_more_hint=none` 时无论 `pager.has_next_button` 真假，都不要写 `discover.paginate`。

### 2.2 替换式分页 vs 追加式分页

| 类型 | 表现 | 通用片段能否处理 |
|---|---|---|
| 追加式 | 点击后链接数增长 | 能 |
| **替换式** | 点击后换掉当前一页，链接数**不增长**（Philips CA / Next.js） | 能，但依赖片段内部重扫页码 |

替换式的识别不能靠"点击后链接是否增长"（不增长），只能靠**检测到编号页码控件**。
`_detect_pager` 会汇报 `paginate_replace`。

### 2.3 分页站的找全率口径

**不能用首屏 HTML 卡分**，要用引擎执行分页片段后的实际发现数。
Philips CA 首屏只有第 1 页 12 个型号，用首屏算就是 48%，实际翻完是 25/25 = 100%。

---

## 三、JS 片段库

### 3.1 片段选型优先级

1. `numbered_pages_generic` — 编号页码型首选，已鲁棒化（每翻页重扫页码 + visited 队列翻到尽头）
2. `philips_paginate` — 站点专用，仅在通用片段失效时用

### 3.2 三层转义坑 ★血泪教训

JS 片段嵌在 Python raw string 里，`new RegExp('...')` 的反斜杠要按
**Python 字面 → JS 字符串 → 正则** 三层数清。

历史 bug：`new RegExp('\\\\bpage\\\\s+')` 四个反斜杠在 JS 里求值成 `\\b`
（匹配**字面反斜杠**），页码按钮永远匹配不到，翻页全失败，表现为"语法对但运行时正则失效"。
正确写法是双反斜杠 `'\\b'`。

**改片段后必须**：`node --check` + 针对真实 `aria-label` 做匹配自测。

---

## 四、规格页解析

### 4.1 选档规律

| 页面特征 | `extract_order` |
|---|---|
| 有内嵌 JSON 承载完整规格（`"specification":{...csChapter...}`） | `["embedded_json", "generic_spec_js"]` |
| 规格在 DOM 表格 / dl / 键值对里 | `["generic_spec_js"]` |

`generic_spec_js` 是通用多策略抽取，**建议始终放在最后当兜底**。

### 4.1b model_url_regex 不要硬依赖 URL 尾斜杠 ★

引擎发现时对每个 href 先过 `clean_url()`，它会**去掉查询串、片段和末尾的一个斜杠**。
所以：

- 若型号在 URL **最末段**（如 `/tv/.../55U8N`），`clean_url` 后没有尾斜杠，
  正则**不能**写成 `...(\w+)/$` 强要求结尾 `/`，否则全部匹配失败（发现 0 个）。
- 若型号**后面还有段**（如 Philips `/c-p/55OLED760_12/overview/`），
  `clean_url` 去掉最后一个 `/` 后仍是 `.../55OLED760_12/overview`，
  正则 `/c-p/([A-Za-z0-9]+)_[A-Za-z0-9]+/` 里的 `_..../` 能正常匹配（型号非末段）。

判断方法：拿 `probe.py --entry` 的 `sample_product_hrefs`，先在脑子里对它做
"去查询串 + 去一个尾斜杠"，再套正则。发现 0 个但选择器命中不为 0 时，**首先怀疑
正则尾部的 `/`**。

### 4.2 内嵌 JSON 的 require_field 坑

`chapters_field` 同时被当作 `require_field`——只接受**含该字段**的根对象。
Philips 页面里有多个 `specification` 键，只有含 `csChapter` 的那个才是规格数据。
不设这个约束会命中同名但无规格的对象，抽出 0 行。

### 4.3 品牌官网价格常需 JS 渲染后才进 JSON-LD（Samsung UK 实测）★

Samsung UK `/uk/tvs/all-tvs/` 的 JSON-LD ItemList 48 条，但**纯 HTTP（urllib+代理）
抓到的 ItemList 不含 `offers.price`**——价格字段是客户端 JS 注入后才出现的。
同一 URL 用 Playwright `domcontentloaded + 滚动` 后再读 `page.content()`，
48/48 条都带 `offers.{price, priceCurrency, availability}`。

规律：品牌官网列表页若"产品有了但价格恒为空"，先怀疑**价格靠 JS 渲染注入**，
别误判成站点不给价。验证方法：同一 URL 分别用 HTTP 和 Playwright 抓，对比
JSON-LD `offers` 字段是否存在。补价用 Playwright 重抓即可，不必逐个 PDP。

匹配入库用**规范化 URL 精匹配**（去尾 `/` + 小写）最稳：套组 URL
（`<TV_CODE>uxxu-hw-...-f-<套组码>/`）与单品 URL 不同，但 DB 入库时存的就是
套组/单品各自的真实 URL，逐一对得上。退化方案：按 URL 末尾 `*xxu` 产品码 +
bundle/size 消歧。另注意 `availability=OutOfStock` 的商品**仍带 price**（≠0），
`in_stock` 要按 availability 分流，不能拿"有价"反推在库。

---

## 五、喂 LLM 的 HTML 预处理

### 5.1 整页压缩会帮倒忙（若用于生成 CSS 选择器）

实测（来源：§9.10 对比实验）：

| 喂法 | 结果 |
|---|---|
| 原始 HTML（截断 30K） | 94 分 PASS，2 轮收敛 |
| `prune_html` 旧正则版压缩后再喂 | **0 分 FAIL** — 压缩破坏 `id`/`class`/结构线索，LLM 只能生成 `h1`/`.price` 这类通用猜测 |

**正确做法**：压缩版当"地图"定位目标区域，**原始 DOM 片段当"施工面"**生成选择器。

### 5.2 prune_html 已升级为 lxml 去重版

重复卡片去重（同 `tag + class + 文本hash` 只留第一个）后：
112K 字符 → **418 字符**，且页尾关键元素 4/4 保留（旧正则版截断 30K 时 0/4）。
列表页 N 个同构产品卡，喂 LLM 留 1 个样例就够。

---

## 六、诊断纪律

### 6.1 每轮只动一个变量

换档 / 改选择器 / 加交互三类改动**不要同时做**，否则分不清哪个起作用。
§9.13 那次找全率 48%→100% 的排查，正是靠"隔离片段这个单一变量（写死
`numbered_pages_generic`）"才定位到真实根因。

### 6.2 初判往往是错的，要拿决定性证据

同一次排查中，初判是"maxPage 只首屏探测一次翻不到尽头"，但证据推翻了它：
首屏其实有 122 个链接、去重后 12 个型号，两种正则提取都是 12 → 排除正则问题 →
最终定位到 `pageBtn` 正则的转义 bug。

**要找的是"能排除其它可能"的证据，不是"符合猜想"的证据。**

### 6.3 PowerShell 管道会吞 stderr

中文异常/traceback 不显示，表现为"进程静默退出"。排查必须加 `2>&1`。
另：本仓库 shell 会话中文可能显示为乱码（代码页问题），不影响文件实际内容。

---

## 七、判定"该手写适配器"的信号

出现以下任一，**及时止损**，不要硬凑（来源：Hisense US 实测）：

- 型号 slug 毫无规律，通用正则无法可靠框住（`75u7sg` / `tv43qd40r` / `40qd40r` 混用）
- Load More 按钮通用点击候选点不开
- 需要多级页面（总览→系列→型号）才能拿到型号 —— 当前引擎无此能力
- 需要调用带动态签名的接口

记入 `cases.jsonl` 标 `verdict: "needs_handwritten"`，并写清**缺哪个引擎档位**——
这是 P0 排期的直接输入。

---

## 八、当前已知引擎缺口（撞上就记，别绕）

| 缺口 | 影响站点 | 状态 |
|---|---|---|
| ~~多级发现（总览→系列→型号）~~ | 松下、夏普 | ✅ **已实现** `dom_anchor_two_level`（2026-09-16），见 playbook/multilevel.md |
| ~~`xhr_api` 接口发现~~ | TCL、Samsung、LG | ✅ **已实现** `xhr_api`（2026-09-16），见 playbook/xhr_api.md |
| ~~`query_param` 分页（`?firstResult=N`）~~ | LG | ✅ **已实现** `paginate.type=query_param`（2026-09-16），见 playbook/numbered_paginate.md |
| 点击 tab 展开才出规格 | TCL 类 SPA | 无此解析档位（P1） |

> **P0 覆盖面缺口已全部清空**（多级 / xhr_api / query_param 均落地）。
> 剩余为 P1 生产化（库表/health/审核门）与 P2 合规，见 docs/任务表与验收标准.md。

---

## 九、SPEC 线小样本检验经验（2026-09-25 新增 ★）

### 9.1 检验方法

SPEC 线检验 6 项：
1. **series/rows 计数** — 与声明的 series/rows 精确匹配
2. **字段完整性** — item_ja 100% 非空，values_json 100% 有效 JSON（0 坏 JSON）
3. **category 覆盖** — 画质/尺寸/面板/连接/音频等核心品类命中
4. **row_order 连续性** — 检查断号和重复
5. **captured_week 合法性** — 全库仅合法 ISO 周（YYYY-Www 格式）
6. **item_zh 翻译覆盖率** — jp 线 97~100%，英文站近 0%（流程覆盖差异非损坏）

### 9.2 ★ tcl_jp row_order 结构性重复

tcl_jp 有 28/222 series 存在 row_order 重复（每个 order 值出现 2 次，distinct 后 1..N 连续无断号）。
这是**源站结构特性**（同一规格项双语/双值拆成两行共享 order），非入库损坏。

**处理建议**：若下游依赖 row_order 唯一，对 tcl_jp 加 `(series_id, row_order)` 去重或改用 `(row_order, item_ja)` 联合排序。

### 9.3 ★ item_zh 翻译覆盖两极分化

- jp 品牌（regza_jp/sony_jp/tcl_jp/sharp_jp/panasonic_jp/hisense_jp）：97~100% 翻译覆盖
- uk/us/ca/mx 等英文站：近 0%（item_ja 列对英文站实际存的是英文原文标题）

**注意**：item_ja 列对 uk/us 站存的是英文原文（如 "Screen Size"/"PRICE"），对 jp 站存日文——这是"源语言标题"列的既有设计，非字段名误导。若产品需要中文规范名，应对英文站补跑翻译流程。

### 9.4 ★ SPEC 数据落点必须写主库

SPEC 数据（spec_series + spec_row）必须全部写 `data/overseas.db`，不能写 `data/mx/overseas_mx.db`。详见运维手册「SPEC 线 DB 落点坑」章节。

---

## 十、LangGraph全自动抓取 + DeepResearch报告（2026-09-28 新增 ★）

### 10.1 探索完成后的自动化流程

```
探索接入(人工Skill) → 适配器校准(人工Skill) → 【LangGraph全量抓取(自动)】 → 【DeepResearch报告(自动)】
                                                  FLOW分支                   REPORT分支
```

**LangGraph引擎**（`overseas/flow/`）：7节点StateGraph，SPEC并行度=2，RETAIL并行度=3，每站子进程隔离SQLite，90/600秒超时，品牌熔断+断点续跑。

**DeepResearch报告**（`overseas/report/`）：6-Agent协作（ChiefArchitect→DataScout→DataAnalyst→CompetitorAnalyst→ReportWriter→CriticMaster），所有结论锚定DB真实数据+信源ID，CriticMaster对抗审核检测幻觉，质量评分8.0/10。

### 10.2 新站探索时的防幻觉要点

1. **country字段必须英文大写**：adapter.py的country字段若是中文（如"墨西哥"/"日本"）会导致所有区域分类逻辑失效。新站接入时**必须检查country字段**。
2. **区域分类中英文兼容**：`LINE_COUNTRIES`集合同时包含英文("MEXICO")和中文("墨西哥")，用`countries_upper`大写匹配。
3. **SPEC站product回填**：SPEC站的product表可从`spec_series.models`静态回填，无需联网。size用统一正则`(\d{2,3})`首匹配。

### 10.3 新站探索后的沉淀检查清单

每次新站接入完成，**必须**：
- [ ] `spec/cases.jsonl` 追加一条（格式见文件头注释）
- [ ] `spec/reference.md` 有新规律/坑则更新
- [ ] 有新结构型 → `spec/playbook/` 加套路
- [ ] `spec/selfcheck.py` 跑一次
- [ ] 爬取进度.csv 更新状态+DB数据
- [ ] 如果是SPEC站 → 检查country字段是否英文

---

## 11. 卖点采集(Selling Points)经验（2026-09-28 新增 ★ 学习自tvcraw-main）

### 11.1 auto_schema.py经验优先匹配器

新站探索**第一步必须是跑auto_schema.py**，不要直接跑probe：
```bash
python auto_schema.py --entry "<URL>" --code <code> --out schema.json
```
命中相似站→秒出schema→沙箱验证→验证通过追加case标注"复用XXX"，**全程未开浏览器**。
验证失败→加`--force-probe`重走探测步骤。

### 11.2 4级匹配优先级

| 优先级 | 匹配条件 | 分数 | 示例 |
|--------|----------|------|------|
| 1 | 精确code匹配 | 100 | 同站再次跑 |
| 2 | 同host匹配 | 90 | samsung.com的uk/ca/cl/co/mx互相复用 |
| 3 | 同品牌不同region | 70+host相似度 | hisense_bo复用hisense_pe |
| 4 | host含品牌名 | 60+host相似度 | samsung.com.bo复用samsung.com |

### 11.3 已验证的复用模式

| 品牌 | 复用源 | 复用到的站 | 机制 |
|------|--------|-----------|------|
| Samsung | samsung_uk | ca/cl/co/mx/pe/ec/bo | 同host(samsung.com) pdd32 accordion |
| TCL | tcl_jp | mx/uk/ar/pe | 同host(tcl.com) Knockout SPA |
| Hisense | hisense_pe | bo/co | 同品牌 dt/dd模式 |
| LG | lg_ca | uk/cl/co/mx/pe | 同host(lg.com) c-compare-selling |
| Philips | philips_ca | de | 同host 内嵌JSON csChapter |

### 11.4 卖点探测3种模式

probe_sp.py(自包含Playwright版)支持3种独立探测：
- `--entry`：探入口页（产品链接发现层）
- `--model`：探型号页（规格结构层）
- `--sp`：探型号页（卖点结构层 — hero/banner/轮播/视频/功能区块/section语义块）

### 11.5 卖点6种Extract方法

| 方法 | 识别特征 | 代表站 |
|------|----------|--------|
| `section_blocks` | `<section>`/`<article>` 含卖点词 | Sony JP/UK |
| `feature_blocks` | div class含feature/highlight | 通用 |
| `hero_block` | 顶部大图区 | 通用 |
| `carousel_images` | 轮播/画廊组件 | Sony JP |
| `interactive_tabs` | SPA tab切换 | TCL |
| `generic_sp_js` | 兜底：语义启发式 | 各站fallback |

### 11.6 卖点cases.jsonl格式

验证通过后在cases.jsonl追加`sp_solution`字段：
```json
{"code":"sony_jp","sp_solution":{"extract_order":["section_blocks","generic_sp_js"],
"container":"section","title":"h2,h3","description":"p","image":"img",
"video":"video,iframe"},"sp_points":145,
"note":"卖点在产品主页section语义区块，含hero大图和宣传视频"}
```

### 11.7 卖点DB落库与导出（2026-09-28 整合 ★ 借鉴 tvcraw-main）

**完整链路**：探测(--sp) → Schema → 引擎抓取 → DB落库 → 导出(Excel/MD)

#### DB 表

| 表 | 用途 |
|---|---|
| `selling_point` | 主表：brand/series/model/point_type/title/description/image_urls/video_urls/refined_text/captured_week |
| `selling_point_status` | 系列级状态：success/empty/failed + point_count + llm_refined |
| `selling_point_md_summary` | MD导出的200字LLM摘要缓存（自动创建） |

**设计要点**：
- `captured_week` 按 ISO 周快照，与 `spec_row` 对齐，可交叉查询
- `refined_text` 独立字段，LLM 可异步回填（`db.update_selling_point_refined()`）
- `ON CONFLICT(brand, series, model, title, captured_week)` 去重，重跑不重复

#### 导出命令

```powershell
# Excel：品牌|系列|机型|类型|标题|描述|图片|视频|LLM摘要
py -3.12 -m overseas.cli sp-export --site sony_jp --format xlsx

# CSV：同上
py -3.12 -m overseas.cli sp-export --site sony_jp --format csv

# Markdown：每机型一节(精炼卖点列表+200字LLM摘要)
py -3.12 -m overseas.cli sp-export --site sony_jp --format md
py -3.12 -m overseas.cli sp-export --site sony_jp --format md --no-llm  # 跳过LLM
```

#### 与 SPEC 采集的独立关系

| 维度 | SPEC | Selling Points |
|------|------|----------------|
| 探测 | `--model` | `--sp` |
| Schema | `solution` 字段 | `sp_solution` 字段（同一cases.jsonl行） |
| DB表 | `spec_row` | `selling_point` |
| 导出 | `spec-export` | `sp-export` |
| 周度快照 | ✅ `captured_week` | ✅ `captured_week`（同ISO周） |

---

## 12. SPEC导出空白诊断与修复经验（2026-09-28 ★ 实战修复）

### 12.1 三种导致SPEC导出空白的bug

| Bug | 现象 | 根因 | 修复位置 |
|-----|------|------|----------|
| **品牌统一周** | 部分系列全空白 | `_collect`用`entry_scope["week"]`(W40)统一取所有系列，但部分系列只有W38数据 | `spec_export.py` `_collect()` 按系列各自取`MAX(captured_week)`，entry_scope.week无数据时回退 |
| **audit run无success清空** | tcl_jp/lg_ca导出0行 | 最新audit run还在running(0个success)，`series_ids`为空导致`series_rows=[]` | `series_ids`为空但有`model_norms`时按型号过滤；`model_norms`也为空时回退全量 |
| **URL哈希key** | tcl_jp填充率28.9% | `values_json`的key是完整URL(`https://www.tcl.com/.../product_spec_copy.BASE64.json`)而非型号名 | 新增`_extract_model_from_url_key()`，从URL末尾base64段解码提取型号 |

### 12.2 tcl_jp URL key的base64提取法

tcl_jp的`values_json` key格式：`https://www.tcl.com/content/brandsite/jp/ja/tvs/c635/jcr:content/.../product_spec_copy.L2NvbnRlbnQ...L2M2MzUvNjVjNjM1.json`

- 末尾`L2NvbnRlbnQ...`是base64编码的路径
- base64解码后：`/content/brandsite-product/jp/ja/tvs/c635/65c635`
- 末尾段`65c635`即型号(归一化后匹配`65C635`)
- 影响系列：C635/C645/C646/C745/C845/C955/P635/P636/P63H/P745/S5400/S5402/S54H(共13个)

### 12.3 如何区分"真空白"和"bug空白"

| 检查项 | 方法 | 判定 |
|--------|------|------|
| DB有值? | `SELECT COUNT(*) FROM spec_row WHERE values_json IS NOT NULL AND values_json != '{}'` | 100%有值=不是DB问题 |
| key格式? | 检查`values_json`的key是否以`http`开头 | URL key=需要`_extract_model_from_url_key` |
| 系列周分布 | `SELECT captured_week, COUNT(*) FROM spec_row WHERE series_id=? GROUP BY captured_week` | 不同系列不同周=需要按系列取周 |
| audit run状态 | `SELECT run_id, COUNT(*) FROM spec_series_status WHERE status='success'` | 0 success=需要回退全量 |
| 系列间spec_item交集率 | 不同系列的`item_ja`集合交集 | <50%=合并空白是**正常结构**，非bug |

### 12.4 修复后填充率基准（单品牌导出）

| 品牌 | 修复前 | 修复后 | 说明 |
|------|--------|--------|------|
| hisense_ca | 0行 | 85行/71% | 按系列取周修复 |
| tcl_jp | 0行→168行/28.9% | 168行/45.6% | URL key base64提取修复 |
| lg_ca | 0行 | 115行/63.3% | 无success回退全量修复 |
| sony_jp | 85行/98.9% | 85行/98.9% | 无变化(本来就对) |

### 12.5 合并到国家Sheet后填充率低是正常现象

不同品牌的型号列不同(Hisense的32A4NF和Samsung的QN90D完全不同)，横排合并后交叉位置必然空白。
**单品牌文件填充率才是正确指标**（71-99%为正常，低于50%需检查key格式）。

---

## 13. 价格导出表头按线路区分（2026-09-28 ★ 实战修复）

### 13.1 问题：非日本线显示了日本8家店铺列

导出脚本用`build_columns()`不传spec参数→默认日本kakaku 8店铺列（爱电王/友都八喜/山田电机/BIC CAMERA/K's Denki/Joshin/Nojima/Amazon），导致加拿大/美国/欧洲线显示不存在的日本店铺名且全空白。

### 13.2 修复：日本线multi_shop，其他线single_shop

| 线路 | 模式 | 表头中间段 | 数据来源 |
|------|------|-----------|----------|
| 日本线(kakaku_jp) | multi_shop | 8家日本店铺+最安店铺 | `price_shop_snapshot`表(有8家店铺比价数据) |
| 其他所有线 | single_shop | 渠道+现价 | `price_snapshot`表(单一价格) |

### 13.3 DB数据分布（关键认知）

- `price_shop_snapshot`表**只有日本kakaku_jp有数据**（1441条，8家店铺）
- 其他260个站点全部0条`price_shop_snapshot`，价格只存在`price_snapshot`（单一价格）
- 原因：非日本线站点是品牌官网或单一电商，不是比价平台，只有一个渠道一个价格

### 13.4 修复后表头对照

**日本线（19列）**：所属区域|品牌|机型|尺寸|上市时间|货币|最低价|爱电王|友都八喜|山田电机|BIC CAMERA|K's Denki|Joshin|Nojima|Amazon|最安店铺|商品ID|商品链接|采集时间

**加拿大/美国/欧洲/南美/墨西哥/俄罗斯线（13列）**：所属区域|品牌|机型|尺寸|上市时间|货币|最低价|渠道|现价|最安店铺|商品ID|商品链接|采集时间
- 渠道列显示来源网站名（如"Amazon Canada"、"Leons"、"Best Buy US"）
- 现价=price_snapshot的单一价格

---

## 14. 网评导出列错位修复（2026-09-28 ★ 实战修复）

### 14.1 问题：图片/视频列显示错误数据

手动拼接Excel行数据时，SQL查询字段顺序与`REVIEW_COLUMNS`表头列错位：
- "图片数量"列显示的是评论时间（`2025-12-02T03:35:36`）
- "图片地址"列显示的是评论链接（`https://www.feefo.com/...`）
- 图片/视频URL完全看不到

### 14.2 根因与修复

**根因**：手动拼接`ws.append([...])`时列数和顺序与`REVIEW_COLUMNS`不对齐。

**修复**：使用`ReviewRecord`数据类 + `as_row()`方法，保证列与`COLUMNS`一一对应：
```python
rec = ReviewRecord(country=ct, brand=..., model=..., channel=..., ...)
ws.append([rg, ct, site_name] + rec.as_row())  # 前加3列: 区域/国家/站点
```

### 14.3 网评23列标准表头（修复后）

| 列号 | 列名 | 数据来源 |
|------|------|----------|
| 1-3 | 区域/国家/站点 | 导出时按区域填 |
| 4 | 所属国家 | ReviewRecord.country |
| 5 | 品牌 | product.brand |
| 6 | 型号 | product.model |
| 7 | 渠道 | site.name |
| 8 | 尺寸 | t_size_inch(product.size) |
| 9 | 网评分数 | review.rating |
| 10 | 网评标题 | review.title |
| 11 | 网评内容 | review.body |
| 12 | 翻译 | 翻译钩子(默认空) |
| 13 | 提炼优点 | AI钩子(默认空) |
| 14 | 提炼缺点 | AI钩子(默认空) |
| 15 | 赞同数 | review.helpful_count |
| 16 | 评论时间 | review.review_date |
| 17 | 评论链接 | review.review_url |
| **18** | **图片数量** | **review.image_count** |
| **19** | **图片地址** | **review.image_urls** |
| **20** | **是否有视频** | **"是"/"否"** |
| **21** | **视频地址** | **review.video_urls** |
| 22 | 商品ID | product.sku |
| 23 | 价格 | price_snapshot最新价 |

### 14.4 DB图片/视频数据分布

- 全库84,095条评论中3,981条有图片(4.7%)，77条有视频(0.1%)
- 有图片数据的站点：sony_uk(693)/falabella_cl(715)/samsung_uk(760)/canadiantire_ca(400)/bestbuy_us(506)/lg_us(497)/costco_us(114)/sony_ca(23)/abc_cl(38)/amazon_us(4)/alkosto_co(55)/oechsle_pe(61)
- 日本kakaku_jp：0条图片/0条视频（価格.com评论无图片功能）
- 导出后Excel中图片/视频数据与DB 100%匹配

---

## 15. 缺SPEC国家借用品牌官网SPEC（2026-09-28 ★ 改进）

### 15.1 问题：30个国家有价格/网评但无SPEC

SPEC来自品牌官网（如samsung_uk），价格/网评来自零售电商（如amazon_de）。
品牌未在所有国家建独立官网，导致这些国家只有价格/网评无SPEC。

### 15.2 借用规则：同大洲优先

缺SPEC的国家，从`product.brand`提取在售品牌，匹配已有SPEC的品牌官网：
1. **同大洲优先**：欧洲缺SPEC→借用samsung_uk/sony_uk；南美→借用samsung_bo/tcl_bo
2. **跨洲兜底**：南美无Sony SPEC→借用sony_ca（北美）
3. **品牌匹配**：brand_name.lower() 与 spec_code前缀(如samsung_uk→samsung)模糊匹配

### 15.3 借用SPEC站点映射（实测）

| 区域 | 缺SPEC国家 | 借用来源(优先同大洲) |
|------|-----------|---------------------|
| 欧洲(24国) | Germany/France/Italy/Spain等 | samsung_uk, sony_uk, hisense_ca, lg_ca, philips_ca, panasonic_jp, sharp_jp, tcl_bo |
| 南美(5国) | Ecuador/Peru/Guatemala/Panama/Bolivia | samsung_bo, tcl_bo, hisense_ca, lg_ca, sony_ca |
| 北美-墨西哥 | Mexico(电商站) | hisense_ca, lg_ca, samsung_ca, tcl_ca |

### 15.4 改进后数据对比

| 维度 | 改进前 | 改进后 |
|------|--------|--------|
| SPEC文件数 | 6个 | 38个(+32) |
| SPEC总行 | 3,419 | 22,237 |
| 有数据国家 | 38个 | 39个 |
| 总文件数 | 62个 | 94个 |

### 15.5 注意事项

- 借用SPEC的型号可能与该国实际在售型号不完全一致（如德国借samsung_uk，但UK和DE型号可能略有差异）
- 品牌标签标注`[借用xxx]`以便用户识别SPEC来源
- 优先接入品牌本国官网是更好的方案（如samsung_de/lg_fr等），但属于新站接入工作

---

## 16. Samsung SPEC 100% 抓取失败根因：captcha 误判（2026-09-28 ★★★）

### 16.1 现象

samsung_co/samsung_cl spec-crawl 全系列 `status=200 抓取失败`，
品牌熔断跳过所有系列。但手动 BrowserFetcher.page() 能正常拿到 114 条 spec。

### 16.2 根因

Samsung 页面前 8000 字符内嵌 `captcha` 脚本引用（grecaptcha），
`BlockDetector.check()` 匹配到 `captcha` 关键字 → `res.blocked=True, res.ok=False` →
crawl 代码 `if dom is None or not res.ok` 判为失败。

**页面实际正常加载**（dom 不为 None，spec JS 能提取数据），但 `res.ok=False` 导致跳过。

### 16.3 修复

adapter 加一行：
```python
block_marker_allowlist = ("captcha",)
```
豁免 captcha 关键字检测，其他判据（403/正文过短/缺锚点）仍生效。

### 16.4 受影响品牌

| 品牌 | 状态 | 备注 |
|------|------|------|
| samsung_us | ✅ 已有 | 原始配置已有 |
| samsung_mx | ✅ 已有 | 原始配置已有 |
| samsung_co | ✅ 已修复 | 本次新增 |
| samsung_cl | ✅ 已修复 | 本次新增 |
| samsung_ca | ⚠️ 无需 | 页面不触发该关键字 |
| samsung_bo | N/A | 零售适配器无 supports_spec |
| samsung_uk | N/A | 零售适配器无 supports_spec |

### 16.5 同时修复：spec_page_scroll_passes

Samsung spec 区域在页面下方，需滚动才渲染。加：
```python
spec_page_scroll_passes = 3
spec_page_extra_wait_ms = 4000
```

### 16.6 补抓结果

| 品牌 | 补抓前(W40) | 补抓后(W40) | 型号覆盖 |
|------|------------|------------|---------|
| samsung_co | 0行 | 5032行 | 180/180 (100%) |
| samsung_cl | 668行 | 5877行 | 146/146 (100%) |
| lg_us | 7355行 | 7355行 | 100/100 (100%) |

### 16.7 通用规律

**任何全站 status=200 抓取失败的场景，先查 `block_reason`：**
- `marker:captcha` → 豁免 captcha 关键字
- `http_403` → WAF 硬拦截，需住宅 IP
- `not_logged_in` → 需登录态
- 无 block_reason 但 dom is None → wait_selector 超时，加 scroll/extra_wait

## 十七、SPEC 缺口的三种不可修复类型 ★

全量复查 23 个 SPEC 品牌后，5 个品牌有缺口，全部属于**不可修复**类型：

### 17.1 官网已下架（404）

**症状**：`spec-crawl` 报 `status=404`，系列页面在官网不存在。
**案例**：tcl_jp 13 个旧系列（C635/C645/C646/C745/C845/P635/P636/P63H/P725/P735/P745/S5400/S5402/S54H）= 46 个型号。
**原因**：TCL 日本官网定期下架旧型号产品页，页面返回 404。
**修复**：无法修复——页面已不存在。这些型号的 SPEC 只能从其他来源（如 価格.com 缓存、Wayback Machine）补。
**判别**：`status=404` + 官网手动确认页面不存在。

### 17.2 CMS 未填充规格数据（no_spec_section）

**症状**：页面返回 200，`classify_spec_empty` 返回 `no_spec_section`，DOM 中无 `section#specifications`。
**案例**：hisense_mx 9 个新型号（U6QV/U7QPRO/A65NV/U65QF/QD6QF/U8Q/A4K/UX100/UX116）。
**诊断步骤**：
1. 对比成功页（如 U8N）：`<section id="specifications">` 存在，含 `.columns-wrapper .column-item`（SSR 渲染）。
2. 对比失败页（如 U6QV）：导航 `href="#specifications"` 存在但 `<section>` 不存在。
3. 检查 `id="info"` div：成功页有 6 个含内容的 `id="info"`，失败页有 10 个全为 `&nbsp;`（空）。
4. 结论：**Hisense Mexico CMS 从未为这些产品页面填充规格数据**，不是懒加载问题。
**验证**：尝试 `spec_click_texts = ["Especificaciones"]` 点击 tab → 无效（tab 目标 section 不存在）。
**修复**：无法修复——CMS 数据源缺失，adapter 无法提取不存在的数据。

### 17.3 WAF 封锁（403）

**症状**：入口页返回 `status=403` + `Access Denied`。
**案例**：lg_ca（4 空白）、lg_mx（5 空白）。
**原因**：LG 官网 WAF 封锁数据中心/代理 IP，与 sony_ca/sony_uk 同一问题。
**修复**：需住宅 IP，当前代理不可用。
**判别**：`status=403` + HTML 含 `Access Denied`。

### 17.4 假性空白（重复型号名）

**症状**：覆盖率 < 100% 但实际型号无缺失。
**案例**：hisense_jp 116U9R 系列：`models=["116U9R","116U9R","116U9R"]`（3 个重复条目），实际仅 1 个唯一型号，有值 1/3 = 33%。
**修复**：去重后实际 100%，无需修复。spec_series.models 的重复条目是入口页发现阶段的 bug（同一型号被多次发现）。

### 17.5 系列发现正则不兼容官网变体 ★

**症状**：官网有系列但adapter发现不了，导致系列数 < 官网实际数。
**案例**：panasonic_jp — DB 9系列 vs 官网13系列，漏抓 LF2/LW2/MR770/W80C。
**根因**：
1. `_SERIES_HREF` 正则不支持 `-series` 后缀（`/viera/LF2-series.html`）
2. `_MODEL_HREF` 正则不支持 `/viera/p-db/` 格式（MR770 用 `/viera/p-db/TH-50MR770_spec.html`）
3. `res.ok=False`（重定向）时跳过了仍有 HTML 的系列页（W80C）

**修复**：
- `_SERIES_HREF` 加 `(?:-series)?` 兼容后缀，数字下限 `\d{2}` → `\d{1}` 支持 LF2/LW2
- `_MODEL_HREF` 改为双格式：`/viera/products/xxx/spec.html` + `/viera/p-db/xxx_spec.html`
- URL 归一化用原始 href 而非 code 重构（保留大小写）
- 放宽系列页检查：`if dom is None: continue`（去掉 `or not res.ok`）

**结果**：9系列27型号 → 12系列34型号（LF2+LW2+MR770新增；W80C无spec页正常跳过）。

### 17.6 SPEC 覆盖率复查流程 ★

逐线复查 SPEC 完整性的标准流程：

1. **DB 系列去重**：`SELECT DISTINCT series FROM spec_series_status WHERE brand=?` → 得到 DB 已抓系列数
2. **官网发现系列**：调用 adapter 的 `list_series(dom, html)` 或 `series_entries(open_dom)` → 得到官网实际系列数
3. **对比**：官网系列数 > DB 系列数 → 漏抓；官网系列数 ≤ DB 系列数 → 无漏抓
4. **失败系列分析**：`status=failed` 看error_kind → 404(下架)/captcha(WAF)/no_rows(页面结构不同)
5. **补抓**：修复正则/adapter后 `spec-crawl --site <brand>`

**日本线结果**(2026-W40)：
| 品牌 | DB系列 | 官网系列 | 状态 |
|------|--------|----------|------|
| hisense_jp | 13 | 13 | ✅ 完全匹配 |
| panasonic_jp | 9→12 | 13 | ✅ 修复+3系列补抓(W80C无spec页) |
| regza_jp | 39 | 39 | ✅ 完全匹配 |
| sharp_jp | 13 | 13 | ✅ 完全匹配 |
| sony_jp | 9 | 8+1 | ✅ 无漏抓(KJ-X81L是旧型号) |
| tcl_jp | 46 | 46 | ✅ 系列全匹配(20个failed=404下架) |

**北美线结果**(2026-W40)：
| 品牌 | DB系列 | 官网系列 | 状态 |
|------|--------|----------|------|
| hisense_ca/us | 33/36 | — | ✅ 100% |
| hisense_mx | 21 | — | 🔴 CMS无数据(57%) |
| lg_ca/mx | 37/48 | — | 🔴 WAF封锁 |
| lg_us | 99 | — | ✅ 100% |
| samsung_ca/mx/us | 66/22/66 | — | ✅ 100% |
| sony_ca/us | 16/33 | — | ✅ 100% |
| tcl_ca/mx | 16/31 | — | ✅ 100% |
| tcl_us | 15 | 13 | ✅ 无漏抓(7系列no_rows=页面结构不同) |
| philips_ca | 11 | — | ✅ 100% |


---

## 竞品情报分支（compintel）：FCC + EPREL + 5 扩展源（非 spec/retail，独立表族）

> 这是 2026-09 新增的业务线，接入 FCC 认证库 + EPREL 能效库做竞品上市预警。
> 2026-10 扩展：+ENERGY STAR、ANATEL、IC/ISED、TÜV Rheinland、VDE/CB 共 7 个数据源。
> **不属于 SPEC（品牌官网 lineup）也不属于 RETAIL（电商价评）**，是第三方合规数据库。
> 代码在 `overseas/compintel/`，表族 `compintel_*`（见 schema.sql 末尾），与电视线解耦。
> Schema v9：source CHECK 扩展为 `('fcc','eprel','energystar','ul','tuv','ic_ised','anatel')`。

### 判定这是 compintel 而非 spec/retail
- 数据源是**政府/合规数据库**（FCC/EPREL/ENERGY STAR/ANATEL/ISED/TÜV/VDE），不是品牌官网 lineup，也不是电商零售站。
- 目的是**竞品上市预警**（前瞻信号），不是抓品牌全型号规格，也不是抓零售价评。
- 走 `overseas/compintel/` 独立模块，不要硬套 spec/retail schema。

### FCC：apps.fcc.gov 被封 → 走 fccid.io 聚合站（纯 HTTP）
| 信号 | 解法 |
|---|---|
| apps.fcc.gov/oetcf/eas 返回 403 + errors.edgesuite.net | Akamai 硬封，换数据源 |
| fccid.io/search?q=<applicant> 返回 200 HTML | 聚合站可纯 HTTP，每结果一个 panel |
| panel 结构：h3>a[href=/FCCID] + table th/td | 正则提 FCC ID/Company/Latest Filing/Frequencies/Grantee Code |
| 详情页文档表用 data-label=Document/Type/Available | 三列正则，日期列叫 Available 不叫 Date |
| 保密到期检测：详情页能抓到 Internal/External Photos | 文件可访问 = 保密期已结束（FCC 保密最长180天） |

### EPREL：Angular SPA → /api/ JSON 接口（纯 HTTP）
| 信号 | 解法 |
|---|---|
| eprel.ec.europa.eu/screen/* 是 Angular SPA（app-root） | 数据不在 HTML，在后端 API |
| /api/products/electronicdisplays 返回 JSON | 列表接口，{size:37509, hits:[25条]} |
| from/size/page/pageSize 参数全部被忽略 | 固定25条/请求，不可翻页 |
| from=370000+ 触发 403 | 大偏移被拦，不能一次拉全量 |
| /api/product/<regNumber> 稳定返回详情 | 按注册号直查可靠 |
| 产品组标识是 electronicdisplays（非 electronicdisplays2021） | 2021 是法规号不是产品组 URL |
| POST /api/products/... 返回 403 | 只接受 GET |

### EPREL 抓全量策略（关键）
列表不可翻页，要拿"最新"记录靠**注册号轮询去重**：
1. 定期调 `/api/products/electronicdisplays`（每次25条样本）。
2. 按 `eprelRegistrationNumber` 去重，新号入库 + 产生 eprel_new_reg 信号。
3. 注册号大致连续递增（新发布日对应更大号），多次轮询逐步覆盖新品。
4. 想抓某具体产品：用注册号直查 `/api/product/<reg>`（稳定）。

### 6+1 类预警信号（alert.py）
| 信号 | 来源 | 判据 |
|---|---|---|
| new_fcc_id | FCC | source_id 首次出现 |
| confidential_expired | FCC | 详情页能抓到 Internal/External Photos/Users Manual |
| eprel_new_reg | EPREL | registration_number 首次出现 |
| energy_class_jump | EPREL | 同品牌新记录能效比历史最佳高 ≥2 级 |
| eprel_delisted | EPREL | status 变非在售 / onMarketEnd 近30天 |
| supplier_change | 两者 | 同 source_id 历史快照 applicant 与本次不同 |
| **new_cert** | energystar/anatel/ic_ised/tuv/ul | 新数据源 source_id 首次出现(统一信号类型) |

### 坑：is_new 必须在 add_record 之前判定
seen_source_id 在 add_record 后恒为 True，必须先判 is_new 再插入，
否则 new 计数和 new_* 信号永远为 0（已修复，见 orchestrator.py）。

### 坑：add_record 的 source_id 位置参数与 **dict 冲突
`add_record(run_id, source, source_id, **rec_dict)` — source_id 是位置参数，
若 rec_dict 里也有 `source_id` 键，`**rec_dict` 展开会报 `multiple values for argument`。
必须先 `sid = r.pop("source_id")` 再 `add_record(run_id, src, sid, **r)`。
FCC/EPREL 不踩此坑(它们提取 sid 后不放进 dict)，新数据源爬虫会把 source_id 放进 dict 返回。

### Schema v8→v9 迁移：SQLite CHECK 约束不能 ALTER
扩展 source CHECK 值时，SQLite 不支持 ALTER 列的 CHECK 约束，必须重建表：
`PRAGMA foreign_keys=OFF → RENAME 旧表 → CREATE 新表(新CHECK) → INSERT SELECT → DROP 旧表 → 重建索引 → PRAGMA foreign_keys=ON`
迁移前自动备份 `data/overseas_v8_backup.db`，314 记录 + 320 alerts + 85 states 全保留。

### ENERGY STAR：Socrata SODA API（无浏览器，无 API key）
| 信号 | 解法 |
|---|---|
| API `data.energystar.gov/resource/8wj2-sec8.json` | Model Index 数据集统一全 47 品类 |
| SoQL `$where=brand_name='Samsung'` | 精确匹配，空格用 urllib.parse.quote 编码 |
| 空结果返回 `[]` → httpx `res.ok=False` | 被 blocked detector 误判，必须判 `res.status != 200` 而非 `res.ok` |
| `$limit=1000` + `$offset` 分页 | 无频率限制，1s/请求 |

### ANATEL：巴西 ZIP-CSV 下载（无浏览器）
| 信号 | 解法 |
|---|---|
| 官方 ZIP-CSV（53MB，191K 行） | urllib.request.urlretrieve 直接下载（HttpFetcher 的 read() 做 UTF-8 decode 会损坏 ZIP 二进制） |
| CSV 编码 UTF-8-sig（非 cp1252） | `decode("utf-8-sig")` 自动去 BOM，否则 BOM `ï»¿` 在 headers 中导致列名匹配失败 |
| 分号 `;` 分隔 | `csv.reader(delimiter=";")` |
| csv.reader 报 "new-line in unquoted field" | `io.StringIO(csv_text, newline="")` 必须加 newline="" |
| 品牌匹配 | `Nome do Fabricante` 列，BRAND_FABRICANTE_MAP 关键词 |

### IC/ISED：加拿大 Spring WebFlow 表单（urllib + CookieJar，无浏览器）
| 信号 | 解法 |
|---|---|
| 表单 hidden `name="execution"`（无下划线） | 正则 `name="execution"\s+value="([^"]+)"` 提取 e1s1 格式 token |
| 提交按钮 `_eventId_search=Search` | POST data 含 execution + _eventId_search |
| 结果页 "Processing…please wait" + setTimeout(refreshpage, 5000) | 轮询 `_eventId_refresh=Refresh` 1-2 次（等 15s+） |
| 结果表 `id="equipmentSearchResultTable"`（非 companyResultTable） | 正则提 table + tbody，公司分组 `<th colspan=7>` + 数据行 6 单元格 |
| **HTTP 500 rate limit**（同 IP 连续请求被限） | 缓存公司号 `ISED_COMPANY_NUMBERS`（Samsung=649A/649B, LG=2703A/2703C）跳过 search_companies + 每 REL 新建 IcedCrawler 实例 + 15s 延迟 |

### TÜV Rheinland + VDE/CB：cert_verify 包复用
| 信号 | 解法 |
|---|---|
| TÜV Certipedia 搜索页返回 `quality_marks` 链接 | 含 `certificate_number=` 参数（非 `/certificates/` 路径），需双 pattern 提取 |
| TÜV 逐证书查详情页 15s/张 × 50 = 12 分钟超时 | 改批量从搜索页提取所有证书号（1 次搜索） |
| VDE Solr `companyName` 字段返回 400 | 必须用 `companyName_en:*<name>*` 通配符 |
| VDE Solr q 参数含空格报 URL 控制字符错误/400 | 取公司名首词即可（Samsung，非 Samsung Electronics） |
| cert_verify 读 `CERT_PROXY`/`VDE_PROXY` 非 `OVERSEAS_PROXY` | orchestrator 用 os.environ 设置这些变量 |
| cert_verify 包独立于 crawl4ai 框架 | cert_crawler.py 开头 sys.path.insert cert_verify 包路径 |


---

## compintel 定时预警运维要点

### 抓取频率:每天 1 次足够(不要过频)
FCC/EPREL 是合规数据库,更新节奏天级。信号提前量:FCC 认证到发布 1-3 月、EPREL 注册到发布数天。
每天 1 次即可捕捉所有领先指标。每小时抓只是重复拿相同数据 + 浪费请求配额 + 增被封风险。

### 分层:daily(快) + weekly(带 details 慢)
- daily: `compintel-run --applicants X --eprel-brands Y` 无 --details,只抓新记录信号。
- weekly: 加 `--details`,每 FCC ID 多 1 次详情请求(2s/个),5 竞品 ~500 ID ~17 分钟。检测保密到期。

### 变化检测关键:before_captured_at 截点(否则 bug)
变化检测在插入本次快照后运行,但查"上次快照"时必须用 `last_record(source, sid, before_captured_at=run_started_at)`,
否则查到刚插入的本次自己 → supplier_change/field_change 恒不触发。
orchestrator 用 `crawl_run.started_at` 作为截点传给所有 detector。

### PowerShell 数组传参陷阱
`--applicants $APPLICANTS`(数组)传外部命令会变成 `System.Object[]` 字符串。
必须:`@("-m","overseas.cli","compintel-run","--applicants") + $APPLICANTS + @("--eprel-brands") + $EPREL_BRANDS`
计划任务的控制台日志中文乱码不影响功能(日志文件是 UTF8);加 `[Console]::OutputEncoding=UTF8` 修复。

### 安装:一键注册计划任务
`compintel_install_task.ps1` 注册 daily(06:00) + weekly(周一 07:00) 两个任务。
带 StartWhenAvailable(错过时间补跑) + 30 分钟超时 + 失败重试 2 次。


---

## compintel 测试时的环境变量陷阱(务必看)

config.py 只认 `OVERSEAS_DB_PATH`,不认 `COMPINTEL_DB`。
测试 compintel 时若误设 `COMPINTEL_DB=data/sandbox.db`,CLI 仍写到正式库 `overseas.db`,
导致正式库被测试数据污染(380 record + 128 alert)。

正确做法:测试一律用 `OVERSEAS_DB_PATH=data/sandbox_compintel.db`,且每次测试后核对
`sandbox_compintel.db` 与 `overseas.db` 的 compintel_record 行数,确认隔离。
清理污染:`DELETE FROM compintel_alert/doc/record WHERE run_id IN (compintel runs)` +
`DELETE FROM crawl_run WHERE scenario LIKE 'compintel%'`。

这个教训通用:本项目所有 CLI 子命令的 DB 路径都由 `OVERSEAS_DB_PATH` 控制,
没有第二套环境变量名。新增模块时切勿自造 `XXX_DB` 变量。
