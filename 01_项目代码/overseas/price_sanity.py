"""电视价格合理性检查（缺价 > 错价）。

用于小样实测与自动修复的验收：抽到的数字如果低于该币种「最便宜电视」的量级，
大概率是分期月供、运费、评分、配件价或「起价」占位，不能当成该型号的价格入库。

阈值是**下限的数量级估计**（32 吋入门电视在当地的大致最低售价再打折），
只用来拦明显错误，不做精细判断。
"""
from __future__ import annotations

# 币种 → 电视价格下限（含税零售价的保守下限）
MIN_TV_PRICE: dict[str, float] = {
    "USD": 70, "CAD": 90, "MXN": 1500, "PEN": 250, "COP": 250_000, "CLP": 60_000,
    "BOB": 500, "GTQ": 600, "ARS": 80_000, "EUR": 70, "GBP": 60, "CHF": 70,
    "PLN": 300, "CZK": 1_800, "HUF": 25_000, "RON": 350, "BGN": 140, "SEK": 800,
    "NOK": 800, "DKK": 550, "TRY": 2_500, "RUB": 7_000, "UAH": 2_500, "RSD": 8_000,
    "BAM": 140, "JPY": 9_000,
}


def check_prices(currency: str, samples: list[tuple[str, float | None]]) -> list[str]:
    """samples = [(型号, 价格)]。返回问题列表（空 = 未发现异常）。

    规则：
      1) 价格低于该币种电视下限 → 可疑（分期/运费/评分/配件价）；
      2) 两个及以上不同型号价格完全相同 → 可疑（页面通用「起价」/推荐位价被当成主价）。
    """
    problems: list[str] = []
    floor = MIN_TV_PRICE.get((currency or "").upper())
    vals = [(m, p) for m, p in samples if isinstance(p, (int, float))]
    if floor:
        low = [f"{m}={p:g}" for m, p in vals if p < floor]
        if low:
            problems.append(f"价格低于{currency}电视下限 {floor:g}：{', '.join(low)}")
    seen: dict[float, list[str]] = {}
    for m, p in vals:
        seen.setdefault(round(float(p), 2), []).append(m)
    dup = [f"{'/'.join(ms)}={p:g}" for p, ms in seen.items() if len(set(ms)) > 1]
    if dup:
        problems.append("不同型号价格完全相同：" + "; ".join(dup))
    return problems
