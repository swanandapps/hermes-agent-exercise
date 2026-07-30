# Part 3 — running on open-weight models

The agent, its tools, its memory and its delegation are **unchanged** across every row below.
Only the `model:` block differs — a different overlay in [`config/`](../config), picked by the
`MODEL` environment variable. No agent code, no tool code and no prompt was modified to make an
open model work.

That is the claim. This page is what happened when it was tested.

---

## The two open-weight models, and where each runs

| | Model | Vendor | Where it runs | Role |
|---|---|---|---|---|
| `MODEL=kimi` | **Kimi K2 (0905)** | Moonshot AI | OpenRouter | **open-weight model #1** — the most stable of these |
| `MODEL=llama33` | **Llama-3.3-70B-Instruct** | Meta | OpenRouter | **open-weight model #2** — see *Which copy of the model* below |
| `MODEL=ollama` | **Qwen2.5-3B** | Alibaba | **Ollama, locally** | proves the self-hosted path |
| `MODEL=openrouter` | Qwen3-32B | Alibaba | OpenRouter | kept as the *thinking-model* data point — correct but ~127 s |
| `MODEL=llama` | Llama-3.1-8B-Instruct | Meta | OpenRouter | kept because it *fails* at delegation |
| `MODEL=fast` | Qwen3.7-Flash | Alibaba | OpenRouter | quickest overall, but **not self-hostable** — see below. Kept for latency comparison only |
| `MODEL=openai` | GPT-5-mini | OpenAI | OpenAI | hosted baseline, for comparison only |

The two models carrying Part 3 are from **different vendors with independently published weights** —
Llama 3.3 under Meta's community licence, Kimi K2 under a Modified MIT licence, both downloadable
from HuggingFace.

### Which to demo, and why

Measured on the full handoff turn — screen a party, look up a trade lane, delegate the memo:

| Model | Turn | Delegated | Notes |
|---|---|---|---|
| **Kimi K2 (0905)** | **41–49 s** | **3 / 3** | best memo of any model tested — cites the lists, the figure, and an OFAC reporting step |
| **Llama-3.3-70B** | **38–56 s** | **3 / 3** | leads with the decision, exactly as the prompt asks — but see the provider caveat below |
| Qwen3-30B-A3B-Instruct | 17–23 s | **0 / 3** | fastest open model tried; writes `delegate_task` as plain text |
| Qwen3-32B | 127 s | ✅ | correct, but a *thinking* model — reasoning tokens dominate the time |
| Llama-3.1-8B | 21 s | ❌ | same failure as the 30B, at 8B |

The two that work differ in one visible way. Llama opens with the decision. Kimi narrates first —
*"I'll screen Rosneft Trading S.A. and look up the trade data"* — then produces the memo, which
the Researcher's prompt asks it not to do. The content is better; the instruction-following is
looser. Neither is wrong enough to matter here, but it is the kind of difference that only shows
up when you read the output rather than check that it ran.

Two things fall out of this, and neither is obvious from a model card:

**Thinking modes cost more than parameters do.** Qwen3-32B is smaller than Llama-3.3-70B and took
**three times longer**, because it generates reasoning tokens on every one of the 4–5 calls in a
turn. For an agent workload, "no thinking mode" is a bigger speed lever than parameter count.

**Nested tool calls are a separate capability from tool calls.** Both models that failed called
`screen_party` and `trade_data_lookup` perfectly, then wrote the delegation as prose instead of a
structured call. A 30B model with 3B active parameters is fast and useful and still cannot hand
work to another agent. **70B is where that became reliable here** — so if a workflow depends on
delegation, that is the number to test, not single tool calls.

Both Kimi and Llama weights are downloadable and self-hostable. They are served here from a cloud
endpoint because an 8 GB laptop cannot hold a useful model at Hermes's 64 K context floor — see
*The local ceiling* below.

### Which copy of the model you get, and why it matters

"Open weights" does not mean one model. OpenRouter routes each request to whichever provider is
cheapest at that moment, and every provider runs its own copy — its own quantisation, its own
serving stack. Three consecutive one-line requests to `llama-3.3-70b-instruct` were answered by
**DeepInfra, AkashML and Cloudflare**.

| Model | Providers | Quantisation |
|---|---|---|
| Llama-3.3-70B | **13** | mixed — **fp8** *and* bf16 |
| Kimi K2 (0905) | 2 | Novita, Groq |
| Qwen3.7-Flash | **1** | Alibaba only |

