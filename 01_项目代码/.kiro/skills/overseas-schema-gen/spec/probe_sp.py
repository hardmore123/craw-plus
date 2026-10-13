#!/usr/bin/env python
"""spec-schema-gen 独立探测脚本（无项目依赖版）。

直接用 Playwright API 渲染页面 + 执行 JS，吐出智能体判断规格载体所需的全部结构信号。
不做判断、不写 schema——只给"眼睛"。

两种模式：
  --entry <入口列表页URL>   探入口页：发现产品链接选择器、URL 模式、分页/滚动信号。
  --model <型号规格页URL>   探型号页：渲染+滚动后在 DOM 上扫结构信号——有没有
                            table/dl、div/span 键值容器、tab 菜单、内嵌 JSON；dump
                            候选容器 outerHTML；点一下疑似 tab 看 DOM 是否变化。

依赖：
  pip install playwright
  playwright install chromium

用法：
  python probe.py --model "https://..." --out probe_model.json
  python probe.py --entry "https://.../tvs" --out probe_entry.json
  python probe.py --entry "https://.../tvs" --out probe_entry.json --deep

结果同时写 --out 文件（完整）并打印摘要到 stdout。
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# Windows 控制台默认 GBK，打印日文/中文规格词会 UnicodeEncodeError。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 多语言规格关键词（从同目录 spec_keywords.py 加载，注入到探测 JS）
import importlib.util as _ilu

_kw_spec = _ilu.spec_from_file_location(
    "spec_keywords", str(Path(__file__).resolve().parent / "spec_keywords.py")
)
_kw_mod = _ilu.module_from_spec(_kw_spec)
_kw_spec.loader.exec_module(_kw_mod)
_KW_JSON = json.dumps(_kw_mod.ALL_KEYWORDS, ensure_ascii=False)
_SP_KW_JSON = json.dumps(getattr(_kw_mod, "ALL_SP_KEYWORDS", []), ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
#  可达性预检（轻量、不启浏览器）
# ═══════════════════════════════════════════════════════════════

def check_reachable(url: str, timeout: int = 10) -> dict:
    """几秒内判断域名在当前网络环境是否可达，避免连不上的站白等浏览器 2-4 分钟。

    用纯 urllib 发一个轻量 GET（不渲染、不解析），只看网络层能不能通：
      - 能连上 + 有 HTTP 响应（哪怕 403 / JS 空壳）→ reachable=True，继续浏览器探测。
      - 连接超时 / DNS 失败 / 连接被拒 → reachable=False，秒退。
    """
    t0 = time.time()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (probe reachability check)",
            "Accept": "text/html,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return {
                "reachable": True,
                "status": resp.status,
                "reason": "ok",
                "elapsed": round(time.time() - t0, 1),
            }
    except urllib.error.HTTPError as e:
        # 有 HTTP 响应（403/404/5xx 等）= 网络可达，只是内容层面拒绝/需浏览器 → 继续
        return {
            "reachable": True,
            "status": e.code,
            "reason": f"http_{e.code}",
            "elapsed": round(time.time() - t0, 1),
        }
    except urllib.error.URLError as e:
        inner = getattr(e, "reason", None)
        inner_str = str(inner)
        is_ssl = isinstance(inner, ssl.SSLError) or "SSL" in inner_str.upper()
        is_timeout = "time" in inner_str.lower() and "out" in inner_str.lower()
        # SSL【证书】错误：TCP 连通、服务器有响应，只是证书不被信任 → 可达。
        # SSL【握手超时】：服务器在超时内无响应 → 不可达。
        if is_ssl and not is_timeout:
            return {
                "reachable": True,
                "status": 0,
                "reason": f"reachable_ssl_cert_issue: {inner}",
                "elapsed": round(time.time() - t0, 1),
            }
        return {
            "reachable": False,
            "status": -1,
            "reason": f"unreachable: {type(e).__name__}: {inner or e}",
            "elapsed": round(time.time() - t0, 1),
        }
    except (socket.timeout, TimeoutError, ConnectionError) as e:
        return {
            "reachable": False,
            "status": -1,
            "reason": f"unreachable: {type(e).__name__}: {e}",
            "elapsed": round(time.time() - t0, 1),
        }
    except Exception as e:
        # 其它异常保守判为可达，交给浏览器探测最终裁决
        return {
            "reachable": True,
            "status": 0,
            "reason": f"reachable_uncertain: {type(e).__name__}: {e}",
            "elapsed": round(time.time() - t0, 1),
        }


# ═══════════════════════════════════════════════════════════════
#  型号页结构信号 JS（在渲染后 DOM 上执行）
# ═══════════════════════════════════════════════════════════════

_MODEL_SIGNALS_JS = r"""() => {
  const clean = (e) => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
  const KW = __KW__;
  const hasKW = (s) => KW.some(k => (s || '').includes(k));

  const out = {
    counts: {
      table: document.querySelectorAll('table').length,
      dl: document.querySelectorAll('dl').length,
      dt: document.querySelectorAll('dt').length,
      dd: document.querySelectorAll('dd').length,
      ul: document.querySelectorAll('ul').length,
      li: document.querySelectorAll('li').length,
    },
    spec_bearing: {table_with_kw: 0, dl_with_kw: 0, ul_with_kw: 0},
    ul_li_with_sep: 0,
    ul_samples: [],
    kv_container_candidates: [],
    tabs: {selectors_hit: {}, labels: []},
    embedded_json: {scripts_with_kw: 0, sample: ''},
    framework: {
      data_bind: document.querySelectorAll('[data-bind]').length,
      v_bind: document.querySelectorAll('[v-bind],[v-for],[v-if]').length,
      ng: document.querySelectorAll('[ng-repeat],[ng-bind]').length,
    },
    collapsed_spec_heading: false,
    see_more_buttons: 0,
    samples: {},
  };

  // 含规格词的 table / dl / ul
  document.querySelectorAll('table').forEach(t => { if (hasKW(clean(t))) out.spec_bearing.table_with_kw++; });
  document.querySelectorAll('dl').forEach(d => { if (hasKW(clean(d))) out.spec_bearing.dl_with_kw++; });
  document.querySelectorAll('ul').forEach(u => { if (hasKW(clean(u))) out.spec_bearing.ul_with_kw++; });

  // <ul><li> 列表 "key: value" 格式探测
  document.querySelectorAll('ul').forEach(ul => {
    const lis = ul.querySelectorAll('li');
    if (lis.length < 2) return;
    let sepCount = 0;
    let sample = '';
    lis.forEach(li => {
      const text = clean(li);
      if (!text) return;
      const idx = text.indexOf(':');
      if (idx > 0 && idx < text.length - 1) sepCount++;
      if (!sample && sepCount === 1) sample = text.slice(0, 120);
    });
    if (sepCount >= 2) {
      out.ul_li_with_sep += sepCount;
      if (out.ul_samples.length < 3) {
        const parent = ul.parentElement;
        const parentCls = parent ? (parent.className || '').split(/\s+/)[0] : '';
        out.ul_samples.push({
          li_count: lis.length,
          sep_count: sepCount,
          parent_tag: parent ? parent.tagName.toLowerCase() : '',
          parent_class: parentCls,
          sample: sample,
        });
      }
    }
  });

  // 候选重复键值容器
  const CLS = ['feature-item','spec-row','spec-item','specification','param-item',
               'attribute','tech-spec','product-spec','specItem','specRow'];
  const seenCls = {};
  CLS.forEach(c => {
    const els = document.querySelectorAll('[class*="' + c + '"]');
    if (els.length >= 2) {
      let kwHit = 0;
      els.forEach(e => { if (hasKW(clean(e))) kwHit++; });
      seenCls[c] = {count: els.length, kw_hit: kwHit};
    }
  });
  out.kv_container_candidates_by_class = seenCls;

  // 通用"成对短文本容器"探测
  const boxHist = {};
  document.querySelectorAll('body *').forEach(el => {
    if (el.children.length < 2 || el.children.length > 4) return;
    const leaves = [];
    el.querySelectorAll(':scope > *').forEach(c => {
      const t = clean(c);
      if (t && t.length <= 60) leaves.push(t);
    });
    if (leaves.length === 2 && (hasKW(leaves[0]) || hasKW(leaves.join(' ')))) {
      const sig = el.tagName.toLowerCase() + '.' + (el.className || '').split(/\s+/)[0];
      boxHist[sig] = (boxHist[sig] || 0) + 1;
    }
  });
  out.pair_container_hist = Object.entries(boxHist)
    .filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 8)
    .map(([sig, n]) => ({sig, count: n}));

  // tab 菜单
  const TAB_SEL = ['[role="tab"]', '.menu-item .item-name', '[data-bind*="changeTab"]',
                   '.tab', '.tabs a', '.spec-tab', 'ul.tabs li', '[class*="tab"] a'];
  TAB_SEL.forEach(sel => {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length >= 2) {
        out.tabs.selectors_hit[sel] = els.length;
        els.forEach(e => { const t = clean(e); if (t && t.length <= 30) out.tabs.labels.push(t); });
      }
    } catch (_) {}
  });
  out.tabs.labels = Array.from(new Set(out.tabs.labels)).slice(0, 20);

  // 内嵌 JSON
  document.querySelectorAll('script').forEach(s => {
    const t = s.textContent || '';
    if (t.length > 200 && hasKW(t)) {
      out.embedded_json.scripts_with_kw++;
      if (!out.embedded_json.sample) {
        let idx = t.length;
        KW.forEach(k => { const i = t.indexOf(k); if (i >= 0) idx = Math.min(idx, i); });
        out.embedded_json.sample = t.slice(Math.max(0, idx - 120), idx + 240);
      }
    }
  });

  // 折叠规格区检测：aria-expanded="false" 的规格标题
  document.querySelectorAll('[class*="specification"],[class*="spec-heading"],#PDPSpecificationsLink').forEach(el => {
    if (el.getAttribute && el.getAttribute('aria-expanded') === 'false') {
      out.collapsed_spec_heading = true;
    }
  });

  // "See More" 按钮计数（可能多个，需用 CSS 选择器精确定位）
  document.querySelectorAll('button').forEach(btn => {
    const text = clean(btn);
    if (text === 'See More' || text === 'See more' || text === 'SEE MORE') {
      out.see_more_buttons++;
    }
  });

  // dump 候选容器 outerHTML
  const dumpSel = ['[class*="feature-item"]', '[class*="spec-row"]', '[class*="specification"]',
                   'dl', 'table', 'ul'];
  for (const sel of dumpSel) {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length) {
        out.samples[sel] = Array.from(els).slice(0, 3)
          .map(e => (e.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600));
      }
    } catch (_) {}
  }
  return out;
}""".replace("__KW__", _KW_JSON)


# 逐个点 tab、每点一次数当前"规格行容器"数，检测"每个 tab 换一批内容"。
_TAB_CLICK_PROBE_JS = r"""async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const clean = (e) => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
  const countBoxes = () => {
    let n = 0;
    ['feature-item','spec-row','spec-item','specification','param-item','product-spec']
      .forEach(c => { n += document.querySelectorAll('[class*="' + c + '"]').length; });
    return n;
  };
  const run = async () => {
    const tabSels = ['[role="tab"]', '.menu-item .item-name', '[data-bind*="changeTab"]'];
    let tabs = [];
    for (const s of tabSels) {
      const els = Array.from(document.querySelectorAll(s));
      if (els.length >= 2) { tabs = els.slice(0, 20); break; }
    }
    const initialBoxes = countBoxes();
    let clicked = 0, maxBoxes = initialBoxes, changed = false, prevSig = '';
    for (const t of tabs) {
      try { t.scrollIntoView({block:'center'}); t.click(); clicked++; } catch(_) { continue; }
      await sleep(700);
      const b = countBoxes();
      const sig = Array.from(document.querySelectorAll('[class*="feature-item"],[class*="spec-row"]'))
        .slice(0, 5).map(clean).join('|');
      if (sig && sig !== prevSig) changed = true;
      prevSig = sig;
      if (b > maxBoxes) maxBoxes = b;
    }
    return {initial_boxes: initialBoxes, max_boxes_per_tab: maxBoxes,
            tabs_clicked: clicked, tab_total: tabs.length, content_changes_per_tab: changed};
  };
  const timeout = new Promise(res => setTimeout(
    () => res({initial_boxes: countBoxes(), max_boxes_per_tab: countBoxes(),
               tabs_clicked: -1, tab_total: -1, content_changes_per_tab: false,
               timed_out: true}), 25000));
  return Promise.race([run(), timeout]);
}"""


# ═══════════════════════════════════════════════════════════════
#  卖点页结构信号 JS（在渲染后 DOM 上执行）
# ═══════════════════════════════════════════════════════════════

_SP_SIGNALS_JS = r"""() => {
  const clean = (e) => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
  const SP_KW = __SP_KW__;
  const hasSPKW = (s) => SP_KW.some(k => (s || '').includes(k));

  const out = {
    counts: {
      section: document.querySelectorAll('section').length,
      article: document.querySelectorAll('article').length,
      img: document.querySelectorAll('img').length,
      video: document.querySelectorAll('video').length,
      iframe: document.querySelectorAll('iframe').length,
      picture: document.querySelectorAll('picture').length,
      source: document.querySelectorAll('source').length,
      h2: document.querySelectorAll('h2').length,
      h3: document.querySelectorAll('h3').length,
      h4: document.querySelectorAll('h4').length,
      p: document.querySelectorAll('p').length,
    },
    hero_banner: false,
    hero_samples: [],
    carousel: 0,
    carousel_samples: [],
    video_elements: 0,
    video_samples: [],
    feature_blocks: {},
    section_blocks: [],
    collapsed_sections: 0,
    see_more_buttons: 0,
    tabs: {selectors_hit: {}, labels: []},
    framework: {
      data_bind: document.querySelectorAll('[data-bind]').length,
      v_bind: document.querySelectorAll('[v-bind],[v-for],[v-if]').length,
      ng: document.querySelectorAll('[ng-repeat],[ng-bind]').length,
    },
    samples: {},
  };

  // hero / banner 区域检测
  const HERO_SEL = ['[class*="hero"]', '[class*="banner"]', '[class*="main-visual"]',
                    '[class*="key-visual"]', '[class*="kv"]', '[class*="top-visual"]',
                    '[class*="product-hero"]', '[class*="pdp-hero"]', '[id*="hero"]'];
  HERO_SEL.forEach(sel => {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length) {
        out.hero_banner = true;
        if (out.hero_samples.length < 3) {
          els.forEach(e => {
            if (out.hero_samples.length < 3) {
              out.hero_samples.push({
                selector: sel,
                text: clean(e).slice(0, 200),
                html: (e.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600),
              });
            }
          });
        }
      }
    } catch(_) {}
  });

  // 轮播 / 画廊组件
  const CAROUSEL_SEL = ['[class*="carousel"]', '[class*="gallery"]', '[class*="slider"]',
                        '[class*="swiper"]', '[class*="slick"]', '[data-carousel]',
                        '[data-gallery]', '[role="region"][aria-label*="gallery" i]'];
  CAROUSEL_SEL.forEach(sel => {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length) {
        out.carousel += els.length;
        if (out.carousel_samples.length < 3) {
          els.forEach(e => {
            if (out.carousel_samples.length < 3) {
              const imgs = e.querySelectorAll('img');
              out.carousel_samples.push({
                selector: sel,
                img_count: imgs.length,
                html: (e.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600),
              });
            }
          });
        }
      }
    } catch(_) {}
  });

  // video 元素
  document.querySelectorAll('video, iframe[src*="youtube"], iframe[src*="vimeo"], iframe[src*="youtu.be"]').forEach(v => {
    out.video_elements++;
    if (out.video_samples.length < 3) {
      out.video_samples.push({
        tag: v.tagName.toLowerCase(),
        src: v.getAttribute('src') || v.querySelector('source')?.getAttribute('src') || '',
        html: (v.outerHTML || '').replace(/\s+/g, ' ').slice(0, 400),
      });
    }
  });

  // 功能区块（class 含 feature/highlight/point/benefit）
  const FEATURE_CLS = ['feature', 'highlight', 'point', 'benefit', 'advantage',
                       'technology', 'spec-feature', 'product-feature',
                       'feature-block', 'feature-card', 'feature-section'];
  FEATURE_CLS.forEach(c => {
    const els = document.querySelectorAll('[class*="' + c + '"]');
    if (els.length >= 1) {
      let kwHit = 0;
      els.forEach(e => { if (hasSPKW(clean(e))) kwHit++; });
      out.feature_blocks[c] = {count: els.length, kw_hit: kwHit};
    }
  });

  // section 语义区块（含卖点词的）
  document.querySelectorAll('section, article').forEach(sec => {
    const text = clean(sec);
    if (text && text.length > 20 && hasSPKW(text)) {
      if (out.section_blocks.length < 8) {
        const headings = sec.querySelectorAll('h2,h3,h4');
        const title = headings.length ? clean(headings[0]) : '';
        const imgs = sec.querySelectorAll('img');
        const videos = sec.querySelectorAll('video, iframe');
        out.section_blocks.push({
          tag: sec.tagName.toLowerCase(),
          class: (sec.className || '').split(/\s+/).slice(0, 3).join(' '),
          title: title.slice(0, 100),
          text_len: text.length,
          img_count: imgs.length,
          video_count: videos.length,
          html: (sec.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600),
        });
      }
    }
  });

  // 折叠区域检测
  document.querySelectorAll('[aria-expanded="false"], details:not([open])').forEach(el => {
    out.collapsed_sections++;
  });

  // "See More" / "もっと見る" / "Ver más" 按钮
  document.querySelectorAll('button, a').forEach(btn => {
    const text = clean(btn);
    if (text.match(/^(See More|See more|SEE MORE|もっと見る|もっと見る|Ver más|Mehr anzeigen)$/i)) {
      out.see_more_buttons++;
    }
  });

  // tab 菜单（复用 spec 的逻辑）
  const TAB_SEL = ['[role="tab"]', '.menu-item .item-name', '[data-bind*="changeTab"]',
                   '.tab', '.tabs a', '.spec-tab', 'ul.tabs li', '[class*="tab"] a'];
  TAB_SEL.forEach(sel => {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length >= 2) {
        out.tabs.selectors_hit[sel] = els.length;
        els.forEach(e => { const t = clean(e); if (t && t.length <= 30) out.tabs.labels.push(t); });
      }
    } catch(_) {}
  });
  out.tabs.labels = Array.from(new Set(out.tabs.labels)).slice(0, 20);

  // dump 候选容器 outerHTML
  const dumpSel = ['[class*="feature"]', '[class*="highlight"]', '[class*="point"]',
                   '[class*="hero"]', '[class*="banner"]', 'section', 'article',
                   '[class*="carousel"]', '[class*="gallery"]'];
  for (const sel of dumpSel) {
    try {
      const els = document.querySelectorAll(sel);
      if (els.length) {
        out.samples[sel] = Array.from(els).slice(0, 3)
          .map(e => (e.outerHTML || '').replace(/\s+/g, ' ').slice(0, 600));
      }
    } catch(_) {}
  }
  return out;
}""".replace("__SP_KW__", _SP_KW_JSON)


# ═══════════════════════════════════════════════════════════════
#  Playwright 浏览器封装
# ═══════════════════════════════════════════════════════════════

def _get_playwright():
    """延迟导入 Playwright，给出友好错误提示。"""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("[ERROR] Playwright 未安装。请执行：", file=sys.stderr)
        print("  pip install playwright", file=sys.stderr)
        print("  playwright install chromium", file=sys.stderr)
        sys.exit(3)


def _scroll_page(page, passes: int = 8, wait_ms: int = 600):
    """滚动页面多次，触发懒加载。"""
    for _ in range(passes):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(wait_ms)


def probe_model(url: str, extra_wait_ms: int, scroll_passes: int) -> dict:
    """探型号页：渲染后 DOM 结构信号 + 点 tab 前后规格词元素数变化。"""
    sync_playwright = _get_playwright()
    out: dict = {"mode": "model", "url": url}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            out["status"] = resp.status if resp else 0
            out["ok"] = 200 <= (resp.status if resp else 0) < 300
        except Exception as e:
            out["status"] = 0
            out["ok"] = False
            out["error"] = str(e)
            browser.close()
            return out

        # 等待 body + 额外渲染时间
        try:
            page.wait_for_selector("body", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(extra_wait_ms)

        # 滚动触发懒加载
        _scroll_page(page, passes=scroll_passes, wait_ms=600)

        # 执行结构信号 JS
        out["signals"] = page.evaluate(_MODEL_SIGNALS_JS) or {}

        # 交互探测：逐 tab 点击
        probe = page.evaluate(_TAB_CLICK_PROBE_JS) or {}
        if not isinstance(probe, dict):
            probe = {}
        out["tab_interaction"] = {
            "initial_boxes": probe.get("initial_boxes"),
            "max_boxes_per_tab": probe.get("max_boxes_per_tab"),
            "tabs_clicked": probe.get("tabs_clicked"),
            "tab_total": probe.get("tab_total"),
            "renders_on_click": bool(
                probe.get("content_changes_per_tab")
                and (probe.get("tab_total") or 0) >= 2
            ),
        }

        browser.close()

    return out




# ═══════════════════════════════════════════════════════════════
#  卖点（Selling Points）探测
# ═══════════════════════════════════════════════════════════════

def probe_sp(url: str, extra_wait_ms: int, scroll_passes: int) -> dict:
    """探型号页卖点结构信号：hero/banner、轮播、视频、功能区块、section 语义块。"""
    sync_playwright = _get_playwright()
    out: dict = {"mode": "sp", "url": url}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            out["status"] = resp.status if resp else 0
            out["ok"] = 200 <= (resp.status if resp else 0) < 300
        except Exception as e:
            out["status"] = 0
            out["ok"] = False
            out["error"] = str(e)
            browser.close()
            return out

        try:
            page.wait_for_selector("body", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(extra_wait_ms)

        _scroll_page(page, passes=scroll_passes, wait_ms=600)

        out["signals"] = page.evaluate(_SP_SIGNALS_JS) or {}

        browser.close()

    return out

# ═══════════════════════════════════════════════════════════════
#  入口页探测（产品链接发现）
# ═══════════════════════════════════════════════════════════════

# 通用"产品卡链接"候选选择器
_LINK_SELECTOR_CANDIDATES = [
    "a[href*='/c-p/']",
    "a[href*='/dp/']",
    "a[href*='/p/']",
    "a[href*='/product/']",
    "a[href*='/bravia/products/']",
    "a[href*='/tv/lineup/']",
    "a[href*='/products/']",
    "a[href*='/tv/']",
    "a[href*='/tvs/']",
    "a[href*='/televisions/']",
    "a[href*='/tv-soundbars/']",
    "a[href*='/product-page/']",
    "a.product-card",
    "a.product-item",
    "[class*='product'] a[href]",
    "[class*='card'] a[href]",
    "article a[href]",
    "li a[href]",
]

# 非电视链接的负向关键词
_NON_TV_RE = re.compile(
    r"soundbar|speaker|headphone|remote|bracket|mount|accessor|cable|"
    r"projector|monitor|/support|/help|/account|/cart|/search",
    re.I,
)

# 末段 slug 是否像"具体型号页"
_MODEL_SLUG_RE = re.compile(r"[A-Za-z]\d{2,}|\d{2,}[A-Za-z]")
_MODEL_HINT_RE = re.compile(
    r"[A-Za-z0-9]*\d[A-Za-z0-9]*[A-Za-z][A-Za-z0-9]*|"
    r"[A-Za-z]{2,}\d{2,}[A-Za-z0-9]*"
)

# "加载更多 / 下一页"按钮候选
_LOAD_MORE_CANDIDATES = [
    "button[aria-label*='more' i]",
    "button[class*='load-more' i]",
    "a[class*='load-more' i]",
    "[data-hook='load-more-button']",
    "button[class*='show-more' i]",
    "a[class*='show-more' i]",
    "[aria-label*='Show page' i]",
    "a[rel='next']",
    "a[class*='next' i]",
    "li[class*='next' i] a",
    "button[class*='pagination' i]",
]


def _looks_like_model_url(href: str) -> bool:
    path = urlsplit(str(href or "")).path.rstrip("/")
    last = path.rsplit("/", 1)[-1] if path else ""
    return bool(last and _MODEL_SLUG_RE.search(last))


def _rank_link_selectors_from_hrefs(all_hrefs: dict[str, list[str]]) -> list[dict]:
    """在已收集的 hrefs 上评估每个候选选择器，返回按"产品相关度"降序的统计。"""
    stats: list[dict] = []
    for sel, hrefs in all_hrefs.items():
        if not hrefs:
            continue
        uniq: list[str] = []
        seen: set[str] = set()
        for h in hrefs:
            hl = h.lower()
            if _NON_TV_RE.search(hl):
                continue
            key = hl.split("?")[0].rstrip("/")
            if key and key not in seen:
                seen.add(key)
                uniq.append(h)
        if uniq:
            model_like = sum(1 for h in uniq if _looks_like_model_url(h))
            purity = model_like / len(uniq)
            stats.append({
                "selector": sel,
                "unique_links": len(uniq),
                "model_like_links": model_like,
                "model_like_ratio": round(purity, 3),
                "sample": uniq[:5],
            })

    def _rank_key(s: dict) -> tuple:
        strong = s["model_like_links"] >= 3
        return (
            1 if strong else 0,
            s["model_like_ratio"] if strong else 0.0,
            s["model_like_links"],
            s["unique_links"],
        )

    stats.sort(key=_rank_key, reverse=True)
    return stats


def _url_pattern(sample_urls: list[str]) -> str:
    if not sample_urls:
        return ""
    path = urlsplit(sample_urls[0]).path
    segs = [s for s in path.split("/") if s]
    out = []
    for s in segs:
        if _MODEL_HINT_RE.fullmatch(s) or _MODEL_HINT_RE.search(s):
            out.append("<MODEL...>")
        else:
            out.append(s)
    return "/" + "/".join(out)


def _detect_pager(html: str) -> dict:
    text = str(html or "")
    numbered = re.findall(
        r"aria-label\s*=\s*[\"'][^\"']*\bpage\s+\d+\b[^\"']*[\"']", text, re.I
    )
    return {
        "has_numbered_pages": bool(numbered),
        "numbered_page_count": len(set(numbered)),
        "has_next_button": bool(
            re.search(r"aria-label\s*=\s*[\"'][^\"']*\b(?:next\s+page|next)\b[^\"']*[\"']", text, re.I)
        ),
        "has_load_more": bool(
            re.search(r"(?:aria-label|class)\s*=\s*[\"'][^\"']*(?:load\s*more|show\s*more)[^\"']*[\"']", text, re.I)
        ),
    }


def _collect_link_hrefs(page) -> dict[str, list[str]]:
    """用 Playwright 在页面上收集每个候选选择器的 href 列表。"""
    all_hrefs: dict[str, list[str]] = {}
    for sel in _LINK_SELECTOR_CANDIDATES:
        try:
            els = page.query_selector_all(sel)
            hrefs = []
            for el in els:
                h = el.get_attribute("href")
                if h:
                    hrefs.append(h)
            all_hrefs[sel] = hrefs
        except Exception:
            all_hrefs[sel] = []
    return all_hrefs


def _count_links(all_hrefs: dict[str, list[str]], selector: str) -> int:
    hrefs = all_hrefs.get(selector, [])
    return len({
        h.lower().split("?")[0].rstrip("/")
        for h in hrefs
        if not _NON_TV_RE.search(h.lower())
    })


def probe_entry(url: str, deep: bool = False, scroll_passes: int = 6) -> dict:
    """探入口页：发现产品链接选择器、URL 模式、分页/滚动信号。"""
    sync_playwright = _get_playwright()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            browser.close()
            return {"mode": "entry", "url": url, "error": str(e)}

        try:
            page.wait_for_selector("a[href]", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(3000)

        # 第一趟：仅滚动
        _scroll_page(page, passes=scroll_passes, wait_ms=600)
        scrolled_hrefs = _collect_link_hrefs(page)
        scrolled_html = page.content()

        more_hrefs: dict[str, list[str]] = {}
        more_html = ""

        # 第二趟（可选）：点击"加载更多/下一页"
        if deep:
            try:
                page2 = context.new_page()
                page2.goto(url, wait_until="domcontentloaded", timeout=30000)
                page2.wait_for_selector("a[href]", timeout=10000)
                page2.wait_for_timeout(3000)
                _scroll_page(page2, passes=scroll_passes, wait_ms=600)

                # 循环点击"加载更多"候选
                for sel in _LOAD_MORE_CANDIDATES:
                    for _ in range(12):
                        try:
                            btn = page2.query_selector(sel)
                            if btn and btn.is_visible():
                                btn.click()
                                page2.wait_for_timeout(1500)
                            else:
                                break
                        except Exception:
                            break

                more_hrefs = _collect_link_hrefs(page2)
                more_html = page2.content()
                page2.close()
            except Exception:
                pass

        browser.close()

    # 选链接最多的那趟
    best_hrefs = scrolled_hrefs
    best_html = scrolled_html
    if more_hrefs:
        best_ranked = _rank_link_selectors_from_hrefs(more_hrefs)
        scrolled_ranked = _rank_link_selectors_from_hrefs(scrolled_hrefs)
        best_count = best_ranked[0]["unique_links"] if best_ranked else 0
        scrolled_count = scrolled_ranked[0]["unique_links"] if scrolled_ranked else 0
        if best_count > scrolled_count:
            best_hrefs = more_hrefs
            best_html = more_html

    ranked = _rank_link_selectors_from_hrefs(best_hrefs)
    best = ranked[0] if ranked else None
    best_selector = best["selector"] if best else ""
    static_count = best["unique_links"] if best else 0
    samples = best["sample"] if best else []

    # 分页/加载方式判断
    load_hint = "none"
    growth = {}
    if best_selector:
        scrolled_count = _count_links(scrolled_hrefs, best_selector)
        more_count = _count_links(more_hrefs, best_selector) if more_hrefs else 0
        if more_hrefs and more_count > scrolled_count * 1.2:
            load_hint = "click_more_or_paginate"
            growth = {"after_scroll": scrolled_count, "after_more": more_count}
        elif scrolled_count > 0:
            growth = {"after_scroll": scrolled_count}

    pager = _detect_pager(best_html)
    if load_hint == "none" and pager["has_numbered_pages"]:
        load_hint = "paginate_replace"

    return {
        "mode": "entry",
        "url": url,
        "best_link_selector": best_selector,
        "static_unique_links": static_count,
        "link_selector_ranking": ranked[:6],
        "sample_product_hrefs": samples,
        "product_url_pattern": _url_pattern(samples),
        "load_more_hint": load_hint,
        "link_growth": growth,
        "pager": pager,
    }


# ═══════════════════════════════════════════════════════════════
#  摘要打印
# ═══════════════════════════════════════════════════════════════

def _print_model_summary(out: dict) -> None:
    sig = out.get("signals") or {}
    counts = sig.get("counts") or {}
    ti = out.get("tab_interaction") or {}
    print(f"[MODEL] status={out.get('status')} ok={out.get('ok')}")
    print(
        f"  table={counts.get('table')} (含规格词 {sig.get('spec_bearing', {}).get('table_with_kw')})"
        f"  dl={counts.get('dl')} (含规格词 {sig.get('spec_bearing', {}).get('dl_with_kw')})"
        f"  dd={counts.get('dd')}"
    )
    print(
        f"  data-bind={sig.get('framework', {}).get('data_bind')}"
        f"  vue={sig.get('framework', {}).get('v_bind')}"
        f"  ng={sig.get('framework', {}).get('ng')}"
    )
    print(f"  内嵌JSON含规格词的script数={sig.get('embedded_json', {}).get('scripts_with_kw')}")
    print(f"  class候选键值容器={sig.get('kv_container_candidates_by_class')}")
    print(f"  成对短文本容器={sig.get('pair_container_hist')}")
    print(f"  tab选择器命中={sig.get('tabs', {}).get('selectors_hit')}")
    print(f"  tab标签={sig.get('tabs', {}).get('labels')}")
    print(
        f"  [交互] 初始容器={ti.get('initial_boxes')} 逐tab最大容器={ti.get('max_boxes_per_tab')} "
        f"点了{ti.get('tabs_clicked')}/{ti.get('tab_total')}个tab "
        f"→ 内容随tab变化(交互渲染站)={ti.get('renders_on_click')}"
    )
    print("  提示：看 --out 文件里 signals.samples 的 outerHTML 定 container/key/value 选择器")




def _print_sp_summary(out: dict) -> None:
    sig = out.get("signals") or {}
    counts = sig.get("counts") or {}
    print(f"[SP] status={out.get('status')} ok={out.get('ok')}")
    print(f"  section={counts.get('section')} article={counts.get('article')}"
          f" img={counts.get('img')} video={counts.get('video')}"
          f" iframe={counts.get('iframe')} picture={counts.get('picture')}")
    print(f"  hero_banner={sig.get('hero_banner')} carousel={sig.get('carousel')}"
          f" video_elements={sig.get('video_elements')}")
    fb = sig.get("feature_blocks") or {}
    if fb:
        for cls, info in fb.items():
            print(f"  feature_block[{cls}]: count={info.get('count')} kw_hit={info.get('kw_hit')}")
    sb = sig.get("section_blocks") or []
    if sb:
        print(f"  section_blocks({len(sb)}):")
        for b in sb[:5]:
            print(f"    <{b.get('tag')} class='{b.get('class')}'> title='{b.get('title')}'"
                  f" text_len={b.get('text_len')} img={b.get('img_count')} video={b.get('video_count')}")
    print(f"  collapsed_sections={sig.get('collapsed_sections')}"
          f" see_more_buttons={sig.get('see_more_buttons')}")
    print(f"  tabs={sig.get('tabs', {}).get('labels')}")
    print("  提示：看 --out 文件里 signals.samples 的 outerHTML 定卖点选择器")

def _print_entry_summary(out: dict) -> None:
    print(f"[ENTRY] {out.get('url')}")
    print(
        f"  best_link_selector={out.get('best_link_selector')} "
        f"links={out.get('static_unique_links')}"
    )
    print(f"  product_url_pattern={out.get('product_url_pattern')}")
    print(f"  sample_hrefs={out.get('sample_product_hrefs')}")
    print(f"  load_more_hint={out.get('load_more_hint')}  pager={out.get('pager')}")


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser(description="spec-schema-gen 独立探测脚本")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--entry", help="入口列表页 URL（探发现层信号）")
    g.add_argument("--model", help="型号规格页 URL（探规格结构信号）")
    g.add_argument("--sp", help="型号页 URL（探卖点结构信号）")
    ap.add_argument("--out", required=True, help="结果 JSON 输出路径")
    ap.add_argument(
        "--extra-wait-ms",
        type=int,
        default=4000,
        help="型号页渲染额外等待毫秒（重 SPA 可加大，默认 4000）",
    )
    ap.add_argument(
        "--scroll-passes",
        type=int,
        default=8,
        help="型号页滚动次数（默认 8）；--entry 时入口页滚动次数（默认 6）",
    )
    ap.add_argument(
        "--deep",
        action="store_true",
        help="--entry 时额外做一趟'点击加载更多'探测（慢，仅在滚动趟链接偏少时用）",
    )
    ap.add_argument(
        "--skip-reachable",
        action="store_true",
        help="跳过可达性预检（一般不用；仅在预检误判、确知能访问时用）",
    )
    ap.add_argument(
        "--reachable-timeout",
        type=int,
        default=10,
        help="可达性预检超时秒数（默认 10）",
    )
    args = ap.parse_args()

    url = args.sp or args.model or args.entry
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    # 可达性预检
    if not args.skip_reachable:
        rc = check_reachable(url, timeout=args.reachable_timeout)
        if not rc.get("reachable"):
            out = {
                "mode": ("sp" if args.sp else "model" if args.model else "entry"),
                "url": url,
                "unreachable": True,
                "reachability": rc,
            }
            outp.write_text(
                json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"[UNREACHABLE] {url}")
            print(f"  {rc.get('reason')}（{rc.get('elapsed')}s）")
            print(
                "  → 该域名在当前网络环境无法访问。请告诉用户，不要重试；换能访问的"
                "网络环境后再探。（若确信能访问、是预检误判，可加 --skip-reachable 重试）"
            )
            return 2
        print(f"[REACHABLE] {url} status={rc.get('status')}（{rc.get('elapsed')}s），继续探测")

    if args.sp:
        out = probe_sp(args.sp, args.extra_wait_ms, args.scroll_passes)
    elif args.model:
        out = probe_model(args.model, args.extra_wait_ms, args.scroll_passes)
    else:
        out = probe_entry(
            args.entry,
            deep=args.deep,
            scroll_passes=(args.scroll_passes if args.scroll_passes != 8 else 6),
        )

    outp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.sp:
        _print_sp_summary(out)
    elif args.model:
        _print_model_summary(out)
    else:
        _print_entry_summary(out)
    print(f"[OUT] 完整信号 → {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
