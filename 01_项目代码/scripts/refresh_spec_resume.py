"""SPEC 定向续跑编排器（阶段一：自动补抓未成功系列）。

背景：批处理 refresh_spec.py 对每个品牌有外层超时（默认 1800s），大品牌
（Hisense/Samsung/LG）常被中途终止，留下一批 pending/failed 系列。过去靠人工
读数据库、拼 --series 清单再手动续跑。本脚本把该流程固化：

    1. 读每个目标品牌"最近一次入口审计"（spec_entry_audit.details_json）作为
       应抓系列全集（内部键；Samsung 含 [family_id=...] 后缀，避免同名覆盖）。
    2. 读该品牌"按 (brand, series) 取最新一条状态"的成功集合。
    3. 全集 - 成功集合 = 本轮待续抓系列，逐品牌用
       `overseas.cli spec-crawl --site <code> --series ...` 定向续跑。
    4. 每个品牌可多轮（--max-rounds），直到无 pending 或不再收敛。

设计约束：
    - 只做 SPEC 续抓，不导出、不跑价格/网评（导出交给 refresh_spec.py --export-only）。
    - 不改数据库、不改现有适配器；只调用既有 CLI。
    - series 键直接用入口审计里的原样字符串（含 family 后缀），与
      overseas/spec_identity.family_series_key 的写入口径一致。
    - 单品牌 spec-crawl 不设外层超时（续抓本身就是为绕开批处理超时）；
      如需保护，用 --per-brand-timeout 显式指定。

用法：
    py -3.12 scripts/refresh_spec_resume.py --region ca --db data/overseas.db
    py -3.12 scripts/refresh_spec_resume.py --site samsung_ca --site lg_ca --db data/overseas.db
    py -3.12 scripts/refresh_spec_resume.py --region ca --dry-run      # 只列待抓清单不执行
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _path_arg(value: str | None, default: Path) -> Path:
    if not value:
        return default.resolve()
    p = Path(value).expanduser()
    return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()


def _region_codes(region_code: str) -> list[str]:
    """取某区域线的 SPEC 品牌 code 列表。"""
    try:
        from overseas.regions_config import get_region
    except Exception as exc:  # pragma: no cover - 仅在导入异常时触发
        print(f"[FAIL] 无法加载区域配置: {type(exc).__name__}: {exc}", flush=True)
        return []
    region = get_region(region_code)
    if not region:
        return []
    # SPEC 品牌以 spec_sites 为准（其 site==品牌 code）。
    return list(region.spec_site_codes())


def _entry_series(con: sqlite3.Connection, brand: str) -> tuple[int | None, list[str]]:
    """返回 (最近入口审计 run_id, 应抓系列内部键列表)。

    内部键取 details_json.series[].series；Samsung 等带 family 的入口，其
    series 字段在审计里就是官网展示名，需要补 [family_id=...] 后缀才能与
    spec_series/spec_series_status 的写入键一致。
    """
    row = con.execute(
        "SELECT run_id, details_json FROM spec_entry_audit "
        "WHERE brand=? ORDER BY id DESC LIMIT 1",
        (brand,),
    ).fetchone()
    if row is None:
        return None, []
    try:
        details = json.loads(row["details_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        details = {}
    entries = details.get("series") if isinstance(details, dict) else None
    if not isinstance(entries, list):
        return row["run_id"], []

    try:
        from overseas.spec_identity import family_series_key
    except Exception:
        family_series_key = None  # type: ignore

    keys: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        series = str(entry.get("series") or "").strip()
        if not series:
            continue
        family_id = str(entry.get("family_id") or "").strip()
        if family_id and family_series_key is not None:
            key = family_series_key(series, family_id)
        else:
            key = series
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return row["run_id"], keys


def _success_series(con: sqlite3.Connection, brand: str) -> set[str]:
    """该品牌"按 (brand, series) 取最新一条状态"为 success 的系列内部键集合。

    与 export_spec_status.py 的 MAX(id) 口径一致：跨多次 run 合并，只要该系列
    最新状态是 success 即视为已完成，无需重抓。
    """
    rows = con.execute(
        """
        SELECT st.series AS series, st.status AS status
        FROM spec_series_status AS st
        JOIN (
            SELECT brand, series, MAX(id) AS id
            FROM spec_series_status
            WHERE brand=?
            GROUP BY brand, series
        ) AS latest ON latest.id = st.id
        """,
        (brand,),
    ).fetchall()
    return {str(r["series"]) for r in rows if r["status"] == "success"}


def _pending_for_brand(con: sqlite3.Connection, brand: str) -> tuple[list[str], dict]:
    """返回该品牌本轮待续抓系列内部键列表 + 诊断信息。"""
    run_id, entry_keys = _entry_series(con, brand)
    success = _success_series(con, brand)
    pending = [key for key in entry_keys if key not in success]
    info = {
        "audit_run_id": run_id,
        "entry_total": len(entry_keys),
        "success_total": len([k for k in entry_keys if k in success]),
        "pending_total": len(pending),
        "has_audit": run_id is not None,
    }
    return pending, info


def _run_crawl(db: Path, brand: str, series_keys: list[str], env: dict[str, str],
               timeout: float | None) -> int:
    command = [sys.executable, "-u", "-m", "overseas.cli", "--db", str(db),
               "spec-crawl", "--site", brand]
    for key in series_keys:
        command.extend(["--series", key])
    print(f"\n[RUN] spec-crawl --site {brand} （{len(series_keys)} 个系列续抓）", flush=True)
    try:
        completed = subprocess.run(command, cwd=ROOT, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {brand} 续抓超过 {timeout:.0f}s，已终止", flush=True)
        return 124
    return completed.returncode


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="SPEC 定向续跑：自动补抓各品牌未成功的系列（不导出、不跑价格/网评）")
    ap.add_argument("--site", action="append",
                    help="只续抓指定品牌 code，可重复；与 --region 二选一，--site 优先")
    ap.add_argument("--region", default="",
                    help="区域线（如 ca/us/mx/jp），续抓该线全部 SPEC 品牌")
    ap.add_argument("--db", help="SQLite 路径，缺省 OVERSEAS_DB_PATH 或 data/overseas.db")
    ap.add_argument("--max-rounds", type=int, default=2,
                    help="每个品牌最多续抓轮次（默认 2）；轮间若 pending 不减少则提前停止")
    ap.add_argument("--per-brand-timeout", type=float, default=0.0,
                    help="单品牌单轮续抓超时秒数；0=不限时（默认，续抓本就为绕开批处理超时）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只打印各品牌待续抓系列，不实际执行")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.site:
        brands = list(dict.fromkeys(args.site))
    elif args.region:
        brands = _region_codes(args.region.strip().lower())
        if not brands:
            print(f"[FAIL] 未知或空的区域: {args.region}", flush=True)
            return 1
    else:
        print("[FAIL] 需指定 --site 或 --region", flush=True)
        return 1

    db = _path_arg(args.db, Path(os.environ.get("OVERSEAS_DB_PATH") or ROOT / "data" / "overseas.db"))
    if not db.is_file():
        print(f"[FAIL] 数据库不存在: {db}", flush=True)
        return 1

    env = os.environ.copy()
    env.setdefault("OVERSEAS_NAV_TIMEOUT", "60")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    timeout = args.per_brand_timeout if args.per_brand_timeout and args.per_brand_timeout > 0 else None

    print(f"[RESUME] 品牌数={len(brands)} db={db} dry_run={args.dry_run} "
          f"max_rounds={args.max_rounds}", flush=True)

    failures: list[str] = []
    no_audit: list[str] = []
    still_pending: dict[str, int] = {}

    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        for brand in brands:
            pending, info = _pending_for_brand(con, brand)
            if not info["has_audit"]:
                no_audit.append(brand)
                print(f"\n[SKIP] {brand}：无入口审计记录，无法确定应抓系列全集（先跑一次 spec-crawl）",
                      flush=True)
                continue
            print(f"\n[BRAND] {brand} 入口={info['entry_total']} "
                  f"已成功={info['success_total']} 待续抓={info['pending_total']}", flush=True)
            if not pending:
                print(f"[OK] {brand}：无未成功系列，跳过", flush=True)
                continue
            preview = pending[:8]
            print("      待抓系列（前 8）:", json.dumps(preview, ensure_ascii=False), flush=True)

            if args.dry_run:
                still_pending[brand] = len(pending)
                continue

            prev_pending = None
            for round_index in range(1, max(1, args.max_rounds) + 1):
                pending, info = _pending_for_brand(con, brand)
                if not pending:
                    print(f"[OK] {brand}：已全部成功（第 {round_index-1} 轮后）", flush=True)
                    break
                if prev_pending is not None and len(pending) >= prev_pending:
                    print(f"[STOP] {brand}：第 {round_index} 轮前 pending={len(pending)} "
                          f"未较上轮({prev_pending})减少，停止续抓（可能是真实失败/空页）", flush=True)
                    break
                prev_pending = len(pending)
                print(f"[ROUND] {brand} 第 {round_index}/{args.max_rounds} 轮，续抓 {len(pending)} 个系列",
                      flush=True)
                rc = _run_crawl(db, brand, pending, env, timeout)
                if rc not in (0, 1):
                    # spec-crawl 在有失败系列时返回 1 属预期；其余非零（如 124 超时）记为异常。
                    failures.append(f"{brand}: spec-crawl rc={rc}")
                # 重新读库看这轮后的 pending
                pending_after, info_after = _pending_for_brand(con, brand)
                print(f"      第 {round_index} 轮后 pending={info_after['pending_total']}", flush=True)
                if not pending_after:
                    print(f"[OK] {brand}：续抓完成，全部成功", flush=True)
                    break
            else:
                _, info_final = _pending_for_brand(con, brand)
                if info_final["pending_total"]:
                    still_pending[brand] = info_final["pending_total"]

            # 循环正常结束（break 除外）后再兜底登记一次
            _, info_final = _pending_for_brand(con, brand)
            if info_final["pending_total"] and brand not in still_pending:
                still_pending[brand] = info_final["pending_total"]
    finally:
        con.close()

    print("\n[SUMMARY]", flush=True)
    if no_audit:
        print("  无入口审计（需先普通 spec-crawl）:", ", ".join(no_audit), flush=True)
    if still_pending:
        for brand, count in still_pending.items():
            print(f"  仍未成功: {brand} pending={count}（可能是官网真实失败/空页，需人工核对）",
                  flush=True)
    if failures:
        print("  执行异常:", flush=True)
        for item in failures:
            print("   -", item, flush=True)

    if args.dry_run:
        print("\n[DRY-RUN] 仅预览，未执行任何续抓", flush=True)
        return 0
    # 有执行异常（如超时 124）才返回非零；"仍有真实失败系列"不算脚本失败，
    # 因为那是官网/反爬问题，需人工判断，而非续跑逻辑出错。
    if failures:
        return 1
    print("\n[OK] 续跑流程完成（仍未成功的系列见上方 SUMMARY）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
