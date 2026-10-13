# -*- coding: utf-8 -*-
"""生成交接包的「可运行项目」部分：把部署包代码 + skill + 文档 + git 历史 + 型号清单 + 主库拷进目标目录。

不拷：浏览器登录目录、缓存、DB 历史备份、sandbox、__pycache__。
用法：py -3.12 scripts/build_handoff.py --dst <交付包>/01_项目代码
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")
DIRS = [".git", ".kiro", "overseas", "scripts", "schemas", "docs", "deploy", "monitor", "skills"]
SKIP_FILES = {"datetime"}
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dst", required=True)
    a = ap.parse_args()
    dst = os.path.abspath(a.dst)
    if os.path.exists(dst):
        import stat

        def _force(func, path, _exc):      # git 对象文件是只读的
            os.chmod(path, stat.S_IWRITE)
            func(path)
        # 只清空子项：目标目录本身可能被 IDE/终端占用，删不掉
        for name in os.listdir(dst):
            p = os.path.join(dst, name)
            if os.path.isdir(p):
                shutil.rmtree(p, onexc=_force)
            else:
                os.chmod(p, stat.S_IWRITE)
                os.remove(p)
    os.makedirs(dst, exist_ok=True)
    for d in DIRS:
        s = os.path.join(ROOT, d)
        if os.path.isdir(s):
            shutil.copytree(s, os.path.join(dst, d), ignore=IGNORE)
    for f in os.listdir(ROOT):
        p = os.path.join(ROOT, f)
        if os.path.isfile(p) and f not in SKIP_FILES:
            shutil.copy2(p, os.path.join(dst, f))
    # data/：主库 + 各国型号清单（全量入口按 data/<中文国名>/SPEC_型号汇总_<rc>_*.csv 取型号）
    os.makedirs(os.path.join(dst, "data"))
    shutil.copy2(os.path.join(ROOT, "data", "overseas.db"), os.path.join(dst, "data", "overseas.db"))
    n = 0
    for p in glob.glob(os.path.join(ROOT, "data", "*", "SPEC_型号汇总_*.csv")):
        country = os.path.basename(os.path.dirname(p))
        if not re.match(r"^[\u4e00-\u9fa5]", country):
            continue
        os.makedirs(os.path.join(dst, "data", country), exist_ok=True)
        shutil.copy2(p, os.path.join(dst, "data", country, os.path.basename(p)))
        n += 1
    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(dst) for f in fs)
    print(f"→ {dst}  {size / 1e6:.1f}MB  型号清单 {n} 份  "
          f"spec {len(glob.glob(os.path.join(dst, 'schemas', 'retail_specs', '*.json')))}  "
          f"adapter {len(glob.glob(os.path.join(dst, 'overseas', 'sites', '*', 'adapter.py')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
