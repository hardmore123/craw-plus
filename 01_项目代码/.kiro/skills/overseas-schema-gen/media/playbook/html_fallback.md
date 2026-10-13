# Playbook: HTML fallback 模式

> 适用站：connect_de, chip_de, hifitest_de, computerbild_de
> 特征：无 JSON-LD Review 结构，评分/优缺点在 HTML 中

## 提取逻辑

### 1. 标题/产品名 → 型号 + 品牌
```python
# 从 <title> 或 <h1> 提取
title = re.search(r"<title[^>]*>([^<]+)</title>", html).group(1)
# 型号正则
model = re.search(r"\b(\d{2,3}[A-Z]{1,4}\d{2,4}[A-Z]{0,3})\b", title)
# 品牌匹配
for b in ["Sony", "Samsung", "LG", "TCL", "Hisense", ...]:
    if b.lower() in title.lower(): brand = b
```

### 2. 评分正则（按语言）
```python
# 德国（反序 1=sehr gut, 5=mangelhaft）
r"([1-5],[0-9])"  # 3,5 → 评分3.5（德国制，1最好）
# 意大利语
r"(?:voto|giudizio|valutazione)\s*[:=]?\s*(\d+(?:[.,]\d+)?)"
# 通用
r"(\d+(?:\.\d+)?)\s*out of\s*(\d+)"
r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+)\b"
```

### 3. 优缺点（HTML 段落）
```python
# Pro/Contra
pro_section = re.search(r"(?:Pro|Vorteile|Plus).*</h[2-4]>(.*?)(?:Contra|Nachteile|Minus)", html, re.S|re.I)
pos = re.findall(r"<li[^>]*>([^<]{5,80})</li>", pro_section)
# Fazit
fazit = re.search(r"(Fazit|Resümee).{0,500}", html, re.I)
```

## per-site 选择器

| 站点 | 评分位置 | 优缺点位置 | 备注 |
|------|----------|-----------|------|
| connect_de | 正文 Fazit 段（德国1-5反序，无CSS标签） | 无结构化Pro/Contra | URL必须从列表页取 |
| chip_de | 无评分（JSON-LD Article无rating） | 无 | 有标题+品牌+日期 |
| hifitest_de | 未找到 | 未找到 | 需Playwright |
| computerbild_de | 榜单表格 | 无 | SSL频繁断连 |

## 坑

- **connect_de URL 重定向**：猜的 URL（如 `-3213161.html`）会重定向到新闻页。必须从列表页取实际链接。
- **德国评分反序**：`3,5` 表示中等偏好（1=最好），不转换会误判质量。
- **computerbild_de SSL**：纯HTTP频繁 `UNEXPECTED_EOF_WHILE_READING`，需浏览器。
