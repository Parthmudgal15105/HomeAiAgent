"""Typed, allowlisted diagnostics for the host; never model-generated commands."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import psutil
from pydantic import BaseModel, ConfigDict, Field

from .config import GatewayConfig, utilization_severity
from .safety import ToolError, http_probe, resolve_addresses, run_command, safe_address


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class NoArguments(Arguments):
    pass


class HostArguments(Arguments):
    hostname: str = Field(min_length=1, max_length=253)


class PingArguments(HostArguments):
    count: int = Field(default=2, ge=1, le=4)


class HTTPArguments(Arguments):
    url: str = Field(min_length=1, max_length=2048)


class ContainerArguments(Arguments):
    container: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class ContainerLogsArguments(ContainerArguments):
    lines: int = Field(default=100, ge=1, le=500)


class ServiceArguments(Arguments):
    service: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class JournalArguments(ServiceArguments):
    lines: int = Field(default=100, ge=1, le=500)


class DiskArguments(Arguments):
    path: str = Field(default="/", max_length=1024)


class ProcessArguments(Arguments):
    limit: int = Field(default=20, ge=1, le=100)


class PortArguments(Arguments):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)


class EventsArguments(Arguments):
    minutes: int = Field(default=10, ge=1, le=60)


@dataclass
class ToolDefinition:
    name: str
    description: str
    arguments: type[Arguments]
    handler: Callable[..., dict[str, Any]]
    risk_level: str = "READ_ONLY"


class DiagnosticTools:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.definitions: dict[str, ToolDefinition] = {}
        specs = [
            ("dns_lookup", "Resolve a configured infrastructure hostname to A/AAAA addresses.", HostArguments),
            ("ping_host", "Send up to four ICMP probes to a configured host; blocked ICMP does not prove an outage.", PingArguments),
            ("http_check", "GET an exact configured URL or container endpoint alias; redirects are never followed.", HTTPArguments),
            ("docker_list", "List status of configured containers, including stopped containers.", NoArguments),
            ("docker_inspect", "Read a container's state, image, restart count, ports and networks; environment and command are omitted.", ContainerArguments),
            ("docker_logs", "Read bounded recent container logs, with secrets redacted.", ContainerLogsArguments),
            ("service_status", "Read selected systemd unit state properties without journal secrets.", ServiceArguments),
            ("journal_logs", "Read bounded recent journal entries for an allowlisted systemd unit.", JournalArguments),
            ("network_interfaces", "Read host network interface state and IP addresses.", NoArguments),
            ("route_table", "Read structured IPv4 and IPv6 routes.", NoArguments),
            ("memory_usage", "Read normalized host RAM and swap usage with deterministic severity.", NoArguments),
            ("disk_usage", "Read filesystem capacity for a configured path with deterministic severity.", DiskArguments),
            ("system_uptime", "Read uptime, boot time, CPU load and available CPU count.", NoArguments),
            ("process_list", "Read bounded process names and memory use; command arguments and environment are omitted.", ProcessArguments),
            ("port_check", "Attempt a TCP connection to one explicitly configured host/port pair.", PortArguments),
            ("tailscale_status", "Read structured Tailscale health and connection state, without node keys.", NoArguments),
            ("cloudflared_status", "Read the allowlisted Cloudflare Tunnel systemd state.", NoArguments),
            ("docker_stats", "Read one resource-usage sample for configured running containers.", NoArguments),
            ("recent_docker_events", "Read bounded recent lifecycle events for configured containers.", EventsArguments),
        ]
        for name, description, arguments in specs:
            self.definitions[name] = ToolDefinition(name, description, arguments, getattr(self, name))
        if config.writes_enabled:
            if config.write_containers:
                self.definitions["restart_container"] = ToolDefinition("restart_container", "Restart an approved container; causes brief interruption. Requires a fresh signed human approval.", ContainerArguments, self.restart_container, "LOW_RISK_WRITE")
                self.definitions["start_container"] = ToolDefinition("start_container", "Start an approved stopped container. Requires a fresh signed human approval.", ContainerArguments, self.start_container, "LOW_RISK_WRITE")
            if config.write_services:
                self.definitions["restart_service"] = ToolDefinition("restart_service", "Restart an approved service using host policy; requires a fresh signed human approval.", ServiceArguments, self.restart_service, "LOW_RISK_WRITE")

    def metadata(self) -> list[dict[str, Any]]:
        tools = []
        for definition in self.definitions.values():
            schema = definition.arguments.model_json_schema()
            properties = schema.get("properties", {})
            for key in ("hostname",):
                if key in properties:
                    properties[key]["enum"] = self.config.hosts
            if "container" in properties:
                properties["container"]["enum"] = self.config.write_containers if definition.risk_level != "READ_ONLY" else self.config.containers
            if "service" in properties:
                properties["service"]["enum"] = self.config.write_services if definition.risk_level != "READ_ONLY" else self.config.services
            if "url" in properties:
                properties["url"]["enum"] = self.config.http_urls + list(self.config.container_http)
            if "path" in properties:
                properties["path"]["enum"] = self.config.disk_paths
            if definition.name == "port_check":
                schema["anyOf"] = [{"properties": {"host": {"const": item.host}, "port": {"const": item.port}}} for item in self.config.tcp_targets] or [{"not": {}}]
            tools.append({"name": definition.name, "description": definition.description, "risk_level": definition.risk_level, "parameters": schema})
        return tools

    def command(self, argv: list[str], **kwargs: Any) -> Any:
        return run_command(argv, timeout=kwargs.pop("timeout", self.config.command_timeout_seconds), max_bytes=self.config.max_output_bytes, **kwargs)

    @staticmethod
    def require(value: str, allowed: list[str], category: str) -> None:
        if value not in allowed:
            raise ToolError(f"{category} is not allowlisted")

    def validate_scope(self, tool: str, arguments: dict[str, Any]) -> None:
        """Validate before consuming approval or invoking any command."""
        if "hostname" in arguments:
            self.require(arguments["hostname"], self.config.hosts, "Host")
        if "container" in arguments:
            targets = self.config.write_containers if tool in ("restart_container", "start_container") else self.config.containers
            self.require(arguments["container"], targets, "Container")
        if "service" in arguments:
            targets = self.config.write_services if tool == "restart_service" else self.config.services
            self.require(arguments["service"], targets, "Service")
        if "url" in arguments:
            self.require(arguments["url"], self.config.http_urls + list(self.config.container_http), "HTTP URL")
        if "path" in arguments:
            self.require(arguments["path"], self.config.disk_paths, "Filesystem path")
        if tool == "port_check" and (arguments["host"], arguments["port"]) not in {(item.host, item.port) for item in self.config.tcp_targets}:
            raise ToolError("TCP host/port pair is not allowlisted")

    def dns_lookup(self, hostname: str) -> dict[str, Any]:
        self.require(hostname, self.config.hosts, "Host")
        try:
            return {"hostname": hostname, "resolved": True, "addresses": resolve_addresses(hostname)}
        except ToolError as exc:
            return {"hostname": hostname, "resolved": False, "addresses": [], "error": str(exc)}

    def ping_host(self, hostname: str, count: int = 2) -> dict[str, Any]:
        self.require(hostname, self.config.hosts, "Host")
        address = resolve_addresses(hostname)[0]
        ip = ipaddress.ip_address(address)
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ToolError("Ping destination address is prohibited")
        result = self.command(["ping", "-n", "-c", str(count), "-W", "1", "-w", "5", address], check=False)
        loss = re.search(r"([\d.]+)% packet loss", result.stdout)
        rtt = re.search(r"(?:rtt|round-trip).*?=\s*([\d.]+)/([\d.]+)/([\d.]+)", result.stdout)
        return {"hostname": hostname, "address": address, "reachable": result.returncode == 0, "packet_loss_percent": float(loss.group(1)) if loss else None, "rtt_avg_ms": float(rtt.group(2)) if rtt else None, "note": "ICMP may be blocked even when the service works", "error": result.stderr[:500] or None}

    def http_check(self, url: str) -> dict[str, Any]:
        if url in self.config.container_http:
            endpoint = self.config.container_http[url]
            item = self.docker_inspect(endpoint.container)
            networks = item["networks"]
            if endpoint.network:
                networks = [network for network in networks if network["name"] == endpoint.network]
            addresses = [network["ip_address"] for network in networks if network.get("ip_address")]
            if not addresses:
                return {"url": url, "reachable": False, "healthy": False, "error": "Configured container has no address in its expected network"}
            address = addresses[0]
            if not safe_address(address, container_target=True):
                raise ToolError("Discovered container address is outside its permitted private network scope")
            target = f"http://{address}:{endpoint.port}{endpoint.path}"
            result = http_probe(target, address=address, container_target=True)
            result["url"] = url
            result["container"] = endpoint.container
            return result
        self.require(url, self.config.http_urls, "HTTP URL")
        return http_probe(url)

    def docker_list(self) -> dict[str, Any]:
        # Exclude labels and executable arguments before capture. Compose labels
        # can consume the output budget before all container rows are returned.
        projection = '{"ID":{{json .ID}},"Names":{{json .Names}},"Image":{{json .Image}},"State":{{json .State}},"Status":{{json .Status}},"Ports":{{json .Ports}}}'
        result = self.command(["docker", "container", "ls", "--all", "--no-trunc", "--format", projection])
        containers = []
        for line in result.stdout.splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                if result.truncated:
                    continue
                raise ToolError("Docker did not return structured container data")
            if item.get("Names") in self.config.containers:
                containers.append({"id": item.get("ID"), "name": item.get("Names"), "image": item.get("Image"), "state": item.get("State"), "status": item.get("Status"), "ports": item.get("Ports")})
        found = {item["name"] for item in containers}
        unobserved = sorted(set(self.config.containers) - found)
        return {"containers": containers, "missing_configured_containers": [] if result.truncated else unobserved,
                "unobserved_configured_containers": unobserved if result.truncated else [], "truncated": result.truncated}

    def docker_inspect(self, container: str) -> dict[str, Any]:
        self.require(container, self.config.containers, "Container")
        # Go-template projection ensures secrets never enter this process from
        # environment, labels, executable arguments, mounts or health output.
        projection = '{"name":{{json .Name}},"image":{{json .Config.Image}},"state":{"status":{{json .State.Status}},"running":{{json .State.Running}},"restarting":{{json .State.Restarting}},"oom_killed":{{json .State.OOMKilled}},"exit_code":{{json .State.ExitCode}},"started_at":{{json .State.StartedAt}},"finished_at":{{json .State.FinishedAt}}},"restart_count":{{json .RestartCount}},"health":{{if .State.Health}}{{json .State.Health.Status}}{{else}}null{{end}},"ports":{{json .NetworkSettings.Ports}},"networks":{{json .NetworkSettings.Networks}}}'
        result = self.command(["docker", "container", "inspect", "--format", projection, "--", container])
        if result.truncated:
            raise ToolError("Container state exceeds diagnostic output limit")
        item = json.loads(result.stdout)
        item["name"] = item["name"].lstrip("/")
        item["networks"] = [{"name": name, "ip_address": network.get("IPAddress"), "gateway": network.get("Gateway")} for name, network in item.get("networks", {}).items()]
        return item

    def docker_logs(self, container: str, lines: int = 100) -> dict[str, Any]:
        self.require(container, self.config.containers, "Container")
        result = self.command(["docker", "container", "logs", "--timestamps", "--tail", str(lines), "--", container], check=False)
        text = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0 and not result.truncated:
            raise ToolError(text[:2000] or "Container logs unavailable")
        return {"container": container, "lines": text.splitlines()[-lines:], "truncated": result.truncated}

    def service_status(self, service: str) -> dict[str, Any]:
        self.require(service, self.config.services, "Service")
        properties = "Id,LoadState,ActiveState,SubState,MainPID,Result,ExecMainCode,ExecMainStatus,NRestarts,ActiveEnterTimestamp,UnitFileState"
        result = self.command(["systemctl", "show", "--no-pager", "--property", properties, "--", service])
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        return {"service": service, "state": values.get("ActiveState", "unknown"), "substate": values.get("SubState"), "loaded": values.get("LoadState") == "loaded", "properties": values}

    def journal_logs(self, service: str, lines: int = 100) -> dict[str, Any]:
        self.require(service, self.config.services, "Service")
        result = self.command(["journalctl", "--unit", service, "--lines", str(lines), "--no-pager", "--output", "json", "--output-fields", "__REALTIME_TIMESTAMP,PRIORITY,MESSAGE,_SYSTEMD_UNIT"])
        entries = []
        for line in result.stdout.splitlines():
            try:
                item = json.loads(line)
                entries.append({"timestamp_us": item.get("__REALTIME_TIMESTAMP"), "priority": item.get("PRIORITY"), "message": item.get("MESSAGE"), "unit": item.get("_SYSTEMD_UNIT")})
            except json.JSONDecodeError:
                if not result.truncated:
                    raise ToolError("Journal did not return structured output")
        return {"service": service, "entries": entries[-lines:], "truncated": result.truncated}

    def network_interfaces(self) -> dict[str, Any]:
        addresses, stats = psutil.net_if_addrs(), psutil.net_if_stats()
        return {"interfaces": [{"name": name, "state": "UP" if stats.get(name) and stats[name].isup else "DOWN", "mtu": stats[name].mtu if name in stats else None, "addresses": [{"address": address.address, "netmask": address.netmask, "family": "IPv6" if address.family == socket.AF_INET6 else "IPv4"} for address in items if address.family in (socket.AF_INET, socket.AF_INET6)]} for name, items in addresses.items()][:100]}

    def route_table(self) -> dict[str, Any]:
        routes = []
        for family in ("-4", "-6"):
            result = self.command(["ip", "-json", family, "route", "show"], timeout=3)
            if result.truncated:
                raise ToolError("Route table exceeds diagnostic output limit")
            routes.extend({"family": family[1:], **route} for route in json.loads(result.stdout))
        return {"routes": routes[:250]}

    def memory_usage(self) -> dict[str, Any]:
        ram, swap = psutil.virtual_memory(), psutil.swap_memory()
        return {"total_bytes": ram.total, "available_bytes": ram.available, "used_bytes": ram.total - ram.available, "used_percent": ram.percent, "severity": utilization_severity(ram.percent), "swap": {"total_bytes": swap.total, "used_bytes": swap.used, "used_percent": swap.percent}}

    def disk_usage(self, path: str = "/") -> dict[str, Any]:
        self.require(path, self.config.disk_paths, "Filesystem path")
        disk = psutil.disk_usage(path)
        return {"path": path, "total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free, "used_percent": disk.percent, "severity": utilization_severity(disk.percent)}

    def system_uptime(self) -> dict[str, Any]:
        boot = psutil.boot_time()
        try:
            uptime = float(Path("/proc/uptime").read_text().split()[0])
        except (OSError, ValueError):
            uptime = max(0, time.time() - boot)
        return {"uptime_seconds": round(uptime, 1), "boot_timestamp": boot, "load_average": list(psutil.getloadavg()), "cpu_count": psutil.cpu_count(), "cpu_count_physical": psutil.cpu_count(logical=False)}

    def process_list(self, limit: int = 20) -> dict[str, Any]:
        processes = []
        for process in psutil.process_iter(["pid", "name", "status", "memory_percent", "username"]):
            try:
                values = process.info
                processes.append({"pid": values["pid"], "name": values["name"], "status": values["status"], "memory_percent": round(values.get("memory_percent") or 0, 3), "user": values.get("username")})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.sort(key=lambda item: item["memory_percent"], reverse=True)
        return {"processes": processes[:limit], "total_processes_seen": len(processes), "arguments_omitted": True}

    def port_check(self, host: str, port: int) -> dict[str, Any]:
        self.validate_scope("port_check", {"host": host, "port": port})
        addresses = resolve_addresses(host)
        start = time.monotonic()
        # An exact host/port pair is administrator-authorized for private services.
        address = addresses[0]
        ip = ipaddress.ip_address(address)
        if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
            raise ToolError("TCP destination address is prohibited")
        sock = socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        try:
            sock.connect((address, port))
            return {"host": host, "port": port, "address": address, "open": True, "latency_ms": round((time.monotonic() - start) * 1000)}
        except OSError as exc:
            return {"host": host, "port": port, "address": address, "open": False, "latency_ms": round((time.monotonic() - start) * 1000), "error": str(exc)[:500]}
        finally:
            sock.close()

    def tailscale_status(self) -> dict[str, Any]:
        result = self.command(["tailscale", "status", "--json"])
        if result.truncated:
            raise ToolError("Tailscale status exceeds diagnostic output limit")
        values = json.loads(result.stdout)
        peers = values.get("Peer") or {}
        return {"backend_state": values.get("BackendState"), "tailscale_ips": values.get("TailscaleIPs", []), "health": values.get("Health", []), "self": {key: (values.get("Self") or {}).get(key) for key in ("HostName", "Online", "OS", "TailscaleIPs")}, "peers": [{key: peer.get(key) for key in ("HostName", "Online", "Active", "TailscaleIPs")} for peer in peers.values()][:50]}

    def cloudflared_status(self) -> dict[str, Any]:
        return self.service_status("cloudflared")

    def docker_stats(self) -> dict[str, Any]:
        if not self.config.containers:
            return {"containers": []}
        # Stopped containers emit zero values or no sample depending on Docker.
        result = self.command(["docker", "container", "stats", "--no-stream", "--format", "{{json .}}", "--", *self.config.containers], check=False)
        items = []
        for line in result.stdout.splitlines():
            try:
                row = json.loads(line)
                items.append({"name": row.get("Name"), "cpu_percent": row.get("CPUPerc"), "memory_usage": row.get("MemUsage"), "memory_percent": row.get("MemPerc"), "network_io": row.get("NetIO"), "block_io": row.get("BlockIO"), "pids": row.get("PIDs")})
            except json.JSONDecodeError:
                continue
        return {"containers": items, "truncated": result.truncated, "error": result.stderr[:500] or None}

    def recent_docker_events(self, minutes: int = 10) -> dict[str, Any]:
        now = int(time.time())
        filters = ["--filter", "type=container"]
        for container in self.config.containers:
            filters.extend(["--filter", "container=" + container])
        if not self.config.containers:
            return {"events": []}
        result = self.command(["docker", "events", "--since", str(now - minutes * 60), "--until", str(now), "--format", "{{json .}}", *filters])
        events = []
        for line in result.stdout.splitlines():
            try:
                item = json.loads(line)
                actor = item.get("Actor", {})
                events.append({"action": item.get("Action"), "time": item.get("time"), "container_id": actor.get("ID"), "name": actor.get("Attributes", {}).get("name")})
            except json.JSONDecodeError:
                continue
        return {"events": events[-100:], "truncated": result.truncated}

    def restart_container(self, container: str) -> dict[str, Any]:
        self.require(container, self.config.write_containers, "Write container")
        self.command(["docker", "container", "restart", "--time", "5", "--", container], timeout=20)
        return {"operation": "restart_container", "container": container, "execution_succeeded": True, "state": self.docker_inspect(container), "verification_required": True}

    def start_container(self, container: str) -> dict[str, Any]:
        self.require(container, self.config.write_containers, "Write container")
        self.command(["docker", "container", "start", "--", container], timeout=15)
        return {"operation": "start_container", "container": container, "execution_succeeded": True, "state": self.docker_inspect(container), "verification_required": True}

    def restart_service(self, service: str) -> dict[str, Any]:
        self.require(service, self.config.write_services, "Write service")
        # No sudo. A separately reviewed host policy must grant this exact unit;
        # absent such a policy systemd denies the request without prompting.
        self.command(["systemctl", "--no-ask-password", "restart", "--", service], timeout=20)
        return {"operation": "restart_service", "service": service, "execution_succeeded": True, "state": self.service_status(service), "verification_required": True}
