"""ENERGY STAR 能效认证爬虫。

数据源：ENERGY STAR Socrata SODA API（data.energystar.gov），免 API key。
  统一入口 Model Index 数据集: 8wj2-sec8（跨品类,约 180 万型号）
  资源端点: https://data.energystar.gov/resource/8wj2-sec8.json

策略：
  1. 按 brand_name + date_certified 查询（SoQL $where + $order + $limit + $offset）
  2. 分页拉取（每页 1000 条）
  3. 增量：只取 date_certified > since 的记录
  4. 品牌名大小写不一致 → 拉 distinct 品牌列表做归一化

字段映射：
  energy_star_model_identifier → source_id
  brand_name → applicant (品牌)
  model_number → model
  product_category → product_group
  date_certified → auth_date
  date_available_on_market → market_start
  markets → extra_json
  meets_most_efficient_criteria → extra_json

注意：
  - 日期返回 ISO 格式 'YYYY-MM-DDTHH:MM:SS.000'，截取前 10 位即可
  - 品牌名需大小写不敏感匹配（Socrata 支持 upper() 函数）
  - Socrata 匿名限速约 1000 req/h，竞品预警频率远低于此
"""
from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any

from ..fetchers import HttpFetcher, FetchResult

# Model Index 统一数据集（跨品类，约 180 万型号）
ES_MODEL_INDEX_ID = "8wj2-sec8"
ES_BASE_URL = "https://data.energystar.gov/resource"

# 竞品品牌 → ENERGY STAR brand_name 匹配关键词
# brand_name 在 ES 里大小写不一致,用 LIKE 模糊匹配
ES_BRAND_MAP = {
    "Samsung": "Samsung",
    "LG": "LG",
    "Hisense": "Hisense",
    "TCL": "TCL",
    "Sony": "Sony",
    "Panasonic": "Panasonic",
}

# TV/显示器相关品类(用于上市预警过滤)
TV_DISPLAY_CATEGORIES = [
    "Televisions", "Displays", "Computers", "Imaging Equipment",
]


