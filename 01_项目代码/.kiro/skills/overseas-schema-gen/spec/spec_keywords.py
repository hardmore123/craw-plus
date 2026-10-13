"""spec-schema-gen 的多语言规格关键词表。

probe.py 用它判断"页面某个结构里是不是含规格内容"。设计原则：
- **不预判站点语种**：probe 默认用 ALL_KEYWORDS（全语言并集）匹配，哪个语言的规格词
  命中都算数。德语站命中德语词、南美站命中西语词，全自动、零配置。
- **一处补、全语系受益**：某站因某语言词不全导致 probe 漏判规格区时，往对应语言补几个
  词即可，该语系所有站都受益。

覆盖的语种：
- ja 日语：Sony/REGZA/Hisense/Sharp/Panasonic/TCL 日本站
- en 英语：加拿大 + 美国 + 英国站
- es 西班牙语：墨西哥 + 南美主力（秘鲁/厄瓜多尔/阿根廷/哥伦比亚/智利/玻利维亚…）
- de 德语：Philips 德国
- pt 葡萄牙语：巴西线（未来）

补词指引见 reference.md「多语言关键词表」一节。
"""

# 各语言的规格项目名/属性词（小写化匹配时用小写；日文无大小写）
SPEC_KEYWORDS_BY_LANG = {
    "ja": [
        "サイズ", "解像度", "パネル", "消費電力", "寸法", "重量", "チューナー",
        "リフレッシュ", "画素", "視野角", "画面", "外形", "本体", "端子", "入力",
        "出力", "スピーカー", "音声", "電源", "付属品", "機能", "対応",
    ],
    "en": [
        "size", "resolution", "panel", "power", "weight", "dimension", "dimensions",
        "tuner", "refresh", "display", "screen", "brightness", "contrast", "hdr",
        "speaker", "audio", "input", "output", "connectivity", "processor", "backlight",
        "viewing angle", "response time", "voltage", "consumption", "inch", "diagonal",
    ],
    "es": [
        "tamaño", "resolución", "pantalla", "potencia", "consumo", "peso",
        "dimensiones", "dimensión", "sintonizador", "frecuencia", "pulgadas",
        "brillo", "contraste", "altavoz", "altavoces", "audio", "entrada", "entradas",
        "salida", "salidas", "conectividad", "procesador", "retroiluminación",
        "ángulo", "tensión", "voltaje", "diagonal", "panel", "actualización",
    ],
    "de": [
        "größe", "grösse", "auflösung", "bildschirm", "anzeige", "leistung",
        "gewicht", "abmessungen", "abmessung", "tuner", "bildwiederholrate",
        "helligkeit", "kontrast", "lautsprecher", "eingang", "eingänge", "ausgang",
        "ausgänge", "anschlüsse", "prozessor", "diagonale", "verbrauch",
        "zoll", "spannung", "bildschirmgröße",
    ],
    "pt": [
        "tamanho", "resolução", "tela", "potência", "consumo", "peso",
        "dimensões", "dimensão", "sintonizador", "frequência", "polegadas",
        "brilho", "contraste", "alto-falante", "áudio", "entrada", "entradas",
        "saída", "saídas", "conectividade", "processador", "retroiluminação",
        "ângulo", "tensão", "diagonal", "atualização",
    ],
    # 单位/技术符号：语言无关，所有站通用
    "units": [
        "cm", "mm", "kg", "Hz", "HDMI", "USB", "bit", "4K", "8K", "inch",
        "V型", "ppi", "nits", "cd/m", "kWh", "VESA", "Wi-Fi", "Bluetooth",
    ],
}


def all_keywords() -> list[str]:
    """全语言并集（去重，保序）。probe 默认用这个，不预判语种。"""
    seen: set[str] = set()
    out: list[str] = []
    for words in SPEC_KEYWORDS_BY_LANG.values():
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


ALL_KEYWORDS = all_keywords()


# ═══════════════════════════════════════════════════════════════
#  卖点关键词（多语言）
# ═══════════════════════════════════════════════════════════════
# probe.py --sp 模式用这些词判断"页面某个结构里是不是含卖点内容"。
# 设计原则同规格关键词：不预判站点语种，用全语言并集匹配。

SP_KEYWORDS_BY_LANG = {
    "ja": [
        "特徴", "機能", "画質", "音質", "デザイン", "新機能", "進化",
        "迫力", "没入", "臨場感", "美しい", "圧倒的", "高性能", "最新",
        "テクノロジー", "体験", "映像", "音響", "スマート", "AI",
        "4K", "8K", "HDR", "有機EL", "OLED", "QLED", "Mini LED",
        "高画質", "高音質", "リフレッシュレート", "ゲーミング",
    ],
    "en": [
        "feature", "highlight", "benefit", "advantage", "technology",
        "experience", "immersive", "stunning", "powerful", "premium",
        "picture quality", "sound quality", "design", "smart", "gaming",
        "4K", "8K", "HDR", "OLED", "QLED", "Mini LED", "Dolby",
        "cinema", "vision", "clarity", "contrast", "color", "brightness",
        "innovation", "performance", "revolutionary", "ultimate",
    ],
    "es": [
        "característica", "función", "calidad", "imagen", "sonido",
        "diseño", "experiencia", "inmersivo", "potente", "premium",
        "tecnología", "innovación", "rendimiento", "inteligente",
        "gaming", "4K", "8K", "HDR", "OLED", "QLED", "Mini LED",
        "cine", "visión", "claridad", "contraste", "color", "brillo",
    ],
    "de": [
        "Funktion", "Eigenschaft", "Qualität", "Bild", "Ton",
        "Design", "Erlebnis", "immersive", "Leistung", "Premium",
        "Technologie", "Innovation", "intelligent", "Gaming",
        "4K", "8K", "HDR", "OLED", "QLED", "Mini LED",
        "Kino", "Klarheit", "Kontrast", "Farbe", "Helligkeit",
    ],
    "pt": [
        "recurso", "função", "qualidade", "imagem", "som",
        "design", "experiência", "imersivo", "potente", "premium",
        "tecnologia", "inovação", "desempenho", "inteligente",
        "gaming", "4K", "8K", "HDR", "OLED", "QLED", "Mini LED",
        "cinema", "clareza", "contraste", "cor", "brilho",
    ],
}


def all_sp_keywords() -> list[str]:
    """卖点关键词全语言并集（去重，保序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for words in SP_KEYWORDS_BY_LANG.values():
        for w in words:
            if w not in seen:
                seen.add(w)
                out.append(w)
    return out


ALL_SP_KEYWORDS = all_sp_keywords()
