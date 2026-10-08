"""Translate LangChain events into assistant-ui message parts without inventing reasoning."""
import json

class PartAccumulator:
    def __init__(self):
        self.parts = []
        self.indices = {}

    def delta(self, key, kind, text):
        if not text:
            return []
        events = []
        if key not in self.indices:
            self.indices[key] = len(self.parts)
            part = {"type": kind, "text": ""}
            self.parts.append(part)
            events.append({"type": "part", "index": len(self.parts)-1, "part": dict(part)})
        index = self.indices[key]
        self.parts[index]["text"] += text
        events.append({"type": "delta", "index": index, "delta": text})
        return events

    def model_chunk(self, run_id, chunk):
        events = []
        # The provider-specific adapter normalizes publicly returned reasoning.
        for block in chunk.content_blocks:
            kind = block.get("type")
            if kind == "text":
                events.extend(self.delta((run_id, "text"), "text", block.get("text", "")))
            elif kind == "reasoning":
                events.extend(self.delta((run_id, "reasoning"), "reasoning", block.get("reasoning", "")))
        return events

    def tool_start(self, run_id, name, args):
        index = len(self.parts)
        self.indices[(run_id, "tool")] = index
        part = {"type":"tool-call", "toolCallId":run_id, "toolName":name,
                "args": args if isinstance(args, dict) else {},
                "argsText": json.dumps(args, ensure_ascii=False),
                "status": {"type": "running"}}
        self.parts.append(part)
        return {"type":"part", "index":index, "part":dict(part)}

    def tool_end(self, run_id, output):
        index = self.indices.get((run_id, "tool"))
        if index is None:
            return None
        if hasattr(output, "content"):
            value = output.content
            error = getattr(output, "status", "success") == "error"
        else:
            value, error = output, False
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        part = self.parts[index]
        part.update(result=value, isError=error, status={"type": "complete"})
        return {"type":"part", "index":index, "part":dict(part)}
