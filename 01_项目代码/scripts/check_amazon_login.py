# -*- coding: utf-8 -*-
"""Amazon 登录态定期检测与自动刷新提示。

检查所有 Amazon 站点的登录态是否有效：
  1. state.json 是否存在
  2. 是否包含凭证 cookie（at-main/x-main/sess-at-main 等）
  3. 凭证 cookie 是否未过期

如果发现过期或缺失，输出提示命令。

用法:
    py -3.12 scripts/check_amazon_login.py [--db <db>]
    py -3.12 scripts/check_amazon_login.py --site amazon_us  # 只查某个站
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

# Amazon 站点列表
AMAZON_SITES = [
    "amazon_us", "amazon_ca", "amazon_uk", "amazon_de", "amazon_fr",
    "amazon_it", "amazon_es", "amazon_nl", "amazon_pl", "amazon_tr",
    "amazon_mx", "amazon_br", "amazon_au", "amazon_jp", "amazon_in",
    "amazon_ae", "amazon_sa", "amazon_sg",
]


def check_site(site_code: str, session_dir: str) -> dict:
    """检查某站点的登录态，返回状态字典。"""
    state_path = os.path.join(session_dir, f"{site_code}.state.json")
    result = {
        "site": site_code,
        "exists": False,
        "cookie_count": 0,
        "auth_cookies": [],
        "auth_expiry": None,
        "status": "missing",
        "message": "",
    }

    if not os.path.exists(state_path):
        result["message"] = f"无登录态文件"
        return result

    result["exists"] = True
    result["file_mtime"] = os.path.getmtime(state_path)

    try:
        with open(state_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        result["status"] = "corrupt"
        result["message"] = f"登录态文件损坏: {e}"
        return result

    cookies = data.get("cookies") or []
    result["cookie_count"] = len(cookies)

    # 检查凭证 cookie
    auth_cookies = []
    auth_expiry = None
    for c in cookies:
        name = str(c.get("name", ""))
        if name.startswith(("at-", "sess-at-", "x-")) and \
           not name.startswith(("at-a-glance", "x-amz")):
            auth_cookies.append(name)
            exp = c.get("expires", -1)
            if exp and exp > 0:
                if auth_expiry is None or exp < auth_expiry:
                    auth_expiry = exp

    result["auth_cookies"] = auth_cookies
    result["auth_expiry"] = auth_expiry

    now = time.time()
    if not auth_cookies:
        result["status"] = "no_auth"
        result["message"] = "无凭证 cookie（at-main/x-main），可能未真正登录"
    elif auth_expiry and auth_expiry < now:
        result["status"] = "expired"
        result["message"] = (f"凭证 cookie 已过期"
                             f"（{time.strftime('%Y-%m-%d', time.localtime(auth_expiry))}）")
    elif auth_expiry:
        days_left = int((auth_expiry - now) / 86400)
        result["status"] = "valid"
        result["message"] = f"有效，还剩 {days_left} 天"
    else:
        result["status"] = "session_only"
        result["message"] = "只有会话级凭证，浏览器关闭后可能失效"

    return result


def main():
    ap = argparse.ArgumentParser(description="Amazon 登录态定期检测")
    ap.add_argument("--site", default="", help="只检查该站点")
    ap.add_argument("--session-dir", default="",
                    help="session 目录（默认 data/session/）")
    args = ap.parse_args()

    # 确定 session 目录
    session_dir = args.session_dir
    if not session_dir:
        # 默认相对脚本位置
        script_dir = os.path.dirname(os.path.abspath(__file__))
        session_dir = os.path.join(os.path.dirname(script_dir), "data", "session")
    session_dir = os.path.abspath(session_dir)

    sites = [args.site] if args.site else AMAZON_SITES

    print(f"=== Amazon 登录态检测 ({time.strftime('%Y-%m-%d %H:%M')}) ===")
    print(f"Session 目录: {session_dir}")
    print()

    need_refresh = []
    valid_count = 0

    for site in sites:
        r = check_site(site, session_dir)
        status_icon = {
            "valid": "✅",
            "session_only": "⚠️ ",
            "no_auth": "⚠️ ",
            "expired": "❌",
            "missing": "❌",
            "corrupt": "❌",
        }.get(r["status"], "?")

        auth_str = f"{len(r['auth_cookies'])}凭证" if r["auth_cookies"] else "无凭证"
        print(f"  {status_icon} {site:15s} {auth_str:10s}  {r['message']}")

        if r["status"] == "valid":
            valid_count += 1
        else:
            need_refresh.append(r)

    print()
    print(f"汇总: {valid_count} 有效, {len(need_refresh)} 需刷新")

    if need_refresh:
        print("\n需要刷新的站点：")
        for r in need_refresh:
            print(f"  py -3.12 -m overseas.cli login --site {r['site']} "
                  f"--profile  # {r['message']}")
        return 1  # 有需要刷新的站点
    return 0


if __name__ == "__main__":
    sys.exit(main())
