# Hermes Agent Exercise — Trade Compliance Researcher

> Built on the real **Nous Research Hermes** agent runtime (open source, MIT) — not a
> from-scratch agent loop, and not LangChain.

A **single tool-using agent** that scales into a **two-agent collaborative workflow**, and runs on
hosted *or* open-weight models by changing one config line — not by rewriting anything.

| Part | Requirement | Status |
|------|-------------|--------|
| **1** | Single tool-using agent | ✅ `v1-single` |
| **2** | Researcher → Writer handoff + long-term memory | ✅ `v2-handoff` |
| **3** | Two open-weight models, no Anthropic, Dockerised | ✅ `v3-open-weight` |
| — | [Hermes vs LangChain](docs/hermes-vs-langchain.md) (presented live) | ✅ |
| — | [Performance notes](docs/performance.md) | ✅ |

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

## Run it

### Docker (everything, no Anthropic)

```bash
cp .env.example .env      # add OPENROUTER_API_KEY and TRADE_GOV_API_KEY
export $(grep -v '^#' .env | grep -v '^$' | xargs)
MODEL=fast docker compose up --build
```

Open **http://localhost:8000**.

Three services: `gateway` (Hermes + this project's MCP tools), `app` (FastAPI relay + built React
UI), and an optional `ollama` for the self-hosted path. For `MODEL=openrouter`/`fast` the model is
a cloud API — only the Ollama path runs weights in a container.

> Stop any local `hermes gateway` / `uvicorn` first — they bind the same ports, and on macOS both
> can hold them, so you cannot tell which one answered.

### Local

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
hermes profile create hermes-exercise
cp .env.example .env            # add OPENROUTER_API_KEY and TRADE_GOV_API_KEY

./dev.sh                        # Part 1 — gateway + relay + UI, one command
./dev.sh handoff                # Part 2
MODEL=ollama ./dev.sh           # Part 3, self-hosted
```

Open **http://localhost:5173**. Ctrl-C stops all three.

`dev.sh` re-syncs the Hermes profile before starting. That matters: the profile lives outside
git, so switching branches does *not* update it, and demoing handoff against a stale single-mode
profile fails silently.

For the CLI instead of the UI: `python run.py --mode single|handoff`.

---

## The model swap is Part 3

`MODEL` picks an overlay in [`config/`](config). Nothing else changes — no agent code, no tool
code, no prompt:

```bash
MODEL=fast       # qwen3.7-flash    ← recommended: fastest, cheapest, most reliable
MODEL=openrouter # qwen3-32b
MODEL=llama      # llama-3.1-8b
MODEL=openai     # gpt-5-mini (hosted)
MODEL=ollama     # local, self-hosted
```

Adding a model is a four-line YAML file. See [docs/performance.md](docs/performance.md) for
measured latency, cost and reliability across them.

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
