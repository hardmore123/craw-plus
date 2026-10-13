@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   竞品对阵分析服务
echo   访问地址: http://127.0.0.1:8090/
echo ========================================
echo.
echo [AI 配置]
echo   xinghai-ultra 经本地转换代理 http://127.0.0.1:8082/v1 接入
echo   配置来源：DSH settings（.dsh/settings.yaml.imported）
echo   代理忽略客户端鉴权头，apiKey 用占位值即可
echo.
echo [启动中...]
py -3.12 run_benchmark_server.py --port 8090
pause
