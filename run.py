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
    live_config = yaml.safe_load(profile_config_path.read_text()) if profile_config_path.exists() else {}
    live_config = live_config or {}

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
