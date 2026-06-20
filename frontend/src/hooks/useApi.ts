// hooks/useApi.ts
import { useState, useEffect, useRef, useCallback } from "react"
import { apiFetch, ApiError } from "../lib/api"

interface UseApiOptions {
  interval?: number      // auto-refresh ms (0 = no auto-refresh)
  enabled?:  boolean     // false = skip fetching
}

interface UseApiResult<T> {
  data:    T | null
  loading: boolean
  error:   string
  refetch: () => void
}

export function useApi<T>(
  url:     string | null,
  apiKey:  string,
  opts:    UseApiOptions = {}
): UseApiResult<T> {
  const { interval = 0, enabled = true } = opts

  const [data,    setData]    = useState<T | null>(null)
  const [loading, setLoading] = useState(!!url && enabled)
  const [error,   setError]   = useState("")
  const abortRef = useRef<AbortController | null>(null)
  const mountRef = useRef(true)

  const run = useCallback(async (showLoading = false) => {
    if (!url || !enabled) return

    // Abort any previous in-flight request for this hook instance
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    if (showLoading) setLoading(true)

    try {
      const result = await apiFetch<T>(url, apiKey, ctrl.signal)
      if (!mountRef.current || ctrl.signal.aborted) return
      setData(result)
      setError("")
    } catch (err) {
      if (!mountRef.current || ctrl.signal.aborted) return
      if (err instanceof ApiError) {
        setError(`${err.status}: ${err.message}`)
      } else if (err instanceof Error && err.name !== "AbortError") {
        setError(err.message)
      }
    } finally {
      if (mountRef.current && !ctrl.signal.aborted) setLoading(false)
    }
  }, [url, apiKey, enabled]) // eslint-disable-line

  // Initial fetch
  useEffect(() => {
    mountRef.current = true
    run(true)
    return () => {
      mountRef.current = false
      abortRef.current?.abort()
    }
  }, [run])

  // Auto-refresh
  useEffect(() => {
    if (!interval) return
    const iv = setInterval(() => run(false), interval)
    return () => clearInterval(iv)
  }, [run, interval])

  return { data, loading, error, refetch: () => run(false) }
}

// ─── Parallel fetch hook ──────────────────────────────────────────────────────
export function useApis<T extends Record<string, unknown>>(
  queries: Record<keyof T, string | null>,
  apiKey:  string,
  opts:    UseApiOptions = {}
): { data: Partial<T>; loading: boolean; error: string; refetch: () => void } {
  const keys   = Object.keys(queries) as (keyof T)[]
  const urls   = keys.map(k => queries[k])
  const joined = urls.join("|")

  const [data,    setData]    = useState<Partial<T>>({})
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState("")
  const mountRef  = useRef(true)
  const abortRef  = useRef<AbortController | null>(null)

  const { interval = 0, enabled = true } = opts

  const run = useCallback(async (showLoading = false) => {
    if (!enabled) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    if (showLoading) setLoading(true)

    try {
      const results = await Promise.all(
        keys.map(k =>
          queries[k]
            ? apiFetch(queries[k]!, apiKey, ctrl.signal)
            : Promise.resolve(null)
        )
      )
      if (!mountRef.current || ctrl.signal.aborted) return
      const merged: Partial<T> = {}
      keys.forEach((k, i) => { if (results[i] !== null) merged[k] = results[i] as T[keyof T] })
      setData(merged)
      setError("")
    } catch (err) {
      if (!mountRef.current || ctrl.signal.aborted) return
      if (err instanceof ApiError) setError(`${err.status}: ${err.message}`)
      else if (err instanceof Error && err.name !== "AbortError") setError(err.message)
    } finally {
      if (mountRef.current && !ctrl.signal.aborted) setLoading(false)
    }
  }, [joined, apiKey, enabled]) // eslint-disable-line

  useEffect(() => {
    mountRef.current = true
    run(true)
    return () => { mountRef.current = false; abortRef.current?.abort() }
  }, [run])

  useEffect(() => {
    if (!interval) return
    const iv = setInterval(() => run(false), interval)
    return () => clearInterval(iv)
  }, [run, interval])

  return { data, loading, error, refetch: () => run(false) }
}