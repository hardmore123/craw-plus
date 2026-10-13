"""按国家导出独立的SQLite数据库，结构与日本库一致：
每国一个 .db 文件，含 site / product / price_snapshot / review / product_spec / spec_series / spec_row 等表。
只取最新周次的spec_row，保证数据最新最全。

输出目录: data/national_db/
  data/national_db/USA/usa.db
  data/national_db/Japan/japan.db
  ...
"""
import sqlite3, sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

SRC = "data/overseas.db"
OUT = "data/national_db"
os.makedirs(OUT, exist_ok=True)

con = sqlite3.connect(SRC)
con.row_factory = sqlite3.Row

# 从adapter读country
base_sites = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overseas", "sites")
site_country = {}
for d in os.listdir(base_sites):
    ap = os.path.join(base_sites, d, "adapter.py")
    if not os.path.exists(ap):
        continue
    with open(ap, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'country\s*=\s*["\']([^"\']+)["\']', src)
    if m:
        site_country[d] = m.group(1)

# 国家名统一
COUNTRY_MAP = {
    "墨西哥": "Mexico", "德国": "Germany", "意大利": "Italy", "日本": "Japan",
    "法国": "France", "英国": "United Kingdom", "美国": "USA", "加拿大": "Canada",
    "智利": "Chile", "哥伦比亚": "Colombia", "秘鲁": "Peru", "玻利维亚": "Bolivia",
    "厄瓜多尔": "Ecuador", "西班牙": "Spain",
}
SUFFIX_MAP = {
    "ca": "Canada", "us": "USA", "mx": "Mexico", "uk": "United Kingdom",
    "de": "Germany", "fr": "France", "it": "Italy", "es": "Spain",
    "jp": "Japan", "cl": "Chile", "co": "Colombia", "pe": "Peru", "bo": "Bolivia",
    "ec": "Ecuador", "br": "Brazil", "pt": "Portugal", "nl": "Netherlands",
    "be": "Belgium", "ch": "Switzerland", "at": "Austria", "se": "Sweden",
    "no": "Norway", "dk": "Denmark", "fi": "Finland", "pl": "Poland",
    "cz": "Czech Republic", "sk": "Slovakia", "hu": "Hungary", "ro": "Romania",
    "bg": "Bulgaria", "gr": "Greece", "hr": "Croatia", "si": "Slovenia",
    "ba": "Bosnia", "rs": "Serbia", "tr": "Turkey", "ru": "Russia", "ua": "Ukraine",
    "lt": "Lithuania", "lv": "Latvia", "ee": "Estonia", "gt": "Guatemala",
    "pa": "Panama", "do": "Dominican Republic",
}

def get_country(code):
    c = site_country.get(code, "")
    if c:
        return COUNTRY_MAP.get(c, c)
    parts = code.rsplit("_", 1)
    if len(parts) == 2:
        return SUFFIX_MAP.get(parts[1].lower(), parts[1].upper())
    return "Other"

# 收集所有站点code→国家
spec_sites = [r["brand"] for r in con.execute("SELECT DISTINCT brand FROM spec_series").fetchall()]
retail_sites = [r["code"] for r in con.execute("SELECT DISTINCT s.code FROM site s JOIN product p ON p.site_id=s.id GROUP BY s.code").fetchall()]

# 按国家分组
from collections import defaultdict
country_sites = defaultdict(set)
for code in spec_sites + retail_sites:
    country_sites[get_country(code)].add(code)

print(f"共{len(country_sites)}个国家")

# 每个站点所属的国家code列表
site_to_country = {}
for country, codes in country_sites.items():
    for code in codes:
        site_to_country[code] = country