That last row is the useful diagnostic, and it settles a question this page previously left open:
**a model served by exactly one provider — its own vendor — is not self-hostable.** Nobody else
can serve Qwen3.7-Flash because nobody else has the weights. It is fast and it is closed, so it
does not carry the Part 3 claim.

**The 13-provider row is a real operational hazard.** A turn makes 4–5 model calls, so it can be
answered by several different copies of the "same" model. Running the Huawei query through
Llama-3.3-70B on a fresh container, the output collapsed into token noise — mixed scripts, escaped
fragments, no coherent sentence — and the tool trail showed the agent looping
`screen_party → delegate → screen_party`. Same code and same prompt that had delegated 3/3 an hour
earlier. **fp8 compression degrades structured output first, which is exactly what a tool call is.**

Routing also dominates speed far more than model size does. Same prompt, same length of answer:

| | Provider | Throughput |
|---|---|---|
| Kimi K2 | **Groq** | **82.9 tok/s** |
| Llama-3.3-70B | DeepInfra | 9.5 tok/s |
| Qwen2.5-3B | this laptop | 14.6 tok/s |

**Nine times, from routing alone** — the smaller model on the faster provider beat the larger one
by an order of magnitude. In production you would pin the provider rather than let a marketplace
choose per call; here it is left unpinned because the variance is itself the finding.

## Running it

```bash
cp .env.example .env          # OPENROUTER_API_KEY + TRADE_GOV_API_KEY
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# cloud open-weight model, whole stack in Docker, no Anthropic
MODEL=openrouter docker compose up --build          # then open http://localhost:8000

# local open-weight model
ollama pull qwen2.5:3b                              # ~1.9 GB, once
MODEL=ollama ./dev.sh                               # then open http://localhost:5173
```

### Why the local model runs outside Docker

There is an `ollama` compose profile, and it works in the sense that the container starts, the
gateway reaches it, and a request completes. It is not the recommended path, for a reason worth
stating:

**Docker Desktop's memory allowance is typically far below the machine's.** On the laptop this
was measured on, Docker had **3.8 GB** against 8 GB of host RAM. Ollama inside that allowance
cannot allocate the 64 K context Hermes requires — it silently loaded a **4,096-token window**
instead, and a 3B model handed a ~2 K prompt at that size returned an unparseable stub. The
gateway retried three times and reported an empty response. Nothing errored in a way that
pointed at memory.

Pointing the containerised gateway at an Ollama on the host is supported —
`OLLAMA_BASE_URL=http://host.docker.internal:11434/v1` — but Ollama binds `127.0.0.1` by default,
so it also needs `OLLAMA_HOST=0.0.0.0` before a container can reach it.

Running Ollama natively avoids both, which is why it is the documented path. The cloud
open-weight model is the one that runs entirely in Docker, and that is what the compose file is
for.

---

## Results

Same query on every model, same gateway, `--mode handoff`:

> *"We are signing a steel deal with Rosneft Trading S.A. Screen them and check Germany iron and
> steel exports to the Russian Federation in 2022, then give me the compliance memo."*

| Model | Open weights | Tools called | Handoff to Writer | Latency | Usable output |
|---|---|---|---|---|---|
| **Kimi K2 (0905)** (cloud) | ✅ | ✅ both | ✅ 3/3 | **41–49 s** | ✅ best memo of the set |
| **Llama-3.3-70B** (cloud) | ✅ | ✅ both | ✅ 3/3 | 38–56 s | ✅ memo — but see the provider caveat |
| **Qwen3-32B** (cloud) | ✅ | ✅ both | ✅ | 127.6 s | ✅ memo, looser wording |
| **Llama-3.1-8B** (cloud) | ✅ | ✅ both | ❌ **failed** | 21.0 s | ❌ raw JSON |
| **Qwen2.5-3B** (local, Ollama, native) | ✅ | ✅ | ❌ failed | 46–154 s | ⚠️ contradicted itself |
| Qwen3.7-Flash (cloud) | ❌ **Alibaba-only** | ✅ both | ✅ | **5–25 s** | ✅ memo — fastest, but closed |
| GPT-5-mini (hosted, baseline) | ❌ | ✅ both | ✅ | ~50 s | ✅ memo |

**Sample size is one run per model for the slower rows.** Directional findings, not benchmarks —
and, given the provider variance above, a result for a model name is really a result for whichever
copy of it answered that day.

---

## Where the differences actually show up

