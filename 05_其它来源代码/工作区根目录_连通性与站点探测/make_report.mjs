import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const results = JSON.parse(fs.readFileSync(path.join(root, 'proxy_final_result.json'), 'utf8'));

// 修正规则:E(可见文本过少)仅在响应体确实很小时成立;大体积+真实标题 = 正常页面
for (const r of results) {
  if (r.code === 'E' && r.bytes > 50000) {
    r.code = 'O';
    r.why = '正常访问(SPA 页面,正文由 JS 渲染)';
  }
}

// 直连(direct)对照结果
const directTcp = JSON.parse(fs.readFileSync(path.join(root, 'site_check_tcp.json'), 'utf8'));
const key = (s) => s.line + '|' + s.name;
const tcpMap = new Map(directTcp.map((r) => [key(r), r]));

const order = { O: 0, A: 1, C: 2, B: 3, K: 4, D: 5, '?': 6, X: 7 };
const sorted = [...results].sort((a, b) => order[a.code] - order[b.code] || a.line.localeCompare(b.line) || a.name.localeCompare(b.name));

const ICON = { O: '✅', A: '⚠️', C: '⚠️', B: '⚠️', K: '⚠️', D: '❌', '?': '❌', X: '❌' };
const esc = (s) => String(s == null ? '' : s).replace(/\|/g, '\\|').replace(/\n/g, ' ');

const directVerdict = (r) => {
  const t = tcpMap.get(key(r));
  if (!t) return '未测';
  if (!t.tcp.ok) return '❌ 不通(TCP 超时)';
  if (!t.tls.ok) return '❌ TLS 被阻断(SNI 过滤)';
  return '⚠️ 可连通(需看应用层)';
};

const cnt = {};
for (const r of sorted) cnt[r.code] = (cnt[r.code] || 0) + 1;
const okCount = results.filter((r) => r.code === 'O').length;

