# Prompt cost and optimisation — working notes

> Detail behind [`performance.md`](performance.md). That page compares the models; this one is
> the record of getting the prompt itself down, including the measurements that were wrong and
> the four optimisations that were reverted.
>
> Some figures in the early sections are **superseded** — they were taken before the toolset fix
> described further down took the prompt from 21,373 to 6,694 tokens per call. They are kept
> because the sequence is the point.

## Results

Same query on every model, run through the same gateway in `--mode handoff`:

> *"We are signing a steel deal with Rosneft Trading S.A. Screen them and check Germany iron and
> steel exports to the Russian Federation in 2022, then give me the compliance memo."*

| Model | Provider | Tools called | Handoff | Latency | Prompt tokens | Usable output |
|---|---|---|---|---|---|---|
| `gpt-5-mini` | OpenAI (hosted) | ✅ both | ✅ | ~50 s | ~30 K¹ | ✅ memo |
| `qwen/qwen3-32b` | OpenRouter | ✅ both | ✅ | **127.6 s** | 54,423 | ✅ memo |
| `meta-llama/llama-3.1-8b-instruct` | OpenRouter | ✅ both | ❌ **failed** | 21.0 s | 59,165 | ❌ raw JSON |

¹ Measured earlier in development on a simpler single-tool query, not a matched run — treat as
indicative only. The OpenAI account hit its quota before a like-for-like handoff run could be
captured. Every other row is a matched measurement of the query above.

**Sample size is one run per model.** These are directional findings, not benchmarks.

## What actually broke, and why it matters

**Llama-3.1-8B called the research tools correctly and then failed at delegation.** It emitted
the delegation as *text* rather than as a structured tool call:

```json
{"name": "delegate_task", "parameters": {"goal": "You are a trade compliance officer …",
 "context": "screen_party outcome: Rosneft Trading S.A. matched SDN, EL, SSI; …",
 "role": "leaf", "toolsets": []}}
```

The session record confirms only two real tool calls. `delegate_task` never fired, so no Writer
subagent was ever spawned, and the user received raw JSON instead of a memo.

This is the single most useful result here. Tool calling is not one capability — **simple tool
calls and nested delegation are different difficulty tiers.** An 8B model handled
`screen_party(name="Rosneft Trading S.A.")` fine and then could not handle a call whose argument
is itself a long instruction for another agent. Any claim that a workflow "runs on open models"
has to be tested at the hardest step, not the easiest.

Note also that its 21 s latency looks like a *win* until you see it never did the expensive part.
Latency is only comparable between runs that completed the same work.

## Quality differences that don't show up as errors

Qwen3-32B produced a correct memo — right decision, right lists, right figure — but followed
instructions less exactly than the hosted model:

- It prefixed the memo with *"The Writer's compliance memo follows your requirements exactly.
  This deliverable includes:"* — the Researcher's `SOUL.md` explicitly forbids adding commentary
  around the Writer's output.
- It skipped writing to memory, which the hosted model did unprompted.

Nothing failed. The output was simply looser. For a compliance tool, that gap matters more than
latency: the memo is the artefact of record.

## Cost

Roughly 55–60 K prompt tokens per handoff turn, dominated by the system prompt (tool schemas,
bundled skills, memory scaffolding) rather than the conversation.

| Model | Input $/M | Approx. cost per handoff turn |
|---|---|---|
| `qwen/qwen3-32b` | $0.08 | ~$0.005 |
| `meta-llama/llama-3.1-8b-instruct` | $0.05 | ~$0.003 |

Under a cent per query on open weights.

## Why local Ollama is a proof, not the demo backend

Hermes enforces a hard floor of **64 K context** (`agent/model_metadata.py`:
`MINIMUM_CONTEXT_LENGTH = 64_000`), and this agent's prompt measures **~30 K tokens in single
mode and ~55 K in handoff mode**. Models small enough to run on an 8 GB laptop cap out around
32 K — the system prompt alone would exceed the window before the user's question is added. A 3B
model configured to 64 K swapped to 8.3 GB and hung.

