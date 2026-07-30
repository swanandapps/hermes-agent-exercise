# Hermes Agent Exercise — Trade Compliance Researcher

> Built on the real **Nous Research Hermes** agent runtime (open source, MIT) — not a
> from-scratch agent loop, and not LangChain.

A **single tool-using agent** that scales into a **two-agent collaborative workflow**, and runs on
hosted *or* open-weight models by changing one config line — not by rewriting anything.

**This branch (`main`) is the complete application — all three parts.**

> ### Reviewing Part 1 on its own?
>
> ```bash
> git checkout part-1
> ```
>
> That branch is the single tool-using agent and the comparison document, and nothing else — no
> second agent, no memory, no Docker, no open-weight overlays.
>
> It is the same agent, not a cut-down copy: `SOUL.md`, `config.yaml` and everything under
> `trade_tools/` are **byte-identical** on both branches. Part 2 was added *alongside* Part 1
> rather than changing it, which is why the split is possible at all.

| Part | Requirement | Where |
|------|-------------|-------|
| **1** | Single tool-using agent | ✅ `main`, or the `part-1` branch on its own |
| **2** | Researcher → Writer handoff + long-term memory | ✅ `main` |
| **3** | Two open-weight models, no Anthropic, Dockerised | ✅ `main` |
| — | [Hermes vs LangChain](docs/hermes-vs-langchain.md) — one page, presented live ([evidence](docs/hermes-vs-langchain-detail.md), [PDF](docs/hermes-vs-langchain.pdf)) | ✅ |
| — | [Performance notes](docs/performance.md) — model comparison ([detail](docs/performance-detail.md)) | ✅ |

The `v1-single` / `v2-handoff` / `v3-open-weight` tags mark when each part was finished. They are
history, not the submission — a tag is frozen where it was placed, so those point at code from
before several fixes. Read the branches.

---

## What it does

**Pre-deal trade compliance due diligence.** Before signing with an international counterparty, an
analyst has to answer two questions: *are we allowed to trade with this party*, and *does this
shipment size make sense for this trade lane*. Both come from real data — never from model memory.

