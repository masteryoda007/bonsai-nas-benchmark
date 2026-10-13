// Speed and stress test for a local model server. Node 18 or newer, no dependencies.
// Writes one JSON object per line to stdout. Only synthetic text and the task
// prompts below are sent to the server.
//
//   MODE=llama   llama.cpp's llama-server: reading speed by prompt length, writing
//                speed by answer length, time to first token, and five small tasks.
//                Uses /completion, /tokenize, /detokenize and the OpenAI-compatible
//                /v1/chat/completions, which all report llama-server's own timings.
//   MODE=ollama  The same five tasks through Ollama's /api/chat (think:false), plus
//                reading speed on a ~1,300-token prompt.
//   MODE=stress  llama-server again: a 4,096-token prompt, four requests at once,
//                then MINUTES (default 10) of back-to-back 256-token answers.
//
//   LLAMA_URL=http://127.0.0.1:8080 MODE=llama node bench.js > bonsai.jsonl
//   OLLAMA_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen3:1.7b MODE=ollama node bench.js > qwen.jsonl
//   LLAMA_URL=http://127.0.0.1:8080 MODE=stress MINUTES=10 node bench.js > stress.jsonl
//
// MODE=bonsai and MODE=qwen are accepted as aliases for llama and ollama.
const ALIASES = { bonsai: 'llama', qwen: 'ollama' };
const MODE = ALIASES[process.env.MODE] || process.env.MODE || 'llama';
const LLM = (process.env.LLAMA_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const OLLAMA = (process.env.OLLAMA_URL || 'http://127.0.0.1:11434').replace(/\/$/, '');
const QWEN = process.env.OLLAMA_MODEL || 'qwen3:1.7b';
const LLAMA_LABEL = process.env.LLAMA_LABEL || 'Bonsai-8B Q1_0';
const OLLAMA_LABEL = process.env.OLLAMA_LABEL || 'Qwen3 1.7B Q4_K_M';
const out = (o) => console.log(JSON.stringify(o));
const sec = (ms) => Math.round(ms / 100) / 10;

const FILLER = 'Momentum is the product of mass and velocity. In a closed system with no external force, the total momentum before a collision equals the total momentum after it. Kinetic energy, half the mass times the square of the speed, is conserved only in elastic collisions; in inelastic ones some of it becomes heat, sound and deformation. Impulse is the change in momentum, equal to the average force multiplied by the time over which it acts, which is why airbags and crumple zones lengthen the stopping time. ';

// node:http, not fetch: fetch (undici) gives up after 5 minutes without
// response headers, and a long prompt on a slow CPU takes longer than that.
const http = require('http');
const https = require('https');
function post(url, body, ms = 1_800_000) {
  const t0 = Date.now();
  const lib = url.startsWith('https:') ? https : http;
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = lib.request(url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, (res) => {
      let buf = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { buf += c; });
      res.on('end', () => { try { resolve({ j: JSON.parse(buf), ms: Date.now() - t0, status: res.statusCode }); } catch (e) { reject(new Error(`bad JSON (${res.statusCode}): ${buf.slice(0, 200)}`)); } });
    });
    req.setTimeout(ms, () => req.destroy(new Error(`timed out after ${ms / 1000} s`)));
    req.on('error', reject);
    req.end(data);
  });
}

async function tokens(text) {
  const { j } = await post(`${LLM}/tokenize`, { content: text });
  return j.tokens.length;
}

// A prompt of about n tokens (measured with the server's own tokenizer).
async function promptOf(n) {
  let text = '';
  while ((await tokens(text)) < n) text += FILLER;
  // Trim to n tokens by detokenizing the first n.
  const { j: tk } = await post(`${LLM}/tokenize`, { content: text });
  const { j: dt } = await post(`${LLM}/detokenize`, { tokens: tk.tokens.slice(0, n) });
  return dt.content;
}

