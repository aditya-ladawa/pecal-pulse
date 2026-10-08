"""LiveKit room bootstrap. Audio rides WebRTC, not buffered HTTP WAV uploads."""
import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from ..agents.settings import Settings
from ..agents.voice_livekit import configured

router = APIRouter(prefix="/api/voice", tags=["voice"])
logger = logging.getLogger(__name__)

class SessionRequest(BaseModel):
    session_id: UUID

@router.get("/status")
def status():
    return {"configured": configured(Settings()), "provider": "livekit", "mode": "push-to-talk"}

@router.post("/connect")
async def connect(payload: SessionRequest, request: Request):
    if not configured(Settings()):
        raise HTTPException(503, "Add LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET to the root .env.")
    try:
        connection = await request.app.state.voice.connect(str(payload.session_id))
    except ValueError as exc:
        # Only the manager's bounded capacity message is public.
        if str(exc).startswith("Close another voice session"):
            raise HTTPException(409, str(exc)) from None
        raise HTTPException(502, "Could not start LiveKit voice. Check server configuration.") from None
    except Exception as exc:
        logger.warning("LiveKit connection failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Could not connect to LiveKit. Check credentials and inference access.") from None
    return {"server_url": connection.settings.livekit_url,
            "token": connection.token(connection.identity), "agent_identity": connection.agent_identity}

@router.post("/stop")
async def stop(payload: SessionRequest, request: Request):
    await request.app.state.voice.stop(str(payload.session_id))
    return {"stopped": True}
