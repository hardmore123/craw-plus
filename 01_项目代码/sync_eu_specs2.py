# -*- coding: utf-8 -*-
import os
import sqlite3, sys, json
sys.stdout.reconfigure(encoding='utf-8')

CRAWL_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
SRC_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")

new_brands = ['samsung_de','samsung_fr','samsung_it','sony_de','sony_fr','sony_it','tcl_de','tcl_fr','tcl_it']

src_conn = sqlite3.connect(CRAWL_DB)
sc = src_conn.cursor()

dst_conn = sqlite3.connect(SRC_DB)
dc = dst_conn.cursor()

# 查spec_series列名
sc.execute("PRAGMA table_info(spec_series)")
crawl_cols = [r[1] for r in sc.fetchall()]
print(f"crawl DB spec_series列: {crawl_cols}")

dc.execute("PRAGMA table_info(spec_series)")
src_cols = [r[1] for r in dc.fetchall()]
print(f"src DB spec_series列: {src_cols}")

# 同步spec_series
series_copied = 0
for brand in new_brands:
    sc.execute("SELECT * FROM spec_series WHERE brand=?", (brand,))
    cols = [d[0] for d in sc.description]
    for row in sc.fetchall():
        row_dict = dict(zip(cols, row))
        brand_val = row_dict.get('brand', '')
        sname = row_dict.get('series', '')
        dc.execute("SELECT id FROM spec_series WHERE brand=? AND series=?", (brand_val, sname))
        if dc.fetchone():
            continue
        dc.execute("""INSERT INTO spec_series
                     (brand, brand_name, series, url, models, first_seen, last_seen)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (brand_val, row_dict.get('brand_name'), sname,
                     row_dict.get('url'), row_dict.get('models'),
                     row_dict.get('first_seen'), row_dict.get('last_seen')))
        series_copied += 1

print(f"同步spec_series: {series_copied}条")

# 同步spec_row
row_copied = 0
for brand in new_brands:
    sc.execute("""SELECT sr.* FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    cols = [d[0] for d in sc.description]
    for row in sc.fetchall():
        row_dict = dict(zip(cols, row))
        src_series_id = row_dict['series_id']

        # 找source series的brand和series_name
        sc2 = src_conn.cursor()
        sc2.execute("SELECT brand, series FROM spec_series WHERE id=?", (src_series_id,))
        src_series = sc2.fetchone()
        if not src_series:
            continue

        dc.execute("SELECT id FROM spec_series WHERE brand=? AND series=?",
                    (src_series[0], src_series[1]))
        dst_series = dc.fetchone()
        if not dst_series:
            continue
        dst_series_id = dst_series[0]

        dc.execute("SELECT id FROM spec_row WHERE series_id=? AND item_ja=?",
                    (dst_series_id, row_dict['item_ja']))
        if dc.fetchone():
            continue

        dc.execute("""INSERT INTO spec_row
                     (series_id, category, item_ja, item_zh, row_order, values_json, captured_week, captured_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (dst_series_id, row_dict.get('category'), row_dict['item_ja'],
                     row_dict.get('item_zh'), row_dict.get('row_order', 0),
                     row_dict['values_json'], row_dict.get('captured_week'),
                     row_dict.get('captured_at')))
        row_copied += 1

print(f"同步spec_row: {row_copied}条")
dst_conn.commit()

# 添加新型号到dim_product_model
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
        brand_name = brand.split('_')[0].upper()
        if brand.startswith('samsung'): brand_name = 'Samsung'
        elif brand.startswith('sony'): brand_name = 'Sony'
        elif brand.startswith('tcl'): brand_name = 'TCL'
        dc.execute("""INSERT OR IGNORE INTO dim_product_model
                     (model_code, brand, brand_raw)
                     VALUES (?, ?, ?)""",
                    (mc, brand_name, brand))
        if dc.rowcount > 0:
            added += 1
    if added > 0:
        print(f"  {brand}: 新增{added}个型号")

dst_conn.commit()

# 生成fact_spec_value
print("\n=== 生成fact_spec_value ===")
dc.execute("SELECT source_term, param_id FROM dim_spec_item_map WHERE source_table='spec_row'")
item_map = {r[0]: r[1] for r in dc.fetchall()}

fact_inserted = 0
for brand in new_brands:
    sc.execute("""SELECT sr.item_ja, sr.values_json
                 FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    for item_ja, values_json in sc.fetchall():
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
            dc.execute("SELECT model_id FROM dim_product_model WHERE model_code=?", (mc,))
            r = dc.fetchone()
            if not r:
                continue
            mid = r[0]
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

# 统计
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
