# agents/

The Researcher's identity and configuration, kept in the repo rather than edited in place inside
the Hermes profile directory.

| File | What it is |
|---|---|
| `researcher/SOUL.md` | Who the agent is, and the rules that hold whatever tools it has |
| `researcher/config.yaml` | Which MCP server to launch, and which toolsets are exposed |

## How these reach Hermes

Hermes reads exactly one identity file per profile — `$HERMES_HOME/SOUL.md`
(`agent/prompt_builder.py:1841`) — plus that profile's `config.yaml`. Neither is read from this
repo at runtime; `run.py` writes both into the active profile on every launch.

That indirection buys two things. The identity is version-controlled next to the config it belongs
with, and the config is **merged** rather than overwritten — Hermes's own defaults for
compression, sessions and everything else survive untouched, so upgrading Hermes inherits its new
defaults for free.

## What belongs where

`SOUL.md` holds the standing rules: never answer from training knowledge, state failures
explicitly, lead with the verdict word. Those hold true of any tool the agent is ever given.

What an individual tool *does* is deliberately not here — it lives in that tool's docstring, which
Hermes sends to the model as the tool description. Restating it in `SOUL.md` would mean two copies
of one fact, and only one of them travels with the function it describes.

`config.yaml` never names a provider. The model comes from `config/model.*.yaml`, merged on top at
launch, which is what makes swapping models a config change rather than a code change.
