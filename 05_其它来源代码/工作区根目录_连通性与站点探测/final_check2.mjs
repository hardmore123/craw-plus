import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import tls from 'node:tls';
import https from 'node:https';
import http2 from 'node:http2';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const sites = JSON.parse(fs.readFileSync(path.join(root, 'sites.json'), 'utf8'));

const PH = '127.0.0.1', PP = 7877;
const TIMEOUT = 45000;
const CONCURRENCY = 5;
const CAP = 600 * 1024;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const COMMON = {
  'user-agent': UA,
  accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
  'accept-language': 'en-US,en;q=0.9',
  'accept-encoding': 'identity',
  'sec-ch-ua': '"Chromium";v="131", "Not_A Brand";v="24"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Windows"',
  'upgrade-insecure-requests': '1',
  'sec-fetch-dest': 'document',
  'sec-fetch-mode': 'navigate',
  'sec-fetch-site': 'none',
  'sec-fetch-user': '?1',
};

function tunnel(host, port, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const sock = net.connect({ host: PH, port: PP });
    let done = false;
    const fail = (e) => { if (done) return; done = true; sock.destroy(); reject(new Error('代理CONNECT失败: ' + (e.message || e))); };
    sock.setTimeout(timeoutMs, () => fail(new Error('代理连接超时')));
    sock.once('error', fail);
    sock.once('connect', () => {
      sock.write(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`);
      let buf = Buffer.alloc(0);
      const onData = (d) => {
        buf = Buffer.concat([buf, d]);
        const i = buf.indexOf('\r\n\r\n');
        if (i === -1) return;
        sock.removeListener('data', onData);
        const line = buf.subarray(0, i).toString('latin1').split('\r\n')[0];
        if (!/ 200 /.test(line)) return fail(new Error(line));
        done = true; sock.setTimeout(0); resolve(sock);
      };
      sock.on('data', onData);
    });
  });
}

async function tlsOver(raw, host) {
  const t = tls.connect({ socket: raw, servername: host, ALPNProtocols: ['h2', 'http/1.1'], rejectUnauthorized: false });
  t.setTimeout(20000, () => t.destroy(new Error('TLS握手超时')));
  await once(t, 'secureConnect');
  t.setTimeout(0);
  return t;
}

function fetchH2(t, host, u, timeoutMs) {
  return new Promise((resolve, reject) => {
    const client = http2.connect(`https://${host}:443`, { createConnection: () => t });
    const timer = setTimeout(() => { try { client.destroy(); } catch {} reject(new Error('HTTP/2 响应超时')); }, timeoutMs);
    client.on('error', (e) => { clearTimeout(timer); reject(new Error('HTTP/2 ' + (e.code || e.message))); });
    const req = client.request({ ':method': 'GET', ':path': u.pathname + u.search, ':authority': host, ':scheme': 'https', ...COMMON });
    let status = 0; let headers = {}; const chunks = []; let n = 0;
    req.on('response', (h) => { status = Number(h[':status']); headers = h; });
    req.on('data', (d) => { if (n < CAP) { chunks.push(d); n += d.length; } });
    req.on('error', (e) => { clearTimeout(timer); try { client.destroy(); } catch {} reject(new Error('HTTP/2 流错误 ' + (e.code || e.message))); });
    req.on('end', () => { clearTimeout(timer); try { client.close(); } catch {} resolve({ status, headers, body: Buffer.concat(chunks).toString('utf8') }); });
    req.end();
  });
}

function fetchH1(t, u, timeoutMs) {
  return new Promise((resolve, reject) => {
    const req = https.request({ host: u.hostname, port: 443, path: u.pathname + u.search, method: 'GET', agent: false, createConnection: () => t, headers: COMMON }, (res) => {
      const chunks = []; let n = 0;
      res.on('data', (d) => { if (n < CAP) { chunks.push(d); n += d.length; } });
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString('utf8') }));
      res.on('error', reject);
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error('HTTP/1.1 响应超时')));
    req.on('error', (e) => reject(new Error('HTTP/1.1 ' + (e.code || e.message))));
    req.end();
  });
}

