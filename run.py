#!/usr/bin/env python3
"""Entry point for the Hermes agent exercise (PST.AG final round).

    python run.py --mode single     # Part 1: single tool-using agent (the Researcher)
    python run.py --mode handoff    # Part 2: Researcher -> Writer handoff + long-term memory

The model PROVIDER is chosen by the MODEL env var (openai | openrouter | ollama), which selects a
config overlay in config/. Part 3 is exactly this: swap MODEL, no code change.

This is a WIP scaffold — the two run_* functions are stubs. See HANDOFF.md sections 3-5 for the plan
(Hermes profile + tools via MCP, handoff via native delegation, model overlays already provided).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

MODEL = os.environ.get("MODEL", "openai")          # openai | openrouter | ollama
CONFIG = Path(__file__).parent / "config" / f"model.{MODEL}.yaml"


def _preflight() -> None:
    if not CONFIG.exists():
        sys.exit(f"Unknown MODEL='{MODEL}'. Expected one of: openai, openrouter, ollama "
                 f"(no overlay at {CONFIG}).")
    print(f"[hermes-exercise] mode-select · model={MODEL} · overlay={CONFIG.name}")


def run_single() -> None:
    """Part 1 — one Hermes agent with 2-3 real tools, driven on a single task.

    TODO: start the Hermes agent for this exercise's profile with the model overlay above, give it its
    tools (MCP), and run one tool-using task end-to-end. See HANDOFF.md sections 4-5 for the Hermes
    invocation + the known-good config.
    """
    raise NotImplementedError("Part 1 (single agent) not built yet — see HANDOFF.md.")


def run_handoff() -> None:
    """Part 2 — Researcher (orchestrator) delegates to Writer (leaf) via Hermes delegate_task, with
    long-term memory (memory_enabled + user_profile_enabled) so context carries across turns.

    TODO: wire the two agents + the delegation handoff. See HANDOFF.md section 4.
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
