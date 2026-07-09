// pages/Live.tsx
import { useEffect, useState, useRef, useCallback, useMemo, memo } from "react"
import type { AppContext } from "../App"
import type { Span } from "../lib/types"
import { scoreColor } from "../lib/types"

// Memoized span row — only re-renders if the span itself changes
const SpanRow = memo(function SpanRow({ span, isNew }: { span: Span; isNew: boolean }) {
  const color = span.has_error ? "var(--r0)" : scoreColor(span.score)
  return (
    <div style={{
      background: "var(--surface)",
      border: `1px solid ${span.has_error ? "var(--rb)" : "var(--b1)"}`,
      borderLeft: `2px solid ${color}`,
      borderRadius: "var(--r1)",
      padding: "9px 14px",
      display: "flex", alignItems: "center", gap: "12px",
      animation: isNew ? "fadeUp 0.22s var(--ease) forwards" : "none",
    }}>
      {/* Score box */}
      <div style={{
        width: "38px", height: "38px", flexShrink: 0,
        border: `1px solid ${color}40`,
        borderRadius: "var(--r1)",
        background: `${color}0d`,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <span style={{ fontFamily: "var(--f-mono)", fontSize: "12px", fontWeight: 700, color }}>
          {span.score !== null ? (+span.score).toFixed(1) : "—"}
        </span>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "7px", marginBottom: "2px" }}>
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "11px", fontWeight: 700, color: "var(--t0)" }}>
            {span.name}
          </span>
          <span className={`sig ${span.status === "success" ? "sig-p" : "sig-r"}`}>
            {span.status?.toUpperCase()}
          </span>
          {span.has_error && <span className="sig sig-r">ERR</span>}
          <span style={{ marginLeft: "auto", fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", letterSpacing: "0.06em" }}>
            {new Date(span.timestamp * 1000).toLocaleTimeString("en-US", { hour12: false })} · {span.duration_ms.toFixed(0)}ms
          </span>
        </div>
        <div style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          <span style={{ color: "var(--t2)" }}>in: </span>{span.input.slice(0, 70)}
          {span.output && <><span style={{ color: "var(--t2)", marginLeft: 10 }}>out: </span>{span.output.slice(0, 70)}</>}
        </div>
      </div>
    </div>
  )
})