# ===== CREATE TABLE DDL（与主库一致）=====
DDL = """
CREATE TABLE site (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE,
    name TEXT,
    base_url TEXT,
    protection TEXT,
    created_at TEXT
);
CREATE TABLE product (
    id INTEGER PRIMARY KEY,
    site_id INTEGER,
    sku TEXT,
    url TEXT,
    title TEXT,
    brand TEXT,
    model TEXT,
    category TEXT,
    first_seen TEXT,
    last_seen TEXT,
    size TEXT
);
CREATE TABLE price_snapshot (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    price REAL,
    list_price REAL,
    currency TEXT,
    in_stock INTEGER,
    raw_text TEXT,
    captured_at TEXT
);
CREATE TABLE review (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    review_key TEXT,
    rating REAL,
    title TEXT,
    body TEXT,
    author TEXT,
    review_date TEXT,
    verified INTEGER,
    helpful_count INTEGER,
    captured_at TEXT,
    review_url TEXT,
    image_urls TEXT,
    image_count INTEGER DEFAULT 0,
    video_urls TEXT,
    has_video INTEGER DEFAULT 0
);
CREATE TABLE product_spec (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    key TEXT,
    value TEXT,
    captured_at TEXT
);
CREATE TABLE spec_series (
    id INTEGER PRIMARY KEY,
    brand TEXT,
    brand_name TEXT,
    series TEXT,
    url TEXT,
    models TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE spec_row (
    id INTEGER PRIMARY KEY,
    series_id INTEGER,
    category TEXT,
    item_ja TEXT,
    item_zh TEXT,
    row_order INTEGER,
    values_json TEXT,
    captured_week TEXT,
    captured_at TEXT
);
CREATE TABLE review_summary (
    id INTEGER PRIMARY KEY,
    product_id INTEGER,
    avg_rating REAL,
    total_count INTEGER,
    summary_text TEXT,
    star1 INTEGER, star2 INTEGER, star3 INTEGER, star4 INTEGER, star5 INTEGER,
    captured_at TEXT
);
"""

