# Analyst-Grade Metrics & Configurable Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Grow the fundamentals store to ~28 base + ~35 derived traced metrics, add a Stooq-quote valuation endpoint, and replace the fixed two-chart dashboard with 12 toggleable analyst panels plus a DB-persisted custom chart builder; default port becomes 3000.

**Architecture:** Base metrics come from an expanded XBRL tag map. Derived metrics compute in two Python passes (values like EBITDA/FCF stored as facts first, then ratios that may cite them), keeping the formula+inputs trace chain. Valuation is computed per request from a cached quote, never stored. The dashboard reads one `dashboard_config` settings key.

**Tech Stack:** existing FastAPI/SQLite/pytest backend; React + Recharts frontend.

**Execution note:** repo root `D:\Projects\AnnualReportAnalyser`; tests run from `backend/` with `..\.venv\Scripts\python -m pytest`. Commit after each task.

---

### Task M1: Expanded XBRL tag map + table synonyms

**Files:** Modify `backend/app/ingest/edgar.py` (TAG_MAP, METRIC_LABELS), `backend/app/ingest/pipeline.py` (TABLE_METRIC_SYNONYMS); Test `backend/tests/test_edgar.py` (extend FACTS fixture + assertions).

1. Extend `test_company_facts_mapping` fixture with GrossProfit, ResearchAndDevelopmentExpense, PaymentsToAcquirePropertyPlantAndEquipment, PaymentsForRepurchaseOfCommonStock, IncomeTaxExpenseBenefit, WeightedAverageNumberOfDilutedSharesOutstanding datapoints; assert `gross_profit`, `rnd_expense`, `capex`, `buybacks`, `income_tax`, `shares_diluted_wa` extracted. Run: FAIL.
2. Add ~15 new (metric, [tags]) pairs and labels per design doc. New tags:
   gross_profit[GrossProfit], cost_of_revenue[CostOfGoodsAndServicesSold, CostOfRevenue, CostOfGoodsSold], rnd_expense[ResearchAndDevelopmentExpense], sga_expense[SellingGeneralAndAdministrativeExpense], depreciation_amortization[DepreciationDepletionAndAmortization, DepreciationAmortizationAndAccretionNet], capex[PaymentsToAcquirePropertyPlantAndEquipment, PaymentsToAcquireProductiveAssets], dividends_paid[PaymentsOfDividends, PaymentsOfDividendsCommonStock], buybacks[PaymentsForRepurchaseOfCommonStock], interest_expense[InterestExpense, InterestExpenseNonoperating], income_tax[IncomeTaxExpenseBenefit], pretax_income[IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest, IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments], inventory[InventoryNet], receivables[AccountsReceivableNetCurrent], payables[AccountsPayableCurrent], ppe_net[PropertyPlantAndEquipmentNet], goodwill[Goodwill], short_term_debt[LongTermDebtCurrent, DebtCurrent], investing_cash_flow[NetCashProvidedByUsedInInvestingActivities], financing_cash_flow[NetCashProvidedByUsedInFinancingActivities], eps_basic[EarningsPerShareBasic], shares_diluted_wa[WeightedAverageNumberOfDilutedSharesOutstanding].
3. Table synonyms add: gross_profit ["gross profit"], operating_cash_flow ["cash generated from operations", "net cash from operating activities"], ebitda ["ebitda"].
4. Run test file: PASS. Commit `feat: expand XBRL extraction to ~28 base metrics`.

### Task M2: Two-pass derived metrics

**Files:** Modify `backend/app/analysis/metrics.py` (add `compute_derived_values`, extend `compute_ratios`, units), `backend/app/ingest/pipeline.py` (`_store_derived_ratios` → two passes, store unit); Test `backend/tests/test_metrics.py`, `backend/tests/test_pipeline.py`.

1. Tests first: `compute_derived_values` returns ebitda/fcf/total_debt/net_debt/invested_capital rows with unit "USD", formula, inputs; missing-input skip. `compute_ratios` on facts including derived values returns gross_margin, ebitda_margin, fcf_margin, roa, roic (verify tax clamp with weird tax values), asset_turnover, dso/dio/dpo/ccc (unit "days"), quick_ratio, interest_coverage, net_debt_to_ebitda, equity_multiplier, rnd_intensity, effective_tax_rate, ocf_to_net_income, fcf_per_share/dividends_per_share/book_value_per_share (unit "USD/share"), dividend_payout, revenue_cagr_3y ((v_y/v_{y-3})**(1/3)−1, needs 4 years), extra growth rows; every row has `unit`. Zero-division guards throughout. Run: FAIL.
2. Implement: table-driven `_RATIOS` gains a unit column; add `_DAYS`, `_PER_SHARE` (denominator shares_diluted_wa fallback shares_outstanding), `_CAGR`; roic/eff-tax special-cased. `compute_derived_values(facts)` sums/differences with per-component optionality (total_debt works with only long_term_debt; fcf requires both ocf and capex).
3. Pipeline `_store_derived_ratios`: pass 1 store derived values, re-query, pass 2 store ratios; `_upsert_fact` unit from row. Pipeline test asserts ebitda + gross_margin + ccc facts exist after EDGAR ingest (extend fixture with the new tags minimally).
4. Full backend pytest: PASS. Commit `feat: two-pass derived metrics (~35 traced ratios)`.

