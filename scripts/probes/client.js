// Speed probes for one llama-server: writing after a short prompt, reading a prompt of
// an exact length, and N requests at once. Server timings, prompt cache off, greedy,
// ignore_eos, so every run does the same work. Prints one JSON line per request.
//   URL=http://127.0.0.1:8080 LABEL="Bonsai t4" TG=128 PP=256 PAR=0 node client.js
const http = require('http');
const URL_ = (process.env.URL || 'http://127.0.0.1:8080').replace(/\/$/, '');
const LABEL = process.env.LABEL || '';
const TG = Number(process.env.TG || 0), PP = Number(process.env.PP || 0), PP_OUT = Number(process.env.PP_OUT || 1);
const PAR = Number(process.env.PAR || 0), PAR_TG = Number(process.env.PAR_TG || 64);
const FILLER = 'Momentum is the product of mass and velocity. In a closed system with no external force, the total momentum before a collision equals the total momentum after it. Kinetic energy, half the mass times the square of the speed, is conserved only in elastic collisions; in inelastic ones some of it becomes heat, sound and deformation. Impulse is the change in momentum, equal to the average force multiplied by the time over which it acts, which is why airbags and crumple zones lengthen the stopping time. ';

function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request(URL_ + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, (res) => {
      let buf = ''; res.setEncoding('utf8');
      res.on('data', c => { buf += c; });
      res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { reject(new Error(`bad JSON (${res.statusCode}): ${buf.slice(0, 200)}`)); } });
    });
    req.setTimeout(1_800_000, () => req.destroy(new Error('timed out')));
    req.on('error', reject); req.end(data);
  });
}
async function promptOf(n) {
  let text = FILLER;
  while ((await post('/tokenize', { content: text })).tokens.length < n) text += FILLER;
  const tk = await post('/tokenize', { content: text });
  return (await post('/detokenize', { tokens: tk.tokens.slice(0, n) })).content;
}
async function run(kind, prompt, nPredict) {
  const t0 = Date.now();
  const j = await post('/completion', { prompt, n_predict: nPredict, cache_prompt: false, temperature: 0, ignore_eos: true });
  const tm = j.timings || {};
  return { label: LABEL, kind, prompt_n: tm.prompt_n, prompt_per_second: tm.prompt_per_second && +tm.prompt_per_second.toFixed(2),
    predicted_n: tm.predicted_n, predicted_per_second: tm.predicted_per_second && +tm.predicted_per_second.toFixed(2),
    prompt_s: tm.prompt_ms && +(tm.prompt_ms / 1000).toFixed(2), predicted_s: tm.predicted_ms && +(tm.predicted_ms / 1000).toFixed(2), wall_s: +((Date.now() - t0) / 1000).toFixed(2) };
}
(async () => {
  const out = (o) => console.log(JSON.stringify(o));
  await run('warmup', 'Hello', 8);
  if (TG) out(await run('tg', 'Write a long story about a lighthouse keeper and the storm that changed her life.', TG));
  if (PP) { const p = await promptOf(PP); out(await run('pp', p, PP_OUT)); }
  if (PAR) {
    const t0 = Date.now();
    const rs = await Promise.all(Array.from({ length: PAR }, (_, i) => run('par', `Write a long story about lighthouse keeper number ${i + 1}.`, PAR_TG)));
    const wall = (Date.now() - t0) / 1000, toks = rs.reduce((n, r) => n + (r.predicted_n || 0), 0);
    rs.forEach(out); out({ label: LABEL, kind: 'par-total', requests: PAR, tokens: toks, wall_s: +wall.toFixed(2), combined_tok_s: +(toks / wall).toFixed(2) });
  }
})().catch(e => { console.log(JSON.stringify({ label: LABEL, error: e.message })); process.exit(1); });
