import { useEffect, useState, useRef } from "react"
import type { AppContext } from "../App"

interface LiveSpan {
  span_id:    string
  name:       string
  input:      string
  output:     string
  score:      number | null
  status:     string
  duration_ms: number
  timestamp:  number
  has_error:  boolean
}

export default function Live({ projectId, apiKey, apiUrl }: AppContext) {
  const [spans,     setSpans]     = useState<LiveSpan[]>([])
  const [connected, setConnected] = useState(false)
  const [paused,    setPaused]    = useState(false)
  const [total,     setTotal]     = useState(0)
  const pausedRef = useRef(false)
  const wsRef     = useRef<WebSocket | null>(null)

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(`ws://localhost:8000/ws/${projectId}`)
      wsRef.current = ws

      ws.onopen  = () => setConnected(true)
      ws.onclose = () => { setConnected(false); setTimeout(connect, 3000) }
      ws.onerror = () => setConnected(false)

      ws.onmessage = (e) => {
        if (pausedRef.current) return
        try {
          const data = JSON.parse(e.data)
          if (data.type === "new_span") {
            setSpans(prev => [data.span, ...prev].slice(0, 100))
            setTotal(t => t + 1)
          }
        } catch { /* ignore */ }
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [projectId])

  // Also poll for recent spans every 5s as fallback
  useEffect(() => {
    async function poll() {
      if (pausedRef.current) return
      try {
        const r = await fetch(
          `${apiUrl}/api/traces/project/${projectId}?limit=20`,
          { headers: { "Authorization": `Bearer ${apiKey}` } }
        )
        const d = await r.json()
        if (d.spans?.length > 0) {
          setSpans(prev => {
            const existingIds = new Set(prev.map(s => s.span_id))
            const newSpans    = d.spans.filter((s: LiveSpan) => !existingIds.has(s.span_id))
            if (newSpans.length === 0) return prev
            return [...newSpans, ...prev].slice(0, 100)
          })
        }
      } catch { /* ignore */ }
    }
    poll()
    const interval = setInterval(poll, 5000)
    return () => clearInterval(interval)
  }, [projectId, apiKey])

  function togglePause() {
    pausedRef.current = !pausedRef.current
    setPaused(pausedRef.current)
  }

  const scoreColor = (s: number | null) =>
    s === null ? "#475569" : s >= 8 ? "#10b981" : s >= 6 ? "#f59e0b" : "#ef4444"

  const scoreBg = (s: number | null) =>
    s === null ? "#1e293b" : s >= 8 ? "#052e16" : s >= 6 ? "#422006" : "#450a0a"

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0", height: "100%" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start",
                    justifyContent: "space-between", marginBottom: "20px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
            <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: 0 }}>
              Live traces
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <div style={{
                width: "8px", height: "8px", borderRadius: "50%",
                background: connected ? "#10b981" : "#ef4444",
                boxShadow: connected ? "0 0 0 2px #05150d" : "none",
                animation: connected ? "pulse 2s infinite" : "none"
              }}/>
              <span style={{ fontSize: "12px",
                             color: connected ? "#10b981" : "#ef4444" }}>
                {connected ? "Live" : "Reconnecting..."}
              </span>
            </div>
          </div>
          <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
            Watch LLM calls as they happen — {total} captured this session
          </p>
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <button onClick={togglePause} style={{
            padding: "8px 16px", borderRadius: "7px",
            border: "1px solid #334155",
            background: paused ? "#6366f1" : "transparent",
            color: paused ? "white" : "#64748b",
            fontSize: "12px", fontWeight: 600, cursor: "pointer"
          }}>
            {paused ? "▶ Resume" : "⏸ Pause"}
          </button>
          <button onClick={() => setSpans([])} style={{
            padding: "8px 16px", borderRadius: "7px",
            border: "1px solid #334155", background: "transparent",
            color: "#64748b", fontSize: "12px", cursor: "pointer"
          }}>
            Clear
          </button>
        </div>
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }`}</style>

      {/* Stats bar */}
      {spans.length > 0 && (
        <div style={{
          display: "flex", gap: "16px", marginBottom: "16px",
          background: "#1e293b", border: "1px solid #334155",
          borderRadius: "8px", padding: "10px 16px"
        }}>
          {[
            { label: "Total",  value: spans.length.toString() },
            { label: "Errors", value: spans.filter(s => s.has_error).length.toString(),
              color: "#ef4444" },
            { label: "Avg score",
              value: (() => {
                const scored = spans.filter(s => s.score !== null)
                if (!scored.length) return "—"
                return (scored.reduce((a,s) => a + (s.score||0), 0) / scored.length).toFixed(1)
              })(),
              color: "#10b981"
            },
            { label: "Pass rate",
              value: (() => {
                const scored = spans.filter(s => s.score !== null)
                if (!scored.length) return "—"
                const passed = scored.filter(s => (s.score||0) >= 7).length
                return `${(passed/scored.length*100).toFixed(0)}%`
              })()
            },
          ].map(stat => (
            <div key={stat.label}>
              <span style={{ fontSize: "11px", color: "#64748b" }}>{stat.label}: </span>
              <span style={{ fontSize: "13px", fontWeight: 600,
                             color: stat.color || "#e2e8f0" }}>
                {stat.value}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Live feed */}
      {spans.length === 0 ? (
        <div style={{
          background: "#1e293b", border: "1px solid #334155",
          borderRadius: "10px", padding: "4rem", textAlign: "center"
        }}>
          <div style={{ fontSize: "40px", marginBottom: "12px" }}>⚡</div>
          <p style={{ color: "#f1f5f9", fontWeight: 500, margin: "0 0 6px" }}>
            Waiting for traces...
          </p>
          <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
            Instrument your app with the SDK and calls will appear here in real time
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {spans.map((span, i) => (
            <div key={span.span_id} style={{
              background: "#1e293b",
              border: `1px solid ${span.has_error ? "#7f1d1d" : "#334155"}`,
              borderLeft: `3px solid ${
                span.has_error ? "#ef4444" :
                scoreColor(span.score)
              }`,
              borderRadius: "8px", padding: "10px 14px",
              animation: i === 0 ? "fadeIn 0.3s ease" : "none",
              display: "flex", alignItems: "center", gap: "12px"
            }}>
              <style>{`@keyframes fadeIn { from{opacity:0;transform:translateY(-4px)} to{opacity:1;transform:none} }`}</style>

              {/* Score badge */}
              <div style={{
                width: "40px", height: "40px", borderRadius: "8px",
                background: scoreBg(span.score),
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0
              }}>
                <span style={{
                  fontSize: "13px", fontWeight: 700,
                  color: scoreColor(span.score)
                }}>
                  {span.score !== null ? Number(span.score).toFixed(1) : "—"}
                </span>
              </div>

              {/* Content */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center",
                              gap: "8px", marginBottom: "2px" }}>
                  <span style={{ fontSize: "13px", fontWeight: 500,
                                 color: "#e2e8f0" }}>
                    {span.name}
                  </span>
                  <span style={{
                    padding: "1px 6px", borderRadius: "99px", fontSize: "10px",
                    background: span.status === "success" ? "#052e16" : "#450a0a",
                    color:      span.status === "success" ? "#4ade80" : "#f87171"
                  }}>
                    {span.status}
                  </span>
                  <span style={{ fontSize: "11px", color: "#475569",
                                 marginLeft: "auto" }}>
                    {new Date(span.timestamp * 1000).toLocaleTimeString()}
                    {" · "}
                    {span.duration_ms.toFixed(0)}ms
                  </span>
                </div>
                <div style={{ fontSize: "12px", color: "#64748b",
                              overflow: "hidden", textOverflow: "ellipsis",
                              whiteSpace: "nowrap" }}>
                  <span style={{ color: "#475569" }}>IN: </span>
                  {span.input.slice(0, 80)}
                  {span.output && (
                    <>
                      <span style={{ color: "#475569", marginLeft: "12px" }}>OUT: </span>
                      {span.output.slice(0, 80)}
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}