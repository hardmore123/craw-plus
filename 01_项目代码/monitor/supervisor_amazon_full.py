# -*- coding: utf-8 -*-
"""Amazon 三站自动接力监督进程（US -> MX -> CA）。

特性：
- 完全脱离进程树运行（pythonw 启动），子进程同样不带新窗口。
- 自带断点续抓：每轮启动前读对应 DB 的任务状态表，把“未达终态”的型号
  生成剩余清单 CSV，只抓剩余部分；save_payload 本身幂等，重复抓不产生脏数据。
- 子进程退出码非 0（被外部杀死/异常）-> 自动重试该站（上限 MAX_ATTEMPTS），
  每次重试前 sleep 避让，避免疯狂重试打爆反爬。
- 完成判定：DB 中该站已到终态（ok/no_price/no_reviews/no_item）的型号数
  >= 清单总数。

用法：
  pythonw scripts/supervisor_amazon_full.py
日志：
  data/logs/supervisor_amazon_full.log
"""
import csv
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

ROOT   = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
PYW    = r"C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\pythonw.exe"
SCRIPT = os.path.join(ROOT, "scripts", "crawl_ca_retail.py")
LOGS   = os.path.join(ROOT, "data", "logs")
SUP_LOG = os.path.join(LOGS, "supervisor_amazon_full.log")
REMAIN = os.path.join(LOGS, "remaining")   # 剩余清单临时目录
MAX_ATTEMPTS = 8                           # 每站最多尝试轮数
# 已"定案"的状态：达到即不再为该型号发起新请求。
# ★ failed 也列入：某型号失败（超时/解析错）一次即跳过，不做无限重试避免死循环；
#   搜不到的型号（no_item）同样直接跳过，不空转。
TERMINAL  = {"ok", "no_price", "no_reviews", "no_item", "failed"}

ENV = dict(os.environ)
ENV["OVERSEAS_PROXY"] = "http://127.0.0.1:7877"
ENV["OVERSEAS_USE_PROFILE"] = "1"

STAGES = [
    dict(name="us", region="us", site="amazon_us",
         spec=os.path.join(ROOT, "docs", "retail_specs", "amazon_us.retail.json"),
         csv=os.path.join(ROOT, "data", "美国", "SPEC_型号汇总_US_20260914.csv"),
         db=os.path.join(ROOT, "data", "overseas.db"),
         log=os.path.join(LOGS, "amazon_us_full_20260920.log"),
         sample_ratio=None),   # US 已完成，不再抓
    dict(name="mx", region="mx", site="amazon_mx",
         spec=os.path.join(ROOT, "docs", "retail_specs", "amazon_mx.retail.json"),
         csv=os.path.join(ROOT, "data", "墨西哥", "SPEC_型号汇总_MX_20260915.csv"),
         db=os.path.join(ROOT, "data", "mx", "overseas_mx.db"),
         log=os.path.join(LOGS, "amazon_mx_full_20260920.log"),
         sample_ratio=None),   # MX 已过半, 让它跑完
    dict(name="ca", region="ca", site="amazon_ca",
         spec=os.path.join(ROOT, "docs", "retail_specs", "amazon_ca.retail.json"),
         csv=os.path.join(ROOT, "data", "加拿大", "SPEC_型号汇总_ca.csv"),
         db=os.path.join(ROOT, "data", "overseas.db"),
         log=os.path.join(LOGS, "amazon_ca_full_20260920.log"),
         sample_ratio=None),   # ★ 策略恢复：CA 跑全量 621（已定案 129 自动跳过）
]