const TASKS = [
  { id: 'json-summary', max: 300, json: true,
    system: 'You extract structured data. Reply with JSON only.',
    user: 'Summarise these notes as JSON with keys "title" (string), "topics" (array of 3 strings) and "summary" (two sentences).\n---\n' + FILLER.repeat(2) },
  { id: 'json-quiz', max: 400, json: true,
    system: 'You write practice questions. Reply with JSON only.',
    user: 'Write 3 multiple-choice questions about these notes as JSON: {"questions":[{"q":string,"choices":[4 strings],"answer":0-3}]}\n---\n' + FILLER },
  { id: 'math', max: 200, check: (t) => /\b1\.5\b|\b3\s*\/\s*2\b/.test(t),
    system: 'Answer briefly and show one line of working.',
    user: 'A 2 kg cart moving at 3 m/s collides with a stationary 2 kg cart and they stick together. What is their speed afterwards, in m/s?' },
  { id: 'grammar', max: 80, check: (t) => /\bweren't|were not\b/i.test(t),
    system: 'Correct the grammar. Reply with the corrected sentence only.',
    user: "Me and him wasn't ready for the test, because the bus was late." },
  { id: 'instruction', max: 120, check: (t) => t.trim().split(/\n+/).filter(Boolean).length === 3,
    system: 'Follow the format exactly.',
    user: 'List exactly three uses of a ground pour on a 2-layer PCB, one per line, no numbering, no extra text.' },
];

function judge(task, text) {
  if (task.json) {
    try {
      const s = text.slice(text.indexOf('{'), text.lastIndexOf('}') + 1);
      const v = JSON.parse(s);
      if (task.id === 'json-summary') return Array.isArray(v.topics) && v.topics.length === 3 && typeof v.summary === 'string' ? 'pass' : 'json, wrong shape';
      if (task.id === 'json-quiz') return Array.isArray(v.questions) && v.questions.length === 3 && v.questions.every(q => Array.isArray(q.choices) && q.choices.length === 4 && Number.isInteger(q.answer)) ? 'pass' : 'json, wrong shape';
      return 'pass';
    } catch { return 'invalid JSON'; }
  }
  return task.check(text) ? 'pass' : 'fail';
}

async function llamaServer() {
  // Warm-up (the model is already in memory once the server answers).
  await post(`${LLM}/completion`, { prompt: 'Hello', n_predict: 8, cache_prompt: false, temperature: 0 });

  // 1. Reading speed by prompt length, and writing speed after it.
  for (const n of [128, 512, 1024, 2048]) {
    const prompt = await promptOf(n);
    const { j, ms } = await post(`${LLM}/completion`, { prompt, n_predict: 64, cache_prompt: false, temperature: 0, ignore_eos: true });
    const t = j.timings || {};
    out({ test: 'prompt-sweep', promptTokens: t.prompt_n, readTokPerS: +t.prompt_per_second?.toFixed(1), writeTokPerS: +t.predicted_per_second?.toFixed(1), generated: t.predicted_n, totalS: sec(ms) });
  }

  // 2. Writing speed over a longer answer.
  for (const n of [32, 128, 512]) {
    const { j, ms } = await post(`${LLM}/completion`, { prompt: 'Write a detailed explanation of how a ground pour works on a printed circuit board.', n_predict: n, cache_prompt: false, temperature: 0, ignore_eos: true });
    const t = j.timings || {};
    out({ test: 'write-sweep', generated: t.predicted_n, writeTokPerS: +t.predicted_per_second?.toFixed(2), readTokPerS: +t.prompt_per_second?.toFixed(1), totalS: sec(ms) });
  }

  // 3. Time to first token for a typical ~300-token chat prompt (streamed).
  {
    const prompt = await promptOf(300);
    const t0 = Date.now();
    const r = await fetch(`${LLM}/completion`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ prompt, n_predict: 32, stream: true, cache_prompt: false, temperature: 0, ignore_eos: true }), signal: AbortSignal.timeout(600_000) });
    if (!r.ok || !r.body) throw new Error(`streaming request failed: HTTP ${r.status}`);
    const reader = r.body.getReader();
    let first = null;
    for (;;) { const { done, value } = await reader.read(); if (done) break; if (first === null && value && value.length) first = Date.now() - t0; }
    out({ test: 'time-to-first-token', promptTokens: 300, firstTokenS: sec(first), totalS: sec(Date.now() - t0) });
  }

  // 4. Real tasks through the OpenAI-compatible endpoint, with quality checks.
  for (const task of TASKS) {
    const body = { messages: [{ role: 'system', content: task.system }, { role: 'user', content: task.user }], max_tokens: task.max, temperature: 0.5, top_k: 20, top_p: 0.9 };
    if (task.json) body.response_format = { type: 'json_object' };
    const { j, ms } = await post(`${LLM}/v1/chat/completions`, body);
    const text = j.choices?.[0]?.message?.content || '';
    const t = j.timings || {};
    out({ test: 'task', model: LLAMA_LABEL, id: task.id, verdict: judge(task, text), promptTokens: t.prompt_n, generated: t.predicted_n, readTokPerS: +t.prompt_per_second?.toFixed(1), writeTokPerS: +t.predicted_per_second?.toFixed(1), totalS: sec(ms), sample: text.replace(/\s+/g, ' ').slice(0, 160) });
  }
}

