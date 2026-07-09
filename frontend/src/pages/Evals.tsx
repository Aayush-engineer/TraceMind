// pages/Evals.tsx
import { useState, useCallback, memo } from "react"
import type { AppContext } from "../App"
import { useApi } from "../hooks/useApi"
import { apiPost, invalidateCache } from "../lib/api"
import type { EvalRun, EvalResult } from "../lib/types"
import { scoreColor, statusChip } from "../lib/types"

const ResultRow = memo(function ResultRow({ r }: { r: EvalResult }) {
  const color = scoreColor(r.score || 0)
  return (
    <div style={{ padding: "11px 14px", borderBottom: "1px solid var(--b1)", borderLeft: `2px solid ${r.passed ? "var(--p0)" : "var(--r0)"}` }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "5px" }}>
        <p style={{ fontFamily: "var(--f-data)", fontSize: "11px", color: "var(--t0)", margin: 0, flex: 1, paddingRight: 10, lineHeight: 1.5 }}>{r.input}</p>
        <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 3 }}>
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "16px", fontWeight: 700, color }}>{(r.score || 0).toFixed(1)}</span>
          <span className={`sig ${r.passed ? "sig-p" : "sig-r"}`}>{r.passed ? "PASS" : "FAIL"}</span>
        </div>
      </div>
      {r.reasoning && (
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0, lineHeight: 1.5, borderTop: "1px solid var(--b1)", paddingTop: 5, marginTop: 5 }}>
          {r.reasoning}
        </p>
      )}
    </div>
  )
})

export default function Evals({ projectId, apiKey, apiUrl }: AppContext) {
  const [selected, setSelected] = useState<EvalRun | null>(null)
  const [running,  setRunning]  = useState(false)

  const { data, loading, refetch } = useApi<{ runs: EvalRun[] }>(
    `${apiUrl}/api/metrics/${projectId}/evals?limit=20`,
    apiKey,
    { interval: 20_000 }
  )

  const runs = data?.runs ?? []

  const loadResults = useCallback(async (run: EvalRun) => {
    if (run.results) { setSelected(run); return }
    try {
      const d = await apiPost<EvalRun>(`${apiUrl}/api/evals/${run.run_id}`, apiKey, undefined as any)
      setSelected({ ...run, ...d, results: (d as any).results || [] })
    } catch { setSelected(run) }
  }, [apiUrl, apiKey])

  const runNewEval = useCallback(async () => {
    const dataset = prompt("Dataset name:", "support-golden-v1")
    if (!dataset) return
    setRunning(true)
    try {
      await apiPost(`${apiUrl}/api/evals/run`, apiKey, {
        project: projectId, dataset_name: dataset,
        name: `eval-${new Date().toISOString().slice(0, 10)}`,
        judge_criteria: ["accurate", "helpful", "professional"],
      })
      invalidateCache("evals")
      setTimeout(refetch, 2000)
      setTimeout(refetch, 8000)
      setTimeout(refetch, 20000)
    } catch {/**/ }
    finally { setRunning(false) }
  }, [apiUrl, apiKey, projectId, refetch])

  return (
    <div style={{ padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "16px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px" }}>Eval Runs</h1>
          <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>[EVL] GOLDEN DATASET EVALUATION HISTORY</p>
        </div>
        <button onClick={runNewEval} disabled={running} className="btn btn-p">{running ? "STARTING…" : "+ RUN EVAL"}</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 400px" : "1fr", gap: "12px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {loading && !runs.length ? (
            [1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 90 }}/>)
          ) : runs.length === 0 ? (
            <div className="panel"><div className="empty"><span className="empty-glyph">◆</span><p className="empty-title">No runs yet</p><button onClick={runNewEval} className="btn btn-p" style={{ marginTop: 8 }}>RUN FIRST EVAL</button></div></div>
          ) : runs.map(run => {
            const pr    = run.pass_rate || 0
            const color = scoreColor(pr * 10)
            const isSel = selected?.run_id === run.run_id
            return (
              <div key={run.run_id} onClick={() => loadResults(run)} className="panel" style={{
                padding: "14px 16px", cursor: "pointer",
                background: isSel ? "var(--overlay)" : "var(--surface)",
                borderColor: isSel ? "var(--pb)" : "var(--b1)",
                transition: "border-color var(--t-fast), background var(--t-fast)",
              }}
              onMouseEnter={e => { if (!isSel) { (e.currentTarget as HTMLElement).style.borderColor = "var(--b2)"; (e.currentTarget as HTMLElement).style.background = "var(--raised)" } }}
              onMouseLeave={e => { if (!isSel) { (e.currentTarget as HTMLElement).style.borderColor = "var(--b1)"; (e.currentTarget as HTMLElement).style.background = "var(--surface)" } }}
              >
                <div className="panel-accent"/>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontFamily: "var(--f-display)", fontSize: "13px", fontWeight: 600, color: "var(--t0)" }}>{run.name || "unnamed"}</span>
                    <span className={`sig ${statusChip(run.status)}`}>{run.status?.toUpperCase()}</span>
                  </div>
                  <span style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)" }}>
                    {run.created_at ? new Date(run.created_at).toLocaleDateString() : "—"}
                  </span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "6px" }}>
                  {[
                    { l: "PASS RATE", v: `${(pr * 100).toFixed(0)}%`,              c: color },
                    { l: "AVG SCORE", v: `${(run.avg_score || 0).toFixed(2)}`,      c: scoreColor(run.avg_score || 0) },
                    { l: "CASES",     v: `${run.passed||0}✓ ${run.failed||0}✗`,    c: "var(--t2)" },
                  ].map(m => (
                    <div key={m.l} style={{ background: "var(--base)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", padding: "8px 10px" }}>
                      <p style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", margin: "0 0 4px", letterSpacing: "0.14em" }}>{m.l}</p>
                      <p style={{ fontFamily: "var(--f-mono)", fontSize: "15px", fontWeight: 700, color: m.c, margin: 0 }}>{m.v}</p>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {selected && (
          <div className="panel" style={{ padding: 0, height: "fit-content", position: "sticky", top: "20px" }}>
            <div className="panel-accent"/>
            <div className="panel-header">
              <span className="panel-label">PER-CASE RESULTS</span>
              <button onClick={() => setSelected(null)} className="btn btn-ghost" style={{ padding: "2px 8px" }}>✕</button>
            </div>
            <div style={{ maxHeight: "580px", overflowY: "auto" }}>
              {!selected.results?.length ? (
                <div className="empty" style={{ padding: "2rem" }}><p className="empty-title">{selected.status === "running" ? "EVAL IN PROGRESS…" : "NO RESULTS YET"}</p></div>
              ) : selected.results.map((r, i) => <ResultRow key={i} r={r}/>)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}