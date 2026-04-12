import asyncio
import json
import time
import uuid
import logging
import chromadb

from ..db.database import get_sync_db
from ..db.models   import (Dataset, DatasetExample, Span,
                            Project, Alert, AgentEpisode)
from .llm          import chat, embed

logger = logging.getLogger(__name__)

from .config import CHROMA_DIR
chroma = chromadb.PersistentClient(path=CHROMA_DIR)
failure_collection = chroma.get_or_create_collection("eval_failures")
pattern_collection = chroma.get_or_create_collection("failure_patterns")


EVAL_AGENT_TOOLS = [
    {
        "name": "run_targeted_eval",
        "description": "Run an evaluation on specific test cases or a full dataset. Use when you need to measure quality on a set of inputs. Returns: pass_rate, avg_score, per-case results with scores and reasoning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_name":    {"type": "string"},
                "filter_category": {"type": "string"},
                "system_prompt":   {"type": "string"},
                "judge_criteria":  {"type": "array", "items": {"type": "string"}}
            },
            "required": ["dataset_name"]
        }
    },
    {
        "name": "search_similar_failures",
        "description": "Search ChromaDB for past failures similar to the current problem. Use when you need to understand if this failure pattern has occurred before.",
        "input_schema": {
            "type": "object",
            "properties": {
                "failure_description": {"type": "string"},
                "limit":               {"type": "integer", "default": 5}
            },
            "required": ["failure_description"]
        }
    },
    {
        "name": "generate_test_cases",
        "description": "Generate new test cases based on a failure pattern or description. Use when you need more coverage for a specific failure mode.",
        "input_schema": {
            "type": "object",
            "properties": {
                "failure_pattern": {"type": "string"},
                "count":           {"type": "integer", "default": 5},
                "difficulty":      {"type": "string", "enum": ["easy", "medium", "hard", "adversarial"]},
                "add_to_dataset":  {"type": "string"}
            },
            "required": ["failure_pattern", "count"]
        }
    },
    {
        "name": "fetch_recent_traces",
        "description": "Fetch recent production traces from the database. Use to understand what real users are doing and where the system is failing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "hours":      {"type": "integer", "default": 24},
                "min_score":  {"type": "number",  "default": 6.0},
                "limit":      {"type": "integer", "default": 20}
            },
            "required": ["project_id"]
        }
    },
    {
        "name": "analyze_failure_pattern",
        "description": "Analyze a set of failing cases to identify the root cause. Use after fetching traces or running evals to understand WHY things are failing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "failing_cases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "input":  {"type": "string"},
                            "output": {"type": "string"},
                            "score":  {"type": "number"}
                        }
                    }
                },
                "context": {"type": "string"}
            },
            "required": ["failing_cases"]
        }
    },
    {
        "name": "send_alert",
        "description": "Send an alert about a quality regression or important finding.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "severity":   {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                "title":      {"type": "string"},
                "message":    {"type": "string"},
                "action":     {"type": "string"}
            },
            "required": ["project_id", "severity", "title", "message"]
        }
    }
]


async def execute_tool(name: str, inputs: dict, project_id: str) -> dict:
    if name == "run_targeted_eval":
        return await _run_targeted_eval(inputs, project_id)
    elif name == "search_similar_failures":
        return await _search_similar_failures(inputs)
    elif name == "generate_test_cases":
        return await _generate_test_cases(inputs, project_id)
    elif name == "fetch_recent_traces":
        return await _fetch_recent_traces(inputs)
    elif name == "analyze_failure_pattern":
        return await _analyze_failure_pattern(inputs)
    elif name == "send_alert":
        return await _send_alert(inputs)
    return {"error": f"Unknown tool: {name}"}


