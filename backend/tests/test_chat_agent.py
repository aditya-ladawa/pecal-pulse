import asyncio
import tempfile
import unittest
import os
from unittest.mock import patch
from pathlib import Path
from uuid import uuid4
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
import json
from backend.app.agents.contracts import AgentChatRequest, WorkspaceContext
from backend.app.agents.react_agent import agent_lifespan, ThreadBusy
from backend.app.agents.settings import Settings

class ToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = next(self.messages)
        if message.tool_calls:
            if message.content:
                yield ChatGenerationChunk(message=AIMessageChunk(content=message.content))
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[
                {"name":c["name"], "args":json.dumps(c["args"]), "id":c["id"], "index":i}
                for i,c in enumerate(message.tool_calls)]))
        else:
            for word in str(message.content).split(" "):
                yield ChatGenerationChunk(message=AIMessageChunk(content=word + " "))

def model(*messages):
    return ToolModel(messages=iter(messages))

def call(name, args=None):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": str(uuid4()), "type": "tool_call"}])

class ChatAgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = Settings(checkpoint_path=str(Path(self.temp.name) / "chat.sqlite3"), openrouter_api_key="")

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def test_spoken_progress_precedes_tool_and_final_reply(self):
        progress = call("get_workspace_context")
        progress.content = "Let me check the current page."
        async with agent_lifespan(self.settings, model(progress, AIMessage(content="Here is the result."))) as service:
            events = [event async for event in service.stream_reply(AgentChatRequest(message="Check the page"))]
        speech = [(i, event) for i, event in enumerate(events) if event["type"] == "speech"]
        tool = next(i for i, event in enumerate(events) if event["type"] == "part" and event["part"]["type"] == "tool-call")
        self.assertEqual(len(speech), 1)
        self.assertEqual(speech[0][1]["text"], "Let me check the current page.")
        self.assertLess(speech[0][0], tool)
        self.assertEqual(events[-1]["type"], "done")

    async def test_customer_shortlist_limit_preserves_total_and_rejects_unbounded_reads(self):
        async with agent_lifespan(self.settings, model(call("list_customers", {"limit": 1}), AIMessage(content="One account."),
                call("list_customers", {"limit": 10000}), AIMessage(content="Please use a smaller list."))) as service:
            first = await service.reply(AgentChatRequest(message="Show one account"))
            result = next(p["result"] for p in first["content"] if p["type"] == "tool-call")
            self.assertEqual(len(result["customers"]), 1)
            self.assertGreater(result["total"], 1)
            other = await service.reply(AgentChatRequest(message="Invalid large list"))
            part = next(p for p in other["content"] if p["type"] == "tool-call")
            self.assertTrue(part["isError"])

    async def test_dotenv_model_and_reasoning_reach_openrouter_request(self):
        from langchain_openrouter import ChatOpenRouter
        dotenv = Path(self.temp.name) / ".env"
        dotenv.write_text("LLM_MODEL=test/configured-model\nRESONING_LVL='low'\n")
        with patch.dict(os.environ):
            os.environ.pop("LLM_MODEL", None)
            os.environ.pop("RESONING_LVL", None)
            settings = Settings(_env_file=dotenv, openrouter_api_key="test",
                                checkpoint_path=str(Path(self.temp.name) / "configured.sqlite3"))
        adapters = []
        def adapter(**kwargs):
            result = ChatOpenRouter(**kwargs)
            adapters.append(result)
            return result
        with patch("backend.app.agents.react_agent.ChatOpenRouter", side_effect=adapter):
            async with agent_lifespan(settings):
                params = adapters[0]._default_params
                self.assertEqual(params["model"], "test/configured-model")
                self.assertEqual(params["reasoning"], {"effort": "low", "exclude": False})
                self.assertTrue(params["stream"])

    async def test_checkpoint_and_display_history_survive_restart_without_replaying_events(self):
        thread = uuid4()
        async with agent_lifespan(self.settings, model(call("create_chart", {"view":"activity"}), AIMessage(content="Here is the chart."))) as service:
            reply = await service.reply(AgentChatRequest(thread_id=thread, message="Chart this account", context=WorkspaceContext(customer_id="DEMO-1001")))
            self.assertEqual([e["type"] for e in reply["events"]], ["artifact.created"])
            self.assertEqual(len(reply["artifacts"][0]["labels"]), 12)
        async with agent_lifespan(self.settings, model(AIMessage(content="I remember the previous chart."))) as service:
            history = await service.history(thread)
            self.assertEqual(len(history["items"]), 2)
            self.assertNotIn("events", history)
            self.assertEqual(history["items"][1]["actions"], ["artifact.created"])
            reply = await service.reply(AgentChatRequest(thread_id=thread, message="What did we do?"))
            self.assertEqual(reply["events"], [])
            state = await service.graph.aget_state({"configurable":{"thread_id":str(thread)}})
            self.assertEqual([m.content for m in state.values["messages"] if m.type == "human"], ["Chart this account", "What did we do?"])
            self.assertEqual(len((await service.history(thread))["items"]), 4)

    async def test_fresh_selection_and_thread_isolation(self):
        first, second = uuid4(), uuid4()
        async with agent_lifespan(self.settings, model(call("get_customer_evidence"), AIMessage(content="First account."), call("get_customer_evidence"), AIMessage(content="Current account."), AIMessage(content="Separate conversation."))) as service:
            await service.reply(AgentChatRequest(thread_id=first, message="Explain", context=WorkspaceContext(customer_id="DEMO-1001")))
            await service.reply(AgentChatRequest(thread_id=first, message="Explain current", context=WorkspaceContext(customer_id="DEMO-1002")))
            state = await service.graph.aget_state({"configurable":{"thread_id":str(first)}})
            evidence = [m.content for m in state.values["messages"] if m.type == "tool"]
            self.assertIn("DEMO-1001", evidence[0])
            self.assertIn("DEMO-1002", evidence[1])
            await service.reply(AgentChatRequest(thread_id=second, message="Hello"))
            self.assertEqual(len((await service.history(second))["items"]), 2)
            self.assertEqual(len((await service.history(first))["items"]), 4)

    async def test_selection_clears_incompatible_filters_and_events_are_turn_scoped(self):
        async with agent_lifespan(self.settings, model(call("select_customer", {"customer_id":"DEMO-1002"}), AIMessage(content="Open account."), AIMessage(content="Hello."))) as service:
            reply = await service.reply(AgentChatRequest(message="Open account"))
            self.assertEqual([e["type"] for e in reply["events"]], ["customers.filters.set", "customers.select", "ui.navigate"])
            self.assertEqual(reply["events"][0]["payload"]["query"], "")
            other = await service.reply(AgentChatRequest(message="Hello"))
            self.assertEqual(other["events"], [])

    async def test_invalid_option_returns_tool_error_without_emitting_command(self):
        async with agent_lifespan(self.settings, model(call("set_customer_filters", {"industry":"Invented sector"}), AIMessage(content="That industry is unavailable."))) as service:
            reply = await service.reply(AgentChatRequest(message="Invalid filter"))
            self.assertEqual(reply["events"], [])

    async def test_busy_thread_is_rejected(self):
        thread = uuid4()
        async with agent_lifespan(self.settings, model(AIMessage(content="Hello"))) as service:
            service.active_threads.add(str(thread))
            with self.assertRaises(ThreadBusy):
                await service.reply(AgentChatRequest(thread_id=thread, message="Hello"))

    async def test_stream_emits_tokens_and_tool_status_before_completion_and_restores_parts(self):
        thread = uuid4()
        async with agent_lifespan(self.settings, model(call("get_workspace_context"), AIMessage(content="**Customers** is open."))) as service:
            events = [e async for e in service.stream_reply(AgentChatRequest(thread_id=thread, message="Check page", context=WorkspaceContext(page="customers")))]
            self.assertEqual(events[0]["type"], "start")
            self.assertEqual(events[-1]["type"], "done")
            self.assertGreater(len([e for e in events if e["type"] == "delta"]), 1)
            tools = [e for e in events if e["type"] == "part" and e["part"]["type"] == "tool-call"]
            self.assertNotIn("result", tools[0]["part"])
            self.assertIn("result", tools[-1]["part"])
            history = await service.history(thread)
            self.assertEqual(history["items"][-1]["content"], events[-1]["reply"]["content"])
            self.assertFalse(service.active_threads)

    async def test_closing_stream_releases_thread(self):
        thread = uuid4()
        async with agent_lifespan(self.settings, model(AIMessage(content="Hello."))) as service:
            stream = service.stream_reply(AgentChatRequest(thread_id=thread, message="Hello"))
            await anext(stream)
            self.assertIn(str(thread), service.active_threads)
            await stream.aclose()
            self.assertNotIn(str(thread), service.active_threads)

class ReasoningPartTests(unittest.TestCase):
    def test_provider_reasoning_remains_separate_from_markdown(self):
        from backend.app.agents.streaming import PartAccumulator
        parts = PartAccumulator()
        chunk = AIMessageChunk(content=[{"type":"reasoning", "reasoning":"Check the available evidence."}, {"type":"text", "text":"**Result**"}])
        events = parts.model_chunk("run", chunk)
        self.assertEqual([p["type"] for p in parts.parts], ["reasoning", "text"])
        self.assertEqual(parts.parts[1]["text"], "**Result**")
        self.assertEqual(len([e for e in events if e["type"] == "delta"]), 2)

    def test_no_reasoning_block_is_invented(self):
        from backend.app.agents.streaming import PartAccumulator
        parts = PartAccumulator()
        parts.model_chunk("run", AIMessageChunk(content="Hello"))
        self.assertEqual([p["type"] for p in parts.parts], ["text"])
