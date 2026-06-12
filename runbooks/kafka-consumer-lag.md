# Runbook — Kafka Consumer Lag Growth

**Symptoms:** consumer group lag climbing monotonically, downstream data freshness alerts, rebalance storms (`Attempt to heartbeat failed since group is rebalancing`), processing timestamps drifting behind produce timestamps.

**Component:** messaging / stream processing.

## Diagnosis (observe first)

1. Quantify: `kafka-consumer-groups --describe --group <g>` — lag per partition; is it all partitions (slow consumer) or one (hot key / stuck partition)?
2. Producer side: did input rate spike (campaign, backfill) or is consumer throughput down?
3. Consumer health: processing time per record, error/retry loops, GC pauses, rebalance frequency.
4. Check for a poison message: same offset failing repeatedly.

## Remediation (least invasive first)

1. If throughput-bound: scale consumers up to (not beyond) partition count.
2. If a poison message: log it to a dead-letter topic and advance past the offset. ⚠ Record the skipped offset; data owner must reprocess.
3. If rebalance storm: stabilise membership (raise `max.poll.interval.ms` / fix slow `poll()` loops) before scaling — adding consumers during a storm makes it worse.
4. If input spike is temporary: let lag drain; alert on ETA, not absolute lag.

## Escalation

Lag implies data-loss risk if retention expires before catch-up: compare drain ETA vs topic retention — if ETA exceeds retention, escalate immediately and extend retention.
