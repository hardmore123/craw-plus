-- 海外电商采集：表结构
--
-- 设计要点：
-- 1) price_snapshot / review_summary / ranking_snapshot 是时序表，只增不改，
--    这样才能做价格曲线和口碑趋势；不要 UPDATE 覆盖历史。
-- 2) review 用站内 review_key 做唯一约束，支持增量抓取自动去重。
-- 3) product_spec 用 KV 表而非宽表：电视/冰箱/手机规格字段差异太大。
-- 4) SQL 尽量保持标准，便于后续整体迁移 PostgreSQL。

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS site (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,          -- amazon_ca
    name        TEXT NOT NULL,
    base_url    TEXT,
    protection  TEXT,                          -- L1 / L2 / L3
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id     INTEGER NOT NULL REFERENCES site(id),
    sku         TEXT NOT NULL,                 -- ASIN / 站内商品号
    url         TEXT,
    title       TEXT,
    brand       TEXT,
    model       TEXT,                          -- 厂商型号，跨站比价用
    category    TEXT,
    size        TEXT,                          -- 尺寸（导出表「尺寸」列）
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    UNIQUE (site_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_product_model ON product(model);
CREATE INDEX IF NOT EXISTS idx_product_brand ON product(brand);

CREATE TABLE IF NOT EXISTS product_spec (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    key         TEXT NOT NULL,
    value       TEXT,
    captured_at TEXT NOT NULL,
    UNIQUE (product_id, key)
);

-- ★ 时序：价格快照
CREATE TABLE IF NOT EXISTS price_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    price       REAL,
    list_price  REAL,
    currency    TEXT,
    in_stock    INTEGER,                       -- 1/0/NULL
    raw_text    TEXT,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_product_time
    ON price_snapshot(product_id, captured_at);

CREATE TABLE IF NOT EXISTS review (
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
    review_url    TEXT,                        -- 评论链接
    image_urls    TEXT,                        -- 图片地址，多张用 " | " 连接
    image_count   INTEGER DEFAULT 0,
    video_urls    TEXT,                        -- 视频地址，多个用 " | " 连接
    has_video     INTEGER DEFAULT 0,           -- 1/0
    captured_at   TEXT NOT NULL,
    UNIQUE (product_id, review_key)
);
CREATE INDEX IF NOT EXISTS idx_review_product ON review(product_id);

-- ★ 时序：评分聚合快照
CREATE TABLE IF NOT EXISTS review_summary (
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
CREATE INDEX IF NOT EXISTS idx_summary_product_time
    ON review_summary(product_id, captured_at);

-- ★ 时序：榜单排名快照
CREATE TABLE IF NOT EXISTS ranking_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    list_name   TEXT NOT NULL,
    rank        INTEGER,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawl_run (
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

CREATE TABLE IF NOT EXISTS crawl_error (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER REFERENCES crawl_run(id),
    url         TEXT,
    stage       TEXT,                          -- search/detail/reviews
    kind        TEXT,                          -- blocked/timeout/http/parse
    message     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_error_run ON crawl_error(run_id);

-- 原始 HTML 只存路径与哈希，正文落文件，避免撑爆数据库
CREATE TABLE IF NOT EXISTS raw_page (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER,
    url         TEXT NOT NULL,
    sha1        TEXT NOT NULL,
    path        TEXT NOT NULL,
    status      INTEGER,
    created_at  TEXT NOT NULL
);


-- ==================== SPEC 采集（日本站规格表）====================
-- 组织：品牌 → 系列 → 机型 / SPEC 行。SPEC 刷新频次为周度，
-- 用 captured_week（ISO 年-周，如 2026-W36）区分快照，便于周度对比与去重。

CREATE TABLE IF NOT EXISTS spec_series (
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

-- SPEC 行：一行 = 一个系列的一个 SPEC 项在某周的一份快照
CREATE TABLE IF NOT EXISTS spec_row (
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
CREATE INDEX IF NOT EXISTS idx_spec_row_series ON spec_row(series_id, captured_week);

-- 记录词典未命中的日文项目，便于人工补词典
CREATE TABLE IF NOT EXISTS spec_untranslated (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_ja      TEXT NOT NULL UNIQUE,
    brand        TEXT,
    seen_count   INTEGER DEFAULT 1,
    last_seen    TEXT NOT NULL
);


-- SPEC 系列级最终状态：每次运行对每个目标系列保留一条结果
-- status 只允许 success / empty / failed；空/失败系列没有 spec_series 也必须能被导出
CREATE TABLE IF NOT EXISTS spec_series_status (
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
CREATE INDEX IF NOT EXISTS idx_spec_status_brand_week
    ON spec_series_status(brand, captured_week, status);
CREATE INDEX IF NOT EXISTS idx_spec_status_series_time
    ON spec_series_status(brand, series, finished_at);


-- ============================================================
-- 店铺维度价格快照（kakaku 等「一个商品多家店铺各自报价」的站点）
-- price_snapshot 记录"该商品的最低价/整体价"；本表记录"每家店铺各自的价"。
-- 同为★时序表：只 INSERT 不 UPDATE，便于算单店价格曲线与店间价差。
-- ============================================================
CREATE TABLE IF NOT EXISTS price_shop_snapshot (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    shop        TEXT NOT NULL,                 -- 店铺名，如 ヨドバシ.com
    price       REAL,                          -- 该店铺售价
    currency    TEXT,                          -- 货币，如 JPY
    is_lowest   INTEGER DEFAULT 0,             -- 1=本次采集中该店为最安店铺
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_shop_product_time
    ON price_shop_snapshot(product_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_price_shop_shop
    ON price_shop_snapshot(shop, captured_at);

-- ============================================================
-- kakaku 价格线/评论线的型号级采集状态（与 SPEC 的 spec_series_status 对应）
-- 目的：ok/no_item/not_target_year/no_reviews/no_price/blocked/failed 不再只打印，
-- 前端可展示"哪些型号没抓到、为什么"。
-- task ∈ {price, review, release}
-- ============================================================
CREATE TABLE IF NOT EXISTS kakaku_task_status (
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
CREATE INDEX IF NOT EXISTS idx_kakaku_status_task_brand
    ON kakaku_task_status(task, brand, status);
CREATE INDEX IF NOT EXISTS idx_kakaku_status_model_time
    ON kakaku_task_status(brand, model, captured_at);

-- ============================================================
-- 讨论主题增量状态（7.2）：记录每个クチコミ主题最后一次抓到的帖号/帖数，
-- 下次运行时若主题帖数与最后帖号都没变，就跳过进入该主题页，减少导航。
-- 仅用于加速，不作为数据正确性来源；解析不到比较字段时调用方回退为「进入主题」。
-- ============================================================
CREATE TABLE IF NOT EXISTS kakaku_thread_state (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        TEXT NOT NULL,               -- kakaku 商品号 K000xxxx
    thread_url     TEXT NOT NULL,               -- 讨论主题绝对 URL（含 SortID）
    thread_title   TEXT,
    last_post_key  TEXT,                         -- 该主题最后一条書込番号
    post_count     INTEGER NOT NULL DEFAULT 0,   -- 该主题上次抓到的帖数
    last_seen      TEXT NOT NULL,
    UNIQUE (item_id, thread_url)
);
CREATE INDEX IF NOT EXISTS idx_kakaku_thread_item
    ON kakaku_thread_state(item_id);


-- ============================================================
-- 通用零售站价格/评价型号级采集状态（加拿大等多零售站线路）
-- 与 kakaku_task_status 隔离：一个型号×零售站同时产生 price/review 两条状态。
-- task ∈ {price, review}
-- ============================================================
CREATE TABLE IF NOT EXISTS retail_task_status (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    region        TEXT NOT NULL,               -- ca / us / mx
    task          TEXT NOT NULL CHECK (task IN ('price', 'review')),
    site_code     TEXT NOT NULL,               -- amazon_ca / bestbuy_ca ...
    site_name     TEXT,
    brand         TEXT NOT NULL,               -- hisense_ca ...
    brand_name    TEXT,
    model         TEXT NOT NULL,
    item_id       TEXT,
    product_id    INTEGER REFERENCES product(id) ON DELETE SET NULL,
    status        TEXT NOT NULL,               -- ok/no_item/no_price/no_reviews/summary_only/blocked/failed
    size          TEXT,
    price         REAL,
    currency      TEXT,
    row_count     INTEGER NOT NULL DEFAULT 0,
    new_count     INTEGER NOT NULL DEFAULT 0,
    message       TEXT,
    captured_at   TEXT NOT NULL,
    UNIQUE (run_id, task, region, site_code, brand, model)
);
CREATE INDEX IF NOT EXISTS idx_retail_status_task_site
    ON retail_task_status(region, task, site_code, status);
CREATE INDEX IF NOT EXISTS idx_retail_status_brand_model
    ON retail_task_status(region, brand, model, captured_at);


-- SPEC 入口页全量发现审计：与成功/失败的系列状态分离，避免把当前 DOM
-- 数量误标成官网全量；details_json 保存系列→型号→URL 发现清单和终止元数据。
CREATE TABLE IF NOT EXISTS spec_entry_audit (
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
CREATE INDEX IF NOT EXISTS idx_spec_entry_audit_brand_time
    ON spec_entry_audit(brand, captured_at);


-- ── 卖点采集（Selling Points）2026-09-28 新增 ★ 借鉴自 tvcraw-main ──
-- 与 spec_row 同按 ISO 周快照；LLM 精炼摘要独立字段（refined_text）
CREATE TABLE IF NOT EXISTS selling_point (
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
CREATE INDEX IF NOT EXISTS idx_sp_brand_week
    ON selling_point(brand, captured_week);
CREATE INDEX IF NOT EXISTS idx_sp_series
    ON selling_point(series_id, captured_week);

-- 卖点系列级采集状态（与 spec_series_status 对应）
CREATE TABLE IF NOT EXISTS selling_point_status (
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
CREATE INDEX IF NOT EXISTS idx_sp_status_brand_week
    ON selling_point_status(brand, captured_week, status);

-- ============================================================
-- 竞品情报（compintel）：FCC 认证 + EPREL 能效注册 + 上市预警信号
-- 与电视 spec/retail 业务解耦：独立表族，通过 crawl_run 关联审计。
-- 设计：FCC/EPREL 各一张"记录"表 + 一张"文档"表（FCC 文件 / EPREL PIS），
-- 加一张"预警信号"表。记录按 source+source_id 唯一，时序靠 captured_at 快照。
-- ============================================================

-- 竞品认证/注册记录：一行 = 一个 FCC ID 或一个 EPREL 注册号在某次抓取的一份快照。
-- source ∈ {fcc, eprel}; source_id = FCC ID 全串 或 EPREL 注册号。
-- 时序：每次抓取 INSERT 新行，便于追踪授权日期/能效等级变化。
CREATE TABLE IF NOT EXISTS compintel_record (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES crawl_run(id) ON DELETE SET NULL,
    source          TEXT NOT NULL CHECK (source IN
                    ('fcc','eprel','energystar','ul','tuv','ic_ised','anatel')),
    source_id       TEXT NOT NULL,            -- FCC ID / EPREL 注册号 / UL 文件号 / ANATEL 认证号
    product_group   TEXT,                     -- EPREL 产品类 / ENERGY STAR 品类 / FCC 设备类
    applicant       TEXT,                      -- 申请人/供应商(公司名)
    applicant_code  TEXT,                      -- FCC Grantee Code / UL 文件号前缀
    brand            TEXT,                     -- 品牌/商标
    model            TEXT,                     -- 型号标识
    description      TEXT,                      -- 产品描述
    auth_date       TEXT,                      -- 认证/授权/注册日期
    market_start    TEXT,                      -- 上市开始日
    market_end      TEXT,                      -- 上市结束日
    frequency       TEXT,                      -- FCC 频段
    energy_class    TEXT,                      -- EPREL/ENERGY STAR 能效等级
    extra_json      TEXT,                      -- 其余技术规格 JSON
    confidentiality TEXT,                      -- 保密标记
    captured_at     TEXT NOT NULL,
    UNIQUE (source, source_id, captured_at)    -- 同一记录每次抓取一行快照
);
CREATE INDEX IF NOT EXISTS idx_ci_record_source_applicant
    ON compintel_record(source, applicant);
CREATE INDEX IF NOT EXISTS idx_ci_record_source_id
    ON compintel_record(source, source_id);
CREATE INDEX IF NOT EXISTS idx_ci_record_brand_model
    ON compintel_record(brand, model);
CREATE INDEX IF NOT EXISTS idx_ci_record_auth_date
    ON compintel_record(source, auth_date);

-- 竞品文档/文件：FCC 的测试报告/内部照片、EPREL 的 PIS/标签 PDF。
CREATE TABLE IF NOT EXISTS compintel_doc (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_id       INTEGER NOT NULL REFERENCES compintel_record(id) ON DELETE CASCADE,
    doc_type        TEXT NOT NULL,            -- RF Exposure Info / Internal Photos / PIS / Label
    doc_name        TEXT,                      -- 文件名
    url             TEXT,                      -- 下载/查看 URL
    doc_date        TEXT,                      -- 文件日期
    captured_at     TEXT NOT NULL,
    UNIQUE (record_id, doc_type, doc_name)
);

-- 预警信号：一次抓取后分析产生的信号。每行一个信号。
-- signal_type 见 alert.py SIGNAL_TYPES；level ∈ {info, watch, alert, critical}
CREATE TABLE IF NOT EXISTS compintel_alert (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER REFERENCES crawl_run(id) ON DELETE SET NULL,
    signal_type     TEXT NOT NULL,            -- new_fcc_id / new_cert / confidential_expired / eprel_new_reg / energy_class_jump / eprel_delisted / supplier_change / field_change / launch_warning
    source          TEXT NOT NULL CHECK (source IN
                    ('fcc','eprel','energystar','ul','tuv','ic_ised','anatel')),
    applicant       TEXT,                      -- 涉及的竞品公司
    brand            TEXT,
    model            TEXT,
    source_id       TEXT,                      -- 关联的 FCC ID / EPREL 注册号 / 认证号
    level           TEXT NOT NULL DEFAULT 'watch',  -- info/watch/alert/critical
    message         TEXT NOT NULL,            -- 人读消息
    details_json    TEXT,                      -- 结构化补充
    detected_at     TEXT NOT NULL,
    UNIQUE (signal_type, source, source_id, detected_at)
);
CREATE INDEX IF NOT EXISTS idx_ci_alert_type
    ON compintel_alert(signal_type, detected_at);
CREATE INDEX IF NOT EXISTS idx_ci_alert_applicant
    ON compintel_alert(applicant, detected_at);

-- 竞品抓取进度状态：增量抓取的断点续抓依据。
-- 每个抓取单位(fcc 授权码 / eprel 扫描区间)一行，记录上次抓到哪、最新记录日期。
-- 下次抓取时：已知授权码只翻第1页，遇全已知ID的页即停（省去重复翻页）。
CREATE TABLE IF NOT EXISTS compintel_crawl_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,            -- fcc / eprel / energystar / ul / tuv / ic_ised / anatel
    state_key       TEXT NOT NULL,            -- fcc=授权码 / eprel=scan:from-to / 其他=品牌或搜索键
    last_crawled_at TEXT NOT NULL,            -- 上次抓取完成时间(UTC)
    last_record_date TEXT,                    -- 该单位最新一条记录的日期(用于早停判断)
    pages_crawled   INTEGER DEFAULT 0,         -- 本次抓了多少页
    records_seen    INTEGER DEFAULT 0,         -- 本次抓到多少条(含已知)
    records_new     INTEGER DEFAULT 0,         -- 本次新增多少条
    meta_json       TEXT,                      -- 额外信息(如 total_pages/品牌)
    UNIQUE (source, state_key)
);

-- 竞品抓取黑名单：跳过不再抓的记录。
-- 用于"完全跳过"已确认无价值的记录(如已下架很久的旧型号)，避免反复入库检查。
CREATE TABLE IF NOT EXISTS compintel_skip (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,            -- fcc / eprel / energystar / ul / tuv / ic_ised / anatel
    source_id       TEXT NOT NULL,            -- FCC ID / EPREL 注册号 / 认证号
    reason          TEXT,                      -- 跳过原因(如 "too_old" / "not_competitor")
    created_at      TEXT NOT NULL,
    UNIQUE (source, source_id)
);
