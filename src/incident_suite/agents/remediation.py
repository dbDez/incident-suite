"""Remediation agent — maps ONE incident to a guarded fix plan, grounded in
RAG-retrieved runbook chunks (rag.py) and optional web research (research.py).
The agent PROPOSES steps with rationale and risk — nothing is ever executed."""

from ..llm import get_llm
from ..schemas import Citation, Incident, RemediationDraft, RemediationPlan, WebFinding

SYSTEM = """You are a senior SRE writing a remediation plan for ONE incident. \
You may be given retrieved runbook excerpts with similarity scores and live \
web research findings — ground every step in them where relevant. If nothing \
retrieved actually matches the incident, reason from first principles and \
set escalate=true unless the fix is trivially safe.

Rules:
- Steps are PROPOSALS for a human operator. Include rationale and risk per step.
- Prefer the least invasive step first (check/observe before restart/rollback).
- Commands are suggestions only; mark anything destructive clearly in risk.
- Runbook excerpts outrank web findings when they conflict.
- Do not copy steps that don't apply to the actual evidence."""


def remediate(
    incident: Incident,
    citations: list[Citation],
    web_findings: list[WebFinding] | None = None,
) -> RemediationPlan:
    web_findings = web_findings or []
    llm = get_llm().with_structured_output(RemediationDraft)

    if citations:
        runbook_block = "\n## Retrieved runbook excerpts\n\n" + "\n\n".join(
            f"### [{c.source} → {c.section}] (similarity {c.score})\n{c.excerpt}"
            for c in citations
        )
    else:
        runbook_block = "\n## No relevant runbook excerpts were retrieved."

    if web_findings:
        web_block = "\n## Web research findings\n\n" + "\n\n".join(
            f"### {w.title}\n{w.url}\n{w.snippet}" for w in web_findings
        )
    else:
        web_block = ""

    draft = llm.invoke(
        f"{SYSTEM}\n\n## Incident\n{incident.model_dump_json(indent=2)}\n"
        f"{runbook_block}{web_block}"
    )
    plan = RemediationPlan(
        **draft.model_dump(),
        incident_id=incident.incident_id,
        citations=citations,
        web_sources=web_findings,
    )
    if citations and not plan.runbook_source:
        plan.runbook_source = citations[0].source
    return plan
