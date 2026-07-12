# Analyst-grade metrics & configurable dashboard — Design

Date: 2026-07-12
Status: Approved

## Goal

Expand from 4 charted metrics (revenue, net income, net/operating margin) to the
metric and visualization breadth of professional analyst/CFO tooling, while keeping
the app's core invariant: every number is Python-computed and traceable to filings.

## Decisions (from brainstorming)

- Curated preset panels **and** a custom chart builder; layout persisted in the DB.
- Valuation metrics included, using free Stooq quotes (cached, best-effort, US tickers).
- Default port moves 8000 → 3000 (8000 is taken by Surrealist on this machine).

## Backend

### Base metrics (edgar.py TAG_MAP: 13 → ~28)

Add with prioritized tag fallbacks: gross_profit, cost_of_revenue, rnd_expense,
sga_expense, depreciation_amortization, capex, dividends_paid, buybacks,
interest_expense, income_tax, pretax_income, inventory, receivables, payables,
ppe_net, goodwill, short_term_debt, investing_cash_flow, financing_cash_flow,
eps_basic, shares_diluted_wa. Global-mode table synonyms get gross profit / EBITDA /
operating cash flow additions.

### Derived metrics (metrics.py: 7 → ~35, two passes)

- **Pass 1 — derived values** (stored as facts, unit USD, so ratios can cite them):
  ebitda = operating_income + depreciation_amortization; fcf = operating_cash_flow −
  capex; total_debt = long_term_debt + short_term_debt; net_debt = total_debt − cash;
  invested_capital = equity + total_debt.
- **Pass 2 — ratios** over base + pass-1 facts: gross/ebitda/fcf margins; roa; roic
  (NOPAT = operating_income × (1 − effective_tax_rate), clamped 0–0.5); asset /
  inventory / receivables turnover; dso, dio, dpo, ccc (days); quick_ratio,
  cash_ratio, interest_coverage, net_debt_to_ebitda, equity_multiplier;
  rnd_intensity, sga_ratio, capex_intensity, effective_tax_rate; ocf_to_net_income;
  eps growth + fcf/ocf/operating-income/total-assets growth YoY; revenue and
  net-income 3-year CAGR; per-share: fcf_per_share, dividends_per_share,
  book_value_per_share, revenue_per_share; dividend_payout, shareholder_payout
  ((dividends+buybacks)/fcf).
- Each row carries `unit` (USD | ratio | days | x | USD/share) and the existing
  formula + input-fact-ids trace. Skip on missing/zero inputs, never LLM-computed.

### Valuation (new analysis/valuation.py + endpoint)

- `get_quote(conn, ticker)`: Stooq CSV `https://stooq.com/q/l/?s={t}.us&…&e=csv`,
  via web.fetch_url with 6 h TTL; returns {price, asof} or None.
- `GET /api/companies/{id}/valuation`: computed on request (prices are volatile, so
  not stored as facts): market_cap (price × shares_outstanding|shares_diluted_wa),
  pe, ps, pb, ev = mcap + net_debt, ev_ebitda, fcf_yield, dividend_yield,
  buyback_yield — each with formula + fact ids + price provenance. 404-free: returns
  `{available: false, reason}` when no ticker or no quote.

### Dashboard config

`settings` key `dashboard_config` (JSON): `{panels: {id: bool}, custom_charts:
[{id, name, chart: line|bar|area, unit_group, metrics: [names]}]}` — global, via the
existing settings API (add to DEFAULTS).

## Frontend

- `metricCatalog.ts`: metric → unit group + display label + fixed color assignment;
  formatters per unit group (currency compact, %, days, ×, $/share).
- Dashboard = panel grid, each panel auto-hides without data, toggleable via a
  **Customize** popover; **Add chart** modal (name, type, unit group, metric
  multi-select) renders like presets, deletable; both persisted via settings.
- Preset panels: Headline KPI tiles (latest FY + YoY delta + trace chip); Income
  statement (bars: revenue, gross profit, operating income, net income); Margins;
  Returns (roe/roa/roic); Cash flow (ocf/capex/fcf); Liquidity & leverage; Working
  capital (dso/dio/dpo/ccc); Expense structure; Per-share; Capital returns
  (dividends+buybacks stacked); Growth (YoY bars); DuPont table (net margin ×
  asset turnover × equity multiplier = ROE); Valuation tiles.
- dataviz rules hold: one axis per chart (unit groups enforce), ≤4 series + legend,
  fixed entity colors from the validated palette, facts table remains the relief.

## Port

Default 3000 everywhere: README, .claude/launch.json, vite proxy.

## Testing

pytest: new tag mapping, each ratio family incl. CAGR + clamps + zero-guards,
valuation math with mocked quote and missing-data paths, dashboard_config
persistence, valuation endpoint. Frontend: `tsc -b` build. Live verify on port 3000
with re-ingested AAPL.
