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


if __name__ == "__main__":
    mcp.run()
