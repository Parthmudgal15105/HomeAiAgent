"use client";
import { Activity, Loader2, RefreshCw, Search } from "lucide-react";
import { duration, serviceLabel, type ServiceMap } from "../lib/dashboard";

type Result = Record<string, unknown>;
type Signal = { ok: boolean; result?: Result; error?: string; duration_ms?: number };
export type OverviewData = {
  collected_at: string;
  health: "Healthy" | "Warning" | "Critical";
  signals: Record<string, Signal>;
  services: ServiceMap;
  findings: { level: string; signal: string; message: string }[];
};
function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}
function percent(value: unknown) {
  const n = number(value);
  return n === undefined ? "Unavailable" : `${n.toFixed(1)}%`;
}
function gib(value: unknown) {
  const n = number(value);
  return n === undefined ? "—" : `${(n / 1024 ** 3).toFixed(1)} GiB`;
}
function text(value: unknown) {
  return typeof value === "string" || typeof value === "number" ? String(value) : "Unavailable";
}
function Badge({ value }: { value: string }) {
  const style = /healthy|running|active|^up/i.test(value) ? "RESOLVED" : /critical|failed|exited|unhealthy/i.test(value) ? "FAILED" : "OPEN";
  return <span className={`pill ${style}`}>{value}</span>;
}
export function ServerOverview({ data, busy, refresh, investigate }: { data: OverviewData | null; busy: boolean; refresh: () => void; investigate: () => void }) {
  const get = (name: string): Result => data?.signals[name]?.ok ? data.signals[name].result || {} : {};
  const memory = get("memory_usage"), uptime = get("system_uptime"), disk = get("disk_usage");
  const load = Array.isArray(uptime.load_average) ? uptime.load_average : [];
  const containers = (get("docker_list").containers || []) as Result[];
  const tailscale = get("tailscale_status");
  return <>
    <div className="titleline">
      <div><div className="eyebrow">CURRENT INFRASTRUCTURE</div><h1>Server overview</h1><p className="muted">Bounded read-only checks of the host and configured workloads.</p></div>
      <div className="actions"><button disabled={busy} onClick={refresh}>{busy ? <Loader2 size={16} className="spin" /> : <RefreshCw size={16} />}Refresh</button><button onClick={investigate}><Search size={16} />Investigate health</button></div>
    </div>
    {!data ? <section className="panel empty"><Activity size={24} /><p>{busy ? "Collecting current server signals…" : "No overview collected. Refresh to retry."}</p></section> : <>
      <section className="panel">
        <div className="panelhead"><h2>Server health</h2><Badge value={data.health} /></div>
        <p className="footnote">Collected {new Date(data.collected_at).toLocaleString()} · Refreshes every minute. This snapshot is separate from an AI investigation.</p>
        {data.findings.length ? <ul>{data.findings.map((finding, i) => <li key={i}><strong>{finding.level}</strong>: {finding.message}</li>)}</ul> : <p>Current configured checks reported no warning or critical signals.</p>}
      </section>
      <div className="stats overview-stats">
        <div className="stat"><small>CPU LOAD · 1 / 5 / 15 MIN</small><strong>{load.length ? load.map(value => Number(value).toFixed(2)).join(" / ") : "Unavailable"}</strong><small>{text(uptime.cpu_count)} logical CPUs · load is runnable/waiting tasks, not utilization</small></div>
        <div className="stat"><small>RAM USED</small><strong>{percent(memory.used_percent)}</strong><small>{gib(memory.available_bytes)} available of {gib(memory.total_bytes)}</small></div>
        <div className="stat"><small>ROOT DISK USED</small><strong>{percent(disk.used_percent)}</strong><small>{gib(disk.free_bytes)} free of {gib(disk.total_bytes)}</small></div>
        <div className="stat"><small>UPTIME</small><strong>{duration(number(uptime.uptime_seconds))}</strong><small>Since the last host boot</small></div>
      </div>
      <div className="grid">
        <section className="panel tablewrap"><div className="panelhead"><h2>Docker containers</h2><Badge value={text(get("service_status_docker").state)} /></div>
          <p className="footnote">Containers permitted by the diagnostic allowlist.</p>
          <table><thead><tr><th>Container</th><th>State</th><th>Health / uptime</th></tr></thead><tbody>{containers.map((container, i) => <tr key={String(container.name || i)}><td>{text(container.name)}</td><td><Badge value={text(container.state)} /></td><td>{text(container.status)}</td></tr>)}</tbody></table>
          {!containers.length && <p className="muted">No container status is available.</p>}
        </section>
        <aside>
          <section className="panel"><h2>Connectivity and storage</h2>
            <div className="twoline"><span>Tailscale</span><Badge value={text(tailscale.backend_state)} /></div>
            <div className="twoline"><span>Cloudflare Tunnel</span><Badge value={text(get("cloudflared_status").state)} /></div>
            {Object.entries(data.signals).filter(([key]) => key.startsWith("disk_usage") && key !== "disk_usage").map(([key, signal]) => <div key={key} className="twoline"><span>{text(signal.result?.path)}</span><span>{signal.ok ? `${percent(signal.result?.used_percent)} used` : "Unavailable"}</span></div>)}
            {Array.isArray(tailscale.health) && tailscale.health.length > 0 && <p className="errorbox">{tailscale.health.map(String).join(" · ")}</p>}
            <details><summary>Network interface details</summary><pre>{JSON.stringify(get("network_interfaces"), null, 2)}</pre></details>
          </section>
          <section className="panel"><h2>Diagnostic availability</h2>{Object.entries(data.signals).map(([name, signal]) => <div className="twoline" key={name}><span className="muted">{name.replaceAll("_", " ")}</span><span>{signal.ok ? "Collected" : "Unavailable"}</span></div>)}<details><summary>Normalized signal results</summary><pre>{JSON.stringify(data.signals, null, 2)}</pre></details></section>
        </aside>
      </div>
      <section className="panel"><h2>Configured monitored services</h2><p className="footnote">Service membership and dependencies come from configuration. A configured service is not assumed healthy without a current check.</p><div className="service-cards">{Object.entries(data.services || {}).map(([id, profile]) => <article className="service-card" key={id}><h3>{serviceLabel(id, profile)}</h3><small>{(profile.type || "service").replaceAll("_", " ")}</small><p>{profile.description}</p>{profile.public_urls?.map(url => <p key={url}><a className="evidence-link" href={url} target="_blank" rel="noopener noreferrer">{url}</a></p>)}<p className="footnote">{profile.containers?.length || 0} containers · {profile.systemd_services?.length || 0} system services</p><p className="footnote">Dependencies: {(profile.depends_on || profile.dependencies || []).map(dep => serviceLabel(dep, data.services[dep])).join(", ") || "None configured"}</p></article>)}</div></section>
    </>}
  </>;
}
