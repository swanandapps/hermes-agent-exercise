# trade_tools/

The Researcher's two tools, exposed to Hermes as a stdio **MCP server**.

| File | What it is |
|---|---|
| `trade_mcp/server.py` | The MCP server. One `@mcp.tool()` wrapper per tool — nothing else. |
| `trade_mcp/logic.py` | The actual work: HTTP calls, retries, response normalisation. |
| `trade_mcp/countries.json` | Country name → UN M49 code, with ~45 aliases. |

Run it standalone to see what the model is offered:

```bash
python -m trade_tools.trade_mcp.server
```

## The docstring is the interface

`@mcp.tool()` reads each function's name, type hints and docstring and generates the JSON schema
Hermes sends to the model. The docstring becomes the tool's `description` — **the only text the
model has** when deciding whether this tool answers the question.

So the docstrings carry routing guidance, not implementation notes. `trade_data_lookup` says
"country-level aggregate data only, NOT company/shipment-level (use `screen_party` for company
questions)" because that sentence is what stops the model reaching for the wrong tool. `SOUL.md`
deliberately does not restate any of it — the schema is generated from the function, so it cannot
drift from it, and a paraphrase elsewhere could.

## Why the logic is a separate module

`server.py` is the adapter; `logic.py` is the work. Keeping them apart means the HTTP behaviour —
retries, timeouts, country resolution, error shapes — can be tested and read without an MCP
client, and would survive being exposed some other way.

## Failing explicitly

Every path returns a result the agent can state plainly: a match with its lists, an explicit "no
matches found", an explicit "no data available", or a named error. Nothing returns an empty
structure that a model could smooth over into a confident answer — in compliance, a fabricated
clean screening is the worst possible output.

## Why it is not `tools/`

Hermes ships its own top-level `tools` package. A local directory of that name shadows it once
Hermes is pip-installed, with confusing failures. Hence `trade_tools/`.
