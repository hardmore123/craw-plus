# -*- coding: utf-8 -*-
"""每站只保留一份 spec：schemas/retail_specs/<code>.retail.json 为唯一权威。

历史上每个零售站有三份抽取定义，内容已各自漂移：
  1) schemas/retail_specs/<code>.retail.json   RetailSpec（通用全量入口 --spec 用）
  2) docs/retail_specs/<code>.retail.json         同名副本（retail-health / 部分诊断脚本读，49 份已不一致）
  3) overseas/sites/<code>/schema.json         adapter 内置六段（无 spec 时 adapter 路径用）
并行会话近期的改进（评价图片/视频 media 段、币种 default 等）只写进了 3)，
spec 驱动的站点因此用不上。

本脚本做两件事（均可重复执行，幂等）：
  a) 把 3) 里**缺失于 1)** 的字段深度补进 1)（只补缺，不覆盖 1) 已有值——1) 的
     match/paginate/search.api 等是逐站实测过的）；
  b) 报告 2) 与 1) 的差异（2) 由调用方删除，读路径统一改到 1)）。
用法：py -3.12 scripts/unify_specs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
SIX = ("anchor", "search", "product", "price", "specs", "summary", "reviews")


def fill_missing(dst, src, path, added: list) -> None:
    """src 中 dst 没有的键补进 dst（递归 dict；list/标量不合并）。"""
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return
    for k, v in src.items():
        if k.startswith("_"):
            continue                       # 注释类字段不搬
        if k not in dst or dst[k] in (None, "", {}, []):
            if v in (None, "", {}, []):
                continue
            dst[k] = v
            added.append(f"{path}.{k}")
        elif isinstance(dst[k], dict) and isinstance(v, dict):
            fill_missing(dst[k], v, f"{path}.{k}", added)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    changed = 0
    total_added = 0
    for f in sorted(glob.glob("schemas/retail_specs/*.retail.json")):
        code = os.path.basename(f).split(".")[0]
        sp = f"overseas/sites/{code}/schema.json"
        if not os.path.exists(sp):
            continue
        spec = json.load(open(f, encoding="utf-8"))
        try:
            s6 = json.load(open(sp, encoding="utf-8"))
        except ValueError:
            print(f"[WARN] {sp} 非法 JSON，跳过")
            continue
        added: list[str] = []
        for sec in SIX:
            if sec not in s6:
                continue
            if sec not in spec or spec[sec] in (None, "", {}, []):
                if s6[sec] not in (None, "", {}, []):
                    spec[sec] = s6[sec]
                    added.append(sec)
            else:
                fill_missing(spec[sec], s6[sec], sec, added)
        if added:
            changed += 1
            total_added += len(added)
            print(f"{code:24} +{len(added)}: {', '.join(added[:6])}{' …' if len(added) > 6 else ''}")
            if not args.dry_run:
                with open(f, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(spec, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
    print(f"[DONE] spec 补字段 {changed} 份 / {total_added} 处{'（dry-run 未写入）' if args.dry_run else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
