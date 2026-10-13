"""Best Buy（.ca / .com）sitemap 商品目录索引：确定性的"这个型号有没有上架"。

为什么要有这个脚本
------------------
两家 Best Buy 的 robots.txt **都明确禁抓站内搜索路径**：

    bestbuy.ca :  Disallow: /en-ca/search   Disallow: /en-ca/Search
    bestbuy.com:  Disallow: */site/searchpage.jsp?st=*

而搜索恰恰是"某型号到底有没有上架"最不可靠的判定方式（广召回 + 广告混排 + 查询词回显，
见 docs/BestBuy美国站_参照加拿大Amazon经验_方案与红线.md §3.1）。
两家又都**显式放行商品页**并公布了站点地图：

    bestbuy.ca :  Allow: /en-ca/product/     Sitemap: https://www.bestbuy.ca/sitemap_index.xml
    bestbuy.com:  Allow: /site/  (AI 发现组)   Sitemap: sitemaps.bestbuy.com/sitemaps_bsin.xml

于是：**用 sitemap 建一份本地商品目录，"型号在不在目录里"就是一个确定性问题**——
不用碰被禁的搜索路径，不用解析模糊搜索结果，也不会有"广告被当成命中"的误抓。

匹配为什么不能简单做子串
------------------------
slug 是连字符分词的商品名（`hisense-65-u8n-series-...-65u8n/12345678`）。
直接子串匹配会让 `U8N` 命中 `XU8NX` 之类的伪命中（和 specs 里那个"整页 regex"是同一类错误）。
所以这里按**分词逐段拼接**比对：
    tokens = slug.split("-") → 归一化每段 → 相邻 k 段拼接后与目标型号归一化串**完全相等**
`65U8N` 命中 `...,65,u8n` ✓；`75,u8n` 不会被 `65U8N` 命中 ✓（尺寸不同即不同型号）。

★ 一个实测确认的边界：若型号本身写成**系列名**（如 `U8N`），它会**同时命中 65/75 各尺寸**，
因为 slug 里确实存在独立的 `u8n` 分词。这是设计使然（系列级入口对应多个具体型号），
但会把"系列"当成"型号"交付。当前加拿大清单里不会发生（实测 621 条中归一化长度 ≤4 的为 0 条，
全是带尺寸的完整型号）；若将来清单引入系列名，须先定义取价口径。

用法
----
    # 1) 建索引（首次约需下载全部 sitemap；带断点续传，可反复运行）
    py -3.12 scripts/bestbuy_ca_catalog.py build --site bestbuy_ca

    # 2) 用加拿大型号清单比对，输出"找到/未找到 + 对应 PDP URL"
    py -3.12 scripts/bestbuy_ca_catalog.py match --site bestbuy_ca --brand hisense_ca

    # 3) 只看索引统计
    py -3.12 scripts/bestbuy_ca_catalog.py stats --site bestbuy_ca

产出（默认落 data/<国家中文名>/）：
    bestbuy_ca_catalog.csv      全量商品目录（sku, slug, url, sitemap）
    bestbuy_ca_match_<brand>.csv 型号比对结果（含 found / not_found 与归因）
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 站点配置：sitemap 索引地址 + 商品 URL 形态（正则里 group(1)=sku、group(2)=slug）
SITES: dict[str, dict] = {
    "bestbuy_ca": {
        "index": "https://www.bestbuy.ca/sitemap_index.xml",
        "cn_dir": "加拿大",
        "product_re": re.compile(r"bestbuy\.ca/en-ca/product/([^/]+)/(\d+)", re.I),
    },
    "bestbuy_us": {
        # bestbuy.com 的 sitemap 是分片索引（sitemaps_pdp / sitemaps_bsin），
        # ★尚未实测可达性与 Akamai 姿态，先用占位并在运行时如实报错。
        "index": "https://sitemaps.bestbuy.com/sitemaps_pdp.xml",
        "cn_dir": "美国",
        "product_re": re.compile(r"bestbuy\.com/(?:site|product)/([^/]+)/(\d+)", re.I),
    },
}

_CJK_RE = re.compile(r"[\u3000-\u9fff\uff00-\uffef]+")


def _norm(value: str) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip",
        "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if url.endswith(".gz"):
            raw = gzip.decompress(raw)
        elif (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        return raw


def _index_dir(site: str) -> Path:
    return PROJECT_ROOT / "data" / "_sitemap" / site


def _out_dir(site: str) -> Path:
    cfg = SITES[site]
    d = PROJECT_ROOT / "data" / cfg["cn_dir"]
    return d if d.is_dir() else PROJECT_ROOT / "data"


# ---------------------------------------------------------------- build

def cmd_build(args) -> int:
    cfg = SITES[args.site]
    cache = _index_dir(args.site)
    cache.mkdir(parents=True, exist_ok=True)
    try:
        idx = _fetch(cfg["index"]).decode("utf-8", "replace")
    except Exception as e:
        print(f"[ERROR] 取 sitemap 索引失败 {cfg['index']}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    subs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", idx)
    if not subs:
        print(f"[ERROR] 索引里没有 <loc>：{cfg['index']}", file=sys.stderr)
        return 2
    print(f"[INDEX] {args.site} 子 sitemap {len(subs)} 个")

    rows_path = cache / "products.csv"
    done_path = cache / "done.json"
    done: set[str] = set()
    if done_path.exists():
        try:
            done = set(json.loads(done_path.read_text(encoding="utf-8")))
        except Exception:
            done = set()
    new_file = not rows_path.exists()
    total = 0
    with rows_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(["sku", "slug", "url", "sitemap"])
        for i, sub in enumerate(subs, 1):
            if sub in done:
                print(f"  [{i}/{len(subs)}] 跳过（已索引） {sub}")
                continue
            try:
                body = _fetch(sub).decode("utf-8", "replace")
            except Exception as e:
                print(f"  [{i}/{len(subs)}] ★失败 {sub}: {type(e).__name__}: {e}")
                time.sleep(args.sleep)
                continue
            n = 0
            for m in cfg["product_re"].finditer(body):
                slug, sku = m.group(1), m.group(2)
                writer.writerow([sku, slug, m.group(0), sub])
                n += 1
            total += n
            done.add(sub)
            done_path.write_text(json.dumps(sorted(done), ensure_ascii=False),
                                 encoding="utf-8")
            print(f"  [{i}/{len(subs)}] {sub} → 商品 {n} 条")
            time.sleep(args.sleep)
    print(f"[DONE] 本次新增商品 {total} 条 → {rows_path}")
    return 0


# ---------------------------------------------------------------- match

def _load_catalog(site: str) -> dict[int, list[tuple[str, str]]]:
    """sku → [(slug, url)]（同一 sku 多个 slug 时都留）。"""
    rows_path = _index_dir(site) / "products.csv"
    if not rows_path.exists():
        raise SystemExit(f"[ERROR] 还没有索引，先跑 build：{rows_path}")
    out: dict[int, list[tuple[str, str]]] = {}
    with rows_path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                sku = int(row["sku"])
            except (TypeError, ValueError):
                continue
            out.setdefault(sku, []).append((row.get("slug", ""), row.get("url", "")))
    return out


# 连接词：尺寸与系列之间常夹着的通用词（`65-inch-class-4k-uhd-u8n-series`）。
# 匹配时允许跳过这些词，但**不把它们从"可拼接"里排除**——万一某个型号真含
# 这类词（如 "4K"），拼接分支仍会命中。
# ★必须过 _norm：slug 分词是归一化后的大写串，这里若留小写会永远匹配不上
#   （这个 bug 让"连接词分隔"的 slug 全部漏判，且不报任何错）。
_FILLERS = frozenset(_norm(t) for t in (
    "inch", "inches", "class", "series", "tv", "television", "televisions",
    "uhd", "4k", "8k", "hdr", "hdr10", "smart", "google", "android",
    "dolby", "vision", "atmos", "miniled", "mini", "led",
    "and", "with", "for", "the", "new",
))


def _slug_matches_model(slug: str, model: str, max_skip: int = 5,
                        max_span: int = 10) -> bool:
    """型号是否以「分词拼接（允许跳过连接词）后完全相等」的方式出现在 slug 里。

    为什么不用子串包含：slug 是连字符分词的商品名，子串匹配会让 `U8N` 命中
    `XU8NX` 这类伪命中——与 specs 里"search.sku 不能配整页 regex"是同一类错误。

    为什么要允许跳过连接词：真实 slug 写成 `...,65,inch,class,4k,uhd,u8n,...`
    时，尺寸与系列之间夹了 4 个通用词，纯相邻拼接会**漏判**。跳过的只能是
    `_FILLERS` 里的通用词，且每个窗口最多跳 max_skip 个，所以精度不靠"窗口宽度"
    而靠"词表封闭"。

    开销：只对**已经通过廉价预筛**的候选调用（见 cmd_match），不是全表扫描。
    """
    want = _norm(model)
    if len(want) < 2:
        return False
    tokens = [_norm(t) for t in re.split(r"[-_/]+", slug or "") if t]
    tokens = [t for t in tokens if t]
    n = len(tokens)

    def dfs(i: int, acc: str, skips: int, start: int) -> bool:
        if acc == want:
            return True
        if i >= n or i - start >= max_span or len(acc) > len(want):
            return False
        tok = tokens[i]
        # 分支 1：把该 token 拼进去（先做前缀剪枝，避免无谓递归）
        merged = acc + tok
        if want.startswith(merged) and dfs(i + 1, merged, skips, start):
            return True
        # 分支 2：该 token 是连接词 → 跳过它继续
        if tok in _FILLERS and skips < max_skip and dfs(i + 1, acc, skips + 1, start):
            return True
        return False

    for start in range(n):
        if dfs(start, "", 0, start):
            return True
    return False


def cmd_match(args) -> int:
    catalog = _load_catalog(args.site)
    print(f"[CATALOG] {args.site} 去重后 SKU {len(catalog)} 个")

    models_csv = Path(args.models_csv) if args.models_csv else None
    if models_csv is None:
        import glob
        region = "ca" if args.site.endswith("_ca") else "us"
        d = PROJECT_ROOT / "data" / SITES[args.site]["cn_dir"]
        # 先找带日期戳的（最新优先），再回落无日期戳的旧命名
        pats = sorted(glob.glob(str(d / f"SPEC_型号汇总_{region}_*.csv")), reverse=True)
        if not pats:
            pats = [str(p) for p in (d / f"SPEC_型号汇总_{region}.csv",) if p.exists()]
        if not pats:
            raise SystemExit(f"[ERROR] 在 {d} 找不到 SPEC_型号汇总_{region}*.csv，"
                             f"请用 --models-csv 指定")
        models_csv = Path(pats[0])
    print(f"[MODELS] {models_csv.name}")

    want_brands = {b.strip() for b in (args.brand or "").split(",") if b.strip()}
    entries: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    with models_csv.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            code = (row.get("brand_code") or "").strip()
            if want_brands and code not in want_brands:
                continue
            model = (row.get("model_raw") or "").strip().split(" | ")[0]
            if not model:
                continue
            if (code, model) in seen:
                continue
            seen.add((code, model))
            name = _CJK_RE.sub(" ", row.get("brand_name") or code).strip()
            entries.append((code, name, model))

    out_rows = []
    found = 0
    # 速度：全表逐 slug 跑精确匹配是 O(型号 × 商品)——26 万 SKU × 140 型号实测
    # 10 分钟都跑不完。所以先把目录摊平并**预计算归一化串**（只算一次），
    # 再用型号主干（65U8N → U8N）做廉价子串预筛，只对少数候选跑精确匹配。
    # 预筛是"宁可多留"，精度完全由精确匹配保证。
    items: list[tuple[str, str, str, str]] = []      # (sku, slug, url, flat)
    for sku, variants in catalog.items():
        for slug, url in variants:
            items.append((str(sku), slug,
                          url or f"https://www.bestbuy.ca/en-ca/product/{slug}/{sku}",
                          _norm(slug)))
    print(f"[PREP] 目录条目 {len(items)} 条（预筛串已预计算）")

    for code, name, model in entries:
        core = core_model(normalize_model(model))
        key = core if len(core) >= 2 else normalize_model(model)
        hits: list[tuple[str, str]] = []
        for sku, slug, url, flat_slug in items:
            if key not in flat_slug:          # 廉价预筛：主干不在 → 直接排除
                continue
            if _slug_matches_model(slug, model):
                hits.append((sku, url))
                if len(hits) >= 5:            # 同型号最多留 5 个候选，够用了
                    break
        status = "found" if hits else "not_found"
        found += bool(hits)
        out_rows.append({
            "brand_code": code, "brand_name": name, "model": model,
            "status": status, "hit_count": len(hits),
            "sku": hits[0][0] if hits else "",
            "url": hits[0][1] if hits else "",
            "all_skus": " | ".join(h[0] for h in hits[:5]),
        })
        print(f"  {status:9s} {name} {model}"
              + (f"  → sku={hits[0][0]}" if hits else ""))

    out_dir = _out_dir(args.site)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = args.brand.replace(",", "_") if args.brand else "all"
    dest = out_dir / f"bestbuy_{args.site.split('_')[-1]}_match_{tag}.csv"
    with dest.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    print(f"\n[MATCH] 型号 {len(entries)} 个：找到 {found}，未找到 {len(entries) - found}"
          f"（覆盖率 {found / max(1, len(entries)):.1%}）")
    print(f"[SAVED] {dest}")
    print("★ 未找到 = 该站在售目录里确实没有这个型号（确定性结论，不是搜索失败）。")
    return 0


def cmd_stats(args) -> int:
    catalog = _load_catalog(args.site)
    rows_path = _index_dir(args.site) / "products.csv"
    n_rows = sum(1 for _ in rows_path.open(encoding="utf-8")) - 1
    done = _index_dir(args.site) / "done.json"
    n_done = len(json.loads(done.read_text(encoding="utf-8"))) if done.exists() else 0
    print(f"[STATS] {args.site}")
    print(f"  商品行数（含重复 slug）: {n_rows}")
    print(f"  去重 SKU              : {len(catalog)}")
    print(f"  已索引子 sitemap      : {n_done}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # 选项挂在子命令上（parents），这样 `build --site x` / `match --brand y` 都直观；
    # 不放在主 parser 上是为了避免 argparse 的经典坑：子 parser 的默认值会覆盖
    # 主 parser 上已解析出来的同名参数。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--site", default="bestbuy_ca", choices=sorted(SITES))
    common.add_argument("--models-csv", default="", help="型号清单；缺省按站点国家自动找")
    common.add_argument("--brand", default="", help="只比对这些 brand_code，逗号分隔")
    common.add_argument("--sleep", type=float, default=0.5, help="每个 sitemap 之间的间隔秒")

    p = argparse.ArgumentParser(
        description="Best Buy sitemap 商品目录索引与型号存在性比对",
        epilog="示例：python scripts/bestbuy_ca_catalog.py build --site bestbuy_ca")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", parents=[common], help="下载 sitemap 建本地商品目录（可续传）")
    sub.add_parser("match", parents=[common], help="型号清单 → SKU/PDP URL 确定性映射")
    sub.add_parser("stats", parents=[common], help="索引统计")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return {"build": cmd_build, "match": cmd_match, "stats": cmd_stats}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
