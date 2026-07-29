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
            "score": r.get("score"),
        }
        for r in results
    ]

    # Screening runs with fuzzy_name=true, so a result set is not the same thing as a match:
    # "Google" comes back with GORGE LIMITED and BESTOP GLOBLE MFG LIMITED at score 80, while
    # "Rosneft Trading S.A." comes back at 100 with the name matching outright.
    #
    # The government computes that distinction and we used to discard it, leaving the agent to
    # judge by eye whether GORGE LIMITED "looks like" Google. It reasoned it out correctly and
    # still labelled the answer a HIT — a false positive dressed as a stop signal. Two of those
    # in production and people stop believing the red ones.
    #
    # So the difference is reported, not inferred. An alias match still counts as exact: a party
    # re-registering under an alt_name is precisely what these lists exist to catch.
    query = name.strip().casefold()
    exact_name_match = any(
        (r.get("name") or "").strip().casefold() == query
        or any((alt or "").strip().casefold() == query for alt in (r.get("alt_names") or []))
        for r in results
    )
    scores = [r.get("score") for r in results if isinstance(r.get("score"), (int, float))]
    top_score = max(scores) if scores else None
    exact = exact_name_match or (top_score is not None and top_score >= 100)

    result = {
        "matched": True,
        "match_quality": "exact" if exact else "partial",
        "exact_name_match": exact_name_match,
        "top_score": top_score,
        "hits": hits,
    }
    if not exact:
        result["note"] = (
            f"No entry matches '{name}' outright — these are partial or phonetic similarities "
            f"(best score {top_score}). Treat as REVIEW, not a confirmed hit, and re-screen with "
            f"the exact legal entity name from the contract."
        )
    return result


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
    # Models reasonably pass HS chapters as numbers (72) as often as strings ("72"),
    # and a chapter is two digits — "8" means chapter 08.
    hs_code = str(hs_code).strip().zfill(2)
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
    # flowCode "X" above means exports, but nothing in a bare {reporter, partner, value}
    # says so, and a model asked for "Germany's exports to Russia" has been observed
    # reporting it back as "Germany imported from Russia". Direction is not a detail in a
    # compliance memo, so it is stated in the payload rather than left to be inferred.
    return {
        "value_usd": total,
        "flow": "exports",
        "direction": f"exports from {reporter_country} to {partner_country}",
        "year": year,
        "reporter": reporter_country,
        "partner": partner_country,
        "product_hs_code": hs_code,
    }


# ── company background ───────────────────────────────────────────────────────────────────────
#
# Answers "who is this counterparty" — sector, what they make, where they are based. It exists
# because screening a name you cannot place is guesswork: an analyst handed "Acme Trading S.A."
# needs to know it is a Rotterdam chemicals broker before deciding whether the deal even makes
# sense.
#
# It is deliberately NOT a news or sanctions tool. The query is shaped toward profile pages, and
# every result is returned tagged as unverified web text, because the difference between this and
# screen_party is the difference between hearsay and the register itself. A page cannot put a
# party on a list and cannot take one off. Blurring the two fails in both directions: an old
# "faces sanctions probe" headline kills a legal deal, and a glowing corporate profile talks
# someone past a real SDN listing.
_DDGS_MAX_RESULTS = 4
_DDGS_SNIPPET_CHARS = 400

_BACKGROUND_DISCLAIMER = (
    "Unverified web text, for context only. This is NOT a compliance finding and says nothing "
    "about sanctions status — only screen_party does. Never let it change a screening verdict. "
    "A search engine always returns its closest guess, so these results may describe a "
    "different, similarly-named company: check each title and URL actually refers to the party "
    "asked about, and say the background could not be confirmed if they do not."
)


def fetch_company_background(name: str) -> dict:
    """Look up what a company is and does, from public web sources. Background, never a finding."""
    try:
        from ddgs import DDGS
    except ImportError:
        return {"error": "web search unavailable: the 'ddgs' package is not installed"}

    # Steered toward "who are they" pages rather than headlines. Search engines happily return
    # news for a bare company name, and news is the one thing this tool must not smuggle into a
    # compliance conversation.
    query = f'"{name}" company profile industry headquarters what the company does'

    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            raw = list(DDGS().text(query, max_results=_DDGS_MAX_RESULTS))
            break
        except Exception as exc:                      # ddgs raises its own rate-limit types
            last_exc = exc
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_BACKOFF_SECONDS[attempt - 1])
    else:
        return {"error": f"web search error: {last_exc}"}

    if not raw:
        return {
            "found": False,
            "message": f"no public background found for '{name}'",
            "evidence_type": "unverified_web",
            "disclaimer": _BACKGROUND_DISCLAIMER,
        }

    return {
        "found": True,
        "evidence_type": "unverified_web",
        "sources": [
            {
                "title": (r.get("title") or "").strip(),
                "url": (r.get("href") or "").strip(),
                "summary": (r.get("body") or "").strip()[:_DDGS_SNIPPET_CHARS],
            }
            for r in raw
        ],
        "disclaimer": _BACKGROUND_DISCLAIMER,
    }
