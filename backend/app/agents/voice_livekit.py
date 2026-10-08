"""LiveKit streaming transport; LangGraph remains the only reasoning/tool agent.

Manual turn RPC returns a transcript to assistant-ui's existing send-time context.
Only an immediate acknowledgement and the completed summary are spoken.
"""
import asyncio
import json
import logging
import re
from datetime import timedelta
from uuid import uuid4

import aiohttp
from livekit import api, rtc
from livekit.agents import Agent, AgentSession, TurnHandlingOptions, inference

from .settings import Settings

logger = logging.getLogger(__name__)


def spoken_summary(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S).strip()
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*#`>|]", "", text.split("\n\n", 1)[0]).strip()
    return text if len(text) <= 600 else text[:597].rsplit(" ", 1)[0] + "…"


def configured(settings: Settings) -> bool:
    return bool(settings.livekit_url and settings.livekit_api_key.get_secret_value()
                and settings.livekit_api_secret.get_secret_value())


class VoiceConnection:
    def __init__(self, settings: Settings, session_id: str):
        self.settings = settings
        self.room = rtc.Room()
        self.session_id = session_id
        self.room_name = "pulse-" + session_id
        self.identity = "browser-" + str(uuid4())
        self.agent_identity = "pulse-voice"
        self.session = None
        self.http = None
        self.listening = False
        self.committing = False
        self.turn_id = None
        self.spoken_turn = None
        self.limit_task = None
        self.closed = False

    def token(self, identity: str, agent: bool = False) -> str:
        return (api.AccessToken(self.settings.livekit_api_key.get_secret_value(),
                                self.settings.livekit_api_secret.get_secret_value())
                .with_identity(identity).with_ttl(timedelta(minutes=10))
                .with_grants(api.VideoGrants(room_join=True, room=self.room_name,
                                           can_publish=True, can_subscribe=True, agent=agent))
                .to_jwt())

    async def start(self):
        await self.room.connect(self.settings.livekit_url, self.token(self.agent_identity, True))
        self.http = aiohttp.ClientSession()
        credentials = dict(api_key=self.settings.livekit_api_key.get_secret_value(),
                           api_secret=self.settings.livekit_api_secret.get_secret_value(),
                           http_session=self.http)
        self.session = AgentSession(
            stt=inference.STT(model="deepgram/nova-3", language="multi", **credentials),
            tts=inference.TTS(model="inworld/inworld-tts-2-flash", voice="Ashley", **credentials),
            vad=None,
            turn_handling=TurnHandlingOptions(turn_detection="manual"),
            user_away_timeout=None,
        )
        await self.session.start(agent=Agent(instructions=""), room=self.room)
        self.session.input.set_audio_enabled(False)

        @self.session.on("error")
        def voice_error(event):
            # Never publish provider errors, request headers or credentials.
            message = "Speech service unavailable. Check LiveKit inference access, then try again."
            logger.warning("LiveKit speech failed (%s)", type(event.error).__name__)
            asyncio.create_task(self.room.local_participant.publish_data(
                json.dumps({"type": "voice.error", "message": message}).encode(),
                reliable=True, destination_identities=[self.identity]))

        def authorize(data):
            if data.caller_identity != self.identity or self.closed:
                raise rtc.RpcError(1500, "Voice session unavailable.")

        @self.room.local_participant.register_rpc_method("start_turn")
        async def start_turn(data):
            authorize(data)
            if self.committing:
                raise rtc.RpcError(1500, "Please wait for transcription.")
            self.session.interrupt()
            self.session.clear_user_turn()
            self.turn_id = str(uuid4())
            self.spoken_turn = None
            self.listening = True
            self.session.room_io.set_participant(data.caller_identity)
            self.session.input.set_audio_enabled(True)
            if self.limit_task:
                self.limit_task.cancel()
            self.limit_task = asyncio.create_task(self._recording_limit())
            return ""

        @self.room.local_participant.register_rpc_method("end_turn")
        async def end_turn(data):
            authorize(data)
            if not self.listening or self.committing:
                raise rtc.RpcError(1500, "No active recording.")
            self.listening = False
            self.committing = True
            # Drain the last in-flight microphone packets before closing input.
            await asyncio.sleep(0.12)
            self.session.input.set_audio_enabled(False)
            if self.limit_task:
                self.limit_task.cancel()
            try:
                committed_turn = self.turn_id
                transcript = await self.session.commit_user_turn(
                    skip_reply=True, transcript_timeout=4.0, stt_flush_duration=0.5)
                if committed_turn != self.turn_id:
                    raise rtc.RpcError(1500, "Voice request cancelled.")
                transcript = transcript.strip()
                if not transcript or len(transcript) > 2000:
                    raise rtc.RpcError(1500, "No clear speech detected. Please try again.")
                # Stream this immediately, without waiting for the LLM or a tool.
                self.session.say("I'll check that for you.", add_to_chat_ctx=False)
                return json.dumps({"text": transcript, "turn_id": self.turn_id})
            except rtc.RpcError:
                raise
            except Exception as exc:
                logger.warning("LiveKit transcription failed (%s)", type(exc).__name__)
                raise rtc.RpcError(1500, "Voice transcription failed. Check LiveKit inference access.") from None
            finally:
                self.committing = False

        @self.room.local_participant.register_rpc_method("speak")
        async def speak(data):
            authorize(data)
            try:
                payload = json.loads(data.payload)
                text = payload["text"]
                if not isinstance(text, str) or not 0 < len(text) <= 12000:
                    raise ValueError()
                turn = payload.get("turn_id")
                if turn and (turn != self.turn_id or self.spoken_turn == turn):
                    return ""  # stale/duplicate final replies never interrupt a newer turn
                if self.listening or self.committing:
                    return ""
                summary = spoken_summary(text)
                if summary:
                    if turn:
                        self.spoken_turn = turn
                    self.session.say(summary, add_to_chat_ctx=False)
                return ""
            except (ValueError, KeyError, TypeError):
                raise rtc.RpcError(1500, "Invalid spoken summary.") from None

        @self.room.local_participant.register_rpc_method("interrupt")
        async def interrupt(data):
            authorize(data)
            self.listening = False
            self.turn_id = None
            self.session.input.set_audio_enabled(False)
            self.session.interrupt()
            self.session.clear_user_turn()
            if self.limit_task:
                self.limit_task.cancel()
            return ""

    async def _recording_limit(self):
        await asyncio.sleep(45)
        self.listening = False
        self.session.input.set_audio_enabled(False)
        self.session.clear_user_turn()

    async def close(self):
        self.closed = True
        if self.limit_task:
            self.limit_task.cancel()
        try:
            if self.session:
                await self.session.aclose()
        finally:
            try:
                await self.room.disconnect()
            finally:
                if self.http:
                    await self.http.close()


