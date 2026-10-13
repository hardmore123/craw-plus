"""把已有零售站 schema.json（已验证六段）确定性反抽象为 RetailSpec。

已有站点（amazon_* / bestbuy_us / costco_us / walmart_* / palacio_mx / sams_mx 等）
的 schema.json 是过去真实探测的成果（选择器已验证可抽取）。本脚本把它们转成
RetailSpec（schemas/retail_specs/<code>.retail.json），六段保留原样、补五段
（match / paginate / shops / export / fetch）加元数据，无需重新探索。

无 schema.json 的站（bestbuy_ca 等）不在此脚本范围，走 probe 探测。

用法：
    py -3.12 scripts/build_retail_specs.py [--site amazon_ca] [--out schemas/retail_specs]
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# site_code → (country, region, currency, capabilities)
_SITE_META = {
    "amazon_ca": ("Canada", "ca", "CAD", ["price", "reviews"]),
    "amazon_us": ("USA", "us", "USD", ["price", "reviews"]),
    "amazon_mx": ("Mexico", "mx", "MXN", ["price", "reviews"]),
    "bestbuy_us": ("USA", "us", "USD", ["price", "reviews"]),
    "costco_us": ("USA", "us", "USD", ["price", "reviews"]),
    "walmart_us": ("USA", "us", "USD", ["price", "reviews"]),
    "walmart_mx": ("Mexico", "mx", "MXN", ["price", "reviews"]),
    "palacio_mx": ("Mexico", "mx", "MXN", ["price", "reviews"]),
    "sams_mx": ("Mexico", "mx", "MXN", ["price", "reviews"]),
}

# 常见品类拒词（防配件混入），按站点微调
_REJECT_AM = ["soporte", "control remoto", "funda", "cable", "adaptador", "accesorio"]
_REJECT_ALL_EN = ["wall mount", "stand", "screen protector", "case", "bracket", "adapter"]
_REJECT_AM_AM = ["case", "cover", "wall mount", "stand", "screen", "bracket", "protector",
                 "cable", "adapter"]


def _adapter_cls(code: str):
    try:
        mod = importlib.import_module(f"overseas.sites.{code}.adapter")
    except ImportError:
        return None
    for v in vars(mod).values():
        if getattr(v, "code", None) == code:
            return v
    return None


def _search_url_for(code: str, kw: str) -> str:
    """构造站点默认搜索 URL（少数站的形态可在 code 里写死）。"""
    import urllib.parse
    code = code or ""
    if "amazon" in code:
        host = {"amazon_ca": "www.amazon.ca", "amazon_us": "www.amazon.com",
                "amazon_mx": "www.amazon.com.mx"}.get(code, "www.amazon.com")
        return f"https://{host}/s?k={urllib.parse.quote(kw)}"
    if code == "bestbuy_us":
        return f"https://www.bestbuy.com/site/searchpage.jsp?st={urllib.parse.quote(kw)}"
    if code == "costco_us":
        return f"https://www.costco.com/on/demandware.store/Sites-costco_us-Site/default/SearchResults?keyword={urllib.parse.quote(kw)}"
    if "walmart" in code:
        base = "https://www.walmart.com" if code == "walmart_us" else "https://www.walmart.com.mx"
        return f"{base}/search?q={urllib.parse.quote(kw)}"
    if code == "palacio_mx":
        return f"https://www.elpalaciodehierro.com/buscar?q={urllib.parse.quote(kw)}"
    if code == "sams_mx":
        return f"https://www.sams.com.mx/busca?ft={urllib.parse.quote(kw)}"
    return f"https://{code or 'example'}.com/search?q={urllib.parse.quote(kw)}"


def build_one(code: str) -> dict:
    """从本地 schema.json + adapter 构造一份 RetailSpec。"""
    schema_path = ROOT / "overseas" / "sites" / code / "schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"{code} 无 schema.json，不走反抽象路径")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    country, region, currency, caps = _SITE_META.get(code, ("", "", "", ["price", "reviews"]))
    cls = _adapter_cls(code)

    fetch = {
        "protection": getattr(cls, "protection", "L2_MEDIUM") if cls else "L2_MEDIUM",
        "requires_browser": getattr(cls, "requires_browser", False) if cls else True,
        "interval_sec": float(getattr(cls, "suggested_interval", 5.0)) if cls else 5.0,
    }
    if hasattr(cls, "retail_page_wait") and getattr(cls, "retail_page_wait"):
        fetch["retail_page_wait"] = getattr(cls, "retail_page_wait")

    reject_words = list(_REJECT_AM_AM if "amazon" in code else
                        (_REJECT_ALL_EN if code in ("costco_us", "bestbuy_us", "walmart_us") else _REJECT_AM))
    spec = {
        "retail_spec_version": "0.1",
        "code": code,
        "name": getattr(cls, "channel", code) if cls else code,
        "country": country,
        "channel": getattr(cls, "channel", code) if cls else code,
        "region": region,
        "base_url": getattr(cls, "base_url", "") if cls else f"https://{code}",
        "currency": currency,
        "capabilities": caps,
        "generated_by": f"反抽象: sites/{code}/adapter.py + schema.json",
        "status": "candidate",
    }
    # 六段原样保留（现有抽取引擎每次都读）
    for sec in ("anchor", "search", "product", "price", "specs", "summary", "reviews"):
        if sec in schema:
            spec[sec] = schema[sec]

    # review_key 兜底：个别站 schema 没声明评价唯一键时，补内容哈希（Extractor 同策略）
    rv_fields = (spec.get("reviews") or {}).get("fields") or {}
    if "reviews" in caps and not rv_fields.get("review_key"):
        spec.setdefault("reviews", {})
        spec["reviews"].setdefault("fields", {})
        spec["reviews"]["fields"]["review_key"] = {"self_attr": "id"}
        # 若 self_attr=id 也拿不到，Extractor 会落到内容哈希——README 注明
        if not spec["reviews"].get("_review_key_note"):
            spec["reviews"]["_review_key_note"] = (
                "原 schema 无唯一评价键，review_key 用 self_attr id，缺则 Extractor 内容哈希兜底")

    # 默认 match（三段兜底 + reject + skip）
    spec["match"] = {
        "strategy": "search_then_verify",
        "search_keyword_template": "{brand} {model}",
        "candidate_limit": 40,
        "verify": {"require_model_in": ["sku", "title"], "normalize": "upper_alnum",
                   "allow_core_match": True, "core_strip_leading_size": True,
                   "core_strip_suffix": ["pro", "max"], "min_core_len": 4},
        "reject": {"title_contains_any": reject_words, "url_contains_any": []},
        "on_no_match": "skip",
    }
    spec["paginate"] = {"reviews": {"type": "none"}}
    spec["incremental"] = {"key_field": "review_key", "stop_when": "page_all_known"}
    spec["shops"] = {"mode": "single_shop"}
    spec["export"] = {"size_from": "title"}
    spec["fetch"] = fetch
    spec["expected"] = {"match_rate_min": 0.9, "price_fill_rate_min": 0.95}
    return spec


def main() -> int:
    ap = argparse.ArgumentParser(prog="build_retail_specs",
                                 description="已有 schema.json 零售站确定性反转为 RetailSpec")
    ap.add_argument("--site", default="", help="逗号分隔站点 code；缺省=全部有 schema 的站")
    ap.add_argument("--out", default=str(ROOT / "schemas" / "retail_specs"), help="输出目录")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = [s.strip() for s in args.site.split(",") if s.strip()] or list(_SITE_META)
    ok, fail = 0, 0
    for code in wanted:
        try:
            spec = build_one(code)
            # 用独立校验确认字段齐全
            from overseas.retail_spec import validate_retail_spec
            problems = validate_retail_spec(spec)
            if problems:
                print(f"[FAIL] {code}: {problems}")
                fail += 1
                continue
            out = out_dir / f"{code}.retail.json"
            out.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[OK] {code} -> {out.name}")
            ok += 1
        except Exception as e:
            print(f"[ERR] {code}: {type(e).__name__}: {e}")
            fail += 1
    print(f"\n完成: {ok} OK, {fail} 失败")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())