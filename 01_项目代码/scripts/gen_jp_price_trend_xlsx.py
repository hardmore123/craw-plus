# -*- coding: utf-8 -*-
"""日本线 kakaku 周度价格趋势 —— Excel 图表生成器。

每品牌一个 sheet，每产品一块：周次为行、8 渠道为列、末尾插入原生 Excel 折线图。
与现有「价格监控_全部品牌全部机型_kakaku_*.xlsx」宽表风格一致。

用法：
    python scripts/gen_jp_price_trend_xlsx.py                     # 全部品牌
    python scripts/gen_jp_price_trend_xlsx.py --brand hisense_jp
    python scripts/gen_jp_price_trend_xlsx.py --weeks 12
    python scripts/gen_jp_price_trend_xlsx.py --out 自定义路径.xlsx

依赖：openpyxl（requirements.txt 可选依赖）
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.db import Database                         # noqa: E402
from overseas.price_export import SHOP_COLUMN_NAMES, SHOP_COLUMN_ZH  # noqa: E402

BRAND_DISPLAY = {
    "hisense_jp": "Hisense", "sony_jp": "SONY", "regza_jp": "REGZA",
    "panasonic_jp": "Panasonic", "tcl_jp": "TCL", "sharp_jp": "SHARP",
}
BRAND_ORDER = ["Hisense", "SONY", "REGZA", "Panasonic", "TCL", "SHARP"]
# xlsx sheet 名长度限制 31 且禁用部分字符
SHEET_BRAND = {"Hisense": "Hisense", "SONY": "SONY", "REGZA": "REGZA",
               "Panasonic": "Panasonic", "TCL": "TCL", "SHARP": "SHARP"}


def main() -> int:
    p = argparse.ArgumentParser(description="日本线周度价格趋势 Excel 图表生成器")
    p.add_argument("--brand", default="", help="品牌 code，缺省全部")
    p.add_argument("--weeks", type=int, default=0, help="最近 N 周（<=0 全部）")
    p.add_argument("--db", help="SQLite 路径，缺省 data/overseas.db")
    p.add_argument("--out", help="输出 xlsx 路径")
    args = p.parse_args()

    db_path = args.db or os.path.join("data", "overseas.db")
    db = Database(db_path)
    rows = db.weekly_price_series("kakaku_jp", weeks_back=args.weeks)
    db.close()

    brand_display = BRAND_DISPLAY.get(args.brand, "")
    if brand_display:
        rows = [r for r in rows if r["brand"] == brand_display]

    all_weeks = sorted({r["week"] for r in rows})
    if args.weeks and args.weeks > 0:
        all_weeks = all_weeks[-args.weeks:]
    week_set = set(all_weeks)
    rows = [r for r in rows if r["week"] in week_set]

    # 按品牌 → 产品分组
    by_brand: dict[str, dict[int, dict]] = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        pid = r["product_id"]
        pr = by_brand[r["brand"]][pid]
        pr.setdefault("model", r["model"])
        pr.setdefault("size", r["size"] or "")
        pr.setdefault("product_id", pid)
        shops = pr.setdefault("shops", {})
        sh = shops.setdefault(r["shop"], {wk: None for wk in all_weeks})
        sh[r["week"]] = r["price"]

    brands = sorted(by_brand.keys(), key=lambda b: BRAND_ORDER.index(b) if b in BRAND_ORDER else 99)

    # 延迟导入 openpyxl（可选依赖，缺时友好报错）
    try:
        from openpyxl import Workbook
        from openpyxl.chart import LineChart, Reference
        from openpyxl.chart.layout import Layout, ManualLayout
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("[ERROR] 缺少 openpyxl，请运行：pip install openpyxl==3.1.5")
        return 1

    wb = Workbook()
    wb.remove(wb.active)  # 删默认 sheet

    head_fill = PatternFill("solid", fgColor="4363d8")
    head_font = Font(bold=True, color="FFFFFF", size=10)
    title_font = Font(bold=True, size=12, color="222222")
    meta_font = Font(size=9, color="888888")
    thin = Side(style="thin", color="e5e7eb")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    n_weeks = len(all_weeks)
    n_shops = len(SHOP_COLUMN_NAMES)
    # 布局：周次列 + 8 渠道列 = 9 列数据
    data_cols = 1 + n_shops

    for b in brands:
        sheet_name = SHEET_BRAND.get(b, b)[:31] or b[:31]
        ws = wb.create_sheet(sheet_name)
        products = sorted(by_brand[b].values(), key=lambda x: x["model"])

        # 顶部标题
        ws.cell(row=1, column=1, value=f"{b} 周度价格趋势（JPY）").font = title_font
        ws.cell(row=2, column=1,
                value=f"周次范围 {all_weeks[0] if all_weeks else '-'} ~ "
                      f"{all_weeks[-1] if all_weeks else '-'}（{n_weeks} 周）｜"
                      f"产品 {len(products)}｜生成 {datetime.now():%Y-%m-%d}"
                ).font = meta_font

        row = 4
        for pr in products:
            # 产品标题行
            ws.cell(row=row, column=1,
                    value=f"{pr['model']}（尺寸 {pr['size'] or '-'}）").font = Font(bold=True, size=11)
            row += 1
            # 表头：周次 + 8 渠道中文
            headers = ["周次"] + [SHOP_COLUMN_ZH.get(s, s) for s in SHOP_COLUMN_NAMES]
            for c, h in enumerate(headers, 1):
                cell = ws.cell(row=row, column=c, value=h)
                cell.fill = head_fill
                cell.font = head_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                cell.border = border
            row += 1
            # 数据行：每周一行
            data_start_row = row
            for wk in all_weeks:
                ws.cell(row=row, column=1, value=wk).alignment = Alignment(horizontal="center")
                ws.cell(row=row, column=1).border = border
                for ci, shop in enumerate(SHOP_COLUMN_NAMES, 2):
                    v = pr["shops"].get(shop, {}).get(wk)
                    cell = ws.cell(row=row, column=ci, value=v if v is not None else None)
                    if v is not None:
                        cell.number_format = '#,##0'
                    cell.alignment = Alignment(horizontal="right")
                    cell.border = border
                row += 1
            data_end_row = row - 1
            row += 1  # 空行隔开

            # 插入折线图
            if data_end_row >= data_start_row and n_weeks >= 1:
                chart = LineChart()
                chart.title = f"{pr['model']} 价格趋势"
                chart.y_axis.title = "JPY"
                chart.x_axis.title = "周次"
                chart.height = 8
                chart.width = 20
                # 数据：8 渠道列，行=周次
                # Reference(ws, min_col, min_row, max_col, max_row)
                # categories=周次列；series=各渠道列（含表头做图例名）
                data_ref = Reference(ws, min_col=2, max_col=1 + n_shops,
                                     min_row=data_start_row - 1,
                                     max_row=data_end_row)
                cats_ref = Reference(ws, min_col=1, min_row=data_start_row,
                                     max_row=data_end_row)
                chart.add_data(data_ref, titles_from_data=True)
                chart.set_categories(cats_ref)
                # 空值断线
                for s in chart.series:
                    s.smooth = False
                ws.add_chart(chart, f"J{data_start_row - 2}")

        # 列宽
        ws.column_dimensions['A'].width = 12
        for ci in range(2, data_cols + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 16

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now().strftime("%Y%m%d")
        tag = f"_{args.brand}" if args.brand else ""
        out_path = PROJECT_ROOT / "data" / f"价格趋势_日本_kakaku{tag}_{stamp}.xlsx"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out_path))
    print(f"[OUT] {out_path} | 品牌数={len(brands)} 周次={n_weeks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
