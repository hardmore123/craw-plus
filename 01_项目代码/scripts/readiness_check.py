# -*- coding: utf-8 -*-
"""全量就绪小样实测：对每个零售站用「真实全量入口」跑 3 个型号，判定 schema+adapter 能否支撑全量。

不跑全量。每站：
  正样本 2 个 —— 主库 data/overseas.db 里该站已入库过的真实型号（6 大品牌、形似型号码）
  负样本 1 个 —— 不存在的型号（必须判 no_item，否则说明匹配会张冠李戴）
走与全量完全相同的入口 scripts/crawl_ca_retail.py --spec --save-db，写独立 sandbox 库
data/sandbox/readiness.db，导出到 data/sandbox/out/<code>/，不碰主库。

判定（每站一行）：
  READY      正样本全部命中且有价；负样本 no_item；spec 声明 reviews 时至少一个正样本有评价
  PARTIAL    部分达标（列出缺口：命中率 / 价格 / 评价 / 翻页未到上限等）
  FAIL       搜索/抓取失败、被拦、负样本误命中（红线）
  NO_SAMPLE  主库无该站正样本，只测了负样本（需另配型号清单再测）

用法：
  py -3.12 scripts/readiness_check.py --region ca            # 一个区域全部有 spec 的站
  py -3.12 scripts/readiness_check.py --sites thebrick_ca otto_de
  py -3.12 scripts/readiness_check.py --region ca --status approved,candidate
环境：必须走代理，脚本内强制 OVERSEAS_PROXY_REQUIRED=1（代理断了直接停，不回落直连）。
产出：data/sandbox/readiness_<日期>.csv（追加，按 site+时间去重看最新）
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from overseas.regions_config import REGIONS  # noqa: E402

MAIN_DB = "data/overseas.db"
SANDBOX_DB = "data/sandbox/readiness.db"
BRANDS = {"hisense": "Hisense", "samsung": "Samsung", "tcl": "TCL", "lg": "LG",
          "sony": "Sony", "philips": "Philips"}
NEG_MODEL = "ZQ99X7NOEXIST"
# 形似电视型号：至少 2 位数字（尺寸）+ 至少 1 个字母；排除 "3-YEAR" 这类保修/配件 SKU
MODEL_RE = re.compile(r"^(?=(?:.*\d){2})(?=.*[A-Z])(?!.*YEAR)[A-Z0-9][A-Z0-9\-/.]{3,17}$")


def site_region(code: str) -> str:
    for rc, reg in REGIONS.items():
        if any(r.site == code for r in reg.retail_sites):
            return rc
    return ""


def positives(code: str, n: int = 2) -> list[tuple[str, str]]:
    """主库里该站真实入库过的型号 [(brand_name, model)]，尽量跨品牌。"""
    if not os.path.exists(MAIN_DB):
        return []
    c = sqlite3.connect(f"file:{MAIN_DB}?mode=ro", uri=True)
    rows = c.execute(
        """select p.brand, p.model from product p join site s on s.id=p.site_id
            where s.code=? and p.model<>'' and p.brand<>''
            order by p.last_seen desc""", (code,)).fetchall()
    c.close()
    out, seen_b = [], set()
    for b, m in rows:
        key = (b or "").strip().lower()
        name = BRANDS.get(key.split()[0] if key else "")
        m = (m or "").strip().upper()
        if not name or not MODEL_RE.match(m):
            continue
        if name in seen_b and len(rows) > n:
            continue
        out.append((name, m))
        seen_b.add(name)
        if len(out) >= n:
            break
    if len(out) < n:                           # 品牌不够分散就放宽
        for b, m in rows:
            name = BRANDS.get((b or "").strip().lower().split()[0] if b else "")
            m = (m or "").strip().upper()
            if name and MODEL_RE.match(m) and (name, m) not in out:
                out.append((name, m))
            if len(out) >= n:
                break
    return out


def keep_awake() -> None:
    """长批次运行期间阻止 Windows 睡眠（进程退出即自动失效）。

    10-09 夜间实测：机器睡眠后浏览器/代理连接全部断开，批次静默停在半途。
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:  # noqa: BLE001
        pass


