// components/Toast.tsx
import { useState, useCallback, createContext, useContext, useMemo, type ReactNode } from "react"

interface Toast { id: string; message: string; type: "success"|"error"|"info" }
interface ToastCtx { show: (msg: string, type?: Toast["type"]) => void }

const Ctx = createContext<ToastCtx>({ show: () => {} })
export const useToast = () => useContext(Ctx)

const CFG = {
  success: { color: "var(--p0)", border: "var(--pb)", icon: "✓" },
  error:   { color: "var(--r0)", border: "var(--rb)", icon: "✕" },
  info:    { color: "var(--c0)", border: "var(--cb)", icon: "ℹ" },
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  // Stable reference — won't cause consumer re-renders
  const show = useCallback((message: string, type: Toast["type"] = "success") => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts(p => [...p, { id, message, type }])
    setTimeout(() => setToasts(p => p.filter(t => t.id !== id)), 3500)
  }, [])

  const value = useMemo(() => ({ show }), [show])

  return (
    <Ctx.Provider value={value}>
      {children}
      <div style={{
        position: "fixed", bottom: 20, right: 20,
        display: "flex", flexDirection: "column", gap: 6,
        zIndex: 9999, pointerEvents: "none",
      }}>
        {toasts.map(t => {
          const c = CFG[t.type]
          return (
            <div key={t.id} style={{
              background: "var(--raised)",
              border: `1px solid ${c.border}`,
              borderLeft: `2px solid ${c.color}`,
              borderRadius: "var(--r1)",
              padding: "9px 14px",
              display: "flex", alignItems: "center", gap: 8,
              fontFamily: "var(--f-mono)",
              fontSize: 10, color: "var(--t0)",
              letterSpacing: "0.04em",
              animation: "fadeUp 0.2s var(--ease) forwards",
              minWidth: 200, maxWidth: 320,
              boxShadow: "0 4px 20px rgba(0,0,0,0.6)",
            }}>
              <span style={{ fontWeight: 700, color: c.color }}>{c.icon}</span>
              {t.message}
            </div>
          )
        })}
      </div>
    </Ctx.Provider>
  )
}