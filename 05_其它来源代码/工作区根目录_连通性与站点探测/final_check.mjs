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
const TIMEOUT = 40000;
const CONCURRENCY = 5;
const CAP = 500 * 1024;
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
    req.on('end', () => {
      clearTimeout(timer);
      try { client.close(); } catch {}
      resolve({ status, headers, body: Buffer.concat(chunks).toString('utf8') });
    });
    req.end();
  });
}

function fetchH1(t, u, timeoutMs) {
  return new Promise((resolve, reject) => {
    const req = https.request(
      { host: u.hostname, port: 443, path: u.pathname + u.search, method: 'GET', agent: false, createConnection: () => t, headers: COMMON },
      (res) => {
        const chunks = []; let n = 0;
        res.on('data', (d) => { if (n < CAP) { chunks.push(d); n += d.length; } });
        res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString('utf8') }));
        res.on('error', reject);
      }
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error('HTTP/1.1 响应超时')));
    req.on('error', (e) => reject(new Error('HTTP/1.1 ' + (e.code || e.message))));
    req.end();
  });
}

function classify(status, body) {
  const b = (body || '').slice(0, 30000);
  if (/Just a moment|cf-browser-verification|Attention Required|Enable JavaScript and cookies to continue|Checking your browser/i.test(b)) return 'CF_CHALLENGE';
  if (/blocked - redirecting|Verifica tu identidad|Verify Your Identity|unusual traffic/i.test(b)) return 'BOT_CHECK';
  if (/challenge-container|AwsWafIntegration|aws-waf-token|window\.awsWaf/i.test(b) || (status === 202 && b.length < 5000)) return 'AWS_WAF';
  if (/Access Denied|You don't have permission to access/i.test(b)) return 'ACCESS_DENIED';
  if (/captcha|Robot Check|Enter the characters you see/i.test(b)) return 'CAPTCHA';
  return null;
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
    chain.push({ url, status: r.status });
    const loc = r.headers.location;
    if ([301, 302, 303, 307, 308].includes(r.status) && loc) {
      url = new URL(loc, url).href;
      continue;
    }
    return { ...r, title, finalUrl: url, chain, reason: classify(r.status, r.body) };
  }
  throw new Error('重定向次数过多');
}

async function check(site) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    const t0 = Date.now();
    try {
      const r = await visit(site.url);
      return {
        ...site, ok: true, status: r.status, elapsedMs: Date.now() - t0,
        finalUrl: r.finalUrl, alpn: r.alpn, bytes: r.body.length, title: r.title,
        chain: r.chain, reason: r.reason, error: '',
        server: r.headers.server || '',
      };
    } catch (e) {
      if (attempt === 2) return { ...site, ok: false, status: 0, elapsedMs: Date.now() - t0, finalUrl: '', alpn: '', bytes: 0, title: '', chain: [], reason: null, error: String(e.message || e).slice(0, 160), server: '' };
      await new Promise((r) => setTimeout(r, 1200));
    }
  }
}

const results = new Array(sites.length);
let idx = 0;
await Promise.all(Array.from({ length: CONCURRENCY }, async () => {
  while (idx < sites.length) { const i = idx++; results[i] = await check(sites[i]); }
}));
fs.writeFileSync(path.join(root, 'proxy_h2_result.json'), JSON.stringify(results, null, 2), 'utf8');

const verdict = (r) => {
  if (!r.ok) return { k: 'X', t: '不可达' };
  if (r.reason === 'CF_CHALLENGE') return { k: 'C', t: 'Cloudflare 人机验证' };
  if (r.reason === 'BOT_CHECK') return { k: 'B', t: '风控跳转(身份验证)' };
  if (r.reason === 'AWS_WAF') return { k: 'A', t: 'AWS WAF 挑战(202)' };
  if (r.reason === 'ACCESS_DENIED') return { k: 'D', t: '访问被拒绝' };
  if (r.reason === 'CAPTCHA') return { k: 'K', t: '验证码页' };
  if (r.status >= 200 && r.status < 300) return { k: 'O', t: '正常访问' };
  return { k: '?', t: '异常 ' + r.status };
};

const order = { O: 0, A: 1, C: 2, B: 3, D: 4, K: 5, '?': 6, X: 7 };
const sorted = [...results].sort((a, b) => order[verdict(a).k] - order[verdict(b).k] || a.line.localeCompare(b.line) || a.name.localeCompare(b.name));

console.log('=== 经 Clash 代理(HTTP/2 浏览器化客户端)最终结果 ===');
console.log('出口 IP: Contabo US 机房 (209.126.8.142) | Clash 全局模式 | 127.0.0.1:7877\n');
for (const r of sorted) {
  const v = verdict(r);
  console.log([`[${v.k}]`.padEnd(4), v.t.padEnd(20), (r.line + ' ' + r.name).padEnd(30), String(r.ok ? r.status : 'ERR').padEnd(5), (r.ok ? r.elapsedMs + 'ms' : '').padEnd(9), (r.title || r.error || '').slice(0, 55)].join(' | '));
}
const cnt = {};
for (const r of sorted) { const k = verdict(r).k; cnt[k] = (cnt[k] || 0) + 1; }
console.log('\n统计: ' + JSON.stringify(cnt));
fs.writeFileSync(path.join(root, 'proxy_h2_summary.json'), JSON.stringify({ exitIp: '209.126.8.142 (Contabo, US)', counts: cnt, results: sorted.map((r) => ({ line: r.line, name: r.name, url: r.url, verdict: verdict(r).t, status: r.status, ok: r.ok, ms: r.elapsedMs, title: r.title, finalUrl: r.finalUrl, error: r.error })) }, null, 2), 'utf8');
