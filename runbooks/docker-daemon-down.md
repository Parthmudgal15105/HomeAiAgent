# Docker daemon unavailable

Applies to `docker`, the host daemon used by CodeDuel and many existing home-server applications. CodeDuel's rootless judge daemon is separate.

## Symptoms and possible causes

Docker diagnostics report daemon connection failure, multiple application containers are unavailable, or container actions fail. Causes include an inactive daemon, startup failure, disk exhaustion, or diagnostic account/socket access failure. A gateway permission error is not evidence that Docker stopped.

## Recommended diagnostics

Correlate `docker_list` with `service_status` for `docker`. If the service is inactive or failed, read its bounded `journal_logs`. Use `disk_usage` and `memory_usage` when journal evidence indicates storage or memory pressure. If systemd says active but only the gateway cannot query Docker, report an access/diagnostic failure and request host-side inspection rather than diagnosing a daemon outage.

The gateway's list is filtered to configured CodeDuel containers. It does not enumerate every existing production workload and does not inspect `/run/user/1001/docker.sock`.

## Safe remediation

A host Docker restart affects many existing services and may disrupt this AI stack as well. Current policy has no writable systemd targets. Do not expand privileges, reset Docker, prune images/volumes, or restart the daemon automatically. An operator must assess affected workloads and use an approved maintenance procedure. A functioning host daemon does not justify restarting unrelated containers.

## Verification

Check the host daemon active state, relevant container states and health, CodeDuel API readiness, and local/public endpoints. Inspect separate judge runtime evidence when the symptom concerns submissions. Report any diagnostic access failure separately from workload health.
