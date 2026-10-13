"""声明式抽取引擎。

抽取规则写在站点目录的 schema.json 里，不写进 Python —— 这是应对
Amazon 这类页面模板频繁变动的关键：改选择器只改配置，不动代码、不重新部署。

规则形态（字段级，按 selectors 顺序逐个尝试，第一个非空即采用）：
    {"selectors": ["#productTitle", "h1.title"], "transform": "clean_text"}
    {"selectors": ["#acrPopover"], "attr": "title", "transform": "rating"}
    {"self_attr": "id"}                                    # 容器元素自身属性
    {"kv": {"container": "#detailBullets li", "key_contains": "model number"}}
    {"regex": "\\"asin\\"\\s*:\\s*\\"([A-Z0-9]{10})\\""}     # 兜底：对整页 HTML 正则
    {"jsonld": "offers.price"}                             # 兜底：schema.org 结构化数据

多选择器兜底链（fallback chain）不是过度设计：实测中
#productDetails_techSpec_section_1 在部分模板不存在，型号实际在
#detailBullets_feature_div，必须逐个试。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

from .fetchers import Dom
from .models import Review, ReviewSummary, SpecItem

# ---------------------------------------------------------------- transforms

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"\d[\d,.\s\u00a0]*")
_CUR_PATTERNS = (
    # 先匹配带符号/缩写的明确货币（优先级高）
    # ★ 单元素 marks 必须带尾逗号 ("xxx",) 否则 Python 当字符串遍历字符
    ("CAD", ("cdn$", "c$", "ca$", "cad")),
    ("USD", ("us$", "usd")),
    ("EUR", ("€", "eur")),
    ("GBP", ("£", "gbp")),
    ("JPY", ("¥", "￥", "jpy", "円")),
    ("RUB", ("₽", "руб", "rub")),
    ("TRY", ("₺", "try")),
    ("CHF", ("chf",)),
    ("PLN", ("zł", "pln")),
    ("CZK", ("kč", "czk")),
    ("RON", ("lei", "ron")),
    ("HUF", ("ft", "huf")),
    ("BGN", ("лв", "bgn")),
    ("BAM", ("bam",)),
    ("UAH", ("₴", "uah", "грн")),
    ("HRK", ("kn", "hrk")),
    ("RSD", ("rsd", "din", "дин")),
    ("ISK", ("isk",)),
    ("MXN", ("mxn", "m.n.", "mn$")),
    ("BRL", ("r$", "brl")),
    ("ARS", ("ars",)),
    ("CLP", ("clp",)),
    ("COP", ("cop",)),
    ("PEN", ("s/", "pen")),
    ("BOB", ("bs.", "bob")),
    ("GTQ", ("gtq",)),
    # 北欧 kr 系放最后（kr 对 SEK/NOK/DKK 都通用，靠站点级 transform 区分）
    ("SEK", ("sek", "kr")),
    ("NOK", ("nok",)),
    ("DKK", ("dkk",)),
)


def t_clean_text(v: str) -> str:
    return _WS_RE.sub(" ", (v or "").replace("\u200e", "").replace("\u200f", "")).strip()


def t_money(v: str) -> float | None:
    """从价格文本解析金额。兼容 'CDN$ 4,999.99' / '$1,299.00' / '1 299,00 €'。"""
    if not v:
        return None
    # 日元符号 ¥ / ￥ 视为非本站货币，跳过不造假价（缺价>错价）
    if "¥" in v or "￥" in v:
        return None
    m = _NUM_RE.search(v.replace("\u00a0", " "))
    if not m:
        return None
    s = m.group(0).strip().replace(" ", "")
    # 判定小数分隔符：取最后出现的 . 或 , 且其后位数 <= 2
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    dec = max(last_dot, last_comma)
    if dec != -1 and len(s) - dec - 1 in (1, 2):
        int_part = re.sub(r"[.,]", "", s[:dec])
        frac = s[dec + 1:]
        s = f"{int_part}.{frac}"
    else:
        # 逗号后跟 5 位（如 "2,49500" = $2,495.00 缺小数点）→ 逗号千分位+末2位小数
        # Amazon 非美国 IP 偶发渲染 "¥249,500" → "$2,49500"（逗号替代小数点）
        if last_comma != -1 and len(s) - last_comma - 1 == 5:
            int_part = re.sub(r"[.,]", "", s[:last_comma]) + s[last_comma + 1 : -2]
            frac = s[-2:]
            s = f"{int_part}.{frac}"
        else:
            s = re.sub(r"[.,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def t_currency(v: str) -> str:
    low = (v or "").lower()
    for code, marks in _CUR_PATTERNS:
        if any(m in low for m in marks):
            return code
    if "$" in low:
        return "CAD"          # 本项目面向加拿大站点，裸 $ 视为 CAD
    return ""


def t_currency_mx(v: str) -> str:
    """墨西哥站专用货币归一：裸 $ / MXN / M.N. / MN$ 一律视为 MXN。

    墨西哥零售站价格常写「$12,999.00」「$12,999 MXN」「$12,999 M.N.」，与加拿大站
    的裸 $=CAD 冲突，因此单列一个 transform 供 *_mx 站点 schema 使用，不改动
    公共 t_currency（避免影响加拿大/美国线）。识别到明确的 USD/EUR 等仍按原样返回。"""
    low = (v or "").lower()
    if any(m in low for m in ("mxn", "m.n.", "mn$", "pesos")):
        return "MXN"
    for code, marks in _CUR_PATTERNS:
        if code == "CAD":
            continue          # 墨西哥站不把裸 $ 当 CAD
        if any(m in low for m in marks):
            return code
    if "$" in low:
        return "MXN"          # 墨西哥站裸 $ 视为 MXN
    return "MXN"              # 墨西哥站兜底 MXN


def t_currency_us(v: str) -> str:
    """美国站专用货币归一：裸 $ / USD 一律视为 USD。

    与 t_currency_mx 同模式：公共 t_currency 把裸 $ 当 CAD（面向加拿大站），
    但 amazon_us 等 US 站的裸 $ 应为 USD，因此单列此 transform。
    识别到明确的 EUR/GBP 等仍按原样返回（防止误判跨境页面）。"""
    low = (v or "").lower()
    for code, marks in _CUR_PATTERNS:
        if code == "CAD":
            continue          # US 站不把裸 $ 当 CAD
        if any(m in low for m in marks):
            return code
    if "$" in low:
        return "USD"          # US 站裸 $ 视为 USD
    return "USD"              # US 站兜底 USD


def t_currency_cl(v: str) -> str:
    """智利站专用货币归一：裸 $ / CLP 一律视为 CLP。

    智利零售站价格写「$1.299.990」「CLP $1.299.990」，与加拿大裸 $=CAD 冲突，
    单列 transform 供 *_cl 站点 schema 使用。识别到明确的 USD/EUR 等仍按原样返回。"""
    low = (v or "").lower()
    for code, marks in _CUR_PATTERNS:
        if code == "CAD":
            continue
        if any(m in low for m in marks):
            return code
    if "$" in low:
        return "CLP"
    return "CLP"


def t_currency_co(v: str) -> str:
    """哥伦比亚站专用货币归一：裸 $ / COP / col$ 一律视为 COP。"""
    low = (v or "").lower()
    if any(m in low for m in ("cop", "col$", "peso")):
        return "COP"
    for code, marks in _CUR_PATTERNS:
        if code == "CAD":
            continue
        if any(m in low for m in marks):
            return code
    if "$" in low:
        return "COP"
    return "COP"


def t_money_cl(v: str) -> float | None:
    """智利 CLP / 哥伦比亚 COP 大数字解析：无小数、点/逗号作千分位。

    CLP/COP 是无小数货币，价格以整数 + 点千分位书写（$1.299.990 = 1299990）。
    通用 t_money 在尾段为 2 位时会误判为小数（$899.90 → 899.9，实际应 899990），
    故对智利/哥伦比亚大数字单列：去掉所有 . , 空格后取整数。"""
    if not v:
        return None
    m = _NUM_RE.search(v.replace("\u00a0", " "))
    if not m:
        return None
    s = re.sub(r"[^\d]", "", m.group(0))
    try:
        return float(s) if s else None
    except ValueError:
        return None


# money_co 与 money_cl 逻辑一致（COP/CLP 都是无小数大数字货币）
t_money_co = t_money_cl


def t_int(v: str) -> int | None:
    if not v:
        return None
    m = _NUM_RE.search(v.replace("\u00a0", " "))
    if not m:
        return None
    s = re.sub(r"[^\d]", "", m.group(0))
    try:
        return int(s) if s else None
    except ValueError:
        return None


def t_float(v: str) -> float | None:
    return t_money(v)


def t_rating(v: str) -> float | None:
    """从 '4.5 out of 5 stars' / '4,5 sur 5' 取评分。"""
    if not v:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", v)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def t_bool_present(v: str) -> bool:
    return bool((v or "").strip())


_BRAND_NOISE = (
    (re.compile(r"^\s*visit\s+the\s+(.+?)\s+store\s*$", re.I), 1),
    (re.compile(r"^\s*visitez\s+la\s+boutique\s+(.+?)\s*$", re.I), 1),
    (re.compile(r"^\s*visita\s+la\s+tienda\s+de\s+(.+?)\s*$", re.I), 1),
    (re.compile(r"^\s*brand\s*[:：]\s*(.+?)\s*$", re.I), 1),
    (re.compile(r"^\s*marque\s*[:：]\s*(.+?)\s*$", re.I), 1),
    (re.compile(r"^\s*(.+?)\s+store\s*$", re.I), 1),
)


def t_brand(v: str) -> str:
    """清洗品牌噪音。Amazon 的 #bylineInfo 实测返回 'Visit the LG Store'。"""
    s = t_clean_text(v)
    if not s:
        return ""
    for rx, g in _BRAND_NOISE:
        m = rx.match(s)
        if m:
            return t_clean_text(m.group(g))
    return s


