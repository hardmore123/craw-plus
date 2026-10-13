# -*- coding: utf-8 -*-
"""补入未入库型号到 dim_product_model + 同步 fact_spec_value

从 spec_series + product 表提取型号，按品牌设 brand_raw='XXX（日本）'，
确保 _region_filter('JP') 的 brand_raw LIKE '%日本%' 能命中。
"""
import os
import sqlite3, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 备份
import shutil
shutil.copy2(DB, DB.replace('.db', '_preimport_bak.db'))
print("已备份到 _preimport_bak.db")

# 品牌映射：adapter_code → (brand, brand_raw)
BRAND_MAP = {
    'sony_jp':      ('Sony', 'Sony（日本）'),
    'regza_jp':     ('REGZA', 'REGZA（日本）'),
    'hisense_jp':   ('Hisense', 'Hisense（日本）'),
    'tcl_jp':       ('TCL', 'TCL（日本）'),
    'panasonic_jp': ('Panasonic', '松下 VIERA（日本）'),
}

# 1. 取 dim_product_model 已有型号（避免重复）
c.execute("SELECT model_code FROM dim_product_model")
existing = set(r[0] for r in c.fetchall() if r[0])
print(f"dim_product_model 现有: {len(existing)}个型号")

# 2. 取 dim_spec_parameter 的 param_id 映射
c.execute("SELECT param_id, param_code FROM dim_spec_parameter")
code_pid = {r['param_code']: r['param_id'] for r in c.fetchall()}

# 3. 取 dim_spec_item_map 的 EXACT 映射（source_term → param_id）
c.execute("""SELECT source_term, param_id FROM dim_spec_item_map
             WHERE source_table='spec_row' AND match_type='EXACT' AND status='CONFIRMED'""")
sr_map = {r['source_term']: r['param_id'] for r in c.fetchall()}
print(f"spec_row 映射规则: {len(sr_map)}条")

# 4. 从 spec_series + product 提取型号，补入 dim_product_model
print("\n=== 补入 dim_product_model ===")
total_imported = 0
total_spec_written = 0

for ac, (brand, brand_raw) in BRAND_MAP.items():
    # 从 product 表取型号（有 brand 和 size 信息）
    c.execute("""
        SELECT DISTINCT p.model, p.brand, p.size, p.title
        FROM product p JOIN site s ON s.id=p.site_id
        WHERE s.code=? AND p.model IS NOT NULL AND p.model != ''
    """, (ac,))
    products = c.fetchall()

    imported = 0
    for p in products:
        mc = p['model'].strip()
        if mc in existing:
            continue
        # 解析尺寸
        size_inch = None
        size_raw = p['size'] or ''
        if size_raw:
            m = re.match(r'(\d+)', size_raw.replace('"', '').replace('V', ''))
            if m:
                size_inch = int(m.group(1))
        if not size_inch:
            # 从型号名提取尺寸（如 55U8S → 55, K-65XR70 → 65）
            m = re.match(r'(?:.*-)?(\d{2,3})[A-Z]', mc)
            if m:
                size_inch = int(m.group(1))
        
        c.execute("""INSERT INTO dim_product_model
            (brand, brand_raw, model_code, size_inch, size_raw, region, our_brand)
            VALUES (?, ?, ?, ?, ?, 'JP', 0)""",
            (brand, brand_raw, mc, size_inch, size_raw))
        existing.add(mc)
        imported += 1
        total_imported += 1

    print(f"  {ac:14s}  补入 {imported:3d}个  (product表{len(products)}个)")

conn.commit()
print(f"\n  总计补入: {total_imported}个型号")

# 5. 重新加载所有型号的 model_code → model_id
c.execute("SELECT model_id, model_code FROM dim_product_model")
mc_mid = {r['model_code']: r['model_id'] for r in c.fetchall()}

# 6. 取已有 fact_spec_value（避免重复）
c.execute("SELECT model_id, param_id FROM fact_spec_value")
existing_fv = set((r[0], r[1]) for r in c.fetchall())
print(f"fact_spec_value 现有: {len(existing_fv)}条")

# 7. 从 spec_row 提取规格值→入 fact_spec_value（对所有适配器）
print("\n=== 从 spec_row 提取规格值 ===")
for ac, (brand, brand_raw) in BRAND_MAP.items():
    written = 0
    c.execute("""
        SELECT sr.item_ja, sr.values_json
        FROM spec_row sr
        JOIN spec_series ss ON ss.id=sr.series_id
        WHERE ss.brand=?
    """, (ac,))
    for sr in c.fetchall():
        item_ja = sr['item_ja']
        if item_ja not in sr_map:
            continue
        pid = sr_map[item_ja]
        try:
            vals = json.loads(sr['values_json'])
        except:
            continue
        if not isinstance(vals, dict):
            continue
        for mc, val in vals.items():
            mc = mc.strip()
            if mc not in mc_mid or not val or str(val).strip() in ('', '-', '—', 'ー'):
                continue
            mid = mc_mid[mc]
            if (mid, pid) in existing_fv:
                continue
            c.execute("""INSERT OR REPLACE INTO fact_spec_value
                (model_id, param_id, value_text, source_table, source_term, captured_at)
                VALUES (?, ?, ?, 'spec_row', ?, datetime('now'))""",
                (mid, pid, str(val)[:500], item_ja))
            written += 1
            existing_fv.add((mid, pid))
            total_spec_written += 1
    print(f"  {ac:14s}  写入 {written:5d}条 spec")

conn.commit()
print(f"\n  总计写入: {total_spec_written}条 spec")

# 8. 最终统计
print("\n=== 最终统计 ===")
c.execute("""
    SELECT brand, brand_raw, COUNT(*) as cnt
    FROM dim_product_model
    WHERE region='JP'
    GROUP BY brand, brand_raw ORDER BY cnt DESC
""")
print("dim_product_model 日本线:")
for r in c.fetchall():
    print(f"  {r['brand']:20s} | {r['brand_raw']:25s} | {r['cnt']:4d}个")

c.execute("SELECT COUNT(*) FROM dim_product_model WHERE region='JP'")
total = c.fetchone()[0]
print(f"  日本线总计: {total}个")

c.execute("""
    SELECT brand, COUNT(DISTINCT f.model_id) as models, COUNT(*) as specs
    FROM fact_spec_value f
    JOIN dim_product_model m ON m.model_id=f.model_id
    WHERE m.region='JP'
    GROUP BY m.brand ORDER BY specs DESC
""")
print("\nfact_spec_value 日本线:")
for r in c.fetchall():
    print(f"  {r['brand']:20s}  {r['models']:4d}个型号  {r['specs']:5d}条spec")

c.execute("SELECT COUNT(*) FROM fact_spec_value")
print(f"  fact_spec_value 总计: {c.fetchone()[0]}条")

conn.close()
print("\n补入完成。")
