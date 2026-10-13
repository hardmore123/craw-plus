"""Philips 意大利官网 TV SPEC 适配器（多级流程）。

意大利语入口 URL（/c-m-so/televisioni 或 /c-m-so/tv）待探测确认，先用
/c-m-so/tv/latest 作为 fallback 入口，后续探测调整。产品 URL 形如
/c-p/<MODEL>/<slug>/support，型号是 /c-p/ 后第一段，例如 43PUS7200_12；
系列提取去掉开头尺寸与 _NN 后缀取中间系列码（PUS7200）。
"""
from __future__ import annotations

from ...fetchers import Dom
from ...models import L2_MEDIUM, SpecSheet
from ...spec_parser import GENERIC_SPEC_JS, parse_en_kv_pairs
from .. import SiteAdapter
from ..ca_spec_common import anchor_records, clearly_non_tv, clean_url
from ..eu_spec_common import (
    PAGINATE_JS,
    PROD_RE,
    model_from_url as eu_model_from_url,
    series_of,
    specification_triples,
)

_BASE = "https://www.philips.it"
TV_LIST = f"{_BASE}/c-m-so/tv/latest"
_FALLBACK_LIST = f"{_BASE}/c-m-so/televisioni"


class PhilipsItAdapter(SiteAdapter):
    code = "philips_it"
    name = "Philips（意大利）"
    base_url = _BASE
    country = "意大利"
    channel = "Philips 官网"
    protection = L2_MEDIUM
    requires_browser = True
    suggested_interval = 5.0
    supports_spec = True
    spec_entry_wait = "a[href*='/c-p/']"
    spec_entry_extra_wait_ms = 5000
    spec_page_wait = "h1, h2"
    spec_entry_scroll_until_stable = True
    spec_entry_scroll_growth_selector = "a[href*='/c-p/']"
    spec_entry_scroll_max_passes = 80
    # 入口 URL 待探测确认，型号/系列数量待首次全量探测后校准。
    spec_entry_expected_model_count = 25
    spec_entry_expected_series_count = 11

    def spec_entry_url(self) -> str:
        return TV_LIST

    def series_entries(self, open_dom):
        model_url: dict[str, str] = {}
        meta: dict = {}
        used_url = TV_LIST
        termination = "entry_failed"
        for entry_url in (TV_LIST, _FALLBACK_LIST):
            try:
                with open_dom(entry_url, self.spec_entry_wait) as (res, dom, html):
                    meta = dict(getattr(res, "meta", {}) or {})
                    if dom is None or not res.ok:
                        continue
                    records: list[dict[str, str]] = []
                    eval_js = getattr(dom, "eval_js", None)
                    if callable(eval_js):
                        paged = eval_js(PAGINATE_JS)
                        if isinstance(paged, list):
                            records = [item for item in paged if isinstance(item, dict)]
                    if not records:
                        records = anchor_records(dom, self.spec_entry_wait, html,
                                                 limit=1800)
                    for record in records:
                        href = clean_url(_BASE, record.get("href", ""))
                        match = PROD_RE.search(href)
                        if not match or clearly_non_tv({**record, "href": href}):
                            continue
                        model_url.setdefault(match.group(1).upper(), href)
                    if model_url:
                        used_url = entry_url
                        termination = str(meta.get("scroll_termination") or "paginated")
                        break
            except Exception as exc:
                meta["exception"] = f"{type(exc).__name__}: {exc}"

        series_map: dict[str, list[str]] = {}
        for model, url in model_url.items():
            series_map.setdefault(series_of(model), []).append(url)
        self.last_entry_audit = {
            "requested_url": used_url,
            "fallback_urls": [TV_LIST, _FALLBACK_LIST],
            "expected_series_count": self.spec_entry_expected_series_count,
            "expected_model_count": self.spec_entry_expected_model_count,
            "discovered_series_count": len(series_map),
            "discovered_model_count": len(model_url),
            "termination_reason": termination,
            "details": {
                "meta": meta,
                "series": [
                    {"series": series,
                     "models": [{"model": self.model_from_url(url), "url": url}
                                for url in urls]}
                    for series, urls in series_map.items()
                ],
            },
        }
        return [(series, urls) for series, urls in series_map.items()]

    def model_from_url(self, url: str) -> str:
        return eu_model_from_url(url)

    def parse_spec_model(self, dom: Dom | None, series: str, model: str,
                         url: str = "") -> SpecSheet:
        empty = SpecSheet(brand=self.code, brand_name=self.name, series=series,
                          url=url, models=[model])
        if dom is None:
            return empty
        triples = specification_triples(dom.html())
        if not triples:
            eval_js = getattr(dom, "eval_js", None)
            if callable(eval_js):
                triples = eval_js(GENERIC_SPEC_JS) or []
        if not triples:
            return empty
        return parse_en_kv_pairs(triples, self.code, self.name, series, model, url)
