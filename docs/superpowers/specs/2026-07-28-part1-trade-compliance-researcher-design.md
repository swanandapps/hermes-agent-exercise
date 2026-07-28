# Part 1 — Trade Compliance Researcher (single tool-using agent)

> Design spec for the "Part 1 — Hermes fundamentals" requirement of the PST.AG Hermes Agent
> exercise (see [`HANDOFF.md`](../../../HANDOFF.md)). Covers goal, scope, architecture, and
> done-criteria only for Part 1. Part 2 (handoff + memory) and Part 3 (open-weight models)
> build on this but are separate specs.

## Goal

Build a single Hermes agent — the **Researcher** — that answers real trade-compliance
due-diligence questions using two genuine external data tools, not from model memory.

**Why this domain:** PST.AG (the hiring company) sells global trade compliance data — sanctions
screening, export control, and trade-agreement data across 160+ countries. This agent mirrors
the actual due-diligence workflow a compliance analyst performs before a deal: (1) is this
party allowed to trade with us, and (2) does this shipment size make sense for this trade lane.
Building in PST.AG's own problem space is a deliberate choice, not incidental.

**Definition of done:** running `python run.py --mode single` starts an interactive session
against a dedicated Hermes profile where a live question such as *"can Rosneft receive
shipments from a German steel exporter?"* triggers real tool calls (not hallucinated answers),
and at least one deliberately thin/edge-case query is demoed to show the agent reports "no
data" honestly instead of fabricating a plausible-sounding answer.

## Out of scope for Part 1 (explicitly deferred)

- **Writer agent / `delegate_task` handoff** — Part 2.
- **Long-term memory (`MEMORY.md`/`USER.md`/`session_search`)** — Part 2. Nothing in Part 1
  requires cross-session recall.
- **Model provider swap (`MODEL=openrouter`/`ollama`)** — Part 3. Part 1 runs OpenAI only.
- **Policy/regulation-lookup Skill** — stretch item, only if Day 1 finishes early. Not required
  for a complete, defensible Part 1.
- **Any UI beyond the terminal** — terminal-first is the deliberate choice. A basic front end is
  planned as a deliberate **final phase across all three parts** (Part 1, 2, and 3 each get
  terminal-verified first; the UI is attached last, once all three work end-to-end on terminal).
  Not started until explicitly requested.

## Architecture

```
agents/researcher/
  SOUL.md              # identity: trade-compliance research assistant, tools-first, no guessing
  config.yaml          # mcp_servers + agent blocks; model block merged in at run time

tools/trade_mcp/
  server.py            # stdio MCP server exposing screen_party + trade_data_lookup
  countries.json        # static country-name -> UN M49 numeric code lookup table

run.py --mode single    # already scaffolded; merges agents/researcher/config.yaml with
                         # config/model.<MODEL>.yaml (MODEL=openai for Part 1), writes the
                         # result into the profile, launches an interactive `hermes -p <profile>` session
```

