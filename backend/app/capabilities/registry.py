from .sales import tools

SALES_TOOLS = {
    name: getattr(tools, name)
    for name in [
        "get_customer_evidence",
        "set_customer_filters",
        "select_customer",
        "create_industry_chart",
        "navigate_workspace",
    ]
}


def get_agent_tools():
    return SALES_TOOLS