class VoiceManager:
    def __init__(self):
        self.connections = {}
        self.expirations = {}
        self.lock = asyncio.Lock()

    async def connect(self, session_id: str):
        async with self.lock:
            if session_id in self.connections:
                return self.connections[session_id]
            if len(self.connections) >= 3:
                raise ValueError("Close another voice session before starting a new one.")
            connection = VoiceConnection(Settings(), session_id)
            try:
                async with asyncio.timeout(20):
                    await connection.start()
            except BaseException:
                await connection.close()
                raise
            self.connections[session_id] = connection
            # Browser crashes or a failed client join must not leave rooms alive forever.
            self.expirations[session_id] = asyncio.create_task(self._expire(session_id))

            @connection.room.on("participant_disconnected")
            def disconnected(participant):
                if participant.identity == connection.identity:
                    asyncio.create_task(self.stop(session_id))

            return connection

    async def stop(self, session_id: str):
        async with self.lock:
            connection = self.connections.pop(session_id, None)
            expiration = self.expirations.pop(session_id, None)
            if expiration and expiration is not asyncio.current_task():
                expiration.cancel()
        if connection:
            await connection.close()

    async def _expire(self, session_id):
        await asyncio.sleep(900)
        await self.stop(session_id)

    async def close(self):
        for session_id in list(self.connections):
            await self.stop(session_id)
