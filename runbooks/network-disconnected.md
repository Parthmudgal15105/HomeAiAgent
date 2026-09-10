# Host network disconnected or Wi-Fi blocked

Applies to host `hp`. Discovery found `wlo1` at `192.168.1.252`, default gateway `192.168.1.1`, and Tailscale at `100.98.193.60`. Addresses can change; use current results.

## Symptoms and possible causes

Multiple external services fail, DNS stops working, Cloudflare disconnects, or Tailscale loses access. Causes include an interface down, missing address/route, gateway failure, DNS problems, wireless link loss, or a blocked Wi-Fi radio. A previous RF-kill incident is guidance only.

## Recommended diagnostics

Use `network_interfaces` and `route_table` to establish interface, address, and default-route state. Choose `ping_host` with `hostname` `192.168.1.1` or `1.1.1.1` only when useful; ICMP may be blocked, so correlate other checks. Compare allowlisted public HTTP or DNS checks to distinguish DNS failure from wider connectivity loss.

Production `network_interfaces` currently reports interface state/addresses, not rfkill switch state. The journal allowlist contains `docker`, `cloudflared`, `tailscaled`, and `ssh`; do not invent a NetworkManager or networkd diagnostic. A down Wi-Fi interface alone does not prove airplane mode. RF-kill requires additional local-console evidence; the synthetic RF-kill evaluation is not live evidence.

## Safe remediation

Do not toggle interfaces, restart networking, alter routes/firewalls, disable Tailscale, or reboot remotely. These changes can remove SSH and the agent itself. Request a local console when physical wireless, airplane mode, or cable checks are needed. Preserve the existing network configuration until a specific cause is established.

## Verification

Require a usable address/default route, gateway and external reachability, then the affected services. Tailscale needs a peer-side connection check. If remote access was lost, obtain new evidence after the trusted connection returns.