async function ollama() {
  const ns = (x) => x / 1e9;
  await post(`${OLLAMA}/api/chat`, { model: QWEN, messages: [{ role: 'user', content: 'Hello' }], stream: false, think: false, options: { num_predict: 8 } });
  for (const task of TASKS) {
    const body = { model: QWEN, stream: false, think: false, messages: [{ role: 'system', content: task.system }, { role: 'user', content: task.user }], options: { num_predict: task.max, temperature: 0.5, top_k: 20, top_p: 0.9 } };
    if (task.json) body.format = 'json';
    const { j, ms } = await post(`${OLLAMA}/api/chat`, body);
    const text = j.message?.content || '';
    out({ test: 'task', model: OLLAMA_LABEL, id: task.id, verdict: judge(task, text), promptTokens: j.prompt_eval_count, generated: j.eval_count, readTokPerS: j.prompt_eval_duration ? +(j.prompt_eval_count / ns(j.prompt_eval_duration)).toFixed(1) : null, writeTokPerS: j.eval_duration ? +(j.eval_count / ns(j.eval_duration)).toFixed(1) : null, totalS: sec(ms), sample: text.replace(/\s+/g, ' ').slice(0, 160) });
  }
  // Reading speed on a longer prompt (about 1,300 tokens), for the comparison.
  const long = FILLER.repeat(12);
  const { j, ms } = await post(`${OLLAMA}/api/chat`, { model: QWEN, stream: false, think: false, messages: [{ role: 'user', content: long + '\nSummarise in one sentence.' }], options: { num_predict: 64 } });
  out({ test: 'prompt-read', model: OLLAMA_LABEL, promptTokens: j.prompt_eval_count, readTokPerS: +(j.prompt_eval_count / ns(j.prompt_eval_duration)).toFixed(1), writeTokPerS: +(j.eval_count / ns(j.eval_duration)).toFixed(1), totalS: sec(ms) });
}

// Host memory from /proc/meminfo (Linux; inside a container this is normally the
// host's own figure). Elsewhere it returns {} and the watchdog never trips.
const MIN_AVAIL_MB = Number(process.env.MIN_AVAIL_MB || 150);
const MAX_SWAP_GROWTH_MB = Number(process.env.MAX_SWAP_GROWTH_MB || 1024);
function mem() {
  try {
    const t = require('fs').readFileSync('/proc/meminfo', 'utf8');
    const kb = (k) => Number((t.match(new RegExp('^' + k + ':\\s+(\\d+)', 'm')) || [])[1] || 0);
    return { availMB: Math.round(kb('MemAvailable') / 1024), swapUsedMB: Math.round((kb('SwapTotal') - kb('SwapFree')) / 1024) };
  } catch { return {}; }
}
const SWAP0 = mem().swapUsedMB;
// Stops the stress test before it pushes the host into heavy swapping.
function watchdog(where) {
  const m = mem();
  if (m.availMB === undefined) return true;
  if (m.availMB < MIN_AVAIL_MB || m.swapUsedMB - SWAP0 > MAX_SWAP_GROWTH_MB) { out({ test: 'watchdog', stoppedAt: where, ...m, swapGrewMB: m.swapUsedMB - SWAP0 }); return false; }
  return true;
}

