"""Pure logic for the trade-compliance MCP tools: HTTP calls + response normalization.

Kept separate from server.py so this is testable without spinning up an MCP server or hitting
the network in tests.
"""
from __future__ import annotations

import json
import os

import httpx

TRADE_GOV_SEARCH_URL = "https://data.trade.gov/consolidated_screening_list/v1/search"


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
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"error": f"screening API error: {exc}"}
    results = payload.get("results", [])   # adjust key name if Step 1 found a different one
    if not results:
        return {"matched": False, "hits": [], "message": "no matches found"}

    hits = [
        {
            "name": r.get("name") or "",
            "source_list": r.get("source") or "",
            "entity_type": r.get("type") or "",
        }
        for r in results
    ]
    return {"matched": True, "hits": hits}


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
