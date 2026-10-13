# -*- coding: utf-8 -*-
"""
将爬取DB(overseas.db)中新增的9个欧洲品牌系列的spec_series和spec_row同步到源DB(overseas_v4_20260929.db)
然后重建dim_product_model和fact_spec_value
"""
import os
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

CRAWL_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
SRC_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")

new_brands = ['samsung_de','samsung_fr','samsung_it','sony_de','sony_fr','sony_it','tcl_de','tcl_fr','tcl_it']

# 1. 从爬取DB读取这些品牌的spec_series和spec_row
src_conn = sqlite3.connect(CRAWL_DB)
src_conn.row_factory = sqlite3.Row
sc = src_conn.cursor()

dst_conn = sqlite3.connect(SRC_DB)
dst_conn.row_factory = sqlite3.Row
dc = dst_conn.cursor()

# 同步spec_series
series_copied = 0
for brand in new_brands:
    sc.execute("SELECT * FROM spec_series WHERE brand=?", (brand,))
    for row in sc.fetchall():
        # 检查目标是否已有
        dc.execute("SELECT id FROM spec_series WHERE brand=? AND series_name=?", (row['brand'], row['series_name']))
        existing = dc.fetchone()
        if existing:
            continue
        # 插入
        dc.execute("""INSERT INTO spec_series
                     (brand, brand_name, series_name, series_url, models, spec_url, captured_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (row['brand'], row['brand_name'], row['series_name'],
                     row['series_url'], row['models'], row['spec_url'], row['captured_at']))
        series_copied += 1

print(f"同步spec_series: {series_copied}条")

# 同步spec_row
row_copied = 0
for brand in new_brands:
    sc.execute("""SELECT sr.* FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    for row in sc.fetchall():
        # 在目标DB中找对应的series_id
        dc.execute("SELECT id FROM spec_series WHERE brand=? AND series_name=?",
                    (brand, dict(row).get('series_name', '')))
        # 如果找不到series_name,用brand+series_id匹配
        # 先获取source series的brand和series_name
        sc2 = src_conn.cursor()
        sc2.execute("SELECT brand, series_name FROM spec_series WHERE id=?", (row['series_id'],))
        src_series = sc2.fetchone()
        if not src_series:
            continue
        dc.execute("SELECT id FROM spec_series WHERE brand=? AND series_name=?",
                    (src_series['brand'], src_series['series_name']))
        dst_series = dc.fetchone()
        if not dst_series:
            continue
        dst_series_id = dst_series['id']

        # 检查是否已存在
        dc.execute("SELECT id FROM spec_row WHERE series_id=? AND item_ja=?",
                    (dst_series_id, row['item_ja']))
        if dc.fetchone():
            continue

        dc.execute("""INSERT INTO spec_row
                     (series_id, category, item_ja, item_zh, row_order, values_json, captured_week, captured_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (dst_series_id, row['category'], row['item_ja'], row['item_zh'],
                     row['row_order'], row['values_json'], row['captured_week'], row['captured_at']))
        row_copied += 1

print(f"同步spec_row: {row_copied}条")

dst_conn.commit()

# 2. 把这些新型号加入dim_product_model
print("\n=== 添加新型号到dim_product_model ===")
for brand in new_brands:
    sc.execute("SELECT models FROM spec_series WHERE brand=?", (brand,))
    all_models = set()
    for r in sc.fetchall():
        try:
            all_models.update(json.loads(r[0]) if r[0] else [])
        except: pass

    added = 0
    for mc in all_models:
        if not mc or len(mc) < 3:
            continue
        dc.execute("SELECT model_id FROM dim_product_model WHERE model_code=?", (mc,))
        if dc.fetchone():
            continue
        # 确定brand_raw
        brand_raw = brand.replace('_', '（') + '）'
        brand_name = brand.split('_')[0].upper()
        if brand.startswith('samsung'):
            brand_name = 'Samsung'
        elif brand.startswith('sony'):
            brand_name = 'Sony'
        elif brand.startswith('tcl'):
            brand_name = 'TCL'
        dc.execute("""INSERT OR IGNORE INTO dim_product_model
                     (model_code, brand, brand_raw, series_code, size_inch)
                     VALUES (?, ?, ?, ?, ?)""",
                    (mc, brand_name, brand_raw, brand, None))
        if dc.rowcount > 0:
            added += 1
    if added > 0:
        print(f"  {brand}: 新增{added}个型号到dim_product_model")

dst_conn.commit()

# 3. 重新生成fact_spec_value for these models
print("\n=== 生成fact_spec_value ===")
# 获取映射
dc.execute("SELECT source_term, param_id FROM dim_spec_item_map WHERE source_table='spec_row'")
item_map = {r['source_term']: r['param_id'] for r in dc.fetchall()}

fact_inserted = 0
for brand in new_brands:
    sc.execute("""SELECT sr.item_ja, sr.values_json, ss.brand, ss.series_name
                 FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    for item_ja, values_json, sbrand, sname in sc.fetchall():
        param_id = item_map.get(item_ja)
        if not param_id:
            continue
        try:
            vj = json.loads(values_json) if values_json else {}
        except:
            continue
        for mc, raw_val in vj.items():
            if not raw_val or str(raw_val).strip() in ('', '-', '—', '－'):
                continue
            # 找model_id
            dc.execute("SELECT model_id FROM dim_product_model WHERE model_code=?", (mc,))
            r = dc.fetchone()
            if not r:
                continue
            mid = r['model_id']
            val_str = str(raw_val).strip()
            if len(val_str) > 200:
                continue
            dc.execute("""INSERT OR IGNORE INTO fact_spec_value
                         (model_id, param_id, value_text, source_table, source_term, confidence, captured_at)
                         VALUES (?, ?, ?, 'spec_row', ?, 0.9, datetime('now'))""",
                        (mid, param_id, val_str, item_ja))
            if dc.rowcount > 0:
                fact_inserted += 1

dst_conn.commit()
print(f"  生成fact_spec_value: {fact_inserted}条")

# 4. 统计
dc.execute("SELECT COUNT(*) FROM fact_spec_value")
print(f"\n源DB fact_spec_value总计: {dc.fetchone()[0]}")
dc.execute("SELECT COUNT(*) FROM spec_row")
print(f"源DB spec_row总计: {dc.fetchone()[0]}")
dc.execute("SELECT COUNT(*) FROM spec_series")
print(f"源DB spec_series总计: {dc.fetchone()[0]}")
dc.execute("SELECT COUNT(*) FROM dim_product_model")
print(f"源DB dim_product_model总计: {dc.fetchone()[0]}")

src_conn.close()
dst_conn.close()
