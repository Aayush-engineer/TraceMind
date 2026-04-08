import { useState, useEffect, createContext, useContext, type ReactNode } from "react"

interface Toast {
  id:      string
  message: string
  type:    "success" | "error" | "info"
}

interface ToastContextType {
  show: (message: string, type?: Toast["type"]) => void
}

const ToastContext = createContext<ToastContextType>({ show: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  function show(message: string, type: Toast["type"] = "success") {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 3500)
  }

  const colors = {
    success: { bg: "#052e16", border: "#166534", color: "#4ade80", icon: "✓" },
    error:   { bg: "#450a0a", border: "#991b1b", color: "#f87171", icon: "✕" },
    info:    { bg: "#0c1a4f", border: "#1e3a8a", color: "#93c5fd", icon: "ℹ" },
  }

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <div style={{
        position: "fixed", bottom: "24px", right: "24px",
        display: "flex", flexDirection: "column", gap: "8px",
        zIndex: 9999, pointerEvents: "none"
      }}>
        {toasts.map(toast => {
          const c = colors[toast.type]
          return (
            <div key={toast.id} style={{
              background: c.bg, border: `1px solid ${c.border}`,
              borderRadius: "8px", padding: "10px 14px",
              display: "flex", alignItems: "center", gap: "8px",
              fontSize: "13px", color: c.color,
              animation: "slideIn 0.2s ease",
              minWidth: "240px", maxWidth: "360px"
            }}>
              <span style={{ fontWeight: 700 }}>{c.icon}</span>
              {toast.message}
            </div>
          )
        })}
      </div>
      <style>{`
        @keyframes slideIn {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
      `}</style>
    </ToastContext.Provider>
  )
}