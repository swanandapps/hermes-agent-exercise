# Hermes vs LangChain

> Written against what this repo actually builds — a trade-compliance Researcher with two real
> tools — and what the same system looks like in LangChain.
>
> Hermes claims are cited to the installed runtime (v0.18.2, MIT, Nous Research — ~658K lines
> across 901 Python files). LangChain claims verified against current docs, mid-2026. Token and
> reliability figures are measured on this repo, not estimated.
>
> **§0 is the one-page version.** Everything after it is the evidence.

---

## §0 · The one page

**Hermes is a runtime you configure. LangChain is a library you assemble.**

Both give you a tool-using agent quickly. They diverge on everything *around* the agent.

| | Hermes | LangChain |
|---|---|---|
| **What you get** | a running process | a set of parts |
| **The agent loop** | ships | ships (`create_agent`) |
| **Sessions across restarts** | ships | you wire a checkpointer |
| **Long-term memory** | ships | you wire a store, and a tool to write to it |
| **A second agent** | one config line | you build the graph |
| **Swap the model** | a 4-line YAML file | a code change + a pip install |
| **Web API + streaming** | ships | you write a server |
| **Control flow** | fixed ReAct loop | any graph you can draw |
| **Where it lives** | *is* the process | embeds in your app |

**The honest summary:** for a two-tool demo, LangChain is less work. This exercise asked for
memory, a second agent, and a model swap — and that is exactly where the columns flip.

**Neither framework's real value is the loop.** The loop is ~15 lines and you can write it (§1).
The value is the twenty things around it you only discover you need once real users arrive.

---

## §1 · The thing neither framework is

Before comparing frameworks, it's worth knowing what they save you from. Here is a complete,
working agent loop with no framework at all:

```python
messages = [{"role": "system", "content": SOUL}, {"role": "user", "content": question}]

while True:
    reply = client.chat.completions.create(
        model=MODEL, messages=messages, tools=TOOL_SCHEMAS
    ).choices[0].message
    messages.append(reply)

    if not reply.tool_calls:
        return reply.content                      # the model is done

    for call in reply.tool_calls:                 # run what it asked for
        result = DISPATCH[call.function.name](**json.loads(call.function.arguments))
        messages.append({"role": "tool", "tool_call_id": call.id,
                         "content": json.dumps(result)})
```

That is the whole ReAct cycle: send the tools, the model picks one, run it, append the result,
go round again. **Anyone claiming you need a framework for this is selling something.**

What those 15 lines do **not** handle:

| Reality | What you write |
|---|---|
| the model call fails | retries, backoff, retry-vs-abort |
| the model returns malformed arguments | it does — repair, reject, re-prompt |
| the conversation outgrows the context window | truncation or summarisation, and *what* to drop |
| the user closes the tab and returns | session persistence |
| "what did we screen last Tuesday?" | search over past transcripts |
| facts that should outlive the session | memory, plus a policy for what earns a place in it |
| a second agent | spawn, scope its tools, collect, bound recursion |
| tools written by someone else | a protocol, a handshake, schema translation, sandboxing |
| a different model provider | per-provider quirks, token fields, context floors |
| a web UI | an API server, streaming, auth |
| "what did this cost?" | token accounting across every call in a turn |

Every row is real code, and most are discovered in production rather than on day one.

> **Break-even:** roughly *the moment the second conversation has to remember the first.*
> Before that, a framework is overhead. After that, you are writing session storage, then search
> over it, then memory policy — building a worse Hermes, part-time, while shipping a product.

---

## §2 · What this repo actually contains

| File | Lines | What it is |
|---|---|---|
| `agents/researcher/SOUL.md` | 31 | Agent identity and standing rules — plain Markdown |
| `agents/researcher/config.yaml` | 39 | MCP server registration + toolset exposure |
| `config/model.openai.yaml` | 9 | Provider block |
| `trade_tools/trade_mcp/logic.py` | 139 | The two tools' real work — HTTP, retries, normalisation |
| `trade_tools/trade_mcp/server.py` | 48 | MCP server — one `@mcp.tool()` wrapper each |
| `run.py` | 106 | Config merge + launch. **Not agent logic.** |

