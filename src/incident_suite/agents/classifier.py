"""Log Classifier agent — LogExtract in, strict ClassificationResult out."""

from ..llm import get_llm
from ..schemas import ClassificationResult, LogExtract

SYSTEM = """You are an SRE log-analysis specialist. You receive a structured \
extract of an operations log (deduplicated error/warn lines with repeat counts, \
level histogram, time window). Identify every DISTINCT incident.

Rules:
- Group related lines into one incident; do not emit one incident per line.
- evidence must quote verbatim lines from the extract.
- incident_id is a stable kebab-case slug describing the failure mode.
- Severity: critical = user-facing outage or data loss in progress; high = \
degradation or imminent outage; medium = needs attention this week; low/info = hygiene.
- Do not invent incidents that the evidence does not support."""


def classify(extract: LogExtract) -> ClassificationResult:
    llm = get_llm().with_structured_output(ClassificationResult)
    prompt = (
        f"{SYSTEM}\n\n## Log extract\n\n"
        f"File: {extract.source_file} | {extract.total_lines} lines | "
        f"{extract.window_start} → {extract.window_end}\n"
        f"Level counts: {extract.line_counts_by_level}\n\n"
        "Error/warn lines (deduplicated, [xN] = repeat count):\n"
        + "\n".join(extract.error_lines)
    )
    return llm.invoke(prompt)
