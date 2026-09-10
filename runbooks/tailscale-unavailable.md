# Tailscale unavailable

Applies to `tailscale` on host `hp`, private address `100.98.193.60`. Tailscale provides the remote administrative path and intended private AI web access.

## Symptoms and possible causes

The private server address becomes unreachable, the AI web UI cannot load, or peer connectivity fails. Possible causes include host power/network loss, an inactive `tailscaled`, peer-side connectivity, or a Tailscale connectivity/authentication issue. Public CodeDuel availability and Tailscale availability are separate signals.

## Recommended diagnostics

If the agent remains accessible through another trusted path, inspect `tailscale_status` and `service_status` for `tailscaled`, then its bounded journal if useful. Check `network_interfaces`, `route_table`, and allowlisted gateway/internet probes to distinguish host network loss from a Tailscale-specific issue. Use `port_check` only for configured SSH targets; it does not authenticate or prove a full SSH session works.

If Tailscale is the only route to the host and it is already down, the remote agent may be unreachable too. Report the observation gap. Do not invent local diagnostics that could not execute.

## Safe remediation

Do not restart `tailscaled`, log out, reauthenticate, rotate node keys, or alter routes/firewall policy from the agent. Current write-service allowlist is empty. Use an available local console or another established administrator path for recovery; preserve SSH and the existing Tailscale configuration.

## Verification

Confirm daemon state, the expected interface/address, and an actual connection from an authorized peer to the private endpoint. Daemon activity alone does not demonstrate peer reachability. The configured automated health check is limited to service state; document additional operator evidence when claiming end-to-end recovery.
