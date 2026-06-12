"""LangGraph orchestrator.

ingest → classify → ⤜ Send() map-reduce: one remediate branch PER incident ⤛
        → fan-out: notify_slack + create_jira + cookbook → END

Each incident gets its own parallel remediation branch (LangGraph Send API);
the joins are implicit — notify/jira/cookbook wait for every branch. Every
node appends human-readable trace events so the UI can stream "which agent
is doing what" live.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from . import rag, vision
from .agents.classifier import classify
from .agents.cookbook import synthesize
from .agents.remediation import remediate
from .agents.research import investigate
from .ingest import ingest_log
from .integrations.jira import create_ticket
from .integrations.slack import notify
from .schemas import (
    ClassificationResult,
    Incident,
    LogExtract,
    NotificationResult,
    RemediationPlan,
    TicketResult,
)


def _append(left: list, right: list) -> list:
    return left + right


def _status(message: str) -> None:
    """Emit a live in-progress line to the UI (no-op outside custom streaming)."""
    try:
        get_stream_writer()(message)
    except Exception:
        pass


class SuiteState(TypedDict, total=False):
    log_path: str
    image_path: str | None
    dashboard_observations: str | None
    extract: LogExtract
    classification: ClassificationResult
    plans: Annotated[list[RemediationPlan], _append]
    notifications: list[NotificationResult]
    tickets: list[TicketResult]
    cookbook: str
    trace: Annotated[list[str], _append]


class RemediateBranch(TypedDict):
    """Input payload of one Send() branch — a single incident."""

    incident: Incident


def node_ingest(state: SuiteState) -> dict:
    _status("⚙ LangGraph orchestrator: run started")
    _status("📥 Ingest: parsing log in the side-channel (no LLM)…")
    extract = ingest_log(state["log_path"])
    update: dict = {"extract": extract}
    lines = [
        f"📥 Ingest: {extract.source_file} — {extract.total_lines} lines → "
        f"{len(extract.error_lines)} deduplicated error/warn lines "
        f"(side-channel: raw log never enters the LLM)"
    ]
    if state.get("image_path"):
        _status("👁 Vision agent: analyzing image…")
        _status("👁 Extracting text, metrics and alert states from the screenshot (vision LLM)…")
        observations = vision.observe_dashboard(state["image_path"])
        update["dashboard_observations"] = observations
        lines.append(
            f"👁 Vision: screenshot analysed → {len(observations.splitlines())} observation lines"
        )
    update["trace"] = lines
    return update


def node_classify(state: SuiteState) -> dict:
    _status("🔎 Classifier agent: LangChain structured-output call (Pydantic schema)…")
    result = classify(state["extract"], state.get("dashboard_observations"))
    # Guard: dedupe incidents by id (models occasionally emit one per repeat line)
    seen: set[str] = set()
    result.incidents = [
        i for i in result.incidents if not (i.incident_id in seen or seen.add(i.incident_id))
    ]
    lines = [f"🔎 Classifier: found {len(result.incidents)} incident(s)"] + [
        f"   · [{i.severity.value.upper()}] {i.title} ({i.affected_component})"
        for i in result.incidents
    ]
    return {"classification": result, "trace": lines}


def fan_out_remediation(state: SuiteState):
    """Send API map: spawn one remediation branch per classified incident."""
    incidents = state["classification"].incidents
    if not incidents:
        return "cookbook"
    return [Send("remediate_one", {"incident": inc}) for inc in incidents]


def node_remediate_one(branch: RemediateBranch) -> dict:
    incident = branch["incident"]
    _status(f"📚 RAG: querying runbook vector index for {incident.incident_id}…")
    citations = rag.retrieve(incident)
    _status(f"🌐 Researching via Tavily: {incident.incident_id}…")
    web_findings = investigate(incident)
    _status(f"🛠 Remediation agent: drafting guarded plan for {incident.incident_id}…")
    plan = remediate(incident, citations, web_findings)

    lines = [
        f"🛠 Remediation[{incident.incident_id}]: {len(plan.steps)} steps"
        + (" ⚠ ESCALATE" if plan.escalate else "")
    ]
    if citations:
        for c in citations:
            lines.append(
                f"   📚 RAG: {c.source} → {c.section} (similarity {c.score})"
            )
    else:
        lines.append("   📚 RAG: no runbook above threshold — first principles")
    if web_findings:
        for w in web_findings:
            lines.append(f"   🌐 Research: {w.title} ({w.url})")
    else:
        lines.append("   🌐 Research: skipped (no TAVILY_API_KEY) or no results")
    return {"plans": [plan], "trace": lines}


def node_notify(state: SuiteState) -> dict:
    plans_by_id = {p.incident_id: p for p in state["plans"]}
    results, lines = [], []
    for incident in state["classification"].incidents:
        plan = plans_by_id.get(incident.incident_id)
        if not plan:
            continue
        _status(f"💬 Posting to Slack: {incident.incident_id}…")
        r = notify(incident, plan)
        results.append(r)
        lines.append(
            f"💬 Slack: {incident.incident_id} → "
            + ("delivered" if r.delivered else f"skipped ({r.skipped_reason})")
        )
    return {"notifications": results, "trace": lines}


def node_jira(state: SuiteState) -> dict:
    plans_by_id = {p.incident_id: p for p in state["plans"]}
    results, lines = [], []
    for incident in state["classification"].incidents:
        plan = plans_by_id.get(incident.incident_id)
        if not plan:
            continue
        _status(f"🎫 Creating JIRA ticket: {incident.incident_id}…")
        r = create_ticket(incident, plan)
        results.append(r)
        lines.append(
            f"🎫 JIRA: {incident.incident_id} → "
            + (r.ticket_key if r.ticket_key else f"skipped ({r.skipped_reason})")
        )
    return {"tickets": results, "trace": lines}


def node_cookbook(state: SuiteState) -> dict:
    _status("📕 Cookbook synthesizer: writing the on-call checklist (LLM)…")
    doc = synthesize(state["classification"], state.get("plans", []))
    return {"cookbook": doc, "trace": ["📕 Cookbook: checklist synthesized"]}


def build_graph():
    g = StateGraph(SuiteState)
    g.add_node("ingest", node_ingest)
    g.add_node("classify", node_classify)
    g.add_node("remediate_one", node_remediate_one)
    g.add_node("notify_slack", node_notify)
    g.add_node("create_jira", node_jira)
    g.add_node("cookbook", node_cookbook)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    # map-reduce: one parallel branch per incident, joined implicitly below
    g.add_conditional_edges(
        "classify", fan_out_remediation, ["remediate_one", "cookbook"]
    )
    g.add_edge("remediate_one", "notify_slack")
    g.add_edge("remediate_one", "create_jira")
    g.add_edge("remediate_one", "cookbook")
    g.add_edge("notify_slack", END)
    g.add_edge("create_jira", END)
    g.add_edge("cookbook", END)
    return g.compile()
