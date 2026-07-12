# Contributing to TraceMind

Thank you for your interest in contributing. This document explains how to get started, what we need most, and how to get your PR merged quickly.

---

## What we need most right now

If you're looking for a place to start, these are the highest-value contributions:

- **Ollama integration** — local LLM support so TraceMind works with zero external API dependencies
- **LangChain callback handler** — `TraceMindCallbackHandler` that integrates with any LangChain chain
- **LlamaIndex observer** — same for LlamaIndex pipelines  
- **Pagination on Traces page** — the frontend Traces page has no pagination yet
- **More eval criteria templates** — pre-built rubrics for common use cases (customer support, code review, RAG, summarization)
- **Tests to reach 80% coverage** — currently at ~65%

Check the [Issues](https://github.com/Aayush-engineer/tracemind/issues) tab for anything labeled `good first issue`.

---

## Development setup

**Requirements:** Python 3.11+, Node.js 18+, Docker (optional but recommended)

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/tracemind
cd tracemind

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env         # add GROQ_API_KEY

# 3. Run backend
uvicorn main:app --reload --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev

# 5. Verify everything works
cd ..
python verify_all.py
# Must show: 44/44 — 100%
```

---

## Running tests

```bash
cd backend
python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_eval_engine.py -v

# Run with coverage
python -m pytest tests/ --cov=. --cov-report=term-missing
```

All 137 tests must pass before submitting a PR. The CI will check this automatically.

---

## Project structure

```
tracemind/
├── backend/
│   ├── api/           # FastAPI route handlers
│   ├── core/          # Business logic (eval engine, agent, hallucination)
│   ├── db/            # SQLAlchemy models + Alembic migrations
│   ├── worker/        # Background scoring + regression detection
│   └── tests/         # pytest test suite
├── frontend/
│   └── src/
│       ├── pages/     # Dashboard, Traces, Evals, Datasets
│       └── components/
├── sdk/
│   ├── python/        # pip install tracemind-sdk
│   └── typescript/    # npm install tracemind-sdk
└── .github/
    └── workflows/     # CI + eval gate
```

---

## Making a database schema change

If your contribution changes a database model:

```bash
cd backend
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

Always include the generated migration file in your PR. Do not use `Base.metadata.create_all()` — we use Alembic for all schema changes.

---

## PR guidelines

**Keep PRs focused.** One feature or one fix per PR. A PR that adds LangChain integration and fixes a bug in the eval engine is two PRs.

**Write a clear description.** Explain what problem your PR solves, not just what it does technically. Link to the relevant issue if one exists.

**Test your change end-to-end.** Run `python verify_all.py` against a locally running server. If it adds new behavior, add a test for it.

**Update the README** if your change adds a user-facing feature or changes setup instructions.

---

## Code style

- Python: Black formatting, type hints on all function signatures, docstrings on public functions
- TypeScript: Prettier formatting, no `any` types
- Commit messages: `type: description` — e.g., `feat: add LangChain callback handler` or `fix: hallucination extraction returning 0 claims`

---

## Getting help

Open an issue with the `question` label. Response time is usually within 24 hours.

If you're building something significant, open an issue first to discuss the approach before investing time in the implementation. This prevents situations where a well-built PR can't be merged because it conflicts with planned architecture changes.

---

## License

By contributing, you agree that your contributions will be licensed under the MIT license.
