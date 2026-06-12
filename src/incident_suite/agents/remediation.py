"""Remediation agent — maps each incident to a guarded fix plan.

Retrieval: naive keyword-scored retrieval over runbooks/ for the scaffold;
upgrade to embedding RAG on build day if time allows. The agent PROPOSES
steps with rationale and risk — nothing is ever executed.
"""

from pathlib import Path

from ..llm import get_llm
from ..schemas import Incident, RemediationPlan

RUNBOOK_DIR = Path(__file__).resolve().parents[3] / "runbooks"

SYSTEM = """You are a senior SRE writing a remediation plan for ONE incident. \
You may be given a matching runbook — if so, ground every step in it and set \
runbook_source. If no runbook matches, reason from first principles and set \
escalate=true unless the fix is trivially safe.

Rules:
- Steps are PROPOSALS for a human operator. Include rationale and risk per step.
- Prefer the least invasive step first (check/observe before restart/rollback).
- Commands are suggestions only; mark anything destructive clearly in risk."""


def _retrieve_runbook(incident: Incident) -> tuple[str | None, str]:
    """Cheap keyword overlap scoring. Returns (filename, content)."""
    terms = set(
        f"{incident.incident_id} {incident.title} {incident.category} "
        f"{incident.affected_component}".lower().replace("-", " ").split()
    )
    best: tuple[int, str, str] | None = None
    for path in sorted(RUNBOOK_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        score = sum(1 for t in terms if t in content.lower())
        if best is None or score > best[0]:
            best = (score, path.name, content)
    if best and best[0] >= 3:
        return best[1], best[2]
    return None, ""


def remediate(incident: Incident) -> RemediationPlan:
    runbook_name, runbook_text = _retrieve_runbook(incident)
    llm = get_llm().with_structured_output(RemediationPlan)
    prompt = (
        f"{SYSTEM}\n\n## Incident\n{incident.model_dump_json(indent=2)}\n"
        + (
            f"\n## Matching runbook: {runbook_name}\n{runbook_text}"
            if runbook_name
            else "\n## No matching runbook found."
        )
    )
    plan = llm.invoke(prompt)
    plan.incident_id = incident.incident_id
    if runbook_name:
        plan.runbook_source = runbook_name
    return plan
