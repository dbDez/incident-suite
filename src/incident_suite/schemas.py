"""Structured-output contracts. Every agent boundary speaks these schemas —
no free-text handoffs between nodes."""

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class LogExtract(BaseModel):
    """What the side-channel ingest layer hands the Classifier — never raw logs."""

    source_file: str
    total_lines: int
    window_start: str = Field(description="Timestamp of first line in extract")
    window_end: str = Field(description="Timestamp of last line in extract")
    error_lines: list[str] = Field(description="Deduplicated error/warn lines, capped")
    line_counts_by_level: dict[str, int]


class Incident(BaseModel):
    incident_id: str = Field(description="Stable slug, e.g. 'db-connection-pool-exhausted'")
    title: str
    severity: Severity
    category: str = Field(description="e.g. database, network, memory, disk, application, security")
    affected_component: str
    evidence: list[str] = Field(description="Verbatim log lines supporting this incident")
    first_seen: str
    occurrence_count: int


class ClassificationResult(BaseModel):
    incidents: list[Incident]
    summary: str = Field(description="One-paragraph operator summary of the log window")


class Citation(BaseModel):
    """A retrieved runbook chunk grounding a remediation plan."""

    source: str = Field(description="Runbook filename")
    section: str = Field(description="Heading breadcrumb of the chunk")
    score: float = Field(description="Cosine similarity (1.0 = identical)")
    excerpt: str = Field(description="The retrieved chunk text")


class WebFinding(BaseModel):
    """A Tavily web-research result enriching an incident."""

    title: str
    url: str
    snippet: str


class RemediationStep(BaseModel):
    order: int
    action: str
    rationale: str
    command: str | None = Field(default=None, description="Suggested command — NEVER executed")
    risk: str = Field(description="What could go wrong applying this step")


class RemediationDraft(BaseModel):
    """What the LLM generates — grounding metadata is attached in code."""

    runbook_source: str | None = Field(
        default=None, description="Which runbook grounded this plan, if any"
    )
    steps: list[RemediationStep]
    escalate: bool = Field(description="True if this needs a human before any action")


class RemediationPlan(RemediationDraft):
    incident_id: str
    citations: list[Citation] = Field(
        default_factory=list, description="RAG chunks that grounded this plan"
    )
    web_sources: list[WebFinding] = Field(
        default_factory=list, description="Web research findings for this incident"
    )


class TicketResult(BaseModel):
    incident_id: str
    ticket_key: str | None
    ticket_url: str | None
    skipped_reason: str | None = None


class NotificationResult(BaseModel):
    incident_id: str
    delivered: bool
    skipped_reason: str | None = None
