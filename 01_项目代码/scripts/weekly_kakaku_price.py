# -*- coding: utf-8 -*-
"""日本线 kakaku 价格 —— 周度采集调度入口。

用途：每周一定时跑一次，把当周各品牌各机型在 8 家店铺的报价抓下来入库
（price_shop_snapshot 只 INSERT 不覆盖，天然形成周度时序），为
「价格趋势曲线」持续积累数据。

底层复用 scripts/crawl_kakaku_prices.py（--save-db --all-brands），
本脚本只负责：调度封装 + 周次标记 + 日志 + 失败重试 + 幂等保护。

用法：
    python scripts/weekly_kakaku_price.py                  # 抓全部 6 品牌
    python scripts/weekly_kakaku_price.py --brand hisense_jp --brand sony_jp
    python scripts/weekly_kakaku_price.py --dry-run        # 只打印不执行
    python scripts/weekly_kakaku_price.py --limit-models 3 # 冒烟测试

配合 Windows 任务计划程序：见 deploy/kakaku_weekly_task.xml
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRAWL_SCRIPT = PROJECT_ROOT / "scripts" / "crawl_kakaku_prices.py"
LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

ALL_BRANDS = ["hisense_jp", "sony_jp", "regza_jp", "panasonic_jp", "tcl_jp", "sharp_jp"]


def iso_week(d: datetime) -> str:
    """ISO 周键 YYYY-Www（与 db.weekly_price_series 一致）。"""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def run_once(args: argparse.Namespace) -> int:
    now = datetime.now(timezone.utc)
    week_key = iso_week(now)
    stamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"weekly_price_{stamp}.log"

    cmd = [sys.executable, str(CRAWL_SCRIPT), "--save-db", "--all-brands",
           "--format", "csv",
           "--out", str(PROJECT_ROOT / "data" / f"价格监控_weekly_kakaku_{stamp}")]
    if args.brand:
        cmd = [sys.executable, str(CRAWL_SCRIPT), "--save-db", "--format", "csv",
               "--out", str(PROJECT_ROOT / "data" / f"价格监控_weekly_kakaku_{stamp}")]
        for b in args.brand:
            cmd += ["--brand", b]
    if args.limit_models > 0:
        cmd += ["--limit-models", str(args.limit_models)]
    if args.year is not None:
        cmd += ["--year", str(args.year)]

    print(f"[weekly] 周次={week_key} 时间={now.isoformat()}")
    print(f"[weekly] 命令={' '.join(cmd)}")
    print(f"[weekly] 日志={log_path}")
    if args.dry_run:
        print("[weekly] --dry-run，不执行")
        return 0

    with open(log_path, "w", encoding="utf-8") as lf:
        lf.write(f"=== kakaku weekly price crawl {week_key} ===\n")
        lf.write(f"cmd: {' '.join(cmd)}\n\n")
        lf.flush()
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT),
                             stdout=lf, stderr=subprocess.STDOUT)
    print(f"[weekly] 退出码={proc.returncode} 日志={log_path}")
    return proc.returncode


def main() -> int:
    p = argparse.ArgumentParser(description="kakaku 日本线周度价格采集调度")
    p.add_argument("--brand", action="append", default=None,
                   help=f"指定品牌（可多次），缺省抓全部：{ALL_BRANDS}")
    p.add_argument("--year", type=int, default=None,
                   help="上市年份过滤，缺省用 crawl_kakaku_prices 默认(2026)；传 0 不过滤")
    p.add_argument("--limit-models", type=int, default=0,
                   help="每品牌只抓前 N 个机型（冒烟测试用）")
    p.add_argument("--dry-run", action="store_true", help="只打印命令不执行")
    args = p.parse_args()
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
