import os
import sys
import json
import time
import httpx

API_URL   = os.environ.get("TRACEMIND_API_URL", "https://tracemind.onrender.com")
API_KEY   = os.environ.get("TRACEMIND_API_KEY", "")
DATASET   = os.environ.get("DATASET_NAME",      "production-golden-v1")
THRESHOLD = float(os.environ.get("PASS_RATE_THRESHOLD", "0.80"))
CRITERIA  = os.environ.get("JUDGE_CRITERIA", "accurate,helpful,professional").split(",")
GIT_SHA   = os.environ.get("GITHUB_SHA", "local")[:8]

if not API_KEY:
    print("❌ TRACEMIND_API_KEY is not set")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type":  "application/json",
}

client = httpx.Client(base_url=API_URL, timeout=120, headers=headers)

print(f"\n{'='*54}")
print(f"  TraceMind Eval Gate")
print(f"  Commit:    {GIT_SHA}")
print(f"  Dataset:   {DATASET}")
print(f"  Threshold: {THRESHOLD:.0%}")
print(f"{'='*54}\n")


# ── Start eval run ─────────────────────────────────────────

print("Starting eval run...")
r = client.post("/api/evals/run", json={
    "dataset_name":   DATASET,
    "judge_criteria": CRITERIA,
    "name":           f"ci-{GIT_SHA}",
    "git_commit":     GIT_SHA,
})

if r.status_code != 200:
    print(f"❌ Failed to start eval: {r.status_code} {r.text[:200]}")
    sys.exit(1)

run_id = r.json()["run_id"]
print(f"  Run ID: {run_id}")


# ── Poll for completion ────────────────────────────────────

print("Waiting for eval to complete...")
start   = time.time()
timeout = 300  # 5 minutes max

while time.time() - start < timeout:
    data   = client.get(f"/api/evals/{run_id}").json()
    status = data.get("status", "")

    if status == "completed":
        break
    elif status == "failed":
        print(f"❌ Eval run failed")
        sys.exit(1)

    elapsed = int(time.time() - start)
    print(f"  [{elapsed}s] Status: {status}...")
    time.sleep(8)
else:
    print(f"❌ Eval timed out after {timeout}s")
    sys.exit(1)


# ── Analyze results ────────────────────────────────────────

pass_rate = float(data.get("pass_rate", 0))
avg_score = float(data.get("avg_score", 0))
total     = int(data.get("total",     0))
passed    = int(data.get("passed",    0))
failed    = int(data.get("failed",    0))
results   = data.get("results", [])

# Write results for artifact upload
with open("eval_results.json", "w") as f:
    json.dump({
        "run_id":    run_id,
        "git_sha":   GIT_SHA,
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "total":     total,
        "passed":    passed,
        "failed":    failed,
        "threshold": THRESHOLD,
        "blocked":   pass_rate < THRESHOLD,
    }, f, indent=2)

print(f"\n{'─'*54}")
print(f"  Results")
print(f"{'─'*54}")
print(f"  Pass rate:  {pass_rate:.1%} ({passed}/{total})")
print(f"  Avg score:  {avg_score:.2f}/10")
print(f"  Threshold:  {THRESHOLD:.1%}")

# Show failing cases
failures = [r for r in results if not r.get("passed")]
if failures:
    print(f"\n  Top failures ({len(failures)} total):")
    for f in sorted(failures, key=lambda x: x.get("score", 0))[:5]:
        score     = f.get("score", 0)
        input_txt = f.get("input",     "")[:60]
        reasoning = f.get("reasoning", "")[:80]
        print(f"  [{score:.1f}] {input_txt}")
        print(f"        → {reasoning}")

print(f"\n{'='*54}")

# ── Gate decision ──────────────────────────────────────────

if pass_rate >= THRESHOLD:
    print(f"  ✅ PASSED — {pass_rate:.1%} ≥ {THRESHOLD:.0%} threshold")
    print(f"  Deploy can proceed.")
    print(f"{'='*54}\n")
    sys.exit(0)
else:
    gap = THRESHOLD - pass_rate
    print(f"  ❌ BLOCKED — {pass_rate:.1%} < {THRESHOLD:.0%} threshold")
    print(f"  Need {gap:.1%} more cases to pass.")
    print(f"  Fix the failing cases above before deploying.")
    print(f"{'='*54}\n")
    sys.exit(1)