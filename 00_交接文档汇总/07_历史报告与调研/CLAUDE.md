# 爬取项目 CLAUDE.md

## 本项目的唯一 skill（所有任务默认使用）
**[.kiro/skills/overseas-schema-gen/SKILL.md](海外/.kiro/skills/overseas-schema-gen/SKILL.md)**
- **统一入口**：接入新站、生成 schema/适配器、诊断抓不全/匹配不到、全量运维——全部走这一个 skill。
- 内部三分支自动分派：
  - **SPEC**（品牌官网 lineup → 发现型号 → 规格）→ `spec/` 子目录
  - **RETAIL**（电商零售站 → 给定型号 → 抓价+网评）→ `retail/` 子目录
  - **OPS**（已有适配器的全量运行/监控/修复/导出）→ `ops/crawl-ops.md`
- 触发词：接入新站、生成 schema、适配器、spec-onboard、spec-crawl、价格、网评、全量、断点续抓、僵尸、污染、监控、rebuild。

## 经验沉淀约定（活文档，强制）
- 每当本项目工作中获得**可复用新经验**（踩坑、修 bug、优化流程、新异常形态、新结构识别），**必须**沉淀进上面唯一 skill 的对应分支文件：
  - SPEC 经验 → `spec/cases.jsonl` + `spec/reference.md` + 必要时 `spec/playbook/`
  - RETAIL 经验 → `retail/cases.jsonl` + `retail/reference.md` + 必要时 `retail/playbook/`
  - 运维经验 → `ops/crawl-ops.md`
- 每个新站的接入（成功或失败）**必须**在对应 `cases.jsonl` 追加一条（格式见文件头注释），这是 skill 越用越强的唯一机制，漏了等于白干。
- 沉淀完成后跑对应分支 `selfcheck.py` 验证（`py -3.12 .kiro/skills/overseas-schema-gen/<spec|retail>/selfcheck.py`）。
- 沉淀原则：只留对未来有用的操作结论（决策 + why + 可执行命令），删一次性细节；与既有条目重复则合并，不堆积。
- `docs/` 与 `日志与经验汇总/` 里的文档是历史交付物，不改写；skill 是活文档。

## 环境变量（海外爬取）
```
OVERSEAS_PROXY=http://127.0.0.1:7877   # 出口代理，不设直连失败
OVERSEAS_USE_PROFILE=1                  # 持久化浏览器 profile，缺它拿不到登录态
PYTHONIOENCODING=utf-8
```

## 工程红线
- 长时爬取**必须** `--save-db`、**串行**（单出口 IP）、先备份 DB、用 supervisor 断点续抓。
- "缺价 > 错价"：宁留空不造假价。
- 失败型号（failed/no_item/no_price/no_reviews）直接跳，不无限重试。