def log(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(SUP_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def run_silent(cmd: list[str], logfile: str) -> int:
    """子进程静默运行（无窗口），stdout/stderr 追加到 logfile。返回退出码。"""
    fout = None
    try:
        fout = open(logfile, "a", encoding="utf-8", errors="replace", buffering=1)
        p = subprocess.Popen(cmd, cwd=ROOT, env=ENV,
                             stdout=fout, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        return p.wait()
    except Exception as e:
        log("run_silent error: %s" % e)
        return -1
    finally:
        if fout:
            fout.close()


def model_of(row: dict) -> str:
    return (row.get("model_raw") or "").strip().split(" | ")[0]


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def done_models(db_path: str, site: str) -> set[str]:
    """该站累计已到终态的型号集（跨 run 汇总，从任务状态表读）。"""
    placeholders = ",".join("?" * len(TERMINAL))
    try:
        con = sqlite3.connect(db_path)
        try:
            rows = con.execute(
                "SELECT DISTINCT model FROM retail_task_status "
                "WHERE site_code=? AND status IN (%s)" % placeholders,
                [site, *TERMINAL],
            ).fetchall()
            return {r[0] for r in rows if r[0]}
        finally:
            con.close()
    except Exception as e:
        log("done_models(%s) errored: %s" % (site, e))
        return set()


def write_remaining_csv(stage: dict, remaining: list[dict]) -> str:
    os.makedirs(REMAIN, exist_ok=True)
    out = os.path.join(REMAIN, "%s_remaining.csv" % stage["name"])
    fieldnames = list(remaining[0].keys()) if remaining else []
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if fieldnames:
            w.writeheader()
        w.writerows(remaining)
    return out


def run_one_round(stage: dict, remain_csv: str) -> int:
    """拉起一次 crawl_ca_retail，抓剩余清单，返回退出码。"""
    cmd = [PYW, "-u", SCRIPT,
           "--region", stage["region"],
           "--sites", stage["site"],
           "--spec", stage["spec"],
           "--save-db",
           "--models-csv", remain_csv]
    if stage["name"] in ("mx", "ca") and stage.get("db") != os.path.join(
            ROOT, "data", "overseas.db"):
        cmd += ["--db", stage["db"]]
    log("RUN %s: %s" % (stage["name"], " ".join(cmd)))
    fout = None
    try:
        fout = open(stage["log"], "a", encoding="utf-8", errors="replace", buffering=1)
        p = subprocess.Popen(cmd, cwd=ROOT, env=ENV,
                             stdout=fout, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        code = p.wait()
    except Exception as e:
        log("run_one_round error: %s" % e)
        code = -1
    finally:
        if fout:
            fout.close()
    log("EXIT %s code=%s" % (stage["name"], code))
    return code


def sample_rows(rows: list[dict], ratio: float | None) -> list[dict]:
    """等距抽样：保留序列上大致 ratio 比例的型号（含第 0 个）。

    None/>=1 = 全量。按行号 step = round(1/ratio) 取第 0、step、2*step... 个，
    保证均匀覆盖前端型号，同时显著减少总量（如 0.2 -> 621 → ~125）。
    """
    if not ratio or ratio >= 1.0:
        return rows
    step = max(1, int(round(1.0 / ratio)))
    return rows[::step]


def run_stage(stage: dict) -> dict:
    """执行单个站点，返回 {'done': bool, ...}。循环重试直到完成或超MAX_ATTEMPTS。"""
    full_all = read_csv(stage["csv"])
    full = sample_rows(full_all, stage.get("sample_ratio"))
    total = len(full)
    if stage.get("sample_ratio"):
        log("stage %s: CSV %d 型号 → 20%%抽样 %d 个（等距）" % (
            stage["name"], len(full_all), total))
    else:
        log("stage %s: total models in CSV = %d" % (stage["name"], total))

    for attempt in range(1, MAX_ATTEMPTS + 1):
        done = done_models(stage["db"], stage["site"])
        remaining = [r for r in full if model_of(r) not in done]
        if not remaining:
            log("%s: no remaining models (%d/%d). DONE." % (
                stage["name"], len(done), total))
            return {"done": True, "done_count": len(done), "total": total}
        log("%s attempt %d: %d/%d done, %d remaining" % (
            stage["name"], attempt, len(done), total, len(remaining)))
        remain_csv = write_remaining_csv(stage, remaining)
        code = run_one_round(stage, remain_csv)

        done = done_models(stage["db"], stage["site"])
        if len(done) >= total:
            log("%s COMPLETE after attempt %d: %d/%d" % (
                stage["name"], attempt, len(done), total))
            return {"done": True, "done_count": len(done), "total": total}
        if code == 0:
            # 退出码 0 但未达总数：可能中途被熔断/跳过，重试剩余
            log("%s: exit=0 but only %d/%d done; retry remaining" % (
                stage["name"], len(done), total))
        else:
            log("%s: attempt %d failed (exit=%s, done %d/%d), sleep 30s"
                % (stage["name"], attempt, code, len(done), total))
        time.sleep(30)

    log("%s: MAX_ATTEMPTS(%d) exceeded, final done=%d/%d" % (
        stage["name"], MAX_ATTEMPTS, len(done), total))
    return {"done": len(done) >= total, "done_count": len(done), "total": total}


def rebuild_exports() -> bool:
    """三站全部完成后，从 DB 重建全量价格/网评 CSV/XLSX。"""
    rebuild = os.path.join(ROOT, "scripts", "rebuild_amazon_csvs.py")
    if not os.path.exists(rebuild):
        log("rebuild_amazon_csvs.py 不存在，跳过导出重建")
        return False
    log(">>> rebuilding full CSV/XLSX exports from DB...")
    rc = run_silent([PYW, "-u", rebuild], os.path.join(LOGS, "rebuild_amazon_csvs.log"))
    log("rebuild finished, exit=%s" % rc)
    return rc == 0


def main() -> int:
    os.makedirs(REMAIN, exist_ok=True)
    log("supervisor started, %d stages: %s" % (len(STAGES),
                                                ", ".join(s["name"] for s in STAGES)))
    results = []
    for stage in STAGES:
        log(">>> stage: %s" % stage["name"])
        res = run_stage(stage)
        results.append((stage["name"], res))
        if not res["done"]:
            log("!!! %s NOT complete — stop relay" % stage["name"])
            break
        log("=== %s COMPLETE ===" % stage["name"])

    all_done = all(r[1]["done"] for r in results)
    if all_done:
        rebuild_exports()
    log("supervisor finished: %s" % results)
    return 0 if all_done else 1


if __name__ == "__main__":
    sys.exit(main())