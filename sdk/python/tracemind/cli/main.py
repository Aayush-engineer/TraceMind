"""
sdk/python/tracemind/cli/main.py — Gap 6 fix.

Thin Click CLI wrapping the SDK.
Installs as: tracemind <command>

Usage:
    tracemind project create my-support-bot
    tracemind eval run --dataset support-v1 --criteria accurate,helpful
    tracemind eval status <run_id>
    tracemind dataset push examples.json
    tracemind agent ask "Why did quality drop yesterday?"
    tracemind hallucination check --question "..." --response "..."

Install:
    pip install tracemind-sdk
    # Then: tracemind --help

Setup (once):
    export TRACEMIND_API_KEY=ef_live_...
    export TRACEMIND_BASE_URL=https://tracemind.onrender.com
    export TRACEMIND_PROJECT=my-project
"""

import os
import sys
import json
import time

try:
    import click
    import httpx
except ImportError:
    print("Error: click and httpx required. Run: pip install click httpx")
    sys.exit(1)


# ── Config from env ───────────────────────────────────────────────────────

def _get_config() -> dict:
    api_key  = os.getenv("TRACEMIND_API_KEY", "")
    base_url = os.getenv("TRACEMIND_BASE_URL", "https://tracemind.onrender.com").rstrip("/")
    project  = os.getenv("TRACEMIND_PROJECT", "")
    return {"api_key": api_key, "base_url": base_url, "project": project}


def _client(cfg: dict) -> httpx.Client:
    if not cfg["api_key"]:
        click.echo("Error: TRACEMIND_API_KEY not set. Run: export TRACEMIND_API_KEY=ef_live_...")
        sys.exit(1)
    return httpx.Client(
        base_url = cfg["base_url"],
        headers  = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"},
        timeout  = 120,
    )


def _print_json(data: dict) -> None:
    click.echo(json.dumps(data, indent=2))


# ── Root CLI group ────────────────────────────────────────────────────────

@click.group()
@click.version_option(version="0.3.0", prog_name="tracemind")
def cli() -> None:
    """TraceMind — LLM quality monitoring CLI."""
    pass


# ── tracemind project ─────────────────────────────────────────────────────

@cli.group()
def project() -> None:
    """Manage projects."""
    pass


@project.command("create")
@click.argument("name")
@click.option("--description", "-d", default="", help="Project description")
def project_create(name: str, description: str) -> None:
    """Create a new project and print the API key."""
    cfg = _get_config()
    # project creation does not require auth
    r = httpx.post(
        f"{cfg['base_url']}/api/projects",
        json    = {"name": name, "description": description},
        timeout = 15,
    )
    if r.status_code == 201:
        data = r.json()
        click.echo(f"✓ Project created: {data['name']}")
        click.echo(f"  ID:      {data['id']}")
        click.echo(f"  API Key: {data['api_key']}")
        click.echo(f"\nSet env vars:")
        click.echo(f"  export TRACEMIND_API_KEY={data['api_key']}")
        click.echo(f"  export TRACEMIND_PROJECT={data['name']}")
    else:
        click.echo(f"Error {r.status_code}: {r.text[:200]}")
        sys.exit(1)


@project.command("list")
def project_list() -> None:
    """List all projects."""
    cfg = _get_config()
    with _client(cfg) as client:
        r = client.get("/api/projects")
    if r.status_code == 200:
        projects = r.json()
        if not projects:
            click.echo("No projects found.")
            return
        for p in projects:
            click.echo(f"  {p['id']}  {p['name']:<30}  {p.get('span_count', 0)} spans")
    else:
        click.echo(f"Error: {r.text[:200]}")
        sys.exit(1)


# ── tracemind eval ────────────────────────────────────────────────────────

@cli.group()
def eval() -> None:
    """Run and inspect evaluations."""
    pass


