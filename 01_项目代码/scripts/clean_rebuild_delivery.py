# -*- coding: utf-8 -*-
"""南美欧洲价格全量交付表 清洗重建（修复审计发现的全部数据质量问题）。

清洗项：
  1. 价格：欧式小数解析(1.154,15 / 267,66 / 1,234.56)、剔0价、剔>1000万坏值
  2. 非TV剔除：estante/mueble/combo/parlante/barra de sonido/soundbar/soporte/rack/
     cable/control remoto/funda/stand/aire acond/refrigeradora/seguro/garantia 等
  3. 型号：垃圾(4GB/8LT/4KUHD/60HZ/120HZ/HD 等) 重提；空型号从标题提取
  4. 尺寸：从标题提取(55"/65"/75"等)
  5. 去重：(零售站, 型号, 商品名[:80])
输出 data/南美欧洲价格全量_清洗_最终交付.csv
"""
from __future__ import annotations

import csv
import io
import os
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

SRC = "data/南美欧洲价格全量_最终交付.csv"
OUT = "data/南美欧洲价格全量_清洗_最终交付.csv"

# 非电视关键词（标题命中即剔除）
NON_TV = (
    "soporte", "rack", "estante", "mueble", "mesa", "cable", "control remoto",
    "control-remoto", "funda", "stand", "barra de sonido", "soundbar",
    "parlante", "bocina", "audifono", "auricular", "combo", "juego",
    "accesorio", "aire acondicionado", "refrigeradora", "lavadora",
    "microonda", "cocina", "licuadora", "batidora", "aspiradora", "plancha",
    "secadora", "horno", "freidora", "extractor", "purificador",
    "lavavajillas", "camara", "proyector", "reloj", "tablet", "celular",
    "laptop", "silla", "escritorio", "seguro", "garantia", "bombillo",
    "lampara", "teclado", "mouse", "cargador", "adaptador", "hdmi",
    "toma tv", "adorno", "tcp", "telefon", "cargador", "memoria",
)
# 垃圾型号（完整匹配即视为无型号）
BAD_MODEL = re.compile(
    r"^(4K|8K|8LT|4KUHD|4k?u?h?d?|60HZ|120HZ|2X8|HD|FHD|UHD|LED|QLED|OLED|"
    r"ULTRA|PRO|MAX|MINI|SMART|GOOGLE|TIZEN|DUAL|4GB|8GB|HZ|SV|X16|)
", re.I)
HZ_MODEL = re.compile(r"^\d{2,3}HZ$", re.I)
SIZE_RE = re.compile(r"(\d{2,3})(?:\"|″|\\\")?(?:in|pulg|p| )", re.I)


def parse_money(s) -> float | None:
    """金额解析：欧式/美式 → float。损坏/越界 → None。"""
    if s is None:
        return None
    s = str(s).strip().replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and s.count(",") == 1 and len(s) - s.rfind(",") - 1 in (1, 2):
        s = s.replace(",", ".")       # 267,66 / 1.154,15 的单逗号小数
    elif "," in s:
        s = s.replace(",", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if v <= 0 or v > 10_000_000:
        return None
    return round(v, 2)


def model_of(t: str) -> str:
    up = t.upper()
    toks = re.split(r"[^A-Z0-9]+", up)
    # 国际机型码（三星/大厂）
    for tok in toks:
        if re.fullmatch(r"(?:QN|UN|RN|UA|MR|AU|QE|OLED|LED|XDR|BRAVIA)[A-Z0-9]{4,12}", tok):
            return tok
    # 尺寸开头机型：55UA7500PSA / 65QD68SG / 43S5K / 65C6K
    for tok in toks:
        if re.fullmatch(r"\d{2,3}[A-Z][A-Z0-9]{2,10}", tok) and not HZ_MODEL.fullmatch(tok):
            return tok
    # 尺寸字母机型：Q6Q / A400 / C6K（系列级）
    for tok in toks:
        if re.fullmatch(r"[A-Z]?\d{0,2}[A-Z][A-Z0-9]{1,6}", tok) and len(tok) >= 3:
            if BAD_MODEL.fullmatch(tok):
                continue
            return tok
    m = re.findall(r"\b(\d{2,3}[A-Z][A-Z0-9]{2,9})\b", up)
    return m[-1] if m else ""


def size_of(t: str) -> str:
    m = SIZE_RE.search(t)
    return (m.group(1) + '"') if m else ""


def main() -> int:
    if not os.path.exists(SRC):
        print(f"[缺] {SRC}")
        return 1
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    print(f"源 {SRC} rows={len(rows)}")

    out = []
    seen = set()
    stats = Counter()
    for r in rows:
        title = (r.get("商品名") or "").strip()
        price_raw = (r.get("价格") or "").strip()
        if not price_raw:
            stats["无价"] += 1
            continue
        p = parse_money(price_raw)
        if p is None:
            stats["坏价"] += 1
            continue
        low = title.lower()
        if any(k in low for k in NON_TV):
            stats["剔非电视"] += 1
            continue
        model = (r.get("型号") or "").strip()
        if not model or BAD_MODEL.fullmatch(model) or HZ_MODEL.fullmatch(model) or len(model) < 3:
            model = model_of(title)
        size = (r.get("尺寸") or "").strip()
        if not size:
            size = size_of(title)
        key = (r.get("零售站", ""), model, title[:40])
        if key in seen:
            stats["去重"] += 1
            continue
        seen.add(key)
        r["价格"] = f"{p:g}"
        r["型号"] = model or title[:20]
        r["尺寸"] = size
        out.append(r)

    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        cols = list(rows[0].keys()) if rows else []
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print(f"[OUT] {OUT} rows={len(out)}")
    print(f"汇总: {dict(stats)}")
    # 结果分布
    print("按站:", dict(Counter(r.get("零售站", "") for r in out)))
    priced = [r for r in out if (r.get("价格") or "").strip()]
    print(f"有价: {len(priced)}")
    return 0


if __name__ == "__main__":
    main()