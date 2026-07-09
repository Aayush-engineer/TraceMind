// pages/Dashboard.tsx
import { useMemo, useCallback, memo } from "react"
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from "recharts"
import type { AppContext } from "../App"
import { useApis } from "../hooks/useApi"
import type { Stats, MetricPoint, Alert, EvalRun, EvalResult } from "../lib/types"
import { scoreColor } from "../lib/types"

// ─── Sub-components memoized to prevent cascade re-renders ───────────────────

const StatCard = memo(function StatCard({ code, label, value, unit, color, sub }: {
  code: string; label: string; value: string; unit: string
  color: string; sub: string
}) {
  return (
    <div className="panel" style={{ padding: "14px 16px" }}>
      <div className="panel-accent"/>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "10px" }}>
        <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", fontWeight: 700, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--t3)" }}>
          [{code}] {label}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginBottom: "5px" }}>
        <span style={{ fontFamily: "var(--f-mono)", fontSize: "24px", fontWeight: 700, color, lineHeight: 1, letterSpacing: "-0.03em" }}>
          {value}
        </span>
        {unit && <span style={{ fontFamily: "var(--f-mono)", fontSize: "12px", color: "var(--t3)" }}>{unit}</span>}
      </div>
      <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0, letterSpacing: "0.04em" }}>{sub}</p>
    </div>
  )
})

const AlertItem = memo(function AlertItem({ alert }: { alert: Alert }) {
  const color = alert.severity === "critical" || alert.severity === "high"
    ? "var(--r0)" : alert.severity === "medium" ? "var(--a0)" : "var(--c0)"
  return (
    <div style={{
      padding: "8px 10px",
      background: "var(--raised)",
      border: "1px solid var(--b1)",
      borderLeft: `2px solid ${color}`,
      borderRadius: "var(--r1)",
    }}>
      <div style={{ fontFamily: "var(--f-mono)", fontSize: "8px", fontWeight: 700, color, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: "3px" }}>
        {alert.severity?.toUpperCase()} · {alert.type?.replace(/_/g, " ").toUpperCase()}
      </div>
      <div style={{ fontSize: "11px", color: "var(--t2)", lineHeight: 1.4 }}>
        {alert.message?.slice(0, 80)}
      </div>
    </div>
  )
})

const RunItem = memo(function RunItem({ run }: { run: EvalRun }) {
  const pr    = run.pass_rate || 0
  const color = scoreColor(pr * 10)
  const circ  = 2 * Math.PI * 13
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "10px",
      padding: "9px 10px",
      background: "var(--raised)",
      border: "1px solid var(--b1)",
      borderRadius: "var(--r1)",
      marginBottom: "5px",
    }}>
      <div className="panel-accent"/>
      <div style={{ position: "relative", width: "34px", height: "34px", flexShrink: 0 }}>
        <svg viewBox="0 0 34 34" style={{ transform: "rotate(-90deg)", width: "100%", height: "100%" }}>
          <circle cx="17" cy="17" r="13" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="3.5"/>
          <circle cx="17" cy="17" r="13" fill="none" stroke={color} strokeWidth="3.5"
            strokeLinecap="round" strokeDasharray={`${pr * circ} 999`}/>
        </svg>
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: "var(--f-mono)", fontSize: "7px", fontWeight: 700, color }}>
          {Math.round(pr * 100)}
        </div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "11px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {run.name || "unnamed"}
        </p>
        <p style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", margin: 0 }}>
          {run.created_at ? new Date(run.created_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) : "—"}
        </p>
      </div>
      <span className={`sig ${run.status === "completed" ? "sig-p" : run.status === "running" ? "sig-c" : "sig-r"}`}>
        {run.status?.toUpperCase()}
      </span>
    </div>
  )
})

