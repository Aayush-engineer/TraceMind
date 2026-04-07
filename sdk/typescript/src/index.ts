import fetch from 'node-fetch';
import { v4 as uuidv4 } from 'uuid';

interface TraceMindConfig {
  apiKey:   string;
  project:  string;
  baseUrl?: string;
  debug?:   boolean;
}

interface SpanData {
  spanId:     string;
  traceId:    string;
  project:    string;
  name:       string;
  input:      string;
  output:     string;
  error?:     string;
  durationMs: number;
  scores?:    Record<string, number>;
  metadata?:  Record<string, unknown>;
  status:     'success' | 'error';
  timestamp:  number;
}

export class TraceMind {
  private config:  TraceMindConfig;
  private buffer:  SpanData[] = [];
  private timer:   NodeJS.Timeout;

  constructor(config: TraceMindConfig) {
    this.config = { baseUrl: 'https://api.TraceMind.dev', ...config };

    // Flush every 5 seconds
    this.timer = setInterval(() => this.flush(), 5000);
    // Flush on process exit
    process.on('beforeExit', () => this.flush());
  }

  trace<T extends (...args: unknown[]) => Promise<unknown>>(
    name: string,
    fn: T
  ): T {
    const self = this;
    return (async (...args: unknown[]) => {
      const traceId = uuidv4();
      const spanId  = uuidv4();
      const t0      = Date.now();

      try {
        const result  = await fn(...args);
        const duration = Date.now() - t0;

        self.bufferSpan({
          spanId, traceId,
          project:    self.config.project,
          name,
          input:      JSON.stringify(args).slice(0, 2000),
          output:     JSON.stringify(result).slice(0, 2000),
          durationMs: duration,
          status:     'success',
          timestamp:  t0 / 1000
        });

        return result;
      } catch (err: unknown) {
        const duration = Date.now() - t0;
        self.bufferSpan({
          spanId, traceId,
          project:    self.config.project,
          name,
          input:      JSON.stringify(args).slice(0, 2000),
          output:     '',
          error:      String(err).slice(0, 500),
          durationMs: duration,
          status:     'error',
          timestamp:  t0 / 1000
        });
        throw err;
      }
    }) as T;
  }

  log(params: {
    name:     string;
    input:    string;
    output:   string;
    score?:   number;
    metadata?: Record<string, unknown>;
    traceId?: string;
  }) {
    this.bufferSpan({
      spanId:    uuidv4(),
      traceId:   params.traceId || uuidv4(),
      project:   this.config.project,
      name:      params.name,
      input:     params.input.slice(0, 2000),
      output:    params.output.slice(0, 2000),
      scores:    params.score != null ? { overall: params.score } : undefined,
      metadata:  params.metadata,
      durationMs: 0,
      status:    'success',
      timestamp: Date.now() / 1000
    });
  }

  private bufferSpan(span: SpanData) {
    this.buffer.push(span);
    if (this.buffer.length >= 20) {
      this.flush();
    }
  }

  async flush() {
    if (this.buffer.length === 0) return;
    const batch   = [...this.buffer];
    this.buffer   = [];

    try {
      await fetch(`${this.config.baseUrl}/api/traces/batch`, {
        method:  'POST',
        headers: {
          'Authorization': `Bearer ${this.config.apiKey}`,
          'Content-Type':  'application/json'
        },
        body: JSON.stringify({ spans: batch })
      });
    } catch {
      // Never crash user's app because of observability failure
    }
  }
}

export default TraceMind;