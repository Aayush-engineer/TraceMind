# Changelog

## [0.1.0] — 2026-04-08

### Added
- FastAPI backend with parallel LLM-as-judge eval engine
- ReAct agent with 4 memory types (in-context, KV, semantic, episodic)
- React dashboard — Dashboard, Traces, Evals, Datasets pages
- Python SDK with decorator, context manager, and manual log patterns
- TypeScript/Node.js SDK
- Background worker for async span scoring
- ChromaDB semantic search over past failures
- API key authentication on all endpoints
- WebSocket real-time dashboard updates
- Regression detection with configurable thresholds
- Alembic database migrations
- Rate limiting (slowapi)
- CSV export for eval results
- Slack webhook alerts
- 50 tests with GitHub Actions CI