# Runbook — Database Connection Pool Exhaustion

**Symptoms:** `Too many connections`, `connection pool exhausted`, `timeout acquiring connection from pool`, app-tier 500s while DB CPU is normal.

**Component:** database / application connection layer (MySQL, PostgreSQL, connection poolers).

## Diagnosis (observe first — no mutations)

1. Count current connections vs limit: `SHOW STATUS LIKE 'Threads_connected';` and `SHOW VARIABLES LIKE 'max_connections';`
2. Identify the top consumers: `SELECT user, host, COUNT(*) FROM information_schema.PROCESSLIST GROUP BY user, host ORDER BY 3 DESC;`
3. Check for long-running idle transactions holding connections: `SELECT * FROM information_schema.PROCESSLIST WHERE COMMAND='Sleep' AND TIME > 300;`
4. Check the application pool metrics (active vs idle vs waiting).

## Remediation (least invasive first)

1. If one client is leaking: restart only that application service, not the database.
2. Kill idle-in-transaction sessions older than 10 minutes (coordinate with app owner).
3. Temporarily raise `max_connections` by 20-30% ONLY if memory headroom exists (~each connection costs memory; check `innodb_buffer_pool_size` vs RAM first). ⚠ Risky on memory-constrained hosts.
4. Fix the leak: ensure connections are returned in `finally`/context-manager; cap pool size below DB `max_connections` / number of app instances.

## Escalation

If connections climb again within 30 minutes, escalate to the application owner — this is a leak, not a capacity problem. Do NOT keep raising `max_connections`.
