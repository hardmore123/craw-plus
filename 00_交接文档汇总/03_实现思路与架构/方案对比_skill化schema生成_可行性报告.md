# Skill 化 schema 生成 vs 现有 LLM 自动适配器：对比与可行性报告

> 日期：2026-09-16
> 状态：评审用。结论基于对 `spec_probe.py` / `spec_generator.py` / `generic_spec.py` / `cli.py`
> 的代码核查与 `docs/LLM自动适配器技术方案.md` 全文，未改动任何抓取代码。

---

## 0. 结论先行

**两个方案不是替代关系，而是同一条流水线上不同环节的替换。**

现有链路是四段：`Probe（探测）→ Generate（出 schema）→ Verify（校验）→ Execute（引擎按 schema 抓）`。

- 提议的 skill 方案，替换的是 **Generate**（把"单轮 LLM + prompt + 自动回喂"换成"智能体带工具迭代"）。
- 但当前挡住覆盖面的 P0 缺口——多级发现、`xhr_api`、`query_param` 分页——**全部在 Execute 端**，
  是引擎能力缺口，不是"生成 schema 的大脑不够聪明"。

**因此：skill 化能显著提升"探索期诊断效率"，但不能替代 P0 引擎工作。**
`generic_spec` 引擎只认 `discover.mode=dom_anchor`、2 个分页片段、3 种解析方法；
智能体再强，产出的 schema 也**超不过引擎的执行能力边界**——超了就是一份跑不动的配置。

推荐**混合**：skill 当"探索/诊断工作台"，引擎 + `spec_probe` 当"固化产线"，经验从前者回流成后者的代码。

---

## 1. 现状进展（截至 2026-09-16）

### 1.1 已跑通的能力

闭环 `Probe → Generate → Verify → Repair → Execute` 代码全通，并在真实站验证：

| 站点 | 结构类型 | 结果 |
|---|---|---|
| Philips CA | 编号页码 + 替换式分页 | **25/25 型号，100%** |
| REGZA JP | 单级 lineup（懒加载注入） | **39 系列 39 型号** |
| 秘鲁 Hisense | 静态 lineup 一次列全 | **13 系列 36 型号** |
| Sony BRAVIA JP | 静态列全（JS 延迟注入） | **8/8 当前在售** |
| Hisense US | Wix + Load More + 杂乱 slug | **失败，判定需手写适配器** |

配套的护栏是这套方案真正的资产，不是附属品：

- **实测打分否决权**：`score_spec_on_html` 四维打分（选择器命中 3 / 型号可提取 3 / 找全率 2 / 规格可解析 2），
  `link` 未命中、型号提不到、找全率 <80% 任一直接否决。Philips 第一次只发现 12/25 时被如实拦截，
  没让"抓一半"蒙混过关。
- **安全边界**：`discover.mode` 白名单、正则必须可编译、`api.url_template` 同源防 SSRF、
  JS 片段只能引用已登记库（`KNOWN_SNIPPETS`）——**LLM 只产配置、不产代码**。
- **`prune_html` 去重版**：112K → 418 字符且页尾关键元素 4/4 保留（旧正则版截断 30K 时 0/4）。

### 1.2 引擎当前的硬边界（代码实测）

这是理解全局的关键。三个白名单常量决定了"schema 能长什么样"：

```python
SUPPORTED_DISCOVER_MODES  = {"dom_anchor"}                     # 仅 1 种
KNOWN_SNIPPETS            = {"philips_paginate", "numbered_pages_generic"}   # 仅 2 个
SUPPORTED_EXTRACT_METHODS = {"embedded_json", "embedded_json_philips", "generic_spec_js"}  # 仅 3 种
```

`generic_spec.py` 里 `mode != "dom_anchor"` 直接 `raise NotImplementedError`——显式报错而非静默降级，
这个设计是对的，但也说明覆盖面就卡在这儿。

### 1.3 达成预想结果所需的剩余工作