@eval.command("run")
@click.option("--dataset",   "-d", required=True, help="Dataset name")
@click.option("--criteria",  "-c", default="accurate,helpful", help="Comma-separated judge criteria")
@click.option("--threshold", "-t", default=0.80,  help="Pass rate threshold (0-1)", type=float)
@click.option("--project",   "-p", default=None,  help="Project name (overrides env)")
@click.option("--wait/--no-wait", default=True,   help="Wait for completion and print results")
def eval_run(dataset: str, criteria: str, threshold: float,
             project: str | None, wait: bool) -> None:
    """
    Run an evaluation against a golden dataset.

    Example:
        tracemind eval run --dataset support-v1 --criteria accurate,helpful,safe

    In GitHub Actions:
        tracemind eval run --dataset support-v1 --threshold 0.80
        # Exits with code 1 if pass rate < threshold (blocks deploy)
    """
    cfg = _get_config()
    project_name = project or cfg["project"]
    if not project_name:
        click.echo("Error: project required. Set TRACEMIND_PROJECT or use --project")
        sys.exit(1)

    criteria_list = [c.strip() for c in criteria.split(",")]

    with _client(cfg) as client:
        r = client.post("/api/evals/run", json={
            "project":        project_name,
            "dataset_name":   dataset,
            "judge_criteria": criteria_list,
            "name":           f"cli-{int(time.time())}",
        })

    if r.status_code != 200:
        click.echo(f"Error starting eval: {r.text[:200]}")
        sys.exit(1)

    run_id = r.json()["run_id"]
    click.echo(f"✓ Eval started: {run_id}")

    if not wait:
        click.echo(f"  Track: tracemind eval status {run_id}")
        return

    # Poll for completion
    click.echo("  Waiting for completion...", nl=False)
    start = time.time()

    with _client(cfg) as client:
        while time.time() - start < 300:
            time.sleep(5)
            r = client.get(f"/api/evals/{run_id}")
            data = r.json()
            status = data.get("status", "")
            click.echo(".", nl=False)

            if status == "completed":
                break
            elif status == "failed":
                click.echo(f"\nEval failed")
                sys.exit(1)
        else:
            click.echo(f"\nTimeout after 5 minutes")
            sys.exit(1)

    click.echo()
    pass_rate = data.get("pass_rate", 0)
    avg_score = data.get("avg_score", 0)
    total     = data.get("total", 0)
    passed    = data.get("passed", 0)
    ci        = data.get("pass_rate_display", f"{pass_rate:.0%}")

    click.echo(f"\n{'='*50}")
    click.echo(f"  Results — {dataset}")
    click.echo(f"{'='*50}")
    click.echo(f"  Pass rate:  {ci}  ({passed}/{total})")
    click.echo(f"  Avg score:  {avg_score:.2f}/10")
    click.echo(f"  Threshold:  {threshold:.0%}")

    # Print top failures
    failures = [r for r in data.get("results", []) if not r.get("passed")]
    if failures:
        click.echo(f"\n  Top failures ({len(failures)} total):")
        for f in sorted(failures, key=lambda x: x.get("judge_score", 0))[:5]:
            score     = f.get("judge_score", 0)
            inp       = f.get("input", "")[:60]
            reasoning = f.get("reasoning", "")[:80]
            click.echo(f"  [{score:.1f}] {inp}")
            if reasoning:
                click.echo(f"         → {reasoning}")

    click.echo(f"\n{'='*50}")

    if pass_rate >= threshold:
        click.echo(f"  ✅ PASSED — {pass_rate:.0%} ≥ {threshold:.0%}")
        sys.exit(0)
    else:
        click.echo(f"  ❌ BLOCKED — {pass_rate:.0%} < {threshold:.0%}")
        sys.exit(1)


@eval.command("status")
@click.argument("run_id")
def eval_status(run_id: str) -> None:
    """Check the status of an eval run."""
    cfg = _get_config()
    with _client(cfg) as client:
        r = client.get(f"/api/evals/{run_id}")
    if r.status_code == 200:
        data = r.json()
        click.echo(f"Status:    {data.get('status', '?')}")
        click.echo(f"Pass rate: {data.get('pass_rate', 0):.0%}")
        click.echo(f"Avg score: {data.get('avg_score', 0):.2f}/10")
        click.echo(f"Cases:     {data.get('total', 0)}")
    elif r.status_code == 404:
        click.echo(f"Eval run '{run_id}' not found")
        sys.exit(1)
    else:
        click.echo(f"Error: {r.text[:200]}")
        sys.exit(1)


# ── tracemind dataset ─────────────────────────────────────────────────────

@cli.group()
def dataset() -> None:
    """Manage golden datasets."""
    pass