function visibleText(html) {
  return (html || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ')
    .trim();
}

function classify(status, body, title) {
  const raw = (body || '').slice(0, 60000);
  const vis = visibleText(raw);
  const head = vis.slice(0, 1500);
  if (/Just a moment|Attention Required|Checking your browser|cf-browser-verification|challenge-platform/i.test(title + ' ' + raw.slice(0, 8000))) return { code: 'C', why: 'Cloudflare 人机验证页' };
  if (/Verify Your Identity|Verifica tu identidad|unusual traffic|blocked - redirecting|Pardon Our Interruption|Access to this page has been denied/i.test(head)) return { code: 'B', why: '风控/身份验证页' };
  if (/challenge-container|AwsWafIntegration|aws-waf-token|window\.awsWaf|awsWafCookieDomainList/i.test(raw) || (status === 202 && vis.length < 3000)) return { code: 'A', why: 'AWS WAF JS 挑战页' };
  if (/Enter the characters you see|Type the characters you see|Robot Check|are you a human|Please verify you are a human/i.test(head)) return { code: 'K', why: '验证码/人机校验页' };
  if (status === 403) return { code: 'D', why: '403 拒绝访问' };
  if (status >= 200 && status < 300) {
    if (vis.length < 400) return { code: 'E', why: '疑似空壳/挑战页(可见文本过少)' };
    return { code: 'O', why: '正常访问' };
  }
  return { code: '?', why: '异常状态 ' + status };
}

async function visit(startUrl) {
  let url = startUrl;
  const chain = [];
  for (let hop = 0; hop < 8; hop++) {
    const u = new URL(url);
    const raw = await tunnel(u.hostname, Number(u.port || 443));
    const t = await tlsOver(raw, u.hostname);
    let r;
    try {
      r = t.alpnProtocol === 'h2' ? await fetchH2(t, u.hostname, u, TIMEOUT) : await fetchH1(t, u, TIMEOUT);
      r.alpn = t.alpnProtocol || 'http/1.1';
    } finally { try { t.destroy(); } catch {} }

    const title = ((r.body || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1].replace(/\s+/g, ' ').trim().slice(0, 110);
    const vis = visibleText(r.body);
    chain.push({ url, status: r.status });
    const loc = r.headers.location;
    if ([301, 302, 303, 307, 308].includes(r.status) && loc) { url = new URL(loc, url).href; continue; }
    const cls = classify(r.status, r.body, title);
    return { ...r, title, visible: vis, finalUrl: url, chain, cls };
  }
  throw new Error('重定向次数过多');
}

async function check(site) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    const t0 = Date.now();
    try {
      const r = await visit(site.url);
      return {
        ...site, ok: true, status: r.status, elapsedMs: Date.now() - t0, finalUrl: r.finalUrl,
        alpn: r.alpn, bytes: r.body.length, title: r.title, chain: r.chain,
        code: r.cls.code, why: r.cls.why, visibleLen: r.visible.length,
        snippet: r.visible.slice(0, 220), error: '', server: r.headers.server || '',
      };
    } catch (e) {
      if (attempt === 2) return { ...site, ok: false, status: 0, elapsedMs: Date.now() - t0, finalUrl: '', alpn: '', bytes: 0, title: '', chain: [], code: 'X', why: '请求失败', visibleLen: 0, snippet: '', error: String(e.message || e).slice(0, 160), server: '' };
      await new Promise((r) => setTimeout(r, 1200));
    }
  }
}

const results = new Array(sites.length);
let idx = 0;
await Promise.all(Array.from({ length: CONCURRENCY }, async () => { while (idx < sites.length) { const i = idx++; results[i] = await check(sites[i]); } }));

fs.writeFileSync(path.join(root, 'proxy_final_result.json'), JSON.stringify(results, null, 2), 'utf8');