| Tool | Source | Returns |
|------|--------|---------|
| `screen_party` | [trade.gov Consolidated Screening List](https://data.trade.gov) — 11 combined US restricted-party lists (OFAC SDN, BIS Entity List, State Dept debarred parties, …) | which lists a party matched |
| `trade_data_lookup` | [UN Comtrade](https://comtradeapi.un.org) | real export value for a country pair, HS chapter and year |

In **handoff mode**, the Researcher gathers the facts and then delegates the write-up to a Writer
subagent, which returns a compliance memo:

```
> We are signing a steel deal with Rosneft Trading S.A. Screen them and check Germany
  iron and steel exports to the Russian Federation in 2022, then give me the memo.

  ⚙ screen_party        1.3s   name: Rosneft Trading S.A.
  ⚙ trade_data_lookup   1.9s   Germany → Russian Federation · HS 72 · 2022
  ⚙ memory              0.0s   recorded the screening outcome
  → RESEARCHER → WRITER AGENT    22.5s

  DO NOT PROCEED
  Rosneft Trading S.A. matched three US restricted-party lists: SDN (Treasury),
  Entity List (BIS), and SSI (Treasury). Germany → Russian Federation iron & steel
  (HS 72), 2022: USD 56,733,053.91. Escalate to sanctions counsel before any contact.
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
| **Docker Desktop** | the Dockerised path | not needed for local runs |
| **Ollama** | the self-hosted model only | [ollama.com](https://ollama.com); not needed otherwise |

**Two API keys**, both free:

| Key | Where | Used for |
|---|---|---|
| `TRADE_GOV_API_KEY` | the trade.gov developer portal, for the [Consolidated Screening List API](https://data.trade.gov) | sanctions screening — **required** |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | the model. A few dollars of credit is plenty |

The trade.gov key is sent as a `subscription-key` header, so it is the one issued by their own
developer portal for that API — not a generic api.data.gov key.

`OPENAI_API_KEY` is optional and only used by `MODEL=openai`. Nothing here needs an Anthropic key.

Tested on an Apple M1 (8 GB), Node 22, with Hermes on Python 3.11. The self-hosted model path is
memory-hungry — read [performance notes](docs/performance.md) before trying it on 8 GB.

> Hermes and this project do not have to share an interpreter: `hermes` only needs to be on
> `PATH`, and the MCP tool server is launched with whichever Python `run.py` is running under.
> A single 3.11–3.13 virtualenv for both is simplest, and that is what the steps below assume.

---

## Run it

### Step 1 — set up, once

```bash
git clone https://github.com/swanandapps/hermes-agent-exercise.git
cd hermes-agent-exercise

python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt      # this project's dependencies
pip install hermes-agent==0.19.0     # the runtime itself
hermes profile create hermes-exercise

cp .env.example .env                 # then put your two keys in it
export $(grep -v '^#' .env | grep -v '^$' | xargs)
```

### Step 2 — run it

**Pick one.** Each is a single command.

| Command | What runs | Open |
|---|---|---|
| `./dev.sh` | **Part 1** — one agent, three tools | http://localhost:5173 |
| `./dev.sh handoff` | **Part 2** — Researcher → Writer + memory | http://localhost:5173 |
| `MODEL=ollama ./dev.sh` | **Part 3** — local open-weight model | http://localhost:5173 |
| `MODEL=openrouter docker compose up --build` | **Part 3** — everything in Docker, no Anthropic | http://localhost:8000 |

`./dev.sh` starts the Hermes gateway, the FastAPI relay and the React UI together, waits for each,
and prints `✓ tools registered` when the agent can actually reach its tools. Ctrl-C stops all
three.

Then ask it something:

> *We are signing a steel deal with Rosneft Trading S.A. Screen them and check Germany iron and
> steel exports to the Russian Federation in 2022, then give me the memo.*

### Terminal instead of a browser

```bash
python run.py --mode single      # Part 1
python run.py --mode handoff     # Part 2
```

### For the local model (Part 3)

```bash
ollama pull qwen2.5:3b           # ~1.9 GB, once
MODEL=ollama ./dev.sh
```

Expect ~50 seconds per answer and read [performance notes](docs/performance.md) first — a 3B
model on 8 GB is a proof that the swap works, not a good demo. There is an `ollama` compose
profile too, but native is the documented path: Docker Desktop's memory allowance is usually
below what a 64 K context needs.

### Two things that will bite you

- **Stop any local `hermes gateway` / `uvicorn` before starting Docker.** They bind the same
  ports, and on macOS both can hold them, so you cannot tell which one answered.
- **The Hermes profile lives outside git** (`~/.hermes/profiles/hermes-exercise/`), so switching
  branches does not update it. `dev.sh` re-syncs it on every start, which is why you should
  launch through `dev.sh` rather than `hermes gateway` directly — a stale single-mode profile
  makes handoff fail silently.

---

## The model swap is Part 3

`MODEL` picks an overlay in [`config/`](config). Nothing else changes — no agent code, no tool
code, no prompt.

| `MODEL=` | Model | Open weights? | Notes |
|---|---|---|---|
| `openrouter` | Qwen3-32B | **yes** | the Part 3 demo — unambiguously self-hostable |
| `llama` | Llama-3.1-8B | **yes** | the second open model |
| `ollama` | Qwen2.5-3B | **yes, and running locally** | the self-hosted proof |
| `fast` | Qwen3.7-Flash | cloud-served | fastest and cheapest; the day-to-day default |
| `openai` | GPT-5-mini | no | hosted baseline, for comparison only |

Adding a model is a four-line YAML file. See [performance notes](docs/performance.md) for measured
latency, cost and reliability across them — including where the smaller open models break.

---

## Layout

```
run.py                       entrypoint — merges config overlays, launches Hermes
agents/
  researcher/SOUL.md         Researcher identity (+ .handoff variant for Part 2)
  researcher/config.yaml     MCP server + toolsets  (+ .handoff variant)
  writer/PERSONA.md          Writer subagent's identity, injected at delegation time
trade_tools/trade_mcp/
  server.py                  stdio MCP server — docstrings are what route the model
  logic.py                   the two tools' real work: HTTP + response normalisation
  countries.json             country name → UN M49 code
backend/app.py               FastAPI relay; keeps the gateway key server-side
frontend/src/                React UI — live audit trail of every tool call
config/model.*.yaml          provider overlays (Part 3)
Dockerfile.gateway           Hermes + our tools
Dockerfile.app               backend + built UI
docker-compose.yml           the three services
```

**Lines of agent-loop code written: zero.** Hermes supplies the ReAct loop, tool dispatch, session
persistence, memory and delegation. This repo supplies identity, tools and config.

---

## Notes worth reading before the code

- **Tools are an MCP server, not core tools.** That's the rung Hermes's own contribution guide
  (`AGENTS.md`, "the Footprint Ladder") recommends: every core tool is prompt cost for every user,
  forever. Ours cost nothing to anyone who doesn't register them.
- **A tool's docstring is the routing signal** — it is sent verbatim to the model as the tool
  description, and it is what teaches the model when to call it.
- **Toolsets resolve per platform.** The CLI and the gateway are different platforms
  (`cli` vs `api_server`); listing only one leaves the other on Hermes's full default toolset.
  Fixing that cut the prompt 68% and improved tool-calling reliability — see
  [docs/performance.md](docs/performance.md).
- **Hermes strips the environment when spawning MCP subprocesses** (`_build_safe_env`), so secrets
  need explicit `${VAR}` passthrough in the server's `env:` block. Good default, sharp edge.
- **Our package is `trade_tools/`, not `tools/`** — Hermes ships its own `tools` package, and once
  pip-installed it shadows a local one silently.

Tags follow the progression: `v1-single` → `v2-handoff` → `v3-open-weight`.
