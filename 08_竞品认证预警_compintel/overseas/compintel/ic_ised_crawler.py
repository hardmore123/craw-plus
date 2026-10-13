"""IC/ISED 加拿大无线电设备认证爬虫。

数据源：ISED SMS 数据库 (sms-sgs.ic.gc.ca)，Spring WebFlow 表单。
  Company Search: https://sms-sgs.ic.gc.ca/equipmentSearch/searchCompanyNames?lang=en_CA
  REL Search:     https://sms-sgs.ic.gc.ca/equipmentSearch/searchRadioEquipments?lang=en_CA

流程（3 步 + 轮询）：
  1. GET 表单 → 拿 execution token + cookie (JSESSIONID + SPWEB_SESSION_TOKEN)
  2. POST _eventId_search + companyName=... → 返回 Processing 页
  3. POST _eventId_refresh 轮询 3-4 次 → 结果 HTML
  4. 解析结果表 → 按公司分组,每组 7 列: HVIN, PMN, HMN, FVIN, Cert#, Approval Date

注意：
  - Spring WebFlow execution token 每次请求变化(e1s1 → e1s2 → ...)
  - 需维护 cookie jar
  - reCAPTCHA 低频可过,高频可能触发 → 限速
  - ISED Company Number 与 FCC Grantee Code 不共享
"""
from __future__ import annotations

import csv
import io
import re
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any

from ..fetchers import HttpFetcher

ISED_BASE = "https://sms-sgs.ic.gc.ca/equipmentSearch"
COMPANY_SEARCH_URL = f"{ISED_BASE}/searchCompanyNames?lang=en_CA"
REL_SEARCH_URL = f"{ISED_BASE}/searchRadioEquipments?lang=en_CA"

# 竞品品牌 → ISED 已知公司号(跳过 search_companies,直接查 REL)
# 这些公司号是通过手动 search_companies 获取并缓存的(避免每次都触发 500)
# 2026-10-25 全 6 品牌验证通过
ISED_COMPANY_NUMBERS = {
    "Samsung": ["649A", "649B"],
    "LG": ["2703A", "2703C"],
    "Hisense": ["11337A", "10680B"],
    "TCL": ["11645A", "11940A"],
    "Sony": ["4170B", "409E", "409F"],
    "Panasonic": ["216B", "216J", "216N"],
}

# 竞品品牌 → ISED 公司名搜索关键词(仅用于首次发现公司号)
ISED_BRAND_MAP = {
    "Samsung": "Samsung Electronics",
    "LG": "LG Electronics",
    "Hisense": "Hisense",
    "TCL": "TCL",
    "Sony": "Sony",
    "Panasonic": "Panasonic",
}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
       "AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/126.0.0.0 Safari/537.36")


def _extract_execution(html: str) -> str:
    """从 HTML 中提取 Spring WebFlow execution token。

    ISED 表单用 name="execution" (无下划线前缀),值如 e1s1。
    """
    m = re.search(r'name="execution"\s+value="([^"]+)"', html)
    return m.group(1) if m else ""


def _extract_field(html: str, name: str) -> str:
    """提取任意 hidden input 的 value。"""
    m = re.search(
        rf'name="{re.escape(name)}"\s+value="([^"]*)"', html)
    return m.group(1) if m else ""