So the split is deliberate:

- **Cloud open-weight endpoint (OpenRouter)** carries the real inference — the models are
  open-weight and self-hostable, just not on this laptop.
- **Ollama** demonstrates the same config swap against a locally-hosted model, with a reduced
  toolset to fit the context budget.

The constraint is Hermes's context floor meeting consumer RAM, not anything about the model swap
itself.

## Reproducing

```bash
export $(grep -v '^#' .env | grep -v '^$' | xargs)

MODEL=openrouter python run.py --mode handoff   # Qwen3-32B
MODEL=llama      python run.py --mode handoff   # Llama-3.1-8B
MODEL=ollama     python run.py --mode handoff   # local
```

## The bug this exposed in our own code

Switching providers initially left OpenAI's `base_url` in the merged config, silently pointing an
OpenRouter model at OpenAI's endpoint. Overlays were being deep-merged key-by-key, but a provider
config is atomic. `run.py` now replaces the `model:` block outright. Worth stating plainly,
because "swapping models is just config" is exactly the kind of claim that hides this class of
bug.

## Token cost: where it actually goes

Measured on this profile, `"say ok"` (no tools, no conversation) — i.e. the fixed cost paid
before the user's question is even considered:

| Configuration | Prompt tokens |
|---|---|
| Default profile (17 bundled skills) | **21,373** |
| Bundled skills disabled | **16,210** |
| Saving | **5,163 (24%)** |

`hermes profile create` seeds 17 skill directories — apple, smart-home, social-media, yuanbao,
media, github and so on. None relate to trade compliance, and all of them cost prompt budget on
every call. Disabling them is a marker file in the profile root:

```bash
touch ~/.hermes/profiles/hermes-exercise/.no-bundled-skills
rm -rf ~/.hermes/profiles/hermes-exercise/skills
```

Without it, Hermes re-seeds the directory on every startup — moving it aside is not enough.

**The saving multiplies.** An agentic turn is not one model call: research, then delegate, then
relay is five or more, and the full system prompt is re-sent on each. A complete handoff turn
measured **81,927 total tokens**. Cutting 5K off the fixed prefix removes ~25K from a turn.

### The `max_tokens` trap

Hermes requests **65,536 output tokens per call** by default (`plugins/model-providers/custom`:
`default_max_tokens=65536`). OpenRouter reserves credit against that ceiling, so requests get
refused outright:

```
HTTP 402: You requested up to 65536 tokens, but can only afford 48357
```

— while the answer it would have produced costs a fraction of a cent. A compliance memo is
~1,500 tokens. The overlays now set `max_tokens: 4096`, which is generous headroom and stops the
over-reservation. This does not reduce tokens *used*; it stops the provider blocking requests
against tokens that were never going to be consumed.

### What the 80,000 tokens are actually made of

An earlier draft of this page blamed verbose tool results. Measurement disproved it, and the
real answer is more useful.

Dumping the stored session for a complete handoff turn:

| Part of the turn | Chars | ≈ Tokens |
|---|---|---|
| User question | 175 | 44 |
| `screen_party` result | 533 | 133 |
| `trade_data_lookup` result | 956 | 239 |
| `memory` result | 194 | 49 |
| Delegation call + Writer's memo returned | 2,396 | 599 |
| Final answer | 608 | 152 |
| **Entire conversation** | **5,855** | **~1,463** |

The turn billed **80,111 prompt tokens**. The conversation is under 2% of it.

**`prompt_tokens` is the sum across every model call in the turn, and each call re-sends the
whole system prompt.** That turn made five model calls — decide, look up trade data, record to
memory, delegate, relay — and 5 × ~16,210 ≈ 81,000. That is the entire bill.

Measured system prompt, this profile, bundled skills already removed:

| Mode | Toolsets | Prompt tokens per call |
|---|---|---|
| `single` | `trade-compliance` | **14,674** |
| `handoff` | `+ delegation, memory, session_search` | **16,210** |

So the three extra toolsets cost 1,536 tokens per call — real, but small next to the ~14.7 K
floor of Hermes's own core tool schemas and scaffolding.

