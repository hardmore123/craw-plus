"""竞品情报可视化看板 — 后端 API（Python 标准库 http.server，零依赖）。

复用 CompIntelDB 的查询方法，暴露 JSON API 给前端单页。
启动：py -3.12 -m overseas.cli compintel-web [--port 8088] [--db <path>]
或直接：py -3.12 -m overseas.compintel.web_api --port 8088

API 路由：
  GET /api/stats              库统计（FCC/EPREL 记录数、信号数、按类型分组）
  GET /api/alerts             预警信号列表（?type=&since=&limit=）
  GET /api/records            最新状态记录（?source=&applicant=&brand=&limit=）
  GET /api/history            某 source_id 历史快照（?source=&source_id=）
  GET /api/run                触发一次抓取（?applicants=&eprel_brands=&details=）
  GET /api/analyze            LLM 解读预警(?mode=single|trend&type=&limit=)
  GET /                       返回 index.html 前端单页
"""
from __future__ import annotations

import json
import os
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

from ..db import Database
from .compintel_db import CompIntelDB

# index.html 与本文件同目录
_HERE = os.path.dirname(os.path.abspath(__file__))
_INDEX_HTML = os.path.join(_HERE, "dashboard.html")


def _row_to_serializable(row: dict) -> dict:
    """SQLite Row 转可 JSON 序列化的 dict（extra_json 字段尝试解析）。"""
    out = {}
    for k, v in row.items():
        if k == "extra_json" and v:
            try:
                out[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                out[k] = v
        else:
            out[k] = v
    return out


class DashboardHandler(BaseHTTPRequestHandler):
    """处理看板 API 请求。"""

    # 模块级共享状态（由 serve() 注入）
    cidb: CompIntelDB = None  # type: ignore
    db: Database = None  # type: ignore

    def log_message(self, fmt, *args):
        # 静默默认日志，避免刷屏
        pass

    def _json(self, data, code: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, path: str):
        if not os.path.exists(path):
            self._json({"error": "dashboard.html not found"}, 404)
            return
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        path = url.path.rstrip("/") or "/"

        try:
            if path == "/" or path == "/index.html":
                self._html(_INDEX_HTML)
            elif path == "/api/stats":
                self._json(self.cidb.stats())
            elif path == "/api/alerts":
                since = qs.get("since", [""])[0]
                stype = qs.get("type", [""])[0]
                source = qs.get("source", [""])[0]
                brand = qs.get("brand", [""])[0]
                days = qs.get("days", [""])[0]
                limit = int(qs.get("limit", ["5000"])[0])
                # 时间过滤:days=N 表示近N天
                if days and not since:
                    from datetime import datetime, timedelta
                    since = (datetime.utcnow() - timedelta(days=int(days))).isoformat()[:19]
                alerts = self.cidb.alerts_since(since)
                # 后端按 type 过滤
                if stype:
                    alerts = [a for a in alerts if a["signal_type"] == stype]
                # 后端按 source 过滤
                if source:
                    alerts = [a for a in alerts if (a.get("source") or "") == source]
                # 后端按 brand 过滤(精确匹配或 applicant 包含)
                if brand:
                    bl = brand.lower()
                    alerts = [a for a in alerts
                              if (a.get("brand") or "").lower() == bl
                              or (a.get("applicant") or "").lower().find(bl) >= 0]
                alerts = alerts[:limit]
                # 解析 details_json,补充 auth_date/description 顶层字段
                import json as _json
                out = []
                for a in alerts:
                    row = _row_to_serializable(a)
                    details = {}
                    try:
                        details = _json.loads(a.get("details_json") or "{}")
                    except Exception:
                        pass
                    auth_date = details.get("auth_date", "")
                    desc = details.get("description", "")
                    # new_fcc_id/new_cert 信号缺 description,从 compintel_record 补
                    sid = a.get("source_id", "")
                    src = a.get("source", "fcc")
                    if (not desc or not auth_date) and sid:
                        rec = self.cidb.last_record(src, sid)
                        if rec:
                            if not desc:
                                desc = rec.get("description") or ""
                            if not auth_date:
                                auth_date = rec.get("auth_date") or ""
                    row["auth_date"] = auth_date
                    row["description"] = desc
                    out.append(row)
                self._json(out)
            elif path == "/api/records":
                source = qs.get("source", [None])[0]
                applicant = qs.get("applicant", [None])[0]
                brand = qs.get("brand", [None])[0]
                limit = int(qs.get("limit", ["100"])[0])
                recs = self.cidb.latest_records(source, applicant, brand, limit)
                self._json([_row_to_serializable(r) for r in recs])
            elif path == "/api/history":
                source = qs.get("source", [""])[0]
                sid = qs.get("source_id", [""])[0]
                if not source or not sid:
                    self._json([])
                    return
                hist = self.cidb.history(source, sid)
                self._json([_row_to_serializable(r) for r in hist])
            elif path == "/api/run":
                # 触发抓取（后台线程，避免阻塞 HTTP 响应）
                applicants = qs.get("applicants", [""])[0].split(",")
                applicants = [a.strip() for a in applicants if a.strip()]
                eprel_brands = qs.get("eprel_brands", [""])[0].split(",")
                eprel_brands = [b.strip() for b in eprel_brands if b.strip()]
                details = qs.get("details", ["0"])[0] in ("1", "true", "yes")
                if not applicants:
                    self._json({"error": "applicants required"}, 400)
                    return
                # 后台执行
                from .orchestrator import crawl_all
                t = threading.Thread(
                    target=crawl_all,
                    args=(self.db, applicants, eprel_brands or None, details),
                    daemon=True)
                t.start()
                self._json({"status": "started", "applicants": applicants,
                            "eprel_brands": eprel_brands, "details": details})
            elif path == "/api/analyze":
                # LLM 解读预警信号(聚好看内网接口,后台调用避免阻塞)
                mode = qs.get("mode", ["single"])[0]  # single|trend
                stype = qs.get("type", ["launch_warning"])[0]
                limit = int(qs.get("limit", ["10"])[0])
                brand = qs.get("brand", [""])[0]
                alerts = self.cidb.alerts_since("")
                if stype:
                    alerts = [a for a in alerts if a["signal_type"] == stype]
                # 品牌过滤
                if brand:
                    brand_lower = brand.lower()
                    if mode == "trend" and stype in ("launch_warning", "new_fcc_id"):
                        # launch_warning/new_fcc_id 不够时补 new_cert(只取该品牌的)
                        brand_alerts = [a for a in alerts
                                        if (a.get("brand") or "").lower() == brand_lower]
                        if len(brand_alerts) < 3:
                            all_alerts = self.cidb.alerts_since("")
                            extra_types = ("new_cert", "new_fcc_id", "eprel_new_reg")
                            new_ids = [a for a in all_alerts
                                       if a["signal_type"] in extra_types
                                       and (a.get("brand") or "").lower() == brand_lower]
                            brand_alerts = brand_alerts + new_ids[:20]
                        alerts = brand_alerts
                    else:
                        alerts = [a for a in alerts
                                  if (a.get("brand") or "").lower() == brand_lower]
                alerts = alerts[:limit]
                if not alerts:
                    self._json({"error": "无符合条件的预警信号"
                                + (f"(品牌 {brand} 无 {stype},可先触发抓取)" if brand else "")})
                    return
                from .llm_analyze import (analyze_launch_warning,
                                          analyze_cert_signal,
                                          analyze_competitor_trend)
                if mode == "trend":
                    result = analyze_competitor_trend(alerts, brand=brand, cidb=self.cidb)
                else:
                    # single 模式:用通用认证信号解读(支持所有 source)
                    result = [analyze_cert_signal(a, cidb=self.cidb) for a in alerts]
                self._json({"analysis": result, "count": len(alerts),
                            "mode": mode, "type": stype, "brand": brand})
            else:
                self._json({"error": "not found", "path": path}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 500)


def serve(port: int = 8088, db_path: str | None = None):
    """启动看板 HTTP 服务。"""
    db = Database(db_path)
    db.init_schema()
    cidb = CompIntelDB(db)

    DashboardHandler.cidb = cidb
    DashboardHandler.db = db

    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"竞品情报看板已启动: http://127.0.0.1:{port}/")
    print(f"DB: {db_path or 'default'}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        db.close()
        server.server_close()


if __name__ == "__main__":
    import sys
    port = 8088
    db_path = os.environ.get("OVERSEAS_DB_PATH")
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    serve(port, db_path)
