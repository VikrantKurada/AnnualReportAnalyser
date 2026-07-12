import { useState } from "react";
import { api, formatValue } from "../api";
import type { Trace } from "../types";

/** Clickable [source] chips that open the provenance modal for chunk:/fact: ids. */
export function TraceChips({ citations }: { citations: string[] | undefined }) {
  const [trace, setTrace] = useState<Trace | null>(null);
  const [open, setOpen] = useState(false);

  if (!citations || citations.length === 0) return null;

  const show = async (cite: string) => {
    const [kind, id] = cite.split(":");
    try {
      setTrace(await api.getTrace(kind, Number(id)));
      setOpen(true);
    } catch { /* stale citation */ }
  };

  return (
    <>
      {citations.map((c) => (
        <button key={c} className="cite" title={`Show source ${c}`}
          onClick={() => show(c)}>{c.replace(":", " ")}</button>
      ))}
      {open && trace && <TraceModal trace={trace} onClose={() => setOpen(false)} />}
    </>
  );
}

export function TraceModal({ trace, onClose }: { trace: Trace; onClose: () => void }) {
  const detail = (trace.detail ?? {}) as Record<string, unknown>;
  const inputs = trace.inputs as
    | { id: number; label: string; fiscal_year: number; value: number }[]
    | undefined;
  const table = trace.table as
    | { caption?: string; page?: number; source_url?: string }
    | undefined;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Source trace</h3>
        {trace.kind === "chunk" ? (
          <>
            <p className="small muted">
              {String(trace.form ?? "report")} · FY{String(trace.fiscal_year ?? "?")} ·
              section “{String(trace.section ?? "")}”
              {trace.page ? ` · page ${trace.page}` : ""}
            </p>
            {typeof trace.source_url === "string" && trace.source_url && (
              <p className="small">
                <a href={trace.source_url} target="_blank" rel="noreferrer">
                  Open original filing ↗
                </a>
              </p>
            )}
            <blockquote style={{ borderLeft: "3px solid var(--grid)", margin: 0,
              paddingLeft: 12, whiteSpace: "pre-wrap" }}>
              {String(trace.text ?? "")}
            </blockquote>
          </>
        ) : (
          <>
            <p>
              <strong>{String(trace.label ?? trace.metric)}</strong> · FY
              {String(trace.fiscal_year)} ={" "}
              <strong>{formatValue(trace.value as number, trace.unit as string)}</strong>
            </p>
            <p className="small muted">Source: {String(trace.source_kind)}</p>
            {trace.source_kind === "xbrl" && (
              <p className="small">
                XBRL tag <code>{String(detail.tag ?? "")}</code>
                {detail.accn ? <> · accession <code>{String(detail.accn)}</code></> : null}
                {detail.end ? <> · period end {String(detail.end)}</> : null}
              </p>
            )}
            {trace.source_kind === "derived" && (
              <>
                <p className="small">
                  Formula: <code>{String(detail.formula ?? "")}</code>
                </p>
                {inputs && inputs.length > 0 && (
                  <table className="data">
                    <thead>
                      <tr><th>Input</th><th>FY</th><th>Value</th></tr>
                    </thead>
                    <tbody>
                      {inputs.map((i) => (
                        <tr key={i.id}>
                          <td>{i.label}</td>
                          <td>{i.fiscal_year}</td>
                          <td>{formatValue(i.value, null)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
            {trace.source_kind === "table" && table && (
              <p className="small">
                From table “{table.caption ?? ""}”
                {table.page ? ` (page ${table.page})` : ""}
                {table.source_url && (
                  <> · <a href={table.source_url} target="_blank" rel="noreferrer">
                    original report ↗</a></>
                )}
              </p>
            )}
          </>
        )}
        <div className="row" style={{ justifyContent: "flex-end", marginTop: 12 }}>
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