### Task M3: Valuation module + endpoint

**Files:** Create `backend/app/analysis/valuation.py`; Modify `backend/app/api/companies.py` (GET /companies/{id}/valuation); Test `backend/tests/test_valuation.py`, extend `backend/tests/test_api.py`.

1. Tests: `get_quote` parses Stooq CSV (mock web.fetch_url returning `Symbol,Date,Time,Open,High,Low,Close,Volume\nAAPL.US,2026-07-10,22:00:00,250,255,249,252.5,1000`), returns {price: 252.5, asof: "2026-07-10", source_url}; N/D row → None. `compute_valuation(conn, company_id, quote)` with seeded facts (net_income? uses eps) returns pe = price/eps_diluted, market_cap = price×shares_outstanding, ps, pb, ev = mcap+net_debt, ev_ebitda, fcf_yield = fcf/mcap, dividend_yield, buyback_yield; each entry {value, formula, inputs:[fact ids or "price"]}; missing fact → metric absent. Endpoint test: mocked quote → JSON with available:true; company without ticker → available:false. Run: FAIL.
2. Implement. Quote URL `https://stooq.com/q/l/?s={ticker}.us&f=sd2t2ohlcv&h&e=csv`, fetched via `web.fetch_url(conn, url, ttl=21600)`. Endpoint wires `get_quote` + `compute_valuation`, catches fetch errors → available:false with reason.
3. PASS. Commit `feat: valuation metrics from cached Stooq quotes`.

### Task M4: dashboard_config setting + port 3000

**Files:** Modify `backend/app/settings.py` (DEFAULTS["dashboard_config"] = "{}"), `README.md`, `.claude/launch.json`, `frontend/vite.config.ts` (proxy → 3000); Test: extend `backend/tests/test_api.py` settings roundtrip with dashboard_config.

Run backend pytest: PASS. Commit `feat: persist dashboard layout config; default port 3000`.

### Task M5: Frontend metric catalog + panel engine

**Files:** Create `frontend/src/metricCatalog.ts`, `frontend/src/components/panels.tsx` (generic ChartPanel + KpiTiles + DuPontTable + ValuationPanel helpers); Modify `frontend/src/api.ts` (valuation + config helpers), `frontend/src/types.ts`.

- `metricCatalog.ts`: `UNIT_GROUPS` (currency | percent | days | multiple | per_share); `METRIC_META: Record<string, {label, group, color}>` with fixed palette-slot colors; `formatByGroup(value, group)`; `PRESET_PANELS: PanelSpec[]` (id, title, chart type, metric list, unit group) covering the 12 design panels; helper `availableMetrics(facts)` .
- `panels.tsx`: `<ChartPanel spec facts/>` renders line/bar/area/stacked from the facts pivot with legend/tooltip/grid per dataviz spec, returns null when <1 series has data; `<KpiTiles facts/>` latest-FY value + YoY delta (green/red per direction) + trace chip; `<DuPontTable facts/>`; `<ValuationPanel companyId/>` fetching `/valuation`, tiles with formula tooltip + price provenance line.

Type-check: `npm run build` in `frontend/`: PASS (panels not yet wired). Commit.

### Task M6: Dashboard integration — customize + chart builder

**Files:** Modify `frontend/src/components/DashboardView.tsx` (replace TrendCharts with panel grid), Create `frontend/src/components/CustomizePanel.tsx` (panel toggles + add-chart modal).

- Load `dashboard_config` via settings API on mount; default: all presets on.
- Panel grid renders enabled presets in order + custom charts; Customize popover lists panels with checkboxes; Add-chart modal: name, type, unit group, multi-select of available metrics in that group; Save → PUT settings dashboard_config. Delete custom chart button.
- Keep facts table + reports card at bottom.
- Build: PASS. Commit `feat: analyst panel grid with customize + custom chart builder`.

### Task M7: Verify live on port 3000

1. Start server on 3000 (launch.json), re-fetch AAPL (re-ingest extracts new facts from cached SEC data).
2. Confirm facts count grew (expect ~45-60 metric rows across years), panels render, valuation panel shows P/E etc. (live Stooq call), customize + custom chart persist across reload.
3. Full backend pytest + `npm run build` green.
4. Update memory + final commit `feat: analyst-grade dashboard verified live`.
