"""FCC 认证记录爬虫。

数据源：fccid.io 聚合站（apps.fcc.gov 官方站被 Akamai 403，走聚合站更稳）。

三种页面（都已验证）：
  1. 搜索页  https://fccid.io/search?q=<query>
     - "Company Results" 表格：公司名 + Grantee Code + 地点 + 注册日
     - panel 列表：FCC ID + 描述 + Company + Latest Filing ...
  2. 授权码页 https://fccid.io/<GC>  （全量抓取的关键！）
     - grantee-detail-table：公司信息
     - grantee-applications-table：该授权码下**全部** FCC ID（100/页，带分页）
     - 分页：https://fccid.io/<GC>/page/2、/page/3 ...
  3. 详情页  https://fccid.io/<FCCID>  → 文件清单

⚠ 关键教训：**公司名搜索会截断结果**。搜 "TCL Communication" 只返回 ~33 条，
   但授权码 2ACCJ 页面有 6 页 ≈ 600 条。必须走"搜索发现授权码 → 遍历授权码所有分页"。

抓取策略（全量）：
  1. 用多个品牌关键词搜出所有关联公司 + 授权码
  2. 逐个授权码遍历所有分页，拿全量 FCC ID
  3. 按 auth_date 过滤只留近期

限速：fccid.io 是聚合站，礼貌 ≥2s 间隔（项目 RateLimiter 默认更慢，够用）。
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Iterator

from ..fetchers import HttpFetcher, FetchResult
from ..infra import RateLimiter

FCC_SEARCH_URL = "https://fccid.io/search?q={q}"
FCC_DETAIL_URL = "https://fccid.io/{fccid}"
FCC_GRANTEE_URL = "https://fccid.io/{gc}"
FCC_GRANTEE_PAGE_URL = "https://fccid.io/{gc}/page/{page}"

# 一个结果 panel：从 <h3 ...><a href="/FCCID">FCCID</a></h3> 到下一个
# <div class="panel panel-default"> 之间。
_PANEL_RE = re.compile(
    r'<h3[^>]*><a href="/([A-Z0-9][A-Z0-9\-]{2,40})"[^>]*>([A-Z0-9\-]+)</a></h3>'
    r'(.*?)(?=<h3\s+style="margin-top:0;"|<div class="panel panel-default"\s*$)',
    re.S)

# 搜索页 "Company Results" 表格行：
#   <td data-label="Company"><a href="/PY7">Sony Corporation</a></td>
#   <td data-label="Grantee Code"><a class="grantee-code-chip" href="/PY7">PY7</a></td>
#   <td data-label="Location">Tokyo, N/A, Japan</td>
#   <td data-label="Registered">2001-10-24</td>
_COMPANY_ROW_RE = re.compile(
    r'<td data-label="Company"><a href="/([A-Z0-9]{3,5})">([^<]+)</a></td>\s*'
    r'<td data-label="Grantee Code">.*?</td>\s*'
    r'<td data-label="Location">([^<]*)</td>\s*'
    r'<td data-label="Registered">([^<]*)</td>', re.S)

# 授权码页 "grantee-applications-table" 行：
#   <td data-label="FCC ID / Date"><b><a href="/2ACCJB247">2ACCJB247</a></b><br>2026-08-17</td>
#   <td data-label="Product / Type">Projector<br>Original Equipment</td>
_GRANTEE_ROW_RE = re.compile(
    r'<td data-label="FCC ID / Date"><b><a href="/([A-Z0-9][A-Z0-9\-]{2,40})">[^<]+</a></b>'
    r'(?:<br>([^<]*))?</td>\s*'
    r'<td data-label="Product / Type">(?:([^<]*))?(?:<br>([^<]*))?</td>', re.S)

# 授权码页标题含 "Page X of Y"
_GRANTEE_PAGE_RE = re.compile(r'Page\s+(\d+)\s+of\s+(\d+)', re.I)

# 授权码页公司信息
_GRANTEE_INFO_RE = re.compile(
    r'<th>Company</th><td>([^<]*)</td>.*?<th>Grantee Code</th><td>([^<]*)</td>', re.S)


@dataclass
class FccRecord:
    fcc_id: str = ""
    description: str = ""
    company: str = ""
    grantee_code: str = ""        # 前3位（A3L）
    grantee_registered: str = ""  # grantee 注册日
    product_code: str = ""
    latest_filing: str = ""       # 最新申报日
    matched_docs: int = 0
    frequencies: str = ""
    docs: list[dict] = field(default_factory=list)   # 详情页文件列表


def _text_after(html: str, label: str) -> str:
    """从 panel HTML 抓 <th>label</th><td>VALUE</td> 的 VALUE。"""
    m = re.search(
        r"<th[^>]*>\s*" + re.escape(label) +
        r"\s*</th>\s*<td[^>]*>(.*?)</td>", html, re.S | re.I)
    if not m:
        return ""
    # 去标签 + 压空白
    val = re.sub(r"<[^>]+>", "", m.group(1))
    return re.sub(r"\s+", " ", val).strip()


def parse_search_results(html: str) -> list[FccRecord]:
    """解析 fccid.io 搜索结果页，返回 FCC 记录列表（不含文件清单）。"""
    out: list[FccRecord] = []
    for m in _PANEL_RE.finditer(html):
        fcc_id, _shown, body = m.group(1), m.group(2), m.group(3)
        if not fcc_id:
            continue
        rec = FccRecord(fcc_id=fcc_id)
        # 描述：第一个 <p>...</p>
        p = re.search(r"<p>(.*?)</p>", body, re.S)
        if p:
            rec.description = _html.unescape(
                re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", p.group(1))).strip())
        rec.company = _html.unescape(_text_after(body, "Company"))
        rec.product_code = _html.unescape(_text_after(body, "Product Code"))
        rec.latest_filing = _html.unescape(_text_after(body, "Latest Filing"))
        rec.frequencies = _html.unescape(_text_after(body, "Frequencies"))
        md = _text_after(body, "Matched Documents")
        if md.isdigit():
            rec.matched_docs = int(md)
        # Registered Grantee 行含 grantee code（括号内）+ 注册日
        rg = _text_after(body, "Registered Grantee")
        gc = re.search(r"\(([A-Z0-9]{2,5})\)", rg)
        if gc:
            rec.grantee_code = gc.group(1)
        rgr = re.search(r"registered\s+(\d{4}-\d{2}-\d{2})", rg)
        if rgr:
            rec.grantee_registered = rgr.group(1)
        out.append(rec)
    return out


def parse_company_results(html: str) -> list[dict]:
    """解析搜索页的 "Company Results" 表格，返回公司+授权码列表。

    返回 [{grantee_code, company, location, registered}]。
    这是全量抓取的入口：用品牌关键词发现所有关联公司的授权码。
    """
    out: list[dict] = []
    seen = set()
    for gc, company, loc, date in _COMPANY_ROW_RE.findall(html):
        gc = gc.strip()
        if gc in seen:
            continue
        seen.add(gc)
        out.append({
            "grantee_code": gc,
            "company": _html.unescape(company).strip(),
            "location": _html.unescape(loc).strip(),
            "registered": date.strip(),
        })
    return out


def parse_grantee_page(html: str) -> tuple[list[dict], int, int]:
    """解析授权码页的 grantee-applications-table。

    返回 (records, current_page, total_pages)。
    records: [{fcc_id, app_date, product, app_type}]
    """
    recs: list[dict] = []
    seen = set()
    for fcc_id, app_date, product, app_type in _GRANTEE_ROW_RE.findall(html):
        fcc_id = fcc_id.strip()
        if not fcc_id or fcc_id in seen:
            continue
        seen.add(fcc_id)
        recs.append({
            "fcc_id": fcc_id,
            "app_date": _html.unescape(app_date or "").strip(),
            "product": _html.unescape(product or "").strip(),
            "app_type": _html.unescape(app_type or "").strip(),
        })
    cur, total = 1, 1
    m = _GRANTEE_PAGE_RE.search(html)
    if m:
        cur, total = int(m.group(1)), int(m.group(2))
    return recs, cur, total


def parse_grantee_info(html: str) -> dict:
    """解析授权码页的公司信息（Company/Grantee Code）。"""
    m = _GRANTEE_INFO_RE.search(html)
    if not m:
        return {}
    return {"company": _html.unescape(m.group(1)).strip(),
            "grantee_code": m.group(2).strip()}


def parse_detail_docs(html: str) -> list[dict]:
    """解析 FCC ID 详情页，抓文件清单（doc_type/doc_name/url/doc_date）。

    详情页"Documents"表行结构（已验证）：
      <tr><td data-label="Document"><a href="/FCCID/Type/Name-ID">Name</a></td>
          <td data-label="Type">Type</td>
          <td data-label="Available">2007-05-26</td>
          <td data-label="File">PDF 200.2 KB</td></tr>

    保密文件（Internal/External Photos, Label, Users Manual）能被抓到 = 保密期已结束。
    """
    docs: list[dict] = []
    row_re = re.compile(
        r'<td[^>]*data-label="Document"[^>]*>\s*'
        r'<a href="/([A-Z0-9\-]+/[^"]+)"[^>]*>([^<]+)</a>\s*</td>\s*'
        r'<td[^>]*data-label="Type"[^>]*>([^<]*)</td>\s*'
        r'<td[^>]*data-label="Available"[^>]*>([^<]*)</td>',
        re.I)
    for m in row_re.finditer(html):
        url_path, doc_name, doc_type, doc_date = m.groups()
        docs.append({
            "doc_name": doc_name.strip(),
            "doc_type": doc_type.strip(),
            "url": "https://fccid.io/" + url_path,
            "doc_date": doc_date.strip(),
        })
    return docs


class FccCrawler:
    """按 applicant 名（竞品公司）抓 FCC 认证记录。"""

    def __init__(self, fetcher: HttpFetcher | None = None,
                 rate: RateLimiter | None = None):
        self.f = fetcher or HttpFetcher()
        self.rate = rate or self.f.rate

    def close(self) -> None:
        self.f.close()

    def __enter__(self) -> "FccCrawler":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def search(self, applicant: str) -> list[FccRecord]:
        """按公司名搜索 fccid.io，返回 FCC 记录列表（会截断，全量请用 list_grantee）。"""
        url = FCC_SEARCH_URL.format(q=_quote(applicant))
        res = self.f.get(url)
        if not res.ok:
            raise RuntimeError(f"FCC search failed: {res.status} {res.block_reason} {res.error}")
        return parse_search_results(res.html)

    def search_companies(self, keyword: str) -> list[dict]:
        """搜索品牌关键词，返回关联公司+授权码列表（Company Results 表格）。

        这是全量抓取的入口。例：search_companies("sony") → 8 家公司授权码。
        """
        url = FCC_SEARCH_URL.format(q=_quote(keyword))
        res = self.f.get(url)
        if not res.ok:
            raise RuntimeError(f"FCC company search failed: {res.status} {res.block_reason}")
        return parse_company_results(res.html)

    def discover_grantees(self, keywords: list[str]) -> dict[str, dict]:
        """用多个关键词发现所有关联授权码，返回 {grantee_code: company_info}。

        两条发现路径并用（缺一不可）：
          1. Company Results 表格 → 直接给授权码（但只覆盖名称前缀匹配的公司）
          2. 搜索结果 panel 的 "Registered Grantee" → 覆盖子公司
             （例:搜 "Hisense" 的面板里有 Hisense Ronshen 的 grantee 2A4A3）

        关键词要给足特异性（公司搜索是前缀匹配，"TCL" 太短返回 0 家）。
        """
        found: dict[str, dict] = {}
        for kw in keywords:
            # 路径 1：Company Results 表格
            try:
                for c in self.search_companies(kw):
                    gc = c["grantee_code"]
                    if gc not in found:
                        found[gc] = c
            except Exception:
                pass
            # 路径 2：搜索面板的 grantee code（能发现子公司）
            try:
                for rec in self.search(kw):
                    gc = (rec.grantee_code or "").strip()
                    if gc and gc not in found:
                        found[gc] = {
                            "grantee_code": gc,
                            "company": rec.company or "",
                            "location": "",
                            "registered": rec.grantee_registered or "",
                            "via": f"panel:{kw}",
                        }
            except Exception:
                pass
        return found

    def list_grantee(self, grantee_code: str, max_pages: int = 0,
                     since: str = "",
                     known_ids: set[str] | None = None) -> tuple[list[dict], dict]:
        """遍历某授权码的所有分页，返回全量 FCC ID 记录。

        这是真正的全量抓取（公司名搜索会被截断，授权码页有分页才是全的）。
        max_pages: 限制页数(0=全部)。since: 只留 app_date >= since 的记录。
        known_ids: 已入库的 FCC ID 集合，用于增量早停——
            授权码页按日期倒序，一旦某页全是已知 ID，后续页必然更旧，
            可直接停翻（省去重复抓已入库的旧记录）。
        返回 (records, meta)，meta 含 pages_fetched/total_pages/stopped_early/new_count。
        """
        out: list[dict] = []
        page = 1
        total_pages = 1
        company = ""
        pages_fetched = 0
        stopped_early = False
        new_count = 0
        while page <= total_pages:
            if page == 1:
                url = FCC_GRANTEE_URL.format(gc=grantee_code)
            else:
                url = FCC_GRANTEE_PAGE_URL.format(gc=grantee_code, page=page)
            try:
                res = self.f.get(url)
            except Exception:
                break
            if not res.ok:
                break
            pages_fetched += 1
            if page == 1:
                info = parse_grantee_info(res.html)
                company = info.get("company", "")
            recs, cur, total = parse_grantee_page(res.html)
            total_pages = total
            page_new = 0
            page_known = 0
            for r in recs:
                # 时间过滤
                if since and r["app_date"] and r["app_date"] < since:
                    continue
                r["grantee_code"] = grantee_code
                r["company"] = company
                out.append(r)
                if known_ids is not None:
                    if r["fcc_id"] in known_ids:
                        page_known += 1
                    else:
                        page_new += 1
                        new_count += 1
            # 增量早停：本页全是已知且非首页 → 后续页必然更旧，停
            if known_ids is not None and page > 1 and page_new == 0 and recs:
                stopped_early = True
                break
            if not recs:
                break
            if max_pages and page >= max_pages:
                break
            page += 1
        meta = {"pages_fetched": pages_fetched, "total_pages": total_pages,
                "stopped_early": stopped_early, "new_count": new_count}
        return out, meta

    def fetch_detail(self, fcc_id: str) -> list[dict]:
        """抓单个 FCC ID 详情页的文件清单。"""
        url = FCC_DETAIL_URL.format(fccid=fcc_id)
        res = self.f.get(url)
        if not res.ok:
            return []
        return parse_detail_docs(res.html)


def _quote(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(s)
