"""Chat transport owned by Aditya/Codex; sales API remains independently mergeable."""
import json
from uuid import UUID
from fastapi.responses import StreamingResponse
from openai import APIStatusError
from fastapi import APIRouter, Request, HTTPException
from ..agents.contracts import AgentChatRequest
from .v2 import DEFAULT_SNAPSHOT, _mode
from ..agents.react_agent import ChatUnavailable, ThreadBusy

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
    except ThreadBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ChatUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "The assistant timed out. Please retry with a smaller request.") from exc
    except APIStatusError as exc:
        body = exc.body if isinstance(exc.body, dict) else {}
        error = body.get("error", body)
        message = str(error.get("message", "")) if isinstance(error, dict) else ""
        if "Paid model training violation" in message:
            raise HTTPException(503, "OpenRouter blocks this model under your account privacy policy (paid-model training restriction). Review https://openrouter.ai/settings/privacy or explicitly select another model. No account settings or model were changed.") from exc
        raise HTTPException(502, "OpenRouter rejected the request for the configured model. Check account access and model availability.") from exc
    except Exception as exc:
        # Provider exception text can contain request data; do not send it to the browser.
        raise HTTPException(502, "The configured OpenRouter model could not complete the request. Check model availability and account access; no alternate model was used.") from exc

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
            if isinstance(exc, ThreadBusy):
                message = "This conversation already has a response in progress."
            elif isinstance(exc, ChatUnavailable):
                message = str(exc)
            elif isinstance(exc, TimeoutError):
                message = "The assistant timed out. Please retry with a smaller request."
            else:
                message = "The model could not finish this response. Check OpenRouter access and try again."
            yield "data: " + json.dumps({"type":"error", "message":message}) + "\n\n"
    return StreamingResponse(frames(), media_type="text/event-stream", headers={
        "Cache-Control":"no-cache", "X-Accel-Buffering":"no",
    })
