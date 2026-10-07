"""Thin callable boundary for the template agent's future sales capability."""

from . import service
from .models import Filters
from ...realtime.publisher import publish


def get_customer_evidence(customer_id: str):
    return service.customer(customer_id)


def set_customer_filters(**filters):
    values = Filters(**filters).model_dump(exclude_none=True)
    return publish("customers.filters.set", values, "agent")


def select_customer(customer_id: str):
    service.customer(customer_id)
    return publish("customers.select", {"customer_id": customer_id}, "agent")


def create_industry_chart():
    return publish("artifact.created", service.industry_chart().model_dump(), "agent")


def navigate_workspace(page: str):
    from .models import NavigatePayload

    return publish("ui.navigate", NavigatePayload(page=page).model_dump(), "agent")
