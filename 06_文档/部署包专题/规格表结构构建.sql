-- ============================================================
-- 规格表结构构建 — 三张目标表 DDL + 初始化数据
-- 基于 data/overseas.db 中 spec_row(175,655行) + product_spec(137,114行) 数据分析
-- ============================================================

-- ============================================================
-- 表 9：dim_spec_parameter（规格参数字典表）
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_spec_parameter (
    param_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    param_code       VARCHAR(30)  NOT NULL UNIQUE,
    param_name       VARCHAR(50)  NOT NULL,
    param_unit       VARCHAR(20),
    is_numeric       TINYINT      NOT NULL DEFAULT 1,
    higher_is_better TINYINT,
    category         VARCHAR(20)  NOT NULL,
    sort_order       INTEGER      NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_spec_param_category ON dim_spec_parameter(category);

-- 初始化18个参数（8核心 + 10扩展）
INSERT INTO dim_spec_parameter
    (param_id, param_code, param_name, param_unit, is_numeric, higher_is_better, category, sort_order)
VALUES
    -- 8个核心参数（按文档要求）
    (1,  'PEAK_BRIGHTNESS',  '峰值亮度',    'nits',   1, 1,    '画质', 1),
    (2,  'DIMMING_ZONES',   '分区控光',    'zones',  1, 1,    '画质', 2),
    (3,  'REFRESH_RATE',    '刷新率',      'Hz',     1, 1,    '画质', 3),
    (4,  'CHIP',            '画质芯片',    NULL,     0, NULL,  '画质', 4),
    (5,  'SYSTEM',          '智能系统',    NULL,     0, NULL,  '智能', 5),
    (6,  'GAMING',          '游戏特性',    NULL,     0, 1,    '游戏', 6),
    (7,  'COLOR_GAMUT',     '色域',        '%',      1, 1,    '画质', 7),
    (8,  'HDMI',            'HDMI 2.1',   '口',      0, 1,    '连接', 8),
    -- 10个扩展参数（从源数据高频项补充）
    (9,  'SCREEN_SIZE',        '屏幕尺寸',  'inch',   1, 0,    '设计', 9),
    (10, 'RESOLUTION',         '分辨率',    NULL,     0, 1,    '画质', 10),
    (11, 'HDR',                'HDR格式',   NULL,     0, 1,    '画质', 11),
    (12, 'CONTRAST',           '对比度',    ':1',     1, 1,    '画质', 12),
    (13, 'WIFI',               'Wi-Fi',     NULL,     0, 1,    '连接', 13),
    (14, 'BLUETOOTH',          '蓝牙',      NULL,     0, 1,    '连接', 14),
    (15, 'DOLBY_ATMOS',        '杜比全景声', NULL,     0, 1,    '画质', 15),
    (16, 'POWER_CONSUMPTION',  '功耗',      'kWh/年',  1, 0,    '设计', 16),
    (17, 'WEIGHT',             '重量',      'kg',     1, 0,    '设计', 17),
    (18, 'DIMENSIONS',         '尺寸',      'mm',     0, 0,    '设计', 18);


-- ============================================================
-- 表 22：dim_spec_normalization_map（SPEC归一化映射表）
-- ============================================================
CREATE TABLE IF NOT EXISTS dim_spec_normalization_map (
    map_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    hisense_term        VARCHAR(100) NOT NULL,
    competitor_terms    TEXT         NOT NULL,
    param_id            INTEGER,
    normalized_category VARCHAR(50)  NOT NULL,
    status              VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
    confirmed_by        INTEGER,
    confirmed_at        DATETIME,
    created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note                VARCHAR(200),
    FOREIGN KEY (param_id) REFERENCES dim_spec_parameter(param_id)
);
CREATE INDEX IF NOT EXISTS idx_norm_map_hisense ON dim_spec_normalization_map(hisense_term);
CREATE INDEX IF NOT EXISTS idx_norm_map_param   ON dim_spec_normalization_map(param_id);
CREATE INDEX IF NOT EXISTS idx_norm_map_status  ON dim_spec_normalization_map(status);

-- 初始化9组归一化映射（从跨品牌术语差异分析结果）
INSERT INTO dim_spec_normalization_map
    (map_id, hisense_term, competitor_terms, param_id, normalized_category, status, created_at)
VALUES
    (1, '144Hz高刷',
     '["Refresh Rate(Samsung)","Motion Xcelerator(LG)","PANEL REFRESH RATE(TCL)","Hz(Panasonic)"]',
     3, '高刷族', 'PENDING', CURRENT_TIMESTAMP),

    (2, 'Mini-LED分区控光',
     '["Dimming Zones(Samsung)","Local Dimming(LG)","XR Backlight Master Drive(Sony)","Mini-LED/Local Dimming Type(TCL)"]',
     2, '分区控光族', 'PENDING', CURRENT_TIMESTAMP),

    (3, 'QLED量子点',
     '["QD(TCL)","Quantum Dot(Samsung)","Quantum Matrix(Samsung)","NanoCell(LG)","TRILUMINOS(Sony)"]',
     7, '量子点族', 'PENDING', CURRENT_TIMESTAMP),

    (4, '信芯AI画质芯片',
     '["AI Picture(Samsung)","α AI Processor(LG)","XR Processor(Sony)","AIPQ Processor(TCL)","Neural Quantum(Samsung)"]',
     4, '画质芯片族', 'PENDING', CURRENT_TIMESTAMP),

    (5, 'VIDAA',
     '["Tizen(Samsung)","webOS(LG)","Google TV(Sony)","Google TV(TCL)","My Home Screen(Panasonic)","Android TV(Sony)","Roku(Hisense US)","Fire TV(Amazon)"]',
     5, '智能系统族', 'PENDING', CURRENT_TIMESTAMP),

    (6, '峰值亮度',
     '["Peak Brightness(nits)(Samsung)","Brightness Booster(LG)","HDR Brightness Optimizer(Sony)","Display Brightness(Hisense)","Brightness(Hisense)"]',
     1, '亮度族', 'PENDING', CURRENT_TIMESTAMP),

    (7, 'HDMI 2.1',
     '["HDMI 2.1(Samsung)","eARC(LG)","HDMI2.1仕様(Sony)","HDMI 2.1(TCL)","ARC(Panasonic)","HDMI®2.1規格対応機能(Sony)"]',
     8, 'HDMI族', 'PENDING', CURRENT_TIMESTAMP),

    (8, 'HDR',
     '["HDR10+(Samsung)","HDR(High Dynamic Range)(Samsung)","Dolby Vision(LG)","HLG(Sony)","HDR10/HLG対応(Panasonic)","HDR10(Hisense)"]',
     11, 'HDR族', 'PENDING', CURRENT_TIMESTAMP),

    (9, '游戏模式',
     '["Gaming Hub(Samsung)","Game Optimizer(LG)","Game Mode(Sony)","144Hz Game Mode Pro(TCL)","Game Motion Plus(Samsung)","Auto Game Mode(ALLM)(Samsung)","VRR(Samsung)","FreeSync(Samsung)","G-SYNC(Samsung)"]',
     6, '游戏族', 'PENDING', CURRENT_TIMESTAMP);


-- ============================================================
-- 表 23：fact_benchmark_comparison（竞品对阵对比表）
-- ============================================================
CREATE TABLE IF NOT EXISTS fact_benchmark_comparison (
    comparison_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    comparison_name         VARCHAR(100) NOT NULL,
    size_inch               INTEGER      NOT NULL,
    price_band              VARCHAR(30)  NOT NULL,
    our_model_id            INTEGER      NOT NULL,
    competitor_model_ids    TEXT         NOT NULL,
    advantage_points        TEXT,
    disadvantage_points     TEXT,
    opportunity_points      TEXT,
    advantage_confidence    DECIMAL(5,2),
    disadvantage_confidence DECIMAL(5,2),
    opportunity_confidence  DECIMAL(5,2),
    strategy_suggestion     TEXT,
    created_by              INTEGER,
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    snapshot_date           DATE         NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_benchmark_size    ON fact_benchmark_comparison(size_inch);
CREATE INDEX IF NOT EXISTS idx_benchmark_band    ON fact_benchmark_comparison(price_band);
CREATE INDEX IF NOT EXISTS idx_benchmark_our     ON fact_benchmark_comparison(our_model_id);
CREATE INDEX IF NOT EXISTS idx_benchmark_created ON fact_benchmark_comparison(created_at);
