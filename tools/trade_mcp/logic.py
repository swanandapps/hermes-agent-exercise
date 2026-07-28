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
