// components/Layout.tsx
import { useState, useEffect, memo } from "react"
import type { ReactNode } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import type { AppContext } from "../App"

interface Props { children: ReactNode; ctx: AppContext; onLogout: () => void }

const NAV = [
  { path: "/",              label: "Overview",      code: "OVR", icon: "◈", group: "monitor"  },
  { path: "/live",          label: "Live Feed",     code: "LIV", icon: "◉", group: "monitor",  live: true },
  { path: "/traces",        label: "Traces",        code: "TRC", icon: "≋", group: "monitor"  },
  { path: "/evals",         label: "Evals",         code: "EVL", icon: "◆", group: "evaluate" },
  { path: "/playground",    label: "Playground",    code: "PLY", icon: "⬡", group: "evaluate" },
  { path: "/hallucination", label: "Hallucination", code: "HAL", icon: "⊛", group: "evaluate" },
  { path: "/datasets",      label: "Datasets",      code: "DAT", icon: "⊟", group: "data"     },
]

const GROUPS: Record<string, string> = {
  monitor: "Monitor", evaluate: "Evaluate", data: "Data",
}

// Clock — isolated so only it re-renders every second
const Clock = memo(function Clock() {
  const [time, setTime] = useState(() => new Date().toLocaleTimeString("en-US", { hour12: false }))
  useEffect(() => {
    const iv = setInterval(() => setTime(new Date().toLocaleTimeString("en-US", { hour12: false })), 1000)
    return () => clearInterval(iv)
  }, [])
  return (
    <span style={{ fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--t2)", letterSpacing: "0.06em" }}>
      {time}
    </span>
  )
})

// Session timer — isolated
const SessionTimer = memo(function SessionTimer() {
  const [s, setS] = useState(0)
  useEffect(() => {
    const iv = setInterval(() => setS(v => v + 1), 1000)
    return () => clearInterval(iv)
  }, [])
  const h   = Math.floor(s / 3600).toString().padStart(2, "0")
  const m   = Math.floor((s % 3600) / 60).toString().padStart(2, "0")
  const sec = (s % 60).toString().padStart(2, "0")
  return (
    <span style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--p3)", letterSpacing: "0.04em" }}>
      {h}:{m}:{sec}
    </span>
  )
})

// Nav button — memoized, only re-renders when active state changes
const NavBtn = memo(function NavBtn({
  item, active, collapsed, onClick,
}: {
  item: typeof NAV[number]
  active: boolean
  collapsed: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      title={collapsed ? item.label : undefined}
      style={{
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: "9px",
        padding: collapsed ? "9px 0" : "7px 10px",
        borderRadius: "var(--r1)",
        border: active ? "1px solid var(--pb)" : "1px solid transparent",
        cursor: "pointer",
        marginBottom: "2px",
        background: active ? "rgba(0,255,136,0.05)" : "transparent",
        color: active ? "var(--p0)" : "var(--t2)",
        fontFamily: "var(--f-data)",
        fontSize: "12px",
        fontWeight: active ? 500 : 400,
        textAlign: "left",
        transition: "all var(--t-fast)",
        justifyContent: collapsed ? "center" : "flex-start",
        position: "relative",
      }}
      onMouseEnter={e => {
        if (!active) {
          const el = e.currentTarget as HTMLElement
          el.style.background = "var(--hover)"
          el.style.color = "var(--t0)"
        }
      }}
      onMouseLeave={e => {
        if (!active) {
          const el = e.currentTarget as HTMLElement
          el.style.background = "transparent"
          el.style.color = "var(--t2)"
        }
      }}
    >
      {active && !collapsed && (
        <div style={{
          position: "absolute", left: 0, top: "50%", transform: "translateY(-50%)",
          width: "2px", height: "60%", background: "var(--p0)",
          borderRadius: "0 2px 2px 0",
        }}/>
      )}
      <span style={{ fontSize: "13px", flexShrink: 0 }}>{item.icon}</span>
      {!collapsed && (
        <>
          <span style={{ flex: 1, fontSize: "12px" }}>{item.label}</span>
          <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: active ? "var(--p3)" : "var(--t4)", letterSpacing: "0.08em" }}>
            {item.code}
          </span>
          {item.live && <span className="live-dot" style={{ width: "5px", height: "5px" }}/>}
        </>
      )}
    </button>
  )
})

