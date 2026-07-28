import { useEffect, useRef, useState } from "react";
import {
  fetchConfig,
  fetchDetail,
  formatArgs,
  streamChat,
  toolLabel,
  verdictOf,
  type AppConfig,
  type ChatMessage,
  type TurnDetail,
  type ToolCall,
  type Verdict,
} from "./api";

interface Exchange {
  query: string;
  answer: string;
  tools: ToolCall[];
  detail?: TurnDetail;
  error?: string;
  done: boolean;
  askedAt: Date;
}

const VERDICT_COPY: Record<Verdict, { label: string; channel: string }> = {
  hit: { label: "Hit found", channel: "Red channel" },
  cleared: { label: "Cleared", channel: "Green channel" },
  nodata: { label: "No data", channel: "Unresolved" },
};

// The third names a specific entity on purpose: without one, the agent correctly
// asks who the counterparty is instead of screening, which makes a poor demo.
const EXAMPLES = [
  "Is Rosneft on any US restricted-party list?",
  "How much steel did Germany export to India in 2022?",
  "We're signing a steel deal with Rosneft Trading S.A. Screen them, and check Germany's iron & steel exports to the Russian Federation in 2022.",
];

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const sessionId = useRef(`web-${Date.now()}`);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig(null));
  }, []);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [exchanges]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;

    setInput("");
    setBusy(true);

    const index = exchanges.length;
    setExchanges((prev) => [
      ...prev,
      { query: trimmed, answer: "", tools: [], done: false, askedAt: new Date() },
    ]);

    const history: ChatMessage[] = exchanges.flatMap((e) => [
      { role: "user" as const, content: e.query },
      { role: "assistant" as const, content: e.answer },
    ]);

    const patch = (fn: (e: Exchange) => Exchange) =>
      setExchanges((prev) => prev.map((e, i) => (i === index ? fn(e) : e)));

    try {
      await streamChat([...history, { role: "user", content: trimmed }], sessionId.current, {
        onDelta: (text) => patch((e) => ({ ...e, answer: e.answer + text })),
        onTool: (call) =>
          patch((e) => {
            const existing = e.tools.find((t) => t.toolCallId === call.toolCallId);
            if (!existing) {
              return {
                ...e,
                tools: [...e.tools, { ...call, startedAt: Date.now() }],
              };
            }
            return {
              ...e,
              tools: e.tools.map((t) =>
                t.toolCallId === call.toolCallId
                  ? { ...t, status: call.status, endedAt: call.status === "completed" ? Date.now() : t.endedAt }
                  : t,
              ),
            };
          }),
        onError: (message) => patch((e) => ({ ...e, error: message })),
      });
    } catch (err) {
      patch((e) => ({ ...e, error: err instanceof Error ? err.message : String(err) }));
    } finally {
      patch((e) => ({ ...e, done: true }));
      setBusy(false);
      // Arguments, results and reasoning only exist in the session history —
      // the live stream carries names and timing alone.
      fetchDetail(sessionId.current)
        .then((detail) => patch((e) => ({ ...e, detail })))
        .catch(() => undefined);
    }
  }

  return (
    <div className="shell">
      <header className="chrome">
        <div className="chrome__title">
          <span className="chrome__mark" aria-hidden="true" />
          Trade Compliance Researcher
        </div>
        <dl className="chrome__meta">
          <div>
            <dt>Model</dt>
            <dd>{config?.model ?? "—"}</dd>
          </div>
          <div>
            <dt>Mode</dt>
            <dd>{config?.mode ?? "—"}</dd>
          </div>
        </dl>
      </header>

      <div className="transcript" ref={transcriptRef}>
        {exchanges.length === 0 && <Welcome onPick={ask} busy={busy} />}
        {exchanges.map((exchange, i) => (
          <Finding key={i} exchange={exchange} index={i + 1} />
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          ask(input);
        }}
      >
        <span className="composer__prompt" aria-hidden="true">
          &gt;
        </span>
        <input
          className="composer__input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Screen a counterparty, or check a trade lane…"
          disabled={busy}
          autoFocus
        />
        <button className="composer__send" type="submit" disabled={busy || !input.trim()}>
          {busy ? "Screening…" : "Screen"}
        </button>
      </form>
    </div>
  );
}

function Welcome({ onPick, busy }: { onPick: (q: string) => void; busy: boolean }) {
  return (
    <div className="welcome">
      <p className="welcome__lede">
        Pre-deal due diligence against live sources: US restricted-party lists and UN Comtrade
        trade flows. Every figure comes from a tool call you can see below the finding.
      </p>
      <p className="welcome__label">Try</p>
      <ul className="welcome__examples">
        {EXAMPLES.map((example) => (
          <li key={example}>
            <button type="button" onClick={() => onPick(example)} disabled={busy}>
              {example}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Finding({ exchange, index }: { exchange: Exchange; index: number }) {
  const verdict = exchange.done ? verdictOf(exchange.answer) : null;
  const time = exchange.askedAt.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <article className="exchange">
      <div className="query">
        <span className="query__ref">Query {String(index).padStart(3, "0")}</span>
        <span className="query__time">{time}</span>
        <p className="query__text">{exchange.query}</p>
      </div>

      <div className="finding">
        {verdict && (
          <div className={`verdict verdict--${verdict}`}>
            <span className="verdict__label">{VERDICT_COPY[verdict].label}</span>
            <span className="verdict__channel">{VERDICT_COPY[verdict].channel}</span>
          </div>
        )}

        <div className="finding__body">
          {exchange.answer ? (
            <p>{exchange.answer.replace(/^\s+/, "")}</p>
          ) : exchange.error ? null : (
            <p className="finding__waiting">Consulting sources…</p>
          )}
          {!exchange.done && exchange.answer && <span className="caret" aria-hidden="true" />}
        </div>

        {exchange.error && (
          <div className="finding__error">
            <strong>Screening did not complete.</strong> {exchange.error}
          </div>
        )}

        {exchange.detail?.reasoning && <Reasoning text={exchange.detail.reasoning} />}

        {exchange.tools.length > 0 && (
          <div className="sources">
            <p className="sources__label">Sources consulted</p>
            <ul>
              {exchange.tools.map((tool) => {
                const detail = exchange.detail?.calls.find((c) => c.id === tool.toolCallId);
                const failed = detail?.failed ?? false;
                return (
                  <li
                    key={tool.toolCallId}
                    className={`source source--${tool.status}${failed ? " source--failed" : ""}`}
                  >
                    <div className="source__head">
                      <span className="source__name">{toolLabel(tool.tool)}</span>
                      <span className="source__status">
                        {tool.status === "running"
                          ? "running…"
                          : failed
                            ? "rejected"
                            : tool.endedAt
                              ? `${((tool.endedAt - tool.startedAt) / 1000).toFixed(1)}s`
                              : "done"}
                      </span>
                    </div>
                    {detail && (
                      <p className="source__args">{formatArgs(detail.arguments)}</p>
                    )}
                    {detail && failed && (
                      <p className="source__result">{firstError(detail.result)}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </article>
  );
}

/** Pull the error message out of a tool's JSON payload for a one-line summary. */
function firstError(result: string): string {
  try {
    const parsed = JSON.parse(result);
    if (typeof parsed?.error === "string") return parsed.error;
  } catch {
    /* fall through to the raw text */
  }
  return result.slice(0, 140);
}

function Reasoning({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="reasoning">
      <button
        type="button"
        className="reasoning__toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="reasoning__chevron" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
        Reasoning
      </button>
      {open && <pre className="reasoning__text">{text}</pre>}
    </div>
  );
}
