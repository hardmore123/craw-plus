"""ANATEL 巴西电信设备认证爬虫。

数据源：ANATEL 开放数据 ZIP-CSV（每日更新，免登录）。
  https://www.anatel.gov.br/dadosabertos/paineis_de_dados/certificacao_de_produtos/produtos_certificados.zip

策略：
  1. 下载 ZIP → 解压 CSV（分号分隔，cp1252 编码，19 万+ 条）
  2. 按 Nome do Fabricante（制造商）过滤竞品品牌
  3. 每条记录标准化为 compintel_record 格式入库
  4. 增量比对：按 Número de Homologação 去重，新出现的 = 新认证

字段映射：
  Data da Homologação → auth_date (dd/mm/yyyy → yyyy-mm-dd)
  Número de Homologação → source_id
  Nome do Fabricante → applicant (制造商)
  Nome do Solicitante → 巴西申请方
  Modelo → model
  Nome Comercial → 商用名
  Tipo do Produto → product_group / description
  País do Fabricante → extra_json
  Situação do Certificado → extra_json (证书状态)

注意：
  - CSV 编码 cp1252（葡文重音），用 errors="replace" 兜底
  - 日期格式 dd/mm/yyyy 需转 yyyy-mm-dd
  - 文件 53MB，下载走 OVERSEAS_PROXY
"""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from typing import Any

from ..fetchers import HttpFetcher, FetchResult

ANATEL_ZIP_URL = (
    "https://www.anatel.gov.br/dadosabertos/paineis_de_dados/"
    "certificacao_de_produtos/produtos_certificados.zip"
)

# CSV 列名(葡文)
COL_HOMOLOG_DATE = "Data da Homologação"
COL_HOMOLOG_NUM = "Número de Homologação"
COL_SOLICITANTE = "Nome do Solicitante"
COL_CNPJ = "CNPJ do Solicitante"
COL_FABRICANTE = "Nome do Fabricante"
COL_MODELO = "Modelo"
COL_NOME_COMERCIAL = "Nome Comercial"
COL_TIPO_PRODUTO = "Tipo do Produto"
COL_PAIS = "País do Fabricante"
COL_SITUACAO_CERT = "Situação do Certificado"
COL_VALIDADE = "Data de Validade do Certificado"

# 竞品品牌 → 制造商名关键词映射(小写包含匹配)
# 关键词不含尾随空格——"tcl" 能匹配 "TCL Communication" 和 "TCL"(纯名)
# "lg" 单独太宽泛(会误匹配 jlg/alg 等),需组合更具体词
BRAND_FABRICANTE_MAP = {
    "Samsung": ["samsung"],
    "LG": ["lg electronics", "lg innotek", "lg chem", "lg display",
            "lg corp", "ericsson-lg", "lg do brasil", "lge"],
    "Hisense": ["hisense"],
    "TCL": ["tcl "],
    "Sony": ["sony"],
    "Panasonic": ["panasonic", "matsushita electric", "sanyo"],
}


def _parse_date_br(v: str) -> str:
    """dd/mm/yyyy → yyyy-mm-dd。空值返回 ''。"""
    v = (v or "").strip()
    if not v:
        return ""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", v)
    if m:
        d, mo, y = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    return v


def _match_brand(fabricante: str) -> str:
    """从制造商名匹配竞品品牌,返回品牌名或空串。"""
    fab_lower = (fabricante or "").lower()
    for brand, keywords in BRAND_FABRICANTE_MAP.items():
        if any(kw in fab_lower for kw in keywords):
            return brand
    return ""


