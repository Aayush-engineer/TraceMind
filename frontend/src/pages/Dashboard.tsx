import { useEffect, useState, useCallback } from "react"
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine
} from "recharts"

interface Props {
  projectId: string
  apiKey:    string
  apiUrl:    string
}

interface Stats {
  avg_score:   number
  pass_rate:   number
  total_calls: number
  cost:        number
}

interface MetricPoint {
  hour:       string
  avg_score:  number
  pass_rate:  number
  call_count: number
}

interface Alert {
  id:         string
  type:       string
  severity:   "low" | "medium" | "high" | "critical"
  message:    string
  created_at: string
}

interface EvalRun {
  run_id:     string
  name:       string
  pass_rate:  number
  avg_score:  number
  status:     string
  created_at: string
}

export default function Dashboard({ projectId, apiKey, apiUrl }: Props) {
  const [stats, setStats] = useState<Stats>({ avg_score: 0, pass_rate: 0, total_calls: 0, cost: 0 })
  const [metrics, setMetrics] = useState<MetricPoint[]>([])
  const [alerts,  setAlerts]  = useState<Alert[]>([])
  const [runs,    setRuns]    = useState<EvalRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState("")
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [categories, setCategories] = useState<{name: string, pass_rate: number, count: number}[]>([])

  const headers = {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type":  "application/json"
  }

  const fetchAll = useCallback(async () => {
    try {
      const [statsRes, metricsRes, alertsRes, runsRes] = await Promise.all([
        fetch(`${apiUrl}/api/metrics/${projectId}/summary`,      { headers }),
        fetch(`${apiUrl}/api/metrics/${projectId}?hours=24`,     { headers }),
        fetch(`${apiUrl}/api/alerts/${projectId}?resolved=false`,{ headers }),
        fetch(`${apiUrl}/api/metrics/${projectId}/evals`,        { headers }),
      ])

      if (!statsRes.ok) {
        setError("Failed to load — check your project ID and API key")
        return
      }

      const [s, m, a, r] = await Promise.all([
        statsRes.json(), metricsRes.json(),
        alertsRes.json(), runsRes.json()
      ])

      setStats({
        avg_score:   Number(s.avg_score   || 0),
        pass_rate:   Number(s.pass_rate   || 0),
        total_calls: Number(s.total_calls || 0),
        cost:        Number(s.cost        || 0),
      })

      if (r.runs && r.runs.length > 0) {
        // fetch latest eval run results for category breakdown
        try {
            const latestRun = r.runs[0]
            const evalRes = await fetch(
            `${apiUrl}/api/evals/${latestRun.run_id}`,
            { headers }
            )
            const evalData = await evalRes.json()
            if (evalData.results) {
            const catMap: Record<string, {passed: number, total: number}> = {}
            evalData.results.forEach((result: any) => {
                const cat = result.category || "general"
                if (!catMap[cat]) catMap[cat] = { passed: 0, total: 0 }
                catMap[cat].total++
                if (result.passed) catMap[cat].passed++
            })
            setCategories(Object.entries(catMap).map(([name, stats]) => ({
                name,
                pass_rate: stats.total > 0 ? stats.passed / stats.total : 0,
                count: stats.total
            })))
            }
        } catch { /* ignore */ }
      }

      setMetrics(m.points || [])
      setAlerts(a.alerts  || [])
      setRuns(r.runs      || [])
      setError("")
      setLastUpdated(new Date())
    } catch {
      setError("Cannot connect to server — is it running on port 8000?")
    } finally {
      setLoading(false)
    }
  }, [projectId, apiKey, apiUrl])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 30000)
    return () => clearInterval(interval)
  }, [fetchAll])

  useEffect(() => {
    let ws: WebSocket | null = null
    const timer = setTimeout(() => {
        try {
        ws = new WebSocket(`ws://localhost:8000/ws/${projectId}`)
        ws.onmessage = (e) => {
            try {
            const data = JSON.parse(e.data)
            if (data.type === "metrics_update") setStats({
                avg_score:   Number(data.stats?.avg_score   || 0),
                pass_rate:   Number(data.stats?.pass_rate   || 0),
                total_calls: Number(data.stats?.total_calls || 0),
                cost:        Number(data.stats?.cost        || 0),
            })
            if (data.type === "new_alert") {
                setAlerts(prev => [data.alert, ...prev].slice(0, 10))
            }
            } catch { /* ignore parse errors */ }
        }
        ws.onerror = () => { /* WebSocket optional — ignore errors */ }
        } catch { /* WebSocket not available */ }
    }, 1000)  // wait 1 second before connecting

    return () => {
        clearTimeout(timer)
        ws?.close()
    }
  }, [projectId])

  function logout() {
    localStorage.removeItem("ef_api_key")
    localStorage.removeItem("ef_project_id")
    window.location.reload()
  }

  const scoreColor = (s: number) =>
    s >= 8 ? "#10b981" : s >= 6 ? "#f59e0b" : "#ef4444"

  const scoreBg = (s: number) =>
    s >= 8 ? "#ecfdf5" : s >= 6 ? "#fffbeb" : "#fef2f2"

  const SEVERITY: Record<string, { bg: string; color: string; dot: string }> = {
    low:      { bg: "#eff6ff", color: "#1d4ed8", dot: "#3b82f6" },
    medium:   { bg: "#fffbeb", color: "#92400e", dot: "#f59e0b" },
    high:     { bg: "#fff7ed", color: "#9a3412", dot: "#f97316" },
    critical: { bg: "#fef2f2", color: "#991b1b", dot: "#ef4444" },
  }

  if (loading) return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#0f172a",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexDirection: "column", gap: "16px"
    }}>
      <div style={{
        width: "40px", height: "40px", border: "3px solid #334155",
        borderTop: "3px solid #6366f1", borderRadius: "50%",
        animation: "spin 1s linear infinite"
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
      <p style={{ color: "#64748b", fontSize: "14px", margin: 0 }}>Loading TraceMind...</p>
    </div>
  )

  const chartData = metrics.filter(m => m.call_count > 0)

  return (
    <div style={{
        padding: "20px 24px",
        color: "#e2e8f0",
        minHeight: "100%"
    }}>

      <div style={{ marginBottom: "20px" }}>
            <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
                Dashboard
            </h1>
            <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
                {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Loading..."}
                <button onClick={fetchAll} style={{
                marginLeft: "12px", background: "transparent",
                border: "none", color: "#6366f1", fontSize: "13px",
                cursor: "pointer", fontWeight: 500
                }}>↻ Refresh</button>
            </p>
      </div>
    
      {/* Main content — scrollable */}
      <div style={{ flex: 1, overflow: "auto", padding: "20px 24px" }}>

        {error && (
          <div style={{
            background: "#450a0a", border: "1px solid #7f1d1d",
            borderRadius: "8px", padding: "12px 16px",
            color: "#fca5a5", fontSize: "13px", marginBottom: "20px"
          }}>
            ⚠ {error}
          </div>
        )}

        {/* Stat cards */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "12px", marginBottom: "20px"
        }}>
          {[
            {
              label: "Avg quality score",
              value: stats.avg_score.toFixed(2),
              unit: "/ 10",
              color: scoreColor(stats.avg_score),
              bg: scoreBg(stats.avg_score),
              icon: "◎",
              sub: stats.avg_score >= 7 ? "Above threshold" : "Below threshold"
            },
            {
              label: "Pass rate",
              value: (stats.pass_rate * 100).toFixed(1),
              unit: "%",
              color: scoreColor(stats.pass_rate * 10),
              bg: scoreBg(stats.pass_rate * 10),
              icon: "✓",
              sub: `${Math.round(stats.pass_rate * stats.total_calls)} of ${stats.total_calls} passed`
            },
            {
              label: "Total LLM calls",
              value: stats.total_calls.toLocaleString(),
              unit: "",
              color: "#6366f1",
              bg: "#eef2ff",
              icon: "⚡",
              sub: "Last 24 hours"
            },
            {
              label: "Cost (24h)",
              value: `$${stats.cost.toFixed(4)}`,
              unit: "",
              color: "#0ea5e9",
              bg: "#f0f9ff",
              icon: "$",
              sub: "Groq free tier"
            },
          ].map(card => (
            <div key={card.label} style={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "10px",
              padding: "16px 18px",
              position: "relative",
              overflow: "hidden"
            }}>
              <div style={{
                position: "absolute", top: "14px", right: "14px",
                width: "32px", height: "32px",
                background: card.bg,
                borderRadius: "8px",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: "14px", color: card.color
              }}>
                {card.icon}
              </div>
              <p style={{
                fontSize: "11px", color: "#64748b", fontWeight: 500,
                textTransform: "uppercase", letterSpacing: "0.06em",
                margin: "0 0 8px"
              }}>
                {card.label}
              </p>
              <p style={{ fontSize: "26px", fontWeight: 700, color: card.color, margin: "0 0 4px" }}>
                {card.value}
                <span style={{ fontSize: "13px", color: "#64748b",
                               fontWeight: 400, marginLeft: "4px" }}>
                  {card.unit}
                </span>
              </p>
              <p style={{ fontSize: "11px", color: "#475569", margin: 0 }}>
                {card.sub}
              </p>
            </div>
          ))}
        </div>

        {/* Chart + Alerts row */}
        <div style={{
          display: "grid", gridTemplateColumns: "1fr 340px",
          gap: "12px", marginBottom: "20px"
        }}>

          {/* Chart */}
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", padding: "18px 20px"
          }}>
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: "16px"
            }}>
              <div>
                <h2 style={{ fontSize: "14px", fontWeight: 600,
                             color: "#f1f5f9", margin: "0 0 2px" }}>
                  Quality score over time
                </h2>
                <p style={{ fontSize: "12px", color: "#64748b", margin: 0 }}>
                  Last 24 hours — hourly average
                </p>
              </div>
              <div style={{
                display: "flex", alignItems: "center", gap: "6px",
                fontSize: "11px", color: "#64748b"
              }}>
                <div style={{ width: "24px", height: "2px", background: "#6366f1" }} />
                Avg score
                <div style={{ width: "24px", height: "2px",
                              background: "#ef4444", borderTop: "2px dashed #ef4444" }} />
                Threshold (7)
              </div>
            </div>

            {chartData.length === 0 ? (
              <div style={{
                height: "200px", display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                color: "#475569", fontSize: "13px", gap: "8px"
              }}>
                <span style={{ fontSize: "32px" }}>📊</span>
                <span>Ingest spans across multiple hours to see the trend</span>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={metrics} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e3a5f" vertical={false} />
                  <XAxis
                    dataKey="hour"
                    tick={{ fontSize: 10, fill: "#475569" }}
                    axisLine={false} tickLine={false}
                  />
                  <YAxis
                    domain={[0, 10]}
                    tick={{ fontSize: 10, fill: "#475569" }}
                    axisLine={false} tickLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: "#0f172a", border: "1px solid #334155",
                      borderRadius: "8px", fontSize: "12px"
                    }}
                    labelStyle={{ color: "#94a3b8" }}
                    itemStyle={{ color: "#6366f1" }}
                    formatter={(v: number) => [v.toFixed(2), "Avg score"]}
                  />
                  <ReferenceLine
                    y={7} stroke="#ef4444" strokeDasharray="4 4" strokeWidth={1}
                  />
                  <Line
                    type="monotone" dataKey="avg_score"
                    stroke="#6366f1" strokeWidth={2.5}
                    dot={{ fill: "#6366f1", r: 3, strokeWidth: 0 }}
                    activeDot={{ r: 5, fill: "#818cf8" }}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Alerts */}
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", padding: "18px 20px",
            display: "flex", flexDirection: "column"
          }}>
            <div style={{
              display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: "16px"
            }}>
              <h2 style={{ fontSize: "14px", fontWeight: 600,
                           color: "#f1f5f9", margin: 0 }}>
                Active alerts
              </h2>
              {alerts.length > 0 && (
                <span style={{
                  background: "#450a0a", color: "#f87171",
                  fontSize: "11px", padding: "2px 8px",
                  borderRadius: "99px", fontWeight: 600
                }}>
                  {alerts.length}
                </span>
              )}
            </div>

            {alerts.length === 0 ? (
              <div style={{
                flex: 1, display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                color: "#475569", fontSize: "13px", gap: "8px"
              }}>
                <div style={{
                  width: "40px", height: "40px",
                  background: "#0f2a1f", borderRadius: "50%",
                  display: "flex", alignItems: "center",
                  justifyContent: "center", fontSize: "18px"
                }}>✓</div>
                <span style={{ color: "#10b981" }}>All metrics healthy</span>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {alerts.slice(0, 5).map(alert => {
                  const s = SEVERITY[alert.severity] || SEVERITY.medium
                  return (
                    <div key={alert.id} style={{
                      background: "#0f172a",
                      border: `1px solid #334155`,
                      borderLeft: `3px solid ${s.dot}`,
                      borderRadius: "6px", padding: "10px 12px"
                    }}>
                      <div style={{
                        display: "flex", alignItems: "center",
                        gap: "6px", marginBottom: "3px"
                      }}>
                        <div style={{
                          width: "6px", height: "6px",
                          borderRadius: "50%", background: s.dot
                        }} />
                        <span style={{
                          fontSize: "11px", fontWeight: 600,
                          color: s.color, textTransform: "uppercase",
                          letterSpacing: "0.05em"
                        }}>
                          {alert.severity}
                        </span>
                      </div>
                      <p style={{ fontSize: "12px", color: "#94a3b8",
                                  margin: 0, lineHeight: 1.4 }}>
                        {alert.message}
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {categories.length > 0 && (
            <div style={{
                background: "#1e293b", border: "1px solid #334155",
                borderRadius: "10px", padding: "18px 20px", marginBottom: "20px"
            }}>
                <h2 style={{ fontSize: "14px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
                Pass rate by category
                </h2>
                <p style={{ fontSize: "12px", color: "#64748b", margin: "0 0 16px" }}>
                From latest eval run — shows where your AI struggles most
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {categories.sort((a,b) => a.pass_rate - b.pass_rate).map(cat => (
                    <div key={cat.name} style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <span style={{
                        width: "80px", fontSize: "12px", color: "#94a3b8",
                        textTransform: "capitalize", textAlign: "right", flexShrink: 0
                    }}>
                        {cat.name}
                    </span>
                    <div style={{
                        flex: 1, height: "8px", background: "#0f172a",
                        borderRadius: "4px", overflow: "hidden"
                    }}>
                        <div style={{
                        height: "100%", borderRadius: "4px",
                        width: `${cat.pass_rate * 100}%`,
                        background: cat.pass_rate >= 0.8 ? "#10b981" :
                                    cat.pass_rate >= 0.6 ? "#f59e0b" : "#ef4444",
                        transition: "width 0.6s ease"
                        }} />
                    </div>
                    <span style={{
                        width: "40px", fontSize: "12px", fontWeight: 600,
                        color: cat.pass_rate >= 0.8 ? "#10b981" :
                            cat.pass_rate >= 0.6 ? "#f59e0b" : "#ef4444"
                    }}>
                        {(cat.pass_rate * 100).toFixed(0)}%
                    </span>
                    <span style={{ fontSize: "11px", color: "#475569", width: "50px" }}>
                        {cat.count} cases
                    </span>
                    </div>
                ))}
                </div>
            </div>
        )}

        {/* Eval runs table */}
        <div style={{
          background: "#1e293b", border: "1px solid #334155",
          borderRadius: "10px", padding: "18px 20px"
        }}>
          <div style={{
            display: "flex", alignItems: "center",
            justifyContent: "space-between", marginBottom: "16px"
          }}>
            <div>
              <h2 style={{ fontSize: "14px", fontWeight: 600,
                           color: "#f1f5f9", margin: "0 0 2px" }}>
                Eval runs
              </h2>
              <p style={{ fontSize: "12px", color: "#64748b", margin: 0 }}>
                Golden dataset evaluation history
              </p>
            </div>
          </div>

          {runs.length === 0 ? (
            <div style={{
              textAlign: "center", padding: "2rem",
              color: "#475569", fontSize: "13px"
            }}>
              No eval runs yet
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
              <thead>
                <tr>
                  {["Name", "Pass rate", "Avg score", "Status", "Date"].map(h => (
                    <th key={h} style={{
                      textAlign: "left",
                      padding: "0 16px 10px 0",
                      fontSize: "11px", color: "#475569",
                      fontWeight: 600, textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      borderBottom: "1px solid #334155"
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((run, i) => (
                  <tr key={run.run_id} style={{
                    borderBottom: i < runs.length - 1 ? "1px solid #1e3a5f" : "none"
                  }}>
                    <td style={{ padding: "12px 16px 12px 0",
                                 color: "#e2e8f0", fontWeight: 500 }}>
                      {run.name || "Unnamed run"}
                    </td>
                    <td style={{ padding: "12px 16px 12px 0" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <div style={{
                          width: "80px", height: "5px",
                          background: "#0f172a", borderRadius: "3px",
                          overflow: "hidden"
                        }}>
                          <div style={{
                            height: "100%", borderRadius: "3px",
                            width: `${(run.pass_rate || 0) * 100}%`,
                            background: scoreColor((run.pass_rate || 0) * 10),
                            transition: "width 0.5s ease"
                          }} />
                        </div>
                        <span style={{ color: scoreColor((run.pass_rate || 0) * 10),
                                       fontWeight: 600, fontSize: "12px" }}>
                          {((run.pass_rate || 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px 12px 0",
                                 color: scoreColor(run.avg_score || 0),
                                 fontWeight: 600 }}>
                      {(run.avg_score || 0).toFixed(2)}
                      <span style={{ color: "#475569", fontWeight: 400 }}>/10</span>
                    </td>
                    <td style={{ padding: "12px 16px 12px 0" }}>
                      <span style={{
                        padding: "3px 10px", borderRadius: "99px",
                        fontSize: "11px", fontWeight: 600,
                        background:
                          run.status === "completed" ? "#052e16" :
                          run.status === "running"   ? "#0c1a4f" :
                          run.status === "failed"    ? "#450a0a" : "#1e293b",
                        color:
                          run.status === "completed" ? "#4ade80" :
                          run.status === "running"   ? "#818cf8" :
                          run.status === "failed"    ? "#f87171" : "#94a3b8"
                      }}>
                        {run.status === "running" ? "⟳ " : ""}
                        {run.status}
                      </span>
                    </td>
                    <td style={{ padding: "12px 0",
                                 color: "#475569", fontSize: "12px" }}>
                      {run.created_at
                        ? new Date(run.created_at).toLocaleDateString("en-GB", {
                            day: "2-digit", month: "short", year: "numeric"
                          })
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div style={{
          textAlign: "center", padding: "20px 0 8px",
          fontSize: "11px", color: "#334155"
        }}>
          TraceMind — open source LLM observability
        </div>
      </div>
    </div>
  )
}