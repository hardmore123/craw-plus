"""compintel 表族读写封装。

复用主 Database 的 crawl_run 审计与 sqlite 连接；只加 compintel_* 表的专用方法，
避免在 db.py 主文件里堆竞品情报逻辑。
"""
from __future__ import annotations

import json
import sqlite3

from ..db import Database, _now


class CompIntelDB:
    """包一层 Database，只暴露 compintel_* 表的增查接口。

    用法：
        db = Database(); db.init_schema()
        cidb = CompIntelDB(db)
        run_id = cidb.start_run("fcc_crawl", {"applicants": ["Samsung"]})
        ... 采到记录后 cidb.add_record(...) / cidb.add_doc(...)
        cidb.finish_run(run_id, ok=N, fail=0)
    """

    def __init__(self, db: Database):
        self.db = db
        self.conn = db.conn

    # ---------------- 审计（复用 crawl_run）----------------
    def start_run(self, scenario: str, params: dict | None = None,
                  site_code: str = "") -> int:
        return self.db.start_run(scenario, site_code, params)

    def finish_run(self, run_id: int, status: str = "completed",
                   ok: int = 0, fail: int = 0, message: str = "") -> None:
        self.db.finish_run(run_id, status, ok, fail, message)

    def log_error(self, run_id: int, url: str, stage: str, kind: str,
                  message: str) -> None:
        self.db.log_error(run_id, url, stage, kind, message)

    # ---------------- 记录 ----------------
    def add_record(self, run_id: int | None, source: str, source_id: str,
                   **fields) -> int:
        """INSERT 一条 compintel_record 快照。source ∈ {fcc,eprel}。

        关键字段：product_group, applicant, applicant_code, brand, model,
        description, auth_date, market_start, market_end, frequency,
        energy_class, extra_json, confidentiality。

        防重复：如果该 source+source_id 已存在,且本次不是字段更新,
        则跳过(返回已有记录的 id)。设 fields['_force_update']=True 可强制插入。
        """
        # 防重复入库:已存在的 source_id 不再插入(除非强制更新)
        if not fields.get("_force_update"):
            existing = self.conn.execute(
                "SELECT id FROM compintel_record WHERE source=? AND source_id=? "
                "ORDER BY captured_at DESC LIMIT 1",
                (source, source_id)).fetchone()
            if existing:
                return int(existing["id"])
        fields.pop("_force_update", None)
        cols = ["run_id", "source", "source_id", "captured_at"]
        vals: list = [run_id, source, source_id, _now()]
        for k in ("product_group", "applicant", "applicant_code", "brand",
                  "model", "description", "auth_date", "market_start",
                  "market_end", "frequency", "energy_class", "extra_json",
                  "confidentiality"):
            if k in fields and fields[k] is not None:
                v = fields[k]
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, ensure_ascii=False)
                cols.append(k)
                vals.append(v)
        placeholders = ",".join("?" * len(vals))
        cur = self.conn.execute(
            f"INSERT INTO compintel_record({','.join(cols)}) "
            f"VALUES ({placeholders})", vals)
        self.conn.commit()
        return int(cur.lastrowid)

    def add_doc(self, record_id: int, doc_type: str, doc_name: str = "",
                url: str = "", doc_date: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO compintel_doc(record_id, doc_type, doc_name, url, "
            "doc_date, captured_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(record_id, doc_type, doc_name) DO UPDATE SET "
            "url=excluded.url, doc_date=excluded.doc_date",
            (record_id, doc_type, doc_name[:300], url[:1000], doc_date, _now()))
        self.conn.commit()
        return int(cur.lastrowid)

    def seen_source_id(self, source: str, source_id: str) -> bool:
        """该 source_id 是否已在历史快照中出现（去重用）。"""
        row = self.conn.execute(
            "SELECT 1 FROM compintel_record WHERE source=? AND source_id=? "
            "LIMIT 1", (source, source_id)).fetchone()
        return row is not None

    def last_record(self, source: str, source_id: str,
                    before_captured_at: str = "") -> dict | None:
        """取该 source_id 最近一次快照（用于变化检测）。

        before_captured_at: 给定时只取该时间点之前的快照（用于在本次插入前
        取"上一次"快照，避免插入后再查拿到的是本次自己）。
        """
        if before_captured_at:
            row = self.conn.execute(
                "SELECT * FROM compintel_record WHERE source=? AND source_id=? "
                "AND captured_at < ? ORDER BY captured_at DESC LIMIT 1",
                (source, source_id, before_captured_at)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM compintel_record WHERE source=? AND source_id=? "
                "ORDER BY captured_at DESC LIMIT 1", (source, source_id)).fetchone()
        return dict(row) if row else None

    def records_for_applicant(self, source: str, applicant: str,
                              limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM compintel_record WHERE source=? AND applicant=? "
            "ORDER BY captured_at DESC LIMIT ?", (source, applicant, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 最新状态视图（时序快照的便捷查询）----------------
    def latest_records(self, source: str | None = None,
                       applicant: str | None = None,
                       brand: str | None = None,
                       limit: int = 500) -> list[dict]:
        """每个 source_id 只取最新一条快照（最新状态视图）。

        时序快照全部保留（历史可追溯），但查"当前状态"用这个视图更直观。
        """
        sql = (
            "SELECT r.* FROM compintel_record r "
            "INNER JOIN (SELECT source, source_id, MAX(captured_at) AS max_t "
            "            FROM compintel_record "
            + ("WHERE source=? " if source else "WHERE 1=1 ")
            + "GROUP BY source, source_id) m "
            "ON r.source=m.source AND r.source_id=m.source_id "
            "AND r.captured_at=m.max_t WHERE 1=1")
        params: list = []
        if source:
            params.append(source)
        if applicant:
            sql += " AND r.applicant LIKE ?"
            params.append(f"%{applicant}%")
        if brand:
            sql += " AND r.brand LIKE ?"
            params.append(f"%{brand}%")
        sql += " ORDER BY r.captured_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def history(self, source: str, source_id: str) -> list[dict]:
        """某 source_id 的全部历史快照（按时间正序，追溯用）。"""
        rows = self.conn.execute(
            "SELECT * FROM compintel_record WHERE source=? AND source_id=? "
            "ORDER BY captured_at ASC", (source, source_id)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 变化检测辅助 ----------------
    DIFF_FIELDS = ("applicant", "brand", "model", "energy_class",
                   "auth_date", "market_start", "market_end", "frequency",
                   "confidentiality", "product_group")

    @staticmethod
    def diff_records(prev: dict | None, cur: dict) -> list[tuple[str, str, str]]:
        """比较两条快照，返回 [(field, old, new), ...] 变化字段列表。

        只比 DIFF_FIELDS 中的语义字段（不含 id/run_id/captured_at/extra_json）。
        prev=None 视为新增（返回空列表，由 new_* 信号处理）。
        """
        if prev is None:
            return []
        out: list[tuple[str, str, str]] = []
        for f in CompIntelDB.DIFF_FIELDS:
            old = (prev.get(f) or "")
            new = (cur.get(f) or "")
            # 归一化：去首尾空白，空串统一
            old_s = str(old).strip()
            new_s = str(new).strip()
            if old_s and new_s and old_s.lower() != new_s.lower():
                out.append((f, old_s, new_s))
        return out

    # ---------------- 信号 ----------------
    def add_alert(self, run_id: int | None, signal_type: str, source: str,
                  level: str = "watch", applicant: str = "", brand: str = "",
                  model: str = "", source_id: str = "", message: str = "",
                  details: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO compintel_alert(run_id, signal_type, source, applicant, "
            "brand, model, source_id, level, message, details_json, detected_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(signal_type, source, source_id, detected_at) DO NOTHING",
            (run_id, signal_type, source, applicant, brand, model, source_id,
             level, message[:500],
             json.dumps(details or {}, ensure_ascii=False), _now()))
        self.conn.commit()
        return int(cur.lastrowid)

    def alerts_since(self, since: str = "") -> list[dict]:
        sql = ("SELECT * FROM compintel_alert"
               + (" WHERE detected_at >= ?" if since else "")
               + " ORDER BY detected_at DESC")
        rows = self.conn.execute(sql, (since,) if since else ()).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 抓取状态(增量) ----------------
    def get_state(self, source: str, state_key: str) -> dict | None:
        """取某抓取单位(fcc授权码/eprel扫描区间)的上次状态。"""
        row = self.conn.execute(
            "SELECT * FROM compintel_crawl_state WHERE source=? AND state_key=?",
            (source, state_key)).fetchone()
        return dict(row) if row else None

    def set_state(self, source: str, state_key: str, *, last_crawled_at: str,
                  last_record_date: str = "", pages_crawled: int = 0,
                  records_seen: int = 0, records_new: int = 0,
                  meta: dict | None = None) -> None:
        """更新某抓取单位的状态(存在则更新，不存在则插入)。"""
        self.conn.execute(
            "INSERT INTO compintel_crawl_state(source, state_key, last_crawled_at,"
            " last_record_date, pages_crawled, records_seen, records_new, meta_json) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source, state_key) DO UPDATE SET "
            " last_crawled_at=excluded.last_crawled_at,"
            " last_record_date=excluded.last_record_date,"
            " pages_crawled=excluded.pages_crawled,"
            " records_seen=excluded.records_seen,"
            " records_new=excluded.records_new,"
            " meta_json=excluded.meta_json",
            (source, state_key, last_crawled_at, last_record_date,
             pages_crawled, records_seen, records_new,
             json.dumps(meta or {}, ensure_ascii=False)))
        self.conn.commit()

    def known_source_ids(self, source: str, state_keys: list[str] | None = None) -> set[str]:
        """取该 source 已入库的全部 source_id 集合(增量早停判断用)。

        可选 state_keys: 只取某些授权码范围内的(用 applicant_code 过滤)。
        """
        if state_keys:
            ph = ",".join("?" * len(state_keys))
            rows = self.conn.execute(
                f"SELECT DISTINCT source_id FROM compintel_record "
                f"WHERE source=? AND applicant_code IN ({ph})",
                (source, *state_keys)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT DISTINCT source_id FROM compintel_record WHERE source=?",
                (source,)).fetchall()
        return {r[0] for r in rows}

    def all_states(self, source: str) -> list[dict]:
        """取该 source 所有抓取单位的状态(看哪些授权码抓过/何时抓)。"""
        rows = self.conn.execute(
            "SELECT * FROM compintel_crawl_state WHERE source=? "
            "ORDER BY last_crawled_at DESC", (source,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 统计 ----------------
    def stats(self) -> dict:
        def one(sql: str) -> int:
            try:
                row = self.conn.execute(sql).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            except sqlite3.Error:
                return 0
        # 各数据源记录数(唯一 source_id)
        all_sources = ["fcc", "eprel", "energystar", "anatel", "ic_ised", "tuv", "ul"]
        source_counts = {}
        for src in all_sources:
            source_counts[src] = one(
                f"SELECT COUNT(DISTINCT source_id) FROM compintel_record WHERE source='{src}'"
            )
        return {
            "fcc_records": one("SELECT COUNT(*) FROM compintel_record WHERE source='fcc'"),
            "eprel_records": one("SELECT COUNT(*) FROM compintel_record WHERE source='eprel'"),
            "fcc_records_unique": source_counts["fcc"],
            "eprel_records_unique": source_counts["eprel"],
            "docs": one("SELECT COUNT(*) FROM compintel_doc"),
            "alerts": one("SELECT COUNT(*) FROM compintel_alert"),
            "alerts_by_type": {r[0]: int(r[1]) for r in self.conn.execute(
                "SELECT signal_type, COUNT(*) FROM compintel_alert "
                "GROUP BY signal_type").fetchall()},
            "alerts_by_source": {r[0]: int(r[1]) for r in self.conn.execute(
                "SELECT source, COUNT(*) FROM compintel_alert "
                "GROUP BY source").fetchall()},
            "fcc_states": one("SELECT COUNT(*) FROM compintel_crawl_state WHERE source='fcc'"),
            "eprel_states": one("SELECT COUNT(*) FROM compintel_crawl_state WHERE source='eprel'"),
            # 新数据源统计
            "source_counts": source_counts,
            "total_records": one("SELECT COUNT(DISTINCT source_id) FROM compintel_record"),
            "total_brands": one("SELECT COUNT(DISTINCT brand) FROM compintel_record WHERE brand != ''"),
        }
