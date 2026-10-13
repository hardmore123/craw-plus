import net from 'node:net';
import tls from 'node:tls';
import https from 'node:https';

const PROXY_HOST = '127.0.0.1';
const PROXY_PORT = 7877;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

const targets = [
  ['北美线-美国', 'Best Buy', 'https://www.bestbuy.com'],
  ['北美线-墨西哥', 'Coppel', 'https://www.coppel.com/sd/TV'],
  ['北美线-加拿大', 'BestBuy', 'https://www.bestbuy.ca/en-ca'],
  ['北美线-加拿大', 'Canadian Tire', 'https://www.canadiantire.ca/en.html'],
  ['北美线-加拿大', 'Visions', 'https://www.visions.ca/'],
  ['北美线-墨西哥', 'Palacio', 'https://www.elpalaciodehierro.com/buscar?q=tv'],
  ['北美线-墨西哥', 'Sams', 'https://www.sams.com.mx/'],
  ['北美线-墨西哥', 'Walmart', 'https://www.walmart.com.mx/search?q=TV'],
  ['北美线-加拿大', 'Amazon', 'https://www.amazon.ca/'],
  ['北美线-美国', 'Amazon', 'https://www.amazon.com/'],
  ['北美线-墨西哥', 'Amazon', 'https://www.amazon.com.mx/'],
];

function stageConnect(host, port, timeoutMs) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const sock = net.connect({ host: PROXY_HOST, port: PROXY_PORT });
    let done = false;
    const fail = (e) => { if (done) return; done = true; sock.destroy(); reject(Object.assign(new Error(String(e.message || e)), { stage: 'TCP->代理', ms: Date.now() - t0 })); };
    sock.setTimeout(timeoutMs, () => fail(new Error('连接代理超时')));
    sock.once('error', fail);
    sock.once('connect', () => {
      sock.write(`CONNECT ${host}:${port} HTTP/1.1\r\nHost: ${host}:${port}\r\n\r\n`);
      let buf = Buffer.alloc(0);
      const onData = (d) => {
        buf = Buffer.concat([buf, d]);
        const idx = buf.indexOf('\r\n\r\n');
        if (idx === -1) return;
        sock.removeListener('data', onData);
        const line = buf.subarray(0, idx).toString('latin1').split('\r\n')[0];
        const m = line.match(/^HTTP\/\d\.\d\s+(\d{3})/);
        if (!m || m[1] !== '200') return fail(Object.assign(new Error('CONNECT ' + line), { stage: 'CONNECT' }));
        done = true;
        sock.setTimeout(0);
        resolve({ sock, ms: Date.now() - t0 });
      };
      sock.on('data', onData);
    });
  });
}

function stageTls(raw, host, timeoutMs) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    const t = tls.connect({ socket: raw, servername: host, rejectUnauthorized: false });
    let done = false;
    const fail = (e) => { if (done) return; done = true; try { t.destroy(); } catch {} reject(Object.assign(new Error(String(e.code || e.message)), { stage: 'TLS', ms: Date.now() - t0 })); };
    t.setTimeout(timeoutMs, () => fail(new Error('TLS 握手超时')));
    t.once('error', fail);
    t.once('secureConnect', () => { done = true; resolve({ tls: t, ms: Date.now() - t0, proto: t.getProtocol(), alpn: t.alpnProtocol }); });
  });
}

function stageHttp(sockOrTls, urlStr, isTls, timeoutMs) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlStr);
    const t0 = Date.now();
    const req = https.request(
      {
        host: u.hostname,
        port: 443,
        path: u.pathname + u.search,
        method: 'GET',
        createConnection: () => sockOrTls,
        agent: false,
        headers: {
          'user-agent': UA,
          accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
          'accept-language': 'en-US,en;q=0.9',
          'accept-encoding': 'identity',
        },
      },
      (res) => {
        let n = 0; const chunks = [];
        res.on('data', (d) => { if (n < 200000) { chunks.push(d); n += d.length; } });
        res.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf8');
          const title = (body.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1].replace(/\s+/g, ' ').trim().slice(0, 80);
          resolve({ status: res.statusCode, ms: Date.now() - t0, bytes: body.length, title, server: res.headers.server || '', body });
        });
        res.on('error', (e) => reject(Object.assign(new Error(String(e.code || e.message)), { stage: 'HTTP读取', ms: Date.now() - t0 })));
      }
    );
    req.setTimeout(timeoutMs, () => req.destroy(Object.assign(new Error('HTTP 响应超时'), { stage: 'HTTP等待' })));
    req.on('error', (e) => reject(Object.assign(new Error(String(e.code || e.message)), { stage: e.stage || 'HTTP', ms: Date.now() - t0 })));
    req.end();
  });
}

for (const [line, name, url] of targets) {
  const host = new URL(url).hostname;
  console.log('='.repeat(78));
  console.log(`${line} / ${name}   ${url}`);
  for (let attempt = 1; attempt <= 3; attempt++) {
    let raw = null, tlsSock = null;
    const parts = [];
    try {
      const c = await stageConnect(host, 443, 20000);
      raw = c.sock;
      parts.push(`CONNECT ${c.ms}ms`);
      const t = await stageTls(raw, host, 30000);
      tlsSock = t.tls;
      parts.push(`TLS ${t.ms}ms(${t.proto}${t.alpn ? '/' + t.alpn : ''})`);
      const r = await stageHttp(tlsSock, url, true, 45000);
      parts.push(`HTTP ${r.status} ${r.ms}ms ${r.bytes}B`);
      console.log(`  #${attempt}  ${parts.join('  |  ')}  title="${r.title}" server=${r.server}`);
      if (attempt === 1 && url.includes('amazon')) {
        console.log('        body: ' + r.body.replace(/\s+/g, ' ').slice(0, 200));
      }
      break;
    } catch (e) {
      parts.push(`${e.stage} FAIL: ${e.message}`);
      console.log(`  #${attempt}  ${parts.join('  |  ')}`);
      try { tlsSock?.destroy(); } catch {}
      try { raw?.destroy(); } catch {}
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
}
