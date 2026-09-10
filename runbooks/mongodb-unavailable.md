# MongoDB Atlas unavailable

Applies to `mongodb-atlas`. CodeDuel uses external Atlas cluster `cluster0.etfzpvb.mongodb.net`. There is no deployed local CodeDuel MongoDB container or systemd service.

## Symptoms and possible causes

`codeduel-api-1` and `codeduel-worker-1` may exit with `MongooseServerSelectionError`, readiness may fail, and public API paths may return 502. This was observed before the AI deployment. Possible underlying causes include DNS/SRV resolution, host egress, database availability, network access rules, authentication/TLS configuration, or an incorrect connection setting. A generic driver suggestion about the Atlas IP allowlist does not identify the root cause.

## Recommended diagnostics

Correlate bounded API and worker logs with current container state. Check `http_check` alias `codeduel-api-ready` when the API remains alive. Inspect `network_interfaces` and `route_table`; use allowlisted `ping_host` targets only when host connectivity is in doubt. ICMP failure is inconclusive by itself.

The cluster base name may be an SRV seed without A/AAAA addresses. The current `dns_lookup` resolves ordinary addresses, so its failure alone cannot establish Atlas DNS failure. Actual shard hostnames, SRV queries, authenticated database probes, and Atlas account APIs are outside the current gateway scope. Record this limit rather than inventing results. Do not output connection URI credentials.

## Safe remediation

Ask the operator to inspect the relevant Atlas or application connection setting when additional evidence is required. Preserve `/opt/codeduel/.env` and existing deployment configuration. Do not create/restart a local MongoDB service, alter Atlas access rules without explicit authorization, or repeatedly restart API/worker while the dependency remains unavailable.

## Verification

Require API readiness to succeed, API/worker to remain running and healthy, and fresh logs to stop reporting database failures. The readiness check is an indirect dependency check, not an independent Atlas diagnostic. Public homepage success alone is insufficient.