async def _run_targeted_eval(inputs: dict, project_id: str) -> dict:
    from .eval_engine import run_eval_parallel
    loop = asyncio.get_running_loop()

    def _fetch_examples():
        db = get_sync_db()
        try:
            dataset = db.query(Dataset).filter_by(
                name=inputs.get("dataset_name") or inputs.get("dataset") or inputs.get("name", "")
            ).first()
            if not dataset:
                return None
            examples = db.query(DatasetExample).filter_by(
                dataset_id=dataset.id
            ).all()
            return [
                {
                    "id":       e.id,
                    "input":    e.input,
                    "expected": e.expected,
                    "criteria": e.criteria or [],
                    "category": e.category
                }
                for e in examples
            ]
        finally:
            db.close()

    examples = await loop.run_in_executor(None, _fetch_examples)

    if examples is None:
        dataset_name = inputs.get("dataset_name") or inputs.get("dataset") or inputs.get("name", "unknown")
        return {"error": f"Dataset '{dataset_name}' not found"}
    if not examples:
        return {"error": "Dataset exists but has no examples"}

    if inputs.get("filter_category"):
        examples = [
            e for e in examples
            if e["category"] == inputs["filter_category"]
        ]

    system_prompt = inputs.get("system_prompt", "You are a helpful AI assistant.")

    def system_fn(input_text: str) -> str:
        return chat(
            messages   = [{"role": "user", "content": input_text}],
            system     = system_prompt,
            model      = "fast",
            max_tokens = 512
        )

    criteria = inputs.get("judge_criteria", ["quality", "accuracy", "helpfulness"])
    summary  = await run_eval_parallel(examples, system_fn, criteria)

    failures = [r for r in summary["results"] if not r["passed"]]
    if failures:
        await _index_failures_to_chromadb(failures, inputs.get("dataset_name", "unknown"))

    return {
        "pass_rate":   summary["pass_rate"],
        "avg_score":   summary["avg_score"],
        "total_cases": summary["total"],
        "passed":      summary["passed"],
        "failed":      summary["failed"],
        "top_failures": [
            {
                "input":     r["input"][:150],
                "score":     r["judge_score"],
                "reasoning": r["reasoning"][:200]
            }
            for r in sorted(
                summary["results"], key=lambda x: x["judge_score"]
            )[:3]
        ]
    }


async def _index_failures_to_chromadb(failures: list, dataset_name: str):
    loop = asyncio.get_running_loop()

    texts = [
        f"Input: {f['input'][:300]}\n"
        f"Output: {f['actual_output'][:300]}\n"
        f"Reason failed: {f['reasoning'][:200]}"
        for f in failures
    ]

    if not texts:
        return

    embeddings_list = await loop.run_in_executor(
        None, lambda: embed([t[:500] for t in texts])
    )

    ids        = []
    embeddings = []
    documents  = []
    metadatas  = []

    for i, (failure, embedding) in enumerate(zip(failures, embeddings_list)):
        ids.append(str(uuid.uuid4()))
        embeddings.append(embedding)
        documents.append(texts[i])
        metadatas.append({
            "dataset":   dataset_name,
            "score":     float(failure["judge_score"]),
            "timestamp": time.time(),
            "input":     failure["input"][:200],
            "reasoning": failure["reasoning"][:200]
        })

    failure_collection.upsert(
        ids       = ids,
        embeddings = embeddings,
        documents  = documents,
        metadatas  = metadatas
    )


async def _search_similar_failures(inputs: dict) -> dict:
    loop = asyncio.get_running_loop()

    description = (
        inputs.get("failure_description") or
        inputs.get("description") or
        inputs.get("query") or
        inputs.get("pattern") or
        str(inputs)[:500]
    )

    embeddings_list = await loop.run_in_executor(
        None, lambda: embed([description[:500]])
    )
    query_embedding = embeddings_list[0]

    count = failure_collection.count()
    limit = inputs.get("limit", 5)

    if count == 0:
        return {"found": 0, "message": "No past failures indexed yet."}

    results = failure_collection.query(
        query_embeddings = [query_embedding],
        n_results        = min(limit, count),
        include          = ["documents", "metadatas", "distances"]
    )

    similar = []
    if results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        ):
            similarity = round(1 - dist, 3)
            if similarity > 0.5:
                similar.append({
                    "similarity": similarity,
                    "input":      meta.get("input", "")[:150],
                    "reasoning":  meta.get("reasoning", "")[:200],
                    "score":      meta.get("score", 0),
                    "dataset":    meta.get("dataset", ""),
                    "days_ago":   round(
                        (time.time() - meta.get("timestamp", time.time())) / 86400,
                        1
                    )
                })

    if not similar:
        return {
            "found":   0,
            "message": "No similar past failures found. This may be a new pattern."
        }

    return {
        "found":   len(similar),
        "similar": similar,
        "insight": (
            f"Found {len(similar)} similar past failures. "
            f"Most similar ({similar[0]['similarity']:.0%} match) "
            f"occurred {similar[0]['days_ago']:.0f} days ago."
        )
    }


