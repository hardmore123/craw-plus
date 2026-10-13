# -*- coding: utf-8 -*-
"""南美零售线驱动：按 region+站点，用 RetailSpec(spec 驱动抽取) 抓价格+网评。

走 engine 的 mx_retail.crawl_region_retail（spec 驱动 collect_detail 抽取价格/网评、
match_product 匹配、collect_reviews_paged 翻页+100上限），薄 adapter 只需
URL 规则，parse_product 由 spec 提供。

用法:
    py scripts/crawl_sa_retail.py --region pe --sites hiraoka_pe \
        --models-csv data/型号清单_短码/models_秘鲁_short.csv \
        --spec data/schema_drafts/hiraoka_pe.retail.json [--limit-models N]

产物: data/<国家>/价格监控_<国家>_<stamp>.csv / 网评汇总_<国家>_<stamp>.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from overseas import config                                    # noqa: E402
from overseas import mx_retail                                 # noqa: E402
from overseas.regions_config import get_region                 # noqa: E402
from overseas.retail_spec import load_retail_spec              # noqa: E402

CN = {"pe": "秘鲁", "ec": "厄瓜多尔", "co": "哥伦比亚",
      "cl": "智利", "bo": "玻利维亚", "ar": "阿根廷"}


def load_models(csv_path: str) -> list[dict]:
    """读取型号清单，并把带中文括号的品牌名（Samsung（PE））清理为纯英文品牌，
    否则 Magento 搜索 {brand} {model} 拼出带括号关键词会 0 命中。"""
    _CLEAN_BRAND = {
        "samsung": "Samsung", "lg": "LG", "tcl": "TCL", "hisense": "Hisense",
        "sony": "Sony", "philips": "Philips",
    }
    out = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            m = (r.get("model_raw") or "").strip()
            if not m:
                continue
            bn = (r.get("brand_name") or "").strip()
            bc = (r.get("brand_code") or "").strip().lower()
            for prefix, clean in _CLEAN_BRAND.items():
                if bc.startswith(prefix):
                    bn = clean
                    break
            out.append({
                "model_raw": m,
                "brand_code": r.get("brand_code") or "",
                "brand_name": bn,
            })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="南美零售线抓取（spec 驱动）")
    ap.add_argument("--region", required=True, help="pe/ec/co/cl/bo")
    ap.add_argument("--sites", nargs="*", help="零售站 code，缺省用 region 全部启用站")
    ap.add_argument("--models-csv", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--limit-models", type=int, default=0)
    ap.add_argument("--offset-models", type=int, default=0)
    ap.add_argument("--max-reviews", type=int, default=100)
    ap.add_argument("--out-dir", default="")
    args = ap.parse_args()

    region = get_region(args.region)
    if region is None:
        print(f"[ERROR] 未知 region {args.region}")
        return 2
    spec = load_retail_spec(args.spec)
    models = load_models(args.models_csv)
    if args.offset_models and args.offset_models > 0:
        models = models[args.offset_models:]
    if args.limit_models and args.limit_models > 0:
        models = models[: args.limit_models]
    if not models:
        print("[错误] 型号清单为空")
        return 2
    sites = args.sites or region.retail_site_codes(only_enabled=True)
    print(f"[SA-RETAIL] region={args.region} 型号={len(models)} 零售站={sites} "
          f"评价上限={args.max_reviews}")

    rows = mx_retail.crawl_region_retail(
        args.region, models, sites=sites, want_reviews=True,
        max_reviews=args.max_reviews, save_db=False,
        retail_spec=load_retail_spec(args.spec), verbose=True)

    # ---- 导出价格 ----
    cn = CN.get(args.region, args.region)
    out_dir = Path(args.out_dir) if args.out_dir else PROJECT_ROOT / "data" / cn
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    price_csv = out_dir / f"价格监控_{cn}_{stamp}.csv"
    review_csv = out_dir / f"网评汇总_{cn}_{stamp}.csv"
    currency = region.currency

    # ---- 抓取时间戳（每条记录的实际抓取时刻，非文件名）----
    captured_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(price_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["国家", "零售站", "网站名称", "品牌", "品牌code", "型号", "尺寸",
                    "价格", "币种", "原价", "库存", "sku", "URL", "状态", "评价数",
                    "抓取时间"])
        for r in rows:
            # 币种：优先用 spec 顶层声明的国家货币（引擎恢复后硬编码 MXN，南美站须覆盖）
            eff_cur = currency
            w.writerow([region.name, r.site, r.channel, r.brand, r.brand_code,
                        r.model, r.size,
                        "" if r.price is None else r.price, eff_cur,
                        "" if r.list_price is None else r.list_price,
                        "" if r.in_stock is None else ("Y" if r.in_stock else "N"),
                        r.sku, r.url, r.status, len(r.reviews),
                        captured_at])
    price_rows = sum(1 for r in rows if r.price is not None)
    review_rows = sum(1 for r in rows for _ in r.reviews)
    print(f"[OUT] 价格 CSV {price_csv} rows={len(rows)} 有价={price_rows} 时间={captured_at}")

    with open(review_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["国家", "品牌", "型号", "渠道", "尺寸", "评分", "标题", "正文",
                    "有帮助", "评论时间", "评论URL", "价格", "抓取时间"])
        for r in rows:
            for rv in r.reviews:
                w.writerow([region.name, r.brand, r.model, r.channel, r.size,
                            rv.rating if rv.rating is not None else "",
                            rv.title, rv.body,
                            rv.helpful_count if rv.helpful_count is not None else "",
                            rv.review_date, rv.review_url,
                            "" if r.price is None else r.price,
                            captured_at])
    print(f"[OUT] 网评 CSV {review_csv} rows={review_rows}")

    from collections import Counter
    st = Counter(r.status for r in rows)
    print(f"[SA-RETAIL] 完成: 共{len(rows)} 状态={dict(st)} 评={review_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())