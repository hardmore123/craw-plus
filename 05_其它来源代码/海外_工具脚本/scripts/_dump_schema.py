"""提取数据库 schema 中 compintel 相关表的完整结构。"""
import sqlite3
c = sqlite3.connect("data/overseas.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
for t in tables:
    if "comp" in t.lower() or "crawl" in t.lower() or "product" in t.lower() or "alert" in t.lower():
        cols = c.execute("PRAGMA table_info({})".format(t)).fetchall()
        n_rows = c.execute("SELECT COUNT(*) FROM {}".format(t)).fetchone()[0]
        print("\n=== {} ({} rows) ===".format(t, n_rows))
        for col in cols:
            flags = []
            if col[3]:
                flags.append("NOT NULL")
            if col[5]:
                flags.append("PK")
            flag_str = " ".join(flags) if flags else ""
            print("  {:25} {:15} {}".format(col[1], col[2], flag_str))
        idxs = c.execute("PRAGMA index_list({})".format(t)).fetchall()
        for idx in idxs:
            idx_cols = [r[2] for r in c.execute("PRAGMA index_info({})".format(idx[1])).fetchall()]
            print("  INDEX: {} cols={} unique={}".format(idx[1], idx_cols, idx[2]))
c.close()
