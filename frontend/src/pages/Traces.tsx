import { useEffect, useState, useCallback } from "react"
import type { AppContext } from "../App";

interface Span {
  id:          string
  trace_id:    string
  name:        string
  score:       number | null
  status:      string
  duration_ms: number
  timestamp:   number
  input:       string
  output:      string
  has_error:   boolean
}

export default function Traces({ projectId, apiKey, apiUrl }: AppContext) {
  const [spans,   setSpans]   = useState<Span[]>([])
  const [loading, setLoading] = useState(true)
  const [filter,  setFilter]  = useState<"all" | "failed" | "errors">("all")
  const [selected, setSelected] = useState<Span | null>(null)
  const [search, setSearch] = useState("")
  const [minScore, setMinScore] = useState(0)


  const headers = { "Authorization": `Bearer ${apiKey}` }

  
  const filteredSpans = spans.filter(span => {
    const matchesSearch = search === "" ||
        span.input.toLowerCase().includes(search.toLowerCase()) ||
        span.name.toLowerCase().includes(search.toLowerCase())
    const matchesScore = minScore === 0 ||
        (span.score !== null && span.score <= minScore)
    return matchesSearch && matchesScore
  })

  const fetchSpans = useCallback(async () => {
    try {
      const url = filter === "failed"
        ? `${apiUrl}/api/traces/project/${projectId}?limit=50&min_score=7`
        : `${apiUrl}/api/traces/project/${projectId}?limit=50`
      const res  = await fetch(url, { headers })
      const data = await res.json()
      setSpans(data.spans || [])
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId, apiKey, filter])

  useEffect(() => { fetchSpans() }, [fetchSpans])

  const scoreColor = (s: number | null) =>
    s === null ? "#475569" : s >= 8 ? "#10b981" : s >= 6 ? "#f59e0b" : "#ef4444"

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0" }}>
      {/* Header */}
      <div style={{ marginBottom: "20px" }}>
        <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
          Traces
        </h1>
        <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
          Every LLM call captured by the SDK — click a row to inspect
        </p>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        {(["all", "failed", "errors"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "6px 14px", borderRadius: "6px", fontSize: "12px",
            fontWeight: 500, cursor: "pointer", border: "1px solid",
            borderColor: filter === f ? "#6366f1" : "#334155",
            background:  filter === f ? "#6366f1" : "transparent",
            color:       filter === f ? "white"   : "#64748b"
          }}>
            {f === "all" ? "All traces" : f === "failed" ? "Low score" : "Errors"}
          </button>
        ))}
        <button onClick={fetchSpans} style={{
          marginLeft: "auto", padding: "6px 14px", borderRadius: "6px",
          fontSize: "12px", border: "1px solid #334155",
          background: "transparent", color: "#64748b", cursor: "pointer"
        }}>
          ↻ Refresh
        </button>
      </div>

      <div style={{
        display: "flex", gap: "10px", marginBottom: "16px", marginTop: "8px"
        }}>
        <div style={{ flex: 1, position: "relative" }}>
            <span style={{
            position: "absolute", left: "10px", top: "50%",
            transform: "translateY(-50%)", color: "#475569", fontSize: "14px"
            }}>🔍</span>
            <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by input text or span name..."
            style={{
                width: "100%", padding: "8px 12px 8px 32px",
                borderRadius: "7px", border: "1px solid #334155",
                background: "#1e293b", color: "#e2e8f0",
                fontSize: "13px", boxSizing: "border-box"
            }}
            />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "12px", color: "#475569", whiteSpace: "nowrap" }}>
            Score below
            </span>
            <select
            value={minScore}
            onChange={e => setMinScore(Number(e.target.value))}
            style={{
                padding: "7px 10px", borderRadius: "6px",
                border: "1px solid #334155", background: "#1e293b",
                color: "#e2e8f0", fontSize: "12px"
            }}
            >
            <option value={0}>Any</option>
            <option value={5}>5 — poor</option>
            <option value={6}>6 — acceptable</option>
            <option value={7}>7 — threshold</option>
            <option value={8}>8 — good</option>
            </select>
        </div>
        {(search || minScore > 0) && (
            <button
            onClick={() => { setSearch(""); setMinScore(0) }}
            style={{
                padding: "7px 12px", borderRadius: "6px",
                border: "1px solid #334155", background: "transparent",
                color: "#64748b", fontSize: "12px", cursor: "pointer"
            }}
            >
            Clear
            </button>
        )}
        </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 400px" : "1fr", gap: "16px" }}>

        {/* Table */}
        <div style={{
          background: "#1e293b", border: "1px solid #334155",
          borderRadius: "10px", overflow: "hidden"
        }}>
          {loading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#475569" }}>
              Loading traces...
            </div>
          ) : spans.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "#475569" }}>
              <p style={{ fontSize: "32px", margin: "0 0 8px" }}>⚡</p>
              <p style={{ margin: 0 }}>No traces yet — instrument your app with the SDK</p>
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155" }}>
                  {["Span name", "Score", "Duration", "Status", "Time"].map(h => (
                    <th key={h} style={{
                      textAlign: "left", padding: "10px 16px",
                      fontSize: "11px", color: "#475569",
                      fontWeight: 600, textTransform: "uppercase",
                      letterSpacing: "0.06em"
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredSpans.map(span => (
                  <tr
                    key={span.id}
                    onClick={() => setSelected(selected?.id === span.id ? null : span)}
                    style={{
                      borderBottom: "1px solid #1e3a5f",
                      cursor: "pointer",
                      background: selected?.id === span.id ? "#1e3a5f" : "transparent"
                    }}
                    onMouseEnter={e => {
                      if (selected?.id !== span.id)
                        (e.currentTarget as HTMLElement).style.background = "#334155"
                    }}
                    onMouseLeave={e => {
                      if (selected?.id !== span.id)
                        (e.currentTarget as HTMLElement).style.background = "transparent"
                    }}
                  >
                    <td style={{ padding: "10px 16px", color: "#e2e8f0", fontWeight: 500 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        {span.has_error && (
                          <span style={{ color: "#ef4444", fontSize: "10px" }}>⚠</span>
                        )}
                        {span.name}
                      </div>
                      <div style={{ fontSize: "11px", color: "#475569", marginTop: "2px" }}>
                        {span.input.slice(0, 50)}{span.input.length > 50 ? "..." : ""}
                      </div>
                    </td>
                    <td style={{ padding: "10px 16px" }}>
                        {span.score !== null ? (
                            <span style={{
                            padding: "3px 8px",
                            borderRadius: "99px",
                            fontSize: "11px",
                            fontWeight: 700,
                            background:
                                span.score >= 8 ? "#052e16" :
                                span.score >= 6 ? "#422006" : "#450a0a",
                            color:
                                span.score >= 8 ? "#4ade80" :
                                span.score >= 6 ? "#fbbf24" : "#f87171"
                            }}>
                            {Number(span.score).toFixed(1)}
                            </span>
                        ) : (
                            <span style={{
                            padding: "3px 8px", borderRadius: "99px",
                            fontSize: "11px", background: "#1e293b", color: "#475569"
                            }}>
                            scoring...
                            </span>
                        )}
                    </td>
                    <td style={{ padding: "10px 16px", color: "#94a3b8" }}>
                      {span.duration_ms.toFixed(0)}ms
                    </td>
                    <td style={{ padding: "10px 16px" }}>
                      <span style={{
                        padding: "2px 8px", borderRadius: "99px", fontSize: "11px",
                        background: span.status === "success" ? "#052e16" : "#450a0a",
                        color:      span.status === "success" ? "#4ade80" : "#f87171"
                      }}>
                        {span.status}
                      </span>
                    </td>
                    <td style={{ padding: "10px 16px", color: "#475569", fontSize: "11px" }}>
                      {new Date(span.timestamp * 1000).toLocaleTimeString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", padding: "16px",
            height: "fit-content", position: "sticky", top: "20px"
          }}>
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: "16px"
            }}>
              <h3 style={{ fontSize: "14px", fontWeight: 600,
                           color: "#f1f5f9", margin: 0 }}>
                {selected.name}
              </h3>
              <button onClick={() => setSelected(null)} style={{
                background: "transparent", border: "none",
                color: "#475569", cursor: "pointer", fontSize: "16px"
              }}>✕</button>
            </div>

            {/* Score */}
            <div style={{
              background: "#0f172a", borderRadius: "8px",
              padding: "12px", marginBottom: "12px",
              display: "flex", alignItems: "center", justifyContent: "space-between"
            }}>
              <span style={{ fontSize: "12px", color: "#64748b" }}>Quality score</span>
              <span style={{
                fontSize: "20px", fontWeight: 700,
                color: scoreColor(selected.score)
              }}>
                {selected.score !== null ? Number(selected.score).toFixed(1) : "—"}
                <span style={{ fontSize: "12px", color: "#475569" }}>/10</span>
              </span>
            </div>

            {/* Input */}
            <div style={{ marginBottom: "12px" }}>
              <p style={{ fontSize: "11px", color: "#475569", margin: "0 0 6px",
                          textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Input
              </p>
              <div style={{
                background: "#0f172a", borderRadius: "6px",
                padding: "10px", fontSize: "12px", color: "#94a3b8",
                lineHeight: 1.6, maxHeight: "120px", overflowY: "auto"
              }}>
                {selected.input || "—"}
              </div>
            </div>

            {/* Output */}
            <div style={{ marginBottom: "12px" }}>
              <p style={{ fontSize: "11px", color: "#475569", margin: "0 0 6px",
                          textTransform: "uppercase", letterSpacing: "0.06em" }}>
                Output
              </p>
              <div style={{
                background: "#0f172a", borderRadius: "6px",
                padding: "10px", fontSize: "12px", color: "#94a3b8",
                lineHeight: 1.6, maxHeight: "120px", overflowY: "auto"
              }}>
                {selected.output || "—"}
              </div>
            </div>

            {/* Meta */}
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: "8px"
            }}>
              {[
                { label: "Duration",   value: `${selected.duration_ms.toFixed(0)}ms` },
                { label: "Status",     value: selected.status },
                { label: "Trace ID",   value: selected.trace_id.slice(0, 12) + "..." },
                { label: "Time",       value: new Date(selected.timestamp * 1000).toLocaleTimeString() },
              ].map(m => (
                <div key={m.label} style={{
                  background: "#0f172a", borderRadius: "6px", padding: "8px 10px"
                }}>
                  <p style={{ fontSize: "10px", color: "#475569", margin: "0 0 2px",
                              textTransform: "uppercase" }}>{m.label}</p>
                  <p style={{ fontSize: "12px", color: "#94a3b8", margin: 0 }}>{m.value}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}