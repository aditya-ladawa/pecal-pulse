"""Bounded push-to-talk adapter. Speech never bypasses the existing chat agent."""
import io
import json
import re
import wave
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from ..agents.settings import Settings

router = APIRouter(prefix="/api/voice", tags=["voice"])
MAX_AUDIO = 5_000_000

def validate_audio(audio: bytes) -> None:
    try:
        with wave.open(io.BytesIO(audio), "rb") as wav:
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                or not 8000 <= wav.getframerate() <= 48000
                or not 0 < wav.getnframes() / wav.getframerate() <= 45):
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(400, "Record up to 45 seconds of mono audio.") from None

def spoken_summary(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S).strip()
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    paragraph = text.split("\n\n", 1)[0]
    paragraph = re.sub(r"[*#`>|]", "", paragraph).strip()
    if len(paragraph) > 600:
        paragraph = paragraph[:597].rsplit(" ", 1)[0] + "…"
    return paragraph

def finalized_wav(audio: bytes) -> bytes:
    """Gradium WAV streams may use an unknown-length header; finalize for Web Audio."""
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
            frames = source.readframes(source.getnframes())
        output = io.BytesIO()
        with wave.open(output, "wb") as target:
            target.setnchannels(channels); target.setsampwidth(width); target.setframerate(rate)
            target.writeframes(frames)
        return output.getvalue()
    except (wave.Error, EOFError):
        raise HTTPException(502, "Could not play this voice response. Please try again.") from None

async def upstream(path: str, **kwargs) -> httpx.Response:
    key = Settings().gradium_api_key.get_secret_value()
    if not key:
        raise HTTPException(503, "Add GRADIUM_API_KEY to the root .env to enable voice.")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post("https://api.gradium.ai/api/post/speech/" + path,
                headers={"x-api-key": key, **kwargs.pop("headers", {})}, **kwargs)
        response.raise_for_status()
        return response
    except httpx.HTTPStatusError as exc:
        message = "Voice provider unavailable. Please try again."
        if exc.response.status_code in (401, 403):
            message = "Gradium rejected the voice credentials. Check the root .env."
        elif exc.response.status_code == 429:
            message = "Voice limit reached. Please try again shortly."
        raise HTTPException(502, message) from None
    except httpx.HTTPError:
        raise HTTPException(502, "Voice connection failed. Please try again.") from None

@router.get("/status")
def status():
    return {"configured": bool(Settings().gradium_api_key.get_secret_value()), "mode": "push-to-talk"}

@router.post("/transcribe")
async def transcribe(request: Request):
    audio = bytearray()
    async for chunk in request.stream():
        audio.extend(chunk)
        if len(audio) > MAX_AUDIO:
            raise HTTPException(413, "Recording is too large. Keep it under 45 seconds.")
    validate_audio(bytes(audio))
    response = await upstream("asr", content=bytes(audio), headers={"Content-Type": "audio/wav"},
        params={"json_config": json.dumps({"language": "any"})})
    parts = []
    try:
        for line in response.text.splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if item.get("type") == "error":
                raise ValueError()
            if item.get("type") == "text":
                parts.append(item["text"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "Could not transcribe this recording. Please try again.") from None
    text = " ".join(parts).strip()
    if not text:
        raise HTTPException(422, "No speech detected. Tap the orb and try again.")
    if len(text) > 2000:
        raise HTTPException(422, "Please use a shorter voice request.")
    return {"text": text}

class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)

@router.post("/speak")
async def speak(payload: SpeakRequest):
    text = spoken_summary(payload.text)
    if not text:
        raise HTTPException(422, "No spoken summary available.")
    response = await upstream("tts", json={"text": text, "voice_id": Settings().gradium_voice_id,
        "output_format": "wav", "only_audio": True})
    return Response(finalized_wav(response.content), media_type="audio/wav", headers={"Cache-Control": "no-store"})
