"""Agent writes reuse the same local workflow services as the sales UI."""
import hashlib
from datetime import date, datetime, timezone
from typing import Literal
from langchain.tools import tool, ToolRuntime
from pydantic import Field
from typing import Annotated
from ...agents.contracts import TurnContext
from ...api import v2 as api
from ...contracts import sales_v2 as v2
from .. import data
from ..data.workflow import update_owners
from ...realtime.publisher import publish
from .drafts import build_email_draft

AccountIds = Annotated[list[str], Field(min_length=1, max_length=20)]
DraftIds = Annotated[list[str], Field(min_length=1, max_length=10)]


def _accounts(runtime, ids):
    sid = runtime.context.workspace.snapshot_id
    if not sid:
        raise ValueError("Workflow actions require an integrated snapshot")
    api._require_snapshot(sid)
    ids = list(dict.fromkeys(ids))
    # Validate the entire batch before the first write.
    for cid in ids:
        data.get_customer_detail(sid, cid)
    return sid, ids


def _record(runtime, event):
    runtime.context.events.append(event)
    runtime.context.workspace.page_snapshot = None
    return event


@tool
def assign_accounts(customer_ids: AccountIds, owner: str, runtime: ToolRuntime[TurnContext]) -> dict:
    """Assign 1–20 explicitly selected accounts to the user-specified teammate/team (e.g. Team A). Use IDs returned by account/cohort tools. Persists locally and refreshes the page; no CRM write. Never assume assignment covers a whole filtered cohort."""
    runtime.context.consume()
    sid, ids = _accounts(runtime, customer_ids)
    update_owners(ids, owner)
    for cid in ids:
        data.refresh_after_correction(sid, cid)
    event = publish("accounts.assigned", {"customer_ids":ids, "owner":owner.strip()}, "agent")
    _record(runtime, event)
    return {"status":"saved", "assigned_count":len(ids), "customer_ids":ids, "owner":owner.strip(), "snapshot_id":sid}


@tool
def draft_followup_emails(customer_ids: DraftIds, runtime: ToolRuntime[TurnContext], owner: str | None = None,
    due_date: str | None = None, language: Literal["en", "de"] = "en") -> dict:
    """Create AND SAVE individual evidence-backed email drafts as local Follow-ups for 1–10 accounts. Uses active Dashboard due-window settings when on Dashboard. No email is sent. Due date is the internal review date: defaults to today's workspace date; owner defaults to account owner or Unassigned. Identical requests reuse the saved task. To view them call set_workspace_view(customer_view='follow-ups')."""
    runtime.context.consume()
    sid, ids = _accounts(runtime, customer_ids)
    due = due_date or runtime.context.workspace.current_date or date.today().isoformat()
    date.fromisoformat(due)
    w = runtime.context.workspace
    scope = {"window_days":w.opportunity_filters.window_days, "include_inferred":w.opportunity_filters.include_inferred,
             "include_past_due":w.opportunity_filters.include_past_due} if w.page == "dashboard" else {}
    requests = []
    for cid in ids:
        detail = api.customer_detail(cid, sid, **scope)
        draft = build_email_draft(detail, language)
        assigned = owner if owner is not None else detail["workflow"]["account_owner"] or "Unassigned"
        key = hashlib.sha256(f"{sid}|{cid}|{assigned}|{due}|{draft.model_dump_json()}".encode()).hexdigest()
        requests.append(v2.FollowupCreateV2(customer_id=cid, owner=assigned, due_date=due,
            note="Review the customer-specific email draft, confirm current timing and team activity, then choose the next step.",
            outcome="Timing to confirm", reason_ids=draft.reason_ids, email_draft=draft, request_key=key))
    tasks = []
    for request in requests:
        event = api.create_followup(request, sid)
        _record(runtime, event)
        tasks.append(event["payload"])
    return {"status":"saved_as_drafts", "count":len(tasks), "sent":False, "followups":tasks}


