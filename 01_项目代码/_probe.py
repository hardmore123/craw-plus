# -*- coding: utf-8 -*-
"""深度探查：为回填SQL收集真实数据。
1. spec_row.item_ja 按品牌分组，看每个param关键词能匹配多少
2. product_spec.key 按品牌分组
3. spec_row型号 vs product型号 关联方式
4. price_snapshot 取价方式"""
import os
import sqlite3, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
db = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(db)
c = conn.cursor()

# ---- 1. 各品牌的 item_ja 样例（看术语差异）----
print('=== 各品牌 spec_row 的 item_ja 样例（按品牌+参数关键词）===')
PARAM_KW = {
    'PEAK_BRIGHTNESS': ['ピーク輝度','最高輝度','輝度','Brightness','Peak','高輝度'],
    'DIMMING_ZONES': ['ローカルディミング','バックライト','Dimming','Mini-LED','Local Dimming','バックライト制御'],
    'REFRESH_RATE': ['リフレッシュ','倍速','Refresh','PANEL REFRESH','パネルリフレッシュ'],
    'CHIP': ['エンジン','プロセッサー','Processor','チップ','AI Picture','XR','AIPQ','IPQ'],
    'SYSTEM': ['システム','OS','Operating System','Tizen','webOS','Google TV','VIDAA','プラットフォーム','Android'],
    'GAMING': ['ゲームモード','ゲーム','Game','VRR','ALLM','FreeSync','G-SYNC'],
    'COLOR_GAMUT': ['色域','広色域','Color Gamut','量子ドット','QLED','DCI-P3','TRILUMINOS'],
    'HDMI': ['HDMI2.1','HDMI 2.1','HDMI端子','HDMI','eARC'],
    'HDR': ['HDR対応','HDR 支持','HDRフォーマット','HDR10','Dolby Vision','HLG','HDR'],
    'RESOLUTION': ['画素数','解像度','Resolution'],
    'CONTRAST': ['コントラスト','Contrast','对比度'],
    'WIFI': ['Wi-Fi','無線LAN','Wireless'],
    'BLUETOOTH': ['Bluetooth','ブルートゥース'],
    'DOLBY_ATMOS': ['Dolby Atmos','ドルビーアトモス','Dolby Atoms'],
    'POWER_CONSUMPTION': ['定格消費電力','消費電力','Power Consumption','Power'],
    'WEIGHT': ['本体質量','質量','Weight','重量'],
    'DIMENSIONS': ['外形寸法','寸法','Dimensions','Dimensions and weight'],
    'SCREEN_SIZE': ['画面サイズ','画面寸法','Screen Size','画面寸法'],
}

for param, kws in PARAM_KW.items():
    print(f'\n--- {param} ---')
    for kw in kws:
        c.execute("""SELECT ss.brand, COUNT(DISTINCT sr.item_ja), COUNT(*)
                     FROM spec_row sr JOIN spec_series ss ON ss.id=sr.series_id
                     WHERE sr.item_ja LIKE ? GROUP BY ss.brand""", (f'%{kw}%',))
        rows = c.fetchall()
        if rows:
            brands = ', '.join(f'{r[0]}({r[1]}种/{r[2]}行)' for r in rows[:6])
            print(f'  [{kw}] → {brands}')

# ---- 2. product_spec.key 的品牌分布 ----
print('\n\n=== product_spec.key 按 brand 分布（前30 key）===')
c.execute("""SELECT ps.key, p.brand, COUNT(*) n
             FROM product_spec ps JOIN product p ON p.id=ps.product_id
             GROUP BY ps.key, p.brand ORDER BY n DESC LIMIT 30""")
for r in c.fetchall():
    print(f'  {r[0]!r} [{r[1]}]: {r[2]}')

# ---- 3. 型号关联探查 ----
print('\n\n=== spec_series.models vs product.model 关联 ===')
# 取一个品牌的 spec_series.models 和 product.model 对比
for brand_pat in ['hisense','sony_jp']:
    print(f'\n--- {brand_pat} ---')
    c.execute("SELECT series, models FROM spec_series WHERE brand=? LIMIT 3", (brand_pat,))
    for r in c.fetchall():
        models_spec = json.loads(r[1])
        print(f'  spec_series: {r[0][:50]} → {models_spec}')
    c.execute("SELECT DISTINCT model FROM product WHERE brand LIKE ? LIMIT 5", (f'%{brand_pat.replace("_jp","")}%',))
    prods = [r[0] for r in c.fetchall()]
    print(f'  product.model: {prods}')

# ---- 4. price_snapshot 取价 ----
print('\n\n=== price_snapshot 样例 ===')
c.execute("""SELECT ps.product_id, p.brand, p.model, p.size, ps.price, ps.currency, ps.captured_at
             FROM price_snapshot ps JOIN product p ON p.id=ps.product_id
             WHERE p.brand LIKE '%isense%' LIMIT 5""")
for r in c.fetchall():
    print(f'  product_id={r[0]} brand={r[1]} model={r[2]} size={r[3]} price={r[4]} {r[5]} @{r[6]}')

conn.close()
