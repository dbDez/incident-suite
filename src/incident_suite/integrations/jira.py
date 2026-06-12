"""JIRA ticket agent — Atlassian Cloud REST v3. Tickets only for critical/high.
Degrades gracefully when unconfigured."""

import os

import requests

from ..schemas import Incident, RemediationPlan, Severity, TicketResult

TICKET_SEVERITIES = (Severity.critical, Severity.high)


def create_ticket(incident: Incident, plan: RemediationPlan) -> TicketResult:
    base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_API_TOKEN", "")
    project = os.environ.get("JIRA_PROJECT_KEY", "")

    if incident.severity not in TICKET_SEVERITIES:
        return TicketResult(
            incident_id=incident.incident_id,
            ticket_key=None,
            ticket_url=None,
            skipped_reason=f"severity {incident.severity.value} below ticket threshold",
        )
    if not all((base, email, token, project)):
        return TicketResult(
            incident_id=incident.incident_id,
            ticket_key=None,
            ticket_url=None,
            skipped_reason="JIRA_* env vars not configured",
        )

    steps_text = "\n".join(
        f"{s.order}. {s.action} — _{s.rationale}_ (risk: {s.risk})" for s in plan.steps
    )
    description = (
        f"Severity: {incident.severity.value}\n"
        f"Component: {incident.affected_component}\n"
        f"Occurrences: {incident.occurrence_count} (first seen {incident.first_seen})\n\n"
        f"Evidence:\n" + "\n".join(f"* {{noformat}}{e}{{noformat}}" for e in incident.evidence[:5])
        + f"\n\nProposed remediation"
        + (f" (runbook: {plan.runbook_source})" if plan.runbook_source else "")
        + f":\n{steps_text}"
    )
    payload = {
        "fields": {
            "project": {"key": project},
            "summary": f"[{incident.severity.value.upper()}] {incident.title}",
            "issuetype": {"name": "Bug"},
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
        }
    }
    resp = requests.post(
        f"{base}/rest/api/3/issue", json=payload, auth=(email, token), timeout=30
    )
    if not resp.ok:
        return TicketResult(
            incident_id=incident.incident_id,
            ticket_key=None,
            ticket_url=None,
            skipped_reason=f"JIRA returned {resp.status_code}: {resp.text[:200]}",
        )
    key = resp.json()["key"]
    return TicketResult(
        incident_id=incident.incident_id,
        ticket_key=key,
        ticket_url=f"{base}/browse/{key}",
        skipped_reason=None,
    )
