"""Trade-compliance MCP server — exposes the Researcher's tools over the Model Context Protocol.

Run standalone for manual testing:

    python -m tools.trade_mcp.server

Docstrings below ARE the tool descriptions the model sees — they carry the routing guidance,
not SOUL.md.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from tools.trade_mcp import logic

mcp = FastMCP("trade-compliance")


@mcp.tool()
def screen_party(name: str) -> dict:
    """Check whether a company or individual name appears on a US government restricted-party
    list (OFAC SDN, BIS Entity/Denied Persons, State Dept debarred parties, and others, combined).
    Use this before any trade deal to confirm the counterparty is not sanctioned. Returns
    matched=True with the matching list(s) if found, or matched=False with an explicit
    "no matches found" message — never guess sanctions status without calling this."""
    return logic.fetch_screen_party(name=name)


@mcp.tool()
def trade_data_lookup(
    reporter_country: str, partner_country: str, hs_code: str | int, year: int
) -> dict:
    """Look up real total import/export value between two countries for one product category and
    year, from UN Comtrade — country-level aggregate data only, NOT company/shipment-level (use
    screen_party for company questions). hs_code is a 2-digit HS chapter, e.g. 72=iron/steel,
    27=mineral fuels/crude oil, 85=electronics, 84=machinery, 10=cereals, 30=pharma. Recent/
    current years are often not yet published — an explicit "no data available" is expected and
    correct in that case, not an error to work around."""
    return logic.fetch_trade_data(
        reporter_country=reporter_country,
        partner_country=partner_country,
        hs_code=hs_code,
        year=year,
    )


if __name__ == "__main__":
    mcp.run()
