# Disk full or critically low free space

Applies to host filesystems `/` and `/storage`. Initial discovery found substantial free space; use a current measurement for every incident.

## Symptoms and possible causes

Applications report `ENOSPC`, databases fail writes, Docker cannot create layers, or logs stop. Causes include filesystem capacity, inode exhaustion, growth in logs/data, or a mount-specific problem. Available bytes alone do not diagnose inode exhaustion.

## Recommended diagnostics

Use `disk_usage` with the affected configured path. Deterministic thresholds are below 80% normal, 80–under 90% warning, 90–95% high, and above 95% critical. Correlate `ENOSPC` messages from relevant container or Docker journal logs with the filesystem measured. Compare `/` and `/storage` only when needed.

The current tool reports capacity and bytes, not directory sizes, inode counts, quotas, or open deleted files. Do not identify a particular directory as the cause without separate evidence. Do not assume moving data to `/storage` is safe for the application.

## Safe remediation

Ask an operator to review consumers and retention, create appropriate backups, and approve a specific cleanup. The agent has no delete or prune tool. Never run Docker system prune, remove production volumes, truncate application databases, or delete `/opt/codeduel-data/redis`. Restarting a write-heavy component does not fix full storage.

## Verification

Recheck the affected path, confirm adequate free space, and verify the application's actual readiness/writes. A lower usage percentage alone cannot establish database integrity or processing recovery. Document inode/quota uncertainty if errors persist despite free bytes.
