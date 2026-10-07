"""Member 1: local workflow persistence (plan §4E).

SQLite tables owned here: workflow_state (owner, manual checks,
signal-scoped suppressions, audit trail). Follow-ups share the existing
followups table with the v1 service (same keys plus reason_ids), so the
mock UI keeps working. Writes commit before any event is published.
Workflow facts are manually supplied; the SQL source is never written.
"""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ...contracts import sales_v2 as v2
from ...realtime.publisher import publish

ROOT = Path(__file__).resolve().parents[4]


def _db_path() -> Path:
    return Path(os.getenv("PECAL_DEMO_DB", str(ROOT / "data/runtime/demo.sqlite3")))


@contextmanager
def _connection():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS followups(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS workflow_state(customer_id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
    )
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blank_workflow() -> dict:
    return {
        "account_owner": None,
        "checks": {
            "quotation_order": "unknown",
            "recent_contact": "unknown",
            "contact_details": "unknown",
            "checked_at": None,
            "checked_by": None,
        },
        "suppressions": [],
        "followups": [],
        "audit": [],
    }


def _load_state(conn, customer_id: str) -> dict:
    row = conn.execute(
        "SELECT payload FROM workflow_state WHERE customer_id=?", (customer_id,)
    ).fetchone()
    if row is None:
        return _blank_workflow()
    state = json.loads(row["payload"])
    state.setdefault("audit", [])
    return state


def _save_state(conn, customer_id: str, state: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO workflow_state VALUES (?,?)",
        (customer_id, json.dumps(state)),
    )


def _followups_for(conn, customer_id: str) -> list[dict]:
    rows = conn.execute("SELECT payload FROM followups").fetchall()
    return [
        payload
        for row in rows
        for payload in [json.loads(row["payload"])]
        if payload.get("customer_id") == customer_id
    ]


def get_workflow(customer_id: str) -> v2.AccountWorkflow:
    with _connection() as conn:
        state = _load_state(conn, customer_id)
        state["followups"] = _followups_for(conn, customer_id)
    state.pop("audit", None)
    return v2.AccountWorkflow.model_validate(state)


def update_checks(
    customer_id: str,
    patch: v2.WorkflowPatchChecks,
    checked_by: str | None = None,
) -> v2.AccountWorkflow:
    with _connection() as conn:
        state = _load_state(conn, customer_id)
        changes = patch.model_dump(exclude_none=True, exclude={"checked_by"})
        state["checks"].update(changes)
        state["checks"]["checked_at"] = _now()
        state["checks"]["checked_by"] = checked_by or patch.checked_by
        state["audit"].append(
            {"at": _now(), "by": checked_by or patch.checked_by, "change": {"checks": changes}}
        )
        _save_state(conn, customer_id, state)
        state["followups"] = _followups_for(conn, customer_id)
    state.pop("audit", None)
    return v2.AccountWorkflow.model_validate(state)


def add_suppression(
    customer_id: str,
    suppression: v2.SuppressionRecord,
    known_reason_ids: set[str],
    updated_by: str | None = None,
) -> v2.AccountWorkflow:
    """Snooze/resolve exactly one reason; unrelated reasons are untouched."""
    if suppression.reason_id not in known_reason_ids:
        raise ValueError(f"Unknown reason: {suppression.reason_id}")
    with _connection() as conn:
        state = _load_state(conn, customer_id)
        record = suppression.model_dump()
        state["suppressions"] = [
            s for s in state["suppressions"] if s["reason_id"] != suppression.reason_id
        ] + [record]
        state["audit"].append(
            {"at": _now(), "by": updated_by, "change": {"suppression": record}}
        )
        _save_state(conn, customer_id, state)
        state["followups"] = _followups_for(conn, customer_id)
    state.pop("audit", None)
    return v2.AccountWorkflow.model_validate(state)


def create_followup_v2(request: v2.FollowupCreateV2, customer_name: str) -> dict:
    followup = v2.Followup.model_validate(
        {
            **request.model_dump(exclude={"reason_ids"}),
            "id": "task-" + uuid.uuid4().hex[:12],
            "customer_name": customer_name,
            "status": "open",
            "source": "manual",
        }
    )
    with _connection() as conn:
        conn.execute(
            "INSERT INTO followups VALUES (?,?)",
            (followup.id, followup.model_dump_json()),
        )
        if request.reason_ids:
            state = _load_state(conn, request.customer_id)
            state["audit"].append(
                {
                    "at": _now(),
                    "by": request.owner,
                    "change": {
                        "followup_id": followup.id,
                        "linked_reason_ids": list(request.reason_ids),
                    },
                }
            )
            _save_state(conn, request.customer_id, state)
    return publish("followup.created", followup.model_dump(), "backend")


def update_followup_status(task_id: str, status: str) -> dict:
    with _connection() as conn:
        row = conn.execute(
            "SELECT payload FROM followups WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Follow-up not found")
        payload = json.loads(row["payload"])
        payload["status"] = status
        followup = v2.Followup.model_validate(payload)
        conn.execute(
            "UPDATE followups SET payload=? WHERE id=?",
            (followup.model_dump_json(), task_id),
        )
    return publish("followup.updated", followup.model_dump(), "backend")


def list_followups_v2() -> list[v2.Followup]:
    with _connection() as conn:
        rows = conn.execute("SELECT payload FROM followups ORDER BY payload").fetchall()
    items = []
    for row in rows:
        try:
            items.append(v2.Followup.model_validate(json.loads(row["payload"])))
        except ValueError:
            continue  # skip legacy rows that predate the v2 schema
    return items
