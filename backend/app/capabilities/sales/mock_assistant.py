"""Explicitly scripted UI demo. Replace orchestration, keep the tool boundary."""

from ..registry import get_agent_tools
from .models import ChatRequest
from . import service


def reply(request: ChatRequest):
    tools = get_agent_tools()
    text = request.message.lower()
    events = []
    artifacts = []
    if any(w in text for w in ["chart", "diagram", "plot"]):
        event = tools["create_industry_chart"]()
        events.append(event)
        artifacts.append(event["payload"])
        answer = "I added a next-quarter industry chart to your dashboard. These are synthetic calibration counts for the UI demo, not trained forecasts."
    elif any(
        w in text
        for w in ["automotive", "medical", "manufacturing", "electronics", "aerospace"]
    ):
        sector = next(s for s in service.FIXTURE["sector_labels"] if s.lower() in text)
        events.extend(
            [
                tools["set_customer_filters"](
                    industry=sector, segment="all", action="all", query=""
                ),
                tools["navigate_workspace"]("customers"),
            ]
        )
        answer = f"I opened Customers and filtered to **{sector}**. Select an account to see its history, opportunity reasons and mock forecast."
    elif any(w in text for w in ["inactive", "inactivity", "retention", "churn"]):
        events.extend(
            [
                tools["set_customer_filters"](
                    industry="all", segment="all", action="inactivity", query=""
                ),
                tools["navigate_workspace"]("customers"),
            ]
        )
        answer = "I filtered the customer list to unusual inactivity. Treat these as reasons to investigate delayed batches or changed schedules, not confirmed churn."
    elif any(w in text for w in ["prepare", "conversation", "why", "explain"]):
        c = tools["get_customer_evidence"](request.context.customer_id or "DEMO-1001")
        answer = f"**{c['name']} — conversation brief**\n\n**Recorded demo signal:** {c['reason']}\n\n**Ask:** Has the batch timing changed? Which instruments need attention? Is a quotation already being prepared?\n\n**Unknown:** Live order status, contact details and commercial value.\n\nThe evidence in this preview is synthetic."
        events.extend(
            [
                tools["select_customer"](c["id"]),
                tools["navigate_workspace"]("customers"),
            ]
        )
    elif any(w in text for w in ["follow", "task"]):
        events.append(tools["navigate_workspace"]("follow-ups"))
        answer = "I opened Follow-ups. You can assign the next step, choose a date and mark an action complete. Demo workflow changes are saved in the local Python backend."
    elif any(w in text for w in ["customer", "opportun", "next", "contact", "review"]):
        events.extend(
            [
                tools["set_customer_filters"](
                    industry="all", segment="all", action="all", query=""
                ),
                tools["select_customer"]("DEMO-1001"),
                tools["navigate_workspace"]("customers"),
            ]
        )
        answer = "Start with **Nordwerk Precision**: its demo record shows 28 instruments approaching a calibration window. Confirm timing before preparing a quotation. I opened the account evidence."
    else:
        answer = "This is a scripted preview of the sales assistant. Try **Show automotive customers**, **Create an industry chart**, **Prepare a conversation**, or **Open follow-ups**. A language model and live SQL data will be connected after the UI review."
    return {
        "message": answer,
        "events": events,
        "artifacts": artifacts,
        "mode": "scripted_mock",
    }