def free_memory_mb() -> int:
    if os.name != "nt":
        return 1 << 30
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullAvailPhys / 1024 / 1024)
    except Exception:  # noqa: BLE001
        return 1 << 30


# 单个 headless Edge 约 300~500MB。1800 是两个会话同时跑浏览器时的经验值；
# 本机 8GB、常驻 Kiro/Edge/飞书后空闲一般 1.2~1.6GB，单批次跑 1200 足够。
# 10-10 晚按用户要求再降到 800：浏览器若因内存崩溃会判 ENV_ERROR 并由看门狗自动重跑，不会产生错误结论。
MIN_FREE_MB = int(os.environ.get("OVERSEAS_MIN_FREE_MB", "800"))


def wait_for_memory(min_mb: int = MIN_FREE_MB, max_wait_s: int = 1800) -> None:
    """可用内存不足时等待（浏览器在内存紧张时会中途崩溃，跑出来的结果无效）。"""
    t0 = time.time()
    warned = False
    while free_memory_mb() < min_mb and time.time() - t0 < max_wait_s:
        if not warned:
            print(f"[WAIT] 可用内存 {free_memory_mb()}MB < {min_mb}MB，等待释放…", flush=True)
            warned = True
        time.sleep(60)


def egress_ok(proxy: str) -> tuple[bool, str]:
    """出口健康检查：经代理真实发一次 HTTP 请求。

    OVERSEAS_PROXY_REQUIRED 只做 TCP 探活——Clash 进程还在、端口开着，但当前节点
    已失效时（经代理请求返回 502 / 连接被关），探活照样通过。2026-10-08 实测：
    南美 40+ 站因此全部 ERR_CONNECTION_CLOSED，被误记成 FAIL。所以每站开跑前再验一次出口。
    """
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(
        {"http": proxy, "https": proxy}))
    for url in ("http://ip-api.com/json/?fields=query,countryCode",
                "https://www.gstatic.com/generate_204"):
        try:
            with opener.open(url, timeout=15) as r:
                body = r.read(200).decode("utf-8", "replace")
                if r.status in (200, 204):
                    return True, body.strip()[:80]
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
            continue
    return False, last


def run_site(code: str, region: str, spec_path: str, timeout: int) -> dict:
    pos = positives(code)
    brand_for_neg = pos[0][0] if pos else "Hisense"
    models = [(b, m) for b, m in pos] + [(brand_for_neg, NEG_MODEL)]
    os.makedirs("data/sandbox/models", exist_ok=True)
    mcsv = f"data/sandbox/models/{code}.csv"
    with open(mcsv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["brand_code", "brand_name", "model_raw", "search_query"])
        for b, m in models:
            w.writerow([f"{b.lower()}_{region}", b, m, f"{b} {m}"])
    spec = json.load(open(spec_path, encoding="utf-8"))
    env = dict(os.environ)
    env.setdefault("OVERSEAS_PROXY", "http://127.0.0.1:7877")
    env["OVERSEAS_PROXY_REQUIRED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    os.makedirs("data/sandbox/logs", exist_ok=True)
    log = f"data/sandbox/logs/{code}.log"
    # -u：子进程超时被杀时日志也不会因缓冲而丢失（否则超时站点日志为空，无从诊断）
    cmd = [sys.executable, "-u", "scripts/crawl_ca_retail.py", "--region", region, "--sites", code,
           "--models-csv", mcsv, "--spec", spec_path, "--max-reviews", "100",
           "--save-db", "--db", SANDBOX_DB, "--out-dir", f"data/sandbox/out/{code}"]
    t0 = time.time()
    before = _max_run()
    with open(log, "w", encoding="utf-8") as lf:
        try:
            p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, env=env, timeout=timeout)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    secs = round(time.time() - t0)
    tail = open(log, encoding="utf-8", errors="replace").read()[-3000:]
    res = {"site": code, "region": region, "spec_status": spec.get("status", ""),
           "caps": "+".join(spec.get("capabilities") or []), "rc": rc, "secs": secs,
           "positives": " ".join(m for _, m in pos), "log": log}
    if "ProxyUnavailableError" in tail:
        res.update(verdict="ABORT", gaps="代理不通，已停止")
        return res
    full = open(log, encoding="utf-8", errors="replace").read()
    if "TargetClosedError" in full or "Target page, context or browser has been closed" in full:
        # 浏览器中途崩溃（10-10 实测：本机可用内存 <2GB、并行会话也在跑浏览器时成批出现）。
        # 这是环境问题，不是 schema/adapter 问题，不能记成 FAIL；看门狗会重跑 ENV_ERROR 站点。
        res.update(verdict="ENV_ERROR", gaps="浏览器中途崩溃（TargetClosedError），环境问题，待重跑")
        return res
    run_id = _max_run()
    if run_id is None or run_id == before:
        res.update(verdict="FAIL", gaps=f"入口未建立 run（rc={rc}）：{_last_err(tail)}")
        return res
    return judge(res, run_id, pos, spec)


