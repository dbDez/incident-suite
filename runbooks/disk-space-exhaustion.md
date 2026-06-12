# Runbook — Disk Space Exhaustion

**Symptoms:** `No space left on device`, `disk usage above 90%`, failed writes, databases switching to read-only, log rotation failures.

**Component:** host / storage.

## Diagnosis (observe first)

1. Which mount: `df -h` — confirm WHICH filesystem is full (root vs data vs logs).
2. What's growing: `du -xh --max-depth=2 /var | sort -h | tail -20`
3. Check for deleted-but-open files holding space: `lsof +L1 | grep -i deleted`
4. Check log rotation health: did rotation stop, or did a service start logging at DEBUG?

## Remediation (least invasive first)

1. Compress or move rotated logs older than 7 days to archive storage.
2. Truncate (don't delete) the active runaway log: `truncate -s 0 <file>` — deleting an open file does NOT free space until the process restarts.
3. Clear package-manager and container-image caches (`docker system prune` ⚠ confirms what's removed first; never `-a --volumes` on a DB host).
4. Restart the process holding deleted file handles (frees phantom space).
5. Fix the source: cap log level, fix rotation config, add disk-usage alerting at 80%.

## Escalation

If a database host hit 100%, verify data integrity after space is freed BEFORE declaring resolved — escalate to the DBA.