### Levers, ranked by measured impact

1. **Remove bundled skills** — 5,163 per call, ~26 K per turn. **Tried, reverted: it breaks
   delegation.** See below.
2. **Make fewer model calls.** Every avoided round trip saves a whole system prompt (~16 K).
   **Tried, reverted:** instructing the Researcher to batch its two lookups did cut the turn to
   47,817 tokens — but it achieved that by silently skipping delegation and memory entirely,
   and leaked the Writer's persona as the answer. A cheaper turn that does less work is not an
   optimisation.
3. **Drop toolsets you are not using** — 1,536 per call, ~7.7 K per turn, but only available if
   you give up delegation or memory.
4. **Trim tool results** — ~161 tokens across the whole turn. Not worth touching.

### Delegation on Qwen3-32B is a coin flip

Before trusting any of the causal claims below, the baseline had to be measured. Eight runs of
the identical query against the identical config:

**`delegate_task` fired in 4 of 8 runs.**

When it fires, the memo is correct. When it does not, the model emits `delegate_task(goal="…")`
as text — the same failure mode as Llama-3.1-8B, just intermittently rather than always. So the
capability ladder is not hosted-works / open-fails. It is:

| Model | Nested delegation |
|---|---|
| `gpt-5-mini` | reliable |
| `qwen/qwen3-32b` | **~50%** |
| `meta-llama/llama-3.1-8b` | never |

Qwen sits exactly on the boundary. **This is the single most important number on this page for
anyone planning to run a multi-agent workflow on open weights** — a 50% success rate on the
step that defines the product is not a working system, and a single successful demo run would
have hidden it completely.

It also means the failure analyses below were over-attributed. With a 50% baseline, one failed
run proves nothing. Only `tool_search` produced a distinct, repeatable error signature; the
skills and batching conclusions are downgraded to "not demonstrated".

### The skills/delegation trade-off

Disabling the 17 bundled skills is the largest single saving available (5,163 per call). With
skills removed, Qwen failed to delegate — but given the 50% baseline above, **one failed run is
not evidence**. Treat this as unproven rather than established; it would need ~10 runs each way
to separate from noise, which was not worth the API spend here. Skills are left enabled because
the saving is not worth the risk on a model that is already marginal at this step.

The observed failure looked like this — the same shape as Llama-3.1-8B:

```
delegate_task(
goal="You are a trade compliance officer writing a due-diligence memo …
```

`delegate_task` never fired, no Writer was spawned, and the persona leaked into the user-facing
answer. Restoring the skills directory fixed it immediately, on the same model and the same
query. Nothing else changed.

The likely mechanism is that one of the bundled skills (`hermes-agent`, which Qwen's own
reasoning trace mentions consulting) carries guidance on Hermes's internal tool conventions,
including delegation. An open model appears to lean on it; the hosted model did not need it.

So the 24% saving is real and unusable here. **Skills stay enabled.** The honest framing for
anyone tuning this: prompt-size optimisations and instruction-following reliability trade
against each other, and on open-weight models the margin is thin enough that a 24% saving can
cost you a whole agent.

### Both false economies had the same shape

Three separate times in this exercise, something looked like a win because it did less work:

- Llama-3.1-8B "finished in 21 s" — by never delegating.
- Batching instructions cut the turn 40% — by never delegating.
- Removing skills cut 24% per call — by breaking delegation.

Latency and token counts are only comparable between runs that produced the same deliverable.
Measure the output first, the cost second.

The counter-intuitive result: in an agentic loop, **what you send is dominated by how many times
you send it**, not by how much the tools return. Optimising payloads is the obvious instinct and
the wrong one.

**Delegation is not free either.** The Writer is a full agent with its own system prompt, so a
handoff pays that prefix again inside the child. It buys context isolation and an independent
reasoning budget — worth it here, but it is a real cost, not a formatting step.

## So what is the floor, and what did we actually fix?

