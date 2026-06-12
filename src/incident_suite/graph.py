"""LangGraph orchestrator.

ingest → classify ⇄ verify_causes (critic loop, max 1 revision)
        → ⤜ Send() map-reduce: one remediate branch PER incident,
            each plan critic-reviewed (+1 revision round) ⤛
        → fan-out: notify_slack + create_jira + cookbook → END

The Critic agent independently re-derives root causes from the same evidence
and judges the Classifier's output; disagreement loops the classification
back once with the objections. Inside each remediation branch the Critic
reviews the plan the same way. Each incident gets its own parallel
remediation branch (LangGraph Send API); the joins are implicit —
notify/jira/cookbook wait for every branch. Every node appends
human-readable trace events so the UI can stream "which agent is doing
what" live.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from . import rag, vision
from .agents.classifier import classify
from .agents.cookbook import synthesize
from .agents.critic import review_causes, review_plan
from .agents.remediation import remediate
from .agents.research import investigate
from .ingest import ingest_log
from .integrations.jira import create_ticket
from .integrations.slack import notify
from .schemas import (
    CauseReview,
    ClassificationResult,
    Incident,
    LogExtract,
    NotificationResult,
    RemediationPlan,
    TicketResult,
)

MAX_CLASSIFY_ROUNDS = 2  # initial classification + at most one critic-driven revision


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
    cause_review: CauseReview
    classify_rounds: int
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
    if state.get("log_path"):
        _status("📥 Ingest: parsing log in the side-channel (no LLM)…")
        extract = ingest_log(state["log_path"])
        lines = [
            f"📥 Ingest: {extract.source_file} — {extract.total_lines} lines → "
            f"{len(extract.error_lines)} deduplicated error/warn lines "
            f"(side-channel: raw log never enters the LLM)"
        ]
    else:
        extract = LogExtract(
            source_file="(screenshot only — no log provided)",
            total_lines=0,
            window_start="unknown",
            window_end="unknown",
            error_lines=[],
            line_counts_by_level={},
        )
        lines = ["📥 Ingest: no log file — running screenshot-only analysis"]
    update: dict = {"extract": extract}
    if state.get("image_path"):
        _status("👁 Vision agent: analyzing image…")
        _status("👁 Extracting text, metrics and alert states from the screenshot (vision LLM)…")
        observations = vision.observe_dashboard(state["image_path"])
        update["dashboard_observations"] = observations
        lines.append(
            f"👁 Vision: screenshot analysed → {len(observations.splitlines())} observation lines"
        )
    # Build the RAG index BEFORE the parallel fan-out — the parallel branches
    # must only ever read it (chromadb builds are not thread-safe).
    _status("📚 RAG: building runbook vector index…")
    chunk_count = rag.warm_up()
    lines.append(f"📚 RAG: runbook index ready ({chunk_count} chunks)")
    update["trace"] = lines
    return update


def node_classify(state: SuiteState) -> dict:
    rounds = state.get("classify_rounds", 0)
    critique = None
    if rounds and state.get("cause_review"):
        review = state["cause_review"]
        critique = "\n".join(
            [f"- [{v.incident_id}] {v.objection}" for v in review.verdicts if not v.agrees]
            + [f"- MISSED root cause: {m}" for m in review.missed_root_causes]
        )
        _status("🔎 Classifier agent: revising classification against the critic's objections…")
    else:
        _status("🔎 Classifier agent: LangChain structured-output call (Pydantic schema)…")
    result = classify(state["extract"], state.get("dashboard_observations"), critique)
    # Guard: dedupe incidents by id (models occasionally emit one per repeat line)
    seen: set[str] = set()
    result.incidents = [
        i for i in result.incidents if not (i.incident_id in seen or seen.add(i.incident_id))
    ]
    label = "revised classification" if critique else "found"
    lines = [f"🔎 Classifier: {label} {len(result.incidents)} incident(s)"] + [
        f"   · [{i.severity.value.upper()}] {i.title} ({i.affected_component})"
        for i in result.incidents
    ]
    return {"classification": result, "classify_rounds": rounds + 1, "trace": lines}


def node_verify_causes(state: SuiteState) -> dict:
    """Critic agent independently re-derives root causes and judges the classification."""
    if not state["classification"].incidents:
        return {"cause_review": CauseReview(verdicts=[], agrees_overall=True), "trace": []}
    _status("⚖ Critic agent: independently re-deriving root causes from the same evidence…")
    review = review_causes(
        state["extract"], state.get("dashboard_observations"), state["classification"]
    )
    lines = []
    for v in review.verdicts:
        mark = "✓ agrees" if v.agrees else f"✗ disagrees — {v.objection}"
        lines.append(f"⚖ Critic[{v.incident_id}]: {mark}")
    for m in review.missed_root_causes:
        lines.append(f"⚖ Critic: missed root cause — {m}")
    if review.agrees_overall:
        lines.append("⚖ Critic: consensus reached — classification confirmed")
    elif state.get("classify_rounds", 1) < MAX_CLASSIFY_ROUNDS:
        lines.append("⚖ Critic: disagreement → sending classification back for one revision")
    else:
        lines.append("⚖ Critic: still disagrees after revision — proceeding, objections recorded")
    return {"cause_review": review, "trace": lines}


def route_after_verify(state: SuiteState):
    """Loop edge: disagree once → back to classify; otherwise fan out remediation."""
    review = state.get("cause_review")
    if (
        review is not None
        and not review.agrees_overall
        and state.get("classify_rounds", 1) < MAX_CLASSIFY_ROUNDS
    ):
        return "classify"
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

    _status(f"⚖ Critic agent: reviewing the plan for {incident.incident_id}…")
    review = review_plan(incident, plan)
    review_lines = []
    if review.approved:
        review_lines.append("   ⚖ Critic: plan approved")
    else:
        for o in review.objections:
            review_lines.append(f"   ⚖ Critic: ✗ {o}")
        _status(f"🛠 Remediation agent: revising plan for {incident.incident_id} (critic objected)…")
        plan = remediate(incident, citations, web_findings, objections=review.objections)
        review = review_plan(incident, plan)
        review_lines.append(
            "   ⚖ Critic: revised plan "
            + ("approved" if review.approved else "STILL contested — objections recorded, escalation advised")
        )
        if not review.approved:
            plan.escalate = True
    plan.review = review

    lines = [
        f"🛠 Remediation[{incident.incident_id}]: {len(plan.steps)} steps"
        + (" (revised after review)" if plan.revised else "")
        + (" ⚠ ESCALATE" if plan.escalate else "")
    ]
    lines.extend(review_lines)
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
    g.add_node("verify_causes", node_verify_causes)
    g.add_node("remediate_one", node_remediate_one)
    g.add_node("notify_slack", node_notify)
    g.add_node("create_jira", node_jira)
    g.add_node("cookbook", node_cookbook)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    # adversarial loop: critic reviews the classification; disagreement sends
    # it back to classify for ONE bounded revision round, then proceeds
    g.add_edge("classify", "verify_causes")
    g.add_conditional_edges(
        "verify_causes", route_after_verify, ["classify", "remediate_one", "cookbook"]
    )
    g.add_edge("remediate_one", "notify_slack")
    g.add_edge("remediate_one", "create_jira")
    g.add_edge("remediate_one", "cookbook")
    g.add_edge("notify_slack", END)
    g.add_edge("create_jira", END)
    g.add_edge("cookbook", END)
    return g.compile()
