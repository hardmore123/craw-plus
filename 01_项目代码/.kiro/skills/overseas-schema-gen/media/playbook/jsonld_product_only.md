# Playbook: JSON-LD Product only（无评分）

> 适用站：which_uk
> 特征：JSON-LD 有 `@type=Product`（产品名+品牌）但无 `review`，评分在付费墙后

## 结构

```json
{"@type": "BreadcrumbList", ...}
{"@type": "Product", "name": "Hisense 65UR9STUK", "brand": {"name": "Hisense"}}
```

## 提取逻辑

只能提取产品名+品牌，评分需会员登录态：

```python
if t == "Product":
    product_name = item.get("name", "")
    brand = item.get("brand", {}).get("name", "")
    # aggregateRating 可能存在但通常为空或付费墙后
```

## 付费墙应对

```python
class WhichUkAdapter(MediaAdapter):
    code = "which_uk"
    extract_mode = "jsonld_product_only"
    requires_browser = True
    needs_login = True  # 评分需Which?会员
    # 使用 storage_state 持久化登录态
```

## 坑

- which_uk 是消费者组织，评分（测试结果）需会员
- 产品评测页可匿名访问，但评分在 `<div class="premium-content">` 后
- 用 `OVERSEAS_USE_PROFILE=1` + `wait_for_login()` 手动登录后持久化