**Superseded — see "The optimisation that actually mattered" below.** The figures in this
section were measured with the gateway accidentally running Hermes's full default toolset.
The real floor is ~6,900 per call.

**Measured (mis-measured) floor: ~21,000 prompt tokens per model call**, and a handoff
turn makes four to five calls — 55,000–80,000 tokens to answer one question.

Where it goes, per call:

| | Tokens |
|---|---|
| Hermes core scaffolding + 49 always-on tool schemas | ~14,700 |
| Bundled skills | ~5,200 |
| Handoff toolsets (delegation, memory, session_search) | ~1,500 |
| **Fixed cost per call** | **~21,400** |
| Everything the conversation actually contains | ~1,500 **per turn** |

Hermes loads all 49 core tools — browser automation, kanban, Home Assistant, terminal, image
generation — regardless of `platform_toolsets`. This agent uses five of them.

A purpose-built agent for this job needs a ~600-token identity, two tool schemas, and two or
three calls: **roughly 2,000–5,000 tokens per turn**. Hermes is therefore **10–20× heavier in
tokens** for this workload.

That is the honest shape of the trade-off, and it belongs in the LangChain comparison: Hermes
gives you delegation, memory, sessions, MCP and a gateway without writing any of it, and charges
~21 K tokens per model call for the privilege. Assembling only what you need is cheaper per call
and costs you the runtime.

### What we actually fixed

1. **`max_tokens` 65,536 → 16,384.** Not a saving — an unblocking. OpenRouter was refusing
   requests outright on reserved credit.
2. **Provider configs are now replaced, not merged.** Switching to OpenRouter had silently kept
   OpenAI's `base_url`.
3. **Country aliases and `hs_code` typing.** Cut the same query from four tool calls to two,
   which is a whole model call saved — worth more than any payload trimming.

### What we tried and backed out

| Attempt | Apparent saving | Why it was rejected |
|---|---|---|
| Disable bundled skills | 24% per call | Delegation failed after — unproven against a 50% baseline, not worth the risk |
| Instruct the agent to batch lookups | 40% per turn | Skipped delegation and memory entirely |
| `tool_search` deferred tool loading | 19% per call | Deferred the MCP tools too; the model was told to "use tool_search to find tools you can call", gave up, and answered from memory |

### A trap in our own overlay design

Removing `tool_search` from the repo overlay did not remove it from the live profile. `run.py`
**merges** overlays onto the profile's existing config, so deleting a key upstream leaves it in
place downstream — the same class of bug as the `base_url` leak, and it cost an hour of
misdiagnosis because the running agent no longer matched the repo. Deleting a setting means
deleting it from the profile config too.

## The optimisation that actually mattered

Everything above about a ~21 K floor and Hermes being "10-20x heavier" was **wrong**, and the
cause was a misconfiguration in this repo, not the framework.

Toolsets are resolved **per platform** (`hermes_cli/tools_config.py`:
`platform_toolsets.get(platform)`). The CLI and the gateway are different platforms — the
gateway identifies itself as `api_server` (`gateway/platforms/api_server.py`). This project set
only:

```yaml
platform_toolsets:
  cli: [trade-compliance, delegation, memory, session_search]
```

So every request through the web UI fell through to Hermes's **full default toolset** — all 49
core tools, browser automation and kanban and Home Assistant included. The restriction we
thought we had was never applied to the surface we were actually demoing. It failed silently:
no warning, no error, just four times the prompt.

Adding `api_server` with the same list:

| | Prompt tokens per call | Per handoff turn |
|---|---|---|
| Before (gateway on default toolset) | **21,373** | 54,600 – 80,111 |
| After (gateway scoped to 4 toolsets) | **6,932** | **14,400 – 22,700** |
| Saving | **68%** | **~70%** |

**Reliability improved too**, which is the more interesting result. Delegation success went from
**4/8 to 3/4** on the identical query and model. Fewer irrelevant tool schemas appears to mean
less for the model to get lost in — the same intervention bought both cost and correctness.
Small samples, but the direction matches the mechanism.

### Why this one was worth finding and the other four were not

