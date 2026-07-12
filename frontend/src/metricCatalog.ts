import type { FactPivot } from "./types";

/** Unit groups keep every chart on a single axis (dataviz: never mix scales). */
export type UnitGroup = "currency" | "percent" | "days" | "multiple" | "per_share" | "shares";

export const UNIT_GROUP_LABELS: Record<UnitGroup, string> = {
  currency: "Currency", percent: "Percent", days: "Days",
  multiple: "Multiple (×)", per_share: "Per share", shares: "Share count",
};

/** Map a stored fact unit to its group. */
export function groupForUnit(unit: string | null): UnitGroup {
  switch (unit) {
    case "ratio": return "percent";
    case "x": return "multiple";
    case "days": return "days";
    case "USD/share":
    case "USD/shares": return "per_share";
    case "shares": return "shares";
    default: return "currency";
  }
}

export function formatByGroup(value: number | null | undefined,
                              group: UnitGroup): string {
  if (value === null || value === undefined) return "–";
  switch (group) {
    case "percent": return `${(value * 100).toFixed(1)}%`;
    case "multiple": return `${value.toFixed(2)}×`;
    case "days": return `${value.toFixed(0)} d`;
    case "per_share": return value.toFixed(2);
    case "shares": return compact(value);
    default: return compact(value);
  }
}

function compact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 1e4) return `${(value / 1e3).toFixed(1)}K`;
  return abs >= 100 ? value.toFixed(0) : value.toFixed(2);
}

/** Validated categorical palette (dataviz reference, light mode), fixed order. */
export const PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300",
                        "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"];

// Fixed slot per metric so a metric keeps its color everywhere on the dashboard.
const COLOR_ORDER = [
  "revenue", "net_income", "operating_income", "gross_profit",
  "operating_cash_flow", "capex", "fcf", "ebitda",
  "gross_margin", "operating_margin", "net_margin", "ebitda_margin",
  "roe", "roa", "roic", "fcf_margin",
  "current_ratio", "quick_ratio", "debt_to_equity", "net_debt_to_ebitda",
  "dso", "dio", "dpo", "ccc",
  "rnd_intensity", "sga_ratio", "capex_intensity", "effective_tax_rate",
  "eps_diluted", "fcf_per_share", "dividends_per_share", "book_value_per_share",
  "dividends_paid", "buybacks",
  "revenue_growth_yoy", "net_income_growth_yoy", "eps_growth_yoy", "fcf_growth_yoy",
];

export function colorFor(metric: string): string {
  const idx = COLOR_ORDER.indexOf(metric);
  if (idx >= 0) return PALETTE[idx % PALETTE.length];
  let hash = 0;
  for (const ch of metric) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[hash % PALETTE.length];
}

export type PanelKind = "tiles" | "bars" | "stacked_bars" | "lines" | "area"
  | "dupont" | "valuation";

export interface PanelSpec {
  id: string;
  title: string;
  kind: PanelKind;
  group: UnitGroup;
  metrics: string[];
}

export const PRESET_PANELS: PanelSpec[] = [
  { id: "headline", title: "Headline KPIs", kind: "tiles", group: "currency",
    metrics: ["revenue", "net_income", "eps_diluted", "fcf",
              "gross_margin", "operating_margin", "net_margin", "roe"] },
  { id: "income_statement", title: "Income statement", kind: "bars",
    group: "currency",
    metrics: ["revenue", "gross_profit", "operating_income", "net_income"] },
  { id: "margins", title: "Margins", kind: "lines", group: "percent",
    metrics: ["gross_margin", "operating_margin", "net_margin", "ebitda_margin"] },
  { id: "returns", title: "Returns on capital", kind: "lines", group: "percent",
    metrics: ["roe", "roa", "roic"] },
  { id: "cash_flow", title: "Cash flow & FCF", kind: "bars", group: "currency",
    metrics: ["operating_cash_flow", "capex", "fcf"] },
  { id: "liquidity", title: "Liquidity & leverage", kind: "lines",
    group: "multiple",
    metrics: ["current_ratio", "quick_ratio", "debt_to_equity",
              "net_debt_to_ebitda"] },
  { id: "working_capital", title: "Working-capital cycle", kind: "lines",
    group: "days", metrics: ["dso", "dio", "dpo", "ccc"] },
  { id: "expenses", title: "Expense structure (% of revenue)", kind: "lines",
    group: "percent",
    metrics: ["rnd_intensity", "sga_ratio", "capex_intensity",
              "effective_tax_rate"] },
  { id: "per_share", title: "Per-share", kind: "lines", group: "per_share",
    metrics: ["eps_diluted", "fcf_per_share", "dividends_per_share",
              "book_value_per_share"] },
  { id: "capital_returns", title: "Capital returned to shareholders",
    kind: "stacked_bars", group: "currency",
    metrics: ["dividends_paid", "buybacks"] },
  { id: "growth", title: "Growth (YoY)", kind: "bars", group: "percent",
    metrics: ["revenue_growth_yoy", "net_income_growth_yoy", "eps_growth_yoy",
              "fcf_growth_yoy"] },
  { id: "dupont", title: "DuPont decomposition", kind: "dupont",
    group: "percent",
    metrics: ["net_margin", "asset_turnover", "equity_multiplier", "roe"] },
  { id: "valuation", title: "Valuation", kind: "valuation", group: "multiple",
    metrics: [] },
];

export interface CustomChart {
  id: string;
  name: string;
  chart: "line" | "bar" | "area";
  unit_group: UnitGroup;
  metrics: string[];
}

export interface DashboardConfig {
  panels?: Record<string, boolean>;
  custom_charts?: CustomChart[];
}

export function panelEnabled(config: DashboardConfig, id: string): boolean {
  return config.panels?.[id] !== false; // default: on
}

/** Metrics present in the facts pivot, grouped by unit group (for the builder). */
export function availableMetrics(facts: FactPivot):
    Record<UnitGroup, { metric: string; label: string }[]> {
  const out: Record<UnitGroup, { metric: string; label: string }[]> = {
    currency: [], percent: [], days: [], multiple: [], per_share: [], shares: [],
  };
  for (const m of facts.metrics) {
    if (Object.values(m.values).every((v) => v === null)) continue;
    out[groupForUnit(m.unit)].push({ metric: m.metric, label: m.label });
  }
  return out;
}
