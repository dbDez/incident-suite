"""LangGraph orchestrator.

ingest → classify → (per incident) remediate → notify_slack + create_jira
                                   ↘ all plans → synthesize_cookbook

Every node appends a human-readable trace event so the UI can stream
"which agent is doing what" live.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents.classifier import classify
from .agents.cookbook import synthesize
from .agents.remediation import remediate
from .ingest import ingest_log
from .integrations.jira import create_ticket
from .integrations.slack import notify
from .schemas import (
    ClassificationResult,
    LogExtract,
    NotificationResult,
    RemediationPlan,
    TicketResult,
)


def _append(left: list, right: list) -> list:
    return left + right


class SuiteState(TypedDict, total=False):
    log_path: str
    extract: LogExtract
    classification: ClassificationResult
    plans: list[RemediationPlan]
    notifications: list[NotificationResult]
    tickets: list[TicketResult]
    cookbook: str
    trace: Annotated[list[str], _append]


def node_ingest(state: SuiteState) -> dict:
    extract = ingest_log(state["log_path"])
    return {
        "extract": extract,
        "trace": [
            f"📥 Ingest: {extract.source_file} — {extract.total_lines} lines → "
            f"{len(extract.error_lines)} deduplicated error/warn lines "
            f"(side-channel: raw log never enters the LLM)"
        ],
    }


def node_classify(state: SuiteState) -> dict:
    result = classify(state["extract"])
    lines = [
        f"🔎 Classifier: found {len(result.incidents)} incident(s)"
    ] + [
        f"   · [{i.severity.value.upper()}] {i.title} ({i.affected_component})"
        for i in result.incidents
    ]
    return {"classification": result, "trace": lines}


def node_remediate(state: SuiteState) -> dict:
    plans, lines = [], []
    for incident in state["classification"].incidents:
        plan = remediate(incident)
        plans.append(plan)
        src = plan.runbook_source or "first principles"
        esc = " ⚠ ESCALATE" if plan.escalate else ""
        lines.append(
            f"🛠 Remediation: {incident.incident_id} → {len(plan.steps)} steps "
            f"(grounded in {src}){esc}"
        )
    return {"plans": plans, "trace": lines}


def node_notify(state: SuiteState) -> dict:
    plans_by_id = {p.incident_id: p for p in state["plans"]}
    results, lines = [], []
    for incident in state["classification"].incidents:
        r = notify(incident, plans_by_id[incident.incident_id])
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
        r = create_ticket(incident, plans_by_id[incident.incident_id])
        results.append(r)
        lines.append(
            f"🎫 JIRA: {incident.incident_id} → "
            + (r.ticket_key if r.ticket_key else f"skipped ({r.skipped_reason})")
        )
    return {"tickets": results, "trace": lines}


def node_cookbook(state: SuiteState) -> dict:
    doc = synthesize(state["classification"], state["plans"])
    return {"cookbook": doc, "trace": ["📕 Cookbook: checklist synthesized"]}


def build_graph():
    g = StateGraph(SuiteState)
    g.add_node("ingest", node_ingest)
    g.add_node("classify", node_classify)
    g.add_node("remediate", node_remediate)
    g.add_node("notify_slack", node_notify)
    g.add_node("create_jira", node_jira)
    g.add_node("cookbook", node_cookbook)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_edge("classify", "remediate")
    # fan-out after remediation
    g.add_edge("remediate", "notify_slack")
    g.add_edge("remediate", "create_jira")
    g.add_edge("remediate", "cookbook")
    g.add_edge("notify_slack", END)
    g.add_edge("create_jira", END)
    g.add_edge("cookbook", END)
    return g.compile()