The four rejected attempts — disabling skills, batching instructions, deferred tool loading,
capping `max_tokens` hard — all traded capability for tokens. This one removed work that was
never wanted: tool schemas for a browser, a kanban board and a smart-home integration, in a
sanctions-screening agent.

The general lesson: before optimising what a system does, check what it is doing that you never
asked for. A config key that silently doesn't apply is worth more than every prompt-trimming
trick combined.

## Final cost picture

With the gateway correctly scoped, measured per model call (`"say ok"`, no tools, no history):

| Configuration | Tokens per call | What it buys |
|---|---|---|
| **Part 1 — single mode**, 1 toolset | **2,329** | Hermes runtime + SOUL.md + the two research tools |
| **Part 2 — handoff mode**, 4 toolsets | **6,932** | the above + delegation, memory, session_search |
| Difference | **4,603** | almost entirely `delegate_task`'s schema, which is large because it documents roles, parallel batch mode, background execution and depth limits |

End to end, measured on real handoff turns: **14,400 – 22,700 tokens to answer one question**,
against 54,600 – 80,111 before the platform fix.

**Part 1 is essentially at the floor.** 2,329 tokens is Hermes's own instructions plus our SOUL
plus two tool schemas — there is nothing meaningful left to remove without deleting features.

**Part 2's extra 4,603 is the price of the multi-agent capability**, not waste. `delegate_task`
carries a long schema because it is a genuinely complex tool. You can decline to pay it by not
delegating; you cannot pay less and still delegate.

### What is genuinely left

- **Drop `session_search`** (~1.5 K/call) if MEMORY.md alone is enough. It is not: the
  cross-session recall demo works *because* the agent searches past transcripts for facts that
  were never written to MEMORY.md.
- **Fewer model calls.** Still the highest-leverage lever, and still the one that keeps breaking
  the workflow when forced with prompt instructions. Fixing the argument bugs earlier — country
  aliases, `hs_code` typing — removed two failed calls from the same query, which is the version
  of this that actually worked: fix the cause, don't instruct around it.

The honest summary: after the platform fix, this is a normally-priced agent. The remaining spend
is delegation, and delegation is the product.

### Turning off MCP discovery: small, but the right *kind* of fix

MCP has three primitives — tools, resources and prompts — and Hermes registers a discovery tool for
each family a server advertises: `list_resources`, `read_resource`, `list_prompts`, `get_prompt`.
Our server exposes two tools and nothing else. But **FastMCP advertises the resources and prompts
capabilities unconditionally**, so Hermes was right to believe there was something to browse, and
offered the agent four tools that could only ever return empty.

Hermes does try to filter these — `_select_utility_schemas` checks the server's advertised
capabilities before registering. That gate simply cannot fire when the server over-advertises. So
we say it explicitly in `agents/researcher/config.yaml`:

```yaml
mcp_servers:
  trade-compliance:
    tools:
      resources: false
      prompts: false
```

| | prompt tokens/call |
|---|---|
| before | 6,932 |
| after | **6,694** |

238 tokens — about 60 per schema, which is what four small schemas should cost. Small. The reason
it is worth doing anyway is the *other* effect: on qwen2.5:3b, two of the model's calls went to
`list_prompts` and `list_resources` before it answered. A wasted call costs a full round trip, not
60 tokens.

The alternative was a line in `SOUL.md` telling the model not to call them. That was the first
instinct and it is worth naming why it is weaker: a prompt instruction *asks*, and the schemas
stay in context either way. Config *removes*. Anything the model cannot see, it cannot waste a
call on — this is the same lesson as the `platform_toolsets` fix, just three orders of magnitude
smaller.

Worth being clear about when discovery **is** the point: a server backed by many or changing items
— a filesystem, a document store, PST.AG's 250+ trade agreements — needs the agent to browse,
because the useful set cannot be enumerated in a tool list. Ours is two fixed tools. Discovery is
pure overhead here and load-bearing there; the config switch is how you say which.

### Saying the same thing twice: SOUL.md vs the tool descriptions