async def _generate_test_cases(inputs: dict, project_id: str) -> dict:
    loop       = asyncio.get_running_loop()
    difficulty = inputs.get("difficulty", "medium")

    diff_desc = {
        "easy":        "simple, clear inputs that should work",
        "medium":      "moderate complexity with some edge cases",
        "hard":        "complex inputs with multiple constraints",
        "adversarial": "inputs designed to probe system weaknesses"
    }.get(difficulty, "medium complexity")

    prompt = f"""Failure pattern to cover: {inputs['failure_pattern']}
Difficulty: {difficulty} — {diff_desc}
Count: {inputs.get('count', 5)}

Generate {inputs.get('count', 5)} test cases as a JSON array:
[{{
  "input":    "exact user message to test",
  "expected": "what a correct response should do",
  "criteria": ["criterion 1", "criterion 2"],
  "category": "single_word_category"
}}]"""

    def _generate():
        return chat(
            messages   = [{"role": "user", "content": prompt}],
            system     = "You generate test cases for AI evaluation datasets. "
                         "Return ONLY valid JSON array, no markdown, no explanation.",
            model      = "smart",
            max_tokens = 2000,
            json_mode  = False   
        )

    raw = await loop.run_in_executor(None, _generate)

    try:
        cleaned = raw.replace("```json", "").replace("```", "").strip()
        cases   = json.loads(cleaned)
        if not isinstance(cases, list):
            cases = []
    except json.JSONDecodeError:
        logger.warning(f"generate_test_cases: JSON parse failed: {raw[:200]}")
        cases = []

    if inputs.get("add_to_dataset") and cases:
        def _save():
            db = get_sync_db()
            try:
                dataset = db.query(Dataset).filter_by(
                    name=inputs["add_to_dataset"]
                ).first()
                if dataset:
                    for case in cases:
                        example = DatasetExample(
                            dataset_id = dataset.id,
                            input      = case.get("input", ""),
                            expected   = case.get("expected", ""),
                            criteria   = case.get("criteria", []),
                            category   = case.get("category", "generated"),
                            source     = "agent_generated"
                        )
                        db.add(example)
                    db.commit()
            finally:
                db.close()

        await loop.run_in_executor(None, _save)

    return {
        "generated":        len(cases),
        "cases":            cases[:5],
        "added_to_dataset": inputs.get("add_to_dataset") or "not saved"
    }


async def _fetch_recent_traces(inputs: dict) -> dict:
    loop = asyncio.get_running_loop()

    def _fetch():
        db    = get_sync_db()
        since = time.time() - inputs.get("hours", 24) * 3600
        limit = inputs.get("limit", 20)
        min_s = inputs.get("min_score", 6.0)
        try:
            spans = db.query(Span).filter(
                Span.project_id  == inputs["project_id"],
                Span.timestamp   >= since,
                Span.judge_score <  min_s
            ).order_by(Span.judge_score.asc()).limit(limit).all()

            return [
                {
                    "input":      s.input[:200],
                    "output":     s.output[:200],
                    "score":      s.judge_score,
                    "latency_ms": s.duration_ms,
                    "span_name":  s.name,
                    "error":      s.error[:100] if s.error else "",
                    "hours_ago":  round((time.time() - s.timestamp) / 3600, 1)
                }
                for s in spans
            ]
        finally:
            db.close()

    traces = await loop.run_in_executor(None, _fetch)

    if not traces:
        return {
            "found":   0,
            "message": f"No failing traces in last {inputs.get('hours', 24)} hours"
        }

    scored = [t for t in traces if t["score"] is not None]
    return {
        "found":   len(traces),
        "traces":  traces,
        "summary": (
            f"Found {len(traces)} low-quality traces. "
            f"Lowest score: {min(t['score'] for t in scored):.1f}"
            if scored else f"Found {len(traces)} traces with errors."
        )
    }