**Lines of agent-loop code written: zero.** No ReAct loop, no tool dispatch, no history
management, no retry control. `AIAgent.run_conversation()` supplies all of it.

### The same thing in LangChain

```python
from langchain.agents import create_agent
from langchain_core.tools import tool

@tool
def screen_party(name: str) -> dict:
    """Check a name against US restricted-party lists..."""   # same docstring-as-routing idea
    return logic.fetch_screen_party(name)

agent = create_agent(model="openai:gpt-5-mini",
                     tools=[screen_party, trade_data_lookup],
                     system_prompt=SOUL_TEXT)
```

`logic.py` — 139 of our 199 lines of real code — is **byte-identical** in both worlds. It is
domain code, not framework code. **For Part 1 alone the two are close to a wash.**

| This exercise's requirement | Hermes | LangChain |
|---|---|---|
| single tool-using agent ← *this branch* | config + tools | `create_agent(...)`, ~10 lines |
| a second agent (handoff) | `delegate_task` exists; add `delegation` to config | `langgraph-supervisor`, or `StateGraph` + `Command` (~15–40 lines you own) |
| long-term memory across turns | two config flags | checkpointer (short-term) **+** `langgraph.store` (long-term) — two systems, a backend, and a tool to write with |
| swap to open-weight models | change the `model:` block | `init_chat_model("ollama:...")` — ~1 line, but a pip install per provider |

---

## §3 · Tool definition — where most of the real difference lives

### 3.1 · The model never sees your code

It sees a JSON schema. This is what our `trade_data_lookup` function actually becomes:

```json
{
  "name": "trade_data_lookup",
  "description": "Look up real total import/export value between two countries for one
    product category and year, from UN Comtrade — country-level aggregate data only, NOT
    company/shipment-level (use screen_party for company questions). hs_code is a 2-digit
    HS chapter, e.g. 72=iron/steel, 27=mineral fuels, 85=electronics...",
  "parameters": {
    "properties": {
      "reporter_country": { "type": "string" },
      "partner_country":  { "type": "string" },
      "hs_code":          { "anyOf": [{"type": "string"}, {"type": "integer"}] },
      "year":             { "type": "integer" }
    },
    "required": ["reporter_country", "partner_country", "hs_code", "year"]
  }
}
```

Every field was read off the Python function: **name** from the function name, **description**
from the docstring, **properties** from the type hints, **required** from which parameters lack
defaults.

Two things follow, and they drive real decisions:

**The docstring is the routing signal.** It is the *only* text the model has when deciding whether
this tool answers the question. That is why ours says "NOT company/shipment-level (use
`screen_party` for company questions)" — a signpost for the model, not a note for developers. It
is also why `SOUL.md` in this repo deliberately does **not** describe the tools: the schema is
generated from the function and cannot drift from it, but a paraphrase elsewhere can.

**Schemas are the prompt's bulk.** That block is ~250 tokens, sent on *every* model call. See §5.

### 3.2 · Three ways into Hermes, and why we chose the third

Hermes's own contribution guide (`AGENTS.md`) states the rule: *"The core is a narrow waist;
capability lives at the edges. Every model tool we add is sent on every API call, so the bar for a
new core tool is high."*

| Route | Schema | Runs in | Cost to users who don't enable it | Portable |
|---|---|---|---|---|
| **Core tool** (fork Hermes) | hand-written | Hermes process | **every user, every call, forever** | no |
| **Plugin** (`ctx.register_tool`) | **hand-written** | Hermes process, full access | none | no |
| **MCP server** ← *ours* | **generated** | its own subprocess | none | **any MCP client** |

Hermes does **not** force MCP. `PluginContext.register_tool(name, toolset, schema, handler)` takes
a plain Python callable, exactly like LangChain's `@tool`. We chose MCP anyway, for three reasons:

1. **The schema is generated, so it cannot drift.** With the plugin API you hand-write ~25 lines
   of JSON and maintain it separately from the function. Add a parameter and forget the schema and
   the model never learns it exists — nothing errors at startup, it just misbehaves at runtime.
