"""Log Classifier agent — LogExtract in, strict ClassificationResult out."""

from ..llm import get_llm
from ..schemas import ClassificationResult, LogExtract

SYSTEM = """You are an SRE log-analysis specialist. You receive a structured \
extract of an operations log (deduplicated error/warn lines with repeat counts, \
level histogram, time window). Identify every DISTINCT incident.

Rules:
- Group by ROOT CAUSE, not by symptom or component: gateway 5xx, upstream \
timeouts and the monitoring alert for the same route are ONE incident; a \
full disk on one host is ONE incident even if it breaks several services \
(list them all in affected_component and evidence). Emit separate incidents \
only for genuinely independent root causes.
- evidence must quote verbatim lines from the extract.
- incident_id is a stable kebab-case slug describing the failure mode.
- Severity: critical = user-facing outage or data loss IN PROGRESS (e.g. \
5xx on a user-facing route above alert threshold, database refusing \
connections/writes); high = degradation or imminent outage; medium = needs \
attention this week; low/info = hygiene.
- Lines tagged [context: operational event] are deploys/restarts/failovers. \
If such an event correlates in time with error onset, emit it as its own \
incident (severity medium, category application) recommending rollback \
consideration — and quote THAT context line as its evidence. Never emit a \
deploy-correlation incident without an explicit operational-event line.
- Do not invent incidents that the evidence does not support."""


def classify(extract: LogExtract, observations: str | None = None) -> ClassificationResult:
    llm = get_llm(temperature=0.0).with_structured_output(ClassificationResult)
    prompt = (
        f"{SYSTEM}\n\n## Log extract\n\n"
        f"File: {extract.source_file} | {extract.total_lines} lines | "
        f"{extract.window_start} → {extract.window_end}\n"
        f"Level counts: {extract.line_counts_by_level}\n\n"
        "Error/warn lines (deduplicated, [xN] = repeat count):\n"
        + "\n".join(extract.error_lines)
    )
    if observations and extract.total_lines == 0:
        prompt += (
            "\n\n## Dashboard screenshot observations (vision agent)\n"
            "No log file was provided — these observations are the ONLY evidence. "
            "Classify incidents from them and quote the observation lines as evidence:\n"
            + observations
        )
    elif observations:
        prompt += (
            "\n\n## Dashboard screenshot observations (vision agent)\n"
            "Corroborating signals observed on an uploaded monitoring screenshot — "
            "use to confirm/enrich incidents, cite as evidence only if echoed in logs:\n"
            + observations
        )
    return llm.invoke(prompt)
