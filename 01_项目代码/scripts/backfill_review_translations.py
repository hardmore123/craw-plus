"""从现有数据库回填网评翻译，不重新抓取官网。

默认读取 data/overseas.db 中已入库的 Kakaku 日本网评，使用本地 NLLB
日语→中文模型补充「翻译」列，并按当前 review_export 标准列顺序生成
CSV/XLSX。可用 ``--engine xinghai`` 调用 HiGPT 大模型；旧汇总文件不覆盖，
输出文件带「已翻译_<engine>」标记。

用法：
    python scripts/backfill_review_translations.py
    python scripts/backfill_review_translations.py --brand hisense_jp
    python scripts/backfill_review_translations.py --engine xinghai
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas.api.exporter import BRAND_ZH, _review_records  # noqa: E402
from overseas.db import Database  # noqa: E402
from overseas.review_export import NULL_HOOKS, write_csv, write_xlsx  # noqa: E402
from overseas.review_translation import build_translation_hooks  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "data" / "overseas.db"
DEFAULT_OUT_DIR = PROJECT_ROOT / "data"
BRAND_ORDER = ("hisense_jp", "panasonic_jp", "regza_jp", "sharp_jp", "sony_jp", "tcl_jp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="从现有网评数据库回填离线翻译，不重新抓取")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="现有 SQLite 数据库路径")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="回填文件输出目录")
    parser.add_argument("--brand", help="只回填一个 Kakaku 品牌；缺省为全部六品牌")
    parser.add_argument(
        "--engine",
        choices=("nllb", "argos", "xinghai"),
        default="nllb",
        help="翻译引擎：nllb=本地 NLLB 直连日→中（默认）；argos=旧的日→英→中；"
             "xinghai=HiGPT xinghai-ultra（未配置或失败时回退离线引擎）",
    )
    parser.add_argument(
        "--batch-tokens",
        type=int,
        default=None,
        help="Argos 引擎单次 CTranslate2 token 预算；NLLB 引擎忽略",
    )
    parser.add_argument(
        "--batch-records",
        type=int,
        default=None,
        help="一次聚合的唯一网评数；缺省 NLLB=16、Argos=64",
    )
    return parser.parse_args()


def _translate_records(
    records,
    translator,
    max_tokens_per_batch: int | None = None,
    max_records_per_batch: int = 64,
    verbose: bool = True,
) -> tuple[int, int]:
    pending = [record for record in records if not record.translation]
    if verbose:
        print(f"[TRANSLATE] 0/{len(pending)}", flush=True)
    if pending:
        def report(done: int, total: int) -> None:
            if verbose:
                print(f"[TRANSLATE] {done}/{total}", flush=True)

        translations = translator.translate_many(
            [record.body for record in pending],
            max_tokens_per_batch=max_tokens_per_batch,
            max_records_per_batch=max_records_per_batch,
            progress=report,
        )
        for record, translation in zip(pending, translations):
            record.translation = translation

    nonempty = sum(1 for record in records if record.translation)
    changed = sum(
        1
        for record in records
        if record.translation and record.translation != record.body
    )
    return nonempty, changed


def _write_pair(records, hooks, path_base: Path) -> None:
    csv_path = path_base.with_suffix(".csv")
    xlsx_path = path_base.with_suffix(".xlsx")
    # 翻译已经预先写入每条 ReviewRecord，导出阶段不再重复调用模型。
    write_csv(csv_path, records, NULL_HOOKS)
    write_xlsx(xlsx_path, records, NULL_HOOKS)
    print(f"[OUT] csv={csv_path} rows={len(records)}", flush=True)
    print(f"[OUT] xlsx={xlsx_path} rows={len(records)}", flush=True)


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        print(f"[ERROR] 数据库不存在：{db_path}")
        return 2

    db = Database(str(db_path))
    try:
        if args.brand:
            brands = [args.brand]
        else:
            brands = list(BRAND_ORDER)
        records = _review_records(db, args.brand or "")
        if not records:
            print("[ERROR] 当前数据库没有可回填的 Kakaku 网评")
            return 1
        print(f"[BACKFILL] 仅读取数据库：{db_path}")
        print(f"[BACKFILL] 品牌={','.join(brands) if args.brand else '全部Kakaku品牌'} 网评={len(records)}")
        _hooks, translator = build_translation_hooks(engine=args.engine)
        default_batch = {"nllb": 16, "argos": 64, "xinghai": 8}[args.engine]
        batch_records = args.batch_records or default_batch
        labels = {
            "nllb": "NLLB 直连日→中",
            "argos": "Argos 日→英→中",
            "xinghai": "HiGPT xinghai-ultra 日→中（失败回退离线引擎）",
        }
        label = labels[args.engine]
        print(f"[ENGINE] {args.engine}（{label}），缓存上限={translator.cache_size}，批={batch_records}")
        nonempty, changed = _translate_records(
            records,
            translator,
            max_tokens_per_batch=args.batch_tokens,
            max_records_per_batch=batch_records,
        )
        stamp = datetime.now().strftime("%Y%m%d")
        # 文件名带引擎标记，避免不同引擎（nllb/argos）同日互相覆盖，便于对比。
        suffix = f"_已翻译_{args.engine}"
        base = out_dir / f"网评汇总_全部品牌_kakaku_{stamp}{suffix}"
        if args.brand:
            base = out_dir / f"网评汇总_{args.brand}_kakaku_{stamp}{suffix}"
        _write_pair(records, NULL_HOOKS, base)
        print(f"[SUMMARY] source_rows={len(records)} translation_nonempty={nonempty} changed={changed}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
