-- ⚠️ 历史旧版 schema（2026-09 早期，表数/列已过时）。当前权威建表 DDL 在
-- ../../01_项目代码/overseas/schema.sql（核心27表）+ db.py（迁移），
-- 数据库结构说明见 ../../01_项目代码/docs/数据库结构说明.md。本文件仅作历史追溯。

CREATE TABLE crawl_error (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER REFERENCES crawl_run(id),
    url         TEXT,
    stage       TEXT,                          -- search/detail/reviews
    kind        TEXT,                          -- blocked/timeout/http/parse
    message     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE crawl_run (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario    TEXT NOT NULL,                 -- s1_search / s2_monitor / s4_reviews
    site_code   TEXT,
    params      TEXT,                          -- JSON
    status      TEXT NOT NULL,                 -- running/completed/failed/stopped
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    ok_count    INTEGER DEFAULT 0,
    fail_count  INTEGER DEFAULT 0,
    message     TEXT
);

CREATE TABLE kakaku_task_status (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER REFERENCES crawl_run(id) ON DELETE CASCADE,
    task          TEXT NOT NULL CHECK (task IN ('price', 'review', 'release')),
    brand         TEXT NOT NULL,               -- 品牌 code，如 hisense_jp
    brand_name    TEXT,                        -- 展示名，如 Hisense
    model         TEXT NOT NULL,               -- 型号，如 65U8S
    item_id       TEXT,                        -- kakaku 商品号 K000xxxx
    product_id    INTEGER REFERENCES product(id) ON DELETE SET NULL,
    status        TEXT NOT NULL,               -- ok/no_item/not_target_year/no_reviews/no_price/blocked/failed
    release_text  TEXT,                        -- 发售日原文
    release_year  INTEGER,
    size          TEXT,
    row_count     INTEGER NOT NULL DEFAULT 0,  -- 本次写入的评价条数/店铺价条数
    new_count     INTEGER NOT NULL DEFAULT 0,  -- 其中新增条数（评论增量）
    message       TEXT,
    captured_at   TEXT NOT NULL,
    UNIQUE (run_id, task, brand, model)
);

CREATE TABLE kakaku_thread_state (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        TEXT NOT NULL,               -- kakaku 商品号 K000xxxx
    thread_url     TEXT NOT NULL,               -- 讨论主题绝对 URL（含 SortID）
    thread_title   TEXT,
    last_post_key  TEXT,                         -- 该主题最后一条書込番号
    post_count     INTEGER NOT NULL DEFAULT 0,   -- 该主题上次抓到的帖数
    last_seen      TEXT NOT NULL,
    UNIQUE (item_id, thread_url)
);

CREATE TABLE price_shop_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    shop        TEXT NOT NULL,                 -- 店铺名，如 ヨドバシ.com
    price       REAL,                          -- 该店铺售价
    currency    TEXT,                          -- 货币，如 JPY
    is_lowest   INTEGER DEFAULT 0,             -- 1=本次采集中该店为最安店铺
    captured_at TEXT NOT NULL
);

CREATE TABLE price_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    price       REAL,
    list_price  REAL,
    currency    TEXT,
    in_stock    INTEGER,                       -- 1/0/NULL
    raw_text    TEXT,
    captured_at TEXT NOT NULL
);

CREATE TABLE product (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     INTEGER NOT NULL REFERENCES site(id),
    sku         TEXT NOT NULL,                 -- ASIN / 站内商品号
    url         TEXT,
    title       TEXT,
    brand       TEXT,
    model       TEXT,                          -- 厂商型号，跨站比价用
    category    TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL, size TEXT,
    UNIQUE (site_id, sku)
);

CREATE TABLE product_spec (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT,
    captured_at TEXT NOT NULL,
    UNIQUE (product_id, key)
);

CREATE TABLE ranking_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    list_name   TEXT NOT NULL,
    rank        INTEGER,
    captured_at TEXT NOT NULL
);

CREATE TABLE raw_page (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    url         TEXT NOT NULL,
    sha1        TEXT NOT NULL,
    path        TEXT NOT NULL,
    status      INTEGER,
    created_at  TEXT NOT NULL
);

