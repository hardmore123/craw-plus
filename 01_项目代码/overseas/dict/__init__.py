"""日中 SPEC 术语词典。

词典是有限集合（SPEC 项目名相对固定），一次建好长期复用，比翻译 API 准。
未命中项返回空串，并由采集流程记入 spec_untranslated 表，便于人工补词典。
"""
from __future__ import annotations

import json
import os
import re

_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spec_ja_zh.json")
_WS_RE = re.compile(r"\s+")

_cache: dict[str, str] | None = None


def _normalize(s: str) -> str:
    """归一化：去空白/换行/软换行分隔符，与词典 key 对齐。

    官网项目名常含 <br>（解析后变 ' / '）或全角空格，归一化时一并去掉，
    这样 '裏番組録画/2番組同時録画' 与解析出的 '裏番組録画 / 2番組同時録画' 能匹配。
    """
    s = (s or "").replace("\u3000", "").replace("／", "/")
    # 括号全半角统一（（）↔()），使词典 key 与实际项目名的括号写法差异不影响匹配。
    s = s.replace("（", "(").replace("）", ")")
    # 剥离星号系注记标记（＊1 / *2 等），随系列变化不应影响匹配
    s = _STAR_NOTE_RE.sub("", s)
    s = _WS_RE.sub("", s)
    # 去掉纯分隔用的 / （项目名里的 / 是并列语义，不影响识别）
    return s.replace("/", "").strip()


