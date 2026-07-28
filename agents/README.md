# agents/

The two agents in this exercise. Both are built fresh here — nothing copied from another project.

| | Role | Lives in |
|---|---|---|
| **researcher** | Gathers facts with the two MCP tools. Part 1's single agent; Part 2's orchestrator. | `researcher/SOUL.md`, `researcher/config.yaml` (+ `.handoff` variants) |
| **writer** | Turns the Researcher's raw findings into a compliance memo. Part 2 only. | `writer/PERSONA.md` |

## Why only one of them is a Hermes profile

Hermes reads exactly one identity file per profile: `$HERMES_HOME/SOUL.md`
(`agent/prompt_builder.py:1841`). Subagents spawned with `delegate_task` don't get one — they
start from a completely fresh conversation, and their entire identity arrives in the `goal` and
`context` strings the parent passes. There is no parameter for pointing a child at a different
profile or `SOUL.md`.

So the Writer isn't a profile; it's a persona injected at delegation time. See
[`writer/README.md`](writer/README.md) for how `PERSONA.md` gets there.

## What's Hermes and what's ours

Hermes only ever reads `SOUL.md` and `config.yaml` from the profile directory. Everything else
here is this repo's own layout, resolved by `run.py` before it writes those two files:

- `SOUL.md` / `config.yaml` — Part 1 (`--mode single`)
- `SOUL.handoff.md` / `config.handoff.yaml` — Part 2 (`--mode handoff`), merged **on top of**
  Part 1's rather than replacing it, so Part 1 keeps working untouched
- `writer/PERSONA.md` — substituted into `SOUL.handoff.md` at the `__WRITER_PERSONA__` placeholder

The `model:` block comes from the overlay chosen by `MODEL` (see [`../config/`](../config/)), so
the agents never hardcode a provider — that's what makes Part 3 a config change rather than a
rewrite.
