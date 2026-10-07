from fastapi import APIRouter, HTTPException
from pydantic import TypeAdapter
from ..capabilities.sales import service
from ..capabilities.sales.models import (
    FollowupCreate,
    FollowupUpdate,
    UiCommand,
)
from ..realtime.publisher import publish
from ..agents.contracts import AgentChatRequest

router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "mode": "mock", "contract_version": "1"}


@router.get("/bootstrap")
def bootstrap():
    return service.bootstrap()


@router.get("/contracts")
def contracts():
    return {
        "version": "1",
        "ui_commands": TypeAdapter(UiCommand).json_schema(),
        "chat_request": AgentChatRequest.model_json_schema(),
    }


@router.post("/commands")
def command(command: UiCommand):
    if command.type == "customers.select":
        try:
            service.customer(command.payload.customer_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc))
    return publish(command.type, command.payload.model_dump(exclude_none=True), "agent")


@router.post("/followups", status_code=201)
def create_followup(request: FollowupCreate):
    try:
        return service.create_followup(request)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.patch("/followups/{task_id}")
def update_followup(task_id: str, request: FollowupUpdate):
    try:
        return service.update_followup(task_id, request.status)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