**P0 — 覆盖面（决定能自动化多少站）**

1. **多级发现**：总览 → 系列 → 型号（松下 / 夏普）。当前只探单层，是最大缺口。
2. **`xhr_api` 模式**：TCL / Samsung / LG 靠接口出数据，目前仅预留、命中即 `NotImplementedError`。
3. **`query_param` 分页**：LG 的 `?firstResult=N` 未支持。

参考手写适配器规模，可以侧面看出这些站的难度：`samsung_mx` 502 行、`samsung_us` 376 行、`tcl_us` 374 行。
这些正是 P0 要覆盖的对象。

**P1 — 生产化（决定能否无人值守）**

4. `adapter_spec` / `onboard_run` 两张表未落地（当前 schema 直接写 JSON 文件，只有 1 份
   `docs/specs/philips_ca.spec.json`）。缺它就没有改版重生成、版本回滚、失败现场复现。
5. `spec-health` 定期探测未实现。
6. 人工审核门 `candidate → approved` 与 `spec-approve` 未实现，当前"生成即用"。

**P2 — 稳健与合规**

7. 异步页面抓取时机波动（Sony 曾抓到 0）。
8. 站点白名单 / 黑名单准入未实现（robots / ToS）。
9. **Verify 的 L3 规格质量校验实测薄弱**——目前验证集中在"发现/找全型号"，
   规格页解析在新站上的自动验证不充分。这是数据污染风险最高的一块。

---

## 2. 方案 B：Skill 化 schema 生成

### 2.1 设想形态

```
.kiro/skills/spec-schema-generator/
    SKILL.md        # 主流程：给新站 URL，如何一步步产出可用 schema
    probe.py        # 硬编码探测脚本（复用 BrowserFetcher）：抓渲染后 HTML、dump 结构信号
    reference.md    # 判断经验库：什么结构用哪个 extract 档、TCL 类 SPA 怎么办
```

智能体照做的流程：入口页定位产品链接选择器与 URL 模式 → 抓一个型号页判断规格载体 →
写 schema → 用 `spec-crawl` / verify 验证抓到的行数 → 抓不到就诊断调整 → 达标保存。

### 2.2 与方案 A 的本质差别

| | 方案 A（现有） | 方案 B（skill） |
|---|---|---|
| Generate 的执行者 | 程序化单轮 LLM 调用 + 自动回喂修复 | 智能体带工具多轮迭代 |
| 判断力来源 | prompt + 探测报告摘要 + 打分失败清单 | 智能体可自主读 HTML、试选择器、看结果再改 |
| 经验沉淀方式 | 固化进 `spec_probe.py` 的候选选择器与排序规则（代码） | 累积进 `reference.md`（自然语言） |
| 可否无人值守 | **可以**（CLI 命令，能进定时任务/CI） | **不可以**（需人在 IDE 内驱动） |
| 灵活度 | 受 prompt 与打分维度限制 | 高，能处理没预料到的怪站 |

### 2.3 方案 B 的三个硬约束（必须正视）

**约束一：`.kiro/` 被 git 忽略。**

`.gitignore` 第 38 行就是 `.kiro/`（已用 `git check-ignore -v` 确认命中）。这意味着放在
`.kiro/skills/` 的 SKILL.md、probe.py、reference.md **不会入库**：不能团队共享、不能版本回滚、
不能在另一台机器复现、`reference.md` 里积累的经验一旦本地丢失就没了。

这和上周刚踩的 `__init__.py` 坑是**同一类问题**——文件只在本机物理存在、git 里没有备份。

处理方式二选一：把 skill 放到仓库内受跟踪的路径（如 `docs/skills/` 或 `tools/spec_onboard_skill/`），
或在 `.gitignore` 里给 `.kiro/skills/` 开白名单。**建议前者**，因为 `probe.py` 本质是项目工具代码，
理应和 `overseas/` 一起版本化。

**约束二：智能体产出的 schema 仍受引擎白名单限制。**

