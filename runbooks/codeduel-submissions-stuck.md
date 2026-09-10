# CodeDuel submissions stuck

Applies to `codeduel` or `codeduel-worker`. The worker uses BullMQ, private Redis, external MongoDB Atlas, and a separate rootless judge Docker socket at `/run/user/1001/docker.sock`.

## Symptoms and possible causes

The frontend loads but submissions remain queued, results never appear, or processing repeatedly fails. Possible causes include worker restarts, Redis connectivity, Atlas failures, judge runtime failure, or host resource pressure. A healthy homepage does not eliminate these causes.

## Recommended diagnostics

Start with `docker_inspect` and bounded `docker_logs` for `codeduel-worker-1`; they discriminate between queue connection failure, database startup failure, and judging errors. Inspect `codeduel-redis-1` if logs implicate BullMQ or Redis. Its native authenticated health check is the available Redis probe; Redis has no configured host TCP target. Inspect `codeduel-api-1` and `http_check` alias `codeduel-api-ready` if API persistence fails. Investigate disk/memory only when the evidence suggests resource exhaustion.

The host `service_status("docker")` and application Docker tools inspect the host daemon. They do not directly verify the separate rootless judge daemon. Worker logs can suggest a judge problem, but do not prove its exact underlying cause. A database error can prevent the worker from reaching the queue or judge code at all.

## Safe remediation

Repair the evidenced dependency before restarting the worker. Any allowlisted container change needs an enabled policy and an exact approved action; writes are currently disabled. Do not flush Redis, delete jobs, remove volumes, or recreate the judge socket. Investigate Atlas access with an operator when current tools cannot discriminate the cause.

## Verification

Check Redis native health, worker running/healthy, absence of repeated dependency failures in fresh logs, and API readiness. A normal test submission and observed completion would establish end-to-end recovery, but there is no current agent tool to create or count queue jobs. Report that gap explicitly and do not infer queue progress from a running worker alone.
