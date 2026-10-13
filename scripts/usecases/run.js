// Use-case runner: the 48 tasks in tasks.json (chat, reasoning, code, debugging,
// summaries, creative writing), same prompts for every model, greedy decoding,
// thinking off. Prints one JSON line per task with the full answer and the server's
// own timings; score.py checks the answers afterwards, in a sandbox.
//   BACKEND=openai BASE=http://127.0.0.1:1234 MODEL=qwen/qwen3-8b LABEL="Qwen3 8B Q4_K_M" NOTHINK=1 node run.js
//   BACKEND=ollama BASE=http://127.0.0.1:11434 MODEL=qwen3:1.7b LABEL="Qwen3 1.7B Q4_K_M" node run.js
// Piped to `node -`, the tasks can come first in the same stream as
// `globalThis.TASKS = [...]`. ACTIVITY_URL is optional: an endpoint that returns
// {"inflight": n, "idleSec": n}; the run pauses while that service is busy.
const http = require('http');
const BACKEND = process.env.BACKEND || 'openai';
const BASE = (process.env.BASE || 'http://127.0.0.1:1234').replace(/\/$/, '');
const MODEL = process.env.MODEL || '';
const LABEL = process.env.LABEL || MODEL;
const NOTHINK = process.env.NOTHINK === '1';
const ACTIVITY_URL = process.env.ACTIVITY_URL || '';
const IDLE_MIN = 120, IDLE_RESUME = 300;
const ONLY = (process.env.ONLY || '').split(',').filter(Boolean);
const TASKS = (globalThis.TASKS || JSON.parse(require('fs').readFileSync(process.env.TASKS_FILE || `${__dirname}/tasks.json`, 'utf8')).tasks)
  .filter(t => !ONLY.length || ONLY.includes(t.id));
const out = (o) => console.log(JSON.stringify(o));
process.stdout.on('error', () => process.exit(1)); // stdout closed: the pipe or remote session went away

function request(url, body, ms) {
  return new Promise((resolve, reject) => {
    const data = body === undefined ? null : JSON.stringify(body);
    const req = http.request(url, { method: data ? 'POST' : 'GET', headers: data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {} }, (res) => {
      let buf = ''; res.setEncoding('utf8');
      res.on('data', (c) => { buf += c; });
      res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { reject(new Error(`bad JSON (${res.statusCode}): ${buf.slice(0, 200)}`)); } });
    });
    req.setTimeout(ms, () => req.destroy(new Error(`timed out after ${ms / 1000} s`)));
    req.on('error', reject);
    req.end(data || undefined);
  });
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

// Pause while the other service is busy: a request in flight, or one in the last 2 min.
// Once paused, resume only after 5 quiet minutes.
async function waitIdle() {
  if (!ACTIVITY_URL) return;
  let since = 0;
  for (;;) {
    let a;
    try { a = await request(ACTIVITY_URL, undefined, 5000); } catch { return; }
    const busy = a.inflight > 0 || a.idleSec < (since ? IDLE_RESUME : IDLE_MIN);
    if (!busy) { if (since) out({ resumed: new Date().toISOString(), pausedS: Math.round((Date.now() - since) / 1000) }); return; }
    if (!since) { since = Date.now(); out({ paused: new Date().toISOString(), inflight: a.inflight, idleSec: a.idleSec }); }
    await sleep(30_000);
  }
}

const SYSTEM = 'You are a helpful assistant. Answer concisely and follow the requested format exactly.';
const strip = (t) => String(t || '').replace(/<think>[\s\S]*?<\/think>/g, '').replace(/^[\s\S]*<\/think>/, '').trim();
const round = (x, d = 2) => (typeof x === 'number' && Number.isFinite(x) ? +x.toFixed(d) : null);

async function ask(task) {
  const msgs = task.messages.map(m => ({ ...m }));
  if (NOTHINK) msgs[msgs.length - 1].content += ' /no_think';
  const messages = [{ role: 'system', content: SYSTEM }, ...msgs];
  const r = {};
  const t0 = Date.now();
  if (BACKEND === 'ollama') {
    const j = await request(`${BASE}/api/chat`, { model: MODEL, messages, stream: false, think: false, options: { temperature: 0, num_predict: task.max_tokens } }, 1_800_000);
    if (j.error) throw new Error(String(j.error).slice(0, 200));
    r.answer = j.message?.content || '';
    r.finish = j.done_reason;
    r.outTokens = j.eval_count; r.promptTokens = j.prompt_eval_count;
    r.readS = j.prompt_eval_duration / 1e9; r.writeS = j.eval_duration / 1e9; r.loadS = j.load_duration / 1e9;
    r.readTokS = j.prompt_eval_count / r.readS; r.writeTokS = j.eval_count / r.writeS;
  } else {
    const body = { model: MODEL, messages, temperature: 0, max_tokens: task.max_tokens, stream: false };
    if (NOTHINK) body.chat_template_kwargs = { enable_thinking: false };
    const j = await request(`${BASE}/v1/chat/completions`, body, 1_800_000);
    if (j.error) throw new Error(JSON.stringify(j.error).slice(0, 200));
    const msg = j.choices?.[0]?.message || {};
    r.answer = msg.content || '';
    r.reasoningChars = (msg.reasoning_content || msg.reasoning || '').length || undefined;
    r.finish = j.choices?.[0]?.finish_reason;
    const tm = j.timings;
    r.outTokens = j.usage?.completion_tokens ?? tm?.predicted_n ?? null;
    r.promptTokens = j.usage?.prompt_tokens ?? tm?.prompt_n ?? null;
    if (tm) {
      r.readS = tm.prompt_ms / 1000; r.writeS = tm.predicted_ms / 1000; r.cachedTokens = tm.cache_n;
      r.readTokS = tm.prompt_per_second; r.writeTokS = tm.predicted_per_second; r.promptProcessed = tm.prompt_n;
    }
  }
  r.s = (Date.now() - t0) / 1000;
  r.answer = strip(r.answer);
  return r;
}

(async () => {
  out({ start: new Date().toISOString(), model: LABEL, backend: BACKEND, tasks: TASKS.length });
  for (const task of TASKS) {
    await waitIdle();
    let r;
    try { r = await ask(task); } catch (e) { r = { answer: `ERROR ${e.message}`, s: null }; }
    out({ model: LABEL, id: task.id, cat: task.cat, finish: r.finish, outTokens: r.outTokens, promptTokens: r.promptTokens,
      promptProcessed: r.promptProcessed, cachedTokens: r.cachedTokens, readTokS: round(r.readTokS, 1), writeTokS: round(r.writeTokS, 1),
      readS: round(r.readS), writeS: round(r.writeS), loadS: round(r.loadS), s: round(r.s, 1), reasoningChars: r.reasoningChars, answer: r.answer });
  }
  out({ end: new Date().toISOString(), model: LABEL });
})();
