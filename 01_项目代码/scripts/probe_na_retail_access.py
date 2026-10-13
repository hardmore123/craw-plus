# -*- coding: utf-8 -*-
"""北美零售站：数据路由（搜索）可达性诊断 —— 判定"是否需要住宅/移动代理"。

为什么需要这个工具（2026-09-20 的教训）：
  只用纯 HTTP 探测会给站点**大面积误判**。本轮 18 站里有 8 站在 HTTP 下表现为
  "被拦"，真实浏览器下却完全正常（`amazon_*` 三站、`canadiantire_ca`、
  `palacio_mx`、`thebrick_ca`、`leons_ca`、`costco_ca/us`）。原因是这些站
  `requires_browser=True`，纯 urllib 的 TLS 指纹/请求头特征会被拦。

  也不能只看 "captcha" 这个词命不命中。它在正常页里出现得极频繁：
  - CSP 声明里的 `www.recaptcha.net`（`sams_mx` 被这条误判）
  - 表单用的 `<script src=".../recaptcha__en.js">`（`bestbuy_us` 被这条误判）
  所以本工具同时输出**命中偏移 + 上下文片段 + 页面业务内容量**，
  并在"命中标记但页面很大且业务内容充足"时给出 `SUSPECT_FALSE_POSITIVE`。

用法：
    py -3.12 scripts/probe_na_retail_access.py --regions ca us mx --phase both
    py -3.12 scripts/probe_na_retail_access.py --sites walmart_us bestbuy_us --phase browser

判定口径与生产一致：用站点自己的 `BlockDetector`（含 `block_marker_allowlist` 豁免）。
只读；不写 data/session；结果落 data/_smoke/na_access_probe.json。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from overseas import config                                       # noqa: E402
from overseas.fetchers import BrowserFetcher                      # noqa: E402
from overseas.infra import BlockDetector, DiskCache, RateLimiter   # noqa: E402
from overseas.regions_config import get_region                    # noqa: E402
from overseas.scenarios import open_dom                           # noqa: E402
from overseas.sites import SiteRegistry                           # noqa: E402

OUT_DIR = ROOT / "data" / "_smoke"
DEFAULT_KEYWORD = "Samsung tv"

# 明确指向"这是挑战页/拒绝页"的标记：命中即判 BLOCKED，不受上下文与页面体积影响。
# （`walmart_ca` 的 `<title>Verify Your Identity</title>` 就是靠这条才没被误判成
#   "疑似误报"——它同时含 `px-captcha`，早期版本被上下文判据放过了。）
DEFINITIVE_MARKERS = (
    "robot or human", "verify your identity", "verifica tu identidad",
    "just a moment", "checking your browser", "cf-challenge",
    "cf-browser-verification", "attention required", "access denied",
    "pardon our interruption", "unusual traffic", "are you a robot",
    "enable javascript and cookies", "best buy international",
    "request blocked", "you don't have permission",
)
# 歧义标记：正常页里也频繁出现（脚本/CSP 引用），必须结合上下文与页面内容判断
AMBIGUOUS_MARKERS = ("captcha", "perimeterx", "px-captcha")

# 用于交叉判断"是拦截页还是正常页"的标记（含上下文，避免误判）
MARKERS = [
    "robot or human", "px-captcha", "perimeterx",
    "verify your identity", "verifica tu identidad",
    "captcha", "access denied", "pardon our interruption",
    "just a moment", "checking your browser", "cf-challenge",
    "unusual traffic", "are you a robot", "enable javascript and cookies",
    "best buy international", "request blocked",
]
# 业务内容迹象：正常 PDP/搜索页应当有
PLINK_PATTERNS = [
    r"/ip/[^\"'\s]*\d{5,}", r"\.product\.\d+\.html", r"/p/[A-Za-z0-9\-]{6,}",
    r"/dp/[A-Z0-9]{8,}", r"/site/[^\"'\s]+/\d{6,}",
    r"/(?:producto|product|prod|item)/[^\"'\s]{4,}",
]


def analyze_html(html: str) -> dict:
    """从 HTML 提取判定所需的客观特征（含 marker 命中偏移与上下文）。"""
    h = html or ""
    low = h.lower()
    m = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
    info = {
        "len": len(h),
        "title": (m.group(1).strip()[:120] if m else ""),
        "price_like": len(re.findall(r"\$\s?\d{1,4}\.\d{2}|\d[\d,]{2,}\.\d{2}\s*(?:MXN|CAD)", h)),
        "add_to_cart": len(re.findall(r"add to cart|añadir al carrito|agregar al carrito", low)),
        "links": len({x for p in PLINK_PATTERNS for x in re.findall(p, h, re.I)}),
        "marker_hits": [],
    }
    for mk in MARKERS:
        i = low.find(mk)
        if i >= 0:
            info["marker_hits"].append({
                "marker": mk, "offset": i, "in_first_8000": i < 8000,
                "context": h[max(0, i - 100):i + 100].replace("\n", " ")[:200],
            })
    return info


def _looks_like_script_or_csp(context: str, marker: str) -> bool:
    """marker 命中处是否只是"页面引用了验证码脚本 / CSP 声明"，而非验证页正文。

    `captcha` 这个词在正常页里出现得极频繁，本轮实测两类误报：
      - `sams_mx`   : CSP 声明 `... www.recaptcha.net; img-src * ...`
      - `bestbuy_us`: `<script src="https://www.gstatic.com/recaptcha/releases/.../recaptcha__en.js">`
    共同特征是命中处紧邻 URL/脚本标签，而不是可见的挑战文案。
    """
    if marker not in ("captcha", "perimeterx", "px-captcha"):
        return False
    c = (context or "").lower()
    return any(t in c for t in ("src=", "content-security", "gstatic",
                                "recaptcha.net", "recaptcha__", ".js",
                                "script", "; img-src", "connect-src"))


def classify(status: int, blocked: bool, reason: str, error: str,
             info: dict, expect_links: bool = True,
             parsed_hits: int | None = None) -> str:
    """给出可汇报的状态。

    判据顺序（每条都在本轮实测里踩过）：
      1. 网络错误
      2. **HTTP 404/410 优先于 blocked** —— 项目红线（《跨国家线复用与开发指南》§5.1）：
         404 是正常缺页，不能因 404 页正文短或含 marker 就记成"被拦"。
         `sams_mx` 正是此例：404 页的 CSP 里有 `recaptcha.net`，被误记成 "404+captcha 被拦"。
      3. blocked：先排除两类误报——
         A) 命中处只是脚本/CSP 引用（与页面大小无关）；
         B) 命中标记但页面体积大且业务内容充足。
      4. **站点自己的解析器抽出几个候选**（parsed_hits）是最强证据：
         >0 → 页面确可用；==0 且无商品链接 → 是选择器/等待问题，不是反爬问题。
         （`costco_us` 正是此例：2.96MB 真页却 0 候选，若按"体积大即有内容"会误判成 OK。）
      5. 非 200 / 体积过小 / 无业务内容
    """
    if error:
        return "TIMEOUT" if "timeout" in error.lower() else "ERROR"
    if status in (404, 410):
        return f"HTTP_{status}(缺页，非拦截)"
    if blocked:
        hits = info.get("marker_hits") or []
        # 先看"明确挑战"标记：命中即判拦截，不给上下文/体积翻案的机会
        definitive = [h for h in hits if h["marker"] in DEFINITIVE_MARKERS]
        if definitive:
            return f"BLOCKED({definitive[0]['marker']})"
        # 只剩歧义标记（captcha/perimeterx/px-captcha）→ 才走误报推断
        if hits and any(_looks_like_script_or_csp(h.get("context", ""), h["marker"])
                        for h in hits):
            return f"SUSPECT_FALSE_POSITIVE(脚本/CSP 引用:{hits[0]['marker']})"
        rich = info["len"] > 200000 and (info["links"] > 0 or info["price_like"] > 10
                                         or info["add_to_cart"] > 0)
        return f"SUSPECT_FALSE_POSITIVE({reason})" if rich else f"BLOCKED({reason})"
    if status != 200:
        return f"HTTP_{status}"
    if info["len"] < 3000:
        return f"TINY({info['len']}B)"
    if parsed_hits is not None:
        if parsed_hits > 0:
            return "OK"
        if parsed_hits == 0:
            # 站点自己的解析器（生产同款）抽出 0 个候选 → 抓不到，不能算 OK。
            # 注意不能用"页面里有几个链接"来豁免：`costco_us` 是 2.96MB 真页、
            # 通用正本能捞到 4 个链接，但生产解析器 0 候选 → 实际一条也抓不到。
            return "OK_NO_CONTENT(站点解析器 0 候选：选择器/等待待查)"
    if expect_links and info["links"] == 0 and info["price_like"] == 0:
        return "OK_NO_CONTENT(选择器/渲染待查)"
    return "OK"


def http_get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return {"status": r.status, "html": body, "error": "",
                    "sec": round(time.time() - t0, 1)}
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return {"status": e.code, "html": body, "error": "",
                "sec": round(time.time() - t0, 1)}
    except Exception as e:
        return {"status": 0, "html": "", "error": f"{type(e).__name__}: {e}",
                "sec": round(time.time() - t0, 1)}


def browser_get(adapter, url: str, scroll: int = 3, wait_ms: int = 8000,
                nav_timeout_ms: int = 45000) -> dict:
    """真实浏览器打开，用站点自己的 BlockDetector（含 allowlist）判定。

    ★ 关键：`parse_search` 必须**在 `with open_dom(...)` 上下文内**调用。
    本工具早期版本把它放到上下文退出之后（且 fetcher 已 close），`dom` 已失效，
    于是**恒返回 0 个候选**——而 `classify` 又把该值当成最强证据，
    导致 `amazon_*` / `liverpool_mx` / `costco_ca` 被误判成 "站点解析器 0 候选"。
    实测同一页面在上下文内调用可得 30 个候选。这类"关页后再解析"的坑
    在真实抓取里不存在（生产是在上下文内解析），故必须对齐生产口径。
    """
    interval = max(config.MIN_INTERVAL, adapter.suggested_interval)
    t0 = time.time()

    def _attempt() -> dict:
        f = BrowserFetcher(
            site_code=adapter.code, persist_state=False,     # 不污染登录态
            rate_limiter=RateLimiter(min_interval=interval),
            detector=BlockDetector(
                ignore_markers=getattr(adapter, "block_marker_allowlist", None)),
            cache=DiskCache())
        try:
            with open_dom(adapter, f, url, wait_selector="a", scroll_passes=scroll,
                          extra_wait_ms=wait_ms,
                          nav_timeout_ms=nav_timeout_ms) as (res, dom, html):
                # —— 必须在上下文内解析（见 docstring）——
                parsed = -1
                if dom is not None and not res.blocked:
                    try:
                        parsed = len(adapter.parse_search(dom, html or "", limit=30))
                    except Exception:
                        parsed = -1
                return {"status": int(getattr(res, "status", 0) or 0),
                        "html": html or "", "blocked": bool(res.blocked),
                        "reason": str(getattr(res, "block_reason", "") or ""),
                        "error": str(getattr(res, "error", "") or ""),
                        "ok": bool(res.ok), "parsed_hits": parsed,
                        "sec": round(time.time() - t0, 1)}
        finally:
            try:
                f.close(save_state=False)
            except Exception:
                pass

    # ★ 空页重试：并发跑多个浏览器时，重站偶尔会返回 len=0 /
    #   `no_anchor_element`（实测 amazon_us、bestbuy_us 出现过）。那不是站点拦截，
    #   把它记成 BLOCKED 会得出错误结论（"这站需要代理"），所以必须重试一次。
    result: dict = {}
    for attempt in (1, 2):
        try:
            result = _attempt()
        except Exception as e:
            result = {"status": 0, "html": "", "blocked": False, "reason": "",
                      "error": f"{type(e).__name__}: {e}", "ok": False,
                      "parsed_hits": -1, "sec": round(time.time() - t0, 1)}
        empty = (not result.get("html")) or (
            result.get("blocked") and "no_anchor" in str(result.get("reason", "")))
        if not empty or attempt == 2:
            break
        time.sleep(6.0)          # 重试前稍等，避开瞬时抖动
    result["attempts"] = attempt
    return result


def probe_one(code: str, region: str, phase: str, keyword: str,
              bopts: dict | None = None) -> dict:
    out: dict = {"site": code, "region": region}
    try:
        adapter = SiteRegistry.get(code)
    except Exception as e:
        out["error"] = f"adapter 加载失败: {e}"
        return out
    out["allowlist"] = list(getattr(adapter, "block_marker_allowlist", None) or [])
    out["requires_browser"] = bool(getattr(adapter, "requires_browser", False))
    try:
        url = adapter.search_url(keyword)
    except Exception as e:
        out["error"] = f"search_url 失败: {e}"
        return out
    out["url"] = url

    if phase in ("http", "both"):
        r = http_get(url)
        info = analyze_html(r["html"])
        out["http"] = {
            "status": r["status"], "sec": r["sec"], "error": r["error"],
            "markers": info["marker_hits"], "title": info["title"],
            "price_like": info["price_like"], "links": info["links"],
            "add_to_cart": info["add_to_cart"], "len": info["len"],
            "class": classify(r["status"], bool(info["marker_hits"]),
                              f"marker:{info['marker_hits'][0]['marker']}"
                              if info["marker_hits"] else "",
                              r["error"], info),
        }
        if phase == "both":
            time.sleep(6.0)

    if phase in ("browser", "both"):
        b = browser_get(adapter, url, **(bopts or {}))
        info = analyze_html(b["html"])
        hits = info["marker_hits"]
        # parsed_hits 已由 browser_get 在页面上下文内算好（见其 docstring）
        parsed = int(b.get("parsed_hits", -1))
        # BlockDetector 用的窗口是前 8000 字符；这里按同一窗口复核上下文
        cls = classify(b["status"], b["blocked"], b.get("reason", ""),
                       b.get("error", ""), info,
                       parsed_hits=(None if parsed < 0 else parsed))
        out["browser"] = {
            "status": b["status"], "sec": b["sec"], "blocked": b["blocked"],
            "reason": b.get("reason", ""), "error": b.get("error", ""),
            "title": info["title"], "len": info["len"], "links": info["links"],
            "price_like": info["price_like"], "add_to_cart": info["add_to_cart"],
            "parsed_hits": parsed, "markers": hits, "class": cls,
        }
        out["verdict"] = cls
    else:
        out["verdict"] = out.get("http", {}).get("class", "")
    return out


def selftest() -> int:
    """离线自检 classify 的四条判据（把本轮踩到的误报形态固化成用例）。

    不联网也能跑：`py -3.12 scripts/probe_na_retail_access.py --selftest`
    """
    def hit(marker, offset, ctx):
        return {"marker": marker, "offset": offset,
                "in_first_8000": offset < 8000, "context": ctx}

    def mk(len_, links, price, cart, *hits):
        return {"len": len_, "links": links, "price_like": price,
                "add_to_cart": cart, "marker_hits": list(hits)}

    cases = [
        # 1) 真实拦截页：体积小、无业务内容、marker 是可见挑战文案
        ("真实拦截页(walmart_us 形态)",
         classify(200, True, "marker:robot or human", "",
                  mk(15260, 0, 0, 0,
                     hit("robot or human", 34, "<title>Robot or human?</title>"))),
         "BLOCKED"),
        # 2) ★ 明确挑战标记必须压过歧义标记的上下文推断。
        #    walmart_ca 实测：<title>Verify Your Identity</title>（明确挑战）
        #    同时含 px-captcha（歧义），而 px-captcha 的上下文后面紧跟 <script>，
        #    只看上下文会把它误判成"疑似误报"——这是本工具自己踩过的假阴性。
        ("明确挑战优先(walmart_ca 形态)",
         classify(200, True, "marker:captcha", "",
                  mk(12042, 0, 0, 0,
                     hit("px-captcha", 2773,
                         '</div><script src="/px.js"></script> #px-captcha'),
                     hit("verify your identity", 137,
                         "<title>Verify Your Identity</title>"))),
         "BLOCKED"),
        # 3) CSP 误报：sams_mx —— 404 页的 CSP 里出现 www.recaptcha.net
        #    ★ 项目红线：404 优先于 blocked，故应为 HTTP_404 而不是 BLOCKED
        ("CSP 误报 + 404 优先(sams_mx 形态)",
         classify(404, True, "marker:captcha", "",
                  mk(282411, 0, 2, 0,
                     hit("captcha", 4705, "... www.recaptcha.net; img-src * ..."))),
         "HTTP_404"),
        # 4) 脚本引用误报：bestbuy_us —— 表单用的 recaptcha__en.js（只有歧义标记）
        ("脚本引用误报(bestbuy_us 形态)",
         classify(200, True, "marker:captcha", "",
                  mk(1823215, 412, 61, 37,
                     hit("captcha", 3054,
                         'script src="https://www.gstatic.com/recaptcha/releases/x/'
                         'recaptcha__en.js"'))),
         "SUSPECT_FALSE_POSITIVE"),
        # 5) 正常页
        ("正常页(thebrick_ca 形态)",
         classify(200, False, "", "", mk(954398, 30, 40, 12),
                  parsed_hits=30), "OK"),
        # 6) 页面通但站点解析器 0 候选（costco_us 实测形态：2.96MB 真页、通用正本能
        #    捞到 4 个链接，但生产解析器 0 候选）——必须与"正常页"区分开，
        #    否则会把"选择器/等待问题"误当成"可抓"。
        ("页面通但 0 候选(costco_us 形态)",
         classify(200, False, "", "", mk(2957914, 4, 2, 4),
                  parsed_hits=0), "OK_NO_CONTENT"),
    ]
    failed = 0
    for name, got, want in cases:
        ok = got.startswith(want)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} -> {got}")
        if not ok:
            failed += 1
    print(f"\n自检{'全部通过' if not failed else f'{failed} 项失败'}")
    return 0 if not failed else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="北美零售站访问性诊断")
    ap.add_argument("--selftest", action="store_true", help="只跑离线判据自检（不联网）")
    ap.add_argument("--regions", nargs="*", default=["ca", "us", "mx"])
    ap.add_argument("--sites", nargs="*", default=None, help="只测指定站点 code")
    ap.add_argument("--phase", choices=["http", "browser", "both"], default="browser")
    ap.add_argument("--keyword", default=DEFAULT_KEYWORD)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--scroll", type=int, default=3,
                    help="浏览器滚动轮数；SPA/懒加载站调大（如 costco_us 需 20）")
    ap.add_argument("--wait-ms", type=int, default=8000,
                    help="渲染后额外等待毫秒；慢站调大（如 15000）")
    ap.add_argument("--nav-timeout-ms", type=int, default=45000)
    ap.add_argument("--out", default=str(OUT_DIR / "na_access_probe.json"))
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    sites: list[tuple[str, str]] = []
    if args.sites:
        for rc in args.regions:
            reg = get_region(rc)
            if reg:
                for rs in reg.retail_sites:
                    if rs.site in args.sites:
                        sites.append((rs.site, rc))
        missing = set(args.sites) - {c for c, _ in sites}
        if missing:
            print(f"[WARN] 未在 region 配置中找到: {sorted(missing)}")
    else:
        for rc in args.regions:
            reg = get_region(rc)
            if reg:
                for rs in reg.retail_sites:
                    sites.append((rs.site, rc))

    if not sites:
        print("[ERROR] 没有可测站点")
        return 2
    print(f"[NA-ACCESS] {len(sites)} 站  阶段={args.phase}  关键词={args.keyword!r}  "
          f"workers={args.workers}")
    print("[NA-ACCESS] 判定用站点自身 BlockDetector（含 allowlist）；"
          "标记命中但页面富内容 → SUSPECT_FALSE_POSITIVE\n")

    results: list[dict] = []
    bopts = {"scroll": args.scroll, "wait_ms": args.wait_ms,
             "nav_timeout_ms": args.nav_timeout_ms}
    print(f"[NA-ACCESS] 浏览器参数 scroll={args.scroll} wait={args.wait_ms}ms "
          f"nav_timeout={args.nav_timeout_ms}ms")
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(probe_one, c, r, args.phase, args.keyword, bopts): (c, r)
                for c, r in sites}
        for fut in as_completed(futs):
            code, rc = futs[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"site": code, "region": rc, "verdict": "ERROR",
                       "error": f"{type(e).__name__}: {e}"}
            results.append(res)
            b = res.get("browser") or res.get("http") or {}
            print(f"[{rc}] {code:18s} {res.get('verdict', ''):46s} "
                  f"status={b.get('status', '-')} len={b.get('len', '-')} "
                  f"links={b.get('links', '-')} hits={b.get('parsed_hits', '-')} "
                  f"{b.get('reason', '') or b.get('error', '')}")
            for mh in (b.get("markers") or [])[:2]:
                print(f"       ↳ marker {mh['marker']!r} @ {mh['offset']} "
                      f"(前8000内={mh['in_first_8000']})  {mh['context'][:110]}")

    order = {c: i for i, (c, _) in enumerate(sites)}
    results.sort(key=lambda r: order.get(r["site"], 99))
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "keyword": args.keyword,
        "phase": args.phase,
        "egress_note": "判定依赖当前出口 IP 类型（本机为美国机房 IP）",
        "results": results,
    }
    outp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    n_ok = sum(1 for r in results if str(r.get("verdict", "")).startswith("OK"))
    n_fp = sum(1 for r in results if "FALSE_POSITIVE" in str(r.get("verdict", "")))
    n_bl = sum(1 for r in results if str(r.get("verdict", "")).startswith("BLOCKED"))
    print(f"\n[汇总] OK={n_ok}  疑似误报={n_fp}  真拦截={n_bl}  共={len(results)}")
    print(f"[DUMP] {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
