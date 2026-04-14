import { useState, useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Dashboard from "./pages/Dashboard"
import Traces    from "./pages/Traces"
import Evals     from "./pages/Evals"
import Datasets  from "./pages/Datasets"
import Layout    from "./components/Layout"
import { ToastProvider } from "./components/Toast"
import ErrorBoundary from "./components/ErrorBoundary"
import Live          from "./pages/Live"
import Playground    from "./pages/Playground"
import Hallucination from "./pages/Hallucination"

// const API_URL = import.meta.env.VITE_API_URL;

const API_URL = 'http://localhost:8000';



console.log("API URL:", import.meta.env.VITE_API_URL);

if (!API_URL) {
  throw new Error("VITE_API_URL is not defined");
}

export interface AppContext {
  projectId: string
  apiKey:    string
  apiUrl:    string
}

function Login({ onLogin }: { onLogin: (pid: string, key: string) => void }) {
  const [projectId, setProjectId] = useState("")
  const [apiKey,    setApiKey]    = useState("")
  const [error, setError] = useState<string>("")

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!projectId.trim() || !apiKey.trim()) {
    setError("Both Project ID and API Key are required")
      return
    }
    
    if (!apiKey.startsWith("ef_live_")) {
      setError("API key should start with ef_live_")
      return
    }

    setError("")
    localStorage.setItem("ef_api_key",    apiKey)
    localStorage.setItem("ef_project_id", projectId)
    onLogin(projectId, apiKey)
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: "#060910",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: "'Inter', system-ui, sans-serif",
      padding: "20px",
    }}>
      <div style={{
        width: "100%",
        maxWidth: "380px",
      }}>
        {/* Logo */}
        <div style={{ textAlign: "center", marginBottom: "32px" }}>
          <div style={{
            width: "48px", height: "48px",
            background: "linear-gradient(135deg, #7c3aed 0%, #a855f7 60%, #06b6d4 100%)",
            borderRadius: "12px",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "12px",
            boxShadow: "0 4px 20px rgba(124,58,237,0.4)",
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path d="M3 6h18M12 6v12" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="12" cy="18" r="2" fill="white"/>
            </svg>
          </div>
          <h1 style={{
            fontSize: "22px", fontWeight: 700,
            color: "#e6edf3", margin: "0 0 4px",
            letterSpacing: "-0.5px",
          }}>
            TraceMind
          </h1>
          <p style={{ fontSize: "13px", color: "#484f58", margin: 0 }}>
            AI Quality Observability Platform
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: "#0d1117",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: "14px",
          padding: "24px",
          boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
        }}>
          {/* Demo banner */}
          <div
            onClick={() => {
              setProjectId("ab85a71f-127")
              setApiKey("ef_live_4T98dMbbqR4x9kpxG89IpSETNOvM5RLC9rL3c9P0ZKw")
            }}
            style={{
              background: "rgba(124,58,237,0.1)",
              border: "1px solid rgba(124,58,237,0.3)",
              borderRadius: "8px",
              padding: "10px 14px",
              marginBottom: "20px",
              cursor: "pointer",
              fontSize: "12px",
              color: "#a78bfa",
              lineHeight: 1.6,
              userSelect: "none" as const,
            }}
          >
            <span style={{ color: "#c4b5fd", fontWeight: 600 }}>
              ↗ Try live demo
            </span>
            {" — "}click to auto-fill credentials
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <label style={{
                fontSize: "11px", fontWeight: 600,
                color: "#8b949e", display: "block",
                marginBottom: "6px", textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}>
                Project ID
              </label>
              <input
                type="text"
                value={projectId}
                onChange={e => setProjectId(e.target.value)}
                placeholder="8e09f14f-2dc..."
                style={{
                  width: "100%", padding: "9px 12px",
                  background: "#161b22",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: "7px", color: "#e6edf3",
                  fontSize: "13px", boxSizing: "border-box" as const,
                  fontFamily: "monospace",
                }}
              />
            </div>

            <div>
              <label style={{
                fontSize: "11px", fontWeight: 600,
                color: "#8b949e", display: "block",
                marginBottom: "6px", textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}>
                API Key
              </label>
              <input
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="ef_live_..."
                style={{
                  width: "100%", padding: "9px 12px",
                  background: "#161b22",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: "7px", color: "#e6edf3",
                  fontSize: "13px", boxSizing: "border-box" as const,
                  fontFamily: "monospace",
                }}
              />
            </div>

            {error && (
              <div style={{
                background: "rgba(248,81,73,0.1)",
                border: "1px solid rgba(248,81,73,0.3)",
                borderRadius: "7px", padding: "9px 12px",
                fontSize: "12px", color: "#f85149",
              }}>
                {error}
              </div>
            )}

            <button
              onClick={handleSubmit}
              disabled={!projectId || !apiKey}
              style={{
                width: "100%", padding: "10px",
                background: (!projectId || !apiKey)
                  ? "rgba(124,58,237,0.3)"
                  : "linear-gradient(135deg, #7c3aed, #a855f7)",
                color: "white", border: "none",
                borderRadius: "8px", fontSize: "14px",
                fontWeight: 600, cursor: (!projectId || !apiKey) ? "not-allowed" : "pointer",
                boxShadow: (!projectId || !apiKey) ? "none" : "0 2px 12px rgba(124,58,237,0.4)",
                marginTop: "4px",
              }}
            >
              Open Dashboard →
            </button>
          </div>

          <p style={{
            fontSize: "11px", color: "#30363d",
            textAlign: "center", margin: "16px 0 0",
          }}>
            No account needed · Self-hosted · Free forever
          </p>
        </div>

        <p style={{
          textAlign: "center", fontSize: "11px",
          color: "#30363d", marginTop: "20px",
        }}>
          <a
            href="https://github.com/Aayush-engineer/tracemind"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#8b949e", textDecoration: "none" }}
          >
            ⭐ Star on GitHub
          </a>
          {" · "}
          <a
            href="https://tracemind.onrender.com/docs"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#8b949e", textDecoration: "none" }}
          >
            API Docs
          </a>
        </p>
      </div>
    </div>
  )
}

export default function App() {
  const [ctx, setCtx] = useState<AppContext | null>(null)

  useEffect(() => {
    const key = localStorage.getItem("ef_api_key")
    const pid = localStorage.getItem("ef_project_id")
    if (key && pid) setCtx({ projectId: pid, apiKey: key, apiUrl: API_URL })
  }, [])

  if (!ctx) return <Login onLogin={(pid, key) =>
    setCtx({ projectId: pid, apiKey: key, apiUrl: API_URL })} />

  return (
    <ToastProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <Layout ctx={ctx} onLogout={() => {
            localStorage.clear(); setCtx(null)
          }}>
            <Routes>
              <Route path="/"         element={<Dashboard {...ctx} />} />
              <Route path="/traces"   element={<Traces    {...ctx} />} />
              <Route path="/evals"    element={<Evals     {...ctx} />} />
              <Route path="/datasets" element={<Datasets  {...ctx} />} />
              <Route path="*"         element={<Navigate to="/" />} />
              <Route path="/live"          element={<Live          {...ctx} />} />
              <Route path="/playground"    element={<Playground    {...ctx} />} />
              <Route path="/hallucination" element={<Hallucination {...ctx} />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </ErrorBoundary>
    </ToastProvider>
  )
}