`SOUL.md` described both tools — "`screen_party` (checks a name against real US restricted-party
lists)" — and so did each tool's docstring, which is what Hermes actually sends as the tool
description. The `screen_party` docstring also ended with "never guess sanctions status without
calling this", which `SOUL.md` already states as a standing rule. Duplicated in both directions.

The dividing line that survived the argument:

| | belongs in |
|---|---|
| what a tool does, when to pick it, how to call it | its docstring — per-tool, routing |
| standing rules that outlive any one tool | `SOUL.md` — cross-cutting, policy |

So `SOUL.md` keeps "you MUST call the relevant tool — never answer from your own training
knowledge" (true of any tool we ever add) and drops the per-tool descriptions.

The real argument for deduplicating is not tokens, it is **drift**: a docstring travels with the
function it documents, a paraphrase in `SOUL.md` does not. Rename a tool and the model gets two
descriptions that disagree.

**Two things went wrong measuring it, both instructive.**

*First attempt made the prompt bigger.* The replacement read "What each does and when to pick it
is in its own description — this file does not restate it, so there is only one place to change
when a tool changes." That explanation is for the human reading the repo, and `SOUL.md` is
**model-facing** — it has no comment syntax, so every word ships on every call, forever. 6,694 →
6,731, +37. Rationale belongs in this file, or a commit message, or a YAML comment; never in the
system prompt. Trimming to just the tool names: 6,696.

*The end-to-end number then lied.* +2 total, when the edited text had demonstrably shrunk 40
tokens. The confound was `memories/MEMORY.md` — the verification query run in between had written
a screening outcome into it, adding ~42 tokens to every subsequent call.

```
  our text        -40
  MEMORY.md grew  +42
  ─────────────────────
  net              +2
```

Worth stating plainly because it generalises: **long-term memory is a slowly rising tax on every
call.** It is not a one-off cost, it grows with use, and it makes naive before/after token
comparisons untrustworthy unless memory is held still. Any real optimisation measurement here has
to control for it — or measure the edited text directly, which is what settled this one.

Behaviour after the change, single mode, three identical runs: `HIT` verdict 3/3, both tools
called 3/3, 4,890 prompt tokens 3/3. Routing did not degrade — unsurprising, since the
descriptions the model routes on never moved.

## A hypothesis that failed: shrinking the delegation payload

`delegate_task` carries by far the largest argument in this system — the Writer's persona plus
every gathered fact, well over a thousand tokens of prose inside a JSON field. The obvious theory
was that its size is what makes the call fragile, so the persona was cut from 417 tokens to 105
(75% smaller) and re-tested on Qwen3-32B, six runs, identical query.

| Persona | Delegation fired |
|---|---|
| Full (417 tokens) | 4/8 |
| Compact (105 tokens) | **3/6** |

**No improvement**, and output quality got worse: one run leaked the persona text into the memo
itself, because the compact version dropped the explicit "line one is the decision, and nothing
else" rule that was holding the format. Reverted.

### What the failures actually look like

Worth being precise, because it is not what "unreliable tool calling" suggests. Every failed run
produced this shape:

```
delegate_task(
    goal="You are a compliance officer writing a due-diligence memo…
          Line 1 is the decision: DO NOT PROCEED…",
    context="Original question: Germany iron and steel (HS…
```

The model **decided to delegate correctly** and **composed correct arguments** — right decision,
right lists, right figure. It then wrote them as plain text instead of emitting them through the
structured tool-calling channel.

That is a **serialisation failure, not a reasoning failure**, and it reframes the whole finding:

- The two research tools never failed once, on any model, including Llama-3.1-8B.
- What varies between models is not whether they can *use* tools, but whether they reliably emit
  a large call through the structured channel rather than narrating it.
- So the fix is not a better prompt or a smaller payload. It is model selection:
  `qwen3.7-flash` delivered 3/3 where `qwen3-32b` gives roughly half.

**Practical consequence:** run the demo on `MODEL=fast`. It is faster (~28 s vs ~54 s), cheaper,
and the only configuration measured to delegate every time.