_SIZE_INCH_RE = re.compile(
    r"(\d{2,3}(?:\.\d)?)\s*(?:\"|”|″|inch|inches|in\b|型|v型|v型|-?インチ|インチ)", re.I)
_SIZE_NUM_RE = re.compile(r"\b(\d{2,3}(?:\.\d)?)\b")


def t_size_inch(v: str) -> str:
    """把各种尺寸写法统一为 X" 格式。

    覆盖：65 Inch / 65" / 65 inches / 65-inch / 65 in / 65型 / 65V型 / 65インチ。
    优先按英寸标记提取；无标记但有 2~3 位纯数字（TV 尺寸区间）时也取。
    取不到返回空串。整数去掉小数点（65.0 → 65）。
    """
    s = t_clean_text(v)
    if not s:
        return ""
    m = _SIZE_INCH_RE.search(s)
    num = None
    if m:
        num = m.group(1)
    else:
        m2 = _SIZE_NUM_RE.search(s)
        # 仅当整串就是个尺寸数字（避免把 3840 之类误当尺寸），限定 20~120 区间
        if m2:
            try:
                val = float(m2.group(1))
                if 20 <= val <= 120:
                    num = m2.group(1)
            except ValueError:
                num = None
    if not num:
        return ""
    try:
        f = float(num)
        num = str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        pass
    return f'{num}"'


