"""This project's MCP tool server.

Deliberately NOT named `tools`: Hermes ships its own top-level package by that name, and
once Hermes is pip-installed (as in the container) it sits in site-packages where it
shadows a local `tools/`. That collision is silent — the gateway starts fine and simply
reports "Tool 'screen_party' does not exist" — so the name is chosen to avoid it rather
than to win a path-precedence fight against it.
"""
