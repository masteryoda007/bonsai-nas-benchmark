# Bonsai-8B (1-bit) on a NAS CPU

Speed, stress and quality measurements of PrismML's 1-bit [Bonsai-8B](https://huggingface.co/prism-ml/Bonsai-8B-gguf) on a NAS with no GPU, next to ordinary 4-bit models. I ran these in my home lab on 11 and 12 October 2026. This repo has the two scripts, the raw output and the summary I wrote up.

PrismML's model card and whitepaper give no x86 CPU speeds for this model. The only other x86 result for the 8B I found is a [community run](https://github.com/PrismML-Eng/Bonsai-demo/blob/main/community-benchmarks/bonsai/cpu-i3-7100-linux-proxmox.md) on an i3-7100 VM with an older build (3.61 tok/s writing). These are mine, from one machine, so treat them as one data point.

## Results at a glance

- Bonsai-8B is a 1.16 GB file. On a 4-core Xeon D-1622 it writes 8-9 tokens/s after a short prompt and reads prompts of up to 1,024 tokens at 10-12 tokens/s; both slow down as the prompt grows (5.1 and 8.5 tok/s at 2,048 tokens). The first token of a reply to a 300-token prompt arrives after 26 s.
- A 4,096-token prompt takes 11.6 minutes. Four concurrent requests queue behind one slot and all succeed. Ten minutes of back-to-back requests: 20 requests, 0 errors, 8.3-8.6 tokens/s throughout.
- On the same 36 auto-checked tasks: Bonsai-8B 32, Qwen3 8B Q4_K_M 33, Qwen3 4B Q4_K_M 35, Qwen3 1.7B Q4_K_M 33 (on the NAS) and 32 (on the Mac).
- On this CPU, Qwen3 1.7B Q4_K_M (1.4 GB in Ollama) writes about 2x and reads about 5-6x faster than Bonsai.

## Hardware and software

| | NAS: speed, stress, quality | Mac: quality only |
|---|---|---|
| Machine | QNAP TS-h886 | MacBook Pro, M4 Max |
| CPU | Intel Xeon D-1622: 4 cores / 8 threads, 2.6 GHz base, AVX2, no AVX-512 | Apple M4 Max |
| Memory | 2 x 8 GB DDR4 ECC UDIMM at 2133 MT/s | 128 GB unified |
| GPU | none | Apple GPU |
| OS | QuTS hero (ZFS), Docker | macOS |
| Runtimes | PrismML's llama.cpp fork, release `prism-b10772-e8fd209`, CPU build (Bonsai); Ollama 0.40.3 (Qwen3 1.7B) | LM Studio: llama.cpp engine for the GGUF files, MLX engine for Qwen3.8 27B |

The Mac only ran the quality tasks. Its timings (the `s` and `totalS` fields in `mac-eval.jsonl`) are left in the raw file but not used anywhere, because they say nothing about a NAS.

## How Bonsai was run

