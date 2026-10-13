# -*- coding: utf-8 -*-
"""规范化维护 benchmark 相关表。

维护内容：
1. dim_product_model.region —— 根据 brand_raw 后缀/关键词批量填充
2. dim_spec_item_map —— 已由 _rebuild_map.py 重建（67条精确映射），确认状态
3. fact_spec_value —— 重新抽值，补全 TCL/Sharp/松下 日本线型号
4. dim_spec_normalization_map —— 确认 PENDING→CONFIRMED
5. dim_product_model —— 填充日本线 our_brand=1（海信日本线型号）

运行后这些表即规范化维护完毕，存放在原 DB（海外/overseas_v4_20260929.db）。
"""
import sqlite3, sys, json, re, os
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8')

DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")

# ===== 1. region 映射规则 =====
# brand_raw 后缀/关键词 → region code
REGION_RULES = [
    # 后缀匹配
    ('_jp', 'JP'), ('_us', 'US'), ('_ca', 'CA'), ('_mx', 'MX'),
    ('_uk', 'UK'), ('_pe', 'PE'), ('_co', 'CO'), ('_cl', 'CL'),
    ('_ec', 'EC'), ('_bo', 'BO'),
    # 关键词匹配（中文国名）
    ('日本', 'JP'), ('美国', 'US'), ('加拿大', 'CA'), ('墨西哥', 'MX'),
    ('英国', 'UK'), ('欧洲', 'EU'), ('欧州', 'EU'),
]

def infer_region(brand_raw):
    """根据 brand_raw 推断 region"""
    if not brand_raw:
        return None
    br = str(brand_raw)
    for keyword, region in REGION_RULES:
        if keyword in br:
            return region
    return None

# ===== 2. spec_row 精确映射（item_ja → param_code）=====
JP_SPEC_ROW_MAP = {
    '画素数': ('RESOLUTION', r'(\d+)\s*[×x]\s*(\d+)'),
    '画素数(水平×垂直)': ('RESOLUTION', r'([\d,]+)\s*[×x]\s*([\d,]+)'),
    '像素数': ('RESOLUTION', r'(\d+)\s*[×x]\s*(\d+)'),
    '画面サイズ': ('SCREEN_SIZE', r'(\d+)V?型?'),
    'パネルサイズ': ('SCREEN_SIZE', r'(\d+)V?型?'),
    '画面サイズ(横×縦/対角)': ('SCREEN_SIZE', r'(\d+)'),
    '倍速対応': ('REFRESH_RATE', r'(\d+)Hz'),
    '倍速駆動(120Hz)': ('REFRESH_RATE', r'(\d+)'),
    'バックライト': ('DIMMING_ZONES', None),
    'パネル': ('DIMMING_ZONES', None),
    'エンジン': ('CHIP', None),
    '映像エンジン': ('CHIP', None),
    '映像処理エンジン': ('CHIP', None),
    '広色域': ('COLOR_GAMUT', None),
    '広色域(WCG)': ('COLOR_GAMUT', None),
    '量子ドット': ('COLOR_GAMUT', None),
    'HDR対応': ('HDR', None),
    'HDR機能': ('HDR', None),
    'スピーカー最大出力': ('SOUND', r'(\d+)W'),
    'スピーカー構成': ('SOUND', None),
    'スピーカー': ('SOUND', None),
    '実用最大出力(JEITA)': ('SOUND', r'(\d+)W'),
    '音声フォーマット': ('DOLBY_ATMOS', None),
    'システム': ('SYSTEM', None),
    '搭載OS': ('SYSTEM', None),
    'ゲームモード': ('GAMING', None),
    'HDMI2.1仕様': ('GAMING', None),
    'HDMI': ('HDMI', None),
    'HDMI端子': ('HDMI', r'(\d+)'),
    '端子数': ('HDMI', r'(\d+)'),
    '無線LAN内蔵': ('WIFI', None),
    'Wi-Fi内蔵': ('WIFI', None),
    'Bluetoothイヤホン//ヘッドホン/サウンドバー': ('BLUETOOTH', None),
    'Bluetooth内蔵': ('BLUETOOTH', None),
    '定格消費電力': ('POWER_CONSUMPTION', r'([\d.]+)W'),
    '定格消費電力(待機時消費電力)': ('POWER_CONSUMPTION', r'約?([\d.]+)W'),
    '消費電力': ('POWER_CONSUMPTION', r'([\d.]+)\s*W'),
    '梱包質量(kg)': ('WEIGHT', r'約?\s*([\d.]+)'),
    '本体質量': ('WEIGHT', r'約?\s*([\d.]+)'),
    '質量': ('WEIGHT', r'約?\s*([\d.]+)'),
    'スタンド含まない(kg)': ('WEIGHT', r'([\d.]+)'),
    'スタンド含む(kg)': ('WEIGHT', r'([\d.]+)'),
    'スタンド含まない(cm)': ('DIMENSIONS', None),
    'スタンド含む(cm)': ('DIMENSIONS', None),
    '壁掛け対応': ('DIMENSIONS', r'(\d+)\s*[×x]\s*(\d+)'),
    '外形寸法': ('DIMENSIONS', None),
    '外形寸法(幅×奥行×高さ)': ('DIMENSIONS', None),
}

