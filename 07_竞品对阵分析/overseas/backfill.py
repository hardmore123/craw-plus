# -*- coding: utf-8 -*-
"""待维护参数回溯补全引擎（真实数据版，无 AI 推断）。

三层递进回溯，全部只返回真实数据，AI 仅用于查找官网信息源：
  第1层 db   —— 在原始 spec_row/product_spec 里用精确关键词搜索真实记录的值
  第2层 site —— 调 spec_crawl 重抓官网规格页（真实抓取）
  第3层 ai   —— 调 AI 查找该型号的官网规格页 URL，供第2层真实抓取（AI 不产出规格值）

核心原则：
  - AI 永远不产出规格值，只查找"去哪里能抓到真实数据"
  - AI 找到 URL 后交给 spec_crawl 真实抓取，抓到的才入库
  - 找不到 URL 或抓取失败 → 诚实标记"待维护"，绝不编造

使用:
    from overseas.backfill import backfill_model_params
    result = backfill_model_params(model_id=2661, param_codes=['PEAK_BRIGHTNESS','DOLBY_ATMOS'])
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from typing import Any

sys.stdout.reconfigure(encoding='utf-8')

DEFAULT_DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "overseas.db")   # 唯一主库

# 18 参数的精确搜索关键词（用于第1层 db 回溯）
BACKFILL_KEYWORDS = {
    'PEAK_BRIGHTNESS': ['ピーク輝度', 'Peak Brightness', 'ピーク輝度( nit )', '最大輝度', 'peak brightness'],
    'DOLBY_ATMOS': ['ドルビーアトモス', 'Dolby Atmos', 'アトモス', '音声フォーマット', 'Dolby Atmos対応'],
    'CONTRAST': ['コントラスト比', 'Contrast Ratio', 'ダイナミックコントラスト', 'コントラスト 比', 'パネルコントラスト比'],
    'REFRESH_RATE': ['倍速対応', '倍速駆動', 'リフレッシュレート', 'Refresh Rate', 'Motion Rate', '倍速駆動(120Hz)', '駆動方式'],
    'COLOR_GAMUT': ['広色域', 'Color Gamut', '量子ドット', 'QLED', 'Wide Color Gamut', '広色域(WCG)', '広色域（WCG）', '量子ドット(QLED)'],
    'HDMI': ['HDMI', 'HDMI端子', '端子数', 'HDMI 4K/2K端子'],
    'HDR': ['HDR対応', 'HDR機能', 'HDR10', 'HDR Support', 'High Dynamic Range', 'HDR10/HLG対応', 'HDR Processing', 'HDR Formats'],
    'RESOLUTION': ['画素数', '画素数(水平×垂直)', '画素数(水平×垂直 画素)', '像素数', 'Resolution', '画 素 数'],
    'POWER_CONSUMPTION': ['定格消費電力', '消費電力', '定格消費電力(待機時消費電力)', '消費電力(W)', '待機時消費電力(W)', '待機時消費電力', 'Power Consumption'],
    'CHIP': ['エンジン', '映像エンジン', '映像処理エンジン', 'Processor', 'Picture Processor', 'チップ', 'IPQエンジン'],
    'SYSTEM': ['搭載OS', 'Operating System', 'Smart TV OS', 'システム', 'Smart Platform', 'Android TVTM OS9.0 Google アシスト搭載', 'Google TV'],
    'GAMING': ['ゲームモード', 'HDMI2.1仕様', 'Gaming', 'VRR', 'ALLM', 'ゲーム機能', 'ゲーム'],
    'DIMMING_ZONES': ['バックライト', 'バックライト方式', 'パネル', 'ローカルディミング', 'Local Dimming', 'Dimming Zones', 'パネルタイプ', 'Mini LED'],
    'WIFI': ['無線LAN内蔵', 'Wi-Fi内蔵', 'Wi-Fi Built in', 'Wi-Fi', 'Wireless LAN', '無線LAN対応'],
    'WEIGHT': ['梱包質量', '本体質量', '質量', 'スタンドあり(kg)', 'スタンドなし（kg）', 'スタンド除く(kg)', '本体重量、スタンド除く', '梱包カートン(kg)'],
    'DIMENSIONS': ['外形寸法', '外形寸法(幅×奥行×高さ)', 'スタンド含まない(cm)', 'スタンド含む(cm)', 'Dimensions', '画面寸法(mm)', 'スタンドあり(mm)', 'スタンド除く(mm)', '梱包カートン(mm)', '梱包寸法(mm)'],
    'BLUETOOTH': ['Bluetooth内蔵', 'Bluetoothイヤホン', 'Bluetooth', 'ブルートゥース', 'Bluetooth ®'],
    'SCREEN_SIZE': ['画面サイズ', '画面サイズ(横×縦/対角)', 'パネルサイズ', 'Screen Size'],
}

# brand_raw → adapter code 映射（日本线）
BRAND_TO_ADAPTER = {
    'hisense_jp': 'hisense_jp', 'Hisense': 'hisense_jp',
    'sony_jp': 'sony_jp', 'Sony': 'sony_jp',
    'regza_jp': 'regza_jp', 'REGZA': 'regza_jp', 'Toshiba': 'regza_jp',
    'sharp_jp': 'sharp_jp', 'Sharp': 'sharp_jp',
    'panasonic_jp': 'panasonic_jp', 'Panasonic': 'panasonic_jp',
    'tcl_jp': 'tcl_jp', 'TCL': 'tcl_jp',
}


def backfill_model_params(model_id: int, param_codes: list[str],
                          db_path: str = DEFAULT_DB,
                          skip_ai: bool = False) -> dict[str, dict]:
    """对指定型号缺失参数三层回溯补全。

    skip_ai=True 时跳过第3层 AI 查找URL（全库批量溯源用）。
    Returns: {param_code: {'value':str, 'source':'db'|'site'|'ai_url'|'none',
                           'confidence':float, 'detail':str}}
    """
    results = {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    c = conn.cursor()
    c.execute("SELECT model_id, brand, model_code, brand_raw FROM dim_product_model WHERE model_id=?", (model_id,))
    model = c.fetchone()
    if not model:
        conn.close()
        return {p: {'value': '', 'source': 'none', 'confidence': 0, 'detail': '型号不存在'} for p in param_codes}

    model_code = model['model_code']
    brand_raw = model['brand_raw'] or model['brand']

    for param_code in param_codes:
        # 第1层：数据库精确回溯（真实值）
        val = _backfill_from_db(conn, model_id, model_code, param_code, brand_raw)
        if val and val.get('confidence', 0) >= 0.9:
            results[param_code] = val
            continue
        # 第2层：官网重抓标记
        site_val = _backfill_from_site(conn, model_id, model_code, brand_raw, param_code)
        # 第3层：AI 查找官网URL（不产出值，只找信息源）
        if skip_ai:
            if site_val:
                results[param_code] = site_val
            else:
                results[param_code] = {'value': '', 'source': 'none', 'confidence': 0,
                                       'detail': '数据库未找到（跳过AI查找URL）'}
        else:
            ai_val = _backfill_from_ai(conn, model_id, model_code, param_code, brand_raw)
            if ai_val and ai_val.get('confidence', 0) > 0:
                results[param_code] = ai_val
            elif site_val:
                results[param_code] = site_val
            else:
                results[param_code] = {'value': '', 'source': 'none', 'confidence': 0,
                                       'detail': '三层回溯均未找到真实数据源'}

    conn.close()
    return results


def _load_model_raw_specs(conn, model_code, brand_raw):
    """一次性取该型号所有原始规格文本，供第1层使用。"""
    cache_key = f'_raw_{model_code}'
    if hasattr(_load_model_raw_specs, cache_key):
        return getattr(_load_model_raw_specs, cache_key)
    result = {'spec_row': {}, 'product_spec': {}}
    c = conn.cursor()
    try:
        c.execute("SELECT sr.item_ja, sr.values_json FROM spec_row sr WHERE sr.values_json LIKE ?", (f'%{model_code}%',))
        for row in c.fetchall():
            try:
                values = json.loads(row['values_json'])
                for mc, val in values.items():
                    if mc.strip() == model_code and val and val not in ('', '-', '—', 'ー'):
                        result['spec_row'][row['item_ja']] = val
            except (json.JSONDecodeError, TypeError):
                pass
    except Exception:
        pass
    try:
        c.execute("SELECT ps.key, ps.value FROM product_spec ps JOIN product p ON p.id=ps.product_id WHERE p.model=?", (model_code,))
        for row in c.fetchall():
            if row['value'] and row['value'] not in ('', '-', '—'):
                result['product_spec'][row['key']] = row['value']
    except Exception:
        pass
    setattr(_load_model_raw_specs, cache_key, result)
    return result


def _backfill_from_db(conn, model_id, model_code, param_code, brand_raw=''):
    """第1层：在原始 spec_row/product_spec 里用精确关键词搜索真实值。"""
    keywords = BACKFILL_KEYWORDS.get(param_code, [])
    if not keywords:
        return None
    raw = _load_model_raw_specs(conn, model_code, brand_raw)
    for item_ja, val in raw['spec_row'].items():
        for kw in keywords:
            if kw in item_ja:
                return {'value': str(val), 'source': 'db', 'confidence': 0.95,
                        'detail': f'原始spec_row命中: item_ja={item_ja!r}'}
    for key, val in raw['product_spec'].items():
        for kw in keywords:
            if kw in key:
                return {'value': str(val), 'source': 'db', 'confidence': 0.95,
                        'detail': f'原始product_spec命中: key={key!r}'}
    return None


_ADAPTER_CACHE = {}


def _backfill_from_site(conn, model_id, model_code, brand_raw, param_code):
    """第2层：标记可调 spec_crawl 重抓官网（真实抓取）。"""
    adapter_code = _infer_adapter_code(brand_raw, model_code)
    if not adapter_code:
        return None
    if adapter_code not in _ADAPTER_CACHE:
        try:
            from overseas.sites import SiteRegistry
            adapter = SiteRegistry.get(adapter_code)
            _ADAPTER_CACHE[adapter_code] = bool(getattr(adapter, 'supports_spec', False))
        except Exception:
            _ADAPTER_CACHE[adapter_code] = False
    if not _ADAPTER_CACHE[adapter_code]:
        return None
    c = conn.cursor()
    c.execute("""SELECT MAX(captured_at) FROM spec_row sr
                 JOIN spec_series ss ON ss.id=sr.series_id
                 WHERE ss.brand=? AND sr.values_json LIKE ?""",
              (adapter_code, f'%{model_code}%'))
    last = c.fetchone()[0]
    return {
        'value': '(待重抓)',
        'source': 'site',
        'confidence': 0.5,
        'detail': f'可调 spec_crawl --site {adapter_code} 重抓官网，上次抓取: {last or "无记录"}',
        'adapter_code': adapter_code,
        'needs_crawl': True
    }


def _backfill_from_ai(conn, model_id, model_code, param_code, brand_raw=''):
    """第3层：调 AI 查找该型号的官网规格页 URL。

    AI 的唯一任务：根据型号名+品牌，找出该型号在品牌官网的规格页 URL。
    AI 不产出任何规格值——找到 URL 后由 spec_crawl 真实抓取。
    如果 AI 找不到 URL，返回 confidence=0（不编造数据）。
    """
    adapter_code = _infer_adapter_code(brand_raw, model_code)
    if not adapter_code:
        return None

    try:
        from overseas.llm_client import LLMClient, LLMUnavailable
        client = LLMClient()
        if not client.configured:
            return {'value': '', 'source': 'ai_url', 'confidence': 0,
                    'detail': 'AI未配置，无法查找官网URL'}

        brand_name = {
            'hisense_jp': '海信(Hisense)日本', 'sony_jp': '索尼(Sony)日本',
            'sharp_jp': '夏普(Sharp)日本', 'panasonic_jp': '松下(Panasonic)日本',
            'tcl_jp': 'TCL日本', 'regza_jp': '东芝(REGZA)日本',
        }.get(adapter_code, adapter_code)

        prompt = f"""你是产品信息检索助手。请根据型号名找出该型号在品牌官网的规格页URL。

