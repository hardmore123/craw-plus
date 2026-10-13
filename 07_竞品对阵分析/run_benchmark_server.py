# -*- coding: utf-8 -*-
"""竞品对阵分析服务一键启动脚本。
用法: py -3.12 启动竞品对阵分析.bat  或  python run_benchmark_server.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)
from overseas.benchmark_server import main
main()
