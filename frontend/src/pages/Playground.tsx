// pages/Playground.tsx
import { useState, useCallback, useRef, useMemo, memo } from "react"
import type { AppContext } from "../App"
import { apiPost } from "../lib/api"
import type { EvalRun, ABResult } from "../lib/types"
import { scoreColor } from "../lib/types"

const CRITERIA_DEFAULT = "accurate,helpful,professional"

// ─── Reusable poll helper ─────────────────────────────────────────────────────
async function pollUntilDone<T extends { status: string }>(
  url:     string,
  apiKey:  string,
  signal:  AbortSignal,
  onTick:  (pct: number) => void,
  maxTries = 30,
  interval = 4000
): Promise<T> {
  for (let i = 0; i < maxTries; i++) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError")
    await new Promise(res => setTimeout(res, interval))
    onTick(Math.min(90, ((i + 1) / maxTries) * 100))
    const res = await fetch(url, { headers: { "Authorization": `Bearer ${apiKey}` }, signal })
    const d: T = await res.json()
    if (d.status === "completed" || d.status === "failed") return d
  }
  throw new Error("Timed out waiting for eval")
}

// ─── Metric tile ─────────────────────────────────────────────────────────────
const Tile = memo(function Tile({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ flex: 1, background: "var(--overlay)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", padding: "8px 10px" }}>
      <p style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", margin: "0 0 3px", letterSpacing: "0.12em" }}>{label}</p>
      <p style={{ fontFamily: "var(--f-mono)", fontSize: "16px", fontWeight: 700, color, margin: 0 }}>{value}</p>
    </div>
  )
})

// ─── Result row ──────────────────────────────────────────────────────────────
const ResultRow = memo(function ResultRow({ r }: { r: any }) {
  return (
    <div style={{ padding: "10px 14px", borderBottom: "1px solid rgba(120,180,255,0.04)", display: "flex", gap: 10, alignItems: "flex-start", borderLeft: `2px solid ${r.passed ? "var(--p0)" : "var(--r0)"}` }}>
      <span className={`sig ${r.passed ? "sig-p" : "sig-r"}`} style={{ flexShrink: 0 }}>{(r.score || 0).toFixed(1)}</span>
      <div>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--t0)", margin: "0 0 3px" }}>{r.input?.slice(0, 80)}</p>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0 }}>{r.reasoning?.slice(0, 100)}</p>
      </div>
    </div>
  )
})