**Hermes profile:** a fresh, isolated profile (e.g. `hermes-exercise`), created via
`hermes profile create <name> --clone <base>` — never the default profile or the existing
`munshi`/`the01dev` profiles, so this exercise's `SOUL.md`/memory never mixes with unrelated
projects (see HANDOFF §5 and the profile-isolation discussion in this project's history).

## Tools

### `screen_party(name: string)`

- **API:** trade.gov Consolidated Screening List (`developer.trade.gov`) — combines 11 official
  US restricted-party lists (OFAC SDN, BIS Entity List, BIS Denied Persons, State Dept debarred
  parties, etc.) into one feed.
- **Auth:** requires a free `subscription-key` (`TRADE_GOV_API_KEY`), obtained via signup at
  developer.trade.gov. **Action item before Part 1 testing can complete: sign up for this key.**
  Add `TRADE_GOV_API_KEY=` to `.env.example`.
- **Behavior:** calls with `fuzzy_name=true` (catches near-matches/spelling variants). Strips the
  raw response down to `{matched: bool, hits: [{name, source_list, entity_type}]}`. No matches
  returns the explicit string `"no matches found"` — never an empty/silent result.

### `trade_data_lookup(reporter_country: string, partner_country: string, hs_code: string, year: int)`

- **API:** UN Comtrade public preview endpoint (`comtradeapi.un.org/public/v1/preview/...`) —
  verified live and working with no API key required.
- **Behavior:** translates `reporter_country`/`partner_country` (plain names, e.g. "Germany")
  to UN M49 numeric codes via the bundled `countries.json` lookup table. `hs_code` is a 2-digit
  HS chapter (e.g. 72 = iron/steel) supplied directly by the model — no fuzzy product-name
  matching is built; the tool's docstring lists common codes as a hint. Filters the ~20-row raw
  response down to the real reported total, returning `{value_usd, year, reporter, partner,
  product}`. No data for the query returns the explicit string `"no data available for this
  query"`.
- **Known limitation, worth demoing deliberately:** country-level aggregate only — cannot answer
  company-level/shipment-level questions (that's `screen_party`'s territory), and recent/current
  years are often not yet published (real publication lag).

### Shared design rule for both tools

Every tool always returns small, pre-cleaned, structured output — never raw upstream payloads —
and every failure mode (no match, no data, API error, unrecognized country) is an explicit
string, never a silent empty result. This is deliberate: it is what stops the model from filling
a gap with a plausible-sounding guess, and it is a good moment to point at live.

## Config

- `config.yaml`: `mcp_servers` block (stdio transport, points at `tools/trade_mcp/server.py`);
  model block merged from `config/model.openai.yaml` for Part 1 (per HANDOFF §5's validated
  `provider: custom` pattern — there is no built-in `"openai"` provider). Model must be
  reasoning-capable (e.g. `gpt-5-mini`, or another reasoning model such as GPT-5.1 if preferred —
  confirm it doesn't 400 on `reasoning_effort` the same way `gpt-4o-mini` does).
- `SOUL.md`: short identity — trade-compliance research assistant, use tools, never guess
  sanctions status or trade figures from memory.

## Error handling philosophy

Already stated above per-tool; restated once because it's a cross-cutting design decision, not
a per-tool afterthought: explicit failure strings everywhere, no silent empty results, no
fabricated numbers when real data is unavailable.

## Testing plan

No formal automated test suite required for the demo itself. Before relying on either tool
live: a couple of small smoke-test scripts that call `screen_party`/`trade_data_lookup`
directly (bypassing the LLM entirely) to confirm both APIs are reachable and parsed correctly —
cheap insurance against an API hiccup during a recording or live walkthrough.

**Example queries to validate against** (from design discussion, useful as informal acceptance
checks):

*Should work:*
- "How much steel did Germany export to India in 2022?"
- "What's the crude oil trade from Saudi Arabia to China in 2023?"
- "Is [a test name] on any US restricted-party list?"

*Should fail gracefully, and are good to demo on purpose:*
- A query for the current/very recent year (publication lag → explicit "no data")
- A company-level trade-volume question (wrong tool's territory → agent should not misuse
  `trade_data_lookup`)
- An obscure/aliased country name not in `countries.json` (explicit "unrecognized country")

## Git workflow for this part

`git init` now if not already done; first commit = current scaffold as-is. One commit per
logical, still-runnable step (profile+SOUL.md+config → screen_party tool → trade_data_lookup
tool → MCP wiring + `run.py --mode single` working end-to-end → `.env.example` key). Tag
`v1-single` once the definition of done above is met. Push to GitHub with explicit confirmation
at that point, not silently.

## Open item

`TRADE_GOV_API_KEY` signup at developer.trade.gov must happen before `screen_party` can be
tested for real — flagged as the first thing to do on Day 1, not something to discover mid-build.
