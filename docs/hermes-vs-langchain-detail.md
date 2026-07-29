# Hermes vs LangChain — the same job, written both ways

> Companion to the one-page comparison ([`hermes-vs-langchain.md`](hermes-vs-langchain.md)).
> That page says how the two differ; this one shows the code. Each section is the same task
> written every way that applies: by hand, in Hermes, in LangChain.
>
> Hermes cited against the installed runtime (v0.18.2, MIT, Nous Research). LangChain verified
> against current docs, mid-2026.

---

## 1 · The agent loop

Worth writing out, because it is the thing people assume a framework is for.

### By hand

```python
messages = [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}]

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

Fifteen lines. Send the tools, the model picks one, run it, append the result, go round again.

### In LangChain

```python
from langchain.agents import create_agent

agent = create_agent(model="openai:gpt-5-mini", tools=[...], system_prompt=SYSTEM_PROMPT)
```

`create_agent` is a prebuilt over LangGraph. Drop to `StateGraph` when you need branches, loops,
or a pause for human approval.

### In Hermes

There is nothing to write. The loop *is* the runtime — `AIAgent.run_conversation()` — and you
configure what it can reach. You also cannot replace it, which is the trade.

### What the fifteen lines do not handle

| Reality | What you end up writing |
|---|---|
| the model call fails | retries, backoff, retry-vs-abort |
| the model returns malformed arguments | repair, reject, or re-prompt |
| the conversation outgrows the context window | truncation or summarisation, and *what* to drop |
| the user closes the tab and comes back | session persistence |
| "what did we look at last Tuesday?" | search over past transcripts |
| facts that should outlive the session | memory, and a policy for what earns a place in it |
| a second agent | spawn, scope its tools, collect, bound recursion |
| tools written by someone else | a protocol, a handshake, schema translation, sandboxing |
| a different model provider | per-provider quirks, token fields, context floors |
| a web UI | an API server, streaming, auth |
| "what did this cost?" | token accounting across every call in a turn |

**A framework earns its place roughly when the second conversation has to remember the first.**
Before that it is overhead; after it, you are writing session storage, then search over it, then
memory policy.

---

## 2 · Defining a tool

The same function, three ways to expose it.

### LangChain — a decorator

```python
from langchain_core.tools import tool

@tool
def screen_party(name: str) -> dict:
    """Check whether a name appears on a restricted-party list."""
    return do_the_work(name)

agent = create_agent(model, tools=[screen_party])
```

In-process, no boundary, no ceremony. Any sandboxing is yours to add.

### Hermes — a plugin

The closest equivalent. `~/.hermes/plugins/<name>/` with a manifest and:

```python
ctx.register_tool(
    name="screen_party",
    toolset="compliance",
    schema={...},                 # hand-written JSON schema
    handler=do_the_work,          # a plain Python callable
)
```

Also in-process — which is why Hermes gates it. Replacing a built-in requires
`allow_tool_override: true` in config, because otherwise any enabled plugin could silently swap
out a privileged tool.

### Hermes — an MCP server

A separate program the runtime launches and talks to over stdin/stdout:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("compliance")

@mcp.tool()
def screen_party(name: str) -> dict:
    """Check whether a name appears on a restricted-party list."""
    return do_the_work(name)

mcp.run()
```

```yaml
# config.yaml
mcp_servers:
  compliance:
    command: python
    args: ["-m", "my_tools.server"]
    env: { API_KEY: "${API_KEY}" }
platform_toolsets:
  cli:        [compliance]
  api_server: [compliance]
```

### Choosing between the three

| | Core tool (fork) | Plugin | MCP server |
|---|---|---|---|
| Schema | hand-written | **hand-written** | **generated from the function** |
| Runs in | the runtime | the runtime, full access | its own process |
| Cost to users who don't enable it | **every call, forever** | none | none |
| Works outside this framework | no | no | **any MCP client** |
| Setup | fork the project | manifest + register call | server file + config block |

The generated schema is the deciding argument for most projects. Hand-written JSON is a second
copy of the truth, and only one of the two travels with the function: add a parameter and forget
the schema, and nothing errors — the model simply never learns the parameter exists.

`AGENTS.md` in the Hermes source states the underlying rule: *"the core is a narrow waist;
capability lives at the edges."* Every core tool is prompt cost for every user, forever.

---

## 3 · What the model actually receives

Neither framework sends your code. Both send JSON, generated from the function:

```json
{
  "name": "trade_data_lookup",
  "description": "Look up the total value of exports from one country to another for a
    product category and year. Country-level aggregates only, NOT company-level...",
  "parameters": {
    "properties": {
      "reporter_country": { "type": "string" },
      "hs_code":          { "anyOf": [{"type": "string"}, {"type": "integer"}] },
      "year":             { "type": "integer" }
    },
    "required": ["reporter_country", "hs_code", "year"]
  }
}
```

| JSON field | Comes from |
|---|---|
| `name` | the function name |
| `description` | **the docstring** |
| `properties` | the type hints |
| `required` | parameters without defaults |

Two consequences, and they hold in both frameworks:

**The docstring is the routing signal.** It is the only text the model has when deciding whether
this tool answers the question, so it should carry guidance — "use X instead for company
questions" — rather than implementation notes. Restating it in the system prompt gives you two
copies of one fact that can disagree.

**Tool schemas are most of the prompt.** A block like the one above is roughly 250 tokens, sent
on every call, multiplied by your tool count. That is why default tool sets matter more than they
look: enabling 49 tools for an agent that uses five costs about 15,000 tokens per call, and every
model call in a turn pays it again.

---

## 4 · Exposing tools

**LangChain** binds per agent — `create_agent(model, tools=[a, b])` or `.bind_tools()`. The list
is the exposure.

