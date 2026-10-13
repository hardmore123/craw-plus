# -*- coding: utf-8 -*-
"""把 MediaMarkt / Saturn / MediaWorld（MMS 集团）共享抓取规则写进各国 retail spec。

共享规则来自 mediamarkt_de 实测（2026-10-11，US 出口）：
- 搜索：{base}/<lang>/search.html?query={q}，商品卡片 [data-test='mms-product-card']，
  卡片内链接 [data-test='mms-router-link-product-list-item-link']（href=PDP），
  标题 [data-test='product-title']。
- 价格：JSON-LD（现 jsonld_find_product 已按 canonical 选中当前尺寸变体，不再串价），
  售价 offers.price，划线价 offers.highPrice；DOM 兜底 [data-test='mms-price']。
- 评价：source=mms_graphql（见 overseas/mms_reviews.py），SSR 首页 + 点分页截获。
各站只有 base_url / 语言前缀不同，字段选择器全用语言无关的 data-test，整组通用。
"""
import json, os, re, glob

LANG = {
    "mediamarkt_at": "de", "mediamarkt_be": "nl", "mediamarkt_ch": "de",
    "mediamarkt_de": "de", "mediamarkt_es": "es", "mediamarkt_hu": "hu",
    "mediamarkt_it": "it", "mediamarkt_nl": "nl", "mediamarkt_pl": "pl",
    "mediamarkt_tr": "tr", "saturn_de": "de",
}
# 从 US 出口被反爬拦（403）的站：规则照写，但保留 _block_status，等换出口再实测
BLOCKED_US = {"mediamarkt_be", "saturn_de"}

CARD = "a[data-test='mms-router-link-product-list-item-link']"


def build_search(lang):
    return {
        "container": CARD,
        "sku": {"self_attr": "href"},
        "title": {"selectors": ["[data-test='product-title']"], "self_text": True},
        "url": {"self_attr": "href"},
        "wait_ms": 6000,
        "scroll_passes": 3,
        "search_url_template": "{base}/" + lang + "/search.html?query={q}",
        "batch": {
            "keyword_template": "{brand} tv", "threshold": 40, "force": True,
            "fallback_per_model": False, "max_candidates": 60,
            "max_search_failures": 2, "min_candidates": 3, "retries": 3,
        },
    }


PRICE = {
    # jsonld_first：MMS 的 PDP 第一个 [data-test='mms-price'] 是含保修/套餐价(3899)，
    # 主售价在 JSON-LD offers.price(3299)。必须 JSON-LD 优先，否则 DOM 首价写错价。
    "price": {"jsonld_first": True, "jsonld": "offers.price",
              "selectors": ["[data-test='mms-price']", "[data-test='branded-price']"],
              "transform": "money"},
    "currency": {"jsonld": "offers.priceCurrency",
                 "selectors": ["[itemprop='priceCurrency']"], "attr": "content",
                 "transform": "currency"},
    "in_stock": {"jsonld": "offers.availability",
                 "selectors": ["[itemprop='availability']"], "attr": "content",
                 "transform": "in_stock"},
    "list_price": {"jsonld": "offers.highPrice",
                   "selectors": ["[data-test='mms-strike-price-type-rrp']"],
                   "transform": "money"},
    "raw_text": {"jsonld": "offers.price", "transform": "clean_text"},
}

SUMMARY = {
    "avg_rating": {"jsonld": "aggregateRating.ratingValue",
                   "selectors": ["[itemprop='ratingValue']"], "transform": "rating"},
    "total_count": {"jsonld": ["aggregateRating.reviewCount", "aggregateRating.ratingCount"],
                    "selectors": ["[itemprop='reviewCount']"], "transform": "int"},
}

REVIEWS = {
    "source": "mms_graphql",
    "_note": ("MMS 集团 PWA：评价底层 BazaarVoice，站方自家 GraphQL(GetProductReviews) "
              "包了一层。第1页随 SSR 内联 __PRELOADED_STATE__.apolloState(GraphqlReview 实体)，"
              "第2页起点评价区分页按钮才发请求。自己拼 URL 重放会被 WAF 拦(429/403)，"
              "故 overseas/mms_reviews.py 不重放、只在真实页面点分页截获站方响应。"
              "评价按商品族聚合(reviewProductId 可能是同系列别尺寸)，串尺寸条数记入 "
              "meta.cross_product，来源商品号写进 review_url 锚点 #mms-src-product="),
    "limit": 60,
}

for f in sorted(glob.glob("schemas/retail_specs/mediamarkt_*.retail.json") +
                glob.glob("schemas/retail_specs/saturn_*.retail.json")):
    d = json.load(open(f, encoding="utf-8"))
    code = d["code"]
    lang = LANG.get(code)
    if not lang:
        print("skip (no lang)", code); continue
    caps = set(d.get("capabilities") or [])
    caps.update(["price", "reviews"])
    d["capabilities"] = [c for c in ("price", "reviews") if c in caps] or ["price"]
    d["search"] = build_search(lang)
    # 价格：保留币种 default（各国不同）
    price = dict(PRICE)
    cur = d.get("currency") or (d.get("price", {}).get("currency", {}) or {}).get("default")
    price["currency"] = {**PRICE["currency"], "default": cur or "EUR"}
    d["price"] = price
    d["summary"] = SUMMARY
    rv = dict(REVIEWS)
    d["reviews"] = rv
    # 清掉旧的误判价格可疑标记（根因是 jsonld 串尺寸，已在 extract.py 修复）
    d.pop("_price_suspect", None)
    d.pop("_autofix_search", None)
    # fetch 配置：浏览器 + 等 h1/JSON-LD
    fetch = d.get("fetch") or {}
    fetch.update({"protection": "L2", "requires_browser": True, "detail_http": False,
                  "retail_page_wait": "h1, script[type='application/ld+json']",
                  "nav_timeout_ms": 30000, "max_retries": 3})
    d["fetch"] = fetch
    d["generated_by"] = (str(d.get("generated_by") or "") +
                         " | 2026-10-11 MMS 集团共享规则(mediamarkt_de 实测): "
                         "search.html?query + mms-product-card + jsonld 变体选中 + mms_graphql 评价").strip(" |")
    if code in BLOCKED_US:
        d["_block_status"] = ("2026-10-11 US 出口搜索页 403(反爬)。规则按 mediamarkt_de "
                              "实测同栈写好，待换欧洲出口实测验证。")
    else:
        d.pop("_block_status", None)
    json.dump(d, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("updated", code, "lang=", lang, "blocked_us=" + str(code in BLOCKED_US))
