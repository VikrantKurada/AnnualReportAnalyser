import { useState } from "react";
import type { CustomChart, DashboardConfig, UnitGroup } from "../metricCatalog";
import {
  PRESET_PANELS, UNIT_GROUP_LABELS, availableMetrics, panelEnabled,
} from "../metricCatalog";
import type { FactPivot } from "../types";

/** Modal for toggling preset panels and building custom charts. */
export function CustomizePanel({ config, facts, onChange, onClose }: {
  config: DashboardConfig;
  facts: FactPivot;
  onChange: (next: DashboardConfig) => void;
  onClose: () => void;
}) {
  const [draftName, setDraftName] = useState("");
  const [draftType, setDraftType] = useState<CustomChart["chart"]>("line");
  const [draftGroup, setDraftGroup] = useState<UnitGroup>("currency");
  const [draftMetrics, setDraftMetrics] = useState<string[]>([]);

  const available = availableMetrics(facts);
  const groupOptions = (Object.keys(available) as UnitGroup[])
    .filter((g) => available[g].length > 0);

  const togglePanel = (id: string) => {
    onChange({
      ...config,
      panels: { ...config.panels, [id]: !panelEnabled(config, id) },
    });
  };

  const toggleDraftMetric = (metric: string) => {
    setDraftMetrics((m) => m.includes(metric)
      ? m.filter((x) => x !== metric) : [...m, metric]);
  };

  const addChart = () => {
    if (!draftName.trim() || draftMetrics.length === 0) return;
    const chart: CustomChart = {
      id: `c${Date.now()}`, name: draftName.trim(), chart: draftType,
      unit_group: draftGroup, metrics: draftMetrics,
    };
    onChange({ ...config, custom_charts: [...(config.custom_charts ?? []), chart] });
    setDraftName("");
    setDraftMetrics([]);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 720 }}>
        <h3>Customize dashboard</h3>

        <h4 style={{ marginBottom: 6 }}>Panels</h4>
        <div className="chat-toggles" style={{ marginBottom: 14 }}>
          {PRESET_PANELS.map((p) => (
            <label key={p.id}>
              <input type="checkbox" checked={panelEnabled(config, p.id)}
                onChange={() => togglePanel(p.id)} />
              {p.title}
            </label>
          ))}
        </div>

        <h4 style={{ marginBottom: 6 }}>Custom charts</h4>
        {(config.custom_charts ?? []).length > 0 && (
          <ul style={{ margin: "0 0 10px", paddingLeft: 18 }}>
            {(config.custom_charts ?? []).map((c) => (
              <li key={c.id}>
                {c.name} <span className="muted small">
                  ({c.chart} · {c.metrics.length} metrics)</span>{" "}
                <button className="small" style={{ padding: "0 6px" }}
                  onClick={() => onChange({
                    ...config,
                    custom_charts: (config.custom_charts ?? [])
                      .filter((x) => x.id !== c.id),
                  })}>✕</button>
              </li>
            ))}
          </ul>
        )}

        <div className="row" style={{ marginBottom: 8 }}>
          <input placeholder="Chart name" value={draftName}
            style={{ flex: 1, minWidth: 160 }}
            onChange={(e) => setDraftName(e.target.value)} />
          <select value={draftType}
            onChange={(e) => setDraftType(e.target.value as CustomChart["chart"])}>
            <option value="line">Line</option>
            <option value="bar">Bar</option>
            <option value="area">Area</option>
          </select>
          <select value={draftGroup} title="Unit group (one axis per chart)"
            onChange={(e) => {
              setDraftGroup(e.target.value as UnitGroup);
              setDraftMetrics([]);
            }}>
            {groupOptions.map((g) => (
              <option key={g} value={g}>{UNIT_GROUP_LABELS[g]}</option>
            ))}
          </select>
        </div>
        <div className="chat-toggles"
          style={{ maxHeight: 180, overflowY: "auto", marginBottom: 10 }}>
          {available[draftGroup].map((m) => (
            <label key={m.metric}>
              <input type="checkbox" checked={draftMetrics.includes(m.metric)}
                onChange={() => toggleDraftMetric(m.metric)} />
              {m.label}
            </label>
          ))}
        </div>
        <div className="row" style={{ justifyContent: "space-between" }}>
          <button onClick={addChart}
            disabled={!draftName.trim() || draftMetrics.length === 0}>
            + Add chart
          </button>
          <button className="primary" onClick={onClose}>Done</button>
        </div>
      </div>
    </div>
  );
}
