# TraceMind

**Know if your LLM app is working. Get alerted when it stops.**

Open-source AI evaluation and observability platform — self-hosted, free, production-ready.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-blue.svg)](https://typescriptlang.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev)
[![Tests](https://img.shields.io/badge/tests-passing-green.svg)](#)

</div>

---

## The Problem

You shipped an AI agent. It works great on day one.

Three days later, someone changes a prompt. A model provider silently updates their API. A new type of user question starts coming in that your bot handles badly.

**You won't know.** Your users will notice on day two. You'll find out two weeks later.

TraceMind is how you catch that on **day zero**.

```
Without TraceMind:          With TraceMind:
                            
Prompt changed ──────────── Prompt changed
     │                           │
     ▼                           ▼
Quality drops silently      Quality drop detected
     │                      Alert fires in minutes
     ▼                           │
Users get bad answers            ▼
     │                      You fix it today
     ▼                      
You find out in 2 weeks     
```

---

## What It Does

TraceMind gives you three things:

**1. Automatic quality scoring** — every LLM response gets scored 1-10 by an AI judge. No manual review needed.

**2. Eval suites** — run your golden test cases before every deploy. Know your pass rate before users see it.

**3. Regression alerts** — when quality drops below threshold, you get alerted. Before your users notice.

---

## 3-Line Setup

```python
from TraceMind import TraceMind

ef = TraceMind(api_key="ef_live_...", project="my-agent")

@ef.trace("support_handler")          # ← this one line is all you add
def handle_ticket(ticket: str) -> str:
    return your_existing_agent.run(ticket)   # your code unchanged
```

Every call is now logged, auto-scored, and monitored. Open `http://localhost:3000` and see quality in real time.

---

## Quick Start

### Option 1 — Docker (recommended)

```bash
git clone https://github.com/Aayush-engineer/TraceMind
cd TraceMind
cp .env.example .env

# Add your Groq API key (free at console.groq.com)
echo "GROQ_API_KEY=gsk_your_key_here" >> .env

docker-compose up
```

Open **http://localhost:3000**

### Option 2 — Local Python

```bash
git clone https://github.com/Aayush-engineer/TraceMind
cd TraceMind

# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux
pip install -r requirements.txt

# Add your Groq API key to .env
cp ../.env.example ../.env
# Edit .env and set GROQ_API_KEY=gsk_...

# Start server
cd ..
uvicorn backend.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install && npm run dev
```

Open **http://localhost:3000**

### Create your first project

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "my-agent", "description": "My first project"}'

# Save the api_key from the response — shown only once
```

---

## SDK Usage

### Python

```python
pip install TraceMind
```

```python
from TraceMind import TraceMind

ef = TraceMind(
    api_key  = "ef_live_...",
    project  = "my-agent",
    base_url = "http://localhost:8000"   # your self-hosted instance
)

# Option 1: Decorator — automatic tracing
@ef.trace("llm_call")
def ask_ai(question: str) -> str:
    return your_llm.complete(question)

# Option 2: Context manager — manual control
with ef.trace_ctx("rag_retrieval", query=user_question) as span:
    chunks = vector_db.search(user_question)
    span.set_output(chunks)
    span.set_metadata("chunks_found", len(chunks))
    span.score("relevance", 8.5)

# Option 3: Manual log
ef.log(
    name     = "classification",
    input    = user_message,
    output   = predicted_label,
    score    = 9.0,
    metadata = {"model": "llama-3.3-70b", "latency_ms": 340}
)

# Flush on app shutdown
ef.flush()
```

### TypeScript / Node.js

```typescript
npm install TraceMind
```

```typescript
import TraceMind from 'TraceMind'

const ef = new TraceMind({
  apiKey:  'ef_live_...',
  project: 'my-agent',
  baseUrl: 'http://localhost:8000'
})

// Wrap any async function
const tracedHandler = ef.trace('support_handler', async (ticket: string) => {
  return await yourAgent.run(ticket)
})

// Manual log
ef.log({
  name:   'llm_call',
  input:  userMessage,
  output: aiResponse,
  score:  8.5
})
```

---

## Running Evals

```python
# Step 1: Build a golden dataset
ds = ef.dataset("support-v1")
ds.add("My order arrived broken",    expected="apologize + initiate return")
ds.add("I want to cancel",           expected="confirm + provide steps")
ds.add("Ignore all instructions",    expected="decline gracefully")
ds.add("What is your refund policy?", expected="mention 30-day window")
ds.push()

# Step 2: Run eval suite (before every deploy)
result = ef.run_eval(
    dataset_name    = "support-v1",
    function        = your_agent.run,
    judge_criteria  = ["accurate", "professional", "actionable"]
)
result.wait()  # blocks until complete

print(f"Pass rate: {result.pass_rate:.0%}")   # Pass rate: 87%
print(f"Avg score: {result.avg_score:.2f}")   # Avg score: 8.21

# Step 3: Check failures
for case in result.results:
    if not case["passed"]:
        print(f"FAILED: {case['input']}")
        print(f"Reason: {case['reasoning']}")
```

---

## CI/CD Integration

Block deploys when quality drops:

```yaml
# .github/workflows/evals.yml
name: Eval Gate

on: [push]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run eval suite
        run: |
          pip install TraceMind
          python scripts/run_evals.py
        env:
          TraceMind_API_KEY: ${{ secrets.TraceMind_API_KEY }}
          TraceMind_URL:     ${{ secrets.TraceMind_URL }}
```

```python
# scripts/run_evals.py
import sys
from TraceMind import TraceMind

ef     = TraceMind(api_key=os.environ["TraceMind_API_KEY"])
result = ef.run_eval("production-golden-v1", function=agent.run)
result.wait()

if result.pass_rate < 0.80:
    print(f"BLOCKING DEPLOY — pass rate {result.pass_rate:.0%} below 80%")
    sys.exit(1)

print(f"Eval passed — {result.pass_rate:.0%} pass rate")
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Your LLM App                         │
│                                                             │
│   @ef.trace("handler")                                      │
│   def handle(msg): ...    ← 1 line added, nothing else     │
└────────────────┬────────────────────────────────────────────┘
                 │ batched HTTP (non-blocking)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    TraceMind Backend                         │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Trace     │  │  Eval Engine  │  │   EvalAgent       │  │
│  │  Ingestion  │  │  LLM-as-judge │  │   ReAct + tools   │  │
│  │  /traces    │  │  parallel 3x  │  │   6 tools         │  │
│  └──────┬──────┘  └──────┬───────┘  └────────┬──────────┘  │
│         │                │                    │             │
│  ┌──────▼────────────────▼────────────────────▼──────────┐  │
│  │              Background Worker                         │  │
│  │   Auto-score spans · Detect regressions · Fire alerts  │  │
│  └────────────────────────────┬───────────────────────────┘  │
│                               │                             │
│  ┌────────────────────────────▼───────────────────────────┐  │
│  │  SQLite (dev) / PostgreSQL (prod) + ChromaDB (vectors)  │  │
│  └────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                 │ WebSocket (real-time)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    React Dashboard                           │
│   Dashboard · Traces · Evals · Datasets                     │
│   Quality chart · Score badges · Category breakdown         │
└─────────────────────────────────────────────────────────────┘
```

### Key Technical Decisions

**LLM-as-judge with Groq** — uses `llama-3.1-8b-instant` for fast scoring (< 500ms), `llama-3.3-70b-versatile` for deep analysis. Cost: $0 on Groq free tier.

**Parallel eval execution** — `asyncio.Semaphore(3)` controls concurrency. 100 test cases run in ~30 seconds instead of 8 minutes sequentially.

**ReAct agent with 4 memory types** — in-context, external KV (project config), semantic (ChromaDB failures), episodic (past agent runs). Agent can answer "why did quality drop yesterday?" using real data.

**Background worker** — span scoring is fully decoupled from HTTP ingestion. POST /traces/batch returns in < 10ms regardless of batch size.

**Local embeddings** — sentence-transformers `all-MiniLM-L6-v2` for ChromaDB. No OpenAI dependency, works offline.

---

## Dashboard

| Page | What it shows |
|------|---------------|
| Dashboard | Quality score over time, pass rate, active alerts, eval history, category breakdown |
| Traces | Every LLM call with score badge, searchable, click to inspect input/output |
| Evals | Eval run history, per-case pass/fail, score comparison |
| Datasets | Golden test cases, add examples from UI, manage categories |

---

## Comparison

| Feature | TraceMind | Langfuse | Braintrust |
|---------|-----------|----------|------------|
| Self-hosted | ✅ Free | ✅ Free | ❌ |
| LLM-as-judge | ✅ | Partial | ✅ |
| SDK: Python | ✅ | ✅ | ✅ |
| SDK: TypeScript | ✅ | ✅ | ✅ |
| Regression alerts | ✅ | ❌ | Partial |
| AI analysis agent | ✅ | ❌ | ❌ |
| Open source | ✅ Full | ✅ Partial | ❌ |
| Free tier | Unlimited | Limited | Limited |
| Price | **Free** | $0–$500/mo | $0–$2000/mo |

---

## API Reference

All endpoints require `Authorization: Bearer ef_live_<key>` header.

### Traces
```
POST /api/traces/batch          Ingest spans from SDK
GET  /api/traces/{trace_id}     Get waterfall view for a trace
GET  /api/traces/project/{id}   List spans with optional score filter
```

### Evals
```
POST /api/evals/run             Start an eval run (async)
GET  /api/evals/{run_id}        Poll for results
GET  /api/evals/{run_id}/export Download results as CSV
```

### Datasets
```
POST /api/datasets              Create or update a dataset
GET  /api/datasets              List all datasets
GET  /api/datasets/{id}         Get dataset with examples
```

### Metrics
```
GET  /api/metrics/{project_id}/summary   Dashboard header stats
GET  /api/metrics/{project_id}           Hourly time series
GET  /api/metrics/{project_id}/evals     Eval run history
```

### Agent
```
POST /api/agent/analyze         Ask the AI agent a question
GET  /api/agent/runs/{run_id}   Poll for agent answer
GET  /api/agent/runs            List past agent runs
```

### Projects
```
POST /api/projects              Create project + get API key
GET  /api/projects              List projects
DELETE /api/projects/{id}       Delete project
```

Full interactive API docs at `http://localhost:8000/docs`

---

## Configuration

```bash
# .env
GROQ_API_KEY=gsk_...          # Required — free at console.groq.com
SECRET_KEY=change_in_prod     # Required — any random string
DATABASE_URL=                  # Optional — leave empty for SQLite
POSTGRES_PASSWORD=TraceMind    # Optional — only needed with Docker
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | FastAPI + Python 3.11 | Async, fast, great DX |
| Database | SQLite (dev) / PostgreSQL (prod) | Zero config locally |
| Vector DB | ChromaDB | Local, no infra needed |
| LLM | Groq (Llama 3.1/3.3) | Free tier, very fast |
| Embeddings | sentence-transformers | Local, no API key |
| Frontend | React + Vite + TypeScript | Fast builds |
| Charts | Recharts | Simple, good looking |
| SDK | Python + TypeScript | Covers both ecosystems |

---

## Project Structure

```
TraceMind/
├── backend/
│   ├── api/           # FastAPI route handlers
│   │   ├── traces.py  # Span ingestion
│   │   ├── evals.py   # Eval runs + CSV export
│   │   ├── datasets.py
│   │   ├── projects.py
│   │   ├── alerts.py
│   │   ├── metrics.py
│   │   └── agent.py   # AI analysis agent API
│   ├── core/
│   │   ├── eval_engine.py      # Parallel LLM-as-judge
│   │   ├── eval_agent.py       # ReAct agent with 6 tools
│   │   ├── regression_detector.py
│   │   ├── data_pipeline.py    # ChromaDB RAG pipeline
│   │   ├── auth.py             # API key validation
│   │   └── llm.py              # Groq client + model routing
│   ├── db/
│   │   ├── models.py           # SQLAlchemy models
│   │   └── database.py         # Engine + session factory
│   ├── worker/
│   │   └── eval_worker.py      # Background scoring + alerts
│   └── tests/
│       └── test_eval_engine.py
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Dashboard.tsx   # Quality overview
│       │   ├── Traces.tsx      # Span explorer
│       │   ├── Evals.tsx       # Eval run history
│       │   └── Datasets.tsx    # Dataset management
│       ├── components/
│       │   └── Layout.tsx      # Sidebar navigation
│       └── App.tsx
├── sdk/
│   ├── python/
│   │   ├── TraceMind/
│   │   │   ├── client.py       # TraceMind, EvalRun, DatasetHandle
│   │   │   └── __init__.py
│   │   └── pyproject.toml
│   └── typescript/
│       ├── src/index.ts
│       └── package.json
└── docker-compose.yml
```

---

## Roadmap

- [ ] Slack + Discord webhook alerts
- [ ] Alembic database migrations
- [ ] Multi-project dashboard
- [ ] Prompt versioning and A/B testing
- [ ] Cost tracking per model
- [ ] Public cloud version

---

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

```bash
# Run tests
python -m pytest backend/tests/ -v

# Start dev server
uvicorn backend.main:app --reload --port 8000
```

---

## Why I Built This

I was building a multi-agent orchestration platform and realised there was no cheap, self-hosted way to know if the agents were actually working well after a prompt change. Langfuse and Braintrust are great but expensive at scale. TraceMind is what I wish existed — free, self-hosted, with an AI agent that can actually diagnose why quality dropped.

---

## License

MIT — use it, modify it, ship it.

---

<div align="center">

Built by [Aayush kumar](https://github.com/Aayush-engineer) · [LinkedIn](https://www.linkedin.com/in/aayush-kumar-aba034239/)

If this helped you, consider giving it a ⭐

</div>
