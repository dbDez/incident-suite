# Runbook — Batch Job / Data Freshness SLA Breach

**Symptoms:** nightly job missed its completion deadline, data-freshness alerts (`ORDER_FRESHNESS_SLA`, `NIGHTLY_ETL_SLA_BREACH`), downstream reports stale, backup windows overrunning.

**Component:** batch / ETL / scheduled pipelines.

## Diagnosis (observe first)

1. Did the job fail, or is it still running slow? Check the scheduler's run state and the job's own logs before assuming failure.
2. Find the bottleneck stage: compare per-stage durations against the last 7 successful runs — one stage regressing is a different problem from uniform slowdown.
3. Check upstream dependencies: did the input data arrive late or grow abnormally (2x input = 2x runtime)?
4. Check resource contention in the batch window: is something else (backup, reindex, another team's job) now sharing the window?

## Remediation (least invasive first)

1. If the job is alive and progressing: let it finish; notify downstream consumers of the revised ETA rather than restarting. ⚠ Restarting a long batch job loses hours of progress.
2. If failed on a transient error: rerun from the last checkpoint, not from scratch, if the pipeline supports it.
3. If input volume grew permanently: split the job into parallel shards or move its start time earlier — coordinate with the batch-window owner.
4. If a competing workload moved into the window: reschedule the lower-priority one. The SLA-bearing job owns the window.
5. After recovery, backfill any skipped runs in chronological order before resuming the normal schedule.

## Escalation

If the SLA is breached two nights running, or the breach cascades into customer-facing data (stale prices, missing orders), escalate to the data-platform owner with the per-stage timing comparison — repeated breaches are a capacity problem, not an operations problem.
