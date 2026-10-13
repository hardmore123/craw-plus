"""Philips 欧洲站（de/fr/it）SPEC 共用工具。

欧洲站结构与加拿大站（ca_spec_common）的差异：
- 产品 URL 形如 /c-p/<MODEL>/<slug>/support，型号是 /c-p/ 后第一段，例如
  43PUS7200_12；加拿大站是 /c-p/SA-TV_<slug>/，型号前缀 SA-TV 在第一段。
- 型号形如 <尺寸><系列码>_<后缀>，如 43PUS7200_12；系列提取需同时去掉开头
  尺寸（2-3 位数字）与结尾 _NN 后缀，取中间系列码 PUS7200。
- 规格页内嵌的 Next.js __NEXT_DATA__ 里 specification/csChapter 结构与加拿大站
  一致，可直接复用 _embedded_specification / _specification_triples。

入口页分页（Next.js 前端、aria-label="Show page N of results"）与加拿大站完全
相同，_PAGINATE_JS 在此复用（逐页点击累积全部 /c-p/ 链接）。
"""
from __future__ import annotations

import json
import re


# 欧洲站产品 URL：/c-p/<MODEL>/<slug>/support，型号在 /c-p/ 后第一段。
# 型号本身可含字母/数字/下划线，如 43PUS7200_12、65PUS8100_12。
PROD_RE = re.compile(r"/c-p/([A-Za-z0-9_]+)/", re.I)

# 型号形如 <尺寸2-3位><系列码>_<后缀数字>，如 43PUS7200_12、50PUS8959_12。
# 系列码 = 去掉开头尺寸 + 去掉结尾 _NN 后缀后的中间段，如 PUS7200、PUS8959。
_SERIES_RE = re.compile(r"^\d{2,3}([A-Z0-9]+?)_\d+$", re.I)


def series_of(model: str) -> str:
    """从欧洲型号提取系列码：去开头尺寸 + 去结尾 _NN 后缀，取中间系列码。

    例：43PUS7200_12 → PUS7200；65PUS8100_12 → PUS8100。
    匹配不到（如 SA-TV 或无后缀）时退回去掉开头尺寸后的剩余大写。
    """
    raw = (model or "").strip().upper()
    if not raw:
        return raw
    m = _SERIES_RE.match(raw)
    if m:
        return m.group(1).upper()
    # 兜底：仅去开头尺寸（与 ca_spec_common._series_of 行为一致）
    return re.sub(r"^\d{2,3}", "", raw).upper() or raw


def model_from_url(url: str) -> str:
    """从 /c-p/<MODEL>/<slug>/support 形 URL 提取型号（第一段，大写）。"""
    m = PROD_RE.search(url or "")
    return m.group(1).upper() if m else (url or "")


# Philips 欧洲站与加拿大站同样把规格嵌在 __NEXT_DATA__ 的 specification 字段，
# 结构为 {csChapter: [{csChapterName, csItem: [{csItemName, csValue: [...]}]}]}。
# 下面两个函数与 philips_ca 的 _balanced_json_text / _embedded_specification /
# _specification_triples 逻辑一致，抽出 (category, item, value) 三元组。


def balanced_json_text(text: str, start: int) -> str:
    stack: list[str] = []
    closing = {"}": "{", "]": "["}
    for index in range(start, len(text)):
        char = text[index]
        if char in "[{":
            stack.append(char)
        elif char in closing:
            if not stack or stack[-1] != closing[char]:
                return ""
            stack.pop()
            if not stack:
                return text[start:index + 1]
    return ""


def embedded_specification(html: str) -> dict:
    markers = [("\"specification\":", False), ("\\\"specification\\\":", True)]
    decoder = json.JSONDecoder()
    for marker, escaped in markers:
        offset = 0
        while True:
            position = html.find(marker, offset)
            if position < 0:
                break
            start = html.find("{", position + len(marker))
            if start < 0:
                break
            try:
                if escaped:
                    raw = balanced_json_text(html, start)
                    value = json.loads(json.loads('"' + raw + '"')) if raw else None
                else:
                    value, _ = decoder.raw_decode(html[start:])
                if isinstance(value, dict) and value.get("csChapter"):
                    return value
            except (ValueError, json.JSONDecodeError):
                pass
            offset = position + 1
    return {}


def specification_triples(html: str) -> list[list[str]]:
    specification = embedded_specification(html)
    triples: list[list[str]] = []
    for chapter in specification.get("csChapter") or []:
        if not isinstance(chapter, dict):
            continue
        category = str(chapter.get("csChapterName") or
                       chapter.get("csChapterCode") or "").strip()
        for item_data in chapter.get("csItem") or []:
            if not isinstance(item_data, dict):
                continue
            item = str(item_data.get("csItemName") or "").strip()
            if not item:
                continue
            values = []
            for value_data in item_data.get("csValue") or []:
                if isinstance(value_data, dict):
                    value = str(value_data.get("csValueName") or "").strip()
                    if value and value not in values:
                        values.append(value)
            triples.append([category, item, " / ".join(values)])
    return triples


# 欧洲站入口页分页脚本：与 philips_ca._PAGINATE_JS 一致（Next.js 前端，aria-label
# "Show page N of results" 逐页点击累积 /c-p/ 链接）。
PAGINATE_JS = r"""async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collected = new Map();
  const harvest = () => {
    document.querySelectorAll("a[href*='/c-p/']").forEach(a => {
      const href = a.href || a.getAttribute('href') || '';
      if (!href) return;
      const card = a.closest('[class*="product"], [class*="card"], article, li') || a.parentElement;
      const text = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
      if (!collected.has(href)) {
        collected.set(href, {href, text: text(a), card: text(card),
                             aria: a.getAttribute('aria-label') || '',
                             title: a.getAttribute('title') || ''});
      }
    });
  };
  const pageButton = (n) => Array.from(
    document.querySelectorAll('button,[role="button"]')).find(b =>
      (b.getAttribute('aria-label') || '') === `Show page ${n} of results`) || null;
  const visitPage = async (n) => {
    const btn = pageButton(n);
    if (!btn) return false;
    const before = collected.size;
    try {
      btn.scrollIntoView({block: 'center'});
      btn.click();
    } catch (e) { return true; }
    for (let w = 0; w < 16; w++) {
      await sleep(500);
      harvest();
      if (collected.size > before) {
        await sleep(700); harvest();
        await sleep(500); harvest();
        break;
      }
    }
    return true;
  };
  let maxPage = 1;
  Array.from(document.querySelectorAll('button,[role="button"]')).forEach(b => {
    const m = /^Show page (\d+) of results$/.exec(b.getAttribute('aria-label') || '');
    if (m) maxPage = Math.max(maxPage, parseInt(m[1], 10));
  });
  harvest();
  for (let round = 0; round < 2; round++) {
    for (let n = 2; n <= Math.min(maxPage, 40); n++) {
      await visitPage(n);
    }
    await visitPage(1);
    harvest();
  }
  return Array.from(collected.values());
}"""
