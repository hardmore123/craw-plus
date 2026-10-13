"""卖点 MD 导出：一个品牌一个 Markdown 文档。

每个机型一节：
  - 页面地址 / 系列 / 机型 / 卖点数
  - 精炼卖点列表（refined_text，编号列表）
  - 结合 Spec 的 200 字卖点摘要（LLM 生成，缓存到 spec_md_summary 字段）

不输出原始卖点明细。
"""
from __future__ import annotations

import json
import os
import re

from .db import Database


def _iso_week(date=None) -> str:
    from datetime import date as _date
    d = _date.today().isocalendar()
    return f"{d[0]}-W{d[1]:02d}"


def _short_url(url: str) -> str:
    """去掉 /spec 后缀，得到产品页地址。"""
    if not url:
        return ""
    url = url.strip()
    if url.endswith("/spec"):
        url = url[: -len("/spec")]
    return url


_META_PREFIXES = ("由于", "请您", "请补充", "注：", "以下是", "基于此", "根据您", "抱歉", "素材")
_TRAIL_GARB = re.compile(r"[*_＊\s]*[（(]\d+\s*字[)）]\s*$")
_LEAD_ENUM = re.compile(r"^\d+[.、)）]\s*")


def _clean_refined(text: str) -> str:
    """精炼文本单行化：压掉 LLM 输出中的换行和解释性废话。"""
    if not text:
        return ""
    # 取第一行非空内容；若第一行以"由于/请您"等说明开头则取其后首个实质句
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    first = lines[0]
    if first.startswith(_META_PREFIXES):
        # 找粗体或后续第一个实质行
        for ln in lines[1:]:
            plain = _LEAD_ENUM.sub("", ln.strip()).strip("*_ \t")
            if plain and not plain.startswith(_META_PREFIXES):
                return _TRAIL_GARB.sub("", plain).rstrip("：:")
        return ""
    return _TRAIL_GARB.sub("", first)


def collect(db: Database, brand: str, week: str = "") -> list[dict]:
    """收集卖点 + spec URL，按系列排序。"""
    where = "brand = ?"
    params: list = [brand]
    if week:
        where += " AND captured_week = ?"
        params.append(week)
    rows = db.conn.execute(
        f"SELECT series, model, refined_text, captured_week FROM selling_point "
        f"WHERE {where} ORDER BY series, point_order, id",
        params,
    ).fetchall()

    series_map: dict[str, dict] = {}
    for r in rows:
        s = r["series"]
        if s not in series_map:
            series_map[s] = {"series": s, "model": r["model"] or s, "week": r["captured_week"], "points": []}
        p = _clean_refined(r["refined_text"] or "")
        if p:
            series_map[s]["points"].append(p)

    # spec URL（spec_series.url 存的是 /spec 页）
    out = []
    for s in sorted(series_map):
        info = series_map[s]
        url = ""
        try:
            r = db.conn.execute(
                "SELECT url FROM spec_series WHERE brand=? AND series=?", (brand, s)
            ).fetchone()
            url = r["url"] if r else ""
        except Exception:
            url = ""
        out.append({
            "series": s,
            "model": info["model"],
            "week": info["week"],
            "url": _short_url(url),
            "points": info["points"],
            "count": len(info["points"]),
        })
    return out


SUMMARY_PROMPT = (
    "你是电视产品营销专家。以下是「{model}」电视的规格参数和产品卖点：\n\n"
    "【规格】\n{spec_text}\n\n"
    "【卖点】\n{sp_text}\n\n"
    "请结合两者生成一段约200字的中文卖点摘要，要求：\n"
    "1. 只输出摘要正文，不要任何解释、前言或标题；\n"
    "2. 突出核心画质/音质/智能/设计卖点与关键规格数字；\n"
    "3. 语言凝练有吸引力，适合放进产品宣传文档。"
)


def _load_llm():
    try:
        from .llm_client import LLMClient
        return LLMClient()
    except ImportError:
        raise RuntimeError("LLM 客户端未安装（llm_client.py 不存在），跳过摘要生成")


def _spec_text_for_series(db: Database, brand: str, series: str, week: str) -> str:
    """拼接该系列 spec_row 为可读文本。"""
    try:
        rows = db.conn.execute(
            "SELECT sr.category, sr.item_ja, sr.item_zh, sr.values_json FROM spec_row sr "
            "JOIN spec_series s ON sr.series_id = s.id "
            "WHERE s.brand=? AND s.series=? ORDER BY sr.row_order",
            (brand, series),
        ).fetchall()
    except Exception:
        return ""
    lines = []
    for r in rows:
        item = (r["item_zh"] or r["item_ja"] or "").strip()
        vals = r["values_json"] or ""
        try:
            vd = json.loads(vals)
            if isinstance(vd, dict):
                vals = "；".join(f"{k}:{v}" for k, v in vd.items())
            elif isinstance(vd, list):
                vals = "；".join(str(x) for x in vd)
        except (json.JSONDecodeError, TypeError):
            pass
        cat = (r["category"] or "").strip()
        lines.append(f"{cat} {item} {vals}".strip())
    return "\n".join(lines)


