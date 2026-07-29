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
  /** Hermes delivers reasoning as one block when the turn finishes — never as
   *  incremental deltas — so this fires at most once, near the end. */
  onReasoning(text: string): void;
  onError(message: string): void;
}

export async function fetchConfig(): Promise<AppConfig> {
  const res = await fetch("/api/config");
  if (!res.ok) throw new Error(`Config unavailable (${res.status})`);
  return res.json();
}

/** Strip the MCP namespace so the trace shows `screen_party`, not
 *  `mcp__trade_compliance__screen_party`. Non-MCP tool names pass through unchanged. */
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
  if (event === "reasoning.available") {
    if (typeof payload?.text === "string" && payload.text.trim()) {
      handlers.onReasoning(payload.text);
    }
    return;
  }
  if (event === "app.error") {
    handlers.onError(payload?.message ?? "Unknown backend error");
    return;
  }

  // The gateway reports upstream failures (quota exhausted, provider outage, auth)
  // as an `error` object on an otherwise-normal chunk. Without this the stream just
  // ends silently and the UI spins forever — the worst way to fail in front of an audience.
  if (payload?.error) {
    const message =
      typeof payload.error === "string"
        ? payload.error
        : (payload.error.message ?? "The model provider returned an error.");
    handlers.onError(message);
    return;
  }

  const delta = payload?.choices?.[0]?.delta?.content;
  if (typeof delta === "string" && delta.length > 0) handlers.onDelta(delta);
}

/** The agent's system prompt mandates that findings open with one of these verdicts,
 *  so an exact leading match is reliable. Anything else renders without a verdict —
 *  showing the wrong one in a compliance tool is worse than showing none. */
export type Verdict = "hit" | "review" | "cleared" | "nodata";

const VERDICT_HEAD =
  /^(hit|review|cleared|clear|no data|insufficient data|blocked|flagged|do not proceed|proceed|possible match|inconclusive|no match)\b/i;

/** Leading markdown, quote and heading decoration. Formatting is not meaning. */
const undecorate = (line: string) => line.replace(/^[\s>#*_`-]+/, "").trimStart();

/**
 * The verdict-bearing opening of one line, or null.
 *
 * SOUL.md asks for the verdict word first with nothing before it, and the model mostly
 * complies — but not always, and dropping the chip whenever it slips is the wrong trade,
 * since the chip is the one thing this page exists to show. So try the bare line, then peel
 * exactly one leading label:
 *
 *   "**REVIEW** — partial matches"           bare, just bolded
 *   "Direct answer: CLEARED — none"          a labelled opening
 *   "**Screening: HIT** — matched three"     the same label, inside bold
 *   "**Rosneft Trading S.A.** — **HIT**"     the party named before the verdict
 *
 * One peel only, each pattern short and anchored, so prose that merely mentions a verdict
 * ("this is not a HIT under any reading") still yields nothing. Order matters: peeling before
 * testing the bare line would eat the verdict out of "**REVIEW** — ...".
 */
function verdictHead(line: string): string | null {
  const candidates = [
    line,
    line.replace(/^[\s>#*_`-]*[A-Za-z][A-Za-z ]{0,24}:\s*/, ""),
    line.replace(/^[^\n\u2014\u2013-]{1,60}\s+[\u2014\u2013-]\s*/, ""),
  ];
  return candidates.map(undecorate).find((c) => VERDICT_HEAD.test(c)) ?? null;
}

export function verdictOf(text: string): Verdict | null {
  // Scan the first few non-empty lines rather than only the first: the model often heads its
  // answer ("## Screening Result") and puts the verdict underneath. Deliberately shallow —
  // a verdict word further down is prose, not a verdict.
  const head = text
    .trim()
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, 3)
    .map(verdictHead)
    .find(Boolean);
  if (!head) return null;

  // REVIEW before HIT: screening is fuzzy, so most result sets are near-misses rather than
  // matches, and colouring those red is how a red banner stops meaning anything. The Writer's
  // memo opens with a deal-desk decision instead of a screening verdict; both map here.
  if (/^(review|possible match|inconclusive)\b/i.test(head)) return "review";
  if (/^(hit|blocked|flagged|do not proceed)\b/i.test(head)) return "hit";
  if (/^(cleared|clear|no match|proceed)\b/i.test(head)) return "cleared";
  if (/^(no data|insufficient data)\b/i.test(head)) return "nodata";
  return null;
}
