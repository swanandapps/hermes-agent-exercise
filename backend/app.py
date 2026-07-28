"""Thin backend for the Trade Compliance Researcher web UI.

Its only jobs: keep the gateway API key server-side, and relay the Hermes gateway's
SSE stream to the browser unchanged. All agent work — the ReAct loop, tool dispatch,
delegation, memory — happens in the Hermes gateway, not here.

    uvicorn backend.app:app --reload --port 8000
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import yaml
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWAY_URL = os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642")
GATEWAY_KEY = os.environ.get("API_SERVER_KEY", "")
PROFILE_NAME = os.environ.get("HERMES_PROFILE", "hermes-exercise")
PROFILE_CONFIG = Path.home() / ".hermes" / "profiles" / PROFILE_NAME / "config.yaml"

app = FastAPI(title="Trade Compliance Researcher")


def _live_config() -> dict:
    """Read what the gateway is ACTUALLY running, from the profile it loaded.

    Not from this process's own env vars: the backend and the gateway are separate
    processes, and `run.py` can re-sync the profile to a different provider without
    the backend ever knowing. During the Part 3 demo the header is the only on-screen
    evidence that the model really changed, so it has to read the same file the
    gateway did — anything else can quietly disagree with reality.
    """
    if not PROFILE_CONFIG.exists():
        return {}
    try:
        return yaml.safe_load(PROFILE_CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}


@app.get("/api/config")
def get_config() -> dict:
    """What the header displays: the model and mode the gateway actually loaded."""
    cfg = _live_config()
    model = cfg.get("model") or {}
    cli_toolsets = ((cfg.get("platform_toolsets") or {}).get("cli")) or []
    return {
        "model": model.get("default", "unknown"),
        "provider": model.get("provider", "unknown"),
        # Handoff mode is defined by delegation being available, which is a fact
        # about the loaded config rather than something we can assert from outside.
        "mode": "handoff" if "delegation" in cli_toolsets else "single",
    }


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    """Relay one turn to the gateway, streaming the response back verbatim.

    The gateway emits two interleaved things on this stream: OpenAI-style content
    deltas, and `hermes.tool.progress` events. Both pass through untouched — the
    browser decides how to render them.
    """
    body = await request.json()
    payload = {
        "model": get_config()["model"],
        "messages": body.get("messages", []),
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {GATEWAY_KEY}",
        "Content-Type": "application/json",
    }
    # Session continuity — the same id across turns keeps one Hermes session,
    # which is what Part 2's long-term memory is scoped to.
    session_id = body.get("session_id")
    if session_id:
        headers["X-Hermes-Session-Id"] = session_id

    async def relay():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", f"{GATEWAY_URL}/v1/chat/completions", json=payload, headers=headers
                ) as upstream:
                    if upstream.status_code != 200:
                        detail = (await upstream.aread()).decode("utf-8", "replace")[:400]
                        yield _error_event(f"Gateway returned {upstream.status_code}: {detail}")
                        return
                    async for chunk in upstream.aiter_raw():
                        yield chunk
        except httpx.HTTPError as exc:
            yield _error_event(
                f"Cannot reach the Hermes gateway at {GATEWAY_URL} ({exc}). "
                "Start it with: hermes -p hermes-exercise gateway run"
            )

    return StreamingResponse(relay(), media_type="text/event-stream")


def _error_event(message: str) -> bytes:
    """Surface backend failures on the same stream, so the UI can show them in place."""
    import json

    return f"event: app.error\ndata: {json.dumps({'message': message})}\n\n".encode()


def _unwrap_tool_result(raw: str) -> tuple[str, bool]:
    """Pull the tool's own JSON out of Hermes's untrusted-content envelope.

    Results arrive wrapped in an `<untrusted_tool_result>` guard block (Hermes's
    prompt-injection defence) with the payload JSON-escaped inside a
    `{"result": "..."}` envelope. Returns (readable payload, failed).
    """
    import json as _json
    import re

    match = re.search(r'\{"result":\s*"(.*?)"\}\s*(?:</untrusted_tool_result>|$)', raw, re.DOTALL)
    if match:
        try:
            inner = _json.loads('"' + match.group(1) + '"')
            parsed = _json.loads(inner)
            return _json.dumps(parsed, indent=2), "error" in parsed
        except (ValueError, TypeError):
            pass
    # Envelope changed or payload truncated — fall back to a text probe rather than
    # silently reporting success.
    return raw, ('\\"error\\"' in raw or '"error"' in raw)


@app.get("/api/detail/{session_id}")
async def turn_detail(session_id: str) -> dict:
    """Tool arguments, tool results, and the model's reasoning for the latest turn.

    The chat stream reports only which tools ran and when. The arguments they were
    called with — and whether a call actually failed — live in the session history,
    which is what makes a run diagnosable after the fact.
    """
    url = f"{GATEWAY_URL}/api/sessions/{session_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            res = await client.get(url, headers={"Authorization": f"Bearer {GATEWAY_KEY}"})
            res.raise_for_status()
            messages = res.json().get("data", [])
    except (httpx.HTTPError, ValueError):
        return {"calls": [], "reasoning": ""}

    # Walk back to the last user message — everything after it belongs to this turn.
    start = 0
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            start = i
            break
    turn = messages[start:]

    results: dict[str, str] = {}
    for message in turn:
        if message.get("role") == "tool" and message.get("tool_call_id"):
            results[message["tool_call_id"]] = message.get("content") or ""

    calls = []
    reasoning_parts = []
    for message in turn:
        if message.get("role") != "assistant":
            continue
        reasoning = message.get("reasoning") or message.get("reasoning_content") or ""
        if reasoning:
            reasoning_parts.append(reasoning)
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {})
            payload, failed = _unwrap_tool_result(results.get(call.get("id", ""), ""))
            calls.append(
                {
                    "id": call.get("id", ""),
                    "name": fn.get("name", ""),
                    "arguments": fn.get("arguments", ""),
                    "result": payload[:700],
                    # A tool that reports an error still succeeds at the transport
                    # level, so failure has to be read out of the payload itself.
                    "failed": failed,
                }
            )

    return {"calls": calls, "reasoning": "\n\n".join(reasoning_parts)}


# Serve the built frontend when it exists (production / Docker). In dev, Vite serves
# the UI and proxies /api here instead.
_DIST = REPO_ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_DIST / "index.html")