## The self-hosted half: Ollama, actually run

Earlier this page asserted that local hosting was infeasible on an 8GB machine — that Hermes's
64K context floor could not be met because the system prompt was ~55K. **That assertion was
written before the platform-toolset fix and is wrong.** With the prompt at ~7K it fits easily.
The optimisation is what made the requirement achievable; the constraint was self-inflicted.

Run for real, `qwen2.5:3b` under Ollama on an 8GB MacBook Air:

| | Result |
|---|---|
| Model load at `num_ctx: 65536` | **12.9 s**, succeeded |
| Resident memory once loaded | ~4.1 GB wired (weights are 1.9 GB — the 64K KV cache is the rest) |
| Free RAM during the run | ~120 MB |
| Tool call | ✅ `screen_party` fired, returned real SDN/EL/SSI matches |
| Answer | correct — named all three lists |
| **Latency** | **153.8 s** |

So the "self-hostable" claim in Part 3 is not theoretical here: the same agent, same tools, same
config mechanism, running against weights on the laptop with no cloud model involved.

**The floor is checked against what Ollama actually loaded**, not what the config declares
(`agent/conversation_loop.py`) — so `ollama_num_ctx: 65536` is mandatory. Declaring 64K while
quietly allocating less is not possible, and that KV cache is what costs the memory, not the
weights.

### What it costs

**153.8 s versus ~25 s** for the same class of question on `qwen3.7-flash` via OpenRouter — about
6× slower, on a machine with no free RAM. Usable for a demonstration; not usable as a product.

### And it is not only slower — re-run after the REVIEW work

Re-tested once the tool started returning `match_quality`, on the same 3B model (46 s this time,
the model already resident):

> `HIT` — Rosneft Trading S.A. — match_quality: "exact" — **the party is not sanctioned**, based
> on screening against US government restricted-party lists.

Right verdict word, right field quoted from the payload, and then the opposite of what both mean,
in the same sentence. The tool call was correct and the data was correct; the model could not hold
the finding together in prose.

`qwen3.7-flash` given the identical payload answers correctly every time. So the failure is not
the tools, the schema or the prompt — it is capacity, and it shows up precisely where a compliance
answer must not fail: in the sentence a human reads.

Which sharpens the Part 3 conclusion. "Runs on open weights" and "is safe on open weights" are
different claims:

| | qwen2.5:3b, local | qwen3.7-flash, hosted |
|---|---|---|
| Calls the right tool | ✅ | ✅ |
| Reads the payload | ✅ | ✅ |
| States the finding coherently | ❌ **contradicted itself** | ✅ |
| Latency | 46–154 s | ~25 s |

The portability is real and is worth demonstrating — same agent, same tools, one config line. The
honest recommendation is still a larger model for anything a compliance officer would act on, and
a 3B model only for proving the swap works.

Quality also drops noticeably. The 3B model got the facts right but ignored the response contract
in `SOUL.md`: no `HIT` verdict line, several hundred words of hedging, and it named the internal
tool (`mcp__trade_compliance__screen_party`) in user-facing output. Compare the cloud models,
which produce the memo format as instructed.

It also burned two calls on `list_prompts` and `list_resources` — the MCP discovery tools that
exist because FastMCP advertises resource and prompt capabilities our server does not implement.
Larger models ignore them; this one went looking.

### The honest framing for Part 3

| | Cloud endpoint (OpenRouter) | Self-hosted (Ollama) |
|---|---|---|
| Open weights | ✅ | ✅ |
| Runs the tools | ✅ | ✅ |
| Runs the handoff | ✅ (`qwen3.7-flash` 3/3) | ✗ not attempted — an 8B could not delegate, a 3B will not |
| Latency | ~25 s | ~154 s |
| Cost | ~$0.001/turn | free |
| Data leaves the machine | yes | **no** |

Both halves of the requirement are real. The split is deliberate: the cloud endpoint carries the
live demo because it is six times faster and can complete the handoff; Ollama proves the same
configuration runs on hardware you own, which is the claim that matters for a company selling
sovereign compliance data.
