# Redis unavailable

Applies to `redis`, the CodeDuel `codeduel-redis-1` container. It runs password-protected Redis 7.4 on private `codeduel_backend:6379`; its data is under `/opt/codeduel-data/redis`. This is separate from the existing Nextcloud Redis container.

## Symptoms and possible causes

BullMQ jobs stall, the worker reports Redis connection/authentication errors, or application readiness fails. Causes may include an exited container, unhealthy Redis, resource pressure, or application connection configuration. An authentication error and an unavailable listener are different findings.

## Recommended diagnostics

Inspect `codeduel-redis-1` for state, native authenticated health, exit code, and restart count. Read bounded Redis and `codeduel-worker-1` logs to correlate errors. Use `docker_list` or `service_status` for `docker` if several containers disappear. Check `disk_usage` for `/` and `/storage` when logs show write failures; check `memory_usage` when the container is OOM killed.

Do not call host `port_check` on 6379: this deployment has no such allowlisted host target. A missing host listener is expected for private Redis. Never expose a Redis password, inspect full container environment, or substitute the unrelated Nextcloud Redis.

## Safe remediation

An evidenced stopped Redis may justify an approved start; a restart can interrupt both API and worker and requires an enabled write policy. Writes are currently disabled. Correct an evidenced host resource issue before repeatedly restarting. Do not flush databases, clear queues, delete persistence files, or remove Redis volumes.

## Verification

Require the native Redis container health check to pass. Then check dependent worker/API health and fresh logs. Queue completion is a separate application check and is not currently automated by this agent.
