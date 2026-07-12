import { useEffect, useState } from "react";
import { api } from "./api";
import { ChatPanel } from "./components/ChatPanel";
import { CompaniesView } from "./components/CompaniesView";
import { DashboardView } from "./components/DashboardView";
import { ProjectsView } from "./components/ProjectsView";
import { SettingsView } from "./components/SettingsView";
import { TokenTracker } from "./components/TokenTracker";
import type { Company, Persona } from "./types";

export type View = "companies" | "dashboard" | "projects" | "settings";

export default function App() {
  const [view, setView] = useState<View>("companies");
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [projectId, setProjectId] = useState<number | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [provider, setProvider] = useState("");

  const refreshCompanies = () => api.listCompanies().then(setCompanies).catch(() => {});

  useEffect(() => {
    refreshCompanies();
    api.listPersonas().then(setPersonas).catch(() => {});
    api.getSettings().then((s) => setProvider(`${s.llm_provider} · ${s.llm_model}`))
      .catch(() => {});
  }, []);

  const openCompany = (id: number) => {
    setCompanyId(id);
    setView("dashboard");
  };

  const chatScope = view === "projects" && projectId
    ? { type: "project" as const, id: projectId }
    : companyId
      ? { type: "company" as const, id: companyId }
      : null;

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Annual Report Analyser</span>
        <nav>
          {(["companies", "dashboard", "projects", "settings"] as View[]).map((v) => (
            <button key={v} className={view === v ? "active" : ""}
              onClick={() => setView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
        </nav>
        <span className="spacer" />
        {provider && <span className="pill small" title="Active LLM provider">{provider}</span>}
        <TokenTracker />
      </header>
      <div className="body">
        <main className="pane">
          {view === "companies" && (
            <CompaniesView companies={companies} onRefresh={refreshCompanies}
              onOpen={openCompany} />
          )}
          {view === "dashboard" && (
            <DashboardView companyId={companyId} companies={companies}
              personas={personas} onSelectCompany={setCompanyId} />
          )}
          {view === "projects" && (
            <ProjectsView companies={companies} personas={personas}
              projectId={projectId} onSelectProject={setProjectId} />
          )}
          {view === "settings" && (
            <SettingsView personas={personas}
              onPersonasChange={() => api.listPersonas().then(setPersonas)}
              onSettingsChange={() =>
                api.getSettings().then((s) =>
                  setProvider(`${s.llm_provider} · ${s.llm_model}`))} />
          )}
        </main>
        <aside className="chat">
          <ChatPanel scope={chatScope} personas={personas}
            scopeName={chatScope?.type === "company"
              ? companies.find((c) => c.id === chatScope.id)?.name
              : undefined} />
        </aside>
      </div>
    </div>
  );
}
