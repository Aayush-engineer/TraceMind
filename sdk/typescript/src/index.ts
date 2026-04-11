export interface TraceMindConfig {
  apiKey:               string
  project:              string
  baseUrl?:             string
  batchSize?:           number
  flushIntervalMs?:     number
  timeoutMs?:           number
  debug?:               boolean
  redactPii?:           boolean
  maskInputs?:          boolean
  maskOutputs?:         boolean
  customRedactPatterns?: Array<[RegExp | string, string]>
}

export interface Span {
  span_id:     string
  trace_id:    string
  project:     string
  name:        string
  input:       string
  output:      string
  error?:      string
  duration_ms: number
  status:      'success' | 'error'
  metadata?:   Record<string, unknown>
  cost_usd?:   number
  tags?:       string[]
  timestamp:   number
}

export interface EvalRunResult {
  run_id:    string
  status:    'pending' | 'running' | 'completed' | 'failed'
  pass_rate: number
  avg_score: number
  passed:    number
  failed:    number
  total:     number
  results:   Array<{
    id:        string
    input:     string
    output:    string
    score:     number
    passed:    boolean
    reasoning: string
    error?:    string
  }>
}

export interface DatasetExample {
  input:      string
  expected?:  string
  criteria?:  string[]
  category?:  string
  tags?:      string[]
  difficulty?: 'easy' | 'medium' | 'hard' | 'adversarial'
}

// ─── PII Redactor ─────────────────────────────────────────────────────────────

