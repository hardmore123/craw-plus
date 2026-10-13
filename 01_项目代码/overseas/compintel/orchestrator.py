"""竞品情报抓取编排：按竞品名单跑 FCC + EPREL，落库并产生预警信号。

这是 CLI 与爬虫之间的薄编排层，不含抓取/解析逻辑（在 fcc_crawler/eprel_crawler），
也不含信号识别细节（在 alert）。只负责：建 run → 调爬虫 → 落库 → 调信号识别 → 收尾。
"""
from __future__ import annotations

import json
import os
from typing import Iterable

from ..db import Database
from ..fetchers import HttpFetcher
from ..infra import RateLimiter
from .compintel_db import CompIntelDB
from .fcc_crawler import FccCrawler, FccRecord
from .eprel_crawler import EprelCrawler, EprelRecord
from . import alert

# compintel 用独立限速器：FCC 聚合站 2s、EPREL 1.2s（官方限 5/s，留余量）
FCC_RATE = RateLimiter(min_interval=2.0, jitter=1.0)
EPREL_RATE = RateLimiter(min_interval=1.2, jitter=0.5)


def _now_ts() -> str:
    """当前 UTC 时间戳(与 db._now 一致格式)。"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ── 全量抓取：品牌关键词 → 授权码发现 ───────────────────────────────────────
# fccid.io 公司搜索是前缀匹配且结果被截断，必须：
#   1. 用多个关键词搜出所有关联公司的 grantee code
#   2. 遍历每个 grantee 的全部分页（那才是全量）
# 关键词要给足特异性："TCL" 太短返回 0 家；"TCL Overseas" 能搜到。
_BRAND_KEYWORDS: dict[str, list[str]] = {
    "Samsung": ["samsung", "Samsung Electronics", "Samsung Display",
                "Samsung Electro", "Samsung SDI"],
    "LG": ["LG Electronics", "LG Innotek", "LG Display", "Goldstar"],
    "Hisense": ["hisense", "Hisense Visual", "Qingdao Hisense",
                "Hisense Ronshen", "Qingdao Intelligent"],
    "TCL": ["TCL Overseas", "TCL Communication", "Shenzhen TCL",
            "TCL Entertainment", "TCL Technology", "TCL Industrial"],
    "Sony": ["sony", "Sony Group", "Sony Semiconductor"],
    "Panasonic": ["panasonic", "Panasonic Corporation", "Panasonic Industrial",
                  "Panasonic Automotive", "Panasonic Avionics", "Panasonic Connect"],
}

# 品牌过滤 token：只接受公司名含这些 token 的授权码（防止关键词误匹配）
# LG 用 "lg "（带空格避免误配）+ goldstar（LG 前身品牌）
_BRAND_TOKENS: dict[str, list[str]] = {
    "Samsung": ["samsung"],
    "LG": ["lg electronics", "lg innotek", "lg display", "goldstar", "gold star"],
    "Hisense": ["hisense"],
    "TCL": ["tcl"],
    "Sony": ["sony"],
    "Panasonic": ["panasonic"],
}

# 显式授权码别名：公司名不含品牌 token 的子公司（实测发现的公司）
# 例:Qingdao Intelligent&Precise Electronics 是 Hisense 子公司(产 WiFi/BT 模组)
_GRANTEE_ALIASES: dict[str, list[str]] = {
    "Hisense": ["2AJVQ"],
}


def discover_brand_grantees(crawler: FccCrawler,
                            brands: list[str]) -> dict[str, list[dict]]:
    """用品牌关键词发现所有关联授权码，返回 {brand: [{grantee_code, company, ...}]}。

    关键词表内置(_BRAND_KEYWORDS)，按品牌 token 过滤误匹配(_BRAND_TOKENS)。
    """
    out: dict[str, list[dict]] = {}
    for brand in brands:
        kws = _BRAND_KEYWORDS.get(brand, [brand])
        tokens = _BRAND_TOKENS.get(brand, [brand.lower()])
        found = crawler.discover_grantees(kws)
        aliases = _GRANTEE_ALIASES.get(brand, [])
        filtered = []
        for gc, info in found.items():
            name = (info.get("company") or "").lower()
            if any(t in name for t in tokens) or gc in aliases:
                filtered.append(info)
        # 补充显式别名里未发现的授权码
        have = {f["grantee_code"] for f in filtered}
        for gc in aliases:
            if gc not in have:
                filtered.append({"grantee_code": gc, "company": f"{brand}(alias)",
                                 "location": "", "registered": ""})
        out[brand] = sorted(filtered, key=lambda x: x["grantee_code"])
    return out


def crawl_fcc_full(db: Database, brands: list[str],
                   fetch_details: bool = False,
                   since: str = "",
                   max_pages: int = 0,
                   incremental: bool = True,
                   refresh_days: int = 0) -> dict:
    """FCC 全量抓取：发现授权码 → 遍历所有分页 → 落库 + 预警。

    比 crawl_fcc（公司名搜索）完整得多：公司名搜索会被截断（如 TCL 只给 33 条，
    但授权码 2ACCJ 有 508 条）。这是推荐的 FCC 抓取方式。

    brands: 标准竞品品牌名（Samsung/LG/Hisense/TCL/Sony/Panasonic）
    since: 只留 app_date >= since（默认近 365 天）
    max_pages: 每授权码最多抓几页（0=全部；调试可用 1）
    incremental: 增量模式(True)——授权码页按日期倒序，遇整页已知ID即停翻；
        首次抓取不受影响(known_ids 空→全抓)；二次抓取只翻到第1页全已知就停。
    refresh_days: N 天内抓过的授权码整码跳过(0=不跳过，每次都至少查第1页)。
        日常任务用 refresh_days=1(今天抓过的不重复)。
    返回 {ok, fail, new, grantees, signals, run_id, coverage, incremental}
    """
    from datetime import datetime, timedelta, timezone
    if not since:
        since = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")

    cidb = CompIntelDB(db)
    run_id = cidb.start_run("fcc_full_crawl",
                            {"brands": brands, "since": since,
                             "fetch_details": fetch_details,
                             "max_pages": max_pages,
                             "incremental": incremental,
                             "refresh_days": refresh_days},
                            site_code="fccid.io")
    ok = fail = new = 0
    skipped = 0
    all_signals: list[dict] = []
    coverage: dict[str, dict] = {}
    fetcher = HttpFetcher(rate_limiter=FCC_RATE)
    # 增量：预载已知 FCC ID（早停判断用）
    known_ids: set[str] | None = cidb.known_source_ids("fcc") if incremental else None
    now_utc = _now_ts()
    refresh_cutoff = (datetime.utcnow() - timedelta(days=refresh_days)
                      ).strftime("%Y-%m-%dT%H:%M:%S") if refresh_days > 0 else ""
    try:
        with FccCrawler(fetcher) as crawler:
            # 1. 发现授权码
            grantee_map = discover_brand_grantees(crawler, brands)
            # 2. 逐授权码全量遍历
            batch: list[dict] = []
            seen_in_run: set[str] = set()   # 同一 FCC ID 可能挂多个授权码,只入一次
            for brand, grantees in grantee_map.items():
                coverage[brand] = {"grantees": len(grantees), "records": 0,
                                   "codes": [g["grantee_code"] for g in grantees],
                                   "pages": 0, "skipped": 0}
                for g in grantees:
                    gc = g["grantee_code"]
                    # refresh_days：N 天内抓过整码跳过
                    if refresh_cutoff:
                        st = cidb.get_state("fcc", gc)
                        if st and st.get("last_crawled_at", "") >= refresh_cutoff:
                            skipped += 1
                            coverage[brand]["skipped"] += 1
                            continue
                    try:
                        recs, meta = crawler.list_grantee(
                            gc, max_pages=max_pages, since=since,
                            known_ids=known_ids)
                    except Exception as e:
                        fail += 1
                        cidb.log_error(run_id, f"fccid.io/{gc}",
                                       "grantee", "fetch", str(e))
                        continue
                    coverage[brand]["pages"] += meta["pages_fetched"]
                    page_new = 0
                    last_date = ""
                    for r in recs:
                        sid = r["fcc_id"]
                        if sid in seen_in_run:
                            continue   # 本次 run 已入(同 ID 挂多授权码)
                        seen_in_run.add(sid)
                        if r.get("app_date") and r["app_date"] > last_date:
                            last_date = r["app_date"]
                        rec_dict = {
                            "product_group": "",
                            "applicant": r.get("company") or brand,
                            "applicant_code": gc,
                            "brand": brand,
                            "model": sid,
                            "description": r.get("product") or "",
                            "auth_date": r.get("app_date") or "",
                            "frequency": "",
                            "extra_json": {"app_type": r.get("app_type", ""),
                                           "grantee_code": gc},
                        }
                        is_new = not cidb.seen_source_id("fcc", sid)
                        # 增量模式：已有记录不重复入库(只入新记录)，避免快照堆积
                        if incremental and not is_new:
                            coverage[brand]["records"] += 1  # 仍计入覆盖统计
                            continue
                        try:
                            cidb.add_record(run_id, "fcc", sid, **rec_dict)
                            ok += 1
                            coverage[brand]["records"] += 1
                            if is_new:
                                new += 1
                                page_new += 1
                            batch.append({
                                "source_id": sid,
                                "applicant": r.get("company") or brand,
                                "brand": brand,
                                "model": sid,
                                "auth_date": r.get("app_date") or "",
                                "description": r.get("product") or "",
                                "is_new": is_new,
                            })
                            if fetch_details:
                                try:
                                    docs = crawler.fetch_detail(sid)
                                    _store_docs(cidb, db, sid, docs)
                                    all_signals += alert.detect_confidential_expired(
                                        cidb, run_id, sid, docs)
                                except Exception:
                                    pass
                        except Exception as e:
                            fail += 1
                            cidb.log_error(run_id, sid, "store", "db", str(e))
                    # 更新该授权码的抓取状态
                    cidb.set_state("fcc", gc, last_crawled_at=now_utc,
                                   last_record_date=last_date,
                                   pages_crawled=meta["pages_fetched"],
                                   records_seen=len(recs), records_new=page_new,
                                   meta={"stopped_early": meta["stopped_early"],
                                         "total_pages": meta["total_pages"],
                                         "brand": brand})
            # 3. 信号
            all_signals += alert.detect_new_records(cidb, run_id, "fcc", batch)
            run_ts = cidb.conn.execute(
                "SELECT started_at FROM crawl_run WHERE id=?", (run_id,)).fetchone()
            cap_at = run_ts["started_at"] if run_ts else ""
            all_signals += alert.detect_supplier_change(cidb, run_id, "fcc", batch, cap_at)
            all_signals += alert.detect_field_changes(cidb, run_id, "fcc", batch, cap_at)
            all_signals += alert.detect_launch_warning(cidb, run_id, batch, "fcc", cap_at)
    except Exception as e:
        cidb.finish_run(run_id, "failed", ok, fail, str(e))
        return {"ok": ok, "fail": fail, "new": new, "skipped": skipped,
                "grantees": coverage, "signals": all_signals, "run_id": run_id,
                "error": str(e), "incremental": incremental}
    cidb.finish_run(run_id, "completed", ok, fail,
                    f"new={new} skipped={skipped} signals={len(all_signals)}")
    return {"ok": ok, "fail": fail, "new": new, "skipped": skipped,
            "grantees": coverage, "signals": all_signals, "run_id": run_id,
            "incremental": incremental}


def crawl_fcc(db: Database, applicants: list[str],
              fetch_details: bool = False,
              since: str = "") -> dict:
    """按竞品公司名列表抓 FCC 认证记录，落库 + 产生 new_fcc_id 信号。

    since: 只留认证日期(auth_date) >= since 的记录(YYYY-MM-DD)。
           限制时间范围,只抓近期新品,不堆旧认证。默认近 365 天。
    返回 {ok, fail, new, signals}。
    """
    # 默认只抓近 1 年的认证(竞品预警只关心新品,旧认证无意义)
    if not since:
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    cidb = CompIntelDB(db)
    run_id = cidb.start_run("fcc_crawl",
                            {"applicants": applicants, "fetch_details": fetch_details,
                             "since": since},
                            site_code="fccid.io")
    ok = fail = new = 0
    all_signals: list[dict] = []
    fetcher = HttpFetcher(rate_limiter=FCC_RATE)
    try:
        with FccCrawler(fetcher) as crawler:
            batch: list[dict] = []
            for applicant in applicants:
                try:
                    recs = crawler.search(applicant)
                except Exception as e:
                    fail += 1
                    cidb.log_error(run_id, f"fccid.io/search?q={applicant}",
                                   "search", "fetch", str(e))
                    continue
                for rec in recs:
                    # 时间过滤:只留 auth_date >= since 的近期认证
                    if rec.latest_filing and rec.latest_filing < since:
                        continue
                    rec_dict = _fcc_to_db_dict(rec, applicant)
                    is_new = not cidb.seen_source_id("fcc", rec.fcc_id)
                    try:
                        cidb.add_record(run_id, "fcc", rec.fcc_id, **rec_dict)
                        ok += 1
                        if is_new:
                            new += 1
                        batch.append({"source_id": rec.fcc_id,
                                      "applicant": rec.company or applicant,
                                      "brand": _normalize_brand(applicant),
                                      "model": rec.fcc_id,
                                      "auth_date": rec.latest_filing,
                                      "description": rec.description or "",
                                      "is_new": is_new})
                        # 保密文件检测（抓详情页文件清单）
                        if fetch_details:
                            try:
                                docs = crawler.fetch_detail(rec.fcc_id)
                                _store_docs(cidb, db, rec.fcc_id, docs)
                                all_signals += alert.detect_confidential_expired(
                                    cidb, run_id, rec.fcc_id, docs)
                            except Exception:
                                pass
                    except Exception as e:
                        fail += 1
                        cidb.log_error(run_id, rec.fcc_id, "store", "db", str(e))
            # 新记录信号（批量）— 用预存的 is_new 标志，避免被本次插入污染
            all_signals += alert.detect_new_records(cidb, run_id, "fcc", batch)
            # 供应商变更 / 字段变化（同 source_id 跨快照，用 run 开始时间作为 before 截点）
            run_ts = cidb.conn.execute(
                "SELECT started_at FROM crawl_run WHERE id=?", (run_id,)).fetchone()
            cap_at = run_ts["started_at"] if run_ts else ""
            all_signals += alert.detect_supplier_change(cidb, run_id, "fcc", batch, cap_at)
            all_signals += alert.detect_field_changes(cidb, run_id, "fcc", batch, cap_at)
            # 上市预警：产品类型过滤 + 在售比对 + 提前量（只对电视/显示器类新品）
            all_signals += alert.detect_launch_warning(cidb, run_id, batch, "fcc", cap_at)
    except Exception as e:
        cidb.finish_run(run_id, "failed", ok, fail, str(e))
        return {"ok": ok, "fail": fail, "new": new, "signals": all_signals, "run_id": run_id}
    cidb.finish_run(run_id, "completed", ok, fail, f"new={new} signals={len(all_signals)}")
    return {"ok": ok, "fail": fail, "new": new, "signals": all_signals, "run_id": run_id}


def crawl_eprel(db: Database, brands: list[str] | None = None,
                fetch_details: bool = False) -> dict:
    """抓 EPREL 电子显示器能效注册记录，落库 + 产生信号。

    brands: 要重点匹配的竞品品牌名（在 supplier_name 里做包含匹配）。
            None = 全量落库列表返回的 25 条（不按品牌过滤）。
    返回 {ok, fail, new, total, signals}。
    """
    cidb = CompIntelDB(db)
    run_id = cidb.start_run("eprel_crawl",
                            {"brands": brands, "fetch_details": fetch_details,
                             "group": "electronicdisplays"},
                            site_code="eprel")
    ok = fail = new = 0
    all_signals: list[dict] = []
    fetcher = HttpFetcher(rate_limiter=EPREL_RATE)
    try:
        with EprelCrawler(fetcher) as crawler:
            recs, total = crawler.list_recent()
            batch: list[dict] = []
            for rec in recs:
                # 品牌过滤：若指定 brands，只保留 supplier_name 含其中之一的
                if brands:
                    sup = (rec.supplier_name + " " + rec.organisation_name).lower()
                    if not any(b.lower() in sup for b in brands):
                        continue
                rec_dict = _eprel_to_db_dict(rec)
                is_new = not cidb.seen_source_id("eprel", rec.registration_number)
                try:
                    cidb.add_record(run_id, "eprel", rec.registration_number, **rec_dict)
                    ok += 1
                    if is_new:
                        new += 1
                    batch.append({"source_id": rec.registration_number,
                                  "applicant": rec.supplier_name,
                                  "brand": _normalize_brand(rec.supplier_name),
                                  "model": rec.model_identifier,
                                  "energy_class": rec.energy_class or rec.energy_class_sdr,
                                  "market_start": rec.on_market_start,
                                  "market_end": rec.on_market_end,
                                  "status": rec.status,
                                  "product_group": "electronicdisplays",
                                  "description": rec.model_identifier or "",
                                  "is_new": is_new})
                except Exception as e:
                    fail += 1
                    cidb.log_error(run_id, rec.registration_number, "store", "db", str(e))
            # 信号（用 run 开始时间作为 before 截点，确保 last_record 取到上次快照）
            run_ts = cidb.conn.execute(
                "SELECT started_at FROM crawl_run WHERE id=?", (run_id,)).fetchone()
            cap_at = run_ts["started_at"] if run_ts else ""
            all_signals += alert.detect_new_records(cidb, run_id, "eprel", batch)
            all_signals += alert.detect_delisted(cidb, run_id, batch, cap_at)
            all_signals += alert.detect_supplier_change(cidb, run_id, "eprel", batch, cap_at)
            all_signals += alert.detect_field_changes(cidb, run_id, "eprel", batch, cap_at)
            all_signals += alert.detect_launch_warning(cidb, run_id, batch, "eprel", cap_at)
            for b in (brands or []):
                all_signals += alert.detect_energy_class_jump(cidb, run_id, b, batch, cap_at)
    except Exception as e:
        cidb.finish_run(run_id, "failed", ok, fail, str(e))
        return {"ok": ok, "fail": fail, "new": new, "total": 0,
                "signals": all_signals, "run_id": run_id}
    cidb.finish_run(run_id, "completed", ok, fail,
                    f"new={new}/{total} signals={len(all_signals)}")
    return {"ok": ok, "fail": fail, "new": new, "total": total,
            "signals": all_signals, "run_id": run_id}


def crawl_eprel_scan(db: Database, brands: list[str] | None = None,
                     start: int = 1, end: int = 400000,
                     step: int = 1, max_results: int = 0,
                     since: str = "") -> dict:
    """EPREL 全量扫描：按注册号区间遍历详情 API，只留竞品品牌的电子显示器。

    EPREL 列表接口不可翻页，全量抓取只能靠注册号逐条查 /api/product/<reg>。
    注册号上限远超 size 字段值(size=37467 但 reg=99999 也有数据)。

    参数：
      brands: 只留 supplier 含这些品牌的记录(None=全留，慎用会很慢)
      start/end: 注册号区间(含两端)，默认 1~400000
      step: 步长(>1 为抽样省时间；=1 为全量遍历)
      max_results: 达到此数停止(0=不限)
      since: 只留上市日期(market_start) >= since 的记录(YYYY-MM-DD)。
             默认近 730 天(2年),只抓近期新品,不堆旧注册。

    返回 {ok, fail, new, total, scanned, signals, run_id}。

    耗时估算：
      step=1 全量: 40 万号 × 1.2s ≈ 12 小时(慎用)
      step=100 抽样: 4000 次 × 1.2s ≈ 80 分钟
      step=1000 抽样: 400 次 × 1.2s ≈ 8 分钟(推荐起步)
    """
    # 默认只抓近 2 年的注册(竞品预警只关心新品,旧注册无意义)
    if not since:
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=730)).strftime("%Y-%m-%d")
    cidb = CompIntelDB(db)
    run_id = cidb.start_run("eprel_scan",
                            {"brands": brands, "start": start, "end": end,
                             "step": step, "max_results": max_results,
                             "since": since},
                            site_code="eprel")
    ok = fail = new = scanned = 0
    all_signals: list[dict] = []
    fetcher = HttpFetcher(rate_limiter=EPREL_RATE)
    try:
        with EprelCrawler(fetcher) as crawler:
            recs = crawler.scan_range(start, end, step, brands, max_results)
            scanned = len(recs)
            batch: list[dict] = []
            for rec in recs:
                # 时间过滤:只留 market_start >= since 的近期注册
                ms = rec.on_market_start or ""
                if ms and ms < since:
                    continue
                is_new = not cidb.seen_source_id("eprel", rec.registration_number)
                try:
                    cidb.add_record(run_id, "eprel", rec.registration_number,
                                    **_eprel_to_db_dict(rec))
                    ok += 1
                    if is_new:
                        new += 1
                    batch.append({"source_id": rec.registration_number,
                                  "applicant": rec.supplier_name,
                                  "brand": _normalize_brand(rec.supplier_name),
                                  "model": rec.model_identifier,
                                  "energy_class": rec.energy_class or rec.energy_class_sdr,
                                  "market_start": rec.on_market_start,
                                  "market_end": rec.on_market_end,
                                  "status": rec.status,
                                  "product_group": "electronicdisplays",
                                  "description": rec.model_identifier or "",
                                  "is_new": is_new})
                except Exception as e:
                    fail += 1
                    cidb.log_error(run_id, rec.registration_number, "store", "db", str(e))
            # 信号
            run_ts = cidb.conn.execute(
                "SELECT started_at FROM crawl_run WHERE id=?", (run_id,)).fetchone()
            cap_at = run_ts["started_at"] if run_ts else ""
            all_signals += alert.detect_new_records(cidb, run_id, "eprel", batch)
            all_signals += alert.detect_launch_warning(cidb, run_id, batch, "eprel", cap_at)
            all_signals += alert.detect_delisted(cidb, run_id, batch, cap_at)
            all_signals += alert.detect_supplier_change(cidb, run_id, "eprel", batch, cap_at)
            all_signals += alert.detect_field_changes(cidb, run_id, "eprel", batch, cap_at)
            for b in (brands or []):
                all_signals += alert.detect_energy_class_jump(cidb, run_id, b, batch, cap_at)
    except Exception as e:
        cidb.finish_run(run_id, "failed", ok, fail, str(e))
        return {"ok": ok, "fail": fail, "new": new, "total": 0,
                "scanned": scanned, "signals": all_signals, "run_id": run_id}
    cidb.finish_run(run_id, "completed", ok, fail,
                    f"scanned={scanned} new={new} signals={len(all_signals)}")
    return {"ok": ok, "fail": fail, "new": new, "total": 0,
            "scanned": scanned, "signals": all_signals, "run_id": run_id}


# EPREL 各竞品的 supplier 搜索关键词(含子品牌)
# EPREL 的 supplierOrTrademark 字段可能是品牌名、子品牌名或集团名
EPREL_SUPPLIER_SEARCH = {
    "Samsung": ["Samsung"],
    "LG": ["LG", "HELGI", "elgato"],
    "Hisense": ["Hisense"],
    "TCL": ["TCL", "THOMSON"],
    "Sony": ["Sony", "SONY"],
    "Panasonic": ["Panasonic"],
}


def crawl_eprel_supplier(db: Database, brands: list[str] | None = None,
                        since: str = "") -> dict:
    """EPREL 按供应商名搜索:用 supplierOrTrademark 过滤器拉各竞品最新 25 条。

    EPREL API 的 offset 翻页不工作(不同 offset 返回相同记录),
    但 supplierOrTrademark 过滤器会改变返回的 25 条。
    近1年的新品通常出现在 offset=0 的 25 条中。

    每个竞品可能有多个 supplier 名(如 LG 有 HELGI/elgato/LG Electronics),
    需用多个搜索关键词覆盖。

    参数:
      brands: 竞品品牌列表(None=默认6大竞品)
      since: 只留 first_publication_date >= since 的记录(YYYY-MM-DD)
             默认近365天

    返回 {ok, fail, signals, run_id}。
    """
    if not since:
        from datetime import datetime, timedelta
        since = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")
    brands = brands or list(EPREL_SUPPLIER_SEARCH.keys())
    cidb = CompIntelDB(db)
    run_id = cidb.start_run("eprel_supplier",
                            {"brands": brands, "since": since, "mode": "supplier_search"},
                            site_code="eprel")
    ok = fail = 0
    all_signals: list[dict] = []
    all_records: list[dict] = []
    fetcher = HttpFetcher(rate_limiter=EPREL_RATE)
    try:
        with EprelCrawler(fetcher) as crawler:
            for group in ("electronicdisplays", "televisions"):
                for brand in brands:
                    search_terms = EPREL_SUPPLIER_SEARCH.get(brand, [brand])
                    for term in search_terms:
                        try:
                            recs, total = crawler.search_by_supplier(term, group)
                            for rec in recs:
                                # 时间过滤:只留近 since 的
                                pub = rec.first_publication_date or ""
                                if pub and pub < since:
                                    continue
                                # 品牌标准化(两级匹配)
                                db_dict = _eprel_to_db_dict(rec)
                                reg = rec.registration_number
                                is_new = not cidb.seen_source_id("eprel", reg)
                                db_dict["is_new"] = is_new
                                try:
                                    cidb.add_record(run_id, "eprel", reg, **db_dict)
                                    ok += 1
                                    all_records.append(db_dict)
                                except Exception as e:
                                    fail += 1
                                    cidb.log_error(run_id, reg, "eprel", "db", str(e))
                        except Exception as e:
                            cidb.log_error(run_id, "", "eprel", "search",
                                           f"{group}/{term}: {e}")
        # 信号生成
        all_signals += alert.detect_new_records(cidb, run_id, "eprel", all_records)
        all_signals += alert.detect_launch_warning(cidb, run_id, all_records, "eprel")
    except Exception as e:
        cidb.finish_run(run_id, "failed", ok, fail, str(e))
        return {"ok": ok, "fail": fail, "signals": all_signals, "run_id": run_id}
    cidb.finish_run(run_id, "completed", ok, fail,
                    f"signals={len(all_signals)}")
    return {"ok": ok, "fail": fail, "signals": all_signals, "run_id": run_id}


def crawl_all(db: Database, applicants: list[str],
              eprel_brands: list[str] | None = None,
              fetch_details: bool = False,
              since: str = "") -> dict:
    """一键全量更新：FCC(所有竞品公司) + EPREL，自动落库 + 出信号。

    定时任务入口。串行执行（单出口 IP，符合工程红线）。
    since: 时间截止(YYYY-MM-DD),只抓近期新品。默认由各子函数自定(FCC近365天)。
    返回 {fcc, eprel, signals_total}。
    """
    fcc_r = crawl_fcc(db, applicants, fetch_details=fetch_details, since=since)
    eprel_r = crawl_eprel(db, eprel_brands, fetch_details=fetch_details)
    return {
        "fcc": fcc_r,
        "eprel": eprel_r,
        "signals_total": len(fcc_r.get("signals", [])) + len(eprel_r.get("signals", [])),
    }


# ---------------- 新数据源编排(energystar/anatel/ic_ised/tuv/cb) ----------------

def crawl_energystar(db: Database, brands: list[str] | None = None,
                     since: str = "", categories: list[str] | None = None,
                     limit_per_brand: int = 5000) -> dict:
    """ENERGY STAR 能效认证抓取 → 落库 + 出信号。

    brands: 竞品品牌列表(None=默认 6 大)
    since: 只取 date_certified > since 的记录
    categories: 产品品类(None=TV+显示器,也可加白电)
    """
    from .energystar_crawler import EnergyStarCrawler, TV_DISPLAY_CATEGORIES
    fetcher = HttpFetcher(proxy=os.environ.get("OVERSEAS_PROXY", ""))
    crawler = EnergyStarCrawler(fetcher=fetcher)
    brands = brands or list(_BRAND_NORMALIZE.values())
    # 去重品牌名
    brands = list(set(brands))
    if categories is None:
        categories = TV_DISPLAY_CATEGORIES

    cidb = CompIntelDB(db)
    run_id = cidb.start_run("energystar_crawl", {
        "brands": brands, "since": since, "categories": categories})
    ok = 0
    fail = 0
    all_signals: list[dict] = []
    try:
        records = crawler.fetch_all_brands(
            brands=brands, since=since,
            categories=categories, limit_per_brand=limit_per_brand)
        for r in records:
            try:
                is_new = not cidb.seen_source_id("energystar", r["source_id"])
                r["is_new"] = is_new
                sid = r.pop("source_id")
                cidb.add_record(run_id, "energystar", sid, **r)
                ok += 1
            except Exception as e:
                fail += 1
                cidb.log_error(run_id, "", "energystar", "db", str(e))
        sigs = alert.detect_new_records(cidb, run_id, "energystar", records)
        all_signals.extend(sigs)
        # 上市预警:ENERGY STAR 含显示器/电视类,叠加产品类型过滤
        all_signals += alert.detect_launch_warning(cidb, run_id, records, "energystar")
    except Exception as e:
        cidb.log_error(run_id, "", "energystar", "fatal", str(e))
    cidb.finish_run(run_id, "completed", ok, fail)
    return {"records": ok, "fail": fail, "signals": all_signals}


def crawl_anatel(db: Database, brands: list[str] | None = None,
                 since: str = "") -> dict:
    """ANATEL 巴西电信认证抓取 → 落库 + 出信号。

    下载全量 ZIP-CSV(19万条),按制造商名过滤竞品。
    """
    from .anatel_crawler import AnatelCrawler
    fetcher = HttpFetcher(proxy=os.environ.get("OVERSEAS_PROXY", ""))
    crawler = AnatelCrawler(fetcher=fetcher)
    brands = brands or list(set(_BRAND_NORMALIZE.values()))

    cidb = CompIntelDB(db)
    run_id = cidb.start_run("anatel_crawl", {
        "brands": brands, "since": since})
    ok = 0
    fail = 0
    all_signals: list[dict] = []
    try:
        records = crawler.fetch_all(brands=brands, since=since)
        for r in records:
            try:
                is_new = not cidb.seen_source_id("anatel", r["source_id"])
                r["is_new"] = is_new
                sid = r.pop("source_id")
                cidb.add_record(run_id, "anatel", sid, **r)
                ok += 1
            except Exception as e:
                fail += 1
                cidb.log_error(run_id, "", "anatel", "db", str(e))
        sigs = alert.detect_new_records(cidb, run_id, "anatel", records)
        all_signals.extend(sigs)
        # 上市预警:ANATEL 含电视类,叠加产品类型过滤
        all_signals += alert.detect_launch_warning(cidb, run_id, records, "anatel")
    except Exception as e:
        cidb.log_error(run_id, "", "anatel", "fatal", str(e))
    cidb.finish_run(run_id, "completed", ok, fail)
    return {"records": ok, "fail": fail, "signals": all_signals}


def crawl_ic_ised(db: Database, brands: list[str] | None = None,
                 since: str = "") -> dict:
    """IC/ISED 加拿大无线电认证抓取 → 落库 + 出信号。

    按公司名搜公司号 → 按 Company Number 查 REL。
    """
    from .ic_ised_crawler import IcedCrawler
    proxy = os.environ.get("OVERSEAS_PROXY", "")
    crawler = IcedCrawler(proxy=proxy)
    brands = brands or list(set(_BRAND_NORMALIZE.values()))

    cidb = CompIntelDB(db)
    run_id = cidb.start_run("ic_ised_crawl", {
        "brands": brands, "since": since})
    ok = 0
    fail = 0
    all_signals: list[dict] = []
    try:
        records = crawler.fetch_all_brands(brands=brands, since=since)
        for r in records:
            try:
                is_new = not cidb.seen_source_id("ic_ised", r["source_id"])
                r["is_new"] = is_new
                sid = r.pop("source_id")
                cidb.add_record(run_id, "ic_ised", sid, **r)
                ok += 1
            except Exception as e:
                fail += 1
                cidb.log_error(run_id, "", "ic_ised", "db", str(e))
        sigs = alert.detect_new_records(cidb, run_id, "ic_ised", records)
        all_signals.extend(sigs)
        # 上市预警:IC/ISED 含电视类,叠加产品类型过滤
        all_signals += alert.detect_launch_warning(cidb, run_id, records, "ic_ised")
    except Exception as e:
        cidb.log_error(run_id, "", "ic_ised", "fatal", str(e))
    cidb.finish_run(run_id, "completed", ok, fail)
    return {"records": ok, "fail": fail, "signals": all_signals}


def crawl_certs(db: Database, brands: list[str] | None = None) -> dict:
    """TÜV Rheinland + VDE/CB 安全认证抓取 → 落库 + 出信号。

    复用 crawl4ai-main/cert_verify 包的 Provider。
    """
    from .cert_crawler import TuvCertCrawler, VdeCertCrawler, _HAS_CERT_VERIFY
    if not _HAS_CERT_VERIFY:
        return {"error": "cert_verify 包不可用"}
    proxy = os.environ.get("OVERSEAS_PROXY", "")
    brands = brands or list(set(_BRAND_NORMALIZE.values()))

    cidb = CompIntelDB(db)
    run_id = cidb.start_run("cert_crawl", {"brands": brands})
    ok = 0
    fail = 0
    all_signals: list[dict] = []
    try:
        # TÜV Rheinland
        try:
            tuv = TuvCertCrawler(proxy=proxy)
            tuv_recs = tuv.fetch_all_brands(brands=brands)
            for r in tuv_recs:
                # 过滤未匹配到竞品品牌的记录
                if not r.get("brand"):
                    continue
                try:
                    is_new = not cidb.seen_source_id("tuv", r["source_id"])
                    r["is_new"] = is_new
                    sid = r.pop("source_id")
                    cidb.add_record(run_id, "tuv", sid, **r)
                    ok += 1
                except Exception as e:
                    fail += 1
            sigs = alert.detect_new_records(cidb, run_id, "tuv", tuv_recs)
            all_signals.extend(sigs)
            # 上市预警:TÜV 含电视/显示器安全认证,叠加产品类型过滤
            all_signals += alert.detect_launch_warning(cidb, run_id, tuv_recs, "tuv")
        except Exception as e:
            cidb.log_error(run_id, "", "tuv", "fatal", str(e))

        # VDE/CB
        try:
            vde = VdeCertCrawler(proxy=proxy)
            vde_recs = vde.fetch_all_brands(brands=brands)
            for r in vde_recs:
                # 过滤未匹配到竞品品牌的记录(VDE Solr 宽泛搜索会返回无关公司)
                if not r.get("brand"):
                    continue
                try:
                    is_new = not cidb.seen_source_id("ul", r["source_id"])
                    r["is_new"] = is_new
                    sid = r.pop("source_id")
                    cidb.add_record(run_id, "ul", sid, **r)
                    ok += 1
                except Exception as e:
                    fail += 1
            sigs = alert.detect_new_records(cidb, run_id, "ul", vde_recs)
            all_signals.extend(sigs)
            # 上市预警:VDE/CB 含电视/显示器安全认证,叠加产品类型过滤
            all_signals += alert.detect_launch_warning(cidb, run_id, vde_recs, "ul")
        except Exception as e:
            cidb.log_error(run_id, "", "vde", "fatal", str(e))
    except Exception as e:
        cidb.log_error(run_id, "", "cert", "fatal", str(e))
    cidb.finish_run(run_id, "completed", ok, fail)
    return {"records": ok, "fail": fail, "signals": all_signals}


def crawl_all_extended(db: Database, brands: list[str] | None = None,
                       sources: list[str] | None = None,
                       since: str = "") -> dict:
    """一键全量更新：所有新数据源(energystar/anatel/ic_ised/tuv/cb)。

    串行执行（单出口 IP，符合工程红线）。
    sources: 指定数据源列表(None=全部),可选:
      energystar / anatel / ic_ised / certs
    """
    brands = brands or list(set(_BRAND_NORMALIZE.values()))
    sources = sources or ["energystar", "anatel", "ic_ised", "certs", "eprel"]
    results: dict = {}
    total_signals = 0

    if "energystar" in sources:
        r = crawl_energystar(db, brands=brands, since=since)
        results["energystar"] = r
        total_signals += len(r.get("signals", []))

    if "anatel" in sources:
        r = crawl_anatel(db, brands=brands, since=since)
        results["anatel"] = r
        total_signals += len(r.get("signals", []))

    if "ic_ised" in sources:
        r = crawl_ic_ised(db, brands=brands, since=since)
        results["ic_ised"] = r
        total_signals += len(r.get("signals", []))

    if "certs" in sources:
        r = crawl_certs(db, brands=brands)
        results["certs"] = r
        total_signals += len(r.get("signals", []))

    if "eprel" in sources:
        r = crawl_eprel_supplier(db, brands=brands, since=since)
        results["eprel"] = r
        total_signals += len(r.get("signals", []))

    results["signals_total"] = total_signals
    return results


# ---------------- 记录 dict 转换 ----------------

# 竞品公司名 → 标准品牌名归一化
# TCL 在 fccid.io 搜 "TCL" 返回 0 条,需搜多个变体:
#   "TCL Electronics" / "TCL Technology" / "TCL Overseas" / "TCL Communication"
# 搜到的记录 brand 统一归一化为 "TCL",便于按竞品聚合
_BRAND_NORMALIZE = {
    # TCL 变体
    "tcl electronics": "TCL",
    "tcl technology": "TCL",
    "tcl technoly electronics": "TCL",
    "tcl overseas": "TCL",
    "tcl communication": "TCL",
    "tcl industrial": "TCL",
    "tcl corp": "TCL",
    "tcl mits": "TCL",
    "tcl holdings": "TCL",
    "tcl ": "TCL",
    "tcl": "TCL",
    # Samsung
    "samsung electronics": "Samsung",
    "samsung": "Samsung",
    # LG
    "lg electronics": "LG",
    "lg ": "LG",
    "lg": "LG",
    # Hisense
    "hisense": "Hisense",
    # Sony
    "sony": "Sony",
    # Panasonic
    "panasonic": "Panasonic",
}


def _normalize_brand(applicant: str) -> str:
    """把搜索用的公司名归一化为标准竞品品牌名。

    用 startswith 匹配,所以关键词按长到短排列(先匹配 "samsung electronics" 再 "samsung")。
    """
    low = (applicant or "").lower().strip()
    for key, val in _BRAND_NORMALIZE.items():
        if low.startswith(key):
            return val
    return applicant


def _fcc_to_db_dict(rec: FccRecord, applicant: str) -> dict:
    return {
        "product_group": "",                  # FCC 设备类需详情页才能细分
        "applicant": rec.company or applicant,
        "applicant_code": rec.grantee_code,
        "brand": _normalize_brand(applicant),
        "model": rec.fcc_id,
        "description": rec.description,
        "auth_date": rec.latest_filing,
        "frequency": rec.frequencies,
        "extra_json": {"grantee_registered": rec.grantee_registered,
                       "product_code": rec.product_code,
                       "matched_docs": rec.matched_docs},
    }


def _eprel_to_db_dict(rec: EprelRecord) -> dict:
    # EPREL 的 supplier_name 可能是子品牌(如THOMSON),organisation_name 含集团名(如TCL Operations)
    # 用两者一起做品牌标准化,优先用 supplier_name 匹配,再用 organisation_name
    brand = _normalize_brand(rec.supplier_name or "")
    if brand == (rec.supplier_name or "") and rec.organisation_name:
        # supplier_name 未匹配到标准品牌,尝试 organisation_name
        org_brand = _normalize_brand(rec.organisation_name)
        if org_brand != rec.organisation_name:
            brand = org_brand
    return {
        "product_group": rec.product_group,
        "applicant": rec.supplier_name or rec.organisation_name,
        "applicant_code": "",                 # EPREL org guid 在 extra
        "brand": brand,
        "model": rec.model_identifier,
        "description": f"{rec.panel_technology} {rec.diagonal_inch}in "
                       f"{rec.resolution_h}x{rec.resolution_v}".strip(),
        "auth_date": rec.first_publication_date,
        "market_start": rec.on_market_start,
        "market_end": rec.on_market_end,
        "energy_class": rec.energy_class or rec.energy_class_sdr,
        "extra_json": {"organisation": rec.organisation_name,
                       "website": rec.organisation_website,
                       "energy_class_hdr": rec.energy_class_hdr,
                       "published_on_date": rec.published_on_date,
                       "published_on_ts": rec.published_on_ts,
                       "diagonal_cm": rec.diagonal_cm,
                       "resolution_h": rec.resolution_h,
                       "resolution_v": rec.resolution_v,
                       "power_on_sdr": rec.power_on_sdr,
                       "power_on_hdr": rec.power_on_hdr,
                       "power_standby": rec.power_standby,
                       "status": rec.status,
                       "extra": rec.extra},
    }


def _store_docs(cidb: CompIntelDB, db: Database, fcc_id: str, docs: list[dict]) -> None:
    """把 FCC 详情页文件清单落 compintel_doc。"""
    row = db.conn.execute(
        "SELECT id FROM compintel_record WHERE source='fcc' AND source_id=? "
        "ORDER BY captured_at DESC LIMIT 1", (fcc_id,)).fetchone()
    if not row:
        return
    record_id = int(row["id"])
    for d in docs:
        cidb.add_doc(record_id, d.get("doc_type", ""), d.get("doc_name", ""),
                     d.get("url", ""), d.get("doc_date", ""))
