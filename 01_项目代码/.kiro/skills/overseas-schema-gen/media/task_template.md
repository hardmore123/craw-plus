# 媒体评测站接入任务模板

## 站点信息
- code: 
- name: 
- base_url: 
- country: 
- channel: 
- 入口URL（评测列表页）: 

## Step 0 — 查经验库
```
Select-String -Path .kiro/skills/overseas-schema-gen/media/cases.jsonl -Pattern "<域名关键词>"
```
命中相似站 → 复用其 adapter 模板。

## Step 1 — 探测
```
py -3.12 .kiro/skills/overseas-schema-gen/media/probe.py --entry "<评测列表URL>" --code <code>
```

### 探测结果
- JSON-LD 类型: ☐ Review ☐ Product嵌套 ☐ Product only ☐ Article ☐ 无
- 评分位置: ☐ reviewRating ☐ aggregateRating ☐ HTML ☐ 付费墙
- 评分量表: ___ (如 0-10 / 0-5 / 1-5反序)
- 优缺点: ☐ positiveNotes/negativeNotes ☐ HTML ul/li ☐ 无
- 评测列表选择器: ___
- WAF状态: ☐ ok ☐ blocked ☐ cloudflare ☐ 付费墙
- 需要浏览器: ☐ 是 ☐ 否

### 选定 playbook
☐ jsonld_review ☐ jsonld_product ☐ jsonld_product_only ☐ html_fallback ☐ waf_playwright

## Step 2 — 写 adapter.py + schema.json

```python
class XxxAdapter(MediaAdapter):
    code = "xxx"
    name = "XXX"
    base_url = "https://xxx"
    country = "国家"
    channel = "媒体名"
    extract_mode = "jsonld_review"  # 或 jsonld_product / html
    supports_media = True
    requires_browser = False  # 或 True
    rating_scale = "0-10"  # 必填
    
    def review_list_url(self, category: str = "") -> str: ...
    def parse_review(self, html: str, article_url: str) -> MediaReview | None: ...
```

## Step 3 — 校验 + 小样实测
```
py -3.12 .kiro/skills/overseas-schema-gen/media/probe.py --verify sites/<code>/adapter.py
```
sandbox db 抓取：
```
$env:OVERSEAS_DB = "data/sandbox_<code>.db"
py -3.12 -m overseas.cli media-crawl --site <code>
```

## Step 4 — 转正 + 沉淀
- [ ] adapter.py → `overseas/sites/<code>/adapter.py`
- [ ] schema.json → `overseas/sites/<code>/schema.json`
- [ ] 追加 `media/cases.jsonl` 一条
- [ ] 更新 `reference.md`（如有新坑）
- [ ] 跑 `selfcheck.py`
