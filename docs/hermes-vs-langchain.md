# Hermes Agents vs LangChain Agents

> Written against what this repo actually builds — a trade-compliance Researcher agent with two
> real tools — plus the same system as it would look in LangChain. Focus: **architecture ·
> tool definition · state management.**
>
> Hermes claims are cited to the installed runtime (v0.18.2, `~/.hermes/hermes-agent/`).
> LangChain claims verified against current docs, mid-2026.

## TL;DR

**Hermes is a runtime you configure. LangChain is a library you assemble.** Both get you a
tool-using agent quickly. The divergence shows up in everything *around* the agent: memory,
delegation, deployment surface, and provider swapping — batteries-included in Hermes, explicit
and composable (and your responsibility) in LangChain.

---

## What we actually built (this repo)

| File | Lines | What it is |
|---|---|---|
| `agents/researcher/SOUL.md` | 18 | Agent identity/behaviour — plain Markdown |
| `agents/researcher/config.yaml` | 16 | MCP server registration + toolset exposure |
| `config/model.openai.yaml` | 9 | Provider/model block |
| `trade_tools/trade_mcp/logic.py` | 136 | Our two tools' actual work (HTTP + normalisation) |
| `trade_tools/trade_mcp/server.py` | 46 | MCP server — one `@mcp.tool()` wrapper each |
| `run.py` | 106 | Config merge + launch. **Not agent logic.** |

**Lines of agent-loop code written: zero.** No ReAct loop, no tool dispatch, no message history
management, no retry/iteration control. Hermes's `AIAgent.run_conversation()` supplies all of it;
we supplied identity, tools, and config.

## The same system in LangChain

Genuinely concise today — `create_agent` (current API, replacing `AgentExecutor`) would be roughly:

```python
from langchain.agents import create_agent
from langchain.tools import tool

@tool
def screen_party(name: str) -> dict:
    """Check a name against US restricted-party lists..."""   # same docstring-as-routing idea
    return fetch_screen_party(name)

agent = create_agent(model="openai:gpt-5-mini", tools=[screen_party, trade_data_lookup],
                     system_prompt=SOUL_TEXT)
```

Our `logic.py` (the actual API work) would be **unchanged** — that's domain code, not framework
code. So for Part 1 alone, the two are close to a wash. The gap opens at Parts 2 and 3:

| This exercise's requirement | Hermes | LangChain |
|---|---|---|
| **Part 1** — single tool-using agent | config + tools | `create_agent(...)`, ~10 lines |
| **Part 2** — Researcher→Writer handoff | `delegate_task` tool already exists; add `delegation` toolset to config | `langgraph-supervisor`, or hand-rolled `StateGraph` + `Command` handoff (~15–40 lines you own) |
| **Part 2** — long-term memory across turns | `memory_enabled: true` — two config flags | checkpointer (short-term) **+** `langgraph.store` (long-term) — two separate systems, plus a store backend, plus a tool to write to it |
| **Part 3** — swap to open-weight models | change the `model:` block | `init_chat_model("ollama:...")` — ~1 line, **but** a separate pip install per provider, and tool-calling fidelity varies by model |

---

## 1. Architecture

**Hermes** — a fixed, synchronous ReAct loop baked into a runtime process (`run_agent.py` →
`AIAgent.run_conversation()`). One core serves CLI, gateway (Telegram/Slack/HTTP), cron, and
batch. You don't compose the loop; you configure what it has access to. Design rule from the
project's own `AGENTS.md`: new capability belongs at the edges (skill → MCP server → plugin),
not as new core code.

**LangChain** — a library. `create_agent` is a prebuilt convenience over LangGraph; underneath,
you can drop to `StateGraph` and define arbitrary node/edge topologies, cycles, interrupts, and
human-in-the-loop gates. You own the graph.

*Consequence:* Hermes gives you less to build and less to get wrong, at the cost of not being
able to express a control flow its loop doesn't support. LangChain expresses anything, and you
maintain it.

## 2. Tool definition

**Hermes** — a self-registering central registry (`tools/registry.py`), plus external tools over
**MCP**. Ours are a stdio MCP server registered in `config.yaml`; Hermes namespaces them
`mcp__trade-compliance__screen_party`. The tool's **docstring is the routing signal** — what
teaches the model when to call it. Tools are reusable across agents without rebinding.