// ─── Main Dashboard ───────────────────────────────────────────────────────────
export default function Dashboard({ projectId, apiKey, apiUrl }: AppContext) {
  const base = `${apiUrl}/api`

  // Single parallel fetch — 4 endpoints at once, auto-refresh every 30 s
  const { data, loading, error, refetch } = useApis<{
    summary: { avg_score: number; pass_rate: number; total_calls: number; cost: number }
    metrics: { points: MetricPoint[] }
    alerts:  { alerts: Alert[] }
    runs:    { runs: EvalRun[] }
  }>({
    summary: `${base}/metrics/${projectId}/summary`,
    metrics: `${base}/metrics/${projectId}?hours=24`,
    alerts:  `${base}/alerts/${projectId}?resolved=false`,
    runs:    `${base}/metrics/${projectId}/evals`,
  }, apiKey, { interval: 30_000 })

  // ── Derived state — only recomputed when data changes ──────────────────────
  const stats = useMemo<Stats>(() => ({
    avg_score:   Number(data.summary?.avg_score   ?? 0),
    pass_rate:   Number(data.summary?.pass_rate   ?? 0),
    total_calls: Number(data.summary?.total_calls ?? 0),
    cost:        Number(data.summary?.cost        ?? 0),
  }), [data.summary])

  const chartData = useMemo(
    () => (data.metrics?.points ?? []).filter(p => p.call_count > 0),
    [data.metrics]
  )

  const alerts = useMemo(() => data.alerts?.alerts ?? [], [data.alerts])
  const runs   = useMemo(() => data.runs?.runs ?? [],     [data.runs])

  // Categories derived from first eval run (fetched lazily from run list)
  const categories = useMemo(() => {
    const firstRun = runs[0]
    if (!firstRun?.results) return []
    const catMap: Record<string, { passed: number; total: number }> = {}
    firstRun.results.forEach((r: EvalResult) => {
      const c = r.category || "general"
      if (!catMap[c]) catMap[c] = { passed: 0, total: 0 }
      catMap[c].total++
      if (r.passed) catMap[c].passed++
    })
    return Object.entries(catMap)
      .map(([name, s]) => ({ name, rate: s.total > 0 ? s.passed / s.total : 0, total: s.total }))
      .sort((a, b) => a.rate - b.rate)
  }, [runs])

  const hPct      = Math.round(stats.pass_rate * 100)
  const ringColor = scoreColor(stats.pass_rate * 10)
  const circ      = 2 * Math.PI * 28

  const statCards = useMemo(() => [
    { code: "AQI", label: "Avg Quality",  value: stats.avg_score.toFixed(2),              unit: "/ 10", color: scoreColor(stats.avg_score),          sub: stats.avg_score >= 7 ? "above threshold" : "below threshold" },
    { code: "PAS", label: "Pass Rate",    value: (stats.pass_rate * 100).toFixed(1),       unit: "%",    color: scoreColor(stats.pass_rate * 10),       sub: `${Math.round(stats.pass_rate * stats.total_calls)} of ${stats.total_calls}` },
    { code: "VOL", label: "Total Calls",  value: stats.total_calls.toLocaleString(),        unit: "",     color: "var(--c0)",                            sub: "last 24 hours" },
    { code: "CST", label: "Cost (24h)",   value: `$${stats.cost.toFixed(4)}`,               unit: "",     color: "var(--a0)",                            sub: "groq free tier" },
  ], [stats])

  const tooltipStyle = useMemo(() => ({
    background: "var(--overlay)", border: "1px solid var(--b2)",
    borderRadius: "var(--r1)", fontSize: "10px",
    fontFamily: "Space Mono", color: "var(--t0)",
    boxShadow: "0 8px 24px rgba(0,0,0,0.6)", padding: "8px 12px",
  }), [])

  const handleRefetch = useCallback(refetch, [refetch])

  if (loading && !data.summary) return (
    <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "10px" }}>
      {[90, 140, 200].map((h, i) => <div key={i} className="skeleton" style={{ height: h }}/>)}
    </div>
  )

  return (
    <div style={{ padding: "18px 20px" }}>

      {error && (
        <div style={{ padding: "9px 14px", marginBottom: "14px", background: "var(--rg)", border: "1px solid var(--rb)", borderRadius: "var(--r1)", color: "var(--r0)", fontFamily: "var(--f-mono)", fontSize: "10px" }}>
          {error}
        </div>
      )}

      {/* Status bar */}
      <div className="panel" style={{ padding: "14px 18px", marginBottom: "14px", display: "flex", alignItems: "center", gap: "20px", overflow: "hidden" }}>
        <div className="panel-accent"/>

        {/* Ring */}
        <div style={{ position: "relative", width: "70px", height: "70px", flexShrink: 0 }}>
          <svg viewBox="0 0 70 70" style={{ transform: "rotate(-90deg)", width: "100%", height: "100%" }}>
            <circle cx="35" cy="35" r="28" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="5"/>
            <circle cx="35" cy="35" r="28" fill="none" stroke={ringColor} strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={`${stats.pass_rate * circ} 999`}
            />
          </svg>
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: "var(--f-mono)", fontSize: "14px", fontWeight: 700, color: ringColor, lineHeight: 1 }}>{hPct}%</span>
            <span style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", marginTop: "2px" }}>PASS</span>
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "5px" }}>
            <span style={{ fontFamily: "var(--f-display)", fontSize: "16px", fontWeight: 700, color: "var(--t0)" }}>
              {stats.pass_rate >= 0.8 ? "System nominal" : stats.pass_rate >= 0.6 ? "Needs attention" : "Quality degraded"}
            </span>
            <span className={`sig ${stats.pass_rate >= 0.8 ? "sig-p" : stats.pass_rate >= 0.6 ? "sig-a" : "sig-r"}`}>
              {stats.pass_rate >= 0.8 ? "NOMINAL" : stats.pass_rate >= 0.6 ? "DEGRADED" : "CRITICAL"}
            </span>
          </div>
          <div style={{ display: "flex", gap: "20px" }}>
            {[
              { label: "CALLS", value: stats.total_calls.toLocaleString() },
              { label: "AVG",   value: `${stats.avg_score.toFixed(1)}/10` },
            ].map(s => (
              <div key={s.label} style={{ display: "flex", gap: "6px", alignItems: "baseline" }}>
                <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", letterSpacing: "0.1em" }}>{s.label}</span>
                <span style={{ fontFamily: "var(--f-mono)", fontSize: "11px", color: "var(--t1)" }}>{s.value}</span>
              </div>
            ))}
          </div>
        </div>

        <button onClick={handleRefetch} className="btn btn-ghost" style={{ padding: "6px 12px", fontSize: "9px", flexShrink: 0 }}>
          ↻ SYNC
        </button>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: "10px", marginBottom: "14px" }}>
        {statCards.map(c => <StatCard key={c.code} {...c}/>)}
      </div>

      {/* Chart + Alerts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: "10px", marginBottom: "10px" }}>
        <div className="panel" style={{ padding: "14px 16px" }}>
          <div className="panel-accent"/>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "14px" }}>
            <div>
              <span className="panel-label">[QOT] Quality over time</span>
              <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: "3px 0 0" }}>hourly avg · last 24h</p>
            </div>
          </div>
          {chartData.length === 0 ? (
            <div className="empty" style={{ height: "160px" }}>
              <span className="empty-glyph">◈</span>
              <p className="empty-title">No data yet</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={160}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }}>
                <defs>
                  <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#00ff88" stopOpacity={0.18}/>
                    <stop offset="100%" stopColor="#00ff88" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="2 4" stroke="rgba(120,180,255,0.05)" vertical={false}/>
                <XAxis dataKey="hour" tick={{ fontSize: 8, fill: "var(--t3)", fontFamily: "Space Mono" }} axisLine={false} tickLine={false}/>
                <YAxis domain={[0, 10]} tick={{ fontSize: 8, fill: "var(--t3)", fontFamily: "Space Mono" }} axisLine={false} tickLine={false}/>
                <Tooltip contentStyle={tooltipStyle} formatter={(v) => [typeof v === "number" ? v.toFixed(2) : "0.00", "score"]}/>
                <ReferenceLine y={7} stroke="var(--r0)" strokeDasharray="3 5" strokeWidth={1} strokeOpacity={0.4}/>
                <Area type="monotone" dataKey="avg_score" stroke="var(--p0)" strokeWidth={1.5} fill="url(#areaGrad)" dot={false} activeDot={{ r: 3, fill: "var(--p0)", stroke: "none" }}/>
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="panel" style={{ display: "flex", flexDirection: "column" }}>
          <div className="panel-accent"/>
          <div className="panel-header">
            <span className="panel-label">[ALT] Active Alerts</span>
            {alerts.length > 0 && <span className="sig sig-r">{alerts.length}</span>}
          </div>
          <div style={{ flex: 1, padding: "10px", display: "flex", flexDirection: "column", gap: "5px" }}>
            {alerts.length === 0 ? (
              <div className="empty" style={{ padding: "2rem" }}>
                <div style={{ width: "34px", height: "34px", background: "var(--pg)", border: "1px solid var(--pb)", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "15px", color: "var(--p0)" }}>✓</div>
                <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--p3)", letterSpacing: "0.06em" }}>ALL NOMINAL</p>
              </div>
            ) : alerts.slice(0, 5).map(a => <AlertItem key={a.id} alert={a}/>)}
          </div>
        </div>
      </div>

      {/* Categories + Runs */}
      <div style={{ display: "grid", gridTemplateColumns: categories.length > 0 ? "1fr 1fr" : "1fr", gap: "10px" }}>
        {categories.length > 0 && (
          <div className="panel" style={{ padding: 0 }}>
            <div className="panel-accent"/>
            <div className="panel-header">
              <span className="panel-label">[CAT] Pass Rate by Category</span>
            </div>
            <div style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: "10px" }}>
              {categories.map(cat => (
                <div key={cat.name} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span style={{ width: "68px", textAlign: "right", flexShrink: 0, fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t2)", textTransform: "capitalize" }}>
                    {cat.name}
                  </span>
                  <div style={{ flex: 1, height: "5px", background: "var(--raised)", borderRadius: "2px", overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${cat.rate * 100}%`, background: scoreColor(cat.rate * 10), borderRadius: "2px" }}/>
                  </div>
                  <span style={{ width: "32px", textAlign: "right", flexShrink: 0, fontFamily: "var(--f-mono)", fontSize: "10px", fontWeight: 700, color: scoreColor(cat.rate * 10) }}>
                    {Math.round(cat.rate * 100)}%
                  </span>
                  <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", width: "32px", flexShrink: 0 }}>
                    n={cat.total}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="panel" style={{ padding: 0 }}>
          <div className="panel-accent"/>
          <div className="panel-header"><span className="panel-label">[RUN] Recent Eval Runs</span></div>
          <div style={{ padding: "10px" }}>
            {runs.length === 0 ? (
              <div className="empty" style={{ padding: "2rem" }}>
                <span className="empty-glyph">◆</span>
                <p className="empty-title">No runs yet</p>
              </div>
            ) : runs.slice(0, 5).map(run => <RunItem key={run.run_id} run={run}/>)}
          </div>
        </div>
      </div>
    </div>
  )
}