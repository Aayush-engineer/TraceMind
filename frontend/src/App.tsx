import { useState, useEffect } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Dashboard from "./pages/Dashboard"
import Traces    from "./pages/Traces"
import Evals     from "./pages/Evals"
import Datasets  from "./pages/Datasets"
import Layout    from "./components/Layout"

const API_URL = import.meta.env.VITE_API_URL;

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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    localStorage.setItem("ef_api_key",    apiKey)
    localStorage.setItem("ef_project_id", projectId)
    onLogin(projectId, apiKey)
  }

  return (
    <div style={{
      position: "fixed", inset: 0, background: "#0f172a",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "system-ui, sans-serif"
    }}>
      <div style={{
        background: "#1e293b", border: "1px solid #334155",
        padding: "2rem", borderRadius: "14px", width: "360px"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
          <div style={{
            width: "32px", height: "32px", background: "#6366f1",
            borderRadius: "8px", display: "flex", alignItems: "center",
            justifyContent: "center", fontSize: "16px", fontWeight: 700, color: "white"
          }}>E</div>
          <h1 style={{ fontSize: "20px", fontWeight: 700, color: "#f1f5f9", margin: 0 }}>
            TraceMind
          </h1>
        </div>
        <p style={{ color: "#64748b", fontSize: "13px", marginBottom: "1.75rem" }}>
          AI quality monitoring platform
        </p>
        <form onSubmit={handleSubmit}>
          {[
            { label: "Project ID", value: projectId, set: setProjectId,
              placeholder: "64768f98-106...", type: "text" },
            { label: "API Key",    value: apiKey,    set: setApiKey,
              placeholder: "ef_live_...", type: "password" },
          ].map(f => (
            <div key={f.label} style={{ marginBottom: "14px" }}>
              <label style={{ fontSize: "12px", fontWeight: 500,
                              color: "#94a3b8", display: "block", marginBottom: "5px" }}>
                {f.label}
              </label>
              <input
                value={f.value}
                onChange={e => f.set(e.target.value)}
                placeholder={f.placeholder}
                type={f.type}
                required
                style={{
                  width: "100%", padding: "9px 12px", borderRadius: "7px",
                  border: "1px solid #334155", background: "#0f172a",
                  color: "#e2e8f0", fontSize: "13px", boxSizing: "border-box"
                }}
              />
            </div>
          ))}
          <button type="submit" style={{
            width: "100%", padding: "10px", background: "#6366f1",
            color: "white", border: "none", borderRadius: "7px",
            fontSize: "14px", fontWeight: 600, cursor: "pointer", marginTop: "4px"
          }}>
            Open Dashboard →
          </button>
        </form>
        <p style={{ textAlign: "center", fontSize: "11px",
                    color: "#334155", marginTop: "1.25rem", marginBottom: 0 }}>
          Open source · Self-hosted · Free
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
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}