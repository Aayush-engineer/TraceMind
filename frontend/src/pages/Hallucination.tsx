// pages/Hallucination.tsx
import { useState, useCallback, useRef, memo } from "react"
import type { AppContext } from "../App"
import type { HallucinationResult, HallucinationClaim } from "../lib/types"
import { riskColor, riskBg, riskBorder, typeColor } from "../lib/types"

const ClaimRow = memo(function ClaimRow({ claim }: { claim: HallucinationClaim }) {
  const tc = typeColor(claim.type)
  return (
    <div style={{ padding: "11px 14px", borderBottom: "1px solid rgba(120,180,255,0.04)", borderLeft: `2px solid ${tc}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 5 }}>
        <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", fontWeight: 700, padding: "2px 7px", borderRadius: "var(--r0)", color: tc, background: `${tc}14`, border: `1px solid ${tc}30`, letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
          {claim.type}
        </span>
        {claim.risk_level !== "low" && (
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", fontWeight: 700, padding: "2px 7px", borderRadius: "var(--r0)", color: riskColor(claim.risk_level), background: riskBg(claim.risk_level), border: `1px solid ${riskBorder(claim.risk_level)}`, letterSpacing: "0.1em", textTransform: "uppercase" as const }}>
            {claim.risk_level}
          </span>
        )}
      </div>
      <p style={{ fontFamily: "var(--f-data)", fontSize: "12px", color: "var(--t0)", margin: "0 0 4px", lineHeight: 1.5 }}>
        "{claim.text}"
      </p>
      {claim.evidence && (
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0, borderTop: "1px solid var(--b1)", paddingTop: 5, marginTop: 5 }}>
          {claim.evidence}
        </p>
      )}
    </div>
  )
})

export default function Hallucination({ apiKey, apiUrl }: AppContext) {
  const [question, setQuestion] = useState("")
  const [response, setResponse] = useState("")
  const [context,  setContext]  = useState("")
  const [result,   setResult]   = useState<HallucinationResult | null>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState("")
  const abortRef = useRef<AbortController | null>(null)

  const check = useCallback(async () => {
    if (!question.trim() || !response.trim()) { setError("ERR: question and response required"); return }
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setLoading(true); setError(""); setResult(null)
    try {
      const res = await fetch(`${apiUrl}/api/hallucination/check`, {
        method: "POST", signal: ctrl.signal,
        headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ question, response, context: context || null, fast_mode: false }),
      })
      if (!res.ok) { setError(`ERR: ${res.status} — check failed`); return }
      setResult(await res.json())
    } catch (e: any) {
      if (e.name !== "AbortError") setError(e.message || "ERR: unknown error")
    } finally { setLoading(false) }
  }, [question, response, context, apiUrl, apiKey])

  const clear = useCallback(() => {
    abortRef.current?.abort()
    setResult(null); setError(""); setLoading(false)
    setQuestion(""); setResponse(""); setContext("")
  }, [])

  return (
    <div style={{ padding: "18px 20px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px" }}>Hallucination Detector</h1>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>[HAL] ANALYZE LLM RESPONSES FOR FACTUAL ERRORS, FABRICATIONS, OVERCONFIDENT CLAIMS</p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
        <div className="panel" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "12px" }}>
          <div className="panel-accent"/>
          <div><label className="label">QUESTION / PROMPT *</label><textarea value={question} onChange={e => setQuestion(e.target.value)} placeholder="What question was the AI answering?" rows={3} className="field"/></div>
          <div><label className="label">AI RESPONSE *</label><textarea value={response} onChange={e => setResponse(e.target.value)} placeholder="Paste the AI response to analyze…" rows={5} className="field"/></div>
          <div>
            <label className="label" style={{ color: "var(--p3)" }}>GROUND TRUTH CONTEXT <span style={{ color: "var(--t4)", fontWeight: 400, textTransform: "none" as const, letterSpacing: 0, marginLeft: 6 }}>optional — recommended</span></label>
            <textarea value={context} onChange={e => setContext(e.target.value)} placeholder="Paste source documents or known facts." rows={4} className="field" style={{ borderColor: "var(--pb)" }}/>
          </div>
          {error && <div style={{ padding: "9px 12px", background: "var(--rg)", border: "1px solid var(--rb)", borderRadius: "var(--r1)", fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--r0)" }}>{error}</div>}
          <div style={{ display: "flex", gap: "6px" }}>
            <button onClick={check} disabled={loading} className="btn btn-p" style={{ flex: 1, justifyContent: "center", padding: "11px" }}>
              {loading ? <><span className="animate-spin" style={{ display: "inline-block", width: 10, height: 10, border: "1.5px solid var(--void)", borderTop: "1.5px solid transparent", borderRadius: "50%" }}/> ANALYZING…</> : "⊛ CHECK FOR HALLUCINATIONS"}
            </button>
            {(result || error) && <button onClick={clear} className="btn btn-ghost" style={{ padding: "11px 14px" }}>CLEAR</button>}
          </div>
        </div>
        <div>
          {!result && !loading && (
            <div className="panel" style={{ height: "100%", minHeight: "300px" }}>
              <div className="panel-accent"/>
              <div className="empty" style={{ height: "100%" }}>
                <span className="empty-glyph">⊛</span>
                <p className="empty-title">ANALYSIS READY</p>
                <p className="empty-sub">Paste a question and AI response, then run the check</p>
              </div>
            </div>
          )}
          {loading && (
            <div className="panel" style={{ height: "100%", minHeight: "300px" }}>
              <div className="panel-accent"/>
              <div className="empty" style={{ height: "100%" }}>
                <div style={{ position: "relative", width: 48, height: 48 }}>
                  <div className="animate-spin" style={{ position: "absolute", inset: 0, border: "1.5px solid var(--b2)", borderTop: "1.5px solid var(--p0)", borderRadius: "50%" }}/>
                  <div style={{ position: "absolute", inset: 10, border: "1px solid var(--pb)", borderBottom: "1px solid transparent", borderRadius: "50%", animation: "spin 0.5s linear infinite reverse" }}/>
                </div>
                <p className="empty-title">EXTRACTING CLAIMS…</p>
                <p className="empty-sub">Verifying each claim against context</p>
              </div>
            </div>
          )}
          {result && (
            <div className="panel" style={{ padding: 0 }}>
              <div className="panel-accent"/>
              <div style={{ padding: "14px 16px", background: riskBg(result.overall_risk), borderBottom: "1px solid var(--b1)" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ fontFamily: "var(--f-mono)", fontSize: "13px", fontWeight: 700, color: riskColor(result.overall_risk), letterSpacing: "0.06em", textTransform: "uppercase" as const }}>{result.overall_risk} risk</span>
                    <div style={{ padding: "2px 8px", background: "var(--base)", border: `1px solid ${riskBorder(result.overall_risk)}`, borderRadius: "var(--r0)", fontFamily: "var(--f-mono)", fontSize: "10px", color: riskColor(result.overall_risk) }}>{result.hallucination_score?.toFixed(1)}/10</div>
                  </div>
                  <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)" }}>{result.total_claims} claims · {result.analysis_time_ms?.toFixed(0)}ms</span>
                </div>
                <p style={{ fontFamily: "var(--f-data)", fontSize: "11px", color: "var(--t2)", margin: 0, lineHeight: 1.6 }}>{result.summary}</p>
              </div>
              <div style={{ maxHeight: "420px", overflowY: "auto" }}>
                {!result.claims?.length
                  ? <div className="empty" style={{ padding: "2rem" }}><p className="empty-title">NO CLAIMS EXTRACTED</p></div>
                  : result.claims.map((claim, i) => <ClaimRow key={i} claim={claim}/>)
                }
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}