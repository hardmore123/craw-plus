"""用最新词典重算 spec_row.item_zh 并回写数据库。

背景：spec_row.item_zh 是采集时用当时的词典翻译后存下来的。导出（spec_export）
优先使用库里的 item_zh，词典更新后不会自动生效。本脚本按最新词典重新翻译所有
spec_row 的日文项目名，仅在中文有变化时更新，避免无谓写入。

典型用途：修正词典后刷新存量库（如修复 mm/kg、2026/2012 基准等翻译撞车），
不需要重新抓取官网。

示例：
    python scripts/retranslate_spec.py --dry-run          # 只预览将变更的项
    python scripts/retranslate_spec.py                    # 全库回写
    python scripts/retranslate_spec.py --site tcl_jp      # 只处理 TCL
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.dict import translate  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "data" / "overseas.db"
BRANDS = ("hisense_jp", "sony_jp", "regza_jp", "panasonic_jp", "tcl_jp", "sharp_jp")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="用最新词典重算 spec_row.item_zh 并回写数据库")
    p.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite 数据库路径，默认 {DEFAULT_DB}")
    p.add_argument("--site", action="append", choices=BRANDS,
                   help="只处理指定品牌，可重复；默认全部六品牌")
    p.add_argument("--dry-run", action="store_true", help="只预览将变更的项，不写库")
    p.add_argument("--show", type=int, default=40, help="预览时最多打印多少条变更（默认 40）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sites = tuple(args.site or BRANDS)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"[ERROR] 数据库不存在: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    placeholders = ",".join("?" for _ in sites)
    rows = conn.execute(
        f"""SELECT r.id, r.item_ja, r.item_zh, s.brand
            FROM spec_row AS r JOIN spec_series AS s ON s.id = r.series_id
            WHERE s.brand IN ({placeholders})""",
        sites).fetchall()

    changes: list[tuple[int, str, str, str, str]] = []  # (id, brand, ja, old_zh, new_zh)
    filled = 0        # 原本为空、现在翻出中文
    corrected = 0     # 原本有中文、现在改成不同中文
    for r in rows:
        ja = r["item_ja"] or ""
        old = r["item_zh"] or ""
        new = translate(ja)
        if not new:
            continue                      # 词典仍未命中，保留原值（不清空已有翻译）
        if new == old:
            continue
        if old:
            corrected += 1
        else:
            filled += 1
        changes.append((r["id"], r["brand"], ja, old, new))

    print(f"[RETRANSLATE] 品牌={len(sites)} 扫描行={len(rows)} "
          f"待变更={len(changes)}（新填充={filled} 纠正={corrected}）")

    # 预览：按品牌聚合展示唯一的 (ja, old->new)
    if changes:
        seen = set()
        shown = 0
        for _id, brand, ja, old, new in changes:
            k = (brand, ja, old, new)
            if k in seen:
                continue
            seen.add(k)
            if shown < args.show:
                print(f"  [{brand}] {ja!r}\n      {old!r} -> {new!r}")
                shown += 1
        uniq = len(seen)
        if uniq > args.show:
            print(f"  ...（另有 {uniq - args.show} 组唯一变更未展示，用 --show 增大上限）")

    if args.dry_run:
        print("[DRY-RUN] 未写库。去掉 --dry-run 执行回写。")
        conn.close()
        return 0

    if changes:
        conn.executemany("UPDATE spec_row SET item_zh=? WHERE id=?",
                         [(new, _id) for _id, _b, _ja, _old, new in changes])
        conn.commit()
        print(f"[DONE] 已更新 {len(changes)} 行 item_zh。")
    else:
        print("[DONE] 无需变更。")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
