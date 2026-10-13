# -*- coding: utf-8 -*-
"""为南美/欧洲零售站批量创建极薄 SiteAdapter（读 _adapter_template.py 替换占位符）。

用法：py scripts/gen_sa_adapters.py
"""
from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

TEMPLATE = open(os.path.join("scripts", "_adapter_template.py"), encoding="utf-8").read()

# code -> (name, base_url, search_path, country)
# country 用于 adapter.country（导出展示）。search_path 待探测后按实际形态修正。
SITES = {
    # 秘鲁（已有 10 个，保留）
    "hiraoka_pe":   ("Hiraoka", "https://hiraoka.com.pe",        "/catalogsearch/result/?q={q}", "Peru"),
    "carsa_pe":     ("Carsa",   "https://www.carsa.pe",          "/buscar?q={q}",      "Peru"),
    "estilos_pe":   ("Estilos", "https://www.estilos.com.pe",    "/busqueda?q={q}",    "Peru"),
    "metro_pe":     ("Metro",   "https://www.metro.pe",          "/busca?q={q}",       "Peru"),
    "credivargas_pe": ("Credivargas", "https://www.credivargas.pe", "/search?q={q}",   "Peru"),
    "efe_pe":       ("Efe",     "https://www.efe.com.pe",        "/buscar?q={q}",      "Peru"),
    "oechsle_pe":   ("Oechsle", "https://www.oechsle.pe",        "/buscar?q={q}",      "Peru"),
    "lacuracao_pe": ("La Curacao", "https://www.lacuracao.pe",   "/buscar?q={q}",      "Peru"),
    "plazavea_pe":  ("Plaza Vea", "https://www.plazavea.com.pe", "/buscar?q={q}",      "Peru"),
    "mercadolibre_pe": ("Mercado Libre", "https://www.mercadolibre.com.pe", "/listado/{q}", "Peru"),
    # 厄瓜多尔
    "cresa_ec":     ("Cresa",   "https://www.cresa.com",         "/buscar?q={q}",      "Ecuador"),
    "japon_ec":     ("Almacenes Japon", "https://www.almacenesjapon.com", "/search?q={q}", "Ecuador"),
    "orvehogar_ec": ("Orvehogar", "https://www.orvehogar.com",   "/buscar?q={q}",      "Ecuador"),
    "artefacta_ec": ("Artefacta", "https://www.artefacta.com",   "/catalogsearch/result/?q={q}", "Ecuador"),
    "marcimex_ec":  ("Marcimex", "https://www.marcimex.com",     "/buscar?q={q}",      "Ecuador"),
    "laganga_ec":   ("L-Ganga", "https://laganga.com",           "/buscar?q={q}",      "Ecuador"),
    "comandato_ec": ("Comandato", "https://www.comandato.com",   "/buscar?q={q}",      "Ecuador"),
    "jaher_ec":     ("Jaher",   "https://www.jaher.com.ec",      "/buscar?q={q}",      "Ecuador"),
    "espana_ec":    ("Almacenes Espana", "https://almacenesespana.ec", "/buscar?q={q}", "Ecuador"),
    "megamaxi_ec":  ("Megamaxi", "https://www.megamaxi.com",     "/buscar?q={q}",      "Ecuador"),
    "sukasa_ec":    ("Sukasa",  "https://www.sukasa.com",        "/buscar?q={q}",      "Ecuador"),
    "todohogar_ec": ("Todohogar", "https://www.todohogar.com",   "/buscar?q={q}",      "Ecuador"),
    "coral_ec":     ("Coral",   "https://coralhipermercados.com", "/buscar?q={q}",     "Ecuador"),
    "ferrisariato_ec": ("Ferrisariato", "https://www.ferrisariato.com", "/buscar?q={q}", "Ecuador"),
    # 哥伦比亚
    "alkosto_co":  ("Alkosto", "https://www.alkosto.com",        "/search?q={q}",      "Colombia"),
    "exito_co":    ("Exito",   "https://www.exito.com",          "/buscar?q={q}",      "Colombia"),
    "falabella_co":("Falabella", "https://www.falabella.com.co", "/search?q={q}",     "Colombia"),
    "jumbo_co":    ("Jumbo",   "https://www.jumbocolombia.com",  "/buscar?q={q}",      "Colombia"),
    "olimpica_co": ("Olimpica", "https://www.olimpica.com.co",   "/buscar?q={q}",      "Colombia"),
    # 智利
    "falabella_cl":("Falabella", "https://www.falabella.com",    "/search?q={q}",     "Chile"),
    "paris_cl":    ("Paris",   "https://www.paris.cl",           "/buscar?q={q}",      "Chile"),
    "ripley_cl":   ("Ripley",  "https://simple.ripley.cl",       "/search?q={q}",     "Chile"),
    "mercadolibre_cl": ("Mercado Libre", "https://www.mercadolibre.cl", "/listado/{q}", "Chile"),
    "lider_cl":    ("Lider",   "https://www.lider.cl",          "/buscar?q={q}",      "Chile"),
    "abc_cl":      ("ABC",     "https://www.abc.cl",             "/buscar?q={q}",      "Chile"),
    "hites_cl":    ("Hites",   "https://www.hites.com",          "/buscar?q={q}",      "Chile"),
    # 玻利维亚
    "multicenter_bo": ("Multicenter", "https://www.multicenter.com", "/buscar?q={q}", "Bolivia"),
    "dismac_bo":   ("Dismac",  "https://www.dismac.com.bo",      "/buscar?q={q}",      "Bolivia"),
    "alkostoplus_bo": ("Multicenter+", "https://alkostoplus.com", "/tienda?s={q}",     "Bolivia"),
}


def main() -> None:
    for code, (name, base, path, country) in SITES.items():
        d = os.path.join("overseas", "sites", code)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "__init__.py"), "w", encoding="utf-8").close()
        cls = name.replace(" ", "").replace("-", "").replace("+", "")
        content = (
            TEMPLATE
            .replace("__NAME__", name)
            .replace("__CLS__", cls)
            .replace("__CODE__", code)
            .replace("__BASE__", base)
            .replace("__COUNTRY__", country)
            .replace("__PATH__", path)
        )
        with open(os.path.join(d, "adapter.py"), "w", encoding="utf-8") as f:
            f.write(content)
        print("[OK]", code)

    # 注册自检
    sys.path.insert(0, ROOT)
    from overseas.sites import SiteRegistry  # noqa: E402
    for code in SITES:
        try:
            a = SiteRegistry.get(code)
            print("  %-18s base=%s search=%s" % (code, a.base_url, a.search_url("55C6K")))
        except Exception as e:
            print("  %-18s FAIL %s: %s" % (code, type(e).__name__, e))


if __name__ == "__main__":
    main()