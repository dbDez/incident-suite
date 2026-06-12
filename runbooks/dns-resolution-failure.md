# Runbook — DNS Resolution Failures

**Symptoms:** `Name or service not known`, `getaddrinfo ENOTFOUND`, `SERVFAIL`/`NXDOMAIN` in resolver logs, intermittent connect errors that retry into success, failures clustered on one host or one zone.

**Component:** network / DNS resolvers / service discovery.

## Diagnosis (observe first)

1. Reproduce from an affected host: `dig +short <name>` vs `dig @8.8.8.8 +short <name>` — local resolver problem or authoritative problem?
2. Check TTL and recent DNS changes — did a record change/deletion propagate?
3. Intermittent: resolver cache poisoning/failover flapping, or one resolver in the pool dead (`resolv.conf` rotation)?
4. In Kubernetes: CoreDNS pod health, `ndots` amplification, conntrack exhaustion on the node.

## Remediation (least invasive first)

1. If one resolver is dead: remove it from the pool / restart the local caching daemon (`systemd-resolved`, `dnsmasq`).
2. If a bad record change: revert the record; respect old TTL when estimating recovery.
3. If NXDOMAIN on a just-deleted record other services still use: restore the record first, deprecate properly later.
4. Reduce blast radius: lower TTLs ahead of planned migrations, not during the incident.

## Escalation

Authoritative zone returning SERVFAIL (DNSSEC breakage, expired signatures) → escalate to whoever owns the zone/registrar immediately; local mitigation cannot fix it.
