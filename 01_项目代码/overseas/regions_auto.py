"""自动生成：欧洲各国 + 危地马拉 + 巴拿马 零售区域（勿手改，改 spec 后重跑生成器）。

生成器：scripts/gen_regions_from_specs.py；来源：schemas/retail_specs/*.retail.json。
enabled = spec.status ∈ {approved, candidate}；其余站仍可用 --sites 显式复测。
"""
from __future__ import annotations

from .regions_config import Brand, Region, RetailSite

AUTO_REGIONS: dict[str, Region] = {
    "at": Region(
        code="at", name="奥地利", currency="EUR", locale="de-AT",
        enabled=True,
        note="奥地利零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_at", "Hisense"), Brand("samsung_at", "Samsung"), Brand("tcl_at", "TCL"), Brand("lg_at", "LG"), Brand("sony_at", "Sony"), Brand("philips_at", "Philips")],
        retail_sites=[
            RetailSite("cyberport_at", "Cyberport AT", "https://www.cyberport.at", enabled=False),  # blocked
            RetailSite("e_tec_at", "E-tec", "https://www.e-tec.at", enabled=False),  # blocked
            RetailSite("electronic4you_at", "Electronic4you", "https://www.electronic4you.at", enabled=False),  # blocked
            RetailSite("mediamarkt_at", "MediaMarkt AT", "https://www.mediamarkt.at", enabled=False),  # blocked
        ],
    ),
    "ba": Region(
        code="ba", name="波黑", currency="BAM", locale="bs-BA",
        enabled=True,
        note="波黑零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ba", "Hisense"), Brand("samsung_ba", "Samsung"), Brand("tcl_ba", "TCL"), Brand("lg_ba", "LG"), Brand("sony_ba", "Sony"), Brand("philips_ba", "Philips")],
        retail_sites=[
            RetailSite("domod_ba", "Domod", "https://domod.ba", enabled=True),  # candidate
            RetailSite("tehnomag_ba", "Tehnomag", "https://tehnomag.com", enabled=False),  # blocked
        ],
    ),
    "be": Region(
        code="be", name="比利时", currency="EUR", locale="nl-BE",
        enabled=True,
        note="比利时零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_be", "Hisense"), Brand("samsung_be", "Samsung"), Brand("tcl_be", "TCL"), Brand("lg_be", "LG"), Brand("sony_be", "Sony"), Brand("philips_be", "Philips")],
        retail_sites=[
            RetailSite("amazon_be", "Amazon Belgium", "https://www.amazon.com.be", enabled=True),  # candidate
            RetailSite("bol_be", "Bol.com Belgium", "https://www.bol.com", enabled=False),  # blocked
            RetailSite("coolblue_be", "Coolblue Belgium", "https://www.coolblue.be", enabled=True),  # candidate
            RetailSite("mediamarkt_be", "MediaMarkt Belgium", "https://www.mediamarkt.be", enabled=True),  # candidate
            RetailSite("vandenborre_be", "Vanden Borre", "https://www.vandenborre.be", enabled=True),  # candidate
        ],
    ),
    "bg": Region(
        code="bg", name="保加利亚", currency="BGN", locale="bg-BG",
        enabled=True,
        note="保加利亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_bg", "Hisense"), Brand("samsung_bg", "Samsung"), Brand("tcl_bg", "TCL"), Brand("lg_bg", "LG"), Brand("sony_bg", "Sony"), Brand("philips_bg", "Philips")],
        retail_sites=[
            RetailSite("emag_bg", "eMAG BG", "https://www.emag.bg", enabled=False),  # blocked
            RetailSite("technomarket_bg", "Technomarket", "https://www.technomarket.bg", enabled=False),  # blocked
            RetailSite("technopolis_bg", "Technopolis", "https://www.technopolis.bg", enabled=False),  # blocked
        ],
    ),
    "ch": Region(
        code="ch", name="瑞士", currency="CHF", locale="de-CH",
        enabled=True,
        note="瑞士零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ch", "Hisense"), Brand("samsung_ch", "Samsung"), Brand("tcl_ch", "TCL"), Brand("lg_ch", "LG"), Brand("sony_ch", "Sony"), Brand("philips_ch", "Philips")],
        retail_sites=[
            RetailSite("brack_ch", "Brack Switzerland", "https://www.brack.ch", enabled=False),  # blocked
            RetailSite("digitec_ch", "Digitec Switzerland", "https://www.digitec.ch", enabled=True),  # candidate
            RetailSite("fust_ch", "Fust", "https://www.fust.ch", enabled=False),  # blocked
            RetailSite("galaxus_ch", "Galaxus Switzerland", "https://www.galaxus.ch", enabled=True),  # candidate
            RetailSite("interdiscount_ch", "Interdiscount", "https://www.interdiscount.ch", enabled=True),  # candidate
            RetailSite("mediamarkt_ch", "MediaMarkt Switzerland", "https://www.mediamarkt.ch", enabled=True),  # candidate
        ],
    ),
    "cz": Region(
        code="cz", name="捷克", currency="CZK", locale="cs-CZ",
        enabled=True,
        note="捷克零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_cz", "Hisense"), Brand("samsung_cz", "Samsung"), Brand("tcl_cz", "TCL"), Brand("lg_cz", "LG"), Brand("sony_cz", "Sony"), Brand("philips_cz", "Philips")],
        retail_sites=[
            RetailSite("alza_cz", "Alza CZ", "https://www.alza.cz", enabled=False),  # blocked
            RetailSite("czc_cz", "CZC.cz", "https://www.czc.cz", enabled=True),  # candidate
            RetailSite("datart_cz", "Datart CZ", "https://www.datart.cz", enabled=True),  # candidate
            RetailSite("mall_cz", "Mall.cz", "https://www.mall.cz", enabled=False),  # blocked
        ],
    ),
    "de": Region(
        code="de", name="德国", currency="EUR", locale="de-DE",
        enabled=True,
        note="德国零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_de", "Hisense"), Brand("samsung_de", "Samsung"), Brand("tcl_de", "TCL"), Brand("lg_de", "LG"), Brand("sony_de", "Sony"), Brand("philips_de", "Philips")],
        retail_sites=[
            RetailSite("alternate_de", "Alternate", "https://www.alternate.de", enabled=True),  # candidate
            RetailSite("amazon_de", "Amazon", "https://www.amazon.de", enabled=True),  # candidate
            RetailSite("cyberport_de", "Cyberport", "https://www.cyberport.de", enabled=False),  # blocked
            RetailSite("ebay_de", "eBay DE", "https://www.ebay.de", enabled=False),  # blocked
            RetailSite("euronics_de", "Euronics", "https://www.euronics.de", enabled=False),  # blocked
            RetailSite("expert_de", "Expert DE", "https://www.expert.de", enabled=True),  # candidate
            RetailSite("mediamarkt_de", "MediaMarkt", "https://www.mediamarkt.de", enabled=True),  # candidate
            RetailSite("otto_de", "OTTO", "https://www.otto.de", enabled=True),  # approved
            RetailSite("saturn_de", "Saturn", "https://www.saturn.de", enabled=True),  # candidate
        ],
    ),
    "dk": Region(
        code="dk", name="丹麦", currency="DKK", locale="da-DK",
        enabled=True,
        note="丹麦零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_dk", "Hisense"), Brand("samsung_dk", "Samsung"), Brand("tcl_dk", "TCL"), Brand("lg_dk", "LG"), Brand("sony_dk", "Sony"), Brand("philips_dk", "Philips")],
        retail_sites=[
            RetailSite("elgiganten_dk", "Elgiganten Denmark", "https://www.elgiganten.dk", enabled=False),  # blocked
            RetailSite("power_dk", "Power DK", "https://www.power.dk", enabled=True),  # candidate
            RetailSite("proshop_dk", "Proshop Denmark", "https://www.proshop.dk", enabled=False),  # blocked
        ],
    ),
    "ee": Region(
        code="ee", name="爱沙尼亚", currency="EUR", locale="et-EE",
        enabled=True,
        note="爱沙尼亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ee", "Hisense"), Brand("samsung_ee", "Samsung"), Brand("tcl_ee", "TCL"), Brand("lg_ee", "LG"), Brand("sony_ee", "Sony"), Brand("philips_ee", "Philips")],
        retail_sites=[
            RetailSite("euronics_ee", "Euronics EE", "https://www.euronics.ee", enabled=True),  # candidate
            RetailSite("kaup24_ee", "Kaup24", "https://kaup24.ee", enabled=True),  # candidate
            RetailSite("klick_ee", "Klick", "https://www.klick.ee", enabled=True),  # candidate
        ],
    ),
    "es": Region(
        code="es", name="西班牙", currency="EUR", locale="es-ES",
        enabled=True,
        note="西班牙零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_es", "Hisense"), Brand("samsung_es", "Samsung"), Brand("tcl_es", "TCL"), Brand("lg_es", "LG"), Brand("sony_es", "Sony"), Brand("philips_es", "Philips")],
        retail_sites=[
            RetailSite("amazon_es", "Amazon", "https://www.amazon.es", enabled=True),  # candidate
            RetailSite("carrefour_es", "Carrefour", "https://www.carrefour.es", enabled=False),  # blocked
            RetailSite("ebay_es", "eBay Spain", "https://www.ebay.es", enabled=False),  # blocked
            RetailSite("elcorteingles_es", "El Corte Ingles", "https://www.elcorteingles.es", enabled=True),  # candidate
            RetailSite("mediamarkt_es", "MediaMarkt", "https://www.mediamarkt.es", enabled=True),  # candidate
            RetailSite("pccomponentes_es", "PCComponentes", "https://www.pccomponentes.com", enabled=False),  # blocked
            RetailSite("worten_es", "Worten", "https://www.worten.es", enabled=False),  # blocked
        ],
    ),
    "fi": Region(
        code="fi", name="芬兰", currency="EUR", locale="fi-FI",
        enabled=True,
        note="芬兰零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_fi", "Hisense"), Brand("samsung_fi", "Samsung"), Brand("tcl_fi", "TCL"), Brand("lg_fi", "LG"), Brand("sony_fi", "Sony"), Brand("philips_fi", "Philips")],
        retail_sites=[
            RetailSite("gigantti_fi", "Gigantti", "https://www.gigantti.fi", enabled=False),  # blocked
            RetailSite("power_fi", "Power FI", "https://www.power.fi", enabled=True),  # candidate
            RetailSite("verkkokauppa_fi", "Verkkokauppa", "https://www.verkkokauppa.com", enabled=True),  # candidate
        ],
    ),
    "fr": Region(
        code="fr", name="法国", currency="EUR", locale="fr-FR",
        enabled=True,
        note="法国零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_fr", "Hisense"), Brand("samsung_fr", "Samsung"), Brand("tcl_fr", "TCL"), Brand("lg_fr", "LG"), Brand("sony_fr", "Sony"), Brand("philips_fr", "Philips")],
        retail_sites=[
            RetailSite("amazon_fr", "Amazon", "https://www.amazon.fr", enabled=True),  # candidate
            RetailSite("auchan_fr", "Auchan", "https://www.auchan.fr", enabled=True),  # candidate
            RetailSite("boulanger_fr", "Boulanger", "https://www.boulanger.com", enabled=False),  # blocked
            RetailSite("but_fr", "BUT", "https://www.but.fr", enabled=False),  # blocked
            RetailSite("carrefour_fr", "Carrefour FR", "https://www.carrefour.fr", enabled=False),  # blocked
            RetailSite("cdiscount_fr", "Cdiscount", "https://www.cdiscount.com", enabled=True),  # candidate
            RetailSite("conforama_fr", "Conforama", "https://www.conforama.fr", enabled=False),  # blocked
            RetailSite("darty_fr", "Darty", "https://www.darty.com", enabled=False),  # blocked
            RetailSite("ebay_fr", "eBay France", "https://www.ebay.fr", enabled=False),  # blocked
            RetailSite("electrodepot_fr", "Electro Depot", "https://www.electrodepot.fr", enabled=False),  # blocked
            RetailSite("fnac_fr", "Fnac", "https://www.fnac.com", enabled=False),  # blocked
            RetailSite("ldlc_fr", "LDLC", "https://www.ldlc.com", enabled=True),  # candidate
            RetailSite("leclerc_fr", "Leclerc", "https://www.e.leclerc", enabled=False),  # blocked
            RetailSite("rueducommerce_fr", "Rue du Commerce", "https://www.rueducommerce.fr", enabled=False),  # blocked
            RetailSite("sonvideo_fr", "Son-Video", "https://www.son-video.com", enabled=False),  # blocked
        ],
    ),
    "gr": Region(
        code="gr", name="希腊", currency="EUR", locale="el-GR",
        enabled=True,
        note="希腊零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_gr", "Hisense"), Brand("samsung_gr", "Samsung"), Brand("tcl_gr", "TCL"), Brand("lg_gr", "LG"), Brand("sony_gr", "Sony"), Brand("philips_gr", "Philips")],
        retail_sites=[
            RetailSite("kotsovolos_gr", "Kotsovolos", "https://www.kotsovolos.gr", enabled=False),  # blocked
            RetailSite("plaisio_gr", "Plaisio", "https://www.plaisio.gr", enabled=False),  # blocked
            RetailSite("public_gr", "Public GR", "https://www.public.gr", enabled=True),  # candidate
            RetailSite("skroutz_gr", "Skroutz", "https://www.skroutz.gr", enabled=True),  # candidate
        ],
    ),
    "gt": Region(
        code="gt", name="危地马拉", currency="GTQ", locale="es-GT",
        enabled=True,
        note="危地马拉零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_gt", "Hisense"), Brand("samsung_gt", "Samsung"), Brand("tcl_gt", "TCL"), Brand("lg_gt", "LG"), Brand("sony_gt", "Sony"), Brand("philips_gt", "Philips")],
        retail_sites=[
            RetailSite("elektra_gt", "Elektra", "https://www.elektra.com.gt", enabled=True),  # candidate
            RetailSite("max_gt", "Max", "https://www.max.com.gt", enabled=True),  # candidate
            RetailSite("tecnofacil_gt", "Tecnofacil", "https://www.tecnofacil.com.gt", enabled=True),  # candidate
            RetailSite("unicomer_gt", "Unicomer", "https://www.lacuracaonline.com", enabled=True),  # candidate
        ],
    ),
    "hr": Region(
        code="hr", name="克罗地亚", currency="EUR", locale="hr-HR",
        enabled=True,
        note="克罗地亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_hr", "Hisense"), Brand("samsung_hr", "Samsung"), Brand("tcl_hr", "TCL"), Brand("lg_hr", "LG"), Brand("sony_hr", "Sony"), Brand("philips_hr", "Philips")],
        retail_sites=[
            RetailSite("ekupi_hr", "eKupi", "https://www.ekupi.hr", enabled=False),  # blocked
            RetailSite("elipso_hr", "Elipso", "https://www.elipso.hr", enabled=False),  # blocked
            RetailSite("links_hr", "Links HR", "https://www.links.hr", enabled=False),  # needs_handwritten
            RetailSite("sancta_domenica_hr", "Sancta Domenica", "https://www.sancta-domenica.hr", enabled=False),  # blocked
        ],
    ),
    "hu": Region(
        code="hu", name="匈牙利", currency="HUF", locale="hu-HU",
        enabled=True,
        note="匈牙利零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_hu", "Hisense"), Brand("samsung_hu", "Samsung"), Brand("tcl_hu", "TCL"), Brand("lg_hu", "LG"), Brand("sony_hu", "Sony"), Brand("philips_hu", "Philips")],
        retail_sites=[
            RetailSite("alza_hu", "Alza HU", "https://www.alza.hu", enabled=False),  # blocked
            RetailSite("emag_hu", "eMAG HU", "https://www.emag.hu", enabled=False),  # blocked
            RetailSite("mediamarkt_hu", "MediaMarkt HU", "https://www.mediamarkt.hu", enabled=False),  # blocked
        ],
    ),
    "it": Region(
        code="it", name="意大利", currency="EUR", locale="it-IT",
        enabled=True,
        note="意大利零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_it", "Hisense"), Brand("samsung_it", "Samsung"), Brand("tcl_it", "TCL"), Brand("lg_it", "LG"), Brand("sony_it", "Sony"), Brand("philips_it", "Philips")],
        retail_sites=[
            RetailSite("amazon_it", "Amazon", "https://www.amazon.it", enabled=True),  # candidate
            RetailSite("ebay_it", "eBay Italy", "https://www.ebay.it", enabled=False),  # blocked
            RetailSite("eprice_it", "ePRICE", "https://www.eprice.it", enabled=False),  # blocked
            RetailSite("euronics_it", "Euronics IT", "https://www.euronics.it", enabled=False),  # blocked
            RetailSite("mediamarkt_it", "MediaWorld IT", "https://www.mediaworld.it", enabled=True),  # candidate
            RetailSite("trony_it", "Trony", "https://www.trony.it", enabled=False),  # blocked
            RetailSite("unieuro_it", "Unieuro", "https://www.unieuro.it/online", enabled=True),  # candidate
        ],
    ),
    "lt": Region(
        code="lt", name="立陶宛", currency="EUR", locale="lt-LT",
        enabled=True,
        note="立陶宛零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_lt", "Hisense"), Brand("samsung_lt", "Samsung"), Brand("tcl_lt", "TCL"), Brand("lg_lt", "LG"), Brand("sony_lt", "Sony"), Brand("philips_lt", "Philips")],
        retail_sites=[
            RetailSite("pigu_lt", "Pigu.lt", "https://pigu.lt", enabled=False),  # blocked
            RetailSite("topocentras_lt", "Topo Centras", "https://www.topocentras.lt", enabled=False),  # blocked
            RetailSite("varle_lt", "Varle.lt", "https://www.varle.lt", enabled=False),  # blocked
        ],
    ),
    "lv": Region(
        code="lv", name="拉脱维亚", currency="EUR", locale="lv-LV",
        enabled=True,
        note="拉脱维亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_lv", "Hisense"), Brand("samsung_lv", "Samsung"), Brand("tcl_lv", "TCL"), Brand("lg_lv", "LG"), Brand("sony_lv", "Sony"), Brand("philips_lv", "Philips")],
        retail_sites=[
            RetailSite("220_lv", "220.lv", "https://220.lv", enabled=True),  # candidate
            RetailSite("euronics_lv", "Euronics LV", "https://www.euronics.lv", enabled=True),  # candidate
            RetailSite("rdveikals_lv", "RD Veikals", "https://www.rdveikals.lv", enabled=False),  # blocked
        ],
    ),
    "nl": Region(
        code="nl", name="荷兰", currency="EUR", locale="nl-NL",
        enabled=True,
        note="荷兰零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_nl", "Hisense"), Brand("samsung_nl", "Samsung"), Brand("tcl_nl", "TCL"), Brand("lg_nl", "LG"), Brand("sony_nl", "Sony"), Brand("philips_nl", "Philips")],
        retail_sites=[
            RetailSite("amazon_nl", "Amazon Netherlands", "https://www.amazon.nl", enabled=True),  # candidate
            RetailSite("bol_nl", "Bol.com Netherlands", "https://www.bol.com", enabled=False),  # blocked
            RetailSite("coolblue_nl", "Coolblue Netherlands", "https://www.coolblue.nl", enabled=True),  # candidate
            RetailSite("mediamarkt_nl", "MediaMarkt Netherlands", "https://www.mediamarkt.nl", enabled=False),  # blocked
        ],
    ),
    "no": Region(
        code="no", name="挪威", currency="NOK", locale="nb-NO",
        enabled=True,
        note="挪威零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_no", "Hisense"), Brand("samsung_no", "Samsung"), Brand("tcl_no", "TCL"), Brand("lg_no", "LG"), Brand("sony_no", "Sony"), Brand("philips_no", "Philips")],
        retail_sites=[
            RetailSite("elkjop_no", "Elkjop Norway", "https://www.elkjop.no", enabled=False),  # blocked
            RetailSite("komplett_no", "Komplett Norway", "https://www.komplett.no", enabled=False),  # blocked
            RetailSite("power_no", "Power NO", "https://www.power.no", enabled=True),  # candidate
        ],
    ),
    "pa": Region(
        code="pa", name="巴拿马", currency="USD", locale="es-PA",
        enabled=True,
        note="巴拿马零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_pa", "Hisense"), Brand("samsung_pa", "Samsung"), Brand("tcl_pa", "TCL"), Brand("lg_pa", "LG"), Brand("sony_pa", "Sony"), Brand("philips_pa", "Philips")],
        retail_sites=[
            RetailSite("evision_pa", "Evision", "https://www.evisionstore.com", enabled=True),  # candidate
            RetailSite("multimax_pa", "Multimax", "https://www.multimax.net", enabled=True),  # candidate
            RetailSite("panafoto_pa", "Panafoto", "https://www.panafoto.com", enabled=True),  # candidate
            RetailSite("raenco_pa", "Raenco", "https://www.raenco.com", enabled=True),  # candidate
            RetailSite("rodelag_pa", "Rodelag", "https://rodelag.com", enabled=True),  # candidate
        ],
    ),
    "pl": Region(
        code="pl", name="波兰", currency="PLN", locale="pl-PL",
        enabled=True,
        note="波兰零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_pl", "Hisense"), Brand("samsung_pl", "Samsung"), Brand("tcl_pl", "TCL"), Brand("lg_pl", "LG"), Brand("sony_pl", "Sony"), Brand("philips_pl", "Philips")],
        retail_sites=[
            RetailSite("allegro_pl", "Allegro", "https://allegro.pl", enabled=False),  # blocked
            RetailSite("amazon_pl", "Amazon", "https://www.amazon.pl", enabled=True),  # candidate
            RetailSite("euro_agd_pl", "RTV Euro AGD", "https://www.euro.com.pl", enabled=False),  # blocked
            RetailSite("mediaexpert_pl", "Media Expert", "https://www.mediaexpert.pl", enabled=True),  # candidate
            RetailSite("mediamarkt_pl", "MediaMarkt", "https://www.mediamarkt.pl", enabled=True),  # candidate
            RetailSite("morele_pl", "Morele", "https://www.morele.net", enabled=True),  # candidate
        ],
    ),
    "pt": Region(
        code="pt", name="葡萄牙", currency="EUR", locale="pt-PT",
        enabled=True,
        note="葡萄牙零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_pt", "Hisense"), Brand("samsung_pt", "Samsung"), Brand("tcl_pt", "TCL"), Brand("lg_pt", "LG"), Brand("sony_pt", "Sony"), Brand("philips_pt", "Philips")],
        retail_sites=[
            RetailSite("fnac_pt", "Fnac PT", "https://www.fnac.pt", enabled=False),  # blocked
            RetailSite("radiopopular_pt", "Radio Popular", "https://www.radiopopular.pt", enabled=False),  # blocked
            RetailSite("worten_pt", "Worten PT", "https://www.worten.pt", enabled=False),  # blocked
        ],
    ),
    "ro": Region(
        code="ro", name="罗马尼亚", currency="RON", locale="ro-RO",
        enabled=True,
        note="罗马尼亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ro", "Hisense"), Brand("samsung_ro", "Samsung"), Brand("tcl_ro", "TCL"), Brand("lg_ro", "LG"), Brand("sony_ro", "Sony"), Brand("philips_ro", "Philips")],
        retail_sites=[
            RetailSite("altex_ro", "Altex RO", "https://www.altex.ro", enabled=False),  # blocked
            RetailSite("emag_ro", "eMAG RO", "https://www.emag.ro", enabled=False),  # blocked
            RetailSite("flanco_ro", "Flanco", "https://www.flanco.ro", enabled=False),  # blocked
        ],
    ),
    "rs": Region(
        code="rs", name="塞尔维亚", currency="RSD", locale="sr-RS",
        enabled=True,
        note="塞尔维亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_rs", "Hisense"), Brand("samsung_rs", "Samsung"), Brand("tcl_rs", "TCL"), Brand("lg_rs", "LG"), Brand("sony_rs", "Sony"), Brand("philips_rs", "Philips")],
        retail_sites=[
            RetailSite("ananas_rs", "Ananas", "https://ananas.rs", enabled=True),  # candidate
            RetailSite("gigatron_rs", "Gigatron", "https://gigatron.rs", enabled=False),  # needs_handwritten
            RetailSite("tehnomanija_rs", "Tehnomanija", "https://www.tehnomanija.rs", enabled=False),  # blocked
        ],
    ),
    "ru": Region(
        code="ru", name="俄罗斯", currency="RUB", locale="ru-RU",
        enabled=True,
        note="俄罗斯零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ru", "Hisense"), Brand("samsung_ru", "Samsung"), Brand("tcl_ru", "TCL"), Brand("lg_ru", "LG"), Brand("sony_ru", "Sony"), Brand("philips_ru", "Philips")],
        retail_sites=[
            RetailSite("citilink_ru", "Citilink", "https://www.citilink.ru", enabled=False),  # blocked
            RetailSite("dns_ru", "DNS", "https://www.dns-shop.ru", enabled=False),  # blocked
            RetailSite("eldorado_ru", "Eldorado", "https://www.eldorado.ru", enabled=False),  # blocked
            RetailSite("mvideo_ru", "M.Video", "https://www.mvideo.ru", enabled=False),  # blocked
            RetailSite("ozon_ru", "Ozon", "https://www.ozon.ru", enabled=False),  # blocked
            RetailSite("technopark_ru", "Technopark", "https://www.technopark.ru", enabled=False),  # blocked
            RetailSite("wildberries_ru", "Wildberries", "https://www.wildberries.ru", enabled=False),  # blocked
            RetailSite("yandex_market_ru", "Yandex Market", "https://market.yandex.ru", enabled=False),  # blocked
        ],
    ),
    "se": Region(
        code="se", name="瑞典", currency="SEK", locale="sv-SE",
        enabled=True,
        note="瑞典零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_se", "Hisense"), Brand("samsung_se", "Samsung"), Brand("tcl_se", "TCL"), Brand("lg_se", "LG"), Brand("sony_se", "Sony"), Brand("philips_se", "Philips")],
        retail_sites=[
            RetailSite("amazon_se", "Amazon Sweden", "https://www.amazon.se", enabled=True),  # candidate
            RetailSite("elgiganten_se", "Elgiganten Sweden", "https://www.elgiganten.se", enabled=False),  # blocked
            RetailSite("komplett_se", "Komplett Sweden", "https://www.komplett.se", enabled=False),  # blocked
            RetailSite("power_se", "Power Sweden", "https://www.power.se", enabled=False),  # blocked
        ],
    ),
    "si": Region(
        code="si", name="斯洛文尼亚", currency="EUR", locale="sl-SI",
        enabled=True,
        note="斯洛文尼亚零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_si", "Hisense"), Brand("samsung_si", "Samsung"), Brand("tcl_si", "TCL"), Brand("lg_si", "LG"), Brand("sony_si", "Sony"), Brand("philips_si", "Philips")],
        retail_sites=[
            RetailSite("bigbang_si", "Big Bang SI", "https://www.bigbang.si", enabled=False),  # blocked
            RetailSite("harveynorman_si", "Harvey Norman SI", "https://www.harveynorman.si", enabled=True),  # candidate
            RetailSite("mimovrste_si", "Mimovrste", "https://www.mimovrste.com", enabled=False),  # blocked
        ],
    ),
    "sk": Region(
        code="sk", name="斯洛伐克", currency="EUR", locale="sk-SK",
        enabled=True,
        note="斯洛伐克零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_sk", "Hisense"), Brand("samsung_sk", "Samsung"), Brand("tcl_sk", "TCL"), Brand("lg_sk", "LG"), Brand("sony_sk", "Sony"), Brand("philips_sk", "Philips")],
        retail_sites=[
            RetailSite("alza_sk", "Alza SK", "https://www.alza.sk", enabled=False),  # blocked
            RetailSite("datart_sk", "Datart SK", "https://www.datart.sk", enabled=True),  # candidate
            RetailSite("nay_sk", "Nay", "https://www.nay.sk", enabled=True),  # candidate
        ],
    ),
    "tr": Region(
        code="tr", name="土耳其", currency="TRY", locale="tr-TR",
        enabled=True,
        note="土耳其零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_tr", "Hisense"), Brand("samsung_tr", "Samsung"), Brand("tcl_tr", "TCL"), Brand("lg_tr", "LG"), Brand("sony_tr", "Sony"), Brand("philips_tr", "Philips")],
        retail_sites=[
            RetailSite("amazon_tr", "Amazon TR", "https://www.amazon.com.tr", enabled=True),  # candidate
            RetailSite("hepsiburada_tr", "Hepsiburada", "https://www.hepsiburada.com", enabled=False),  # blocked
            RetailSite("mediamarkt_tr", "MediaMarkt TR", "https://www.mediamarkt.com.tr", enabled=False),  # blocked
            RetailSite("teknosa_tr", "Teknosa", "https://www.teknosa.com", enabled=False),  # blocked
            RetailSite("trendyol_tr", "Trendyol", "https://www.trendyol.com", enabled=True),  # candidate
            RetailSite("vatan_tr", "Vatan", "https://www.vatanbilgisayar.com", enabled=False),  # blocked
        ],
    ),
    "ua": Region(
        code="ua", name="乌克兰", currency="UAH", locale="uk-UA",
        enabled=True,
        note="乌克兰零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_ua", "Hisense"), Brand("samsung_ua", "Samsung"), Brand("tcl_ua", "TCL"), Brand("lg_ua", "LG"), Brand("sony_ua", "Sony"), Brand("philips_ua", "Philips")],
        retail_sites=[
            RetailSite("allo_ua", "Allo", "https://allo.ua", enabled=False),  # blocked
            RetailSite("comfy_ua", "Comfy", "https://comfy.ua", enabled=True),  # candidate
            RetailSite("foxtrot_ua", "Foxtrot UA", "https://www.foxtrot.com.ua", enabled=False),  # blocked
            RetailSite("rozetka_ua", "Rozetka UA", "https://rozetka.com.ua", enabled=False),  # blocked
        ],
    ),
    "uk": Region(
        code="uk", name="英国", currency="GBP", locale="en-GB",
        enabled=True,
        note="英国零售线（spec 驱动，自动生成）",
        brands=[Brand("hisense_uk", "Hisense"), Brand("samsung_uk", "Samsung"), Brand("tcl_uk", "TCL"), Brand("lg_uk", "LG"), Brand("sony_uk", "Sony"), Brand("philips_uk", "Philips")],
        retail_sites=[
            RetailSite("amazon_uk", "Amazon", "https://www.amazon.co.uk", enabled=True),  # candidate
            RetailSite("ao_uk", "AO", "https://ao.com", enabled=False),  # blocked
            RetailSite("argos_uk", "Argos", "https://www.argos.co.uk/browse/technology/televisions", enabled=False),  # blocked
            RetailSite("currys_uk", "Currys", "https://www.currys.co.uk", enabled=True),  # candidate
            RetailSite("ebay_uk", "eBay UK", "https://www.ebay.co.uk", enabled=False),  # blocked
            RetailSite("hughes_uk", "Hughes UK", "https://www.hughes.co.uk", enabled=True),  # candidate
            RetailSite("jd_uk", "JD Williams", "https://www.jdwilliams.co.uk", enabled=False),  # blocked
            RetailSite("jlp_uk", "John Lewis", "https://www.johnlewis.com", enabled=True),  # candidate
            RetailSite("joybuy_uk", "Joybuy", "https://www.joybuy.co.uk", enabled=False),  # blocked
            RetailSite("markselectrical_uk", "Marks Electrical", "https://www.markselectrical.co.uk", enabled=True),  # candidate
            RetailSite("richersounds_uk", "Richer Sounds", "https://www.richersounds.com", enabled=False),  # blocked
            RetailSite("very_uk", "Very", "https://www.very.co.uk", enabled=False),  # blocked
        ],
    ),
}