这是最容易被忽略的一点。智能体判断出"TCL 这站需要点击展开 tab 才能拿到规格"，
但只要引擎的 `SUPPORTED_EXTRACT_METHODS` 里没有对应档位，这个判断就无法落地成可执行 schema。

也就是说：**skill 化不会自动带来覆盖面提升。** 覆盖面提升 = 引擎新增能力档位（P0 工作）。
skill 的作用是**更快发现"缺哪个档位"**，以及在档位齐备后更准地选档填参。

**约束三：失去无人值守能力。**

方案 A 的 `spec-onboard` 是 CLI，可以进定时任务、可以被 `spec-health` 在检测到成功率骤降时自动触发重生成
（P1 第 5 项的设计前提）。skill 必须有人开着 IDE 驱动。

对"日常重跑"没影响（schema 已落盘，抓取零 LLM 依赖），但对"改版自愈"是致命的——
站点改版往往在无人注意时发生，正需要自动重生成。

### 2.4 方案 B 的真实价值

排除掉上面三条之后，剩下的价值是**实在的，而且正好对准当前阶段的痛点**：

你现在的处境是"每个网站遇到的难点不同、结构分布很散"。这个阶段的瓶颈**不是**批量自动化，
而是**逐站诊断的效率**。而智能体在诊断上的优势是结构性的：

- 能自主决定"再抓一个页面看看"、"换个选择器试试"、"把这段 HTML 打出来瞧瞧"，而方案 A 的回喂只有
  打分失败清单这一条窄通道；
- 能一次性看到 Hisense US 那种"型号 slug 混乱 + Load More 点不开 + 混入投影音箱"的复合难点，
  并给出"这站要手写"的判断，而不是在打分器里反复不收敛；
- `reference.md` 的经验积累对**人**也有价值——它是"新站接入判断手册"，方案 A 的经验固化在
  `spec_probe.py` 的排序权重里，人不易读。

历史上 §11.2、§12.2 那几次探测器改进（纯度优先排序、精确候选选择器、分页误判修复），
本质就是**人工做了一遍智能体该做的诊断**，然后把结论固化成代码。skill 化是把这个过程工具化。

---

## 3. 逐维度对比

| 维度 | 方案 A 程序化闭环 | 方案 B skill 智能体 | 说明 |
|---|---|---|---|
| 覆盖面上限 | 受引擎档位限制 | **同样受引擎档位限制** | 关键：两者上限相同，瓶颈在 Execute 端 |
| 探索期诊断效率 | 低（只能靠打分失败清单回喂） | **高** | 当前阶段最痛的点 |
| 怪站处理 | 反复不收敛，靠轮次上限兜底 | 能快速判定"该手写" | |
| 无人值守 / CI | **支持** | 不支持 | 决定 spec-health 自愈能否实现 |
| 团队共享与版本化 | 天然入库 | `.kiro/` 被忽略，需先解决 | 见 2.3 约束一 |
| 结果可复现 | 高（同 schema 同结果） | 中（智能体每次判断可能不同） | 但 schema 一旦落盘，执行端都确定 |
| 数据污染风险控制 | 打分否决权 + 守恒校验（已建成） | **需显式复用同一套校验** | 不能因为"智能体看着对"就跳过 |
| Token / 成本 | 低（一次性，之后零调用） | 中高（多轮交互） | 但接站是低频动作，可接受 |
| 落地成本 | 已投入约 70% | 增量（复用 probe + 现有 schema 格式） | |

---

## 4. 可行性判定

**方案 B 技术可行，但不能作为方案 A 的替代品，只能作为其 Generate 环节的增强与探索期工作台。**

判定依据：

1. **可行性成立的部分**：探测脚本可直接复用 `BrowserFetcher`（TCL 这类必须渲染 + 点击的站，
   只有真实浏览器能拿到 DOM，通用 web_fetch 拿不到 SPA 渲染后结果）；schema 格式可直接复用现有
   `AdapterSpec`；验证可直接复用 `score_spec_on_html` 与 `spec-crawl --schema`。
   **三个环节都有现成件，增量成本低。**

