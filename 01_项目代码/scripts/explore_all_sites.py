# -*- coding: utf-8 -*-
"""【全站探索】对每个可达零售站，自动发现 TV 商品目录与搜索入口。

策略（每站多通道，任一命中即录）：
  1. 平台专用：
     - VTEX: 目录 Catalog API（api/catalog_system/pub/products/search/xxx）
     - Shopify: /products.json 或 <coll>/products.json
     - MercadoLibre: api search
     - Magento: /catalogsearch/result/?q=<品牌> + 分类页路径试探
  2. HTML 兜底：从首页找搜索表单 action；用电视关键词（televisor/tv）搜；
     解析 a[href* /p/ ]、a[href* .html] 商品卡片。
  3. JSON-LD：页面含 Product/ItemList → 直接解商品名+价格。

每站 output：data/explore/<site>.json  {site, platform, base, method, items:[{title,url,price?,model?}]}
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

import requests
import urllib3

urllib3.disable_warnings()
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

PROXY = {"http": "http://127.0.0.1:7877", "https": "http://127.0.0.1:7877"}
HDR = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/json",
}

# 全部南美价格+网评站点: site -> (host, platform_hint, region)
SITES = {
    # 秘鲁
    "hiraoka_pe": ("hiraoka.com.pe", "magento", "pe"),
    "lacuracao_pe": ("www.lacuracao.pe", "magento", "pe"),
    "efe_pe": ("www.efe.com.pe", "magento", "pe"),
    "sodimac_pe": ("www.sodimac.com.pe", "magento", "pe"),
    "falabella_pe": ("www.falabella.com.pe", "magento", "pe"),
    "ripley_pe": ("simple.ripley.com.pe", "other", "pe"),
    "tottus_pe": ("www.tottus.com.pe", "other", "pe"),
    "oechsle_pe": ("www.oechsle.pe", "vtex", "pe"),
    "plazavea_pe": ("www.plazavea.com.pe", "vtex", "pe"),
    "estilos_pe": ("www.estilos.com.pe", "vtex", "pe"),
    "metro_pe": ("www.metro.pe", "vtex", "pe"),
    "carsa_pe": ("www.carsa.pe", "vtex", "pe"),
    "credivargas_pe": ("www.credivargas.pe", "vtex", "pe"),
    "mercadolibre_pe": ("www.mercadolibre.com.pe", "mercadolibre", "pe"),
    # 厄瓜多尔
    "cresa_ec": ("www.crescos.com", "other", "ec"),
    "japon_ec": ("www.almacenesjapon.com", "vtex", "ec"),
    "orvehogar_ec": ("www.orvehogar.com", "vtex", "ec"),
    "artefacta_ec": ("www.artefacta.com", "magento", "ec"),
    "marcimex_ec": ("www.marcimex.com", "vtex", "ec"),
    "laganga_ec": ("laganga.com", "other", "ec"),
    "comandato_ec": ("www.comandato.com", "vtex", "ec"),
    "jaher_ec": ("www.jaher.com.ec", "other", "ec"),
    "espana_ec": ("almacenesespana.ec", "magento", "ec"),
    "megamaxi_ec": ("www.megamaxi.com", "woo", "ec"),
    "sukasa_ec": ("www.sukasa.com", "other", "ec"),
    "todohogar_ec": ("www.todohogar.com", "other", "ec"),
    "coral_ec": ("coralhipermercados.com", "magento", "ec"),
    "ferrisariato_ec": ("www.ferrisariato.com", "other", "ec"),
    # 哥伦比亚
    "alkosto_co": ("www.alkosto.com", "other", "co"),
    "exito_co": ("www.exito.com", "vtex", "co"),
    "falabella_co": ("www.falabella.com.co", "magento", "co"),
    "jumbo_co": ("www.jumbocolombia.com", "vtex", "co"),
    "olimpica_co": ("www.olimpica.com.co", "other", "co"),
    # 智利
    "falabella_cl": ("www.falabella.com", "magento", "cl"),
    "paris_cl": ("www.paris.cl", "other", "cl"),
    "ripley_cl": ("simple.ripley.cl", "other", "cl"),
    "mercadolibre_cl": ("www.mercadolibre.cl", "mercadolibre", "cl"),
    "lider_cl": ("www.lider.cl", "other", "cl"),
    "abc_cl": ("www.abc.cl", "other", "cl"),
    "hites_cl": ("www.hites.com", "other", "cl"),
    # 玻利维亚
    "multicenter_bo": ("www.multicenter.com", "vtex", "bo"),
    "dismac_bo": ("www.dismac.com.bo", "other", "bo"),
    "multicenterplus_bo": ("alkostoplus.com", "other", "bo"),
    # 巴拿马 / 危地马拉
    "panafoto_pa": ("panafoto.com", "magento", "pa"),
    "evision_pa": ("www.evisionstore.com", "magento", "pa"),
    "multimax_pa": ("www.multimax.net", "shopify", "pa"),
    "rodelag_pa": ("rodelag.com", "shopify", "pa"),
    "raenco_pa": ("www.raenco.com", "magento", "pa"),
    "max_gt": ("www.max.com.gt", "shopify", "gt"),
    "tecnofacil_gt": ("www.tecnofacil.com.gt", "other", "gt"),
    "unicomer_gt": ("www.lacuracaonline.com", "magento", "gt"),
    "elektra_gt": ("www.elektra.com.gt", "vtex", "gt"),
}

OUT_DIR = "data/explore"
os.makedirs(OUT_DIR, exist_ok=True)


def _get(url: str, accept_json: bool = False, timeout: int = 18):
    h = dict(HDR)
    if accept_json:
        h["Accept"] = "application/json"
    try:
        return requests.get(url, proxies=PROXY, headers=h, timeout=timeout,
                            verify=False, allow_redirects=True)
    except requests.RequestException:
        return None


def pick_model(title: str) -> str:
    """从标题提取疑似型号短码（最后一个 数字[字母] 组）。"""
    m = re.findall(r"\b(\d{1,3}[A-Z][A-Z0-9]{1,9})\b", title.upper())
    return m[-1] if m else ""


def catalog_vtex(host: str) -> list[dict]:
    items = []
    for cat in ("televisores", "televisores/smart-tv",
                "televisores/4k", "tv", "tecnologia/televisores"):
        for start in range(0, 40, 10):
            url = (f"https://{host}/api/catalog_system/pub/products/search/{cat}"
                   f"?_from={start}&_to={start + 9}")
            r = _get(url, accept_json=True)
            if r is None or r.status_code not in (200, 206):
                break
            try:
                data = r.json()
            except Exception:
                break
            if not isinstance(data, list) or not data:
                break
            for it in data:
                nm = it.get("productName") or ""
                if "televisor" not in nm.lower() and not nm.lower().startswith("tv"):
                    continue
                sellers = ((it.get("items") or [{}])[0].get("sellers") or [{}])[0]
                off = sellers.get("commertialOffer") or {}
                items.append({"title": nm, "url": it.get("link") or "",
                              "price": off.get("Price"), "model": pick_model(nm)})
            if len(data) < 10:
                break
        if items:
            break
    return items


def _catalog_shopify(host: str) -> list[dict]:
    items = []
    for url in (f"https://{host}/products.json?limit=250",
                f"https://{host}/collections/all/products.json?limit=250"):
        r = _get(url, accept_json=True)
        if r is None or r.status_code != 200:
            continue
        try:
            data = r.json()
            for p in data.get("products", []):
                t = p.get("title") or ""
                if "televisor" in t.lower() or t.lower().startswith("tv"):
                    variants = p.get("variants") or [{}]
                    items.append({"title": t, "url": f"https://{host}/products/{p.get('handle')}",
                                  "price": variants and variants[0].get("price"),
                                  "model": pick_model(t)})
        except Exception:
            continue
    return items


def _catalog_mercadolibre(site_id: str) -> list[dict]:
    items = []
    for q in ("televisor", "smart tv", "tv"):
        url = f"https://api.mercadolibre.com/sites/{site_id}/search?q={q}&limit=50"
        r = _get(url, accept_json=True)
        if r is None or r.status_code != 200:
            continue
        try:
            for it in r.json().get("results", []):
                t = it.get("title") or ""
                if "tvc" in t.lower() or "tv" in t.lower():
                    items.append({"title": t, "url": it.get("permalink") or "",
                                  "price": it.get("price"), "model": pick_model(t)})
        except Exception:
            pass
        if items:
            break
    return items


def _catalog_magento(host: str) -> list[dict]:
    items = []
    for q in ("televisor", "smart", "google tv"):
        url = f"https://{host}/catalogsearch/result/?q={q}"
        r = _get(url)
        if r is None or r.status_code != 200:
            continue
        html = r.text or ""
        # 搜索卡片
        found = re.findall(
            r'<a[^>]*(?:class="[^"]*product-item-link[^"]*"|href="[^"]*/[^"]+")[^>]*>\s*([^<]{6,180})<',
            html, re.I)
        seen = set()
        for t in found[:60]:
            t = re.sub(r"\s+", " ", t).strip()
            if t and t not in seen and ("tv" in t.lower() or "televis" in t.lower()):
                seen.add(t)
                items.append({"title": t, "url": "", "price": "",
                              "model": pick_model(t)})
        if items:
            break
    # 若搜索卡片 0，试分类页
    if not items:
        for p in ("/televisores", "/televisores.html", "/tv", "/televisiones"):
            r = _get(f"https://{host}{p}")
            if r is None or r.status_code != 200:
                continue
            html = r.text or ""
            found = re.findall(
                r'<a[^>]+class="[^"]*product-item-link[^"]*"[^>]*>\s*([^<]{6,180})<',
                html, re.I)
            for t in found[:60]:
                t = re.sub(r"\s+", " ", t).strip()
                if t:
                    items.append({"title": t, "url": "", "price": "", "model": pick_model(t)})
            if items:
                break
    return items


def _catalog_html(host: str, search_paths: tuple = ("/search?q=", "/buscar?q=",
                                                    "/busqueda?q=", "/catalogsearch/result/?q=",
                                                    "/resultado?q=", "/?s=")) -> list[dict]:
    """HTML 兜底：搜索关键词 / 商品卡链接。"""
    items = []
    for q in ("televisor", "smart+tv", "tv"):
        for sp in search_paths:
            url = f"https://{host}{sp}{q}"
            r = _get(url)
            if r is None:
                continue
            html = r.text or ""
            low = html.lower()
            if r.status_code == 200 and len(html) > 2000 and "404" not in low[:600]:
                # 商品卡标题（多形态）
                titles = re.findall(
                    r'class=["\'](?:product-title|product-name|card-title|product-item-link|'
                    r'product-card-title|search-result-title)["\'][^>]*>\s*([^<]{6,180})<',
                    html, re.I)
                if not titles:
                    titles = re.findall(
                        r'<a[^>]+href=["\'][^"\']*(?:/p/|/product|/prod-|/item/|\.html|'
                        r'/producto/)[^"\']*["\'][^>]*>\s*([^<]{6,180})<',
                        html, re.I)
                seen = set()
                for t in titles[:80]:
                    t = re.sub(r"\s+", " ", t).strip()
                    if t and t not in seen:
                        seen.add(t)
                        items.append({"title": t, "url": "", "price": "",
                                      "model": pick_model(t)})
                if items:
                    return items
    # 兜底：首页找所有商品 href
    r = _get(f"https://{host}/")
    if r is not None and r.status_code == 200:
        html = r.text or ""
        seen = set()
        for m in re.finditer(r'href=["\']([^"\']*(?:/p/|/product/|/producto/|\.html)[^"\']*)["\']', html, re.I):
            h = m.group(1)
            if h in seen:
                continue
            seen.add(h)
            if "login" in h.lower() or "cart" in h.lower():
                continue
            items.append({"title": h, "url": h, "price": "", "model": ""})
            if len(seen) >= 40:
                break
    return items


def explore(site: str, host: str, platform: str) -> dict:
    res = {"site": site, "host": host, "platform": platform, "method": "",
           "items": [], "http": 0, "error": ""}
    if platform == "vtex":
        items = catalog_vtex(host)
        res["method"] = "vtex_api"
    elif platform == "shopify":
        items = _catalog_shopify(host)
        res["method"] = "shopify_json"
    elif platform == "mercadolibre":
        items = _catalog_mercadolibre("MPE" if "pe" in site else "MLC")
        res["method"] = "mercadolibre_api"
    else:
        items = _catalog_html(host)
        res["method"] = "html"
    res["items"] = items
    # http 探测
    r = _get(f"https://{host}/")
    res["http"] = getattr(r, "status_code", 0) if r else 0
    return res


def main() -> None:
    agg = []
    for site, (host, platform, region) in SITES.items():
        print(f"=== {site} ({host}, {platform}) ===")
        res = explore(site, host, platform)
        n = len(res["items"])
        print(f"  方法={res['method']} 在售TV/商品={n} 首页=http={res['http']}")
        for it in res["items"][:3]:
            print(f"    {it.get('title','')[:60]} 价{it.get('price','')}")
        with open(os.path.join(OUT_DIR, f"{site}.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        agg.append({"site": site, "host": host, "platform": platform,
                    "region": region, "method": res["method"],
                    "items": len(res["items"]), "http": res["http"]})
    with open(os.path.join(OUT_DIR, "_summary.json"), "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, indent=1)
    print("\n[OUT] data/explore/_summary.json")
    for a in agg:
        print(f"  {a['site']:<20} {a['platform']:<10} items={a['items']:<4} http={a['http']}")


if __name__ == "__main__":
    main()