CREATE TABLE retail_task_status (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id      INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
                    region      TEXT NOT NULL,
                    task        TEXT NOT NULL CHECK (task IN ('price', 'review')),
                    site_code   TEXT NOT NULL,
                    site_name   TEXT,
                    brand       TEXT NOT NULL,
                    brand_name  TEXT,
                    model       TEXT NOT NULL,
                    item_id     TEXT,
                    product_id  INTEGER REFERENCES product(id) ON DELETE SET NULL,
                    status      TEXT NOT NULL,
                    size        TEXT,
                    price       REAL,
                    currency    TEXT,
                    row_count   INTEGER NOT NULL DEFAULT 0,
                    new_count   INTEGER NOT NULL DEFAULT 0,
                    message     TEXT,
                    captured_at TEXT NOT NULL,
                    UNIQUE (run_id, task, region, site_code, brand, model)
                );

CREATE TABLE review (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id    INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    review_key    TEXT NOT NULL,               -- 站内唯一 id，增量去重
    rating        REAL,
    title         TEXT,
    body          TEXT,
    author        TEXT,
    review_date   TEXT,
    verified      INTEGER,
    helpful_count INTEGER,
    captured_at   TEXT NOT NULL, review_url TEXT, image_urls TEXT, image_count INTEGER DEFAULT 0, video_urls TEXT, has_video INTEGER DEFAULT 0,
    UNIQUE (product_id, review_key)
);

CREATE TABLE review_summary (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    avg_rating  REAL,
    total_count INTEGER,
    star1       INTEGER,
    star2       INTEGER,
    star3       INTEGER,
    star4       INTEGER,
    star5       INTEGER,
    captured_at TEXT NOT NULL
);

CREATE TABLE schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

CREATE TABLE selling_point (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id     INTEGER REFERENCES spec_series(id) ON DELETE SET NULL,
    brand         TEXT NOT NULL,             -- 品牌 code，如 sony_jp
    brand_name    TEXT,                      -- 展示名
    series        TEXT NOT NULL,             -- 系列
    model         TEXT,                      -- 机型（可为空，表示系列级卖点）
    point_type    TEXT NOT NULL,             -- text / image / video / composite
    title         TEXT,                      -- 卖点标题
    description   TEXT,                      -- 卖点描述/文案
    image_urls    TEXT,                      -- 图片 URL JSON 数组
    video_urls    TEXT,                      -- 视频 URL JSON 数组
    refined_text  TEXT,                      -- LLM 精炼后的卖点摘要
    refined_by    TEXT,                      -- LLM 模型名
    point_order   INTEGER DEFAULT 0,         -- 顺序
    captured_week TEXT NOT NULL,             -- ISO 周，如 2026-W38
    captured_at   TEXT NOT NULL,
    UNIQUE (brand, series, model, title, captured_week)
);

CREATE TABLE selling_point_status (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    brand          TEXT NOT NULL,
    brand_name     TEXT,
    series         TEXT NOT NULL,
    captured_week  TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('success', 'empty', 'failed')),
    series_id      INTEGER REFERENCES spec_series(id) ON DELETE SET NULL,
    point_count    INTEGER NOT NULL DEFAULT 0,
    llm_refined    INTEGER NOT NULL DEFAULT 0,   -- 1=已用 LLM 精炼
    error_kind     TEXT,
    message        TEXT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT NOT NULL,
    UNIQUE (run_id, brand, series)
);

CREATE TABLE site (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,          -- amazon_ca
    name        TEXT NOT NULL,
    base_url    TEXT,
    protection  TEXT,                          -- L1 / L2 / L3
    created_at  TEXT NOT NULL
);

CREATE TABLE spec_entry_audit (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                   INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    brand                    TEXT NOT NULL,
    brand_name               TEXT,
    requested_url            TEXT,
    expected_series_count    INTEGER,
    discovered_series_count  INTEGER NOT NULL DEFAULT 0,
    expected_model_count     INTEGER,
    discovered_model_count   INTEGER NOT NULL DEFAULT 0,
    termination_reason       TEXT,
    details_json             TEXT,
    captured_at              TEXT NOT NULL,
    UNIQUE (run_id, brand)
);

