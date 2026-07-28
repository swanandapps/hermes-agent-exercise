# agents/

Hermes agent definitions for this exercise. Build FRESH here (do not copy another project).

- **researcher** — Part 1's single tool-using agent; becomes the orchestrator in Part 2.
- **writer** — Part 2's second agent; the Researcher hands off to it (Hermes `delegate_task`, leaf).

Each agent = a Hermes profile/config (SOUL.md identity + config.yaml). The `model:` block comes from
the overlay chosen by `MODEL` (see `../config/`), so agents never hardcode a provider.

TODO: create the profiles and identities. See `../HANDOFF.md` §4–§5 for the Hermes specifics.
