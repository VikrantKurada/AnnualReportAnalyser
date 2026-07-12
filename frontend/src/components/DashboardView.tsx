import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatValue } from "../api";
import type { DashboardConfig } from "../metricCatalog";
import { PRESET_PANELS, panelEnabled } from "../metricCatalog";
import type { Analysis, Company, FactPivot, Persona } from "../types";
import { CustomizePanel } from "./CustomizePanel";
import { CustomChartPanel, PresetPanel } from "./panels";
import { RichText, TraceChips } from "./TraceChips";

const WIDE_PANELS = new Set(["headline", "dupont", "valuation"]);

export function DashboardView({ companyId, companies, personas, onSelectCompany }: {
  companyId: number | null;
  companies: Company[];
  personas: Persona[];
  onSelectCompany: (id: number) => void;
}) {
  const [company, setCompany] = useState<Company | null>(null);
  const [facts, setFacts] = useState<FactPivot | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [personaId, setPersonaId] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [config, setConfig] = useState<DashboardConfig>({});
  const [customizing, setCustomizing] = useState(false);
  const baselineId = useRef<number | null>(null);

  useEffect(() => {
    api.getDashboardConfig().then(setConfig).catch(() => {});
  }, []);

  const saveConfig = (next: DashboardConfig) => {
    setConfig(next);
    api.putDashboardConfig(next).catch(() => {});
  };

  const load = useCallback(async () => {
    if (!companyId) return;
    const [c, f, a] = await Promise.all([
      api.getCompany(companyId),
      api.companyFacts(companyId),
      api.latestAnalysis(companyId, personaId),
    ]);
    setCompany(c);
    setFacts(f);
    setAnalysis(a.analysis);
  }, [companyId, personaId]);

  useEffect(() => {
    setAnalysis(null);
    setAnalyzing(false);
    load().catch(() => {});
  }, [load]);

  // poll while an analysis is running
  useEffect(() => {
    if (!analyzing || !companyId) return;
    const t = setInterval(async () => {
      const a = (await api.latestAnalysis(companyId, personaId)).analysis;
      if (a && a.id !== baselineId.current) {
        setAnalysis(a);
        setAnalyzing(false);
      }
    }, 3000);
    return () => clearInterval(t);
  }, [analyzing, companyId, personaId]);

  if (!companyId) {
    const ready = companies.filter((c) => c.status === "ready");
    return (
      <div>
        <h2 className="page-title">Dashboard</h2>
        <div className="card">
          <p className="muted">Pick a company to open its dashboard:</p>
          <div className="row">
            {ready.length === 0 && (
              <span className="muted small">
                No analysed companies yet — fetch one from the Companies tab.
              </span>
            )}
            {ready.map((c) => (
              <button key={c.id} onClick={() => onSelectCompany(c.id)}>{c.name}</button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const startAnalysis = async () => {
    baselineId.current = analysis?.id ?? null;
    await api.analyzeCompany(companyId, personaId);
    setAnalyzing(true);
  };

  const content = analysis?.content;
  const failed = analysis?.kind === "error";

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 16 }}>
        <h2 className="page-title" style={{ margin: 0 }}>
          {company?.name ?? "…"}{" "}
          {company?.ticker && <span className="muted">({company.ticker})</span>}
        </h2>
        <div className="row">
          <select value={personaId ?? ""} title="Analysis persona lens"
            onChange={(e) => setPersonaId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">No persona</option>
            {personas.filter((p) => p.enabled).map((p) => (
              <option key={p.id} value={p.id}>{p.name} lens</option>
            ))}
          </select>
          <button className="primary" onClick={startAnalysis} disabled={analyzing}>
            {analyzing ? "Analysing…" : analysis ? "Re-run analysis" : "Run analysis"}
          </button>
          <button onClick={() => setCustomizing(true)}
            title="Choose panels and build custom charts">Customize</button>
        </div>
      </div>

      {customizing && facts && (
        <CustomizePanel config={config} facts={facts} onChange={saveConfig}
          onClose={() => setCustomizing(false)} />
      )}

      {company?.status === "failed" && (
        <div className="card"><p className="error-text">Ingestion failed: {company.error}</p></div>
      )}

      {failed && (
        <div className="card">
          <p className="error-text">Analysis failed: {String(content?.error ?? "unknown error")}</p>
        </div>
      )}

      {!analysis && !analyzing && company?.status === "ready" && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            Reports are ingested. Run the analysis to populate the dashboard
            {personaId ? " through the selected persona's lens" : ""}.
          </p>
        </div>
      )}
      {analyzing && (
        <div className="card">
          <p style={{ margin: 0 }}>
            <span className="status-dot status-working" /> The LLM is analysing the
            reports — this can take a while with local models.
          </p>
        </div>
      )}

      {content && !failed && (
        <>
          {content.executive_summary && (
            <div className="card">
              <h3>Executive summary</h3>
              <p style={{ margin: 0 }}><RichText text={content.executive_summary} /></p>
              {analysis && (
                <p className="muted small" style={{ margin: "8px 0 0" }}>
                  {analysis.model ?? analysis.provider} · {analysis.created_at}
                  {analysis.persona_id
                    ? ` · ${personas.find((p) => p.id === analysis.persona_id)?.name ?? "persona"} lens`
                    : ""}
                </p>
              )}
            </div>
          )}
          {content.business_overview && (
            <div className="card">
              <h3>Business overview</h3>
              <p style={{ margin: 0 }}><RichText text={content.business_overview} /></p>
            </div>
          )}
          {content.financial_highlights && content.financial_highlights.length > 0 && (
            <div className="card">
              <h3>Financial highlights</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {content.financial_highlights.map((h, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <RichText text={h.statement} /> <TraceChips citations={h.citations} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      {facts && facts.metrics.length > 0 && (
        <div className="panel-grid">
          {PRESET_PANELS.filter((p) => panelEnabled(config, p.id)).map((p) => (
            <div key={p.id}
              style={{ gridColumn: WIDE_PANELS.has(p.id) ? "1 / -1" : undefined,
                minWidth: 0 }}>
              <PresetPanel spec={p} facts={facts} companyId={companyId} />
            </div>
          ))}
          {(config.custom_charts ?? []).map((c) => (
            <div key={c.id} style={{ minWidth: 0 }}>
              <CustomChartPanel chart={c} facts={facts}
                onDelete={() => saveConfig({
                  ...config,
                  custom_charts: (config.custom_charts ?? [])
                    .filter((x) => x.id !== c.id),
                })} />
            </div>
          ))}
        </div>
      )}

      {content && !failed && (
        <>
          {content.trends && content.trends.length > 0 && (
            <div className="card">
              <h3>Trends</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {content.trends.map((t, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <strong>{t.metric}</strong>{" "}
                    {t.direction === "up" ? "▲" : t.direction === "down" ? "▼" : "▬"}{" "}
                    {t.comment} <TraceChips citations={t.citations} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {content.risks && content.risks.length > 0 && (
            <div className="card">
              <h3>Key risks</h3>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {content.risks.map((r, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    <strong>{r.title}.</strong> <RichText text={r.summary} />{" "}
                    <TraceChips citations={r.citations} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {content.outlook && (
            <div className="card">
              <h3>Outlook</h3>
              <p style={{ margin: 0 }}><RichText text={content.outlook} /></p>
            </div>
          )}
        </>
      )}

      {facts && facts.metrics.length > 0 && <FactsTable facts={facts} />}

      {company?.reports && company.reports.length > 0 && (
        <div className="card">
          <h3>Source reports</h3>
          <div className="scroll-x">
            <table className="data">
              <thead>
                <tr><th>Fiscal year</th><th>Form</th><th>Status</th><th>Filed</th><th>Source</th></tr>
              </thead>
              <tbody>
                {company.reports.map((r) => (
                  <tr key={r.id}>
                    <td>{r.fiscal_year ?? "?"}</td>
                    <td>{r.form ?? "-"}</td>
                    <td>{r.status}{r.error ? ` — ${r.error}` : ""}</td>
                    <td>{r.filed_at ?? "-"}</td>
                    <td>
                      {r.source_url && (
                        <a href={r.source_url} target="_blank" rel="noreferrer">open ↗</a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function FactsTable({ facts }: { facts: FactPivot }) {
  return (
    <div className="card">
      <h3>Financial facts by fiscal year</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        Click a value to see exactly where it came from.
      </p>
      <div className="scroll-x">
        <table className="data">
          <thead>
            <tr>
              <th>Metric</th>
              {facts.years.map((y) => <th key={y}>FY{y}</th>)}
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {facts.metrics.map((m) => (
              <tr key={m.metric}>
                <td>{m.label}</td>
                {facts.years.map((y) => {
                  const v = m.values[String(y)];
                  const id = m.fact_ids[String(y)];
                  return (
                    <td key={y}>
                      {v !== null && v !== undefined && id ? (
                        <ValueWithTrace value={v} unit={m.unit} factId={id} />
                      ) : "–"}
                    </td>
                  );
                })}
                <td className="muted small">{m.source_kind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ValueWithTrace({ value, unit, factId }: {
  value: number; unit: string | null; factId: number;
}) {
  return (
    <span className="row" style={{ gap: 2, display: "inline-flex", flexWrap: "nowrap" }}>
      {formatValue(value, unit)}
      <TraceChips citations={[`fact:${factId}`]} />
    </span>
  );
}
