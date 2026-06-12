"""Slack notifier — incoming webhook. Degrades gracefully when unconfigured."""

import os

import requests

from ..schemas import Incident, NotificationResult, RemediationPlan


def notify(incident: Incident, plan: RemediationPlan) -> NotificationResult:
    url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not url:
        return NotificationResult(
            incident_id=incident.incident_id,
            delivered=False,
            skipped_reason="SLACK_WEBHOOK_URL not configured",
        )

    sev_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}
    first_steps = "\n".join(
        f"  {s.order}. {s.action}" for s in plan.steps[:3]
    )
    payload = {
        "text": (
            f"{sev_emoji.get(incident.severity.value, '⚪')} "
            f"*{incident.severity.value.upper()}* — {incident.title}\n"
            f"Component: `{incident.affected_component}` · seen ×{incident.occurrence_count}\n"
            f"First steps:\n{first_steps}\n"
            + (f"_Runbook: {plan.runbook_source}_" if plan.runbook_source else "_No runbook matched_")
        )
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
    except requests.RequestException as e:
        return NotificationResult(
            incident_id=incident.incident_id,
            delivered=False,
            skipped_reason=f"Slack unreachable: {type(e).__name__}",
        )
    return NotificationResult(
        incident_id=incident.incident_id,
        delivered=resp.ok,
        skipped_reason=None if resp.ok else f"Slack returned {resp.status_code}",
    )
