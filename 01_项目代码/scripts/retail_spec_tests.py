"""零售线 RetailSpec P0 验收测试（对齐任务表 P0-1~P0-4）。

用法（Python 3.12）：
    py -3.12 scripts/retail_spec_tests.py

覆盖：
    P0-1  RetailSpec 加载 + L0~L3 校验 + 三个负例（on_no_match=first / 站外URL / 缺review_key）
    P0-2  shops 段多店铺抽取 {店铺名:价} + 列映射 + lowest（kakaku 风格离线 HTML）
    P0-3  price_export 店铺列动态化（multi/single/无 spec 向后兼容）与数据行
    P0-4  match 三段兜底 + reject + 未匹配返回 None（宁缺毋滥）

全部通过时 exit 0，任何一处失败退出码非 0。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILED = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


# ---------------------------------------------------------------- P0-1

def test_p0_1_validation() -> None:
    print("== P0-1 RetailSpec 加载与静态校验 ==")
    from overseas.retail_spec import validate_retail_spec, load_retail_spec

    valid = {
        "retail_spec_version": "0.1",
        "code": "liverpool_mx",
        "base_url": "https://www.liverpool.com.mx",
        "capabilities": ["price", "reviews"],
        "price": {"price": {"selectors": ["h1"]}},
        "reviews": {"container": "div", "fields": {"review_key": {"self_attr": "id"}}},
        "match": {"strategy": "search_then_verify", "on_no_match": "skip",
                  "verify": {"require_model_in": ["sku", "title"]}},
    }
    problems = validate_retail_spec(valid)
    check("合法 spec 问题列表为空", problems == [], str(problems))

    # 负例 1：on_no_match=first → 拒绝
    bad1 = dict(valid)
    bad1["match"] = dict(valid["match"], on_no_match="first")
    p1 = validate_retail_spec(bad1)
    check("负例1: on_no_match=first 被拒绝", any("on_no_match" in p for p in p1), str(p1))

    # 负例 2：站外 URL → 拒绝（防 SSRF）
    bad2 = dict(valid)
    bad2["paginate"] = {"reviews": {"type": "url_page",
                                    "url_template": "https://evil.com/review/{item}/"}}
    p2 = validate_retail_spec(bad2)
    check("负例2: 站外 URL 被拒绝", any("不同源" in p for p in p2), str(p2))

    # 负例 3：缺 review_key → 拒绝
    bad3 = dict(valid)
    bad3["reviews"] = {"container": "div", "fields": {"rating": {}}}
    p3 = validate_retail_spec(bad3)
    check("负例3: 缺 review_key 被拒绝", any("review_key" in p for p in p3), str(p3))

    # 类型/枚举：shops.mode 越界
    bad4 = dict(valid)
    bad4["shops"] = {"mode": "triple_shop"}
    p4 = validate_retail_spec(bad4)
    check("负例4: shops.mode 越界被拒绝", any("shops.mode" in p for p in p4), str(p4))

    # 加载：不存在文件/坏 JSON
    from overseas.retail_spec import load_retail_spec
    try:
        load_retail_spec(ROOT / "no_such_file.retail.json")
        check("load_retail_spec 缺文件报错", False)
    except ValueError:
        check("load_retail_spec 缺文件报错", True)


# ---------------------------------------------------------------- P0-4

def _hit(sku, title="", url=""):
    class _Hit:
        def __init__(self, sku, title, url):
            self.sku, self.title, self.url = sku, title, url
    return _Hit(sku, title, url)


def test_p0_4_match() -> None:
    print("== P0-4 match 段配置化型号匹配 ==")
    from overseas.retail_spec import match_product

    match = {
        "strategy": "search_then_verify", "on_no_match": "skip",
        "verify": {"require_model_in": ["sku", "title"], "allow_core_match": True,
                   "core_strip_leading_size": True, "core_strip_suffix": ["pro", "max"],
                   "min_core_len": 4},
        "reject": {"title_contains_any": ["soporte", "control remoto", "funda"],
                   "url_contains_any": ["/accesorios/"]},
    }
    spec = {"match": match}

    cands = [
        _hit("/tv/hisense-55u6n", "Hisense 55U6N 4K TV"),
        _hit("/tv/soporte-hisense", "Soporte para TV Hisense 55U6N (soporte de pared)"),
        _hit("/tv/control-remoto", "Control remoto Hisense U6N"),
        _hit("/tv/funda", "Funda protectora para Hisense 55U6N"),
        _hit("/tv/hisense-65u6n", "Hisense 65U6N 4K"),
    ]
    hit = match_product(spec, cands, "hisense", "55U6N")
    check("精确匹配只命中目标型号", hit is not None and hit.sku == "/tv/hisense-55u6n",
          getattr(hit, "sku", None))

    cands2 = [c for c in cands if "soporte" in c.title or "control" in c.title or "funda" in c.title]
    hit_rej = match_product(spec, cands2, "hisense", "55U6N")
    check("reject 排除配件后无命中 → None", hit_rej is None,
          getattr(hit_rej, "sku", None))

    cands3 = [_hit("/x/qd8sf", "Hisense QD8SF 55", "/x/qd8sf")]
    hit3 = match_product(spec, cands3, "hisense", "55QD8SF-PRO")
    check("主干命中（55QD8SF-PRO → QD8SF）", hit3 is not None and hit3.sku == "/x/qd8sf",
          getattr(hit3, "sku", None))

    hit4 = match_product(spec, [_hit("/x/other", "TCL C805K 55")], "hisense", "55U6N")
    check("目标不在候选 → None（宁缺毋滥）", hit4 is None, str(hit4))


# ---------------------------------------------------------------- P0-2

_KAKAKU_HTML = """<html><body>
<div class="p-priceTable_row"><a class="p-priceList_shopName"><h3>ヨドバシ.com</h3></a><p class="p-priceList_price">123,000円</p></div>
<div class="p-priceTable_row"><a class="p-priceList_shopName"><h3>エディオンネットショップ</h3></a><p class="p-priceList_price">125,800円</p></div>
<div class="p-priceTable_row"><a class="p-priceList_shopName"><h3>ビックカメラ.com</h3></a><p class="p-priceList_price">127,000円</p></div>
<div class="p-priceTable_row"><a class="p-priceList_shopName"></a><p class="p-priceList_price">99,999円</p></div>
<div class="p-priceTable_row"><a class="p-priceList_shopName"><h3>Amazon</h3></a><p class="p-priceList_price">121,999円</p></div>
</body></html>"""


def _kakaku_spec() -> dict:
    return {
        "code": "kakaku_jp", "base_url": "https://kakaku.com", "capabilities": ["price"],
        "price": {"price": {"selectors": ["h1"]}},
        # match 段是 P0-4 / P3 红线：声明了 price/reviews 能力就必须给出型号匹配规则
        # （on_no_match=skip），否则无法防止型号张冠李戴。真实 kakaku_jp.retail.json
        # 已有该段，本 fixture 原先漏了，导致 P3 修复后本项一直失败。
        "match": {"strategy": "url_template", "on_no_match": "skip",
                  "verify": {"require_model_in": ["sku", "title"]}},
        "shops": {"mode": "multi_shop",
                  "list": {"container": "div.p-priceTable_row",
                           "shop_name": ".p-priceList_shopName",
                           "price": ".p-priceList_price", "limit": 30},
                  "columns": [
                      {"key": "エディオンネットショップ", "display": "爱电王(EDION)", "match": ["エディオン"]},
                      {"key": "ヨドバシ.com", "display": "友都八喜(Yodobashi.com)", "match": ["ヨドバシ"]},
                      {"key": "ヤマダウェブコム", "display": "山田(Yamada)", "match": ["ヤマダ"]},
                      {"key": "ビックカメラ.com", "display": "BIC CAMERA.com", "match": ["ビック"]},
                      {"key": "ケーズデンキ", "display": "K's", "match": ["ケーズ"]},
                      {"key": "Joshin", "display": "上新(Joshin)", "match": ["JOSHIN"]},
                      {"key": "ノジマオンライン", "display": "Nojima", "match": ["ノジマ"]},
                      {"key": "Amazon", "display": "亚马逊(Amazon)", "match": ["AMAZON"]},
                  ]},
    }


def test_p0_2_shops() -> None:
    print("== P0-2 shops 段与多店铺抽取 ==")
    from overseas.fetchers import LxmlDom
    from overseas.retail_spec import (extract_shop_prices, map_shop_columns,
                                      lowest_price, validate_retail_spec)

    spec = _kakaku_spec()
    check("kakaku spec 校验通过", validate_retail_spec(spec) == [],
          str(validate_retail_spec(spec)))

    dom = LxmlDom.parse(_KAKAKU_HTML)
    if dom is None:
        check("lxml 可用（离线样本前置依赖）", False)
        return
    prices = extract_shop_prices(spec, dom)
    check("抽取含 ヨドバシ/エディオン/Amazon", prices.get("ヨドバシ.com") == 123000.0
          and prices.get("エディオンネットショップ") == 125800.0
          and prices.get("Amazon") == 121999.0, str(prices))
    check("无 h3 的小店不混入", 99999.0 not in prices.values(), str(prices))

    mapped = map_shop_columns(spec, prices)
    check("映射到列: ビックカメラ.com=127000", mapped.get("ビックカメラ.com") == 127000.0, str(mapped))
    check("映射到列: Amazon=121999", mapped.get("Amazon") == 121999.0, str(mapped))

    low, low_shop = lowest_price(spec, prices)
    check("最低价 121999 / Amazon", low == 121999.0 and low_shop == "Amazon", f"{low} {low_shop}")

    # single_shop：不抽店铺
    spec_s = {"code": "liverpool_mx", "base_url": "https://www.liverpool.com.mx",
              "capabilities": ["price"], "price": {"price": {"selectors": ["h1"]}},
              "shops": {"mode": "single_shop"}}
    check("single_shop 不抽店铺", extract_shop_prices(spec_s, dom) == {})


# ---------------------------------------------------------------- P0-3

def test_p0_3_export() -> None:
    print("== P0-3 price_export 店铺列动态化 ==")
    from overseas.price_export import (SHOP_COLUMN_NAMES, PriceRecord, build_columns,
                                       COLUMNS, DISPLAY_COLUMNS)

    internal, display = build_columns(None)
    check("无 spec 向后兼容（列逐字一致）", internal == COLUMNS and display == DISPLAY_COLUMNS)
    check("无 spec 列数 7+8+4=19", len(internal) == 19, str(len(internal)))

    multi = build_columns(_kakaku_spec())
    check("multi_shop 列 key 命中日本 8 列", multi[0][7:15] == SHOP_COLUMN_NAMES,
          str(multi[0][7:15]))

    single_spec = {"shops": {"mode": "single_shop"}}
    s_int, s_disp = build_columns(single_spec)
    check("single_shop 简化列 [渠道, 现价]", s_int[7:9] == ["渠道", "现价"], str(s_int))
    check("single_shop 不含日本店铺列", "ヨドバシ" not in s_int[7:], str(s_int))

    rec = PriceRecord(region="Mexico", brand="Hisense", model="55U6N", size="55",
                      currency="MXN", lowest_price=9999.0, channel="Liverpool")
    row = rec.as_row(single_spec)
    check("single 行渠道/现价", row[7] == "Liverpool" and row[8] == 9999.0, str(row))

    rec2 = PriceRecord(region="Japan", brand="Hisense", model="65U8N",
                       lowest_price=123000,
                       shop_prices={"ヨドバシ.com": 123000, "Amazon": 121999})
    row2 = rec2.as_row(_kakaku_spec())
    check("multi 行店铺列取值", row2[8] == 123000 and row2[14] == 121999, str(row2))

    # P0-3 硬验收：真实 kakaku retail spec 导出列与现状 8 个日本店铺列逐字一致
    try:
        from overseas.retail_spec import load_retail_spec
        kspec = load_retail_spec(ROOT / "schemas/retail_specs/kakaku_jp.retail.json")
        k_int, k_disp = build_columns(kspec)
        expect_disp = [DISPLAY_COLUMNS[i] for i in range(7, 15)]
        check("P0-3 验收: kakaku retail spec 列与现状逐字一致",
              k_int[7:15] == SHOP_COLUMN_NAMES and k_disp[7:15] == expect_disp,
              str(k_disp[7:15]))
    except Exception as e:
        check("P0-3 验收: kakaku retail spec 列与现状逐字一致", False, str(e))


# ---------------------------------------------------------------- 阶段0 复用回归

def test_phase0_retail_reuse() -> None:
    """阶段 0（美国 Walmart 复用加拿大零售链）的离线回归。

    覆盖三件容易悄悄坏掉的事：
      1) 商品页抽取分派：只有声明 spec_driven_detail 的站才走 spec 驱动；Amazon
         必须继续走适配器，否则丢掉 amazon_common 的价格区校验（32A4NV 配件价事故）；
      2) 币种按 region 解析：否则美国线价格会被打上 MXN 标签；
      3) Walmart 权威型号与取价护栏：model_candidates 必须被填充（否则详情页型号
         校验退化成宽松子串匹配），且拿不到价格区判定时宁可无价、绝不产出兜底价。
    """
    print("== 阶段0 零售链复用（抽取分派 / 币种 / Walmart 护栏）==")

    # --- 1) 商品页抽取分派 ---
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts"))
    import crawl_ca_retail as ca
    from overseas.sites import SiteRegistry

    spec = {"product": {"title": {"selectors": ["h1"]}},
            "price": {"price": {"selectors": ["h1"]}}}
    check("walmart_us + 抽取段 spec → 走 spec 驱动",
          ca._spec_drives_detail(SiteRegistry.get("walmart_us"), spec) is True)
    check("amazon_us + 同一 spec → 仍走适配器（保住价格区校验）",
          ca._spec_drives_detail(SiteRegistry.get("amazon_us"), spec) is False)
    check("walmart_us 无 spec → 回落适配器",
          ca._spec_drives_detail(SiteRegistry.get("walmart_us"), None) is False)
    check("walmart_us spec 无抽取段 → 回落适配器",
          ca._spec_drives_detail(SiteRegistry.get("walmart_us"), {"match": {}}) is False)

    # --- 2) 币种按 region 解析 ---
    from overseas.mx_retail import resolve_region_currency
    check("us → USD（不再被写成 MXN）", resolve_region_currency("us") == "USD")
    check("ca → CAD", resolve_region_currency("ca") == "CAD")
    check("mx → MXN（原行为不变）", resolve_region_currency("mx") == "MXN")
    check("pe → PEN", resolve_region_currency("pe") == "PEN")
    check("显式入参优先", resolve_region_currency("us", "CAD") == "CAD")

    # --- 3) Walmart 权威型号 + 取价护栏 ---
    from overseas.models import Product, ProductPayload
    from overseas.sites.walmart_common import (enrich_walmart_payload,
                                               extract_models, extract_size,
                                               pick_price_text)

    html = ('<script type="application/ld+json">'
            '{"@type":"Product","name":"Hisense 55 in Class U7 Series 4K QLED TV",'
            '"model":"55U7SG","offers":{"price":"448.00","priceCurrency":"USD"}}'
            '</script><div>Model</div><div>55U7SG</div>')
    models = extract_models(html)
    check("Walmart 权威型号抽取（JSON-LD + 规格表）", "55U7SG" in models, str(models))
    check("Walmart 尺寸抽取", extract_size('Hisense 55" Class 4K TV') == '55"',
          extract_size('Hisense 55" Class 4K TV'))
    check("纯数字 sku 不被当成型号",
          all(not m.isdigit() for m in extract_models(
              '<script type="application/ld+json">{"sku":"123456789"}</script>')))

    payload = ProductPayload(product=Product(
        site_code="walmart_us", sku="1", title='Hisense 55" Class 4K TV'))
    enrich_walmart_payload(payload, dom=None, html=html, url="")
    check("enrich 填入 model_candidates（供详情页精确校验）",
          "55U7SG" in (payload.product.model_candidates or []),
          str(payload.product.model_candidates))
    check("enrich 补尺寸", payload.product.size == '55"', payload.product.size)
    check("非浏览器路径不产出兜底价（缺价 > 错价）", payload.price is None)
    check("拿不到价格区判定时取价为空（保守拒绝）", pick_price_text(None) == "")

    # --- 4) spec 驱动抽取 + enrich 钩子 端到端（用**真实** walmart_us spec，离线 HTML）---
    # 这一步证明：站点代码只留 URL 规则也能跑通「标题/价格/评价/权威型号」全链路。
    from overseas.fetchers import LxmlDom
    from overseas.retail_spec import load_retail_spec

    wspec = load_retail_spec(ROOT / "schemas/retail_specs/walmart_us.retail.json")
    whtml = (
        '<html><body>'
        '<h1 itemprop="name">Hisense 55 in Class U7 Series 4K QLED TV</h1>'
        # 诱饵：推荐位/配件轮播里的价格。绝不能被抓成整机价（32A4NV 事故形态）
        '<div class="similar-items-carousel"><span itemprop="price">9.49</span></div>'
        '<div class="review-card" id="rev-1">'
        '<span class="review-rating">5</span>'
        '<span class="review-text">Great picture quality</span>'
        '</div>'
        '<script type="application/ld+json">'
        '{"@type":"Product","model":"55U7SG",'
        '"offers":{"price":"448.00","priceCurrency":"USD"},'
        '"aggregateRating":{"ratingValue":"4.5","reviewCount":"120"}}'
        '</script></body></html>')
    wdom = LxmlDom.parse(whtml)
    if wdom is None:
        check("lxml 可用（spec 抽取端到端前置依赖）", False)
    else:
        pl = ca._detail_payload(SiteRegistry.get("walmart_us"), wspec, wdom, whtml,
                                "123456789", "https://www.walmart.com/ip/123456789")
        check("spec 驱动抽取到标题", "Hisense" in (pl.product.title or ""),
              pl.product.title)
        check("spec 驱动抽取到价格 448.00（取 JSON-LD 主价）",
              pl.price is not None and pl.price.price == 448.0,
              str(pl.price.price if pl.price else None))
        check("★取价没有抓到推荐位诱饵 9.49（防误抓红线）",
              pl.price is not None and pl.price.price != 9.49,
              str(pl.price.price if pl.price else None))
        check("spec 驱动抽取到评价正文",
              len(pl.reviews) == 1 and "picture" in (pl.reviews[0].body or ""),
              str([r.body for r in pl.reviews]))
        check("spec 驱动抽取到评分汇总",
              pl.summary is not None and pl.summary.total_count == 120,
              str(pl.summary.total_count if pl.summary else None))
        check("enrich 钩子在 spec 路径同样生效（model_candidates）",
              "55U7SG" in (pl.product.model_candidates or []),
              str(pl.product.model_candidates))

        # JSON-LD 无 offers（缺货 / 仅第三方在售）→ CSS 只能是**带护栏**的兜底，
        # 非浏览器路径拿不到祖先链判定，必须留空而不是退回诱饵价。
        whtml2 = (
            '<html><body><h1>Hisense 55 in Class U7 Series 4K QLED TV</h1>'
            '<div class="similar-items-carousel"><span itemprop="price">9.49</span></div>'
            '<div class="price-characteristic"><span>448.00</span></div>'
            '<script type="application/ld+json">'
            '{"@type":"Product","model":"55U7SG"}</script></body></html>')
        wdom2 = LxmlDom.parse(whtml2)
        pl2 = ca._detail_payload(SiteRegistry.get("walmart_us"), wspec, wdom2, whtml2,
                                 "123456789", "https://www.walmart.com/ip/123456789")
        check("JSON-LD 无价时留空（不退回诱饵价，缺价 > 错价）",
              pl2.price is None or pl2.price.price is None,
              str(pl2.price.price if pl2.price else None))


def main() -> None:
    import py_compile
    for f in ("overseas/retail_spec.py", "overseas/price_export.py"):
        py_compile.compile(str(ROOT / f), doraise=True)
        print(f"py_compile {f} OK")

    # 对 schemas/retail_specs/ 下所有真实 spec 跑静态校验
    from overseas.retail_spec import load_retail_spec, validate_retail_spec
    spec_dir = ROOT / "schemas" / "retail_specs"
    if spec_dir.exists():
        for p in sorted(spec_dir.glob("*.retail.json")):
            problems = validate_retail_spec(load_retail_spec(p))
            check(f"真实 spec 校验通过: {p.name}", problems == [], str(problems))
    else:
        print("  (schemas/retail_specs/ 不存在，跳过真实 spec 校验)")

    test_p0_1_validation()
    test_p0_4_match()
    test_p0_2_shops()
    test_p0_3_export()
    test_phase0_retail_reuse()

    if FAILED:
        print(f"\n{len(FAILED)} 个失败: {FAILED}")
        return 1
    print("\n=== 零售线规格自检全部通过 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())