"""导出 SPEC 系列级成功/空抓取/失败状态。

状态规则：
- success：得到至少一个型号和一行规格；
- empty：请求成功，但没有可用 table/型号/规格行；
- failed：404、其它 HTTP 错误、超时、浏览器/网络异常或解析异常。

状态和型号清单分开输出：empty/failed 系列没有可搜索型号，不生成伪造型号行。

示例：
    python scripts/export_spec_status.py
    python scripts/export_spec_status.py --format all
    python scripts/export_spec_status.py --site hisense_jp --format csv
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from export_spec_models import BRANDS, PROJECT_ROOT, write_csv, write_json, write_jsonl, write_xlsx

sys.path.insert(0, str(PROJECT_ROOT))
from overseas.spec_identity import display_series_name

DEFAULT_DB = PROJECT_ROOT / "data" / "overseas.db"
STATUS_COLUMNS = [
    "brand_code",
    "brand_name",
    "series",
    "status",
    "status_source",
    "captured_week",
    "requested_url",
    "selected_url",
    "attempted_urls",
    "series_id",
    "run_id",
    "model_expected",
    "model_ok",
    "model_empty",
    "model_failed",
    "row_count",
    "error_kind",
    "status_message",
    "finished_at",
]


def _sites_clause(sites: Iterable[str]) -> tuple[str, tuple[str, ...]]:
    values = tuple(sites)
    return ",".join("?" for _ in values), values


def _models_count(raw: Any) -> int:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, json.JSONDecodeError):
        return 0
    if not isinstance(values, list):
        return 0
    return len({str(value).strip() for value in values if str(value).strip()})


def load_status_rows(conn: sqlite3.Connection, sites: Iterable[str]) -> list[dict[str, Any]]:
    placeholders, params = _sites_clause(sites)
    result: dict[tuple[str, str], dict[str, Any]] = {}

    try:
        latest_sql = f"""
            SELECT st.*
            FROM spec_series_status AS st
            JOIN (
                SELECT brand, series, MAX(id) AS id
                FROM spec_series_status
                WHERE brand IN ({placeholders})
                GROUP BY brand, series
            ) AS latest ON latest.id = st.id
            ORDER BY st.brand, st.series
        """
        for row in conn.execute(latest_sql, params).fetchall():
            result[(row["brand"], row["series"])] = {
                "brand_code": row["brand"],
                "brand_name": row["brand_name"] or row["brand"],
                "series": display_series_name(row["series"]),
                "status": row["status"],
                "status_source": row["status_source"] or "crawl",
                "captured_week": row["captured_week"] or "",
                "requested_url": row["requested_url"] or "",
                "selected_url": row["selected_url"] or "",
                "attempted_urls": row["attempted_urls"] or "[]",
                "series_id": row["series_id"] or "",
                "run_id": row["run_id"] or "",
                "model_expected": row["model_expected"] or 0,
                "model_ok": row["model_ok"] or 0,
                "model_empty": row["model_empty"] or 0,
                "model_failed": row["model_failed"] or 0,
                "row_count": row["row_count"] or 0,
                "error_kind": row["error_kind"] or "",
                "status_message": row["message"] or "",
                "finished_at": row["finished_at"] or "",
            }
    except sqlite3.OperationalError:
        # 旧数据库在首次通过 Database.init_schema 前还没有状态表。
        pass

    # 旧库中已经成功写入 spec_series、但没有状态历史的系列，明确标为 legacy success。
    series_sql = f"""
        SELECT s.id, s.brand, s.brand_name, s.series, s.url, s.models,
               s.last_seen,
               MAX(r.captured_week) AS latest_week
        FROM spec_series AS s
        LEFT JOIN spec_row AS r ON r.series_id = s.id
        WHERE s.brand IN ({placeholders})
        GROUP BY s.id, s.brand, s.brand_name, s.series, s.url, s.models, s.last_seen
        ORDER BY s.brand, s.series
    """
    for row in conn.execute(series_sql, params).fetchall():
        key = (row["brand"], row["series"])
        if key in result:
            continue
        latest_week = row["latest_week"] or ""
        row_count = 0
        if latest_week:
            row_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM spec_row WHERE series_id=? AND captured_week=?",
                    (row["id"], latest_week),
                ).fetchone()[0]
            )
        model_count = _models_count(row["models"])
        result[key] = {
            "brand_code": row["brand"],
            "brand_name": row["brand_name"] or row["brand"],
            "series": display_series_name(row["series"]),
            "status": "success",
            "status_source": "legacy",
            "captured_week": latest_week,
            "requested_url": row["url"] or "",
            "selected_url": row["url"] or "",
            "attempted_urls": "[]",
            "series_id": row["id"],
            "run_id": "",
            "model_expected": model_count,
            "model_ok": model_count,
            "model_empty": 0,
            "model_failed": 0,
            "row_count": row_count,
            "error_kind": "",
            "status_message": "历史数据未记录系列状态，按已有有效 SPEC 标记为 success",
            "finished_at": row["last_seen"] or "",
        }

    # 按固定品牌顺序和系列排序，保证 CSV/XLSX 每次输出稳定。
    brand_order = {brand: index for index, brand in enumerate(BRANDS)}
    rows = list(result.values())
    rows.sort(key=lambda item: (brand_order.get(item["brand_code"], 999), item["series"]))
    return rows


def output_paths(out: str | None, output_format: str) -> dict[str, Path]:
    extensions = {"csv": ".csv", "xlsx": ".xlsx", "json": ".json", "jsonl": ".jsonl"}
    if out:
        base = Path(out)
    else:
        base = PROJECT_ROOT / "data" / f"SPEC_系列状态_{datetime.now():%Y%m%d}.csv"
    if output_format == "all":
        if base.suffix.lower() in extensions.values():
            base = base.with_suffix("")
        return {name: base.with_suffix(ext) for name, ext in extensions.items() if name != "jsonl"}
    suffix = extensions[output_format]
    if base.suffix.lower() != suffix:
        base = base.with_suffix(suffix) if base.suffix else Path(str(base) + suffix)
    return {output_format: base}


def write_outputs(paths: dict[str, Path], rows: list[dict[str, Any]]) -> None:
    for output_format, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "csv":
            write_csv(path, rows, STATUS_COLUMNS)
        elif output_format == "xlsx":
            write_xlsx(path, rows, STATUS_COLUMNS)
        elif output_format == "json":
            write_json(path, rows)
        elif output_format == "jsonl":
            write_jsonl(path, rows)
        print(f"[OUT] {output_format}: {path} rows={len(rows)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出 SPEC 系列级 success/empty/failed 状态")
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite 数据库路径，默认 {DEFAULT_DB}")
    parser.add_argument("--site", action="append",
                        help="只输出指定品牌 code，可重复；默认全部日本六品牌")
    parser.add_argument("--format", choices=("csv", "xlsx", "json", "jsonl", "all"), default="csv")
    parser.add_argument("--out", help="输出文件路径；--format all 时作为文件名主干")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sites = tuple(args.site or BRANDS)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 数据库不存在: {db_path}")
        return 2
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = load_status_rows(conn, sites)
    finally:
        conn.close()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"[SPEC-STATUS] brands={len(sites)} series={len(rows)} counts={counts}")
    write_outputs(output_paths(args.out, args.format), rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
