# Post-mortem — 2026-03-14 Checkout Outage (47 min)

**Summary:** checkout was down 14:02–14:49 after release v2.9.1 introduced a connection leak. Severity: SEV-1. Customer impact: ~2,300 failed checkouts.

## What happened

Release v2.9.1 changed the order-service repository layer and stopped returning pooled connections in an error path. Under afternoon traffic the pool drained in ~25 minutes; HikariPool acquisition timeouts cascaded into nginx 502s on /api/checkout. The on-call engineer initially scaled out app replicas, which made it WORSE — more replicas, more leaked connections, faster pool exhaustion at the database.

## Root cause

Connection leak in an error path (missing finally/return-to-pool), shipped in v2.9.1. The leak only manifests under elevated error rates, which the deploy itself triggered.

## What worked / what didn't

- ❌ Scaling out replicas accelerated the failure — capacity is NOT the fix for a leak.
- ✅ Rolling back to v2.9.0 restored service within 6 minutes of the decision.
- ✅ Killing idle-in-transaction sessions bought 10 minutes of breathing room.
- ❌ The deploy-to-error correlation took 31 minutes to spot. The release had landed 4 minutes before error onset.

## Lessons / actions

1. When connection-pool exhaustion follows a deploy within ~30 minutes, ROLL BACK FIRST and diagnose after. Do not scale out.
2. Always check the deploy timeline before any capacity action on pool exhaustion.
3. Pool-utilisation alert at 80% added (was: none).
4. Repository-layer changes now require a connection-lifecycle review in PR.
