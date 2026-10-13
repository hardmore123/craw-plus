# -*- coding: utf-8 -*-
"""从 DB 重建 Amazon 三站全量价格/网评 CSV/XLSX（供验收 §5/§10 使用）。

背景：supervisor 按"剩余型号分片"逐轮跑 crawl_ca_retail.py，每轮导出只覆盖
当轮子集，文件互相覆盖。DB（price_snapshot / review / product /
retail_task_status）是累积全量，故用本脚本从 DB 重建一次完整导出，
列格式与 crawl_ca_retail.py 的导出（price_export_ca / review_export）一致。

数据来源：
  - 价格：retail_task_status（task='price'，每型号最新一条的 price/brand/size）
  - 网评：review JOIN product（按站点全量取出）
  - 型号清单：data/<区域>/SPEC_型号汇总_<region>_*.csv（最新，决定行顺序）

用法：
  python scripts/rebuild_amazon_csvs.py                  # 三站全部
  python scripts/rebuild_amazon_csvs.py --region us      # 只重建一站
  python scripts/rebuild_amazon_csvs.py --out-dir data/_rebuilt
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # 项目根（原写死 C:\...\海外）
sys.path.insert(0, str(ROOT))
_MAIN_DB = Path(os.environ.get("OVERSEAS_DB_PATH") or ROOT / "data" / "overseas.db")

from overseas.regions_config import get_region
from overseas.price_export_ca import CaPriceRecord
from overseas.price_export_ca import write_csv as price_write_csv
from overseas.price_export_ca import write_xlsx as price_write_xlsx
from overseas.review_export import ReviewRecord
from overseas.review_export import write_csv as review_write_csv
from overseas.review_export import write_xlsx as review_write_xlsx

DB_BY_REGION = {
    "us": _MAIN_DB,
    "ca": _MAIN_DB,
    "mx": _MAIN_DB,          # 统一主库（原 data/mx/overseas_mx.db 已并入）
}
SITE_BY_REGION = {"us": "amazon_us", "mx": "amazon_mx", "ca": "amazon_ca"}
CN_DIR = {"us": "美国", "mx": "墨西哥", "ca": "加拿大"}
LOG_FILE = ROOT / "data" / "logs" / "rebuild_amazon_csvs.log"


def log(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(LOG_FILE.parent, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def default_models_csv(region_code: str) -> Path:
    """与 crawl_ca_retail._default_models_csv 相同的解析顺序。"""
    d = ROOT / "data" / CN_DIR[region_code]
    if d.is_dir():
        matches = sorted(d.glob("SPEC_型号汇总_%s_*.csv" % region_code), reverse=True)
        if matches:
            return matches[0]
        legacy = d / ("SPEC_型号汇总_%s.csv" % region_code)
        if legacy.exists():
            return legacy
    return ROOT / "data" / ("SPEC_型号汇总_%s.csv" % region_code)


def read_catalog(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def model_key(row: dict) -> str:
    return (row.get("model_raw") or "").strip().split(" | ")[0]


def collect_price_map(con: sqlite3.Connection, site_code: str) -> dict[str, dict]:
    """retail_task_status 按型号取最新一条 price 记录。{model: {...}}"""
    rows = con.execute(
        "SELECT model, brand_name, size, price, currency, captured_at, status "
        "FROM retail_task_status "
        "WHERE site_code=? AND task='price' AND model IS NOT NULL AND model<>'' "
        "ORDER BY captured_at DESC",
        (site_code,),
    ).fetchall()
    out: dict[str, dict] = {}
    for (model, brand, size, price, currency, captured_at, status) in rows:
        if model in out:
            continue  # 已取最新
        out[model] = dict(model=model, brand=brand or "", size=size or "",
                          price=price, currency=currency or "",
                          captured_at=captured_at or "", status=status or "")
    return out


def build_price_records(region_code: str, site_code: str,
                        price_map: dict[str, dict]) -> list[CaPriceRecord]:
    """按型号清单顺序生成一行一机型（对齐 crawl 的 build_price_records）。"""
    region = get_region(region_code)
    country = region.name if region else region_code
    currency = region.currency if region else ""
    full = read_model_csv(region_code, site_code)
    records: list[CaPriceRecord] = []
    seen: set[str] = set()
    for row in full:
        model = model_key(row)
        if not model or model in seen:
            continue
        seen.add(model)
        pm = price_map.get(model) or {}
        price = pm.get("price")
        records.append(CaPriceRecord(
            country=country,
            brand=pm.get("brand") or row.get("brand_name") or "",
            model=model,
            size=pm.get("size") or "",
            currency=currency,
            retail_prices={site_code: price} if price is not None else {},
            captured_at=pm.get("captured_at") or "",
        ))
    return records


def read_model_csv(region_code: str, site_code: str) -> list[dict]:
    return [r for r in read_catalog(default_models_csv(region_code)) if r.get("model_raw")]


def site_display_name(con: sqlite3.Connection, site_id: int) -> str:
    try:
        row = con.execute("SELECT code, name FROM site WHERE id=?", (site_id,)).fetchone()
        if not row:
            return ""
        code, name = row
        try:
            from overseas.sites import SiteRegistry
            adapter = SiteRegistry.get(code)
            if adapter is not None:
                return adapter.channel or adapter.name
        except Exception:
            pass
        return name or ""
    except Exception:
        return ""


def build_review_records(con: sqlite3.Connection, site_id: int,
                         region_code: str) -> list[ReviewRecord]:
    region = get_region(region_code)
    country = region.name if region else region_code
    channel = site_display_name(con, site_id) or SITE_BY_REGION[region_code]

    # 每 product 最新价格（用于"价格"列）
    latest_price: dict[int, float] = {}
    for pid, price in con.execute(
        "SELECT product_id, price FROM price_snapshot WHERE id IN "
        "(SELECT MAX(id) FROM price_snapshot GROUP BY product_id)"
    ).fetchall():
        if price is not None:
            latest_price[pid] = price

    rows = con.execute(
        "SELECT r.rating, r.title, r.body, r.review_date, r.helpful_count,"
        " r.review_url, r.image_count, r.image_urls, r.video_urls, r.has_video,"
        " p.id, p.sku, p.size, p.brand, p.model "
        "FROM review r JOIN product p ON p.id = r.product_id "
        "WHERE p.site_id=? ORDER BY p.id, r.review_date",
        (site_id,),
    ).fetchall()

    out: list[ReviewRecord] = []
    for (rating, title, body, rdate, helpful, rurl,
         img_count, img_urls, video_urls, has_video,
         pid, sku, size, brand, model) in rows:
        price = latest_price.get(pid)
        out.append(ReviewRecord(
            country=country, brand=brand or "", model=model or "",
            channel=channel, size=size or "",
            rating=rating if rating is not None else "",
            title=title or "", body=body or "",
            helpful=helpful if helpful is not None else "",
            review_time=rdate or "", review_url=rurl or "",
            image_count=img_count if img_count is not None else 0,
            image_urls=img_urls or "",
            has_video="是" if has_video else "否",
            video_urls=video_urls or "",
            item_id=sku or "",
            price="" if price is None else price,
        ))
    return out


def rebuild_region(region_code: str, out_dir: Path | None) -> None:
    site_code = SITE_BY_REGION[region_code]
    db_path = DB_BY_REGION[region_code]
    if not db_path.exists():
        log("DB 不存在: %s，跳过 %s" % (db_path, region_code))
        return
    con = sqlite3.connect(db_path)
    try:
        site_row = con.execute("SELECT id FROM site WHERE code=?", (site_code,)).fetchone()
        if not site_row:
            log("站点 %s 未在库中注册，跳过 %s" % (site_code, region_code))
            return
        site_id = site_row[0]

        price_map = collect_price_map(con, site_code)
        price_recs = build_price_records(region_code, site_code, price_map)
        review_recs = build_review_records(con, site_id, region_code)

        region = get_region(region_code)
        cname = region.name if region else region_code
        target = out_dir or (ROOT / "data" / cname)
        target.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d")

        p_csv = target / ("价格监控_%s_%s.csv" % (cname, stamp))
        p_xlsx = target / ("价格监控_%s_%s.xlsx" % (cname, stamp))
        r_csv = target / ("网评汇总_%s_%s.csv" % (cname, stamp))
        r_xlsx = target / ("网评汇总_%s_%s.xlsx" % (cname, stamp))

        n_price = price_write_csv(p_csv, price_recs, region_code)
        n_review = review_write_csv(r_csv, review_recs)
        try:
            price_write_xlsx(p_xlsx, price_recs, region_code)
        except Exception as e:
            log("价格 XLSX 失败: %s" % e)
        try:
            review_write_xlsx(r_xlsx, review_recs)
        except Exception as e:
            log("网评 XLSX 失败: %s" % e)

        priced = sum(1 for r_ in price_recs if r_.retail_prices)
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        log("== %s: 型号=%d 有价=%d 网评=%d -> %s / %s integrity=%s" % (
            region_code, len(price_recs), priced, n_review,
            p_csv.name, r_csv.name, integrity))
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="从 DB 重建 Amazon 三站全量导出")
    ap.add_argument("--region", choices=["us", "mx", "ca"], default=None)
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args(argv)
    targets = [args.region] if args.region else ["us", "mx", "ca"]
    out_dir = Path(args.out_dir) if args.out_dir else None
    for rc in targets:
        try:
            rebuild_region(rc, out_dir)
        except Exception as e:
            log("ERROR %s: %s" % (rc, e))
    log("rebuild done: %s" % targets)
    return 0


if __name__ == "__main__":
    sys.exit(main())