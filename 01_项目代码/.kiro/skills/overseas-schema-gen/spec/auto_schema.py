#!/usr/bin/env python
"""overseas-schema-gen spec 自动 Schema 生成器（经验优先，一次成型）。

核心思路（学习自 tvcraw-main/spec-schema-gen）：
  1. 先查 cases.jsonl——如果已有同 host / 同品牌+region 的案例，直接把 solution
     转成 schema JSON，不跑 probe，一次成型。全程未开浏览器探测。
  2. 如果没有匹配案例，才跑 probe.py 探入口+型号页，输出结构信号供智能体判断。
  3. 验证通过后追加/更新 cases.jsonl，标注"复用XXX经验"。

用法：
  # 已有经验的站点——直接出 schema（秒出，不跑浏览器）
  python auto_schema.py --entry "https://www.sony.jp/bravia/lineup/" --code sony_jp --out schema_sony_jp.json

  # 新站——先查经验，没命中则跑 probe
  python auto_schema.py --entry "https://www.example.com/tvs" --code example_xx --out schema.json

  # 强制重新探测（忽略已有经验，验证失败时用）
  python auto_schema.py --entry "https://www.sony.jp/bravia/lineup/" --code sony_jp --out schema.json --force-probe

匹配优先级：
  1. 精确 code 匹配（同站再次跑）→ 100 分
  2. 同 host 匹配（如 samsung.com 的 uk/ca/cl/co/mx 互相复用）→ 90 分
  3. 同品牌不同 region（如 hisense_bo 复用 hisense_pe）→ 70 + host_similarity
  4. 同 host 父域（如 samsung.com.bo 复用 samsung.com）→ 60 + host_similarity

一次完整会话示例：
  用户: "用skill给samsung_mx生成规格schema"
  1. 智能体跑 auto_schema.py --entry "https://www.samsung.com/mx/tvs/" --code samsung_mx
  2. [HOST90]命中samsung_uk→直接输出复用schema，提示做沙箱验证
  3. 下游引擎验证通过→追加/更新cases.jsonl的samsung_mx行(solution标注"复用samsung_uk")，会话结束
  4. 若验证失败(页面改版/region差异)→加--force-probe重走探测步骤
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

CASES_FILE = Path(__file__).resolve().parent / "cases.jsonl"


def load_cases() -> list[dict]:
    cases = []
    if not CASES_FILE.exists():
        return cases
    for line in CASES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return cases


def extract_host(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) >= 2:
        if parts[-2] in ("com", "co", "org", "net", "gov", "edu"):
            return ".".join(parts[-3:]) if len(parts) >= 3 else host
        return ".".join(parts[-2:])
    return host


def extract_brand(code: str) -> str:
    return code.rsplit("_", 1)[0].lower() if "_" in code else code.lower()


def extract_region(code: str) -> str:
    return code.rsplit("_", 1)[1].lower() if "_" in code else ""


def _host_similarity(host_a: str, host_b: str) -> int:
    if not host_a or not host_b:
        return 0
    parts_a = host_a.split(".")
    parts_b = host_b.split(".")
    common = 0
    for i in range(min(len(parts_a), len(parts_b))):
        if parts_a[i] == parts_b[i]:
            common += 1
        else:
            break
    common_suffix = 0
    for i in range(1, min(len(parts_a), len(parts_b)) + 1):
        if parts_a[-i] == parts_b[-i]:
            common_suffix += 1
        else:
            break
    return common * 8 + common_suffix * 2


def match_cases(cases: list[dict], url: str, code: str) -> list[tuple[int, dict]]:
    """按优先级匹配 cases.jsonl，返回 (score, case) 排序列表。"""
    entry_host = extract_host(url)
    target_brand = extract_brand(code)
    scored: list[tuple[int, dict]] = []

    for case in cases:
        case_code = case.get("code", "")
        case_host = case.get("host", "")
        case_brand = extract_brand(case_code)
        case_solution = case.get("solution")

        if case.get("signals", {}).get("unreachable"):
            continue
        if not case_solution:
            continue

        score = 0
        if case_code == code:
            score = 100
        elif case_host == entry_host:
            score = 90
        elif case_brand == target_brand and target_brand:
            score = 70 + _host_similarity(entry_host, case_host)
        elif case_host and entry_host and target_brand:
            if target_brand in case_host and target_brand in entry_host:
                score = 60 + _host_similarity(entry_host, case_host)

        if score > 0:
            scored.append((score, case))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def case_to_schema(case: dict, url: str, code: str) -> dict:
    """把 cases.jsonl 一条 case 转成完整 schema JSON。"""
    sol = case.get("solution", {})
    host = urlsplit(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    extract_order = sol.get("extract_order", [])
    spec: dict = {"extract_order": extract_order}
    for method in extract_order:
        method_config = sol.get(method, {})
        if method_config:
            spec[method] = method_config

    schema = {
        "site_code": code,
        "host": host,
        "region": extract_region(code),
        "discover": {
            "entry_url": url,
            "link_selector": "",
            "url_pattern": "",
            "load_more": "none",
        },
        "spec": spec,
        "identity": {
            "series_key": "series_name",
            "model_normalize": "upper_alnum",
        },
        "expected": {"series_count": None, "model_count": None},
        "_source": f"reused from cases.jsonl: {case.get('code', '')}",
        "_note": case.get("note", ""),
    }

    url_suffix = sol.get("url_suffix", "")
    if url_suffix:
        schema["spec"]["url_suffix"] = url_suffix
    if sol.get("url_suffix_preferred"):
        schema["spec"]["url_suffix_preferred"] = True
    series_rule = sol.get("series_rule", "")
    if series_rule:
        schema["discover"]["series_rule"] = series_rule

    # 卖点段
    sp_sol = case.get("sp_solution", {})
    if sp_sol:
        sp_extract_order = sp_sol.get("extract_order", [])
        sp: dict = {"extract_order": sp_extract_order}
        for method in sp_extract_order:
            method_config = sp_sol.get(method, {})
            if method_config:
                sp[method] = method_config
        for field in ("container", "title", "description", "image", "video"):
            val = sp_sol.get(field)
            if val:
                first_method = sp_extract_order[0] if sp_extract_order else ""
                if first_method and first_method not in sp:
                    sp[first_method] = {}
                if first_method and isinstance(sp.get(first_method), dict):
                    sp[first_method].setdefault(field, val)
        schema["selling_points"] = sp

    return schema


def main():
    ap = argparse.ArgumentParser(description="spec 自动 Schema 生成（经验优先）")
    ap.add_argument("--entry", required=True, help="入口页 URL")
    ap.add_argument("--code", required=True, help="站点代号，如 sony_jp")
    ap.add_argument("--out", default="", help="输出 schema JSON 路径")
    ap.add_argument("--force-probe", action="store_true", help="强制重新探测")
    args = ap.parse_args()

    out_path = Path(args.out) if args.out else Path(f"schema_{args.code}.json")
    cases = load_cases()

    if not args.force_probe:
        scored = match_cases(cases, args.entry, args.code)
        if scored:
            best_score, best = scored[0]
            schema = case_to_schema(best, args.entry, args.code)
            out_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
            tag = "精确匹配" if best.get("code") == args.code else f"复用{best['code']}"
            print(f"[MATCH] {tag} (score={best_score})")
            print(f"  → schema已生成: {out_path}")
            print(f"  → 来源: {best.get('note', '')[:80]}")
            print(f"  → 建议做沙箱验证，验证失败加 --force-probe")
            return
        else:
            print(f"[NOMATCH] 无匹配经验，需要探测")

    # 跑 probe
    probe_script = Path(__file__).resolve().parent / "probe.py"
    if not probe_script.exists():
        print(f"[ERROR] probe.py 不存在: {probe_script}")
        return
    import subprocess
    entry_out = out_path.parent / f"probe_{args.code}_entry.json"
    print(f"[PROBE] 探入口页: {args.entry}")
    result = subprocess.run(
        [sys.executable, str(probe_script), "--entry", args.entry,
         "--code", args.code],
        capture_output=True, text=True, encoding="utf-8",
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    print(f"\n[DONE] probe完成")
    print(f"  → 请查看信号，手动写 schema，保存到 {out_path}")
    print(f"  → 验证通过后追加 cases.jsonl")


if __name__ == "__main__":
    main()
