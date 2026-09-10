"use client";
import { useEffect, useState, useCallback } from "react";
import { QUICK_ACTIONS, observationFailed, resolutionTime, serviceLabel, suggestedService, type ServiceMap } from "../lib/dashboard";
import { ServerOverview, type OverviewData } from "../components/server-overview";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronRight,
  Clock3,
  History,
  Loader2,
  LockKeyhole,
  LogOut,
  Network,
  Play,
  Search,
  Server,
  ShieldCheck,
  Terminal,
  TriangleAlert,
  XCircle,
} from "lucide-react";
type Obs = {
  id: string;
  step_number: number;
  tool_name: string;
  tool_arguments: unknown;
  normalized_result: Record<string, unknown>;
  raw_result?: { ok?: boolean; error?: string };
  interpretation: string;
  created_at: string;
};
type Hyp = {
  id: string;
  description: string;
  confidence: number;
  status: string;
  supporting_observation_ids: string[];
  contradicting_observation_ids: string[];
};
type Action = {
  id: string;
  tool_name: string;
  arguments: unknown;
  reason: string;
  risk_level: string;
  approval_status: string;
  verification_status?: string;
  result?: unknown;
};
type Report = {
  root_cause?: string;
  confidence?: number;
  evidence_observation_ids?: string[];
  eliminated_causes?: string[];
  remediation?: unknown[] | string;
  verification_plan?: string[];
  prevention?: string[];
  summary?: string;
};
type Incident = {
  id: string;
  title: string;
  description: string;
  service: string;
  status: string;
  severity: string;
  created_at: string;
  updated_at: string;
  resolved_at?: string | null;
  root_cause?: string;
  root_cause_confidence?: number;
  summary?: string;
  observations?: Obs[];
  hypotheses?: Hyp[];
  actions?: Action[];
  report?: Report;
  agent_state?: Record<string, unknown>;
};
type Topology = { services?: ServiceMap };
function date(s: string) {
  return new Date(s).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
function json(v: unknown) {
  return JSON.stringify(v, null, 2);
}
function Pill({ status }: { status: string }) {
  return (
    <span className={"pill " + status}>{status.replaceAll("_", " ")}</span>
  );
}
function List({ items }: { items: unknown }) {
  const values = Array.isArray(items) ? items : items ? [items] : [];
  return (
    <ul>
      {values.map((x, i) => (
        <li key={i}>
          {typeof x === "string"
            ? x
            : x && typeof x === "object" && "reason" in x
              ? String(x.reason)
              : json(x)}
        </li>
      ))}
    </ul>
  );
}
export default function Dashboard() {
  const [auth, setAuth] = useState<boolean | null>(null),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [symptom, setSymptom] = useState(""),
    [service, setService] = useState(""),
    [overview, setOverview] = useState<OverviewData | null>(null),
    [overviewBusy, setOverviewBusy] = useState(false),
    [view, setView] = useState("investigate"),
    [incidents, setIncidents] = useState<Incident[]>([]),
    [incidentsTotal, setIncidentsTotal] = useState(0),
    [historyPage, setHistoryPage] = useState(0),
    [selected, setSelected] = useState<Incident | null>(null),
    [health, setHealth] = useState<Record<string, unknown>>({}),
    [topology, setTopology] = useState<Topology>({});
  const api = useCallback(
    async (path: string, method = "GET", body?: unknown) => {
      const r = await fetch("/api/operator/" + path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const data = await r.json();
      if (r.status === 401) setAuth(false);
      if (!r.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : data.error || "Request failed",
        );
      return data;
    },
    [],
  );
  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((d) => setAuth(d.authenticated))
      .catch(() => setAuth(false));
    if (location.pathname === "/incidents") setView("history");
    if (location.pathname === "/overview") setView("overview");
  }, []);
  useEffect(() => {
    if (!auth) return;
    const incidentId = new URLSearchParams(location.search).get("incident");
    if (incidentId && /^[a-f0-9-]{36}$/.test(incidentId)) {
      api("incidents/" + incidentId).then(setSelected).catch(e => setError(e.message));
    }
  }, [auth, api]);
  useEffect(() => {
    if (!auth) return;
    const context = (
      document as Document & {
        modelContext?: {
          registerTool: (
            tool: unknown,
            options: unknown,
          ) => void | Promise<void>;
        };
      }
    ).modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    try {
      Promise.resolve(
        context.registerTool(
          {
            name: "read_current_investigation",
            description:
              "Read the currently open investigation, its evidence and approval status. Does not execute diagnostics or approve actions.",
            inputSchema: {
              type: "object",
              properties: {},
              additionalProperties: false,
            },
            annotations: { readOnlyHint: true, untrustedContentHint: true },
            execute: (input: unknown) => {
              if (
                !input ||
                typeof input !== "object" ||
                Object.keys(input).length
              )
                throw Error("Expected empty arguments");
              return selected
                ? {
                    id: selected.id,
                    title: selected.title,
                    status: selected.status,
                    root_cause: selected.root_cause,
                    observations: selected.observations,
                    hypotheses: selected.hypotheses,
                  }
                : { selected: false };
            },
          },
          { signal: lifecycle.signal },
        ),
      ).catch(() => {});
    } catch {}
    return () => lifecycle.abort();
  }, [auth, selected]);
  const refresh = useCallback(async () => {
    try {
      const [list, h, t] = await Promise.all([
        api(`incidents?limit=50&offset=${view === "history" ? historyPage * 50 : 0}`),
        api("health"),
        api("topology"),
      ]);
      setIncidents(
        Array.isArray(list) ? list : list.items || list.incidents || [],
      );
      setIncidentsTotal(list.total ?? (list.incidents || list.items || list).length);
      setHealth(h);
      setTopology(t);
    } catch (e) {
      setError((e as Error).message);
    }
  }, [api, historyPage, view]);
  useEffect(() => {
    if (!auth) return;
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [auth, refresh]);
  const refreshOverview = useCallback(async () => {
    setOverviewBusy(true);
    try { setOverview(await api("overview")); } catch (e) { setError((e as Error).message); }
    finally { setOverviewBusy(false); }
  }, [api]);
  useEffect(() => {
    if (!auth || view !== "overview") return;
    refreshOverview();
    const timer = setInterval(refreshOverview, 60000);
    return () => clearInterval(timer);
  }, [auth, view, refreshOverview]);
  useEffect(() => {
    if (!auth || !selected) return;
    let live = true;
    const update = () =>
      api("incidents/" + selected.id)
        .then((i) => {
          if (live) setSelected(i);
        })
        .catch((e) => {
          if (live) setError(e.message);
        });
    const timer = setInterval(update, 3000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [auth, selected?.id, api]);
  async function login(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.error);
      setPassword("");
      setAuth(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!symptom.trim() || !service) return;
    setBusy(true);
    setError("");
    try {
      const i = await api("incidents", "POST", {
        title: symptom.trim(),
        description: symptom.trim(),
        service: service || undefined,
      });
      setSelected(i);
      history.replaceState({}, "", "/?incident=" + i.id);
      await api("incidents/" + i.id + "/investigate", "POST", {});
      setSelected(await api("incidents/" + i.id));
      setSymptom("");
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function open(i: Incident) {
    setError("");
    try {
      setSelected(await api("incidents/" + i.id));
      setView("investigate");
      history.replaceState({}, "", "/?incident=" + i.id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function operate(path: string) {
    setBusy(true);
    setError("");
    try {
      await api(path, "POST", {});
      if (selected) setSelected(await api("incidents/" + selected.id));
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function navigate(v: string) {
    setView(v);
    setSelected(null);
    setError("");
    history.replaceState({}, "", v === "history" ? "/incidents" : v === "overview" ? "/overview" : "/");
  }
  if (auth === null)
    return (
      <main className="login">
        <Loader2 className="spin" />
        <p>Connecting to your operator…</p>
      </main>
    );
  if (!auth)
    return (
      <main className="login">
        <div className="brand">
          <Server size={32} />
          <div>
            AI Home-Lab Operator<small>PRIVATE WORKSPACE</small>
          </div>
        </div>
        <div className="panel">
          <div className="eyebrow">PRIVATE OPERATOR</div>
          <h1>Operator sign in</h1>
          <p className="muted">
            Investigate your infrastructure with a local AI model.
          </p>
          <form onSubmit={login}>
            <label htmlFor="password">Operator password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
            {error && (
              <p role="alert" className="errorbox">
                {error}
              </p>
            )}
            <button className="primary" disabled={busy}>
              {busy ? (
                <Loader2 className="spin" size={18} />
              ) : (
                <LockKeyhole size={18} />
              )}
              Sign in
            </button>
          </form>
        </div>
        <p className="footnote">
          <ShieldCheck size={15} /> Diagnostics, incident history and model
          inference stay on your server. Use the generated operator password
          from the deployment environment.
        </p>
      </main>
    );
  const active = incidents.filter((i) =>
    ["INVESTIGATING", "VERIFYING"].includes(i.status),
  ).length;
  const observations = selected?.observations || [],
    hypotheses = selected?.hypotheses || [];
  const report = selected?.report || {};
  const rootCause = report.root_cause || selected?.root_cause;
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Server size={28} />
          <div>
            Home-Lab
            <br />
            Operator<small>LOCAL AI</small>
          </div>
        </div>
        <nav className="nav" aria-label="Main navigation">
          <a
            href="/"
            className={view === "investigate" ? "active" : ""}
            onClick={(e) => {
              e.preventDefault();
              navigate("investigate");
            }}
          >
            <Activity size={18} />
            Investigate
          </a>
          <a
            href="/incidents"
            className={view === "history" ? "active" : ""}
            onClick={(e) => {
              e.preventDefault();
              navigate("history");
            }}
          >
            <History size={18} />
            Incident history
          </a>
          <a href="/overview" className={view === "overview" ? "active" : ""} onClick={(e) => { e.preventDefault(); navigate("overview"); }}>
            <Server size={18} />Server overview
          </a>
          <button
            className={view === "topology" ? "active" : ""}
            onClick={() => navigate("topology")}
          >
            <Network size={18} />
            Service topology
          </button>
        </nav>
        <div className="railfoot">
          <ShieldCheck size={20} />
          <p>Read-only diagnostics run automatically.</p>
          <p>Changes require your approval.</p>
          <hr className="divider" />
          <button
            onClick={async () => {
              await fetch("/api/session", { method: "DELETE" });
              setAuth(false);
            }}
          >
            <LogOut size={16} />
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span>
            <strong>Infrastructure</strong> /{" "}
            {selected
              ? "Investigation"
              : view === "history"
                ? "Incident history"
                : view === "topology"
                  ? "Service topology"
                  : view === "overview" ? "Server overview" : "Investigate"}
          </span>
          <span className="meta">
            <span className="dot" />
            Private workspace
          </span>
        </header>
        {error && (
          <div role="alert" className="errorbox">
            {error}
          </div>
        )}
        {view === "overview" ? (
          <ServerOverview data={overview} busy={overviewBusy} refresh={refreshOverview} investigate={() => { setSymptom(QUICK_ACTIONS[0].symptom); setService(suggestedService("health", topology.services || {})); navigate("investigate"); }} />
        ) : view === "topology" ? (
          <>
            <div className="titleline">
              <div>
                <div className="eyebrow">ENVIRONMENT</div>
                <h1>Service topology</h1>
                <p className="muted">
                  Configured dependencies guide the agent’s diagnostic choices.
                </p>
              </div>
              <span className="pill">{Object.keys(topology.services || {}).length} configured services</span>
            </div>
            <div className="grid">
              {Object.entries(topology.services || {}).map(([name, s]) => (
                <section className="panel" key={name}>
                  <div className="service-node">
                    <h2>{serviceLabel(name, s)}</h2>
                    <p>{s.description}</p>
                  </div>
                  <small>DEPENDS ON</small>
                  <div className="chips">
                    {(s.depends_on || s.dependencies)?.length ? (
                      (s.depends_on || s.dependencies || []).map((d) => (
                        <span className="pill" key={d}>
                          {d}
                        </span>
                      ))
                    ) : (
                      <span className="muted">No configured dependency</span>
                    )}
                  </div>
                  <p className="footnote">
                    {s.health_checks?.length || 0} configured verification
                    checks
                  </p>
                </section>
              ))}
            </div>
          </>
        ) : view === "history" ? (
          <>
            <div className="eyebrow">INVESTIGATION LOG</div>
            <h1>Incident history</h1>
            <p className="muted">
              Evidence, decisions and recovery checks, saved locally.
            </p>
            <div className="panel tablewrap">
              <table>
                <thead>
                  <tr>
                    <th>Incident</th>
                    <th>Service</th>
                    <th>Status</th>
                    <th>Confidence</th>
                    <th>Created</th>
                    <th>Resolution time</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <button
                          className="incident-row"
                          onClick={() => open(i)}
                        >
                          <div>
                            <strong>{i.title}</strong>
                            <small>{i.root_cause || "Diagnosis pending"}</small>
                          </div>
                        </button>
                      </td>
                      <td>{i.service}</td>
                      <td>
                        <Pill status={i.status} />
                      </td>
                      <td>
                        {i.root_cause_confidence != null
                          ? Math.round(i.root_cause_confidence * 100) + "%"
                          : "—"}
                      </td>
                      <td>{date(i.created_at)}</td>
                      <td>{resolutionTime(i.created_at, i.resolved_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="actions" style={{ marginTop: 18 }}>
                <button disabled={historyPage === 0} onClick={() => setHistoryPage(p => p - 1)}>Previous</button>
                <span className="meta">{incidentsTotal ? `${historyPage * 50 + 1}–${Math.min((historyPage + 1) * 50, incidentsTotal)} of ${incidentsTotal}` : "No incidents"}</span>
                <button disabled={(historyPage + 1) * 50 >= incidentsTotal} onClick={() => setHistoryPage(p => p + 1)}>Next</button>
              </div>
              {!incidents.length && (
                <div className="empty">
                  Your first investigation will appear here.
                </div>
              )}
            </div>
          </>
        ) : selected ? (
          <>
            <button className="back" onClick={() => navigate("investigate")}>
              <ArrowLeft size={15} />
              All investigations
            </button>
            <div className="titleline">
              <div>
                <div className="eyebrow">
                  INCIDENT / {selected.id.slice(0, 8)}
                </div>
                <h1>{selected.title}</h1>
                <p className="muted">
                  {serviceLabel(selected.service, topology.services?.[selected.service])} · {selected.severity} · Opened {date(selected.created_at)}
                </p>
              </div>
              <Pill status={selected.status} />
            </div>
            <div className="grid">
              <div>
                {!rootCause && selected.summary && (
                  <section className="panel">
                    <h2>Investigation update</h2>
                    <p>{selected.summary}</p>
                  </section>
                )}
                {rootCause && (
                  <section className="panel report">
                    <div className="panelhead">
                      <h2>Diagnosis</h2>
                      <span className="confidence">
                        {Math.round(
                          (report.confidence ??
                            selected.root_cause_confidence ??
                            0) * 100,
                        )}
                        <small>%</small>
                      </span>
                    </div>
                    <p className="rootcause">{rootCause}</p>
                    <p className="muted">
                      {report.summary || selected.summary}
                    </p>
                    <small>
                      Evidence-based estimate; confidence is not a guarantee.
                    </small>
                    <h3 style={{ marginTop: 22 }}>Supporting evidence</h3>
                    <ul>
                      {(report.evidence_observation_ids || []).map((id) => {
                        const o = observations.find((x) => x.id === id);
                        return (
                          <li key={id}>
                            <a href={"#obs-" + id}>
                              {o ? `${o.tool_name}: ${o.interpretation}` : id}
                            </a>
                          </li>
                        );
                      })}
                    </ul>
                    {report.eliminated_causes?.length ? (
                      <>
                        <h3>Eliminated causes</h3>
                        <List items={report.eliminated_causes} />
                      </>
                    ) : null}
                    {report.remediation && (
                      <>
                        <h3>Recommended remediation</h3>
                        <List items={report.remediation} />
                      </>
                    )}
                    {report.verification_plan?.length ? (
                      <>
                        <h3>Verification plan</h3>
                        <List items={report.verification_plan} />
                      </>
                    ) : null}
                    {report.prevention?.length ? (
                      <>
                        <h3>Prevention</h3>
                        <List items={report.prevention} />
                      </>
                    ) : null}
                  </section>
                )}
                {(selected.actions || []).map((a) => (
                  <section key={a.id} className="panel approval">
                    <div className="panelhead">
                      <h2>Remediation approval</h2>
                      <Pill status={a.approval_status} />
                    </div>
                    <h3>{a.tool_name}</h3>
                    <p className="muted">{a.reason}</p>
                    <pre>{json(a.arguments)}</pre>
                    <small>
                      Risk: {a.risk_level.replaceAll("_", " ")}. Restarting a
                      service may interrupt traffic.
                    </small>
                    {a.approval_status === "PENDING" && (
                      <div className="actions">
                        <button
                          className="primary"
                          disabled={busy}
                          onClick={() =>
                            operate("actions/" + a.id + "/approve")
                          }
                        >
                          <CheckCircle2 size={17} />
                          Approve this action
                        </button>
                        <button
                          className="danger"
                          disabled={busy}
                          onClick={() => operate("actions/" + a.id + "/reject")}
                        >
                          Reject
                        </button>
                      </div>
                    )}
                    {a.verification_status && (
                      <p className="footnote">
                        Verification: {a.verification_status}
                      </p>
                    )}
                    {a.result != null && (
                      <details>
                        <summary>Action result</summary>
                        <pre>{json(a.result)}</pre>
                      </details>
                    )}
                  </section>
                ))}
                <section className="panel">
                  <div className="panelhead">
                    <h2>Investigation timeline</h2>
                    <small>{observations.length} observations</small>
                  </div>
                  {!observations.length ? (
                    <div className="empty">
                      <Search size={24} />
                      <p>Gathering the first evidence</p>
                      <small>The local model is choosing a diagnostic.</small>
                    </div>
                  ) : (
                    <div className="timeline">
                      {observations.map((o) => {
                        const bad = observationFailed(o.normalized_result, o.raw_result?.ok);
                        return (
                          <article
                            id={"obs-" + o.id}
                            className={"step " + (bad ? "error" : "")}
                            key={o.id}
                          >
                            {bad ? (
                              <XCircle size={20} className="stepicon" />
                            ) : (
                              <CheckCircle2 size={20} className="stepicon" />
                            )}
                            <div
                              className="panelhead"
                              style={{ marginBottom: 4 }}
                            >
                              <h3>{o.tool_name.replaceAll("_", " ")}</h3>
                              <small>Step {o.step_number} · {date(o.created_at)}</small>
                            </div>
                            <p>
                              {o.interpretation ||
                                "Diagnostic result recorded."}
                            </p>
                            <details>
                              <summary>Inspect arguments and result</summary>
                              <pre>
                                {json({
                                  arguments: o.tool_arguments,
                                  result: o.normalized_result,
                                })}
                              </pre>
                            </details>
                          </article>
                        );
                      })}
                    </div>
                  )}
                  {["INVESTIGATING", "VERIFYING"].includes(selected.status) && (
                    <p className="pending" aria-live="polite">
                      <Loader2 size={16} className="spin" />
                      Local model is evaluating the evidence…
                    </p>
                  )}
                  {![
                    "INVESTIGATING",
                    "VERIFYING",
                    "WAITING_FOR_APPROVAL",
                  ].includes(selected.status) && (
                    <div className="actions">
                      <button
                        disabled={busy}
                        onClick={() =>
                          operate("incidents/" + selected.id + "/investigate")
                        }
                      >
                        <Play size={16} />
                        Continue investigation
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          operate("incidents/" + selected.id + "/verify")
                        }
                      >
                        <ShieldCheck size={16} />
                        Verify recovery
                      </button>
                    </div>
                  )}
                </section>
              </div>
              <aside>
                <section className="panel">
                  <div className="panelhead">
                    <h2>Current hypotheses</h2>
                    <Activity size={18} className="muted" />
                  </div>
                  {hypotheses
                    .filter((h) => h.status !== "ELIMINATED")
                    .map((h) => (
                      <div className="hypothesis" key={h.id}>
                        <div className="hyptitle">
                          <span>{h.description}</span>
                          <strong>{Math.round(h.confidence * 100)}%</strong>
                        </div>
                        <div className="bar">
                          <span
                            style={{
                              width:
                                Math.max(0, Math.min(100, h.confidence * 100)) +
                                "%",
                            }}
                          />
                        </div>
                        <small>
                          {h.status} · Evidence{" "}
                          {(h.supporting_observation_ids || []).map((id, i) => (
                            <a
                              key={id}
                              href={"#obs-" + id}
                              style={{ marginLeft: 6 }}
                            >
                              {observations.find((o) => o.id === id)
                                ?.step_number || i + 1}
                            </a>
                          ))}
                        </small>
                        {h.contradicting_observation_ids?.length > 0 && <small className="contradictions">Contradicting evidence: {h.contradicting_observation_ids.map(id => <a key={id} href={"#obs-" + id}>Step {observations.find(o => o.id === id)?.step_number || "?"} </a>)}</small>}
                      </div>
                    ))}
                  {!hypotheses.length && (
                    <p className="muted">
                      Hypotheses appear as the agent gathers evidence.
                    </p>
                  )}
                  {hypotheses.some((h) => h.status === "ELIMINATED") && (
                    <>
                      <hr className="divider" />
                      <h3>Eliminated</h3>
                      {hypotheses
                        .filter((h) => h.status === "ELIMINATED")
                        .map((h) => (
                          <p key={h.id} className="meta">
                            {h.description} · {Math.round(h.confidence * 100)}%
                          </p>
                        ))}
                    </>
                  )}
                </section>
                <section className="panel">
                  <h2>Investigation context</h2>
                  <div className="twoline">
                    <span className="muted">Service</span>
                    <span>{selected.service}</span>
                  </div>
                  <div className="twoline">
                    <span className="muted">Severity</span>
                    <span>{selected.severity}</span>
                  </div>
                  <div className="twoline">
                    <span className="muted">Updated</span>
                    <span>{date(selected.updated_at)}</span>
                  </div>
                  {(Array.isArray(selected.agent_state?.retrieved_incidents) ? selected.agent_state.retrieved_incidents as Record<string, unknown>[] : []).map((context, index) => <div className="historical-context" key={String(context.document_id || index)}><small>HISTORICAL CONTEXT</small><p>{String(context.title || context.symptom || context.service || "Similar past incident")}</p><small>Similarity guides diagnostics; this is not current evidence.</small></div>)}
                  <details>
                    <summary>Historical context and runbook guidance</summary>
                    <pre>{json({ past_incidents: selected.agent_state?.retrieved_incidents || [], runbooks: selected.agent_state?.retrieved_runbooks || [], retrieval_status: selected.agent_state?.rag_status })}</pre>
                  </details>
                  <p className="footnote">
                    Runbooks and past incidents guide the investigation. Current
                    observations establish the diagnosis.
                  </p>
                </section>
              </aside>
            </div>
          </>
        ) : (
          <>
            <div className="titleline">
              <div>
                <div className="eyebrow">YOUR INFRASTRUCTURE, UNDERSTOOD</div>
                <h1>What is wrong?</h1>
                <p className="muted">
                  Describe a symptom. Follow the evidence as your local agent
                  investigates.
                </p>
              </div>
              <span className="pill">
                <ShieldCheck size={13} style={{ marginRight: 6 }} />
                Approval required for changes
              </span>
            </div>
            <section className="panel composer">
              <form onSubmit={create}>
                <label htmlFor="symptom">Start an investigation</label>
                <label htmlFor="service">Monitored service</label>
                <select id="service" value={service} onChange={e => setService(e.target.value)} style={{ marginBottom: 16 }}>
                  <option value="">Select a configured service</option>
                  {Object.entries(topology.services || {}).map(([id, profile]) => <option key={id} value={id}>{serviceLabel(id, profile)}{profile.type ? " · " + profile.type.replaceAll("_", " ") : ""}</option>)}
                </select>
                <label htmlFor="symptom">Describe the issue</label>
                <textarea
                  id="symptom"
                  value={symptom}
                  maxLength={300}
                  onChange={(e) => setSymptom(e.target.value)}
                  placeholder="e.g. Check whether my application is healthy."
                  required
                />
                <div className="composerbar">
                  <span className="meta">
                    <LockKeyhole size={14} /> Logs and reasoning stay on this
                    server
                  </span>
                  <button
                    className="primary"
                    disabled={busy || !symptom.trim() || !service}
                  >
                    {busy ? (
                      <Loader2 className="spin" size={18} />
                    ) : (
                      <Search size={18} />
                    )}
                    Investigate
                    <ArrowUpRight size={17} />
                  </button>
                </div>
              </form>
              <div className="chips">
                {QUICK_ACTIONS.map((x) => (
                  <button
                    className="chip"
                    key={x.id}
                    onClick={() => { setSymptom(x.symptom); const recommended = suggestedService(x.id, topology.services || {}); if (recommended) setService(recommended); }}
                  >
                    {x.label}
                  </button>
                ))}
              </div>
            </section>
            <div className="stats">
              <div className="stat">
                <small>INVESTIGATIONS</small>
                <strong>{incidentsTotal}</strong>
                <small>Saved on this server</small>
              </div>
              <div className="stat">
                <small>RUNNING</small>
                <strong>{active}</strong>
                <small>Gathering evidence</small>
              </div>
              <div className="stat">
                <small>AWAITING APPROVAL</small>
                <strong>
                  {
                    incidents.filter((i) => i.status === "WAITING_FOR_APPROVAL")
                      .length
                  }
                </strong>
                <small>You control changes</small>
              </div>
            </div>
            <div className="grid">
              <section className="panel">
                <div className="panelhead">
                  <h2>Recent investigations</h2>
                  <button className="chip" onClick={() => navigate("history")}>
                    View all
                    <ChevronRight size={14} />
                  </button>
                </div>
                {incidents.slice(0, 6).map((i) => (
                  <button
                    key={i.id}
                    className="incident-row"
                    onClick={() => open(i)}
                  >
                    <div>
                      <strong>{i.title}</strong>
                      <small>
                        {i.service} · {date(i.created_at)}
                      </small>
                    </div>
                    <Pill status={i.status} />
                  </button>
                ))}
                {!incidents.length && (
                  <div className="empty">
                    <Terminal size={28} />
                    <p>No investigations yet</p>
                    <small>Describe a symptom above to begin.</small>
                  </div>
                )}
              </section>
              <aside>
                <section className="panel">
                  <div className="panelhead">
                    <h2>Operator health</h2>
                    <Activity size={18} className="muted" />
                  </div>
                  {Object.entries(
                    (health.components as Record<string, unknown>) || health,
                  ).map(([k, v]) => (
                    <div className="twoline" key={k}>
                      <span className="muted">{k.replaceAll("_", " ")}</span>
                      <span>
                        {typeof v === "object"
                          ? (v as Record<string, unknown>)?.status === "ok"
                            ? "Ready"
                            : "Unavailable"
                          : String(v)}
                      </span>
                    </div>
                  ))}
                  <details>
                    <summary>Component details</summary>
                    <pre>{json(health)}</pre>
                  </details>
                </section>
                <section className="panel">
                  <ShieldCheck size={22} style={{ color: "var(--accent)" }} />
                  <h3 style={{ marginTop: 12 }}>Evidence before action</h3>
                  <p className="meta">
                    The agent selects bounded diagnostic tools, records
                    observations and updates hypotheses. Service changes wait
                    for your approval.
                  </p>
                </section>
              </aside>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