export default function Live({ projectId, apiKey, apiUrl }: AppContext) {
  const [spans,     setSpans]     = useState<Span[]>([])
  const [connected, setConnected] = useState(false)
  const [paused,    setPaused]    = useState(false)
  const [total,     setTotal]     = useState(0)
  const [newestId,  setNewestId]  = useState<string | null>(null)

  // Refs so closures always see current values without causing re-runs
  const pausedRef  = useRef(false)
  const mountedRef = useRef(true)
  const wsRef      = useRef<WebSocket | null>(null)
  const seenIds    = useRef(new Set<string>())

  const addSpan = useCallback((span: Span) => {
    if (pausedRef.current) return
    const id = span.span_id || span.id
    if (seenIds.current.has(id)) return
    seenIds.current.add(id)
    setSpans(prev => [span, ...prev].slice(0, 100))
    setTotal(t => t + 1)
    setNewestId(id)
  }, [])

  // WebSocket
  useEffect(() => {
    mountedRef.current = true
    let reconnectTimer: ReturnType<typeof setTimeout>

    function connect() {
      if (!mountedRef.current) return
      const ws = new WebSocket(`ws://localhost:8000/ws/${projectId}`)
      wsRef.current = ws

      ws.onopen  = () => { if (mountedRef.current) setConnected(true) }
      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        reconnectTimer = setTimeout(connect, 3000)
      }
      ws.onerror = () => { if (mountedRef.current) setConnected(false) }
      ws.onmessage = (e) => {
        if (!mountedRef.current) return
        try {
          const data = JSON.parse(e.data)
          if (data.type === "new_span") addSpan(data.span)
        } catch {/**/ }
      }
    }

    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [projectId, addSpan])

  // Polling fallback (fills gaps when WS misses events)
  useEffect(() => {
    let active = true

    async function poll() {
      if (!active || pausedRef.current) return
      try {
        const res = await fetch(
          `${apiUrl}/api/traces/project/${projectId}?limit=20`,
          { headers: { "Authorization": `Bearer ${apiKey}` } }
        )
        const d = await res.json()
        if (!active) return
        ;(d.spans || []).forEach((s: Span) => addSpan(s))
      } catch {/**/ }
    }

    poll()
    const iv = setInterval(poll, 5000)
    return () => { active = false; clearInterval(iv) }
  }, [projectId, apiKey, apiUrl, addSpan])

  const togglePause = useCallback(() => {
    pausedRef.current = !pausedRef.current
    setPaused(pausedRef.current)
  }, [])

  const clearFeed = useCallback(() => {
    setSpans([])
    seenIds.current.clear()
    setTotal(0)
  }, [])

  // Derived stats — memoized
  const stats = useMemo(() => {
    const scored  = spans.filter(s => s.score !== null)
    const errored = spans.filter(s => s.has_error).length
    const avg     = scored.length ? scored.reduce((a, s) => a + (s.score || 0), 0) / scored.length : null
    const pass    = scored.length ? scored.filter(s => (s.score || 0) >= 7).length / scored.length : null
    return { errored, avg, pass, scored: scored.length }
  }, [spans])

  return (
    <div style={{ padding: "18px 20px" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "16px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "3px" }}>
            <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: 0 }}>
              Live Feed
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              {connected
                ? <span className="live-dot"/>
                : <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%", background: "var(--r0)" }}/>
              }
              <span style={{ fontFamily: "var(--f-mono)", fontSize: "9px", letterSpacing: "0.1em", color: connected ? "var(--p2)" : "var(--r0)" }}>
                {connected ? "CONNECTED" : "RECONNECTING…"}
              </span>
            </div>
          </div>
          <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>
            [LIV] {total} CAPTURED THIS SESSION
          </p>
        </div>
        <div style={{ display: "flex", gap: "6px" }}>
          <button onClick={togglePause} className={`btn ${paused ? "btn-p" : "btn-ghost"}`}>
            {paused ? "▶ RESUME" : "⏸ PAUSE"}
          </button>
          <button onClick={clearFeed} className="btn btn-ghost">CLEAR</button>
        </div>
      </div>

      {/* Stats bar */}
      {spans.length > 0 && (
        <div className="panel" style={{ padding: "10px 16px", marginBottom: "12px", display: "flex", gap: 0 }}>
          <div className="panel-accent"/>
          {[
            { code: "TOT", label: "Captured",  value: spans.length.toString(),                                  color: "var(--t0)" },
            { code: "ERR", label: "Errors",     value: stats.errored.toString(),                                 color: stats.errored > 0 ? "var(--r0)" : "var(--t2)" },
            { code: "AVG", label: "Avg Score",  value: stats.avg !== null ? stats.avg.toFixed(1) : "—",         color: "var(--p0)" },
            { code: "PSS", label: "Pass Rate",  value: stats.pass !== null ? `${(stats.pass * 100).toFixed(0)}%` : "—", color: "var(--p0)" },
          ].map((s, i) => (
            <div key={s.code} style={{
              flex: 1, padding: "4px 16px",
              borderRight: i < 3 ? "1px solid var(--b1)" : "none",
              display: "flex", flexDirection: "column", gap: "2px",
            }}>
              <span style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", letterSpacing: "0.16em" }}>
                [{s.code}] {s.label}
              </span>
              <span style={{ fontFamily: "var(--f-mono)", fontSize: "16px", fontWeight: 700, color: s.color, lineHeight: 1 }}>
                {s.value}
              </span>
            </div>
          ))}
          {paused && (
            <div style={{ display: "flex", alignItems: "center", padding: "0 16px", borderLeft: "1px solid var(--b1)" }}>
              <span className="sig sig-a">PAUSED</span>
            </div>
          )}
        </div>
      )}

      {/* Feed */}
      {spans.length === 0 ? (
        <div className="panel">
          <div className="panel-accent"/>
          <div className="empty">
            <div style={{ width: "48px", height: "48px", border: "1px solid var(--pb)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <span className="live-dot"/>
            </div>
            <p className="empty-title">WAITING FOR TRACES…</p>
            <p className="empty-sub">Instrument your app with the SDK and calls appear here instantly</p>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
          {spans.map((span, i) => (
            <SpanRow
              key={span.span_id || span.id}
              span={span}
              isNew={i === 0 && (span.span_id || span.id) === newestId}
            />
          ))}
        </div>
      )}
    </div>
  )
}