import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import tls from 'node:tls';
import https from 'node:https';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const sites = JSON.parse(fs.readFileSync(path.join(root, 'sites.json'), 'utf8'));

const PROXY_HOST = process.env.CLASH_HOST || '127.0.0.1';
const PROXY_PORT = Number(process.env.CLASH_PORT || 7877);
const TIMEOUT_MS = 40000;
const CONNECT_TIMEOUT = 15000;
const CONCURRENCY = 5;
const ATTEMPTS = 2;
const CAP = 400 * 1024;

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function connectViaProxy(targetHost, targetPort) {
  return new Promise((resolve, reject) => {
    const sock = net.connect({ host: PROXY_HOST, port: PROXY_PORT });
    let done = false;
    const fail = (e) => { if (done) return; done = true; sock.destroy(); reject(e instanceof Error ? e : new Error(String(e))); };
    sock.setTimeout(CONNECT_TIMEOUT, () => fail(new Error(`代理 CONNECT 超时 (${PROXY_HOST}:${PROXY_PORT})`)));
    sock.once('error', fail);
    sock.once('connect', () => {
      sock.write(`CONNECT ${targetHost}:${targetPort} HTTP/1.1\r\nHost: ${targetHost}:${targetPort}\r\nProxy-Connection: keep-alive\r\n\r\n`);
      let buf = Buffer.alloc(0);
      const onData = (d) => {
        buf = Buffer.concat([buf, d]);
        const idx = buf.indexOf('\r\n\r\n');
        if (idx === -1) { if (buf.length > 16384) fail(new Error('代理响应异常')); return; }
        sock.removeListener('data', onData);
        const head = buf.subarray(0, idx).toString('latin1');
        const statusLine = head.split('\r\n')[0];
        const m = statusLine.match(/^HTTP\/\d\.\d\s+(\d{3})/);
        if (!m) return fail(new Error('代理响应无法解析: ' + statusLine));
        if (m[1] !== '200') return fail(new Error('代理拒绝 CONNECT: ' + statusLine));
        done = true;
        sock.setTimeout(0);
        resolve(sock);
      };
      sock.on('data', onData);
    });
  });
}

function httpsViaProxy(urlStr, timeoutMs) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const port = Number(u.port || 443);
    const agent = new https.Agent({ keepAlive: false });
    agent.createConnection = (opts, cb) => {
      connectViaProxy(opts.host, opts.port || 443).then(
        (raw) => {
          raw.setNoDelay(true);
          const t = tls.connect({ socket: raw, servername: opts.host, rejectUnauthorized: false });
          t.once('secureConnect', () => cb(null, t));
          t.once('error', (e) => cb(e));
        },
        (e) => cb(e)
      );
    };
    const req = https.request(
      {
        host: u.hostname,
        port,
        path: u.pathname + u.search,
        method: 'GET',
        agent,
        headers: {
          'user-agent': UA,
          accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
          'accept-language': 'en-US,en;q=0.9',
          'accept-encoding': 'identity',
        },
      },
      (res) => {
        const chunks = [];
        let size = 0;
        res.on('data', (d) => { if (size < CAP) { chunks.push(d); size += d.length; } });
        res.on('end', () =>
          resolve({
            status: res.statusCode,
            statusText: res.statusMessage,
            headers: res.headers,
            body: Buffer.concat(chunks).toString('utf8'),
            finalUrl: urlStr,
          })
        );
        res.on('error', reject);
      }
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`请求超时 > ${timeoutMs}ms`)));
    req.on('error', reject);
    req.end();
  });
}

function extractTitle(html) {
  const m = (html || '').match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  return m ? m[1].replace(/\s+/g, ' ').trim().slice(0, 120) : '';
}

async function fetchFollowing(url, timeoutMs) {
  let cur = url;
  const chain = [];
  for (let i = 0; i < 8; i++) {
    const r = await httpsViaProxy(cur, timeoutMs);
    chain.push({ url: cur, status: r.status });
    if ([301, 302, 303, 307, 308].includes(r.status)) {
      const loc = r.headers.location;
      if (!loc) return { ...r, chain };
      cur = new URL(loc, cur).href;
      continue;
    }
    return { ...r, chain };
  }
  throw new Error('重定向次数过多');
}

async function check(site) {
  let lastErr = null;
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    const t0 = Date.now();
    try {
      const r = await fetchFollowing(site.url, TIMEOUT_MS);
      const headers = {};
      for (const k of ['server', 'content-type', 'content-length', 'location', 'cf-mitigated', 'x-amzn-waf-action']) {
        const v = r.headers[k];
        if (v) headers[k] = String(v).slice(0, 120);
      }
      const bodyText = r.body || '';
      return {
        ...site, ok: true, status: r.status, statusText: r.statusText,
        elapsedMs: Date.now() - t0, finalUrl: r.finalUrl,
        redirected: r.finalUrl.replace(/\/$/, '') !== site.url.replace(/\/$/, ''),
        bytes: bodyText.length, title: extractTitle(bodyText),
        headers, chain: r.chain, attempts: attempt, error: '',
        blocked: /captcha|cf-browser-verification|Just a moment|Attention Required|Verify Your Identity|Access Denied|Robot Check/i.test(bodyText.slice(0, 20000)),
      };
    } catch (e) {
      lastErr = e;
      if (attempt < ATTEMPTS) await new Promise((r) => setTimeout(r, 1500));
    }
  }
  const cause = lastErr?.cause;
  let msg = lastErr?.message || String(lastErr);
  if (cause?.code) msg = `${cause.code}: ${cause.message || ''}`.trim();
  return {
    ...site, ok: false, status: 0, statusText: '', elapsedMs: 0, finalUrl: '',
    redirected: false, bytes: 0, title: '', headers: {}, chain: [],
    attempts: ATTEMPTS, error: msg.slice(0, 200), blocked: false,
  };
}

