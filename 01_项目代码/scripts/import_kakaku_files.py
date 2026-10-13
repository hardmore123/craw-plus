"""把已抓好的 kakaku 价格/评论 CSV 直接导入数据库，避免重新抓取。

适用场景：`crawl_kakaku_prices.py` / `crawl_kakaku_reviews.py` 已产出 CSV，
但当时未加 --save-db；用本脚本把文件回灌入库即可（秒级完成）。

导入价格 CSV（价格监控模板，19 列）：
    product / price_snapshot（最低价）/ price_shop_snapshot（各店铺）/ kakaku_task_status
导入评论 CSV（通用网评模板，20 列）：
    product / review（按 review_key 增量去重）/ kakaku_task_status
    review_key 从「评论链接」提取：bbs=SortID、レビュー=ReviewCD，取不到用正文哈希。

示例：
    python scripts/import_kakaku_files.py --prices data/价格监控_全部品牌全部机型_kakaku_20260909.csv
    python scripts/import_kakaku_files.py --reviews data/网评汇总_hisense_kakaku_20260908.csv
    python scripts/import_kakaku_files.py --prices <价格csv> --reviews <评论csv>
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                       # noqa: E402
from overseas.db import Database                  # noqa: E402
from overseas.models import PriceSnapshot, Product, Review  # noqa: E402
from overseas.price_export import SHOP_COLUMN_NAMES, SHOP_COLUMN_ZH  # noqa: E402
from overseas.sites import SiteRegistry           # noqa: E402

# 品牌展示名 → code（CSV 里存的是展示名）
DISPLAY_TO_CODE = {
    "Hisense": "hisense_jp",
    "SONY": "sony_jp",
    "REGZA": "regza_jp",
    "Panasonic": "panasonic_jp",
    "TCL": "tcl_jp",
    "SHARP": "sharp_jp",
}


def _to_int(value: str):
    v = (value or "").replace(",", "").strip()
    return int(v) if v.isdigit() else None


def _release_year(text: str):
    m = re.search(r"(20\d\d)\s*年", text or "")
    return int(m.group(1)) if m else None


def _review_key_from_url(url: str, body: str) -> str:
    """从评论链接提取稳定 key；取不到用正文哈希。与抓取脚本规则一致。"""
    m = re.search(r"ReviewCD=(\d+)", url or "")
    if m:
        return f"ReviewCD={m.group(1)}"
    m = re.search(r"SortID=(\d+)", url or "")
    if m:
        return f"bbs:{m.group(1)}"
    digest = hashlib.sha1((body or "")[:80].encode("utf-8", "replace")).hexdigest()[:16]
    return f"hash:{digest}"


def import_prices(db: Database, adapter, site_id: int, run_id: int, path: Path,
                  currency: str = "JPY") -> tuple[int, int]:
    """导入价格 CSV。返回 (机型数, 店铺价条数)。"""
    n_models = 0
    n_shop = 0
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            model = (row.get("机型") or "").strip()
            item_id = (row.get("商品ID") or "").strip()
            if not model or model.startswith("【") or not item_id:
                continue          # 跳过品牌分隔行与无商品行
            display = (row.get("品牌") or "").strip()
            brand = DISPLAY_TO_CODE.get(display, display)
            size = (row.get("尺寸") or "").strip()
            release = (row.get("上市时间") or "").strip()
            lowest = _to_int(row.get("最低价"))
            product = Product(
                site_code=adapter.code, sku=item_id,
                url=row.get("商品链接") or adapter.item_url(item_id),
                title=f"{display} {model}".strip(), brand=display,
                model=model, category="TV", size=size)
            pid = db.upsert_product(product, site_id)
            if lowest is not None:
                db.add_price(pid, PriceSnapshot(price=float(lowest),
                             currency=currency, raw_text=str(lowest)))
            shops = {}
            for name in SHOP_COLUMN_NAMES:
                # 兼容两种表头：旧文件用日文列名，新导出用中文列名；内部仍以日文 key 存。
                v = _to_int(row.get(name))
                if v is None:
                    v = _to_int(row.get(SHOP_COLUMN_ZH.get(name, name)))
                if v is not None:
                    shops[name] = v
            n_shop += db.add_shop_prices(pid, shops, currency=currency,
                                         lowest_shop=(row.get("最安店铺") or "").strip())
            db.record_kakaku_status(
                task="price", brand=brand, model=model, status="ok",
                run_id=run_id, brand_name=display, item_id=item_id,
                product_id=pid, release_text=release,
                release_year=_release_year(release), size=size,
                row_count=len(shops), message="imported from CSV")
            n_models += 1
    return n_models, n_shop


def import_reviews(db: Database, adapter, site_id: int, run_id: int,
                   path: Path) -> tuple[int, int]:
    """导入评论 CSV。返回 (机型数, 新增评价条数)。"""
    # 先按型号聚合评价（同一型号的多条评论一次写库，便于增量去重统计）
    by_model: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            model = (row.get("型号") or "").strip()
            item_id = (row.get("商品ID") or "").strip()
            if not model or not item_id:
                continue
            entry = by_model.setdefault(item_id, {
                "model": model,
                "display": (row.get("品牌") or "").strip(),
                "size": (row.get("尺寸") or "").strip(),
                "release": (row.get("评论时间") or "").strip(),
                "reviews": [],
            })
            body = (row.get("网评内容") or "").strip()
            if not body:
                continue
            url = (row.get("评论链接") or "").strip()
            rating = (row.get("网评分数(星级)") or "").strip()
            entry["reviews"].append(Review(
                review_key=_review_key_from_url(url, body),
                rating=float(rating) if rating.replace(".", "").isdigit() else None,
                title=(row.get("网评标题") or "").strip(),
                body=body,
                review_date=(row.get("评论时间") or "").strip(),
                review_url=url))

    n_models = 0
    n_new = 0
    for item_id, entry in by_model.items():
        display = entry["display"]
        brand = DISPLAY_TO_CODE.get(display, display)
        product = Product(
            site_code=adapter.code, sku=item_id,
            url=adapter.item_url(item_id),
            title=f"{display} {entry['model']}".strip(), brand=display,
            model=entry["model"], category="TV", size=entry["size"])
        pid = db.upsert_product(product, site_id)
        new = db.add_reviews(pid, entry["reviews"]) if entry["reviews"] else 0
        n_new += new
        db.record_kakaku_status(
            task="review", brand=brand, model=entry["model"],
            status="ok" if entry["reviews"] else "no_reviews",
            run_id=run_id, brand_name=display, item_id=item_id,
            product_id=pid, size=entry["size"],
            row_count=len(entry["reviews"]), new_count=new,
            message="imported from CSV")
        n_models += 1
    return n_models, n_new


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="把已抓的 kakaku 价格/评论 CSV 导入数据库")
    p.add_argument("--prices", help="价格监控 CSV 路径")
    p.add_argument("--reviews", help="网评汇总 CSV 路径")
    p.add_argument("--db", help="SQLite 路径，缺省用 OVERSEAS_DB_PATH 或 data/overseas.db")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.prices and not args.reviews:
        print("[ERROR] 至少指定 --prices 或 --reviews")
        return 2
    config.ensure_dirs()
    adapter = SiteRegistry.get("kakaku_jp")
    db = Database(args.db)
    db.init_schema()
    site_id = db.upsert_site(adapter.code, adapter.name, adapter.base_url,
                             adapter.protection)
    try:
        if args.prices:
            path = Path(args.prices)
            if not path.exists():
                print(f"[ERROR] 价格文件不存在: {path}")
            else:
                run_id = db.start_run("kakaku_price_import", adapter.code,
                                      {"file": str(path)})
                nm, ns = import_prices(db, adapter, site_id, run_id, path)
                db.finish_run(run_id, "completed", nm, 0, f"models={nm} shops={ns}")
                print(f"[价格] 导入 {nm} 个机型，{ns} 条店铺价 ← {path.name}")
        if args.reviews:
            path = Path(args.reviews)
            if not path.exists():
                print(f"[ERROR] 评论文件不存在: {path}")
            else:
                run_id = db.start_run("kakaku_review_import", adapter.code,
                                      {"file": str(path)})
                nm, nn = import_reviews(db, adapter, site_id, run_id, path)
                db.finish_run(run_id, "completed", nm, 0, f"models={nm} new={nn}")
                print(f"[评论] 导入 {nm} 个机型，新增 {nn} 条评价 ← {path.name}")
        print(f"[DB] 统计={db.stats()}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
