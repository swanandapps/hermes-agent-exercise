# Part 3 — Running on open-weight models

The agent, tools, memory and delegation are unchanged across every row below. Only the `model:`
block differs — a different overlay in [`config/`](../config), selected by the `MODEL` env var.
No agent code, no tool code, and no prompt was modified to make an open model work.

That is the claim. This page is what happened when it was tested.

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

### Remaining levers, not yet applied

- **Trim tool results.** `screen_party` returns all nine Rosneft matches with full fields, and
  every one is re-sent on each subsequent model call in the turn. Collapsing to the three unique
  source lists would cut the largest repeated payload.
- **Fewer toolsets.** Handoff mode adds `delegation`, `memory` and `session_search`; each tool
  schema is prompt budget on every call. Single mode is meaningfully cheaper.
- **Delegation is not free.** The Writer is a full agent with its own system prompt, so the
  handoff pays that prefix a second time. It buys context isolation and an independent reasoning
  budget — worth it here, but it is a real cost, not a formatting step.
