# -*- coding: utf-8 -*-
"""批次看门狗：由 Windows 计划任务每小时调用，保证 autofix / readiness 长批次跑完。

每次调用做三件事：
  1) 有批次进程在跑 → 不打扰，只刷新进度；
  2) 没有进程在跑、队列里还有未完成站点 → 先验代理出口（不通只告警、不启动），
     再把**剩余站点**作为新批次后台拉起（断点续跑：已有结果的站不重跑）；
  3) 写 data/sandbox/进度_latest.md（各队列任务剩余数、最新判定分布、价格可疑、异常）。

队列：data/sandbox/queue.json
  {"jobs": [{"id": "...", "kind": "autofix|readiness", "sites": [...], "created": "MM-DD HH:MM",
             "args": [...]}]}
「站点已完成」= 对应结果 CSV 里该站有一行，且时间 ≥ 任务创建时间。

用法：
  py -3.12 scripts/batch_watchdog.py                      # 计划任务调用（默认 run）
  py -3.12 scripts/batch_watchdog.py enqueue --kind readiness --region pe --region ec
  py -3.12 scripts/batch_watchdog.py enqueue --kind autofix --sites max_gt rodelag_pa
  py -3.12 scripts/batch_watchdog.py status
日志：data/sandbox/watchdog.log；批次输出：data/sandbox/wd_<id>.log
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SANDBOX = os.path.join(ROOT, "data", "sandbox")
QUEUE = os.path.join(SANDBOX, "queue.json")
REPORT = os.path.join(SANDBOX, "进度_latest.md")
LOG = os.path.join(SANDBOX, "watchdog.log")
PROXY = os.environ.get("OVERSEAS_PROXY") or "http://127.0.0.1:7877"
SCRIPTS = {"autofix": "scripts/autofix_search.py", "readiness": "scripts/readiness_check.py"}
RESULTS = {"autofix": "autofix_search_*.csv", "readiness": "readiness_*.csv"}


def now() -> str:
    return dt.datetime.now().strftime("%m-%d %H:%M")


def log(msg: str) -> None:
    os.makedirs(SANDBOX, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")


def load_queue() -> dict:
    if os.path.exists(QUEUE):
        return json.load(open(QUEUE, encoding="utf-8"))
    return {"jobs": []}


def save_queue(q: dict) -> None:
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=1)


def results(kind: str) -> list[dict]:
    rows = []
    for p in sorted(glob.glob(os.path.join(SANDBOX, RESULTS[kind]))):
        try:
            rows += list(csv.DictReader(open(p, encoding="utf-8-sig")))
        except Exception:  # noqa: BLE001
            continue
    return rows


RETRY_VERDICTS = {"ENV_ERROR", "ABORT"}       # 环境问题的结果不算完成，下一轮重跑


def remaining(job: dict) -> list[str]:
    latest = {}
    for r in results(job["kind"]):
        if (r.get("time") or "") >= job["created"]:
            latest[r.get("site")] = r
    done = {s for s, r in latest.items()
            if (r.get("verdict") or r.get("result") or "") not in RETRY_VERDICTS}
    return [s for s in job["sites"] if s not in done]


def batch_alive() -> list[str]:
    """正在跑的批次进程（命令行含 autofix_search / readiness_check）。"""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             # 计划任务用 pythonw 启动，子批次进程名也是 pythonw.exe——两种都要认
             "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\\.exe$' } | "
             "ForEach-Object { $_.CommandLine }"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
    except Exception:  # noqa: BLE001
        return []
    return [ln.strip() for ln in out.splitlines()
            if ("autofix_search.py" in ln or "readiness_check.py" in ln) and "--no-isolate" not in ln]


def resolve_sites(regions: list[str], sites: list[str]) -> list[str]:
    from overseas.regions_config import REGIONS
    from overseas.retail_spec import find_retail_spec
    out = list(sites)
    for rc in regions:
        reg = REGIONS.get(rc)
        if not reg:
            continue
        for r in reg.retail_sites:
            s = find_retail_spec(r.site) or {}
            if s.get("status") in ("approved", "candidate"):
                out.append(r.site)
    return list(dict.fromkeys(out))


def launch(job: dict, sites: list[str]) -> None:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("OVERSEAS_PROXY", PROXY)
    batch = [sys.executable, "-u", SCRIPTS[job["kind"]], "--sites", *sites, *job.get("args", [])]
    # 批次结束后立刻再调一次看门狗：队列里的下一个任务无缝接上，不用等下一个整点
    after = [sys.executable, "-u", os.path.join("scripts", "batch_watchdog.py"), "run"]
    cmd = ["cmd", "/c", subprocess.list2cmdline(batch) + " & " + subprocess.list2cmdline(after)] \
        if os.name == "nt" else ["sh", "-c", " ".join(batch) + " ; " + " ".join(after)]
    logf = open(os.path.join(SANDBOX, f"wd_{job['id']}.log"), "a", encoding="utf-8")
    logf.write(f"\n===== {now()} 启动 {len(sites)} 站 =====\n")
    logf.flush()
    flags = 0
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200 | 0x08000000   # DETACHED | NEW_GROUP | NO_WINDOW
    subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=logf, stderr=subprocess.STDOUT,
                     creationflags=flags, close_fds=True)
    log(f"launch {job['id']} {job['kind']} {len(sites)} 站：{' '.join(sites[:8])}{' …' if len(sites) > 8 else ''}")


def write_report(q: dict, alive: list[str], note: str) -> None:
    from overseas.price_sanity import check_prices  # noqa: F401  (保证模块可导入)
    L = [f"# 批次进度（{dt.datetime.now():%Y-%m-%d %H:%M}）\n",
         f"- 看门狗：{note}",
         f"- 运行中的批次进程：{len(alive)}"]
    for a in alive[:4]:
        L.append(f"  - `{a[:160]}`")
    L.append("\n## 队列\n")
    L.append("| 任务 | 类型 | 创建 | 站点数 | 剩余 |")
    L.append("|---|---|---|---|---|")
    for j in q["jobs"]:
        L.append(f"| {j['id']} | {j['kind']} | {j['created']} | {len(j['sites'])} | {len(remaining(j))} |")
    rd = {}
    for r in results("readiness"):
        rd[r["site"]] = r
    c = collections.Counter(r.get("verdict") for r in rd.values())
    L.append(f"\n## readiness 最新判定（{len(rd)} 站）\n")
    L.append("- " + "，".join(f"{k} {v}" for k, v in c.most_common()))
    L.append("- READY：" + " ".join(sorted(s for s, r in rd.items() if r.get("verdict") == "READY")))
    sus = [s for s, r in rd.items() if "价格可疑" in (r.get("gaps") or "")]
    if sus:
        L.append("- 价格可疑：" + " ".join(sorted(sus)))
    af = {}
    for r in results("autofix"):
        af[r["site"]] = r
    c2 = collections.Counter(r.get("result") for r in af.values())
    L.append(f"\n## autofix 最新结果（{len(af)} 站）\n")
    L.append("- " + "，".join(f"{k} {v}" for k, v in c2.most_common()))
    for k in ("FIXED", "FIXED_PRICE_SUSPECT", "TIMEOUT", "ERROR"):
        ss = sorted(s for s, r in af.items() if r.get("result") == k)
        if ss:
            L.append(f"- {k}：" + " ".join(ss))
    tail = open(LOG, encoding="utf-8").read().splitlines()[-8:] if os.path.exists(LOG) else []
    L.append("\n## 看门狗最近日志\n")
    L += [f"    {t}" for t in tail]
    open(REPORT, "w", encoding="utf-8").write("\n".join(L) + "\n")


def cmd_run() -> int:
    from readiness_check import egress_ok
    q = load_queue()
    alive = batch_alive()
    if alive:
        note = "批次进行中，未干预"
    else:
        pending = [(j, remaining(j)) for j in q["jobs"]]
        pending = [(j, r) for j, r in pending if r]
        if not pending:
            note = "队列已全部完成"
        else:
            from readiness_check import MIN_FREE_MB, free_memory_mb
            ok, info = egress_ok(PROXY)
            mem = free_memory_mb()
            if not ok:
                note = f"⚠ 代理出口不通（{info}），本轮不启动"
            elif mem < MIN_FREE_MB:
                note = f"⚠ 可用内存仅 {mem}MB < {MIN_FREE_MB}MB（浏览器会中途崩溃），本轮不启动"
            else:
                job, rem = pending[0]
                launch(job, rem)
                note = f"已续跑 {job['id']}（剩 {len(rem)} 站，出口 {info}）"
    write_report(q, alive, note)
    log(note)
    return 0


def cmd_enqueue(a) -> int:
    q = load_queue()
    sites = resolve_sites(a.region, a.sites)
    jid = a.id or f"{a.kind}_{dt.datetime.now():%m%d_%H%M}"
    args = ["--site-timeout", "900"] if a.kind == "autofix" else ["--timeout", "1200", "--status", "all"]
    q["jobs"].append({"id": jid, "kind": a.kind, "sites": sites, "created": now(), "args": args})
    save_queue(q)
    print(f"enqueued {jid}: {len(sites)} 站")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    e = sub.add_parser("enqueue")
    e.add_argument("--kind", choices=list(SCRIPTS), required=True)
    e.add_argument("--region", action="append", default=[])
    e.add_argument("--sites", nargs="*", default=[])
    e.add_argument("--id", default="")
    sub.add_parser("status")
    sub.add_parser("run")
    a = ap.parse_args()
    if a.cmd == "enqueue":
        return cmd_enqueue(a)
    if a.cmd == "status":
        q = load_queue()
        write_report(q, batch_alive(), "status 手动刷新")
        print(open(REPORT, encoding="utf-8").read())
        return 0
    return cmd_run()


if __name__ == "__main__":
    raise SystemExit(main())