CREATE TABLE spec_row (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id     INTEGER NOT NULL REFERENCES spec_series(id) ON DELETE CASCADE,
    category      TEXT,                     -- 区分
    item_ja       TEXT NOT NULL,            -- 项目（日文）
    item_zh       TEXT,                     -- 项目（中文，查词典）
    row_order     INTEGER DEFAULT 0,
    values_json   TEXT,                     -- {机型: 值} JSON
    captured_week TEXT NOT NULL,            -- ISO 周，如 2026-W36
    captured_at   TEXT NOT NULL,
    UNIQUE (series_id, item_ja, category, captured_week)
);

CREATE TABLE spec_series (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    brand        TEXT NOT NULL,             -- 品牌 code，如 hisense_jp
    brand_name   TEXT,                      -- 展示名
    series       TEXT NOT NULL,             -- 系列，如 U8S
    url          TEXT,
    models       TEXT,                      -- 机型列表 JSON（列顺序）
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    UNIQUE (brand, series)
);

CREATE TABLE spec_series_status (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    brand          TEXT NOT NULL,
    brand_name     TEXT,
    series         TEXT NOT NULL,
    captured_week  TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('success', 'empty', 'failed')),
    status_source  TEXT NOT NULL DEFAULT 'crawl',
    requested_url  TEXT,
    selected_url   TEXT,
    attempted_urls TEXT,
    series_id      INTEGER REFERENCES spec_series(id) ON DELETE SET NULL,
    model_expected INTEGER NOT NULL DEFAULT 0,
    model_ok       INTEGER NOT NULL DEFAULT 0,
    model_empty    INTEGER NOT NULL DEFAULT 0,
    model_failed   INTEGER NOT NULL DEFAULT 0,
    row_count      INTEGER NOT NULL DEFAULT 0,
    error_kind     TEXT,
    message        TEXT,
    started_at     TEXT NOT NULL,
    finished_at    TEXT NOT NULL,
    UNIQUE (run_id, brand, series)
);

CREATE TABLE spec_untranslated (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_ja      TEXT NOT NULL UNIQUE,
    brand        TEXT,
    seen_count   INTEGER DEFAULT 1,
    last_seen    TEXT NOT NULL
);

CREATE INDEX idx_error_run ON crawl_error(run_id);

CREATE INDEX idx_kakaku_status_model_time
    ON kakaku_task_status(brand, model, captured_at);

CREATE INDEX idx_kakaku_status_task_brand
    ON kakaku_task_status(task, brand, status);

CREATE INDEX idx_kakaku_thread_item
    ON kakaku_thread_state(item_id);

CREATE INDEX idx_price_product_time
    ON price_snapshot(product_id, captured_at);

CREATE INDEX idx_price_shop_product_time
    ON price_shop_snapshot(product_id, captured_at);

CREATE INDEX idx_price_shop_shop
    ON price_shop_snapshot(shop, captured_at);

CREATE INDEX idx_product_brand ON product(brand);

CREATE INDEX idx_product_model ON product(model);

CREATE INDEX idx_retail_status_brand_model ON retail_task_status(region, brand, model, captured_at);

CREATE INDEX idx_retail_status_task_site ON retail_task_status(region, task, site_code, status);

CREATE INDEX idx_review_product ON review(product_id);

CREATE INDEX idx_sp_brand_week
    ON selling_point(brand, captured_week);

CREATE INDEX idx_sp_series
    ON selling_point(series_id, captured_week);

CREATE INDEX idx_sp_status_brand_week
    ON selling_point_status(brand, captured_week, status);

CREATE INDEX idx_spec_entry_audit_brand_time
    ON spec_entry_audit(brand, captured_at);

CREATE INDEX idx_spec_row_series ON spec_row(series_id, captured_week);

CREATE INDEX idx_spec_status_brand_week
    ON spec_series_status(brand, captured_week, status);

CREATE INDEX idx_spec_status_series_time
    ON spec_series_status(brand, series, finished_at);

CREATE INDEX idx_summary_product_time
    ON review_summary(product_id, captured_at);