async def _analyze_failure_pattern(inputs: dict) -> dict:
    loop = asyncio.get_running_loop()

    failing    = inputs["failing_cases"]
    context    = inputs.get("context", "")
    cases_text = "\n\n".join([
        f"Input: {c.get('input', '')[:200]}\n"
        f"Output: {c.get('output', '')[:200]}\n"
        f"Score: {c.get('score', 0):.1f}"
        for c in failing[:10]
    ])

    prompt = f"""Analyze these failing AI system responses:

{cases_text}

Additional context: {context or 'None provided'}

Return ONLY this JSON (no markdown):
{{
  "pattern":        "what type of inputs are failing",
  "root_cause":     "why is the AI failing technically",
  "fix":            "what specific change would address this",
  "new_test_cases": ["input1", "input2"],
  "severity":       "low"
}}"""

    def _analyze():
        return chat(
            messages   = [{"role": "user", "content": prompt}],
            system     = "You are an expert AI system debugger. "
                         "Analyze failing cases and identify root causes. "
                         "Return ONLY valid JSON, no markdown.",
            model      = "smart",
            max_tokens = 800,
            json_mode  = True
        )

    raw = await loop.run_in_executor(None, _analyze)

    try:
        analysis = json.loads(raw.replace("```json", "").replace("```", "").strip())
    except json.JSONDecodeError:
        logger.warning(f"analyze_failure_pattern: JSON parse failed")
        analysis = {
            "pattern":    raw[:300],
            "root_cause": "See pattern",
            "fix":        "Review manually",
            "severity":   "medium"
        }

    try:
        pattern_text = (
            f"Pattern: {analysis.get('pattern', '')} "
            f"Root cause: {analysis.get('root_cause', '')}"
        )
        pattern_embedding = await loop.run_in_executor(
            None, lambda: embed([pattern_text[:500]])
        )
        pattern_collection.upsert(
            ids        = [str(uuid.uuid4())[:12]],
            embeddings = [pattern_embedding[0]],
            documents  = [pattern_text],
            metadatas  = [{
                "fix":       analysis.get("fix", ""),
                "severity":  analysis.get("severity", "medium"),
                "timestamp": time.time()
            }]
        )
    except Exception:
        pass  

    return analysis


async def _send_alert(inputs: dict) -> dict:
    import httpx
    loop     = asyncio.get_running_loop()
    alert_id = str(uuid.uuid4())[:12]

    def _save_and_get_webhook():
        db = get_sync_db()
        try:
            alert = Alert(
                id         = alert_id,
                project_id = inputs["project_id"],
                type       = "quality_regression",
                severity   = inputs["severity"],
                message    = f"{inputs['title']}: {inputs['message']}",
                resolved   = False,
            )
            db.add(alert)
            project = db.query(Project).filter_by(
                id=inputs["project_id"]
            ).first()
            webhook = project.webhook_url if project else None
            db.commit()
            return webhook
        finally:
            db.close()

    webhook_url = await loop.run_in_executor(None, _save_and_get_webhook)

    if webhook_url:
        try:
            is_slack = "hooks.slack.com" in webhook_url

            if is_slack:
                severity_emoji = {
                    "low": "🟡", "medium": "🟠",
                    "high": "🔴", "critical": "🚨"
                }.get(inputs["severity"], "⚠️")

                slack_payload = {
                    "text": f"{severity_emoji} *TraceMind Alert*",
                    "attachments": [{
                        "color":  "#e74c3c" if inputs["severity"] in ("high","critical") else "#f39c12",
                        "fields": [
                            {"title": "Title",    "value": inputs["title"],   "short": False},
                            {"title": "Severity", "value": inputs["severity"].upper(), "short": True},
                            {"title": "Message",  "value": inputs["message"], "short": False},
                            {"title": "Action",   "value": inputs.get("action", "Review dashboard"), "short": False}
                        ],
                        "footer": "TraceMind · AI Quality Monitoring",
                        "ts":     int(time.time())
                    }]
                }
                async with httpx.AsyncClient() as hc:
                    await hc.post(webhook_url, json=slack_payload, timeout=5.0)
            else:
                async with httpx.AsyncClient() as hc:
                    await hc.post(
                        webhook_url,
                        json={
                            "alert_id":   alert_id,
                            "project_id": inputs["project_id"],
                            "severity":   inputs["severity"],
                            "title":      inputs["title"],
                            "message":    inputs["message"],
                            "action":     inputs.get("action", ""),
                            "timestamp":  time.time()
                        },
                        timeout=5.0
                    )
        except Exception:
            pass

    return {
        "sent":     True,
        "alert_id": alert_id,
        "severity": inputs["severity"]
    }