_PALACIO_MODEL_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9][A-Za-z0-9-]{4,}(?![A-Za-z0-9])")


def t_palacio_model(v: str) -> str:
    """从 Palacio 商品标题中提取含字母和数字的电视型号 token。"""
    s = t_clean_text(v)
    if not s:
        return ""
    for token in _PALACIO_MODEL_TOKEN_RE.findall(s):
        if any(ch.isalpha() for ch in token) and any(ch.isdigit() for ch in token):
            return token.upper()
    return s


def t_in_stock(v: str) -> bool | None:
    """库存判断，覆盖英语/法语以及墨西哥站常见的 Disponible/InStock。"""
    low = (v or "").lower()
    if not low:
        return None
    compact = re.sub(r"[^a-z]", "", low)
    if any(k in low for k in ("out of stock", "unavailable", "sold out",
                              "rupture de stock", "non disponible", "agotado")) \
            or any(k in compact for k in ("outofstock", "unavailable", "soldout", "nodisponible")):
        return False
    if any(k in low for k in ("in stock", "en stock", "add to cart",
                              "ajouter au panier", "available", "disponible")) \
            or any(k in compact for k in ("instock", "enstock", "addtocart", "disponible")):
        return True
    return None


def t_liverpool_money(v: str) -> float | None:
    r"""解析 Liverpool 在线 DOM 的金额。

    Liverpool 价格区小数点常被 invisible span 隐藏，clean_text 后形成：
    1) 带千分逗号但末段非3位：'$11,49930' → 11499.30（正常千分位末段是3位）
    2) 无任何小数分隔的大整数：'$2197425 MXN' → 21974.25（正常价格无小数点）

    策略：先用标准 t_money 解析（处理正常格式），若结果 >= 100000（明显异常高价）
    且原始文本无真正小数点，则末2位当分修正。带逗号且末段非3位也修正。
    """
    s = t_clean_text(v)
    if not s:
        return None
    # 先用标准 t_money 解析
    val = t_money(s)
    if val is None:
        return None
    # 提取数字部分（去掉$和字母）
    import re as _re
    m = _re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", s)
    if not m:
        return val
    raw_num = m.group(1)
    has_real_decimal = "." in raw_num
    # 无真正小数点 + >= 100000 → 小数点被吃掉，末2位当分
    if not has_real_decimal and val >= 100000:
        sv = str(int(val))
        return float(sv[:-2] + "." + sv[-2:])
    # 带逗号但无小数点 + 末段非3位 → invisible span 隐藏
    if not has_real_decimal and "," in raw_num:
        parts = raw_num.split(",")
        last_seg = parts[-1]
        if len(last_seg) != 3 and len(last_seg) >= 2:
            # 逗号后末段非3位说明不是千分位而是隐藏小数
            int_part = "".join(parts[:-1]) + last_seg[:-2]
            frac = last_seg[-2:]
            try:
                return float(int_part + "." + frac)
            except ValueError:
                pass
    return val


