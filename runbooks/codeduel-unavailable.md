# CodeDuel unavailable

Applies to service profile `codeduel` on host `hp`. This runbook guides tool selection; its statements are not evidence of a new incident.

## Symptoms and known deployment

`codeduel.online` may show a gateway error, an empty application, or failed API calls. Existing `cloudflared` forwards to the NGINX proxy at `127.0.0.1:8085`. Containers are `codeduel-proxy-1`, `codeduel-frontend-1`, `codeduel-api-1`, `codeduel-worker-1`, and `codeduel-redis-1`. MongoDB is external Atlas. A homepage HTTP 200 does not establish API or submission health.

Discovery on 9 September 2026 found the frontend/proxy/Redis healthy and API/worker already restarting with `MongooseServerSelectionError`. Recheck these conditions; do not treat the baseline as current proof.

## Possible causes and discriminating diagnostics

Use the symptom to select the next check. Compare `http_check` for `https://codeduel.online`, `http://127.0.0.1:8085/healthz` (proxy only), and `codeduel-api-ready` (configured alias to API `/health/ready`). If only the public path fails, inspect `service_status` for `cloudflared`, then its bounded journal. If the local API fails, inspect `codeduel-api-1` and its logs. Follow reported Redis, Atlas, Docker, memory, or storage evidence with the matching runbook. Use `docker_list` to distinguish one failed component from a daemon-wide failure.

## Safe remediation

Present observed causes and uncertainty before proposing changes. Container start/restart requires enabled write policy and a persisted approval for that exact target. Current deployment policy disables writes. Do not replace the existing tunnel service, modify CodeDuel environment secrets, or restart a nonexistent local MongoDB service. Atlas/network remediation may require an operator outside the tool scope.

## Verification

Use the configured `codeduel` dependency health checks: relevant containers, API readiness, tunnel, and public endpoint. Keep the incident open when a dependency still fails. Queue execution requires additional evidence; the current checks do not submit a real judging job.
