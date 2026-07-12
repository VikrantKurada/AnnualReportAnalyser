import { useEffect, useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "../api";
import type { CustomChart, PanelSpec, UnitGroup } from "../metricCatalog";
import { colorFor, formatByGroup, groupForUnit } from "../metricCatalog";
import type { FactPivot, Valuation } from "../types";
import { TraceChips } from "./TraceChips";

const GRID = "#e1e0d9";
const AXIS = "#c3c2b7";
const TICK = { fill: "#898781", fontSize: 12 };

interface Series { metric: string; label: string; color: string }

function buildData(facts: FactPivot, metrics: string[], group: UnitGroup) {
  const byName = new Map(facts.metrics.map((m) => [m.metric, m]));
  const series: Series[] = [];
  for (const name of metrics) {
    const m = byName.get(name);
    if (m && Object.values(m.values).some((v) => v !== null)) {
      series.push({ metric: name, label: m.label, color: colorFor(name) });
    }
  }
  const years = [...facts.years].sort();
  const data = years.map((year) => {
    const row: Record<string, number | string | null> = { year };
    for (const s of series) {
      const v = byName.get(s.metric)?.values[String(year)] ?? null;
      row[s.label] = v === null ? null
        : group === "percent" ? Number((v * 100).toFixed(3)) : v;
    }
    return row;
  }).filter((row) => series.some((s) => row[s.label] !== null));
  return { series, data };
}

function axisFormatter(group: UnitGroup) {
  return (v: number) =>
    group === "percent" ? `${v}%` : formatByGroup(v, group);
}

function tooltipFormatter(group: UnitGroup) {
  return (v: unknown) =>
    group === "percent" ? `${(v as number).toFixed(1)}%`
      : formatByGroup(v as number, group);
}

/** One chart card driven by a preset spec or a custom chart definition. */
export function ChartPanel({ title, kind, group, metrics, facts, onDelete }: {
  title: string;
  kind: "bars" | "stacked_bars" | "lines" | "area" | "line" | "bar";
  group: UnitGroup;
  metrics: string[];
  facts: FactPivot;
  onDelete?: () => void;
}) {
  const { series, data } = buildData(facts, metrics, group);
  if (series.length === 0 || data.length === 0) return null;

  const common = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey="year" stroke={AXIS} tick={TICK} />
      <YAxis stroke={AXIS} tick={TICK} width={58}
        tickFormatter={axisFormatter(group)} />
      <Tooltip formatter={tooltipFormatter(group)}
        contentStyle={{ fontSize: 12, borderRadius: 6 }} />
      {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
    </>
  );

  let chart;
  if (kind === "lines" || kind === "line") {
    chart = (
      <LineChart data={data}>
        {common}
        {series.map((s) => (
          <Line key={s.metric} dataKey={s.label} stroke={s.color}
            strokeWidth={2} dot={{ r: 4 }} connectNulls />
        ))}
      </LineChart>
    );
  } else if (kind === "area") {
    chart = (
      <AreaChart data={data}>
        {common}
        {series.map((s) => (
          <Area key={s.metric} dataKey={s.label} stroke={s.color}
            fill={s.color} fillOpacity={0.18} strokeWidth={2} connectNulls />
        ))}
      </AreaChart>
    );
  } else {
    const stacked = kind === "stacked_bars";
    chart = (
      <BarChart data={data} barGap={2}>
        {common}
        {series.map((s, i) => (
          <Bar key={s.metric} dataKey={s.label} fill={s.color} maxBarSize={34}
            stackId={stacked ? "stack" : undefined}
            radius={!stacked || i === series.length - 1 ? [4, 4, 0, 0] : undefined} />
        ))}
      </BarChart>
    );
  }

  return (
    <div className="card panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3>{title}</h3>
        {onDelete && (
          <button className="small" style={{ padding: "1px 8px" }}
            title="Delete this custom chart" onClick={onDelete}>✕</button>
        )}
      </div>
      <div style={{ height: 230 }}>
        <ResponsiveContainer>{chart}</ResponsiveContainer>
      </div>
    </div>
  );
}

export function CustomChartPanel({ chart, facts, onDelete }: {
  chart: CustomChart; facts: FactPivot; onDelete: () => void;
}) {
  return (
    <ChartPanel title={chart.name} kind={chart.chart} group={chart.unit_group}
      metrics={chart.metrics} facts={facts} onDelete={onDelete} />
  );
}

/** Headline stat tiles: latest FY value, YoY delta, trace chip. */
export function KpiTiles({ facts, metrics }: {
  facts: FactPivot; metrics: string[];
}) {
  const byName = new Map(facts.metrics.map((m) => [m.metric, m]));
  const tiles = [];
  for (const name of metrics) {
    const m = byName.get(name);
    if (!m) continue;
    const years = facts.years.filter((y) => m.values[String(y)] !== null
      && m.values[String(y)] !== undefined);
    if (years.length === 0) continue;
    const latest = Math.max(...years);
    const value = m.values[String(latest)]!;
    const prev = m.values[String(latest - 1)];
    const group = groupForUnit(m.unit);
    let delta: string | null = null;
    let up: boolean | null = null;
    if (prev !== null && prev !== undefined) {
      if (group === "percent") {
        const pp = (value - prev) * 100;
        delta = `${pp >= 0 ? "+" : ""}${pp.toFixed(1)} pp`;
        up = pp >= 0;
      } else if (prev !== 0) {
        const pct = (value / prev - 1) * 100;
        delta = `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
        up = pct >= 0;
      }
    }
    tiles.push(
      <div key={name} className="tile">
        <div className="tile-label">{m.label}</div>
        <div className="tile-value">{formatByGroup(value, group)}</div>
        <div className="tile-foot">
          {delta && (
            <span className={up ? "delta-up" : "delta-down"}>
              {up ? "▲" : "▼"} {delta}
            </span>
          )}
          <span className="muted small">FY{latest}</span>
          <TraceChips citations={[`fact:${m.fact_ids[String(latest)]}`]} />
        </div>
      </div>,
    );
  }
  if (tiles.length === 0) return null;
  return (
    <div className="card panel">
      <h3>Headline KPIs</h3>
      <div className="tile-grid">{tiles}</div>
    </div>
  );
}

/** DuPont: ROE = net margin × asset turnover × equity multiplier, per year. */
export function DuPontPanel({ facts }: { facts: FactPivot }) {
  const byName = new Map(facts.metrics.map((m) => [m.metric, m]));
  const parts = ["net_margin", "asset_turnover", "equity_multiplier", "roe"];
  if (parts.some((p) => !byName.has(p))) return null;
  const rows = facts.years
    .filter((y) => parts.every((p) => byName.get(p)!.values[String(y)] != null))
    .sort((a, b) => b - a);
  if (rows.length === 0) return null;

  return (
    <div className="card panel">
      <h3>DuPont decomposition</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        ROE = net margin × asset turnover × equity multiplier
      </p>
      <div className="scroll-x">
        <table className="data">
          <thead>
            <tr>
              <th>FY</th><th>Net margin</th><th>Asset turnover</th>
              <th>Leverage</th><th>= ROE</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((y) => (
              <tr key={y}>
                <td>FY{y}</td>
                {parts.map((p) => {
                  const m = byName.get(p)!;
                  const v = m.values[String(y)]!;
                  return (
                    <td key={p}>
                      {formatByGroup(v, groupForUnit(m.unit))}{" "}
                      <TraceChips citations={[`fact:${m.fact_ids[String(y)]}`]} />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const VALUATION_LABELS: Record<string, string> = {
  market_cap: "Market cap", pe: "P/E", ps: "P/S", pb: "P/B", ev: "EV",
  ev_ebitda: "EV / EBITDA", fcf_yield: "FCF yield",
  dividend_yield: "Dividend yield", buyback_yield: "Buyback yield",
};
const VALUATION_PERCENT = new Set(["fcf_yield", "dividend_yield", "buyback_yield"]);
const VALUATION_MULTIPLE = new Set(["pe", "ps", "pb", "ev_ebitda"]);

export function ValuationPanel({ companyId }: { companyId: number }) {
  const [valuation, setValuation] = useState<Valuation | null>(null);

  useEffect(() => {
    setValuation(null);
    api.getValuation(companyId).then(setValuation).catch(() => {});
  }, [companyId]);

  if (!valuation) return null;
  if (!valuation.available) {
    return (
      <div className="card panel">
        <h3>Valuation</h3>
        <p className="muted small" style={{ margin: 0 }}>
          Not available: {valuation.reason}
        </p>
      </div>
    );
  }

  return (
    <div className="card panel">
      <h3>Valuation</h3>
      <p className="muted small" style={{ marginTop: 0 }}>
        {valuation.ticker} · {valuation.price} as of {valuation.asof} ·{" "}
        <a href={valuation.source_url} target="_blank" rel="noreferrer">
          quote source ↗
        </a>{" "}
        · fundamentals FY{valuation.fiscal_year}
      </p>
      <div className="tile-grid">
        {(valuation.metrics ?? []).map((m) => (
          <div key={m.metric} className="tile" title={m.formula}>
            <div className="tile-label">{VALUATION_LABELS[m.metric] ?? m.metric}</div>
            <div className="tile-value">
              {VALUATION_PERCENT.has(m.metric)
                ? formatByGroup(m.value, "percent")
                : VALUATION_MULTIPLE.has(m.metric)
                  ? formatByGroup(m.value, "multiple")
                  : formatByGroup(m.value, "currency")}
            </div>
            <div className="tile-foot">
              <TraceChips citations={m.inputs.map((id) => `fact:${id}`)} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PresetPanel({ spec, facts, companyId }: {
  spec: PanelSpec; facts: FactPivot; companyId: number;
}) {
  if (spec.kind === "tiles") return <KpiTiles facts={facts} metrics={spec.metrics} />;
  if (spec.kind === "dupont") return <DuPontPanel facts={facts} />;
  if (spec.kind === "valuation") return <ValuationPanel companyId={companyId} />;
  return (
    <ChartPanel title={spec.title} kind={spec.kind} group={spec.group}
      metrics={spec.metrics} facts={facts} />
  );
}
