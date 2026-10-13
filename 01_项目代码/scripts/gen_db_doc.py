# -*- coding: utf-8 -*-
"""从主库 + overseas/schema.sql 自动生成「数据库表结构明细」（列、类型、约束、索引、外键、行数、列注释）。

手写的业务说明（表用途、写入方/读取方、关系、误区）在 docs/数据库结构说明.md；
本脚本只产出可随库重新生成的机械部分：docs/数据库表结构明细.md。
用法：py -3.12 scripts/gen_db_doc.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")
DB = os.environ.get("OVERSEAS_DB_PATH") or "data/overseas.db"
OUT = "docs/数据库表结构明细.md"


def col_comments(ddl: str) -> dict[str, str]:
    """从 CREATE TABLE 文本里取「列名 ... -- 注释」。"""
    out = {}
    for line in (ddl or "").splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s+[A-Za-z].*?--\s*(.+)$", line)
        if m and m.group(1).upper() not in ("UNIQUE", "FOREIGN", "PRIMARY", "CHECK", "CONSTRAINT"):
            out[m.group(1)] = m.group(2).strip()
    return out


def schema_sql_comments() -> dict[str, dict[str, str]]:
    """overseas/schema.sql 里的列注释（运行时库里的 DDL 可能是迁移重建的，注释更全的以 schema.sql 为准）。"""
    p = os.path.join("overseas", "schema.sql")
    if not os.path.exists(p):
        return {}
    txt = open(p, encoding="utf-8").read()
    res = {}
    for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\n\);", txt, re.S):
        res[m.group(1)] = col_comments(m.group(2))
    return res


def main() -> int:
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    sc = schema_sql_comments()
    tables = [r[0] for r in c.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
    ver = c.execute("select max(version) from schema_version").fetchone()[0]
    L = ["# 数据库表结构明细（自动生成）", "",
         f"库：`{DB}`，schema_version = {ver}，共 {len(tables)} 张表。由 `scripts/gen_db_doc.py` 生成，改表后重跑。",
         "业务含义、表间关系、读写方与使用误区见 `docs/数据库结构说明.md`。", "",
         "| 表 | 行数 |", "|---|---|"]
    counts = {t: c.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
    for t in tables:
        L.append(f"| [{t}](#{t}) | {counts[t]:,} |")
    for t in tables:
        ddl = c.execute("select sql from sqlite_master where name=?", (t,)).fetchone()[0] or ""
        cm = {**col_comments(ddl), **sc.get(t, {})}
        L += ["", f"## {t}", "", f"行数 {counts[t]:,}", "",
              "| 列 | 类型 | 非空 | 主键 | 默认 | 说明 |", "|---|---|---|---|---|---|"]
        for cid, name, typ, nn, dflt, pk in c.execute(f'pragma table_info("{t}")'):
            L.append(f"| {name} | {typ} | {'Y' if nn else ''} | {'Y' if pk else ''} | "
                     f"{'' if dflt is None else str(dflt).replace('|', '/')} | {cm.get(name, '').replace('|', '/')} |")
        fks = c.execute(f'pragma foreign_key_list("{t}")').fetchall()
        if fks:
            L += ["", "外键：" + "；".join(f"`{f[3]}` → `{f[2]}.{f[4]}`（删除时 {f[6]}）" for f in fks)]
        idx = []
        for _, iname, uniq, origin, _p in c.execute(f'pragma index_list("{t}")'):
            cols = [r[2] for r in c.execute(f'pragma index_info("{iname}")')]
            kind = "唯一" if uniq else "索引"
            src = "（表约束）" if origin in ("u", "pk") else ""
            idx.append(f"{kind} ({', '.join(cols)}){src}")
        if idx:
            L += ["", "约束/索引：" + "；".join(idx)]
        chk = re.findall(r"CHECK\s*\((.*?)\)\s*[,)]", ddl, re.S)
        if chk:
            L += ["", "CHECK：" + "；".join(" ".join(x.split()) for x in chk)]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"→ {OUT}  {len(tables)} 表")
    for t in tables:
        print(f"  {t:32} {counts[t]:>9,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
