"""UL / TÜV Rheinland / CB(VDE) 安全认证爬虫适配层。

复用 crawl4ai-main/cert_verify 包的 Provider,改为按"公司名/品牌名"搜索,
而非原始的"证书号→查详情"。适配到 compintel 架构的 compintel_record 格式。

数据源：
  TÜV Rheinland → Certipedia (www.certipedia.com)，纯 HTTP
  CB 证书       → VDE Solr JSON 接口，纯 HTTP
  UL            → UL Prospector (iq.ulprospector.com)，需 Playwright + 登录

注意：
  - cert_verify 包读 CERT_PROXY / VDE_PROXY 环境变量,不读 OVERSEAS_PROXY
  - cert_verify 原始输入是证书号,这里改为公司名搜索
  - UL 需先跑 python -m cert_verify.ul_login 人工登录,否则返回 UNSUPPORTED
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

# cert_verify 包在 crawl4ai-main 下,需加入 path
_CERT_VERIFY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "crawl4ai-main")
if _CERT_VERIFY_PATH not in sys.path:
    sys.path.insert(0, _CERT_VERIFY_PATH)

try:
    from cert_verify.providers.tuv_rheinland import TuvRheinlandProvider
    from cert_verify.providers.vde import VdeProvider
    from cert_verify.http_client import HttpClient
    _HAS_CERT_VERIFY = True
except ImportError:
    _HAS_CERT_VERIFY = False

# 竞品品牌 → 公司名搜索关键词
CERT_BRAND_MAP = {
    "Samsung": "Samsung Electronics",
    "LG": "LG Electronics",
    "Hisense": "Hisense",
    "TCL": "TCL",
    "Sony": "Sony",
    "Panasonic": "Panasonic",
}

CERTIPEDIA_SEARCH_URL = (
    "https://www.certipedia.com/search/matching_product_certificates"
    "?locale=en&q={q}")
VDE_SEARCH_URL = (
    "https://www.vde.com/www8/servlet/restSearch/2289904/zertreg-certificates"
    "?wt=json&fq=(detailDocType:zertreg|certificate)&start=0&rows=50"
    "&q=companyName_en:*{q}*")


def _normalize_cert_record(rec: Any, brand: str, source: str) -> dict | None:
    """将 cert_verify 的 CertRecord 转为 compintel_record 格式。"""
    if not hasattr(rec, "manufacturer"):
        return None
    cert_no = rec.cert_no_on_site or rec.query_no
    if not cert_no:
        return None
    extra = {
        "standard": getattr(rec, "standard", ""),
        "cert_type": getattr(rec, "cert_type", ""),
        "cert_status": getattr(rec, "cert_status", ""),
        "issue_date": getattr(rec, "issue_date", ""),
        "expiry_date": getattr(rec, "expiry_date", ""),
        "source_url": getattr(rec, "source_url", ""),
    }
    return {
        "source_id": cert_no,
        "applicant": rec.manufacturer or "",
        "brand": brand,
        "model": rec.model or "",
        "description": getattr(rec, "cert_type", "") or getattr(rec, "standard", ""),
        "auth_date": getattr(rec, "issue_date", ""),
        "market_end": getattr(rec, "expiry_date", ""),
        "product_group": getattr(rec, "cert_type", "") or "Safety Certificate",
        "extra_json": extra,
    }


class TuvCertCrawler:
    """TÜV Rheinland 安全认证爬虫(通过 Certipedia 搜索)。"""

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        if not _HAS_CERT_VERIFY:
            raise ImportError(
                "cert_verify 包不可用,请确保 crawl4ai-main/cert_verify 可导入")
        # 设置代理环境变量(cert_verify 读 VDE_PROXY / CERT_PROXY)
        if proxy:
            os.environ["CERT_PROXY"] = proxy
            os.environ["VDE_PROXY"] = proxy
        self.client = HttpClient(proxy=proxy)

    def search_by_company(self, company_name: str) -> list[dict]:
        """在 Certipedia 按公司名搜索证书。

        Certipedia 搜索: GET /search/matching_product_certificates?locale=en&q=<name>
        结果页含两种链接 + 摘要信息:
          /certificates/<数字证书号>  ← 直连详情
          /quality_marks/<id>?certificate_number=<编号>  ← 从 URL 参数取证书号

        优化: 从搜索结果页 HTML 直接提取摘要(证书持有人/产品/标准),
        不再逐条查详情(原 15s/条 × 50条 = 12min,改为 1 次请求秒出)。
        """
        import urllib.request, urllib.parse

        url = CERTIPEDIA_SEARCH_URL.format(
            q=urllib.parse.quote(company_name, safe=""))
        try:
            resp = self.client.get(url)
            if not resp or resp.status != 200:
                return []
            text = resp.text or ""
            brand = _match_brand_cert(company_name)
            records: list[dict] = []

            # 从搜索结果页提取每条结果的块
            # 结构: 每个结果是一个 div/section,含证书持有人/产品/标准
            # 提取所有证书号(从 /certificates/ 和 certificate_number= 两种)
            cert_nums = set()
            for m in re.finditer(r"/certificates/(\d+)", text):
                cert_nums.add(m.group(1))
            for m in re.finditer(r"certificate_number=(\d+)", text):
                cert_nums.add(m.group(1))

            # 从结果页提取公司名(Certipedia 搜索结果含证书持有人)
            # 每个 result-item 通常有: 证书号, 持有人, 产品, 标准
            # 简单提取: 找所有含 "Certificate Holder" 的文本块
            holder_re = re.compile(
                r'certificate\s*holder[^>]*>\s*([^<]+)', re.I)
            holders = [m.group(1).strip() for m in holder_re.finditer(text)]

            # 如果找不到结构化摘要,用证书号 + 搜索公司名
            for i, cert_no in enumerate(sorted(cert_nums)):
                holder = holders[i] if i < len(holders) else company_name
                records.append({
                    "source_id": cert_no,
                    "applicant": holder,
                    "brand": brand,
                    "model": "",
                    "description": "TÜV Rheinland Certificate",
                    "auth_date": "",
                    "product_group": "Safety Certificate",
                    "extra_json": {
                        "source_url": f"https://www.certipedia.com/certificates/{cert_no}?locale=en",
                        "search_company": company_name,
                    },
                })
            return records
        except Exception as e:
            print(f"  [TÜV] 搜索失败: {e}")
            return []

    def fetch_all_brands(self, brands: list[str] | None = None) -> list[dict]:
        """批量搜索多品牌证书。"""
        brands = brands or list(CERT_BRAND_MAP.keys())
        all_records: list[dict] = []
        for brand in brands:
            search_term = CERT_BRAND_MAP.get(brand, brand)
            try:
                recs = self.search_by_company(search_term)
                all_records.extend(recs)
            except Exception as e:
                print(f"  [TÜV] {brand} 失败: {e}")
        return all_records


class VdeCertCrawler:
    """CB 证书 / VDE 认证爬虫(通过 VDE Solr JSON 接口)。"""

    def __init__(self, proxy: str | None = None):
        self.proxy = proxy
        if proxy:
            os.environ["VDE_PROXY"] = proxy
        self.client = HttpClient(proxy=proxy) if _HAS_CERT_VERIFY else None

    def search_by_company(self, company_name: str) -> list[dict]:
        """在 VDE Solr 接口按公司名搜索证书。

        VDE Solr: GET .../zertreg-certificates?q=companyName_en:*<name>*
        实测 companyName 字段返回 400,必须用 companyName_en。
        公司名含空格需用 + 或 %20 编码(Solr 接受 + 作为空格)。
        """
        import urllib.request, urllib.parse, json as _json

        # Solr 通配符查询: companyName_en:*Samsung*
        # 多词公司名只取第一个词(含空格在 Solr q 参数中会 400)
        first_word = company_name.split()[0] if company_name else ""
        url = VDE_SEARCH_URL.format(q=first_word)
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "Referer": ("https://www.vde.com/tic-en/marks-and-certificates/"
                            "vde-approved-products/search"),
                "User-Agent": "Mozilla/5.0",
            })
            if self.proxy:
                handler = urllib.request.ProxyHandler(
                    {"http": self.proxy, "https": self.proxy})
                opener = urllib.request.build_opener(handler)
            else:
                opener = urllib.request.build_opener()
            with opener.open(req, timeout=30) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  [VDE] 搜索失败: {e}")
            return []

        docs = data.get("response", {}).get("docs", [])
        records: list[dict] = []
        for doc in docs:
            cert_id = doc.get("id", "").replace("zertreg|certificate#", "")
            company = (doc.get("companyName_en") or doc.get("companyName")
                       or doc.get("companyName_de") or "")
            types = doc.get("typeNames") or doc.get("firstTypes") or []
            model = types[0] if types else ""
            brand = _match_brand_cert(company or company_name)
            records.append({
                "source_id": cert_id,
                "applicant": company,
                "brand": brand,
                "model": model,
                "description": doc.get("productName_en") or doc.get("productName") or "",
                "auth_date": "",   # VDE Solr 不返回认证日期
                "product_group": "CB Certificate",
                "extra_json": {
                    "register_number": doc.get("registerNumber", ""),
                    "validity_limit": doc.get("validityLimit", ""),
                    "url": doc.get("generatedUrl", ""),
                },
            })
        return records

    def fetch_all_brands(self, brands: list[str] | None = None) -> list[dict]:
        """批量搜索多品牌 CB 证书。"""
        brands = brands or list(CERT_BRAND_MAP.keys())
        all_records: list[dict] = []
        for brand in brands:
            search_term = CERT_BRAND_MAP.get(brand, brand)
            try:
                recs = self.search_by_company(search_term)
                all_records.extend(recs)
            except Exception as e:
                print(f"  [VDE] {brand} 失败: {e}")
        return all_records


def _match_brand_cert(company_name: str) -> str:
    """从公司名匹配竞品品牌。"""
    name_lower = (company_name or "").lower()
    for brand, keyword in CERT_BRAND_MAP.items():
        if keyword.lower() in name_lower:
            return brand
    return ""
