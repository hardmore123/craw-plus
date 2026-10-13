# -*- coding: utf-8 -*-
"""
1. 为新增欧洲品牌的spec_row item_ja自动匹配param_id
2. 重新生成fact_spec_value
3. 跨区域匹配欧洲零售站型号
"""
import os
import sqlite3, sys, json, re
from collections import defaultdict
sys.stdout.reconfigure(encoding='utf-8')
DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overseas.db")
conn = sqlite3.connect(DB)
c = conn.cursor()

new_brands = ['samsung_de','samsung_fr','samsung_it','sony_de','sony_fr','sony_it','tcl_de','tcl_fr','tcl_it']

# 1. 收集所有未映射的item_ja
c.execute("SELECT DISTINCT source_term FROM dim_spec_item_map WHERE source_table='spec_row'")
mapped = set(r[0] for r in c.fetchall())

unmapped_items = set()
for brand in new_brands:
    c.execute("""SELECT DISTINCT sr.item_ja FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    for r in c.fetchall():
        if r[0] and r[0] not in mapped:
            unmapped_items.add(r[0])

print(f"未映射的item_ja: {len(unmapped_items)}个")

# 2. 自动匹配规则：item_ja关键词 → param_id
PARAM_MAP = {
    'PEAK_BRIGHTNESS': 1, 'DIMMING_ZONES': 2, 'REFRESH_RATE': 3, 'CHIP': 4,
    'SYSTEM': 5, 'GAMING': 6, 'COLOR_GAMUT': 7, 'HDMI': 8, 'SCREEN_SIZE': 9,
    'RESOLUTION': 10, 'HDR': 11, 'CONTRAST': 12, 'WIFI': 13, 'BLUETOOTH': 14,
    'DOLBY_ATMOS': 15, 'POWER_CONSUMPTION': 16, 'WEIGHT': 17, 'DIMENSIONS': 18
}

# 关键词匹配规则
KEYWORD_RULES = [
    # (关键词列表, param_code)
    (['明るさ', '輝度', 'Helligkeit', 'Luminosité', 'Luminosità', 'Brightness', 'peak brightness', 'ピーク輝度'], 'PEAK_BRIGHTNESS'),
    (['バックライト', 'Backlight', 'Rétroéclairage', 'Retroilluminazione', 'dimming', 'ローカルディミング', 'Local Dimming', 'Zones de dimming'], 'DIMMING_ZONES'),
    (['リフレッシュレート', 'Refresh Rate', 'Bildwiederholrate', 'Taux de rafraîchissement', 'Frequenza di aggiornamento', 'Refresh-Rate', 'リフレッシュ'], 'REFRESH_RATE'),
    (['プロセッサ', 'Processor', 'Prozessor', 'Processeur', 'Processore', 'チップ', 'Chip', '画像処理'], 'CHIP'),
    (['OS', ' Betriebssystem', 'système d''exploitation', 'Sistema operativo', 'Smart TV', 'Smart-TV', 'OS-Version'], 'SYSTEM'),
    (['HDMI', 'HDMI端子', 'HDMI-Anschlüsse', 'HDMI-Eingänge', 'Port HDMI', 'Porte HDMI'], 'HDMI'),
    (['画面サイズ', 'Bildschirmgröße', 'Taille d''écran', 'Dimensioni schermo', 'Screen Size', 'Diagonale', '画面寸法', 'ディスプレイサイズ'], 'SCREEN_SIZE'),
    (['解像度', 'Auflösung', 'Résolution', 'Risoluzione', 'Resolution', '表示解像度', 'パネル解像度'], 'RESOLUTION'),
    (['HDR', 'High Dynamic Range', 'HDR10', 'Dolby Vision', 'HLG'], 'HDR'),
    (['コントラスト', 'Contrast', 'Kontrast', 'Rapport de contraste', 'Rapporto di contrasto'], 'CONTRAST'),
    (['Wi-Fi', 'WiFi', 'WLAN', 'WLAN-Standard', '無線LAN'], 'WIFI'),
    (['Bluetooth', 'ブルートゥース'], 'BLUETOOTH'),
    (['Dolby Atmos', 'ドルビーアトモス', 'Atmos'], 'DOLBY_ATMOS'),
    (['消費電力', 'Power Consumption', 'Stromverbrauch', 'Consommation électrique', 'Consumo elettrico', 'Energieverbrauch', '電力消費'], 'POWER_CONSUMPTION'),
    (['質量', 'Weight', 'Gewicht', 'Poids', 'Peso', '重量', '本体重量', '产品重量'], 'WEIGHT'),
    (['外形寸法', 'Dimensions', 'Abmessungen', 'Dimensions physiques', 'Dimensioni', 'Size', '本体寸法', '製品寸法', 'Set Dimensions', 'サイズ'], 'DIMENSIONS'),
    (['色域', 'Color Gamut', 'Farbumfang', 'Gamme de couleurs', 'Gamut colori'], 'COLOR_GAMUT'),
    (['GAMING', 'ゲーミング', 'VRR', 'ALLM', 'Game Mode', 'Gaming-Modus', 'Mode jeu'], 'GAMING'),
]

auto_mapped = 0
for item in unmapped_items:
    item_lower = item.lower()
    for keywords, pcode in KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in item_lower:
                param_id = PARAM_MAP[pcode]
                # 检查是否已存在
                c.execute("SELECT item_map_id FROM dim_spec_item_map WHERE source_table='spec_row' AND source_term=?", (item,))
                if c.fetchone():
                    break
                c.execute("""INSERT INTO dim_spec_item_map
                             (source_table, source_field, source_term, param_id, match_type, status, note)
                             VALUES ('spec_row', 'item_ja', ?, ?, 'EXACT', 'AUTO', ?)""",
                          (item, param_id, f'auto-matched: {pcode} (kw={kw})'))
                auto_mapped += 1
                break
        else:
            continue
        break

conn.commit()
print(f"自动映射: {auto_mapped}条")

# 3. 重新生成fact_spec_value for new brands
c.execute("SELECT source_term, param_id FROM dim_spec_item_map WHERE source_table='spec_row'")
item_map = {r[0]: r[1] for r in c.fetchall()}

fact_inserted = 0
for brand in new_brands:
    c.execute("""SELECT sr.item_ja, sr.values_json
                 FROM spec_row sr
                 JOIN spec_series ss ON ss.id = sr.series_id
                 WHERE ss.brand=?""", (brand,))
    for item_ja, values_json in c.fetchall():
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
            c.execute("SELECT model_id FROM dim_product_model WHERE model_code=?", (mc,))
            r = c.fetchone()
            if not r:
                continue
            c.execute("""INSERT OR IGNORE INTO fact_spec_value
                         (model_id, param_id, value_text, source_table, source_term, confidence, captured_at)
                         VALUES (?, ?, ?, 'spec_row', ?, 0.9, datetime('now'))""",
                        (r[0], param_id, str(raw_val).strip(), item_ja))
            if c.rowcount > 0:
                fact_inserted += 1

conn.commit()
print(f"新增fact_spec_value: {fact_inserted}条")
c.execute("SELECT COUNT(*) FROM fact_spec_value")
print(f"fact_spec_value总计: {c.fetchone()[0]}")

# 4. 跨区域匹配：欧洲零售站无规格型号 → 新同步的SPEC型号
print("\n=== 跨区域匹配 ===")
# 有规格的型号
c.execute("""SELECT DISTINCT m.model_code, m.model_id
             FROM dim_product_model m
             JOIN fact_spec_value f ON f.model_id = m.model_id""")
models_with_spec = {r[0]: r[1] for r in c.fetchall()}

def extract_core(mc):
    mc = mc.upper()
    mc = re.sub(r'\s*PRO$', '', mc)
    mc = re.sub(r'(STUK|QTUK|TUK)$', '', mc)
    mc = re.sub(r'(PUA|PSA|PSC|AUA|ZUA|ASG|AAA|B6B|B6A|B6LA|B6LC|6LA|6LC|6LB|6LE|6PSA|A6B|B6C|TSA|BSA|B3LA|74006L|74006|E3A|E6B|B3LA|UXZG|UXXC|UXZT|ZG|XC|ZT|ATXZG|AUXXC|ATXZT|HAUXZG|HAUXXC|HATXZT|HAEXZG|HAEXXC|HATXZT|FAEXZG|FAUXXC|FATXZT|FUXZG|FUXXC|FUXZT|EUXZG|EUXXC|EUXZT|PUAEP|PAEP|CEI|\.CEI)$', '', mc)
    return mc.strip().upper()

# 建核心码索引
core_index = defaultdict(list)
for mc in models_with_spec:
    core = extract_core(mc)
    if len(core) >= 5:
        core_index[core].append(mc)

total_matched = 0
total_copied = 0
for region, currency in [('EU','EUR'),('UK','GBP'),('CH','CHF'),('PL','PLN'),('SE','SEK'),('RO','RON'),('NO','NOK'),('DK','DKK'),('BG','BGN'),('RS','RSD'),('BA','BAM')]:
    c.execute("""SELECT DISTINCT m.model_code, m.model_id, m.brand
                 FROM dim_product_model m
                 WHERE m.model_code IN (
                     SELECT DISTINCT p.model FROM product p
                     JOIN price_snapshot ps ON ps.product_id=p.id
                     WHERE ps.currency=? AND p.model IS NOT NULL AND LENGTH(p.model) > 4
                     AND p.model NOT LIKE '%HTML%' AND p.model NOT LIKE '%/%'
                     AND p.model NOT LIKE 'REF=SR%'
                 )
                 AND m.model_id NOT IN (SELECT DISTINCT model_id FROM fact_spec_value)
                 """, (currency,))
    no_spec = c.fetchall()
    if not no_spec:
        continue

    matched = 0
    copied = 0
    for mc, mid, brand in no_spec:
        core = extract_core(mc)
        best = None
        if core in core_index:
            best = core_index[core][0]
        elif len(core) >= 6:
            for ci, models in core_index.items():
                if ci.startswith(core[:6]) or core.startswith(ci[:6]):
                    if abs(len(ci) - len(core)) <= 3:
                        best = models[0]
                        break

        if best and best != mc:
            src_mid = models_with_spec[best]
            c.execute("SELECT param_id, value_text, source_table, source_term, confidence, captured_at FROM fact_spec_value WHERE model_id=?", (src_mid,))
            for sf in c.fetchall():
                c.execute("""INSERT OR IGNORE INTO fact_spec_value
                             (model_id, param_id, value_text, source_table, source_term, confidence, captured_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (mid, sf[0], sf[1], 'cross_region_' + sf[2], sf[3] + f' (from {best})', 0.5, sf[4]))
                if c.rowcount > 0:
                    copied += 1
            matched += 1

    conn.commit()
    if matched > 0:
        print(f"  {region}: 匹配{matched} 复制{copied}条")
    total_matched += matched
    total_copied += copied

print(f"\n跨区域总计: 匹配{total_matched} 复制{total_copied}条")

# 最终覆盖率
for region, currency in [('EU','EUR'),('UK','GBP'),('CH','CHF'),('PL','PLN')]:
    c.execute("""SELECT COUNT(DISTINCT m.model_id) FROM dim_product_model m
                 WHERE m.model_code IN (
                     SELECT DISTINCT p.model FROM product p
                     JOIN price_snapshot ps ON ps.product_id=p.id
                     WHERE ps.currency=? AND p.model IS NOT NULL AND LENGTH(p.model) > 4
                     AND p.model NOT LIKE '%HTML%' AND p.model NOT LIKE '%/%' AND p.model NOT LIKE 'REF=SR%'
                 ) AND m.model_id IN (SELECT DISTINCT model_id FROM fact_spec_value)""", (currency,))
    with_spec = c.fetchone()[0]
    c.execute("""SELECT COUNT(DISTINCT p.model) FROM product p
                 JOIN price_snapshot ps ON ps.product_id=p.id
                 WHERE ps.currency=? AND p.model IS NOT NULL AND LENGTH(p.model) > 4
                 AND p.model NOT LIKE '%HTML%' AND p.model NOT LIKE '%/%' AND p.model NOT LIKE 'REF=SR%'""", (currency,))
    total = c.fetchone()[0]
    print(f"  {region}: {with_spec}/{total} ({with_spec/max(total,1)*100:.1f}%)")

conn.close()
