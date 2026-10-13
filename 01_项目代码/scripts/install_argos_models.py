"""安装离线日语→中文翻译所需的 Argos 模型。

Argos 官方索引目前提供 ja→en 与 en→zh 两个模型，本项目运行时串联它们
完成日语→中文。只需首次运行一次；模型安装到当前用户的 Argos 模型目录，
不会写入项目目录。

用法：
    python scripts/install_argos_models.py
"""
from __future__ import annotations

from argostranslate import package

REQUIRED = ("translate-ja_en", "translate-en_zh")


def main() -> int:
    package.update_package_index()
    available = {p.code: p for p in package.get_available_packages()}
    installed = {
        (getattr(p, "from_code", ""), getattr(p, "to_code", ""))
        for p in package.get_installed_packages()
    }
    for code in REQUIRED:
        if code == "translate-ja_en":
            pair = ("ja", "en")
        elif code == "translate-en_zh":
            pair = ("en", "zh")
        else:
            pair = ("", "")
        if pair in installed:
            print(f"[ARGOS] 已安装 {code}")
            continue
        pkg = available.get(code)
        if pkg is None:
            print(f"[ARGOS] 找不到模型：{code}")
            return 1
        print(f"[ARGOS] 下载 {code} {pkg.package_version} …", flush=True)
        pkg_path = pkg.download()
        print(f"[ARGOS] 安装 {pkg_path} …", flush=True)
        pkg.install()
        print(f"[ARGOS] 完成 {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
