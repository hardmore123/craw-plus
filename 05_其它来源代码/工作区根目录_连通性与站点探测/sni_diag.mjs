import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns/promises';

const TIMEOUT = 10000;

function tlsProbe(ip, servername, label) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    let done = false;
    let sock;
    const finish = (ok, info) => {
      if (done) return;
      done = true;
      try { sock.destroy(); } catch {}
      resolve({ label, ok, ms: Date.now() - t0, info });
    };
    const opts = { host: ip, port: 443, rejectUnauthorized: false, timeout: TIMEOUT };
    if (servername) opts.servername = servername;
    sock = tls.connect(opts, () => {
      const cert = sock.getPeerCertificate();
      finish(true, `握手成功 proto=${sock.getProtocol()} 证书CN=${cert?.subject?.CN || '?'}`);
    });
    sock.setTimeout(TIMEOUT, () => finish(false, 'TLS 握手超时(ClientHello 被丢弃)'));
    sock.once('error', (e) => finish(false, `TLS 层响应: ${e.code || e.message}`));
  });
}

function httpProbe(ip, host, servername) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    let done = false;
    let sock;
    const finish = (ok, info) => {
      if (done) return;
      done = true;
      try { sock.destroy(); } catch {}
      resolve({ ok, ms: Date.now() - t0, info });
    };
    sock = net.connect({ host: ip, port: 80 }, () => {
      sock.write(`GET / HTTP/1.1\r\nHost: ${host}\r\nUser-Agent: Mozilla/5.0\r\nConnection: close\r\n\r\n`);
    });
    let buf = '';
    sock.setTimeout(TIMEOUT, () => finish(false, '无响应/超时'));
    sock.on('data', (d) => {
      buf += d.toString('latin1');
      if (buf.includes('\r\n\r\n') || buf.length > 4096) finish(true, buf.split('\r\n')[0]);
    });
    sock.once('error', (e) => finish(false, e.code || e.message));
    sock.once('end', () => { if (!done) finish(buf.length > 0, buf.split('\r\n')[0] || '空响应'); });
  });
}

const targets = [
  ['www.bestbuy.com', 'Best Buy US'],
  ['www.walmart.com', 'Walmart US'],
  ['www.costco.com', 'Costco US'],
  ['www.canadiantire.ca', 'Canadian Tire'],
  ['www.visions.ca', 'Visions'],
  ['www.coppel.com', 'Coppel'],
];

console.log('=== SNI 对比实验:同一 IP,分别用真实 SNI / 良性 SNI / 无 SNI ===\n');
for (const [host, label] of targets) {
  const r = await dns.lookup(host, { all: true });
  const ip = r[0].address;
  console.log(`--- ${label}  ${host}  ->  ${ip}`);
  const a = await tlsProbe(ip, host, '真实SNI=' + host);
  console.log(`    [真实SNI ] ${a.ok ? 'OK  ' : 'FAIL'} ${String(a.ms).padStart(6)}ms  ${a.info}`);
  const b = await tlsProbe(ip, 'www.amazon.com', '良性SNI=www.amazon.com');
  console.log(`    [良性SNI ] ${b.ok ? 'OK  ' : 'FAIL'} ${String(b.ms).padStart(6)}ms  ${b.info}`);
  const c = await tlsProbe(ip, null, '无SNI');
  console.log(`    [无SNI   ] ${c.ok ? 'OK  ' : 'FAIL'} ${String(c.ms).padStart(6)}ms  ${c.info}`);
  const h = await httpProbe(ip, host);
  console.log(`    [明文HTTP] ${h.ok ? 'OK  ' : 'FAIL'} ${String(h.ms).padStart(6)}ms  ${h.info}`);
  console.log('');
}

console.log('=== 对照:已知可访问站点换用被阻断的 SNI ===\n');
const ctrl = await dns.lookup('www.amazon.com', { all: true });
const cip = ctrl[0].address;
const c1 = await tlsProbe(cip, 'www.amazon.com', '真实SNI');
console.log(`--- www.amazon.com -> ${cip}`);
console.log(`    [真实SNI=www.amazon.com  ] ${c1.ok ? 'OK' : 'FAIL'} ${c1.ms}ms ${c1.info}`);
const c2 = await tlsProbe(cip, 'www.walmart.com', '替换SNI=www.walmart.com');
console.log(`    [替换SNI=www.walmart.com] ${c2.ok ? 'OK' : 'FAIL'} ${c2.ms}ms ${c2.info}`);
