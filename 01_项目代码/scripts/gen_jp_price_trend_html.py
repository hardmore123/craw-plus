# -*- coding: utf-8 -*-
"""日本线 kakaku 周度价格趋势 —— HTML 报告生成器。

从数据库 price_shop_snapshot 读取周度聚合时序（db.weekly_price_series），
生成自包含 HTML，每个产品一张折线图：X 轴=周(YYYY-Www)，Y 轴=JPY，
每个渠道一条线，悬停显示渠道/价格/周。当前数据少时为单点/短线，后续
每周采集自动长出曲线。

用法：
    python scripts/gen_jp_price_trend_html.py                     # 全部品牌
    python scripts/gen_jp_price_trend_html.py --brand hisense_jp  # 单品牌
    python scripts/gen_jp_price_trend_html.py --weeks 12           # 最近 12 周
    python scripts/gen_jp_price_trend_html.py --out 自定义路径.html

依赖：无第三方依赖（纯 SVG 折线图，离线可打开）。
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.db import Database                         # noqa: E402
from overseas.price_export import SHOP_COLUMN_ZH         # noqa: E402

# 品牌 code → 展示名（与 service.BRAND_DISPLAY 一致）
BRAND_DISPLAY = {
    "hisense_jp": "Hisense", "sony_jp": "SONY", "regza_jp": "REGZA",
    "panasonic_jp": "Panasonic", "tcl_jp": "TCL", "sharp_jp": "SHARP",
}
BRAND_ORDER = ["Hisense", "SONY", "REGZA", "Panasonic", "TCL", "SHARP"]

# 8 渠道固定配色（色盲友好）
SHOP_COLORS = {
    "エディオンネットショップ": "#e6194b", "ヨドバシ.com": "#3cb44b",
    "ヤマダウェブコム": "#4363d8", "ビックカメラ.com": "#f58231",
    "ケーズデンキ": "#911eb4", "Joshin": "#46f0f0",
    "ノジマオンライン": "#f032e6", "Amazon": "#bfef45",
}


def shop_zh(shop: str) -> str:
    return SHOP_COLUMN_ZH.get(shop, shop)


def fmt_jpy(v) -> str:
    try:
        return f"¥{int(v):,}"
    except (TypeError, ValueError):
        return str(v)


def _svg_chart(weeks: list[str], shops_data: list[dict]) -> str:
    """生成一张 SVG 折线图。shops_data=[{shop, series:{week:price}}]。

    weeks 为完整周次列表（含无数据周，用于断点）。无数据的点留空（断线）。
    """
    if not weeks:
        weeks = ["-"]
    w_px = 760
    h_px = 320
    pad_l, pad_r, pad_t, pad_b = 64, 16, 16, 48
    plot_w = w_px - pad_l - pad_r
    plot_h = h_px - pad_t - pad_b

    # 价格范围
    all_prices = [p for s in shops_data for p in s["series"].values() if p is not None]
    if not all_prices:
        return f'<div class="empty">暂无价格数据</div>'
    pmin = min(all_prices)
    pmax = max(all_prices)
    # 留 10% 上下边距
    span = (pmax - pmin) or 1
    pmin -= span * 0.1
    pmax += span * 0.1
    span = pmax - pmin

    n = len(weeks)
    x_of = lambda i: pad_l + (plot_w * i / max(n - 1, 1))
    y_of = lambda p: pad_t + plot_h * (1 - (p - pmin) / span)

    def x_label(i: int) -> str:
        # 周次多时稀疏标注
        step = max(1, n // 8)
        if i % step == 0 or i == n - 1:
            return weeks[i]
        return ""

    parts = [f'<svg viewBox="0 0 {w_px} {h_px}" class="chart" preserveAspectRatio="xMidYMid meet">']

    # Y 轴网格 + 刻度（4 档）
    for k in range(5):
        gv = pmin + span * k / 4
        gy = y_of(gv)
        parts.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w_px-pad_r}" y2="{gy:.1f}" class="grid"/>')
        parts.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" text-anchor="end" class="axis">{fmt_jpy(gv)}</text>')
    # X 轴刻度
    for i, wk in enumerate(weeks):
        lbl = x_label(i)
        if lbl:
            parts.append(f'<text x="{x_of(i):.1f}" y="{h_px-pad_b+18}" text-anchor="middle" class="axis">{html.escape(lbl)}</text>')

    # 每个渠道一条折线
    for s in shops_data:
        shop = s["shop"]
        color = SHOP_COLORS.get(shop, "#888")
        series = s["series"]
        pts = []
        for i, wk in enumerate(weeks):
            p = series.get(wk)
            if p is not None:
                pts.append((x_of(i), y_of(p), p))
        if not pts:
            continue
        # 折线
        d = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        # 数据点 + tooltip
        parts.append('<g class="dots">')
        for x, y, p in pts:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}">'
                f'<title>{html.escape(shop_zh(shop))} | {html.escape(shop)}'
                f'\n{fmt_jpy(p)}</title></circle>')
        parts.append('</g>')

    parts.append('</svg>')

    # 图例
    legend = '<div class="legend">'
    for s in shops_data:
        shop = s["shop"]
        color = SHOP_COLORS.get(shop, "#888")
        n_pts = sum(1 for v in s["series"].values() if v is not None)
        legend += (f'<span class="lg"><i style="background:{color}"></i>'
                   f'{html.escape(shop_zh(shop))}'
                   f'<small>{n_pts}点</small></span>')
    legend += '</div>'
    return "".join(parts) + legend


HTML_HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>日本线周度价格趋势 - kakaku</title>
<style>
:root{--bg:#fff;--fg:#222;--muted:#888;--line:#e5e7eb;--card:#fafafa}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
  color:var(--fg);background:var(--bg);line-height:1.5}
header{padding:20px 32px;border-bottom:1px solid var(--line);background:#fff}
header h1{margin:0 0 4px;font-size:20px}
header .meta{color:var(--muted);font-size:13px}
nav{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);
  padding:8px 32px;z-index:10;flex-wrap:wrap;display:flex;gap:6px}
nav a{padding:3px 10px;border-radius:6px;text-decoration:none;color:#4363d8;
  font-size:13px;background:#f3f4f6}
nav a:hover{background:#e0e7ff}
main{padding:16px 32px 64px}
section.brand{margin:24px 0 8px;padding-top:12px;border-top:2px solid var(--line)}
section.brand>h2{margin:0 0 12px;font-size:17px}
.product{background:var(--card);border:1px solid var(--line);border-radius:8px;
  padding:14px 16px;margin:12px 0;overflow-x:auto}
.product h3{margin:0 0 4px;font-size:14px;font-weight:600}
.product .pmeta{color:var(--muted);font-size:12px;margin:0 0 8px}
.chart{width:100%;max-width:760px;height:auto}
.axis{font-size:10px;fill:var(--muted)}
.grid{stroke:var(--line);stroke-width:1;stroke-dasharray:3 3}
.legend{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:6px;font-size:12px}
.legend .lg{display:inline-flex;align-items:center;gap:4px}
.legend .lg i{display:inline-block;width:12px;height:12px;border-radius:2px}
.legend .lg small{color:var(--muted);margin-left:2px}
.empty{color:var(--muted);padding:20px;text-align:center}
footer{padding:16px 32px;color:var(--muted);font-size:12px;border-top:1px solid var(--line)}
</style></head><body>"""