- Model: `Bonsai-8B-Q1_0.gguf` from [prism-ml/Bonsai-8B-gguf](https://huggingface.co/prism-ml/Bonsai-8B-gguf), 1,158,654,496 bytes, Apache 2.0. Qwen3-8B architecture, 8.19B parameters. Each weight is one sign bit, with one FP16 scale per 128 weights: 1.125 bits per weight.
- Server: llama-server from [PrismML's fork of llama.cpp](https://github.com/PrismML-Eng/llama.cpp), CPU build in Docker.
- Flags: `-t 4 -c 8192 --cache-type-k q8_0 --cache-type-v q8_0 --jinja -np 1` (4 threads, 8K context, 8-bit KV cache, one request slot).
- Container: 3 GB memory cap and no published port. Only containers on a private Docker network can reach it. On the NAS, the scripts ran from a Node 20 container on that network.
- Memory: 1.62-1.81 GiB container RSS during these runs (2.09-2.17 GiB in a run on 11 October). Docker's own counter, which includes some page cache, read 2.3-2.7 GiB during the stress run.

A setup like mine looks roughly like this. The fork builds with upstream llama.cpp's Dockerfiles; the CPU image picks the right kernels (AVX2 here) at run time.

```sh
git clone https://github.com/PrismML-Eng/llama.cpp && cd llama.cpp
git checkout prism-b10772-e8fd209
docker build -t llama-cpu:prism-b10772 --target server -f .devops/cpu.Dockerfile .

docker network create llm-net
docker run -d --name bonsai --network llm-net --memory 3g \
  -v /path/to/models:/models:ro llama-cpu:prism-b10772 \
  -m /models/Bonsai-8B-Q1_0.gguf -t 4 -c 8192 \
  --cache-type-k q8_0 --cache-type-v q8_0 --jinja -np 1
```

No `-p`, so nothing is exposed outside Docker. Other containers on `llm-net` reach it at `http://bonsai:8080`.

## Methodology

### Speed: `scripts/bench.js`, `MODE=llama` and `MODE=ollama`

- All speed numbers are from the NAS. Bonsai figures are llama-server's own timings (`prompt_per_second`, `predicted_per_second`). Qwen3 1.7B figures come from Ollama's `prompt_eval_duration` and `eval_duration`.
- Reading means prompt processing. Writing means token generation.
- Prompt sweep: filler text cut to exactly 128, 512, 1,024 and 2,048 tokens with the server's own tokenizer, then 64 tokens generated with `ignore_eos`. Prompt cache off.
- Write sweep: one short prompt, 32, 128 and 512 tokens generated.
- Time to first token: a 300-token prompt, streamed.
- Five small tasks (JSON summary, JSON quiz, a momentum problem, a grammar fix, a three-line list) through the chat endpoint at temperature 0.5, top_k 20, top_p 0.9, with light pass/fail checks. They are there for timing; quality comes from `eval.js`.
- These are not llama-bench `pp512`/`tg128` runs, so they are not directly comparable with published llama-bench tables.

### Stress: `scripts/bench.js`, `MODE=stress`

- A 4,096-token prompt (half the 8K context), 64 tokens out.
- Four requests at once (256-token prompt, 128 tokens out each) against the one-slot server.
- Sustained load: back-to-back 256-token answers for 10 minutes. The request in flight at the 10-minute mark finishes, hence 10.5 minutes.
- A watchdog stops the test if available host memory drops below 150 MB or swap grows by more than 1 GB. Neither happened.
- Separately, an HTTP health check hit another web app on the same NAS every 10 seconds for the whole session (300 checks). That loop is not in this repo; something like this does the same job:

```sh
while true; do printf '%s ' "$(date +%T)"; curl -s -o /dev/null -w '%{http_code} %{time_total}\n' http://127.0.0.1:8000/health; sleep 10; done
```

### Quality: `scripts/eval.js`

- 36 tasks in four groups: 12 math word problems (the last `Answer: <number>` in the reply, 1% tolerance), 8 JSON extractions (the JSON must parse and the required fields must hold the right values; numbers given as strings are accepted), 8 instruction-following tasks (format rules), 8 short knowledge questions.
- The same system prompt and user prompts for every model. Greedy decoding (temperature 0), at most 512 output tokens, `<think>` blocks stripped before checking.
- Thinking off: `/no_think` plus `enable_thinking: false` for Qwen-family models (Bonsai included), `think: false` in Ollama. Gemma and Llama got no switch and ran on LM Studio's defaults.
- One run per model. Every answer is checked by code, not by eye and not by another model.
- Bonsai and one Qwen3 1.7B run were on the NAS. Everything else ran on the Mac in LM Studio, quality only.

## Results

### Quality: the same 36 tasks on every model

| Model | Format | File size | Ran on | Score | Math | JSON | Instr. | Know. | Avg output tokens | Missed |
|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| Qwen3 4B | GGUF Q4_K_M | 2.50 GB | Mac | **35** | 12/12 | 8/8 | 7/8 | 8/8 | 58.6 | i7 |
| Gemma 4 E4B | GGUF Q4_K_M | 6.33 GB¹ | Mac | **35** | 12/12 | 8/8 | 7/8 | 8/8 | 101.3 | i7 |
| Qwen3.8 27B | MLX 4-bit | 16.08 GB | Mac | **35** | 12/12 | 8/8 | 7/8 | 8/8 | 131.6² | i8 |
| Gemma 4 31B | GGUF Q4_K_M | 19.89 GB¹ | Mac | **34** | 11/12 | 8/8 | 7/8 | 8/8 | 219.9² | m5, i7 |
| Qwen3 1.7B | Ollama `qwen3:1.7b` (Q4_K_M) | 1.4 GB | NAS CPU, Ollama | **33** | 11/12 | 8/8 | 6/8 | 8/8 | 34.2 | m10, i3, i7 |
| Qwen3 8B | GGUF Q4_K_M | 5.03 GB | Mac | **33** | 12/12 | 7/8 | 6/8 | 8/8 | 40.2 | j8, i3, i7 |
| Bonsai-8B | GGUF Q1_0 | 1.16 GB | NAS CPU, PrismML fork | **32** | 12/12 | 7/8 | 5/8 | 8/8 | 44.2 | j8, i3, i4, i7 |
| Qwen3 1.7B | GGUF Q4_K_M | 1.28 GB | Mac | **32** | 11/12 | 8/8 | 5/8 | 8/8 | 40.8 | m10, i1, i3, i7 |
| Llama 3.2 3B | GGUF Q4_K_M | 2.02 GB | Mac | **28** | 12/12 | 5/8 | 4/8 | 7/8 | 41.2 | j1, j4, j7, i1, i2, i4, i7, k8 |

¹ Includes the BF16 vision projector file that ships with the model (0.99 GB for E4B, 1.20 GB for 31B).
² These two spent 37 to 206 output tokens on one-word answers, so they were reasoning before answering. Treat their scores as a reference, not a like-for-like comparison.

GGUF files on the Mac are the Q4_K_M builds from LM Studio's catalogue (lmstudio-community).

What the misses were:

- `i7`, write "circuit" backwards: every model except Qwen3.8 27B got it wrong (Bonsai wrote "tircuit").
- `i3`, one sentence of at most 20 words with no commas: Bonsai, Qwen3 8B and both Qwen3 1.7B runs went over.
- `j8`, a parts list as `{"parts":[...]}`: Bonsai echoed the schema back; Qwen3 8B returned a bare array.
- `i4`, start the reply with Yes or No, is 17 prime: Bonsai and Llama 3.2 3B said No.
- `m10`, range on 45 litres at 6 L/100 km: both Qwen3 1.7B runs said 75 km instead of 750.
- `m5` for Gemma 4 31B hit the 512-token limit before its final answer. `i8` for Qwen3.8 27B was an empty answer after 511 tokens. Both count as misses, the same rule as everyone else.

Rescoring: after the first runs I fixed two checkers. `k8` now accepts LaTeX `\times`, and `i5` accepts 10 as "between 1 and 10". Three saved answers were rescored and now pass: Gemma 4 E4B `k8`, Qwen3 1.7B (Mac) `k8` and Llama 3.2 3B `i5`. The raw files keep the original `pass` flags; `results/results.json` has the corrected scores, and `scripts/eval.js` has the fixed checkers.

### Speed on the NAS: Bonsai-8B

Reading speed by prompt length (64 tokens generated after each prompt):

| Prompt tokens | Reading tok/s | Writing tok/s | Total s |
|---:|---:|---:|---:|
| 128 | 11.8 | 8.5 | 18.2 |
| 512 | 10.8 | 7.6 | 56.0 |
| 1,024 | 9.9 | 6.4 | 113.2 |
| 2,048 | 8.5 | 5.1 | 253.6 |
| 4,096 (stress run) | 6.1 | 2.9 | 696 |

Writing speed by answer length (short prompt):

| Tokens generated | Writing tok/s | Total s |
|---:|---:|---:|
| 32 | 8.61 | 5.1 |
| 128 | 8.42 | 16.5 |
| 512 | 8.06 | 64.7 |

Time to first token for a 300-token prompt, streamed: 26.3 s (30.2 s for the whole 32-token reply).

### Speed on the NAS: Bonsai-8B vs Qwen3 1.7B on the same five tasks

| Task | Bonsai prompt / output tokens | Bonsai read / write tok/s | Bonsai total s | Qwen3 1.7B prompt / output tokens | Qwen3 1.7B read / write tok/s | Qwen3 1.7B total s |
|---|---:|---:|---:|---:|---:|---:|
| json-summary | 273 / 143 | 11.3 / 8.0 | 42.7 | 277 / 127 | 66.2 / 17.1 | 12.0 |
| json-quiz | 162 / 167 | 11.3 / 8.3 | 34.4 | 170 / 176 | 62.5 / 17.5 | 12.9 |
| math | 58 / 39 | 11.6 / 8.9 | 9.3 | 65 / 108 | 69.7 / 17.7 | 7.4 |
| grammar | 41 / 17 | 12.3 / 8.5 | 5.3 | 48 / 17 | 70.6 / 20.1 | 2.1 |
| instruction | 45 / 46 | 11.8 / 8.9 | 8.9 | 52 / 28 | 66.1 / 19.8 | 2.2 |

All ten passed their checks. Qwen3 1.7B on a 1,285-token prompt: reading 54 tok/s, writing 12.5 tok/s after it, 28.5 s in total.

### Stress on the NAS: Bonsai-8B

- Long prompt: 4,096 tokens in, 64 out, 696 s (11.6 minutes). Reading 6.1 tok/s, writing 2.9 tok/s.
- Four requests at once: the server has one slot, so they ran one after another and finished at 38.9, 77.2, 115.7 and 154.0 s. All four returned HTTP 200.
- Sustained: 20 requests in 10.5 minutes, 0 errors, 5,120 tokens written. Writing speed per request stayed between 8.31 and 8.64 tok/s from the first request to the last; 8.12 tok/s overall, including prompt time.
- The rest of the NAS: 300 health checks of another web app on the box during the session. All returned 200. Median 32 ms, 7 over 1 s, 1 over 2 s, worst 5.03 s.

## Caveats

- 36 tasks is a small, easy set, run once per model. It catches broken JSON and ignored instructions. It cannot rank models that are one or two tasks apart. The same Qwen3 1.7B scored 33 in Ollama on the NAS and 32 in LM Studio on the Mac, with different files (1.4 GB and 1.28 GB) and runtimes.
- The Mac is in this repo for quality only. Mac speeds are not comparable with the NAS and are not used anywhere.
- Most speed figures are single runs. The sustained test shows the spread on this box: 8.31 to 8.64 tok/s.
- The NAS kept running its normal containers during the tests.
- The `answer` and `sample` fields in the raw files are cut to 140 and 160 characters with whitespace collapsed. They are for reading, not for re-scoring; re-run `eval.js` to re-score.
- Speed results come from the PrismML fork. Mainline llama.cpp has run Q1_0 on CPU since April 2026 (x86 AVX2 kernels since 20 April), but it lacks the fork's x86 repacked kernels. I did not compare the two.
- My explanation of the speed is arithmetic, not profiling. Bonsai moves about 1 GB of weights per token, roughly 9-10 GB/s at these speeds, against a theoretical 34 GB/s for dual-channel DDR4-2133. Qwen3 1.7B (a 1.36 GB blob in Ollama, listed as 1.4 GB) moves about 23-27 GB/s on the same box. That points at the four cores, not memory bandwidth, as Bonsai's limit here.
- Node's built-in `fetch` gives up when response headers take more than 5 minutes. My first stress run died on that during the 4,096-token prompt, which is why the scripts send their requests with `node:http` and explicit timeouts (only the short streaming test still uses `fetch`), and why the stress file is `stress2.jsonl`.

## PrismML's numbers, for context

These are PrismML's own results, not reproduced here. Six benchmarks (MMLU-Redux, MuSR, GSM8K, HumanEval+, IFEval, BFCLv3), non-thinking, greedy, EvalScope and vLLM on H100s. Every baseline is a 16-bit model, not a 4-bit file.

| Model | Precision in PrismML's table | Six-benchmark average |
|---|---|---:|
| Qwen3 8B | 16-bit | 79.3 |
| Qwen3 4B | 16-bit | 77.1 |
| Bonsai-8B | 1-bit | 70.5 |
| Qwen3 1.7B | 16-bit | 66.6 |

PrismML's speed and energy comparisons (6.2x faster on an RTX 4090, 368 vs 59 tok/s; 4.1-5.6x less energy per token on an RTX 4090 and an M4 Pro) are measured against 16-bit models on GPUs and Apple silicon. PrismML does not say how Bonsai is made beyond "built from Qwen3-8B" with "proprietary Caltech intellectual property".

Sources: the [1-bit Bonsai 8B whitepaper](https://github.com/PrismML-Eng/Bonsai-demo/blob/main/1-bit-bonsai-8b-whitepaper.pdf), and the [Ternary-Bonsai-4B](https://huggingface.co/prism-ml/Ternary-Bonsai-4B-gguf) and [Ternary-Bonsai-1.7B](https://huggingface.co/prism-ml/Ternary-Bonsai-1.7B-gguf) model cards, which carry PrismML's same-harness scores for Qwen3 4B and 1.7B. Use the whitepaper rather than the Bonsai-8B card for baseline cells; several cells on that card don't match the whitepaper or add up to the card's own averages.

## Reproduce it

You need Node 18 or newer (the scripts have no dependencies) and a model server.

Speed and stress need llama-server, because they use its `/tokenize`, `/detokenize` and `/completion` endpoints and its timings. Mainline llama.cpp or PrismML's fork both load the Q1_0 file.

```sh
llama-server -m Bonsai-8B-Q1_0.gguf -t 4 -c 8192 \
  --cache-type-k q8_0 --cache-type-v q8_0 --jinja -np 1 --port 8080

LLAMA_URL=http://127.0.0.1:8080 MODE=llama  node scripts/bench.js | tee bonsai.jsonl
LLAMA_URL=http://127.0.0.1:8080 MODE=stress MINUTES=10 node scripts/bench.js | tee stress.jsonl
```

The Ollama comparison:

```sh
ollama pull qwen3:1.7b
OLLAMA_URL=http://127.0.0.1:11434 OLLAMA_MODEL=qwen3:1.7b MODE=ollama node scripts/bench.js | tee qwen.jsonl
```

Quality works with any OpenAI-compatible server (llama-server, LM Studio, vLLM and others) or with Ollama:

```sh
# llama-server ignores MODEL; LM Studio and vLLM need the loaded model's id
BACKEND=openai BASE=http://127.0.0.1:8080 LABEL="Bonsai-8B Q1_0" NOTHINK=1 node scripts/eval.js | tee bonsai-eval.jsonl
BACKEND=openai BASE=http://127.0.0.1:1234 MODEL=qwen/qwen3-8b LABEL="Qwen3 8B Q4_K_M" NOTHINK=1 node scripts/eval.js | tee qwen3-8b-eval.jsonl
BACKEND=ollama BASE=http://127.0.0.1:11434 MODEL=qwen3:1.7b LABEL="Qwen3 1.7B Q4_K_M" node scripts/eval.js | tee qwen-eval.jsonl
```

Environment variables:

| Script | Variable | Default | Meaning |
|---|---|---|---|
| bench.js | `MODE` | `llama` | `llama`, `ollama` or `stress` (`bonsai` and `qwen` also work) |
| bench.js | `LLAMA_URL` | `http://127.0.0.1:8080` | llama-server base URL |
| bench.js | `LLAMA_LABEL` | `Bonsai-8B Q1_0` | model label in the output |
| bench.js | `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama base URL |
| bench.js | `OLLAMA_MODEL` | `qwen3:1.7b` | Ollama model tag |
| bench.js | `OLLAMA_LABEL` | `Qwen3 1.7B Q4_K_M` | model label in the output |
| bench.js | `MINUTES` | `10` | length of the sustained stress phase |
| bench.js | `MIN_AVAIL_MB`, `MAX_SWAP_GROWTH_MB` | `150`, `1024` | watchdog limits (Linux hosts only) |
| eval.js | `BACKEND` | `openai` | `openai` or `ollama` |
| eval.js | `BASE` | `http://127.0.0.1:1234` | server base URL |
| eval.js | `MODEL` | empty | model id or tag |
| eval.js | `LABEL` | `MODEL` | model label in the output |
| eval.js | `NOTHINK` | off | `1` adds Qwen3's thinking-off switches |
| eval.js | `MAXTOK` | `512` | output token cap |
| eval.js | `API_KEY` | empty | sent as a Bearer token if set |

Run the scripts from a machine or container that can reach the server. To keep a server off the network the way I did, run the scripts in a container on the same private Docker network, for example `docker run --rm --network llm-net -v "$PWD":/w -w /w -e LLAMA_URL=http://bonsai:8080 node:20 node scripts/bench.js`.

## Files

- `scripts/bench.js`: speed and stress.
- `scripts/eval.js`: the 36-task quality check.
- `results/results.json`: the summary used in the write-up, with the rescoring applied.
- `results/raw/bonsai.jsonl`: Bonsai speed runs (prompt sweep, write sweep, time to first token, five tasks).
- `results/raw/qwen.jsonl`: Qwen3 1.7B speed runs on the NAS.
- `results/raw/stress2.jsonl`: the stress run (long prompt, four at once, sustained) with host memory readings.
- `results/raw/bonsai-eval.jsonl`, `results/raw/qwen-eval.jsonl`: 36-task runs on the NAS.
- `results/raw/mac-eval.jsonl`: 36-task runs on the Mac, seven models.

## Links

- PrismML: [Bonsai-8B model card](https://huggingface.co/prism-ml/Bonsai-8B-gguf), [Bonsai-demo repo and whitepapers](https://github.com/PrismML-Eng/Bonsai-demo), [llama.cpp fork](https://github.com/PrismML-Eng/llama.cpp) and its [AVX2 repack PR](https://github.com/PrismML-Eng/llama.cpp/pull/233)
- Qwen: [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B), [Qwen3-8B-GGUF](https://huggingface.co/Qwen/Qwen3-8B-GGUF), [Qwen3-4B-GGUF](https://huggingface.co/Qwen/Qwen3-4B-GGUF), [Qwen3 technical report](https://arxiv.org/abs/2505.09388)
- llama.cpp: [repository](https://github.com/ggml-org/llama.cpp), [Q1_0 CPU support (PR 21273)](https://github.com/ggml-org/llama.cpp/pull/21273), [x86 Q1_0 kernels (PR 21636)](https://github.com/ggml-org/llama.cpp/pull/21636)
- [Ollama qwen3 tags](https://ollama.com/library/qwen3), [LM Studio](https://lmstudio.ai)
- An independent, informal Bonsai test on a Jetson Orin: [ArmanJR/PrismML-Bonsai-vs-Qwen3.5-Benchmark](https://github.com/ArmanJR/PrismML-Bonsai-vs-Qwen3.5-Benchmark)

## Credits

PrismML for publishing the weights under Apache 2.0, the Qwen team for the base models, and the llama.cpp contributors whose CPU kernels do the work here: khosravipasha and pl752 upstream, and Strike3D for the AVX2 repack in PrismML's fork. Thanks also to the Ollama and LM Studio teams.

## License

MIT. See [LICENSE](LICENSE).
