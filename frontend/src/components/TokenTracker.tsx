import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { TokenReport } from "../types";

/** Header pill showing live session token totals; click for the call log. */
export function TokenTracker() {
  const [report, setReport] = useState<TokenReport | null>(null);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const load = () => api.getTokens().then(setReport).catch(() => {});
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const s = report?.session;
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="pill" title="Session token usage (input / output)"
        onClick={() => setOpen(!open)} style={{ fontVariantNumeric: "tabular-nums" }}>
        ▲ {s ? s.input_tokens.toLocaleString() : "–"} ▼{" "}
        {s ? s.output_tokens.toLocaleString() : "–"}
      </button>
      {open && report && (
        <div className="card" style={{ position: "absolute", right: 0, top: 36,
          width: 380, zIndex: 30, maxHeight: 420, overflowY: "auto",
          boxShadow: "0 8px 32px rgba(11,11,11,0.15)" }}>
          <h3>Token usage</h3>
          <p className="small muted" style={{ margin: "4px 0" }}>
            This session: {report.session.input_tokens.toLocaleString()} in ·{" "}
            {report.session.output_tokens.toLocaleString()} out ·{" "}
            {report.session.calls} calls
          </p>
          <p className="small muted" style={{ margin: "4px 0 10px" }}>
            All time: {report.all_time.input_tokens.toLocaleString()} in ·{" "}
            {report.all_time.output_tokens.toLocaleString()} out
          </p>
          {report.recent.length > 0 && (
            <div className="scroll-x">
              <table className="data small">
                <thead>
                  <tr><th>Call</th><th>Model</th><th>In</th><th>Out</th></tr>
                </thead>
                <tbody>
                  {report.recent.map((r) => (
                    <tr key={r.id}>
                      <td>{r.context || "chat"}</td>
                      <td>{r.model ?? r.provider}</td>
                      <td>{r.input_tokens.toLocaleString()}</td>
                      <td>{r.output_tokens.toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
