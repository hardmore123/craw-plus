"""LLM 分析模块：用聚好看模型(海信内网 OpenAI 兼容接口)解读上市预警信号。

接入说明：
  - 聚好看接口是海信内网(inner-apisix.hisense.com)，不走 OVERSEAS_PROXY，直连。
  - 已验证 deepseek-v4-flash 可用(deepseek-v3-jhk 报 No model permission)。
  - 用 openai 库(已装)，兼容 OpenAI 接口格式。
  - 调用时临时清空 HTTP_PROXY/HTTPS_PROXY，确保不走外网代理。

功能：
  1. analyze_launch_warning(alert) — 解读单条上市预警，输出自然语言简报
  2. analyze_competitor_trend(alerts) — 按竞品汇总近期动态，输出趋势简报
  3. batch_analyze(alerts) — 批量解读，每条预警一段简报

设计原则：
  - LLM 只读数据做解读，不修改库。解读结果可存可打印。
  - 提示词模板内置，避免用户手写 prompt。
  - 失败优雅降级：LLM 不通时返回规则式摘要(不阻塞)。
"""
from __future__ import annotations

import json
import os
import traceback
from typing import Any

# ── 聚好看模型配置 ───────────────────────────────────────────────────────────
# 内网接口，不走 OVERSEAS_PROXY。已验证 deepseek-v4-flash 可用。
# 凭据只走环境变量（原先明文写在这里，已移除）：
#   COMPINTEL_LLM_BASE_URL（默认聚好看内网网关）、COMPINTEL_LLM_API_KEY、COMPINTEL_LLM_USER_KEY
_BASE = os.environ.get("COMPINTEL_LLM_BASE_URL", "https://inner-apisix.hisense.com/higpt-new/v1")
_KEY = os.environ.get("COMPINTEL_LLM_API_KEY", "")
_UKEY = os.environ.get("COMPINTEL_LLM_USER_KEY", "")
MODEL_CONFIGS = {
    "deepseek-v4-flash": {"base_url": _BASE, "api_key": _KEY, "user_key": _UKEY},
    "qwen3-5-397b": {"base_url": _BASE, "api_key": _KEY, "user_key": _UKEY},
}

DEFAULT_MODEL = "deepseek-v4-flash"


def _get_client(model: str = DEFAULT_MODEL):
    """创建 OpenAI 客户端(直连内网，不走外网代理)。

    关键：临时清空 HTTP_PROXY/HTTPS_PROXY，否则 openai 库会走外网代理导致内网不可达。
    """
    from openai import OpenAI
    cfg = MODEL_CONFIGS.get(model)
    if not cfg:
        raise ValueError(f"不支持的模型: {model}，可选: {list(MODEL_CONFIGS)}")
    if not cfg["api_key"]:
        raise RuntimeError("未设置 COMPINTEL_LLM_API_KEY / COMPINTEL_LLM_USER_KEY 环境变量")
    return OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"]), cfg


def call_llm(prompt: str, model: str = DEFAULT_MODEL, system: str = "") -> str:
    """调用聚好看文本模型，返回完整响应文本。

    内部始终用 stream=True(部分接口强制流式)，收集完整文本返回。
    失败时返回空字符串(不抛异常，让调用方优雅降级)。

    ⚠ 必须绕过系统代理，且**必须在创建 client 之前**设好：
    httpx2 的 client 在构造时就缓存代理配置，事后改环境变量无效。
    清空 HTTP_PROXY/HTTPS_PROXY **并**设 NO_PROXY，否则 httpx 走系统代理
    导致内网域名 SSL 握手失败(`[SSL: UNEXPECTED_EOF_WHILE_READING]`)。
    """
    proxy_keys = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
    no_proxy_keys = ("NO_PROXY", "no_proxy")
    saved: dict[str, str] = {}
    for k in proxy_keys + no_proxy_keys:
        if k in os.environ:
            saved[k] = os.environ[k]
    # ① 先改环境（必须在建 client 前）
    for k in proxy_keys:
        os.environ[k] = ""
    no_proxy_val = "inner-apisix.hisense.com,10.18.217.60,localhost,127.0.0.1"
    for k in no_proxy_keys:
        os.environ[k] = no_proxy_val
    try:
        # ② 再建 client（此时读到的是无代理配置）
        client, cfg = _get_client(model)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system or "你是竞品情报分析助手，善于解读产品认证数据并给出上市预警判断。"},
                {"role": "user", "content": prompt},
            ],
            extra_query={"user_key": cfg["user_key"]},
            stream=True,
        )
        result = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                result += chunk.choices[0].delta.content
        return result
    except Exception:
        # 静默失败，返回空字符串让调用方降级
        return ""
    finally:
        # ③ 恢复环境变量
        for k in proxy_keys + no_proxy_keys:
            if k in saved:
                os.environ[k] = saved[k]
            else:
                os.environ.pop(k, None)


