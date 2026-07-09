// components/ErrorBoundary.tsx
import { Component, type ReactNode } from "react"
interface Props { children: ReactNode }
interface State { hasError: boolean; error: string }
export default class ErrorBoundary extends Component<Props, State> {
  state = { hasError: false, error: "" }
  static getDerivedStateFromError(e: Error) { return { hasError: true, error: e.message } }
  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div style={{ padding: "60px 40px", textAlign: "center", fontFamily: "var(--f-mono)" }}>
        <div style={{ display:"inline-flex", width:48, height:48, background:"var(--rg)", border:"1px solid var(--rb)", borderRadius:"var(--r2)", alignItems:"center", justifyContent:"center", fontSize:22, marginBottom:16, color:"var(--r0)" }}>⚠</div>
        <p style={{ fontSize:14, fontWeight:700, color:"var(--t0)", margin:"0 0 8px", letterSpacing:"0.04em" }}>RUNTIME ERROR</p>
        <p style={{ fontSize:11, color:"var(--t2)", margin:"0 0 20px" }}>{this.state.error}</p>
        <button onClick={() => this.setState({ hasError:false, error:"" })} className="btn btn-p">RETRY</button>
      </div>
    )
  }
}