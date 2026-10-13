"""在 価格.com 按型号抓取「上市时间（発売日）」映射，供 SPEC 导出增加上市时间列/行。

只访问「搜索 → 商品页」两步（不抓评价），比完整评价抓取快很多。
输出 data/发售日_<brand>.json：{型号: {release, release_raw, year, item_id}}。
SPEC 导出（overseas.cli spec-export / refresh_spec.py）会自动读取同名文件。

示例：
    python scripts/crawl_kakaku_release.py --brand hisense_jp
    python scripts/crawl_kakaku_release.py --brand hisense_jp --models 65U8S 55U8S
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from overseas import config                       # noqa: E402
from overseas.fetchers import BrowserFetcher      # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter  # noqa: E402
from overseas.scenarios import open_dom           # noqa: E402
from overseas.sites import SiteRegistry           # noqa: E402

DEFAULT_MODELS_CSV = PROJECT_ROOT / "data" / "SPEC_型号汇总_20260908.csv"


def load_models(models_csv: Path, brand: str, explicit: list[str] | None) -> list[str]:
    if explicit:
        return [m.strip() for m in explicit if m.strip()]
    out: list[str] = []
    seen: set[str] = set()
    with models_csv.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if (row.get("brand_code") or "").strip() != brand:
                continue
            model = (row.get("model_raw") or "").split("|")[0].strip()
            if model and model.upper() not in seen:
                seen.add(model.upper())
                out.append(model)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="価格.com 上市时间（発売日）抓取")
    p.add_argument("--brand", default="hisense_jp")
    p.add_argument("--models-csv", default=str(DEFAULT_MODELS_CSV))
    p.add_argument("--models", nargs="*")
    p.add_argument("--out", help="输出 JSON，缺省 data/发售日_<brand>.json")
    p.add_argument("--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    verbose = not args.quiet
    config.ensure_dirs()
    adapter = SiteRegistry.get("kakaku_jp")
    models = load_models(Path(args.models_csv), args.brand, args.models)
    if not models:
        print("[ERROR] 无型号")
        return 2
    print(f"[RELEASE] 品牌={args.brand} 型号数={len(models)}")

    interval = max(config.MIN_INTERVAL, adapter.suggested_interval)
    fetcher = BrowserFetcher(rate_limiter=RateLimiter(min_interval=interval),
                             detector=BlockDetector(), cache=DiskCache())
    result: dict[str, dict] = {}
    try:
        for i, model in enumerate(models, 1):
            item_id = ""
            release_text = ""
            try:
                with open_dom(adapter, fetcher, adapter.search_url(model)) as (res, dom, html):
                    if res.ok and dom is not None:
                        item_id = adapter.first_item_id(dom, want_model=model)
                if item_id:
                    with open_dom(adapter, fetcher, adapter.item_url(item_id)) as (res, dom, html):
                        if res.ok and dom is not None:
                            release_text = adapter.release_text(dom)
            except Exception as e:
                if verbose:
                    print(f"[{i}/{len(models)}] {model} ERR {type(e).__name__}: {e}")
            if release_text:
                result[model] = {
                    "release": adapter.release_display(release_text),
                    "release_raw": release_text,
                    "year": adapter.release_year(release_text),
                    "item_id": item_id,
                }
            if verbose:
                print(f"[{i}/{len(models)}] {model}: {result.get(model, {}).get('release', '(无)')} "
                      f"item={item_id}")
    finally:
        fetcher.close()

    out = Path(args.out) if args.out else (PROJECT_ROOT / "data" / f"发售日_{args.brand}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(f"[OUT] {out} models={len(result)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