class EnergyStarCrawler:
    """ENERGY STAR 能效认证爬虫。

    用法：
        crawler = EnergyStarCrawler(fetcher=HttpFetcher(proxy="..."))
        records = crawler.fetch_by_brand("Samsung", since="2026-01-01")
        for r in records:
            cidb.add_record(run_id, "energystar", r["source_id"], **r)
    """

    def __init__(self, fetcher: HttpFetcher | None = None):
        self.f = fetcher or HttpFetcher()

    def _api_get(self, params: dict[str, str]) -> list[dict]:
        """调 Socrata SODA API,返回 JSON 数组。

        Socrata 对无匹配结果返回 HTTP 200 + 空数组 [],HttpFetcher 的
        blocked 检测器可能误判空响应为 blocked,故不依赖 res.ok,直接解析 JSON。
        """
        url = f"{ES_BASE_URL}/{ES_MODEL_INDEX_ID}.json"
        # SoQL 参数以 $ 开头,值可能含空格/引号/特殊字符,需 URL 编码
        parts: list[str] = []
        for k, v in params.items():
            encoded = urllib.parse.quote(str(v), safe="'")
            parts.append(f"${k}={encoded}")
        full_url = f"{url}?{'&'.join(parts)}"
        res = self.f.get(full_url, headers={
            "Accept": "application/json",
        })
        if res.status != 200:
            raise RuntimeError(f"ENERGY STAR API 失败: HTTP {res.status}")
        try:
            data = json.loads(res.html)
            if isinstance(data, list):
                return data
            return []
        except (json.JSONDecodeError, ValueError) as e:
            # 空响应也是合法的(无匹配结果)
            if not res.html or res.html.strip() in ("", "[]"):
                return []
            raise RuntimeError(f"ENERGY STAR JSON 解析失败: {e}")

    def fetch_by_brand(self, brand: str, since: str = "",
                       categories: list[str] | None = None,
                       limit: int = 10000) -> list[dict]:
        """按品牌拉取认证记录。

        brand: 竞品品牌名(如 "Samsung")
        since: 只取 date_certified > since 的记录(yyyy-mm-dd)
        categories: 产品品类过滤(None=全部)
        limit: 最多拉取条数(分页每次 1000)
        """
        records: list[dict] = []
        offset = 0
        page_size = 1000

        while offset < limit:
            where_parts = [f"upper(brand_name)='{brand.upper()}'"]
            if since:
                where_parts.append(f"date_certified > '{since}'")
            if categories:
                cat_list = ",".join(f"'{c}'" for c in categories)
                where_parts.append(f"product_category IN ({cat_list})")

            params = {
                "select": ("product_category,brand_name,model_number,"
                           "model_name,date_certified,"
                           "date_available_on_market,markets,"
                           "energy_star_model_identifier,"
                           "meets_most_efficient_criteria"),
                "where": " AND ".join(where_parts),
                "order": "date_certified DESC",
                "limit": str(min(page_size, limit - offset)),
                "offset": str(offset),
            }
            page = self._api_get(params)
            if not page:
                break
            for row in page:
                rec = self._normalize(row, brand)
                if rec:
                    records.append(rec)
            if len(page) < page_size:
                break   # 最后一页
            offset += page_size

        return records

    def fetch_all_brands(self, brands: list[str] | None = None,
                         since: str = "",
                         categories: list[str] | None = None,
                         limit_per_brand: int = 5000) -> list[dict]:
        """批量拉取多个品牌的记录。

        brands: 品牌列表(None=用默认 6 大竞品)
        since: 只取 date_certified > since 的记录
        categories: 产品品类过滤
        limit_per_brand: 每个品牌最多拉取条数
        """
        brands = brands or list(ES_BRAND_MAP.keys())
        all_records: list[dict] = []
        for brand in brands:
            try:
                recs = self.fetch_by_brand(brand, since=since,
                                           categories=categories,
                                           limit=limit_per_brand)
                all_records.extend(recs)
            except Exception as e:
                # 某个品牌失败不影响其他
                print(f"  [警告] {brand} 拉取失败: {e}")
        return all_records

    def _normalize(self, row: dict, brand_hint: str = "") -> dict | None:
        """将 Socrata 返回的行标准化为 compintel_record 格式。"""
        es_id = (row.get("energy_star_model_identifier") or "").strip()
        if not es_id:
            # 没有唯一 ID,用 brand+model+date 拼一个
            model = (row.get("model_number") or "").strip()
            date = (row.get("date_certified") or "")[:10]
            if not model:
                return None
            es_id = f"{brand_hint}_{model}_{date}"

        def _date(v: str) -> str:
            """'2026-01-15T00:00:00.000' → '2026-01-15'"""
            v = (v or "").strip()
            return v[:10] if v else ""

        extra = {
            "product_category": row.get("product_category", ""),
            "model_name": row.get("model_name", ""),
            "markets": row.get("markets", ""),
            "meets_most_efficient": row.get("meets_most_efficient_criteria", ""),
        }

        return {
            "source_id": es_id,
            "applicant": (row.get("brand_name") or "").strip(),
            "brand": brand_hint,
            "model": (row.get("model_number") or "").strip(),
            "description": (row.get("product_category") or "").strip(),
            "auth_date": _date(row.get("date_certified", "")),
            "market_start": _date(row.get("date_available_on_market", "")),
            "product_group": (row.get("product_category") or "").strip(),
            "extra_json": extra,
        }

    def get_brands(self) -> list[str]:
        """获取去重品牌列表(用于建监控白名单)。"""
        params = {
            "select": "brand_name",
            "group": "brand_name",
            "order": "brand_name ASC",
            "limit": "500",
        }
        rows = self._api_get(params)
        return [r.get("brand_name", "").strip() for r in rows
                if r.get("brand_name")]