【严格规则】
1. 只返回你确信存在的官网规格页URL，不要编造
2. 如果不确定，回复：未找到|0|无法确认官网URL
3. 不要返回电商页、评测页，只要品牌官网的规格页

【返回格式】URL|置信度(0-1)|来源说明
例如：https://www.sharp.co.jp/tv/aquos/4t-c65hn2/|0.8|夏普官网AQUOS产品页

【型号】{model_code}
【品牌】{brand_name}
"""
        result = client.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=200)
        parts = result.strip().split('|')
        if len(parts) >= 2:
            url = parts[0].strip()
            conf = float(parts[1].strip()) if parts[1].strip().replace('.', '').isdigit() else 0
            detail = parts[2].strip() if len(parts) > 2 else 'AI查找URL'
            if '未找到' in url or conf == 0 or not url.startswith('http'):
                return {'value': '', 'source': 'ai_url', 'confidence': 0,
                        'detail': 'AI未找到可确认的官网URL，需人工查证'}
            # AI 找到 URL，但数据仍需 spec_crawl 真实抓取（AI 不产出值）
            return {
                'value': '(待重抓)',
                'source': 'ai_url',
                'confidence': conf,
                'detail': f'AI找到官网URL: {url}，需触发spec_crawl真实抓取',
                'adapter_code': adapter_code,
                'url': url,
                'needs_crawl': True
            }
        return {'value': '', 'source': 'ai_url', 'confidence': 0,
                'detail': f'AI返回格式异常: {result.strip()[:80]}'}
    except Exception as e:
        return {'value': '', 'source': 'ai_url', 'confidence': 0, 'detail': f'AI调用失败: {e}'}


def _infer_adapter_code(brand_raw, model_code):
    """从 brand_raw 或 model_code 推断 adapter code。"""
    brand_raw_lower = (brand_raw or '').lower()
    for key, adapter_code in BRAND_TO_ADAPTER.items():
        if key.lower() in brand_raw_lower:
            return adapter_code
    mc_upper = (model_code or '').upper()
    if mc_upper.startswith('K-'): return 'sony_jp'
    if mc_upper.startswith('4T-'): return 'sharp_jp'
    if mc_upper.startswith('TV-'): return 'panasonic_jp'
    if 'REGZA' in (brand_raw or '').upper() or 'REGZA' in mc_upper: return 'regza_jp'
    return None


def trigger_site_crawl(adapter_code, series_name, db_path=DEFAULT_DB):
    """触发第2层实际抓取：调 spec_crawl 抓指定系列。"""
    try:
        from overseas.scenarios import spec_crawl
        from overseas.db import Database
        db = Database(db_path)
        stats = spec_crawl(adapter_code, only_series=[series_name], db=db, verbose=True)
        return {'success': True, 'stats': {'pass': stats.pass_, 'fail': stats.fail}}
    except Exception as e:
        return {'success': False, 'error': str(e)}
