#!/usr/bin/env node
/**
 * DSH 会话日志读取器 —— 直接分析 session.v3.jsonl.zstd，无需启动 dsh。
 *
 * 为什么需要它：DSH 的会话日志是**多帧 zstd**（每次追加写一帧），
 * Node 的 zlib.zstdDecompressSync 默认只解第一帧，会得到几乎空的输出。
 * 本脚本按 zstd 魔数切帧逐帧解压，拼出完整事件流。
 *
 * 用法:
 *   node dsh_session_log.js <session.v3.jsonl.zstd> [关键词]
 *
 * 无关键词时打印事件类型分布 + 压缩/命令/模型/token 概览。
 * 带关键词时额外打印含该词的最近事件。
 */
const fs = require('fs');
const zlib = require('zlib');

const file = process.argv[2];
const keyword = process.argv[3];
if (!file) {
  console.error('用法: node dsh_session_log.js <session.v3.jsonl.zstd> [关键词]');
  process.exit(2);
}

function decompressAll(buf) {
  const MAGIC = [0x28, 0xb5, 0x2f, 0xfd];
  const offs = [];
  for (let i = 0; i + 4 <= buf.length; i++) {
    if (buf[i] === MAGIC[0] && buf[i + 1] === MAGIC[1] && buf[i + 2] === MAGIC[2] && buf[i + 3] === MAGIC[3]) offs.push(i);
  }
  let text = '', ok = 0, bad = 0;
  for (let k = 0; k < offs.length; k++) {
    const s = offs[k], e = k + 1 < offs.length ? offs[k + 1] : buf.length;
    try { text += zlib.zstdDecompressSync(buf.subarray(s, e)).toString('utf8'); ok++; }
    catch { bad++; }
  }
  return { text, frames: offs.length, ok, bad };
}

const buf = fs.readFileSync(file);
const { text, frames, ok, bad } = decompressAll(buf);
const evs = [];
for (const ln of text.split('\n').filter(Boolean)) {
  try { evs.push(JSON.parse(ln)); } catch { /* header 等非 JSON 行 */ }
}

const ts = (ms) => (ms ? new Date(ms).toLocaleString('zh-CN', { hour12: false }) : '?');

const head = evs.find(e => e.type === 'session');
console.log(`文件: ${file}`);
console.log(`zstd 帧 ${frames}（解压 ${ok} / 跳过 ${bad}）→ ${(text.length / 1048576).toFixed(2)} MB, ${evs.length} 个事件`);
if (head) console.log(`会话: ${head.id}  preset=${head.agentPreset}  cwd=${head.cwd}  创建=${ts(head.createdAt)}`);

const kinds = {};
for (const e of evs) kinds[e.type] = (kinds[e.type] || 0) + 1;
console.log('\n=== 事件类型 Top 20 ===');
Object.entries(kinds).sort((a, b) => b[1] - a[1]).slice(0, 20)
  .forEach(([k, v]) => console.log(`  ${k.padEnd(32)} ${v}`));

// 压缩健康度
const cStart = evs.filter(e => e.type === 'compaction/start');
const cEnd = evs.filter(e => e.type === 'compaction/end');
const cSum = evs.filter(e => e.type === 'compaction/summary');
console.log('\n=== 压缩健康度 ===');
console.log(`  start=${cStart.length}  end=${cEnd.length}  summary=${cSum.length}`);
const errs = {};
for (const e of cEnd) {
  const k = (e.data || {}).error ? String(e.data.error).slice(0, 120) : '(成功)';
  errs[k] = (errs[k] || 0) + 1;
}
Object.entries(errs).sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log(`    x${String(v).padStart(3)} ${k}`));

// 模型路由
console.log('\n=== 模型路由（request/context）===');
const seen = new Set();
for (const e of evs.filter(e => e.type === 'request/context')) {
  const d = e.data || {};
  const key = `${d.provider}/${d.model} window=${d.contextWindow}`;
  if (!seen.has(key)) { seen.add(key); console.log(`  ${key}`); }
}

// token 用量
const us = evs.filter(e => e.type === 'assistant/message' && (e.data || {}).usage).slice(-3);
if (us.length) {
  console.log('\n=== 最近 token 用量 ===');
  us.forEach(e => console.log(`  ${ts(e.time)} ${JSON.stringify(e.data.usage)}`));
}

// 命令
const cmds = evs.filter(e => e.type === 'command/run' || e.type === 'command/done');
if (cmds.length) {
  console.log('\n=== 命令执行 ===');
  cmds.slice(-10).forEach(e => {
    const d = e.data || {};
    console.log(`  ${ts(e.time)} ${e.type} ${JSON.stringify(d).slice(0, 180)}`);
  });
}

if (keyword) {
  const hit = evs.filter(e => JSON.stringify(e).includes(keyword));
  console.log(`\n=== 含 "${keyword}" 的事件 (${hit.length})，显示最近 5 条 ===`);
  hit.slice(-5).forEach(e => console.log(`  [${e.type}] ${JSON.stringify(e).slice(0, 300)}`));
}