const PII_PATTERNS: Array<[RegExp, string]> = [
  [/\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,         '[EMAIL]'],
  [/\b(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g,  '[PHONE]'],
  [/\b(?:\d{4}[-\s]?){3}\d{4}\b/g,                                   '[CARD]'],
  [/\b\d{3}-\d{2}-\d{4}\b/g,                                         '[SSN]'],
  [/\b(?:\d{1,3}\.){3}\d{1,3}\b/g,                                   '[IP]'],
  [/\b(sk-|pk-|tm_live_|Bearer\s)[A-Za-z0-9_\-]{20,}/g,             '[API_KEY]'],
  [/\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b/g,   '[JWT]'],
]

class PIIRedactor {
  private patterns: Array<[RegExp, string]>

  constructor(custom: Array<[RegExp | string, string]> = []) {
    this.patterns = [...PII_PATTERNS]
    for (const [pat, rep] of custom) {
      this.patterns.push([
        typeof pat === 'string' ? new RegExp(pat, 'g') : pat,
        rep
      ])
    }
  }

  redact(text: string): string {
    if (typeof text !== 'string') return text
    for (const [pattern, replacement] of this.patterns) {
      text = text.replace(pattern, replacement)
    }
    return text
  }
}

// ─── OpenAI Integration ──────────────────────────────────────────────────────

const OPENAI_COSTS: Record<string, { input: number; output: number }> = {
  'gpt-4o':        { input: 5.00,  output: 15.00 },
  'gpt-4o-mini':   { input: 0.15,  output: 0.60  },
  'gpt-4-turbo':   { input: 10.00, output: 30.00 },
  'gpt-4':         { input: 30.00, output: 60.00 },
  'gpt-3.5-turbo': { input: 0.50,  output: 1.50  },
  'o1':            { input: 15.00, output: 60.00 },
  'o1-mini':       { input: 3.00,  output: 12.00 },
  'o3-mini':       { input: 1.10,  output: 4.40  },
}

function estimateCost(model: string, inputTokens: number, outputTokens: number): number {
  for (const [key, costs] of Object.entries(OPENAI_COSTS)) {
    if (model.startsWith(key)) {
      return (inputTokens * costs.input / 1_000_000) +
             (outputTokens * costs.output / 1_000_000)
    }
  }
  return 0
}

// ─── DatasetBuilder ───────────────────────────────────────────────────────────

export class DatasetBuilder {
  private examples: DatasetExample[] = []

  constructor(
    private readonly tm:   TraceMind,
    private readonly name: string,
  ) {}

  add(example: DatasetExample): this {
    if (!example.input?.trim()) {
      throw new Error('input cannot be empty')
    }
    this.examples.push({
      criteria:   [],
      category:   'general',
      tags:       [],
      difficulty: 'medium',
      ...example,
    })
    return this
  }

  addBatch(examples: DatasetExample[]): this {
    examples.forEach(e => this.add(e))
    return this
  }

  get size(): number { return this.examples.length }

  async push(): Promise<{ name: string; examples_added: number }> {
    if (this.examples.length === 0) {
      throw new Error('Dataset is empty. Add examples before pushing.')
    }
    const res = await this.tm['_request']('POST', '/api/datasets', {
      name:     this.name,
      project:  this.tm.project,
      examples: this.examples,
    })
    return res
  }
}

// ─── EvalRun ─────────────────────────────────────────────────────────────────

export class EvalRun {
  private data: Partial<EvalRunResult>

  constructor(data: Partial<EvalRunResult>, private readonly tm: TraceMind) {
    this.data = data
  }

  get runId():    string { return this.data.run_id ?? '' }
  get status():   string { return this.data.status  ?? 'unknown' }
  get passRate(): number { return this.data.pass_rate ?? 0 }
  get avgScore(): number { return this.data.avg_score ?? 0 }
  get total():    number { return this.data.total     ?? 0 }
  get passed():   number { return this.data.passed    ?? 0 }
  get failed():   number { return this.data.failed    ?? 0 }
  get results():  EvalRunResult['results'] { return this.data.results ?? [] }

  get failures(): EvalRunResult['results'] {
    return this.results.filter(r => !r.passed)
  }

  get isComplete(): boolean { return this.status === 'completed' }

  async wait(options: {
    pollIntervalMs?: number
    timeoutMs?:      number
    onProgress?:     (run: EvalRun) => void
  } = {}): Promise<EvalRun> {
    const { pollIntervalMs = 2000, timeoutMs = 300_000, onProgress } = options
    const start = Date.now()

    while (Date.now() - start < timeoutMs) {
      const data = await this.tm['_request']('GET', `/api/evals/${this.runId}`)
      this.data  = data

      if (onProgress) onProgress(this)

      if (this.isComplete) return this
      if (this.status === 'failed') throw new Error(`Eval ${this.runId} failed`)

      await sleep(pollIntervalMs)
    }

    throw new Error(`Eval ${this.runId} timed out after ${timeoutMs}ms`)
  }

  printSummary(): this {
    console.log(`\n${'='.repeat(48)}`)
    console.log(`Eval: ${this.runId}`)
    console.log(`Status:     ${this.status}`)
    console.log(`Pass rate:  ${(this.passRate * 100).toFixed(1)}% (${this.passed}/${this.total})`)
    console.log(`Avg score:  ${this.avgScore.toFixed(2)}/10`)
    if (this.failures.length > 0) {
      console.log('\nTop failures:')
      this.failures.slice(0, 5).forEach(f => {
        console.log(`  [${f.score.toFixed(1)}] ${f.input.slice(0, 60)}`)
        console.log(`        → ${f.reasoning.slice(0, 80)}`)
      })
    }
    console.log('='.repeat(48) + '\n')
    return this
  }

  toString(): string {
    return `EvalRun(${this.runId}, ${this.status}, ${(this.passRate*100).toFixed(0)}% pass)`
  }
}

// ─── Span Context ─────────────────────────────────────────────────────────────

export class SpanContext {
  private output:   unknown = null
  private scores:   Record<string, number> = {}
  private metadata: Record<string, unknown> = {}
  private error:    string = ''
  readonly spanId:  string
  readonly traceId: string
  private readonly t0: number

  constructor(
    private readonly tm:   TraceMind,
    private readonly name: string,
    private readonly inputData: Record<string, unknown>,
  ) {
    this.spanId  = randomId()
    this.traceId = randomId()
    this.t0      = Date.now()
  }

  setOutput(output: unknown): this {
    this.output = output
    return this
  }

  score(dimension: string, value: number): this {
    this.scores[dimension] = Math.max(0, Math.min(10, value))
    return this
  }

  setMeta(key: string, value: unknown): this {
    this.metadata[key] = value
    return this
  }

  setError(err: string): this {
    this.error = err
    return this
  }

  flush(): void {
    const duration = Date.now() - this.t0
    this.tm['_bufferSpan']({
      span_id:     this.spanId,
      trace_id:    this.traceId,
      project:     this.tm.project,
      name:        this.name,
      input:       JSON.stringify(this.inputData).slice(0, 2000),
      output:      String(this.output ?? '').slice(0, 2000),
      error:       this.error,
      duration_ms: duration,
      status:      this.error ? 'error' : 'success',
      metadata:    { ...this.metadata, scores: this.scores },
      timestamp:   this.t0 / 1000,
    })
  }
}

// ─── Stream Span Context ──────────────────────────────────────────────────────

export class StreamSpanContext {
  private chunks:         string[] = []
  private firstTokenTime: number | null = null
  private metadata:       Record<string, unknown> = {}
  private inputText:      string = ''
  readonly spanId:        string
  readonly traceId:       string
  private readonly t0:    number

  constructor(
    private readonly tm:   TraceMind,
    private readonly name: string,
  ) {
    this.spanId  = randomId()
    this.traceId = randomId()
    this.t0      = Date.now()
  }

  setInput(text: string): this {
    this.inputText = text
    return this
  }

  addChunk(chunk: string): void {
    if (chunk && this.firstTokenTime === null) {
      this.firstTokenTime = Date.now()
    }
    if (chunk) this.chunks.push(chunk)
  }

  get output(): string { return this.chunks.join('') }
  get firstTokenLatencyMs(): number {
    return this.firstTokenTime ? this.firstTokenTime - this.t0 : 0
  }

  flush(error?: string): void {
    this.tm['_bufferSpan']({
      span_id:     this.spanId,
      trace_id:    this.traceId,
      project:     this.tm.project,
      name:        this.name,
      input:       this.inputText.slice(0, 2000),
      output:      this.output.slice(0, 2000),
      error:       error ?? '',
      duration_ms: Date.now() - this.t0,
      status:      error ? 'error' : 'success',
      metadata: {
        first_token_ms: this.firstTokenLatencyMs,
        total_chunks:   this.chunks.length,
        streaming:      true,
      },
      timestamp: this.t0 / 1000,
    })
  }
}

// ─── TraceMind Core ───────────────────────────────────────────────────────────

export class TraceMind {
  readonly project:  string
  readonly apiKey:   string
  readonly baseUrl:  string

  private buffer:    Span[] = []
  private flushTimer: ReturnType<typeof setInterval> | null = null
  private redactor:  PIIRedactor | null
  private readonly batchSize:   number
  private readonly debug:       boolean
  private readonly maskInputs:  boolean
  private readonly maskOutputs: boolean

  constructor(config: TraceMindConfig) {
    if (!config.apiKey)   throw new Error('apiKey is required')
    if (!config.project)  throw new Error('project is required')

    this.project     = config.project
    this.apiKey      = config.apiKey
    this.baseUrl     = (config.baseUrl ?? 'https://tracemind.onrender.com').replace(/\/$/, '')
    this.batchSize   = config.batchSize      ?? 20
    this.debug       = config.debug          ?? false
    this.maskInputs  = config.maskInputs     ?? false
    this.maskOutputs = config.maskOutputs    ?? false
    this.redactor    = config.redactPii
      ? new PIIRedactor(config.customRedactPatterns)
      : null

    const intervalMs = config.flushIntervalMs ?? 5_000
    this.flushTimer  = setInterval(() => this._flush(), intervalMs)

    if (typeof process !== 'undefined' && process.on) {
      process.on('exit',    () => this.close())
      process.on('SIGTERM', () => this.close())
    }
  }

  // ── Integration helpers ──────────────────────────────────────────────────

  wrapOpenAI<T extends object>(client: T): T {
    const tm = this
    const originalChat = (client as any).chat

    const wrappedCompletions = {
      create: async (params: any) => {
        const t0      = Date.now()
        const spanId  = randomId()
        const traceId = randomId()
        const model   = params.model ?? 'unknown'

        const lastUser = [...(params.messages ?? [])].reverse()
          .find((m: any) => m.role === 'user')
        const inputText = typeof lastUser?.content === 'string'
          ? lastUser.content
          : JSON.stringify(lastUser?.content ?? '')

        try {
          const response = await originalChat.completions.create(params)
          const duration = Date.now() - t0

          const outputText  = response.choices?.[0]?.message?.content ?? ''
          const inputTokens  = response.usage?.prompt_tokens     ?? 0
          const outputTokens = response.usage?.completion_tokens ?? 0
          const cost         = estimateCost(model, inputTokens, outputTokens)

          tm._bufferSpan({
            span_id:     spanId,
            trace_id:    traceId,
            project:     tm.project,
            name:        `openai/${model}`,
            input:       inputText.slice(0, 2000),
            output:      outputText.slice(0, 2000),
            error:       '',
            duration_ms: duration,
            status:      'success',
            metadata: {
              model, inputTokens, outputTokens, cost,
              provider: 'openai',
            },
            cost_usd:  cost,
            tags:      ['openai', model],
            timestamp: t0 / 1000,
          })

          return response
        } catch (err: any) {
          tm._bufferSpan({
            span_id: spanId, trace_id: traceId,
            project: tm.project, name: `openai/${model}`,
            input: inputText.slice(0, 2000), output: '',
            error: String(err?.message ?? err).slice(0, 500),
            duration_ms: Date.now() - t0, status: 'error',
            metadata: { model, provider: 'openai' },
            tags: ['openai', model], timestamp: t0 / 1000,
          })
          throw err
        }
      }
    }

    return new Proxy(client, {
      get(target, prop) {
        if (prop === 'chat') {
          return new Proxy(originalChat, {
            get(chatTarget, chatProp) {
              if (chatProp === 'completions') return wrappedCompletions
              return (chatTarget as any)[chatProp]
            }
          })
        }
        return (target as any)[prop]
      }
    })
  }

  // ── Decorator pattern ────────────────────────────────────────────────────

  trace<TArgs extends unknown[], TReturn>(
    name: string,
    fn:   (...args: TArgs) => Promise<TReturn>,
    tags: string[] = [],
  ): (...args: TArgs) => Promise<TReturn> {
    const tm = this
    return async function (...args: TArgs): Promise<TReturn> {
      const spanId  = randomId()
      const traceId = randomId()
      const t0      = Date.now()

      const inputRepr = JSON.stringify({
        args: args.map(a => String(a).slice(0, 500)),
      }).slice(0, 2000)

      try {
        const result   = await fn(...args)
        const duration = Date.now() - t0

        tm._bufferSpan({
          span_id:     spanId,
          trace_id:    traceId,
          project:     tm.project,
          name,
          input:       inputRepr,
          output:      String(result).slice(0, 2000),
          error:       '',
          duration_ms: duration,
          status:      'success',
          tags,
          timestamp:   t0 / 1000,
        })

        return result
      } catch (err: any) {
        tm._bufferSpan({
          span_id:     spanId,
          trace_id:    traceId,
          project:     tm.project,
          name,
          input:       inputRepr,
          output:      '',
          error:       String(err?.message ?? err).slice(0, 500),
          duration_ms: Date.now() - t0,
          status:      'error',
          tags,
          timestamp:   t0 / 1000,
        })
        throw err
      }
    }
  }

  // ── Context manager ──────────────────────────────────────────────────────

  span(name: string, input: Record<string, unknown> = {}): SpanContext {
    return new SpanContext(this, name, input)
  }

  streamSpan(name: string): StreamSpanContext {
    return new StreamSpanContext(this, name)
  }

  // ── Manual log ───────────────────────────────────────────────────────────

  log(params: {
    name:      string
    input:     string
    output:    string
    score?:    number
    metadata?: Record<string, unknown>
    traceId?:  string
    tags?:     string[]
  }): void {
    this._bufferSpan({
      span_id:     randomId(),
      trace_id:    params.traceId ?? randomId(),
      project:     this.project,
      name:        params.name,
      input:       params.input.slice(0, 2000),
      output:      params.output.slice(0, 2000),
      error:       '',
      duration_ms: 0,
      status:      'success',
      metadata:    {
        ...(params.metadata ?? {}),
        ...(params.score != null ? { manual_score: params.score } : {}),
      },
      tags:        params.tags ?? [],
      timestamp:   Date.now() / 1000,
    })
  }

  // ── Dataset ──────────────────────────────────────────────────────────────

  dataset(name: string): DatasetBuilder {
    return new DatasetBuilder(this, name)
  }

  // ── Eval ─────────────────────────────────────────────────────────────────

  async runEval(params: {
    datasetName:   string
    judgeCriteria?: string[]
    systemPrompt?:  string
    name?:          string
    gitCommit?:     string
  }): Promise<EvalRun> {
    const data = await this._request('POST', '/api/evals/run', {
      project:        this.project,
      dataset_name:   params.datasetName,
      judge_criteria: params.judgeCriteria ?? ['accurate', 'helpful'],
      system_prompt:  params.systemPrompt,
      name:           params.name,
      git_commit:     params.gitCommit,
    })
    return new EvalRun(data, this)
  }

  // ── Agent ─────────────────────────────────────────────────────────────────

  async ask(query: string, projectId?: string): Promise<string> {
    const projects = await this._request('GET', '/api/projects')
    const pid      = projectId ??
      projects.projects?.find((p: any) => p.name === this.project)?.id

    if (!pid) throw new Error(`Project '${this.project}' not found`)

    const run = await this._request('POST', '/api/agent/analyze', {
      project_id: pid,
      query,
    })

    // Poll for result
    const start = Date.now()
    while (Date.now() - start < 120_000) {
      const data = await this._request('GET', `/api/agent/runs/${run.run_id}`)
      if (data.status === 'completed') return data.answer ?? ''
      if (data.status === 'failed')    throw new Error(`Agent failed: ${data.error}`)
      await sleep(3000)
    }

    throw new Error('Agent timed out')
  }

  // ── Lifecycle ────────────────────────────────────────────────────────────

  async flush(): Promise<void> {
    await this._flush()
  }

  close(): void {
    if (this.flushTimer) {
      clearInterval(this.flushTimer)
      this.flushTimer = null
    }
    this._flush().catch(() => {})
  }

  // ── Internal ─────────────────────────────────────────────────────────────

  private _bufferSpan(span: Span): void {
    if (this.redactor) {
      span.input  = this.redactor.redact(span.input)
      span.output = this.redactor.redact(span.output)
      if (span.error) span.error = this.redactor.redact(span.error)
    }
    if (this.maskInputs)  span.input  = '[MASKED]'
    if (this.maskOutputs) span.output = '[MASKED]'

    this.buffer.push(span)
    if (this.buffer.length >= this.batchSize) {
      this._flush().catch(() => {})
    }
  }

  private async _flush(): Promise<void> {
    if (this.buffer.length === 0) return

    const batch   = this.buffer.splice(0, this.buffer.length)
    const url     = `${this.baseUrl}/api/traces/batch`

    try {
      const res = await fetch(url, {
        method:  'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type':  'application/json',
          'X-SDK-Version': '0.3.0',
          'X-SDK-Lang':    'typescript',
        },
        body: JSON.stringify({ spans: batch }),
        signal: AbortSignal.timeout(10_000),
      })

      if (this.debug) {
        console.log(`[TraceMind] Flushed ${batch.length} spans — ${res.status}`)
      }
    } catch (err) {
      // Never throw — observability must never crash the app
      if (this.debug) {
        console.debug('[TraceMind] Flush failed (non-fatal):', err)
      }
    }
  }

  private async _request(
    method: string,
    path:   string,
    body?:  unknown,
  ): Promise<any> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        'Authorization': `Bearer ${this.apiKey}`,
        'Content-Type':  'application/json',
      },
      body:   body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30_000),
    })

    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new Error(`TraceMind API error ${res.status}: ${text.slice(0, 200)}`)
    }

    return res.json()
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function randomId(): string {
  return Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2)
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export default TraceMind