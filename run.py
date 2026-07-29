#!/usr/bin/env python3
"""Entry point for the trade-compliance Researcher.

    python run.py

Merges this repo's config and identity into a Hermes profile, then launches Hermes.
The model provider is chosen by the MODEL env var, which selects an overlay in config/.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

MODEL = os.environ.get("MODEL", "openai")          # openai | openrouter | fast
REPO_ROOT = Path(__file__).parent
CONFIG = REPO_ROOT / "config" / f"model.{MODEL}.yaml"
PROFILE_NAME = "hermes-exercise"
# In a container there are no other profiles to coexist with, so Hermes's own
# HERMES_HOME is the profile directory and there is nothing to create or name.
# Locally we keep a named profile so this exercise stays isolated from the other
# Hermes profiles on the machine.
PROFILE_HOME = Path(
    os.environ.get("HERMES_HOME") or Path.home() / ".hermes" / "profiles" / PROFILE_NAME
)


def _preflight() -> None:
    if not CONFIG.exists():
        overlays = sorted(p.stem.replace("model.", "") for p in (REPO_ROOT / "config").glob("model.*.yaml"))
        sys.exit(f"Unknown MODEL='{MODEL}'. Available: {', '.join(overlays)} (no overlay at {CONFIG}).")
    if os.environ.get("HERMES_HOME"):
        PROFILE_HOME.mkdir(parents=True, exist_ok=True)   # container: we own this dir
    if not PROFILE_HOME.exists():
        sys.exit(
            f"Profile '{PROFILE_NAME}' does not exist yet. Create it first:\n"
            f"  hermes profile create {PROFILE_NAME} "
            f'--description "Trade compliance Researcher"'
        )
    print(f"[researcher] model={MODEL} · overlay={CONFIG.name} · profile={PROFILE_NAME}")


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


def _researcher_soul() -> str:
    """The Researcher's identity.

    Hermes reads exactly one file — $HERMES_HOME/SOUL.md. Keeping ours under agents/
    means the identity is version-controlled next to the config it belongs with, rather
    than edited in place inside the profile directory.
    """
    return (REPO_ROOT / "agents" / "researcher" / "SOUL.md").read_text()


def _sync_profile() -> None:
    """Merge this repo's config overlay + the selected model overlay into the live profile's
    own config.yaml (never overwritten wholesale — Hermes's own defaults for compression,
    memory, delegation, etc. are preserved), and write the Researcher's SOUL.md in."""
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
    # A provider config is atomic — merging it key-by-key leaves stale settings from the
    # previous provider behind. Switching OpenAI -> OpenRouter kept OpenAI's base_url,
    # which silently points an open-weight model at the wrong endpoint. Replace outright.
    if "model" in model_overlay:
        merged["model"] = model_overlay["model"]

    profile_config_path.write_text(yaml.safe_dump(merged, sort_keys=False))
    (PROFILE_HOME / "SOUL.md").write_text(_researcher_soul())


def main() -> None:
    argparse.ArgumentParser(description="Trade-compliance Researcher (Hermes)").parse_args()
    _preflight()
    _sync_profile()
    print(f"[researcher] profile synced — launching hermes -p {PROFILE_NAME}")
    subprocess.run(["hermes", "-p", PROFILE_NAME], check=False)


if __name__ == "__main__":
    main()
