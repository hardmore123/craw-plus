# -*- coding: utf-8 -*-
"""日本线终极补全：把 Sharp/TCL/Panasonic 官网真实存在的 item_ja 全部映射
只映射真实的，排除已知误匹配"""
import os
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT param_id, param_code FROM dim_spec_parameter")
code_pid = {r['param_code']: r['param_id'] for r in c.fetchall()}

# ===== Sharp/TCL/Panasonic 真实 item_ja 映射 =====
# 基于上面输出的实际 item_ja 清单，精确对应到 18 参数
MAPPINGS = {
    # ===== Sharp =====
    # HDMI
    'HDMI端子': 'HDMI',
    # HDR
    'HDR対応': 'HDR',
    # BLUETOOTH
    'Bluetooth': 'BLUETOOTH',
    # WIFI
    '無線LAN対応': 'WIFI', '無線LAN内蔵': 'WIFI',
    # RESOLUTION
    '画素数(水平×垂直 画素)': 'RESOLUTION',
    # SCREEN_SIZE
    '画面サイズ(横×縦/対角)': 'SCREEN_SIZE',
    # WEIGHT
    '本体質量': 'WEIGHT',
    # DIMENSIONS
    '外形寸法(幅×奥行×高さ)': 'DIMENSIONS', '梱包サイズ(幅×奥行×高さ)': 'DIMENSIONS',
    # POWER_CONSUMPTION
    '定格消費電力(待機時消費電力)': 'POWER_CONSUMPTION',
    # SOUND
    '音声実用最大出力(JEITA)': 'SOUND', 'スピーカー': 'SOUND',
    # SOUND(アンプ)
    'アンプ': 'SOUND',
    # CHIP - Sharp没有映像エンジン类

    # ===== TCL（item_ja 变体很多，全补）=====
    # HDMI
    'HDMI': 'HDMI', 'HDMI 4K/2K端子': 'HDMI', 'HDMI再生': 'HDMI',
    # HDR
    'HDR対応': 'HDR', 'HDR10/HLG対応': 'HDR',
    # BLUETOOTH
    'Bluetooth内蔵': 'BLUETOOTH',
    # WIFI
    'Wi-Fi内蔵': 'WIFI', 'Wi-Fi内蔵(2.4G/5G)': 'WIFI', 'Wi-Fi内蔵(2.4G/5G）': 'WIFI',
    # SYSTEM
    'Android TVTM OS9.0 Google アシスト搭載': 'SYSTEM', 'Android TV™ OS9.0': 'SYSTEM',
    'Google TV': 'SYSTEM', 'Google アシスタント搭載': 'SYSTEM', 'Google アシスト搭載': 'SYSTEM',
    # DOLBY_ATMOS
    'Dolby Atmos対応': 'DOLBY_ATMOS', 'Dolby Atoms対応': 'DOLBY_ATMOS',
    # CHIP
    'IPQエンジン': 'CHIP', '映像エンジン': 'CHIP',
    # COLOR_GAMUT
    '広色域(WCG)': 'COLOR_GAMUT', '広色域（WCG）': 'COLOR_GAMUT',
    '量子ドット': 'COLOR_GAMUT', '量子ドット(QLED)': 'COLOR_GAMUT',
    '量子ドットLED(QLED)': 'COLOR_GAMUT', '量子ドットLED（QLED）': 'COLOR_GAMUT',
    # DIMMING_ZONES
    'バックライト方式': 'DIMMING_ZONES', 'ローカルディミング': 'DIMMING_ZONES',
    'ローカルdimming': 'DIMMING_ZONES', 'マイクロディミング': 'DIMMING_ZONES',
    'マイクロdimming': 'DIMMING_ZONES', 'パネルタイプ': 'DIMMING_ZONES',
    'Mini LED': 'DIMMING_ZONES',
    # REFRESH_RATE
    '倍速駆動(120Hz)': 'REFRESH_RATE', '駆動方式': 'REFRESH_RATE',
    # GAMING
    'ゲーム機能': 'GAMING',
    # CONTRAST
    'コントラスト 比': 'CONTRAST', 'コントラスト比': 'CONTRAST',
    # RESOLUTION
    '画素数': 'RESOLUTION', '画 素 数': 'RESOLUTION',
    # SCREEN_SIZE
    '画面サイズ': 'SCREEN_SIZE', '画面サイズ (※2)': 'SCREEN_SIZE',
    # WEIGHT
    'スタンドあり(kg)': 'WEIGHT', 'スタンドなし（kg）': 'WEIGHT',
    'スタンド除く(kg)': 'WEIGHT', '本体重量、スタンド除く': 'WEIGHT',
    # DIMENSIONS
    'スタンドあり (mm)': 'DIMENSIONS', 'スタンドあり(mm)': 'DIMENSIONS',
    'スタンド除く (mm)': 'DIMENSIONS', 'スタンド除く(mm)': 'DIMENSIONS',
    '外形寸法 内は本体 スタンド除く': 'DIMENSIONS',
    '画面寸法 (mm)': 'DIMENSIONS', '画面寸法 mm': 'DIMENSIONS', '画面寸法(mm)': 'DIMENSIONS',
    '梱包カートン (mm)': 'DIMENSIONS', '梱包カートン(mm)': 'DIMENSIONS',
    # POWER_CONSUMPTION
    '定格消費電力': 'POWER_CONSUMPTION', '消費電力': 'POWER_CONSUMPTION',
    '消費電力(W)': 'POWER_CONSUMPTION', '待機時消費電力(W)': 'POWER_CONSUMPTION',
    '待機時消費電力': 'POWER_CONSUMPTION',
    # SOUND
    'スピーカー': 'SOUND', '実用最大出力(JEITA)': 'SOUND', '実用最大出力（JEITA）': 'SOUND',
    '音 声 出 力': 'SOUND', 'ONKYOスピーカー': 'SOUND', 'Onkyoスピーカー': 'SOUND',
    'ONKYOサウンドバー': 'SOUND', 'ONKYOサブウーファー': 'SOUND',
    # PEAK_BRIGHTNESS - TCL无

    # ===== Panasonic =====
    # HDMI
    '端子数': 'HDMI',
    # WIFI
    '無線LAN内蔵': 'WIFI',
    # SYSTEM
    'Fire TV★1': 'SYSTEM',
    # RESOLUTION
    '画素数(水平×垂直)': 'RESOLUTION',
    # SCREEN_SIZE
    '画面寸法': 'SCREEN_SIZE', 'パネルサイズ': 'SCREEN_SIZE',
    # WEIGHT
    '質量': 'WEIGHT', '梱包質量(kg)': 'WEIGHT',
    # DIMENSIONS
    '外形寸法': 'DIMENSIONS', '梱包寸法(mm)': 'DIMENSIONS',
    # POWER_CONSUMPTION
    '消費電力': 'POWER_CONSUMPTION',
    # SOUND
    'スピーカー': 'SOUND', '実用最大出力(JEITA)': 'SOUND',
    # DIMMING_ZONES
    'パネル': 'DIMMING_ZONES',
    # DOLBY_ATMOS - Panasonic无独立项

    # ===== Sony (BRAVIA) - 之前没列，补通用 =====
    # 已由前面的英文 key 覆盖
}

