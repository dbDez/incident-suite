"""Eval: does the Log Classifier detect the incidents seeded in the sample logs?

Scored by an LLM judge against a deterministic known-incidents checklist —
same shape as the Eng Acc evals session's code-critique task.

Usage:
    inspect eval task_classifier.py --model openai/openai/gpt-4o-mini
    inspect eval task_classifier.py -T grader_model=openai/anthropic/claude-sonnet-4-6
"""

import os
import sys
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import GenerateConfig, get_model
from inspect_ai.scorer import CORRECT, INCORRECT, PARTIAL, Score, accuracy, scorer
from inspect_ai.solver import generate, system_message

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.incident_suite.agents.classifier import SYSTEM  # noqa: E402 — same prompt as production
from src.incident_suite.ingest import ingest_log  # noqa: E402

KNOWN_INCIDENTS = {
    "web-outage.log": [
        {
            "id": "checkout-gateway-outage",
            "expected_severity": "critical",
            "description": "User-facing outage on /api/checkout: nginx 502s and upstream read timeouts, 5xx alert firing above threshold. Worker-pool saturation lines may appear as evidence here or under the DB incident. May reasonably be reported as one incident or split into 502s + timeouts.",
        },
        {
            "id": "db-connection-pool-exhaustion",
            "expected_severity": "critical",
            "description": "MySQL 'Too many connections' (Threads_connected=501/500) plus HikariPool acquisition timeouts; idle-in-transaction sessions holding connections.",
        },
        {
            "id": "deploy-correlation",
            "expected_severity": "medium",
            "description": "release v2.14.3 deployed ~4 minutes before error onset — flagged as a likely trigger worth rollback consideration.",
        },
    ],
    "host-degradation.log": [
        {
            "id": "disk-space-exhaustion",
            "expected_severity": "critical",
            "description": "/var at 99% on batch-02, 'No space left on device' across etl, logrotate and backup.",
        },
        {
            "id": "oom-kills-etl-worker",
            "expected_severity": "high",
            "description": "kernel OOM killer terminated etl-worker 3 times (~16GB RSS), systemd restart loop.",
        },
        {
            "id": "postgres-readonly-wal",
            "expected_severity": "critical",
            "description": "postgres cannot write WAL, database switched to read-only — write transactions rejected.",
        },
        {
            "id": "etl-sla-breach",
            "expected_severity": "medium",
            "description": "nightly-aggregate failed repeatedly and breached its 02:00 SLA; nightly backup also failed.",
        },
    ],
}

RUBRIC = (Path(__file__).parent / "rubrics" / "classifier.txt").read_text(encoding="utf-8")


def _known_incidents_text(log_name: str) -> str:
    return "\n".join(
        f"{i}. **{k['id']}** (expected severity: {k['expected_severity']}): {k['description']}"
        for i, k in enumerate(KNOWN_INCIDENTS[log_name], 1)
    )


def _build_prompt(log_name: str) -> str:
    extract = ingest_log(ROOT / "data" / "sample_logs" / log_name)
    return (
        f"## Log extract\n\n"
        f"File: {extract.source_file} | {extract.total_lines} lines | "
        f"{extract.window_start} → {extract.window_end}\n"
        f"Level counts: {extract.line_counts_by_level}\n\n"
        "Error/warn lines (deduplicated, [xN] = repeat count):\n"
        + "\n".join(extract.error_lines)
        + "\n\nIdentify every distinct incident. For each: a kebab-case id, title, "
        "severity (critical/high/medium/low/info), affected component, and verbatim evidence lines."
    )


@scorer(metrics=[accuracy()])
def classifier_scorer(grader_model: str | None = None):
    async def score(state, target):
        log_name = state.metadata["log_name"]
        rubric = RUBRIC.replace("{known_incidents}", _known_incidents_text(log_name))
        grader = get_model(
            grader_model
            or os.environ.get("INSPECT_GRADER_MODEL", "openai/anthropic/claude-sonnet-4-6")
        )
        result = await grader.generate(
            f"{rubric}\n\n## Classifier output to evaluate\n\n{state.output.completion}"
        )
        text = result.completion.lower()
        if "grade: correct" in text:
            return Score(value=CORRECT, explanation=result.completion)
        if "grade: partial" in text:
            return Score(value=PARTIAL, explanation=result.completion)
        return Score(value=INCORRECT, explanation=result.completion)

    return score


@task
def classifier_eval(grader_model: str | None = None):
    samples = [
        Sample(
            input=_build_prompt(log_name),
            target=f"Detect all {len(incidents)} seeded incidents with grounded evidence",
            id=log_name,
            metadata={"log_name": log_name, "known_incident_count": len(incidents)},
        )
        for log_name, incidents in KNOWN_INCIDENTS.items()
    ]
    return Task(
        dataset=samples,
        solver=[system_message(SYSTEM), generate()],
        scorer=classifier_scorer(grader_model),
        config=GenerateConfig(temperature=0.2, max_tokens=8192),
    )
