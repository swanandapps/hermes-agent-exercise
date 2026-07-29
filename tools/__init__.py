"""This project's tool implementations.

The __init__.py is load-bearing, not decoration. Hermes ships its own package called
`tools`, and once Hermes is pip-installed (as it is in the container) that package sits
in site-packages. A directory without __init__.py is only a *namespace* package, and
regular packages take precedence over namespace packages no matter what PYTHONPATH says —
so `import tools` resolved to Hermes's copy and our MCP server vanished with
"No module named 'tools.trade_mcp'". Declaring ours a regular package restores normal
path-order resolution.
"""
