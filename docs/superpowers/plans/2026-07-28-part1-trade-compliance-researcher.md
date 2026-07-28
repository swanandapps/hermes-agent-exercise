# Part 1 — Trade Compliance Researcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Researcher — a single Hermes agent, running in a dedicated profile, that
answers real trade-compliance questions using two genuine external-API tools (sanctions
screening + trade-volume lookup), demonstrable via `python run.py --mode single`.

**Architecture:** A fresh, isolated Hermes profile (`hermes-exercise`) hosts the agent's
`SOUL.md` + `config.yaml`. Two tools live in a small stdio MCP server (`tools/trade_mcp/`),
split into a pure `logic.py` (HTTP calls + response normalization, unit-testable without a
network call) and a thin `server.py` (FastMCP wrapper, one `@mcp.tool()` per tool — the
docstring IS the tool description Hermes's model sees). `run.py --mode single` deep-merges our
small config overlay (`agents/researcher/config.yaml`) and the selected model overlay
(`config/model.<MODEL>.yaml`) into the *existing* profile config Hermes already seeded on
`hermes profile create` (so we never clobber Hermes's own sensible defaults for compression,
memory, delegation, etc.), then launches an interactive `hermes -p hermes-exercise` session.

**Tech Stack:** Python 3.10+, `mcp>=1.0` (official MCP SDK, `FastMCP` — verified as the real
working pattern via the Munshi project's own trade MCP server on this machine), `httpx>=0.27`
for HTTP calls, `PyYAML` for config merging, `pytest` for tests. Real APIs: trade.gov
Consolidated Screening List (requires a free `TRADE_GOV_API_KEY`) and UN Comtrade public
preview endpoint (no key required — already verified live and working against Germany→India
steel-export data).

## Global Constraints

- Every tool failure mode (no match, no data, API error, unrecognized input) returns an
  **explicit string result**, never a silent empty value — per the spec's error-handling
  philosophy (`docs/superpowers/specs/2026-07-28-part1-trade-compliance-researcher-design.md`).
- Every tool returns small, pre-cleaned, structured output — never a raw upstream payload.
- The Hermes profile used is `hermes-exercise` — never the `default` profile or the existing
  `munshi`/`the01dev` profiles on this machine.
- Model must be reasoning-capable (`config/model.openai.yaml` already pins `gpt-5-mini`, which
  is confirmed working — do not swap to a non-reasoning model like `gpt-4o-mini`, which 400s on
  Hermes's `reasoning_effort`).
- No UI work of any kind in this plan — terminal only (see spec's "Out of scope").
- No Part 2 (delegation/memory) or Part 3 (model swap) work in this plan.

---

## Task 1: Hermes profile + agent identity/config source files

**Files:**
- Create: `agents/researcher/SOUL.md`
- Create: `agents/researcher/config.yaml`
- Create: `requirements.txt`
- Modify: `.gitignore` (confirm `.venv/` and `__pycache__/` are excluded — check existing file
  first, only add what's missing)

**Interfaces:**
- Produces: a live Hermes profile named `hermes-exercise` on this machine, and two repo source
  files that later tasks read from (`agents/researcher/SOUL.md`, `agents/researcher/config.yaml`).
  `config.yaml` here is a **small overlay**, not a full profile config — it only carries the keys
  this project adds (`mcp_servers`, `platform_toolsets.cli`), not Hermes's own defaults
  (compression, memory, delegation, etc.), which stay untouched in the profile's own config.

- [ ] **Step 1: Check current environment**

Run: `hermes profile list`
Expected: shows `default`, `munshi`, `the01dev` — confirms `hermes-exercise` does not exist yet.

- [ ] **Step 2: Create the isolated profile**

Run: `hermes profile create hermes-exercise --description "PST.AG exercise: trade compliance Researcher/Writer agents"`

(No `--clone`/`--clone-from` — we want Hermes's own clean bundled defaults, not another
profile's customized `SOUL.md`.)

Expected: command succeeds; `~/.hermes/profiles/hermes-exercise/` now exists with a default
`SOUL.md`, `config.yaml`, etc.

- [ ] **Step 3: Verify the profile launches with no customization yet**

Run: `hermes -p hermes-exercise "say hello in one sentence"`

(This will prompt for an API key/model setup on first use if not already configured — follow
the interactive prompts, selecting OpenAI/`gpt-5-mini` if asked, or Ctrl-C once you've confirmed
the profile itself is reachable; full model config gets nailed down properly in Task 4.)

Expected: the profile responds (proves the profile exists and is invocable) — do not worry yet
about identity/tools, those come next.

- [ ] **Step 4: Write the Researcher's identity**

Create `agents/researcher/SOUL.md`:

```markdown
# Identity

You are the **Researcher**, a trade-compliance research assistant. You help answer
due-diligence questions before a trade deal: is this party allowed to trade with us, and does
this shipment size make sense for this trade lane.

# Tools-first, never guess

You have two tools: `screen_party` (checks a name against real US restricted-party lists) and
`trade_data_lookup` (real country-to-country trade volume by product). For any question about
sanctions status or trade figures, you MUST call the relevant tool — never answer from your own
training knowledge. If a tool returns "no matches found" or "no data available", say so plainly;
do not invent a plausible-sounding number or status.

# Style

Lead with the direct answer (cleared / hit found / no data), then the supporting detail. Keep
it tight — this is a compliance brief, not an essay.
```

- [ ] **Step 5: Write the config overlay**

Create `agents/researcher/config.yaml`:

```yaml
# Overlay merged into the hermes-exercise profile's own config.yaml by run.py.
# Only the keys this project adds — Hermes's own defaults for everything else are untouched.
mcp_servers:
  trade-compliance:
    command: "__PYTHON_EXECUTABLE__"
    args:
      - "-m"
      - "tools.trade_mcp.server"
    env:
      PYTHONPATH: "__REPO_ROOT__"
    enabled: true

platform_toolsets:
  cli:
    - mcp-trade-compliance
```

(The `__PYTHON_EXECUTABLE__`/`__REPO_ROOT__` placeholders are filled in by `run.py` at merge
time with real absolute paths — see Task 4. They're written literally here because this file is
also human-readable documentation of the shape being merged; `run.py` never reads these two
literal strings as anything other than substitution targets.)

- [ ] **Step 6: Create `requirements.txt`**

```
mcp>=1.0
httpx>=0.27
pyyaml>=6.0
pytest>=8.0
```

- [ ] **Step 7: Confirm `.gitignore` covers the venv**

Read the existing `.gitignore`. If `.venv/` and `__pycache__/` are not already present, add
them. (Do not overwrite the file — it already exists with content from the initial scaffold.)

- [ ] **Step 8: Set up the environment and install dependencies**

Run:
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```
Expected: installs cleanly, no errors.

- [ ] **Step 9: Commit**

```bash
git add agents/researcher/SOUL.md agents/researcher/config.yaml requirements.txt .gitignore
git commit -m "add Researcher profile identity + config overlay"
```

---

## Task 2: `screen_party` tool

**Files:**
- Create: `tools/trade_mcp/__init__.py` (empty)
- Create: `tools/trade_mcp/logic.py`
- Create: `tools/trade_mcp/server.py`

**Interfaces:**
- Consumes: nothing from Task 1's code (independent of it).
- Produces: `tools.trade_mcp.logic.fetch_screen_party(name: str) -> dict` — returns
  `{"matched": True, "hits": [{"name": str, "source_list": str, "entity_type": str}]}` or
  `{"matched": False, "hits": [], "message": "no matches found"}` or `{"error": str}`. Task 3
  extends `server.py` with a second tool; Task 4 wires `mcp_servers` in config to invoke this
  server module.

**Verification approach for this task:** this tool talks to a real external API whose exact
response shape we don't control and can't safely guess. A test written against a made-up/mocked
response would only prove the code agrees with our own guess — not that it agrees with reality.
So verification here is a real call against the live API (Step 4), not a written-first fake test.

- [ ] **Step 1: Get a real API key and inspect one real response**

Sign up at developer.trade.gov (free) for a subscription key covering the Consolidated
Screening List API. Then run one manual request to see the real shape:

```bash
curl -s "https://api.trade.gov/consolidated_screening_list/search?name=Rosneft&fuzzy_name=true" \
  -H "subscription-key: YOUR_KEY_HERE" | python3 -m json.tool | head -40
```

Note the real top-level array key and per-result field names — use these exact names in Step 2,
in place of the `results`/`name`/`source`/`type` guesses shown there if the real response
differs.

- [ ] **Step 2: Write the implementation**

Create `tools/trade_mcp/__init__.py` (empty file).

Create `tools/trade_mcp/logic.py`:

```python
"""Pure logic for the trade-compliance MCP tools: HTTP calls + response normalization.

Kept separate from server.py so this is testable without spinning up an MCP server or hitting
the network in tests.
"""
from __future__ import annotations

import os

import httpx

TRADE_GOV_SEARCH_URL = "https://api.trade.gov/consolidated_screening_list/search"


def fetch_screen_party(name: str) -> dict:
    """Screen a name against the US Consolidated Screening List (11 combined restricted-party
    lists). Returns a small, pre-cleaned result — never the raw government payload, and never a
    silent empty result on failure."""
    api_key = os.environ.get("TRADE_GOV_API_KEY", "")
    if not api_key:
        return {"error": "TRADE_GOV_API_KEY is not set"}

    try:
        response = httpx.get(
            TRADE_GOV_SEARCH_URL,
            params={"name": name, "fuzzy_name": "true"},
            headers={"subscription-key": api_key},
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"error": f"screening API error: {exc}"}

    payload = response.json()
    results = payload.get("results", [])   # adjust key name if Step 1 found a different one
    if not results:
        return {"matched": False, "hits": [], "message": "no matches found"}

    hits = [
        {
            "name": r.get("name", ""),
            "source_list": r.get("source", ""),
            "entity_type": r.get("type", ""),
        }
        for r in results
    ]
    return {"matched": True, "hits": hits}
```

- [ ] **Step 3: Wrap it as an MCP tool**

Create `tools/trade_mcp/server.py`:

```python
"""Trade-compliance MCP server — exposes the Researcher's tools over the Model Context Protocol.

Run standalone for manual testing:

    python -m tools.trade_mcp.server

Docstrings below ARE the tool descriptions the model sees — they carry the routing guidance,
not SOUL.md.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.trade_mcp import logic

mcp = FastMCP("trade-compliance")


@mcp.tool()
def screen_party(name: str) -> dict:
    """Check whether a company or individual name appears on a US government restricted-party
    list (OFAC SDN, BIS Entity/Denied Persons, State Dept debarred parties, and others, combined).
    Use this before any trade deal to confirm the counterparty is not sanctioned. Returns
    matched=True with the matching list(s) if found, or matched=False with an explicit
    "no matches found" message — never guess sanctions status without calling this."""
    return logic.fetch_screen_party(name=name)


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 4: Real verification — call the live API directly, bypassing the LLM entirely**

Run:
```bash
. .venv/bin/activate
python3 -c "
from tools.trade_mcp.logic import fetch_screen_party
import json
print(json.dumps(fetch_screen_party('Rosneft'), indent=2))
print(json.dumps(fetch_screen_party('Acme Test Corp Definitely Not Real'), indent=2))
"
```
Expected: first call returns `matched: true` with at least one hit; second call returns the
explicit `"no matches found"` shape. If either result looks wrong, fix `logic.py`'s field
mapping now — this real call is the actual proof the tool works, not a formality.

- [ ] **Step 5: Commit**

```bash
git add tools/trade_mcp/__init__.py tools/trade_mcp/logic.py tools/trade_mcp/server.py
git commit -m "add screen_party sanctions-screening tool"
```

---

## Task 3: `trade_data_lookup` tool

**Files:**
- Create: `tools/trade_mcp/countries.json`
- Modify: `tools/trade_mcp/logic.py` (append `fetch_trade_data`)
- Modify: `tools/trade_mcp/server.py` (append `trade_data_lookup` tool)

**Verification approach:** same reasoning as Task 2 — this talks to a real external API (UN
Comtrade), so the real proof is a live call (Step 4), not a mocked test.

**Interfaces:**
- Consumes: nothing from Task 2's code paths (independent function), but lives in the same
  files.
- Produces: `tools.trade_mcp.logic.fetch_trade_data(reporter_country: str, partner_country: str,
  hs_code: str, year: int) -> dict` — returns `{"value_usd": float, "year": int, "reporter":
  str, "partner": str, "product_hs_code": str}` or `{"error": "no data available for this
  query"}` or `{"error": "unrecognized country: <name>"}`.

- [ ] **Step 1: Write the country lookup table**

Create `tools/trade_mcp/countries.json` — a starter set of real UN M49 numeric codes (this is a
deliberately-scoped starter list, not the full ~200-country UN M49 table; extend it by adding
more `"name": code` entries as needed — the lookup logic itself doesn't change):

```json
{
  "germany": 276,
  "india": 699,
  "united states": 842,
  "usa": 842,
  "china": 156,
  "russia": 643,
  "saudi arabia": 682,
  "brazil": 76,
  "uae": 784,
  "united arab emirates": 784,
  "france": 251,
  "united kingdom": 826,
  "uk": 826,
  "japan": 392,
  "south korea": 410,
  "italy": 380,
  "netherlands": 528,
  "mexico": 484,
  "canada": 124,
  "australia": 36,
  "south africa": 710,
  "nigeria": 566,
  "indonesia": 360,
  "singapore": 702,
  "switzerland": 757,
  "spain": 724,
  "turkey": 792,
  "poland": 616,
  "egypt": 818,
  "pakistan": 586,
  "bangladesh": 50,
  "vietnam": 704,
  "thailand": 764
}
```

(Germany=276 and India=699 were live-verified earlier against the real Comtrade API and
returned real steel-trade data — highest-confidence entries in this table.)

- [ ] **Step 2: Implement it**

Append to `tools/trade_mcp/logic.py`:

```python
import json
from pathlib import Path

COMTRADE_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
_COUNTRIES_PATH = Path(__file__).parent / "countries.json"
_COUNTRY_CODES = json.loads(_COUNTRIES_PATH.read_text())


def _country_code(name: str) -> int | None:
    return _COUNTRY_CODES.get(name.strip().lower())


def fetch_trade_data(reporter_country: str, partner_country: str, hs_code: str, year: int) -> dict:
    """Look up real import/export value between two countries for one HS product chapter and
    year, from UN Comtrade. Returns a single clean total — never the raw ~20-row response with
    its duplicate/estimate-flag noise."""
    reporter_code = _country_code(reporter_country)
    if reporter_code is None:
        return {"error": f"unrecognized country: {reporter_country}"}
    partner_code = _country_code(partner_country)
    if partner_code is None:
        return {"error": f"unrecognized country: {partner_country}"}

    try:
        response = httpx.get(
            COMTRADE_URL,
            params={
                "reporterCode": reporter_code,
                "partnerCode": partner_code,
                "period": year,
                "flowCode": "X",
                "cmdCode": hs_code,
            },
            timeout=15.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {"error": f"trade data API error: {exc}"}

    rows = response.json().get("data", [])
    aggregate_rows = [r for r in rows if r.get("isAggregate") and r.get("primaryValue")]
    if not aggregate_rows:
        return {"error": "no data available for this query"}

    total = max(r["primaryValue"] for r in aggregate_rows)
    return {
        "value_usd": total,
        "year": year,
        "reporter": reporter_country,
        "partner": partner_country,
        "product_hs_code": hs_code,
    }
```

- [ ] **Step 3: Add the second MCP tool**

Append to `tools/trade_mcp/server.py` (before the `if __name__ == "__main__":` line):

```python
@mcp.tool()
def trade_data_lookup(reporter_country: str, partner_country: str, hs_code: str, year: int) -> dict:
    """Look up real total import/export value between two countries for one product category and
    year, from UN Comtrade — country-level aggregate data only, NOT company/shipment-level (use
    screen_party for company questions). hs_code is a 2-digit HS chapter, e.g. 72=iron/steel,
    27=mineral fuels/crude oil, 85=electronics, 84=machinery, 10=cereals, 30=pharma. Recent/
    current years are often not yet published — an explicit "no data available" is expected and
    correct in that case, not an error to work around."""
    return logic.fetch_trade_data(
        reporter_country=reporter_country,
        partner_country=partner_country,
        hs_code=hs_code,
        year=year,
    )
```

- [ ] **Step 4: Real verification — call the live API directly**

Run:
```bash
python3 -c "
from tools.trade_mcp.logic import fetch_trade_data
import json
print(json.dumps(fetch_trade_data('Germany', 'India', '72', 2022), indent=2))
print(json.dumps(fetch_trade_data('Germany', 'India', '72', 2099), indent=2))
"
```
Expected: first call returns a real `value_usd` (this exact query was live-verified during
design); second call (a not-yet-published year) returns the explicit no-data error. This real
call is the actual proof the tool works.

- [ ] **Step 5: Commit**

```bash
git add tools/trade_mcp/countries.json tools/trade_mcp/logic.py tools/trade_mcp/server.py
git commit -m "add trade_data_lookup tool + country code lookup table"
```

---

## Task 4: Wire it into the profile and run end-to-end

**Files:**
- Modify: `run.py` (implement `run_single()` and add a config-merge helper)
- Modify: `.env.example` (add `TRADE_GOV_API_KEY`)
- Test: `tests/test_run_config_merge.py`

**Interfaces:**
- Consumes: `agents/researcher/config.yaml` (Task 1), `agents/researcher/SOUL.md` (Task 1),
  `tools/trade_mcp/server.py` (Tasks 2-3), `config/model.openai.yaml` (pre-existing).
- Produces: `run.py::_deep_merge(base: dict, overlay: dict) -> dict` (pure, unit-tested),
  `run.py::run_single()` (integration — launches the real interactive session).

- [ ] **Step 1: Write the failing test for the merge helper**

Create `tests/test_run_config_merge.py`:

```python
from run import _deep_merge


def test_deep_merge_adds_new_keys():
    base = {"a": 1, "nested": {"x": 1}}
    overlay = {"b": 2, "nested": {"y": 2}}
    result = _deep_merge(base, overlay)
    assert result == {"a": 1, "b": 2, "nested": {"x": 1, "y": 2}}


def test_deep_merge_overlay_wins_on_conflict():
    base = {"model": {"default": "old-model"}}
    overlay = {"model": {"default": "new-model"}}
    result = _deep_merge(base, overlay)
    assert result == {"model": {"default": "new-model"}}


def test_deep_merge_list_values_replaced_not_merged():
    base = {"platform_toolsets": {"cli": ["memory"]}}
    overlay = {"platform_toolsets": {"cli": ["memory", "mcp-trade-compliance"]}}
    result = _deep_merge(base, overlay)
    assert result["platform_toolsets"]["cli"] == ["memory", "mcp-trade-compliance"]
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_run_config_merge.py -v`
Expected: FAIL — `ImportError: cannot import name '_deep_merge' from 'run'`.

- [ ] **Step 3: Implement the merge helper and profile-sync logic in `run.py`**

Modify `run.py` — replace the existing `run_single()` stub and add supporting code. Full
resulting file:

```python
#!/usr/bin/env python3
"""Entry point for the Hermes agent exercise (PST.AG final round).

    python run.py --mode single     # Part 1: single tool-using agent (the Researcher)
    python run.py --mode handoff    # Part 2: Researcher -> Writer handoff + long-term memory

The model PROVIDER is chosen by the MODEL env var (openai | openrouter | ollama), which selects a
config overlay in config/. Part 3 is exactly this: swap MODEL, no code change.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

MODEL = os.environ.get("MODEL", "openai")          # openai | openrouter | ollama
REPO_ROOT = Path(__file__).parent
CONFIG = REPO_ROOT / "config" / f"model.{MODEL}.yaml"
PROFILE_NAME = "hermes-exercise"
PROFILE_HOME = Path.home() / ".hermes" / "profiles" / PROFILE_NAME


def _preflight() -> None:
    if not CONFIG.exists():
        sys.exit(f"Unknown MODEL='{MODEL}'. Expected one of: openai, openrouter, ollama "
                 f"(no overlay at {CONFIG}).")
    if not PROFILE_HOME.exists():
        sys.exit(
            f"Profile '{PROFILE_NAME}' does not exist yet. Create it first:\n"
            f"  hermes profile create {PROFILE_NAME} "
            f'--description "PST.AG exercise: trade compliance Researcher/Writer agents"'
        )
    print(f"[hermes-exercise] mode-select · model={MODEL} · overlay={CONFIG.name} "
          f"· profile={PROFILE_NAME}")


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. Dicts merge key-by-key; any other type
    (including lists) is replaced wholesale by the overlay's value."""
    result = dict(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _sync_profile() -> None:
    """Merge this repo's config overlay + the selected model overlay into the live profile's
    own config.yaml (never overwritten wholesale — Hermes's own defaults for compression,
    memory, delegation, etc. are preserved), and copy SOUL.md in."""
    profile_config_path = PROFILE_HOME / "config.yaml"
    live_config = yaml.safe_load(profile_config_path.read_text()) or {}

    overlay_text = (REPO_ROOT / "agents" / "researcher" / "config.yaml").read_text()
    overlay_text = overlay_text.replace("__PYTHON_EXECUTABLE__", sys.executable)
    overlay_text = overlay_text.replace("__REPO_ROOT__", str(REPO_ROOT))
    project_overlay = yaml.safe_load(overlay_text)

    model_overlay = yaml.safe_load(CONFIG.read_text())

    merged = _deep_merge(live_config, project_overlay)
    merged = _deep_merge(merged, model_overlay)

    profile_config_path.write_text(yaml.safe_dump(merged, sort_keys=False))

    shutil.copyfile(
        REPO_ROOT / "agents" / "researcher" / "SOUL.md",
        PROFILE_HOME / "SOUL.md",
    )


def run_single() -> None:
    """Part 1 — the Researcher, one agent with two real tools, driven interactively."""
    _sync_profile()
    print(f"[hermes-exercise] profile synced — launching hermes -p {PROFILE_NAME}")
    subprocess.run(["hermes", "-p", PROFILE_NAME], check=False)


def run_handoff() -> None:
    """Part 2 — Researcher (orchestrator) delegates to Writer (leaf) via Hermes delegate_task, with
    long-term memory (memory_enabled + user_profile_enabled) so context carries across turns.

    TODO: wire the two agents + the delegation handoff. See HANDOFF.md section 4. Not part of
    this plan (Part 1 only).
    """
    raise NotImplementedError("Part 2 (handoff) not built yet — see HANDOFF.md.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Hermes agent exercise")
    ap.add_argument("--mode", choices=["single", "handoff"], default="single")
    args = ap.parse_args()
    _preflight()
    {"single": run_single, "handoff": run_handoff}[args.mode]()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the merge test to verify it passes**

Run: `pytest tests/test_run_config_merge.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: the 3 merge tests PASS (these are the only automated tests in this plan — the two API
tools were verified by real calls in Tasks 2 and 3, not by pytest).

- [ ] **Step 6: Add the API key slot**

Modify `.env.example` — add one line after the existing `OPENAI_API_KEY=` line:

```
TRADE_GOV_API_KEY=
```

- [ ] **Step 7: Add the real key to your local `.env` and export it for the run**

This is local-only, never committed (`.env` is already gitignored per the existing
`.gitignore`). Add your real trade.gov key to `.env`, then before running:

```bash
export $(grep -v '^#' .env | xargs)
```

(Or use a `.env`-loading approach if one gets added later — not required for this plan; manual
export is sufficient for Part 1's terminal-only scope.)

- [ ] **Step 8: End-to-end manual verification**

Run: `python run.py --mode single`

In the interactive session, ask:
1. *"Is Rosneft on any US restricted-party list?"* — expect a real `screen_party` tool call
   (visible in Hermes's tool-call trace) and an answer grounded in its result.
2. *"How much steel did Germany export to India in 2022?"* — expect a real `trade_data_lookup`
   tool call and a real dollar figure in the answer.
3. *"How much steel did Germany export to India in 2099?"* — expect the agent to report no data
   is available, not a fabricated figure.

Expected: all three behave as described. This is the spec's definition-of-done.

- [ ] **Step 9: Commit**

```bash
git add run.py .env.example
git commit -m "wire MCP server into Researcher config, verify single-mode run"
```

- [ ] **Step 10: Tag `v1-single`**

Only after Step 8's verification genuinely passed:

```bash
git tag -a v1-single -m "Part 1 complete: single tool-using Researcher agent"
```

Do not push to GitHub yet — that happens with explicit confirmation, not automatically as part
of this plan.
