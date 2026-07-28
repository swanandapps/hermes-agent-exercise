# Hermes Agent Exercise

> **PST.AG — Senior AI Engineer (Hermes Agent) — final-round exercise.**
> One project, built in layers, demonstrating all three required capabilities on the real
> **Nous Research Hermes** runtime. See [`HANDOFF.md`](./HANDOFF.md) for the full brief.

A **single tool-using agent** that scales into a **2-agent collaborative workflow**, and runs on
**hosted or open-weight models** with a one-line config change — *not* a rewrite. That last point is
the core Hermes strength (and the sharpest contrast with LangChain).

> ⚠️ **Status: WIP scaffold.** The structure, run seam, and model overlays are in place; the agents,
> tools, and delegation are still to be built (grep `TODO`). This README is the map.

---

## What it does (maps 1:1 to the exercise)

| Part | Requirement | How to run / demo |
|------|-------------|-------------------|
| **1 — Fundamentals** | Single tool-using agent | `python run.py --mode single` |
| **2 — Multi-agent** | Researcher → Writer handoff + long-term memory | `python run.py --mode handoff` |
| **3 — Open-weight** | Same agents, no Anthropic, via Ollama + a cloud endpoint | `MODEL=ollama docker compose up` (or `MODEL=openrouter`) |
| — | Hermes vs LangChain comparison (presented live) | [`docs/hermes-vs-langchain.md`](./docs/hermes-vs-langchain.md) |

The Part-1 agent (the **Researcher**) becomes one half of Part 2; Part 3 changes only the model
config. Each part stays independently runnable so every requirement is demoable on its own.

## The model swap = Part 3 in one line

Provider is chosen by the `MODEL` env var, which selects an overlay in [`config/`](./config):

```bash
MODEL=openai     python run.py --mode handoff   # hosted (dev)
MODEL=openrouter python run.py --mode handoff   # open-weight via cloud endpoint
MODEL=ollama     python run.py --mode handoff   # open-weight, self-hosted (local)
```

No agent/tool code changes between them — that's the point.

## Setup

```bash
cp .env.example .env          # add your keys; pick MODEL
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt   # TODO: pin deps
```

For local open-weight (Part 3): `ollama pull qwen2.5:3b` (small model — see the 8 GB-laptop note in HANDOFF §2).

## Layout

```
run.py                     # entrypoint: --mode single | handoff ; reads MODEL env
config/
  model.openai.yaml        # hosted overlay   (provider: custom — NOT "openai")
  model.openrouter.yaml    # open-weight, cloud endpoint
  model.ollama.yaml        # open-weight, local (small model)
agents/                    # Hermes agent definitions (Researcher, Writer) — TODO
tools/                     # tool definitions (MCP server) — TODO
docs/hermes-vs-langchain.md# the 1-page comparison (live-presented)
docker-compose.yml         # Part 3: app + Ollama, no Anthropic
HANDOFF.md                 # full brief / cold-start context
```

## Progression (for the live walk-through)

Git tags tell the story: `v1-single` → `v2-handoff` → `v3-open-weight`. The final repo runs all modes.
