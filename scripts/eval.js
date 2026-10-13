// Same-prompt quality comparison of local models: 36 auto-checked tasks in four
// groups (math, JSON extraction, instruction following, knowledge). Greedy
// decoding and the same prompts for every model; thinking is switched off only
// by NOTHINK=1 or the ollama backend (see below). Synthetic tasks only.
// Node 18 or newer, no dependencies. Writes one JSON line per task, then a summary.
//
//   Any OpenAI-compatible server (llama-server, LM Studio, vLLM, ...):
//     BACKEND=openai BASE=http://127.0.0.1:1234 MODEL=qwen/qwen3-8b LABEL="Qwen3 8B Q4_K_M" NOTHINK=1 node eval.js
//   Ollama:
//     BACKEND=ollama BASE=http://127.0.0.1:11434 MODEL=qwen3:1.7b LABEL="Qwen3 1.7B Q4_K_M" node eval.js
//
// NOTHINK=1 appends " /no_think" to every prompt and, on the openai backend, sends
// chat_template_kwargs {enable_thinking: false} (the Qwen3 switches). The ollama
// backend always sends think:false. MAXTOK caps output tokens (default 512).
// API_KEY, if set, is sent as a Bearer token for servers that require one.
const BACKEND = process.env.BACKEND || 'openai';
const BASE = (process.env.BASE || 'http://127.0.0.1:1234').replace(/\/$/, '');
const MODEL = process.env.MODEL || '';
const LABEL = process.env.LABEL || MODEL;
const NOTHINK = process.env.NOTHINK === '1';
const MAXTOK = Number(process.env.MAXTOK || 512);
const out = (o) => console.log(JSON.stringify(o));

const MATH_TAIL = '\nFinish with a final line in the form: Answer: <number>';
const num = (t) => { const m = [...t.matchAll(/Answer:\s*\$?\s*(-?[\d,]*\.?\d+)/gi)].pop(); return m ? Number(m[1].replace(/,/g, '')) : NaN; };
const near = (x, want) => Number.isFinite(x) && Math.abs(x - want) <= 0.01 * Math.max(1, Math.abs(want));
const math = (id, q, want) => ({ id, cat: 'math', user: q + MATH_TAIL, check: (t) => near(num(t), want) });
const firstJson = (t) => {
  const i = Math.min(...['{', '['].map(c => { const k = t.indexOf(c); return k < 0 ? Infinity : k; }));
  if (!Number.isFinite(i)) throw new Error('no JSON');
  const close = t[i] === '{' ? '}' : ']';
  return JSON.parse(t.slice(i, t.lastIndexOf(close) + 1));
};
const json = (id, user, test) => ({ id, cat: 'extract', user: user + '\nReply with JSON only.', check: (t) => { try { return !!test(firstJson(t)); } catch { return false; } } });
const lines = (t) => t.split('\n').map(s => s.trim()).filter(Boolean);
const words = (t) => t.trim().split(/\s+/).filter(Boolean);

