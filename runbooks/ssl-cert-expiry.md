# Runbook — TLS/SSL Certificate Expiry

**Symptoms:** `certificate has expired`, `SSL_ERROR_EXPIRED_CERT_ALERT`, `x509: certificate has expired or is not yet valid`, sudden 100% client failures at a clean timestamp, mobile apps failing while curl with `-k` works.

**Component:** edge / load balancer / service-to-service TLS.

## Diagnosis (observe first)

1. Confirm which cert and when it expired: `openssl s_client -connect host:443 -servername host 2>/dev/null | openssl x509 -noout -dates`
2. Identify scope: edge cert (all clients) vs internal mTLS cert (service pairs only)?
3. Check why renewal failed: certbot/ACME logs, DNS-01 challenge records, renewal cron status.

## Remediation (least invasive first)

1. Renew/reissue the cert now (ACME: `certbot renew --force-renewal` for the affected cert only) and reload the terminating proxy — reload, not restart, keeps connections.
2. If automation is broken, install a manually issued cert as a stopgap and ticket the automation fix.
3. Verify full chain after deploy (`openssl verify` / SSL Labs) — a missing intermediate looks fixed in browsers but still fails older clients.
4. Fix the alert gap: add expiry monitoring at 30/14/7 days.

## Escalation

If the expired cert is pinned in a shipped mobile app → escalate immediately to the app team; server-side renewal alone will not restore those clients.
