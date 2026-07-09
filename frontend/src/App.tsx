import { useState, useEffect, lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import Layout            from "./components/Layout"
import { ToastProvider } from "./components/Toast"
import ErrorBoundary     from "./components/ErrorBoundary"
import "./index.css"

// ─── Lazy-load every page — only parsed when first visited ───────────────────
const Dashboard     = lazy(() => import("./pages/Dashboard"))
const Traces        = lazy(() => import("./pages/Traces"))
const Evals         = lazy(() => import("./pages/Evals"))
const Datasets      = lazy(() => import("./pages/Datasets"))
const Live          = lazy(() => import("./pages/Live"))
const Playground    = lazy(() => import("./pages/Playground"))
const Hallucination = lazy(() => import("./pages/Hallucination"))

// ─── Env var — MUST be set in Vercel project settings ───────────────────────
// Vite replaces import.meta.env.* at build time.
// If VITE_API_URL is not defined the build will still succeed because we
// provide a fallback, but the deployed app won't reach a real backend.
const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000"

export interface AppContext {
  projectId: string
  apiKey:    string
  apiUrl:    string
}

// ─── Page skeleton shown while a lazy chunk loads ────────────────────────────
function PageFallback() {
  return (
    <div style={{ padding: "20px", display: "flex", flexDirection: "column", gap: "10px" }}>
      {[90, 140, 200].map((h, i) => (
        <div key={i} className="skeleton" style={{ height: h }}/>
      ))}
    </div>
  )
}

// ─── Login screen ────────────────────────────────────────────────────────────
interface LoginProps {
  onLogin: (projectId: string, apiKey: string) => void
}

function Login({ onLogin }: LoginProps) {
  const [projectId, setProjectId] = useState("")
  const [apiKey,    setApiKey]    = useState("")
  const [error,     setError]     = useState("")
  const [loading,   setLoading]   = useState(false)

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!projectId.trim() || !apiKey.trim()) {
      setError("Both fields are required")
      return
    }
    if (!apiKey.startsWith("ef_live_")) {
      setError("API key must start with ef_live_")
      return
    }
    setError("")
    setLoading(true)
    setTimeout(() => {
      localStorage.setItem("ef_api_key",    apiKey)
      localStorage.setItem("ef_project_id", projectId)
      onLogin(projectId, apiKey)
    }, 300)
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "var(--void)", padding: "20px",
      position: "relative", overflow: "hidden",
    }}>
      {/* Dot-grid background */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.02) 1px, transparent 1px)",
        backgroundSize: "24px 24px",
        pointerEvents: "none",
      }}/>

      {/* Corner ticks */}
      {([
        { top: 16,    left: 16,   borderTop:    "1px solid var(--pb)", borderLeft:   "1px solid var(--pb)" },
        { top: 16,    right: 16,  borderTop:    "1px solid var(--pb)", borderRight:  "1px solid var(--pb)" },
        { bottom: 16, left: 16,   borderBottom: "1px solid var(--pb)", borderLeft:   "1px solid var(--pb)" },
        { bottom: 16, right: 16,  borderBottom: "1px solid var(--pb)", borderRight:  "1px solid var(--pb)" },
      ] as React.CSSProperties[]).map((s, i) => (
        <div key={i} style={{ position: "absolute", ...s, width: 28, height: 28, opacity: 0.35 }}/>
      ))}

      <div style={{
        width: "100%", maxWidth: "390px",
        position: "relative", zIndex: 1,
        animation: "fadeUp 0.4s var(--ease) forwards",
      }}>

        {/* Logo */}
        <div style={{ marginBottom: "32px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "14px", marginBottom: "10px" }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: "3px", height: "32px", flexShrink: 0 }}>
              <div style={{ width: "7px", height: "16px", borderRadius: "2px 2px 0 0", background: "var(--p1)", opacity: 0.5 }}/>
              <div style={{ width: "7px", height: "32px", borderRadius: "2px 2px 0 0", background: "var(--p1)" }}/>
              <div style={{ width: "7px", height: "22px", borderRadius: "2px 2px 0 0", background: "var(--p1)", opacity: 0.72 }}/>
            </div>
            <div>
              <h1 style={{
                fontFamily: "var(--f-display)",
                fontSize: "28px", fontWeight: 800,
                color: "var(--t0)", margin: 0,
                letterSpacing: "-0.03em", lineHeight: 1,
              }}>
                TraceMind
              </h1>
              <p style={{
                fontFamily: "var(--f-mono)",
                fontSize: "9px", color: "var(--p3)",
                margin: "5px 0 0", letterSpacing: "0.22em",
                textTransform: "uppercase",
              }}>
                AI Eval Observatory
              </p>
            </div>
          </div>

          <div style={{
            fontFamily: "var(--f-mono)",
            fontSize: "10px", color: "var(--t3)",
            lineHeight: 1.8,
            borderLeft: "2px solid var(--b2)",
            paddingLeft: "12px",
          }}>
            <div style={{ color: "var(--p3)" }}>[ SYS ] TraceMind v3 — initializing</div>
            <div>[ NET ] Awaiting authentication credentials…</div>
          </div>
        </div>

        {/* Card */}
        <div style={{
          background: "var(--surface)",
          border: "1px solid var(--b2)",
          borderRadius: "var(--r3)",
          overflow: "hidden",
          position: "relative",
        }}>
          <div className="panel-accent"/>

          {/* Demo autofill */}
          <div
            onClick={() => {
              setProjectId("91f6a5bf-eed")
              setApiKey("ef_live_qsu6qr-xhtpjgGnafolcj_CkQJ4pGyfwxY-Q2R-Rmu4")
            }}
            style={{
              padding: "10px 18px",
              borderBottom: "1px solid var(--b1)",
              display: "flex", alignItems: "center", gap: "10px",
              cursor: "pointer",
              background: "rgba(0,230,118,0.03)",
              transition: "background var(--t-fast)",
            }}
            onMouseEnter={e => ((e.currentTarget as HTMLElement).style.background = "rgba(0,230,118,0.06)")}
            onMouseLeave={e => ((e.currentTarget as HTMLElement).style.background = "rgba(0,230,118,0.03)")}
          >
            <span className="sig sig-p">DEMO</span>
            <span style={{ fontSize: "11px", color: "var(--t2)" }}>
              Click to auto-fill live credentials
            </span>
            <span style={{ marginLeft: "auto", color: "var(--p3)", fontSize: "12px" }}>→</span>
          </div>

          <form onSubmit={handleSubmit} style={{ padding: "20px 18px", display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <label className="label">Project ID</label>
              <input
                className="field"
                type="text"
                value={projectId}
                onChange={e => setProjectId(e.target.value)}
                placeholder="8e09f14f-2dc…"
                autoComplete="off"
              />
            </div>

            <div>
              <label className="label">API Key</label>
              <input
                className="field"
                type="password"
                value={apiKey}
                onChange={e => setApiKey(e.target.value)}
                placeholder="ef_live_…"
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div style={{
                padding: "8px 12px",
                background: "var(--rg)",
                border: "1px solid var(--rb)",
                borderRadius: "var(--r1)",
                fontFamily: "var(--f-mono)",
                fontSize: "10px",
                color: "var(--r0)",
                letterSpacing: "0.04em",
              }}>
                ✕ {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !projectId || !apiKey}
              className="btn btn-p"
              style={{ width: "100%", justifyContent: "center", padding: "11px", fontSize: "11px" }}
            >
              {loading ? "AUTHENTICATING…" : "AUTHENTICATE →"}
            </button>
          </form>

          <div style={{
            padding: "10px 18px",
            borderTop: "1px solid var(--b1)",
            display: "flex", justifyContent: "center", gap: "20px",
          }}>
            {[
              { label: "GitHub ↗",  href: "https://github.com/Aayush-engineer/tracemind" },
              { label: "API Docs ↗", href: "https://tracemind.onrender.com/docs" },
            ].map(l => (
              <a
                key={l.label}
                href={l.href}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontFamily: "var(--f-mono)",
                  fontSize: "9px", color: "var(--t3)",
                  textDecoration: "none",
                  letterSpacing: "0.08em", textTransform: "uppercase",
                  transition: "color var(--t-fast)",
                }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.color = "var(--p2)")}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.color = "var(--t3)")}
              >
                {l.label}
              </a>
            ))}
          </div>
        </div>

        <p style={{
          textAlign: "center", marginTop: "16px",
          fontFamily: "var(--f-mono)", fontSize: "9px",
          color: "var(--t4)", letterSpacing: "0.1em",
        }}>
          SELF-HOSTED · OPEN SOURCE · FREE
        </p>
      </div>
    </div>
  )
}