class AnatelCrawler:
    """ANATEL 巴西认证数据爬虫。

    用法：
        crawler = AnatelCrawler(fetcher=HttpFetcher(proxy="..."))
        records = crawler.fetch_all(brands=["Samsung", "LG", ...])
        for r in records:
            cidb.add_record(run_id, "anatel", r["source_id"], **r)
    """

    def __init__(self, fetcher: HttpFetcher | None = None):
        self.f = fetcher or HttpFetcher()

    def fetch_all(self, brands: list[str] | None = None,
                  since: str = "") -> list[dict]:
        """下载 ANATEL ZIP → 解析 CSV → 按品牌过滤 → 返回记录列表。

        brands: 竞品品牌列表(None=全部)
        since: 只保留 auth_date >= since 的记录(yyyy-mm-dd)
        返回: [{source_id, applicant, brand, model, description, auth_date,
                product_group, extra_json, ...}]
        """
        # 1. 下载 ZIP(二进制,用 urllib 直取,不走 HttpFetcher 的 text 解码)
        raw_zip = self._download_zip()
        # 2. 解压 ZIP → 读 CSV
        csv_text = self._extract_csv(raw_zip)
        if not csv_text:
            raise RuntimeError("ANATEL ZIP 解压失败: 无 CSV 文件")
        # 3. 解析 CSV → 过滤品牌
        return self._parse_csv(csv_text, brands=brands, since=since)

    def _download_zip(self) -> bytes:
        """直接用 urllib 下载 ZIP 二进制内容(避免 HttpFetcher 的 UTF-8 解码损坏)。"""
        import urllib.request
        proxy = self.f.proxy if hasattr(self.f, "proxy") else None
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        if proxy:
            handler = urllib.request.ProxyHandler(
                {"http": proxy, "https": proxy})
            opener = urllib.request.build_opener(handler)
        else:
            opener = urllib.request.build_opener()
        req = urllib.request.Request(ANATEL_ZIP_URL, headers=headers)
        with opener.open(req, timeout=120) as resp:
            return resp.read()

    def _extract_csv(self, zip_bytes: bytes) -> str:
        """从 ZIP bytes 解压出 CSV 文本。

        ANATEL CSV 实测为 UTF-8 编码(带 BOM),用 utf-8-sig 解码自动去 BOM。
        部分历史批次可能用 cp1252,先试 utf-8-sig,失败回退 cp1252。
        """
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        except zipfile.BadZipFile:
            return ""
        # 找 CSV 文件
        csv_name = None
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                csv_name = name
                break
        if not csv_name:
            return ""
        raw = zf.read(csv_name)
        # 先试 utf-8-sig(去 BOM),失败回退 cp1252
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            return raw.decode("cp1252", errors="replace")

    def _parse_csv(self, csv_text: str,
                   brands: list[str] | None = None,
                   since: str = "") -> list[dict]:
        """解析 CSV 文本,按品牌过滤,返回标准化的记录列表。"""
        records: list[dict] = []
        # utf-8-sig 解码已去 BOM;兜底再检查一次
        if csv_text.startswith("\ufeff"):
            csv_text = csv_text[1:]
        # CSV 含 \r\n 和字段内换行,用 io.StringIO + newline="" 让 csv 模块自行处理
        reader = csv.DictReader(io.StringIO(csv_text, newline=""),
                                delimiter=";")
        if not reader.fieldnames:
            return []

        brand_set = set(brands) if brands else None
        seen_ids: set[str] = set()

        for row in reader:
            fabricante = (row.get(COL_FABRICANTE) or "").strip()
            brand = _match_brand(fabricante)
            if not brand:
                continue   # 非竞品品牌跳过
            if brand_set and brand not in brand_set:
                continue

            homolog_num = (row.get(COL_HOMOLOG_NUM) or "").strip()
            if not homolog_num or homolog_num in seen_ids:
                continue
            seen_ids.add(homolog_num)

            auth_date = _parse_date_br(row.get(COL_HOMOLOG_DATE, ""))
            if since and auth_date and auth_date < since:
                continue

            model = (row.get(COL_MODELO) or "").strip()
            tipo = (row.get(COL_TIPO_PRODUTO) or "").strip()
            solicitante = (row.get(COL_SOLICITANTE) or "").strip()
            pais = (row.get(COL_PAIS) or "").strip()
            situacao = (row.get(COL_SITUACAO_CERT) or "").strip()
            validade = _parse_date_br(row.get(COL_VALIDADE, ""))
            nome_comercial = (row.get(COL_NOME_COMERCIAL) or "").strip()

            extra = {
                "solicitante": solicitante,
                "cnpj": (row.get(COL_CNPJ) or "").strip(),
                "pais_fabricante": pais,
                "situacao_certificado": situacao,
                "validade": validade,
                "nome_comercial": nome_comercial,
            }

            records.append({
                "source_id": homolog_num,
                "applicant": fabricante,
                "applicant_code": homolog_num[:8] if len(homolog_num) >= 8 else "",
                "brand": brand,
                "model": model,
                "description": tipo,
                "auth_date": auth_date,
                "product_group": tipo,
                "extra_json": extra,
            })

        return records

    def get_last_modified(self) -> str:
        """HEAD 请求取 Last-Modified 头,判断是否有更新。"""
        try:
            import urllib.request
            req = urllib.request.Request(ANATEL_ZIP_URL, method="HEAD")
            proxy = self.f.proxy
            if proxy:
                handler = urllib.request.ProxyHandler(
                    {"http": proxy, "https": proxy})
                opener = urllib.request.build_opener(handler)
            else:
                opener = urllib.request.build_opener()
            resp = opener.open(req, timeout=30)
            return resp.headers.get("Last-Modified", "")
        except Exception:
            return ""
