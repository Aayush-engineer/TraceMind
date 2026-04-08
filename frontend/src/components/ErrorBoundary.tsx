import { Component, type ReactNode } from "react"

interface Props { children: ReactNode }
interface State { hasError: boolean; error: string }

export default class ErrorBoundary extends Component<Props, State> {
  state = { hasError: false, error: "" }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: "40px", textAlign: "center",
          color: "#e2e8f0", fontFamily: "system-ui"
        }}>
          <p style={{ fontSize: "32px", margin: "0 0 12px" }}>⚠</p>
          <p style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 8px" }}>
            Something went wrong
          </p>
          <p style={{ fontSize: "13px", color: "#64748b", margin: "0 0 20px" }}>
            {this.state.error}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: "" })}
            style={{
              padding: "8px 16px", background: "#6366f1",
              color: "white", border: "none", borderRadius: "6px",
              cursor: "pointer", fontSize: "13px"
            }}
          >
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}