# Runbook — Gateway 502/504 Upstream Timeouts

**Symptoms:** nginx/ALB `502 Bad Gateway`, `504 Gateway Time-out`, `upstream timed out (110: Connection timed out)`, rising p99 latency before errors.

**Component:** reverse proxy / load balancer / app tier.

## Diagnosis (observe first)

1. Is the upstream actually down or just slow? `curl -m 5 http://<upstream>:<port>/health` from the proxy host.
2. Check upstream process state and recent restarts: `systemctl status <app>`, container restart counts.
3. Correlate with deploys — did a release land in the error window?
4. Check upstream resource saturation: CPU, memory, thread/worker pool exhaustion, GC pauses.

## Remediation (least invasive first)

1. If one instance is bad: drain it from the pool, leave the rest serving.
2. If a fresh deploy correlates: roll back the release. ⚠ Confirm rollback target is the last known-good tag.
3. If worker pool exhaustion: scale out replicas before tuning timeouts.
4. Only as a stopgap: raise `proxy_read_timeout` modestly. ⚠ Hides the real problem; never exceed client-side timeout budgets.

## Escalation

User-facing 5xx above 1% for more than 15 minutes → declare an incident, page the service owner.
