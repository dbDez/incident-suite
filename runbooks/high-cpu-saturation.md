# Runbook — High CPU Saturation

**Symptoms:** sustained CPU above 90%, load average far above core count, request latency climbing without error spikes, autoscaler thrashing.

**Component:** host / application compute.

## Diagnosis (observe first)

1. Which process: `top -o %CPU` / `pidstat 1 5` — one hot process or systemic?
2. Inside the process: thread dump / `py-spy top` / profiler — busy loop, regex backtracking, GC storm, or genuine load?
3. Correlate with traffic: did request rate rise to match, or is CPU up at flat traffic (= regression)?
4. Check recent deploys and cron windows.

## Remediation (least invasive first)

1. If genuine load: scale out horizontally before touching the code path.
2. If a single runaway worker: recycle just that worker/pod.
3. If a deploy regression at flat traffic: roll back. ⚠ Confirm last known-good tag.
4. If a batch job is stealing cycles from a latency-sensitive service: nice/cgroup-limit the batch job or reschedule it off-peak.

## Escalation

CPU pegged with no matching traffic increase and no recent deploy → profile and escalate to the service owner with the flame graph; do not just add replicas to hide a regression.
