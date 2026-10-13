# -*- coding: utf-8 -*-
"""确认 spec_row 型号与 product.model 的关联覆盖率。"""
import os
import sqlite3, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
db = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# 取 product 表所有型号（去空白）
c.execute("SELECT DISTINCT model FROM product WHERE model IS NOT NULL AND model != ''")
prod_models = set(r[0] for r in c.fetchall())
print(f'product 表去重型号数: {len(prod_models)}')

# 取 spec_row.values_json 里的所有型号
c.execute("SELECT values_json FROM spec_row WHERE values_json IS NOT NULL AND values_json != ''")
spec_models = set()
matched = 0; total = 0
for (vj,) in c.fetchall():
    try:
        d = json.loads(vj)
    except:
        continue
    for k in d.keys():
        total += 1
        spec_models.add(k)
        if k in prod_models:
            matched += 1

print(f'spec_row.values_json 出现的型号数（去重）: {len(spec_models)}')
print(f'spec 型号在 product 表中能匹配的次数: {matched} / {total}')

# 看未匹配的型号样例
unmatched = [m for m in spec_models if m not in prod_models][:20]
print(f'\n未匹配型号样例: {unmatched}')

# 看 product.size 分布
c.execute("SELECT size, COUNT(*) FROM product WHERE size IS NOT NULL AND size != '' GROUP BY size ORDER BY 2 DESC LIMIT 15")
print('\nproduct.size 分布:')
for r in c.fetchall():
    print(f'  {r[0]!r}: {r[1]}')

# 看 product.brand 归一化需求（大小写）
c.execute("SELECT brand, COUNT(DISTINCT model) FROM product GROUP BY brand ORDER BY 2 DESC LIMIT 15")
print('\nproduct.brand 分布（需归一大小写）:')
for r in c.fetchall():
    print(f'  {r[0]!r}: {r[1]} 型号')

conn.close()
