# High memory usage

Applies to host `hp`, with approximately 15 GiB usable RAM and 4 GiB swap at discovery. CPU-only local inference shares resources with existing production applications.

## Symptoms and possible causes

The server becomes slow, model responses time out, containers are OOM killed, or processes repeatedly exit. Causes include model/context memory demand, application growth, concurrent workloads, or exhausted swap. Linux page cache use alone is not a failure.

## Recommended diagnostics

Start with `memory_usage`: consider available RAM and swap together. Use `system_uptime` for load and `process_list` for bounded process names/memory totals. Process arguments and environment are intentionally omitted. Use `docker_stats` for configured application containers and `docker_inspect` to verify `oom_killed` and restart evidence. Correlate logs before attributing an exit to memory pressure.

The model may run in an AI container outside the CodeDuel container allowlist; do not invent `docker_stats` entries for it. Host measurements can establish pressure while separate operator inspection identifies unexposed workloads.

## Safe remediation

Reduce AI workload concurrency or model/context demand through a reviewed application configuration change. Model selection is configurable, but not an agent write tool. Do not kill arbitrary processes, reboot, disable swap, or alter kernel settings automatically. Current writes are disabled; even an approved CodeDuel restart should follow an evidenced cause and account for interrupted requests/jobs.

## Verification

Observe available RAM and swap after the change, run the intended workload, and confirm affected applications stay healthy without further OOM exits. A single quiet-memory sample does not prove capacity under load. Record any model latency and memory measurements separately from scripted evaluation timing.