# ── 通用认证信号解读(支持 new_cert/new_fcc_id/eprel_new_reg) ──────────────────

# 各数据源的中文名 + 国家 + 认证类型描述
SOURCE_META = {
    "fcc": {"name": "FCC认证", "country": "美国", "cert_type": "无线电认证"},
    "eprel": {"name": "EPREL", "country": "欧盟", "cert_type": "能效注册"},
    "energystar": {"name": "ENERGY STAR", "country": "美国", "cert_type": "能效认证"},
    "anatel": {"name": "ANATEL", "country": "巴西", "cert_type": "电信认证"},
    "ic_ised": {"name": "IC/ISED", "country": "加拿大", "cert_type": "无线电认证"},
    "tuv": {"name": "TÜV Rheinland", "country": "欧盟", "cert_type": "安全认证"},
    "ul": {"name": "VDE/CB", "country": "欧盟", "cert_type": "CB安全认证"},
}


def analyze_cert_signal(alert_row: dict, cidb=None) -> str:
    """解读单条认证信号(new_cert/new_fcc_id/eprel_new_reg/launch_warning)。

    支持所有 7 个数据源,根据 source 字段生成对应的解读。
    alert_row 需含: source_id, brand, source, signal_type, details_json
    cidb: 可选,用于补充 description/auth_date 等字段
    """
    details = {}
    if alert_row.get("details_json"):
        try:
            details = json.loads(alert_row["details_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    brand = alert_row.get("brand", "")
    sid = alert_row.get("source_id", "")
    source = alert_row.get("source", "fcc")
    stype = alert_row.get("signal_type", "")
    desc = details.get("description", "")
    auth_date = details.get("auth_date", "")
    ptype = details.get("product_type", "")

    # 从 compintel_record 补充缺失字段
    if (not desc or not auth_date) and cidb is not None:
        rec = cidb.last_record(source, sid)
        if rec:
            if not desc:
                desc = rec.get("description") or ""
            if not auth_date:
                auth_date = rec.get("auth_date") or ""
            if not ptype:
                ptype = rec.get("product_group") or ""

    meta = SOURCE_META.get(source, {"name": source, "country": "", "cert_type": "认证"})
    model = details.get("model", "")

    # 根据信号类型定制解读侧重点
    if stype == "launch_warning":
        lead_days = details.get("lead_days")
        on_market = details.get("on_market", False)
        focus = f"提前量{lead_days}天,{'已在售' if on_market else '尚未在售'}"
        action = "建议重点关注其上市动向" if not on_market else "已上市,关注后续型号"
    elif stype == "eprel_new_reg":
        energy_class = details.get("energy_class", "")
        focus = f"能效等级={energy_class}" if energy_class else "能效注册"
        action = "关注该品牌在欧盟市场的能效合规布局"
    else:
        focus = meta["cert_type"]
        action = "关注该品牌在该国/地区的合规动态和后续产品线"

    prompt = f"""请基于以下竞品认证预警信号，用中文输出一段 100-200 字的简报解读：

【预警信号】
- 数据源: {meta['name']}({meta['country']} {meta['cert_type']})
- 竞品品牌: {brand}
- 认证/型号ID: {sid}
- 产品类型: {ptype}
- 产品描述: {desc}
- 型号: {model}
- 认证/注册日期: {auth_date}
- 信号特征: {focus}

【解读要求】
1. 判断该信号是否值得关注(认证日期越近 = 越值得关注)
2. 推测产品品类和目标市场({meta['country']})
3. 给出对产品团队的行动建议

请直接输出简报，不要加标题或多余格式。"""

    llm_result = call_llm(prompt)
    if llm_result:
        return llm_result.strip()

    # LLM 失败时降级为规则式摘要
    return (f"[规则式摘要] {brand} 在{meta['country']}获得{meta['name']}{meta['cert_type']},"
            f"ID={sid},型号={model},产品={desc or ptype}。"
            f"认证日{auth_date},{focus}。{action}。")


# ── 上市预警解读(旧接口,保持兼容) ─────────────────────────────────────────────

def analyze_launch_warning(alert_row: dict) -> str:
    """解读单条 launch_warning 上市预警，输出自然语言简报。

    alert_row 需含字段：source_id, brand, message, details_json
    返回：LLM 生成的解读文本(失败时返回规则式摘要)。
    """
    # 解析 details
    details = {}
    if alert_row.get("details_json"):
        try:
            details = json.loads(alert_row["details_json"])
        except (json.JSONDecodeError, TypeError):
            pass

    brand = alert_row.get("brand", "")
    sid = alert_row.get("source_id", "")
    ptype = details.get("product_type", "")
    lead_days = details.get("lead_days")
    auth_date = details.get("auth_date", "")
    desc = details.get("description", "")
    source = details.get("source", "fcc")
    on_market = details.get("on_market", False)

    # 构造 prompt
    prompt = f"""请基于以下竞品上市预警信号，用中文输出一段 100-200 字的简报解读：

【预警信号】
- 数据源: {('FCC认证(美国)' if source == 'fcc' else 'EPREL能效注册(欧盟)')}
- 竞品品牌: {brand}
- 产品类型: {ptype}
- 产品描述: {desc}
- 认证/注册日期: {auth_date}
- 提前量(距今天数): {lead_days} 天
- 在售状态: {'已在售' if on_market else '尚未在售(真预警)'}

【解读要求】
1. 判断这是否是一个值得重点关注的上市预警(认证日期越近、提前量越大、尚未在售 = 越值得关注)
2. 推测产品品类(电视/显示器/车载显示/后排娱乐等)
3. 给出对产品团队的行动建议(如"建议关注XX的新品动向""预计X月内可能上市")

请直接输出简报，不要加标题或多余格式。"""

    llm_result = call_llm(prompt)
    if llm_result:
        return llm_result.strip()

    # LLM 失败时降级为规则式摘要
    lead_text = f"提前{lead_days}天" if lead_days is not None else "提前量未知"
    status = "尚未在售" if not on_market else "已上市"
    return (f"[规则式摘要] {brand} 新{ptype} #{sid}，{desc}。"
            f"认证日{auth_date}，{lead_text}，{status}。"
            f"{'建议重点关注，预计近期可能上市。' if not on_market else '已上市，非新预警。'}")


def analyze_competitor_trend(alerts: list[dict], brand: str = "",
                              cidb=None) -> str:
    """按竞品汇总近期动态，输出趋势简报。

    alerts: 信号列表(每条含 source_id/brand/source/signal_type/message/details_json)
            支持 launch_warning/new_fcc_id/new_cert/eprel_new_reg 等所有信号类型
    brand: 指定竞品时只分析该品牌(空=全部)
    cidb:  可选 CompIntelDB 实例，用于补充缺失字段
    """
    # 过滤品牌
    if brand:
        alerts = [a for a in alerts if (a.get("brand") or "").lower() == brand.lower()]
    if not alerts:
        return f"无 {brand or '竞品'} 的认证预警数据。"

    # 提取关键信息汇总，补充缺失字段，去重(同一 source_id 只取一条)
    items = []
    seen_ids: set[str] = set()
    for a in alerts:
        sid = a.get("source_id", "")
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        details = {}
        try:
            details = json.loads(a.get("details_json") or "{}")
        except (json.JSONDecodeError, TypeError):
            pass
        source = a.get("source", "fcc")
        desc = details.get("description", "")
        auth_date = details.get("auth_date", "")
        # 从 compintel_record 补 description/auth_date
        if (not desc or not auth_date) and cidb is not None:
            rec = cidb.last_record(source, sid)
            if rec:
                if not desc:
                    desc = rec.get("description") or ""
                if not auth_date:
                    auth_date = rec.get("auth_date") or ""
        meta = SOURCE_META.get(source, {"name": source, "country": ""})
        items.append({
            "ID": sid,
            "品牌": a.get("brand", ""),
            "数据源": meta["name"],
            "国家": meta["country"],
            "产品类型": details.get("product_type", ""),
            "产品描述": desc,
            "批准时间": auth_date,
            "信号类型": a.get("signal_type", ""),
        })

    summary = json.dumps(items[:30], ensure_ascii=False, indent=2)  # 最多30条避免 prompt 过长
    n = len(items)
    if brand:
        prompt = f"""请基于以下{brand}品牌的竞品认证预警数据，输出一份该品牌的专项分析简报。

【{brand} 预警数据】(共 {n} 条，已去重，每条含认证ID/数据源/批准时间/产品描述)
{summary}

【输出格式要求】
第一部分「逐条明细」——按批准时间倒序排列，每行格式：
  • 批准时间 | 数据源 | 认证ID | 批准产品 | 可能上线时段
  例: • 2026-08-17 | FCC | 2ACCJB247 | 投影仪(Projector) | 2026年Q4
  (如产品描述为空，写"未标注")
  (可能上线时段根据认证日期推算，一般认证后2-4个月上市)

第二部分「总结分析」(200-300字)：
1. {brand}近期在各数据源的认证节奏(按月分布、密集时段)
2. 推测{brand}正在布局的产品方向和目标市场
3. 给出产品团队针对{brand}的行动建议

请直接输出，不要输出思考过程、不要加标题、不要解释你的推理。"""
    else:
        prompt = f"""请基于以下竞品认证预警数据，输出一份竞品趋势分析简报。

【预警数据】(共 {n} 条，每条含认证ID/数据源/批准时间/产品描述/品牌)
{summary}

【输出格式要求】
第一部分「逐条明细」——按品牌分组，每品牌内按批准时间倒序排列，每行格式：
  • 批准时间 | 数据源 | 认证ID | 批准产品 | 可能上线时段
  例: 【Samsung】
  • 2026-09-27 | FCC | A3LSMO200P | (产品描述) | 2026年Q4

第二部分「总结分析」(200-300字)：
1. 按竞品品牌分组，总结各品牌近期的认证动态
2. 指出哪个竞品动作最频繁/最值得关注
3. 给出产品团队的整体行动建议

请直接输出，不要输出思考过程、不要加标题、不要解释你的推理。"""

    llm_result = call_llm(prompt)
    if llm_result:
        return llm_result.strip()

    # 降级：规则式统计 + 逐条列表
    lines = [f"[规则式统计] 共 {len(items)} 条预警。", "逐条明细:"]
    for i in items:
        lines.append(f"  • {i['批准时间'] or '?'} | {i['数据源']} | {i['ID']} | {i['产品描述'] or '(无描述)'}")
    from collections import Counter
    brand_counts = Counter(i["品牌"] for i in items)
    source_counts = Counter(i["数据源"] for i in items)
    lines.append("品牌分布: " + ", ".join(f"{b} {n}条" for b, n in brand_counts.most_common()))
    lines.append("数据源分布: " + ", ".join(f"{s} {n}条" for s, n in source_counts.most_common()))
    return "\n".join(lines)


def batch_analyze(alerts: list[dict]) -> list[dict]:
    """批量解读上市预警，每条加 llm_analysis 字段。

    返回原 alerts 列表，每条增加 "llm_analysis" 字段(LLM 解读文本)。
    """
    out = []
    for a in alerts:
        analysis = analyze_launch_warning(a)
        a_copy = dict(a)
        a_copy["llm_analysis"] = analysis
        out.append(a_copy)
    return out
