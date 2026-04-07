import { useEffect, useState, useCallback } from "react"
import type { AppContext } from "../App";

interface EvalRun {
  run_id:      string
  name:        string
  pass_rate:   number
  avg_score:   number
  status:      string
  total:       number
  passed:      number
  failed:      number
  created_at:  string
  results?:    EvalResult[]
}

interface EvalResult {
  input:     string
  score:     number
  passed:    boolean
  reasoning: string
}

export default function Evals({ projectId, apiKey, apiUrl }: AppContext) {
  const [runs,     setRuns]     = useState<EvalRun[]>([])
  const [selected, setSelected] = useState<EvalRun | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [running,  setRunning]  = useState(false)

  const headers = {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type":  "application/json"
  }

  const fetchRuns = useCallback(async () => {
    try {
      const res  = await fetch(`${apiUrl}/api/metrics/${projectId}/evals?limit=20`, { headers })
      const data = await res.json()
      setRuns(data.runs || [])
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId, apiKey])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  async function loadResults(run: EvalRun) {
    if (run.results) { setSelected(run); return }
    try {
      const res  = await fetch(`${apiUrl}/api/evals/${run.run_id}`, { headers })
      const data = await res.json()
      const updated = { ...run, results: data.results || [], ...data }
      setRuns(prev => prev.map(r => r.run_id === run.run_id ? updated : r))
      setSelected(updated)
    } catch { setSelected(run) }
  }

  async function runNewEval() {
    const dataset = prompt("Dataset name to evaluate against:", "support-golden-v1")
    if (!dataset) return
    setRunning(true)
    try {
      const res = await fetch(`${apiUrl}/api/evals/run`, {
        method: "POST", headers,
        body: JSON.stringify({
          project:        projectId,
          dataset_name:   dataset,
          name:           `eval-${new Date().toISOString().slice(0, 10)}`,
          judge_criteria: ["accurate", "helpful", "professional"]
        })
      })
      if (res.ok) {
        setTimeout(fetchRuns, 2000)
        setTimeout(fetchRuns, 8000)
        setTimeout(fetchRuns, 20000)
      }
    } catch { /* ignore */ }
    finally { setRunning(false) }
  }

  const scoreColor = (s: number) =>
    s >= 8 ? "#10b981" : s >= 6 ? "#f59e0b" : "#ef4444"

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0" }}>
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", marginBottom: "20px"
      }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
            Eval runs
          </h1>
          <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
            Golden dataset evaluation history — click a run to see per-case results
          </p>
        </div>
        <button onClick={runNewEval} disabled={running} style={{
          padding: "9px 16px", background: "#6366f1",
          color: "white", border: "none", borderRadius: "7px",
          fontSize: "13px", fontWeight: 600, cursor: "pointer",
          opacity: running ? 0.6 : 1
        }}>
          {running ? "Starting..." : "+ Run eval"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 420px" : "1fr", gap: "16px" }}>

        {/* Runs list */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {loading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#475569" }}>
              Loading...
            </div>
          ) : runs.length === 0 ? (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center", color: "#475569"
            }}>
              <p style={{ fontSize: "32px", margin: "0 0 8px" }}>✓</p>
              <p style={{ margin: "0 0 16px" }}>No eval runs yet</p>
              <button onClick={runNewEval} style={{
                padding: "8px 16px", background: "#6366f1",
                color: "white", border: "none", borderRadius: "6px",
                fontSize: "13px", cursor: "pointer"
              }}>
                Run your first eval
              </button>
            </div>
          ) : runs.map(run => (
            <div
              key={run.run_id}
              onClick={() => loadResults(run)}
              style={{
                background: selected?.run_id === run.run_id ? "#1e3a5f" : "#1e293b",
                border: `1px solid ${selected?.run_id === run.run_id ? "#6366f1" : "#334155"}`,
                borderRadius: "10px", padding: "16px 18px",
                cursor: "pointer", transition: "all 0.15s"
              }}
            >
              <div style={{ display: "flex", alignItems: "center",
                            justifyContent: "space-between", marginBottom: "10px" }}>
                <div>
                  <span style={{ fontWeight: 600, fontSize: "14px", color: "#f1f5f9" }}>
                    {run.name || "Unnamed run"}
                  </span>
                  <span style={{
                    marginLeft: "10px", padding: "2px 8px", borderRadius: "99px",
                    fontSize: "11px", fontWeight: 600,
                    background: run.status === "completed" ? "#052e16" :
                                run.status === "running"   ? "#0c1a4f" : "#450a0a",
                    color:      run.status === "completed" ? "#4ade80" :
                                run.status === "running"   ? "#818cf8" : "#f87171"
                  }}>
                    {run.status}
                  </span>
                </div>
                <span style={{ fontSize: "12px", color: "#475569" }}>
                  {run.created_at
                    ? new Date(run.created_at).toLocaleDateString()
                    : "—"}
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "8px" }}>
                {[
                  { label: "Pass rate", value: `${((run.pass_rate || 0) * 100).toFixed(0)}%`,
                    color: scoreColor((run.pass_rate || 0) * 10) },
                  { label: "Avg score", value: `${(run.avg_score || 0).toFixed(2)}/10`,
                    color: scoreColor(run.avg_score || 0) },
                  { label: "Cases",     value: `${run.passed || 0}✓ ${run.failed || 0}✗`,
                    color: "#94a3b8" },
                ].map(m => (
                  <div key={m.label} style={{
                    background: "#0f172a", borderRadius: "6px", padding: "8px 10px"
                  }}>
                    <p style={{ fontSize: "10px", color: "#475569", margin: "0 0 2px",
                                textTransform: "uppercase" }}>{m.label}</p>
                    <p style={{ fontSize: "14px", fontWeight: 700, color: m.color, margin: 0 }}>
                      {m.value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Results detail */}
        {selected && (
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", overflow: "hidden",
            height: "fit-content", position: "sticky", top: "20px"
          }}>
            <div style={{
              padding: "14px 16px", borderBottom: "1px solid #334155",
              display: "flex", alignItems: "center", justifyContent: "space-between"
            }}>
              <h3 style={{ fontSize: "13px", fontWeight: 600, color: "#f1f5f9", margin: 0 }}>
                Per-case results
              </h3>
              <button onClick={() => setSelected(null)} style={{
                background: "transparent", border: "none",
                color: "#475569", cursor: "pointer"
              }}>✕</button>
            </div>
            <div style={{ maxHeight: "600px", overflowY: "auto" }}>
              {(selected.results || []).map((r, i) => (
                <div key={i} style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid #1e3a5f"
                }}>
                  <div style={{ display: "flex", alignItems: "flex-start",
                                justifyContent: "space-between", marginBottom: "6px" }}>
                    <p style={{ fontSize: "12px", color: "#e2e8f0",
                                margin: 0, flex: 1, paddingRight: "12px",
                                lineHeight: 1.4 }}>
                      {r.input}
                    </p>
                    <div style={{ display: "flex", flexDirection: "column",
                                  alignItems: "flex-end", gap: "4px", flexShrink: 0 }}>
                      <span style={{
                        fontSize: "16px", fontWeight: 700,
                        color: scoreColor(r.score || 0)
                      }}>
                        {(r.score || 0).toFixed(1)}
                      </span>
                      <span style={{
                        padding: "1px 7px", borderRadius: "99px", fontSize: "10px",
                        background: r.passed ? "#052e16" : "#450a0a",
                        color:      r.passed ? "#4ade80" : "#f87171"
                      }}>
                        {r.passed ? "pass" : "fail"}
                      </span>
                    </div>
                  </div>
                  {r.reasoning && (
                    <p style={{ fontSize: "11px", color: "#475569",
                                margin: 0, lineHeight: 1.4,
                                fontStyle: "italic" }}>
                      {r.reasoning}
                    </p>
                  )}
                </div>
              ))}
              {(!selected.results || selected.results.length === 0) && (
                <div style={{ padding: "2rem", textAlign: "center", color: "#475569" }}>
                  {selected.status === "running" ? "Eval in progress..." : "No results yet"}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}