// pages/Datasets.tsx
import { useState, useCallback, memo } from "react"
import type { AppContext } from "../App"
import { useApi } from "../hooks/useApi"
import { apiPost, invalidateCache } from "../lib/api"
import type { Dataset, Example } from "../lib/types"

const ExampleRow = memo(function ExampleRow({ ex }: { ex: Example }) {
  return (
    <div style={{
      padding: "11px 16px",
      borderBottom: "1px solid rgba(120,180,255,0.04)",
      display: "flex", alignItems: "flex-start",
      justifyContent: "space-between", gap: 12,
    }}>
      <div style={{ flex: 1 }}>
        <p style={{ fontSize: "12px", color: "var(--t0)", margin: "0 0 3px", lineHeight: 1.5 }}>
          {ex.input}
        </p>
        {ex.expected && (
          <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0 }}>
            expected: {ex.expected}
          </p>
        )}
      </div>
      <span className="sig sig-x">{ex.category}</span>
    </div>
  )
})

const CATEGORIES = ["general","refunds","billing","shipping","safety","support"] as const

export default function Datasets({ projectId, apiKey, apiUrl }: AppContext) {
  const [selected,    setSelected]    = useState<Dataset | null>(null)
  const [examples,    setExamples]    = useState<Example[]>([])
  const [showForm,    setShowForm]    = useState(false)
  const [newInput,    setNewInput]    = useState("")
  const [newExpected, setNewExpected] = useState("")
  const [newCategory, setNewCategory] = useState<typeof CATEGORIES[number]>("general")
  const [saving,      setSaving]      = useState(false)
  const [exLoading,   setExLoading]   = useState(false)

  const { data, loading, refetch } = useApi<{ datasets: Dataset[] }>(
    `${apiUrl}/api/datasets`,
    apiKey,
    { interval: 60_000 }
  )

  const datasets = data?.datasets ?? []

  const loadExamples = useCallback(async (ds: Dataset) => {
    setSelected(ds)
    setExLoading(true)
    try {
      const res = await fetch(`${apiUrl}/api/datasets/${ds.id}`, {
        headers: { "Authorization": `Bearer ${apiKey}` },
      })
      const d = await res.json()
      setExamples(d.examples || [])
    } catch {
      setExamples([])
    } finally {
      setExLoading(false)
    }
  }, [apiUrl, apiKey])

  const addExample = useCallback(async () => {
    if (!selected || !newInput.trim()) return
    setSaving(true)
    try {
      await apiPost(`${apiUrl}/api/datasets`, apiKey, {
        name:     selected.name,
        project:  projectId,
        examples: [{ input: newInput, expected: newExpected, criteria: ["accurate","helpful"], category: newCategory }],
      })
      invalidateCache("datasets")
      setNewInput(""); setNewExpected(""); setNewCategory("general"); setShowForm(false)
      await loadExamples(selected)
      refetch()
    } catch {/**/ }
    finally { setSaving(false) }
  }, [selected, newInput, newExpected, newCategory, apiUrl, apiKey, projectId, loadExamples, refetch])

  const createDataset = useCallback(async () => {
    const name = prompt("Dataset name:", "my-dataset-v1")
    if (!name) return
    try {
      await apiPost(`${apiUrl}/api/datasets`, apiKey, { name, project: projectId, examples: [] })
      invalidateCache("datasets")
      refetch()
    } catch {/**/ }
  }, [apiUrl, apiKey, projectId, refetch])

  const toggleForm = useCallback(() => setShowForm(v => !v), [])
  const closeSelected = useCallback(() => { setSelected(null); setExamples([]) }, [])

  return (
    <div style={{ padding: "18px 20px" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "16px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--f-display)", fontSize: "18px", fontWeight: 700, color: "var(--t0)", margin: "0 0 2px" }}>
            Datasets
          </h1>
          <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", letterSpacing: "0.08em" }}>
            [DAT] GOLDEN TEST CASES FOR EVAL RUNS · {datasets.length} DATASETS
          </p>
        </div>
        <button onClick={createDataset} className="btn btn-p">+ NEW DATASET</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: selected ? "220px 1fr" : "1fr", gap: "12px" }}>

        {/* Dataset list */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          {loading && !datasets.length ? (
            [1,2,3].map(i => <div key={i} className="skeleton" style={{ height: 60 }}/>)
          ) : datasets.length === 0 ? (
            <div className="panel">
              <div className="empty">
                <span className="empty-glyph">⊟</span>
                <p className="empty-title">No datasets yet</p>
                <button onClick={createDataset} className="btn btn-p" style={{ marginTop: 8 }}>CREATE FIRST</button>
              </div>
            </div>
          ) : datasets.map((ds, i) => {
            const isSel = selected?.id === ds.id
            return (
              <div
                key={ds.id}
                onClick={() => loadExamples(ds)}
                className="panel"
                style={{
                  padding: "12px 14px",
                  cursor: "pointer",
                  background: isSel ? "var(--overlay)" : "var(--surface)",
                  borderColor: isSel ? "var(--pb)" : "var(--b1)",
                  transition: "all var(--t-fast)",
                  animation: `fadeUp 0.25s ${i * 0.04}s var(--ease) both`,
                }}
                onMouseEnter={e => { if (!isSel) { (e.currentTarget as HTMLElement).style.background = "var(--raised)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--b2)" } }}
                onMouseLeave={e => { if (!isSel) { (e.currentTarget as HTMLElement).style.background = "var(--surface)"; (e.currentTarget as HTMLElement).style.borderColor = "var(--b1)" } }}
              >
                <div className="panel-accent"/>
                <p style={{ fontFamily: "var(--f-mono)", fontSize: "11px", fontWeight: 700, color: "var(--t0)", margin: "0 0 4px" }}>
                  {ds.name}
                </p>
                <p style={{ fontFamily: "var(--f-mono)", fontSize: "9px", color: "var(--t3)", margin: 0 }}>
                  {ds.example_count} examples
                  {ds.created_at && ` · ${new Date(ds.created_at).toLocaleDateString()}`}
                </p>
              </div>
            )
          })}
        </div>

        {/* Examples panel */}
        {selected && (
          <div className="panel" style={{ padding: 0 }}>
            <div className="panel-accent"/>
            <div className="panel-header">
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span className="panel-label">{selected.name}</span>
                <span style={{ fontFamily: "var(--f-mono)", fontSize: "8px", color: "var(--t3)" }}>
                  {examples.length} CASES
                </span>
              </div>
              <div style={{ display: "flex", gap: "6px" }}>
                <button onClick={toggleForm} className={`btn ${showForm ? "btn-ghost" : "btn-p"}`} style={{ padding: "5px 12px" }}>
                  {showForm ? "CANCEL" : "+ ADD"}
                </button>
                <button onClick={closeSelected} className="btn btn-ghost" style={{ padding: "5px 8px" }}>✕</button>
              </div>
            </div>

            {/* Add form */}
            {showForm && (
              <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--b1)", background: "var(--base)", display: "flex", flexDirection: "column", gap: "10px" }}>
                <div>
                  <label className="label">INPUT (USER MESSAGE) *</label>
                  <textarea
                    value={newInput}
                    onChange={e => setNewInput(e.target.value)}
                    placeholder="What should the AI be asked?"
                    rows={2}
                    className="field"
                  />
                </div>
                <div>
                  <label className="label">EXPECTED BEHAVIOR</label>
                  <input
                    value={newExpected}
                    onChange={e => setNewExpected(e.target.value)}
                    placeholder="What should a good response do?"
                    className="field"
                  />
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <select
                    value={newCategory}
                    onChange={e => setNewCategory(e.target.value as typeof CATEGORIES[number])}
                    className="field"
                    style={{ width: "auto" }}
                  >
                    {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <button
                    onClick={addExample}
                    disabled={saving || !newInput.trim()}
                    className="btn btn-p"
                  >
                    {saving ? "SAVING…" : "SAVE"}
                  </button>
                </div>
              </div>
            )}

            {/* Examples list */}
            <div style={{ maxHeight: "460px", overflowY: "auto" }}>
              {exLoading ? (
                <div style={{ padding: "2rem", display: "flex", justifyContent: "center" }}>
                  <div className="animate-spin" style={{ width: 22, height: 22, border: "2px solid var(--b2)", borderTop: "2px solid var(--p0)", borderRadius: "50%" }}/>
                </div>
              ) : examples.length === 0 ? (
                <div className="empty">
                  <p className="empty-title">No examples yet</p>
                  <p className="empty-sub">Add test cases above</p>
                </div>
              ) : examples.map((ex, i) => <ExampleRow key={i} ex={ex}/>)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}