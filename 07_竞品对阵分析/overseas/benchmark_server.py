# -*- coding: utf-8 -*-
"""竞品对阵分析后端服务：国家选择 → AI对阵推荐 → SPEC对比 → 雷达图 → AI结论。

依赖：overseas_v4_20260929.db 中已建 6 张表（dim_spec_parameter/dim_spec_item_map/
dim_product_model/fact_spec_value/dim_spec_normalization_map/fact_benchmark_comparison）。
AI 分析接入 xinghai-ultra（overseas.llm_client.LLMClient）。

启动：
    python -m overseas.benchmark_server                    # 127.0.0.1:8090
    python -m overseas.benchmark_server --port 8090 --cors "*"
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__, config

# ============================================================
# 区域配置（价格带阈值 + 货币）
# ============================================================
COUNTRIES = {
    # === 日本线 ===
    'JP': {'name': '日本', 'currency': 'JPY', 'flag': '🇯🇵', 'group': '日本',
           'bands': {55:{'入门':(0,100000),'中端':(100000,200000),'高端':(200000,350000),'旗舰':(350000,9e9)},
                     65:{'入门':(0,150000),'中端':(150000,300000),'高端':(300000,500000),'旗舰':(500000,9e9)},
                     75:{'入门':(0,200000),'中端':(200000,400000),'高端':(400000,600000),'旗舰':(600000,9e9)},
                     85:{'入门':(0,300000),'中端':(300000,500000),'高端':(500000,800000),'旗舰':(800000,9e9)}}},
    # === 北美线 ===
    'US': {'name': '美国', 'currency': 'USD', 'flag': '🇺🇸', 'group': '北美',
           'bands': {55:{'入门':(0,400),'中端':(400,900),'高端':(900,1800),'旗舰':(1800,9e9)},
                     65:{'入门':(0,600),'中端':(600,1200),'高端':(1200,2500),'旗舰':(2500,9e9)},
                     75:{'入门':(0,800),'中端':(800,1800),'高端':(1800,3500),'旗舰':(3500,9e9)},
                     85:{'入门':(0,1200),'中端':(1200,2500),'高端':(2500,5000),'旗舰':(5000,9e9)}}},
    'CA': {'name': '加拿大', 'currency': 'CAD', 'flag': '🇨🇦', 'group': '北美',
           'bands': {55:{'入门':(0,500),'中端':(500,1000),'高端':(1000,2000),'旗舰':(2000,9e9)},
                     65:{'入门':(0,700),'中端':(700,1400),'高端':(1400,3000),'旗舰':(3000,9e9)},
                     75:{'入门':(0,1000),'中端':(1000,2000),'高端':(2000,4000),'旗舰':(4000,9e9)},
                     85:{'入门':(0,1500),'中端':(1500,3000),'高端':(3000,6000),'旗舰':(6000,9e9)}}},
    'MX': {'name': '墨西哥', 'currency': 'MXN', 'flag': '🇲🇽', 'group': '北美',
           'bands': {55:{'入门':(0,8000),'中端':(8000,16000),'高端':(16000,32000),'旗舰':(32000,9e9)},
                     65:{'入门':(0,12000),'中端':(12000,24000),'高端':(24000,45000),'旗舰':(45000,9e9)},
                     75:{'入门':(0,18000),'中端':(18000,35000),'高端':(35000,60000),'旗舰':(60000,9e9)}}},
    # === 南美线 ===
    'CO': {'name': '哥伦比亚', 'currency': 'COP', 'flag': '🇨🇴', 'group': '南美',
           'bands': {55:{'入门':(0,1500000),'中端':(1500000,3000000),'高端':(3000000,5000000),'旗舰':(5000000,9e9)},
                     65:{'入门':(0,2500000),'中端':(2500000,5000000),'高端':(5000000,8000000),'旗舰':(8000000,9e9)},
                     75:{'入门':(0,3500000),'中端':(3500000,7000000),'高端':(7000000,12000000),'旗舰':(12000000,9e9)}}},
    'PE': {'name': '秘鲁', 'currency': 'PEN', 'flag': '🇵🇪', 'group': '南美',
           'bands': {55:{'入门':(0,1200),'中端':(1200,2500),'高端':(2500,4500),'旗舰':(4500,9e9)},
                     65:{'入门':(0,1800),'中端':(1800,3800),'高端':(3800,6500),'旗舰':(6500,9e9)},
                     75:{'入门':(0,2800),'中端':(2800,5500),'高端':(5500,9000),'旗舰':(9000,9e9)}}},
    'CL': {'name': '智利', 'currency': 'CLP', 'flag': '🇨🇱', 'group': '南美',
           'bands': {55:{'入门':(0,350000),'中端':(350000,700000),'高端':(700000,1200000),'旗舰':(1200000,9e9)},
                     65:{'入门':(0,550000),'中端':(550000,1100000),'高端':(1100000,1800000),'旗舰':(1800000,9e9)},
                     75:{'入门':(0,800000),'中端':(800000,1600000),'高端':(1600000,2800000),'旗舰':(2800000,9e9)}}},
    'GT': {'name': '危地马拉', 'currency': 'GTQ', 'flag': '🇬🇹', 'group': '南美',
           'bands': {55:{'入门':(0,2500),'中端':(2500,5000),'高端':(5000,9000),'旗舰':(9000,9e9)},
                     65:{'入门':(0,4000),'中端':(4000,8000),'高端':(8000,14000),'旗舰':(14000,9e9)},
                     75:{'入门':(0,6000),'中端':(6000,12000),'高端':(12000,20000),'旗舰':(20000,9e9)}}},
    'BO': {'name': '玻利维亚', 'currency': 'BOB', 'flag': '🇧🇴', 'group': '南美',
           'bands': {55:{'入门':(0,2000),'中端':(2000,4000),'高端':(4000,7000),'旗舰':(7000,9e9)},
                     65:{'入门':(0,3000),'中端':(3000,6000),'高端':(6000,10000),'旗舰':(10000,9e9)},
                     75:{'入门':(0,5000),'中端':(5000,9000),'高端':(9000,15000),'旗舰':(15000,9e9)}}},
    # === 欧洲线 ===
    'UK': {'name': '英国', 'currency': 'GBP', 'flag': '🇬🇧', 'group': '欧洲',
           'bands': {55:{'入门':(0,300),'中端':(300,700),'高端':(700,1400),'旗舰':(1400,9e9)},
                     65:{'入门':(0,500),'中端':(500,1000),'高端':(1000,2000),'旗舰':(2000,9e9)},
                     75:{'入门':(0,700),'中端':(700,1500),'高端':(1500,3000),'旗舰':(3000,9e9)}}},
    'EU': {'name': '欧洲(欧元区)', 'currency': 'EUR', 'flag': '🇪🇺', 'group': '欧洲',
           'bands': {55:{'入门':(0,400),'中端':(400,800),'高端':(800,1600),'旗舰':(1600,9e9)},
                     65:{'入门':(0,600),'中端':(600,1200),'高端':(1200,2400),'旗舰':(2400,9e9)},
                     75:{'入门':(0,800),'中端':(800,1800),'高端':(1800,3500),'旗舰':(3500,9e9)}}},
    'CH': {'name': '瑞士', 'currency': 'CHF', 'flag': '🇨🇭', 'group': '欧洲',
           'bands': {55:{'入门':(0,500),'中端':(500,1000),'高端':(1000,2000),'旗舰':(2000,9e9)},
                     65:{'入门':(0,800),'中端':(800,1500),'高端':(1500,3000),'旗舰':(3000,9e9)},
                     75:{'入门':(0,1200),'中端':(1200,2500),'高端':(2500,4500),'旗舰':(4500,9e9)}}},
    'SE': {'name': '瑞典', 'currency': 'SEK', 'flag': '🇸🇪', 'group': '欧洲',
           'bands': {55:{'入门':(0,5000),'中端':(5000,10000),'高端':(10000,18000),'旗舰':(18000,9e9)},
                     65:{'入门':(0,8000),'中端':(8000,15000),'高端':(15000,28000),'旗舰':(28000,9e9)},
                     75:{'入门':(0,12000),'中端':(12000,22000),'高端':(22000,40000),'旗舰':(40000,9e9)}}},
    'PL': {'name': '波兰', 'currency': 'PLN', 'flag': '🇵🇱', 'group': '欧洲',
           'bands': {55:{'入门':(0,2500),'中端':(2500,5000),'高端':(5000,9000),'旗舰':(9000,9e9)},
                     65:{'入门':(0,4000),'中端':(4000,8000),'高端':(8000,14000),'旗舰':(14000,9e9)},
                     75:{'入门':(0,6000),'中端':(6000,12000),'高端':(12000,20000),'旗舰':(20000,9e9)}}},
    'RS': {'name': '塞尔维亚', 'currency': 'RSD', 'flag': '🇷🇸', 'group': '欧洲',
           'bands': {55:{'入门':(0,40000),'中端':(40000,80000),'高端':(80000,140000),'旗舰':(140000,9e9)},
                     65:{'入门':(0,60000),'中端':(60000,120000),'高端':(120000,210000),'旗舰':(210000,9e9)},
                     75:{'入门':(0,90000),'中端':(90000,180000),'高端':(180000,300000),'旗舰':(300000,9e9)}}},
    'RO': {'name': '罗马尼亚', 'currency': 'RON', 'flag': '🇷🇴', 'group': '欧洲',
           'bands': {55:{'入门':(0,2000),'中端':(2000,4000),'高端':(4000,7000),'旗舰':(7000,9e9)},
                     65:{'入门':(0,3000),'中端':(3000,6000),'高端':(6000,11000),'旗舰':(11000,9e9)},
                     75:{'入门':(0,5000),'中端':(5000,9000),'高端':(9000,16000),'旗舰':(16000,9e9)}}},
    'NO': {'name': '挪威', 'currency': 'NOK', 'flag': '🇳🇴', 'group': '欧洲',
           'bands': {55:{'入门':(0,5000),'中端':(5000,10000),'高端':(10000,18000),'旗舰':(18000,9e9)},
                     65:{'入门':(0,8000),'中端':(8000,15000),'高端':(15000,28000),'旗舰':(28000,9e9)},
                     75:{'入门':(0,12000),'中端':(12000,22000),'高端':(22000,40000),'旗舰':(40000,9e9)}}},
    'DK': {'name': '丹麦', 'currency': 'DKK', 'flag': '🇩🇰', 'group': '欧洲',
           'bands': {55:{'入门':(0,4000),'中端':(4000,8000),'高端':(8000,14000),'旗舰':(14000,9e9)},
                     65:{'入门':(0,6000),'中端':(6000,12000),'高端':(12000,22000),'旗舰':(22000,9e9)},
                     75:{'入门':(0,9000),'中端':(9000,18000),'高端':(18000,32000),'旗舰':(32000,9e9)}}},
    'BG': {'name': '保加利亚', 'currency': 'BGN', 'flag': '🇧🇬', 'group': '欧洲',
           'bands': {55:{'入门':(0,1500),'中端':(1500,3000),'高端':(3000,5500),'旗舰':(5500,9e9)},
                     65:{'入门':(0,2500),'中端':(2500,5000),'高端':(5000,8500),'旗舰':(8500,9e9)},
                     75:{'入门':(0,4000),'中端':(4000,7500),'高端':(7500,13000),'旗舰':(13000,9e9)}}},
    'BA': {'name': '波黑', 'currency': 'BAM', 'flag': '🇧🇦', 'group': '欧洲',
           'bands': {55:{'入门':(0,1000),'中端':(1000,2000),'高端':(2000,3500),'旗舰':(3500,9e9)},
                     65:{'入门':(0,1500),'中端':(1500,3000),'高端':(3000,5500),'旗舰':(5500,9e9)},
                     75:{'入门':(0,2500),'中端':(2500,5000),'高端':(5000,8500),'旗舰':(8500,9e9)}}},
    'TR': {'name': '土耳其', 'currency': 'TRY', 'flag': '🇹🇷', 'group': '欧洲',
           'bands': {55:{'入门':(0,15000),'中端':(15000,30000),'高端':(30000,55000),'旗舰':(55000,9e9)},
                     65:{'入门':(0,25000),'中端':(25000,50000),'高端':(50000,90000),'旗舰':(90000,9e9)},
                     75:{'入门':(0,40000),'中端':(40000,80000),'高端':(80000,140000),'旗舰':(140000,9e9)}}},
}

DEFAULT_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "overseas.db")   # 唯一主库
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'benchmark_static')
SETTINGS = {'db': DEFAULT_DB, 'cors': ''}

PARAM_ORDER = ['PEAK_BRIGHTNESS','DIMMING_ZONES','REFRESH_RATE','CHIP','SYSTEM','GAMING',
               'COLOR_GAMUT','HDMI','SCREEN_SIZE','RESOLUTION','HDR','CONTRAST',
               'WIFI','BLUETOOTH','DOLBY_ATMOS','POWER_CONSUMPTION','WEIGHT','DIMENSIONS']
PARAM_NAMES_ZH = {
    'PEAK_BRIGHTNESS':'峰值亮度','DIMMING_ZONES':'分区控光','REFRESH_RATE':'刷新率','CHIP':'画质芯片',
    'SYSTEM':'智能系统','GAMING':'游戏特性','COLOR_GAMUT':'色域','HDMI':'HDMI 2.1',
    'SCREEN_SIZE':'屏幕尺寸','RESOLUTION':'分辨率','HDR':'HDR格式','CONTRAST':'对比度',
    'WIFI':'Wi-Fi','BLUETOOTH':'蓝牙','DOLBY_ATMOS':'杜比全景声',
    'POWER_CONSUMPTION':'功耗','WEIGHT':'重量','DIMENSIONS':'尺寸'
}
PARAM_CATEGORY = {
    'PEAK_BRIGHTNESS':'画质','DIMMING_ZONES':'画质','REFRESH_RATE':'画质','CHIP':'画质',
    'SYSTEM':'智能','GAMING':'游戏','COLOR_GAMUT':'画质','HDMI':'连接',
    'SCREEN_SIZE':'设计','RESOLUTION':'画质','HDR':'画质','CONTRAST':'画质',
    'WIFI':'连接','BLUETOOTH':'连接','DOLBY_ATMOS':'音质',
    'POWER_CONSUMPTION':'设计','WEIGHT':'设计','DIMENSIONS':'设计'
}
RADAR_DIMS = {'画质':['PEAK_BRIGHTNESS','DIMMING_ZONES','REFRESH_RATE','COLOR_GAMUT','HDR','CHIP','RESOLUTION','CONTRAST'],
              '音质':['DOLBY_ATMOS'],'智能':['SYSTEM'],'游戏':['GAMING','REFRESH_RATE','HDMI'],
              '连接':['HDMI','WIFI','BLUETOOTH'],'设计':['POWER_CONSUMPTION','SCREEN_SIZE','WEIGHT','DIMENSIONS']}


def _db():
    conn = sqlite3.connect(SETTINGS['db'])
    conn.row_factory = sqlite3.Row
    return conn


def _json(payload) -> bytes:
    return json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')


def infer_region(brand_raw):
    if not brand_raw: return None
    m = {'_jp':'JP','_ca':'CA','_us':'US','_mx':'MX','_pe':'PE','_co':'CO',
         '_cl':'CL','_uk':'UK','_ec':'EC','_bo':'BO'}
    for suf, reg in m.items():
        if brand_raw.endswith(suf): return reg
    return None


# ===== 规格值归一化显示（日文→简洁中文）=====
# 把冗长日文规格值转换为简洁规范的中文显示
_DISPLAY_NORMALIZE = {
    # ===== 最具体的规则放前面（避免被宽泛规则先匹配）=====

    # Sharp HDMI（含 3,840×2,160 字样，必须在分辨率规则前匹配）
    r'^(\d+)（3[,.]?840×2[,.]?160.*?eARC/ARC対応.*?）.*?入力3.*?4K120.*?VRR/ALLM.*': r'HDMI 2.1×\1口 (4K120Hz/eARC/VRR/ALLM)',
    r'^(\d+)（3[,.]?840×2[,.]?160.*?eARC/ARC対応.*?）.*?入力3.*?4K120.*?': r'HDMI 2.1×\1口 (4K120Hz/eARC)',
    r'^(\d+)（3[,.]?840×2[,.]?160.*?）.*?入力3.*?4K120.*?': r'HDMI 2.1×\1口 (4K120Hz)',
    r'^(\d+)（3[,.]?840.*?eARC.*?）.*': r'HDMI \1口 (eARC)',
    r'^【.*?】(\d+)（3[,.]?840.*?eARC.*?）.*': r'HDMI \1口 (eARC)',
    r'^【.*?】(\d+)（.*?）.*': r'HDMI \1口',
    # Sharp HDMI（2口 ARC，无4K）
    r'^(\d+)（1[,.]?080.*?ARC対応.*?）.*': r'HDMI \1口 (ARC)',
    r'^(\d+)（.*?ARC対応.*?）.*': r'HDMI \1口 (ARC)',
    # 海信/TCL HDMI
    r'HDMI\s*2\.1[×xX]\s*(\d+)\s*/\s*HDMI\s*2\.0[×xX]\s*(\d+)': r'HDMI 2.1×\1 / HDMI 2.0×\2',
    # TCL: 4個 (VRR/ALLM対応，HDMI1&HDMI2：最大4K 120Hz映像入力，HDMI3&HDMI4：最大4K 60Hz映像入力)
    r'^(\d+)個\s*\(VRR/ALLM.*?4K\s*(\d+)Hz.*?4K\s*(\d+)Hz.*': r'HDMI \1口 (HDMI2.1×2×\2Hz+HDMI2.0×2×\3Hz/VRR+ALLM)',
    r'^(\d+)個\s*\(VRR/ALLM.*': r'HDMI \1口 (VRR+ALLM)',
    # TCL: 3個 (2個Ver2.1/Ver2.0a、1個Ver2.0a/Ver1.4a) HDMIモードは…
    r'(\d+)個\s*\((\d+)個Ver2\.1.*?(\d+)個Ver2\.0.*?\).*': r'HDMI 2.1×\2 / HDMI 2.0×\3 (\1口)',
    r'(\d+)個\s*\((\d+)個Ver2\.1.*?\).*': r'HDMI 2.1×\2 / HDMI 2.0×\1',
    r'[○○]\((\d+)系統全て\)': r'\1口 HDMI',

    # 分辨率（Sharp HDMI 已在前面处理，这里只匹配纯分辨率值）
    r'^3[,.]?840\s*[×xX]\s*2[,.]?160.*': '4K (3840×2160)',
    r'^3840\s*[×xX]\s*2160.*': '4K (3840×2160)',
    r'(\d+)\s*[×xX]\s*(\d+)\s*\(4K\s*UHD\)': r'4K (\1×\2)',

    # 功耗：約239W（0.5W）→239W；260 W / ...→260W；410 W→410W
    r'約?([\d.]+)\s*W\s*[（(].*?[)）].*': r'\1W',
    r'^([\d.]+)\s*W\s*/.*': r'\1W',
    r'約([\d.]+)W.*': r'\1W',
    r'^([\d.]+)\s*W$': r'\1W',

    # 重量：①約28.5kg ②約23.5kg→28.5kg
    r'①約?([\d.]+)\s*kg.*': r'\1kg',
    r'約\s*([\d.]+)\s*kg.*': r'\1kg',

    # 尺寸：幅1428 x 高さ804 対角 1639(64.5")→142.8×80.4cm
    # 用 mm_to_cm 标记，在 _normalize_display 里特殊处理（提取数字/10转cm）
    r'幅\s*([\d,]+)\s*x\s*高さ\s*([\d,]+).*': r'mm_to_cm',
    # 松下 幅：1,453mm / 高さ：892mm / 奥行：303mm → 145.3×30.3×89.2cm
    r'テレビスタンド含む\s*/\s*幅：([\d,]+)mm\s*/\s*高さ：([\d,]+)mm\s*/\s*奥行：([\d,]+)mm.*': r'mm_to_cm',
    r'テレビスタンド含む\s*/\s*幅：([\d,]+)mm\s*/\s*高さ：([\d,]+)mm\s*/\s*対角：([\d,]+)mm.*': r'mm_to_cm',
    # 幅：1,453mm / 高さ：892mm / 奥行：303mm（松下其他格式）
    r'幅\s*([\d,]+)\s*[×xX]\s*奥行\s*([\d.]+)\s*[×xX]\s*高さ\s*([\d.]+).*': r'\1×\2×\3cm',
    r'①([\d.]+×[\d.]+×[\d.]+)cm.*': r'\1cm',

    # HDR
    r'.*HDR10\s*/\s*Dolby\s*Vision\s*IQ.*HLG.*': 'HDR10+HLG+Dolby Vision IQ',
    r'.*HDR10\s*/\s*Dolby\s*Vision.*HLG.*': 'HDR10+HLG+Dolby Vision',
    r'●（HDR10/HLG/Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    r'●（HDR10\s*/\s*Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    r'●\d+（HDR10/HLG/Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    r'HDR10/HLG/HDR10\+/HDR10\+Adaptive/Dolby\s*Vision/Dolby\s*Vision\s*IQ.*': 'HDR10+HLG+Dolby Vision',
    r'HDR10\+\+/HLG/DoblyVision.*': 'HDR10+HLG+Dolby Vision',
    r'HDR10\+/HLG/DoblyVision.*': 'HDR10+HLG+Dolby Vision',
    # HDR 统一格式：HDR10/HLG/Dolby VISION → HDR10+HLG+Dolby Vision
    r'HDR10/HLG/Dolby\s*VISION.*': 'HDR10+HLG+Dolby Vision',
    r'HDR10/HLG/Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    r'・HDR10\s*・\s*HLG\s*HDR\s*・\s*Dolby\s*Vision\s*・\s*HDR10\+.*': 'HDR10+HLG+Dolby Vision',
    r'・Dolby\s*VISION\s*IQ\s*・\s*HDR\s*10\s*・\s*HLG\s*HDR\s*・\s*HDR\s*10\+.*': 'HDR10+HLG+Dolby Vision IQ',
    r'HDR10\+/HLG/Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    r'HDR10\+/HLG/DolbyVision.*': 'HDR10+HLG+Dolby Vision',

    # 刷新率：REGZA/Sony 专用规则（必须在通用倍速规则前）
    r'●120Hz倍速（ゲームモード\s*(\d+)Hz\s*VRR対応）': r'120Hz/VRR \1Hz',
    r'●120Hz倍速（ゲームモード.*': '120Hz',
    r'●120Hz倍速': '120Hz',
    r'倍速駆動パネル/XR\s*OLED\s*モーション': '120Hz (XR OLED Motion)',
    r'倍速駆動パネル/XR\s*モーション\s*クラリティー': '120Hz (XR Motion Clarity)',
    r'Motionflow\s*XR\s*(\d+).*?Native\s*(\d+)Hz': r'Motionflow XR\1 (原生\2Hz)',
    # TCL 刷新率：倍速120Hz/４K VRR 288Hz(ゲームモード)
    r'倍速\s*(\d+)Hz[／/]\s*[４4]K\s*VRR\s*(\d+)Hz.*': r'\1Hz/VRR \2Hz',
    r'倍速[（(]([\d.]+)Hz[)）].*?VRR\s*([\d.]+)Hz.*': r'\1Hz/VRR \2Hz',
    r'標準速\s*(\d+)Hz.*': r'\1Hz',
    r'標準速度[（(](\d+)Hz[)）].*': r'\1Hz',
    r'倍速[（(]([\d.]+)Hz[)）].*': r'\1Hz',
    r'(\d+)Hz倍速.*': r'\1Hz',
    r'(\d+)Hz\s*倍速.*': r'\1Hz',

    # 音响功率
    r'^(\d+)W$': r'\1W',
    r'(\d+)W\(\d+W\+\d+W\).*': r'\1W',
    r'(\d+)W（\d+W\+\d+W）.*': r'\1W',

    # 屏幕尺寸
    r'(\d+)V型.*': r'\1寸',
    r'(\d+)\s*型.*': r'\1寸',

    # 背光/分区：直下式LED→直下式LED；Mini LED→Mini LED
    r'^液晶パネル（RGB\s*Mini\s*LED.*': 'RGB Mini LED',
    r'^液晶パネル（Mini\s*LED.*量子ドット.*': 'Mini LED量子点',
    r'^液晶パネル（Mini\s*LED.*': 'Mini LED',
    r'^液晶パネル$': 'LCD液晶',
    r'^有機ELパネル（QD-OLED）': 'QD-OLED',
    r'^有機ELパネル\(QD-OLED\)': 'QD-OLED',
    r'^有機ELパネル': 'OLED面板',
    r'^QD-OLED$': 'QD-OLED',
    r'^OLED$': 'OLED',
    r'^LCD\s*Mini\s*LED$': 'Mini LED',
    r'^LCD\s*LED$': 'LED直下式',
    r'^LCD$': 'LCD液晶',
    r'^Direct-LED$': '直下式LED',
    r'^RGB\s*LED$': 'RGB LED',
    r'Mini-LED\s*PRO.*': 'Mini LED PRO',
    # REGZA 分区控光（必须在通用 Mini LED 规则前）
    r'新開発\s*高輝度\s*ファイン\s*Mini\s*LED.*': 'Mini LED',
    r'新開発\s*レグザ専用高コントラスト.*': 'OLED',
    r'新開発\s*高コントラスト.*有機EL.*': 'OLED',
    r'新開発\s*Mini\s*LED.*': 'Mini LED',
    r'新開発\s*全面直下型.*': '全面直下式LED',
    r'新開発.*有機EL.*': 'OLED',
    r'Mini\s*LED.*': 'Mini LED',
    r'VA[×xX]\s*Mini\s*LED.*': 'Mini LED',
    # TCL REFRESH_RATE 误映射: VAパネル 直下型LEDバックライト → 不是刷新率
    r'VAパネル\s*直下型.*': '—',
    r'直下式LED.*': '直下式LED',
    r'直下型.*': '直下式LED',

    # 画质芯片
    r'HI-VIEW\s*AIエンジン\s*PRO.*': 'Hi-View AI引擎 PRO',
    r'HI-VIEW\s*AIエンジン.*': 'Hi-View AI引擎',
    r'Hi-View\s*AI\s*エンジン\s*PRO.*': 'Hi-View AI引擎 PRO',
    r'Hi-View\s*AI\s*エンジン.*': 'Hi-View AI引擎',
    r'Hi-View\s*エンジン\s*([A-Z]+)': r'Hi-View引擎 \1',
    r'Hi-View\s*エンジン.*': 'Hi-View引擎',
    r'AlgoエンジンPro.*': 'Algo引擎 Pro',
    r'Algo\s*エンジン.*': 'Algo引擎',
    r'AiPQ\s*Engine\s*Max\s*III.*': 'AIPQ Engine Max III',
    r'AiPQ\s*Engine\s*Max.*': 'AIPQ Engine Max',
    r'AiPQ\s*Engine.*': 'AIPQ Engine',
    r'AiPQ\s*プロセッサー.*': 'AiPQ处理器',
    r'IPQ\s*Engine.*': 'IPQ Engine',
    r'レグザエンジン\s*ZRα.*': 'REGZA引擎 ZRα',
    r'レグザエンジン\s*ZRⅡ.*': 'REGZA引擎 ZRⅡ',
    r'レグザエンジン\s*ZR.*': 'REGZA引擎 ZR',
    r'レグザエンジン\s*HR.*': 'REGZA引擎 HR',
    # Sharp 画质芯片：Medalist S6
    r'Medalist\s*S6.*': 'Medalist S6',
    r'Medalist\s*S5.*': 'Medalist S5',
    r'Medalist\s*S4.*': 'Medalist S4',

    # 色域：有り→支持；量子ドット→量子点
    r'Hi-QLED\s*量子ドット.*': 'QLED量子点',
    r'広色域量子ドット.*': '量子点广色域',
    # Sharp 色域：リッチカラーテクノロジー
    r'リッチカラー.*': 'Rich Color（广色域）',
    r'3次元カラーリマスターPRO.*': '3D色彩重塑PRO',
    r'3次元カラーリマスター.*': '3D色彩重塑',
    r'カラーリマスター.*': '色彩重塑',
    r'量子ドット.*': '量子点',
    r'広色域LED.*': '广色域LED',
    r'広色域.*': '广色域',

    # 游戏模式：Game Master/AMD FreeSync...→VRR+ALLM+FreeSync+DLG 240Hz
    r'.*Game\s*Master.*?FreeSync\s*Premium\s*Pro.*?DLG\s*(\d+)Hz.*': r'VRR+ALLM+FreeSync+DLG \1Hz',
    r'.*Game\s*Master.*?FreeSync\s*Premium\s*Pro.*': 'VRR+ALLM+FreeSync Premium Pro',
    r'.*Game\s*Master.*?FreeSync.*': 'VRR+ALLM+FreeSync',
    r'瞬速ゲームモード.*': '瞬速游戏模式',
    r'有機EL瞬速ゲームモード.*': 'OLED瞬速游戏模式',
    r'144Hz\s*ゲームモードPRO.*': '144Hz游戏模式PRO',
    r'VRR、ALLM、AMD\s*FreeSync\s*Premium.*': 'VRR+ALLM+FreeSync',
    # TCL HDMI 规则必须在 VRR/ALLM 通用规则前（否则 HDMI 值中的 VRR/ALLM 被先匹配）
    r'(\d+)個[（(]\s*最大4K60Hz.*?VRR/ALLM.*': r'HDMI \1口 (4K60Hz/VRR+ALLM)',
    r'(\d+)個[（(]\s*最大4K\d+Hz.*?VRR/ALLM.*': r'HDMI \1口 (4K120Hz/VRR+ALLM)',
    r'(\d+)個[（(]\s*最大4K60Hz.*': r'HDMI \1口 (4K60Hz)',
    r'(\d+)個[（(]\s*最大4K\d+Hz.*': r'HDMI \1口 (4K)',
    r'VRR/ALLM対応.*': 'VRR+ALLM',
    r'ゲーム機能.*': '支持',
    # Sharp GAMING: HDMI 2.1 (4K120Hz/VRR/ALLM/eARC) → 简化
    r'HDMI\s*2\.1.*4K120Hz.*VRR.*ALLM.*eARC.*': 'VRR+ALLM+4K120Hz (eARC)',
    r'HDMI\s*2\.1.*4K120Hz.*VRR.*ALLM.*': 'VRR+ALLM+4K120Hz',

    # 智能系统
    r'VIDAA.*': 'VIDAA',
    r'Google\s*TV.*': 'Google TV',
    r'Google\s*アシスト.*': 'Google TV',
    r'Android\s*TV.*': 'Android TV',
    r'Fire\s*TV.*': 'Fire TV',
    r'ビエラリンク.*': 'VIERA Link',
    r'VIERA\s*Link.*': 'VIERA Link',
    r'スマートスピーカー連携.*': '支持',

    # 杜比全景声
    r'Dolby\s*ATMOS.*': 'Dolby Atmos',
    r'Dolby\s*Atmos.*': 'Dolby Atmos',
    r'ドルビーアトモス.*': 'Dolby Atmos',
    r'Dolby\s*AUDIO.*': 'Dolby Audio',
    r'ドルビーオーディオ.*': 'Dolby Audio',
    r'DTS[:：]\s*X.*': 'DTS:X',
    r'高音質機能.*Dolby\s*Atmos.*': 'Dolby Atmos',
    r'高音質機能.*支持.*Dolby.*': 'Dolby Atmos',

    # Wi-Fi（REGZA/Sony 含●前缀的先匹配，在通用IEEE规则前）
    r'.*●\s*Wi-Fi6.*IEEE802\.11([a-z/]+).*': r'Wi-Fi 6 (802.11\1)',
    r'.*●\s*＊\d+（IEEE802\.11([a-z/]+)）.*': r'Wi-Fi 802.11\1',
    r'^-\s*※.*Wi-Fi.*': 'Wi-Fi支持',
    r'IEEE802\.11([a-z/]+)\s*※?\d*.*': r'Wi-Fi 802.11\1',
    r'IEEE802\.11([a-z/]+).*': r'Wi-Fi 802.11\1',
    r'Wi-Fi\s*802\.11([a-z/]+)\s*※?\d*.*': r'Wi-Fi 802.11\1',
    r'(\d+\.\d)G\+(\d+)G': r'双频 \1G+\2G',
    r'無線LAN内蔵.*': 'Wi-Fi内置',
    r'Wi-Fi内蔵.*': 'Wi-Fi内置',

    # 蓝牙
    r'Bluetooth内蔵.*': '支持',
    r'Bluetooth対応.*': '支持',
    r'ボイスアシスタント.*': '支持',
    r'AIボイスアシスタント.*': '支持',

    # REGZA 对比度
    r'RGB独立エリアコントロール.*': 'RGB独立分区控光',
    r'Mini\s*LED/エリアコントロールPRO.*': 'Mini LED分区控光PRO',
    r'Mini\s*LED/エリアコントロール.*': 'Mini LED分区控光',
    r'Mini\s*LEDエリアコントロールPRO.*': 'Mini LED分区控光PRO',
    r'リアルブラックエリアコントロールPRO.*': '真黑分区控光PRO',
    r'リアルブラックエリアコントロール.*': '真黑分区控光',
    r'ディープブラックコントロールPRO.*': '深黑控光PRO',
    r'ディープブラック.*': '深黑控光',
    # REGZA 分区控光（已移到通用Mini LED规则前，这里不重复）
    r'高コントラスト.*': '高对比度',
    r'4K\s*有機ELパネル.*': 'OLED',
    r'全面直下型\s*広色域.*LED.*': '全面直下式广色域LED',
    r'全面直下型LEDパネル.*': '全面直下式LED',
    r'全面直下型.*LED.*': '全面直下式LED',
    r'全面直下型.*': '全面直下式LED',
    r'除外項目': '—',
    r'直下型.*LED.*': '直下式LED',
    r'エッジ式LED.*': '侧入式LED',
    r'直下式LED.*': '直下式LED',
    r'4K液晶パネル.*': '4K液晶面板',
    r'直下型白色LED.*': '直下式白光LED',

    # ===== Sony 专用规则 =====
    # Sony 画质芯片：プロセッサー「XR」→XR处理器；高画質プロセッサー「HDR X1」→X1 HDR处理器
    r'プロセッサー「XR」': 'XR处理器',
    r'高画質プロセッサー「HDR\s*X1」': 'X1 HDR处理器',
    r'高画質プロセッサー.*': '画质处理器',
    
    # Sony 色域：トリルミナス→特丽魅彩
    r'RGB\s*トリルミナス\s*マックス': 'RGB特丽魅彩Max',
    r'XR\s*トリルミナス\s*マックス': 'XR特丽魅彩Max',
    r'XR\s*トリルミナス\s*プロ': 'XR特丽魅彩Pro',
    r'トリルミナス\s*プロ': '特丽魅彩Pro',
    
    # Sony 峰值亮度
    r'ルミナンス\s*ブースター\s*プロ.*?XR\s*コントラスト\s*ブースター\s*(\d+)': r'峰值增强Pro+对比度增强\1',
    r'ルミナンス\s*ブースター.*?XR\s*コントラスト\s*ブースター\s*(\d+)': r'峰值增强+对比度增强\1',
    r'ハイ\s*ピーク\s*ルミナンス.*?XR\s*コントラスト\s*ブースター\s*(\d+)': r'高峰值亮度+对比度增强\1',
    r'XR\s*コントラスト\s*ブースター\s*(\d+)': r'XR对比度增强\1',
    
    # Sony 分区控光（已在前面通用分区区块处理）
    
    # Sony 刷新率（已在前面通用刷新率区块处理）
    
    # Sony HDR（已在前面通用HDR区块处理）
    
    # Sony HDMI（长串输入信号列表→提取HDMI口数）
    r'^(\d+)\s*ea\s*\(.*eARC.*ALLM.*\)': r'HDMI \1口 (eARC/ALLM)',  # 4ea (supports 4K 120Hz, eARC, VRR, ALLM, QMS, QFT)
    r'^(\d+)\s*ea\s*\(.*': r'HDMI \1口',  # 3ea (supports eARC+ALLM)
    r'^(\d+)（.*eARC.*ALLM.*': r'HDMI \1口 (eARC/ALLM)',
    r'^(\d+)（.*eARC.*': r'HDMI \1口 (eARC)',
    r'eARC.*?ALLM.*': 'eARC+ALLM',
    r'^(\d+)（.*4K.*120.*': r'HDMI \1口 (4K120Hz)',
    # Sony HDMI: 输入信号长串（640x480...）→无法提取口数，显示"详见官网"
    r'^640[x×]480.*': '支持多分辨率输入',
    # Sony HDMI: 418 → 4口HDMI 2.1; Yes (eARC/ARC) → 支持(eARC/ARC)
    r'^Yes\s*\(eARC/ARC\).*': '支持 (eARC/ARC)',
    r'^Yes\s*\(eARC\s*HDMI\s*(\d+)\).*': r'支持 (eARC HDMI \1)',
    r'^eARC\s*\(HDMI\s*(\d+)\)$': r'eARC (HDMI \1)',  # LG: eARC (HDMI 2)
    r'^Yes$': '支持',
    r'^No$': '—',
    
    # Sony 尺寸/重量/功耗（系列共享值，提取当前型号的值，已在 _normalize_display 提取）
    # 尺寸提取后：144.7 x 83.2 x 5.8 → 144.7×83.2×5.8cm
    r'^([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)$': r'\1×\2×\3cm',
    # 功耗：248[0.5] → 248W（纯整数[小数]）；重量：24.9[26.3] → 24.9kg (含脚架26.3kg)（小数[小数]）
    r'^(\d+)\[([\d.]+)\]$': r'\1W',
    r'^([\d]+\.[\d.]+)\[([\d.]+)\]$': r'\1kg (含脚架\2kg)',
    r'^([\d]+\.[\d.]+)\[([\d.]+)\].*': r'\1kg (含脚架\2kg)',
    r'【.*?】([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+).*': r'\1×\2×\3cm',
    r'【.*?】([\d.]+)\[([\d.]+)\].*': r'\1kg (含脚架\2kg)',
    r'【.*?】(\d+)\s.*': r'\1W',
    r'^(\d+)（\d+\s*\+\s*\d+.*': r'\1W',
    
    # Sony 蓝牙/系统/游戏/杜比：●16/●17→支持（必须●后紧跟数字）
    r'^●\d+$': '支持',
    r'^●\d+（.*': '支持',
    
    # Sony Wi-Fi（已在前面通用Wi-Fi区块处理）

    # ===== REGZA 专用规则 =====
    # REGZA 杜比全景声（必须在通用●规则前）
    r'●（5\.1\.2ch対応）': 'Dolby Atmos (5.1.2ch)',
    
    # REGZA 画质芯片
    r'レグザエンジンZRα': 'REGZA引擎 ZRα',
    r'レグザエンジンZRⅡ': 'REGZA引擎 ZR II',
    r'レグザエンジンZR': 'REGZA引擎 ZR',
    r'レグザエンジンHR': 'REGZA引擎 HR',
    
    # REGZA HDMI（在通用HDMI规则前）
    r'(\d+)\(eARC/ARC＊\d+\s*\)': r'HDMI \1口 (eARC/ARC)',
    r'(\d+)\(eARC/ARC\)': r'HDMI \1口 (eARC/ARC)',
    r'(\d+)\(eARC/ARC＊\d+\)': r'HDMI \1口 (eARC/ARC)',
    r'eARC＊\d+、ALLM': 'eARC+ALLM',
    r'^ー$': '—',
    r'^＊$': '—',
    
    # REGZA HDR
    r'・HDR\s*10\+\s*ADAPTIVE.*Dolby\s*VISION\s*IQ.*HDR\s*10.*HLG.*': 'HDR10+Adaptive+Dolby Vision IQ+HLG',
    r'・Dolby\s*VISION\s*IQ.*HDR\s*10.*HLG.*HDR\s*10\+.*': 'HDR10+HLG+Dolby Vision IQ',
    r'・HDR10.*HLG.*Dolby\s*Vision.*HDR10\+.*': 'HDR10+HLG+Dolby Vision',
    r'・HDR\s*10\+.*Dolby\s*VISION.*HDR\s*10.*HLG.*': 'HDR10+HLG+Dolby Vision',
    
    # REGZA 色域
    r'広色域LED.*': '广色域LED',
    r'広色域量子ドット.*': '量子点广色域',
    r'3次元カラーリマスター.*': '3D色彩重塑',
    r'カラーリマスター.*': '色彩重塑',
    
    # REGZA 对比度
    r'RGB独立エリアコントロール.*': 'RGB独立分区控光',
    r'Mini\s*LED/エリアコントロールPRO': 'Mini LED分区控光PRO',
    r'Mini\s*LED/エリアコントロール': 'Mini LED分区控光',
    r'リアルブラックエリアコントロール': '真黑分区控光',
    
    # REGZA 分区控光
    r'除外項目': '—',
    r'全面直下型LED.*': '全面直下式LED',
    r'4K液晶パネル': '4K液晶面板',
    r'直下型LED.*': '直下式LED',
    
    # REGZA 游戏特性
    r'有機EL瞬速ゲームモード': 'OLED瞬速游戏模式',
    r'瞬速ゲームモード': '瞬速游戏模式',
    
    # REGZA Wi-Fi（已在前面通用Wi-Fi区块处理）
    
    # REGZA 智能系统
    r'^●\s*＊\d+$': '支持',
    
    # REGZA 尺寸/重量/功耗
    r'幅\s*([\d.]+)cm，高さ\s*([\d.]+)cm，奥行\s*([\d.]+)cm.*': r'\1×\2×\3cm',
    r'([\d.]+)cm[×x]([\d.]+)cm[×x]([\d.]+)cm.*': r'\1×\2×\3cm',
    # REGZA 重量：含脚架／本体 → 本体 (含脚架)
    r'^([\d.]+)kg／([\d.]+)kg$': r'\2kg (含脚架\1kg)',
    r'^([\d.]+)\s*kg／([\d.]+)\s*[Kk]g$': r'\2kg (含脚架\1kg)',
    # 功耗：205W（0.5W/14W）→205W
    r'(\d+)W[（(].*?[)）].*': r'\1W',
    r'(\d+)W\s*\(電源.*': r'\1W',
    
    # REGZA 峰值亮度
    r'^●$': '支持',
    
    # REGZA 分辨率
    r'3840×2160\s*\[4Kパネル\]': '4K (3840×2160)',
    r'1920×1080': '1080P (1920×1080)',
    r'1366\s*[×xX]\s*768': 'HD (1366×768)',
    r'1366×768': 'HD (1366×768)',
    
    # REGZA 屏幕尺寸（幅142.8cm，高さ80.4cm，対角163.9cm）
    r'幅\s*([\d.]+)\s*cm，高さ\s*([\d.]+)\s*cm，対角\s*([\d.]+)\s*cm': r'\1×\2cm (对角\3cm)',
    r'幅\s*([\d.]+)cm，高さ\s*([\d.]+)cm，対角\s*([\d.]+)cm': r'\1×\2cm (对角\3cm)',
    # REGZA 屏幕尺寸（142.8cm×80.4cm／163.9cm）
    r'([\d.]+)cm[×x]([\d.]+)cm／([\d.]+)cm': r'\1×\2cm (对角\3cm)',
    # Sharp 屏幕尺寸（142.8×80.4/163.9cm）
    r'([\d.]+)[×x]([\d.]+)\/([\d.]+)cm': r'\1×\2cm (对角\3cm)',

    # REGZA 尺寸：幅 144.6cm，高さ (低)86.5cm/(高)89.5cm，奥行 29.1cm
    r'幅\s*([\d.]+)\s*cm，高さ\s*\(低\)([\d.]+)\s*cm/\(高\)([\d.]+)\s*cm，奥行\s*([\d.]+)\s*cm': r'\1×\2×\4cm (高\3cm)',
    r'幅\s*([\d.]+)cm，高さ\s*\(低\)([\d.]+)cm/\(高\)([\d.]+)cm，奥行\s*([\d.]+)cm': r'\1×\2×\4cm (高\3cm)',
    # REGZA 尺寸：幅 122.6 cm，高さ 76.1 cm，奥行 28.7 cm
    r'幅\s*([\d.]+)\s*cm，高さ\s*([\d.]+)\s*cm，奥行\s*([\d.]+)\s*cm': r'\1×\2×\3cm',
    r'幅\s*([\d.]+)cm，高さ\s*([\d.]+)cm，奥行\s*([\d.]+)cm': r'\1×\2×\3cm',

    # TCL 尺寸：横 1428 ×高さ804 ×対角 1639 mm → 142.8×80.4cm (对角163.9cm)
    r'横\s*([\d]+)\s*[×xX]\s*高さ\s*([\d]+)\s*[×xX]\s*対角\s*([\d]+)\s*mm': r'mm_to_cm',
    r'横\s*([\d]+)\s*[×xX]\s*高さ\s*([\d]+)\s*[×xX]\s*対角\s*([\d]+)': r'mm_to_cm',
    # TCL 尺寸：幅1210 X 高さ680 X 対角1388（无空格）
    r'幅\s*([\d]+)\s*[Xx×]\s*高さ\s*([\d]+)\s*[Xx×]\s*対角\s*([\d]+).*': r'mm_to_cm',
    r'幅\s*([\d]+)\s*mm\s*[Xx×]\s*高さ\s*([\d]+)\s*mm\s*[Xx×]\s*対角\s*([\d]+)\s*mm.*': r'mm_to_cm',
    
    # ===== 补全归一化规则（审计发现） =====
    # REGZA 分区控光（已移到高コントラスト前，这里不重复）
    r'4K\s*有機ELパネル': 'OLED',
    r'全面直下型\s*広色域.*LED.*': '全面直下式广色域LED',
    # REGZA 色域（补充）
    r'3次元カラーリマスターPRO.*': '3D色彩重塑PRO',
    r'広色域量子ドット.*': '量子点广色域',
    # REGZA 对比度（补充）
    r'ディープブラックコントロールPRO.*': '深黑控光PRO',
    r'ディープブラック.*': '深黑控光',
    r'Mini\s*LEDエリアコントロールPRO.*': 'Mini LED分区控光PRO',
    
    # TCL 游戏特性（英文补充）
    r'Game\s*Mode/ALLM/VRR/DLG\s*(\d+)Hz.*': r'ALLM+VRR+DLG \1Hz',
    r'GameMode/ALLM/VRR.*': 'ALLM+VRR',
    r'Game\s*Mode/ALLM/VRR.*': 'ALLM+VRR',
    r'Game\s*Mode/ALLM.*': 'ALLM',
    r'Game\s*Mode': '游戏模式',
    # TCL 画质芯片（英文补充）
    r'AiPQ\s*Pro\s*Processor.*': 'AiPQ Pro处理器',
    r'AiPQ\s*Lite\s*Processor.*': 'AiPQ Lite处理器',
    r'AiPQ\s*PRO\s*PROCESSOR.*': 'AiPQ Pro处理器',
    # TCL 分辨率（英文）
    r'3840\s*x\s*2160.*4K\s*UHD.*': '4K (3840×2160)',
    r'1920\s*x\s*1080.*FHD.*': '1080P (1920×1080)',
    # TCL 峰值亮度（英文）
    r'High\s*HDR\s*Brightness\s*L(\d+)': r'高HDR亮度 L\1',
    # TCL HDMI（英文补充）
    r'4\s*HDMI\s*\(1\s*eARC\)': 'HDMI 4口 (1×eARC)',
    # TCL Wi-Fi（带空格/※）
    r'IEEE\s*802\.11([a-z/]+)\s*※?\d*.*': r'Wi-Fi 802.11\1',
    # TCL 重量（英文 lbs → kg）
    r'([\d.]+)\s*lbs': r'\1磅',
    # TCL QD-Mini LED
    r'QD-Mini\s*LED.*': 'QD-Mini LED',
    # TCL 游戏特性：Game Master/VRR/ALLM/ゲームアシスタント(DLG 240Hz)
    r'Game\s*Master/VRR/ALLM/.*?DLG\s*(\d+)Hz.*': r'VRR+ALLM+DLG \1Hz',
    r'Game\s*Master/VRR/ALLM.*?FreeSync.*?DLG\s*(\d+)Hz.*': r'VRR+ALLM+FreeSync+DLG \1Hz',
    r'Game\s*Master/VRR/ALLM.*?FreeSync.*': 'VRR+ALLM+FreeSync',
    # TCL HDMI 补充：2個（Ver2.1/Ver2.0a対応ｘ1個、Ver2.0a/1.4a対応ｘ1個）
    r'(\d+)個（Ver2\.1.*?ｘ(\d+)個.*?Ver2\.0.*?ｘ(\d+)個.*?': r'HDMI 2.1×\2 / HDMI 2.0×\3 (\1口)',
    r'(\d+)個（Ver2\.1.*?ｘ(\d+)個.*?': r'HDMI 2.1×\2 (\1口)',
    r'(\d+)個（Ver2\.1.*?(\d+)個.*?Ver2\.0.*?(\d+)個.*?': r'HDMI 2.1×\2+HDMI 2.0×\3 (\1口)',
    # TCL HDMI: 2個 (Ver2.0/Ver1.4) / 3個 (Ver2.0a/Ver1.4a)
    r'(\d+)個\s*\(Ver2\.0/Ver1\.4\)': r'HDMI 2.0×\1口',
    r'(\d+)個\s*\(Ver2\.0a/Ver1\.4a\)': r'HDMI 2.0×\1口',
    r'(\d+)個\s*\(Version\s*1\.4\).*': r'HDMI 1.4×\1口',
    r'HDMI\s*\(Version\s*1\.4a\)\s*x\s*(\d+)個.*': r'HDMI 1.4×\1口',
    r'Ver1\.4a入力.*?(\d+)\s*個.*': r'HDMI 1.4×\1口',
    # TCL HDMI: 1個 (φ3.5ミニジャック...) → 不是HDMI
    r'^1個\s*\(φ3\.5.*': '—',
    # TCL HDR: HDR10 ,HDR10+,HLG, Dolby Vision IQ,Dolby Vision Ga...
    r'HDR10\s*,\s*HDR10\+.*?HLG.*?Dolby\s*Vision\s*IQ.*?Dolby\s*Vision\s*Ga.*': 'HDR10+HLG+Dolby Vision IQ',
    r'HDR10\s*,\s*HDR10\+.*?HLG.*?Dolby\s*Vision.*': 'HDR10+HLG+Dolby Vision',
    # TCL 分辨率: 4K Ultra HD (3840 x 2160)
    r'4K\s*Ultra\s*HD.*3840\s*x\s*2160.*': '4K (3840×2160)',
    r'^パネル.*': '—',

    # REGZA HDR 补充：・Dolby VISION IQ ・HDR 10 ・HLG HDR
    r'・Dolby\s*VISION\s*IQ\s*・\s*HDR\s*10\s*・\s*HLG\s*HDR.*': 'HDR10+HLG+Dolby Vision IQ',
    r'・HDR\s*10\+\s*ADAPTIVE\s*・\s*Dolby\s*VISION\s*IQ.*': 'HDR10+HLG+Dolby Vision IQ',
    # Sony 峰值亮度补充
    r'XR\s*OLED\s*コントラスト\s*プロ.*': 'XR OLED对比度Pro',

    # Sharp 分辨率补充：1,920×1,080（2T-C43GE2）、1,366×768（...）→ 提取第一个
    r'^1[,.]?920\s*[×xX]\s*1[,.]?080.*': '1080P (1920×1080)',
    r'^1[,.]?366\s*[×xX]\s*768.*': 'HD (1366×768)',

    # 松下 HDMI 补充：－(HDCP1.4对应) → HDMI 1.4
    r'^－\(HDCP1\.4対応\)': 'HDMI 1.4',
    r'^－\(HDCP.*': '—',

    # ===== ●/○ 符号的 source_term 归一化（当 value_text 是符号时用 source_term） =====
    # BLUETOOTH: Bluetoothイヤホン//ヘッドホン/サウンドバー → 支持
    r'Bluetoothイヤホン.*': '支持',
    # CHIP: 映像エンジン/IPQエンジン 不是芯片名 → —
    r'^映像エンジン$': '—',
    r'^IPQエンジン$': 'AiPQ处理器',
    # COLOR_GAMUT: 量子点 LED → QLED量子点
    r'高画質機能.*量子点.*LED.*': 'QLED量子点',
    r'高画質機能.*QLED.*': 'QLED量子点',
    r'^広視野角$': '广视角',
    r'^色温度センサー$': '—',
    # GAMING: ゲームメニュー → 支持
    r'^ゲームメニュー$': '支持',
    # HDR: 高画質機能｜支持 HDR10/HLG → HDR10+HLG
    r'高画質機能.*支持\s*HDR10/HLG.*': 'HDR10+HLG',
    r'高画質機能.*HDR10.*HLG.*': 'HDR10+HLG',
    # PEAK_BRIGHTNESS: 明るさセンサー 不是峰值亮度 → —
    r'^明るさセンサー$': '—',
    # REFRESH_RATE: 倍速駆動(120Hz) / 倍速対応 → 120Hz
    r'倍速駆動\s*\(?(\d+)Hz\)?': r'\1Hz',
    r'^倍速対応$': '120Hz',
    # WIFI: 入力・出力｜内置 Wi-Fi → Wi-Fi内置
    r'入力・出力.*内置\s*Wi-Fi.*': 'Wi-Fi内置',
    # BLUETOOTH: Bluetooth対応/内蔵 → 支持（已有规则但补充）
    
    # 松下 分区控光
    r'VA[×x]\s*LED.*': 'VA LED',
    r'VA[×x]\s*Mini\s*LED.*': 'Mini LED',
    r'IPS[×x]\s*LED.*': 'IPS LED',
    r'IPSα\s*LED.*': 'IPSα LED',
    r'有機EL.*': 'OLED',
    # 松下 功耗：543 W / リモコン... → 543W
    r'([\d.]+)\s*W\s*/\s*リモコン.*': r'\1W',
    # 松下 HDMI：○(4系統全て) → 4口 HDMI
    r'[○◯]\((\d+)系統全て\)': r'\1口 HDMI',
    r'[○◯]\((\d+)系統.*\)': r'\1口 HDMI',
    # 松下 SYSTEM：○(ビエラリンクSelect) → 支持
    r'[○◯]\(ビエラリンク.*\)': '支持',
    # 松下 尺寸/重量：約 32.0kg → 32.0kg；約4.5kg(テレビスタンド含む) → 4.5kg(含脚架)
    r'約\s*([\d.]+)\s*kg\(テレビスタンド含む\)': r'\1kg (含脚架)',
    r'約\s*([\d.]+)\s*kg.*': r'\1kg',
    # 松下 屏幕：65V型 → 65寸（已在通用规则）
    # TCL 尺寸：1428×804mm → 142.8×80.4cm（mm→cm，在 _normalize_display 里特殊处理）
    # 松下 尺寸：1,453×303×892mm → 1453×303×892mm（先去逗号再转cm）
    r'^(\d{1,3}),(\d{3})×(\d{1,3}),?(\d{0,3})×(\d{1,3}),?(\d{0,3})mm$': r'mm_to_cm',
    r'^(\d{3,4})×(\d{3,4})×(\d{3,4})mm$': r'mm_to_cm',
    r'^(\d{3,4})×(\d{3,4})mm$': r'mm_to_cm',
    
    # 通用：●＊4 等带星号的支持标记
    r'^●＊\d+$': '支持',
    r'^●\s*＊\d+$': '支持',
    
    # 符号→支持
    r'^○$': '支持',
    r'^○\s*$': '支持',
    r'^○（.*': '支持',
    r'^●$': '支持',
    r'^●（.*': '支持',
    r'^有り$': '支持',
    r'^あり$': '支持',

    # ============================================================
    # 多区域扩展（英文/西班牙文/葡萄牙文）— 非 JP 品牌
    # ============================================================

    # --- SCREEN_SIZE (英寸→寸，cm→寸) ---
    r'^(\d+\.?\d*)"$': r'\1寸',
    r'^(\d+\.?\d*)\s*inch$': r'\1寸',
    r'^(\d+\.?\d*)\s*inches?$': r'\1寸',
    r'^(\d+\.?\d*)\s*pulgadas?$': r'\1寸',
    r'^(\d+)\s*V$': r'\1寸',  # TCL: 40V → 40寸
    # REGZA: 165.0cm× 92.8cm／ 189.3cm → 提取对角线 cm→寸
    r'^(\d+\.?\d*)cm×\s*(\d+\.?\d*)cm／\s*(\d+\.?\d*)cm$': lambda m: f'{float(m.group(3))/2.54:g}寸',
    r'^(\d+\.?\d*)\s*cm$': lambda m: f'{float(m.group(1))/2.54:g}寸',
    r'^(\d+\.?\d*)\s*cm\s*\((\d+\.?\d*)"$\)': r'\2寸',
    r'^(\d+\.?\d*)\s*\((\d+\.?\d*)"\)$': r'\2寸',
    r'^(\d+\.?\d*)"\s*\((\d+\.?\d*)"\)$': r'\1寸',
    r'^(\d+)\s*型$': r'\1寸',
    r'^Screen Size.*': '—',
    r'^Diagonal$': '—',
    r'^Pantalla$': '—',
    r'^Tamaño.*': '—',
    r'^Actual Screen Size.*': '—',
    r'^Display Size$': '—',
    r'^Display Diagonal$': '—',
    r'^Class Size$': '—',

    # --- RESOLUTION ---
    # 必须从最具体到最通用排列（避免嵌套替换）
    r'^4K\s*Ultra\s*HD\s*\(.*3,?840.*2,?160.*\)$': '4K UHD (3840×2160)',
    r'^4K\s*Ultra\s*HD.*3,?840.*2,?160.*$': '4K UHD (3840×2160)',
    r'^4K\s*UHD\s*\(3,?840.*2,?160.*\)$': '4K UHD (3840×2160)',
    r'^4K\s*UHD$': '4K UHD',
    r'^4K\s*Ultra\s*HD$': '4K UHD',
    r'^4K$': '4K UHD',
    r'^UHD$': '4K UHD',
    r'^3840\s*[x×]\s*2160$': '4K UHD (3840×2160)',
    r'^3,?8[46]0\s*[x×]\s*2,?1[68]0$': '4K UHD (3840×2160)',
    r'3840\s*[x×]\s*2160': '4K UHD (3840×2160)',
    r'1920\s*[x×]\s*1080.*': 'FHD (1920×1080)',
    r'1,?920\s*[x×]\s*1,?080.*': 'FHD (1920×1080)',
    r'1366\s*[x×]\s*768.*': 'HD (1366×768)',
    r'2560\s*[x×]\s*1440.*': '2K (2560×1440)',
    r'7680\s*[x×]\s*4320.*': '8K UHD (7680×4320)',
    r'^FHD$': 'FHD (1920×1080)',
    r'^Full HD$': 'FHD (1920×1080)',
    r'^HD$': 'HD',
    r'^8K$': '8K UHD',
    r'^Resolution$': '—',
    r'^Resolución$': '—',
    r'^Display Resolution$': '—',
    r'^Panel resolution$': '—',
    r'^Screen resolution$': '—',
    r'^Resolution type$': '—',
    r'^Resolución nativa$': '—',
    r'^Resolution Upscaler$': '—',

    # --- HDR (英文/西班牙文) ---
    r'Dolby Vision IQ.*HDR10\+.*HLG.*': 'Dolby Vision IQ+HDR10++HLG',
    r'Dolby Vision IQ.*HDR10.*HLG.*': 'Dolby Vision IQ+HDR10+HLG',
    r'Dolby Vision.*HDR10\+.*HLG.*': 'Dolby Vision+HDR10++HLG',
    r'Dolby Vision.*HDR10.*HLG.*': 'Dolby Vision+HDR10+HLG',
    r'Dolby Vision.*HDR10.*': 'Dolby Vision+HDR10',
    r'Dolby Vision.*HLG.*': 'Dolby Vision+HLG',
    r'^Dolby Vision$': 'Dolby Vision',
    r'HDR10\+.*HLG.*': 'HDR10++HLG',
    r'HDR10.*HLG.*': 'HDR10+HLG',
    r'^HDR10\+$': 'HDR10+',
    r'^HDR10$': 'HDR10',
    r'^HLG$': 'HLG',
    r'Active HDR.*HDR10.*HLG.*': 'HDR10+HLG (Active HDR)',
    r'Cinema HDR.*Dolby Vision.*': 'Dolby Vision+HDR10+HLG',
    r'^HDR$': '—',
    r'^HDR\(.*': '—',
    r'^Formatos HDR$': '—',
    r'^Auto HDR.*': '—',
    r'^AI HDR.*': '—',
    r'^Compatible with HDR.*': '—',
    r'^HDR Brightness Optimizer$': '—',
    r'^HDR Remaster$': '—',
    # 西语 HDR 字段名/状态值
    r'^Soporte$': '支持',
    r'^Apoyo$': '支持',
    r'^OLED HDR.*': 'OLED HDR',
    r'^Neo Quantum HDR.*': 'Neo Quantum HDR',
    r'^NQ HDR.*': 'NQ HDR',
    r'^Micro RGB HDR\+.*': 'Micro RGB HDR+',
    r'^HDR10\+$': 'HDR10+',
    r'^HDR10$': 'HDR10',
    r'^HLG$': 'HLG',

    # --- HDMI ---
    r'(\d+)\s*[x×]\s*2\.1.*2\.0.*': r'HDMI 2.1×\1 / HDMI 2.0',
    r'(\d+)\s*x\s*HDMI\s*2\.1.*(\d+)\s*x\s*HDMI\s*2\.0.*': r'HDMI 2.1×\1 / HDMI 2.0×\2',
    r'(\d+)\s*x\s*HDMI2\.1\+(\d+)\s*x\s*HDMI2\.0.*': r'HDMI 2.1×\1+HDMI 2.0×\2',
    r'^(\d+)\s*\(\s*1\s*eARC\s*\).*': r'HDMI \1口 (1×eARC)',
    r'^(\d+)\s*\(\s*1\s*ARC\s*\).*': r'HDMI \1口 (1×ARC)',
    r'^(\d+)\s*\(\s*\d\s*ARC\s*\).*': r'HDMI \1口 (ARC)',
    r'^(\d+)\s*\(\s*HDMI\s*1\.4\s*\).*': r'HDMI \1口 (HDMI 1.4)',
    r'^(\d+)\s*\(\s*Back\s*\).*': r'HDMI \1口',
    r'^(\d+)\s*ea$': r'HDMI \1口',
    r'^(\d+)\s*\(.*1\.4.*\).*': r'HDMI \1口 (HDMI 1.4)',
    r'^(\d+)\s*\(.*2\.0.*\).*': r'HDMI \1口 (HDMI 2.0)',
    r'^(\d+)\s*\(.*2\.1.*\).*': r'HDMI \1口 (HDMI 2.1)',
    r'^(\d+)\s*\(\s*\d\s*eARC\s*\).*': r'HDMI \1口 (eARC)',
    r'^(\d+)\s*\(.*eARC.*\).*': r'HDMI \1口 (eARC)',
    r'^(\d+)\s*\(.*ARC.*\).*': r'HDMI \1口 (ARC)',
    r'^HDMI$': '—',
    r'^HDMI Input.*': '—',
    r'^Entrada HDMI.*': '—',
    r'^Puertos HDMI$': '—',
    r'^Cable HDMI$': '—',
    r'^HDMI Version$': '—',
    r'^HDMI ARC$': '—',
    r'^eARC$': '支持 (eARC)',
    r'^ARC/eARC$': '支持 (eARC)',
    r'^Anynet.*': '支持 (HDMI-CEC)',
    r'^BRAVIA SYNC.*': '支持 (HDMI-CEC)',
    r'^EasyLink.*': '支持 (HDMI-CEC)',
    r'^Canal de [Rr]etorno.*': '支持 (eARC)',
    r'^120Hz 1080p HDMI.*': '—',
    # HDMI 无空格格式: HDMI2.1×4 → HDMI 2.1×4
    r'^HDMI(\d+\.\d+)[×xX](\d+)$': r'HDMI \1×\2',
    r'^HDMI(\d+\.\d+)[×xX](\d+)[×xX](\d+)$': r'HDMI \1×\2 / HDMI 2.0×\3',

    # --- REFRESH_RATE ---
    r'^(\d+)\s*Hz\s*\(.*up to\s*(\d+)\s*Hz.*\)': r'\1Hz (最高\2Hz)',
    r'^(\d+)\s*Hz\s*\(.*VRR\s*(\d+)\s*Hz.*\)': r'\1Hz (VRR最高\2Hz)',
    r'^(\d+)/(\d+)Hz$': r'\1/\2Hz',
    r'^(\d+)\s*Hz$': r'\1Hz',
    r'^(\d+)Hz$': r'\1Hz',
    r'^(\d+)\s*Hz\s*\(.*VRR.*\)': r'\1Hz (VRR)',
    r'^(\d+)\s*Hz\s*\(.*compatible.*VRR.*\)': r'\1Hz (VRR)',
    r'^(\d+)\s*Hz\s*\(.*hasta.*(\d+)\s*Hz.*\)': r'\1Hz (最高\2Hz)',
    r'^(\d+)\s*Hz\s*/\s*4K\s*(\d+)\s*Hz.*': r'\1Hz (VRR最高\2Hz)',
    r'^(\d+)Hz\(\s*Up to\s*(\d+)Hz\)': r'\1Hz (最高\2Hz)',
    r'^(\d+)Hz\(\s*Up to 4K\s*(\d+)Hz\)': r'\1Hz (VRR最高\2Hz)',
    r'^(\d+)Hz\(Up to 4K (\d+)Hz\)': r'\1Hz (VRR最高\2Hz)',
    r'^Sí\s*\(hasta\s*(\d+)\s*Hz\)$': r'\1Hz',  # 西班牙语 Sí (hasta 144Hz)
    r'^Sí\s*\(hasta\s*(\d+)Hz.*\)': r'\1Hz',
    r'^Refresh Rate$': '—',
    r'^Motion Rate$': '—',
    r'^Native Refresh Rate$': '—',
    r'^Motion enhancer.*': '—',
    r'^MOTION ENHANCER.*': '—',
    r'^Panel Refresh.*': '—',
    r'^PANEL REFRESH RATE$': '—',
    r'^PICTURE\(DISPLAY\) - Refresh Rate$': '—',
    r'^Frecuencia de.*': '—',
    r'^Fuente de alimentación.*': '—',
    r'^Power Supply.*': '—',
    r'^144Hz$': '144Hz',
    r'^144Hz Game Mode.*': '144Hz',
    r'^165Hz Game Mode.*': '165Hz',
    r'^120Hz Native.*': '120Hz',
    r'^60Hz Native.*': '60Hz',
    r'^(\d+)Hz\s*Native$': r'\1Hz',
    r'^Latest HDMI.*': '—',
    r'^Dolby Vision.*Gaming.*': '—',

    # --- PEAK_BRIGHTNESS ---
    r'^(\d[\d,.]*)\s*nits?\s*\(.*peak.*\)': r'\1 nits (峰值)',
    r'^(\d[\d,.]*)\s*nits?\s*\(.*pico.*\)': r'\1 nits (峰值)',
    r'^(\d[\d,.]*)\s*nit\s*\(.*pico.*\)': r'\1 nits (峰值)',
    r'^(\d[\d,.]*)\s*nit\s*\(.*típico.*\)': r'\1 nits (典型)',
    r'^(\d[\d,.]*)\s*nits?\s*\(.*típ.*\)': r'\1 nits (典型)',
    r'^(\d[\d,.]*)\s*nits?\s*\(.*típico.*\)': r'\1 nits (典型)',
    r'^(\d[\d,.]*)\s*nits?$': r'\1 nits',
    r'^(\d[\d,.]*)\s*nit$': r'\1 nits',
    r'^(\d[\d,.]*)\s*nits?\s*$': r'\1 nits',
    r'^(\d[\d,]*)\s*cd/m2.*': r'\1 nits',
    r'^(\d[\d,]*)\s*cd/m².*': r'\1 nits',
    r'^(\d[\d,.]*)nit\s*typical$': r'\1 nits (典型)',
    r'^(\d[\d,]*)nits$': r'\1 nits',
    r'^Brightness$': '—',
    r'^Peak Brightness$': '—',
    r'^Brillo$': '—',
    r'^Brillo del.*': '—',
    r'^Brillo.*nits.*': '—',
    r'^Brillo.*cd/m.*': '—',
    r'^Brillo 43.*': '—',
    r'^Brightness Booster$': '—',
    r'^Brightness uniformity.*': '—',
    r'^AI Brightness.*': '—',
    r'^Auto Brightness.*': '—',
    r'^Control.*Brillo.*': '—',
    r'^Compensación de brillo$': '—',
    r'^Ambient Mode Brightness.*': '—',
    r'^Luminosidad$': '—',
    r'^Luminance.*': '—',
    r'^Brightness Level$': '—',

    # --- CHIP ---
    r'^Cognitive Processor.*': 'Cognitive Processor XR',
    r'^4K HDR Processor X1.*': '4K HDR Processor X1',
    r'^4K Processor X1.*': '4K Processor X1',
    r'^Neural Quantum Processor.*': 'Neural Quantum Processor',
    r'^NQ\d*\s*AI\s*Gen(\d+)\s*Processor.*': r'NQ AI Gen\1',
    r'^NQ\d*\s*AI\s*Processor.*': 'NQ AI Processor',
    r'^NQ\d+\s*AI\s*Gen(\d+).*$': r'NQ AI Gen\1',
    r'^Q\d+\s*AI\s*Processor.*': 'Q4 AI',
    r'^Quantum Processor.*': 'Quantum Processor',
    r'^Micro RGB AI Engine.*': 'Micro RGB AI Engine',
    r'^Crystal Processor 4K$': 'Crystal Processor 4K',
    r'^Alpha\s*(\d+)\s*AI.*Gen(\d+)': r'Alpha \1 AI Gen\2',
    r'^Alpha\s*(\d+)\s*AI.*': r'Alpha \1 AI',
    r'^Alpha\s*(\d+).*': r'Alpha \1',
    r'^Procesador\s*α\s*(\d+)\s*AI.*Gen(\d+)': r'Alpha \1 AI Gen\2',  # 西班牙语
    r'^Procesador\s*α\s*(\d+).*': r'Alpha \1',  # 西班牙语
    r'^Pentonic.*': 'Pentonic',
    r'^AiPQ Pro Processor$': 'AiPQ Pro',
    r'^AiPQ.*': 'AiPQ',
    r'^AI PQ Engine$': 'AI PQ Engine',
    r'^AI Picture Pro$': 'AI Picture Pro',
    r'^IPQ Engine$': 'IPQ Engine',
    r'^Hi-View Engine$': 'Hi-View Engine',
    r'^MT9615.*': 'MT9615',
    r'^Realtek.*': 'Realtek',
    r'^CPU:.*GPU:.*': 'A73×4 @1.39GHz',
    r'^Processor$': '—',
    r'^PROCESSOR$': '—',
    r'^Picture [Pp]rocessor$': '—',
    r'^PICTURE PROCESSOR$': '—',
    r'^Picture Engine$': '—',
    r'^Motor de.*': '—',
    r'^Procesador$': '—',
    r'^Procesador de imagen$': '—',
    r'^4K Processor$': '—',
    r'^AI Processor$': '—',
    r'^Processor Type$': '—',

    # --- DIMMING_ZONES ---
    r'^4K QNED MiniLED$': 'QNED Mini LED',
    r'^4K QNED$': 'QNED',
    r'^4K OLED$': 'OLED',
    r'^4K UHD$': 'LED',
    r'.*[Qq]uantum.*[Mm]ini.*LED.*': 'Quantum Mini LED',
    r'.*Mini[-\s]*LED\s*PRO.*': 'Mini LED PRO',
    r'.*Mini[-\s]*LED\s*X.*': 'Mini LED X',
    r'.*Mini[-\s]*LED.*': 'Mini LED',
    r'.*MiniLED.*': 'Mini LED',
    r'^Direct\s*\(Full Array Mini LED\)$': '直下式 Mini LED',
    r'^Direct\s*\(Full Array LED\)$': '直下式 LED',
    r'^Direct\s*LED$': '直下式 LED',
    r'^Direct-LED$': '直下式 LED',
    r'^Direct$': '直下式 LED',
    r'^Directa$': '直下式 LED',  # 西班牙语
    r'^Mini\s*RGB$': 'Mini RGB',  # LG Mini RGB backlight
    r'^Edge$': '侧入式 LED',
    r'^Edge lit$': '侧入式 LED',
    r'^Edge\s*lit$': '侧入式 LED',
    r'^Frame Dimming$': 'Frame Dimming',
    r'^Direc QD MINI-LED$': 'QD Mini LED',
    r'^Bendable Self-Lighting OLED.*': 'OLED',
    r'^Backlight$': '—',
    r'^Backlight Type.*': '—',
    r'^BACKLIGHT TYPE$': '—',
    r'^Backlight Dimming.*': '—',
    r'^BACKLIGHT DIMMING TYPE$': '—',
    r'^Backlight Source.*': '—',
    r'^Local Dimming.*': '—',
    r'^Dimming Technology$': '—',
    r'^Dimming Zones$': '—',
    r'^Contrast Control Zones.*': '—',
    r'^Dynamic Backlight.*': '—',
    r'^Display Backlight.*': '—',
    r'^Display Type$': '—',
    r'^Calidad de imagen$': '—',

    # --- SYSTEM ---
    r'^Google TV$': 'Google TV',
    r'^Android TV™$': 'Android TV',
    r'^Android TV$': 'Android TV',
    r'^Android\s*(\d+)$': r'Android \1',
    r'^Fire TV$': 'Fire TV',
    r'^Fire TV OS(\d+)$': r'Fire TV \1',
    r'^webOS$': 'webOS',
    r'^webOS\s*(\d+).*': r'webOS \1',
    r'^Tizen.*': 'Tizen',
    r'^VIDAA$': 'VIDAA',
    r'^VIDAA\s*(\d+).*': r'VIDAA \1',
    r'^Roku.*': 'Roku TV',
    r'^Smart TV$': '—',
    r'^Operating System$': '—',
    r'^OS$': '—',
    r'^Sistema [Oo]perativo.*': '—',
    r'^Sistema operacional$': '—',
    r'^Smart OS$': '—',
    r'^TV OS$': '—',
    r'^Smart Platform$': '—',
    r'^Smart TV Platform$': '—',
    r'^Plataforma$': '—',
    r'^Plataforma Smart TV$': '—',
    r'^Google$': '—',
    r'^SMART TV$': '—',
    r'^OPERATING SYSTEM$': '—',
    r'^ATSC.*': '—',

    # --- GAMING ---
    r'^(\d+)Hz Game Mode PRO$': r'Game Mode PRO \1Hz',
    r'^(\d+)Hz Game Mode Pro$': r'Game Mode PRO \1Hz',
    r'^(\d+)Hz Game Mode Ultra$': r'Game Mode ULTRA \1Hz',
    r'^(\d+)Hz Game Mode PLUS$': r'Game Mode PLUS \1Hz',
    r'^(\d+)Hz Game Mode Plus$': r'Game Mode PLUS \1Hz',
    r'^(\d+)Hz Game Mode$': r'Game Mode \1Hz',
    r'^Game Mode$': '支持 (Game Mode)',
    r'^GAME MODE$': '支持 (Game Mode)',
    r'^Game Mode Plus$': 'Game Mode PLUS',
    r'^Auto Game Mode.*': 'ALLM',
    r'^AI Auto Game Mode$': 'ALLM',
    r'^ALLM$': 'ALLM',
    r'^Auto Low Latency Mode.*': 'ALLM',
    r'^AUTO LOW LATENCY MODE.*': 'ALLM',
    r'^VRR$': 'VRR',
    r'^Variable Refresh Rate.*': 'VRR',
    r'^AMD FreeSync Premium Pro$': 'FreeSync Premium Pro',
    r'^AMD FreeSync Premium$': 'FreeSync Premium',
    r'^AMD FreeSync$': 'FreeSync',
    r'^FreeSync Premium Pro$': 'FreeSync Premium Pro',
    r'^FreeSync Premium$': 'FreeSync Premium',
    r'^FreeSync$': 'FreeSync',
    r'^Freesync$': 'FreeSync',
    r'^Free-Sync Premium$': 'FreeSync Premium',
    r'^G-Sync.*': 'G-Sync',
    r'^Compatible con G-Sync.*': 'G-Sync',
    r'^Gaming Hub$': 'Gaming Hub',
    r'^Centro de juegos$': 'Gaming Hub',
    r'^Game Bar$': 'Game Bar',
    r'^Barra de juego$': 'Game Bar',
    r'^Juego$': '—',
    r'^Gaming$': '—',
    r'^Dolby Vision.*Gaming.*': '—',
    r'^Dolby Vision.*juegos.*': '—',
    r'^Dolby Gaming$': '—',
    r'^Compatible$': '支持',
    r'^4K 120Hz$': '4K 120Hz',
    r'^4K@120Hz$': '4K 120Hz',

    # --- COLOR_GAMUT ---
    r'^100% BT\.?2020.*': '100% BT.2020',
    r'^100% DCI-P3$': '100% DCI-P3',
    r'^100% Color Volume.*Quantum Dot.*': '100% Color Volume (QD)',
    r'^100% Color Volume$': '100% Color Volume',
    r'^100% Colour Volume.*': '100% Color Volume',
    r'^100% volumen de color.*Quantum Dot.*': '100% Color Volume (QD)',
    r'^100% volumen de color$': '100% Color Volume',
    r'^(\d+)%.*DCI-P3.*': r'\1% DCI-P3',
    r'^DCI-P3$': 'DCI-P3',
    r'^BT\.?2020$': 'BT.2020',
    r'^Dynamic Crystal Color$': 'Dynamic Crystal Color',
    r'^Dynamic QNED Color Pro$': 'Dynamic QNED Color Pro',
    r'^Dynamic QNED Color.*': 'Dynamic QNED Color',
    r'^Quantum Dot$': 'Quantum Dot',
    r'^Quantum Dot NanoCell.*': 'Quantum Dot NanoCell',
    r'^Wide Color Gamut$': '广色域',
    r'^Wide Color Reference$': '广色域',
    r'^Color de Precisión Micro RGB 100$': 'Micro RGB 100',
    r'^Color de [Pp]recisión Micro RGB$': 'Micro RGB',
    r'^Color cristal dinámico$': 'Dynamic Crystal Color',
    r'^16\.7 Million.*8bit.*': '16.7M (8bit)',
    r'^Color$': '—',
    r'^Color Gamut$': '—',
    r'^Color Space$': '—',
    r'^Color Volume$': '—',
    r'^% color space coverage.*': '—',
    r'^Color Accuracy$': '—',
    r'^Color Consistency$': '—',
    r'^Color Fidelity$': '—',
    r'^Gamut de color$': '—',

    # --- WIFI ---
    r'^Si$': '支持',
    r'^Sí$': '支持',
    r'^No$': '不支持',
    r'^O$': '支持',
    r'802\.11\s*a/b/g/n/ac/ax.*': 'Wi-Fi 6E (802.11ax)',
    r'802\.11\s*a/b/g/n/ac.*': 'Wi-Fi 5 (802.11ac)',
    r'802\.11\s*a/b/g/n.*': 'Wi-Fi 4 (802.11n)',
    r'802\.11\s*ac.*': 'Wi-Fi 5 (802.11ac)',
    r'802\.11\s*ax.*': 'Wi-Fi 6 (802.11ax)',
    r'802\.11\s*n.*': 'Wi-Fi 4 (802.11n)',
    r'^Wi-?Fi\s*(\d+)([A-E]?)$': r'Wi-Fi \1\2',  # Wifi 5 → Wi-Fi 5
    r'^Wi-?Fi\s*(\d+[A-E]?)$': r'Wi-Fi \1',
    r'^2\.4 GHz/5 GHz$': '双频 (2.4/5GHz)',
    r'^2\.4G/5G$': '双频 (2.4/5GHz)',
    r'^Dual.*Wi-?Fi.*': '双频Wi-Fi',
    r'^Si\s*\(Wi-Fi\s*(\d+)\)$': r'支持 (Wi-Fi \1)',
    r'^Yes\s*\(Wi-Fi\s*(\d+)\)$': r'支持 (Wi-Fi \1)',
    r'^Yes\s*\(Wi-Fi\s*(\d+[A-E]?)\)$': r'支持 (Wi-Fi \1)',
    r'^〇$': '支持',
    r'^－$': '—',
    r'^Wi-Fi$': '—',
    r'^WiFi$': '—',
    r'^Wifi$': '—',
    r'^Wi-Fi:?$': '—',
    r'^Wi-Fi Directo$': '—',
    r'^WiFi Direct$': '—',
    r'^Wifi directo$': '—',
    r'^Wireless$': '—',
    r'^Wireless LAN$': '—',
    r'^Wireless connection$': '—',
    r'^Wireless Technology$': '—',
    r'^WI-FI FREQUENCY$': '—',
    r'^WI-FI STANDARD$': '—',
    r'^Wi-Fi/BT.*': '—',
    r'^Red inalámbrica$': '—',
    r'^Conexión inalámbrica$': '—',
    r'^Miracast.*': '—',
    r'^Wireless Dex$': '—',
    r'^Wi-Fi Built in$': '—',
    r'^Wi-Fi Standard$': '—',
    r'^Wireless built-in$': '—',

    # --- BLUETOOTH ---
    r'^BT\s*(\d+\.\d+)$': r'Bluetooth \1',
    r'^BTS\s*(\d+\.\d+)$': r'Bluetooth \1',
    r'^Bluetooth\s*(\d+\.\d+)$': r'Bluetooth \1',
    r'^Yes\s*\((\d+\.\d+)\)$': r'Bluetooth \1',
    r'^Yes\s*\(BT\s*(\d+\.\d+)\)$': r'Bluetooth \1',
    r'^Yes\s*\(v\.?\s*(\d+\.\d+)\)$': r'Bluetooth \1',
    r'^Yes\s*\(v\s*(\d+\.\d+)\)$': r'Bluetooth \1',
    r'^Sí\s*\(BT\s*(\d+\.\d+)\)$': r'Bluetooth \1',
    r'^Sí\s*\(BT\s*(\d+\.\d+)\s*.*\)$': r'Bluetooth \1',
    r'^Sí\s*\(v\.?\s*(\d+\.\d+)\)$': r'Bluetooth \1',  # Sí (v 5.3)
    r'^Sí\s*\(v\s*(\d+\.\d+)\s*.*\)$': r'Bluetooth \1',
    r'^Sí\s*\(reproducción.*\)$': '支持 (双向传输)',  # 西班牙语双向蓝牙
    r'^Sí\s*\(.*bidirecc.*\)$': '支持 (双向传输)',
    r'^Version\s*(\d+\.\d+).*': r'Bluetooth \1',
    r'^Yes$': '支持',
    r'^Sí$': '支持',
    r'^Bluetooth$': '支持',
    r'^Bluetooth:$': '—',
    r'^Bluetooth™$': '—',
    r'^Bluetooth®.*': '—',
    r'^BlueTooth$': '—',
    r'^Soporte Bluetooth$': '—',
    r'^BLUETOOTH PROFILE.*': '—',
    r'^Audio Bluetooth$': '—',
    r'^Conexión Bluetooth.*': '—',
    r'^Bluetooth version$': '—',
    r'^Bluetooth Low Energy$': '—',
    r'^Bluetooth de baja.*': '—',
    r'^Dual Audio.*': '—',

    # --- DOLBY_ATMOS ---
    r'^Dolby Atmos$': 'Dolby Atmos',
    r'^Dolby™ Audio, Dolby™ Atmos$': 'Dolby Atmos',
    r'^Dolby™ Audio$': 'Dolby Audio',
    r'^Dolby Audio$': 'Dolby Audio',
    r'^Dolby Audio, Dolby Atmos$': 'Dolby Atmos',
    r'^Dolby Atmos.*DTS.*': 'Dolby Atmos+DTS:X',
    r'^B&O.*Dolby Atmos.*': 'B&O Dolby Atmos',
    r'^(\d+)\s*ch$': r'\1声道',
    r'^(\d+\.\d+)\s*ch$': r'\1声道',
    r'^(\d+\.\d+)\s*Ch$': r'\1声道',
    r'^(\d+\.\d+)\.(\d+)Ch$': r'\1.\2声道',
    r'^Surround Sound$': '—',
    r'^Dolby Audio Format Support$': '—',
    r'^DOLBY AUDIO FORMAT SUPPORT$': '—',
    r'^Dolby Vision Atmos$': '—',

    # --- POWER_CONSUMPTION ---
    r'^(\d+)\s*W$': r'\1W',
    r'^(\d+)W$': r'\1W',
    r'^(\d+)\s*kWh/1000h$': r'\1kWh/1000h',
    r'^(\d+)\s*kWh/y$': r'\1kWh/年',
    r'^(\d+)kWh/y$': r'\1kWh/年',
    r'^0\.5\s*W$': '0.5W (待机)',
    r'^Power Consumption.*': '—',
    r'^POWER CONSUMPTION.*': '—',
    r'^Annual.*': '—',
    r'^ANNUAL.*': '—',
    r'^Energy Consumption.*': '—',
    r'^Consumo de.*': '—',
    r'^Consumo energ.*': '—',
    r'^Potencia$': '—',
    r'^Power Input.*': '—',
    r'^AC Power.*': '—',
    r'^Energy Star.*': '—',
    r'^Typical Power.*': '—',
    r'^Standby Power.*': '—',
    r'^Wattage$': '—',
    r'^Power consumption$': '—',

    # --- WEIGHT ---
    r'^(\d+\.?\d*)\s*kg$': r'\1kg',
    r'^(\d+\.?\d*)\s*kg\s*\|.*': r'\1kg',
    r'^(\d+\.?\d*)\s*\(\d+\.?\d*\)\s*[Kk]g$': r'\1kg',  # 6.3 (6.2) Kg → 6.3kg
    r'^(\d+\.?\d*)\s*lbs?\.?$': r'\1lbs',
    r'^(\d+\.?\d*)\s*lbs?\s*\|.*': r'\1lbs',
    r'^(\d+\.?\d*)\s*lb\s*\|.*': r'\1lbs',
    r'^Weight$': '—',
    r'^Weight \(.*': '—',
    r'^Weight without Stand.*': '—',
    r'^Weight with Stand.*': '—',
    r'^TV Weight.*': '—',
    r'^Product Weight.*': '—',
    r'^Peso$': '—',
    r'^Peso:?$': '—',
    r'^Peso Neto.*': '—',
    r'^Peso Bruto.*': '—',
    r'^Peso TV.*': '—',
    r'^Peso del.*': '—',
    r'^Packaging Weight.*': '—',
    r'^DIMENSIONS AND WEIGHTS - TV Weight.*': '—',
    r'^Product weight$': '—',

    # --- DIMENSIONS ---
    r'^(\d+\.?\d*)\s*[x×]\s*(\d+\.?\d*)\s*[x×]\s*(\d+\.?\d*)\s*mm$': r'mm_to_cm',
    r'^(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*mm$': r'mm_to_cm',
    r'^(\d+\.?\d*)\s*[x×]\s*(\d+\.?\d*)\s*[x×]\s*(\d+\.?\d*)\s*inch.*': r'\1×\2×\3英寸',
    r'^(\d+\.?\d*)"\s*x\s*(\d+\.?\d*)/(\d+\.?\d*)"\s*x\s*(\d+\.?\d*)"': r'\1×\2×\3英寸',
    r'^(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*inch\s*\|.*': r'\1×\2×\3英寸',
    r'^(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)$': r'\1×\2×\3cm',
    r'^(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*$': r'\1×\2×\3mm',
    r'^(\d+)\s*x\s*(\d+)\s*x\s*(\d+)\s*mm.*': r'\1×\2×\3mm',
    r'^(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*/.*': r'\1×\2×\3cm',
    r'^Dimensions$': '—',
    r'^Dimensions \(.*': '—',
    r'^Dimensiones.*': '—',
    r'^Medidas.*': '—',
    r'^Product Dimensions.*': '—',
    r'^VESA:.*': '—',  # VESA壁挂孔距，非产品尺寸
    r'^TV Dimensions.*': '—',
    r'^Dimension of TV.*': '—',
    r'^DIMENSION OF TV.*': '—',
    r'^Box dimensions.*': '—',
    r'^Carton Dimensions.*': '—',
    r'^Ajustar medida.*': '—',
    r'^Dimensões.*': '—',
    r'^Dimensiones y Peso$': '—',
    r'^DIMENSIONS AND WEIGHTS.*': '—',
    r'^Physical Dimensions.*': '—',
    r'^Set Dimensions.*': '—',
    r'^Size\(WxHxD\).*': '—',

    # --- CONTRAST ---
    r'^(\d[\d,]*):1\s*\(.*típico.*\)': r'\1:1 (典型)',
    r'^(\d[\d,]*):1\s*\(.*tipico.*\)': r'\1:1 (典型)',
    r'^(\d[\d,]*):1\s*\(.*typical.*\)': r'\1:1 (典型)',
    r'^(\d[\d,]*)\s*:1$': r'\1:1',
    r'^(\d[\d,]*):1$': r'\1:1',
    r'^1,000,000:1$': '1,000,000:1',
    r'^6000:01:00$': '6000:1',
    r'^Contrast$': '—',
    r'^Contrast Ratio.*': '—',
    r'^Contraste$': '—',
    r'^Contraste:?$': '—',
    r'^Relación de [Cc]ontraste.*': '—',
    r'^Ratio de contraste$': '—',
    r'^Contrast enhancement$': '—',
    r'^CONTRAST ENHANCEMENT$': '—',
    r'^Contrast Enhancer$': '—',
    r'^Dynamic Contrast.*': '—',
    r'^High Contrast$': '—',
    r'^Alto contraste$': '—',
    r'^Pixel Contrast.*': '—',
    r'^Mejorador de contraste$': '—',
    r'^Potenciador de [Cc]ontraste.*': '—',
    r'^Backlight system Contrast.*': '—',
}

def _normalize_display(raw, param_code, model_code=None):
    """把原始规格值归一化为简洁规范的显示文本。
    按规则顺序匹配，第一个命中的生效（规则已按优先级排列）。
    model_code: 可选，用于 Sony 系列共享值按当前型号提取。
    """
    if not raw:
        return '—'
    text = str(raw).strip()
    import re
    # 全角横线统一为半角 —（－→—）
    text = text.replace('－', '—')
    # Sony 系列共享值：【K-65XR50】24.9[26.0]... → 提取当前型号的值
    if model_code and '【' in text and model_code in text:
        # 尺寸格式：【K-65XR50】144.7 x 81.7 x 5.7[144.7 x 86.3 x 47.4...]
        m_dim = re.search(r'【' + re.escape(model_code) + r'】([\d.]+)\s*x\s*([\d.]+)\s*x\s*([\d.]+)', text)
        if m_dim:
            text = m_dim.group(1) + ' x ' + m_dim.group(2) + ' x ' + m_dim.group(3)
        else:
            # 重量/功耗格式：【K-65XR50】24.9[26.3]
            m = re.search(r'【' + re.escape(model_code) + r'】([\d.]+)(\[([\d.]+)\])?', text)
            if m:
                val = m.group(1)
                if m.group(3):
                    text = val + '[' + m.group(3) + ']'
                else:
                    text = val
    for pattern, replacement in _DISPLAY_NORMALIZE.items():
        try:
            if re.search(pattern, text, flags=re.I):
                if replacement == 'mm_to_cm':
                    # 特殊处理：mm→cm 转换（先去逗号）
                    import re as _re2
                    clean = text.replace(',', '')
                    # TCL 幅1428 x 高さ804 対角 1639(64.5") → 142.8×80.4cm
                    m = _re2.match(r'幅\s*(\d+)\s*x\s*高さ\s*(\d+).*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        return f'{w:g}×{h:g}cm'
                    # TCL 横1428 ×高さ804 ×対角1639 mm → 142.8×80.4cm (对角163.9cm)
                    m = _re2.match(r'横\s*(\d+)\s*[×xX]\s*高さ\s*(\d+)\s*[×xX]\s*対角\s*(\d+).*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        diag = int(m.group(3)) / 10
                        return f'{w:g}×{h:g}cm (对角{diag:g}cm)'
                    # TCL 幅698 mm X 高さ392 mm X 対角800 mm → 69.8×39.2cm (对角80.0cm)
                    m = _re2.match(r'幅\s*(\d+)\s*mm\s*[Xx×]\s*高さ\s*(\d+)\s*mm\s*[Xx×]\s*対角\s*(\d+)\s*mm.*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        diag = int(m.group(3)) / 10
                        return f'{w:g}×{h:g}cm (对角{diag:g}cm)'
                    # TCL 幅1210 X 高さ680 X 対角1388（无mm后缀）
                    m = _re2.match(r'幅\s*(\d+)\s*[Xx×]\s*高さ\s*(\d+)\s*[Xx×]\s*対角\s*(\d+).*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        diag = int(m.group(3)) / 10
                        return f'{w:g}×{h:g}cm (对角{diag:g}cm)'
                    # 松下 テレビスタンド含む / 幅：893mm / 高さ：557mm / 対角：224mm
                    m = _re2.match(r'テレビスタンド含む\s*/\s*幅：(\d+)mm\s*/\s*高さ：(\d+)mm\s*/\s*対角：(\d+)mm.*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        diag = int(m.group(3)) / 10
                        return f'{w:g}×{h:g}cm (对角{diag:g}cm)'
                    # 松下 テレビスタンド含む / 幅：1453mm / 高さ：892mm / 奥行：303mm → 145.3×30.3×89.2cm
                    m = _re2.match(r'テレビスタンド含む\s*/\s*幅：(\d+)mm\s*/\s*高さ：(\d+)mm\s*/\s*奥行：(\d+)mm.*', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        d = int(m.group(3)) / 10
                        return f'{w:g}×{d:g}×{h:g}cm'
                    # 通用三维 mm 格式（全角×或半角x）
                    m = _re2.match(r'^(\d{3,4})\s*[x×X]\s*(\d{3,4})\s*[x×X]\s*(\d{3,4})\s*mm$', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        d = int(m.group(3)) / 10
                        return f'{w:g}×{h:g}×{d:g}cm'
                    # 通用二维 mm 格式
                    m = _re2.match(r'^(\d{3,4})\s*[x×X]\s*(\d{3,4})\s*mm$', clean)
                    if m:
                        w = int(m.group(1)) / 10
                        h = int(m.group(2)) / 10
                        return f'{w:g}×{h:g}cm'
                    return text
                new = re.sub(pattern, replacement, text, flags=re.I)
                return new if len(new) <= 60 else new[:58] + '…'
        except re.error:
            pass
    # WEIGHT 参数的纯数字→加kg
    if param_code == 'WEIGHT' and re.match(r'^[\d.]+$', text):
        return text + 'kg'
    # HDMI 参数的纯数字→加"口"
    if param_code == 'HDMI' and re.match(r'^\d+$', text):
        return text + '口'
    # PEAK_BRIGHTNESS 参数的纯数字→加"nits"
    if param_code == 'PEAK_BRIGHTNESS' and re.match(r'^\d+$', text):
        return text + ' nits'
    # BLUETOOTH 参数的 x.y→加"Bluetooth "
    if param_code == 'BLUETOOTH' and re.match(r'^\d+\.\d+$', text):
        return 'Bluetooth ' + text
    # CONTRAST 参数的纯数字→加":1"
    if param_code == 'CONTRAST' and re.match(r'^\d[\d,]*$', text):
        return text + ':1'
    # SCREEN_SIZE 参数的纯数字→加"寸"
    if param_code == 'SCREEN_SIZE' and re.match(r'^\d+\.?\d*$', text):
        return text + '寸'
    # REFRESH_RATE 参数的纯数字→加"Hz"
    if param_code == 'REFRESH_RATE' and re.match(r'^\d+$', text):
        return text + 'Hz'
    if len(text) > 60:
        text = text[:58] + '…'
    return text


# ============================================================
# API 实现
# ============================================================

def api_countries():
    """返回可用国家列表（含大模块分组）"""
    return [{'code': k, 'name': v['name'], 'currency': v['currency'], 'flag': v['flag'],
             'group': v.get('group', '')}
            for k, v in COUNTRIES.items()]


def _region_filter(region):
    """根据 region 返回 dim_product_model 的 WHERE 条件片段 + 参数。

    策略：
    - JP: 竞品 brand_raw LIKE '%日本%' + 海信日本线（有 JPY 价格）
    - 非JP: 该区域货币有价格的型号（WHERE model_code IN (有该货币价格的型号)）
    """
    if region == 'JP':
        # 海信日本线型号（our_brand=1 且有 JPY 价格）
        hisense_jp = """model_code IN (
            SELECT DISTINCT p.model FROM product p
            JOIN price_snapshot ps ON ps.product_id=p.id
            WHERE p.brand LIKE '%isense%' AND ps.currency='JPY'
        )"""
        return f"(brand_raw LIKE '%日本%' OR ({hisense_jp}))", []
    # 非日本线：按货币过滤，只显示有该货币价格的型号
    currency = COUNTRIES.get(region, {}).get('currency', '')
    if currency:
        return f"""model_code IN (
            SELECT DISTINCT p.model FROM product p
            JOIN price_snapshot ps ON ps.product_id=p.id
            WHERE ps.currency=?
        )""", [currency]
    return "1=1", []


def api_sizes(region):
    """返回某区域可用尺寸列表 + 各尺寸型号数"""
    cur = COUNTRIES.get(region, {})
    currency = cur.get('currency', 'JPY')
    where, params = _region_filter(region)
    conn = _db()
    c = conn.cursor()
    c.execute(f"""SELECT size_inch, COUNT(*) FROM dim_product_model
                  WHERE size_inch IS NOT NULL AND {where}
                  GROUP BY size_inch ORDER BY size_inch""", params)
    sizes = []
    for r in c.fetchall():
        if r[0] in (19,24,32,40,42,43,48,50,55,58,65,75,77,85,98,100):
            sizes.append({'size': r[0], 'model_count': r[1]})
    conn.close()
    return {'region': region, 'currency': currency, 'sizes': sizes}


def api_models(region, size):
    """返回某区域某尺寸的所有型号 + 均价 + 价格带"""
    cur = COUNTRIES.get(region, {})
    currency = cur.get('currency', 'JPY')
    bands = cur.get('bands', {}).get(int(size), {})
    where, params = _region_filter(region)
    conn = _db()
    c = conn.cursor()
    c.execute(f"""SELECT model_id, brand, model_code, brand_raw, our_brand
                  FROM dim_product_model
                  WHERE size_inch=? AND model_code IS NOT NULL AND {where}
                  ORDER BY our_brand DESC, brand""", (int(size),) + tuple(params))
    models = []
    for r in c.fetchall():
        # 取均价（严格按货币过滤：region 指定时只取该货币，无则跳过）
        c2 = conn.cursor()
        c2.execute("""SELECT AVG(ps.price) FROM price_snapshot ps
                      JOIN product p ON p.id=ps.product_id
                      WHERE p.model=? AND ps.currency=?""", (r['model_code'], currency))
        price = c2.fetchone()[0]
        # 日本线严格只取 JPY 价格，无 JPY 则不显示该型号（缺价 > 错价）
        # 不再 fallback 到任意货币（之前会把 COP/PEN/USD/EUR 当 JPY 显示）
        if price is None:
            continue  # 确实无价格 → 跳过
        # 过滤脏数据型号名
        if not _is_valid_model_code(r['model_code']):
            continue
        band = None
        for b, (lo, hi) in bands.items():
            if lo <= price < hi: band = b; break
        models.append({'model_id': r['model_id'], 'brand': r['brand'], 'model_code': r['model_code'],
                       'price': int(price), 'price_band': band, 'our_brand': r['our_brand'],
                       'is_our': bool(r['our_brand'])})
    conn.close()
    return {'region': region, 'currency': currency, 'size': int(size), 'models': models}


def _is_valid_model_code(code):
    """过滤脏数据型号名：排除纯规格词(180HZ/60LED)和纯数字(38751)，保留真实型号(65U8R/65C855)"""
    if not code: return False
    code = str(code).strip()
    if len(code) < 4: return False
    import re
    # 纯数字 → 过滤
    if re.match(r'^\d+$', code): return False
    # "数字+2-3大写字母"且无更多字符 → 规格词(180HZ/60LED/4KHDR) → 过滤
    if re.match(r'^\d{2,4}[A-Z]{1,3}$', code): return False
    # 至少含1个字母
    if not any(c.isalpha() for c in code): return False
    return True


def api_ai_recommend(region, size):
    """AI 智能推荐对阵组合：选我方型号 + 按价格带分组推荐竞品同档型号"""
    data = api_models(region, size)
    models = data['models']
    # 过滤脏数据型号名
    models = [m for m in models if _is_valid_model_code(m['model_code'])]
    our = [m for m in models if m['is_our']]
    comps = [m for m in models if not m['is_our']]
    if not our:
        return {'error': '该区域该尺寸暂无海信型号', 'recommendations': []}
    recommendations = []
    # 优先选有 spec 数据的我方型号，按价格带分布均衡选3个
    our_sorted = sorted(our, key=lambda m: (m['price_band'] or 'z'))
    seen_bands = set()
    selected_our = []
    for o in our_sorted:
        b = o['price_band']
        if b not in seen_bands:
            selected_our.append(o)
            seen_bands.add(b)
        if len(selected_our) >= 3:
            break
    for o in selected_our:
        ob = o['price_band']
        same_band = [c for c in comps if c['price_band'] == ob and abs(c['price']-o['price'])/max(o['price'],1) < 2.0]
        if not same_band:
            same_band = sorted(comps, key=lambda c: abs(c['price']-o['price']))[:4]
        competitors = same_band[:4]
        recommendations.append({
            'our': o, 'competitors': competitors, 'price_band': ob,
            'reason': f'按价格带「{ob or "相近"}」匹配，我方¥{o["price"]:,} 对阵同档竞品'
        })
    return {'region': region, 'size': int(size), 'recommendations': recommendations}


def api_spec_compare(model_ids, region='JP'):
    """返回多个型号的 SPEC 归一化对比矩阵"""
    if not model_ids:
        return {'error': '未指定型号', 'spec_matrix': {}, 'models': []}
    conn = _db()
    c = conn.cursor()
    currency = COUNTRIES.get(region, {}).get('currency', 'JPY')
    # 取型号信息
    models = []
    for mid in model_ids:
        c.execute("SELECT model_id, brand, model_code, our_brand, size_inch FROM dim_product_model WHERE model_id=?", (mid,))
        r = c.fetchone()
        if r:
            # 取价（严格按 region 货币过滤，不 fallback）
            c2 = conn.cursor()
            c2.execute("""SELECT AVG(ps.price), ps.currency FROM price_snapshot ps
                          JOIN product p ON p.id=ps.product_id WHERE p.model=? AND ps.currency=?
                          GROUP BY ps.currency""", (r['model_code'], currency))
            pr = c2.fetchone()
            price_val = pr[0] if pr else None
            models.append({'model_id': r['model_id'], 'brand': r['brand'], 'model_code': r['model_code'],
                           'is_our': bool(r['our_brand']), 'size_inch': r['size_inch'],
                           'price': int(price_val) if price_val is not None else None,
                           'currency': currency if price_val is not None else None})
    # 取每个参数的值
    spec_matrix = {}
    for code in PARAM_ORDER:
        pid_row = c.execute("SELECT param_id, param_name, param_unit, is_numeric, higher_is_better FROM dim_spec_parameter WHERE param_code=?", (code,)).fetchone()
        if not pid_row: continue
        pid = pid_row[0]
        values = {}
        for m in models:
            c2 = conn.cursor()
            # 多条记录时取最优先：排除误匹配值 > 非●值 > ●值 > 数值，值越长越优先
            c2.execute("""SELECT value_text, value_numeric, source_term FROM fact_spec_value
                          WHERE model_id=? AND param_id=?
                          ORDER BY CASE WHEN value_text LIKE '%VIDAA Voice%' THEN 2
                                        WHEN value_text LIKE '%附属品%' THEN 2
                                        WHEN value_text LIKE '%取扱説明書%' THEN 2
                                        WHEN value_text LIKE '%音声操作%' THEN 2
                                        WHEN value_text LIKE '%语音操作%' THEN 2
                                        WHEN value_text LIKE '%ハンズフリー%' THEN 2
                                        WHEN value_text LIKE '%语音助手%' THEN 2
                                        WHEN value_text='●' THEN 1 ELSE 0 END,
                                   LENGTH(COALESCE(value_text,'')) DESC""", (m['model_id'], pid))
            v = c2.fetchone()
            if v and (v['value_text'] or v['value_numeric'] is not None):
                raw_text = v['value_text'] or str(v['value_numeric'])
                # 当值是 ●/○ 符号时，用 source_term（如 Google TV6）作为归一化输入
                if raw_text in ('●', '○', '◯', '〇', '◯'):
                    src = v['source_term'] or ''
                    if src:
                        # source_term 本身可能含日文，走归一化规则
                        display = _normalize_display(src, code, m['model_code'])
                        raw_text = src  # raw 也显示 source_term 便于追溯
                    else:
                        display = _normalize_display(raw_text, code, m['model_code'])
                else:
                    display = _normalize_display(raw_text, code, m['model_code'])
                # 数值型且显示文本只是纯数字 → 加单位
                if v['value_numeric'] is not None and pid_row[3] == 1:
                    unit = pid_row[2] or ''
                    if unit and display.replace('.', '').isdigit():
                        display = f"{display}{unit}"
                values[m['model_code']] = {
                    'display': display,
                    'numeric': v['value_numeric'],
                    'raw': raw_text
                }
            else:
                values[m['model_code']] = {'display': '—', 'raw': None}
        spec_matrix[code] = {
            'param_code': code, 'param_name': pid_row[1], 'param_name_zh': PARAM_NAMES_ZH.get(code, code),
            'param_unit': pid_row[2], 'is_numeric': pid_row[3], 'higher_is_better': pid_row[4],
            'category': PARAM_CATEGORY.get(code, ''), 'values': values
        }
    conn.close()
    return {'spec_matrix': spec_matrix, 'models': models}


def api_radar(model_ids):
    """返回多个型号的六维雷达图得分"""
    spec = api_spec_compare(model_ids)
    if 'error' in spec:
        return spec
    sm = spec['spec_matrix']
    models = spec['models']
    scores = {}
    for m in models:
        scores[m['model_code']] = {}
        for dim, params in RADAR_DIMS.items():
            total, cnt = 0, 0
            for code in params:
                p = sm.get(code)
                if not p: continue
                v = p['values'].get(m['model_code'], {})
                disp = v.get('display', '')
                score = 50
                # 文本特征评分
                if code == 'SYSTEM':
                    if 'VIDAA' in disp: score = 55
                    elif 'Google TV' in disp or 'Android' in disp: score = 80
                    elif 'Tizen' in disp or 'webOS' in disp: score = 78
                    elif disp and disp != '—': score = 70
                elif code == 'GAMING':
                    if 'FreeSync' in disp or '240Hz' in disp: score = 90
                    elif '144Hz' in disp: score = 85
                    elif 'Game' in disp or 'ゲーム' in disp: score = 72
                    elif disp and disp != '—': score = 65
                elif code == 'HDR':
                    if 'Dolby Vision' in disp and 'HDR10+' in disp: score = 88
                    elif 'Dolby Vision' in disp or 'HDR10+' in disp: score = 78
                    elif 'HDR' in disp: score = 68
                elif code == 'CHIP':
                    if 'XR' in disp or 'AI' in disp or 'PRO' in disp or 'Pro' in disp: score = 82
                    elif disp and disp != '—': score = 72
                elif code == 'COLOR_GAMUT':
                    if '量子' in disp or 'QLED' in disp or 'Quantum' in disp: score = 85
                    elif '色域' in disp or '%' in disp: score = 72
                elif code == 'DOLBY_ATMOS':
                    if 'Dolby Atmos' in disp or '支持' in disp: score = 80
                    elif disp and disp != '—': score = 60
                # 数值型相对评分
                if v.get('numeric') is not None and p.get('is_numeric') == 1:
                    all_nums = [p['values'][mm['model_code']].get('numeric') for mm in models]
                    all_nums = [x for x in all_nums if x is not None]
                    if len(all_nums) > 1:
                        mx, mn = max(all_nums), min(all_nums)
                        if mx > mn and p.get('higher_is_better') is not None:
                            hib = p['higher_is_better']
                            num = v['numeric']
                            score = 60 + 35 * ((num-mn)/(mx-mn) if hib == 1 else (mx-num)/(mx-mn))
                total += score; cnt += 1
            scores[m['model_code']][dim] = round(total/cnt) if cnt else 50
    return {'radar_dims': list(RADAR_DIMS.keys()), 'scores': scores, 'models': models}


def api_ai_analysis(model_ids, region=None):
    """接入 xinghai-ultra 生成 AI 对阵结论（优势/劣势/机会点）"""
    spec = api_spec_compare(model_ids, region or 'JP')
    radar = api_radar(model_ids)
    if 'error' in spec:
        return spec
    # 构造给 AI 的规格对比摘要
    models = spec['models']
    sm = spec['spec_matrix']
    our_model = next((m for m in models if m['is_our']), models[0] if models else None)
    summary_lines = []
    summary_lines.append(f"区域: {region or '未指定'}")
    for m in models:
        role = '我方(海信)' if m['is_our'] else '竞品'
        summary_lines.append(f"{role} {m['brand']} {m['model_code']} 价格{m.get('price','?')}{m.get('currency','')}")
    summary_lines.append("\n规格对比:")
    for code in PARAM_ORDER[:12]:
        p = sm.get(code)
        if not p: continue
        vals = []
        for m in models:
            v = p['values'].get(m['model_code'], {})
            vals.append(f"{m['model_code']}={v.get('display','—')}")
        summary_lines.append(f"  {p.get('param_name_zh',code)}: " + " | ".join(vals))
    summary = "\n".join(summary_lines)

    prompt = f"""你是电视产品竞品分析专家。基于以下规格对比数据，生成"我方(海信)"对阵竞品的结论。
