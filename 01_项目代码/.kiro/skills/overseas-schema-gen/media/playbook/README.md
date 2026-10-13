# Playbook 索引 — 媒体评测站结构型套路

> 按结构信号选 playbook，复用提取逻辑。

| 套路 | 信号 | 适用站 | 文件 |
|------|------|--------|------|
| JSON-LD @graph Review | `<script ld+json>` 含 `@type=Review` + `positiveNotes` | techfi_nl, techzilla_it | [jsonld_review.md](jsonld_review.md) |
| JSON-LD Product 嵌套 | `@type=Product` 内嵌 `review` | techradar_uk | [jsonld_product.md](jsonld_product.md) |
| JSON-LD Product only | `@type=Product` 无 `review`（付费墙） | which_uk | [jsonld_product_only.md](jsonld_product_only.md) |
| HTML fallback | 无 JSON-LD Review，评分在 HTML | connect_de, chip_de, hifitest_de, computerbild_de | [html_fallback.md](html_fallback.md) |
| WAF 突破 | Cloudflare/403 需 Playwright | hwupgrade_it, clubic_fr, tweakers_nl | [waf_playwright.md](waf_playwright.md) |

## 选型决策树

```
有 <script type="application/ld+json">?
├─ YES → 含 @type=Review?
│   ├─ YES → 有 positiveNotes? → jsonld_review (techfi_nl)
│   └─ NO  → @type=Product 有 review? → jsonld_product (techradar_uk)
│           └─ Product 无 review → jsonld_product_only (which_uk, 付费墙)
├─ NO  → html_fallback (connect_de)
│
WAF 拦截?
├─ HTTP 403 → waf_playwright (Playwright尝试突破)
├─ Cloudflare Challenge → 需住宅IP
└─ 付费墙 → needs_human (会员登录态)
```
