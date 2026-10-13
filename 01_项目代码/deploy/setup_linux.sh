#!/usr/bin/env bash
# 海外采集框架 · Linux 环境准备与自检（幂等，可重复执行）
#
# 用法：
#   cd /home/hisense/pro/overseas
#   bash deploy/setup_linux.sh
#
# 做的事：venv → 依赖 → 离线 Chrome → 数据库初始化 → 站点注册自检 → 网络连通性自检

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/venv/bin/python"
BROWSER_DIR="$ROOT/.browser"
CHROME="$BROWSER_DIR/chrome-linux64/chrome"

ok()   { echo "  [ok]   $*"; }
warn() { echo "  [warn] $*"; }
fail() { echo "  [FAIL] $*"; }

echo "=== 0. 基本信息 ==="
echo "  项目目录: $ROOT"
command -v python3 >/dev/null 2>&1 || { fail "未找到 python3"; exit 1; }
echo "  python3 : $(python3 --version 2>&1)"

echo "=== 1. 虚拟环境 ==="
if [ ! -x "$PY" ]; then
    python3 -m venv venv || { fail "创建 venv 失败"; exit 1; }
    ok "已创建 venv"
else
    ok "venv 已存在"
fi

echo "=== 2. 依赖 ==="
"$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || warn "pip 升级跳过（可能无外网）"
if "$PY" -c "import playwright" >/dev/null 2>&1; then
    ok "playwright 已安装"
else
    warn "playwright 未安装，尝试安装（需要能访问 PyPI）"
    "$PY" -m pip install --quiet playwright && ok "playwright 安装完成" \
        || fail "playwright 安装失败：无外网时请用离线 wheel"
fi

echo "=== 3. 离线 Chrome ==="
# 服务器访问不了 cdn.playwright.dev，所以不执行 playwright install，改用离线包。
if [ -x "$CHROME" ]; then
    ok "离线 Chrome 已就绪: $CHROME"
else
    ZIP="$(ls "$ROOT"/../crawl4ai-main/Linux/浏览器安装包/chrome-linux64.zip 2>/dev/null | head -1 || true)"
    if [ -z "$ZIP" ]; then
        ZIP="$(ls "$ROOT"/浏览器安装包/chrome-linux64.zip 2>/dev/null | head -1 || true)"
    fi
    if [ -n "$ZIP" ] && [ -f "$ZIP" ]; then
        mkdir -p "$BROWSER_DIR"
        "$PY" -c "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])" "$ZIP" "$BROWSER_DIR" \
            && ok "已解压离线 Chrome" || fail "解压失败"
    else
        warn "未找到 chrome-linux64.zip，请手动放到 $ROOT/浏览器安装包/ 后重跑"
    fi
fi
if [ -f "$CHROME" ]; then
    chmod 755 "$CHROME" 2>/dev/null || true
    chmod 755 "$BROWSER_DIR/chrome-linux64/chrome_crashpad_handler" 2>/dev/null || true
    ok "已设置可执行权限（chrome 与 crashpad handler 都要）"
fi

echo "=== 4. 浏览器可启动性自检 ==="
if [ -x "$CHROME" ]; then
    OVERSEAS_BROWSER_EXECUTABLE="$CHROME" timeout 90 "$PY" - <<'PYEOF'
import os, sys
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("  [warn] playwright 未安装，跳过"); sys.exit(0)
exe = os.environ["OVERSEAS_BROWSER_EXECUTABLE"]
try:
    p = sync_playwright().start()
    # --no-sandbox 是服务器无头环境的关键，缺了会静默卡住
    b = p.chromium.launch(executable_path=exe, headless=True,
                          args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
    print(f"  [ok]   浏览器可启动，版本 {b.version}")
    b.close(); p.stop()
except Exception as e:
    print(f"  [FAIL] 浏览器启动失败: {type(e).__name__}: {e}")
    print("         缺系统库时执行: sudo $PY -m playwright install-deps chromium")
    sys.exit(1)
PYEOF
else
    warn "无离线 Chrome，跳过浏览器自检"
fi

echo "=== 5. 数据库初始化 ==="
"$PY" -m overseas.cli init-db && ok "数据库就绪" || fail "数据库初始化失败"

echo "=== 6. 站点插件注册自检 ==="
"$PY" -m overseas.cli sites || fail "站点注册异常"

echo "=== 7. 目标站点连通性自检 ==="
# 这一步最关键：服务器出网能力决定 L3 站点能不能用
for host in www.amazon.ca www.bestbuy.ca www.samsung.com; do
    if timeout 12 bash -c "</dev/tcp/$host/443" >/dev/null 2>&1; then
        ok "$host:443 可连"
    else
        warn "$host:443 不可连（需要出海代理，见 overseas.env 的 OVERSEAS_PROXY）"
    fi
done

echo
echo "=== 完成 ==="
echo "下一步："
echo "  1) cp deploy/overseas.env.example overseas.env  然后按实际填写（尤其 OVERSEAS_PROXY）"
echo "  2) $PY -m overseas.cli probe --site amazon_ca --url https://www.amazon.ca/dp/B0GPHMTMLC"
echo "  3) 安装定时任务见 部署说明.md 第 4 节"
