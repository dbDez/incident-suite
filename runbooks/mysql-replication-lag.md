# Runbook — MySQL Replication Lag

**Symptoms:** `Seconds_Behind_Master` climbing, read-replica queries returning stale data, failover readiness degraded, replica `SQL_THREAD` busy at 100% on one core.

**Component:** database / replication.

## Diagnosis (observe first)

1. `SHOW REPLICA STATUS\G` — is `IO_THREAD` behind (network/binlog transfer) or `SQL_THREAD` behind (apply speed)?
2. What's applying slowly: large transaction (bulk UPDATE/DELETE), DDL, or many small writes on a single-threaded applier?
3. Check for replica-only load: heavy analytics queries on the replica steal apply capacity.
4. Binlog format: row-based with huge transactions transfers and applies far more volume.

## Remediation (least invasive first)

1. Move/pause heavy read queries off the lagging replica until it catches up.
2. If one mega-transaction is the cause: wait it out (killing it mid-apply forces a longer rollback). Prevent recurrence by chunking bulk writes (e.g. 10k rows per transaction).
3. Enable parallel apply (`replica_parallel_workers`) if write concurrency allows. ⚠ Test ordering assumptions first.
4. If lag breaches failover SLO routinely: capacity work — replica hardware or write-path reduction.

## Escalation

If lag is still growing while diagnosis says apply rate is normal, suspect data divergence/duplicate-key stalls — escalate to the DBA before anyone attempts a failover on a stale replica.
