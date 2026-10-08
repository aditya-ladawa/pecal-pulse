from .workspace import tools
from .workspace import workflow_tools

SALES_TOOLS = {name: getattr(tools, name) for name in (
    "get_workspace_context", "list_customers", "get_customer_evidence",
    "set_customer_filters", "select_customer", "create_chart",
    "navigate_workspace", "set_customer_tab", "set_action_limit",
    "get_opportunity_cohort", "set_opportunity_filters", "select_opportunity_cluster",
    "open_customer_preview", "set_workspace_view",
)}
SALES_TOOLS.update({name: getattr(workflow_tools, name) for name in (
    "assign_accounts", "draft_followup_emails", "record_followup", "list_followups",
    "set_followup_status", "update_customer_checks", "update_calibration_reason",
)})

def get_agent_tools():
    return SALES_TOOLS
