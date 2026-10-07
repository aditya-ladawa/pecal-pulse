import json, os, sqlite3, uuid
from contextlib import contextmanager
from pathlib import Path
from .models import ChartArtifact, Dataset, Filters, FollowupCreate
from ...realtime.publisher import publish

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = json.loads((ROOT / "data/mock/workspace.json").read_text())


def customer(customer_id: str):
    found = next((c for c in FIXTURE["customers"] if c["id"] == customer_id), None)
    if found is None:
        raise ValueError("Customer not found")
    return found


@contextmanager
def connection():
    path = Path(os.getenv("PECAL_DEMO_DB", str(ROOT / "data/runtime/demo.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS followups(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
    )
    for f in FIXTURE["followups"]:
        conn.execute(
            "INSERT OR IGNORE INTO followups VALUES (?,?)", (f["id"], json.dumps(f))
        )
    conn.commit()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def list_followups():
    with connection() as conn:
        return [
            json.loads(r["payload"])
            for r in conn.execute("SELECT payload FROM followups")
        ]


def bootstrap():
    return {**FIXTURE, "followups": list_followups()}


def filter_customers(filters: Filters):
    return [
        c
        for c in FIXTURE["customers"]
        if (
            not filters.industry
            or filters.industry == "all"
            or c["industry"] == filters.industry
        )
        and (
            not filters.segment
            or filters.segment == "all"
            or c["segment"] == filters.segment
        )
        and (
            not filters.action
            or filters.action == "all"
            or c["action"] == filters.action
        )
        and (
            not filters.query
            or filters.query.lower() in (c["name"] + " " + c["id"]).lower()
        )
    ]


def industry_chart():
    labels = FIXTURE["sector_labels"]
    values = [
        sum(sum(c["forecast"]) for c in FIXTURE["customers"] if c["industry"] == s)
        for s in labels
    ]
    return ChartArtifact(
        id="industry-outlook",
        title="Next-quarter activity by industry",
        kind="bar",
        labels=labels,
        datasets=[Dataset(name="Mock forecast", values=values)],
        unit="calibrations",
    )


def create_followup(request: FollowupCreate):
    c = customer(request.customer_id)
    f = {
        **request.model_dump(),
        "id": "task-" + uuid.uuid4().hex[:12],
        "customer_name": c["name"],
        "status": "open",
        "source": "manual",
    }
    with connection() as conn:
        conn.execute("INSERT INTO followups VALUES (?,?)", (f["id"], json.dumps(f)))
    return publish("followup.created", f)


def update_followup(task_id: str, status: str):
    with connection() as conn:
        row = conn.execute(
            "SELECT payload FROM followups WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise ValueError("Follow-up not found")
        f = json.loads(row["payload"])
        f["status"] = status
        conn.execute(
            "UPDATE followups SET payload=? WHERE id=?", (json.dumps(f), task_id)
        )
    return publish("followup.updated", f)