@dataset.command("push")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", "-n", default=None, help="Dataset name (default: filename without extension)")
@click.option("--project", "-p", default=None)
def dataset_push(file: str, name: str | None, project: str | None) -> None:
    """
    Push a JSON dataset file to TraceMind.

    File format:
        [
          {
            "input": "question here",
            "expected": "correct answer",
            "criteria": ["accurate", "helpful"],
            "category": "policy"
          }
        ]
    """
    import pathlib

    cfg          = _get_config()
    project_name = project or cfg["project"]
    dataset_name = name or pathlib.Path(file).stem

    with open(file) as f:
        examples = json.load(f)

    if not isinstance(examples, list):
        click.echo("Error: file must contain a JSON array of examples")
        sys.exit(1)

    with _client(cfg) as client:
        r = client.post("/api/datasets", json={
            "name":        dataset_name,
            "description": f"Uploaded from {file}",
            "project":     project_name,
            "examples":    examples,
        })

    if r.status_code == 201:
        data = r.json()
        click.echo(f"✓ Dataset created: {data['name']}")
        click.echo(f"  ID:       {data['id']}")
        click.echo(f"  Examples: {len(examples)}")
    else:
        click.echo(f"Error {r.status_code}: {r.text[:200]}")
        sys.exit(1)


@dataset.command("list")
def dataset_list() -> None:
    """List all datasets in the current project."""
    cfg = _get_config()
    with _client(cfg) as client:
        r = client.get("/api/datasets")
    if r.status_code == 200:
        datasets = r.json()
        for d in datasets:
            click.echo(f"  {d['id']}  {d['name']:<30}  {d.get('example_count', 0)} examples")
    else:
        click.echo(f"Error: {r.text[:200]}")
        sys.exit(1)


# ── tracemind agent ───────────────────────────────────────────────────────

@cli.group()
def agent() -> None:
    """Run diagnostic investigations."""
    pass


@agent.command("ask")
@click.argument("query")
@click.option("--project", "-p", default=None)
def agent_ask(query: str, project: str | None) -> None:
    """
    Ask the diagnostic agent why quality dropped.

    Example:
        tracemind agent ask "Why did quality drop in the last 6 hours?"
    """
    cfg          = _get_config()
    project_name = project or cfg["project"]
    if not project_name:
        click.echo("Error: project required. Set TRACEMIND_PROJECT or use --project")
        sys.exit(1)

    with _client(cfg) as client:
        r = client.post("/api/agent/analyze", json={
            "project_id": project_name,
            "query":      query,
        })

    if r.status_code != 200:
        click.echo(f"Error: {r.text[:200]}")
        sys.exit(1)

    run_id = r.json().get("run_id")
    click.echo(f"✓ Investigation started: {run_id}")
    click.echo("  Investigating...", nl=False)

    start = time.time()
    with _client(cfg) as client:
        while time.time() - start < 120:
            time.sleep(3)
            r = client.get(f"/api/agent/runs/{run_id}")
            data = r.json()
            status = data.get("status", "")
            click.echo(".", nl=False)
            if status in ("completed", "failed"):
                break

    click.echo()
    click.echo(f"\n{'='*50}")
    click.echo(f"  Root Cause Analysis")
    click.echo(f"{'='*50}")
    click.echo(data.get("diagnosis", "No diagnosis available"))

    steps = data.get("steps_taken", [])
    if steps:
        click.echo(f"\n  Steps ({len(steps)} tool calls):")
        for step in steps:
            click.echo(f"  → {step.get('tool', '?')}: {str(step.get('result', ''))[:80]}")


# ── tracemind hallucination ───────────────────────────────────────────────

@cli.group()
def hallucination() -> None:
    """Check responses for hallucinations."""
    pass


@hallucination.command("check")
@click.option("--question", "-q", required=True)
@click.option("--response", "-r", required=True)
@click.option("--context",  "-c", default="")
def hallucination_check(question: str, response: str, context: str) -> None:
    """Check a response for hallucinations."""
    cfg = _get_config()
    with _client(cfg) as client:
        r = client.post("/api/hallucination/check", json={
            "question":  question,
            "response":  response,
            "context":   context,
            "fast_mode": False,
        })

    if r.status_code != 200:
        click.echo(f"Error: {r.text[:200]}")
        sys.exit(1)

    data = r.json()
    risk = data.get("overall_risk", "unknown")
    click.echo(f"Risk level: {risk.upper()}")
    click.echo(f"Score:      {data.get('hallucination_score', 0):.1f}/10")
    click.echo(f"Claims:     {data.get('total_claims', 0)}")
    click.echo(f"Summary:    {data.get('summary', '')}")

    claims = data.get("claims", [])
    if claims:
        click.echo("\nClaims:")
        for c in claims:
            marker = "⚠" if c.get("type") != "none" else "✓"
            click.echo(f"  {marker} [{c.get('type','none').upper()}] {c.get('text','')[:80]}")
            if c.get("evidence"):
                click.echo(f"    Evidence: {c['evidence'][:80]}")


# ── Entry point ───────────────────────────────────────────────────────────

def main() -> None:
    cli()


if __name__ == "__main__":
    main()