**Tool calling is not one capability.** Llama-3.1-8B called both research tools correctly and
then failed at delegation — it wrote the call as *text* instead of emitting a structured tool
call, so no Writer was ever spawned and the user got raw JSON. A simple call like
`screen_party(name="…")` is a different difficulty tier from a call whose argument is itself a
long instruction for another agent.

Its 21 s latency looks like a win until you notice it never did the expensive part. **Latency is
only comparable between runs that completed the same work.**

**Failures that are not errors.** Qwen3-32B produced a correct memo — right decision, right
lists, right figure — but followed instructions less exactly: it wrapped the memo in commentary
the prompt forbids, and skipped writing to memory. Nothing errored. The output was simply looser,
which for a compliance artefact matters more than latency.

**The smallest model breaks at the sentence, not the tool call.** Qwen2.5-3B called the tool,
read the result correctly, and then wrote a verdict and its opposite in the same sentence — a
confirmed match reported alongside "the party is not sanctioned". The tools and data were right;
the model could not hold the finding together in prose. That fails exactly where a compliance
answer cannot afford to.

---

## Cost

After scoping the toolset (see [`performance-detail.md`](performance-detail.md)), the prompt is
**2,686 tokens per call in single mode** and **7,757 in handoff mode** (measured), with 4–5
model calls per turn.

| Model | Input $/M | Approx. per handoff turn |
|---|---|---|
| Qwen3-32B | $0.08 | ~$0.003 |
| Llama-3.1-8B | $0.05 | ~$0.002 |
| Qwen2.5-3B, local | — | electricity |

Well under a cent per query on open weights. The dominant cost is the number of model calls in a
turn, not the size of any one prompt.

---

## The local ceiling

Measured on an **Apple M1, 8 GB RAM, 8 cores**. Everything below is specific to that; a 16 GB
machine changes the answers.

Hermes requires a **64 K context** (`agent/model_metadata.py`: `MINIMUM_CONTEXT_LENGTH`), and the
**KV cache for that window — not the weights — is the binding constraint**:

| | Weights | Resident at 64 K | Result |
|---|---|---|---|
| Qwen2.5-3B | 1.9 GB | **~4.1 GB** | runs; ~120 MB free; 46–62 s per turn |
| Qwen2.5-7B | 4.7 GB | — | timed out at 64 K |

The weights are the smaller half of the bill. A 3B model more than doubles its footprint once a
64 K window is allocated.

### Why not just use a smaller context window?

The obvious move, and it does not work — tested rather than assumed. Our prompt is only ~2,700
tokens, so 16 K would be ample, and at 16 K the same 3B model answers coherently in seconds.

Hermes refuses:

```
runtime_context=32768  minimum_context=64000  →  turn refused
```

Two separate checks enforce it. `model.context_length` below 64,000 is rejected outright, and
`agent/conversation_loop.py` then probes the context Ollama **actually loaded** and refuses if
that is short — so declaring 64 K while quietly serving less does not work either. (A third check
in `cli.py` only warns, which is misleading if that is the one you find first.)

Raising the ceiling by shrinking the window is therefore not available. The floor is deliberate:
tool schemas plus system prompt are a large fixed prefix, and Hermes would rather refuse than
silently truncate them.

### Why not a bigger model, then?

Qwen2.5-7B at 16 K produced a noticeably better sentence — and took **2 minutes 8 seconds**,
leaving 95 MB free. Correct, and unusable for a demo. The quality ceiling and the memory ceiling
are the same ceiling on this machine.

### What a memory-starved 3B actually does

Not an error. On one run the tool call **succeeded** and the model reported:

> *"There seems to have been an issue with the screening API. I will try running the test again."*

That is the failure mode worth knowing about: the data was correct and the model narrated a
failure that never happened.

So the split is deliberate, and worth stating as two separate claims:

- **Runs on open weights** — demonstrated, locally and in the cloud, by changing one config line.
- **Safe on open weights** — not at 3B. A larger open model is the honest recommendation for
  anything a compliance officer would act on.

---

## Reproducing

```bash
export $(grep -v '^#' .env | grep -v '^$' | xargs)

MODEL=openrouter python run.py --mode handoff   # Qwen3-32B
MODEL=llama      python run.py --mode handoff   # Llama-3.1-8B
MODEL=ollama     python run.py --mode handoff   # Qwen2.5-3B, local
```

Adding a model is a four-line YAML file in [`config/`](../config); nothing else changes.

*The prompt-size work behind the cost figures — what the tokens were made of, the four
optimisations that were tried and reverted, and the one that mattered — is in
[`performance-detail.md`](performance-detail.md).*