2. **不可行的部分**：指望 skill 化解决"预想结果"（覆盖 TCL / Samsung / LG / 松下 / 夏普）。
   这些站缺的是 `xhr_api`、多级发现、`query_param` 分页——都得改引擎。

3. **必须先解决的**：`.kiro/` 不入库的问题。否则 skill 与其积累的经验都是"只在一台机器上存在"的资产。

---

## 5. 建议路线

分三步，**不推翻已有的 70%**：

**第一步（低成本，立刻做）：skill 落地为探索工作台**

- 放在**受 git 跟踪**的路径，如 `tools/spec_onboard_skill/`，内含 `SKILL.md` + `probe.py` + `reference.md`；
  或改 `.gitignore` 给 `.kiro/skills/` 开白名单。
- `probe.py` 直接复用 `spec_probe.probe_site` + `BrowserFetcher`，不重写探测逻辑。
- schema 格式**沿用现有 AdapterSpec**，不另造一套。产出后必须过 `validate_spec` +
  `score_spec_on_html`，**校验环节不允许因为"智能体判断过了"而跳过**。
- `reference.md` 初始内容直接从技术方案文档 §11.4、§12.4 的沉淀经验搬过来。

**第二步（并行，决定覆盖面）：继续推 P0 引擎能力**

用 skill 当诊断工具去啃松下 / 夏普（多级发现）与 TCL / Samsung（`xhr_api`），
每啃下一类结构就给引擎**新增一个能力档位**并同步更新三个白名单常量。
这是覆盖面唯一的真实来源。

**第三步（生产化）：两条路径并存**

- 接新站 / 疑难诊断 → skill（人机协同，判断力优先）
- 改版自愈 / 定时健康探测 → 程序化 `spec-onboard`（无人值守，可 CI）

两者共用同一份 schema 格式、同一套校验、同一个执行引擎。这样既拿到智能体的灵活度，
又不丢掉自动化能力。

---

## 6. 对截图中四个问题的直接回答

1. **schema 用什么格式？** 复用现有 `AdapterSpec`（`discover` / `spec` / `identity` / `fetch` / `expected`
   + `extract_order`）。不要另造格式，否则 `generic_spec` 引擎和 `validate_spec` 都得改，白丢已验证的资产。

2. **用什么工具探测？** 复用 `BrowserFetcher` / `spec_probe.probe_site`。TCL 这类必须渲染 + 点击的站，
   通用网页抓取工具拿不到 SPA 渲染后 DOM，只有现有浏览器路径能做。

3. **LLM 还用不用？** **两条都留。** 探索期由智能体主导（判断力强）；但 `spec-health` 自动重生成
   必须是程序化 LLM 调用，否则无人值守自愈无法实现（P1 第 5 项直接依赖它）。

4. **`kv_generic` / `interactive_tabs` 保留吗？** ⚠️ **注意：这两档在当前仓库里不存在。**
   已核查 `SUPPORTED_EXTRACT_METHODS` 只有 `embedded_json` / `embedded_json_philips` / `generic_spec_js`，
   全仓库 grep 无 `kv_generic` / `interactive_tabs` / `css_table`。
   若它们是在另一台机器或另一分支上加的，**需要先确认是否已提交并合入**——
   这正是上周 `__init__.py` 问题的翻版。若确已实现，应保留：它们属于引擎能力档位扩展，正是 P0 需要的方向。

---

## 7. 一句话总结

Skill 化值得做，但要放对位置：它是**探索期的诊断加速器和经验沉淀载体**，不是覆盖面问题的解药。
覆盖面靠 P0 引擎档位扩展，生产化靠 P1 库表与 health。
最该先动的两件事：把 skill 放到 git 跟踪的路径下、用它去啃多级发现。