2. **Isolation.** Plugins run *inside* Hermes with full access. Hermes gates this explicitly:
   overriding a built-in requires opt-in, because otherwise *"any enabled plugin could silently
   replace a privileged built-in like `shell_exec` and exfiltrate everything the model invokes
   through it."* For a tool holding a government API key, a subprocess boundary is the right
   default.
3. **Portability.** `python -m trade_tools.trade_mcp.server` runs standalone — the same server
   works in Claude Desktop or Cursor, unchanged. A LangChain `@tool` runs in LangChain.

The cost is ~60 lines of wrapper and one IPC hop, invisible next to an HTTP call to trade.gov.

### 3.3 · What Hermes wraps MCP in

Undocumented, found in `tools/mcp_tool.py`: prompt-injection scanning of tool descriptions, an
OSV.dev malware preflight before spawning stdio servers, approval gating, and a filtered
subprocess environment.

> **A real gotcha.** That env filtering (`_build_safe_env()`) means an MCP subprocess does *not*
> inherit your shell. Our `TRADE_GOV_API_KEY` silently arrived empty and the agent hallucinated
> instead of calling the tool. Fix: explicit `${VAR}` passthrough in the server's `env:` block.
> Good security default, sharp edge, no mention in the docs.

**LangChain** uses the `@tool` decorator (or `StructuredTool`), bound per agent via
`.bind_tools()`. Schema generation from type hints works the same way. MCP is supported via
`langchain-mcp-adapters` (`MultiServerMCPClient`) — so **MCP is not a Hermes advantage**, though
in Hermes it is a first-class config key rather than an add-on package, and none of the security
machinery above has a LangChain equivalent out of the box.

---

## §4 · State and memory

**Hermes** — four mechanisms, all built in, no external service:

| | What | Cost |
|---|---|---|
| `MEMORY.md` / `USER.md` | curated facts, injected at session start | grows the prompt permanently |
| SQLite + FTS5 over the full transcript | `session_search`, **no LLM in the search path** | ~1.5K tokens/call for the tool |
| Skills | procedural `SKILL.md` playbooks | loaded on relevance |
| One optional external provider | 8 ship (Hindsight, Mem0, Honcho, …) | one `memory.provider` key, zero app code |

**LangChain** — deliberately separated, and you wire them:

- **Short-term:** a LangGraph checkpointer (`InMemorySaver` → `SqliteSaver`/`PostgresSaver`)
- **Long-term:** `langgraph.store` (`InMemoryStore` → `PostgresStore`), usually surfaced through a
  tool you write so the agent can save and recall
- `ConversationBufferMemory` and friends are deprecated (moved to `langchain-classic`)

*Consequence:* Hermes gives persistence free but on its terms — a char cap on `MEMORY.md`, keyword
rather than semantic search by default. LangChain gives no default and total choice, including
vector recall: more work, more capability.

> **Measured, and rarely mentioned:** memory is a **rising tax on every call**. Editing this
> repo's prompt to remove 40 tokens showed a *net +2*, because `MEMORY.md` had grown 42 tokens in
> between. Long-term memory is not a one-off cost, and it quietly invalidates naive before/after
> token comparisons.

---

## §5 · What it costs — measured on this repo

Framework comparisons usually stop at lines of code. The number that reaches the invoice is
tokens, and a framework's **defaults** decide most of it.

| State | Tools in prompt | Prompt tokens/call |
|---|---|---|
| Hermes defaults | 49 | **21,373** |
| after scoping `platform_toolsets` | 5 | **6,932** |
| after disabling unused MCP discovery | 5 | **6,694** |

**A 68% cut, from config alone.** The cause is worth naming: Hermes resolves toolsets *per
platform*, and the CLI and the web gateway are different platforms (`cli` vs `api_server`).
Configuring only the CLI left the gateway silently running all 49 tools.

Two things generalise beyond Hermes:

- **The saving multiplies.** One question is 4–5 model calls, each carrying the full tool menu.
  14,441 tokens saved per call is ~72,000 per question.
- **Fewer tools also worked better.** A model choosing among 5 tools routes more reliably than one
  choosing among 49. Cost and quality moved together, which is rare.