TRANSFORMS = {
    "clean_text": t_clean_text,
    "money": t_money,
    "money_cl": t_money_cl,
    "money_co": t_money_co,
    "liverpool_money": t_liverpool_money,
    "currency": t_currency,
    "currency_mx": t_currency_mx,
    "currency_us": t_currency_us,
    "currency_cl": t_currency_cl,
    "currency_co": t_currency_co,
    "int": t_int,
    "float": t_float,
    "rating": t_rating,
    "bool_present": t_bool_present,
    "in_stock": t_in_stock,
    "brand": t_brand,
    "palacio_model": t_palacio_model,
    "size_inch": t_size_inch,
}


def apply_transform(raw: str, name: str) -> Any:
    if not name:
        return t_clean_text(raw)
    fn = TRANSFORMS.get(name)
    if fn is None:
        raise ValueError(f"未知 transform: {name}（可用: {sorted(TRANSFORMS)}）")
    return fn(raw)


# ---------------------------------------------------------------- JSON-LD

_LDJSON_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.S | re.I)


def jsonld_blocks(html: str) -> list[Any]:
    out = []
    for m in _LDJSON_RE.finditer(html or ""):
        try:
            out.append(json.loads(m.group(1).strip()))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


_CANONICAL_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]*href=["\']([^"\']+)["\']'
    r'|<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']canonical["\']', re.I)


def _url_path(u: str) -> str:
    u = re.sub(r"^https?://[^/]+", "", str(u or "").strip())
    return u.split("?", 1)[0].split("#", 1)[0].rstrip("/")


def jsonld_find_product(html: str) -> dict | None:
    """在 JSON-LD 中找当前页的商品节点（@type=Product / ProductGroup）。

    ★尺寸变体陷阱（MediaMarkt 实测 2026-10）：主节点是 ProductGroup（自带
    offers=当前尺寸的价），hasVariant 里列出同系列 43/50/55/65 各尺寸的 Product。
    旧逻辑「深度优先取第一个 Product」会拿到第一个变体（43 寸）的价，导致同系列
    不同尺寸价格完全相同（错价）。现在的优先级：
      1) 变体的 url / offers.url 与页面 canonical 路径一致 → 该变体；
      2) 自带 offers 的 ProductGroup / Product（最先出现的）→ 它；
      3) 兜底：第一个 Product（旧行为）。
    """
    groups: list[dict] = []      # 自带 offers 的 Product/ProductGroup，按出现顺序
    products: list[dict] = []    # 所有 Product，按出现顺序

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            types = {str(x).lower() for x in (t if isinstance(t, list) else [t] if t else [])}
            if types & {"product", "productgroup"}:
                if "product" in types:
                    products.append(node)
                if node.get("offers"):
                    groups.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for b in jsonld_blocks(html):
        walk(b)
    if not products and not groups:
        return None
    m = _CANONICAL_RE.search(html or "")
    canon = _url_path((m.group(1) or m.group(2)) if m else "")
    if canon:
        for n in products:
            offers = n.get("offers")
            offers = offers[0] if isinstance(offers, list) and offers else offers
            for u in (n.get("url"), offers.get("url") if isinstance(offers, dict) else None):
                if u and _url_path(u) == canon:
                    # 变体节点通常不带 aggregateRating/review（挂在主节点上），
                    # 用主节点字段打底、变体字段覆盖，评分与价格都对得上。
                    if groups and groups[0] is not n:
                        return {**groups[0], **n}
                    return n
    if groups:
        return groups[0]
    return products[0]


def dig(node: Any, path: str) -> Any:
    """按 'offers.price' 取值，遇 list 取第一个元素。"""
    cur = node
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[0] if cur else None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    if isinstance(cur, list):
        cur = cur[0] if cur else None
    return cur


# ---------------------------------------------------------------- Schema


def load_schema(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Extractor:
    """按 schema 从 Dom（或 HTML 文本）抽取结构化数据。"""

    def __init__(self, schema: dict, html: str = "", base_url: str = ""):
        self.schema = schema or {}
        self.html = html
        self.base_url = base_url
        self._ld: dict | None | bool = False      # 懒加载

    def _jsonld_value(self, rule: dict) -> str:
        """取 JSON-LD 字段值（支持多候选路径）；无则空串。"""
        ld_path = rule.get("jsonld")
        if not (ld_path and self.html):
            return ""
        if self._ld is False:
            self._ld = jsonld_find_product(self.html)
        if not self._ld:
            return ""
        for p in (ld_path if isinstance(ld_path, list) else [ld_path]):
            v = dig(self._ld, p)
            if v is not None:
                return str(v)
        return ""

    # ---- 单字段 ----
    def raw(self, dom: Dom | None, rule: dict) -> str:
        if not isinstance(rule, dict):
            return ""
        # 0) jsonld_first：显式要求 JSON-LD 优先于 DOM 选择器。
        # 动机（MMS 集团实测）：PDP 第一个 [data-test='mms-price'] 是「含保修/套餐」价
        # (QE55QN77FAT DOM=3899) 而非主售价(JSON-LD offers.price=3299)，DOM 选择器
        # 先命中就会写错价。对这类「结构化价可靠、DOM 首价不可信」的站用此开关。
        if rule.get("jsonld_first"):
            v = self._jsonld_value(rule)
            if v:
                return v
        # 1) 容器自身属性（评价条目 id 等）
        if rule.get("self_attr") and dom is not None:
            v = dom.self_attr(rule["self_attr"])
            if v:
                return v
        # 1b) 容器自身文本。零售搜索卡片常常就是 <a>…标题…</a>，卡片内没有
        # 稳定的标题子选择器；`{"self_text": true}` 直接取卡片文本，
        # 比猜类名稳（Costco 的卡片标题实测没有可用的 class）。
        if rule.get("self_text") and dom is not None:
            v = dom.self_text()
            if v:
                return v
        # 2) 选择器链
        if dom is not None:
            attr = rule.get("attr")
            for sel in rule.get("selectors") or []:
                v = dom.attr(sel, attr) if attr else dom.text(sel)
                if v:
                    return v
        # 3) 键值列表（label: value 结构）
        kv = rule.get("kv")
        if kv and dom is not None:
            v = self._kv_lookup(dom, kv)
            if v:
                return v
        # 4) 正则兜底：默认搜标题区域（避免全HTML匹配到DOCTYPE/META等），
        #    regex_scope="html" 时搜全页
        rx = rule.get("regex")
        if rx and self.html:
            scope = rule.get("regex_scope", "title")
            search_text = self.html
            if scope == "title":
                # 优先搜h1/title/og:title文本，避免全HTML误匹配DOCTYPE等
                for t_sel in ("h1", "title", "meta[property='og:title']"):
                    try:
                        tv = dom.attr(t_sel, "content") or dom.text(t_sel) if dom is not None else ""
                        if tv and len(tv) > 3:
                            search_text = tv
                            break
                    except Exception:
                        pass
                if search_text is self.html and dom is not None:
                    # 回退：搜body文本前2000字符
                    bt = dom.text("body") or ""
                    if bt:
                        search_text = bt[:2000]
            m = re.search(rx, search_text, re.S | re.I)
            if m:
                val = (m.group(1) if m.groups() else m.group(0)).strip()
                # 排除HTML标签/DOCTYPE等误匹配
                if val and val.upper() not in ("DOCTYPE", "HTML", "HEAD", "BODY", "META", "LINK", "STYLE", "SCRIPT", "TITLE"):
                    return val
        # 5) JSON-LD 兜底（jsonld_first 已在步骤 0 取过，这里不会重复命中）
        v = self._jsonld_value(rule)
        if v:
            return v
        # 6) 默认值兜底（选择器/jsonld全未命中时返回default）
        default = rule.get("default")
        if default:
            return str(default)
        return ""

    def value(self, dom: Dom | None, rule: dict) -> Any:
        return apply_transform(self.raw(dom, rule), (rule or {}).get("transform", ""))

    def _kv_lookup(self, dom: Dom, kv: dict) -> str:
        """在 container 列表里按 key 关键字找对应值。

        Amazon 的 #detailBullets_feature_div li 形如
        'Item model number ‏ : ‎ OLED77G6WUA'，按分隔符切开取右半。
        """
        container = kv.get("container") or ""
        want = (kv.get("key_contains") or "").lower()
        if not container or not want:
            return ""
        for item in dom.sub(container, limit=int(kv.get("limit", 120))):
            text = t_clean_text(item.self_text())
            if not text or want not in text.lower():
                continue
            # 优先用子选择器（表格 th/td 结构）
            k_sel, v_sel = kv.get("key"), kv.get("value")
            if v_sel:
                v = item.text(v_sel)
                if v:
                    return t_clean_text(v)
            for sep in (":", "：", "\n"):
                if sep in text:
                    left, _, right = text.partition(sep)
                    if want in left.lower() and right.strip():
                        return t_clean_text(right)
            return text
        return ""

    # ---- 分组 ----
    def fields(self, dom: Dom | None, group: str) -> dict:
        spec = self.schema.get(group) or {}
        out: dict[str, Any] = {}
        for name, rule in spec.items():
            try:
                out[name] = self.value(dom, rule)
            except ValueError:
                raise
            except Exception:
                out[name] = None
        return out

    def specs(self, dom: Dom | None) -> list[SpecItem]:
        """规格：支持 table（th/td）与 kvlist（label: value）两种形态，可配多组。"""
        rules = self.schema.get("specs") or []
        if isinstance(rules, dict):
            rules = [rules]
        out: list[SpecItem] = []
        seen: set[str] = set()
        if dom is None:
            return out
        for rule in rules:
            container = rule.get("container") or ""
            if not container:
                continue
            kind = rule.get("type") or "table"
            skip = [s.lower() for s in (rule.get("skip_keys") or [])]
            for row in dom.sub(container, limit=int(rule.get("limit", 200))):
                key = value = ""
                if kind == "table":
                    key = t_clean_text(row.text(rule.get("key") or "th"))
                    value = t_clean_text(row.text(rule.get("value") or "td"))
                else:                                  # kvlist
                    text = t_clean_text(row.self_text())
                    for sep in (":", "："):
                        if sep in text:
                            k, _, v = text.partition(sep)
                            key, value = t_clean_text(k), t_clean_text(v)
                            break
                if not key or not value:
                    continue
                kl = key.lower()
                if kl in seen or any(s in kl for s in skip) or len(key) > 120:
                    continue
                seen.add(kl)
                out.append(SpecItem(key=key[:120], value=value[:1000]))
        return out

    def reviews(self, dom: Dom | None) -> list[Review]:
        cfg = self.schema.get("reviews") or {}
        container = cfg.get("container") or ""
        fields = cfg.get("fields") or {}
        if dom is None or not container or not fields:
            return []
        media = cfg.get("media") or {}
        out: list[Review] = []
        for i, block in enumerate(dom.sub(container, limit=int(cfg.get("limit", 60)))):
            vals: dict[str, Any] = {}
            for name, rule in fields.items():
                try:
                    vals[name] = self.value(block, rule)
                except Exception:
                    vals[name] = None
            images = self._media_list(block, media.get("images"))
            videos = self._media_list(block, media.get("videos"))
            review_url = str(vals.get("review_url") or "").strip()
            key = str(vals.get("review_key") or "").strip()
            if not key:
                # 没有站内 id 时用内容哈希兜底，保证增量去重仍可用
                basis = f"{vals.get('author','')}|{vals.get('review_date','')}|{str(vals.get('body',''))[:120]}"
                if not basis.strip("|"):
                    continue
                import hashlib
                key = "h" + hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16]
            out.append(Review(
                review_key=key[:120],
                rating=_as_float(vals.get("rating")),
                title=_as_text(vals.get("title"))[:300],
                body=_as_text(vals.get("body"))[:5000],
                author=_as_text(vals.get("author"))[:120],
                review_date=_as_text(vals.get("review_date"))[:80],
                verified=vals.get("verified") if isinstance(vals.get("verified"), bool) else None,
                helpful_count=_as_int(vals.get("helpful_count")),
                review_url=self._abs_url(review_url),
                image_urls=images,
                video_urls=videos,
            ))
        return out

    def _media_list(self, block: Dom, mrule: dict | None) -> list[str]:
        """抽取评价内的图片/视频 URL 列表，按规则过滤/替换。

        mrule 例：
          {"selector": "img[data-hook='review-image-tile']", "attr": "src",
           "include": ["media-amazon.com/images/I/"], "exclude": ["avatars-global"],
           "hires": ["._SY88_", "._SL1600_"]}
        """
        if not mrule:
            return []
        sel = mrule.get("selector") or ""
        attr = mrule.get("attr") or "src"
        if not sel:
            return []
        raw = block.attr_list(sel, attr, limit=int(mrule.get("limit", 40)))
        inc = mrule.get("include") or []
        exc = mrule.get("exclude") or []
        hires = mrule.get("hires")           # [pat_from, pat_to] 拿高清图
        out: list[str] = []
        seen: set[str] = set()
        for u in raw:
            u = self._abs_url(u.strip())
            if not u:
                continue
            if inc and not any(s in u for s in inc):
                continue
            if exc and any(s in u for s in exc):
                continue
            if hires and len(hires) == 2:
                u = re.sub(hires[0], hires[1], u)
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    def _abs_url(self, u: str) -> str:
        if not u:
            return ""
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/") and self.base_url:
            return self.base_url.rstrip("/") + u
        return u

    def summary(self, dom: Dom | None) -> ReviewSummary:
        vals = self.fields(dom, "summary")
        stars: dict[int, int] = {}
        for n in range(1, 6):
            v = _as_int(vals.get(f"star{n}"))
            if v is not None:
                stars[n] = v
        return ReviewSummary(avg_rating=_as_float(vals.get("avg_rating")),
                             total_count=_as_int(vals.get("total_count")),
                             stars=stars)

    def anchor_selector(self) -> str:
        return self.schema.get("anchor") or ""


def _as_text(v: Any) -> str:
    return "" if v is None else (v if isinstance(v, str) else str(v))


def _as_float(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return t_money(_as_text(v))


def _as_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    return t_int(_as_text(v))
