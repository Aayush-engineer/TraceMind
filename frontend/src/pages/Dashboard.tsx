import { useEffect, useState, useCallback } from "react"
import {
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine
} from "recharts"
import type { AppContext } from "../App"

interface Props extends AppContext {}

interface Stats {
  avg_score:   number
  pass_rate:   number
  total_calls: number
  cost:        number
}

export default function Dashboard({ projectId, apiKey, apiUrl }: Props) {
  const [stats,      setStats]      = useState<Stats>({ avg_score:0, pass_rate:0, total_calls:0, cost:0 })
  const [metrics,    setMetrics]    = useState<any[]>([])
  const [alerts,     setAlerts]     = useState<any[]>([])
  const [runs,       setRuns]       = useState<any[]>([])
  const [categories, setCategories] = useState<any[]>([])
  const [loading,    setLoading]    = useState(true)
  const [lastUpdated,setLastUpdated]= useState<Date|null>(null)
  const [error,      setError]      = useState("")

  const headers = { "Authorization": `Bearer ${apiKey}` }

  const fetchAll = useCallback(async () => {
    try {
      const [sRes, mRes, aRes, rRes] = await Promise.all([
        fetch(`${apiUrl}/api/metrics/${projectId}/summary`,      { headers }),
        fetch(`${apiUrl}/api/metrics/${projectId}?hours=24`,     { headers }),
        fetch(`${apiUrl}/api/alerts/${projectId}?resolved=false`,{ headers }),
        fetch(`${apiUrl}/api/metrics/${projectId}/evals`,        { headers }),
      ])

      if (!sRes.ok) { setError("Failed to load — check credentials"); setLoading(false); return }

      const [s, m, a, r] = await Promise.all([sRes.json(), mRes.json(), aRes.json(), rRes.json()])

      setStats({
        avg_score:   Number(s.avg_score   || 0),
        pass_rate:   Number(s.pass_rate   || 0),
        total_calls: Number(s.total_calls || 0),
        cost:        Number(s.cost        || 0),
      })
      setMetrics(m.points || [])
      setAlerts(a.alerts  || [])
      setRuns(r.runs      || [])
      setError("")
      setLastUpdated(new Date())

      // Category data from latest eval
      if (r.runs?.[0]) {
        try {
          const er = await fetch(`${apiUrl}/api/evals/${r.runs[0].run_id}`, { headers })
          if (er.ok) {
            const ed = await er.json()
            const catMap: Record<string, {passed:number,total:number}> = {}
            ed.results?.forEach((res: any) => {
              const c = res.category || "general"
              if (!catMap[c]) catMap[c] = { passed:0, total:0 }
              catMap[c].total++
              if (res.passed) catMap[c].passed++
            })
            setCategories(
              Object.entries(catMap)
                .map(([name, s]) => ({ name, pass_rate: s.total > 0 ? s.passed/s.total : 0, total: s.total }))
                .sort((a,b) => a.pass_rate - b.pass_rate)
            )
          }
        } catch { /* ignore */ }
      }
    } catch { setError("Cannot connect to server") }
    finally  { setLoading(false) }
  }, [projectId, apiKey])

  useEffect(() => {
    fetchAll()
    const i = setInterval(fetchAll, 30000)
    return () => clearInterval(i)
  }, [fetchAll])

  const sc = (v: number) => v >= 8 ? "var(--green)" : v >= 6 ? "var(--amber)" : "var(--red)"

  if (loading) return (
    <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "16px" }}>
      {[100,80,120,60].map((w,i) => (
        <div key={i} style={{
          height: "80px", borderRadius: "var(--radius-lg)",
          background: "linear-gradient(90deg, var(--bg-elevated) 25%, var(--bg-overlay) 50%, var(--bg-elevated) 75%)",
          backgroundSize: "200% 100%",
          animation: "shimmer 1.5s infinite",
        }}/>
      ))}
    </div>
  )

  const chartData = metrics.filter(m => m.call_count > 0)
  const healthPct = Math.round(stats.pass_rate * 100)

  return (
    <div style={{ padding: "20px 24px", animation: "fadeIn 0.3s ease" }}>

      {error && (
        <div style={{
          background: "var(--red-bg)", border: "1px solid rgba(248,81,73,0.3)",
          borderRadius: "var(--radius-md)", padding: "10px 14px",
          color: "var(--red)", fontSize: "13px", marginBottom: "16px"
        }}>⚠ {error}</div>
      )}

      {/* Hero — health ring + key stats */}
      <div style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-xl)",
        padding: "20px 24px",
        marginBottom: "16px",
        display: "flex",
        alignItems: "center",
        gap: "24px",
        position: "relative",
        overflow: "hidden",
      }}>
        {/* Background glow */}
        <div style={{
          position: "absolute", top: "-40px", left: "-40px",
          width: "200px", height: "200px",
          background: `radial-gradient(circle, ${stats.pass_rate >= 0.8 ? "rgba(63,185,80,0.06)" : stats.pass_rate >= 0.6 ? "rgba(210,153,34,0.06)" : "rgba(248,81,73,0.06)"} 0%, transparent 70%)`,
          pointerEvents: "none",
        }}/>

        {/* Ring */}
        <div style={{ position: "relative", width: "72px", height: "72px", flexShrink: 0 }}>
          <svg viewBox="0 0 72 72" style={{ transform: "rotate(-90deg)" }}>
            <circle cx="36" cy="36" r="30" fill="none"
                    stroke="var(--bg-overlay)" strokeWidth="6"/>
            <circle cx="36" cy="36" r="30" fill="none"
                    stroke={sc(stats.pass_rate * 10)}
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeDasharray={`${2 * Math.PI * 30}`}
                    strokeDashoffset={`${2 * Math.PI * 30 * (1 - stats.pass_rate)}`}
                    style={{ transition: "stroke-dashoffset 1s ease" }}/>
          </svg>
          <div style={{
            position: "absolute", inset: 0,
            display: "flex", alignItems: "center", justifyContent: "center",
            flexDirection: "column",
          }}>
            <span style={{ fontSize: "14px", fontWeight: 700,
                           color: sc(stats.pass_rate * 10), lineHeight: 1 }}>
              {healthPct}%
            </span>
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
            <span style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)" }}>
              {stats.pass_rate >= 0.8 ? "System healthy" :
               stats.pass_rate >= 0.6 ? "Needs attention" : "Quality degraded"}
            </span>
            <span style={{
              fontSize: "10px", fontWeight: 600, padding: "2px 8px",
              borderRadius: "99px", textTransform: "uppercase",
              background: stats.pass_rate >= 0.8 ? "var(--green-bg)" :
                          stats.pass_rate >= 0.6 ? "var(--amber-bg)" : "var(--red-bg)",
              color: sc(stats.pass_rate * 10),
              border: `1px solid ${stats.pass_rate >= 0.8 ? "rgba(63,185,80,0.3)" : stats.pass_rate >= 0.6 ? "rgba(210,153,34,0.3)" : "rgba(248,81,73,0.3)"}`,
            }}>
              {stats.pass_rate >= 0.8 ? "nominal" : stats.pass_rate >= 0.6 ? "degraded" : "critical"}
            </span>
          </div>
          <p style={{ fontSize: "13px", color: "var(--text-secondary)", margin: 0 }}>
            {stats.total_calls.toLocaleString()} calls monitored
            {" · "}avg score {stats.avg_score.toFixed(1)}/10
            {" · "}last updated {lastUpdated?.toLocaleTimeString()}
          </p>
        </div>

        <button
          onClick={fetchAll}
          style={{
            padding: "7px 14px",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border-default)",
            borderRadius: "var(--radius-md)",
            color: "var(--text-secondary)",
            fontSize: "12px",
            cursor: "pointer",
            transition: "all var(--transition)",
            flexShrink: 0,
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Stat cards */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr)",
        gap: "10px",
        marginBottom: "16px",
      }}>
        {[
          { label: "Avg quality",   value: stats.avg_score.toFixed(2), unit: "/10",
            color: sc(stats.avg_score), icon: "◎",
            sub: stats.avg_score >= 7 ? "Above threshold" : "Below threshold" },
          { label: "Pass rate",     value: `${(stats.pass_rate*100).toFixed(1)}`, unit: "%",
            color: sc(stats.pass_rate*10), icon: "✓",
            sub: `${Math.round(stats.pass_rate*stats.total_calls)} of ${stats.total_calls}` },
          { label: "Total calls",   value: stats.total_calls.toLocaleString(), unit: "",
            color: "var(--blue)", icon: "⚡", sub: "Last 24 hours" },
          { label: "Cost (24h)",    value: `$${stats.cost.toFixed(4)}`, unit: "",
            color: "var(--purple)", icon: "$", sub: "Groq free tier" },
        ].map(card => (
          <div
            key={card.label}
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-lg)",
              padding: "16px",
              transition: "border-color var(--transition), transform var(--transition)",
              cursor: "default",
              position: "relative",
              overflow: "hidden",
            }}
            onMouseEnter={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)"
              ;(e.currentTarget as HTMLElement).style.transform = "translateY(-1px)"
            }}
            onMouseLeave={e => {
              (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)"
              ;(e.currentTarget as HTMLElement).style.transform = "none"
            }}
          >
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, height: "2px",
              background: `linear-gradient(90deg, ${card.color}66, transparent)`,
            }}/>
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: "10px",
            }}>
              <span style={{ fontSize: "11px", color: "var(--text-muted)",
                             textTransform: "uppercase", letterSpacing: "0.06em",
                             fontWeight: 600 }}>
                {card.label}
              </span>
              <span style={{
                width: "28px", height: "28px",
                background: `${card.color}18`,
                borderRadius: "var(--radius-sm)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "12px", color: card.color,
              }}>{card.icon}</span>
            </div>
            <p style={{ fontSize: "22px", fontWeight: 700, color: card.color, margin: "0 0 4px" }}>
              {card.value}
              <span style={{ fontSize: "12px", color: "var(--text-muted)",
                             fontWeight: 400, marginLeft: "3px" }}>{card.unit}</span>
            </p>
            <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: 0 }}>
              {card.sub}
            </p>
          </div>
        ))}
      </div>

      {/* Chart + Alerts */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: "12px", marginBottom: "12px" }}>

        {/* Area chart */}
        <div style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "18px 20px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h2 style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 2px" }}>
                Quality over time
              </h2>
              <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: 0 }}>
                Hourly average — last 24 hours
              </p>
            </div>
            <div style={{ display: "flex", gap: "12px", fontSize: "11px", color: "var(--text-muted)" }}>
              <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                <span style={{ width: "20px", height: "2px", background: "var(--accent-light)", display: "inline-block" }}/>
                Score
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                <span style={{ width: "16px", height: "1px", background: "var(--red)", display: "inline-block",
                               borderTop: "1px dashed var(--red)" }}/>
                Threshold
              </span>
            </div>
          </div>

          {chartData.length === 0 ? (
            <div style={{ height: "180px", display: "flex", flexDirection: "column",
                          alignItems: "center", justifyContent: "center", gap: "8px" }}>
              <span style={{ fontSize: "28px" }}>📊</span>
              <span style={{ fontSize: "13px", color: "var(--text-muted)" }}>
                No data — ingest spans to see quality trend
              </span>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={metrics} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                <defs>
                  <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%"   stopColor="#a78bfa" stopOpacity={0.3}/>
                    <stop offset="100%" stopColor="#a78bfa" stopOpacity={0.0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false}/>
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                       axisLine={false} tickLine={false}/>
                <YAxis domain={[0,10]} tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                       axisLine={false} tickLine={false}/>
                <Tooltip
                  contentStyle={{
                    background: "var(--bg-overlay)", border: "1px solid var(--border-default)",
                    borderRadius: "8px", fontSize: "12px", color: "var(--text-primary)"
                  }}
                  formatter={(v) => [
                      typeof v === "number" ? v.toFixed(2) : "0.00",
                      "Avg score"
                    ]}
                />
                <ReferenceLine y={7} stroke="var(--red)" strokeDasharray="4 4" strokeWidth={1}/>
                <Area type="monotone" dataKey="avg_score"
                      stroke="#a78bfa" strokeWidth={2}
                      fill="url(#scoreGrad)"
                      dot={false} activeDot={{ r: 4, fill: "#a78bfa" }}/>
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Alerts */}
        <div style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "16px",
          display: "flex",
          flexDirection: "column",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
            <h2 style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              Active alerts
            </h2>
            {alerts.length > 0 && (
              <span style={{
                background: "var(--red-bg)", color: "var(--red)",
                fontSize: "10px", fontWeight: 700, padding: "2px 7px",
                borderRadius: "99px", border: "1px solid rgba(248,81,73,0.3)"
              }}>
                {alerts.length}
              </span>
            )}
          </div>

          {alerts.length === 0 ? (
            <div style={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: "8px",
              color: "var(--text-muted)", fontSize: "13px"
            }}>
              <div style={{
                width: "36px", height: "36px",
                background: "var(--green-bg)",
                borderRadius: "50%",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "16px",
              }}>✓</div>
              <span style={{ color: "var(--green)", fontSize: "12px" }}>All metrics healthy</span>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {alerts.slice(0,4).map((alert: any) => {
                const colors: Record<string,string> = {
                  low:"var(--blue)", medium:"var(--amber)", high:"var(--red)", critical:"var(--red)"
                }
                return (
                  <div key={alert.id} style={{
                    background: "var(--bg-overlay)",
                    border: "1px solid var(--border-subtle)",
                    borderLeft: `3px solid ${colors[alert.severity] || "var(--amber)"}`,
                    borderRadius: "6px",
                    padding: "8px 10px",
                  }}>
                    <div style={{ fontSize: "11px", fontWeight: 600,
                                  color: colors[alert.severity], marginBottom: "2px",
                                  textTransform: "capitalize" }}>
                      {alert.type?.replace(/_/g," ")}
                    </div>
                    <div style={{ fontSize: "11px", color: "var(--text-muted)", lineHeight: 1.4 }}>
                      {alert.message?.slice(0,80)}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Category breakdown + Eval runs */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", marginBottom: "12px" }}>

        {/* Category bars */}
        {categories.length > 0 && (
          <div style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border-subtle)",
            borderRadius: "var(--radius-lg)",
            padding: "16px 20px",
          }}>
            <h2 style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 4px" }}>
              Pass rate by category
            </h2>
            <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: "0 0 14px" }}>
              From latest eval run
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {categories.map(cat => (
                <div key={cat.name} style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <span style={{
                    width: "72px", fontSize: "11px", color: "var(--text-secondary)",
                    textAlign: "right", flexShrink: 0, textTransform: "capitalize",
                    fontWeight: 500,
                  }}>
                    {cat.name}
                  </span>
                  <div style={{
                    flex: 1, height: "6px",
                    background: "var(--bg-overlay)",
                    borderRadius: "3px",
                    overflow: "hidden",
                  }}>
                    <div style={{
                      height: "100%",
                      width: `${cat.pass_rate * 100}%`,
                      background: cat.pass_rate >= 0.8 ? "var(--green)" :
                                  cat.pass_rate >= 0.6 ? "var(--amber)" : "var(--red)",
                      borderRadius: "3px",
                      transition: "width 0.8s ease",
                    }}/>
                  </div>
                  <span style={{
                    width: "36px", fontSize: "11px", fontWeight: 700,
                    color: sc(cat.pass_rate * 10), textAlign: "right",
                  }}>
                    {Math.round(cat.pass_rate * 100)}%
                  </span>
                  <span style={{ fontSize: "10px", color: "var(--text-muted)", width: "44px" }}>
                    {cat.total} cases
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Eval runs */}
        <div style={{
          background: "var(--bg-elevated)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "var(--radius-lg)",
          padding: "16px 20px",
          gridColumn: categories.length === 0 ? "1 / -1" : undefined,
        }}>
          <h2 style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 14px" }}>
            Recent eval runs
          </h2>
          {runs.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)", fontSize: "13px" }}>
              No eval runs yet
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {runs.slice(0,5).map((run: any) => (
                <div key={run.run_id} style={{
                  display: "flex", alignItems: "center", gap: "10px",
                  padding: "8px 10px",
                  background: "var(--bg-overlay)",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--border-subtle)",
                  transition: "border-color var(--transition)",
                  cursor: "pointer",
                }}
                onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)"}
                onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)"}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: "12px", fontWeight: 500,
                                color: "var(--text-primary)", margin: "0 0 2px",
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {run.name || "Unnamed run"}
                    </p>
                    <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: 0 }}>
                      {run.created_at ? new Date(run.created_at).toLocaleDateString("en-GB",{day:"2-digit",month:"short"}) : "—"}
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <div style={{ width: "48px", height: "4px", background: "var(--bg-base)", borderRadius: "2px" }}>
                      <div style={{
                        height: "100%", borderRadius: "2px",
                        width: `${(run.pass_rate||0)*100}%`,
                        background: sc((run.pass_rate||0)*10),
                      }}/>
                    </div>
                    <span style={{ fontSize: "11px", fontWeight: 700,
                                   color: sc((run.pass_rate||0)*10), width: "32px", textAlign: "right" }}>
                      {Math.round((run.pass_rate||0)*100)}%
                    </span>
                  </div>
                  <span style={{
                    padding: "2px 7px", borderRadius: "99px", fontSize: "10px", fontWeight: 600,
                    background: run.status==="completed" ? "var(--green-bg)" :
                                run.status==="running"   ? "var(--blue-bg)"  : "var(--red-bg)",
                    color:      run.status==="completed" ? "var(--green)" :
                                run.status==="running"   ? "var(--blue)"  : "var(--red)",
                  }}>
                    {run.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}