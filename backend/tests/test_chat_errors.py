import json
import unittest
from types import SimpleNamespace
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langgraph.errors import GraphRecursionError
from openrouter.errors import OpenRouterError, ResponseValidationError
from backend.app.agents.errors import chat_failure
from backend.app.api.chat import router

class ChatErrorsTests(unittest.TestCase):
    def test_sdk_errors_are_classified_without_leaking_provider_details(self):
        for status, expected in [(401, "credentials"), (402, "credits"), (429, "rate_limit"), (504, "provider_timeout"), (503, "provider_failure")]:
            error = OpenRouterError("secret-key private-account-text", httpx.Response(status), "secret-key")
            _, code, message = chat_failure(error)
            self.assertEqual(code, expected)
            self.assertNotIn("secret-key", message)
            self.assertNotIn("private-account-text", message)

    def test_timeout_tool_loop_and_bad_response_are_not_access_errors(self):
        self.assertEqual(chat_failure(TimeoutError())[1], "timeout")
        self.assertEqual(chat_failure(GraphRecursionError("private prompt"))[1], "tool_loop")
        error = ResponseValidationError("private response", httpx.Response(200), ValueError("secret"))
        self.assertEqual(chat_failure(error)[1], "provider_response")
        error = ValueError("OpenRouter API returned an error during streaming: private prompt (code: 429)")
        self.assertEqual(chat_failure(error)[1], "rate_limit")

    def test_stream_reports_safe_category_after_partial_progress(self):
        async def stream(payload):
            yield {"type": "speech", "id": "progress", "text": "Checking the list."}
            raise OpenRouterError("secret account data", httpx.Response(429))
        app = FastAPI()
        app.include_router(router)
        app.state.chat = SimpleNamespace(configured=True, active_threads=set(), stream_reply=stream)
        with TestClient(app) as client, self.assertLogs("backend.app.api.chat", level="WARNING") as logs:
            result = client.post("/api/chat/stream", json={"message": "Show customers"})
        events = [json.loads(frame[6:]) for frame in result.text.split("\n\n") if frame.startswith("data: ")]
        self.assertEqual(events[0]["type"], "speech")
        self.assertEqual(events[-1]["code"], "rate_limit")
        self.assertNotIn("secret", result.text)
        self.assertNotIn("secret", " ".join(logs.output))
