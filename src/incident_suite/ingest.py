"""Side-channel log ingest.

Raw log files NEVER enter the LLM context. This module parses, deduplicates
and windows the log entirely in Python, producing a compact LogExtract that
the Classifier agent consumes. Token discipline is a feature.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .schemas import LogExtract

# Tune as needed; keeps the extract well under any context budget.
MAX_ERROR_LINES = 120

LEVEL_PATTERN = re.compile(
    r"\b(TRACE|DEBUG|INFO|NOTICE|WARN(?:ING)?|ERROR|SEVERE|CRIT(?:ICAL)?|FATAL|PANIC)\b",
    re.IGNORECASE,
)
TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
)
# Strip volatile tokens so near-identical lines dedupe together.
VOLATILE_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[^\s]*)|(\b0x[0-9a-fA-F]+\b)|(\b\d{4,}\b)"
)


def _normalise(line: str) -> str:
    return VOLATILE_PATTERN.sub("<v>", line).strip()


def ingest_log(path: str | Path) -> LogExtract:
    path = Path(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    level_counts: Counter[str] = Counter()
    error_lines: list[str] = []
    seen_normalised: Counter[str] = Counter()
    first_ts, last_ts = "", ""

    for line in lines:
        ts = TIMESTAMP_PATTERN.search(line)
        if ts:
            last_ts = ts.group(0)
            if not first_ts:
                first_ts = ts.group(0)

        match = LEVEL_PATTERN.search(line)
        level = match.group(1).upper() if match else "UNLEVELLED"
        level = {"WARNING": "WARN", "CRITICAL": "CRIT", "SEVERE": "ERROR"}.get(level, level)
        level_counts[level] += 1

        if level in ("WARN", "ERROR", "CRIT", "FATAL", "PANIC"):
            key = _normalise(line)
            seen_normalised[key] += 1
            if seen_normalised[key] == 1 and len(error_lines) < MAX_ERROR_LINES:
                error_lines.append(line.strip())

    # Annotate repeat counts so the model sees frequency without seeing repeats.
    annotated = []
    for line in error_lines:
        count = seen_normalised[_normalise(line)]
        annotated.append(f"{line}  [x{count}]" if count > 1 else line)

    return LogExtract(
        source_file=path.name,
        total_lines=len(lines),
        window_start=first_ts or "unknown",
        window_end=last_ts or "unknown",
        error_lines=annotated,
        line_counts_by_level=dict(level_counts),
    )
