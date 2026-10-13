# -*- coding: utf-8 -*-
"""P0-2: 查 TCL 无 JPY 价格的 9 个型号，尝试从 kakaku.com 补爬"""
import os
import sqlite3, sys, json, urllib.request, re, time
sys.stdout.reconfigure(encoding='utf-8')
DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. 查 TCL 无 JPY 价格的型号
c.execute("""SELECT DISTINCT m.model_code, m.model_id
             FROM dim_product_model m
             WHERE m.brand_raw LIKE '%日本%' AND m.brand='TCL'
             AND m.model_code NOT IN (
                 SELECT DISTINCT p.model FROM product p
                 JOIN price_snapshot ps ON ps.product_id=p.id
                 WHERE p.model=m.model_code AND ps.currency='JPY'
             )
             ORDER BY m.model_code""")
no_jpy = c.fetchall()
print(f"TCL 无 JPY 价格的型号: {len(no_jpy)}个")
for r in no_jpy:
    print(f"  {r['model_code']} (model_id={r['model_id']})")

# 2. 检查这些型号是否已有 product 记录（其他货币）
print(f"\n各型号已有的 product 记录:")
for r in no_jpy:
    mc = r['model_code']
    c.execute("""SELECT p.id, p.title, ps.price, ps.currency
                 FROM product p
                 JOIN price_snapshot ps ON ps.product_id=p.id
                 WHERE p.model=? ORDER BY ps.price""", (mc,))
    rows = c.fetchall()
    if rows:
        print(f"\n  {mc}:")
        for pr in rows[:3]:
            print(f"    {pr['price']} {pr['currency']}  {str(pr['title'])[:40]}")
    else:
        print(f"  {mc}: 无任何价格记录")

conn.close()
