import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api import voice
from backend.app.agents.voice_livekit import VoiceManager, spoken_summary

class VoiceAdapterTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI(); self.app.include_router(voice.router)
        self.app.state.voice = SimpleNamespace(connect=AsyncMock(), stop=AsyncMock())
        self.client = TestClient(self.app)

    def test_missing_configuration_never_starts_room(self):
        with patch.object(voice, "configured", return_value=False):
            self.assertFalse(self.client.get("/api/voice/status").json()["configured"])
            response = self.client.post("/api/voice/connect", json={"session_id":str(uuid4())})
        self.assertEqual(response.status_code, 503)
        self.app.state.voice.connect.assert_not_called()

    def test_connect_returns_only_scoped_participant_token(self):
        connection = SimpleNamespace(settings=SimpleNamespace(livekit_url="wss://test.livekit.cloud"),
            identity="browser-random", agent_identity="pulse-voice", token=lambda identity: "scoped-token")
        self.app.state.voice.connect.return_value = connection
        with patch.object(voice, "configured", return_value=True):
            response = self.client.post("/api/voice/connect", json={"session_id":str(uuid4())})
        self.assertEqual(response.json(), {"server_url":"wss://test.livekit.cloud", "token":"scoped-token", "agent_identity":"pulse-voice"})
        self.assertNotIn("secret", response.text)

    def test_invalid_session_does_not_reach_provider(self):
        self.assertEqual(self.client.post("/api/voice/connect", json={"session_id":"anything"}).status_code, 422)
        self.app.state.voice.connect.assert_not_called()

    def test_language_reaches_voice_manager_and_invalid_language_is_rejected(self):
        session_id = str(uuid4())
        connection = SimpleNamespace(settings=SimpleNamespace(livekit_url="wss://test"),
            identity="browser", agent_identity="pulse-voice", token=lambda identity: "scoped")
        self.app.state.voice.connect.return_value = connection
        with patch.object(voice, "configured", return_value=True):
            self.assertEqual(self.client.post("/api/voice/connect", json={"session_id":session_id,"language":"en"}).status_code, 200)
        self.app.state.voice.connect.assert_awaited_once_with(session_id, "en")
        self.assertEqual(self.client.post("/api/voice/connect", json={"session_id":session_id,"language":"fr"}).status_code, 422)
        self.app.state.voice.connect.assert_awaited_once()

    def test_provider_error_does_not_leak_details(self):
        self.app.state.voice.connect.side_effect = RuntimeError("private provider credentials")
        with patch.object(voice, "configured", return_value=True):
            response = self.client.post("/api/voice/connect", json={"session_id":str(uuid4())})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private provider", response.text)

    def test_old_buffered_gradium_routes_are_gone(self):
        self.assertEqual(self.client.post("/api/voice/transcribe", content=b"audio").status_code, 404)
        self.assertEqual(self.client.post("/api/voice/speak", json={"text":"hello"}).status_code, 404)

    def test_summary_leaves_details_in_chat(self):
        self.assertEqual(spoken_summary("**Found 12 accounts.**\n\n- Extra detail"), "Found 12 accounts.")
        self.assertLessEqual(len(spoken_summary("word " * 500)), 600)

class VoiceLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_idempotent_connect_and_stop(self):
        with patch("backend.app.agents.voice_livekit.VoiceConnection") as factory:
            factory.return_value.start = AsyncMock(); factory.return_value.close = AsyncMock()
            factory.return_value.language = "de"
            manager = VoiceManager()
            first = await manager.connect("same")
            self.assertIs(await manager.connect("same"), first)
            with self.assertRaisesRegex(ValueError, "changing its language"):
                await manager.connect("same", "en")
            factory.return_value.start.assert_awaited_once()
            await manager.stop("same"); await manager.stop("same")
            factory.return_value.close.assert_awaited_once()

    async def test_failed_start_cleans_up_and_can_retry(self):
        with patch("backend.app.agents.voice_livekit.VoiceConnection") as factory:
            factory.return_value.start = AsyncMock(side_effect=RuntimeError("failed"))
            factory.return_value.close = AsyncMock()
            manager = VoiceManager()
            with self.assertRaises(RuntimeError): await manager.connect("same")
            self.assertFalse(manager.connections)
            factory.return_value.close.assert_awaited_once()
            factory.return_value.start.side_effect = None
            await manager.connect("same")
            await manager.close()

class VoiceTurnTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import MagicMock
        from backend.app.agents.voice_livekit import VoiceConnection
        from backend.app.agents.settings import Settings
        self.handlers = {}
        self.session = MagicMock()
        self.session.start = AsyncMock(); self.session.aclose = AsyncMock()
        self.session.interrupt = AsyncMock()
        self.session.commit_user_turn = AsyncMock(return_value="Show accounts due soon")
        room = MagicMock(); room.connect = AsyncMock(); room.disconnect = AsyncMock()
        def register(name):
            def decorator(handler): self.handlers[name] = handler; return handler
            return decorator
        room.local_participant.register_rpc_method.side_effect = register
        self.patches = [patch("backend.app.agents.voice_livekit.rtc.Room", return_value=room),
                        patch("backend.app.agents.voice_livekit.AgentSession",return_value=self.session),
                        patch("backend.app.agents.voice_livekit.inference.STT"),
                        patch("backend.app.agents.voice_livekit.inference.TTS")]
        for p in self.patches: p.start()
        self.connection = VoiceConnection(Settings(livekit_api_key="test",livekit_api_secret="test-secret-for-local-unit-tests-only",livekit_url="wss://test"), str(uuid4()))
        await self.connection.start()
        self.data = lambda payload="": SimpleNamespace(caller_identity=self.connection.identity,payload=payload)

    async def asyncTearDown(self):
        await self.connection.close()
        for p in reversed(self.patches): p.stop()

    async def test_only_one_ack_and_one_final_duplicate_suppression(self):
        await self.handlers["start_turn"](self.data())
        result=json.loads(await self.handlers["end_turn"](self.data()))
        self.session.commit_user_turn.assert_awaited_once_with(skip_reply=True,transcript_timeout=4.0,stt_flush_duration=0.5)
        payload=json.dumps({"turn_id":result["turn_id"],"text":"Found 12 accounts.\n\nDetailed chart explanation."})
        await self.handlers["speak"](self.data(payload)); await self.handlers["speak"](self.data(payload))
        self.assertEqual([call.args[0] for call in self.session.say.call_args_list], ["Ich schaue mir das an.","Found 12 accounts."])

    async def test_transcript_keeps_german_words_numbers_and_punctuation(self):
        expected = "Zeige Müller: 30 Geräte, fällig am 15. Oktober."
        self.session.commit_user_turn.return_value = expected
        await self.handlers["start_turn"](self.data())
        result = json.loads(await self.handlers["end_turn"](self.data()))
        self.assertEqual(result["text"], expected)
        await self.handlers["interrupt"](self.data())
        self.assertEqual(self.session.interrupt.await_count, 2)

    async def test_english_uses_english_recognition_speech_and_acknowledgement(self):
        from backend.app.agents.voice_livekit import inference
        self.connection.language = "en"
        await self.connection.http.close()
        await self.connection.start()
        self.assertEqual(inference.STT.call_args.kwargs["language"], "en")
        self.assertEqual(inference.TTS.call_args.kwargs["language"], "en")
        await self.handlers["start_turn"](self.data())
        await self.handlers["end_turn"](self.data())
        self.assertEqual(self.session.say.call_args.args[0], "I'll take a look.")

    async def test_german_configures_both_speech_providers(self):
        from backend.app.agents.voice_livekit import inference
        self.assertEqual(inference.STT.call_args.kwargs["language"], "de")
        self.assertEqual(inference.TTS.call_args.kwargs["language"], "de")

    async def test_paused_scheduling_skips_ack_but_keeps_transcript(self):
        self.session.say.side_effect = RuntimeError("AgentSession is closing, cannot use say()")
        await self.handlers["start_turn"](self.data())
        result = json.loads(await self.handlers["end_turn"](self.data()))
        self.assertEqual(result["text"], "Show accounts due soon")
        self.session.say.assert_called_once()

    async def test_empty_transcript_cannot_trigger_ack_or_agent_command(self):
        from livekit import rtc
        self.session.commit_user_turn.return_value=" "
        await self.handlers["start_turn"](self.data())
        with self.assertRaises(rtc.RpcError): await self.handlers["end_turn"](self.data())
        self.session.say.assert_not_called()

    async def test_another_participant_cannot_control_voice(self):
        from livekit import rtc
        with self.assertRaises(rtc.RpcError): await self.handlers["start_turn"](SimpleNamespace(caller_identity="intruder"))
        self.session.clear_user_turn.assert_not_called()

    async def test_stale_final_cannot_speak_during_a_new_recording(self):
        await self.handlers["start_turn"](self.data())
        old=self.connection.turn_id
        await self.handlers["interrupt"](self.data())
        await self.handlers["start_turn"](self.data())
        await self.handlers["speak"](self.data(json.dumps({"text":"Old reply", "turn_id":old})))
        self.session.say.assert_not_called()
