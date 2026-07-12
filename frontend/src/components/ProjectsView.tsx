import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatValue } from "../api";
import type { Analysis, Company, Comparison, Persona, Project } from "../types";
import { TraceChips } from "./TraceChips";

export function ProjectsView({ companies, personas, projectId, onSelectProject }: {
  companies: Company[];
  personas: Persona[];
  projectId: number | null;
  onSelectProject: (id: number | null) => void;
}) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");

  const refresh = () => api.listProjects().then(setProjects).catch(() => {});
  useEffect(() => { refresh(); }, []);

  const create = async () => {
    if (!name.trim()) return;
    const p = await api.createProject(name.trim(), "");
    setName("");
    refresh();
    onSelectProject(p.id);
  };

  if (projectId) {
    return (
      <ProjectDetail projectId={projectId} companies={companies} personas={personas}
        onBack={() => { onSelectProject(null); refresh(); }} />
    );
  }

  return (
    <div>
      <h2 className="page-title">Projects</h2>
      <div className="card">
        <div className="row">
          <input style={{ flex: 1, minWidth: 220 }} value={name}
            placeholder="New project name (e.g. Cloud giants comparison)"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()} />
          <button className="primary" onClick={create}>Create project</button>
        </div>
        <p className="muted small" style={{ marginBottom: 0 }}>
          Projects compare saved company profiles side by side, derive custom
          metrics, and store the results for later.
        </p>
      </div>
      <div className="grid-cards">
        {projects.map((p) => (
          <div key={p.id} className="card" style={{ marginBottom: 0 }}>
            <strong>{p.name}</strong>
            <p className="muted small">{p.company_count ?? 0} companies</p>
            <div className="row">
              <button className="primary" onClick={() => onSelectProject(p.id)}>Open</button>
              <button onClick={async () => {
                if (confirm(`Delete project ${p.name}?`)) {
                  await api.deleteProject(p.id);
                  refresh();
                }
              }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProjectDetail({ projectId, companies, personas, onBack }: {
  projectId: number;
  companies: Company[];
  personas: Persona[];
  onBack: () => void;
}) {
  const [project, setProject] = useState<Project | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [personaId, setPersonaId] = useState<number | null>(null);
  const baselineId = useRef<number | null>(null);
  const [metricName, setMetricName] = useState("");
  const [metricFormula, setMetricFormula] = useState("");
  const [suggestPrompt, setSuggestPrompt] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const [p, c, a] = await Promise.all([
      api.getProject(projectId),
      api.compareProject(projectId),
      api.latestProjectAnalysis(projectId),
    ]);
    setProject(p);
    setComparison(c);
    setAnalysis(a.analysis);
  }, [projectId]);

  useEffect(() => { load().catch(() => {}); }, [load]);

  useEffect(() => {
    if (!analyzing) return;
    const t = setInterval(async () => {
      const a = (await api.latestProjectAnalysis(projectId)).analysis;
      if (a && a.id !== baselineId.current) {
        setAnalysis(a);
        setAnalyzing(false);
      }
    }, 3000);
    return () => clearInterval(t);
  }, [analyzing, projectId]);

  const inProject = new Set((project?.companies ?? []).map((c) => c.id));
  const addable = companies.filter((c) => c.saved && !inProject.has(c.id)
    && c.status === "ready");

  const addMetric = async (name: string, description: string, formula: string) => {
    setError("");
    try {
      await api.addMetric(projectId, name, description, formula);
      setMetricName("");
      setMetricFormula("");
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const suggest = async () => {
    if (!suggestPrompt.trim()) return;
    setSuggesting(true);
    setError("");
    try {
      const s = await api.suggestMetric(projectId, suggestPrompt.trim());
      setMetricName(s.name);
      setMetricFormula(s.formula);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSuggesting(false);
    }
  };

  const content = analysis?.content as
    | { summary?: string; comparison?: { statement: string; citations?: string[] }[];
        verdict?: string; error?: string }
    | undefined;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <h2 className="page-title" style={{ margin: 0 }}>
          <button onClick={onBack} style={{ marginRight: 10 }}>←</button>
          {project?.name ?? "…"}
        </h2>
        <div className="row">
          <select value={personaId ?? ""} title="Comparison persona lens"
            onChange={(e) => setPersonaId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">No persona</option>
            {personas.filter((p) => p.enabled).map((p) => (
              <option key={p.id} value={p.id}>{p.name} lens</option>
            ))}
          </select>
          <button className="primary" disabled={analyzing}
            onClick={async () => {
              baselineId.current = analysis?.id ?? null;
              await api.analyzeProject(projectId, personaId);
              setAnalyzing(true);
            }}>
            {analyzing ? "Comparing…" : "Run comparison analysis"}
          </button>
        </div>
      </div>

      <div className="card">
        <h3>Companies</h3>
        <div className="row">
          {(project?.companies ?? []).map((c) => (
            <span key={c.id} className="pill">
              {c.name}
              <button style={{ border: "none", padding: 0, background: "none" }}
                title="Remove from project"
                onClick={async () => {
                  await api.removeProjectCompany(projectId, c.id);
                  load();
                }}>✕</button>
            </span>
          ))}
          {addable.length > 0 && (
            <select value="" onChange={async (e) => {
              if (e.target.value) {
                await api.addProjectCompany(projectId, Number(e.target.value));
                load();
              }
            }}>
              <option value="">+ Add saved company…</option>
              {addable.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}
        </div>
        {(project?.companies ?? []).length === 0 && (
          <p className="muted small" style={{ marginBottom: 0 }}>
            Add saved company profiles (save them from the Companies tab first).
          </p>
        )}
      </div>

      {content && analysis?.kind !== "error" && (
        <div className="card">
          <h3>Comparison analysis</h3>
          {content.summary && <p>{content.summary}</p>}
          {content.comparison && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {content.comparison.map((s, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {s.statement} <TraceChips citations={s.citations} />
                </li>
              ))}
            </ul>
          )}
          {content.verdict && (
            <p style={{ marginBottom: 0 }}><strong>Verdict:</strong> {content.verdict}</p>
          )}
        </div>
      )}
      {analysis?.kind === "error" && (
        <div className="card">
          <p className="error-text">Comparison failed: {String(content?.error)}</p>
        </div>
      )}
      {analyzing && (
        <div className="card">
          <p style={{ margin: 0 }}>
            <span className="status-dot status-working" /> Comparing companies…
          </p>
        </div>
      )}

      {comparison && comparison.companies.length > 0 && comparison.rows.length > 0 && (
        <div className="card">
          <h3>Side-by-side facts (latest years)</h3>
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr>
                  <th>Metric</th>
                  {comparison.companies.map((c) => (
                    <th key={c.id}>{c.ticker ?? c.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {comparison.rows.map((row) => {
                  const latest = (cid: number) => {
                    const values = row.values[String(cid)] ?? {};
                    const years = Object.keys(values).sort().reverse();
                    for (const y of years) {
                      if (values[y] !== null) {
                        return { y, v: values[y],
                          id: row.fact_ids[String(cid)]?.[y] };
                      }
                    }
                    return null;
                  };
                  return (
                    <tr key={row.metric}>
                      <td>{row.label}</td>
                      {comparison.companies.map((c) => {
                        const cell = latest(c.id);
                        return (
                          <td key={c.id}>
                            {cell ? (
                              <>
                                {formatValue(cell.v, row.unit)}{" "}
                                <span className="muted small">FY{cell.y}</span>
                                {cell.id && <TraceChips citations={[`fact:${cell.id}`]} />}
                              </>
                            ) : "–"}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Custom comparison metrics</h3>
        {(project?.metrics ?? []).length > 0 && (
          <div className="scroll-x" style={{ marginBottom: 12 }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th>Formula</th>
                  {(project?.companies ?? []).map((c) => (
                    <th key={c.id}>{c.ticker ?? c.name}</th>
                  ))}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(project?.metrics ?? []).map((m) => (
                  <tr key={m.id}>
                    <td title={m.description ?? ""}>{m.name}</td>
                    <td><code className="small">{m.formula}</code></td>
                    {(project?.companies ?? []).map((c) => {
                      const r = m.results[String(c.id)];
                      return (
                        <td key={c.id}>
                          {r && r.value !== null && r.value !== undefined
                            ? formatValue(r.value, null)
                            : (r?.error ?? "–")}
                        </td>
                      );
                    })}
                    <td>
                      <button className="small" style={{ padding: "2px 8px" }}
                        onClick={async () => {
                          await api.deleteMetric(projectId, m.id);
                          load();
                        }}>✕</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="row" style={{ marginBottom: 8 }}>
          <input style={{ flex: 1, minWidth: 160 }} value={metricName}
            placeholder="Metric name" onChange={(e) => setMetricName(e.target.value)} />
          <input style={{ flex: 2, minWidth: 220 }} value={metricFormula}
            placeholder="Formula, e.g. net_income / revenue"
            onChange={(e) => setMetricFormula(e.target.value)} />
          <button className="primary"
            disabled={!metricName.trim() || !metricFormula.trim()}
            onClick={() => addMetric(metricName.trim(), "", metricFormula.trim())}>
            Add metric
          </button>
        </div>
        <div className="row">
          <input style={{ flex: 1, minWidth: 220 }} value={suggestPrompt}
            placeholder="…or describe a goal and let the LLM suggest a formula"
            onChange={(e) => setSuggestPrompt(e.target.value)} />
          <button disabled={suggesting} onClick={suggest}>
            {suggesting ? "Suggesting…" : "Suggest with AI"}
          </button>
        </div>
        {error && <p className="error-text small">{error}</p>}
        <p className="muted small" style={{ marginBottom: 0 }}>
          Formulas use stored metric names (revenue, net_income, total_assets, …)
          and are computed in Python over each company's latest fiscal year — never
          by the LLM — so results stay traceable.
        </p>
      </div>
    </div>
  );
}
