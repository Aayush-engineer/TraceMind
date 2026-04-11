import { useState } from "react"
import type { AppContext } from "../App"

export default function Hallucination({ apiKey, apiUrl }: AppContext) {
  const [question, setQuestion] = useState("")
  const [response, setResponse] = useState("")
  const [context,  setContext]  = useState("")
  const [result,   setResult]   = useState<any>(null)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState("")

  const headers = {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type":  "application/json"
  }

  async function check() {
    if (!question.trim() || !response.trim()) {
      setError("Question and response are required"); return
    }
    setLoading(true); setError(""); setResult(null)

    try {
      const r = await fetch(`${apiUrl}/api/hallucination/check`, {
        method: "POST", headers,
        body: JSON.stringify({
          question,
          response,
          context:   context || null,
          fast_mode: false,
        })
      })
      if (!r.ok) { setError("Check failed — try again"); return }
      setResult(await r.json())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const riskColor = (r: string) => ({
    low:      "#10b981", medium: "#f59e0b",
    high:     "#f97316", critical: "#ef4444"
  })[r] || "#64748b"

  const riskBg = (r: string) => ({
    low:      "#052e16", medium: "#422006",
    high:     "#431407", critical: "#450a0a"
  })[r] || "#1e293b"

  const typeColor = (t: string) => ({
    none:          "#10b981",
    factual:       "#ef4444",
    fabrication:   "#f97316",
    contradiction: "#a855f7",
    overconfident: "#f59e0b",
  })[t] || "#64748b"

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0" }}>
      <div style={{ marginBottom: "20px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
          Hallucination detector
        </h1>
        <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
          Analyze LLM responses for factual errors, fabrications, and overconfident claims
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
        {/* Input */}
        <div style={{
          background: "#1e293b", border: "1px solid #334155",
          borderRadius: "10px", padding: "16px",
          display: "flex", flexDirection: "column", gap: "12px"
        }}>
          <div>
            <label style={{ fontSize: "11px", color: "#64748b", display: "block",
                            marginBottom: "5px", textTransform: "uppercase" }}>
              Question / Prompt *
            </label>
            <textarea
              value={question}
              onChange={e => setQuestion(e.target.value)}
              placeholder="What question was the AI answering?"
              rows={3}
              style={{
                width: "100%", padding: "8px 10px", borderRadius: "6px",
                border: "1px solid #334155", background: "#0f172a",
                color: "#e2e8f0", fontSize: "13px",
                resize: "vertical", boxSizing: "border-box"
              }}
            />
          </div>

          <div>
            <label style={{ fontSize: "11px", color: "#64748b", display: "block",
                            marginBottom: "5px", textTransform: "uppercase" }}>
              AI Response *
            </label>
            <textarea
              value={response}
              onChange={e => setResponse(e.target.value)}
              placeholder="Paste the AI response to analyze..."
              rows={5}
              style={{
                width: "100%", padding: "8px 10px", borderRadius: "6px",
                border: "1px solid #334155", background: "#0f172a",
                color: "#e2e8f0", fontSize: "13px",
                resize: "vertical", boxSizing: "border-box"
              }}
            />
          </div>

          <div>
            <label style={{ fontSize: "11px", color: "#64748b", display: "block",
                            marginBottom: "5px", textTransform: "uppercase" }}>
              Ground truth context (optional but recommended)
            </label>
            <textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="Paste the source documents, database results, or known facts. Without this, only self-consistency is checked."
              rows={4}
              style={{
                width: "100%", padding: "8px 10px", borderRadius: "6px",
                border: "1px solid #475569", background: "#0f172a",
                color: "#e2e8f0", fontSize: "13px",
                resize: "vertical", boxSizing: "border-box"
              }}
            />
          </div>

          {error && (
            <div style={{
              background: "#450a0a", borderRadius: "6px",
              padding: "8px 12px", color: "#f87171", fontSize: "12px"
            }}>
              {error}
            </div>
          )}

          <button onClick={check} disabled={loading} style={{
            padding: "10px", background: loading ? "#334155" : "#6366f1",
            color: "white", border: "none", borderRadius: "7px",
            fontSize: "13px", fontWeight: 600, cursor: loading ? "default" : "pointer"
          }}>
            {loading ? "Analyzing..." : "🔍 Check for hallucinations"}
          </button>
        </div>

        {/* Results */}
        <div>
          {!result && !loading && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center",
              color: "#475569"
            }}>
              <div style={{ fontSize: "40px", marginBottom: "12px" }}>🧠</div>
              <p style={{ margin: 0 }}>Analysis results will appear here</p>
            </div>
          )}

          {loading && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center"
            }}>
              <div style={{
                width: "36px", height: "36px", margin: "0 auto 16px",
                border: "3px solid #334155", borderTop: "3px solid #6366f1",
                borderRadius: "50%", animation: "spin 1s linear infinite"
              }}/>
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
              <p style={{ color: "#94a3b8", margin: 0, fontSize: "13px" }}>
                Extracting and verifying claims...
              </p>
            </div>
          )}

          {result && (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", overflow: "hidden"
            }}>
              {/* Risk banner */}
              <div style={{
                padding: "14px 16px",
                background: riskBg(result.overall_risk),
                borderBottom: "1px solid #334155"
              }}>
                <div style={{ display: "flex", alignItems: "center",
                              justifyContent: "space-between" }}>
                  <div>
                    <span style={{
                      fontSize: "13px", fontWeight: 700,
                      color: riskColor(result.overall_risk),
                      textTransform: "uppercase"
                    }}>
                      {result.overall_risk} risk
                    </span>
                    <span style={{ fontSize: "12px", color: "#94a3b8", marginLeft: "8px" }}>
                      Score: {result.hallucination_score?.toFixed(1)}/10
                    </span>
                  </div>
                  <span style={{ fontSize: "12px", color: "#475569" }}>
                    {result.total_claims} claims analyzed
                    {" · "}
                    {result.analysis_time_ms?.toFixed(0)}ms
                  </span>
                </div>
                <p style={{ fontSize: "12px", color: "#94a3b8",
                            margin: "6px 0 0", lineHeight: 1.5 }}>
                  {result.summary}
                </p>
              </div>

              {/* Claims list */}
              <div style={{ maxHeight: "450px", overflowY: "auto" }}>
                {result.claims?.length === 0 ? (
                  <div style={{ padding: "2rem", textAlign: "center", color: "#475569" }}>
                    No specific claims extracted
                  </div>
                ) : result.claims?.map((claim: any, i: number) => (
                  <div key={i} style={{
                    padding: "12px 16px",
                    borderBottom: "1px solid #1e3a5f",
                    borderLeft: `3px solid ${typeColor(claim.type)}`
                  }}>
                    <div style={{ display: "flex", alignItems: "center",
                                  gap: "8px", marginBottom: "5px" }}>
                      <span style={{
                        padding: "2px 7px", borderRadius: "99px",
                        fontSize: "10px", fontWeight: 600,
                        color: typeColor(claim.type),
                        background: "#0f172a",
                        border: `1px solid ${typeColor(claim.type)}33`
                      }}>
                        {claim.type}
                      </span>
                      {claim.risk_level !== "low" && (
                        <span style={{
                          padding: "2px 7px", borderRadius: "99px",
                          fontSize: "10px",
                          color: riskColor(claim.risk_level),
                          background: riskBg(claim.risk_level)
                        }}>
                          {claim.risk_level} risk
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: "13px", color: "#e2e8f0",
                                margin: "0 0 5px", lineHeight: 1.4 }}>
                      "{claim.text}"
                    </p>
                    {claim.evidence && (
                      <p style={{ fontSize: "11px", color: "#64748b",
                                  margin: 0, fontStyle: "italic" }}>
                        {claim.evidence}
                      </p>
                    )}
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