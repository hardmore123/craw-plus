# -*- coding: utf-8 -*-
"""全量就绪静态自检：逐站检查 schema+adapter 是否具备「硬编码全量抓取」的全部条件（不联网）。

全量入口固定为 scripts/crawl_ca_retail.py --region <r> --sites <code> --save-db
（不给 --spec 时按 _resolve_site_spec 逐站自动加载 schemas/retail_specs/<code>.retail.json）。
这里把该入口在运行时会经过的每道门按顺序静态走一遍：

  G1 region     区域存在，且站点登记在该区域 retail_sites（否则 resolve_sites 直接退出）
  G2 allowlist  合规白名单通过（mx_retail 路径与 retail-health 会拦）
  G3 adapter    已注册且 supports_retail（否则 crawl_site 静默 [SKIP]）
  G4 spec       本次实际使用的 spec（自动解析结果）；Amazon 类自带 parse_product 的站可为无
  G5 search     能产出搜索候选：spec.search.api / spec.search.container / adapter 覆写 parse_search
  G6 detail     能抽商品页：spec 驱动时 product + price.price 规则齐；否则 adapter 自带 parse_product
  G7 match      spec 有 match 且 on_no_match=skip、require_model_in 非空（validate_retail_spec 通过）
  G8 reviews    capabilities 含 reviews 时：评价来源可执行（BV/PowerReviews 接口，或
                reviews.container + fields.review_key），且 paginate.reviews.type 合法
  G9 models     该区域默认型号清单存在且非空
  G10 status    spec.status 非 blocked/needs_handwritten（这两类按设计不进全量）

结论：READY_STATIC（G1~G10 全过）/ GAP（列出未过的门）/ EXCLUDED（G10：spec 自身标为不可抓）
产出：data/sandbox/full_readiness_static_<日期>.csv + 终端汇总
用法：py -3.12 scripts/full_readiness_static.py
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import crawl_ca_retail as C  # noqa: E402
from overseas import retail_compliance as RC  # noqa: E402
from overseas.regions_config import REGIONS  # noqa: E402
from overseas.retail_spec import (SUPPORTED_REVIEW_PAGINATE, SPEC_DIR,  # noqa: E402
                                  validate_retail_spec)
from overseas.sites import SiteAdapter, SiteRegistry  # noqa: E402

BRAND_PREFIX = {"hisense", "samsung", "tcl", "lg", "sony", "philips", "panasonic", "regza", "sharp"}
# 不走通用入口、有专用全量脚本的站
DEDICATED = {"kakaku_jp": "日本线专用：crawl_kakaku_prices.py / crawl_kakaku_reviews.py"}
API_REVIEW_SOURCES = {"bazaarvoice_bfd", "bv_api", "powerreviews_api", "yotpo_api",
                      "trustpilot_api", "next_data", "jsonld", "mms_graphql"}


def model_count(region: str) -> int:
    p = C._default_models_csv(region)
    if not p.exists():
        return 0
    with p.open(encoding="utf-8-sig") as f:
        return sum(1 for r in csv.DictReader(f) if (r.get("model_raw") or "").strip())


def main() -> int:
    site_region = {}
    for rc, reg in REGIONS.items():
        for rs in reg.retail_sites:
            site_region.setdefault(rs.site, rc)
    spec_files = {os.path.basename(p).split(".")[0] for p in glob.glob(str(SPEC_DIR / "*.retail.json"))}
    codes = set(SiteRegistry.codes())
    universe = set(spec_files) | {c for c in codes
                                  if getattr(SiteRegistry.get(c), "supports_retail", False)}
    mcount = {}
    rows = []
    for code in sorted(universe):
        gaps = []
        rc = site_region.get(code, "")
        if not rc:
            gaps.append("G1 未登记任何区域")
        try:
            ad = SiteRegistry.get(code) if code in codes else None
        except Exception:
            ad = None
        raw_spec = json.load(open(SPEC_DIR / f"{code}.retail.json", encoding="utf-8")) \
            if code in spec_files else None
        base = (ad.base_url if ad else (raw_spec or {}).get("base_url", ""))
        try:
            RC.ensure_allowed(base, check_robots=False)
        except Exception:
            gaps.append("G2 不在合规白名单")
        if ad is None:
            gaps.append("G3 无 adapter")
        elif not getattr(ad, "supports_retail", False):
            gaps.append("G3 adapter 未声明 supports_retail")
        spec = C._resolve_site_spec(code, None) if ad is not None else raw_spec
        own_parse = ad is not None and type(ad).parse_product is not SiteAdapter.parse_product
        own_search = ad is not None and type(ad).parse_search is not SiteAdapter.parse_search
        path = "spec" if (ad is not None and spec and C._spec_drives_detail(ad, spec)) else \
            ("adapter" if own_parse else "none")
        if spec is None and not own_parse:
            gaps.append("G4 无可用 spec 且 adapter 无 parse_product")
        scfg = (spec or {}).get("search") or {}
        if spec:
            if not (scfg.get("api") or scfg.get("container")):
                gaps.append("G5 spec 无 search.container/search.api")
        elif not own_search and not (ad and (ad.schema or {}).get("search", {}).get("container")):
            gaps.append("G5 无搜索候选规则")
        if path == "spec":
            pr = ((spec.get("price") or {}).get("price") or {})
            if not (pr.get("jsonld") or pr.get("selectors") or pr.get("regex")):
                gaps.append("G6 spec 缺 price.price 抽取规则")
            if not spec.get("product"):
                gaps.append("G6 spec 缺 product 段")
        elif path == "none":
            gaps.append("G6 商品页无抽取路径")
        if spec:
            probs = validate_retail_spec(spec)
            if probs:
                gaps.append("G7 spec 校验不过：" + probs[0][:60])
        caps = (spec or raw_spec or {}).get("capabilities") or []
        if "reviews" in caps and spec:
            rv = spec.get("reviews") or {}
            src = str(rv.get("source") or "")
            ok_src = src in API_REVIEW_SOURCES or (
                rv.get("container") and (rv.get("fields") or {}).get("review_key"))
            if not ok_src:
                gaps.append(f"G8 评价来源不可执行（source={src or '-'}）")
            ptype = ((spec.get("paginate") or {}).get("reviews") or {}).get("type")
            if ptype and ptype not in SUPPORTED_REVIEW_PAGINATE:
                gaps.append(f"G8 paginate.reviews.type={ptype} 不支持")
        if rc:
            if rc not in mcount:
                mcount[rc] = model_count(rc)
            if not mcount[rc]:
                gaps.append("G9 区域无型号清单")
        status = (raw_spec or {}).get("status", "")
        excluded = status in ("blocked", "needs_handwritten")
        brand_site = code.split("_")[0] in BRAND_PREFIX
        if code in DEDICATED:
            verdict, gaps = "DEDICATED", [DEDICATED[code]]
        elif brand_site and not rc:
            # 品牌官网：走 SPEC 线（spec-crawl / refresh_spec），其 retail spec 只是占位
            verdict, gaps = "SPEC_LINE", ["品牌官网，走 SPEC 线，不进零售全量"]
        elif excluded:
            verdict = "EXCLUDED"
        else:
            verdict = "READY_STATIC" if not gaps else "GAP"
        rows.append({"site": code, "region": rc, "spec_status": status or "-",
                     "caps": "+".join(caps), "detail_path": path,
                     "search": ("api:" + scfg["api"]["type"]) if scfg.get("api") else
                               ("dom" if scfg.get("container") else ("adapter" if own_search else "-")),
                     "models": mcount.get(rc, 0), "verdict": verdict, "gaps": "；".join(gaps)})

    stamp = dt.date.today().strftime("%Y%m%d")
    os.makedirs("data/sandbox", exist_ok=True)
    out = f"data/sandbox/full_readiness_static_{stamp}.csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    c = collections.Counter(r["verdict"] for r in rows)
    print(f"[总计] {len(rows)} 站 {dict(c)}")
    g = collections.Counter(x.split(" ")[0] for r in rows if r["verdict"] == "GAP"
                            for x in r["gaps"].split("；") if x)
    print("[GAP 分布]", dict(g))
    for r in rows:
        if r["verdict"] == "GAP":
            print(f"  {r['site']:22} {r['region']:3} {r['spec_status']:10} {r['gaps']}")
    print(f"[OUT] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
