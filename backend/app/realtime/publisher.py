"""One envelope shared by HTTP now and the template's live transport later."""

import time, uuid


def publish(event_type: str, payload: dict, source: str = "backend") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "timestamp": int(time.time() * 1000),
        "source": {"type": source},
        "payload": payload,
    }
