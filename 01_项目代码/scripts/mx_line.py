"""墨西哥（AM 北美洲）TV 线统一入口脚本。

数据隔离：默认用独立数据库 data/mx/overseas_mx.db、独立产物目录 data/mx/，
不与日本线（data/overseas.db）或其它线数据重叠。通过在导入 overseas 之前设置
OVERSEAS_DB_PATH / OVERSEAS_DATA_DIR 环境变量实现（config 读这两个 env）。

执行顺序（先 SPEC 后价格/网评）：
    1) spec-crawl  抓 4 品牌官网规格入独立库
    2) spec-export 导出各品牌 SPEC 宽表
    3) models      从库汇总墨西哥型号全集（价格/网评线的输入）
    4) retail      按「型号 × 启用零售站」同步抓价格 + 网评并导出

用法（固定 Python 见项目总说明）：
    $py = 'C:\\Users\\likunyuan\\AppData\\Local\\Programs\\Python\\Python312\\python.exe'
    & $py scripts\\mx_line.py spec-crawl --site hisense_mx --series <系列>
    & $py scripts\\mx_line.py spec-crawl                       # 全部 4 品牌
    & $py scripts\\mx_line.py spec-export --site hisense_mx
    & $py scripts\\mx_line.py models
    & $py scripts\\mx_line.py retail --site liverpool_mx --models 55U6N
    & $py scripts\\mx_line.py retail --save-db                 # 全部启用零售站 + 入库

强防护零售站（amazon_mx / walmart_mx）默认在 regions_config 里 enabled=False，
不纳入 retail 批量；单独验证时用 --site amazon_mx 显式指定。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# ---- 数据隔离：在导入 overseas 之前把库与产物目录指到 data/墨西哥/ ----
# R1-6 输出归国：新产物统一落 data/墨西哥/（与 CA/US 线目录结构一致）。
# 数据库沿用 data/mx/overseas_mx.db（历史库位置不动，避免破坏既有状态表）；
# 仅将导出产物目录指到中文国家目录；若创建失败（只读等）回退旧 data/mx/。
MX_DATA_DIR = PROJECT_ROOT / "data" / "墨西哥"
os.environ.setdefault("OVERSEAS_DATA_DIR", str(MX_DATA_DIR))
os.environ.setdefault("OVERSEAS_DB_PATH", str(PROJECT_ROOT / "data" / "mx" / "overseas_mx.db"))

sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                                    # noqa: E402
from overseas.db import Database                               # noqa: E402
from overseas.regions_config import get_region                 # noqa: E402
from overseas.sites import SiteRegistry                        # noqa: E402

REGION = "mx"


def _p(*a):
    print(*a, flush=True)


def _region():
    r = get_region(REGION)
    if r is None:
        raise SystemExit(f"regions_config 中缺少 {REGION} 线")
    return r


def _spec_site_codes(only: list[str] | None) -> list[str]:
    codes = _region().spec_site_codes()
    if only:
        want = {c.strip() for c in only}
        codes = [c for c in codes if c in want]
    return codes


# ---------------------------------------------------------------- spec-crawl
def cmd_spec_crawl(args) -> int:
    from overseas.scenarios import spec_crawl
    config.ensure_dirs()
    codes = _spec_site_codes(args.site)
    if not codes:
        _p("无匹配的 SPEC 站点")
        return 2
    rc = 0
    with Database(config.DB_PATH) as db:
        db.init_schema()
        for code in codes:
            _p(f"\n===== SPEC 采集 {code} =====")
            try:
                st = spec_crawl(code, only_series=args.series, db=db)
                _p(f"完成: {st.summary()}")
                if st.fail and not st.ok:
                    rc = 1
            except Exception as e:
                _p(f"[ERROR] {code}: {type(e).__name__}: {e}")
                rc = 1
    return rc


# ---------------------------------------------------------------- spec-export
def cmd_spec_export(args) -> int:
    from overseas import spec_export
    config.ensure_dirs()
    codes = _spec_site_codes(args.site)
    if not codes:
        _p("无匹配的 SPEC 站点")
        return 2
    ts = datetime.now().strftime("%Y%m%d")
    with Database(config.DB_PATH) as db:
        db.init_schema()
        for code in codes:
            ext = "xlsx" if args.format == "xlsx" else "csv"
            out = args.out or str(MX_DATA_DIR / f"SPEC_{code}_{ts}.{ext}")
            rel_path = str(MX_DATA_DIR / f"发售日_{code}.json")
            release_map = spec_export.load_release_map(
                rel_path if os.path.exists(rel_path) else None)
            try:
                if args.format == "xlsx":
                    n = spec_export.export_xlsx(db, code, out, release_map)
                else:
                    n = spec_export.export_csv(db, code, out, release_map)
                _p(f"[OUT] {code}: {n} 行 → {out}")
            except Exception as e:
                _p(f"[ERROR] 导出 {code} 失败: {type(e).__name__}: {e}")
    return 0


# ---------------------------------------------------------------- spec-register
def cmd_spec_register(args) -> int:
    """型号登记：调各 SPEC 站 series_entries() 抓型号清单，仅把「系列+型号」写入
    spec_series（models 字段，不含规格行），让规格 React 异步渲染、规格入不了库的
    品牌（TCL/Samsung/LG）型号仍能进入型号全集清单，供价格/网评线使用。

    这是「先跑通全链路」策略的关键补充：Hisense 走 spec-crawl 带规格入库；
    TCL/Samsung/LG 走本命令登记型号（规格详表后续接 param 接口再补）。
    replace-current 只精确替换当前型号列表，不删除已有本周规格行，避免登记步骤
    覆盖 Hisense 等站点已经抓到的规格；历史周数据始终保留。
    只用 db.save_spec_sheet 现有方法和独立 MX 数据库，不影响其它线。
    """
    from overseas.scenarios import make_fetcher, open_dom
    from overseas.models import SpecSheet
    from datetime import datetime as _dt
    config.ensure_dirs()
    codes = _spec_site_codes(args.site)
    if not codes:
        _p("无匹配的 SPEC 站点")
        return 2
    week = _iso_week()
    replace_current = bool(getattr(args, "replace_current", False))
    with Database(config.DB_PATH) as db:
        db.init_schema()
        for code in codes:
            adapter = SiteRegistry.get(code)
            if not getattr(adapter, "supports_spec", False):
                continue
            fetcher = make_fetcher(adapter)

            def _open(url, wait=""):
                return open_dom(adapter, fetcher, url, wait_selector=wait)

            try:
                entries = adapter.series_entries(_open) or []
            except Exception as e:
                _p(f"[ERROR] {code} series_entries: {type(e).__name__}: {e}")
                fetcher.close()
                continue
            fetcher.close()
            if not entries:
                _p(f"[ERROR] {code}: 入口未返回任何型号，跳过 --replace-current，保留当前快照")
                continue
            n_series = n_models = 0
            current_series: set[str] = set()
            for series, urls in entries:
                models = list(dict.fromkeys(
                    m for m in (adapter.model_from_url(u) for u in urls) if m))
                if not models:
                    continue
                current_series.add(series)
                sheet = SpecSheet(brand=adapter.code, brand_name=adapter.name,
                                  series=series, url=urls[0] if urls else "",
                                  models=models)
                try:
                    if not replace_current:
                        db.save_spec_sheet(sheet, week, replace_week=False)
                    else:
                        # 登记只更新入口型号快照，不用空 sheet 覆盖本周已有规格。
                        # 先让 save_spec_sheet 建立/更新系列，再把 models 精确替换
                        # （而非合并旧型号），最后裁剪本周规格行中的旧型号值。
                        db.save_spec_sheet(sheet, week, replace_week=False)
                        db.conn.execute(
                            "UPDATE spec_series SET models=? WHERE brand=? AND series=?",
                            (json.dumps(models, ensure_ascii=False), adapter.code, series),
                        )
                        row = db.conn.execute(
                            "SELECT id FROM spec_series WHERE brand=? AND series=?",
                            (adapter.code, series),
                        ).fetchone()
                        if row:
                            model_set = set(models)
                            spec_rows = db.conn.execute(
                                "SELECT id, values_json FROM spec_row "
                                "WHERE series_id=? AND captured_week=?",
                                (row["id"], week),
                            ).fetchall()
                            for spec_row in spec_rows:
                                try:
                                    values = json.loads(spec_row["values_json"] or "{}")
                                except (TypeError, json.JSONDecodeError):
                                    continue
                                if not isinstance(values, dict):
                                    continue
                                filtered = {k: v for k, v in values.items() if k in model_set}
                                if filtered != values:
                                    db.conn.execute(
                                        "UPDATE spec_row SET values_json=? WHERE id=?",
                                        (json.dumps(filtered, ensure_ascii=False), spec_row["id"]),
                                    )
                        db.conn.commit()
                    n_series += 1
                    n_models += len(models)
                except Exception as e:
                    _p(f"[WARN] {code}/{series} 登记失败: {type(e).__name__}: {e}")

            # 当前入口快照替换是非破坏性的：旧系列保留历史规格行，但把当前周的
            # models 清空，避免已下架/非电视型号继续进入 models 汇总。
            cleared = 0
            if replace_current:
                old_rows = db.conn.execute(
                    "SELECT series, brand_name, url FROM spec_series WHERE brand=?",
                    (adapter.code,),
                ).fetchall()
                for old in old_rows:
                    if old["series"] in current_series:
                        continue
                    empty = SpecSheet(
                        brand=adapter.code,
                        brand_name=old["brand_name"] or adapter.name,
                        series=old["series"],
                        url=old["url"] or "",
                        models=[],
                    )
                    db.save_spec_sheet(empty, week, replace_week=True)
                    cleared += 1
            suffix = "，清空旧系列 " + str(cleared) if replace_current else ""
            _p(f"[REGISTER] {code}: 系列 {n_series}，型号 {n_models}（{week}）{suffix}")
    return 0


def _iso_week(dt=None) -> str:
    from datetime import datetime
    d = dt or datetime.now()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ---------------------------------------------------------------- models
def _normalize_model(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").upper()
    return re.sub(r"[^A-Z0-9]+", "", text)


def cmd_models(args) -> int:
    """从墨西哥独立库汇总型号全集（价格/网评线输入）。复用 export_spec_models 的
    解析与写出函数，仅把品牌换成墨西哥 4 品牌。"""
    import sqlite3
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import export_spec_models as esm                       # 复用其解析/写出

    brands = _region().brand_codes()
    db_path = Path(config.DB_PATH)
    if not db_path.exists():
        _p(f"[ERROR] 墨西哥库不存在: {db_path}（先跑 spec-crawl）")
        return 2
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        occurrences, series_count = esm.load_series_rows(conn, brands)
    finally:
        conn.close()
    aggregates = esm.aggregate_occurrences(occurrences)
    rows = esm.public_rows(aggregates, args.include_duplicates)
    out = args.out or str(MX_DATA_DIR / f"SPEC_型号汇总_MX_{datetime.now():%Y%m%d}.csv")
    paths = esm.output_paths(out, args.format)
    esm.write_outputs(paths, rows, args.include_duplicates)
    _p(f"[MODELS] brands={len(brands)} series={series_count} "
       f"models={len(aggregates)}")
    return 0


# ---------------------------------------------------------------- retail
def _load_models_for_retail(args) -> list[dict]:
    """取价格/网评线的型号输入：优先 --models-file / --models，否则从库汇总。"""
    if args.models:
        return [{"model_raw": m, "brand_code": "", "brand_name": ""}
                for m in args.models]
    if args.models_file:
        import csv
        out: list[dict] = []
        with open(args.models_file, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                out.append({"model_raw": r.get("model_raw") or r.get("model") or "",
                            "brand_code": r.get("brand_code") or "",
                            "brand_name": r.get("brand_name") or ""})
        return [m for m in out if m["model_raw"]]
    # 从库汇总（复用 export_spec_models）
    import sqlite3
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    import export_spec_models as esm
    db_path = Path(config.DB_PATH)
    if not db_path.exists():
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        occ, _ = esm.load_series_rows(conn, _region().brand_codes())
    finally:
        conn.close()
    agg = esm.aggregate_occurrences(occ)
    out = []
    for a in agg:
        raw0 = (a["model_raw"].split(" | ")[0] if a["model_raw"] else "")
        out.append({"model_raw": raw0, "brand_code": a["brand_code"],
                    "brand_name": a["brand_name"]})
    return [m for m in out if m["model_raw"]]


def cmd_retail(args) -> int:
    from overseas import mx_retail
    from overseas.retail_spec import load_retail_spec
    config.ensure_dirs()
    models = _load_models_for_retail(args)
    # --brand 补品牌（--models/--models-file 未带 brand 时用，供 search_keyword_template 拼 品牌+型号）
    if args.brand and models:
        for m in models:
            if not m.get("brand_code"):
                m["brand_code"] = args.brand
            if not m.get("brand_name"):
                m["brand_name"] = args.brand
    if args.limit_models and args.limit_models > 0:
        models = models[: args.limit_models]
    if not models:
        _p("无型号输入：先跑 spec-crawl + models，或用 --models / --models-file")
        return 2
    sites = args.site or None
    retail_spec = None
    if args.spec:
        retail_spec = load_retail_spec(args.spec)
        _p(f"[RETAIL] 使用 RetailSpec 配置化匹配: {args.spec}")
    _p(f"[RETAIL] 型号 {len(models)} 个 × 零售站 "
       f"{sites or _region().retail_site_codes(only_enabled=True)}")

    db = None
    if args.save_db:
        db = Database(config.DB_PATH)
        db.init_schema()
    try:
        rows = mx_retail.crawl_region_retail(
            REGION, models, sites=sites, want_reviews=not args.no_reviews,
            review_pages=args.review_pages,
            max_reviews=getattr(args, "max_reviews", None),
            db=db, save_db=args.save_db,
            retail_spec=retail_spec, verbose=True)
    finally:
        if db is not None:
            db.close()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    price_base = MX_DATA_DIR / f"价格监控_MX_{ts}"
    review_base = MX_DATA_DIR / f"网评汇总_MX_{ts}"

    # 价格导出（先 CSV 后 XLSX，XLSX 失败不影响 CSV；模板对齐日本线 price_export）
    np = mx_retail.write_mx_price_csv(str(price_base) + ".csv", rows,
                                      retail_spec=retail_spec)
    _p(f"[OUT] 价格 CSV: {price_base}.csv rows={np}")
    try:
        mx_retail.write_mx_price_xlsx(str(price_base) + ".xlsx", rows,
                                      retail_spec=retail_spec)
        _p(f"[OUT] 价格 XLSX: {price_base}.xlsx")
    except Exception as e:
        _p(f"[WARN] 价格 XLSX 跳过（{type(e).__name__}），CSV 已生成")

    # 网评导出（复用通用 20 列模板，AI 三列空）
    from overseas import review_export
    recs = mx_retail.rows_to_review_records(rows)
    nr = review_export.write_csv(str(review_base) + ".csv", recs)
    _p(f"[OUT] 网评 CSV: {review_base}.csv rows={nr}")
    try:
        review_export.write_xlsx(str(review_base) + ".xlsx", recs)
        _p(f"[OUT] 网评 XLSX: {review_base}.xlsx")
    except Exception as e:
        _p(f"[WARN] 网评 XLSX 跳过（{type(e).__name__}），CSV 已生成")

    ok = sum(1 for r in rows if r.status == "ok")
    _p(f"[RETAIL] 完成：记录 {len(rows)} 条，ok={ok}，"
       f"价格 {np} 行，网评 {nr} 行")
    return 0


# ---------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="mx_line",
                                 description="墨西哥 TV 线统一入口（数据隔离到 data/mx/）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("spec-crawl", help="抓 4 品牌官网 SPEC 入独立库")
    s.add_argument("--site", action="append", help="限定品牌站点，如 hisense_mx，可多次")
    s.add_argument("--series", action="append", help="只抓指定系列（调试），可多次")
    s.set_defaults(func=cmd_spec_crawl)

    s = sub.add_parser("spec-export", help="导出 SPEC 宽表到 data/mx/")
    s.add_argument("--site", action="append", help="限定品牌站点，可多次")
    s.add_argument("--format", choices=["csv", "xlsx"], default="xlsx")
    s.add_argument("--out", help="单站点导出时的输出路径")
    s.set_defaults(func=cmd_spec_export)

    s = sub.add_parser("spec-register",
                       help="型号登记：抓型号清单入库(规格异步渲染的品牌用,型号仍进全集)")
    s.add_argument("--site", action="append", help="限定品牌站点，可多次")
    s.add_argument("--replace-current", action="store_true",
                   help="按本次官网入口替换当前品牌快照；旧系列保留历史但不再进入当前型号汇总")
    s.set_defaults(func=cmd_spec_register)

    s = sub.add_parser("models", help="汇总墨西哥型号全集（价格/网评线输入）")
    s.add_argument("--format", choices=["csv", "xlsx", "json", "jsonl", "all"],
                   default="csv")
    s.add_argument("--out")
    s.add_argument("--include-duplicates", action="store_true")
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("retail", help="型号 × 零售站 同步抓取价格+网评并导出")
    s.add_argument("--site", action="append",
                   help="限定零售站 code（如 liverpool_mx），可多次；缺省=全部启用站")
    s.add_argument("--models", action="append", help="直接指定型号，可多次")
    s.add_argument("--models-file", help="型号清单 CSV（含 model_raw/brand_code 列）")
    s.add_argument("--brand", help="品牌（--models 未带品牌时补充，如 Hisense）")
    s.add_argument("--limit-models", type=int, default=0, help="只取前 N 个型号（调试）")
    s.add_argument("--review-pages", type=int, default=2, help="独立评价页翻页上限")
    s.add_argument("--max-reviews", type=int, default=None,
                   help="每型号每站最多取多少条评价（含翻页累积）。"
                        "缺省按 spec.paginate.reviews.max_reviews > 环境变量 "
                        "OVERSEAS_MAX_REVIEWS > 默认 100 解析")
    s.add_argument("--no-reviews", action="store_true", help="只抓价格不抓评价")
    s.add_argument("--save-db", action="store_true", help="同时入独立库并写状态")
    s.add_argument("--spec", help="RetailSpec JSON 路径；传入时匹配走配置化 match_product")
    s.set_defaults(func=cmd_retail)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        _p("\n已中断")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