**Hermes** separates registration from exposure. Registering puts a tool in the registry;
`platform_toolsets` decides who sees it — and toolsets resolve **per platform**, where the CLI and
the HTTP gateway count as different platforms:

```yaml
platform_toolsets:
  cli:        [compliance]
  api_server: [compliance]      # the gateway is a separate platform
```

Listing only one leaves the other on the framework's defaults, so the same agent can be running
two different tool sets depending on how you reached it. Worth knowing before measuring anything.

### What Hermes wraps around MCP

Undocumented, in `tools/mcp_tool.py`. None of it has a LangChain equivalent out of the box:

| | |
|---|---|
| Prompt-injection scanning of tool descriptions | a hostile tool description is a real attack surface |
| OSV.dev malware preflight before spawning | checks the package before running it |
| Filtered subprocess environment | the tool process does **not** inherit your shell; secrets need explicit `${VAR}` passthrough |
| Approval gating | a tool can require confirmation before it runs |

MCP itself is not a Hermes advantage — LangChain supports it via `langchain-mcp-adapters`. The
difference is that it is a first-class config key in one and an extra package in the other, and
that the four rows above come free in only one of them.

---

## 5 · Memory and sessions

| What you need | Hermes | LangChain |
|---|---|---|
| History within a session | automatic | a checkpointer you wire |
| Survives a restart | automatic — SQLite | `SqliteSaver` / `PostgresSaver` |
| Curated long-lived facts | `MEMORY.md` / `USER.md`, injected at session start | `langgraph.store` **+** a tool you write so the agent can save |
| Search past transcripts | `session_search` — SQLite FTS5, **no model call in the search path** | build it |
| Reusable procedures | Skills (`SKILL.md`) | no equivalent |
| Meaning-based recall | not by default | your choice of vector store |
| Hosted memory service | one `memory.provider` key — eight ship | pick and wire your own |

```python
# LangChain
from langgraph.checkpoint.sqlite import SqliteSaver
graph = builder.compile(checkpointer=SqliteSaver.from_conn_string("state.db"))
```

```yaml
# Hermes
memory:
  memory_enabled: true
  user_profile_enabled: true
```

Two properties of the Hermes side to know before relying on it:

- **`MEMORY.md` is capped** — 2,200 characters by default. When full it *refuses* the write and
  asks the agent to consolidate, rather than silently dropping the oldest entry.
- **It is injected into every prompt.** Memory is not a one-off cost; it grows, and from then on
  it grows the prompt on every call.

`ConversationBufferMemory` and friends are deprecated in LangChain, moved to `langchain-classic`.

---

## 6 · A second agent

**Hermes** — a built-in tool. Add `delegation` to the toolset list and the agent can call:

```python
delegate_task(goal="...", context="...", role="leaf", toolsets=[])
```

The child starts from a blank conversation. It cannot see the parent's history or tool results,
so everything it needs must be written into `goal` and `context`. There is no parameter for
pointing a child at a different profile or system prompt — its identity arrives inside those
strings.

**LangChain** — `langgraph-supervisor`, or a hand-rolled `StateGraph` with `Command` handoffs:
roughly 15–40 lines you own and can shape exactly as you like.

The usual trade. Hermes gives you one delegation shape for free; LangChain gives you any shape,
and you maintain it.

---

## 7 · Swapping the model

| | Hermes | LangChain |
|---|---|---|
| What changes | a YAML block | a line of code |
| How | `model: { provider, default, base_url }` | `init_chat_model("ollama:...")` |
| Install needed | none | that provider's integration package |
| Redeploy | no | yes |
| Agent or tool code touched | none | none |

Both are genuinely about one line. The difference is that one is configuration and one is code,
which matters when the person switching models is not the person who can deploy.

**The one-line swap is real in both. The assumption that behaviour is identical afterwards is
not.** Tool-calling fidelity varies sharply by model, and it fails in a specific way: a weaker
model writes the call as plain text in the `content` field instead of the structured `tool_calls`
field. It knew what to do and put it in the wrong box. Nested calls — an agent delegating to
another agent — are where this appears first, well before single tool calls start failing.

---

## 8 · Serving it

**Hermes** ships an OpenAI-compatible gateway: `/v1/chat/completions` with streaming, plus
session endpoints, cron, and adapters for messaging platforms. Point any OpenAI client at it.

**LangChain** is a library, so serving is yours — FastAPI, LangServe, or whatever your
application already uses. That is the point of a library, and it is why LangChain drops into an
existing product more easily than a runtime does.

---

## 9 · Honest trade-offs

| Dimension | Hermes | LangChain | Better |
|---|---|---|---|
| Control flow | one loop + delegation | any graph — cycles, interrupts, human-in-the-loop | LangChain |
| Ecosystem | MCP servers, memory providers, plugins | retrievers, vector stores, hundreds of integrations | LangChain |
| Where it lives | *is* the process | embeds inside your application | LangChain |
| Tracing / evaluation | none built in | LangSmith | LangChain |
| Batteries | memory, sessions, delegation, gateway present | wire each one | Hermes |
| Provider swap | config | code + install | Hermes |
| Deployment surface | one runtime | an assembled stack | Hermes |
| Tool sandboxing | injection scan, malware preflight, env filtering | none out of the box | Hermes |
| Sovereignty | MIT, fully local, no required service | possible, yours to assemble | Hermes |
| API stability | pre-1.0 | agent API moved twice in ~a year | *neither* |

**On that last row** — LangChain went `AgentExecutor` → `create_react_agent` → `create_agent`,
with the first two deprecated. Hermes is pre-1.0, and its published documentation contradicts its
own source in more than one place. Pin your versions and read the source, whichever you pick.