class EvalAgent:

    SYSTEM_PROMPT = """You are TraceMind's AI quality analyst.
You have tools to investigate why AI systems fail and how to fix them.

When a user asks about quality problems:
1. THINK: What information do I need to understand this problem?
2. ACT: Use tools to gather that information
3. OBSERVE: What did the tool reveal?
4. REPEAT until you have enough to give a specific, actionable answer

Always check search_similar_failures first — this failure may have
occurred before with a known fix.

Be specific. Always generate new test cases for any failure pattern found."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.run_id     = str(uuid.uuid4())[:8]
        self._project_context = self._load_project_context()
        self._past_runs       = self._load_episodic_memory()

    def _load_project_context(self) -> str:
        db = get_sync_db()
        try:
            project = db.query(Project).filter_by(id=self.project_id).first()
            if project:
                return f"Project: {project.name}\nDescription: {project.description}"
            return f"Project ID: {self.project_id}"
        finally:
            db.close()

    def _load_episodic_memory(self) -> str:
        db = get_sync_db()
        try:
            episodes = db.query(AgentEpisode).filter_by(
                project_id=self.project_id
            ).order_by(AgentEpisode.timestamp.desc()).limit(5).all()

            if not episodes:
                return "No past agent runs found for this project."

            lines = ["Recent agent run history:"]
            for ep in episodes:
                lines.append(f"  - Query: {ep.query[:80]}")
                lines.append(f"    Answer: {ep.answer[:100]}")
            return "\n".join(lines)
        finally:
            db.close()

    async def run(self, user_query: str, max_iterations: int = 8) -> dict:
        loop        = asyncio.get_running_loop()
        steps_taken = []
        total_tokens = 0
        context     = ""

        tool_desc = "\n".join([
            f"- {t['name']}: {t['description'].split(chr(10))[0]}"
            for t in EVAL_AGENT_TOOLS
        ])

        system = f"""{self.SYSTEM_PROMPT}

{self._project_context}
{self._past_runs}

Available tools:
{tool_desc}

To use a tool write exactly:
TOOL: tool_name
INPUT: {{"key": "value"}}

When you have enough information write:
ANSWER: your detailed answer here"""

        messages = [{"role": "user", "content": user_query}]

        for iteration in range(max_iterations):
            if context:
                messages[-1]["content"] = (
                    f"{user_query}\n\nContext so far:\n{context}"
                )

            def _call():
                return chat(
                    messages   = messages,
                    system     = system,
                    model      = "smart",
                    max_tokens = 1500
                )

            response     = await loop.run_in_executor(None, _call)
            total_tokens += len(response.split()) * 2

            if "TOOL:" in response and "INPUT:" in response:
                try:
                    tool_name  = response.split("TOOL:")[1].split("\n")[0].strip()
                    input_line = response.split("INPUT:")[1].split("\n")[0].strip()
                    tool_input = json.loads(input_line)
                except Exception as e:
                    context += f"\nStep {iteration+1}: Parse error ({e}), retrying...\n"
                    continue

                t0      = time.time()
                result  = await execute_tool(tool_name, tool_input, self.project_id)
                elapsed = round((time.time() - t0) * 1000)

                steps_taken.append({
                    "tool":    tool_name,
                    "input":   tool_input,
                    "latency": elapsed,
                    "success": "error" not in result
                })

                context += (
                    f"\nStep {iteration+1}: Used {tool_name}\n"
                    f"Result: {json.dumps(result)[:500]}\n"
                )

            elif "ANSWER:" in response:
                final = response.split("ANSWER:")[1].strip()
                self._save_episode(user_query, steps_taken, final, total_tokens)
                return {
                    "answer":      final,
                    "steps_taken": steps_taken,
                    "iterations":  iteration + 1,
                    "tokens_used": total_tokens,
                    "run_id":      self.run_id
                }

            else:
                context += f"\nThinking: {response[:300]}\n"

        final = f"Analysis incomplete after {max_iterations} steps."
        self._save_episode(user_query, steps_taken, final, total_tokens)
        return {
            "answer":      final,
            "steps_taken": steps_taken,
            "iterations":  max_iterations,
            "tokens_used": total_tokens,
            "run_id":      self.run_id
        }

    def _save_episode(self, query: str, steps: list,
                      answer: str, tokens_used: int):
        db = get_sync_db()
        try:
            episode = AgentEpisode(
                id          = self.run_id,
                project_id  = self.project_id,
                query       = query[:300],
                steps_json  = json.dumps(steps),
                answer      = answer[:500],
                tokens_used = tokens_used,
                iterations  = len(steps),
                timestamp   = time.time()
            )
            db.add(episode)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to save agent episode")
        finally:
            db.close()


