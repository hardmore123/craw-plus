"""汇总7站重抓前后对比"""
import sqlite3, sys
sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect("data/overseas.db")

SITES = ["amazon_de", "amazon_uk", "amazon_fr", "amazon_it", "amazon_es", "amazon_ca", "amazon_mx"]

# 重抓前数据（从checkpoint记录）
BEFORE = {
    "amazon_us": {"product": 410, "review": 0},
    "amazon_de": {"product": 4, "review": 13},
    "amazon_uk": {"product": 13, "review": 21},
    "amazon_fr": {"product": 70, "review": 284},
    "amazon_it": {"product": 43, "review": 337},
    "amazon_es": {"product": 42, "review": 234},
    "amazon_ca": {"product": 205, "review": 3178},
    "amazon_mx": {"product": 72, "review": 265},
}

print(f"{'站点':<14s} {'重抓前产品':>10s} {'重抓后产品':>10s} {'增量':>8s} {'重抓后评论':>10s} {'增量':>8s}")
print("-" * 70)

total_prod_before = 0
total_prod_after = 0
total_rev_before = 0
total_rev_after = 0

for code in SITES:
    prod = con.execute("SELECT COUNT(*) FROM product p JOIN site s ON p.site_id=s.id WHERE s.code=?", (code,)).fetchone()[0]
    rev = con.execute("SELECT COUNT(*) FROM review r JOIN product p ON r.product_id=p.id JOIN site s ON p.site_id=s.id WHERE s.code=?", (code,)).fetchone()[0]
    ts = con.execute("SELECT status, COUNT(*) FROM retail_task_status WHERE site_code=? GROUP BY status", (code,)).fetchall()
    ts_dict = dict(ts)

    before_p = BEFORE.get(code, {}).get("product", 0)
    before_r = BEFORE.get(code, {}).get("review", 0)
    d_p = prod - before_p
    d_r = rev - before_r

    total_prod_before += before_p
    total_prod_after += prod
    total_rev_before += before_r
    total_rev_after += rev

    ok = ts_dict.get("ok", 0)
    print(f"{code:<14s} {before_p:>10d} {prod:>10d} {d_p:>+8d} {rev:>10d} {d_r:>+8d}  ok={ok} no_item={ts_dict.get('no_item',0)} blocked={ts_dict.get('blocked',0)}")

print("-" * 70)
print(f"{'合计':<14s} {total_prod_before:>10d} {total_prod_after:>10d} {total_prod_after-total_prod_before:>+8d} {total_rev_after:>10d} {total_rev_after-total_rev_before:>+8d}")

con.close()
