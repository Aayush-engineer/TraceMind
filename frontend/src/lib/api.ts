// lib/api.ts
// ─── Lightweight API client ───────────────────────────────────────────────────
// • In-flight deduplication  — same URL fired twice = one request
// • TTL cache               — avoid re-fetching data that hasn't changed
// • AbortController cleanup — no state updates on unmounted components
// • Typed responses         — no any[] at call sites

interface CacheEntry<T> {
  data: T
  ts:   number
}

const CACHE   = new Map<string, CacheEntry<unknown>>()
const INFLIGHT = new Map<string, Promise<unknown>>()

const TTL: Record<string, number> = {
  summary: 20_000,   // 20 s
  metrics: 30_000,   // 30 s
  alerts:  15_000,   // 15 s
  evals:   60_000,   // 1 min — eval runs change slowly
  traces:  10_000,   // 10 s — live data
  datasets: 60_000,
  default:  20_000,
}

function ttlFor(url: string): number {
  for (const [key, ms] of Object.entries(TTL)) {
    if (url.includes(key)) return ms
  }
  return TTL.default
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

export async function apiFetch<T>(
  url:     string,
  apiKey:  string,
  signal?: AbortSignal,
  options: RequestInit = {}
): Promise<T> {
  const cacheKey = url

  // Serve from cache if fresh
  const cached = CACHE.get(cacheKey)
  if (cached && Date.now() - cached.ts < ttlFor(url)) {
    return cached.data as T
  }

  // Deduplicate in-flight GETs
  if (!options.method || options.method === "GET") {
    const existing = INFLIGHT.get(cacheKey)
    if (existing) return existing as Promise<T>
  }

  const promise = fetch(url, {
    ...options,
    signal,
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type":  "application/json",
      ...options.headers,
    },
  }).then(async res => {
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new ApiError(res.status, text)
    }
    return res.json() as Promise<T>
  }).then(data => {
    // Cache successful GETs
    if (!options.method || options.method === "GET") {
      CACHE.set(cacheKey, { data, ts: Date.now() })
    }
    INFLIGHT.delete(cacheKey)
    return data
  }).catch(err => {
    INFLIGHT.delete(cacheKey)
    throw err
  })

  if (!options.method || options.method === "GET") {
    INFLIGHT.set(cacheKey, promise)
  }

  return promise as Promise<T>
}

// Invalidate cache entries by prefix (call after mutations)
export function invalidateCache(prefix: string) {
  for (const key of CACHE.keys()) {
    if (key.includes(prefix)) CACHE.delete(key)
  }
}

// POST helper
export async function apiPost<T>(
  url:    string,
  apiKey: string,
  body:   unknown
): Promise<T> {
  return apiFetch<T>(url, apiKey, undefined, {
    method: "POST",
    body:   JSON.stringify(body),
  })
}