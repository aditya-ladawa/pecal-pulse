from .workspace import tools

SALES_TOOLS = {name: getattr(tools, name) for name in (
    "get_workspace_context", "list_customers", "get_customer_evidence",
    "set_customer_filters", "select_customer", "create_chart",
    "navigate_workspace", "set_customer_tab", "set_action_limit",
    "get_opportunity_cohort", "set_opportunity_filters", "select_opportunity_cluster",
)}

def get_agent_tools():
    return SALES_TOOLS
