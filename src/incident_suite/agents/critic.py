"""Critic agent — the second pair of eyes that makes agents REASON WITH each
other instead of just handing off. Two duties:

1. review_causes — independently re-derives root causes from the same evidence
   the Classifier saw, then judges each proposed incident. Disagreement sends
   the Classifier back one bounded revision round (graph loop edge).
2. review_plan — checks one remediation plan against the agreed cause and its
   grounding. Objections send the Remediation agent back one revision round.

The critic never sees the other agent's reasoning prompt — only its structured
output — so agreement is a genuine cross-check, not an echo.
"""

from ..llm import get_llm
from ..schemas import (
    CauseReview,
    ClassificationResult,
    Incident,
    LogExtract,
    PlanReview,
    RemediationPlan,
)

CAUSE_SYSTEM = """You are an independent senior SRE acting as a REVIEWER. A \
colleague has classified incidents from a log extract. Your job is to verify \
their root-cause analysis — you are rewarded for catching real mistakes, not \
for politeness, and not for inventing disagreements.

Method:
1. FIRST reason about the evidence yourself: what distinct root causes does \
the extract actually support?
2. THEN compare against the proposed incidents. For each, decide: does the \
quoted evidence support this incident as stated (root cause, severity, \
affected component)?
- Disagree when: the root cause is wrong (symptom mislabelled as cause), two \
incidents share one root cause (should be merged), severity is clearly \
miscalibrated, or evidence does not support the claim.
- missed_root_causes is ONLY for failure modes with NO corresponding proposed \
incident at all. If an incident already covers the cause — even with narrower \
wording or a partial component list — that is NOT a missed root cause; raise \
it as an objection on that incident instead, or let it pass.
- agrees_overall is true ONLY if every verdict agrees and nothing was missed.
- Do NOT object to phrasing, slug naming, or judgement calls that are \
defensible — only substantive errors. An empty objection list with \
agrees_overall=true is the expected outcome for a sound classification."""

PLAN_SYSTEM = """You are an independent senior SRE acting as a REVIEWER of a \
remediation plan written by a colleague for ONE incident. You are rewarded \
for catching real problems, not for politeness, and not for nitpicking.

Approve unless a step has a substantive problem:
- A step does not actually address the incident's root cause.
- A destructive/invasive step lacks an honest risk statement, or runs before \
cheaper diagnostic steps.
- A step contradicts the cited runbook excerpts without justification.
- escalate=false on a plan that clearly needs a human before action.
NOT objections (approve despite these):
- escalate=true. That is the safe, conservative setting — never object to it.
- A later step not restating "only if earlier steps didn't resolve it" — \
sequential ordering already implies that.
- A risk statement that exists but could be more thorough. Only a MISSING \
risk statement on a destructive step is an objection — never its wording.
- Style, wording, level of detail, or reasonable judgement calls.
The test for an objection: would an operator following this plan as written \
plausibly cause harm or fail to fix the incident? If not, approve. Approval \
on the first pass is the normal outcome for a competent plan."""


def review_causes(
    extract: LogExtract,
    observations: str | None,
    classification: ClassificationResult,
) -> CauseReview:
    llm = get_llm(temperature=0.0).with_structured_output(CauseReview)
    prompt = (
        f"{CAUSE_SYSTEM}\n\n## Evidence (same extract the classifier saw)\n\n"
        f"File: {extract.source_file} | {extract.total_lines} lines | "
        f"{extract.window_start} → {extract.window_end}\n"
        f"Level counts: {extract.line_counts_by_level}\n\n"
        "Error/warn lines (deduplicated, [xN] = repeat count):\n"
        + "\n".join(extract.error_lines)
    )
    if observations:
        prompt += "\n\n## Dashboard screenshot observations\n" + observations
    prompt += (
        "\n\n## Proposed classification to review\n"
        + classification.model_dump_json(indent=2)
    )
    return llm.invoke(prompt)


def review_plan(incident: Incident, plan: RemediationPlan) -> PlanReview:
    llm = get_llm(temperature=0.0).with_structured_output(PlanReview)
    return llm.invoke(
        f"{PLAN_SYSTEM}\n\n## Incident\n{incident.model_dump_json(indent=2)}\n\n"
        f"## Plan to review\n{plan.model_dump_json(indent=2, exclude={'review'})}"
    )
