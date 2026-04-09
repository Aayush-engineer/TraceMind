import { useState } from "react"
import type { ReactNode} from "react"
import { useLocation, useNavigate } from "react-router-dom"
import type { AppContext } from "../App"

interface Props {
  children:  ReactNode
  ctx:       AppContext
  onLogout:  () => void
}

const NAV = [
  { path: "/",              label: "Overview",     icon: "○",  group: "main" },
  { path: "/live",          label: "Live",         icon: "◉",  group: "main", badge: "live" },
  { path: "/traces",        label: "Traces",       icon: "≡",  group: "main" },
  { path: "/evals",         label: "Evals",        icon: "✦",  group: "eval" },
  { path: "/playground",    label: "Playground",   icon: "⬡",  group: "eval" },
  { path: "/hallucination", label: "Hallucination",icon: "⊕",  group: "eval" },
  { path: "/datasets",      label: "Datasets",     icon: "⊞",  group: "data" },
]

const GROUPS = {
  main: "Monitor",
  eval: "Evaluate",
  data: "Data",
}

export default function Layout({ children, ctx, onLogout }: Props) {
  const location = useLocation()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(false)

  const grouped = Object.entries(GROUPS).map(([key, label]) => ({
    label,
    items: NAV.filter(n => n.group === key)
  }))

  return (
    <div style={{
      position: "fixed", inset: 0,
      display: "flex",
      background: "var(--bg-base)",
      fontFamily: "var(--font-sans)"
    }}>
      {/* Sidebar */}
      <aside style={{
        width: collapsed ? "56px" : "220px",
        flexShrink: 0,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border-subtle)",
        display: "flex",
        flexDirection: "column",
        transition: "width 0.2s ease",
        overflow: "hidden",
        zIndex: 10,
      }}>

        {/* Logo */}
        <div style={{
          padding: collapsed ? "16px 12px" : "16px 20px",
          borderBottom: "1px solid var(--border-subtle)",
          display: "flex",
          alignItems: "center",
          gap: "10px",
          minHeight: "56px",
        }}>
          {/* TraceMind Logo */}
          <div style={{
            width: "28px", height: "28px",
            background: "linear-gradient(135deg, #7c3aed 0%, #a855f7 50%, #06b6d4 100%)",
            borderRadius: "8px",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
            boxShadow: "0 2px 8px rgba(124,58,237,0.4)",
            position: "relative",
            overflow: "hidden",
          }}>
            {/* Logo mark — T with pulse */}
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M2 4h12M8 4v8" stroke="white" strokeWidth="2" strokeLinecap="round"/>
              <circle cx="8" cy="12" r="1.5" fill="white"/>
            </svg>
          </div>

          {!collapsed && (
            <div style={{ overflow: "hidden" }}>
              <p style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)", margin: 0, letterSpacing: "-0.3px" }}>
                TraceMind
              </p>
              <p style={{ fontSize: "10px", color: "var(--text-muted)", margin: 0 }}>
                AI Observability
              </p>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: "8px", overflowY: "auto", overflowX: "hidden" }}>
          {grouped.map(group => (
            <div key={group.label} style={{ marginBottom: "4px" }}>
              {!collapsed && (
                <p style={{
                  fontSize: "10px", fontWeight: 600,
                  color: "var(--text-muted)",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  padding: "8px 10px 4px",
                  margin: 0,
                }}>
                  {group.label}
                </p>
              )}
              {group.items.map(item => {
                const active = location.pathname === item.path
                return (
                  <button
                    key={item.path}
                    onClick={() => navigate(item.path)}
                    title={collapsed ? item.label : undefined}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: collapsed ? "9px 12px" : "8px 10px",
                      borderRadius: "var(--radius-md)",
                      border: "none",
                      cursor: "pointer",
                      marginBottom: "2px",
                      background: active
                        ? "linear-gradient(135deg, rgba(124,58,237,0.2) 0%, rgba(168,85,247,0.1) 100%)"
                        : "transparent",
                      color: active ? "var(--accent-light)" : "var(--text-secondary)",
                      fontSize: "13px",
                      fontWeight: active ? 500 : 400,
                      textAlign: "left",
                      transition: "all var(--transition)",
                      position: "relative",
                      boxShadow: active ? "inset 0 0 0 1px var(--accent-border)" : "none",
                      justifyContent: collapsed ? "center" : "flex-start",
                    }}
                    onMouseEnter={e => {
                      if (!active) {
                        (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"
                        ;(e.currentTarget as HTMLElement).style.color = "var(--text-primary)"
                      }
                    }}
                    onMouseLeave={e => {
                      if (!active) {
                        (e.currentTarget as HTMLElement).style.background = "transparent"
                        ;(e.currentTarget as HTMLElement).style.color = "var(--text-secondary)"
                      }
                    }}
                  >
                    <span style={{ fontSize: "14px", flexShrink: 0 }}>{item.icon}</span>
                    {!collapsed && (
                      <>
                        <span style={{ flex: 1 }}>{item.label}</span>
                        {item.badge === "live" && (
                          <span style={{
                            fontSize: "9px", fontWeight: 700,
                            padding: "1px 5px", borderRadius: "99px",
                            background: "rgba(63,185,80,0.15)",
                            color: "var(--green)",
                            border: "1px solid rgba(63,185,80,0.3)",
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                          }}>
                            live
                          </span>
                        )}
                      </>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </nav>

        {/* Bottom */}
        <div style={{
          padding: "8px",
          borderTop: "1px solid var(--border-subtle)",
        }}>
          {/* Project badge */}
          {!collapsed && (
            <div style={{
              padding: "8px 10px",
              background: "var(--bg-overlay)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--border-subtle)",
              marginBottom: "6px",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "2px" }}>
                <div style={{
                  width: "6px", height: "6px", borderRadius: "50%",
                  background: "var(--green)",
                  flexShrink: 0,
                }}/>
                <span style={{ fontSize: "10px", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                  Project
                </span>
              </div>
              <p
                onClick={() => { navigator.clipboard.writeText(ctx.projectId); }}
                title="Click to copy project ID"
                style={{
                  fontSize: "11px", color: "var(--text-secondary)",
                  margin: 0, cursor: "pointer",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  fontFamily: "var(--font-mono)",
                }}
              >
                {ctx.projectId.slice(0, 18)}...
              </p>
            </div>
          )}

          {/* Collapse toggle */}
          <button
            onClick={() => setCollapsed(!collapsed)}
            style={{
              width: "100%", padding: "7px",
              background: "transparent",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              color: "var(--text-muted)",
              cursor: "pointer",
              fontSize: "12px",
              transition: "all var(--transition)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
            }}
          >
            {collapsed ? "→" : "← Collapse"}
          </button>
        </div>
      </aside>

      {/* Main */}
      <main style={{
        flex: 1,
        overflow: "auto",
        background: "var(--bg-base)",
        display: "flex",
        flexDirection: "column",
      }}>
        {/* Top bar */}
        <header style={{
          height: "52px",
          borderBottom: "1px solid var(--border-subtle)",
          background: "var(--bg-surface)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 20px",
          flexShrink: 0,
          position: "sticky",
          top: 0,
          zIndex: 9,
        }}>
          {/* Breadcrumb */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>TraceMind</span>
            <span style={{ color: "var(--text-muted)" }}>/</span>
            <span style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 500 }}>
              {NAV.find(n => n.path === location.pathname)?.label || "Dashboard"}
            </span>
          </div>

          {/* Actions */}
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <button
              onClick={onLogout}
              style={{
                padding: "5px 12px",
                background: "transparent",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                color: "var(--text-muted)",
                fontSize: "12px",
                cursor: "pointer",
                transition: "all var(--transition)",
              }}
            >
              Switch project
            </button>
          </div>
        </header>

        {/* Page content */}
        <div style={{ flex: 1, overflow: "auto" }}>
          {children}
        </div>
      </main>
    </div>
  )
}