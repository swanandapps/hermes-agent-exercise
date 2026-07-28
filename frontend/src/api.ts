/** Client for the relay backend. Parses the gateway's two interleaved stream shapes:
 *  OpenAI content deltas, and `hermes.tool.progress` events. */

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ToolCall {
  /** Raw name from the gateway, e.g. mcp__trade_compliance__screen_party */
  tool: string;
  toolCallId: string;
  status: "running" | "completed";
  startedAt: number;
  endedAt?: number;
}

export interface AppConfig {
  model: string;
  provider: string;
  mode: string;
}

/** Post-turn detail: what each tool was actually called with, and what came back.
 *  The live stream reports only tool names and timing. */
export interface CallDetail {
  id: string;
  name: string;
  arguments: string;
  result: string;
  failed: boolean;
}

export interface TurnDetail {
  calls: CallDetail[];
  reasoning: string;
}

export async function fetchDetail(sessionId: string): Promise<TurnDetail> {
  const res = await fetch(`/api/detail/${encodeURIComponent(sessionId)}`);
  if (!res.ok) return { calls: [], reasoning: "" };
  return res.json();
}

/** `{"reporter_country":"Germany","hs_code":72}` → `reporter_country: Germany · hs_code: 72` */
export function formatArgs(raw: string): string {
  try {
    const parsed = JSON.parse(raw);
    return Object.entries(parsed)
      .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
      .join("  ·  ");
  } catch {
    return raw;
  }
}

export interface StreamHandlers {
  onDelta(text: string): void;
  onTool(call: { tool: string; toolCallId: string; status: "running" | "completed" }): void;
  onError(message: string): void;
}

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error(`Config unavailable (${res.status})`);
  return res.json();
}

/** Strip the MCP namespace so the trace shows `screen_party`, not
 *  `mcp__trade_compliance__screen_party`. Non-MCP tools (delegate_task) pass through. */
export function toolLabel(raw: string): string {
  const parts = raw.split("__");
  return parts.length >= 3 ? parts.slice(2).join("__") : raw;
}

export async function streamChat(
  messages: ChatMessage[],
  sessionId: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, session_id: sessionId }),
    signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError(`The backend returned ${res.status}. Is it running on port 8000?`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let split: number;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      handleFrame(frame, handlers);
    }
  }
}

function handleFrame(frame: string, handlers: StreamHandlers): void {
  let event = "";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (dataLines.length === 0) return;

  const raw = dataLines.join("\n");
  if (raw === "[DONE]") return;

  let payload: any;
  try {
    payload = JSON.parse(raw);
  } catch {
    return; // ignore keep-alives and anything non-JSON
  }

  if (event === "hermes.tool.progress") {
    if (payload?.tool && payload?.toolCallId) handlers.onTool(payload);
    return;
  }
  if (event === "app.error") {
    handlers.onError(payload?.message ?? "Unknown backend error");
    return;
  }

  const delta = payload?.choices?.[0]?.delta?.content;
  if (typeof delta === "string" && delta.length > 0) handlers.onDelta(delta);
}

/** The agent's system prompt mandates that findings open with one of these verdicts,
 *  so an exact leading match is reliable. Anything else renders without a verdict —
 *  showing the wrong one in a compliance tool is worse than showing none. */
export type Verdict = "hit" | "cleared" | "nodata";

export function verdictOf(text: string): Verdict | null {
  const firstLine = text.trim().split("\n")[0] ?? "";
  // The model sometimes labels its opening line ("Direct answer: Cleared — …"),
  // so look past that prefix, but nowhere further: a verdict word buried mid-answer
  // is not a verdict. It also varies the wording — "Hit", "Hit found", "Blocked" —
  // so match on the leading word, anchored, rather than one exact phrase.
  const head = firstLine.replace(/^direct answer:\s*/i, "").trimStart();
  if (/^(hit|blocked|flagged)\b/i.test(head)) return "hit";
  if (/^(cleared|clear|no match)\b/i.test(head)) return "cleared";
  if (/^no data\b/i.test(head)) return "nodata";
  return null;
}
