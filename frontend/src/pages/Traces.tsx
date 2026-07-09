// pages/Traces.tsx
import { useState, useMemo, useCallback, memo } from "react"
import type { AppContext } from "../App"
import { useApi } from "../hooks/useApi"
import type { Span } from "../lib/types"
import { scoreColor, scoreChip } from "../lib/types"

// ─── Row — memoized so only changed rows re-render ───────────────────────────
const SpanRow = memo(function SpanRow({
  span, selected, onSelect
}: { span: Span; selected: boolean; onSelect: (s: Span | null) => void }) {
  const sc = scoreColor(span.score)

  const handleClick = useCallback(() => {
    onSelect(selected ? null : span)
  }, [selected, span, onSelect])

  return (
    <tr onClick={handleClick} style={{ background: selected ? "var(--hover)" : "transparent" }}>
      <td>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {span.has_error && <span style={{ color: "var(--r0)", fontSize: "10px" }}>⚠</span>}
          <div>
            <div style={{ fontWeight: 500, color: "var(--t0)", fontSize: "12px", marginBottom: "2px" }}>{span.name}</div>
            <div style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)" }}>
              {span.input.slice(0, 55)}{span.input.length > 55 ? "…" : ""}
            </div>
          </div>
        </div>
      </td>
      <td><span className={`sig ${scoreChip(span.score)}`}>{span.score !== null ? (+span.score).toFixed(1) : "—"}</span></td>
      <td style={{ fontFamily: "var(--f-mono)", fontSize: "10px" }}>{span.duration_ms.toFixed(0)}ms</td>
      <td><span className={`sig ${span.status === "success" ? "sig-p" : "sig-r"}`}>{span.status?.toUpperCase()}</span></td>
      <td style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)" }}>
        {new Date(span.timestamp * 1000).toLocaleTimeString("en-US", { hour12: false })}
      </td>
    </tr>
  )
})

