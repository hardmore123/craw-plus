"""将 web 搜索抓取的专业评测写入 media_review 表。

从 Wired (55U7SG) 和 techfi.nl (QN90F for QN80H) 提取评测数据入库。
"""
from __future__ import annotations
import sys, os, json, sqlite3, re
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("OVERSEAS_PROXY", "http://127.0.0.1:7877")

DB = os.environ.get("OVERSEAS_DB_PATH") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "overseas.db")

# ──────────────────────────────────────────────
# 评测数据（从 Wired 和 techfi.nl 提取）
# ──────────────────────────────────────────────
REVIEWS = [
    {
        "site_code": "wired_us",
        "article_url": "https://www.wired.com/review/hisense-u7sg/",
        "title": "Hisense U7SG TV Review (2026): Better Design, Great Value",
        "headline": "Hisense U7SG TV Review (2026): Better Design, Great Value",
        "description": "Hisense's midrange U7 TV gets some high-end upgrades, but the competition is only getting stiffer.",
        "author": "WIRED",
        "date_published": "2026-01-15",
        "product_name": "Hisense 55U7SG",
        "product_model": "55U7SG",
        "product_brand": "Hisense",
        "rating_value": 8.0,
        "best_rating": 10.0,
        "worst_rating": 0.0,
        "rating_scale": "0-10",
        "positive_notes": [
            "Premium upgraded stand and anti-reflective screen",
            "Lots of brightness and deep black levels",
            "Improved image processing for impressive detail",
            "Vibrant colors, especially with high-quality video",
            "Excellent gaming support",
            "Snappy Google TV interface",
            "Solid sound quality",
        ],
        "negative_notes": [
            "Middling off-angle performance",
            "Default settings on picture modes look weird",
            "Better TVs are coming soon",
        ],
        "article_type": "review",
    },
    # ── 旗舰机型评测：BGR Hisense U8QG ──
    {
        "site_code": "bgr_us",
        "article_url": "https://www.bgr.com/reviews/hisense-u8qg-review-you-cant-do-better-at-this-price-point/",
        "title": "Hisense U8QG Review: You Can't Do Better At This Price Point",
        "headline": "Hisense U8QG Review: You Can't Do Better At This Price Point",
        "description": "The Hisense U8QG makes the U8 series even more tempting, with a brighter image and even better audio than before.",
        "author": "Christian de Looper",
        "date_published": "2026-06-01",
        "product_name": "Hisense 75U88QG",
        "product_model": "75U88QG",
        "product_brand": "Hisense",
        "rating_value": 8.0,
        "best_rating": 10.0,
        "worst_rating": 0.0,
        "rating_scale": "0-10",
        "positive_notes": [
            "Stunningly bright",
            "Deep black levels",
            "Improved audio",
            "HDMI 2.1 on all ports",
            "Excellent color response",
            "Good value-for-money",
        ],
        "negative_notes": [
            "Audio still isn't amazing",
            "Only three HDMI ports",
        ],
        "article_type": "review",
    },
    # ── 旗舰机型评测：Choose.tv Samsung QN80H ──
    {
        "site_code": "choose_tv",
        "article_url": "https://www.choose.tv/us/tv/reviews/samsung/samsung-qn80h_AIW/75",
        "title": "Samsung QN80H Review – Neo QLED TV Test and Opinion",
        "headline": "Samsung QN80H Review – Neo QLED TV Test and Opinion",
        "description": "We test the Samsung QN80H with Mini LED backlighting. See how it performs in picture quality, HDR, black levels, colors, gaming, and the Tizen system.",
        "author": "Maciej Koper",
        "date_published": "2026-03-01",
        "product_name": "Samsung QN75QN80HAFXZC",
        "product_model": "QN75QN80HAFXZC",
        "product_brand": "Samsung",
        "rating_value": 7.3,
        "best_rating": 10.0,
        "worst_rating": 1.0,
        "rating_scale": "0-10",
        "positive_notes": [
            "Deep blacks thanks to Mini LED backlighting",
            "High peak brightness over 1000 nits in HDR",
            "Vivid colors from QLED quantum dots",
            "High panel refresh rate of 144 Hz",
            "4 HDMI 2.1 ports",
            "Very low input lag",
            "Extensive gaming features",
            "Fast Tizen OS",
            "Seven years of system support",
            "Excellent PC compatibility (240 Hz mode, great font readability)",
            "Adjustable stand width and height",
        ],
        "negative_notes": [
            "Limited number of local dimming zones: 110 in the 65-inch model",
            "Average reflection suppression",
            "No USB recording or PIP function",
            "Cheap-looking plastic feet",
            "No solar-powered remote",
        ],
        "article_type": "review",
    },
]

# techfi_nl 的 QN90F 评测（已在DB中），但我们需要标注它对应 QN80H
# 不需要新增，只需在报告生成时用 QN90F 评测替代 QN80H


def insert_reviews():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    now = datetime.now(timezone.utc).isoformat()

    for rev in REVIEWS:
        # Check if exists
        cur.execute("SELECT id FROM media_review WHERE site_code=? AND article_url=?",
                    (rev["site_code"], rev["article_url"]))
        existing = cur.fetchone()

        cols = ["site_code","article_url","title","headline","description","author",
                "date_published","date_modified","product_name","product_model","product_brand",
                "rating_value","best_rating","worst_rating","rating_scale",
                "positive_notes","negative_notes","article_type","captured_at","raw_jsonld"]
        vals = [
            rev["site_code"], rev["article_url"], rev["title"], rev["headline"],
            rev["description"], rev["author"], rev["date_published"], "",
            rev["product_name"], rev["product_model"], rev["product_brand"],
            rev["rating_value"], rev["best_rating"], rev["worst_rating"], rev["rating_scale"],
            json.dumps(rev["positive_notes"], ensure_ascii=False),
            json.dumps(rev["negative_notes"], ensure_ascii=False),
            rev["article_type"], now, "",
        ]
        placeholders = ",".join(["?"]*len(cols))
        col_str = ",".join(cols)

        if existing:
            set_clause = ",".join(f"{c}=?" for c in cols if c not in ("site_code","article_url"))
            set_vals = [v for c, v in zip(cols, vals) if c not in ("site_code","article_url")]
            set_vals.extend([rev["site_code"], rev["article_url"]])
            cur.execute(f"UPDATE media_review SET {set_clause} WHERE site_code=? AND article_url=?", set_vals)
            print(f"  UPDATE: {rev['product_name']} ({rev['site_code']}) rating={rev['rating_value']}/10")
        else:
            cur.execute(f"INSERT OR REPLACE INTO media_review ({col_str}) VALUES ({placeholders})", vals)
            print(f"  INSERT: {rev['product_name']} ({rev['site_code']}) rating={rev['rating_value']}/10")

    con.commit()
    con.close()
    print(f"\n✅ 完成 {len(REVIEWS)} 条评测入库")


if __name__ == "__main__":
    insert_reviews()
