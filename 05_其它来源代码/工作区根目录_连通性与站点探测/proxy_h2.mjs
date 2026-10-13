import net from 'node:net';
import tls from 'node:tls';
import http2 from 'node:http2';
import { once } from 'node:events';

const PH = '127.0.0.1', PP = 7877;
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function connectViaProxy(host, port) {
  return new Promise((resolve, reject) => {
    const sock = net.connect({ host: PH, port: PP });
    let done = false;
    const fail = (e) => { if (done) return; done = true; sock.destroy(); reject(new Error(String(e.message || e))); };
    sock.setTimeout(15000, () => fail(new Error('代理 CONNECT 超时')));
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
        if (!/ 200 /.test(line)) return fail(new Error('CONNECT ' + line));
        done = true; sock.setTimeout(0); resolve(sock);
      };
      sock.on('data', onData);
    });
  });
}

const targets = [
  ['美国 Best Buy', 'https://www.bestbuy.com/'],
  ['加拿大 BestBuy', 'https://www.bestbuy.ca/en-ca'],
  ['加拿大 Canadian Tire', 'https://www.canadiantire.ca/en.html'],
  ['加拿大 Visions', 'https://www.visions.ca/'],
  ['墨西哥 Coppel', 'https://www.coppel.com/sd/TV'],
  ['墨西哥 Walmart', 'https://www.walmart.com.mx/search?q=TV'],
  ['墨西哥 Sams', 'https://www.sams.com.mx/'],
  ['美国 Walmart(对照)', 'https://www.walmart.com/'],
  ['加拿大 Costco(对照)', 'https://www.costco.ca/'],
];

for (const [name, url] of targets) {
  const u = new URL(url);
  const host = u.hostname;
  process.stdout.write(`\n${'='.repeat(70)}\n${name}  ${url}\n`);
  let raw, t;
  try {
    raw = await connectViaProxy(host, 443);
    t = tls.connect({ socket: raw, servername: host, ALPNProtocols: ['h2', 'http/1.1'], rejectUnauthorized: false });
    await once(t, 'secureConnect');
    console.log(`  TLS ok  ALPN=${t.alpnProtocol || '(none)'}  proto=${t.getProtocol()}`);
  } catch (e) {
    console.log('  TLS 失败: ' + e.message);
    continue;
  }

  if (t.alpnProtocol === 'h2') {
    try {
      const client = http2.connect(`https://${host}:443`, { createConnection: () => t });
      client.on('error', () => {});
      const req = client.request({
        ':method': 'GET',
        ':path': u.pathname + u.search,
        ':authority': host,
        ':scheme': 'https',
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
      });
      let n = 0; const chunks = [];
      req.on('response', (h) => console.log('  HTTP/2 状态: ' + h[':status'] + '  server=' + (h.server || '-')));
      req.on('data', (d) => { if (n < 300000) { chunks.push(d); n += d.length; } });
      req.on('error', (e) => console.log('  HTTP/2 流错误: ' + (e.code || e.message)));
      req.end();
      await Promise.race([once(req, 'end'), new Promise((r) => setTimeout(r, 25000))]);
      const body = Buffer.concat(chunks).toString('utf8');
      const title = (body.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [, ''])[1].replace(/\s+/g, ' ').trim().slice(0, 90);
      console.log(`  收到 ${body.length}B  title="${title}"`);
      console.log('  片段: ' + body.replace(/\s+/g, ' ').slice(0, 160));
      client.close();
    } catch (e) {
      console.log('  HTTP/2 异常: ' + e.message);
    }
  } else {
    console.log('  未协商到 h2,跳过');
  }
  try { t.destroy(); } catch {}
}
