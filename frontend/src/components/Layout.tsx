import type { ReactNode } from "react"
import { useLocation, useNavigate } from "react-router-dom"
import type { AppContext } from "../App";

interface Props {
  children:  ReactNode
  ctx:       AppContext
  onLogout:  () => void
}

const NAV = [
  { path: "/",         label: "Dashboard", icon: "◎" },
  { path: "/traces",   label: "Traces",    icon: "⚡" },
  { path: "/evals",    label: "Evals",     icon: "✓" },
  { path: "/datasets", label: "Datasets",  icon: "◫" },
]

export default function Layout({ children, ctx, onLogout }: Props) {
  const location = useLocation()
  const navigate = useNavigate()

  return (
    <div style={{
      position: "fixed", inset: 0,
      background: "#0f172a",
      fontFamily: "system-ui, sans-serif",
      display: "flex"
    }}>
      {/* Sidebar */}
      <div style={{
        width: "200px", flexShrink: 0,
        background: "#1e293b",
        borderRight: "1px solid #334155",
        display: "flex", flexDirection: "column",
        padding: "0"
      }}>
        {/* Logo */}
        <div style={{
          padding: "18px 16px",
          
          borderBottom: "1px solid #334155",
          display: "flex", alignItems: "center", gap: "8px"
        }}>
          <div style={{
            width: "26px", height: "26px",
            borderRadius: "6px", display: "flex", alignItems: "center",
            background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
            justifyContent: "center", fontSize: "13px",
            fontWeight: 700, color: "white"
          }}>T</div>
          <span style={{ fontWeight: 600, fontSize: "14px", color: "#f1f5f9" }}>
            TraceMind
          </span>
        </div>

        {/* Project info */}
        <div style={{
          padding: "12px 16px",
          borderBottom: "1px solid #1e3a5f"
        }}>
          <p style={{ fontSize: "10px", color: "#475569", margin: "0 0 3px",
                      textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Project
          </p>
          <p style={{ fontSize: "12px", color: "#94a3b8", margin: 0,
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {ctx.projectId.slice(0, 16)}...
          </p>
        </div>

        {/* Nav links */}
        <nav style={{ padding: "8px 8px", flex: 1 }}>
          {NAV.map(item => {
            const active = location.pathname === item.path
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                style={{
                  width: "100%", display: "flex", alignItems: "center",
                  gap: "10px", padding: "9px 10px", borderRadius: "7px",
                  border: "none", cursor: "pointer", marginBottom: "2px",
                  background: active ? "#6366f1" : "transparent",
                  color:      active ? "white"   : "#64748b",
                  fontSize: "13px", fontWeight: active ? 600 : 400,
                  textAlign: "left", transition: "all 0.15s"
                }}
                onMouseEnter={e => {
                  if (!active) (e.target as HTMLElement).style.background = "#334155"
                }}
                onMouseLeave={e => {
                  if (!active) (e.target as HTMLElement).style.background = "transparent"
                }}
              >
                <span style={{ fontSize: "14px" }}>{item.icon}</span>
                {item.label}
              </button>
            )
          })}
        </nav>

        {/* Bottom — logout */}
        <div style={{ padding: "12px 8px", borderTop: "1px solid #334155" }}>
          <button onClick={onLogout} style={{
            width: "100%", padding: "8px 10px", borderRadius: "7px",
            border: "none", background: "transparent",
            color: "#475569", fontSize: "12px",
            cursor: "pointer", textAlign: "left"
          }}>
            ← Switch project
          </button>
        </div>
      </div>

      {/* Page content */}
      <div style={{ flex: 1, overflow: "auto", background: "#0f172a" }}>
        {children}
      </div>
    </div>
  )
}