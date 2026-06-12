"""Cookbook Synthesizer agent — turns all plans into one actionable checklist."""

from ..llm import get_llm
from ..schemas import ClassificationResult, RemediationPlan

SYSTEM = """You are an incident commander writing the post-triage cookbook. \
Given the classified incidents and their remediation plans, produce ONE \
markdown checklist document an on-call engineer can execute top-to-bottom.

Format:
# Incident Cookbook — <date/window>
## Triage summary  (3-5 bullets, severity-ordered)
## Checklist       (numbered, grouped by incident, checkbox per step, \
inline rationale in italics, ⚠ prefix on risky steps)
## Escalations     (anything flagged escalate=true, with who/why)
"""


def synthesize(classification: ClassificationResult, plans: list[RemediationPlan]) -> str:
    llm = get_llm(temperature=0.3)
    prompt = (
        f"{SYSTEM}\n\n## Classification\n{classification.model_dump_json(indent=2)}\n\n"
        "## Remediation plans\n"
        + "\n".join(p.model_dump_json(indent=2) for p in plans)
    )
    return llm.invoke(prompt).content