total_files = 0
for country in sorted(country_sites.keys()):
    codes = country_sites[country]
    cdir = os.path.join(OUT, country)
    os.makedirs(cdir, exist_ok=True)
    
    # 文件名：国家小写+下划线
    safe_name = re.sub(r"[^\w]", "_", country.lower())
    db_path = os.path.join(cdir, f"{safe_name}.db")
    
    # 删除旧文件
    if os.path.exists(db_path):
        os.remove(db_path)
    
    out = sqlite3.connect(db_path)
    out.executescript(DDL)
    
    # ID映射
    site_id_map = {}  # old_id → new_id
    product_id_map = {}  # old_id → new_id
    series_id_map = {}  # old_id → new_id
    
    # 1. 导出site
    for code in sorted(codes):
        row = con.execute("SELECT * FROM site WHERE code=?", (code,)).fetchone()
        if not row:
            # SPEC站可能不在site表，构造一条
            ap = os.path.join(base_sites, code, "adapter.py")
            name = code
            base_url = ""
            if os.path.exists(ap):
                with open(ap, encoding="utf-8") as f:
                    src = f.read()
                m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', src)
                if m: name = m.group(1)
                m2 = re.search(r'base_url\s*=\s*["\']([^"\']+)["\']', src)
                if m2: base_url = m2.group(1)
            cur = out.execute("INSERT INTO site(code,name,base_url,protection,created_at) VALUES(?,?,?,?,?)",
                            (code, name, base_url, "L2", ""))
            site_id_map[row["id"] if row else 0] = cur.lastrowid
            old_sid = row["id"] if row else 0
            site_id_map[old_sid] = cur.lastrowid
        else:
            cur = out.execute("INSERT INTO site(code,name,base_url,protection,created_at) VALUES(?,?,?,?,?)",
                            (row["code"], row["name"], row["base_url"], row["protection"], row["created_at"]))
            site_id_map[row["id"]] = cur.lastrowid
    
    # 2. 导出product（零售站的产品）
    for code in sorted(codes):
        rows = con.execute("SELECT * FROM product WHERE site_id IN (SELECT id FROM site WHERE code=?)", (code,)).fetchall()
        for r in rows:
            old_pid = r["id"]
            new_sid = site_id_map.get(r["site_id"], 0)
            if new_sid == 0:
                continue
            cur = out.execute(
                "INSERT INTO product(site_id,sku,url,title,brand,model,category,first_seen,last_seen,size) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (new_sid, r["sku"], r["url"], r["title"], r["brand"], r["model"],
                 r["category"], r["first_seen"], r["last_seen"], r["size"]))
            product_id_map[old_pid] = cur.lastrowid
    
    # 3. 导出price_snapshot
    for code in sorted(codes):
        rows = con.execute(
            "SELECT ps.* FROM price_snapshot ps JOIN product p ON ps.product_id=p.id "
            "JOIN site s ON p.site_id=s.id WHERE s.code=?", (code,)).fetchall()
        for r in rows:
            new_pid = product_id_map.get(r["product_id"], 0)
            if new_pid == 0:
                continue
            out.execute(
                "INSERT INTO price_snapshot(product_id,price,list_price,currency,in_stock,raw_text,captured_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (new_pid, r["price"], r["list_price"], r["currency"],
                 r["in_stock"], r["raw_text"], r["captured_at"]))
    
    # 4. 导出review
    for code in sorted(codes):
        rows = con.execute(
            "SELECT r.* FROM review r JOIN product p ON r.product_id=p.id "
            "JOIN site s ON p.site_id=s.id WHERE s.code=?", (code,)).fetchall()
        for r in rows:
            new_pid = product_id_map.get(r["product_id"], 0)
            if new_pid == 0:
                continue
            out.execute(
                "INSERT INTO review(product_id,review_key,rating,title,body,author,review_date,"
                "verified,helpful_count,captured_at,review_url,image_urls,image_count,video_urls,has_video) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (new_pid, r["review_key"], r["rating"], r["title"], r["body"],
                 r["author"], r["review_date"], r["verified"], r["helpful_count"],
                 r["captured_at"], r["review_url"], r["image_urls"], r["image_count"],
                 r["video_urls"], r["has_video"]))
    
    # 5. 导出product_spec
    for code in sorted(codes):
        rows = con.execute(
            "SELECT ps.* FROM product_spec ps JOIN product p ON ps.product_id=p.id "
            "JOIN site s ON p.site_id=s.id WHERE s.code=?", (code,)).fetchall()
        for r in rows:
            new_pid = product_id_map.get(r["product_id"], 0)
            if new_pid == 0:
                continue
            out.execute(
                "INSERT INTO product_spec(product_id,key,value,captured_at) VALUES(?,?,?,?)",
                (new_pid, r["key"], r["value"], r["captured_at"]))
    
    # 6. 导出spec_series + spec_row（只取最新周次）
    for code in sorted(codes):
        # spec_series
        series_rows = con.execute("SELECT * FROM spec_series WHERE brand=?", (code,)).fetchall()
        for r in series_rows:
            cur = out.execute(
                "INSERT INTO spec_series(brand,brand_name,series,url,models,first_seen,last_seen) "
                "VALUES(?,?,?,?,?,?,?)",
                (r["brand"], r["brand_name"], r["series"], r["url"],
                 r["models"], r["first_seen"], r["last_seen"]))
            series_id_map[r["id"]] = cur.lastrowid
        
        # spec_row — 只取最新周次
        latest = con.execute(
            "SELECT MAX(sr.captured_week) as w FROM spec_row sr "
            "JOIN spec_series ss ON sr.series_id=ss.id WHERE ss.brand=?", (code,)).fetchone()
        if latest["w"]:
            spec_rows = con.execute(
                "SELECT sr.* FROM spec_row sr "
                "JOIN spec_series ss ON sr.series_id=ss.id "
                "WHERE ss.brand=? AND sr.captured_week=? ORDER BY sr.row_order",
                (code, latest["w"])).fetchall()
            for r in spec_rows:
                new_sid = series_id_map.get(r["series_id"], 0)
                if new_sid == 0:
                    continue
                out.execute(
                    "INSERT INTO spec_row(series_id,category,item_ja,item_zh,row_order,values_json,captured_week,captured_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (new_sid, r["category"], r["item_ja"], r["item_zh"],
                     r["row_order"], r["values_json"], r["captured_week"], r["captured_at"]))
    
    out.commit()
    
    # 统计
    stats = {}
    for tbl in ["site", "product", "price_snapshot", "review", "product_spec", "spec_series", "spec_row"]:
        stats[tbl] = out.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    
    out.close()
    total_files += 1
    print(f"  {country:30s} → {safe_name}.db "
          f"({stats['site']}站 {stats['product']}产品 {stats['price_snapshot']}价格 "
          f"{stats['review']}评论 {stats['spec_series']}系列 {stats['spec_row']}规格行)")

print(f"\n{'='*80}")
print(f"完成: {total_files}个国家数据库")
print(f"目录: {OUT}/")
print(f"{'='*80}")

con.close()
