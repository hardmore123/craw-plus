"""在 価格.com（kakaku.com）抓取指定品牌电视的各店铺分列价格，按价格监控模板导出。

数据来源：https://kakaku.com/kaden/lcd-tv 覆盖的液晶/有机 EL 电视商品页。
默认针对海信（hisense_jp），型号清单来自 SPEC 型号汇总 CSV
（scripts/export_spec_models.py 产出，与评价抓取共用）。

流程（每个型号）：
    型号 → search.kakaku.com 定位商品 item id
         → 商品页读：最安価格（第一列标的「最低价」）、发售日、尺寸
         → 解析主要店铺一览（ul.p-priceList_list），取模板 8 家店铺各自售价
         → 一行一机型输出

输出模板：overseas/price_export.py 的价格监控宽表：
    品牌 | 机型 | 尺寸 | 上市时间 | 最低价 | 8 个店铺列 | 溯源列
第一列「最低价」= kakaku 页面顶部「最安価格」（全站最低标的价）。
8 个店铺列覆盖模板约定的日本大型电商（Edion/ヨドバシ/ヤマダ/BIC/ケーズ/Joshin/
ノジマ/Amazon）；某店铺本商品无在售时该列留空。

默认抓取全部品牌（hisense/sony/regza/panasonic/tcl/sharp），导出时每个品牌聚成
一块（品牌标题行 + 该品牌各机型），并标注所属区域（按品牌来源站点，kakaku=Japan）
与货币（JPY）。

加 --save-db 时同时写入数据库（供后端 API 查询）：
    product              机型登记为商品（sku=kakaku item id）
    price_snapshot       该商品整体最低价（★时序）
    price_shop_snapshot  各店铺分列报价（★时序）
    kakaku_task_status   型号级状态，空/失败不静默

示例：
    python scripts/crawl_kakaku_prices.py                       # 全部品牌
    python scripts/crawl_kakaku_prices.py --brand hisense_jp --brand sony_jp
    python scripts/crawl_kakaku_prices.py --brand hisense_jp --limit-models 5
    python scripts/crawl_kakaku_prices.py --brand hisense_jp --models 65U8S 55U8S
    python scripts/crawl_kakaku_prices.py --year 0              # 不按上市年份过滤
    python scripts/crawl_kakaku_prices.py --brand hisense_jp --save-db   # 同时入库
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                       # noqa: E402
from overseas.db import Database                  # noqa: E402
from overseas.fetchers import BrowserFetcher      # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.models import PriceSnapshot, Product  # noqa: E402
from overseas.price_export import (               # noqa: E402
    PriceRecord, write_csv, write_xlsx,
)
from overseas.scenarios import open_dom           # noqa: E402
from overseas.sites import SiteRegistry           # noqa: E402

# 品牌 code → 模板「品牌」列展示名（与评价脚本一致）
BRAND_DISPLAY = {
    "hisense_jp": "Hisense",
    "sony_jp": "SONY",
    "regza_jp": "REGZA",
    "panasonic_jp": "Panasonic",
    "tcl_jp": "TCL",
    "sharp_jp": "SHARP",
}

DEFAULT_MODELS_CSV = PROJECT_ROOT / "data" / "SPEC_型号汇总_20260908.csv"


# ==================== 数据结构 ====================

@dataclass
class ModelPrice:
    model: str
    item_id: str = ""
    release_text: str = ""
    release_year: int | None = None
    size: str = ""
    lowest_price: str = ""                 # kakaku 最安価格
    lowest_shop: str = ""                  # 最安店铺（溯源）
    shop_cols: dict[str, int] = field(default_factory=dict)   # {模板店铺列名: 价}
    status: str = ""                       # ok / no_item / not_target_year / no_price / blocked / failed
    message: str = ""


# ==================== 型号清单 ====================

def load_models(models_csv: Path, brand: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        return [m.strip() for m in explicit if m.strip()]
    if not models_csv.exists():
        raise SystemExit(f"[ERROR] 型号清单不存在: {models_csv}")
    out: list[str] = []
    seen: set[str] = set()
    with models_csv.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if (row.get("brand_code") or "").strip() != brand:
                continue
            raw = (row.get("model_raw") or "").strip()
            model = raw.split("|")[0].strip()      # 合并写法取第一个用于搜索
            key = model.upper()
            if model and key not in seen:
                seen.add(key)
                out.append(model)
    return out


# ==================== 单型号抓取 ====================

def crawl_model(adapter, fetcher, model: str, target_year: int,
                verbose: bool) -> ModelPrice:
    result = ModelPrice(model=model)

    # 1) 搜索定位 item id
    with open_dom(adapter, fetcher, adapter.search_url(model)) as (res, dom, html):
        if res.blocked:
            result.status, result.message = "blocked", res.block_reason or "搜索被拦截"
            return result
        if not res.ok or dom is None:
            result.status, result.message = "failed", res.error or f"搜索 status={res.status}"
            return result
        item_id = adapter.first_item_id(dom, want_model=model)
    if not item_id:
        result.status, result.message = "no_item", "搜索无匹配商品"
        return result
    result.item_id = item_id

    # 2) 商品页：最安価格 + 发售日 + 尺寸 + 各店铺价格
    with open_dom(adapter, fetcher, adapter.item_url(item_id)) as (res, dom, html):
        if res.blocked:
            result.status, result.message = "blocked", res.block_reason or "商品页被拦截"
            return result
        if not res.ok or dom is None:
            result.status, result.message = "failed", res.error or f"商品页 status={res.status}"
            return result
        result.lowest_price = adapter.lowest_price(dom)
        release_text = adapter.release_text(dom)
        page_text = dom.self_text() if dom else ""
        raw_shops = adapter.shop_prices(dom)
        result.shop_cols = adapter.map_shop_columns(raw_shops)
    result.release_text = release_text
    result.release_year = adapter.release_year(release_text)
    result.size = adapter.size_inch(model, page_text)

    # 最安店铺：在店铺一览里找价格等于最安価格的店铺（溯源用，可为空）
    if result.lowest_price.isdigit():
        low = int(result.lowest_price)
        for shop_name, price in raw_shops.items():
            if price == low:
                result.lowest_shop = shop_name
                break

    # 3) 上市年份过滤（year<=0 时不过滤）
    if target_year and result.release_year and result.release_year != target_year:
        result.status = "not_target_year"
        result.message = f"上市年份={result.release_year}，非 {target_year}"
        return result

    if not result.lowest_price and not result.shop_cols:
        result.status, result.message = "no_price", "未解析到任何价格"
        return result
    result.status = "ok"
    return result


# ==================== 记录转换 ====================

# kakaku 是日本站，价格货币固定日元
KAKAKU_CURRENCY = "JPY"


def to_record(brand: str, r: ModelPrice) -> PriceRecord:
    display = BRAND_DISPLAY.get(brand, brand)
    adapter = SiteRegistry.get("kakaku_jp")
    release_disp = adapter.release_display(r.release_text)
    return PriceRecord(
        region=adapter.country,                # 按品牌来源站点划分区域（kakaku=Japan）
        brand=display,
        model=r.model,
        size=r.size,
        release=release_disp,
        currency=KAKAKU_CURRENCY,
        lowest_price=int(r.lowest_price) if r.lowest_price.isdigit() else "",
        shop_prices=dict(r.shop_cols),
        lowest_shop=r.lowest_shop,
        item_id=r.item_id,
        url=adapter.item_url(r.item_id) if r.item_id else "",
        captured_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


# ==================== 入库 ====================

def save_to_db(db: Database, adapter, site_id: int, run_id: int | None,
               brand: str, r: ModelPrice) -> int | None:
    """把一个型号的价格结果写库，返回 product_id（无商品时 None）。

    落点：
      - product              ：kakaku 机型登记为商品，sku=item_id，便于与 SPEC 型号对齐
      - price_snapshot       ：该商品整体最低价（★时序）
      - price_shop_snapshot  ：各店铺分列报价（★时序）
      - kakaku_task_status   ：型号级状态，空/失败不静默
    """
    display = BRAND_DISPLAY.get(brand, brand)
    product_id: int | None = None
    row_count = 0

    if r.item_id:
        product = Product(
            site_code=adapter.code,
            sku=r.item_id,
            url=adapter.item_url(r.item_id),
            title=f"{display} {r.model}".strip(),
            brand=display,
            model=r.model,
            category="TV",
            size=r.size,
        )
        product_id = db.upsert_product(product, site_id)

        # 整体最低价快照
        if r.lowest_price and str(r.lowest_price).isdigit():
            db.add_price(product_id, PriceSnapshot(
                price=float(r.lowest_price),
                currency=KAKAKU_CURRENCY,
                raw_text=str(r.lowest_price),
            ))
        # 各店铺报价
        row_count = db.add_shop_prices(
            product_id, r.shop_cols, currency=KAKAKU_CURRENCY,
            lowest_shop=r.lowest_shop)

    db.record_kakaku_status(
        task="price", brand=brand, model=r.model, status=r.status,
        run_id=run_id, brand_name=display, item_id=r.item_id,
        product_id=product_id, release_text=r.release_text,
        release_year=r.release_year, size=r.size,
        row_count=row_count, message=r.message,
    )
    return product_id


# ==================== 主流程 ====================

def make_fetcher(adapter):
    interval = max(config.MIN_INTERVAL, adapter.suggested_interval)
    return BrowserFetcher(rate_limiter=RateLimiter(min_interval=interval),
                          detector=BlockDetector(), cache=DiskCache())


# 全部品牌顺序（--all-brands / 缺省时使用），也是导出分块的品牌先后顺序
ALL_BRANDS = ["hisense_jp", "sony_jp", "regza_jp", "panasonic_jp", "tcl_jp", "sharp_jp"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="価格.com 各店铺分列价格抓取（多品牌，按品牌分块，价格监控模板）")
    p.add_argument("--brand", action="append",
                   help="品牌 code，可重复指定多个；缺省=全部品牌")
    p.add_argument("--all-brands", action="store_true",
                   help="抓取全部品牌（等价于不指定 --brand）")
    p.add_argument("--models-csv", default=str(DEFAULT_MODELS_CSV),
                   help=f"型号清单 CSV，默认 {DEFAULT_MODELS_CSV}")
    p.add_argument("--models", nargs="*",
                   help="直接指定型号（仅当只选一个品牌时生效，覆盖 CSV）")
    p.add_argument("--year", type=int, default=2026,
                   help="只抓该上市年份的机型；传 0 表示不过滤，默认 2026")
    p.add_argument("--limit-models", type=int, default=0,
                   help="每个品牌最多处理多少个型号（0=不限）")
    p.add_argument("--format", choices=("xlsx", "csv", "all"), default="all")
    p.add_argument("--out", help="输出路径主干；缺省写到 data/ 带时间戳")
    p.add_argument("--save-db", action="store_true",
                   help="同时写入数据库：product / price_snapshot / price_shop_snapshot"
                        " / kakaku_task_status（供后端 API 查询）")
    p.add_argument("--db", help="SQLite 路径，缺省用 OVERSEAS_DB_PATH 或 data/overseas.db")
    p.add_argument("--quiet", action="store_true")
    return p


def _resolve_brands(args) -> list[str]:
    """确定要抓的品牌列表：--brand 优先，否则全部品牌。"""
    if args.brand and not args.all_brands:
        # 保持用户指定顺序，同时按 ALL_BRANDS 已知集合校验
        return [b.strip() for b in args.brand if b.strip()]
    return list(ALL_BRANDS)


def crawl_brand(adapter, fetcher, brand: str, models: list[str], year: int,
                verbose: bool, db: Database | None = None,
                site_id: int | None = None,
                run_id: int | None = None) -> tuple[list[ModelPrice], list[PriceRecord]]:
    """抓单个品牌的全部型号，返回 (原始结果, 导出记录)。db 非空时同时入库。"""
    results: list[ModelPrice] = []
    records: list[PriceRecord] = []
    for i, model in enumerate(models, 1):
        if verbose:
            print(f"  [{brand} {i}/{len(models)}] {model} ...")
        try:
            r = crawl_model(adapter, fetcher, model, year, verbose)
        except Exception as e:
            r = ModelPrice(model=model, status="failed",
                           message=f"{type(e).__name__}: {e}")
        results.append(r)
        if r.status == "ok":
            records.append(to_record(brand, r))
        if db is not None and site_id is not None:
            try:
                save_to_db(db, adapter, site_id, run_id, brand, r)
            except Exception as e:              # 入库失败不影响文件输出
                print(f"      [WARN] 入库失败 {model}: {type(e).__name__}: {e}")
        if verbose:
            shops = "，".join(f"{k}={v}" for k, v in r.shop_cols.items())
            print(f"      → {r.status} {r.message} 最低价={r.lowest_price} "
                  f"({r.lowest_shop}) 店铺={{{shops}}} item={r.item_id}")
    return results, records


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verbose = not args.quiet
    config.ensure_dirs()

    try:
        adapter = SiteRegistry.get("kakaku_jp")
    except KeyError as e:
        print(f"[ERROR] {e}")
        return 2

    brands = _resolve_brands(args)
    if args.models and len(brands) != 1:
        print("[ERROR] --models 只能在选定单个品牌时使用")
        return 2
    if not brands:
        print("[ERROR] 没有可抓取的品牌")
        return 2

    # 预载每个品牌的型号清单
    brand_models: dict[str, list[str]] = {}
    for brand in brands:
        models = load_models(Path(args.models_csv), brand,
                             args.models if len(brands) == 1 else None)
        if args.limit_models > 0:
            models = models[:args.limit_models]
        brand_models[brand] = models

    total_models = sum(len(m) for m in brand_models.values())
    print(f"[KAKAKU-PRICE] 品牌={brands} 型号总数={total_models} "
          f"上市年份过滤={args.year or '不过滤'} 区域={adapter.country} 货币={KAKAKU_CURRENCY}")

    # 入库准备（--save-db）
    db: Database | None = None
    site_id: int | None = None
    run_id: int | None = None
    if args.save_db:
        db = Database(args.db)
        db.init_schema()
        site_id = db.upsert_site(adapter.code, adapter.name, adapter.base_url,
                                 adapter.protection)
        run_id = db.start_run("kakaku_price", adapter.code,
                              {"brands": brands, "year": args.year,
                               "models": total_models})
        print(f"[DB] {db.path} site_id={site_id} run_id={run_id}")

    fetcher = make_fetcher(adapter)
    all_results: list[tuple[str, ModelPrice]] = []
    records: list[PriceRecord] = []          # 已按品牌顺序聚集（品牌块内即该品牌记录）
    try:
        for brand in brands:
            models = brand_models[brand]
            if not models:
                print(f"[{brand}] 无型号，跳过")
                continue
            print(f"\n===== 品牌块 {BRAND_DISPLAY.get(brand, brand)} "
                  f"（{brand}）型号 {len(models)} 个 =====")
            b_results, b_records = crawl_brand(adapter, fetcher, brand, models,
                                               args.year, verbose,
                                               db=db, site_id=site_id, run_id=run_id)
            all_results.extend((brand, r) for r in b_results)
            records.extend(b_records)
    finally:
        fetcher.close()

    from collections import Counter
    status_counts = Counter(r.status for _, r in all_results)
    ok = [r for _, r in all_results if r.status == "ok"]
    print(f"\n[汇总] 型号={len(all_results)} 命中={len(ok)} "
          f"输出行数={len(records)} 状态={dict(status_counts)}")
    # 按品牌分块的命中统计
    by_brand: dict[str, list[str]] = {}
    for brand, r in all_results:
        by_brand.setdefault(brand, []).append(r.status)
    for brand in brands:
        sts = by_brand.get(brand, [])
        n_ok = sum(1 for s in sts if s == "ok")
        print(f"    - {BRAND_DISPLAY.get(brand, brand)}: 命中 {n_ok}/{len(sts)}")
    for brand, r in all_results:
        if r.status != "ok":
            print(f"      · {brand} {r.model}: {r.status} {r.message}")

    # 结束运行记录并汇报入库结果
    if db is not None:
        n_fail = len(all_results) - len(ok)
        if run_id is not None:
            db.finish_run(run_id, "completed", len(ok), n_fail,
                          f"brands={brands} rows={len(records)}")
        counts = db.kakaku_status_counts(task="price")
        print(f"[DB] 价格状态入库统计={counts}")
        print(f"[DB] 统计={db.stats()}")
        db.close()

    stamp = datetime.now().strftime("%Y%m%d")
    brand_tag = brands[0] if len(brands) == 1 else "all"
    base = (Path(args.out) if args.out
            else (PROJECT_ROOT / "data" / f"价格监控_{brand_tag}_kakaku_{stamp}"))
    # 先写 CSV 再写 XLSX：XLSX 被 Excel 占用时不影响 CSV 落盘
    formats = ("csv", "xlsx") if args.format == "all" else (args.format,)
    for fmt in formats:
        path = base if base.suffix.lower() == f".{fmt}" else base.with_suffix(f".{fmt}")
        try:
            if fmt == "xlsx":
                write_xlsx(path, records)      # 导出层按品牌分块 + 品牌标题行
            else:
                write_csv(path, records)
            print(f"[OUT] {fmt}: {path} rows={len(records)}")
        except PermissionError:
            alt = path.with_name(f"{path.stem}_{datetime.now():%H%M%S}{path.suffix}")
            if fmt == "xlsx":
                write_xlsx(alt, records)
            else:
                write_csv(alt, records)
            print(f"[OUT] {fmt}: 原文件被占用，已改写 {alt} rows={len(records)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
