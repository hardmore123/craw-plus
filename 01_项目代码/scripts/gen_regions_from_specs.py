# -*- coding: utf-8 -*-
"""按 schemas/retail_specs 生成「欧洲各国 + 危地马拉 + 巴拿马」的 Region 静态配置与零售白名单。

背景：通用全量入口 crawl_ca_retail.py 只认 regions_config.REGIONS 里的区域，且 --sites
必须登记在该区域的 retail_sites 里；mx_retail 路径还要过 retail_compliance 白名单。
原先只有北美/南美 9 个区域，欧洲 150+ 个已有 spec 的零售站因此无法走 schema 驱动的全量。

本脚本只**生成静态代码/数据**（便于 git 审阅），不在运行时动态扫描 spec：
  overseas/regions_auto.py        —— 生成的 Region 定义（AUTO_REGIONS）
  schemas/retail_allowlist.json   —— 生成的合规白名单（status ∈ approved/candidate 的站）

站点 enabled 口径：spec.status ∈ {approved, candidate} → True；blocked/needs_handwritten → False
（显式 --sites 仍可跑，便于复测）。

用法：py -3.12 scripts/gen_regions_from_specs.py
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ["OVERSEAS_NO_AUTO_REGIONS"] = "1"     # 只看手写区域，避免生成结果反过来影响生成

from overseas.regions_config import REGIONS  # noqa: E402  已有区域不重复生成

# 国家码 → (中文名, 币种, locale)。中文名用于导出目录 data/<中文名>/
COUNTRIES = {
    "uk": ("英国", "GBP", "en-GB"), "de": ("德国", "EUR", "de-DE"), "fr": ("法国", "EUR", "fr-FR"),
    "it": ("意大利", "EUR", "it-IT"), "es": ("西班牙", "EUR", "es-ES"), "pt": ("葡萄牙", "EUR", "pt-PT"),
    "nl": ("荷兰", "EUR", "nl-NL"), "be": ("比利时", "EUR", "nl-BE"), "at": ("奥地利", "EUR", "de-AT"),
    "ch": ("瑞士", "CHF", "de-CH"), "pl": ("波兰", "PLN", "pl-PL"), "cz": ("捷克", "CZK", "cs-CZ"),
    "sk": ("斯洛伐克", "EUR", "sk-SK"), "hu": ("匈牙利", "HUF", "hu-HU"), "ro": ("罗马尼亚", "RON", "ro-RO"),
    "bg": ("保加利亚", "BGN", "bg-BG"), "gr": ("希腊", "EUR", "el-GR"), "tr": ("土耳其", "TRY", "tr-TR"),
    "ru": ("俄罗斯", "RUB", "ru-RU"), "ua": ("乌克兰", "UAH", "uk-UA"), "se": ("瑞典", "SEK", "sv-SE"),
    "no": ("挪威", "NOK", "nb-NO"), "dk": ("丹麦", "DKK", "da-DK"), "fi": ("芬兰", "EUR", "fi-FI"),
    "ee": ("爱沙尼亚", "EUR", "et-EE"), "lv": ("拉脱维亚", "EUR", "lv-LV"), "lt": ("立陶宛", "EUR", "lt-LT"),
    "hr": ("克罗地亚", "EUR", "hr-HR"), "rs": ("塞尔维亚", "RSD", "sr-RS"), "si": ("斯洛文尼亚", "EUR", "sl-SI"),
    "ba": ("波黑", "BAM", "bs-BA"), "gt": ("危地马拉", "GTQ", "es-GT"), "pa": ("巴拿马", "USD", "es-PA"),
}
BRANDS = [("hisense", "Hisense"), ("samsung", "Samsung"), ("tcl", "TCL"),
          ("lg", "LG"), ("sony", "Sony"), ("philips", "Philips")]
RUNNABLE = {"approved", "candidate"}


def main() -> int:
    specs = []
    for f in sorted(glob.glob("schemas/retail_specs/*.retail.json")):
        s = json.load(open(f, encoding="utf-8"))
        specs.append(s)

    def spec_cc(s: dict) -> str:
        """国家码：code 后缀；后缀不是国家码（cresa_ec_more / laganga_ec2）时用 spec.region。"""
        cc = s["code"].rsplit("_", 1)[-1]
        if cc in COUNTRIES or cc in REGIONS:
            return cc
        r = str(s.get("region") or "").strip().lower()
        return r if (r in COUNTRIES or r in REGIONS) else cc

    by_cc: dict[str, list[dict]] = defaultdict(list)
    for s in specs:
        cc = spec_cc(s)
        if cc in COUNTRIES and cc not in REGIONS:
            # 品牌官网 spec（hisense_de 等）不是零售站，跳过
            if s["code"].split("_")[0] in {b for b, _ in BRANDS}:
                continue
            by_cc[cc].append(s)

    lines = [
        '"""自动生成：欧洲各国 + 危地马拉 + 巴拿马 零售区域（勿手改，改 spec 后重跑生成器）。',
        "",
        "生成器：scripts/gen_regions_from_specs.py；来源：schemas/retail_specs/*.retail.json。",
        "enabled = spec.status ∈ {approved, candidate}；其余站仍可用 --sites 显式复测。",
        '"""',
        "from __future__ import annotations",
        "",
        "from .regions_config import Brand, Region, RetailSite",
        "",
        "AUTO_REGIONS: dict[str, Region] = {",
    ]
    total = enabled = 0
    for cc in sorted(by_cc):
        name, cur, loc = COUNTRIES[cc]
        lines.append(f'    "{cc}": Region(')
        lines.append(f'        code="{cc}", name="{name}", currency="{cur}", locale="{loc}",')
        lines.append("        enabled=True,")
        lines.append(f'        note="{name}零售线（spec 驱动，自动生成）",')
        lines.append("        brands=[" + ", ".join(
            f'Brand("{b}_{cc}", "{n}")' for b, n in BRANDS) + "],")
        lines.append("        retail_sites=[")
        for s in sorted(by_cc[cc], key=lambda x: x["code"]):
            on = s.get("status") in RUNNABLE
            total += 1
            enabled += on
            nm = (s.get("name") or s.get("channel") or s["code"]).replace('"', "'")
            lines.append(f'            RetailSite("{s["code"]}", "{nm}", "{s.get("base_url", "")}", '
                         f'enabled={on}),  # {s.get("status")}')
        lines.append("        ],")
        lines.append("    ),")
    lines.append("}")

    # 已有区域（北美/南美）里漏登记的零售站：有 spec + 零售 adapter，却不在 retail_sites
    from overseas.sites import SiteRegistry
    known = {rs.site for reg in REGIONS.values() for rs in reg.retail_sites}
    extra: dict[str, list[dict]] = defaultdict(list)
    for s in specs:
        cc = spec_cc(s)
        if cc not in REGIONS or s["code"] in known:
            continue
        try:
            ad = SiteRegistry.get(s["code"])
        except Exception:
            continue
        if getattr(ad, "supports_retail", False):
            extra[cc].append(s)
    lines += ["", "",
              "# 已有区域漏登记的零售站（有 spec + 零售 adapter）。品牌官网商城也在此列，",
              "# 默认按 spec.status 决定 enabled。",
              "EXTRA_RETAIL_SITES: dict[str, list[RetailSite]] = {"]
    for cc in sorted(extra):
        lines.append(f'    "{cc}": [')
        for s in sorted(extra[cc], key=lambda x: x["code"]):
            on = s.get("status") in RUNNABLE
            nm = (s.get("name") or s.get("channel") or s["code"]).replace('"', "'")
            lines.append(f'        RetailSite("{s["code"]}", "{nm}", "{s.get("base_url", "")}", '
                         f'enabled={on}),  # {s.get("status")}')
        lines.append("    ],")
    lines.append("}")
    open("overseas/regions_auto.py", "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"[OUT] 已有区域补登记 {sum(len(v) for v in extra.values())} 站：{dict((k, len(v)) for k, v in extra.items())}")

    hosts = set()
    for s in specs:
        if s.get("status") not in RUNNABLE:
            continue
        urls = [s.get("base_url") or ""]
        try:                                   # adapter 的 base_url 才是实际请求的域名
            urls.append(SiteRegistry.get(s["code"]).base_url)
        except Exception:
            pass
        for u in urls:
            h = urlsplit(u).netloc.lower().split(":")[0]
            if h.startswith("www."):
                h = h[4:]
            if h:
                hosts.add(h)
    json.dump({"_note": "自动生成（scripts/gen_regions_from_specs.py）：status∈approved/candidate 的零售站域名",
               "hosts": sorted(hosts)},
              open("schemas/retail_allowlist.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[OUT] overseas/regions_auto.py 区域 {len(by_cc)} 个，站 {total}（enabled {enabled}）")
    print(f"[OUT] schemas/retail_allowlist.json 域名 {len(hosts)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