export default function Layout({ children, ctx, onLogout }: Props) {
  const location = useLocation()
  const navigate  = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const currentPage = NAV.find(n => n.path === location.pathname)

  const grouped = Object.entries(GROUPS).map(([key, label]) => ({
    key, label,
    items: NAV.filter(n => n.group === key),
  }))

  return (
    <div style={{ position: "fixed", inset: 0, display: "flex", background: "var(--void)", fontFamily: "var(--f-data)" }}>

      {/* Sidebar */}
      <aside style={{
        width: collapsed ? "56px" : "210px",
        flexShrink: 0,
        background: "var(--base)",
        borderRight: "1px solid var(--b1)",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.22s var(--ease)",
        overflow: "hidden",
        position: "relative",
        zIndex: 20,
      }}>
        {/* Vertical accent line */}
        <div style={{ position: "absolute", top: 0, bottom: 0, right: 0, width: "1px", background: "linear-gradient(180deg, transparent 0%, var(--p3) 30%, var(--c0) 70%, transparent 100%)", opacity: 0.2, pointerEvents: "none" }}/>

        {/* Logo */}
        <div style={{
          padding: collapsed ? "14px 0" : "14px 16px",
          borderBottom: "1px solid var(--b1)",
          display: "flex", alignItems: "center", gap: "10px",
          minHeight: "56px", justifyContent: collapsed ? "center" : "flex-start",
          flexShrink: 0,
        }}>
          {/* Bar-chart logo mark */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", flexShrink: 0, height: "20px" }}>
            <div style={{ width: "5px", height: "10px", borderRadius: "1px 1px 0 0", background: "var(--p0)", opacity: 0.45 }}/>
            <div style={{ width: "5px", height: "20px", borderRadius: "1px 1px 0 0", background: "var(--p0)" }}/>
            <div style={{ width: "5px", height: "14px", borderRadius: "1px 1px 0 0", background: "var(--p0)", opacity: 0.7 }}/>
          </div>
          {!collapsed && (
            <div style={{ overflow: "hidden" }}>
              <p style={{ fontFamily: "var(--f-display)", fontSize: "15px", fontWeight: 800, color: "var(--t0)", margin: 0, letterSpacing: "-0.02em", whiteSpace: "nowrap" }}>
                TraceMind
              </p>
              <p style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--p3)", margin: 0, letterSpacing: "0.2em", textTransform: "uppercase" }}>
                OBSERVATORY
              </p>
            </div>
          )}
        </div>

        {/* Status strip */}
        {!collapsed && (
          <div style={{ padding: "7px 14px", borderBottom: "1px solid var(--b1)", display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(0,255,136,0.02)", flexShrink: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span className="live-dot" style={{ width: "5px", height: "5px" }}/>
              <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--p2)", letterSpacing: "0.12em" }}>ONLINE</span>
            </div>
            <Clock/>
          </div>
        )}

        {/* Nav */}
        <nav style={{ flex: 1, padding: "8px", overflowY: "auto", overflowX: "hidden" }}>
          {grouped.map((group, gi) => (
            <div key={group.key} style={{ marginBottom: "4px" }}>
              {!collapsed ? (
                <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "8px 6px 4px" }}>
                  <div style={{ flex: 1, height: "1px", background: "var(--b1)" }}/>
                  <span style={{ fontFamily: "var(--f-mono)", fontSize: "7px", fontWeight: 700, color: "var(--t4)", letterSpacing: "0.2em", textTransform: "uppercase", whiteSpace: "nowrap" }}>
                    {group.label}
                  </span>
                  <div style={{ flex: 1, height: "1px", background: "var(--b1)" }}/>
                </div>
              ) : (gi > 0 && <div style={{ height: "1px", background: "var(--b1)", margin: "6px 4px" }}/>)}

              {group.items.map(item => (
                <NavBtn
                  key={item.path}
                  item={item}
                  active={location.pathname === item.path}
                  collapsed={collapsed}
                  onClick={() => navigate(item.path)}
                />
              ))}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div style={{ borderTop: "1px solid var(--b1)", padding: "8px", display: "flex", flexDirection: "column", gap: "6px", flexShrink: 0 }}>
          {!collapsed && (
            <div
              onClick={() => navigator.clipboard.writeText(ctx.projectId)}
              title="Copy project ID"
              style={{ padding: "8px 10px", background: "var(--raised)", border: "1px solid var(--b1)", borderRadius: "var(--r1)", cursor: "pointer" }}
              onMouseEnter={e => (e.currentTarget as HTMLElement).style.borderColor = "var(--b2)"}
              onMouseLeave={e => (e.currentTarget as HTMLElement).style.borderColor = "var(--b1)"}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                <span style={{ fontFamily: "var(--f-mono)", fontSize: "7px", color: "var(--t3)", textTransform: "uppercase", letterSpacing: "0.14em" }}>Session</span>
                <SessionTimer/>
              </div>
              <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                ⌗ {ctx.projectId.slice(0, 20)}…
              </p>
            </div>
          )}
          <button onClick={() => setCollapsed(!collapsed)} className="btn btn-ghost" style={{ padding: "6px", fontSize: "10px", width: "100%", justifyContent: "center" }}>
            {collapsed ? "→" : "← collapse"}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflow: "auto", background: "var(--base)", display: "flex", flexDirection: "column", position: "relative" }}>
        {/* Top bar */}
        <header style={{
          height: "50px",
          borderBottom: "1px solid var(--b1)",
          background: "rgba(3,6,13,0.9)",
          backdropFilter: "blur(10px)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "0 20px",
          flexShrink: 0,
          position: "sticky", top: 0, zIndex: 10,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.1em" }}>TRACEMIND</span>
            <span style={{ color: "var(--t4)", fontFamily: "var(--f-mono)" }}>/</span>
            <span style={{ fontFamily: "var(--f-mono)", fontSize: "10px", color: "var(--p2)", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase" }}>
              {currentPage?.code ?? "OVR"}
            </span>
            <span style={{ color: "var(--t4)", fontFamily: "var(--f-mono)" }}>·</span>
            <span style={{ fontFamily: "var(--f-data)", fontSize: "12px", color: "var(--t1)" }}>
              {currentPage?.label ?? "Overview"}
            </span>
            {currentPage?.live && <span className="sig sig-p" style={{ marginLeft: "4px" }}>live</span>}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", padding: "5px 12px", background: "var(--raised)", border: "1px solid var(--b1)", borderRadius: "var(--r1)" }}>
              {["SYS","NET","API"].map(l => (
                <div key={l} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <div style={{ width: "4px", height: "4px", borderRadius: "50%", background: "var(--p0)", boxShadow: "0 0 4px var(--p0)" }}/>
                  <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)", letterSpacing: "0.1em" }}>{l}</span>
                </div>
              ))}
            </div>
            <button onClick={onLogout} className="btn btn-ghost" style={{ padding: "5px 12px", fontSize: "9px" }}>
              SWITCH PROJECT
            </button>
          </div>
        </header>

        {/* Page */}
        <div style={{ flex: 1, overflow: "auto", animation: "fadeUp 0.28s var(--ease) forwards" }}>
          {children}
        </div>
      </main>
    </div>
  )
}