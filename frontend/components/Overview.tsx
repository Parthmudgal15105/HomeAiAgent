"use client";

import { Activity, Box, Clock3, Cpu, Database, HardDrive, Network, RefreshCw, ShieldCheck, Wifi } from "lucide-react";
import { duration, serviceLabel, type ServiceMap, type QuickAction, QUICK_ACTIONS } from "../lib/dashboard";

type Result = Record<string, unknown>;
export type GatewaySignal = { ok: boolean; result?: Result; error?: string };
export type OverviewData = {
  collected_at: string;
  health: "Healthy" | "Warning" | "Critical";
  signals: Record<string, GatewaySignal>;
  services: ServiceMap;
};
type Container = { name?: string; state?: string; status?: string; image?: string; health?: string };

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
function percent(value: unknown): string {
  const n = number(value);
  return n == null ? "Unavailable" : `${Math.round(n)}%`;
}
function bytes(value: unknown): string {
  const n = number(value);
  return n == null ? "—" : `${(n / 1024 ** 3).toFixed(1)} GiB`;
}
function statusClass(status: string): string {
  return ["Healthy", "Running", "active", "healthy"].includes(status) ? "Healthy"
    : ["Critical", "Exited", "exited", "restarting", "unhealthy", "failed", "inactive"].includes(status) ? "Critical" : "Warning";
}
function Status({ children }: { children: string }) {
  return <span className={`pill ${statusClass(children)}`}>{children}</span>;
}
function Metric({ title, value, caption, icon, used }: { title: string; value: string; caption: string; icon: React.ReactNode; used?: number | null }) {
  return <section className="panel resource-card"><div className="resource-label">{icon}<span>{title}</span></div><strong>{value}</strong><p className="meta">{caption}</p>{used != null && <div className="meter" role="meter" aria-label={title} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(used)}><span style={{ width: `${Math.min(100, Math.max(0, used))}%` }} className={used > 95 ? "critical" : used >= 80 ? "warning" : ""} /></div>}</section>;
}

export function QuickActions({ onSelect }: { onSelect: (id: QuickAction) => void }) {
  return <div className="quick-actions" aria-label="Quick investigations">{QUICK_ACTIONS.map(action => <button key={action.id} onClick={() => onSelect(action.id)}><Activity size={15} />{action.label}</button>)}</div>;
}

