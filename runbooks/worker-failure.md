# CodeDuel worker failure

Applies to `codeduel-worker-1`. It depends on private Redis/BullMQ, external MongoDB Atlas, and a rootless Docker judge at `/run/user/1001/docker.sock`. Initial discovery found repeated worker exits with database connection errors before the AI deployment.

## Symptoms and possible causes

Worker restarts or exits, submissions remain queued, results are missing, or judge jobs fail. Distinguish startup dependency failure from a worker that runs but cannot execute jobs. Causes include Atlas connectivity, Redis, application errors, judge access, OOM termination, or exhausted storage.

## Recommended diagnostics

Inspect worker state, exit code, restart count, health, and `oom_killed`; read bounded fresh worker logs. Follow explicit dependency errors with the Atlas or Redis runbook. Compare API logs when both components fail together. If job-execution logs mention a Docker socket/runtime failure, record the exact symptom while noting that host Docker tools do not directly query the separate rootless judge daemon.

Use disk/memory diagnostics when resource evidence warrants them. A healthy host daemon or a worker process existing is insufficient proof that a judge job can run. A gateway permission failure should remain a diagnostic limitation.

## Safe remediation

Restore the evidenced dependency first. A specific approved worker start/restart may be appropriate after dependency recovery, with potential in-flight job effects explained. Current write policy is disabled. Do not recreate the judge daemon, change socket ownership, broaden Docker privileges, remove Redis jobs, or change production worker configuration automatically.

## Verification

Require stable worker running/healthy state, healthy dependencies, and fresh logs without recurring startup failures. API readiness and public service checks cover adjacent components. End-to-end submission completion needs separate operator evidence because the agent currently has no queue-count or test-submission tool.