export default function Playground({ projectId, apiKey, apiUrl }: AppContext) {
  const [prompt,   setPrompt]   = useState("You are a helpful customer support agent.")
  const [promptB,  setPromptB]  = useState("")
  const [dataset,  setDataset]  = useState("")
  const [criteria, setCriteria] = useState(CRITERIA_DEFAULT)
  const [mode,     setMode]     = useState<"single" | "ab">("single")
  const [running,  setRunning]  = useState(false)
  const [progress, setProgress] = useState(0)
  const [result,   setResult]   = useState<EvalRun | null>(null)
  const [abResult, setAbResult] = useState<ABResult | null>(null)
  const [error,    setError]    = useState("")

  const abortRef = useRef<AbortController | null>(null)

  const parsedCriteria = useMemo(
    () => criteria.split(",").map(s => s.trim()).filter(Boolean),
    [criteria]
  )

  const runEval = useCallback(async () => {
    if (!dataset.trim()) { setError("ERR: enter a dataset name"); return }
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true); setError(""); setResult(null); setProgress(0)
    try {
      const run = await apiPost<{ run_id: string }>(`${apiUrl}/api/evals/run`, apiKey, {
        project:        projectId,
        dataset_name:   dataset,
        name:           `playground-${Date.now()}`,
        system_prompt:  prompt,
        judge_criteria: parsedCriteria,
      })
      const done = await pollUntilDone<EvalRun>(
        `${apiUrl}/api/evals/${run.run_id}`,
        apiKey, ctrl.signal, setProgress
      )
      if (done.status === "failed") { setError("ERR: eval failed"); return }
      setProgress(100)
      setResult(done)
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message || "ERR: unknown error")
    } finally {
      setRunning(false)
    }
  }, [apiUrl, apiKey, projectId, dataset, prompt, parsedCriteria])

  const runABTest = useCallback(async () => {
    if (!dataset.trim() || !promptB.trim()) { setError("ERR: enter dataset and Prompt B"); return }
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setRunning(true); setError(""); setAbResult(null); setProgress(0)
    try {
      const run = await apiPost<{ test_id: string }>(`${apiUrl}/api/ab/run`, apiKey, {
        dataset_name:   dataset,
        prompt_a:       prompt,
        prompt_b:       promptB,
        judge_criteria: parsedCriteria,
      })
      const done = await pollUntilDone<{ status: string; result: ABResult }>(
        `${apiUrl}/api/ab/${run.test_id}`,
        apiKey, ctrl.signal, setProgress
      )
      if (done.status === "failed") { setError("ERR: A/B test failed"); return }
      setProgress(100)
      setAbResult(done.result)
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message || "ERR: unknown error")
    } finally {
      setRunning(false)
    }
  }, [apiUrl, apiKey, dataset, prompt, promptB, parsedCriteria])

  const cancel = useCallback(() => {
    abortRef.current?.abort()
    setRunning(false)
    setProgress(0)
  }, [])

  return (
    <div style={{ padding: "18px 20px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px" }}>
          Prompt Playground
        </h1>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>
          [PLY] TEST PROMPT CHANGES AGAINST GOLDEN DATASET · NO CODE REQUIRED
        </p>
      </div>

      {/* Mode toggle */}
      <div style={{ display: "flex", gap: "6px", marginBottom: "16px" }}>
        {(["single", "ab"] as const).map(m => (
          <button key={m} onClick={() => setMode(m)} className={`btn ${mode === m ? "btn-p" : "btn-ghost"}`}>
            {m === "single" ? "SINGLE EVAL" : "A/B TEST"}
          </button>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        {/* Config */}
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>

          <div className="panel" style={{ padding: "14px 16px" }}>
            <div className="panel-accent"/>
            <label className="label">{mode === "ab" ? "PROMPT A (CURRENT)" : "SYSTEM PROMPT"}</label>
            <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={6} className="field"/>
          </div>

          {mode === "ab" && (
            <div className="panel" style={{ padding: "14px 16px", borderColor: "var(--pb)" }}>
              <div className="panel-accent"/>
              <label className="label" style={{ color: "var(--p2)" }}>PROMPT B — CHALLENGER</label>
              <textarea value={promptB} onChange={e => setPromptB(e.target.value)}
                placeholder="Enter the new prompt to test…" rows={6} className="field"/>
            </div>
          )}

          <div className="panel" style={{ padding: "14px 16px" }}>
            <div className="panel-accent"/>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <div>
                <label className="label">DATASET NAME</label>
                <input value={dataset} onChange={e => setDataset(e.target.value)} placeholder="e.g. support-golden-v1" className="field"/>
              </div>
              <div>
                <label className="label">JUDGE CRITERIA (COMMA-SEPARATED)</label>
                <input value={criteria} onChange={e => setCriteria(e.target.value)} className="field"/>
              </div>
            </div>
          </div>

          {error && (
            <div style={{ padding: "9px 12px", background: "var(--rg)", border: "1px solid var(--rb)", borderRadius: "var(--r1)", fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--r0)" }}>
              {error}
            </div>
          )}

          {/* Progress */}
          {running && (
            <div style={{ background: "var(--raised)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", overflow: "hidden", height: "4px" }}>
              <div style={{ height: "100%", width: `${progress}%`, background: "linear-gradient(90deg, var(--p3), var(--p0))", transition: "width 0.5s var(--ease)" }}/>
            </div>
          )}

          <div style={{ display: "flex", gap: "6px" }}>
            <button
              onClick={mode === "single" ? runEval : runABTest}
              disabled={running}
              className="btn btn-p"
              style={{ flex: 1, justifyContent: "center", padding: "11px" }}
            >
              {running
                ? <><span className="animate-spin" style={{ display: "inline-block", width: 10, height: 10, border: "1.5px solid var(--void)", borderTop: "1.5px solid transparent", borderRadius: "50%" }}/> RUNNING… ({Math.round(progress)}%)</>
                : mode === "single" ? "▶ RUN EVAL" : "▶ RUN A/B TEST"}
            </button>
            {running && (
              <button onClick={cancel} className="btn btn-ghost" style={{ padding: "11px 14px" }}>
                ✕ CANCEL
              </button>
            )}
          </div>
        </div>

        {/* Results */}
        <div>
          {!result && !abResult && !running && (
            <div className="panel" style={{ height: "100%", minHeight: "300px" }}>
              <div className="panel-accent"/>
              <div className="empty" style={{ height: "100%" }}>
                <span className="empty-glyph">⬡</span>
                <p className="empty-title">AWAITING RUN</p>
                <p className="empty-sub">Configure your prompt and dataset, then execute</p>
              </div>
            </div>
          )}

          {running && !result && !abResult && (
            <div className="panel" style={{ height: "100%", minHeight: "300px" }}>
              <div className="panel-accent"/>
              <div className="empty" style={{ height: "100%" }}>
                <div style={{ position: "relative", width: 48, height: 48 }}>
                  <div className="animate-spin" style={{ position: "absolute", inset: 0, border: "1.5px solid var(--b2)", borderTop: "1.5px solid var(--p0)", borderRadius: "50%" }}/>
                  <div style={{ position: "absolute", inset: 8, border: "1px solid var(--pb)", borderBottom: "1px solid transparent", borderRadius: "50%", animation: "spin 0.6s linear infinite reverse" }}/>
                </div>
                <p className="empty-title">EVALUATING…</p>
                <p className="empty-sub">{Math.round(progress)}% complete</p>
              </div>
            </div>
          )}

          {/* Single result */}
          {result && (
            <div className="panel" style={{ padding: 0 }}>
              <div className="panel-accent"/>
              <div className="panel-header">
                <span className="panel-label">EVAL RESULTS</span>
                <div style={{ display: "flex", gap: "10px" }}>
                  {[
                    { l: "PASS",  v: `${((result.pass_rate || 0) * 100).toFixed(0)}%`, c: scoreColor((result.pass_rate || 0) * 10) },
                    { l: "SCORE", v: `${(result.avg_score  || 0).toFixed(2)}/10`,       c: scoreColor(result.avg_score || 0) },
                  ].map(s => (
                    <div key={s.l} style={{ display: "flex", gap: 5, alignItems: "baseline" }}>
                      <span style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", letterSpacing: "0.1em" }}>{s.l}</span>
                      <span style={{ fontFamily: "var(--f-mono)", fontSize: "13px", fontWeight: 700, color: s.c }}>{s.v}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div style={{ maxHeight: "440px", overflowY: "auto" }}>
                {(result.results || []).map((r: any, i: number) => <ResultRow key={i} r={r}/>)}
              </div>
            </div>
          )}

          {/* A/B result */}
          {abResult && (
            <div className="panel" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              <div className="panel-accent"/>
              <div style={{
                padding: "12px 14px", borderRadius: "var(--r1)",
                background: abResult.is_improvement ? "var(--pg)" : abResult.winner === "a" ? "var(--rg)" : "var(--cg)",
                border: `1px solid ${abResult.is_improvement ? "var(--pb)" : abResult.winner === "a" ? "var(--rb)" : "var(--cb)"}`,
              }}>
                <p style={{ fontFamily: "var(--f-mono)", fontSize: "11px", fontWeight: 700, margin: "0 0 4px", color: abResult.is_improvement ? "var(--p0)" : abResult.winner === "a" ? "var(--r0)" : "var(--c0)" }}>
                  {!abResult.is_significant ? "⚠ NO SIGNIFICANT DIFFERENCE"
                   : abResult.is_improvement ? "✓ PROMPT B IS BETTER — SAFE TO DEPLOY"
                   : "✗ PROMPT B IS WORSE — DO NOT DEPLOY"}
                </p>
                <p style={{ fontFamily: "var(--f-data)", fontSize: "11px", color: "var(--t2)", margin: 0 }}>{abResult.recommendation}</p>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                {(["a","b"] as const).map(v => {
                  const variant  = abResult[`variant_${v}` as "variant_a" | "variant_b"]
                  const isWinner = abResult.winner === v && abResult.is_significant
                  const pr       = variant?.pass_rate || 0
                  return (
                    <div key={v} style={{ background: "var(--raised)", border: `1px solid ${isWinner ? "var(--pb)" : "var(--b1)"}`, borderRadius: "var(--r1)", padding: "10px 12px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                        <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", letterSpacing: "0.14em" }}>PROMPT {v.toUpperCase()}</span>
                        {isWinner && <span className="sig sig-p">★ WINNER</span>}
                      </div>
                      <p style={{ fontFamily: "var(--f-mono)", fontSize: "20px", fontWeight: 700, margin: "0 0 2px", color: scoreColor(pr * 10) }}>{(pr * 100).toFixed(0)}%</p>
                      <p style={{ fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--t2)", margin: 0 }}>{(variant?.avg_score || 0).toFixed(2)}/10 avg</p>
                    </div>
                  )
                })}
              </div>

              <div style={{ display: "flex", gap: "6px" }}>
                {[
                  { l: "P-VALUE",     v: abResult.p_value?.toFixed(3) },
                  { l: "EFFECT SIZE", v: abResult.effect_size_label },
                  { l: "Δ SCORE",     v: `${abResult.score_delta > 0 ? "+" : ""}${abResult.score_delta?.toFixed(2)}` },
                ].map(s => (
                  <Tile key={s.l} label={s.l} value={s.v ?? "—"} color="var(--t1)"/>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}