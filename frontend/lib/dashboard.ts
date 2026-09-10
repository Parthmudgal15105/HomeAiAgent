export type ServiceProfile = {
  name?: string;
  description?: string;
  public_urls?: string[];
  local_health_urls?: string[];
  containers?: string[];
  systemd_services?: string[];
  dependencies?: string[];
  label?: string;
  display_name?: string;
  type?: string;
  tags?: string[];
  depends_on?: string[];
  health_checks?: { tool: string; arguments: Record<string, unknown>; expect?: Record<string, unknown> }[];
};

export type ServiceMap = Record<string, ServiceProfile>;
export type QuickAction = "health" | "application" | "docker" | "cloudflare" | "tailscale" | "slow";

export const QUICK_ACTIONS: { id: QuickAction; label: string; symptom: string }[] = [
  { id: "health", label: "Check server health", symptom: "Check the current server health and investigate any warning or critical condition." },
  { id: "application", label: "Application down", symptom: "The selected application is down. Investigate its current state and dependencies." },
  { id: "docker", label: "Docker issue", symptom: "Docker workloads are having problems. Investigate the daemon and affected containers." },
  { id: "cloudflare", label: "Cloudflare 502", symptom: "The public application returns Cloudflare 502. Compare the tunnel and local origin health." },
  { id: "tailscale", label: "Tailscale unavailable", symptom: "Tailscale is unavailable. Investigate current connectivity without changing networking." },
  { id: "slow", label: "Server slow", symptom: "The server feels slow. Investigate CPU load, memory pressure, storage, and relevant processes." },
];

export function serviceLabel(id: string, profile?: ServiceProfile): string {
  return profile?.display_name || profile?.label || profile?.name || id;
}

export function suggestedService(action: QuickAction, services: ServiceMap): string {
  const entries = Object.entries(services);
  const terms = action === "health" || action === "slow" ? ["host", "server", "linux"]
    : action === "application" ? ["application", "app", "public"] : [action];
  const exact = entries.find(([id, profile]) => terms.some(term =>
    id.toLowerCase() === term || profile.type?.toLowerCase().includes(term) || profile.tags?.some(tag => tag.toLowerCase() === term),
  ));
  if (exact) return exact[0];
  if (action === "application") {
    return entries.find(([, profile]) => profile.health_checks?.some(check => check.tool === "http_check"))?.[0] || "";
  }
  return entries.find(([id]) => terms.some(term => id.toLowerCase().includes(term)))?.[0] || "";
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

export function resolutionTime(createdAt: string, resolvedAt?: string | null): string {
  if (!resolvedAt) return "Not resolved";
  return duration((Date.parse(resolvedAt) - Date.parse(createdAt)) / 1000);
}

export function observationFailed(result: Record<string, unknown>, executionOk?: boolean): boolean {
  if (executionOk === false || result.ok === false || result.reachable === false || result.healthy === false || result.resolved === false || result.open === false) return true;
  if (typeof result.status_code === "number" && result.status_code >= 400) return true;
  if (["HIGH", "CRITICAL", "high", "critical"].includes(String(result.severity))) return true;
  const state = result.state && typeof result.state === "object" ? (result.state as Record<string, unknown>).status : result.state;
  if (["inactive", "failed", "restarting", "exited", "dead"].includes(String(state)) || result.health === "unhealthy") return true;
  return false;
}