// ─── Detail panel — memoized ─────────────────────────────────────────────────
const DetailPanel = memo(function DetailPanel({ span, onClose }: { span: Span; onClose: () => void }) {
  const sc = scoreColor(span.score)
  return (
    <div className="panel" style={{ padding: 0, height: "fit-content", position: "sticky", top: "20px" }}>
      <div className="panel-accent"/>
      <div className="panel-header">
        <span className="panel-label" style={{ fontFamily: "var(--f-mono)", fontSize: "11px" }}>{span.name}</span>
        <button onClick={onClose} className="btn btn-ghost" style={{ padding: "2px 8px" }}>✕</button>
      </div>
      <div style={{ padding: "14px" }}>
        <div style={{ padding: "12px 14px", marginBottom: "12px", background: "var(--raised)", border: "1px solid var(--b1)", borderLeft: `2px solid ${sc}`, borderRadius: "var(--r1)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.1em" }}>QUALITY SCORE</span>
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "22px", fontWeight: 700, color: sc }}>
            {span.score !== null ? (+span.score).toFixed(1) : "—"}
            <span style={{ fontSize: "11px", color: "var(--t3)" }}>/10</span>
          </span>
        </div>
        {[{ label: "INPUT", val: span.input || "—" }, { label: "OUTPUT", val: span.output || "—" }].map(f => (
          <div key={f.label} style={{ marginBottom: "10px" }}>
            <div style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", letterSpacing: "0.16em", textTransform: "uppercase", marginBottom: "5px" }}>{f.label}</div>
            <div style={{ background: "var(--base)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", padding: "9px", fontSize: "11px", color: "var(--t1)", lineHeight: 1.6, maxHeight: "90px", overflowY: "auto", fontFamily: "var(--f-data)" }}>{f.val}</div>
          </div>
        ))}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
          {[
            { l: "DURATION", v: `${span.duration_ms.toFixed(0)}ms` },
            { l: "STATUS",   v: span.status },
            { l: "TRACE",    v: span.trace_id.slice(0, 10) + "…" },
            { l: "TIME",     v: new Date(span.timestamp * 1000).toLocaleTimeString("en-US", { hour12: false }) },
          ].map(m => (
            <div key={m.l} style={{ background: "var(--base)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", padding: "8px 10px" }}>
              <p style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", margin: "0 0 3px", letterSpacing: "0.16em" }}>{m.l}</p>
              <p style={{ fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--t1)", margin: 0 }}>{m.v}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
})

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function Traces({ projectId, apiKey, apiUrl }: AppContext) {
  const [filter,   setFilter]   = useState<"all" | "failed" | "errors">("all")
  const [selected, setSelected] = useState<Span | null>(null)
  const [search,   setSearch]   = useState("")
  const [minScore, setMinScore] = useState(0)

  const url = useMemo(() => {
    const base = `${apiUrl}/api/traces/project/${projectId}?limit=50`
    return filter === "failed" ? `${base}&min_score=7` : base
  }, [apiUrl, projectId, filter])

  const { data, loading, refetch } = useApi<{ spans: Span[] }>(url, apiKey, { interval: 15_000 })

  // Filtered list — only recomputed when deps change
  const spans = useMemo(() => {
    const all = data?.spans ?? []
    if (!search && !minScore) return all
    const q = search.toLowerCase()
    return all.filter(s => {
      const ms = !q || s.input.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
      const mv = !minScore || (s.score !== null && s.score <= minScore)
      return ms && mv
    })
  }, [data, search, minScore])

  const handleSelect = useCallback((s: Span | null) => setSelected(s), [])
  const handleClose  = useCallback(() => setSelected(null), [])

  const clearFilters = useCallback(() => { setSearch(""); setMinScore(0) }, [])

  return (
    <div style={{ padding: "18px 20px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px" }}>Traces</h1>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>
          [TRC] EVERY LLM CALL CAPTURED BY THE SDK · {spans.length} RESULTS
        </p>
      </div>

      <div style={{ display: "flex", gap: "6px", marginBottom: "10px", flexWrap: "wrap" }}>
        {(["all", "failed", "errors"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} className={`btn ${filter === f ? "btn-p" : "btn-ghost"}`} style={{ padding: "5px 12px" }}>
            {f === "all" ? "ALL" : f === "failed" ? "LOW SCORE" : "ERRORS"}
          </button>
        ))}
        <div style={{ flex: 1 }}/>
        <button onClick={refetch} className="btn btn-ghost" style={{ padding: "5px 12px" }}>↻ REFRESH</button>
      </div>

      <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        <div style={{ flex: 1, position: "relative" }}>
          <span style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--t3)", fontFamily: "var(--f-mono)", fontSize: "11px", pointerEvents: "none" }}>⌕</span>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search input or span name…" className="field" style={{ paddingLeft: "28px" }}/>
        </div>
        <select value={minScore} onChange={e => setMinScore(+e.target.value)} className="field" style={{ width: "auto" }}>
          <option value={0}>Any score</option>
          <option value={5}>Below 5</option>
          <option value={6}>Below 6</option>
          <option value={7}>Below 7</option>
          <option value={8}>Below 8</option>
        </select>
        {(search || minScore > 0) && (
          <button onClick={clearFilters} className="btn btn-ghost" style={{ padding: "5px 10px" }}>✕</button>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 360px" : "1fr", gap: "12px" }}>
        <div className="panel" style={{ padding: 0 }}>
          <div className="panel-accent"/>
          {loading && !data ? (
            <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
              <div className="animate-spin" style={{ width: 24, height: 24, border: "2px solid var(--b2)", borderTop: "2px solid var(--p0)", borderRadius: "50%" }}/>
            </div>
          ) : spans.length === 0 ? (
            <div className="empty"><span className="empty-glyph">≋</span><p className="empty-title">No traces found</p></div>
          ) : (
            <table className="dt">
              <thead><tr>{["Span / Input", "Score", "Duration", "Status", "Time"].map(h => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {spans.map(span => (
                  <SpanRow
                    key={span.id || span.span_id}
                    span={span}
                    selected={selected?.id === span.id}
                    onSelect={handleSelect}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {selected && <DetailPanel span={selected} onClose={handleClose}/>}
      </div>
    </div>
  )
}