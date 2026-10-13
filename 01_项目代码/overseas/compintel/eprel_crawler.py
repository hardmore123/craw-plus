"""EPREL 能效注册记录爬虫（电子显示器品类）。

数据源：EPREL 官方 API（https://eprel.ec.europa.eu/api/）。
  列表：GET /api/products/electronicdisplays  → JSON, 25 条/请求
        {size: 总数, offset: 0, hits: [...]}
  详情：GET /api/product/<regNumber>           → 完整 JSON 产品
        GET /api/products/electronicdisplays/<regNumber> → 同上

关键发现（实测）：
- 页大小固定 25，from/size/page 等查询参数被忽略；大 from 触发 403。
- 故采用"轮询去重"策略：定期调列表，按 eprelRegistrationNumber 去重，新号入库。
- 需要某竞品的全部记录时，列表只给 25 条样本；用 supplierName 前缀在详情里核对。
- 想抓某具体产品：用注册号直查详情 API（稳定）。

字段（hit 顶层）：
  eprelRegistrationNumber, modelIdentifier, supplierOrTrademark, trademarkOwner,
  organisation{organisationName, website, isClosed},
  energyClass / energyClassSDR / energyClassHDR, energyClassRange,
  firstPublicationDate / firstPublicationDateTS,
  onMarketStartDate / onMarketStartDateTS,
  onMarketEndDate / onMarketEndDateTS,
  publishedOnDate / publishedOnDateTS, importedOn, exportDateTS,
  diagonalCm, diagonalInch, panelTechnology, resolutionHorizontalPixels,
  resolutionVerticalPixels, powerOnModeSDR, powerOnModeHDR, powerStandby,
  productGroup, category, status, formType
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ..fetchers import HttpFetcher, FetchResult

EPREL_LIST_URL = "https://eprel.ec.europa.eu/api/products/{group}"
EPREL_DETAIL_URL = "https://eprel.ec.europa.eu/api/product/{reg}"
EPREL_DETAIL_URL2 = "https://eprel.ec.europa.eu/api/products/{group}/{reg}"

# 电子显示器（电视/显示器）产品组标识
DISPLAY_GROUP = "electronicdisplays"

# 速率限制：EPREL 官方限 5 req/s。项目 RateLimiter 默认 6s 间隔太保守，
# compintel 独立用一个更快的限速器（每请求 1.2s）。
EPREL_MIN_INTERVAL = 1.2


@dataclass
class EprelRecord:
    registration_number: str = ""
    model_identifier: str = ""
    supplier_name: str = ""          # supplierOrTrademark
    trademark_owner: str = ""
    organisation_name: str = ""
    organisation_website: str = ""
    org_closed: bool = False
    energy_class: str = ""            # energyClass
    energy_class_sdr: str = ""
    energy_class_hdr: str = ""
    first_publication_date: str = ""  # "2020 7 19"
    first_publication_ts: int = 0
    on_market_start: str = ""
    on_market_end: str = ""
    published_on_date: str = ""
    published_on_ts: int = 0
    product_group: str = ""
    category: str = ""
    status: str = ""
    # 技术规格
    diagonal_cm: float = 0.0
    diagonal_inch: float = 0.0
    panel_technology: str = ""
    resolution_h: int = 0
    resolution_v: int = 0
    power_on_sdr: float = 0.0
    power_on_hdr: float = 0.0
    power_standby: float = 0.0
    extra: dict = field(default_factory=dict)


def _arr_to_date(v: Any) -> str:
    """[2019,5,15] 或 "2019 5 15" → "2019-05-15"。"""
    if isinstance(v, list) and len(v) >= 3:
        try:
            return f"{int(v[0]):04d}-{int(v[1]):02d}-{int(v[2]):02d}"
        except (TypeError, ValueError):
            return ""
    if isinstance(v, str):
        parts = re.split(r"[\s/-]+", v.strip())
        if len(parts) >= 3:
            try:
                return f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}"
            except (TypeError, ValueError):
                pass
    return ""


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def hit_to_record(hit: dict, group: str = DISPLAY_GROUP) -> EprelRecord:
    """API hit JSON → EprelRecord。保留原始未映射字段到 extra。"""
    org = hit.get("organisation") or {}
    rec = EprelRecord(
        registration_number=str(hit.get("eprelRegistrationNumber") or ""),
        model_identifier=str(hit.get("modelIdentifier") or ""),
        supplier_name=str(hit.get("supplierOrTrademark") or ""),
        trademark_owner=str(hit.get("trademarkOwner") or ""),
        organisation_name=str(org.get("organisationName") or ""),
        organisation_website=str(org.get("website") or ""),
        org_closed=bool(org.get("isClosed")),
        energy_class=str(hit.get("energyClass") or ""),
        energy_class_sdr=str(hit.get("energyClassSDR") or ""),
        energy_class_hdr=str(hit.get("energyClassHDR") or ""),
        first_publication_date=_arr_to_date(hit.get("firstPublicationDate")),
        first_publication_ts=int(hit.get("firstPublicationDateTS") or 0),
        on_market_start=_arr_to_date(hit.get("onMarketStartDate")),
        on_market_end=_arr_to_date(hit.get("onMarketEndDate")),
        published_on_date=_arr_to_date(hit.get("publishedOnDate")),
        published_on_ts=int(hit.get("publishedOnDateTS") or 0),
        product_group=str(hit.get("productGroup") or group),
        category=str(hit.get("category") or ""),
        status=str(hit.get("status") or ""),
        diagonal_cm=_num(hit.get("diagonalCm")),
        diagonal_inch=_num(hit.get("diagonalInch")),
        panel_technology=str(hit.get("panelTechnology") or ""),
        resolution_h=int(hit.get("resolutionHorizontalPixels") or 0),
        resolution_v=int(hit.get("resolutionVerticalPixels") or 0),
        power_on_sdr=_num(hit.get("powerOnModeSDR")),
        power_on_hdr=_num(hit.get("powerOnModeHDR")),
        power_standby=_num(hit.get("powerStandby")),
    )
    # 已显式映射的字段名集合，剩下的塞 extra
    mapped = {
        "eprelRegistrationNumber", "modelIdentifier", "supplierOrTrademark",
        "trademarkOwner", "organisation", "energyClass", "energyClassSDR",
        "energyClassHDR", "firstPublicationDate", "firstPublicationDateTS",
        "onMarketStartDate", "onMarketEndDate", "publishedOnDate",
        "publishedOnDateTS", "productGroup", "category", "status",
        "diagonalCm", "diagonalInch", "panelTechnology",
        "resolutionHorizontalPixels", "resolutionVerticalPixels",
        "powerOnModeSDR", "powerOnModeHDR", "powerStandby",
    }
    for k, v in hit.items():
        if k not in mapped and not k.startswith("_"):
            rec.extra[k] = v
    return rec


class EprelCrawler:
    """EPREL 电子显示器爬虫。"""

    def __init__(self, fetcher: HttpFetcher | None = None,
                 group: str = DISPLAY_GROUP):
        self.f = fetcher or HttpFetcher()
        self.group = group

    def close(self) -> None:
        self.f.close()

    def __enter__(self) -> "EprelCrawler":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get_json(self, url: str) -> dict:
        res = self.f.get(url, headers={"Accept": "application/json",
                                      "Origin": "https://eprel.ec.europa.eu",
                                      "Referer": "https://eprel.ec.europa.eu/screen/product/" + self.group})
        if not res.ok:
            raise RuntimeError(f"EPREL API failed {res.status}: {res.block_reason} {res.error}")
        try:
            return json.loads(res.html)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"EPREL API bad JSON: {e}") from e

    def list_recent(self) -> tuple[list[EprelRecord], int]:
        """调列表 API，返回本次 25 条记录 + 总数 size。"""
        url = EPREL_LIST_URL.format(group=self.group)
        data = self._get_json(url)
        total = int(data.get("size") or 0)
        hits = data.get("hits") or []
        recs = [hit_to_record(h, self.group) for h in hits]
        return recs, total

    def search_by_supplier(self, supplier: str,
                           group: str = "") -> tuple[list[EprelRecord], int]:
        """按供应商名搜索,返回最新 25 条 + 总数。

        EPREL API 的 offset 翻页不工作(不同 offset 返回相同记录),
        但 supplierOrTrademark 过器会改变返回的 25 条。
        近1年的新品通常出现在 offset=0 的 25 条中。

        supplier: 供应商名(如 "Samsung"、"LG"、"HELGI")
        group: 产品组(默认 self.group)
        """
        grp = group or self.group
        import urllib.parse
        url = EPREL_LIST_URL.format(group=grp) + "?" + \
              urllib.parse.urlencode({"supplierOrTrademark": supplier})
        data = self._get_json(url)
        total = int(data.get("size") or 0)
        hits = data.get("hits") or []
        recs = [hit_to_record(h, grp) for h in hits]
        return recs, total

    def fetch_detail(self, registration_number: str) -> EprelRecord:
        """按注册号抓单条详情（稳定，不受 25 条限制）。"""
        url = EPREL_DETAIL_URL.format(reg=registration_number)
        data = self._get_json(url)
        return hit_to_record(data, self.group)

    def fetch_many_details(self, registration_numbers: list[str]) -> list[EprelRecord]:
        """批量抓详情。逐个请求，依赖 fetcher 限速。"""
        out: list[EprelRecord] = []
        for reg in registration_numbers:
            try:
                out.append(self.fetch_detail(reg))
            except Exception:
                continue
        return out

    def scan_range(self, start: int, end: int, step: int = 1,
                   brands: list[str] | None = None,
                   max_results: int = 0) -> list[EprelRecord]:
        """按注册号区间遍历详情 API，返回电子显示器记录。

        EPREL 列表接口不可翻页（from 参数实质无效），全量抓取只能靠
        注册号逐条查 /api/product/<reg>。注册号上限远超 size 字段值
        （size=37467 但 reg=99999 也有数据）。

        参数：
          start/end: 注册号区间（含两端）
          step: 步长（>1 为抽样，省时间；=1 为全量遍历）
          brands: 只保留 supplier_name 含这些品牌名的记录（None=全留）
          max_results: 达到此数停止（0=不限）

        用法：
          # 全量遍历（慢，约 12 小时跑完 40 万号）
          crawler.scan_range(1, 400000, step=1, brands=["Samsung","LG"])
          # 抽样遍历（快，每 100 号抽 1 个，约 7 分钟）
          crawler.scan_range(1, 400000, step=100, brands=["Samsung","LG"])
        """
        out: list[EprelRecord] = []
        brands_lower = [b.lower() for b in brands] if brands else None
        # 电视相关产品组(EPREL 注册号跨组混编,需同时接受 televisions + electronicdisplays)
        TV_GROUPS = {"televisions", "electronicdisplays"}
        for reg in range(start, end + 1, step):
            try:
                rec = self.fetch_detail(str(reg))
                # 只留电视/显示器类(televisions + electronicdisplays)
                pg = (rec.product_group or "").lower()
                if pg not in TV_GROUPS:
                    continue
                # 品牌过滤
                if brands_lower:
                    sup = (rec.supplier_name + " " + rec.organisation_name).lower()
                    if not any(b in sup for b in brands_lower):
                        continue
                out.append(rec)
                if max_results and len(out) >= max_results:
                    break
            except Exception:
                continue
        return out
