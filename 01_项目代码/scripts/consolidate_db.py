# -*- coding: utf-8 -*-
"""把散落在各处的爬取库合并进唯一指定库 data/overseas.db（config.DB_PATH）。

只增不改：已存在的行不覆盖，只补空字段（product 的 brand/model/size/title/url）。
去重键：
  site(code) / product(site.code, sku) / price_snapshot(product, captured_at, price)
  review(product, review_key) / review_summary(product, captured_at)
  product_spec(product, key) / price_shop_snapshot(product, shop, captured_at)
  spec_series(brand, series) / spec_row(series, item_ja, category, captured_week)
  media_review(article_url)
不合并运行日志（crawl_run / crawl_error / *_task_status）：它们引用各库自己的 run_id。
各源库列不一致时取列交集。

用法：
  py -3.12 scripts/consolidate_db.py --dry-run      # 只统计每个源能补多少行
  py -3.12 scripts/consolidate_db.py                # 先备份目标库再合并
  py -3.12 scripts/consolidate_db.py --src a.db b.db
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")
TARGET = "data/overseas.db"


def default_sources() -> list[str]:
    s = ["data/na/overseas_na.db", "data/sa/overseas_sa.db", "data/eu/overseas_eu.db",
         "data/japan/overseas_japan.db", "data/asia/overseas_asia.db",
         "data/sandbox/readiness.db",
         "../海外/overseas_v4_20260929.db", "../海外/data/overseas.db",
         "../海外/data/mx/overseas_mx.db"]
    s += sorted(glob.glob("data/national_db/*/*.db"))
    return [p for p in s if os.path.exists(p) and os.path.getsize(p) > 0]


# 与 2026-10-05 主库清洗同口径（scripts/clean_rebuild_delivery.py NON_TV + 英语配件词）：
# 旧库里还留着当时已删掉的配件/非电视/无型号无价行，合并时不能把它们带回来。
import re  # noqa: E402
NON_TV_RE = re.compile(
    r"soporte|rack\b|estante|mueble|control remoto|funda|barra de sonido|soundbar|sound bar|"
    r"parlante|bocina|aud[ií]fono|auricular|accesorio|aire acondicionado|refrigerador|lavadora|"
    r"microonda|licuadora|aspiradora|freidora|proyector|projector|tablet|celular|laptop|"
    r"garant[ií]a|warranty|seguro|cargador|adaptador|hdmi|wall ?mount|bracket|halterung|"
    r"wandhalterung|fernbedienung|remote control|screen protector|cable\b|kabel\b|headphone|"
    r"speaker|lautsprecher|subwoofer|monitor\b", re.I)


def is_junk(title: str, model: str, has_price: bool) -> bool:
    if title and NON_TV_RE.search(title):
        return True
    return not (model or "").strip() and not has_price


def cols(c, t):
    return [r[1] for r in c.execute(f"pragma table_info('{t}')")]


def has(c, t):
    return c.execute("select 1 from sqlite_master where type='table' and name=?", (t,)).fetchone()


def merge(tgt: sqlite3.Connection, src_path: str) -> dict:
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    st = {"site": 0, "product": 0, "product_fill": 0, "price": 0, "review": 0,
          "summary": 0, "spec": 0, "shop": 0, "series": 0, "spec_row": 0, "media": 0}
    if not has(src, "product"):
        return st
    # ---- site ----
    t_site = {code: i for i, code in tgt.execute("select id, code from site")}
    s_rows = {r[0]: r[1:] for r in src.execute(
        "select id, code, name, base_url, protection, created_at from site")}
    s_site_cache: dict = {}

    def site_id(ssid):
        """源 site_id → 目标 site_id；目标没有该站时才建（只为有商品的站建行）。"""
        if ssid in s_site_cache:
            return s_site_cache[ssid]
        r = s_rows.get(ssid)
        if r is None:
            return None
        code, name, base, prot, created = r
        if code not in t_site:
            cur = tgt.execute("insert into site(code,name,base_url,protection,created_at) "
                              "values(?,?,?,?,?)", (code, name or code, base, prot,
                                                     created or dt.datetime.now().isoformat()))
            t_site[code] = cur.lastrowid
            st["site"] += 1
        s_site_cache[ssid] = t_site[code]
        return t_site[code]
    # ---- product ----
    t_prod = {(sid, sku): pid for pid, sid, sku in tgt.execute("select id, site_id, sku from product")}
    pc = cols(src, "product")
    fill = [c for c in ("url", "title", "brand", "model", "category", "size") if c in pc]
    pmap = {}
    priced = ({r[0] for r in src.execute("select distinct product_id from price_snapshot where price > 0")}
              if has(src, "price_snapshot") else set())
    for row in src.execute(f"select id, site_id, sku, first_seen, last_seen, {', '.join(fill)} from product"):
        spid, ssid, sku, fs, ls, *vals = row
        code = (s_rows.get(ssid) or [None])[0]
        if code is None or not sku:
            continue
        d = dict(zip(fill, vals))
        if (t_site.get(code), sku) not in t_prod and is_junk(
                d.get("title") or "", d.get("model") or "", spid in priced):
            st["skip_junk"] = st.get("skip_junk", 0) + 1
            continue
        tsid = site_id(ssid)
        key = (tsid, sku)
        if key not in t_prod:
            cur = tgt.execute(
                f"insert into product(site_id, sku, first_seen, last_seen, {', '.join(fill)}) "
                f"values(?,?,?,?{',?' * len(fill)})", (tsid, sku, fs or ls, ls or fs, *vals))
            t_prod[key] = cur.lastrowid
            st["product"] += 1
        else:
            pid = t_prod[key]
            for c, v in zip(fill, vals):
                if v not in (None, ""):
                    n = tgt.execute(f"update product set {c}=? where id=? and ({c} is null or {c}='')",
                                    (v, pid)).rowcount
                    st["product_fill"] += n
            tgt.execute("update product set first_seen=min(first_seen, ?), last_seen=max(last_seen, ?) "
                        "where id=?", (fs or ls, ls or fs, pid))
        pmap[spid] = t_prod[key]
    # ---- 按 product 挂的子表 ----
    def child(table, key_cols, stat):
        if not has(src, table):
            return
        cc = [c for c in cols(src, table) if c != "id" and c in cols(tgt, table)]
        exist = set(tgt.execute(f"select {', '.join(key_cols)} from {table}"))
        med: dict = {}
        if table == "price_snapshot":
            # 目标库里该商品已有价的中位数：新价偏离 >3 倍视为旧库残留错价（缺价 > 错价）
            by: dict = {}
            for pid_, p_ in tgt.execute("select product_id, price from price_snapshot where price > 0"):
                by.setdefault(pid_, []).append(p_)
            med = {k: sorted(v)[len(v) // 2] for k, v in by.items()}
        ph = ",".join("?" * len(cc))
        ki = [cc.index(k) for k in key_cols]
        for row in src.execute(f"select {', '.join(cc)} from {table}"):
            row = list(row)
            pid = pmap.get(row[cc.index("product_id")])
            if pid is None:
                continue
            row[cc.index("product_id")] = pid
            if tuple(row[i] for i in ki) in exist:
                continue
            if table == "price_snapshot":
                p = row[cc.index("price")]
                if p is None or p <= 0 or p > 1e7:      # 清洗口径：剔 0 价/坏值
                    continue
                m = med.get(pid)
                if m and (p > 3 * m or p < m / 3):
                    st["skip_outlier"] = st.get("skip_outlier", 0) + 1
                    continue
            k = tuple(row[i] for i in ki)
            if k in exist:
                continue
            tgt.execute(f"insert or ignore into {table}({', '.join(cc)}) values({ph})", row)
            exist.add(k)
            st[stat] += 1
    child("price_snapshot", ["product_id", "captured_at", "price"], "price")
    child("review", ["product_id", "review_key"], "review")
    child("review_summary", ["product_id", "captured_at"], "summary")
    child("product_spec", ["product_id", "key"], "spec")
    child("price_shop_snapshot", ["product_id", "shop", "captured_at"], "shop")
    # ---- SPEC 线：spec_series / spec_row ----
    if has(src, "spec_series") and has(src, "spec_row"):
        t_ser = {(b, s): i for i, b, s in tgt.execute("select id, brand, series from spec_series")}
        smap = {}
        for sid, b, bn, s, url, models, fs, ls in src.execute(
                "select id, brand, brand_name, series, url, models, first_seen, last_seen from spec_series"):
            if (b, s) not in t_ser:
                cur = tgt.execute("insert into spec_series(brand,brand_name,series,url,models,first_seen,last_seen) "
                                  "values(?,?,?,?,?,?,?)", (b, bn, s, url, models, fs, ls))
                t_ser[(b, s)] = cur.lastrowid
                st["series"] += 1
            smap[sid] = t_ser[(b, s)]
        rc = [c for c in cols(src, "spec_row") if c != "id" and c in cols(tgt, "spec_row")]
        for row in src.execute(f"select {', '.join(rc)} from spec_row"):
            row = list(row)
            nid = smap.get(row[rc.index("series_id")])
            if nid is None:
                continue
            row[rc.index("series_id")] = nid
            st["spec_row"] += tgt.execute(
                f"insert or ignore into spec_row({', '.join(rc)}) values({','.join('?' * len(rc))})",
                row).rowcount
    # ---- 媒体评测 ----
    if has(src, "media_review") and has(tgt, "media_review"):
        mc = [c for c in cols(src, "media_review") if c != "id" and c in cols(tgt, "media_review")]
        for row in src.execute(f"select {', '.join(mc)} from media_review"):
            st["media"] += tgt.execute(
                f"insert or ignore into media_review({', '.join(mc)}) values({','.join('?' * len(mc))})",
                row).rowcount
    src.close()
    return st


def counts(c):
    return {t: c.execute(f"select count(*) from {t}").fetchone()[0]
            for t in ("site", "product", "price_snapshot", "review", "review_summary",
                      "product_spec", "spec_series", "spec_row", "media_review")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", nargs="*")
    ap.add_argument("--target", default=TARGET)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sources = [p for p in (a.src or default_sources())
               if os.path.abspath(p) != os.path.abspath(a.target)]
    if not a.dry_run:
        bak = a.target.replace(".db", f"_before_consolidate_{dt.datetime.now():%Y%m%d_%H%M%S}.bak")
        shutil.copy2(a.target, bak)
        print("备份 →", bak)
    tgt = sqlite3.connect(a.target, timeout=60)
    tgt.execute("pragma busy_timeout=60000")
    before = counts(tgt)
    print("合并前:", before)
    for p in sources:
        try:
            st = merge(tgt, p)
        except Exception as e:
            tgt.rollback()
            print(f"  ✗ {p}: {type(e).__name__}: {e}")
            continue
        if a.dry_run:
            tgt.rollback()
        else:
            tgt.commit()
        nz = {k: v for k, v in st.items() if v}
        print(f"  {'(dry) ' if a.dry_run else ''}{p}: {nz or '无新增'}")
    after = counts(tgt)
    print("合并后:", after)
    print("净增:", {k: after[k] - before[k] for k in after})
    tgt.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
