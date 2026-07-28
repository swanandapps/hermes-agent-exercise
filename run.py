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


def _researcher_soul(mode: str) -> str:
    """The Researcher's identity for this mode, with the Writer's persona substituted in.

    Hermes reads exactly one file — $HERMES_HOME/SOUL.md. The `.handoff` variant and
    the Writer's PERSONA.md are this repo's own layout: kept separate so the Writer can
    be tuned without touching the Researcher, then merged here into the single file
    Hermes actually loads.
    """
    agents = REPO_ROOT / "agents"
    soul = (agents / "researcher" / ("SOUL.handoff.md" if mode == "handoff" else "SOUL.md")).read_text()
    if mode == "handoff":
        persona = (agents / "writer" / "PERSONA.md").read_text().strip()
        soul = soul.replace("__WRITER_PERSONA__", persona)
    return soul


def _sync_profile(mode: str = "single") -> None:
    """Merge this repo's config overlay + the selected model overlay into the live profile's
    own config.yaml (never overwritten wholesale — Hermes's own defaults for compression,
    memory, delegation, etc. are preserved), and write the mode's SOUL.md in."""
    profile_config_path = PROFILE_HOME / "config.yaml"
    live_config = yaml.safe_load(profile_config_path.read_text()) if profile_config_path.exists() else {}
    live_config = live_config or {}

    overlay_text = (REPO_ROOT / "agents" / "researcher" / "config.yaml").read_text()
    overlay_text = overlay_text.replace("__PYTHON_EXECUTABLE__", sys.executable)
    overlay_text = overlay_text.replace("__REPO_ROOT__", str(REPO_ROOT))
    project_overlay = yaml.safe_load(overlay_text)

    model_overlay = yaml.safe_load(CONFIG.read_text())

    merged = _deep_merge(live_config, project_overlay)
    if mode == "handoff":
        handoff_overlay = yaml.safe_load(
            (REPO_ROOT / "agents" / "researcher" / "config.handoff.yaml").read_text()
        )
        merged = _deep_merge(merged, handoff_overlay)
    merged = _deep_merge(merged, model_overlay)

    profile_config_path.write_text(yaml.safe_dump(merged, sort_keys=False))
    (PROFILE_HOME / "SOUL.md").write_text(_researcher_soul(mode))


def run_single() -> None:
    """Part 1 — the Researcher, one agent with two real tools, driven interactively."""
    _sync_profile("single")
    print(f"[hermes-exercise] profile synced — launching hermes -p {PROFILE_NAME}")
    subprocess.run(["hermes", "-p", PROFILE_NAME], check=False)


def run_handoff() -> None:
    """Part 2 — the Researcher gathers facts, then delegates the memo to a Writer subagent
    via Hermes's native delegate_task, with memory and session_search enabled so findings
    carry across sessions."""
    _sync_profile("handoff")
    print(f"[hermes-exercise] profile synced (handoff: delegation + memory) — "
          f"launching hermes -p {PROFILE_NAME}")
    subprocess.run(["hermes", "-p", PROFILE_NAME], check=False)


def main() -> None:
    ap = argparse.ArgumentParser(description="Hermes agent exercise")
    ap.add_argument("--mode", choices=["single", "handoff"], default="single")
    args = ap.parse_args()
    _preflight()
    {"single": run_single, "handoff": run_handoff}[args.mode]()


if __name__ == "__main__":
    main()
