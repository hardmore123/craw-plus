"""把采集框架打包沉淀为可交付 zip（代码 + 文档 + 部署文件）。

文档入口为 `项目总说明.md`（架构/数据字典/前后端与部署指南），其余文档分工：
`使用说明.md` 操作手册、`部署说明.md` 运维部署、`交付说明.md` 交付内容、`工作日志.md` 决策与经验、
`跨国家线复用与开发指南.md` 跨国家线复用方法论（把日本线经验用到美国/加拿大等其它线）。

排除：运行数据 data/、缓存、__pycache__、.db、临时脚本 _*.py、已生成的报表。
`scripts/` 目录会同时打包六品牌刷新入口、`export_spec_models.py` 型号汇总脚本和
`export_spec_status.py` 系列状态导出脚本。状态脚本不读取运行缓存，只从 SQLite 导出 success/empty/failed 审计。
产物：交付包/overseas-crawler_<版本>_<时间戳>.zip

用法：
    python pack.py
"""
from __future__ import annotations

import fnmatch
import os
import zipfile
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))

# 要打进包的顶层条目（目录或文件）
INCLUDE = [
    "overseas",
    "deploy",
    "scripts",
    "README.md",
    "项目总说明.md",
    "接口说明.md",
    "使用说明.md",
    "部署说明.md",
    "交付说明.md",
    "跨国家线复用与开发指南.md",
    "requirements.txt",
    "pyproject.toml",
    ".gitignore",
    "benchmark.py",
    "check_xlsx.py",
    "工作日志.md",
    "pack.py",
]

# 任何路径命中这些模式即排除
EXCLUDE_PATTERNS = [
    "*/__pycache__/*", "*.pyc", "*.pyo",
    "*/data/*", "data/*",
    "*.db", "*.db-*",
    # 临时诊断脚本（用具体前缀，避免误伤 __init__.py 等包标记文件）
    "_probe*.py", "_diag*.py", "_check*.py", "_t.py", "_v.py", "_amazon*.py",
    "*.xlsx", "*.csv",       # 已生成的报表
    "overseas.env",          # 真实环境配置
    "*/.browser/*",
]


def _excluded(rel: str) -> bool:
    rel_posix = rel.replace(os.sep, "/")
    for pat in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch("/" + rel_posix, "*/" + pat.lstrip("*/")):
            return True
    # 兜底：路径任一段是 data / __pycache__ / .browser
    parts = set(rel_posix.split("/"))
    if parts & {"__pycache__", "data", ".browser"}:
        return True
    return False


def collect() -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for item in INCLUDE:
        p = os.path.join(ROOT, item)
        if os.path.isfile(p):
            rel = os.path.relpath(p, ROOT)
            if not _excluded(rel):
                files.append((p, rel))
        elif os.path.isdir(p):
            for dp, dns, fns in os.walk(p):
                dns[:] = [d for d in dns if d not in ("__pycache__", "data", ".browser")]
                for fn in fns:
                    fp = os.path.join(dp, fn)
                    rel = os.path.relpath(fp, ROOT)
                    if not _excluded(rel):
                        files.append((fp, rel))
    return files


def main() -> int:
    version = "0.3.0"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(ROOT, "交付包")
    os.makedirs(out_dir, exist_ok=True)
    name = f"overseas-crawler_v{version}_{ts}.zip"
    out = os.path.join(out_dir, name)

    files = collect()
    # 包内统一放在 overseas-crawler/ 顶层目录下，解压不散落
    top = f"overseas-crawler_v{version}"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for fp, rel in files:
            z.write(fp, os.path.join(top, rel).replace(os.sep, "/"))

    size_kb = os.path.getsize(out) / 1024
    print(f"已打包 {len(files)} 个文件 → {out}  ({size_kb:.0f} KB)")
    print("\n包含条目预览：")
    for _, rel in sorted(files)[:40]:
        print(f"  {rel}")
    if len(files) > 40:
        print(f"  ... 共 {len(files)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