class IcedCrawler:
    """IC/ISED 加拿大无线电认证爬虫。

    用法：
        crawler = IcedCrawler(proxy="http://127.0.0.1:7877")
        # 1. 先建公司名→Company Number 映射
        companies = crawler.search_companies("Samsung Electronics")
        # 2. 再按 Company Number 查 REL
        records = crawler.search_rel(company_number=companies[0]["number"])
    """

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        self.jar = CookieJar()
        self.opener = self._build_opener()

    def _build_opener(self):
        """重建 opener(含 cookie jar + 代理),用于每个搜索流程隔离 session。"""
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        if self.proxy:
            opener.add_handler(
                urllib.request.ProxyHandler(
                    {"http": self.proxy, "https": self.proxy}))
        return opener

    def _reset_session(self):
        """清空 cookie + 重建 opener,确保每个 Spring WebFlow 流程独立。"""
        self.jar = CookieJar()
        self.opener = self._build_opener()

    def _get(self, url: str) -> str:
        """GET 请求,返回 HTML 文本。"""
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-CA,en;q=0.9",
        })
        with self.opener.open(req, timeout=30) as resp:
            return resp.read().decode("utf-8", "replace")

    def _post(self, url: str, data: dict[str, str],
              retries: int = 3) -> str:
        """POST 表单,返回 HTML 文本。自动重试(500/SSL EOF)。"""
        body = urllib.parse.urlencode(data).encode("utf-8")
        last_err = ""
        for attempt in range(retries):
            req = urllib.request.Request(url, data=body, headers={
                "User-Agent": _UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-CA,en;q=0.9",
                "Content-Type": "application/x-www-form-urlencoded",
            })
            try:
                with self.opener.open(req, timeout=45) as resp:
                    return resp.read().decode("utf-8", "replace")
            except Exception as e:
                last_err = str(e)
                if attempt < retries - 1:
                    time.sleep(3 * (attempt + 1))   # 指数退避
        raise RuntimeError(f"POST 失败({retries}次重试): {last_err}")

    def search_companies(self, company_name: str) -> list[dict]:
        """搜索公司名 → 返回 [{number, name}] 列表。

        流程: GET 表单 → POST _eventId_search → 轮询 _eventId_refresh
        ISED Spring WebFlow 表单格式:
          execution=e1s1, companyName=..., _eventId_search=Search
        """
        self._reset_session()
        # 1. GET 表单页,拿 execution token
        html = self._get(COMPANY_SEARCH_URL)
        execution = _extract_execution(html)
        if not execution:
            return []

        # 2. POST search (Spring WebFlow: _eventId_<event> 格式)
        data = {
            "execution": execution,
            "companyName": company_name,
            "_eventId_search": "Search",
        }
        html = self._post(COMPANY_SEARCH_URL, data)

        # 3. 轮询 refresh (结果可能异步加载,最多 5 次,每次 3 秒)
        #    实测公司搜索是同步的(POST 即返回结果),但保留轮询兜底
        for _ in range(5):
            if "equipmentSearchResultTable" in html or "No results" in html:
                break
            execution = _extract_execution(html)
            if not execution:
                break
            html = self._post(COMPANY_SEARCH_URL, {
                "execution": execution,
                "_eventId_refresh": "Refresh",
            })
            time.sleep(3)

        # 4. 解析结果
        return self._parse_company_results(html)

    def _parse_company_results(self, html: str) -> list[dict]:
        """解析公司搜索结果表。

        表格 id="equipmentSearchResultTable",2 列: Company Name / Company Number。
        公司名含地址(多行),取第一行作为公司名。
        """
        results: list[dict] = []
        # 找结果表
        table_match = re.search(
            r'<table[^>]*equipmentSearchResultTable[^>]*>(.*?)</table>',
            html, re.S | re.I)
        if not table_match:
            return []
        table_html = table_match.group(1)
        # 找所有数据行(跳过表头 thead)
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_html, re.S | re.I)
        rows_html = tbody_match.group(1) if tbody_match else table_html
        row_re = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S | re.I)
        for row in row_re.finditer(rows_html):
            cells = re.findall(r'<td[^>]*>(.*?)</td>', row.group(1), re.S)
            if len(cells) < 2:
                continue
            name_raw = re.sub(r'<[^>]+>', '', cells[0]).strip()
            number = re.sub(r'<[^>]+>', '', cells[1]).strip()
            # 公司名含地址,取第一行(到第一个换行/多空格)
            name = re.split(r'\s{2,}|\n|\r', name_raw)[0].strip()
            if name and number:
                results.append({"number": number, "name": name})
        return results

    def search_rel(self, company_number: str = "",
                   company_name: str = "",
                   since_date: str = "",
                   max_pages: int = 10) -> list[dict]:
        """搜索 REL (Radio Equipment List) → 返回认证记录列表。

        company_number: ISED 公司号(如 "25314")
        company_name: 公司名(模糊匹配)
        since_date: 只取 Approval Date >= since 的记录(yyyy-mm-dd)
        max_pages: 最多翻几页(每页 20 条)

        注意: 每次搜索前清空 cookie jar,避免上一个流程的 execution token 干扰。
        """
        self._reset_session()
        # 1. GET 表单页
        html = self._get(REL_SEARCH_URL)
        execution = _extract_execution(html)
        if not execution:
            return []

        # 2. POST search (Spring WebFlow 格式)
        data: dict[str, str] = {
            "execution": execution,
            "_eventId_search": "Search",
        }
        if company_number:
            data["companyNumber"] = company_number
        if company_name:
            data["companyName"] = company_name
        # 注意: licenceDateFrom 参数会导致 ISED API 返回 500,
        # 改为抓全量后本地按 auth_date 过滤

        html = self._post(REL_SEARCH_URL, data)

        # 3. 轮询 refresh
        for _ in range(5):
            if "equipmentSearchResultTable" in html or "No results" in html:
                break
            execution = _extract_execution(html)
            if not execution:
                break
            html = self._post(REL_SEARCH_URL, {
                "execution": execution,
                "_eventId_refresh": "Refresh",
            })
            time.sleep(3)

        # 4. 解析结果
        records = self._parse_rel_results(html)

        # 5. 翻页
        for page in range(1, max_pages):
            execution = _extract_execution(html)
            if not execution:
                break
            html = self._post(REL_SEARCH_URL, {
                "execution": execution,
                "_eventId_paginate": "Paginate",
                "offset": str(page * 20),
                "max": "20",
            })
            page_recs = self._parse_rel_results(html)
            if not page_recs:
                break
            records.extend(page_recs)
            time.sleep(2)

        return records

    def _parse_rel_results(self, html: str) -> list[dict]:
        """解析 REL 结果表。

        表格结构(实测):
          <tbody>
            <tr><th colspan=7> 649A - SAMSUNG ELECTRONICS CO. LTD. </th></tr>  ← 公司分组标题
            <tr>
              <th>HVIN</th><th>PMN</th><th>HMN</th><th>FVIN</th>
              <th>Cert#</th><th>Approval Date</th><th>Details</th>  ← 表头(th)
            </tr>
            <tr><td>SP-R936</td><td></td>...<td>649 6652 A</td><td>1995-05-09</td><td>...</td></tr>
            ...
          </tbody>
        """
        records: list[dict] = []
        # 找结果表 tbody
        table_match = re.search(
            r'<table[^>]*equipmentSearchResultTable[^>]*>(.*?)</table>',
            html, re.S | re.I)
        if not table_match:
            return []
        tbody_match = re.search(
            r'<tbody>(.*?)</tbody>', table_match.group(1), re.S | re.I)
        if not tbody_match:
            return []
        tbody = tbody_match.group(1)

        # 公司分组标题正则: <th colspan=...> Number - Name </th>
        company_re = re.compile(
            r'<th[^>]*colspan[^>]*>\s*<div>\s*(\d+\w*)\s*-\s*(.+?)\s*</div>',
            re.I)

        current_company_num = ""
        current_company_name = ""

        for line in tbody.split("<tr"):
            # 检测公司分组标题
            cm = company_re.search(line)
            if cm:
                current_company_num = cm.group(1).strip()
                current_company_name = cm.group(2).strip()
                continue

            # 检测数据行: 找所有 <td> 或 <th>
            cells = re.findall(
                r'<t[dh][^>]*>(.*?)</t[dh]>', line, re.S | re.I)
            if len(cells) < 5:
                continue
            # 清理 HTML 标签
            clean = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]

            # 跳过表头行(含 HVIN 文字)
            if "hvin" in clean[0].lower() or "hardware version" in clean[0].lower():
                continue

            # 数据列: HVIN(0), PMN(1), HMN(2), FVIN(3), Cert#(4), Date(5)
            hvin = clean[0] if len(clean) > 0 else ""
            pmn = clean[1] if len(clean) > 1 else ""
            hmn = clean[2] if len(clean) > 2 else ""
            fvin = clean[3] if len(clean) > 3 else ""
            cert_num = clean[4] if len(clean) > 4 else ""
            approval_date = clean[5] if len(clean) > 5 else ""

            if not cert_num or not approval_date:
                continue

            brand = _match_brand_ised(current_company_name)
            records.append({
                "source_id": cert_num.replace(" ", ""),
                "applicant": current_company_name,
                "applicant_code": current_company_num,
                "brand": brand,
                "model": hvin or pmn,
                "description": f"Radio Equipment ({hmn})" if hmn else "Radio Equipment",
                "auth_date": approval_date[:10],
                "product_group": "Radio Equipment",
                "extra_json": {
                    "hvin": hvin, "pmn": pmn, "hmn": hmn,
                    "fvin": fvin,
                },
            })
        return records

    def fetch_all_brands(self, brands: list[str] | None = None,
                         since: str = "",
                         max_companies_per_brand: int = 2,
                         max_pages_per_company: int = 10,
                         use_cached_numbers: bool = True) -> list[dict]:
        """批量拉取多品牌 REL 记录。

        use_cached_numbers: True=用 ISED_COMPANY_NUMBERS 缓存的公司号直接查 REL
            (跳过 search_companies,避免 ISED 对连续请求返回 500)。
            False=先搜公司再查 REL(慢,可能触发 500)。
        max_companies_per_brand: 每品牌最多查几个公司。
            ISED 对连续请求返回 500,建议每品牌只查 1 个(最主要的)。
        """
        brands = brands or list(ISED_COMPANY_NUMBERS.keys())
        all_records: list[dict] = []
        for brand_idx, brand in enumerate(brands):
            if brand_idx > 0:
                time.sleep(15)   # 品牌间也需长延迟,避免 ISED 500
            if use_cached_numbers:
                company_nums = ISED_COMPANY_NUMBERS.get(brand, [])
                if not company_nums:
                    print(f"  [ISED] {brand}: 无缓存公司号,跳过")
                    continue
                # 直接用缓存公司号查 REL(每号新 crawler + 延迟)
                for num in company_nums[:max_companies_per_brand]:
                    try:
                        time.sleep(15)   # ISED 对快速连续请求返回 500,需等 15s+
                        sub = IcedCrawler(proxy=self.proxy)
                        recs = sub.search_rel(
                            company_number=num,
                            since_date=since,
                            max_pages=max_pages_per_company)
                        for r in recs:
                            r["brand"] = brand
                        # 本地按 since 过滤(API 的 licenceDateFrom 参数会 500)
                        if since:
                            recs = [r for r in recs if r.get("auth_date", "") >= since]
                        all_records.extend(recs)
                    except Exception as e:
                        print(f"  [ISED] {brand}/{num} REL失败: {e}")
            else:
                search_term = ISED_BRAND_MAP.get(brand, brand)
                try:
                    companies = self.search_companies(search_term)
                    if not companies:
                        print(f"  [ISED] {brand}: 无公司匹配 '{search_term}'")
                        continue
                    for comp in companies[:max_companies_per_brand]:
                        try:
                            time.sleep(10)
                            sub_crawler = IcedCrawler(proxy=self.proxy)
                            recs = sub_crawler.search_rel(
                                company_number=comp["number"],
                                since_date=since,
                                max_pages=max_pages_per_company)
                            for r in recs:
                                r["brand"] = brand
                            if since:
                                recs = [r for r in recs if r.get("auth_date", "") >= since]
                            all_records.extend(recs)
                        except Exception as e:
                            print(f"  [ISED] {brand}/{comp['number']} REL失败: {e}")
                except Exception as e:
                    print(f"  [ISED] {brand} 失败: {e}")
        return all_records


def _match_brand_ised(company_name: str) -> str:
    """从公司名匹配竞品品牌。"""
    name_lower = (company_name or "").lower()
    for brand, keyword in ISED_BRAND_MAP.items():
        if keyword.lower() in name_lower:
            return brand
    return ""
