"""Member 1: account composition + refresh-after-correction seam (plan §5).

`refresh_after_correction` re-derives an account's actionable state after a
workflow write: stored requirements minus signal-scoped suppressions, plus
the persisted workflow. The ranking itself is Member 3's pure function and
is injected — without it the refresh still recomputes everything Member 1
owns and returns `action: None` instead of a fabricated score.
"""

import os
from collections.abc import Callable

from .service import get_customer_detail
from .workflow import get_workflow
from ...contracts import sales_v2 as v2

WORKFLOW_TODAY = os.getenv("PECAL_TODAY", "2026-10-07")


def _suppressed_ids(state: v2.AccountWorkflow, today: str) -> set[str]:
    suppressed = set()
    for record in state.suppressions:
        if record.status == "resolved":
            suppressed.add(record.reason_id)
        elif record.status == "snoozed" and record.until is not None and record.until >= today:
            suppressed.add(record.reason_id)
    return suppressed


def refresh_after_correction(
    snapshot_id: str,
    customer_id: str,
    ranking_fn: Callable | None = None,
    today: str = WORKFLOW_TODAY,
) -> dict:
    """Recompute one account's requirements/workflow/action after a correction."""
    detail = get_customer_detail(snapshot_id, customer_id)
    state = get_workflow(customer_id)
    suppressed = _suppressed_ids(state, today)
    active = [r for r in detail["requirements"] if r.id not in suppressed]
    action = None
    if ranking_fn is not None:
        action = ranking_fn(detail["profile"], active, None, [], state)
    return {
        "customer_id": customer_id,
        "requirements": detail["requirements"],
        "active_requirement_ids": [r.id for r in active],
        "suppressed_requirement_ids": sorted(suppressed),
        "workflow": state,
        "action": action,
    }
