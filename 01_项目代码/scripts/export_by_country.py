# -*- coding: utf-8 -*-
"""从唯一主库 data/overseas.db 按国家导出 CSV（价格最新值 + 价格历史 + 评价 + 评分汇总）。

用法：py -3.12 scripts/export_by_country.py [--out data/export_by_country]
国家取自各站适配器的 country 属性；取不到的归「未知」。
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8")


def site_country() -> dict[str, str]:
    from overseas.sites import SiteRegistry
    out = {}
    for code in SiteRegistry.codes() if hasattr(SiteRegistry, "codes") else []:
        try:
            out[code] = getattr(SiteRegistry.get(code), "country", "") or ""
        except Exception:
            pass
    if not out:
        import glob, re
        for p in glob.glob("overseas/sites/*/adapter.py"):
            t = open(p, encoding="utf-8").read()
            m1, m2 = re.search(r'code = "([^"]+)"', t), re.search(r'country = "([^"]+)"', t)
            if m1:
                out[m1.group(1)] = m2.group(1) if m2 else ""
    return out


Q_PRICE = """
select s.code, s.name, p.brand, p.model, p.size, p.title, p.url, ps.price, ps.list_price,
       ps.currency, ps.in_stock, ps.captured_at
from price_snapshot ps join product p on p.id = ps.product_id join site s on s.id = p.site_id
where ps.price > 0 order by s.code, p.model, ps.captured_at"""
Q_REVIEW = """
select s.code, p.brand, p.model, p.size, r.rating, r.title, r.body, r.author, r.review_date,
       r.helpful_count, r.review_url, r.image_count, r.image_urls, r.captured_at
from review r join product p on p.id = r.product_id join site s on s.id = p.site_id
order by s.code, p.model"""
Q_SUM = """
select s.code, p.brand, p.model, rs.avg_rating, rs.total_count, rs.star1, rs.star2, rs.star3,
       rs.star4, rs.star5, rs.captured_at
from review_summary rs join product p on p.id = rs.product_id join site s on s.id = p.site_id
order by s.code, p.model, rs.captured_at"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/overseas.db")
    ap.add_argument("--out", default="data/export_by_country")
    a = ap.parse_args()
    sc = site_country()
    c = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    files: dict = {}

    def w(country, kind, header, row):
        key = (country, kind)
        if key not in files:
            d = os.path.join(a.out, country or "未知")
            os.makedirs(d, exist_ok=True)
            f = open(os.path.join(d, f"{kind}.csv"), "w", encoding="utf-8-sig", newline="")
            files[key] = (f, csv.writer(f))
            files[key][1].writerow(header)
        files[key][1].writerow(row)

    hp = ["site", "site_name", "brand", "model", "size", "title", "url", "price", "list_price",
          "currency", "in_stock", "captured_at"]
    latest: dict = {}
    for r in c.execute(Q_PRICE):
        w(sc.get(r[0], ""), "价格历史", hp, r)
        latest[(r[0], r[3], r[6])] = r
    for r in latest.values():
        w(sc.get(r[0], ""), "价格最新", hp, r)
    hr = ["site", "brand", "model", "size", "rating", "title", "body", "author", "review_date",
          "helpful_count", "review_url", "image_count", "image_urls", "captured_at"]
    for r in c.execute(Q_REVIEW):
        w(sc.get(r[0], ""), "评价明细", hr, r)
    hs = ["site", "brand", "model", "avg_rating", "total_count", "star1", "star2", "star3",
          "star4", "star5", "captured_at"]
    for r in c.execute(Q_SUM):
        w(sc.get(r[0], ""), "评分汇总", hs, r)
    for f, _ in files.values():
        f.close()
    countries = sorted({k[0] or "未知" for k in files})
    print(f"导出 {len(countries)} 个国家 → {a.out}: {', '.join(countries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