# product_spec 关键词映射
US_PS_MAP = {
    'Peak Brightness': ('PEAK_BRIGHTNESS', r'([\d.]+)\s*nits?'),
    'Brightness': ('PEAK_BRIGHTNESS', r'([\d.]+)\s*nits?'),
    'Dimming Zones': ('DIMMING_ZONES', r'([\d.]+)\s*[zZ]ones?'),
    'Local Dimming': ('DIMMING_ZONES', None),
    'Refresh Rate': ('REFRESH_RATE', r'(\d+)\s*Hz'),
    'Processor': ('CHIP', None),
    'Picture Processor': ('CHIP', None),
    'Operating System': ('SYSTEM', None),
    'Smart TV': ('SYSTEM', None),
    'HDR': ('HDR', None),
    'Dolby Atmos': ('DOLBY_ATMOS', None),
    'Speaker': ('SOUND', r'([\d.]+)\s*W'),
    'Audio Output': ('SOUND', r'([\d.]+)\s*W'),
    'Color Gamut': ('COLOR_GAMUT', None),
    'QLED': ('COLOR_GAMUT', None),
    'Quantum Dot': ('COLOR_GAMUT', None),
    'HDMI': ('HDMI', r'(\d+)'),
    'Wi-Fi': ('WIFI', None),
    'Bluetooth': ('BLUETOOTH', None),
    'Resolution': ('RESOLUTION', None),
    'Weight': ('WEIGHT', r'([\d.]+)\s*(kg|lbs?)'),
    'Dimensions': ('DIMENSIONS', None),
    'Power Consumption': ('POWER_CONSUMPTION', r'([\d.]+)\s*W'),
    'Screen Size': ('SCREEN_SIZE', r'(\d+)'),
    'Gaming': ('GAMING', None),
    'VRR': ('GAMING', None),
    'ALLM': ('GAMING', None),
}


