import { useEffect, useState } from "react";
import { api } from "../api";
import type { Company } from "../types";

const WORKING = new Set(["queued", "ingesting", "new"]);

export function CompaniesView({ companies, onRefresh, onOpen }: {
  companies: Company[];
  onRefresh: () => void;
  onOpen: (id: number) => void;
}) {
  const [name, setName] = useState("");
  const [mode, setMode] = useState("edgar");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // poll while any company is still ingesting
  useEffect(() => {
    if (!companies.some((c) => WORKING.has(c.status))) return;
    const t = setInterval(onRefresh, 2500);
    return () => clearInterval(t);
  }, [companies, onRefresh]);

  const fetchCompany = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError("");
    try {
      await api.fetchCompany(name.trim(), mode);
      setName("");
      onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const saved = companies.filter((c) => c.saved);
  const others = companies.filter((c) => !c.saved);

  return (
    <div>
      <h2 className="page-title">Analyse a company</h2>
      <div className="card">
        <div className="row">
          <input style={{ flex: 1, minWidth: 220 }} value={name}
            placeholder="Company name or ticker (e.g. Apple, AAPL)"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchCompany()} />
          <select value={mode} onChange={(e) => setMode(e.target.value)}
            title="Where to fetch annual reports from">
            <option value="edgar">US-listed (SEC EDGAR)</option>
            <option value="global">Global (web search)</option>
          </select>
          <button className="primary" disabled={busy} onClick={fetchCompany}>
            {busy ? "Starting…" : "Fetch last 3 annual reports"}
          </button>
        </div>
        {error && <p className="error-text small">{error}</p>}
        <p className="muted small" style={{ marginBottom: 0 }}>
          US-listed uses official SEC filings and XBRL financial data. Global mode
          searches the web for annual-report PDFs on the company's investor pages.
        </p>
      </div>

      {saved.length > 0 && (
        <>
          <h2 className="page-title">Saved profiles</h2>
          <div className="grid-cards" style={{ marginBottom: 24 }}>
            {saved.map((c) => (
              <CompanyCard key={c.id} company={c} onOpen={onOpen} onRefresh={onRefresh} />
            ))}
          </div>
        </>
      )}

      {others.length > 0 && (
        <>
          <h2 className="page-title">Recent</h2>
          <div className="grid-cards">
            {others.map((c) => (
              <CompanyCard key={c.id} company={c} onOpen={onOpen} onRefresh={onRefresh} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function CompanyCard({ company, onOpen, onRefresh }: {
  company: Company;
  onOpen: (id: number) => void;
  onRefresh: () => void;
}) {
  const working = WORKING.has(company.status);
  const dot = company.status === "ready" ? "status-ready"
    : company.status === "failed" ? "status-failed" : "status-working";

  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <strong>{company.name}</strong>
        <span className="pill small">
          <span className={`status-dot ${dot}`} />
          {working ? "fetching…" : company.status}
        </span>
      </div>
      <p className="muted small" style={{ margin: "6px 0" }}>
        {company.ticker ? `${company.ticker} · ` : ""}
        {company.source_mode === "edgar" ? "SEC EDGAR" : "Global"} ·{" "}
        {company.ready_reports ?? 0} report(s) ready
      </p>
      {company.status === "failed" && company.error && (
        <p className="error-text small">{company.error}</p>
      )}
      <div className="row">
        <button className="primary" disabled={working}
          onClick={() => onOpen(company.id)}>Open dashboard</button>
        <button onClick={async () => {
          await api.saveCompany(company.id, !company.saved);
          onRefresh();
        }}>{company.saved ? "Unsave" : "Save profile"}</button>
        <button title="Delete company and all its data" onClick={async () => {
          if (confirm(`Delete ${company.name} and all stored data?`)) {
            await api.deleteCompany(company.id);
            onRefresh();
          }
        }}>Delete</button>
      </div>
    </div>
  );
}