async function stress() {
  const minutes = Number(process.env.MINUTES || 10);
  out({ test: 'stress-start', ...mem() });
  // 1. A long prompt, half the 8K context.
  if (watchdog('long-prompt')) try {
    const prompt = await promptOf(4096);
    const { j, ms } = await post(`${LLM}/completion`, { prompt, n_predict: 64, cache_prompt: false, temperature: 0, ignore_eos: true }, 1_500_000);
    const t = j.timings || {};
    out({ test: 'long-prompt', promptTokens: t.prompt_n, readTokPerS: +t.prompt_per_second?.toFixed(1), writeTokPerS: +t.predicted_per_second?.toFixed(1), totalS: sec(ms), ...mem() });
  } catch (e) { out({ test: 'long-prompt-error', error: String(e.message || e), ...mem() }); }
  // 2. Four requests at once: with one slot (-np 1) on the server, they queue.
  if (watchdog('concurrency')) try {
    const prompt = await promptOf(256);
    const t0 = Date.now();
    const rs = await Promise.all([0, 1, 2, 3].map(async (i) => {
      const { j, ms, status } = await post(`${LLM}/completion`, { prompt: prompt + ` (${i})`, n_predict: 128, cache_prompt: false, temperature: 0, ignore_eos: true });
      const t = j.timings || {};
      return { i, status, totalS: sec(ms), writeTokPerS: +t.predicted_per_second?.toFixed(1), readTokPerS: +t.prompt_per_second?.toFixed(1) };
    }));
    out({ test: 'concurrency-4', wallS: sec(Date.now() - t0), each: rs, ...mem() });
  } catch (e) { out({ test: 'concurrency-error', error: String(e.message || e), ...mem() }); }
  // 3. Sustained writing for N minutes: one 256-token answer after another.
  const until = Date.now() + minutes * 60_000;
  let n = 0, errors = 0, tokensOut = 0;
  const t0 = Date.now();
  while (Date.now() < until && watchdog(`sustained #${n}`)) {
    try {
      const { j, ms } = await post(`${LLM}/completion`, { prompt: `Explain, step by step, how to choose a resistor for an LED (${n}).`, n_predict: 256, cache_prompt: false, temperature: 0.5, ignore_eos: true });
      const t = j.timings || {};
      tokensOut += t.predicted_n || 0;
      out({ test: 'sustained', n, atMin: +((Date.now() - t0) / 60000).toFixed(1), writeTokPerS: +t.predicted_per_second?.toFixed(2), readTokPerS: +t.prompt_per_second?.toFixed(1), totalS: sec(ms), ...mem() });
    } catch (e) { errors++; out({ test: 'sustained-error', n, error: String(e.message || e) }); }
    n++;
  }
  out({ test: 'sustained-summary', requests: n, errors, tokensOut, minutes: +((Date.now() - t0) / 60000).toFixed(1), avgWriteTokPerS: +(tokensOut / ((Date.now() - t0) / 1000)).toFixed(2), ...mem() });
}

const RUN = { llama: llamaServer, ollama, stress };
if (!RUN[MODE]) {
  console.error(`Unknown MODE "${MODE}". Use llama, ollama or stress.`);
  process.exit(2);
}
RUN[MODE]().then(() => out({ done: MODE }), (e) => { out({ error: String(e && e.message || e) }); process.exit(1); });