# 已有区域漏登记的零售站（有 spec + 零售 adapter）。品牌官网商城也在此列，
# 默认按 spec.status 决定 enabled。
EXTRA_RETAIL_SITES: dict[str, list[RetailSite]] = {
    "bo": [
        RetailSite("hisense_bo", "Hisense（玻利维亚）", "https://hisense.com.bo", enabled=True),  # candidate
        RetailSite("samsung_bo", "Samsung（玻利维亚）", "https://samsung.com.bo", enabled=True),  # candidate
        RetailSite("tcl_bo", "TCL（玻利维亚）", "https://web.tcl.bo", enabled=True),  # candidate
    ],
    "cl": [
        RetailSite("tcl_cl", "TCL（智利）", "https://tclstore.cl", enabled=True),  # candidate
    ],
    "co": [
        RetailSite("hisense_co", "Hisense Colombia", "https://hisense.com.co", enabled=True),  # approved
    ],
    "ec": [
        RetailSite("cresa_ec_more", "Cresa More", "https://www.crecos.com", enabled=True),  # candidate
        RetailSite("hisense_ec", "Hisense Ecuador", "https://www.hisense.ec", enabled=True),  # approved
        RetailSite("laganga_ec2", "L-Ganga", "https://laganga.com", enabled=True),  # candidate
        RetailSite("lg_ec", "LG Shop Ecuador", "https://www.lgshop.com.ec", enabled=True),  # approved
        RetailSite("tcl_ec", "TCL Ecuador", "https://tclecuador.com.ec", enabled=False),  # blocked
    ],
    "pe": [
        RetailSite("falabella_pe", "Falabella Peru", "https://www.falabella.com.pe", enabled=True),  # approved
        RetailSite("hisense_pe", "Hisense Perú", "https://www.hisense.com.pe", enabled=True),  # approved
        RetailSite("ripley_pe", "Ripley PE", "https://simple.ripley.com.pe", enabled=False),  # blocked
        RetailSite("sodimac_pe", "Sodimac Perú", "https://www.sodimac.com.pe", enabled=True),  # approved
        RetailSite("tottus_pe", "Tottus PE", "https://www.tottus.com.pe", enabled=False),  # blocked
    ],
}