def main():
    # 备份
    import shutil
    bak = DB.replace('.db', '_benchmark_bak.db')
    if not os.path.exists(bak):
        shutil.copy2(DB, bak)
        print(f"已备份: {bak}")
    else:
        print(f"备份已存在: {bak}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # ===== 1. 填充 dim_product_model.region =====
    print("\n=== 1. 填充 dim_product_model.region ===")
    updated = 0
    c.execute("SELECT model_id, brand_raw, region FROM dim_product_model WHERE region IS NULL OR region=''")
    rows = c.fetchall()
    for r in rows:
        region = infer_region(r['brand_raw'])
        if region:
            c.execute("UPDATE dim_product_model SET region=? WHERE model_id=?", (region, r['model_id']))
            updated += 1
    conn.commit()
    print(f"  填充 region: {updated}/{len(rows)} 型号")

    # 统计
    c.execute("SELECT region, COUNT(*) FROM dim_product_model GROUP BY region ORDER BY COUNT(*) DESC")
    print("  region 分布:")
    for r in c.fetchall():
        print(f"    {str(r[0]):10s} {r[1]}型号")

    # ===== 2. 重建 dim_spec_item_map =====
    print("\n=== 2. 重建 dim_spec_item_map（精确映射）===")
    c.execute("DELETE FROM dim_spec_item_map WHERE source_table='spec_row'")
    old_sr = c.rowcount
    c.execute("DELETE FROM dim_spec_item_map WHERE source_table='product_spec'")
    old_ps = c.rowcount
    print(f"  删除旧映射: spec_row {old_sr} + product_spec {old_ps}")

    new_sr = 0
    for item_ja, (param_code, regex) in JP_SPEC_ROW_MAP.items():
        c.execute("SELECT param_id FROM dim_spec_parameter WHERE param_code=?", (param_code,))
        r = c.fetchone()
        if r:
            c.execute("""INSERT INTO dim_spec_item_map
                (source_table, source_field, source_term, param_id, extract_regex, match_keyword, match_type, status, created_at)
                VALUES ('spec_row', 'item_ja', ?, ?, ?, NULL, 'EXACT', 'CONFIRMED', datetime('now'))""",
                (item_ja, r['param_id'], regex))
            new_sr += 1
    new_ps = 0
    for keyword, (param_code, regex) in US_PS_MAP.items():
        c.execute("SELECT param_id FROM dim_spec_parameter WHERE param_code=?", (param_code,))
        r = c.fetchone()
        if r:
            c.execute("""INSERT INTO dim_spec_item_map
                (source_table, source_field, source_term, param_id, extract_regex, match_keyword, match_type, status, created_at)
                VALUES ('product_spec', 'key', ?, ?, ?, ?, 'LIKE', 'CONFIRMED', datetime('now'))""",
                (keyword, r['param_id'], regex, keyword))
            new_ps += 1
    conn.commit()
    print(f"  插入新映射: spec_row {new_sr} + product_spec {new_ps} = {new_sr+new_ps}条")

    # ===== 3. 重新抽 fact_spec_value =====
    print("\n=== 3. 重新抽取 fact_spec_value ===")
    c.execute("DELETE FROM fact_spec_value")
    print(f"  清空: {c.rowcount} 条")

    # 型号字典
    c.execute("SELECT model_id, model_code FROM dim_product_model")
    model_map = {row['model_code']: row['model_id'] for row in c.fetchall() if row['model_code']}

    # 加载映射
    c.execute("SELECT source_table, source_term, param_id, extract_regex, match_keyword FROM dim_spec_item_map WHERE status='CONFIRMED'")
    exact_map = {}
    keyword_list = []
    for src_tbl, term, pid, rx, kw in c.fetchall():
        if src_tbl == 'spec_row':
            exact_map[(src_tbl, term)] = {'param_id': pid, 'extract_regex': rx}
        elif src_tbl == 'product_spec' and kw:
            keyword_list.append({'keyword': kw, 'param_id': pid, 'extract_regex': rx})

    # 处理 spec_row
    written = 0
    c.execute("""SELECT sr.id, sr.item_ja, sr.values_json FROM spec_row sr
                 JOIN spec_series ss ON ss.id=sr.series_id""")
    spec_rows = c.fetchall()
    print(f"  扫描 spec_row: {len(spec_rows)} 行...")
    for sr in spec_rows:
        item_ja = sr['item_ja']
        key = ('spec_row', item_ja)
        if key not in exact_map:
            continue
        pm = exact_map[key]
        try:
            values = json.loads(sr['values_json'])
        except:
            continue
        for mc, val in values.items():
            if not val or val in ('', '-', '—', 'ー'):
                continue
            mc_clean = mc.strip()
            if mc_clean not in model_map:
                continue
            mid = model_map[mc_clean]
            num = None
            if pm['extract_regex']:
                try:
                    m = re.search(pm['extract_regex'], str(val))
                    if m:
                        num = float(m.group(1).replace(',', ''))
                except: pass
            try:
                c.execute("""INSERT OR REPLACE INTO fact_spec_value
                    (model_id, param_id, value_text, value_numeric, source_table, source_term, captured_at)
                    VALUES (?, ?, ?, ?, 'spec_row', ?, datetime('now'))""",
                    (mid, pm['param_id'], str(val)[:500], num, item_ja))
                written += 1
            except sqlite3.IntegrityError:
                pass

    # 处理 product_spec
    c.execute("SELECT ps.key, ps.value, p.model FROM product_spec ps JOIN product p ON p.id=ps.product_id")
    ps_rows = c.fetchall()
    print(f"  扫描 product_spec: {len(ps_rows)} 行...")
    for psr in ps_rows:
        key = psr['key']
        val = psr['value']
        model = psr['model']
        if not val or not model or model not in model_map:
            continue
        key_lower = (key or '').lower()
        matched = None
        for item in keyword_list:
            if item['keyword'].lower() in key_lower:
                matched = item
                break
        if not matched:
            continue
        mid = model_map[model]
        num = None
        if matched['extract_regex']:
            try:
                m = re.search(matched['extract_regex'], str(val), re.I)
                if m:
                    num = float(m.group(1).replace(',', ''))
            except: pass
        try:
            c.execute("""INSERT OR REPLACE INTO fact_spec_value
                (model_id, param_id, value_text, value_numeric, source_table, source_term, captured_at)
                VALUES (?, ?, ?, ?, 'product_spec', ?, datetime('now'))""",
                (mid, matched['param_id'], str(val)[:500], num, key))
            written += 1
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    print(f"  写入 fact_spec_value: {written} 条")

    # ===== 4. 确认 dim_spec_normalization_map =====
    print("\n=== 4. 确认 dim_spec_normalization_map ===")
    c.execute("UPDATE dim_spec_normalization_map SET status='CONFIRMED', confirmed_by='benchmark_maintain', confirmed_at=datetime('now') WHERE status='PENDING'")
    print(f"  PENDING → CONFIRMED: {c.rowcount} 条")
    conn.commit()

    # ===== 5. 海信日本线 our_brand=1 =====
    print("\n=== 5. 海信日本线 our_brand 标记 ===")
    # 有 JPY 价格的海信型号 → our_brand=1
    c.execute("""SELECT DISTINCT m.model_id FROM dim_product_model m
                 WHERE m.model_code IN (
                   SELECT DISTINCT p.model FROM product p
                   JOIN price_snapshot ps ON ps.product_id=p.id
                   WHERE p.brand LIKE '%isense%' AND ps.currency='JPY'
                 ) AND m.our_brand=0""")
    hisense_jp_ids = [r[0] for r in c.fetchall()]
    for mid in hisense_jp_ids:
        c.execute("UPDATE dim_product_model SET our_brand=1 WHERE model_id=?", (mid,))
    conn.commit()
    print(f"  海信日本线标记 our_brand=1: {len(hisense_jp_ids)} 型号")

    # ===== 最终统计 =====
    print("\n=== 最终统计 ===")
    c.execute("SELECT COUNT(*) FROM fact_spec_value")
    print(f"  fact_spec_value: {c.fetchone()[0]} 条")
    c.execute("SELECT COUNT(*) FROM dim_spec_item_map WHERE status='CONFIRMED'")
    print(f"  dim_spec_item_map CONFIRMED: {c.fetchone()[0]} 条")
    c.execute("SELECT COUNT(*) FROM dim_product_model WHERE region IS NOT NULL")
    print(f"  dim_product_model 有region: {c.fetchone()[0]} 型号")
    c.execute("SELECT COUNT(*) FROM dim_product_model WHERE our_brand=1")
    print(f"  dim_product_model our_brand=1: {c.fetchone()[0]} 型号")
    c.execute("SELECT COUNT(*) FROM dim_spec_normalization_map WHERE status='CONFIRMED'")
    print(f"  dim_spec_normalization_map CONFIRMED: {c.fetchone()[0]} 条")

    conn.close()
    print("\n规范化维护完成。")


if __name__ == '__main__':
    main()
