# Runbook — Upstream Rate Limiting (429s)

**Symptoms:** `429 Too Many Requests` from a third-party or internal API, `Retry-After` headers, error rate periodic with clock windows (top of minute/hour), retry storms amplifying the problem.

**Component:** application / external integration.

## Diagnosis (observe first)

1. Which caller and which quota: aggregate 429s by API key/client/route — one tenant or all traffic?
2. What changed: traffic spike, a new batch job, a retry loop without backoff (one failure → N retries → more 429s)?
3. Read the provider's limit headers (`X-RateLimit-Remaining`, `Retry-After`) — are we near quota or hitting burst limits?

## Remediation (least invasive first)

1. Honour `Retry-After` with jittered exponential backoff — verify the client actually backs off; retry storms are usually self-inflicted.
2. Pause/reschedule the batch job competing with interactive traffic.
3. Add client-side throttling (token bucket) just below the provider limit; smooth bursts rather than clipping them.
4. If genuinely under-provisioned: request a quota raise / upgrade the plan — with usage data attached.

## Escalation

If 429s come from OUR edge onto our own users (WAF/API-gateway misconfig after a change), revert the gateway config first and escalate to whoever changed it.
