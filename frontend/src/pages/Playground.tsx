import { useState } from "react"
import type { AppContext } from "../App"

export default function Playground({ projectId, apiKey, apiUrl }: AppContext) {
  const [prompt,    setPrompt]    = useState("You are a helpful customer support agent.")
  const [promptB,   setPromptB]   = useState("")
  const [dataset,   setDataset]   = useState("")
  const [criteria,  setCriteria]  = useState("accurate,helpful,professional")
  const [mode,      setMode]      = useState<"single"|"ab">("single")
  const [running,   setRunning]   = useState(false)
  const [result,    setResult]    = useState<any>(null)
  const [abResult,  setAbResult]  = useState<any>(null)
  const [error,     setError]     = useState("")

  const headers = {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type":  "application/json"
  }

  async function runEval() {
    if (!dataset.trim()) { setError("Enter a dataset name"); return }
    setRunning(true); setError(""); setResult(null)

    try {
      const r = await fetch(`${apiUrl}/api/evals/run`, {
        method: "POST", headers,
        body: JSON.stringify({
          project:        projectId,
          dataset_name:   dataset,
          name:           `playground-${Date.now()}`,
          system_prompt:  prompt,
          judge_criteria: criteria.split(",").map(s => s.trim()),
        })
      })
      const run = await r.json()

      // Poll
      let attempts = 0
      while (attempts < 30) {
        await new Promise(res => setTimeout(res, 4000))
        const poll = await fetch(`${apiUrl}/api/evals/${run.run_id}`, { headers })
        const data = await poll.json()
        if (data.status === "completed") { setResult(data); break }
        if (data.status === "failed")    { setError("Eval failed"); break }
        attempts++
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  async function runABTest() {
    if (!dataset.trim() || !promptB.trim()) {
      setError("Enter dataset name and Prompt B"); return
    }
    setRunning(true); setError(""); setAbResult(null)

    try {
      const r = await fetch(`${apiUrl}/api/ab/run`, {
        method: "POST", headers,
        body: JSON.stringify({
          dataset_name:   dataset,
          prompt_a:       prompt,
          prompt_b:       promptB,
          judge_criteria: criteria.split(",").map(s => s.trim()),
        })
      })
      const run = await r.json()

      // Poll
      let attempts = 0
      while (attempts < 30) {
        await new Promise(res => setTimeout(res, 4000))
        const poll = await fetch(`${apiUrl}/api/ab/${run.test_id}`, { headers })
        const data = await poll.json()
        if (data.status === "completed") { setAbResult(data.result); break }
        if (data.status === "failed")    { setError(data.error || "A/B test failed"); break }
        attempts++
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const scoreColor = (s: number) =>
    s >= 8 ? "#10b981" : s >= 6 ? "#f59e0b" : "#ef4444"

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0" }}>
      <div style={{ marginBottom: "20px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
          Prompt playground
        </h1>
        <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
          Test prompt changes against your golden dataset — no code required
        </p>
      </div>

      {/* Mode toggle */}
      <div style={{ display: "flex", gap: "6px", marginBottom: "20px" }}>
        {(["single", "ab"] as const).map(m => (
          <button key={m} onClick={() => setMode(m)} style={{
            padding: "7px 16px", borderRadius: "6px", fontSize: "12px",
            fontWeight: 600, cursor: "pointer",
            border:     `1px solid ${mode === m ? "#6366f1" : "#334155"}`,
            background: mode === m ? "#6366f1" : "transparent",
            color:      mode === m ? "white"   : "#64748b"
          }}>
            {m === "single" ? "Single eval" : "A/B test"}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        {/* Left — config */}
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>

          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", padding: "16px"
          }}>
            <label style={{ fontSize: "11px", color: "#64748b", display: "block",
                            marginBottom: "6px", textTransform: "uppercase" }}>
              {mode === "ab" ? "Prompt A (current)" : "System prompt"}
            </label>
            <textarea
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              rows={6}
              style={{
                width: "100%", padding: "10px", borderRadius: "7px",
                border: "1px solid #334155", background: "#0f172a",
                color: "#e2e8f0", fontSize: "13px",
                resize: "vertical", boxSizing: "border-box",
                fontFamily: "monospace", lineHeight: 1.6
              }}
            />
          </div>

          {mode === "ab" && (
            <div style={{
              background: "#1e293b", border: "1px solid #6366f1",
              borderRadius: "10px", padding: "16px"
            }}>
              <label style={{ fontSize: "11px", color: "#64748b", display: "block",
                              marginBottom: "6px", textTransform: "uppercase" }}>
                Prompt B (challenger)
              </label>
              <textarea
                value={promptB}
                onChange={e => setPromptB(e.target.value)}
                placeholder="Enter the new prompt you want to test..."
                rows={6}
                style={{
                  width: "100%", padding: "10px", borderRadius: "7px",
                  border: "1px solid #334155", background: "#0f172a",
                  color: "#e2e8f0", fontSize: "13px",
                  resize: "vertical", boxSizing: "border-box",
                  fontFamily: "monospace", lineHeight: 1.6
                }}
              />
            </div>
          )}

          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", padding: "16px",
            display: "flex", flexDirection: "column", gap: "10px"
          }}>
            <div>
              <label style={{ fontSize: "11px", color: "#64748b",
                              display: "block", marginBottom: "5px",
                              textTransform: "uppercase" }}>
                Dataset name
              </label>
              <input
                value={dataset}
                onChange={e => setDataset(e.target.value)}
                placeholder="e.g. support-golden-v1"
                style={{
                  width: "100%", padding: "8px 10px", borderRadius: "6px",
                  border: "1px solid #334155", background: "#0f172a",
                  color: "#e2e8f0", fontSize: "13px", boxSizing: "border-box"
                }}
              />
            </div>
            <div>
              <label style={{ fontSize: "11px", color: "#64748b",
                              display: "block", marginBottom: "5px",
                              textTransform: "uppercase" }}>
                Judge criteria (comma separated)
              </label>
              <input
                value={criteria}
                onChange={e => setCriteria(e.target.value)}
                style={{
                  width: "100%", padding: "8px 10px", borderRadius: "6px",
                  border: "1px solid #334155", background: "#0f172a",
                  color: "#e2e8f0", fontSize: "13px", boxSizing: "border-box"
                }}
              />
            </div>
          </div>

          {error && (
            <div style={{
              background: "#450a0a", border: "1px solid #7f1d1d",
              borderRadius: "7px", padding: "10px 14px",
              color: "#f87171", fontSize: "12px"
            }}>
              {error}
            </div>
          )}

          <button
            onClick={mode === "single" ? runEval : runABTest}
            disabled={running}
            style={{
              padding: "11px", background: running ? "#334155" : "#6366f1",
              color: "white", border: "none", borderRadius: "8px",
              fontSize: "14px", fontWeight: 600, cursor: running ? "default" : "pointer"
            }}
          >
            {running
              ? "Running... (this takes 30-60s)"
              : mode === "single" ? "▶ Run eval" : "▶ Run A/B test"}
          </button>
        </div>

        {/* Right — results */}
        <div>
          {!result && !abResult && !running && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center",
              color: "#475569"
            }}>
              <div style={{ fontSize: "40px", marginBottom: "12px" }}>🧪</div>
              <p style={{ margin: 0 }}>Results will appear here after running</p>
            </div>
          )}

          {running && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center"
            }}>
              <div style={{
                width: "40px", height: "40px", margin: "0 auto 16px",
                border: "3px solid #334155", borderTop: "3px solid #6366f1",
                borderRadius: "50%", animation: "spin 1s linear infinite"
              }}/>
              <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
              <p style={{ color: "#94a3b8", margin: 0, fontSize: "13px" }}>
                Running eval against your dataset...
              </p>
            </div>
          )}

          {/* Single eval result */}
          {result && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", overflow: "hidden"
            }}>
              <div style={{
                padding: "14px 16px", borderBottom: "1px solid #334155",
                display: "flex", gap: "16px"
              }}>
                {[
                  { label: "Pass rate", value: `${((result.pass_rate||0)*100).toFixed(0)}%`,
                    color: scoreColor((result.pass_rate||0)*10) },
                  { label: "Avg score", value: `${(result.avg_score||0).toFixed(2)}/10`,
                    color: scoreColor(result.avg_score||0) },
                  { label: "Passed",   value: `${result.passed||0}/${result.total||0}`,
                    color: "#94a3b8" },
                ].map(s => (
                  <div key={s.label}>
                    <p style={{ fontSize: "10px", color: "#475569", margin: "0 0 2px",
                                textTransform: "uppercase" }}>{s.label}</p>
                    <p style={{ fontSize: "18px", fontWeight: 700,
                                color: s.color, margin: 0 }}>{s.value}</p>
                  </div>
                ))}
              </div>
              <div style={{ maxHeight: "400px", overflowY: "auto" }}>
                {(result.results || []).map((r: any, i: number) => (
                  <div key={i} style={{
                    padding: "10px 16px",
                    borderBottom: "1px solid #1e3a5f",
                    display: "flex", gap: "10px", alignItems: "flex-start"
                  }}>
                    <span style={{
                      padding: "2px 8px", borderRadius: "99px",
                      fontSize: "11px", fontWeight: 700, flexShrink: 0,
                      background: r.passed ? "#052e16" : "#450a0a",
                      color:      r.passed ? "#4ade80" : "#f87171"
                    }}>
                      {(r.score||0).toFixed(1)}
                    </span>
                    <div>
                      <p style={{ fontSize: "12px", color: "#e2e8f0",
                                  margin: "0 0 3px" }}>
                        {r.input?.slice(0,80)}
                      </p>
                      <p style={{ fontSize: "11px", color: "#475569",
                                  margin: 0, fontStyle: "italic" }}>
                        {r.reasoning?.slice(0,100)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* A/B test result */}
          {abResult && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "16px"
            }}>
              {/* Winner banner */}
              <div style={{
                background: abResult.is_improvement ? "#052e16" :
                            abResult.winner === "a"  ? "#450a0a" : "#0c1a4f",
                border: `1px solid ${
                  abResult.is_improvement ? "#166534" :
                  abResult.winner === "a"  ? "#991b1b" : "#1e3a8a"
                }`,
                borderRadius: "8px", padding: "12px 14px", marginBottom: "14px"
              }}>
                <p style={{
                  fontSize: "14px", fontWeight: 700, margin: "0 0 4px",
                  color: abResult.is_improvement ? "#4ade80" :
                         abResult.winner === "a"  ? "#f87171" : "#93c5fd"
                }}>
                  {!abResult.is_significant
                    ? "⚠ No significant difference"
                    : abResult.is_improvement
                    ? "✓ Prompt B is better — safe to deploy"
                    : "✗ Prompt B is worse — do not deploy"}
                </p>
                <p style={{ fontSize: "12px", color: "#94a3b8", margin: 0 }}>
                  {abResult.recommendation}
                </p>
              </div>

              {/* Stats comparison */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginBottom: "14px" }}>
                {["a","b"].map(v => {
                  const variant = abResult[`variant_${v}`]
                  const isWinner = abResult.winner === v && abResult.is_significant
                  return (
                    <div key={v} style={{
                      background: "#0f172a",
                      border: `1px solid ${isWinner ? "#6366f1" : "#334155"}`,
                      borderRadius: "7px", padding: "10px 12px"
                    }}>
                      <p style={{ fontSize: "11px", color: "#64748b",
                                  margin: "0 0 6px", textTransform: "uppercase",
                                  display: "flex", justifyContent: "space-between" }}>
                        Prompt {v.toUpperCase()}
                        {isWinner && <span style={{ color: "#6366f1" }}>★ Winner</span>}
                      </p>
                      <p style={{ fontSize: "18px", fontWeight: 700,
                                  color: scoreColor((variant?.pass_rate||0)*10), margin: "0 0 2px" }}>
                        {((variant?.pass_rate||0)*100).toFixed(0)}% pass
                      </p>
                      <p style={{ fontSize: "13px", color: "#94a3b8", margin: 0 }}>
                        {(variant?.avg_score||0).toFixed(2)}/10 avg score
                      </p>
                    </div>
                  )
                })}
              </div>

              {/* Stats */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: "6px" }}>
                {[
                  { label: "p-value",     value: abResult.p_value?.toFixed(3) },
                  { label: "Effect size", value: abResult.effect_size_label },
                  { label: "Score delta", value: `${abResult.score_delta > 0 ? "+" : ""}${abResult.score_delta?.toFixed(2)}` },
                ].map(s => (
                  <div key={s.label} style={{
                    background: "#0f172a", borderRadius: "6px", padding: "8px 10px", textAlign: "center"
                  }}>
                    <p style={{ fontSize: "10px", color: "#475569", margin: "0 0 2px",
                                textTransform: "uppercase" }}>{s.label}</p>
                    <p style={{ fontSize: "13px", fontWeight: 600,
                                color: "#94a3b8", margin: 0 }}>{s.value}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}