def _load() -> dict[str, str]:
    global _cache
    if _cache is not None:
        return _cache
    with open(_DICT_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    # 用归一化后的 key 建索引，容忍原文里的换行/空格差异
    _cache = {_normalize(k): v for k, v in raw.items() if not k.startswith("_")}
    return _cache


_PAREN_RE = re.compile(r"[（(].*?[)）]")
_NOTE_RE = re.compile(r"※.*")
# 括注里若含「区分性内容」（单位 mm/kg/cm/W、年份基准、纵横方向等），
# 去括注兜底会把不同项误并成一项（如 スタンドあり(Kg) 误命中 スタンドあり(mm)）。
# 命中这些标志时，禁止对该项使用去括注兜底，必须精确/剥脚注匹配。
_DISCRIMINATIVE_PAREN_RE = re.compile(
    r"(mm|cm|kg|㎏|ｋｇ|[0-9]{4}年|年基準|年度基準|縦|横|幅|奥行|高さ|W\b|ｗ)",
    re.IGNORECASE)
# 注记标记（星号系）：REGZA 用全角＊/半角* 加序号，如 '年間消費電力量＊1'、
# '4K衛星放送 ＊3'。剥离「＊/*/☆ 后可跟 1~2 位数字」的尾部注记标记。
_STAR_NOTE_RE = re.compile(r"[＊*☆★✳]\s*\d{0,2}")
# 尾部脚注编号：日文项目名末尾常带页面注记序号（如 Google TV6 / MHL端子20 /
# 年間消費電力量：kWh/年22）。这些数字随系列变化，需在匹配前剥离。
# 只剥「结尾的 1~2 位半角数字」，且不动 4K/8K/2.1 这类正文数字：
# 规则=数字前必须是非数字且非 . / x / × / - 的字符（即真正的注记）。
_FOOTNOTE_RE = re.compile(r"(?<=[^\d.\-xX×])\d{1,2}$")


def _core(s: str) -> str:
    """去掉括注、※注记后的核心词，用于兜底匹配。

    不同系列对同一项目常有不同括注，如
    '待機電力（※リモコンの電源OFF時）' vs '待機電力※リモコンの電源OFF時'。
    """
    s = _PAREN_RE.sub("", s or "")
    s = _NOTE_RE.sub("", s)
    return _normalize(s)


def _strip_footnote(s: str) -> str:
    """剥离项目名末尾的脚注编号后再归一化。"""
    s = _NOTE_RE.sub("", s or "")
    s = _FOOTNOTE_RE.sub("", s.strip())
    return _normalize(s)


def _dedup_repeat(s: str) -> str:
    """折叠「同一短语紧邻重复两次」为一次（TCL 老系列 name 字段有此脏数据）。

    如 '音声/字幕の切換え 音声/字幕の切換え' → '音声/字幕の切換え'。
    以空格分隔尝试对半判断；也处理无空格的整串对半重复。
    """
    s = (s or "").strip()
    if not s:
        return s
    # 有空格：若左右两半（去空白后）相等则取一半
    parts = s.split()
    if len(parts) >= 2 and len(parts) % 2 == 0:
        half = len(parts) // 2
        if parts[:half] == parts[half:]:
            return " ".join(parts[:half])
    # 无空格整串对半重复
    n = len(s)
    if n % 2 == 0 and s[:n // 2] == s[n // 2:]:
        return s[:n // 2]
    return s


# 长 name 常以「已知项目名 + 一长串取值/说明」形式出现（TCL 老系列），
# 用这些前缀词把它们归到规范项目名。
_PREFIX_KEYS = ("VOD機能", "地上デジタル", "衛星110度CSデジタル（右旋）",
                "衛星ＢＳデジタル（右旋）", "衛星110度CSデジタル", "衛星ＢＳデジタル",
                "本体重量", "外形寸法")


def translate(item_ja: str) -> str:
    """返回中文；未命中返回空串。

    匹配顺序：精确 → 去括注 → 剥脚注编号。词典 key 也做同样处理后比较，
    这样 'Google TV6'/'Google TV5' 都能命中词典里的 'Google TV'。
    """
    if not item_ja:
        return ""
    d = _load()
    key = _normalize(item_ja)
    if key in d:
        return d[key]
    # 判断本项括注是否含「区分性内容」（单位/年份/方向）。若含，则跳过去括注兜底，
    # 避免把 スタンドあり(Kg) 误并到 スタンドあり(mm)、(2012年基準) 误并到 (2026年基準)。
    _parens = "".join(re.findall(r"[（(]([^）)]*)[）)]", item_ja or ""))
    _has_discriminative = bool(_DISCRIMINATIVE_PAREN_RE.search(_parens))
    # 兜底1：去括注后匹配（仅当括注不含区分性内容时启用）
    if not _has_discriminative:
        core = _core(item_ja)
        if core:
            for k, v in d.items():
                if _core(k) == core:
                    return v
    # 兜底2：剥脚注编号后匹配
    fk = _strip_footnote(item_ja)
    if fk:
        for k, v in d.items():
            if _strip_footnote(k) == fk:
                return v
    # 兜底3：折叠重复短语后再匹配一次
    dd = _dedup_repeat(item_ja)
    if dd != item_ja:
        r = translate(dd)
        if r:
            return r
    # 兜底4：长 name 取前缀规范项目名（如 'VOD機能 Youtube/...' → 'VOD機能'）
    raw = (item_ja or "").strip()
    for pk in _PREFIX_KEYS:
        if raw.startswith(pk):
            r = d.get(_normalize(pk))
            if r:
                return r
    # 兜底5：在线翻译接口（默认关闭；开启后翻译并缓存，人工审核后可合入主词典）。
    # 词典/规则全部未命中才走这里，保证离线优先、结果稳定可复现。
    online = _translate_online(item_ja)
    if online:
        return online
    return ""


def _translate_online(item_ja: str) -> str:
    """调用在线翻译接口（延迟导入，避免离线场景引入依赖/循环导入）。"""
    try:
        from .. import translator
        return translator.translate_online(item_ja)
    except Exception:  # noqa: BLE001 — 翻译回退绝不影响主流程
        return ""


def size() -> int:
    return len(_load())


# ==================== 西班牙语→中文（墨西哥线）====================
# 与日语词典完全隔离：独立文件、独立缓存、独立 translate_es()，
# 不改动上面的 translate()，因此不影响日本线/加拿大线的既有行为。

_ES_DICT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "spec_es_zh.json")
_es_cache: dict[str, str] | None = None


def _es_normalize(s: str) -> str:
    """西语项目名归一化：小写、去两端空白、折叠内部空白、去尾部冒号。

    西语词典 key 大小写不敏感、容忍多空格与尾冒号（如 'Resolución :'）。
    与日语归一化分开实现，避免误用日语专用的去 / 与全角处理。
    """
    s = (s or "").strip().rstrip(":：").strip()
    s = _WS_RE.sub(" ", s)
    return s.lower()


def _es_load() -> dict[str, str]:
    global _es_cache
    if _es_cache is not None:
        return _es_cache
    try:
        with open(_ES_DICT_PATH, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        raw = {}
    _es_cache = {_es_normalize(k): v for k, v in raw.items()
                 if not str(k).startswith("_")}
    return _es_cache


def translate_es(item_es: str) -> str:
    """西语项目名→中文；未命中返回空串（缺词由采集流程记入 spec_untranslated）。

    匹配：精确 → 去尾部括注后再试一次。命不中不报错、不阻塞抓取。
    """
    if not item_es:
        return ""
    d = _es_load()
    key = _es_normalize(item_es)
    if key in d:
        return d[key]
    core = _es_normalize(_PAREN_RE.sub("", item_es))
    if core and core in d:
        return d[core]
    return ""


def es_size() -> int:
    return len(_es_load())
