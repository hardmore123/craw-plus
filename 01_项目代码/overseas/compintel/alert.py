"""竞品上市预警信号识别。

7 类基础信号：
  new_fcc_id          FCC    竞品新硬件已完成认证，上市在即(1-3月)
  confidential_expired FCC   竞品保密文件到期，技术细节将公开
  eprel_new_reg       EPREL  竞品新品完成欧盟合规注册，即将入欧
  energy_class_jump   EPREL  能效等级跃升，技术迭代完成
  eprel_delisted      EPREL  产品下架，可能停产或推替代型号
  supplier_change     两者   供应商/代工信息变更
  field_change        两者   同 source_id 字段级变化

上市预警（launch_warning）— 在基础信号之上叠加业务过滤，只留真正"新产品即将上市"信号：
  1. 产品类型过滤：只留电视/显示器相关（FCC description 关键词匹配）
  2. 在售状态比对：EPREL/在售库无对应型号 = 尚未上市 = 真预警
  3. 提前量计算：认证日期/注册日期距今的天数 = 提前上市多少天

实现策略：
  - new_fcc_id / eprel_new_reg：本次抓取出现、库中未见过的 source_id。
  - confidential_expired：本次 detail 抓到保密类文档(doc_type 含
    Internal Photos/Photos 且文件已可访问) → 保密期结束。
  - energy_class_jump：同一品牌+型号族，新记录能效等级比历史最佳高 ≥2 级。
  - eprel_delisted：EPREL 记录 status 变为非在售 / onMarketEnd 在近期。
  - supplier_change：同 source_id 历史快照中 applicant/organisation 与本次不同。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from .compintel_db import CompIntelDB

SIGNAL_TYPES = [
    "new_fcc_id", "confidential_expired", "eprel_new_reg",
    "energy_class_jump", "eprel_delisted", "supplier_change", "field_change",
    "new_cert",           # 通用新认证信号(energystar/anatel/ic_ised/tuv/ul)
    "launch_warning",
]

# 新数据源 → source 标识(与 schema.sql CHECK 约束一致)
NEW_SOURCES = {"energystar", "anatel", "ic_ised", "tuv", "ul"}

# 电视/显示器相关产品类型关键词（FCC description 字段小写匹配）
# 用这些词过滤掉手机/家电/可穿戴等非电视新品，只留电视/显示器类
TV_DISPLAY_KEYWORDS = [
    "tv", "television", "display", "monitor", "tuner",
    "oled", "qled", "led tv", "lcd tv", "smart tv",
    "uhd", "4k", "8k", "set-top", "stb", "media player",
    "rear seat entertainment", "digital signage", "projector",
]

# 非电视关键词（含这些词的 description 排除，即使含 tv 关键词）
# 例如 "TV Remote" 不是电视，是遥控器
EXCLUDE_KEYWORDS = [
    "remote", "remote control", "charger", "headset", "speaker",
    "phone", "handset", "wearable", "watch", "glasses",
    "lock", "thermostat", "appliance", "oven", "cooktop",
    "baby monitor", "module", "transceiver",
]

# 各数据源的产品类型匹配策略
# key=source, value=(匹配模式, 说明)
# "keywords": 用 description/product_group 做关键词匹配
# "pass": 该源的记录天然都是电视/显示器(如 EPREL 只抓 televisions/electronicdisplays)
# "model_keywords": 用 model 字段做关键词匹配(当 description 不可靠时)
SOURCE_PRODUCT_MATCH = {
    "fcc": "keywords",          # description 关键词匹配
    "eprel": "pass",             # 只抓 televisions/electronicdisplays
    "energystar": "keywords",    # ENERGY STAR 含显示器/电视,但也有很多非电视(洗衣机等),用关键词
    "anatel": "keywords",        # ANATEL 含大量非电视(手机/路由器等),用 description 关键词
    "ic_ised": "keywords",      # IC/ISED 同 ANATEL
    "tuv": "keywords",          # TÜV description=产品类型,用关键词
    "ul": "keywords",           # UL/VDE description=产品类型,用关键词
}

# 能效等级排序：A > B > ... > G
_ENERGY_ORDER = {"A": 7, "B": 6, "C": 5, "D": 4, "E": 3, "F": 2, "G": 1,
                 "A+++": 10, "A++": 9, "A+": 8, "": 0}


def _energy_rank(cls: str) -> int:
    return _ENERGY_ORDER.get((cls or "").strip().upper(), 0)


def detect_new_records(cidb: CompIntelDB, run_id: int,
                       source: str, records: list[dict]) -> list[dict]:
    """检测新出现的 source_id（new_fcc_id / eprel_new_reg / new_cert）。

    records: 本次抓取的记录 dict 列表。每条可带 is_new 标志（在插入前预判），
    避免插入后 seen_source_id 恒为 True。未带 is_new 时回退到查库。
    """
    # 信号类型映射: fcc→new_fcc_id, eprel→eprel_new_reg, 其他→new_cert
    if source == "fcc":
        stype = "new_fcc_id"
    elif source == "eprel":
        stype = "eprel_new_reg"
    else:
        stype = "new_cert"
    signals: list[dict] = []
    for r in records:
        sid = r.get("source_id", "")
        if not sid:
            continue
        is_new = r.get("is_new")
        if is_new is None:
            is_new = not cidb.seen_source_id(source, sid)
        if not is_new:
            continue
        applicant = r.get("applicant") or r.get("supplier_name") or ""
        brand = r.get("brand") or ""
        model = r.get("model") or r.get("model_identifier") or ""
        # 消息按 source 定制
        if source == "fcc":
            msg = f"FCC 新记录: {sid} | {applicant} | {model}"
        elif source == "eprel":
            msg = (f"EPREL 新注册: #{sid} | {applicant} | {model} | "
                   f"能效 {r.get('energy_class','?')}")
        else:
            source_name = source.upper().replace("_", "/")
            msg = f"{source_name} 新认证: {sid} | {applicant} | {model}"
        details = {"auth_date": r.get("auth_date") or r.get("first_publication_date") or "",
                   "energy_class": r.get("energy_class") or r.get("energy_class_sdr") or "",
                   "description": r.get("description", "")}
        cidb.add_alert(run_id, stype, source, level="alert",
                       applicant=applicant, brand=brand, model=model,
                       source_id=sid, message=msg, details=details)
        signals.append({"signal_type": stype, "source_id": sid, "applicant": applicant})
    return signals


def detect_confidential_expired(cidb: CompIntelDB, run_id: int,
                                fcc_id: str, docs: list[dict]) -> list[dict]:
    """检测 FCC 保密文件到期（内部照片等文件已可抓到 = 保密期结束）。"""
    signals: list[dict] = []
    confidential_types = {"internal photos", "internal photo", "external photos",
                          "external photo", "id label", "users manual"}
    for d in docs:
        dtype = (d.get("doc_type") or "").lower()
        if not any(c in dtype for c in confidential_types):
            continue
        msg = (f"FCC 保密文件到期: {fcc_id} 的 {d.get('doc_type')} "
               f"({d.get('doc_name','')}) 现已可访问")
        cidb.add_alert(run_id, "confidential_expired", "fcc", level="watch",
                       source_id=fcc_id, message=msg,
                       details={"doc_type": d.get("doc_type"),
                                "doc_name": d.get("doc_name"),
                                "doc_date": d.get("doc_date")})
        signals.append({"signal_type": "confidential_expired", "source_id": fcc_id})
        break   # 一个 FCC ID 一条信号即可
    return signals


def detect_supplier_change(cidb: CompIntelDB, run_id: int,
                           source: str, records: list[dict],
                           captured_at: str = "") -> list[dict]:
    """检测供应商信息变更：同 source_id 历史快照 applicant 与本次不同。

    captured_at: 本次抓取的时间戳。给定时用 before_captured_at 取"上一次"快照，
    避免插入后再查拿到本次自己（时序 bug 修复）。
    """
    signals: list[dict] = []
    for r in records:
        sid = r.get("source_id", "")
        if not sid:
            continue
        cur_app = (r.get("applicant") or r.get("supplier_name") or "").strip()
        if not cur_app:
            continue
        prev = cidb.last_record(source, sid, before_captured_at=captured_at)
        if not prev:
            continue
        prev_app = (prev.get("applicant") or "").strip()
        if prev_app and prev_app.lower() != cur_app.lower():
            msg = (f"{source.upper()} 供应商变更: {sid} {prev_app} → {cur_app}")
            cidb.add_alert(run_id, "supplier_change", source, level="watch",
                           applicant=cur_app, source_id=sid, message=msg,
                           details={"prev_applicant": prev_app, "new_applicant": cur_app})
            signals.append({"signal_type": "supplier_change", "source_id": sid})
    return signals


def detect_field_changes(cidb: CompIntelDB, run_id: int, source: str,
                         records: list[dict],
                         captured_at: str = "") -> list[dict]:
    """通用字段级变化检测：同一 source_id 本次 vs 上次快照的语义字段变化。

    产出 field_change 信号，details 记录变化的 (field, old, new) 列表。
    特别关注：energy_class 变化（能效升级/降级）、frequency 变化（频段重新设计）、
    market_start/market_end 变化（上市/退市日期调整）。
    这是 new_* / supplier_change 之外的细粒度变化追踪。
    """
    signals: list[dict] = []
    for r in records:
        sid = r.get("source_id", "")
        if not sid or not r.get("is_new", False) is False and r.get("is_new"):
            # 新记录没有"上次"可比，跳过
            pass
        if not sid:
            continue
        if r.get("is_new"):
            continue   # 新记录由 new_* 信号处理，无变化可对比
        prev = cidb.last_record(source, sid, before_captured_at=captured_at)
        if not prev:
            continue
        diffs = cidb.diff_records(prev, r)
        if not diffs:
            continue
        applicant = r.get("applicant") or ""
        brand = r.get("brand") or ""
        model = r.get("model") or ""
        changes = [{"field": f, "old": o, "new": n} for f, o, n in diffs]
        msg_parts = [f"{f}:{o}→{n}" for f, o, n in diffs[:4]]
        msg = f"{source.upper()} 字段变化: {sid} {brand} {model} | " + ", ".join(msg_parts)
        cidb.add_alert(run_id, "field_change", source, level="watch",
                       applicant=applicant, brand=brand, model=model,
                       source_id=sid, message=msg, details={"changes": changes})
        signals.append({"signal_type": "field_change", "source_id": sid,
                        "fields": [f for f, _, _ in diffs]})
    return signals


def detect_energy_class_jump(cidb: CompIntelDB, run_id: int,
                             brand: str, records: list[dict],
                             captured_at: str = "") -> list[dict]:
    """检测能效等级跃升：同品牌新记录能效等级比历史最佳高 ≥2 级。

    同时做记录级对比：同一 source_id 本次能效比上次高（单产品升级）也产出信号。
    records: 本次抓取的 EPREL 记录 dict 列表。
    """
    signals: list[dict] = []
    # 历史最佳能效（该品牌所有记录中最高等级）
    rows = cidb.conn.execute(
        "SELECT energy_class FROM compintel_record WHERE source='eprel' "
        "AND brand=? AND energy_class IS NOT NULL AND energy_class!=''",
        (brand,)).fetchall()
    hist_best = max((_energy_rank(r["energy_class"]) for r in rows), default=0) if rows else 0
    for r in records:
        ec = r.get("energy_class") or r.get("energy_class_sdr") or ""
        rank = _energy_rank(ec)
        if not rank:
            continue
        # 维度1：比该品牌历史最佳高 ≥2 级
        if hist_best and rank - hist_best >= 2:
            msg = (f"EPREL 能效跃升: {brand} {r.get('model','')} 从历史最佳 {hist_best}级 "
                   f"升至 {ec}（+{rank - hist_best}级）")
            cidb.add_alert(run_id, "energy_class_jump", "eprel", level="alert",
                           brand=brand, model=r.get("model", ""),
                           source_id=r.get("source_id", ""), message=msg,
                           details={"new_class": ec, "hist_best_rank": hist_best,
                                    "dimension": "brand_best"})
            signals.append({"signal_type": "energy_class_jump",
                            "source_id": r.get("source_id", "")})
            continue
        # 维度2：同 source_id 本次比上次高（单产品升级）
        sid = r.get("source_id", "")
        if not sid:
            continue
        prev = cidb.last_record("eprel", sid, before_captured_at=captured_at)
        if not prev:
            continue
        prev_ec = prev.get("energy_class") or ""
        prev_rank = _energy_rank(prev_ec)
        if prev_rank and rank > prev_rank:
            msg = (f"EPREL 能效升级: {brand} {r.get('model','')} {prev_ec} → {ec} "
                   f"（+{rank - prev_rank}级，同一产品 #{sid}）")
            cidb.add_alert(run_id, "energy_class_jump", "eprel", level="watch",
                           brand=brand, model=r.get("model", ""),
                           source_id=sid, message=msg,
                           details={"new_class": ec, "prev_class": prev_ec,
                                    "dimension": "same_product"})
            signals.append({"signal_type": "energy_class_jump", "source_id": sid})
    return signals


def detect_delisted(cidb: CompIntelDB, run_id: int,
                    records: list[dict],
                    captured_at: str = "") -> list[dict]:
    """检测 EPREL 产品下架。

    两个维度：
    1. 本次 status 变为非在售 / onMarketEnd 在近 30 天内（绝对状态）。
    2. 同 source_id 上次在售、本次变下架（状态变化，更准）。
    """
    signals: list[dict] = []
    now = datetime.now(timezone.utc)
    for r in records:
        sid = r.get("source_id", "")
        if not sid:
            continue
        status = (r.get("status") or "").lower()
        market_end = r.get("market_end") or r.get("on_market_end") or ""
        delisted = False
        reason = ""
        if status in ("delisted", "discontinued", "not on market", "off market"):
            delisted = True
            reason = f"status={status}"
        elif market_end:
            try:
                end = datetime.fromisoformat(market_end)
                if (now - end).days <= 30 and end <= now:
                    delisted = True
                    reason = f"market_end={market_end}"
            except ValueError:
                pass
        # 维度2：状态变化（上次在售 → 本次下架）
        if not delisted and not r.get("is_new"):
            prev = cidb.last_record("eprel", sid, before_captured_at=captured_at)
            if prev:
                prev_status = (prev.get("status") or "").lower()
                # 上次不是下架态、本次是 → 变化
                prev_on_market = prev_status not in (
                    "delisted", "discontinued", "not on market", "off market")
                cur_off_market = status in (
                    "delisted", "discontinued", "not on market", "off market")
                if prev_on_market and cur_off_market:
                    delisted = True
                    reason = f"status变化 {prev_status or 'on_market'} → {status}"
        if delisted:
            msg = (f"EPREL 产品下架: #{sid} {r.get('brand','')} {r.get('model','')} ({reason})")
            cidb.add_alert(run_id, "eprel_delisted", "eprel", level="watch",
                           brand=r.get("brand", ""), model=r.get("model", ""),
                           source_id=sid, message=msg, details={"reason": reason})
            signals.append({"signal_type": "eprel_delisted", "source_id": sid})
    return signals


# ---------------- 上市预警（launch_warning）----------------

def _match_product_type(description: str, product_group: str = "",
                         source: str = "", model: str = "") -> str | None:
    """判断记录是否电视/显示器类产品，返回匹配的关键词或 None。

    各数据源策略:
      EPREL: product_group=electronicdisplays 天然是显示器，直接通过。
      其他源: 用 description + model 做关键词匹配（排除手机/家电等）。
    """
    if source == "eprel":
        if product_group and "display" in product_group.lower():
            return "electronic_display"
        return None
    # 通用关键词匹配(适用于 fcc/energystar/anatel/ic_ised/tuv/ul)
    # 合并 description + model 做匹配(model 可能含 TV/显示器型号关键词)
    text = ((description or "") + " " + (model or "")).lower()
    if not text.strip():
        return None
    # 先排除非电视产品（即使含 tv 关键词）
    for ex in EXCLUDE_KEYWORDS:
        if ex in text:
            return None
    # 再匹配电视/显示器关键词
    for kw in TV_DISPLAY_KEYWORDS:
        if kw in text:
            return kw
    return None


def _parse_date(s: str) -> datetime | None:
    """解析 YYYY-MM-DD 或带时分秒的日期字符串。"""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _is_on_market(cidb: CompIntelDB, source: str, source_id: str,
                  brand: str, model: str) -> bool:
    """检查该产品是否已在售（在 product 表有对应型号）。

    EPREL 天然有 market_start 字段；FCC 无在售信息，靠品牌+型号关联 product 表。
    """
    # EPREL: 直接看 market_start 是否已过（已上市）
    if source == "eprel":
        rec = cidb.last_record("eprel", source_id)
        if rec and rec.get("market_start"):
            d = _parse_date(rec["market_start"])
            if d:
                d_naive = d.replace(tzinfo=None) if d.tzinfo else d
                return d_naive <= datetime.utcnow()
        return False
    # FCC: 认证 ≠ 在售。FCC 认证的是即将上市的产品,不能靠"品牌在 product 表有记录"
    # 判定在售(那会把所有竞品品牌的新认证都误判为已售)。
    # 只有当 FCC ID 本身出现在 product 表的 model 字段时才算在售(极少见)。
    if not source_id:
        return False
    try:
        row = cidb.conn.execute(
            "SELECT 1 FROM product WHERE model = ? LIMIT 1",
            (source_id,)).fetchone()
        return row is not None
    except Exception:
        return False


def detect_launch_warning(cidb: CompIntelDB, run_id: int,
                         records: list[dict], source: str,
                         now_str: str = "") -> list[dict]:
    """新产品上市预警：在基础 new_* 信号上叠加产品类型过滤 + 在售比对 + 提前量。

    只对"本次新出现的 + 电视/显示器类 + 尚未在售"的记录产出 launch_warning。
    这是把 new_fcc_id/eprel_new_reg（含大量噪声）升级为"真正可用的上市预警"。

    每条 launch_warning 包含：
    - product_type: 匹配的电视/显示器关键词
    - lead_days: 认证/注册日期距今天数（提前量）
    - on_market: 是否已在售（False = 尚未上市 = 真预警）
    """
    signals: list[dict] = []
    # 统一用 naive UTC，避免 offset-naive vs aware 相减报错
    now = datetime.utcnow()
    for r in records:
        if not r.get("is_new"):
            continue   # 只对新记录做上市预警
        sid = r.get("source_id", "")
        if not sid:
            continue
        # 1. 产品类型过滤(支持全数据源)
        desc = r.get("description") or ""
        group = r.get("product_group") or ""
        model = r.get("model") or ""
        ptype = _match_product_type(desc, group, source, model)
        if not ptype:
            continue   # 非电视/显示器，跳过
        # 2. 在售状态比对
        brand = r.get("brand") or r.get("applicant") or ""
        on_market = _is_on_market(cidb, source, sid, brand, model)
        # EPREL: market_start 是上市日期,近1年认证的新品即使已上市也生成预警(竞品新品信号)
        # 其他源: 已在售的跳过(只预警尚未上市的)
        if on_market and source != "eprel":
            continue   # 已在售，不是"即将上市"预警
        # 3. 提前量计算（认证/注册日期距今天数）
        date_field = "market_start" if source == "eprel" else "auth_date"
        ref_date_str = r.get(date_field) or r.get("auth_date") or r.get("market_start") or ""
        ref_date = _parse_date(ref_date_str)
        lead_days = None
        if ref_date:
            # ref_date 可能带时区也可能不带，统一转 naive 比较
            ref_naive = ref_date.replace(tzinfo=None) if ref_date.tzinfo else ref_date
            lead_days = (now - ref_naive).days
        # 4. 产出上市预警信号
        applicant = r.get("applicant") or ""
        lead_text = f"提前 {lead_days} 天" if lead_days is not None else "提前量未知"
        source_names = {"fcc": "FCC", "eprel": "EPREL", "energystar": "ENERGY STAR",
                        "anatel": "ANATEL", "ic_ised": "IC/ISED", "tuv": "TÜV", "ul": "VDE/CB"}
        src_name = source_names.get(source, source)
        product_label = "电视/显示器" if source in ("fcc", "eprel") else "电视/显示器类"
        msg = (f"[上市预警] {brand} 新{product_label} #{sid} | {src_name} | 类型:{ptype} | "
               f"{lead_text} | 认证日:{ref_date_str or '?'} | "
               f"{'尚未在售' if not on_market else '已上市'}")
        details = {
            "product_type": ptype,
            "lead_days": lead_days,
            "on_market": on_market,
            "auth_date": ref_date_str,
            "description": desc,
            "source": source,
        }
        cidb.add_alert(run_id, "launch_warning", source, level="alert",
                       applicant=applicant, brand=brand, model=model,
                       source_id=sid, message=msg, details=details)
        signals.append({"signal_type": "launch_warning", "source_id": sid,
                        "brand": brand, "lead_days": lead_days,
                        "product_type": ptype})
    return signals
