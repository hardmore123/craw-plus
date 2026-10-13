# -*- coding: utf-8 -*-
"""型号短码：SPEC 长型号 → 零售站可搜的短型号(真实机型码)。

背景：SPEC 明细的型号来自官网页面的 slug/标题串，零售站标题用的是真实机型码
（如 Hiraoka：'Televisor Hisense Smart TV 55" ULED 4K UHD 55U6ESG'）。用完整
SPEC 长号去零售站搜索会 0 命中或返回一批相似商品。

品牌差异：
  - Hisense EC/PE：官网 slug 形如 TELEVISOR-HISENSE-55-UHD-4-K-SMART-TV-55-A6-N-VIDAA
                      取「最后一个 \\d{1,3}[-_][A-Z0-9]+」并拼接 → 55A6N
  - Samsung 国际版：形如 M70H-55-INCH-4K-SMART-TV-UN55M70HAGXPE
                      取真实机型码 UN55M70HAGXPE（末尾 \\b(UN|QN|AU|MR|UA|RN)[A-Z0-9]+）
  - LG：机型码已是短码(100MRGB96BS / 98NU855BPS0...) → 原样保留
  - TCL：已短码(98C6K / 55A400-PRO) → 原样保留

对外接口：
    shorten(spec_model) -> str      # 候选短码（可能空）
    build_search_models(models) -> list[dict]  # 生成含短码的型号清单
"""
from __future__ import annotations

import re

_STOPWORDS = re.compile(
    r"\b(televisor|smart|tv|uhd|4k|hdr|google|mini|led|qled|oled|uled|hi|premium|"
    r"ultra|hd|fhd|video|destacado|inch|inches|pulgadas|with|soundbar|and|2026|modelo|samsung|hisense|lg|tcl)\b",
    re.I)

# 取末尾「(两位以上数字) 或 (字母+数字)」的机型码 token（55A6N / UN55M70HAGXPE / 100MRGB96BS）
_SHORT_RE = re.compile(r"\b(\d{1,4}[A-Z0-9]{2,12})\b")


def short_from_spec(spec_model: str) -> str:
    """把 SPEC 长型号降为候选短码；无法提取返回空串。

    策略（连字符/下划线 slug 分段，剔除无类型词后取真实机型码）：
      1. 已是短码（5~16位、含数字、无分隔符）→ 原样
      2. slug 按 -/_ 分段，剔除停用词段与纯"SMART-TV"类段，
         从剩余段中取「数字+字母」机型码段；多个时取最后一个
         （Samsung: ...SMART-TV-QN75QN70HAGXPE → QN75QN70HAGXPE；
          Hisense: ...TV-55-A6-N-VIDAA → 55A6N；若无则拼接末两段）
      3. 仍无 → 取末尾 \\d{1,4}[A-Z0-9]{2,} 机型码 token
    """
    s = (spec_model or "").strip()
    if not s:
        return ""
    # 1) 已是短码（无分隔符）
    if re.fullmatch(r"[A-Z0-9][A-Z0-9]{2,14}", s.upper()):
        return s
    # 2) slug 分段提取
    parts = [p for p in re.split(r"[-_]", s) if p]
    meaningful = [p for p in parts if p and not _STOPWORDS.fullmatch(p)]
    # 优先：段匹配「数字+字母」真实机型码（55A15 / UN55M70UX / 65UR8S）
    code_cands = []
    for p in meaningful:
        if re.fullmatch(r"(?:\d{1,4}[A-Z]{1,2})?\d{0,2}[A-Z0-9]{2,}", p, re.I) and \
           re.search(r"[A-Z]", p) and re.search(r"\d", p) and len(p) >= 3:
            code_cands.append(p)
    if code_cands:
        return code_cands[-1]
    # 4) 数字段 + 后续连续纯字母段拼接（55-A6-N → 55A6N；50-U6-ESG → 50U6ESG）
    #    避免把 VIDAA/VIDEO 等尾缀吞掉太多：只允许少量字母段。
    for i, seg in enumerate(meaningful):
        if not re.fullmatch(r"\d{1,4}", seg):
            continue
        j = i + 1
        tail = []
        # 段: 字母开头、含数字或无数字但 1~4 字符（型号段如 A6/N）；5+ 纯字母段
        # （VIDAA / GOOGLE / VIDEO）视为品牌词，自动断尾。
        while j < len(meaningful) and (
                re.fullmatch(r"[A-Z][A-Z0-9]{0,3}", meaningful[j]) or
                re.fullmatch(r"[A-Z]{1,4}", meaningful[j])):
            tail.append(meaningful[j])
            j += 1
        if tail:
            joined = (seg + "".join(tail)).upper()
            if len(joined) >= 4:
                return joined
    # 5) 仍无 → 取末尾机型 token
    m = re.search(r"(\d{1,4}[A-Z][A-Z0-9]{1,10})$", s.upper())
    if m:
        return m.group(1)
    return ""


def build_search_models(models: list[dict], *, need_short: bool = True) -> list[dict]:
    """从 SPEC 型号清单生成零售抓取用的搜索型号（含 short 字段）。

    models 每条: {brand_code, brand_name, model_raw}
    返回: 每条含 model_raw(短码) / spec_model(原始) / brand_code / brand_name。
    """
    out = []
    for m in models:
        raw = (m.get("model_raw") or "").strip()
        if not raw:
            continue
        short = short_from_spec(raw)
        if not short:
            continue
        out.append({
            "brand_code": m.get("brand_code") or "",
            "brand_name": m.get("brand_name") or "",
            "model_raw": short,          # 零售站搜索/匹配用短码
            "model_normalized": short,
            "spec_model": raw,           # 源 SPEC 型号
        })
    return out


if __name__ == "__main__":
    test = [
        ("TELEVISOR-HISENSE-50-UHD-4-K-SMART-TV-55-A6-N-VIDEO", "55A6N"),
        ("TELEVISOR-HISENSE-MINI-LED-HIGH-60HZ-55-UHD-SMART-GOOGLE-TV-55UR8S", "55UR8S"),
        ("M70N-55-INCH-4K-SMART-TV-UN55M70HAGXPE", "UN55M70HAGXPE"),
        ("QN70H-75-INCH-NEO-QLED-4K-MINI-LED-SMART-TV-QN75QN70HAGXPE", "QN75QN70HAGXPE"),
        ("65LX7B6EUA", "65LX7B6EUA"),
        ("98C6K", "98C6K"),
        ("SMART-TV-55-TCL-4K-QLED-MINI-LED-55C6K", "55C6K"),
        ("OLED55C6PSA", "OLED55C6PSA"),
        ("QN80H-85-INCH-NEO-QLED-4K-MINI-LED-SMART-TV-QN85QN80HAGXPE", "QN85QN80HAGXPE"),
        ("TV-HISENSE-QLED-MINILED-75-4K-75U6ESG-GOOGLE-TV", "75U6ESG"),
    ]
    ok = 0
    for src, exp in test:
        got = short_from_spec(src)
        mark = "OK" if got == exp else "X"
        if got == exp:
            ok += 1
        print(f"[{mark}] {src}\n      -> {got!r} (expect {exp!r})")
    print(f"\n{ok}/{len(test)} 通过")