要求输出 JSON（不要 markdown 代码块），格式:
{{
  "advantage_points": [{{"point":"...","evidence":"...","confidence":0.9}}],
  "disadvantage_points": [{{"point":"...","evidence":"...","confidence":0.85}}],
  "opportunity_points": [{{"point":"...","evidence":"...","confidence":0.8}}],
  "strategy_suggestion": "一句话策略建议"
}}
优势点：我方领先的参数（数值高/功能全）；劣势点：我方落后之处；机会点：可差异化或补位的市场机会。
每条要可溯源到具体参数或价格。置信度0-1。

规格对比数据:
{summary}
"""
    # 调用 xinghai-ultra
    try:
        from .llm_client import LLMClient, LLMUnavailable
    except ImportError:
        # llm_client 模块本身不可用 → 走兜底
        return {'ai_conclusion': _fallback_analysis(spec, radar, our_model),
                'model': 'xinghai-ultra（llm_client 不可用，规则兜底）',
                'fallback': True, 'summary': summary}
    try:
        client = LLMClient()
        if not client.configured:
            # 未配置 → 直接走兜底，不报错
            return {'ai_conclusion': _fallback_analysis(spec, radar, our_model),
                    'model': 'xinghai-ultra（未配置，规则兜底）',
                    'fallback': True, 'summary': summary,
                    'config_needed': '设置 OVERSEAS_XINGHAI_API_KEY / OVERSEAS_XINGHAI_USER_KEY / OVERSEAS_XINGHAI_BASE_URL 后即可调用 AI'}
        result_text = client.chat([{"role": "user", "content": prompt}], temperature=0.2, max_tokens=2048)
        # 解析 JSON（容错：去掉可能的 ```json 包裹）
        text = result_text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
        ai_result = json.loads(text)
        return {'ai_conclusion': ai_result, 'model': client.describe(), 'summary': summary}
    except LLMUnavailable as e:
        return {'error': f'xinghai-ultra 调用失败: {e}', 'summary': summary,
                'fallback': True,
                'ai_conclusion': _fallback_analysis(spec, radar, our_model)}
    except (json.JSONDecodeError, Exception) as e:
        return {'error': f'AI 返回解析失败: {e}', 'raw': result_text[:500] if 'result_text' in dir() else '',
                'summary': summary, 'fallback': True,
                'ai_conclusion': _fallback_analysis(spec, radar, our_model)}


def _fallback_analysis(spec, radar, our_model):
    """AI 不可用时的规则兜底结论"""
    if not our_model:
        return {'advantage_points': [], 'disadvantage_points': [], 'opportunity_points': []}
    adv, dis, opp = [], [], []
    models = spec['models']
    sm = spec['spec_matrix']
    # 价格对比
    our_price = our_model.get('price') or 0
    comp_prices = [m.get('price', 0) for m in models if not m['is_our']]
    if comp_prices and our_price:
        avg = sum(comp_prices)/len(comp_prices)
        if our_price < avg * 0.85:
            adv.append({'point': f'价格领先：¥{our_price:,} 低于竞品均价¥{int(avg):,}',
                        'evidence': '价格对比', 'confidence': 0.95})
        opp.append({'point': f'价格带卡位：¥{our_price:,} 价格带有差异化空间',
                    'evidence': '价格分布', 'confidence': 0.85})
    # 参数对比
    for code in ['REFRESH_RATE','GAMING','HDR']:
        p = sm.get(code)
        if not p: continue
        our_v = p['values'].get(our_model['model_code'], {})
        our_disp = our_v.get('display', '')
        if '144Hz' in our_disp or 'FreeSync' in our_disp or '240Hz' in our_disp:
            adv.append({'point': f'{p.get("param_name_zh","")} 领先：{our_disp}',
                        'evidence': f'spec {code}', 'confidence': 0.9})
    # 系统劣势
    sys_p = sm.get('SYSTEM')
    if sys_p:
        our_sys = sys_p['values'].get(our_model['model_code'], {}).get('display', '')
        if 'VIDAA' in our_sys:
            dis.append({'point': f'智能系统 {our_sys} 生态弱于 Google TV/Tizen 系',
                        'evidence': '智能系统对比', 'confidence': 0.85})
            opp.append({'point': 'VIDAA 本地化机会：强化本地视频App/语音弥补生态',
                        'evidence': '智能系统归一化', 'confidence': 0.75})
    return {'advantage_points': adv, 'disadvantage_points': dis, 'opportunity_points': opp,
            'strategy_suggestion': '以画质+游戏+性价比组合应对，补强智能生态'}


# ============================================================
# HTTP 服务
# ============================================================

class Handler(BaseHTTPRequestHandler):
    server_version = f"benchmark-api/{__version__}"

    def _send(self, status, payload):
        body = _json(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        cors = SETTINGS.get('cors', '')
        if cors:
            self.send_header("Access-Control-Allow-Origin", cors)
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (ConnectionAbortedError, BrokenPipeError, OSError):
                pass  # 浏览器已断开，忽略

    def _error(self, status, msg):
        self._send(status, {"error": msg})

    def _serve_static(self, path, head_only=False):
        if path == "/" or path == "":
            path = "/index.html"
        full = os.path.join(STATIC_DIR, path.lstrip("/"))
        if not os.path.isfile(full):
            self._error(404, f"静态文件不存在: {path}")
            return
        import mimetypes
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if not head_only:
            with open(full, "rb") as f:
                data = f.read()
        else:
            data = b""
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(os.path.getsize(full)))
        cors = SETTINGS.get('cors', '')
        if cors:
            self.send_header("Access-Control-Allow-Origin", cors)
        self.end_headers()
        if not head_only and self.command != "HEAD":
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("[对阵] %s - %s\n" % (self.address_string(), fmt % args))

    def do_OPTIONS(self):
        self._send(204, {})

    def do_HEAD(self):
        # 支持 HEAD 请求（浏览器缓存验证）
        parsed = urlparse(self.path)
        raw = parsed.path
        if not raw.startswith("/api"):
            self._serve_static(raw, head_only=True)
            return
        self._send(200, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        raw = parsed.path
        query = parse_qs(parsed.query)
        if not raw.startswith("/api"):
            self._serve_static(raw)
            return
        try:
            path = raw.rstrip("/") or "/"
            self._route(path, query)
        except Exception as e:
            traceback.print_exc()
            self._error(500, str(e))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}
        try:
            self._route_post(path, payload)
        except Exception as e:
            traceback.print_exc()
            self._error(500, str(e))

    def _route(self, path, query):
        def q(name, default=""):
            return (query.get(name) or [default])[0].strip()
        if path == "/api/health":
            from . import config as _cfg
            ai_ready = bool(_cfg.XINGHAI_API_KEY)
            self._send(200, {"status": "ok", "version": __version__,
                            "ai_ready": ai_ready,
                            "ai_model": _cfg.XINGHAI_MODEL,
                            "ai_base": _cfg.XINGHAI_BASE_URL})
        elif path == "/api/countries":
            self._send(200, {"countries": api_countries()})
        elif path == "/api/sizes":
            self._send(200, api_sizes(q("region", "JP")))
        elif path == "/api/models":
            self._send(200, api_models(q("region", "JP"), q("size", "65")))
        elif path == "/api/ai-recommend":
            self._send(200, api_ai_recommend(q("region", "JP"), q("size", "65")))
        elif path == "/api/spec":
            ids = [int(x) for x in q("model_ids").split(",") if x.strip()]
            self._send(200, api_spec_compare(ids))
        elif path == "/api/radar":
            ids = [int(x) for x in q("model_ids").split(",") if x.strip()]
            self._send(200, api_radar(ids))
        elif path == "/api/ai-analysis":
            ids = [int(x) for x in q("model_ids").split(",") if x.strip()]
            self._send(200, api_ai_analysis(ids, q("region")))
        elif path == "/api/backfill":
            self._send(200, api_backfill(q("model_ids"), q("region")))
        elif path == "/api/backfill-status":
            self._send(200, api_backfill_status(q("model_id")))
        elif path == "/api/auto-trace":
            wa = q("with_ai","0") in ("1","true","yes")
            self._send(200, api_auto_trace(q("region"), q("size"), max_models=int(q("max_models","50")), with_ai=wa))
        else:
            self._error(404, f"未知路径: {path}")

    def _route_post(self, path, payload):
        if path == "/api/ai-analysis":
            ids = payload.get("model_ids", [])
            region = payload.get("region")
            self._send(200, api_ai_analysis(ids, region))
        elif path == "/api/spec":
            self._send(200, api_spec_compare(payload.get("model_ids", []), payload.get("region", "JP")))
        elif path == "/api/backfill":
            self._send(200, api_backfill(payload.get("model_ids", []), payload.get("region"),
                                         skip_ai=bool(payload.get("skip_ai", False))))
        elif path == "/api/backfill-crawl":
            self._send(200, api_backfill_crawl(payload.get("adapter_code"), payload.get("series")))
        elif path == "/api/auto-trace":
            self._send(200, api_auto_trace(payload.get("region"), payload.get("size"),
                                           max_models=int(payload.get("max_models",50)),
                                           with_ai=bool(payload.get("with_ai",False))))
        else:
            self._error(404, f"未知路径: {path}")


def api_backfill(model_ids_str, region=None, skip_ai=False):
    """对指定型号缺失参数做三层回溯补全。

    skip_ai=True: 只走第1层(db)+第2层(site标记)，不调AI（自动溯源用）
    skip_ai=False: 走全部三层含AI查找官网URL（手动触发用）
    """
    if not model_ids_str:
        return {'error': '未指定型号', 'results': {}}
    if isinstance(model_ids_str, list):
        model_ids = model_ids_str
    else:
        model_ids = [int(x) for x in str(model_ids_str).split(',') if x.strip()]
    if not model_ids:
        return {'error': '型号ID无效', 'results': {}}

    from .backfill import backfill_model_params
    conn = _db()
    c = conn.cursor()
    results = {}
    all_params = PARAM_ORDER

    for mid in model_ids:
        c.execute("SELECT model_code FROM dim_product_model WHERE model_id=?", (mid,))
        r = c.fetchone()
        if not r:
            results[str(mid)] = {'error': '型号不存在'}
            continue
        model_code = r[0]
        # 查已有参数
        c2 = conn.cursor()
        c2.execute("SELECT p.param_code FROM fact_spec_value f JOIN dim_spec_parameter p ON p.param_id=f.param_id WHERE f.model_id=?", (mid,))
        have = set(x[0] for x in c2.fetchall())
        missing = [p for p in all_params if p not in have]
        if not missing:
            results[str(mid)] = {'model_code': model_code, 'missing': [], 'backfill': {}, 'message': '无缺失参数'}
            continue
        # 三层回溯
        bf = backfill_model_params(mid, missing, SETTINGS['db'], skip_ai=skip_ai)
        results[str(mid)] = {
            'model_code': model_code,
            'missing': missing,
            'backfill': bf,
            'message': f'缺失{len(missing)}个参数，已回溯'
        }
    conn.close()
    return {'results': results, 'total_models': len(model_ids)}


def api_backfill_status(model_id):
    """查某型号回溯补全状态"""
    if not model_id:
        return {'error': '未指定型号'}
    mid = int(model_id)
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT model_code, brand, brand_raw FROM dim_product_model WHERE model_id=?", (mid,))
    r = c.fetchone()
    if not r:
        conn.close()
        return {'error': '型号不存在'}
    c.execute("SELECT p.param_code, p.param_name, f.value_text, f.source_table FROM fact_spec_value f JOIN dim_spec_parameter p ON p.param_id=f.param_id WHERE f.model_id=?", (mid,))
    have = [{'param_code': x[0], 'param_name': x[1], 'value': x[2], 'source': x[3]} for x in c.fetchall()]
    all_params = set(PARAM_ORDER)
    have_codes = set(x['param_code'] for x in have)
    missing = list(all_params - have_codes)
    conn.close()
    return {'model_id': mid, 'model_code': r[0], 'brand': r[1],
            'have_count': len(have), 'missing': missing, 'have': have}


def api_backfill_crawl(adapter_code, series):
    """触发第2层实际抓取：调 spec_crawl 重抓指定系列。"""
    if not adapter_code or not series:
        return {'error': '需指定 adapter_code 和 series'}
    from .backfill import trigger_site_crawl
    result = trigger_site_crawl(adapter_code, series, SETTINGS['db'])
    return result


def api_auto_trace(region=None, size=None, write_back=True, max_models=50, with_ai=False):
    """全库自动溯源：扫描所有型号缺失参数，三层回溯补全，写回 fact_spec_value。

    GET /api/auto-trace?region=JP&size=65&max_models=50&with_ai=1
    with_ai 默认 False：全库批量只走第1层(db)+第2层(site)，跳过慢的第3层(AI)。
    with_ai=1：开启第3层 AI 推断（慢，建议单型号用 /api/backfill）。
    """
    from .backfill import backfill_model_params
    conn = _db()
    c = conn.cursor()
    sql = """SELECT m.model_id, m.model_code, m.brand, m.size_inch,
             (SELECT GROUP_CONCAT(DISTINCT p.param_code) FROM dim_spec_parameter p
              WHERE p.param_id NOT IN (SELECT f2.param_id FROM fact_spec_value f2 WHERE f2.model_id=m.model_id)
             ) as missing_codes
             FROM dim_product_model m
             WHERE m.model_code IS NOT NULL"""
    params = []
    if size:
        sql += " AND m.size_inch=?"
        params.append(int(size))
    sql += " ORDER BY m.our_brand DESC, m.model_id LIMIT ?"
    params.append(max_models)
    c.execute(sql, params)
    rows = c.fetchall()

    results = []
    total_filled = 0
    total_missing = 0
    for r in rows:
        mid = r['model_id']
        missing_codes_str = r['missing_codes'] or ''
        missing = [x.strip() for x in missing_codes_str.split(',') if x.strip() and x.strip() in PARAM_ORDER]
        if not missing:
            continue
        total_missing += len(missing)
        bf = backfill_model_params(mid, missing, SETTINGS['db'], skip_ai=not with_ai)
        filled = 0
        for param_code, info in bf.items():
            if info.get('confidence', 0) > 0 and info.get('value') and info['value'] != '(待重抓)':
                if write_back:
                    c2 = conn.cursor()
                    c2.execute("SELECT param_id FROM dim_spec_parameter WHERE param_code=?", (param_code,))
                    pid_row = c2.fetchone()
                    if pid_row:
                        pid = pid_row[0]
                        source_tag = f"[{info['source']}] {info.get('detail','')[:100]}"
                        c2.execute("""INSERT OR REPLACE INTO fact_spec_value
                            (model_id, param_id, value_text, value_numeric, value_unit, source_table, source_term, captured_at, confidence)
                            VALUES (?, ?, ?, NULL, '', ?, ?, datetime('now'), ?)""",
                            (mid, pid, info['value'][:500], f'auto-trace-{info["source"]}', source_tag, info['confidence']))
                        conn.commit()
                filled += 1
        total_filled += filled
        results.append({'model_id': mid, 'model_code': r['model_code'], 'brand': r['brand'],
                        'missing_count': len(missing), 'filled_count': filled,
                        'still_missing': len(missing) - filled})
    conn.close()
    return {'total_models': len(results), 'total_missing': total_missing,
            'total_filled': total_filled, 'coverage': f'{total_filled}/{total_missing}',
            'results': results}


def _setup_xinghai():
    """从 DSH settings 注入 xinghai-ultra 配置（本地转换代理）。

    DSH settings.yaml 里 xinghai-ultra 走 http://127.0.0.1:8082/v1 本地代理，
    代理忽略客户端鉴权头（apiKey 用占位值）。此处把该配置注入 config 模块。
    """
    import os
    # DSH 本地代理地址（OpenAI 兼容协议）
    proxy_url = "http://127.0.0.1:8082/v1"
    placeholder_key = "local-proxy-placeholder"

    # 只在环境变量未显式设置时注入（避免覆盖用户自定义）
    if not os.environ.get("OVERSEAS_LLM_BASE_URL"):
        os.environ["OVERSEAS_LLM_BASE_URL"] = proxy_url
    if not os.environ.get("OVERSEAS_LLM_API_KEY"):
        os.environ["OVERSEAS_LLM_API_KEY"] = placeholder_key
    if not os.environ.get("OVERSEAS_LLM_MODEL"):
        os.environ["OVERSEAS_LLM_MODEL"] = "xinghai-ultra"
    if not os.environ.get("OVERSEAS_LLM_PROVIDER"):
        os.environ["OVERSEAS_LLM_PROVIDER"] = "xinghai"

    # 同步注入 XINGHAI_* （llm_client 在 provider=xinghai 时会复用）
    if not os.environ.get("OVERSEAS_XINGHAI_BASE_URL"):
        os.environ["OVERSEAS_XINGHAI_BASE_URL"] = proxy_url
    if not os.environ.get("OVERSEAS_XINGHAI_API_KEY"):
        os.environ["OVERSEAS_XINGHAI_API_KEY"] = placeholder_key
    # 本地代理不需要 user_key，但 LLMClient 的 configured 检查会看 uses_user_key
    # provider=xinghai 默认 uses_user_key=True，需设个占位值让 configured=True
    if not os.environ.get("OVERSEAS_XINGHAI_USER_KEY"):
        os.environ["OVERSEAS_XINGHAI_USER_KEY"] = placeholder_key

    # 强制重新加载 config 模块的值（因为 config 在 import 时已读了一次）
    from . import config as _cfg
    _cfg.XINGHAI_BASE_URL = proxy_url
    _cfg.XINGHAI_API_KEY = placeholder_key
    _cfg.XINGHAI_USER_KEY = placeholder_key
    _cfg.XINGHAI_MODEL = "xinghai-ultra"
    _cfg.LLM_BASE_URL = proxy_url
    _cfg.LLM_API_KEY = placeholder_key
    _cfg.LLM_MODEL = "xinghai-ultra"
    _cfg.LLM_PROVIDER = "xinghai"
    _cfg.LLM_USER_KEY = placeholder_key
    # 本地代理不需要 user_key 校验
    _cfg._LLM_PROVIDER_DEFAULTS["xinghai"]["uses_user_key"] = False
    # 本地代理走 OpenAI 兼容协议，用非流式更稳
    os.environ["OVERSEAS_LLM_STREAM"] = "false"
    # 本地 HTTP 代理不需要 SSL 校验
    os.environ["OVERSEAS_LLM_SSL_VERIFY"] = "false"
    _cfg.LLM_STREAM = False
    _cfg.LLM_SSL_VERIFY = False


def main():
    _setup_xinghai()
    ap = argparse.ArgumentParser(description="竞品对阵分析服务")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--cors", default="")
    ap.add_argument("--enable-scheduled-trace", action="store_true",
                    help="启用定时溯源任务（默认不启动，见 README §定时溯源）")
    args = ap.parse_args()

    SETTINGS['db'] = args.db
    SETTINGS['cors'] = args.cors

    print(f"竞品对阵分析服务 v{__version__}")
    print(f"数据库: {args.db}")
    print(f"静态目录: {STATIC_DIR}")
    print(f"xinghai-ultra: {config.XINGHAI_BASE_URL} model={config.XINGHAI_MODEL}")
    # 验证代理可用性
    try:
        import urllib.request
        req = urllib.request.Request(f"{config.XINGHAI_BASE_URL}/models",
                                     headers={"Authorization": f"Bearer {config.XINGHAI_API_KEY}"})
        urllib.request.urlopen(req, timeout=3)
        print(f"AI 代理: [OK] 可用")
    except Exception as e:
        print(f"AI 代理: [不可用] {e}，将走规则兜底")
    print(f"访问: http://{args.host}:{args.port}/")
    print()

    server = ThreadingHTTPServer((args.host, args.port), Handler)

    # 定时自动溯源：默认不启动，加 --enable-scheduled-trace 才启用
    # 见 README §定时溯源（每天凌晨2点扫描全库缺失参数并补全）
    if args.enable_scheduled_trace:
        import threading
        import datetime

        def _scheduled_trace():
            """定时溯源任务：每天凌晨2点执行。"""
            SETTINGS['db'] = args.db
            try:
                print(f"[定时溯源 {datetime.datetime.now():%Y-%m-%d %H:%M}] 开始全库溯源...")
                r = api_auto_trace(max_models=100, with_ai=False)
                print(f"[定时溯源完成] 扫描{r['total_models']}型号，补全{r['total_filled']}/{r['total_missing']}")
            except Exception as e:
                print(f"[定时溯源失败] {e}")
            finally:
                # 计算下次执行时间（明天凌晨2点）
                now = datetime.datetime.now()
                next_run = (now + datetime.timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)
                delay = (next_run - now).total_seconds()
                timer = threading.Timer(delay, _scheduled_trace)
                timer.daemon = True
                timer.start()
                print(f"[下次溯源] {next_run:%Y-%m-%d %H:%M}")

        # 启动时立即调度首次（明天2点），并在后台跑
        _first_now = datetime.datetime.now()
        _first_run = (_first_now + datetime.timedelta(days=1)).replace(hour=2, minute=0, second=0, microsecond=0)
        _first_delay = (_first_run - _first_now).total_seconds()
        _t = threading.Timer(_first_delay, _scheduled_trace)
        _t.daemon = True
        _t.start()
        print(f"定时溯源已启用：每天凌晨2点自动执行，首次 {_first_run:%Y-%m-%d %H:%M}")
    else:
        print("定时溯源：未启用（加 --enable-scheduled-trace 启用，详见 README §定时溯源）")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