A framework's defaults are tuned for a *general* assistant, not for your agent. Knowing the loop
is 15 lines (§1) is precisely what makes 21,373 tokens look wrong rather than inevitable.

---

## §6 · Provider swap

In this repo, swapping models is `MODEL=openrouter python run.py` — a different YAML overlay.
**No code touched, no imports changed, no reinstall.** Agents and tools are provider-agnostic by
construction.

LangChain's `init_chat_model("ollama:...")` is also ~one line — but it is a *code* change and
needs that provider's integration package installed.

**The one-line swap is real in both. The assumption that behaviour is identical afterwards is
not.** Measured here on Qwen3-32B: the two research tools never failed, but **delegation
succeeded 4 times in 8** — a coin flip. The failure is specific and worth knowing: the model
writes `delegate_task(goal="...")` as plain text in the `content` field instead of the structured
`tool_calls` field. **A serialisation failure, not a reasoning failure** — it knew what to do and
said it in the wrong box. Nested tool calls are where open-weight models break first, and no
framework fixes that.

---

## §7 · Open source, licence and community

| | Hermes | LangChain |
|---|---|---|
| **Licence** | MIT | MIT |
| **Backed by** | Nous Research | LangChain, Inc. (VC-funded) |
| **Maturity** | pre-1.0 (v0.18.2) | post-1.0, several major API generations |
| **Community** | small, young | very large — the default answer in most job specs |
| **Ecosystem** | MCP servers + 8 memory providers + plugins | hundreds of integrations, retrievers, vector stores |
| **Commercial layer** | none required | LangSmith (tracing/eval) — the funded product |
| **Hiring pool** | narrow | wide |
| **Runs fully offline** | yes, by design | yes, if you choose offline components |

Both are MIT, so neither is a licensing risk. The differences that matter operationally:

**Governance shape.** LangChain's open-source core is funded by a commercial observability
product. That is a healthy, common model, but the incentive gradient points toward the hosted
service. Hermes has no commercial layer to pull it — the sovereignty story ("runs entirely on your
own hardware, no required external service") is the point of the project, not a feature of it.

**Ecosystem size is LangChain's genuine moat.** If tomorrow's requirement is a Postgres vector
retriever, LangChain has one and Hermes does not model retrieval at all. Nothing about Hermes
prevents you writing it — it just isn't handed to you.

**Both are unstable ground.** LangChain has moved agent APIs twice in about a year
(`AgentExecutor` → `create_react_agent` → `create_agent`, the first two deprecated). Hermes is
pre-1.0, and building this exercise found its published docs contradicting its own source in three
places (`custom_providers` list-vs-dict, the MCP tool-name prefix, and undocumented MCP security).
**Pin versions and read the source, in either camp.**

**A note on contributing back.** Hermes's `AGENTS.md` ranks contributions explicitly — skill, then
MCP server, then plugin, and only then core. That ladder is a real advantage for a company like
PST.AG: domain tools live at the edge, cost nothing to other users, and survive upgrades without
maintaining a fork. This repo follows it — our tools are an MCP server, and Hermes's own tree is
untouched.

---

## §8 · Honest trade-offs

**Where LangChain wins** — far larger ecosystem; arbitrary graph topologies, cycles and
human-in-the-loop; it embeds inside your application instead of being the process; LangSmith for
tracing and evaluation; a much bigger community and hiring pool.

**Where Hermes wins** — memory, delegation, sessions, MCP security and an OpenAI-compatible
gateway all present without wiring; provider-agnostic by config; one deployment surface instead of
an assembled stack; and a genuine sovereignty story — MIT, fully local, no required external
service.

**Where both are the same** — the loop is trivial, the surrounding twenty things are not, and
neither project's API is stable yet.

> **Choose Hermes** when you want a sovereign, batteries-included runtime and your control flow
> fits a ReAct loop with delegation.
>
> **Choose LangChain** when the agent is a component inside a larger application, or you need
> graph topologies and retrieval infrastructure Hermes does not model.
>
> **Choose neither** when you have two tools, one user, and no memory requirement. That is 60
> lines, and a framework will cost you more in defaults than it saves you in code.
