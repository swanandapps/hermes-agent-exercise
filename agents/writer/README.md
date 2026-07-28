# writer/

Part 2's second agent. It has no `config.yaml` and no Hermes profile — deliberately.

Hermes spawns subagents with `delegate_task`, and a subagent starts with a **completely fresh
conversation**. Its entire identity and context come from the `goal` and `context` strings the
parent passes; there is no parameter for pointing a child at a different `SOUL.md` or profile.
(See Hermes's own docs: `user-guide/features/delegation.md` — "Critical: Subagents Know Nothing".)

So the Writer's identity lives in [`PERSONA.md`](PERSONA.md), and `run.py` substitutes it into
`agents/researcher/SOUL.handoff.md` at the `__WRITER_PERSONA__` placeholder when syncing the
profile — the same mechanism that fills in `__REPO_ROOT__` in the config overlay. The Researcher
then passes that text through when it delegates.

Keeping it in its own file means the Writer's memo format can be tuned without touching the
Researcher's identity, and the two agents are visible in the repo rather than inferred from prose.

**The Researcher composes the delegation call at run time**, so it can paraphrase the persona
rather than copy it verbatim. The persona is written to be short and instruction-dense so that
paraphrasing costs little. Hermes offers no way to set a subagent's system prompt directly.