// ─── Root ─────────────────────────────────────────────────────────────────────
export default function App() {
  const [ctx, setCtx] = useState<AppContext | null>(null)

  useEffect(() => {
    const key = localStorage.getItem("ef_api_key")
    const pid = localStorage.getItem("ef_project_id")
    if (key && pid) {
      setCtx({ projectId: pid, apiKey: key, apiUrl: API_URL })
    }
  }, [])

  if (!ctx) {
    return (
      <Login
        onLogin={(pid, key) =>
          setCtx({ projectId: pid, apiKey: key, apiUrl: API_URL })
        }
      />
    )
  }

  return (
    <ToastProvider>
      <ErrorBoundary>
        <BrowserRouter>
          <Layout ctx={ctx} onLogout={() => { localStorage.clear(); setCtx(null) }}>
            <Routes>
              <Route path="/"              element={<Suspense fallback={<PageFallback/>}><Dashboard     {...ctx}/></Suspense>}/>
              <Route path="/traces"        element={<Suspense fallback={<PageFallback/>}><Traces        {...ctx}/></Suspense>}/>
              <Route path="/evals"         element={<Suspense fallback={<PageFallback/>}><Evals         {...ctx}/></Suspense>}/>
              <Route path="/datasets"      element={<Suspense fallback={<PageFallback/>}><Datasets      {...ctx}/></Suspense>}/>
              <Route path="/live"          element={<Suspense fallback={<PageFallback/>}><Live          {...ctx}/></Suspense>}/>
              <Route path="/playground"    element={<Suspense fallback={<PageFallback/>}><Playground    {...ctx}/></Suspense>}/>
              <Route path="/hallucination" element={<Suspense fallback={<PageFallback/>}><Hallucination {...ctx}/></Suspense>}/>
              <Route path="*"              element={<Navigate to="/" replace/>}/>
            </Routes>
          </Layout>
        </BrowserRouter>
      </ErrorBoundary>
    </ToastProvider>
  )
}