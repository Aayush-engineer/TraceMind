# Contributing to TraceMind

We welcome contributions of all kinds.

## Good first issues

Look for issues tagged `good first issue` on GitHub.
These are intentionally scoped to be completable in a few hours.

Current good first issues:
- Add `@ef.trace_async` decorator for async functions
- Add pagination to the Traces page (currently loads 50 at a time)
- Add a "copy as curl" button on the API docs page
- Write tests for the datasets API endpoints
- Add a favicon and app icon

## How to contribute

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Make your change
4. Write or update tests
5. Commit with conventional commits: `feat:`, `fix:`, `test:`, `docs:`
6. Push and open a PR

## Local setup

See README.md Quick Start section.
Tests: `python -m pytest backend/tests/ -v`

## What we need most

- **SDK improvements** — async support, better error messages
- **Tests** — we want to reach 80% coverage
- **Documentation** — examples for different LLM frameworks
- **Integrations** — LangChain, LlamaIndex, OpenAI SDK decorators

## Code style

Python: follow existing patterns, no linter enforced yet.
TypeScript: follow existing patterns.
Keep PRs focused — one feature per PR.