@tool
def record_followup(customer_id: str, owner: str, due_date: str, note: str, runtime: ToolRuntime[TurnContext],
    outcome: Literal["Timing to confirm", "Timing changed", "Need confirmed", "Not applicable", "Equipment retired"] = "Timing to confirm") -> dict:
    """Save a local next step with user-supplied owner, date and note. Outcomes are customer-confirmed facts: do not claim Need confirmed or retirement from a prediction."""
    runtime.context.consume()
    sid, _ = _accounts(runtime, [customer_id])
    event = api.create_followup(v2.FollowupCreateV2(customer_id=customer_id,owner=owner,due_date=due_date,note=note,outcome=outcome),sid)
    _record(runtime, event)
    return {"status":"saved", "followup":event["payload"]}


@tool
def list_followups(runtime: ToolRuntime[TurnContext], customer_id: str | None = None, owner: str | None = None,
    status: Literal["all", "open", "done"] = "all") -> dict:
    """Read saved follow-ups/email drafts; optional account, owner and status filters. Returns at most 50 tasks plus the full matching total."""
    runtime.context.consume()
    sid = runtime.context.workspace.snapshot_id
    if not sid:
        raise ValueError("Follow-up tools require an integrated snapshot")
    rows = api.list_followups(sid)["items"]
    rows = [r for r in rows if (customer_id is None or r["customer_id"] == customer_id)
        and (owner is None or r["owner"] == owner) and (status == "all" or r["status"] == status)]
    return {"total":len(rows), "items":rows[:50]}


@tool
def set_followup_status(task_id: str, status: Literal["open", "done"], runtime: ToolRuntime[TurnContext]) -> dict:
    """Complete/reopen a known local task. Completion does not prove an email was sent or that a calibration need was resolved."""
    runtime.context.consume()
    sid = runtime.context.workspace.snapshot_id
    if not sid or task_id not in {r["id"] for r in api.list_followups(sid)["items"]}:
        raise ValueError("Unknown follow-up in the active snapshot")
    from ..sales.models import FollowupUpdate
    event = api.update_followup(task_id, FollowupUpdate(status=status))
    _record(runtime, event)
    return {"status":"saved", "followup":event["payload"]}


@tool
def update_customer_checks(customer_id: str, runtime: ToolRuntime[TurnContext],
    quotation_order: Literal["unknown", "reported_none", "in_progress"] | None = None,
    recent_contact: Literal["unknown", "checked"] | None = None,
    contact_details: Literal["unknown", "supplied"] | None = None) -> dict:
    """Record ONLY explicit user-confirmed team checks. Unknown is not outreach-ready. Never mark no quotation/contact details from missing historical data."""
    runtime.context.consume()
    sid, _ = _accounts(runtime, [customer_id])
    patch = {k:v for k,v in {"quotation_order":quotation_order,"recent_contact":recent_contact,"contact_details":contact_details}.items() if v is not None}
    if not patch:
        raise ValueError("Supply at least one confirmed check")
    event = api.update_workflow(customer_id,v2.WorkflowPatch(checks=v2.WorkflowPatchChecks(**patch,checked_by="Sales assistant · user reported")),sid)
    _record(runtime,event)
    return {"status":"saved", "customer_id":customer_id, "checks":event["payload"]["workflow"]["checks"]}


@tool
def update_calibration_reason(customer_id: str, reason_id: str, status: Literal["snoozed", "resolved"], note: str,
    runtime: ToolRuntime[TurnContext], until: str | None = None) -> dict:
    """Snooze one exact calibration reason until YYYY-MM-DD, or mark it not applicable/resolved using an explicitly user-reported explanation. Do not suppress an entire account. Get exact reason IDs from customer evidence first."""
    runtime.context.consume()
    sid, _ = _accounts(runtime, [customer_id])
    detail = api.customer_detail(customer_id,sid)
    if reason_id not in {r["id"] for r in (detail.get("action") or {}).get("reasons",[]) if r["type"] == "upcoming"}:
        raise ValueError("Choose an active calibration batch reason for this customer")
    if until:
        date.fromisoformat(until)
    suppression = v2.SuppressionRecord(reason_id=reason_id,status=status,until=until,note=note,updated_at=datetime.now(timezone.utc).isoformat())
    event = api.update_workflow(customer_id,v2.WorkflowPatch(suppression=suppression),sid)
    _record(runtime,event)
    return {"status":"saved", "customer_id":customer_id, "reason_id":reason_id}
