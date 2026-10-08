from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api.sales import router as sales_router
from .api.v2 import router as v2_router
from .api.chat import router as chat_router
from .api.voice import router as voice_router
from .agents.react_agent import agent_lifespan
from .agents.voice_livekit import VoiceManager

@asynccontextmanager
async def lifespan(app):
    async with agent_lifespan() as chat:
        app.state.chat = chat
        app.state.voice = VoiceManager()
        try:
            yield
        finally:
            await app.state.voice.close()

app = FastAPI(title="PeCal Sales Assistant", version="0.2.0", lifespan=lifespan)
app.include_router(sales_router)
app.include_router(v2_router)
app.include_router(chat_router)
app.include_router(voice_router)