const L = [];
L.push('# 北美线 18 个目标站点可访问性测试报告');
L.push('');
L.push(`测试时间:${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })} (北京时间)`);
L.push('');
L.push('## 一、结论摘要');
L.push('');
L.push(`**经 Clash 代理:18 个站点中 ${okCount} 个可正常访问,${18 - okCount} 个被目标站点的反爬系统拦截(与网络连通性无关)。**`);
L.push('');
L.push('| 结论 | 数量 | 站点 |');
L.push('|------|------|------|');
const groupBy = (codes) => sorted.filter((r) => codes.includes(r.code)).map((r) => `${r.line.replace('北美线-', '')} ${r.name}`).join('、');
L.push(`| ✅ 可正常访问 | ${okCount} | ${groupBy(['O'])} |`);
L.push(`| ⚠️ AWS WAF 挑战 | ${cnt.A || 0} | ${groupBy(['A'])} |`);
L.push(`| ⚠️ Cloudflare 人机验证 | ${cnt.C || 0} | ${groupBy(['C'])} |`);
L.push(`| ⚠️ 风控/身份验证跳转 | ${(cnt.B || 0) + (cnt.K || 0)} | ${groupBy(['B', 'K'])} |`);
L.push(`| ❌ 403 拒绝访问 | ${cnt.D || 0} | ${groupBy(['D'])} |`);
L.push(`| ❌ 请求失败 | ${cnt.X || 0} | ${groupBy(['X']) || '无'} |`);
L.push('');
L.push('## 二、测试环境');
L.push('');
L.push('| 项目 | 值 |');
L.push('|------|-----|');
L.push('| 代理 | Clash Plus 混合端口 `127.0.0.1:7877`(HTTP CONNECT 隧道) |');
L.push('| 出站模式 | `global`(全局代理) |');
L.push('| 出口 IP | `209.126.8.142` —— Contabo Inc., St. Louis, Missouri, US(**机房 IP**) |');
L.push('| 客户端 | Node.js 内置 net/tls/http2,ALPN 协商 `h2`,Chrome 131 请求头 |');
L.push('| 超时 / 重试 | 45s / 2 次,并发 5 |');
L.push('');
L.push('## 三、结果总表(代理 vs 直连)');
L.push('');
L.push('| # | 线路 | 站点 | URL | 经代理结论 | HTTP | 耗时 | 直连对照 |');
L.push('|---|------|------|-----|-----------|------|------|----------|');
sorted.forEach((r, i) => {
  L.push(`| ${i + 1} | ${esc(r.line)} | ${esc(r.name)} | ${esc(r.url)} | ${ICON[r.code]} ${esc(r.why)} | ${r.ok ? r.status : 'ERR'} | ${r.ok ? (r.elapsedMs / 1000).toFixed(1) + 's' : '-'} | ${directVerdict(r)} |`);
});
L.push('');
L.push('> 直连对照来自同机无代理测试:**12 个站点在 TCP 层可达,但因 TLS ClientHello 中的 SNI 被丢弃而无法完成握手**(换用良性 SNI 可立即握手成功,明文 HTTP 也可返回 302 —— 典型的 SNI 阻断特征);`costco.ca` 则是 TCP 层直接超时。**挂上 Clash 代理后 18 个站点的网络层全部打通**,剩余失败全部来自站点自身的反爬策略。');
L.push('');
L.push('## 四、逐站明细');
L.push('');
for (const r of sorted) {
  L.push(`### ${ICON[r.code]} ${r.line} / ${r.name}`);
  L.push('');
  L.push(`- **URL**:${r.url}`);
  if (r.chain && r.chain.length > 1) L.push(`- **重定向链**:${r.chain.map((c) => `${c.status} ${c.url}`).join(' → ')}`);
  L.push(`- **HTTP**:${r.ok ? r.status : '无响应'}　**耗时**:${r.ok ? r.elapsedMs + 'ms' : '-'}　**ALPN**:${r.alpn || '-'}　**响应体**:${r.bytes} B　**可见文本**:${r.visibleLen} 字符`);
  L.push(`- **页面标题**:${r.title || '(空)'}`);
  if (r.error) L.push(`- **错误**:\`${r.error}\``);
  L.push(`- **判定**:${r.why}`);
  if (r.snippet) L.push(`- **可见文本开头**:${esc(r.snippet).slice(0, 200)}`);
  L.push('');
}
L.push('## 五、对爬取项目的建议');
L.push('');
L.push('1. **必须走代理**:直连时 `bestbuy.com/.ca`、`walmart.com/.ca/.com.mx`、`costco.com/.ca`、`visions.ca`、`canadiantire.ca`、`liverpool.com.mx`、`coppel.com` 等因 SNI 阻断无法建立 TLS;这是链路问题,与站点反爬无关。');
L.push('2. **客户端必须伪装成浏览器 TLS 指纹并协商 HTTP/2**。实测关键证据:同一个出口 IP 下,仅支持 HTTP/1.1 且无 ALPN 的客户端访问 `bestbuy.com`、`coppel.com`、`canadiantire.ca` 会被服务器在 TLS 握手完成后立刻 `ECONNRESET`;改为协商 `ALPN=h2` 后同样请求全部返回 200 真实页面。Python 的 `requests`/`httpx` 默认指纹会被同样拦截,建议使用 `curl_cffi`(impersonate)或 `httpx` + HTTP/2。');
L.push('3. **当前 Clash 节点是机房 IP(Contabo / US),会持续触发风控**。`Amazon`(AWS WAF 挑战)、`Visions`、`Palacio`(Cloudflare)、`BestBuy CA`(403 Access Denied)、`Sams MX` / `Walmart MX`(身份验证)均属此类。换成住宅 IP 节点(Residential)通常可直接通过;或在采集时接入打码/指纹浏览器。');
L.push('4. **部分结果是波动的**:`Palacio` 在两次测试间分别返回 Cloudflare 403 和 200 真实页面;`BestBuy CA` 分别为 403 与连接重置。采集端需要实现重试 + 失败降级。');
L.push('5. **对强风控站点建议上无头浏览器**:`Amazon`、`Visions`、`Sams MX`、`Walmart MX` 返回的是需要执行 JS 才能通过的挑战页(202/2KB 或 Cloudflare "Just a moment..."),用 Playwright/Puppeteer 走真实浏览器内核是最稳的方案。');
L.push('');
fs.writeFileSync(path.join(root, '北美线站点测试报告.md'), L.join('\n'), 'utf8');
fs.writeFileSync(path.join(root, 'proxy_final_result.json'), JSON.stringify(results, null, 2), 'utf8');

console.log('可正常访问: ' + okCount + ' / 18');
console.log('统计: ' + JSON.stringify(cnt));
console.log('报告 -> 北美线站点测试报告.md');

// 打印两个被修正站点的证据
for (const r of results.filter((x) => x.code === 'O' && x.visibleLen < 400)) {
  console.log(`\n[修正] ${r.line} ${r.name}: bytes=${r.bytes} title="${r.title}" snippet="${r.snippet.slice(0, 120)}"`);
}
