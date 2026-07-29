# Hermes Agent Exercise — Trade Compliance Researcher

> Built on the real **Nous Research Hermes** agent runtime (open source, MIT) — not a
> from-scratch agent loop and not LangChain.

A **single tool-using agent** that scales into a **2-agent collaborative workflow**, and runs on
**hosted or open-weight models with a one-line config change** — *not* a rewrite. That last point
is the core Hermes strength (and the sharpest contrast with LangChain).

## Status

| Part | Requirement | Status | How to run |
|------|-------------|--------|------------|
| **1** | Single tool-using agent | ✅ **Done** — tag `v1-single` | `python run.py --mode single` |
| **2** | Researcher → Writer handoff + long-term memory | 🚧 next | `python run.py --mode handoff` |
| **3** | Open-weight models, no Anthropic | 🚧 planned | `MODEL=ollama docker compose up` |
| — | Hermes vs LangChain comparison (presented live) | ✅ **Done** | [`docs/hermes-vs-langchain.md`](docs/hermes-vs-langchain.md) |

## What it does

A **trade-compliance due-diligence assistant**. Before signing with an international counterparty,
an analyst has to answer two questions: *are we allowed to trade with this party*, and *does this
shipment size make sense for this trade lane*. The Researcher answers both from **real data**,
never from model memory.

| Tool | Data source | Returns |
|------|-------------|---------|
| `screen_party` | [trade.gov Consolidated Screening List](https://data.trade.gov) — 11 combined US restricted-party lists (OFAC SDN, BIS Entity List, BIS Denied Persons, State Dept debarred parties, …) | match / no-match, and which lists matched |
| `trade_data_lookup` | [UN Comtrade](https://comtradeapi.un.org) | real export value for a country pair, HS chapter, and year |

Verified live, end to end:

```
> Is Rosneft on any US restricted-party list?
Hit found — Rosneft appears on multiple U.S. restricted-party lists.
  · Specially Designated Nationals (SDN) — U.S. Treasury (OFAC)
  · Sectoral Sanctions Identifications (SSI) — U.S. Treasury (OFAC)
  · Entity List (EL) — Bureau of Industry and Security (BIS)

> How much steel did Germany export to India in 2022?
USD 437,432,476 of iron & steel (HS chapter 72), country-level aggregate. Source: UN Comtrade.

> How much steel did Germany export to India in 2099?
No data available. (Reported honestly — not fabricated.)
```

Every tool failure mode — no match, no data, unrecognised country, API error — returns an
**explicit** result. The agent is instructed never to fill a gap with a plausible-sounding guess,
which matters more in compliance than almost anywhere else.

## Setup

```bash
cp .env.example .env          # add your keys
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

hermes profile create hermes-exercise \
  --description "PST.AG exercise: trade compliance Researcher/Writer agents"

export $(grep -v '^#' .env | grep -v '^$' | xargs)
python run.py --mode single
```

Keys needed: `OPENAI_API_KEY`, and a free `TRADE_GOV_API_KEY` from
[developer.trade.gov](https://developer.trade.gov).

`run.py` merges this repo's config overlay and the selected model overlay into the Hermes
profile, then launches an interactive session — Hermes's own defaults are preserved, not
overwritten.

## The model swap = Part 3 in one line

Provider is chosen by the `MODEL` env var, which selects an overlay in [`config/`](config):

```bash
MODEL=openai     python run.py --mode single   # hosted
MODEL=openrouter python run.py --mode single   # open-weight via cloud endpoint
MODEL=ollama     python run.py --mode single   # open-weight, local
```

No agent or tool code changes between them — that's the point.

## Layout

```
run.py                      # entrypoint: --mode single | handoff ; reads MODEL env
agents/researcher/
  SOUL.md                   # agent identity — tools-first, never guess
  config.yaml               # MCP server registration + toolset exposure (overlay)
trade_tools/trade_mcp/
  logic.py                  # the two tools' real work: HTTP + response normalisation
  server.py                 # stdio MCP server — docstrings are what route the model
  countries.json            # country name → UN M49 code lookup
config/model.{openai,openrouter,ollama}.yaml   # Part-3 provider overlays
docs/hermes-vs-langchain.md # the 1-page comparison
docs/superpowers/           # design spec + implementation plan
```

**Lines of agent-loop code written: zero.** Hermes supplies the ReAct loop, tool dispatch, session
persistence, memory, and delegation; this repo supplies identity, tools, and config. See the
[comparison doc](docs/hermes-vs-langchain.md) for what the same system would look like in
LangChain.

## Notes

- Tools are exposed over **MCP** (stdio). A tool's **docstring is the routing signal** — what
  teaches the model when to call it.
- Hermes deliberately strips the parent environment when spawning MCP subprocesses
  (`_build_safe_env`), so secrets need explicit `${VAR}` passthrough in the server's `env:` block.
- `trade_data_lookup` is country-level aggregate data only — company-level questions belong to
  `screen_party`. Recent years are often unpublished; "no data" is the correct answer, not an error.

Git tags tell the progression: `v1-single` → `v2-handoff` → `v3-open-weight`.