const TASKS = [
  math('m1', 'A shop sells pencils at 3 for $0.75. How many dollars do 12 pencils cost?', 3),
  math('m2', 'A train travels 180 km in 2.5 hours. What is its average speed in km/h?', 72),
  math('m3', 'Mia has 3 times as many marbles as Leo. Together they have 48 marbles. How many marbles does Mia have?', 36),
  math('m4', 'A rectangle is 8 cm long and its perimeter is 28 cm. What is its area in square centimetres?', 48),
  math('m5', 'A 2 kg cart moving at 3 m/s collides with a stationary 2 kg cart and they stick together. What is their speed afterwards, in m/s?', 1.5),
  math('m6', 'A jacket costs $80. It is discounted by 25%, then a 10% tax is added to the discounted price. What is the final price in dollars?', 66),
  math('m7', 'If 5 workers can build a wall in 12 days, how many days would 6 workers take, working at the same rate?', 10),
  math('m8', 'A 220 ohm resistor is connected across a 3.3 V supply. What current flows, in milliamps?', 15),
  math('m9', 'What is the sum of the interior angles of a hexagon, in degrees?', 720),
  math('m10', 'A car\'s fuel tank holds 45 litres and the car uses 6 litres per 100 km. How many kilometres can it travel on a full tank?', 750),
  math('m11', 'Solve for x: 3x - 7 = 2x + 5.', 12),
  math('m12', 'A ball is dropped from rest. Ignoring air resistance and using g = 10 m/s^2, how far does it fall in 3 seconds, in metres?', 45),

  json('j1', 'Extract order_id (number), customer, date (YYYY-MM-DD), quantity (number) and unit_price (number) from: "Order #4471 was placed by Dana Ruiz on 2026-03-14 for 3 notebooks at $4.50 each."',
    (v) => v.order_id == 4471 && v.customer === 'Dana Ruiz' && v.date === '2026-03-14' && v.quantity == 3 && Number(v.unit_price) === 4.5),
  json('j2', 'Extract board (string), digital_pins (number), clock_mhz (number) and sram_kb (number) from: "The XIAO ESP32-C3 has 11 digital pins, a 160 MHz RISC-V core and 400 KB of SRAM."',
    (v) => /XIAO ESP32-C3/i.test(v.board) && v.digital_pins == 11 && v.clock_mhz == 160 && v.sram_kb == 400),
  json('j3', 'Extract team, day, time and room from: "Meeting moved: the robotics team will meet on Thursday at 4:30 pm in Room 214 instead of Wednesday."',
    (v) => /robotics/i.test(v.team) && v.day === 'Thursday' && /4:30/.test(String(v.time)) && /214/.test(String(v.room))),
  json('j4', 'Extract the ingredients as {"ingredients":[{"item","amount","unit"}]} from: "Ingredients: 2 cups flour, 1 cup sugar, 3 eggs."',
    (v) => Array.isArray(v.ingredients) && v.ingredients.length === 3 && ['flour', 'sugar', 'egg'].every((w, i) => new RegExp(w, 'i').test(v.ingredients[i].item)) && [2, 1, 3].every((a, i) => Number(v.ingredients[i].amount) === a)),
  json('j5', 'Classify each review as "positive" or "negative" and return {"A":..., "B":..., "C":...}. A) "Battery lasts all day, love it." B) "Stopped working after a week." C) "Great screen, fast shipping."',
    (v) => /^positive$/i.test(v.A) && /^negative$/i.test(v.B) && /^positive$/i.test(v.C)),
  json('j6', 'Convert 5 km to metres and 2 hours to minutes. Return {"metres": number, "minutes": number}.',
    (v) => v.metres == 5000 && v.minutes == 120),
  json('j7', 'Split the email address "alex.chen@example.org" into {"user": ..., "domain": ...}.',
    (v) => v.user === 'alex.chen' && v.domain === 'example.org'),
  json('j8', 'Extract the parts as {"parts":[{"ref","value","net"}]} from: "R1 is a 10 kOhm resistor on net SDA; C3 is a 100 nF capacitor on net 3V3."',
    (v) => Array.isArray(v.parts) && v.parts.length === 2 && v.parts[0].ref === 'R1' && v.parts[0].net === 'SDA' && v.parts[1].ref === 'C3' && v.parts[1].net === '3V3' && /100\s*nF/i.test(v.parts[1].value)),

  { id: 'i1', cat: 'instruct', user: 'Name the three primary colours of light. Write exactly three lines, one word per line, and nothing else.', check: (t) => { const l = lines(t); return l.length === 3 && l.every(s => words(s).length === 1) && ['red', 'green', 'blue'].every(c => l.some(s => s.toLowerCase().replace(/[^a-z]/g, '') === c)); } },
  { id: 'i2', cat: 'instruct', user: 'Answer in ALL CAPITAL LETTERS: what is the largest planet in our solar system?', check: (t) => /JUPITER/.test(t) && !/[a-z]/.test(t) },
  { id: 'i3', cat: 'instruct', user: 'Describe what a ground pour on a circuit board is in one sentence of at most 20 words, without using any commas.', check: (t) => { const s = t.trim(); return !s.includes(',') && words(s).length <= 20 && (s.match(/[.!?](\s|$)/g) || []).length <= 1; } },
  { id: 'i4', cat: 'instruct', user: 'Start your reply with the word Yes or No, with nothing before it: is 17 a prime number?', check: (t) => /^\s*Yes\b/.test(t) },
  { id: 'i5', cat: 'instruct', user: 'List four even numbers between 1 and 10 as a comma-separated list, with no other text.', check: (t) => { const s = t.trim(); if (!/^\d+(\s*,\s*\d+){3}$/.test(s)) return false; const n = s.split(',').map(Number); return new Set(n).size === 4 && n.every(x => x % 2 === 0 && x > 1 && x <= 10); } },
  { id: 'i6', cat: 'instruct', user: 'Reply with a JSON array of exactly 3 strings, the names of three noble gases, and nothing else.', check: (t) => { try { const a = JSON.parse(t.trim().replace(/^```(json)?|```$/g, '').trim()); const g = ['helium', 'neon', 'argon', 'krypton', 'xenon', 'radon', 'oganesson']; return Array.isArray(a) && a.length === 3 && a.every(x => g.includes(String(x).toLowerCase())); } catch { return false; } } },
  { id: 'i7', cat: 'instruct', user: 'Write the word "circuit" backwards, in lowercase, and nothing else.', check: (t) => t.trim().replace(/["'.`]/g, '') === 'tiucric' },
  { id: 'i8', cat: 'instruct', user: 'Give a title for an essay about momentum, in Title Case, at most 6 words, with no punctuation at all.', check: (t) => { const s = t.trim().replace(/^["']|["']$/g, ''); const w = words(s); const small = new Set(['a', 'an', 'the', 'of', 'and', 'in', 'on', 'for', 'to', 'at', 'by', 'or']); return w.length >= 1 && w.length <= 6 && !/[.,;:!?()\-—]/.test(s) && w.every((x, i) => /^[A-Z0-9]/.test(x) || (i > 0 && small.has(x))); } },

  { id: 'k1', cat: 'know', user: 'What is the chemical symbol for sodium? Answer with the symbol only.', check: (t) => /^\W*Na\W*$/.test(t.trim()) },
  { id: 'k2', cat: 'know', user: 'In which year did Apollo 11 land on the Moon? Answer with the year only.', check: (t) => /\b1969\b/.test(t) },
  { id: 'k3', cat: 'know', user: 'What is the SI unit of electrical resistance?', check: (t) => /ohm|Ω/i.test(t) },
  { id: 'k4', cat: 'know', user: 'What is the derivative of x^3 with respect to x?', check: (t) => /3\s*\*?\s*x\s*(\^\s*2|²|\*\*\s*2)/.test(t) },
  { id: 'k5', cat: 'know', user: 'Which gas makes up most of Earth\'s atmosphere?', check: (t) => /nitrogen/i.test(t) },
  { id: 'k6', cat: 'know', user: 'Which organelle produces most of a cell\'s ATP?', check: (t) => /mitochondri/i.test(t) },
  { id: 'k7', cat: 'know', user: 'Who wrote the novel "Pride and Prejudice"?', check: (t) => /austen/i.test(t) },
  { id: 'k8', cat: 'know', user: 'What is the speed of light in a vacuum, in metres per second, to three significant figures?', check: (t) => /3(\.00?)?\s*(×|x|\*|\\times|\\cdot)\s*10\s*(\^|\*\*)?\s*\{?8|3(\.00?)?\s*[eE]\+?8|300[, ]?000[, ]?000|299[, ]?792[, ]?458|3\.00\s*×\s*10⁸/.test(t) },
];

// node:http, not fetch: fetch (undici) gives up after 5 minutes without response
// headers, which a slow CPU can exceed on a long answer.
const http = require('http');
const https = require('https');
const API_KEY = process.env.API_KEY || '';
function postJson(url, body, ms = 1_800_000) {
  const lib = url.startsWith('https:') ? https : http;
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const headers = { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) };
    if (API_KEY) headers.Authorization = `Bearer ${API_KEY}`;
    const req = lib.request(url, { method: 'POST', headers }, (res) => {
      let buf = ''; res.setEncoding('utf8');
      res.on('data', (c) => { buf += c; });
      res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { reject(new Error(`bad JSON (${res.statusCode}): ${buf.slice(0, 200)}`)); } });
    });
    req.setTimeout(ms, () => req.destroy(new Error(`timed out after ${ms / 1000} s`)));
    req.on('error', reject);
    req.end(data);
  });
}
const SYSTEM = 'You are a helpful assistant. Answer concisely and follow the requested format exactly.';
const strip = (t) => String(t || '').replace(/<think>[\s\S]*?<\/think>/g, '').replace(/^[\s\S]*<\/think>/, '').trim();

async function ask(task) {
  const user = NOTHINK ? `${task.user} /no_think` : task.user;
  const messages = [{ role: 'system', content: SYSTEM }, { role: 'user', content: user }];
  const t0 = Date.now();
  let text = '', outTokens = null, tokPerS = null, promptTokens = null;
  if (BACKEND === 'ollama') {
    const j = await postJson(`${BASE}/api/chat`, { model: MODEL, messages, stream: false, think: false, options: { temperature: 0, num_predict: MAXTOK } });
    text = j.message?.content || ''; outTokens = j.eval_count; promptTokens = j.prompt_eval_count;
    tokPerS = j.eval_duration ? j.eval_count / (j.eval_duration / 1e9) : null;
  } else {
    const body = { model: MODEL, messages, temperature: 0, max_tokens: MAXTOK, stream: false };
    if (NOTHINK) body.chat_template_kwargs = { enable_thinking: false };
    const j = await postJson(`${BASE}/v1/chat/completions`, body);
    text = j.choices?.[0]?.message?.content || '';
    outTokens = j.usage?.completion_tokens ?? j.timings?.predicted_n ?? null;
    promptTokens = j.usage?.prompt_tokens ?? j.timings?.prompt_n ?? null;
    tokPerS = j.timings?.predicted_per_second ?? j.stats?.tokens_per_second ?? null;
    if (j.error) text = `ERROR ${JSON.stringify(j.error).slice(0, 200)}`;
  }
  const answer = strip(text);
  return { answer, outTokens, promptTokens, tokPerS, ms: Date.now() - t0 };
}

(async () => {
  const byCat = {};
  let pass = 0, totalMs = 0, outTok = 0;
  for (const task of TASKS) {
    let r;
    try { r = await ask(task); } catch (e) { r = { answer: `ERROR ${e.message}`, ms: 0 }; }
    const ok = !r.answer.startsWith('ERROR') && task.check(r.answer);
    pass += ok ? 1 : 0; totalMs += r.ms; outTok += r.outTokens || 0;
    (byCat[task.cat] = byCat[task.cat] || { pass: 0, n: 0 }).n++; if (ok) byCat[task.cat].pass++;
    out({ model: LABEL, id: task.id, cat: task.cat, pass: ok, outTokens: r.outTokens, tokPerS: r.tokPerS ? +r.tokPerS.toFixed(1) : null, s: +(r.ms / 1000).toFixed(1), answer: r.answer.replace(/\s+/g, ' ').slice(0, 140) });
  }
  out({ summary: LABEL, pass, of: TASKS.length, byCat, totalS: +(totalMs / 1000).toFixed(1), avgOutTokens: +(outTok / TASKS.length).toFixed(1) });
})();
