# Runbook — Redis Memory Pressure / Eviction Storm

**Symptoms:** `OOM command not allowed when used memory > 'maxmemory'`, cache hit rate collapsing, `evicted_keys` spiking, app latency rising as reads fall through to the database.

**Component:** cache / Redis.

## Diagnosis (observe first)

1. `INFO memory` — `used_memory` vs `maxmemory`, fragmentation ratio; `INFO stats` — `evicted_keys`, `keyspace_misses`.
2. What grew: `redis-cli --bigkeys` / `MEMORY USAGE <key>` on suspects — one giant key or general growth?
3. Check the eviction policy (`maxmemory-policy`) — `noeviction` causes write errors; `allkeys-lru` causes silent cache churn.
4. Did TTLs disappear? A deploy that stopped setting EXPIRE turns a cache into a leak.

## Remediation (least invasive first)

1. If one runaway key/pattern: delete or TTL just that pattern (`SCAN` + `UNLINK`, never `KEYS` in prod). ⚠ `UNLINK` not `DEL` for big keys.
2. If missing TTLs from a deploy: fix the writer, then backfill EXPIRE on the affected pattern.
3. Raise `maxmemory` one notch ONLY if host headroom exists; check `maxmemory` vs instance RAM minus fork overhead (BGSAVE doubles peak).
4. Protect the database below: enable/verify request coalescing or a short negative-cache while the hit rate recovers.

## Escalation

If the database tier is now saturating from cache misses, treat as a cascading incident — page the DB owner before the cache work, the DB is the one that falls over.
