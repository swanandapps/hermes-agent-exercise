"""Pure logic for the trade-compliance MCP tools: HTTP calls + response normalization.

Kept separate from server.py so this is testable without spinning up an MCP server or hitting
the network in tests.
"""
from __future__ import annotations

import json
import os
import time

import httpx

TRADE_GOV_SEARCH_URL = "https://data.trade.gov/consolidated_screening_list/v1/search"

# Both external APIs are hit exactly once per tool call, over the open internet, from a
# long-lived stdio subprocess — a one-off DNS/connection blip shouldn't turn into a fabricated
# "no data" or an unhelpful error the model then has to explain to the user. Retry ONLY on
# transport-level failures (httpx.HTTPError: timeouts, DNS resolution, connection resets, bad
# status codes) — never on a successful, parsed response, even an empty one. An empty result is
# a real answer ("no matches found" / "no data available"), not a failure to retry.
#
# 3 attempts with modestly increasing backoff (1s, then 2s between attempts) rather than 2
# attempts with a single fixed pause: observed live flakiness (data.trade.gov intermittently
# failing DNS resolution, confirmed as real dual-stack DNS flapping — not a code or environment
# bug) has also been observed to clear again moments later, so a bit more spacing and one more
# shot meaningfully raises the odds of landing on a working moment. Deliberately NOT doing
# anything fancier (manual IPv4 forcing, custom resolution, IP pinning) — this is an ordinary
# transient-network problem, not one that needs bespoke networking code.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1.0, 2.0)  # wait before attempt 2, then before attempt 3


def _get_with_retry(url: str, *, params: dict, headers: dict, timeout: float) -> httpx.Response:
    """GET with up to 2 retries (3 attempts total) and modestly increasing backoff between them.

    Raises the last httpx.HTTPError if every attempt fails — callers catch that the same way
    they'd catch a single failed request, so the external {"error": ...} contract is unchanged.
    """
    last_exc: httpx.HTTPError | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = httpx.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS[attempt - 1])
    raise last_exc


def fetch_screen_party(name: str) -> dict:
    """Screen a name against the US Consolidated Screening List (11 combined restricted-party
    lists). Returns a small, pre-cleaned result — never the raw government payload, and never a
    silent empty result on failure."""
    api_key = os.environ.get("TRADE_GOV_API_KEY", "")
    if not api_key:
        return {"error": "TRADE_GOV_API_KEY is not set"}

    try:
        response = _get_with_retry(
            TRADE_GOV_SEARCH_URL,
            params={"name": name, "fuzzy_name": "true"},
            headers={"subscription-key": api_key},
            timeout=15.0,
        )
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
        response = _get_with_retry(
            COMTRADE_URL,
            params={
                "reporterCode": reporter_code,
                "partnerCode": partner_code,
                "period": year,
                "flowCode": "X",
                "cmdCode": hs_code,
            },
            headers={},
            timeout=15.0,
        )
        rows = response.json().get("data", [])
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"error": f"trade data API error: {exc}"}

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