const order = { O: 0, E: 1, A: 2, C: 3, B: 4, K: 5, D: 6, '?': 7, X: 8 };
const sorted = [...results].sort((a, b) => order[a.code] - order[b.code] || a.line.localeCompare(b.line) || a.name.localeCompare(b.name));

console.log('=== 经 Clash 代理 (HTTP/2 浏览器化客户端) ===');
console.log('出口 IP: 209.126.8.142 (Contabo, US 机房) | 全局模式 | 127.0.0.1:7877\n');
for (const r of sorted) {
  console.log([`[${r.code}]`.padEnd(4), r.why.padEnd(24), (r.line + ' ' + r.name).padEnd(30), String(r.ok ? r.status : 'ERR').padEnd(5), (r.ok ? r.elapsedMs + 'ms' : '').padEnd(9), 'bytes=' + String(r.bytes).padEnd(8), (r.title || r.error || '').slice(0, 48)].join(' | '));
}
const cnt = {};
for (const r of sorted) cnt[r.code] = (cnt[r.code] || 0) + 1;
console.log('\n统计: ' + JSON.stringify(cnt));

const lines = [];
lines.push('# 北美线 18 站点可访问性测试报告(经 Clash 代理)');
lines.push('');
lines.push(`测试时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })} (北京时间)`);
lines.push('');
lines.push('## 测试环境');
lines.push('');
lines.push('| 项目 | 值 |');
lines.push('|------|-----|');
lines.push('| 代理 | Clash Plus 混合端口 `127.0.0.1:7877`(HTTP CONNECT 隧道) |');
lines.push('| 出站模式 | global(全局) |');
lines.push('| 出口 IP | `209.126.8.142` — Contabo Inc., St. Louis, Missouri, US(机房 IP) |');
lines.push('| 客户端 | Node.js v24 内置 net/tls/http2,ALPN 协商 h2,Chrome 131 请求头 |');
lines.push(`| 超时/重试 | ${TIMEOUT / 1000}s / 2 次,并发 ${CONCURRENCY} |`);
lines.push('');
lines.push('## 结果总表');
lines.push('');
lines.push('| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 页面标题 |');
lines.push('|---|------|------|-----|------|------|------|----------|');
const esc = (s) => String(s || '').replace(/\|/g, '\\|');
sorted.forEach((r, i) => {
  lines.push(`| ${i + 1} | ${esc(r.line)} | ${esc(r.name)} | ${esc(r.url)} | ${r.code === 'O' ? '✅' : r.code === 'X' || r.code === 'D' || r.code === '?' ? '❌' : '⚠️'} ${esc(r.why)} | ${r.ok ? r.status : 'ERR'} | ${r.ok ? (r.elapsedMs / 1000).toFixed(1) + 's' : '-'} | ${esc(r.title)} |`);
});
lines.push('');
lines.push('## 明细');
lines.push('');
for (const r of sorted) {
  lines.push(`### [${r.code}] ${r.line} / ${r.name}`);
  lines.push(`- URL: ${r.url}`);
  if (r.redirected || (r.chain && r.chain.length > 1)) lines.push(`- 重定向链: ${r.chain.map((c) => c.status + ' ' + c.url).join(' → ')}`);
  lines.push(`- HTTP: ${r.ok ? r.status : '无响应'} | 耗时: ${r.ok ? r.elapsedMs + 'ms' : '-'} | ALPN: ${r.alpn || '-'} | 字节: ${r.bytes} | 可见文本: ${r.visibleLen}`);
  lines.push(`- 标题: ${r.title || '(空)'}`);
  if (r.error) lines.push(`- 错误: \`${r.error}\``);
  lines.push(`- 判定: ${r.why}`);
  if (r.snippet) lines.push(`- 可见文本开头: ${r.snippet}`);
  lines.push('');
}
fs.writeFileSync(path.join(root, 'proxy_final_report.md'), lines.join('\n'), 'utf8');
console.log('report -> proxy_final_report.md');