def _max_run():
    if not os.path.exists(SANDBOX_DB):
        return None
    c = sqlite3.connect(SANDBOX_DB)
    try:
        return c.execute("select max(id) from crawl_run").fetchone()[0]
    except sqlite3.Error:
        return None
    finally:
        c.close()


def _last_err(tail: str) -> str:
    lines = [ln for ln in tail.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if "Error" in ln or "ERROR" in ln or "Traceback" in ln:
            return ln.strip()[:160]
    return (lines[-1].strip()[:160] if lines else "")


def judge(res: dict, run_id: int, pos, spec: dict) -> dict:
    c = sqlite3.connect(SANDBOX_DB)
    st = {}
    for task, model, status, rows, msg, price in c.execute(
            "select task, model, status, row_count, message, price from retail_task_status "
            "where run_id=?", (run_id,)):
        st[(task, model.upper())] = (status, rows or 0, msg or "", price)
    c.close()
    cap = 100
    gaps, red = [], False
    pos_models = [m for _, m in pos]
    # 命中 = 找到并打开了目标商品页（价格任务状态 ok/no_price，或商品级状态
    # no_reviews/summary_only——这两种是「商品找到了，只是评价侧没拿到」）
    HIT = ("ok", "no_price", "no_reviews", "summary_only")
    empty = ("missing", 0, "", None)
    neg = st.get(("price", NEG_MODEL), empty)
    if neg[0] in HIT:
        red = True
        gaps.append("负样本被误命中（红线：匹配会张冠李戴）")
    elif neg[0] in ("failed", "blocked"):
        gaps.append(f"负样本搜索 {neg[0]}：{neg[2][:60]}")
    hit = [m for m in pos_models if st.get(("price", m), empty)[0] in HIT]
    priced = [m for m in hit if st.get(("price", m), empty)[3] is not None]
    blocked = [m for m in pos_models if st.get(("price", m), empty)[0] in ("blocked", "failed")]
    rv = {m: st.get(("review", m), empty) for m in pos_models}
    rv_rows = {m: v[1] for m, v in rv.items()}
    want_rv = "reviews" in (spec.get("capabilities") or [])
    if pos_models:
        if len(hit) < len(pos_models):
            gaps.append(f"正样本命中 {len(hit)}/{len(pos_models)}"
                        + (f"（{','.join(blocked)} 被拦/失败）" if blocked else ""))
        if len(priced) < len(hit):
            gaps.append(f"价格填充 {len(priced)}/{len(hit)}")
        if want_rv and hit and not any(rv_rows.get(m) for m in hit):
            gaps.append("spec 声明 reviews 但命中商品 0 条评价（" +
                        ",".join(rv.get(m, ("",))[0] for m in hit) + "）")
        if want_rv and any(rv_rows.get(m) == cap for m in hit):
            res["review_cap_hit"] = "Y"       # 翻页确实能翻到上限
        # 价格合理性：低于币种电视下限 / 不同型号同价 → 不可信（缺价 > 错价）
        from overseas.price_sanity import check_prices
        cur = (REGIONS.get(res.get("region", "")) or None)
        cur = cur.currency if cur else ""
        sp = check_prices(cur, [(m, st.get(("price", m), empty)[3]) for m in hit])
        if sp:
            gaps.append("价格可疑：" + "；".join(sp))
        if spec.get("_price_suspect"):
            gaps.append("spec 标记 _price_suspect（价格不入库）")
    res.update(hit=f"{len(hit)}/{len(pos_models)}", priced=len(priced),
               reviews=" ".join(f"{m}:{rv_rows.get(m, 0)}" for m in pos_models),
               neg=neg[0], run_id=run_id)
    if red or (pos_models and not hit and blocked) or (not pos_models and neg[0] in ("failed", "blocked")):
        res["verdict"] = "FAIL"
    elif not pos_models:
        res["verdict"] = "NO_SAMPLE"
    elif not gaps:
        res["verdict"] = "READY"
    else:
        res["verdict"] = "PARTIAL"
    res["gaps"] = "；".join(gaps)
    return res


def main() -> int:
    keep_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", action="append", default=[])
    ap.add_argument("--sites", nargs="*", default=[])
    ap.add_argument("--status", default="approved,candidate",
                    help="只测这些 spec.status（逗号分隔；all=全部）")
    ap.add_argument("--timeout", type=int, default=900, help="单站超时秒")
    args = ap.parse_args()

    specs = {os.path.basename(p).split(".")[0]: p for p in glob.glob("schemas/retail_specs/*.retail.json")}
    want_status = None if args.status == "all" else set(args.status.split(","))
    targets = []
    if args.sites:
        targets = [(s, site_region(s)) for s in args.sites]
    for rc in args.region:
        reg = REGIONS.get(rc)
        if reg:
            targets += [(r.site, rc) for r in reg.retail_sites]
    out_rows = []
    os.makedirs("data/sandbox", exist_ok=True)
    stamp = dt.date.today().strftime("%Y%m%d")
    out = f"data/sandbox/readiness_{stamp}.csv"
    cols = ["time", "site", "region", "spec_status", "caps", "verdict", "hit", "priced", "reviews",
            "review_cap_hit", "neg", "gaps", "positives", "secs", "rc", "run_id", "egress", "log"]
    # 列变更后不往旧文件追加（会错列），换新文件名
    n = 1
    while os.path.exists(out):
        with open(out, encoding="utf-8-sig") as f:
            if f.readline().strip().split(",") == cols:
                break
        n += 1
        out = f"data/sandbox/readiness_{stamp}_{n}.csv"
    new = not os.path.exists(out)
    for code, rc in dict.fromkeys(targets):
        if code not in specs:
            print(f"[SKIP] {code}: 无 retail spec")
            continue
        status = json.load(open(specs[code], encoding="utf-8")).get("status", "")
        if want_status and status not in want_status:
            print(f"[SKIP] {code}: spec.status={status}")
            continue
        if not rc:
            print(f"[SKIP] {code}: 不在任何区域")
            continue
        wait_for_memory()
        ok, info = egress_ok(os.environ.get("OVERSEAS_PROXY") or "http://127.0.0.1:7877")
        if not ok:
            print(f"[STOP] 代理出口不通（{info}），终止本批：请在 Clash 里换可用节点后重跑")
            return 3
        print(f"[RUN ] {code} ({rc}, {status}) 出口 {info} ...", flush=True)
        r = run_site(code, rc, specs[code], args.timeout)
        r["egress"] = info
        r["time"] = dt.datetime.now().strftime("%m-%d %H:%M")
        print(f"[{r['verdict']:9}] {code} hit={r.get('hit', '-')} priced={r.get('priced', '-')} "
              f"rev={r.get('reviews', '-')} neg={r.get('neg', '-')} {r.get('secs')}s | {r.get('gaps', '')}",
              flush=True)
        with open(out, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            if new:
                w.writeheader()
                new = False
            w.writerow(r)
        out_rows.append(r)
        if r["verdict"] == "ABORT":
            print("[STOP] 代理不通，终止本批")
            return 3
    print(f"[OUT] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
