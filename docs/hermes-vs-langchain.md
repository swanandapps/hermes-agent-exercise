# Hermes Agents vs LangChain Agents

> One page, presented live. Fill each section with 2-4 crisp points + a code snippet where it helps.
> Focus (their rubric): **architecture · tool definition · state management.**

## TL;DR
_One or two lines: when you'd reach for Hermes vs LangChain, and the single biggest difference._

## 1. Architecture
- **Hermes:** _ReAct loop as a runtime/agent process; profiles; SOUL.md identity; config-driven;
  provider-agnostic model layer; native delegation; gateway serves it. …_
- **LangChain:** _library you compose in code; AgentExecutor / LangGraph; you wire the loop. …_

## 2. Tool definition
- **Hermes:** _tools via MCP / toolsets; the tool's description is what routes the model; same tools
  reusable across agents. …_
- **LangChain:** _`@tool` / Tool objects / StructuredTool; bound to the agent in code. …_

## 3. State management
- **Hermes:** _built-in session + user memory (local FTS5), user_profile modeling, compression; no
  external store needed. …_
- **LangChain:** _memory classes / checkpointers (LangGraph), often an external store; you assemble it. …_

## 4. The point that lands live
- **Swapping models = one config block in Hermes** (this repo: `MODEL=openai|openrouter|ollama`,
  no code change) vs re-wiring the LLM + often the tool/memory glue in LangChain.

## 5. Honest trade-offs
- _Where LangChain wins (ecosystem, flexibility, granular control); where Hermes wins (batteries-
  included agent runtime, memory/delegation/gateway out of the box, provider-agnostic). No overclaiming._
