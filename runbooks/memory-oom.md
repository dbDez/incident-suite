# Runbook — Memory Pressure / OOM Kills

**Symptoms:** `Out of memory: Killed process`, `oom-kill`, services restarting without error logs, swap thrashing, `MemoryError`.

**Component:** host / application memory management.

## Diagnosis (observe first)

1. Confirm the kill and the victim: `dmesg -T | grep -i oom` — note which process and its RSS at kill time.
2. Trend, leak or spike? Check memory graphs over 24h — a sawtooth that climbs to the kill is a leak; a step is a workload change.
3. Check container/cgroup limits vs host memory — was the limit just too low for a legitimate workload?
4. Identify top consumers now: `ps aux --sort=-%mem | head -10`

## Remediation (least invasive first)

1. If a leaking process: restart it now to restore service (buys time, fixes nothing).
2. If a cgroup limit is genuinely undersized: raise the limit one notch with the owner's sign-off. ⚠ Verify host headroom first or you move the OOM to the host level.
3. If a leak: capture a heap snapshot before the next restart so the owner can diagnose.
4. Add a memory alert at 85% of limit so the next event is caught pre-kill.

## Escalation

Repeated OOM kills of the SAME process within 24h → escalate to the service owner with the dmesg evidence and heap snapshot; restarts are no longer an acceptable response.