def build_html(data: dict, generated: str, weeks_back: int) -> str:
    weeks = data["weeks"]
    products = data["products"]
    # 按品牌分组
    by_brand: dict[str, list] = defaultdict(list)
    for p in products:
        by_brand[p["brand"]].append(p)
    brands = sorted(by_brand.keys(), key=lambda b: BRAND_ORDER.index(b) if b in BRAND_ORDER else 99)

    out = [HTML_HEAD, "<body>"]
    out.append(f'<header><h1>日本线周度价格趋势曲线</h1>'
               f'<div class="meta">数据源：kakaku.com（価格.com）｜'
               f'生成时间：{generated}｜周次范围：{weeks[0] if weeks else "-"} ~ '
               f'{weeks[-1] if weeks else "-"}（共 {len(weeks)} 周）｜'
               f'产品数：{len(products)}｜显示最近 {weeks_back} 周</div></header>')

    # 导航
    out.append('<nav>')
    for b in brands:
        out.append(f'<a href="#brand-{html.escape(b)}">{html.escape(b)} ({len(by_brand[b])})</a>')
    out.append('</nav><main>')

    if not weeks or len(weeks) <= 1:
        out.append('<div class="empty">当前仅有 1 个时间点，曲线需多周数据逐步积累。'
                   '请保持每周执行 weekly_kakaku_price.py 采集。</div>')

    for b in brands:
        out.append(f'<section class="brand" id="brand-{html.escape(b)}"><h2>{html.escape(b)}</h2>')
        for p in by_brand[b]:
            # series: [{week,price}] → {week:price}
            shops_data = []
            for sh in p["shops"]:
                series = {x["week"]: x["price"] for x in sh["series"]}
                shops_data.append({"shop": sh["shop"], "series": series})
            chart = _svg_chart(weeks, shops_data)
            out.append(f'<div class="product"><h3>{html.escape(p["brand"])} {html.escape(p["model"])}</h3>'
                       f'<p class="pmeta">尺寸：{html.escape(p["size"] or "-")}｜'
                       f'product_id：{p["product_id"]}｜渠道数：{len(shops_data)}</p>'
                       f'{chart}</div>')
        out.append('</section>')

    out.append('</main>')
    out.append('<footer>价格趋势曲线由 gen_jp_price_trend_html.py 自动生成｜'
               '渠道名中文映射取自 overseas.price_export.SHOP_COLUMN_ZH</footer>')
    out.append('</body></html>')
    return "".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description="日本线周度价格趋势 HTML 报告生成器")
    p.add_argument("--brand", default="", help="品牌 code（hisense_jp...），缺省全部")
    p.add_argument("--weeks", type=int, default=0, help="最近 N 周（<=0 全部）")
    p.add_argument("--db", help="SQLite 路径，缺省 data/overseas.db")
    p.add_argument("--out", help="输出 HTML 路径，缺省 data/价格趋势_日本_kakaku_时间戳.html")
    args = p.parse_args()

    db_path = args.db or os.path.join("data", "overseas.db")
    db = Database(db_path)
    rows = db.weekly_price_series("kakaku_jp", weeks_back=args.weeks)
    db.close()

    brand_display = BRAND_DISPLAY.get(args.brand, "")
    if brand_display:
        rows = [r for r in rows if r["brand"] == brand_display]

    # 聚合成产品维度
    all_weeks = sorted({r["week"] for r in rows})
    if args.weeks and args.weeks > 0:
        all_weeks = all_weeks[-args.weeks:]
    week_set = set(all_weeks)
    rows = [r for r in rows if r["week"] in week_set]

    prods: dict[int, dict] = {}
    for r in rows:
        pid = r["product_id"]
        pr = prods.setdefault(pid, {
            "product_id": pid, "brand": r["brand"], "model": r["model"],
            "size": r["size"] or "", "shops": {}})
        sh = pr["shops"].setdefault(r["shop"], {"shop": r["shop"], "series": []})
        sh["series"].append({"week": r["week"], "price": r["price"]})
    products = []
    for pr in prods.values():
        shops_out = sorted(pr["shops"].values(), key=lambda x: x["shop"])
        for sh in shops_out:
            sh["series"].sort(key=lambda x: x["week"])
        pr["shops"] = shops_out
        products.append(pr)
    products.sort(key=lambda x: (x["brand"], x["model"]))
    data = {"weeks": all_weeks, "products": products}

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    html_str = build_html(data, generated, args.weeks if args.weeks > 0 else len(all_weeks))

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        tag = f"_{args.brand}" if args.brand else ""
        out_path = PROJECT_ROOT / "data" / f"价格趋势_日本_kakaku{tag}_{stamp}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_str, encoding="utf-8")
    print(f"[OUT] {out_path} | 周次={len(all_weeks)} 产品={len(products)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