print("=== 补全日本线 item_ja 映射 ===")
added = 0
for term, pcode in MAPPINGS.items():
    pid = code_pid.get(pcode)
    if not pid: continue
    c.execute("""SELECT 1 FROM dim_spec_item_map WHERE source_table='spec_row'
                 AND source_term=? AND param_id=?""", (term, pid))
    if c.fetchone(): continue
    c.execute("""INSERT INTO dim_spec_item_map
        (source_table, source_field, source_term, param_id, match_type, status, created_at)
        VALUES ('spec_row','item_ja',?,?,'EXACT','CONFIRMED',datetime('now'))""", (term, pid))
    added += 1
conn.commit()
print(f"  新增: {added} 条")

# 重抽 fact_spec_value
print("\n=== 重抽 fact_spec_value ===")
c.execute("""SELECT source_term, param_id FROM dim_spec_item_map
             WHERE source_table='spec_row' AND match_type='EXACT' AND status='CONFIRMED'""")
sr_exact = {r['source_term']: r['param_id'] for r in c.fetchall()}
print(f"  spec_row 映射总数: {len(sr_exact)}")

c.execute("SELECT model_id, model_code FROM dim_product_model WHERE model_code IS NOT NULL")
mc_mid = {r['model_code']: r['model_id'] for r in c.fetchall()}
c.execute("SELECT model_id, param_id FROM fact_spec_value")
existing = set((r['model_id'], r['param_id']) for r in c.fetchall())

written = 0
c.execute("SELECT item_ja, values_json FROM spec_row")
for sr in c.fetchall():
    item_ja = sr['item_ja']
    if item_ja not in sr_exact: continue
    pid = sr_exact[item_ja]
    try: vals = json.loads(sr['values_json'])
    except: continue
    for mc, val in vals.items():
        mc = mc.strip()
        if mc not in mc_mid or not val or val in ('', '-', '—', 'ー'): continue
        mid = mc_mid[mc]
        if (mid, pid) in existing: continue
        c.execute("""INSERT OR REPLACE INTO fact_spec_value
            (model_id, param_id, value_text, source_table, source_term, captured_at)
            VALUES (?, ?, ?, 'spec_row', ?, datetime('now'))""",
            (mid, pid, str(val)[:500], item_ja))
        written += 1
        existing.add((mid, pid))
conn.commit()
print(f"  新增: {written} 条")
c.execute("SELECT COUNT(*) FROM fact_spec_value")
print(f"  总量: {c.fetchone()[0]}")

# 最终统计日本线覆盖率
print("\n=== 日本线最终覆盖率 ===")
for brand_filter, label in [("(brand_raw LIKE '%Sharp%日本%' OR brand_raw LIKE '%AQUOS%日本%')", 'Sharp'),
                             ("(brand_raw LIKE '%TCL%日本%')", 'TCL'),
                             ("(brand_raw LIKE '%Panasonic%日本%' OR brand_raw LIKE '%VIERA%日本%')", 'Panasonic'),
                             ("our_brand=1", 'Hisense我方')]:
    c.execute(f"SELECT COUNT(*) FROM dim_product_model WHERE {brand_filter}")
    total = c.fetchone()[0]
    c.execute(f"""SELECT COUNT(DISTINCT m.model_id) FROM dim_product_model m
                  JOIN fact_spec_value f ON f.model_id=m.model_id WHERE {brand_filter}""")
    has = c.fetchone()[0]
    # 平均参数数
    c.execute(f"""SELECT AVG(cnt) FROM (
                  SELECT m.model_id, COUNT(DISTINCT f.param_id) cnt FROM dim_product_model m
                  JOIN fact_spec_value f ON f.model_id=m.model_id WHERE {brand_filter} GROUP BY m.model_id)""")
    avg = c.fetchone()[0] or 0
    print(f"  {label:12s} {total:3d}个 有spec={has:3d} 平均{avg:.1f}/18")

conn.close()
print("\n日本线终极补全完成。")
