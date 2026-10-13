# -*- coding: utf-8 -*-
"""完成守望者：盯住当前 supervisor（PID 20048），其退出后自动重建全量导出。

背景：当前运行的 supervisor（PID 20048）是旧代码，没有"三站完成后自动
rebuild"逻辑（新逻辑已写入 supervisor_amazon_full.py 但尚未重启）。本进程
以 pythonw 脱离进程树运行，轮询监督进程；一旦 supervisor 退出（正常完成或
被外部终止），即执行 rebuild_amazon_csvs.py 从 DB 重建三站全量价格/网评导出。

- 若 supervisor 意外退出（三站未完）：先记录完成度，再照常重建已有数据
  （rebuild 幂等，只导出 DB 里已有的东西），方便拿部分成果。
- 若我用新代码重启 supervisor，本守望者只会盯新的 PID（改 WATCH_PIDS 再启）。

用法：
  pythonw scripts/watchdog_rebuild_amazon_full.py
日志：
  data/logs/watchdog_rebuild_amazon_full.log
"""
import ctypes
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

ROOT = r"C:\Users\likunyuan\Desktop\爬取项目\海外"
PYW = r"C:\Users\likunyuan\AppData\Local\Programs\Python\Python312\pythonw.exe"
LOGS = os.path.join(ROOT, "data", "logs")
WATCH_LOG = os.path.join(LOGS, "watchdog_rebuild_amazon_full.log")

WATCH_PIDS = [23748]     # 盯着的 supervisor 进程
POLL_SEC = 60            # 轮询间隔（秒）
REBUILD_WAIT = 15        # supervisor 退出后等 DB 释放的秒数

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
_kernel32 = ctypes.windll.kernel32


def pid_alive(pid: int) -> bool:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == STILL_ACTIVE
    finally:
        _kernel32.CloseHandle(handle)


def log(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        os.makedirs(LOGS, exist_ok=True)
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def db_done_counts() -> dict:
    """三站已到终态的型号数（记录 supervisor 退出时的进度）。"""
    counts = {}
    targets = [
        ("us", os.path.join(ROOT, "data", "overseas.db"), "amazon_us"),
        ("ca", os.path.join(ROOT, "data", "overseas.db"), "amazon_ca"),
        ("mx", os.path.join(ROOT, "data", "mx", "overseas_mx.db"), "amazon_mx"),
    ]
    terminal = ("ok", "no_price", "no_reviews", "no_item", "failed")
    ph = ",".join("?" * len(terminal))
    for region, db_path, site in targets:
        try:
            con = sqlite3.connect(db_path)
            try:
                n = con.execute(
                    "SELECT COUNT(DISTINCT model) FROM retail_task_status "
                    "WHERE site_code=? AND status IN (%s)" % ph,
                    [site, *terminal]).fetchone()[0]
                counts[region] = n
            finally:
                con.close()
        except Exception as e:
            counts[region] = "ERR:" + str(e)
    return counts


def run_rebuild() -> int:
    rebuild = os.path.join(ROOT, "scripts", "rebuild_amazon_csvs.py")
    if not os.path.exists(rebuild):
        log("rebuild_amazon_csvs.py 不存在，跳过")
        return -1
    cmd = [PYW, "-u", rebuild]
    log("RUN rebuild: " + " ".join(cmd))
    fout = None
    try:
        fout = open(os.path.join(LOGS, "rebuild_amazon_csvs.log"), "a",
                    encoding="utf-8", errors="replace", buffering=1)
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=fout, stderr=subprocess.STDOUT,
                             creationflags=subprocess.CREATE_NO_WINDOW
                             if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        return p.wait()
    except Exception as e:
        log("rebuild run error: %s" % e)
        return -1
    finally:
        if fout:
            fout.close()


def main() -> int:
    os.makedirs(LOGS, exist_ok=True)
    log("watchdog started. watching PID(s) %s ..." % WATCH_PIDS)
    waited_min = 0
    if not any(pid_alive(p) for p in WATCH_PIDS):
        log("WARNING: watched PID already gone at start — will rebuild once.")
    while any(pid_alive(p) for p in WATCH_PIDS):
        time.sleep(POLL_SEC)
        waited_min += POLL_SEC // 60
        if waited_min and waited_min % 30 == 0:
            log("still watching, %d min elapsed" % waited_min)

    log("watched supervisor exited. progress before rebuild: %s"
        % db_done_counts())
    time.sleep(REBUILD_WAIT)
    rc = run_rebuild()
    log("watchdog rebuild finished, exit=%s" % rc)
    log("final done counts: %s" % db_done_counts())
    return rc


if __name__ == "__main__":
    sys.exit(main())