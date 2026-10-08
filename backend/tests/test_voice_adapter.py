import io
import unittest
import wave
from unittest.mock import AsyncMock, patch
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from backend.app.api import voice

def wav(seconds=1):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(24000)
        output.writeframes(b"\0\0" * int(24000 * seconds))
    return buf.getvalue()

class VoiceAdapterTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI(); app.include_router(voice.router)
        self.client = TestClient(app)

    def test_transcription_joins_segments_without_running_agent(self):
        upstream = AsyncMock(return_value=httpx.Response(200, text='{"type":"text","text":"Show customers"}\n{"type":"end_text"}\n{"type":"text","text":"due soon"}\n'))
        with patch.object(voice, "upstream", upstream):
            result = self.client.post("/api/voice/transcribe", content=wav())
        self.assertEqual(result.json(), {"text":"Show customers due soon"})
        self.assertEqual(upstream.call_args.args[0], "asr")

    def test_invalid_and_overlong_recordings_never_reach_provider(self):
        with patch.object(voice, "upstream", AsyncMock()) as upstream:
            for audio in (b"not wav", wav(46)):
                self.assertEqual(self.client.post("/api/voice/transcribe", content=audio).status_code, 400)
            self.assertEqual(self.client.post("/api/voice/transcribe", content=b"x" * (voice.MAX_AUDIO+1)).status_code, 413)
            upstream.assert_not_called()

    def test_silence_does_not_become_a_user_command(self):
        with patch.object(voice, "upstream", AsyncMock(return_value=httpx.Response(200, text='{"type":"end_of_stream"}'))):
            self.assertEqual(self.client.post("/api/voice/transcribe", content=wav()).status_code, 422)

    def test_partial_transcript_is_not_executed_on_provider_error(self):
        text='{"type":"text","text":"Assign all accounts"}\n{"type":"error","message":"private provider detail"}'
        with patch.object(voice, "upstream", AsyncMock(return_value=httpx.Response(200, text=text))):
            result = self.client.post("/api/voice/transcribe", content=wav())
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("private provider detail", result.text)

    def test_speech_only_reads_summary_not_long_details(self):
        upstream = AsyncMock(return_value=httpx.Response(200, content=wav()))
        with patch.object(voice, "upstream", upstream):
            response = self.client.post("/api/voice/speak", json={"text":"**Found 12 accounts.**\n\n- Extra detail with [source](https://example.com)."})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(upstream.call_args.kwargs["json"]["text"], "Found 12 accounts.")
        self.assertLessEqual(len(voice.spoken_summary("word " * 500)), 600)

    def test_missing_key_is_visible_without_exposing_credentials(self):
        with patch.object(voice, "Settings") as settings:
            settings.return_value.gradium_api_key = SecretStr("")
            self.assertFalse(self.client.get("/api/voice/status").json()["configured"])
            response = self.client.post("/api/voice/speak", json={"text":"Hello"})
        self.assertEqual(response.status_code, 503)

    def test_streaming_wav_header_is_finalized_for_browser_decoding(self):
        audio = bytearray(wav())
        audio[4:8] = b"\xff" * 4
        audio[40:44] = b"\xff" * 4
        result = voice.finalized_wav(bytes(audio))
        voice.validate_audio(result)
        with wave.open(io.BytesIO(result), "rb") as stream:
            self.assertEqual(stream.getnframes(), 24000)

if __name__ == "__main__": unittest.main()
