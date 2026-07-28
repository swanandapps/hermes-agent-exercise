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
MODEL = os.environ.get("MODEL", "openai")
MODE = os.environ.get("HERMES_MODE", "single")

app = FastAPI(title="Trade Compliance Researcher")


def _model_name() -> str:
    """The concrete model id from the active provider overlay (e.g. gpt-5-mini)."""
    overlay = REPO_ROOT / "config" / f"model.{MODEL}.yaml"
    if not overlay.exists():
        return MODEL
    try:
        return (yaml.safe_load(overlay.read_text()) or {}).get("model", {}).get("default", MODEL)
    except Exception:
        return MODEL


@app.get("/api/config")
def get_config() -> dict:
    """What the header displays: which model and which mode are actually running."""
    return {"model": _model_name(), "provider": MODEL, "mode": MODE}


@app.post("/api/chat")
async def chat(request: Request) -> StreamingResponse:
    """Relay one turn to the gateway, streaming the response back verbatim.

    The gateway emits two interleaved things on this stream: OpenAI-style content
    deltas, and `hermes.tool.progress` events. Both pass through untouched — the
    browser decides how to render them.
    """
    body = await request.json()
    payload = {
        "model": _model_name(),
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


# Serve the built frontend when it exists (production / Docker). In dev, Vite serves
# the UI and proxies /api here instead.
_DIST = REPO_ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_DIST / "index.html")