// ---------- 出口 IP 校验 ----------
async function exitIp() {
  for (const u of ['https://api.ipify.org/?format=json', 'https://ipinfo.io/json']) {
    try {
      const r = await fetchFollowing(u, 20000);
      return r.body.replace(/\s+/g, ' ').slice(0, 300);
    } catch { /* try next */ }
  }
  return '(出口 IP 查询失败)';
}

console.log(`代理: ${PROXY_HOST}:${PROXY_PORT}`);
const exitIpCache = await exitIp();
console.log('出口 IP: ' + exitIpCache);
console.log('');

// ---------- 并发测试 ----------
const results = new Array(sites.length);
let idx = 0;
async function worker() {
  while (idx < sites.length) {
    const i = idx++;
    results[i] = await check(sites[i]);
  }
}
await Promise.all(Array.from({ length: CONCURRENCY }, worker));

fs.writeFileSync(path.join(root, 'proxy_check_result.json'), JSON.stringify(results, null, 2), 'utf8');

const rank = (r) => (!r.ok ? 5 : r.status >= 200 && r.status < 300 ? 0 : r.status === 403 || r.status === 429 ? 2 : 3);
const verdict = (r) => {
  if (!r.ok) return 'X 失败';
  if (r.status >= 200 && r.status < 300) return r.blocked ? '△ 200 但疑似风控页' : 'O 可访问';
  if (r.status === 403 || r.status === 429) return '△ 被拒 ' + r.status;
  return '? 异常 ' + r.status;
};

const sorted = [...results].sort((a, b) => rank(a) - rank(b) || a.line.localeCompare(b.line) || a.name.localeCompare(b.name));

const lines = [];
lines.push('# 北美线站点可访问性测试报告(经 Clash 代理)');
lines.push('');
lines.push(`测试时间: ${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })} (北京时间)`);
lines.push('');
lines.push(`- 代理: \`http://${PROXY_HOST}:${PROXY_PORT}\` (Clash 混合端口,HTTP CONNECT 隧道)`);
lines.push(`- 方式: Node.js ${process.version} 内置 net/tls/https 手工建隧道,超时 ${TIMEOUT_MS / 1000}s,失败重试 ${ATTEMPTS} 次,并发 ${CONCURRENCY},跟随重定向`);
lines.push(`- 出口 IP: \`${exitIpCache}\``);
lines.push('');
lines.push('| # | 线路 | 站点 | URL | 结论 | HTTP | 耗时 | 跳转后最终地址 | 页面标题 |');
lines.push('|---|------|------|-----|------|------|------|----------------|----------|');
const esc = (s) => String(s || '').replace(/\|/g, '\\|');
sorted.forEach((r, i) => {
  const t = r.ok ? (r.elapsedMs / 1000).toFixed(2) + 's' : '-';
  lines.push(`| ${i + 1} | ${esc(r.line)} | ${esc(r.name)} | ${esc(r.url)} | ${verdict(r)} | ${r.ok ? r.status : 'ERR'} | ${t} | ${esc(r.redirected ? r.finalUrl : '')} | ${esc(r.title)} |`);
});
lines.push('');
lines.push('## 明细');
lines.push('');
for (const r of sorted) {
  lines.push(`### ${r.line} / ${r.name}`);
  lines.push(`- URL: ${r.url}`);
  lines.push(`- 结论: ${verdict(r)}`);
  lines.push(`- HTTP: ${r.ok ? r.status + ' ' + r.statusText : '无响应'}   耗时: ${r.ok ? r.elapsedMs + 'ms' : '-'}   字节: ${r.bytes}`);
  if (r.redirected) lines.push(`- 最终地址: ${r.finalUrl}`);
  if (r.chain?.length > 1) lines.push(`- 重定向链: ${r.chain.map((c) => c.status + ' ' + c.url).join('  ->  ')}`);
  if (r.error) lines.push(`- 错误: \`${r.error}\``);
  if (r.title) lines.push(`- 标题: ${r.title}`);
  if (Object.keys(r.headers).length) lines.push(`- 响应头: ${Object.entries(r.headers).map(([k, v]) => `${k}=${v}`).join('; ')}`);
  lines.push('');
}
fs.writeFileSync(path.join(root, 'proxy_check_report.md'), lines.join('\n'), 'utf8');

console.log('=== 结果汇总 ===');
for (const r of sorted) {
  console.log([verdict(r).padEnd(18), (r.line + ' ' + r.name).padEnd(30), String(r.ok ? r.status : 'ERR').padEnd(5), (r.ok ? r.elapsedMs + 'ms' : '').padEnd(9), (r.error || r.title || '').slice(0, 60)].join(' | '));
}
console.log('');
console.log('total=' + results.length);
console.log('ok=' + results.filter((r) => r.ok && r.status >= 200 && r.status < 300 && !r.blocked).length);
console.log('blocked/challenge=' + results.filter((r) => r.ok && (r.blocked || [401, 403, 429].includes(r.status))).length);
console.log('failed=' + results.filter((r) => !r.ok).length);
