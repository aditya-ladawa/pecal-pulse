"""Chat transport owned by Aditya/Codex; sales API remains independently mergeable."""
import json
import logging
from uuid import UUID
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Request, HTTPException
from ..agents.contracts import AgentChatRequest
from .v2 import DEFAULT_SNAPSHOT, _mode
from ..agents.react_agent import ChatUnavailable, ThreadBusy
from ..agents.errors import chat_failure

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

@router.get("/chat/status")
async def status(request: Request):
    service = request.app.state.chat
    return {"mode": "agent", "configured": service.configured, "model": service.model_name,
            "data_mode": _mode(DEFAULT_SNAPSHOT), "snapshot_id": DEFAULT_SNAPSHOT, "checkpointing": "sqlite"}

@router.post("/chat")
async def chat(payload: AgentChatRequest, request: Request):
    try:
        return await request.app.state.chat.reply(payload)
    except Exception as exc:
        status, code, message = chat_failure(exc)
        logger.warning("Agent failure category=%s exception=%s", code, type(exc).__name__)
        raise HTTPException(status, message) from exc

@router.get("/chat/threads/{thread_id}/messages")
async def history(thread_id: UUID, request: Request):
    return await request.app.state.chat.history(thread_id)

@router.post("/chat/stream")
async def stream_chat(payload: AgentChatRequest, request: Request):
    service = request.app.state.chat
    if not service.configured:
        raise HTTPException(503, "Add OPENROUTER_API_KEY to the root .env and restart the backend.")
    if payload.thread_id and str(payload.thread_id) in service.active_threads:
        raise HTTPException(409, "This conversation already has a response in progress.")

    async def frames():
        try:
            async for event in service.stream_reply(payload):
                yield "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
        except Exception as exc:
            _, code, message = chat_failure(exc)
            logger.warning("Agent stream failure category=%s exception=%s", code, type(exc).__name__)
            yield "data: " + json.dumps({"type":"error", "code":code, "message":message}) + "\n\n"
    return StreamingResponse(frames(), media_type="text/event-stream", headers={
        "Cache-Control":"no-cache", "X-Accel-Buffering":"no",
    })
