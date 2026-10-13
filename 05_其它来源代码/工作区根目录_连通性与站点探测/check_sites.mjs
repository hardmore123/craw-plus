import fs from 'node:fs';
import path from 'node:path';
import dns from 'node:dns/promises';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const sites = JSON.parse(fs.readFileSync(path.join(root, 'sites.json'), 'utf8'));

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';
const TIMEOUT_MS = 30000;
const CONCURRENCY = 6;
const ATTEMPTS = 2;
const CAP = 400 * 1024;

function extractTitle(html) {
  if (!html) return '';
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (!m) return '';
  return m[1].replace(/\s+/g, ' ').trim().slice(0, 120);
}

async function readCapped(res) {
  if (!res.body) return '';
  const reader = res.body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (size < CAP) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      size += value.length;
    }
  } catch { /* ignore body read errors */ }
  try { await reader.cancel(); } catch {}
  const buf = Buffer.concat(chunks.map((c) => Buffer.from(c)));
  return buf.toString('utf8');
}

async function check(site) {
  let lastErr = null;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const t0 = Date.now();
    try {
      const res = await fetch(site.url, {
        redirect: 'follow',
        headers: {
          'user-agent': UA,
          accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
          'accept-language': 'en-US,en;q=0.9',
          'upgrade-insecure-requests': '1',
        },
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      const elapsed = Date.now() - t0;
      const body = await readCapped(res);
      const headers = {};
      for (const k of ['server', 'content-type', 'content-length', 'x-akamai-transformed', 'cf-mitigated', 'set-cookie']) {
        const v = res.headers.get(k);
        if (v) headers[k] = k === 'set-cookie' ? '(present)' : v.slice(0, 120);
      }
      return {
        ...site,
        ok: true,
        status: res.status,
        statusText: res.statusText,
        elapsedMs: elapsed,
        finalUrl: res.url,
        redirected: res.url.replace(/\/$/, '') !== site.url.replace(/\/$/, ''),
        bytes: body.length,
        title: extractTitle(body),
        headers,
        attempts: attempt,
        error: '',
      };
    } catch (e) {
      lastErr = e;
      if (attempt < ATTEMPTS) await new Promise((r) => setTimeout(r, 1500));
    }
  }
  const cause = lastErr?.cause;
  let msg = lastErr?.message || String(lastErr);
  if (cause?.code) msg = `${cause.code}: ${cause.message || ''}`.trim();
  else if (cause?.message) msg = cause.message;
  return {
    ...site,
    ok: false,
    status: 0,
    statusText: '',
    elapsedMs: 0,
    finalUrl: '',
    redirected: false,
    bytes: 0,
    title: '',
    headers: {},
    attempts: ATTEMPTS,
    error: msg.slice(0, 200),
  };
}

async function dnsCheck(host) {
  try {
    const r = await dns.lookup(host, { all: true });
    return r.map((x) => x.address).join(', ');
  } catch (e) {
    return `DNS-FAIL: ${e.code || e.message}`;
  }
}

const results = new Array(sites.length);
let idx = 0;
async function worker() {
  while (idx < sites.length) {
    const i = idx++;
    results[i] = await check(sites[i]);
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

// DNS detail for any failure
for (const r of results) {
  if (!r.ok) {
    const host = new URL(r.url).hostname;
    r.dns = await dnsCheck(host);
  } else {
    r.dns = '';
  }
}

fs.writeFileSync(path.join(root, 'site_check_result.json'), JSON.stringify(results, null, 2), 'utf8');

const rank = (r) => {
  if (!r.ok) return 4;
  if (r.status >= 200 && r.status < 300) return 0;
  if (r.status >= 300 && r.status < 400) return 1;
  if (r.status === 403 || r.status === 429 || r.status === 503) return 2;
  return 3;
};
results.sort((a, b) => rank(a) - rank(b) || a.line.localeCompare(b.line) || a.name.localeCompare(b.name));

const verdict = (r) => {
  if (!r.ok) return 'X 不可达';
  const blocked = [401, 403, 405, 406, 429, 503].includes(r.status);
  if (blocked) return '△ 可连但被拒';
  if (r.status >= 200 && r.status < 400) return 'O 可访问';
  return '? 异常 ' + r.status;
};

const lines = [];
lines.push('# 北美线站点可访问性测试报告');
lines.push('');
lines.push(`测试时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}  (北京时间)`);
lines.push('');
lines.push(`测试方式: Node.js ${process.version} fetch / OpenSSL 直连,超时 ${TIMEOUT_MS / 1000}s,失败重试 ${ATTEMPTS} 次,并发 ${CONCURRENCY},跟随重定向,桌面 Chrome UA。`);
lines.push('');
lines.push('| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 跳转后最终地址 | 页面标题 |');
lines.push('|---|------|------|-----|------|------|------|----------------|----------|');
results.forEach((r, i) => {
  const t = r.ok ? (r.elapsedMs / 1000).toFixed(2) + 's' : '-';
  const http = r.ok ? String(r.status) : 'ERR';
  const fin = r.redirected ? r.finalUrl : '';
  const esc = (s) => String(s || '').replace(/\|/g, '\\|');
  lines.push(`| ${i + 1} | ${esc(r.line)} | ${esc(r.name)} | ${esc(r.url)} | ${verdict(r)} | ${http} | ${t} | ${esc(fin)} | ${esc(r.title)} |`);
});
lines.push('');
lines.push('## 失败 / 异常明细');
lines.push('');
const bad = results.filter((r) => !r.ok || !(r.status >= 200 && r.status < 400));
if (!bad.length) {
  lines.push('无。');
} else {
  for (const r of bad) {
    lines.push(`### ${r.line} / ${r.name} — ${r.url}`);
    lines.push(`- 结论: ${verdict(r)}`);
    lines.push(`- HTTP: ${r.ok ? r.status + ' ' + r.statusText : '无响应'}`);
    lines.push(`- 耗时: ${r.ok ? r.elapsedMs + 'ms' : '-'}`);
    if (r.error) lines.push(`- 错误: \`${r.error}\``);
    if (r.dns) lines.push(`- DNS 解析: ${r.dns}`);
    if (r.title) lines.push(`- 标题: ${r.title}`);
    if (Object.keys(r.headers).length) {
      lines.push(`- 响应头: ${Object.entries(r.headers).map(([k, v]) => `${k}=${v}`).join('; ')}`);
    }
    lines.push(`- 判定说明: ${r.ok && [401, 403, 405, 406, 429, 503].includes(r.status) ? 'TCP/TLS 与 HTTP 层均连通,但服务器以反爬/风控策略拒绝了本次请求(常见于 Akamai / Cloudflare / PerimeterX),真实浏览器通常可正常打开。' : r.ok ? '服务器返回了非预期的状态码,需人工确认。' : '请求未获得任何 HTTP 响应(连接/超时/TLS 层失败)。'}`);
    lines.push('');
  }
}

fs.writeFileSync(path.join(root, 'site_check_report.md'), lines.join('\n'), 'utf8');

console.log('total=' + results.length);
console.log('reachable=' + results.filter((r) => r.ok && r.status >= 200 && r.status < 400).length);
console.log('blocked=' + results.filter((r) => r.ok && [401, 403, 405, 406, 429, 503].includes(r.status)).length);
console.log('failed=' + results.filter((r) => !r.ok).length);
console.log('report=site_check_report.md');
