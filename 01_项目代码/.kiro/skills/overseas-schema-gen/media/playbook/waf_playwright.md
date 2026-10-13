# Playbook: WAF 突破策略

> 适用站：hwupgrade_it（突破成功）/ clubic_fr, tweakers_nl, avforums_uk（需住宅IP）

## WAF 类型判别

| 信号 | WAF 类型 | Playwright能否突破 |
|------|----------|-------------------|
| HTTP 403 + `blocked=True` | 自建WAF | 部分可（hwupgrade_it ✅） |
| 页面含 `cloudflare` + `challenge` | Cloudflare JS Challenge | ❌ 需住宅IP |
| 页面含 `datadome` | DataDome | ❌ 需住宅IP |
| HTTP 410 | 站点已下线 | N/A |

## Playwright 突破条件

1. **不是 JS Challenge**（纯 403 可突破）
2. **用持久化 profile**：`OVERSEAS_USE_PROFILE=1`
3. **stealth JS 注入**：项目已有 `_STEALTH_JS` 在 `BrowserFetcher`
4. **足够等待**：`settle_ms=4000` 让 WAF 检查完成

```python
fetcher = BrowserFetcher(
    proxy="http://127.0.0.1:7877",
    headless=True,
    site_code="hwupgrade_it",  # 触发 profile 持久化
)
with fetcher.page(url, wait_selector="body", nav_timeout_ms=25000, settle_ms=4000) as (res, dom):
    html = dom.html()
```

## 突破成功的站

| 站点 | WAF | 结果 |
|------|-----|------|
| hwupgrade_it | Cloudflare | ✅ 10条评测(2条有评分) |
| techradar_uk | 无WAF但超时 | ✅ Playwright解决超时 |

## 无法突破的站

| 站点 | WAF | 原因 |
|------|-----|------|
| clubic_fr | Cloudflare | JS Challenge页面 |
| tweakers_nl | 自建 | blocked=True |
| avforums_uk | 自建 | HTTP 403 |
| fwd_nl | 自建 | blocked |

## 解决方案

- **住宅IP**：机房IP（127.0.0.1:7877出口）被WAF标记，换住宅代理
- **cloudscraper**：Python库可解简单JS Challenge（非本项目依赖）
- **人工登录态**：消费者组织站(test_de/which_uk)用会员登录绕过付费墙