Hermes wraps MCP servers in security machinery that isn't in its public docs (`tools/mcp_tool.py`):
prompt-injection scanning of tool descriptions, an OSV.dev malware preflight before spawning stdio
servers, approval gating, and a filtered subprocess environment.

> **A real gotcha we hit:** that env filtering (`_build_safe_env()`) means an MCP subprocess does
> *not* inherit your shell — our `TRADE_GOV_API_KEY` silently arrived empty and the agent
> hallucinated instead of calling the tool. Fix was explicit `${VAR}` passthrough in the server's
> `env:` block. Good security default, sharp edge.

**LangChain** — `@tool` decorator (or `StructuredTool`), bound per-agent via `.bind_tools()`.
Same docstring-as-description principle. Native MCP support exists via `langchain-mcp-adapters`
(`MultiServerMCPClient`), actively maintained — so MCP is *not* a Hermes-only advantage, though in
LangChain it's an add-on package rather than a first-class config key.

## 3. State management

**Hermes** — four mechanisms, all built in, no external service:
1. `MEMORY.md` / `USER.md` — curated facts, injected into the system prompt at session start
2. SQLite + FTS5 over the full transcript (`state.db`), searchable via `session_search` — **no LLM
   calls in the search path**
3. Skills — procedural `SKILL.md` playbooks
4. Optionally *one* external provider (8 ship: Hindsight, Mem0, Honcho, holographic, …) — enabled
   by a single `memory.provider` key, **zero application code**

**LangChain** — deliberately separated concerns, and you wire them:
- Short-term: a LangGraph **checkpointer** (`InMemorySaver` → `SqliteSaver`/`PostgresSaver`)
- Long-term: **`langgraph.store`** (`InMemoryStore` → `PostgresStore`), typically surfaced through
  a tool you write so the agent can save/recall facts
- `ConversationBufferMemory` and friends are deprecated (moved to `langchain-classic`)

*Consequence:* Hermes gives you persistence for free but on its terms (a small char cap on
MEMORY.md; keyword rather than semantic search by default). LangChain gives you no default and
total choice — including semantic/vector recall — which is more work and more capability.

---

## 4. The point that lands live

**Provider swap.** In this repo, Part 3 is `MODEL=openrouter python run.py --mode single` —
a different YAML overlay, **no code touched, no imports changed, no reinstall**. Agents, tools,
memory, and delegation are provider-agnostic by construction.

LangChain's `init_chat_model("ollama:...")` is also ~one line — but it's a *code* change, needs
that provider's integration package installed, and tool-calling reliability genuinely varies by
model (many local models don't support native tool calling at all). The one-line swap is real;
the assumption that behaviour is identical afterwards is not — in either framework.

## 5. Honest trade-offs

**Where LangChain wins:** far larger ecosystem (retrievers, vector stores, integrations);
arbitrary graph topologies, cycles, and human-in-the-loop; it's a library, so it embeds inside
any application rather than being the process; LangSmith for tracing; vastly bigger community and
hiring pool.

**Where Hermes wins:** memory, delegation, sessions, MCP security, and an OpenAI-compatible
gateway are all present without wiring; provider-agnostic by config; a single deployment surface
instead of an assembled stack; and a strong sovereignty story — the whole thing runs locally,
MIT-licensed, with no required external service.

**Where both are the same:** neither is stable ground. LangChain has moved agent APIs twice in
about a year (`AgentExecutor` → `langgraph.prebuilt.create_react_agent` → `langchain.agents.create_agent`,
with the first two now deprecated). Hermes is pre-1.0 at v0.18.2, and we found its published docs
contradicting its own source in three places (`custom_providers` list-vs-dict, MCP tool-name
prefix, undocumented MCP security). **Pin your versions and read the source, in either camp.**

**Choose Hermes when** you want a sovereign, batteries-included agent runtime and your control
flow fits a ReAct loop with delegation. **Choose LangChain when** the agent is a component inside
a larger application, or you need graph topologies and retrieval infrastructure Hermes doesn't
model.
