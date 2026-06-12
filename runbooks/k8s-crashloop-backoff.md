# Runbook — Kubernetes CrashLoopBackOff

**Symptoms:** pod restarts climbing, `CrashLoopBackOff` in `kubectl get pods`, service intermittently underprovisioned as replicas cycle.

**Component:** orchestration / application startup.

## Diagnosis (observe first)

1. Why is it dying: `kubectl logs <pod> --previous` (the PREVIOUS container's logs — the current one hasn't failed yet).
2. Exit code via `kubectl describe pod`: 137 = OOMKilled (memory limit), 1/2 = app error, 126/127 = bad command/image.
3. Probe-induced? Liveness probe timeout shorter than startup time kills healthy-but-slow starts — check probe config vs measured startup.
4. Config/secret dependency: missing ConfigMap/Secret/env var fails fast at boot.

## Remediation (least invasive first)

1. OOMKilled: raise the memory limit one notch OR fix the limit/request ratio. ⚠ Verify node headroom.
2. Probe-induced: add/lengthen `startupProbe` rather than disabling liveness.
3. Bad release: `kubectl rollout undo deployment/<d>` — fastest restore; investigate from the rolled-back state.
4. Missing config: restore the ConfigMap/Secret; add a CI check that manifests reference existing keys.

## Escalation

If the previous ReplicaSet is also crashing (rollback target broken), this is not a deploy issue — escalate to the platform team with `--previous` logs and exit codes.
