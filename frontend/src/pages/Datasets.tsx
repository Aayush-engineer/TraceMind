import { useEffect, useState, useCallback } from "react"
import type { AppContext } from "../App";

interface Dataset {
  id:            string
  name:          string
  description:   string
  example_count: number
  created_at:    string
}

interface Example {
  input:    string
  expected: string
  criteria: string[]
  category: string
}

export default function Datasets({ projectId, apiKey, apiUrl }: AppContext) {
  const [datasets,  setDatasets]  = useState<Dataset[]>([])
  const [selected,  setSelected]  = useState<Dataset | null>(null)
  const [examples,  setExamples]  = useState<Example[]>([])
  const [loading,   setLoading]   = useState(true)
  const [showForm,  setShowForm]  = useState(false)

  // New example form state
  const [newInput,    setNewInput]    = useState("")
  const [newExpected, setNewExpected] = useState("")
  const [newCategory, setNewCategory] = useState("general")
  const [saving,      setSaving]      = useState(false)

  const headers = {
    "Authorization": `Bearer ${apiKey}`,
    "Content-Type":  "application/json"
  }

  const fetchDatasets = useCallback(async () => {
    try {
      const res  = await fetch(`${apiUrl}/api/datasets`, { headers })
      const data = await res.json()
      setDatasets(data.datasets || [])
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [projectId, apiKey])

  useEffect(() => { fetchDatasets() }, [fetchDatasets])

  async function loadExamples(ds: Dataset) {
    setSelected(ds)
    try {
      const res  = await fetch(`${apiUrl}/api/datasets/${ds.id}`, { headers })
      const data = await res.json()
      setExamples(data.examples || [])
    } catch { setExamples([]) }
  }

  async function addExample() {
    if (!selected || !newInput.trim()) return
    setSaving(true)
    try {
      await fetch(`${apiUrl}/api/datasets`, {
        method: "POST", headers,
        body: JSON.stringify({
          name:     selected.name,
          project:  projectId,
          examples: [{
            input:    newInput,
            expected: newExpected,
            criteria: ["accurate", "helpful"],
            category: newCategory
          }]
        })
      })
      setNewInput(""); setNewExpected(""); setNewCategory("general")
      setShowForm(false)
      await loadExamples(selected)
      await fetchDatasets()
    } catch { /* ignore */ }
    finally { setSaving(false) }
  }

  async function createDataset() {
    const name = prompt("Dataset name:", "my-dataset-v1")
    if (!name) return
    try {
      await fetch(`${apiUrl}/api/datasets`, {
        method: "POST", headers,
        body: JSON.stringify({ name, project: projectId, examples: [] })
      })
      await fetchDatasets()
    } catch { /* ignore */ }
  }

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0" }}>
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", marginBottom: "20px"
      }}>
        <div>
          <h1 style={{ fontSize: "20px", fontWeight: 600, color: "#f1f5f9", margin: "0 0 4px" }}>
            Datasets
          </h1>
          <p style={{ color: "#64748b", fontSize: "13px", margin: 0 }}>
            Golden test cases for eval runs — click a dataset to manage examples
          </p>
        </div>
        <button onClick={createDataset} style={{
          padding: "9px 16px", background: "#6366f1",
          color: "white", border: "none", borderRadius: "7px",
          fontSize: "13px", fontWeight: 600, cursor: "pointer"
        }}>
          + New dataset
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "280px 1fr" : "1fr", gap: "16px" }}>

        {/* Dataset list */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {loading ? (
            <div style={{ color: "#475569", padding: "2rem", textAlign: "center" }}>
              Loading...
            </div>
          ) : datasets.length === 0 ? (
            <div style={{
              background: "#1e293b", border: "1px solid #334155",
              borderRadius: "10px", padding: "3rem", textAlign: "center", color: "#475569"
            }}>
              <p style={{ fontSize: "32px", margin: "0 0 8px" }}>◫</p>
              <p style={{ margin: "0 0 16px" }}>No datasets yet</p>
              <button onClick={createDataset} style={{
                padding: "8px 16px", background: "#6366f1",
                color: "white", border: "none", borderRadius: "6px",
                fontSize: "13px", cursor: "pointer"
              }}>
                Create your first dataset
              </button>
            </div>
          ) : datasets.map(ds => (
            <div
              key={ds.id}
              onClick={() => loadExamples(ds)}
              style={{
                background: selected?.id === ds.id ? "#1e3a5f" : "#1e293b",
                border: `1px solid ${selected?.id === ds.id ? "#6366f1" : "#334155"}`,
                borderRadius: "10px", padding: "14px 16px",
                cursor: "pointer", transition: "all 0.15s"
              }}
            >
              <p style={{ fontWeight: 600, fontSize: "13px",
                          color: "#f1f5f9", margin: "0 0 4px" }}>
                {ds.name}
              </p>
              <p style={{ fontSize: "12px", color: "#475569", margin: 0 }}>
                {ds.example_count} examples
                {ds.created_at && ` · ${new Date(ds.created_at).toLocaleDateString()}`}
              </p>
            </div>
          ))}
        </div>

        {/* Examples panel */}
        {selected && (
          <div style={{
            background: "#1e293b", border: "1px solid #334155",
            borderRadius: "10px", overflow: "hidden"
          }}>
            <div style={{
              padding: "14px 18px", borderBottom: "1px solid #334155",
              display: "flex", alignItems: "center", justifyContent: "space-between"
            }}>
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: 600,
                             color: "#f1f5f9", margin: "0 0 2px" }}>
                  {selected.name}
                </h3>
                <p style={{ fontSize: "12px", color: "#475569", margin: 0 }}>
                  {examples.length} test cases
                </p>
              </div>
              <button
                onClick={() => setShowForm(!showForm)}
                style={{
                  padding: "7px 14px", background: showForm ? "#334155" : "#6366f1",
                  color: "white", border: "none", borderRadius: "6px",
                  fontSize: "12px", fontWeight: 600, cursor: "pointer"
                }}>
                {showForm ? "Cancel" : "+ Add example"}
              </button>
            </div>

            {/* Add example form */}
            {showForm && (
              <div style={{
                padding: "16px 18px", borderBottom: "1px solid #334155",
                background: "#0f172a"
              }}>
                <div style={{ marginBottom: "10px" }}>
                  <label style={{ fontSize: "11px", color: "#64748b",
                                  display: "block", marginBottom: "4px",
                                  textTransform: "uppercase" }}>
                    Input (user message) *
                  </label>
                  <textarea
                    value={newInput}
                    onChange={e => setNewInput(e.target.value)}
                    placeholder="What should the AI be asked?"
                    rows={2}
                    style={{
                      width: "100%", padding: "8px 10px", borderRadius: "6px",
                      border: "1px solid #334155", background: "#1e293b",
                      color: "#e2e8f0", fontSize: "12px", resize: "vertical",
                      boxSizing: "border-box"
                    }}
                  />
                </div>
                <div style={{ marginBottom: "10px" }}>
                  <label style={{ fontSize: "11px", color: "#64748b",
                                  display: "block", marginBottom: "4px",
                                  textTransform: "uppercase" }}>
                    Expected behavior
                  </label>
                  <input
                    value={newExpected}
                    onChange={e => setNewExpected(e.target.value)}
                    placeholder="What should a good response do?"
                    style={{
                      width: "100%", padding: "8px 10px", borderRadius: "6px",
                      border: "1px solid #334155", background: "#1e293b",
                      color: "#e2e8f0", fontSize: "12px", boxSizing: "border-box"
                    }}
                  />
                </div>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <select
                    value={newCategory}
                    onChange={e => setNewCategory(e.target.value)}
                    style={{
                      padding: "7px 10px", borderRadius: "6px",
                      border: "1px solid #334155", background: "#1e293b",
                      color: "#e2e8f0", fontSize: "12px"
                    }}
                  >
                    {["general","refunds","billing","shipping","safety","support"].map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <button
                    onClick={addExample}
                    disabled={saving || !newInput.trim()}
                    style={{
                      padding: "7px 16px", background: "#10b981",
                      color: "white", border: "none", borderRadius: "6px",
                      fontSize: "12px", fontWeight: 600, cursor: "pointer",
                      opacity: saving || !newInput.trim() ? 0.5 : 1
                    }}>
                    {saving ? "Saving..." : "Save example"}
                  </button>
                </div>
              </div>
            )}

            {/* Examples list */}
            <div style={{ maxHeight: "500px", overflowY: "auto" }}>
              {examples.length === 0 ? (
                <div style={{ padding: "3rem", textAlign: "center", color: "#475569" }}>
                  No examples yet — add your first test case above
                </div>
              ) : examples.map((ex, i) => (
                <div key={i} style={{
                  padding: "12px 18px",
                  borderBottom: "1px solid #1e3a5f"
                }}>
                  <div style={{ display: "flex", alignItems: "flex-start",
                                justifyContent: "space-between", gap: "12px" }}>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontSize: "13px", color: "#e2e8f0",
                                  margin: "0 0 4px", lineHeight: 1.4 }}>
                        {ex.input}
                      </p>
                      {ex.expected && (
                        <p style={{ fontSize: "11px", color: "#475569",
                                    margin: 0, lineHeight: 1.4 }}>
                          Expected: {ex.expected}
                        </p>
                      )}
                    </div>
                    <span style={{
                      padding: "2px 8px", borderRadius: "99px",
                      fontSize: "10px", background: "#0f172a",
                      color: "#64748b", flexShrink: 0
                    }}>
                      {ex.category}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}