export default function Overview({ data, loading, error, refresh, onQuickAction, onService }: {
  data: OverviewData | null;
  loading: boolean;
  error: string;
  refresh: () => void;
  onQuickAction: (id: QuickAction) => void;
  onService: (id: string) => void;
}) {
  const signals = data?.signals || {};
  const result = (key: string): Result => signals[key]?.ok ? signals[key].result || {} : {};
  const memory = result("memory_usage"), uptime = result("system_uptime"), tailscale = result("tailscale_status"), cloudflare = result("cloudflared_status");
  const disks = Object.entries(signals).filter(([key]) => key.startsWith("disk_usage"));
  const containers = (Array.isArray(result("docker_list").containers) ? result("docker_list").containers : []) as Container[];
  const load = Array.isArray(uptime.load_average) ? number(uptime.load_average[0]) : null;
  const cpuPercent = number(uptime.cpu_percent);
  const tailSelf = tailscale.self && typeof tailscale.self === "object" ? tailscale.self as Result : {};
  const tailState = typeof tailscale.backend_state === "string" ? tailscale.backend_state : "Unavailable";
  const cloudState = typeof cloudflare.state === "string" ? cloudflare.state : typeof cloudflare.active_state === "string" ? cloudflare.active_state : "Unavailable";
  const services = Object.entries(data?.services || {});
  const stale = Boolean(data?.collected_at && Date.now() - Date.parse(data.collected_at) > 120000);
  return <>
    <div className="titleline"><div><div className="eyebrow">HOST SNAPSHOT</div><h1>Server overview</h1><p className="muted">Current resources, connectivity, and configured applications.</p></div><div className="overview-controls">{data && <Status>{data.health}</Status>}<button onClick={refresh} disabled={loading}><RefreshCw size={16} className={loading ? "spin" : ""} />{loading ? "Refreshing" : "Refresh"}</button></div></div>
    <p className="snapshot-time meta" aria-live="polite">{data ? `Updated ${new Date(data.collected_at).toLocaleString()}` : loading ? "Collecting read-only server signals…" : "No server snapshot available yet."} · Refreshes every 30 seconds</p>
    {(error || stale) && <div role="alert" className="notice">{error || "This snapshot is more than two minutes old. Refresh to check current conditions."}{data && " Last received values are shown below."}</div>}
    <QuickActions onSelect={onQuickAction} />
    <div className="resource-grid">
      <Metric title="Memory" value={percent(memory.used_percent)} caption={number(memory.total_bytes) != null ? `${bytes(memory.available_bytes)} available of ${bytes(memory.total_bytes)}` : "Host memory measurement unavailable"} icon={<Database size={17} />} used={number(memory.used_percent)} />
      <Metric title={cpuPercent == null ? "CPU load" : "CPU usage"} value={cpuPercent == null ? load?.toFixed(2) || "Unavailable" : percent(cpuPercent)} caption={load == null ? "Host CPU measurement unavailable" : `1-minute load · ${number(uptime.cpu_count) ?? "—"} logical CPUs${cpuPercent == null ? " · load is not a percentage" : ""}`} icon={<Cpu size={17} />} used={cpuPercent} />
      <Metric title="Uptime" value={number(uptime.uptime_seconds) == null ? "Unavailable" : duration(number(uptime.uptime_seconds))} caption="Time since the host last started" icon={<Clock3 size={17} />} />
      {disks.length ? disks.map(([key, signal]) => { const disk = signal.ok ? signal.result || {} : {}; return <Metric key={key} title={`Disk ${typeof disk.path === "string" ? disk.path : key.replace("disk_usage", "") || "/"}`} value={percent(disk.used_percent)} caption={number(disk.total_bytes) == null ? "Filesystem measurement unavailable" : `${bytes(disk.free_bytes)} free of ${bytes(disk.total_bytes)}`} used={number(disk.used_percent)} icon={<HardDrive size={17} />} />; }) : <Metric title="Disk" value="Unavailable" caption="Filesystem measurement unavailable" icon={<HardDrive size={17} />} />}
    </div>
    <div className="connectivity-grid">
      <section className="panel"><div className="panelhead"><h2><Wifi size={18} /> Tailscale</h2><Status>{tailState}</Status></div><p className="meta">{Array.isArray(tailscale.tailscale_ips) && tailscale.tailscale_ips.length ? tailscale.tailscale_ips.join(" · ") : "No private address reported"}</p><p>{tailSelf.Online === true ? "This host reports online." : tailSelf.Online === false ? "This host reports offline." : "Peer connectivity has not been established by this snapshot."}</p>{Array.isArray(tailscale.health) && tailscale.health.length > 0 && <p className="notice">{tailscale.health.map(String).join(" · ")}</p>}</section>
      <section className="panel"><div className="panelhead"><h2><Network size={18} /> Cloudflare Tunnel</h2><Status>{cloudState}</Status></div><p>{cloudState === "active" ? "The tunnel service is active." : "Check the tunnel service and origin if public requests fail."}</p><p className="meta">Process state alone does not verify public application reachability.</p></section>
    </div>
    <section className="panel tablewrap"><div className="panelhead"><h2><Box size={18} /> Docker containers</h2><span className="meta">{containers.length} in diagnostic scope</span></div>{signals.docker_list?.ok === false && <p className="notice">Docker diagnostics are unavailable. A failed check alone does not establish a daemon outage.</p>}<table><thead><tr><th>Container</th><th>State</th><th>Status</th><th>Image</th></tr></thead><tbody>{containers.map((item, index) => <tr key={item.name || index}><td><strong>{item.name || "Unnamed"}</strong></td><td><Status>{item.state || "Unknown"}</Status></td><td>{item.status || "—"}</td><td className="meta">{item.image || "—"}</td></tr>)}</tbody></table>{containers.length === 0 && <p className="empty">No container states are available in this snapshot.</p>}</section>
    <section className="panel"><div className="panelhead"><h2><ShieldCheck size={18} /> Configured applications and services</h2><span className="meta">{services.length} service profiles</span></div><p className="meta">Profiles describe diagnostic scope. Open an investigation to verify a service and its dependencies.</p><div className="application-grid">{services.map(([id, profile]) => { const targets = profile.health_checks?.filter(check => check.tool === "docker_inspect").map(check => check.arguments.container) || []; const found = containers.filter(item => targets.includes(item.name)); return <article className="application-card" key={id}><div className="panelhead"><h3>{serviceLabel(id, profile)}</h3><span className="meta">{profile.health_checks?.length || 0} checks</span></div><p className="meta">{profile.description || "Configured service profile"}</p>{found.length > 0 && <div className="chips">{found.map(item => <Status key={item.name}>{`${item.name}: ${item.state || "Unknown"}`}</Status>)}</div>}<button className="chip" onClick={() => onService(id)}>Investigate {serviceLabel(id, profile)}</button></article>; })}</div>{services.length === 0 && <p className="empty">No application profiles have been configured.</p>}</section>
  </>;
}
