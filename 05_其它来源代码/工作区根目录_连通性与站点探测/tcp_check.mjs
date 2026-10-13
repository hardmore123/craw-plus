import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import tls from 'node:tls';
import dns from 'node:dns/promises';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const sites = JSON.parse(fs.readFileSync(path.join(root, 'sites.json'), 'utf8'));

const TCP_TIMEOUT = 12000;

function tcpProbe(host, port) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    const sock = new net.Socket();
    let done = false;
    const finish = (ok, info) => {
      if (done) return;
      done = true;
      sock.destroy();
      resolve({ ok, ms: Date.now() - t0, info });
    };
    sock.setTimeout(TCP_TIMEOUT);
    sock.once('connect', () => finish(true, 'tcp-ok'));
    sock.once('timeout', () => finish(false, 'TCP 连接超时'));
    sock.once('error', (e) => finish(false, e.code || e.message));
    sock.connect(port, host);
  });
}

function tlsProbe(host, port, ip) {
  return new Promise((resolve) => {
    const t0 = Date.now();
    let done = false;
    const finish = (ok, info) => {
      if (done) return;
      done = true;
      try { sock.destroy(); } catch {}
      resolve({ ok, ms: Date.now() - t0, info });
    };
    const opts = { host, port, servername: host, rejectUnauthorized: false, timeout: TCP_TIMEOUT };
    if (ip) { opts.host = ip; }
    const sock = tls.connect(opts, () => {
      finish(true, 'TLS-ok proto=' + sock.getProtocol() + ' cipher=' + (sock.getCipher()?.name || ''));
    });
    sock.setTimeout(TCP_TIMEOUT);
    sock.once('timeout', () => finish(false, 'TLS 握手超时'));
    sock.once('error', (e) => finish(false, (e.code || e.message)));
  });
}

const out = [];
for (const s of sites) {
  const u = new URL(s.url);
  const host = u.hostname;
  let ips = [];
  let dnsErr = '';
  try {
    const r = await dns.lookup(host, { all: true });
    ips = r.map((x) => `${x.address}(v${x.family})`);
  } catch (e) { dnsErr = e.code || e.message; }

  const tcp = await tcpProbe(host, 443);
  const tcp80 = tcp.ok ? null : await tcpProbe(host, 80);
  const tlsr = tcp.ok ? await tlsProbe(host, 443) : { ok: false, ms: 0, info: 'TCP 未通,跳过' };

  out.push({ ...s, host, ips, dnsErr, tcp, tcp80, tls: tlsr });
  const mark = tcp.ok ? (tlsr.ok ? 'TCP+TLS OK ' : 'TCP OK/TLS 失败') : 'TCP 失败';
  console.log([mark.padEnd(16), (s.line + ' ' + s.name).padEnd(28), host.padEnd(28), 'tcp=' + String(tcp.ok).padEnd(5), (tcp.ms + 'ms').padEnd(8), tcp.ok ? '' : tcp.info, tlsr.ok ? tlsr.info : (tcp.ok ? tlsr.info : '')].join(' | '));
}

fs.writeFileSync(path.join(root, 'site_check_tcp.json'), JSON.stringify(out, null, 2), 'utf8');
console.log('\ntcp-fail=' + out.filter((r) => !r.tcp.ok).length + ' tls-fail=' + out.filter((r) => r.tcp.ok && !r.tls.ok).length + ' both-ok=' + out.filter((r) => r.tcp.ok && r.tls.ok).length);
