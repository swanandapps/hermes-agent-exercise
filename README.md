# Trade Compliance Researcher — a single tool-using Hermes agent

> Built on the real **Nous Research Hermes** agent runtime (open source, MIT) — not a
> from-scratch agent loop, and not LangChain.

An agent that answers pre-deal due-diligence questions using real government data sources.

## Which branch

**This is `part-1` — Part 1 of the exercise, on its own.** One tool-using agent plus the
one-page Hermes vs LangChain comparison. No second agent, no long-term memory, no Docker, no
open-weight model overlays.

```bash
git checkout main     # the complete three-part system
```

It is not a cut-down copy: `SOUL.md`, `config.yaml` and everything under `trade_tools/` are
**byte-identical** on both branches. Part 2 was added *alongside* this agent rather than changing
it, which is what keeps the single-agent system independently runnable with the rest built on top.

New here? [What it does](#what-it-does) → [Prerequisites](#prerequisites) → [Run it](#run-it) →
[Documentation](#documentation).

---

## What it does

**Pre-deal trade compliance due diligence.** Before signing with an international counterparty, an
analyst has to answer two questions: *are we allowed to trade with this party*, and *does this
shipment size make sense for this trade lane*. Both come from live data — never from model memory.

| Tool | Source | Returns |
|------|--------|---------|
| `screen_party` | [trade.gov Consolidated Screening List](https://data.trade.gov) — 11 combined US restricted-party lists (OFAC SDN, BIS Entity List, State Dept debarred parties, …) | which lists a party matched |
| `trade_data_lookup` | [UN Comtrade](https://comtradeapi.un.org) | real export value for a country pair, HS chapter and year |

```
> Screen Rosneft Trading S.A. and check Germany iron and steel exports to the
  Russian Federation in 2022.

  ⚙ screen_party        1.3s   name: Rosneft Trading S.A.
  ⚙ trade_data_lookup   1.9s   Germany → Russian Federation · HS 72 · 2022

  HIT — Rosneft Trading S.A. matched three US restricted-party lists: SDN (Treasury),
  Entity List (BIS), and SSI (Treasury). Germany → Russian Federation iron & steel
  (HS 72), 2022: USD 56,733,053.91.
```

Every failure mode — no match, no data, unrecognised country, API error — returns an **explicit**
result. The agent is instructed never to fill a gap with a plausible guess, which matters more in
compliance than almost anywhere else.

---

## Prerequisites

| | Needed for | Notes |
|---|---|---|
| **Python 3.11–3.13** | everything | the floor is `hermes-agent`'s, not this project's — it declares `>=3.11,<3.14` |
| **Node 18+ / npm** | the web UI | Vite 5; skip it if you only want the CLI |
| **`hermes-agent`** | everything | the runtime. Installed separately — see below |

**One API key to add.** The other is already in `.env.example`:

| Key | Status | Used for |
|---|---|---|
| `OPENROUTER_API_KEY` | **yours to add** — [openrouter.ai/keys](https://openrouter.ai/keys) | the model. A few dollars of credit is plenty |
| `TRADE_GOV_API_KEY` | **already filled in** | sanctions screening, via the [Consolidated Screening List API](https://data.trade.gov) |

A working trade.gov key is committed to `.env.example` deliberately, so that setting this up is
one key and not two. It is free, read-only and not billable — it buys queries against a public
government list and nothing else, with no account or spend behind it. Keys that cost money or
carry an identity are left empty, which is the distinction being drawn rather than ignored. Get
your own from the trade.gov developer portal if you would rather; it is sent as a
`subscription-key` header, so it must be issued by that portal, not a generic api.data.gov key.

`OPENAI_API_KEY` is optional and only used by `MODEL=openai`. Nothing here needs an Anthropic key.

Tested on an Apple M1 (8 GB), Node 22, with Hermes on Python 3.11.

> Hermes and this project do not have to share an interpreter: `hermes` only needs to be on
> `PATH`, and the MCP tool server is launched with whichever Python `run.py` is running under.
> A single 3.11–3.13 virtualenv for both is simplest, and that is what the steps below assume.

---

## Run it

### Step 1 — set up, once

```bash
git clone -b part-1 https://github.com/swanandapps/hermes-agent-exercise.git
cd hermes-agent-exercise

python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt      # this project's dependencies
pip install hermes-agent==0.19.0     # the runtime itself
hermes profile create hermes-exercise

cp .env.example .env                 # then add your OpenRouter key
export $(grep -v '^#' .env | grep -v '^$' | xargs)
```

### Step 2 — run it

| Command | What you get | Open |
|---|---|---|
| `./dev.sh` | the agent with a web UI and a live audit trail | http://localhost:5173 |
| `python run.py` | the same agent in the terminal | — |

`./dev.sh` starts the Hermes gateway, the FastAPI relay and the React UI together, waits for each,
and prints `✓ tools registered` when the agent can actually reach its tools. Ctrl-C stops all
three.

Then ask it something:

> *Screen Rosneft Trading S.A. and check Germany iron and steel exports to the Russian Federation
> in 2022.*

The UI shows every tool call, its arguments, how long it took and the model's reasoning — so you
can watch the agent decide rather than just read its answer. Try `Screen Siemens AG` for a clean
result, and `Screen Google` for a partial match that is deliberately **not** reported as a hit.

### One thing that will bite you

The Hermes profile lives outside git (`~/.hermes/profiles/hermes-exercise/`), so switching
branches does not update it. `dev.sh` re-syncs it on every start — which is why you should launch
through `dev.sh` rather than calling `hermes gateway` directly.

---

## Documentation

| | Answers |
|---|---|
| **[Hermes vs LangChain](docs/hermes-vs-langchain.md)** · [PDF](docs/hermes-vs-langchain.pdf) | The one-page comparison, on the three dimensions the brief names: **architecture**, **tool definition**, **state management**. Ends with which framework to reach for given six concrete kinds of application. |
| **[Hermes vs LangChain — the code](docs/hermes-vs-langchain-detail.md)** | The same job written both ways, with code: the agent loop by hand, a tool as a decorator vs a plugin vs an MCP server, what a tool schema actually contains, memory, a second agent, swapping the model. |
| [`agents/README.md`](agents/README.md) | How identity and config reach Hermes, and what belongs in `SOUL.md` versus a tool's own description |
| [`trade_tools/README.md`](trade_tools/README.md) | Why the tools are an MCP server, and why a docstring is what routes the model |
| [`agents/researcher/SOUL.md`](agents/researcher/SOUL.md) | The agent's actual instructions — worth reading, it is short |

---

## Layout

```
run.py                       entrypoint — merges config overlays, launches Hermes
agents/researcher/
  SOUL.md                    the agent's identity and standing rules
  config.yaml                MCP server registration + which toolsets are exposed
trade_tools/trade_mcp/
  server.py                  stdio MCP server — docstrings are what route the model
  logic.py                   the two tools' real work: HTTP + response normalisation
  countries.json             country name → UN M49 code, with ~45 aliases
config/model.*.yaml          provider overlays — the model is config, not code
backend/app.py               FastAPI relay; keeps the gateway key server-side
frontend/src/                React UI — live audit trail of every tool call
docs/hermes-vs-langchain.md  the architectural comparison
```

**Lines of agent-loop code written: zero.** Hermes supplies the ReAct loop, tool dispatch and
session persistence. This repo supplies identity, tools and config.

---

## Notes worth reading before the code

- **Tools are an MCP server, not core tools.** That's the rung Hermes's own contribution guide
  (`AGENTS.md`, "the Footprint Ladder") recommends: every core tool is prompt cost for every user,
  forever. Ours cost nothing to anyone who doesn't register them.
- **A tool's docstring is the routing signal** — it is sent verbatim to the model as the tool
  description, and it is what teaches the model when to call it. `SOUL.md` deliberately does not
  restate it, so there is only one place to change when a tool changes.
- **Toolsets resolve per platform.** The CLI and the gateway are different platforms
  (`cli` vs `api_server`); listing only one leaves the other running Hermes's full 49-tool default
  set. Fixing that cut the prompt from 21,373 to 6,932 tokens per call — and improved
  tool-calling reliability, since a model given five tools picks better than one given 49.
- **MCP discovery is off.** FastMCP advertises the `resources` and `prompts` capabilities whether
  or not a server has any, so Hermes registers four browse tools that can only return empty.
  `tools.resources/prompts: false` removes them.
- **Hermes strips the environment when spawning MCP subprocesses** (`_build_safe_env`), so secrets
  need explicit `${VAR}` passthrough in the server's `env:` block. Good default, sharp edge.
- **Our package is `trade_tools/`, not `tools/`** — Hermes ships its own `tools` package, and once
  pip-installed it shadows a local one silently.