def _sp_text_for_summary(points: list[str], fallback_titles: list[str]) -> str:
    pts = [p for p in points if p]
    if not pts:
        pts = fallback_titles
    return "；".join(pts)


def ensure_summaries(db: Database, brand: str, models: list[dict], refined_by: str = "llm",
                     use_llm: bool = True) -> int:
    """为每个系列生成/更新 spec_md_summary（LLM 200字摘要）。返回生成条数。

    已有摘要（spec_md_summary 非空且 refined_by 匹配）跳过，可重入。
    """
    # 轻量缓存表：key = brand+series
    db.conn.execute(
        "CREATE TABLE IF NOT EXISTS selling_point_md_summary ("
        "brand TEXT NOT NULL, series TEXT NOT NULL, summary TEXT, refined_by TEXT, "
        "captured_week TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
        "PRIMARY KEY(brand, series))"
    )
    db.conn.commit()

    if not use_llm:
        return 0
    llm = None
    done = 0
    for m in models:
        existing = db.conn.execute(
            "SELECT summary FROM selling_point_md_summary WHERE brand=? AND series=?",
            (brand, m["series"]),
        ).fetchone()
        if existing and (existing["summary"] or "").strip():
            m["summary"] = existing["summary"]
            continue
        if llm is None:
            llm = _load_llm()
        spec_text = _spec_text_for_series(db, brand, m["series"], m["week"])
        sp_text = _sp_text_for_summary(m["points"], [])
        if not spec_text and not sp_text:
            m["summary"] = ""
            continue
        prompt = SUMMARY_PROMPT.format(model=m["model"], spec_text=spec_text[:6000], sp_text=sp_text[:4000])
        try:
            resp = llm.chat([{"role": "user", "content": prompt}])
            summary = str(resp or "").strip()
        except Exception as e:
            print(f"  [WARN] {m['series']} 摘要失败: {e}")
            summary = ""
        summary = re.sub(r"\s+", " ", summary).strip()
        m["summary"] = summary
        if summary:
            db.conn.execute(
                "INSERT INTO selling_point_md_summary(brand, series, summary, refined_by, captured_week) "
                "VALUES(?,?,?,?,?) "
                "ON CONFLICT(brand, series) DO UPDATE SET summary=excluded.summary, "
                "refined_by=excluded.refined_by, captured_week=excluded.captured_week",
                (brand, m["series"], summary, refined_by, m["week"]),
            )
            db.conn.commit()
            done += 1
            print(f"  [SUM] {m['series']}: {len(summary)}字")
    return done


def render_md(brand: str, brand_name: str, models: list[dict]) -> str:
    """渲染 Markdown（无原始明细）。"""
    total_points = sum(m["count"] for m in models)
    lines = [
        f"# {brand_name} 卖点汇总",
        "",
        f"> 机型数: {len(models)}",
        f"> 卖点总数: {total_points}",
        "",
        "## 目录",
        "",
    ]
    for i, m in enumerate(models, 1):
        lines.append(f"{i}. [{m['model']}](#{_anchor(m['model'])}) — {m['count']} 个卖点")
    lines += ["", "---", ""]

    for m in models:
        lines += [
            f"## {m['model']}",
            "",
            f"- 页面地址: {m['url'] or '(未记录)'}",
            f"- 系列: {m['series']}",
            f"- 机型: {m['model']}",
            f"- 卖点数: {m['count']}",
            "",
            "### 精炼卖点列表",
            "",
        ]
        for j, p in enumerate(m["points"], 1):
            lines.append(f"{j}. {p}")
        lines += ["", "### 结合Spec的200字卖点摘要", ""]
        summary = (m.get("summary") or "").strip()
        if summary:
            lines.append(summary)
        else:
            lines.append("（待生成：运行 `sp-md` 时加 `--llm` 生成摘要）")
        lines += ["", "---", ""]
    return "\n".join(lines)


def _anchor(text: str) -> str:
    return re.sub(r"[^\w\-]+", "", text.lower()).strip("-") or "sec"


def export_md(db: Database, brand: str, path: str, week: str = "",
              use_llm: bool = True) -> tuple[int, int]:
    """导出 MD。返回 (机型数, 新生成摘要数)。"""
    if not week:
        r = db.conn.execute(
            "SELECT MAX(captured_week) AS w FROM selling_point WHERE brand=?", (brand,)
        ).fetchone()
        week = (r["w"] if r else "") or ""
    models = collect(db, brand, week=week)
    if not models:
        raise RuntimeError(f"品牌 {brand} 无卖点数据")
    brand_name = brand
    r = db.conn.execute(
        "SELECT brand_name FROM selling_point WHERE brand=? LIMIT 1", (brand,)
    ).fetchone()
    if r and r["brand_name"]:
        brand_name = r["brand_name"]
    n_sum = ensure_summaries(db, brand, models, use_llm=use_llm)
    md = render_md(brand, brand_name, models)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return len(models), n_sum
