"""
backend/tests/test_eval_agent_function_calling.py

Tests for EvalAgent native function-calling migration.

Verifies:
- Provider dispatch (anthropic → openai → groq priority)
- Output structure identical across all three providers
- Tool execution called with correct arguments
- Max iterations respected on all providers
- Parse failures handled gracefully in groq text path
- _save_episode called on every exit path
- _parse_tool_call handles all edge cases
"""

import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, call


# ── Helpers ───────────────────────────────────────────────────────────────

def _make_agent(project_id: str = "test_proj") -> "EvalAgent":
    """
    Build a minimal EvalAgent without hitting DB or real HTTP.
    Bypasses __init__ to avoid needing a real server.
    """
    from backend.core.eval_agent import EvalAgent

    agent = EvalAgent.__new__(EvalAgent)
    agent.project_id       = project_id
    agent.run_id           = "test_run_001"
    agent._project_context = "Project: test-project"
    agent._past_runs       = ""
    return agent


def _expected_keys() -> set:
    return {"answer", "steps_taken", "iterations", "tokens_used", "run_id"}


def _good_return() -> dict:
    return {
        "answer":      "Analysis complete.",
        "steps_taken": [],
        "iterations":  1,
        "tokens_used": 50,
        "run_id":      "test_run_001",
    }


def _run(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── TestProviderDispatch ──────────────────────────────────────────────────

class TestProviderDispatch:

    def test_uses_anthropic_when_key_set(self):
        """Anthropic is chosen when ANTHROPIC_API_KEY is present."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY":    "",
        }):
            with patch.object(agent, "_run_anthropic",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_ant, \
                 patch.object(agent, "_run_openai",
                              new_callable=AsyncMock) as mock_oai, \
                 patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock) as mock_groq:

                _run(agent.run("test query"))

                mock_ant.assert_called_once()
                mock_oai.assert_not_called()
                mock_groq.assert_not_called()

    def test_uses_openai_when_no_anthropic_key(self):
        """OpenAI is chosen when ANTHROPIC_API_KEY is absent."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY":    "sk-test",
        }):
            with patch.object(agent, "_run_anthropic",
                              new_callable=AsyncMock) as mock_ant, \
                 patch.object(agent, "_run_openai",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_oai, \
                 patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock) as mock_groq:

                _run(agent.run("test query"))

                mock_ant.assert_not_called()
                mock_oai.assert_called_once()
                mock_groq.assert_not_called()

    def test_uses_groq_when_no_api_keys(self):
        """Groq text fallback chosen when neither Anthropic nor OpenAI key set."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY":    "",
        }):
            with patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_groq:

                _run(agent.run("test query"))
                mock_groq.assert_called_once()

    def test_falls_back_to_groq_when_anthropic_raises(self):
        """If Anthropic raises, fallback to groq text automatically."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY":    "",
        }):
            with patch.object(agent, "_run_anthropic",
                              new_callable=AsyncMock,
                              side_effect=Exception("API error")), \
                 patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_fallback:

                result = _run(agent.run("test query"))
                mock_fallback.assert_called_once()
                assert result["answer"] == "Analysis complete."

    def test_falls_back_to_groq_when_anthropic_import_error(self):
        """ImportError from missing anthropic package triggers fallback."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY":    "",
        }):
            with patch.object(agent, "_run_anthropic",
                              new_callable=AsyncMock,
                              side_effect=ImportError("No module named 'anthropic'")), \
                 patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_fallback:

                _run(agent.run("test query"))
                mock_fallback.assert_called_once()

    def test_falls_back_to_groq_when_openai_raises(self):
        """If OpenAI raises, fallback to groq text."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY":    "sk-test",
        }):
            with patch.object(agent, "_run_openai",
                              new_callable=AsyncMock,
                              side_effect=Exception("rate limit")), \
                 patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_fallback:

                _run(agent.run("test query"))
                mock_fallback.assert_called_once()

    def test_whitespace_only_key_treated_as_absent(self):
        """A key containing only whitespace is treated as not set."""
        agent = _make_agent()
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "   ",
            "OPENAI_API_KEY":    "   ",
        }):
            with patch.object(agent, "_run_groq_text",
                              new_callable=AsyncMock,
                              return_value=_good_return()) as mock_groq:

                _run(agent.run("test query"))
                mock_groq.assert_called_once()


# ── TestOutputStructure ───────────────────────────────────────────────────

class TestOutputStructure:

    # ── Anthropic ──────────────────────────────────────────────────────────

    def _ant_end_turn_response(self, text: str = "Here is my analysis."):
        block       = MagicMock()
        block.type  = "text"
        block.text  = text
        resp        = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content     = [block]
        resp.usage       = MagicMock(input_tokens=100, output_tokens=50)
        return resp

    def test_anthropic_output_has_all_required_keys(self):
        agent    = _make_agent()
        mock_resp = self._ant_end_turn_response()

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            with patch.object(agent, "_save_episode"):
                result = _run(agent._run_anthropic("test", 8))

        assert _expected_keys().issubset(result.keys())

    def test_anthropic_output_types_are_correct(self):
        agent    = _make_agent()
        mock_resp = self._ant_end_turn_response()

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            with patch.object(agent, "_save_episode"):
                result = _run(agent._run_anthropic("test", 8))

        assert isinstance(result["answer"],      str)
        assert isinstance(result["steps_taken"], list)
        assert isinstance(result["iterations"],  int)
        assert isinstance(result["tokens_used"], int)
        assert isinstance(result["run_id"],      str)

    def test_anthropic_returns_answer_text(self):
        agent    = _make_agent()
        mock_resp = self._ant_end_turn_response("Quality dropped due to prompt change.")

        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = mock_resp

            with patch.object(agent, "_save_episode"):
                result = _run(agent._run_anthropic("test", 8))

        assert result["answer"] == "Quality dropped due to prompt change."

    # ── OpenAI ────────────────────────────────────────────────────────────

    def _oai_response(self, content: str = "Analysis complete.", tool_calls=None):
        msg            = MagicMock()
        msg.content    = content
        msg.tool_calls = tool_calls
        choice         = MagicMock()
        choice.message = msg
        resp           = MagicMock()
        resp.choices   = [choice]
        resp.usage     = MagicMock(prompt_tokens=80, completion_tokens=40)
        return resp

    def test_openai_output_has_all_required_keys(self):
        agent    = _make_agent()
        mock_resp = self._oai_response()

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            with patch.object(agent, "_save_episode"):
                result = _run(agent._run_openai("test", 8))

        assert _expected_keys().issubset(result.keys())

    def test_openai_output_types_are_correct(self):
        agent    = _make_agent()
        mock_resp = self._oai_response()

        with patch("openai.OpenAI") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_resp

            with patch.object(agent, "_save_episode"):
                result = _run(agent._run_openai("test", 8))

        assert isinstance(result["answer"],      str)
        assert isinstance(result["steps_taken"], list)
        assert isinstance(result["iterations"],  int)
        assert isinstance(result["tokens_used"], int)

    # ── Groq text ─────────────────────────────────────────────────────────

    def test_groq_text_output_has_all_required_keys(self):
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="ANSWER: Analysis complete."), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", 8))

        assert _expected_keys().issubset(result.keys())

    def test_groq_text_output_types_are_correct(self):
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="ANSWER: Done."), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", 8))

        assert isinstance(result["answer"],      str)
        assert isinstance(result["steps_taken"], list)
        assert isinstance(result["iterations"],  int)
        assert isinstance(result["tokens_used"], int)
        assert isinstance(result["run_id"],      str)

    def test_run_id_matches_agent_run_id_across_providers(self):
        """run_id in output always matches agent.run_id."""
        agent         = _make_agent()
        agent.run_id  = "specific_run_999"

        with patch("backend.core.eval_agent.chat",
                   return_value="ANSWER: Done."), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", 8))

        assert result["run_id"] == "specific_run_999"


# ── TestToolExecution ─────────────────────────────────────────────────────

class TestToolExecution:

    def test_anthropic_calls_execute_tool_on_tool_use(self):
        """execute_tool called with correct args when Anthropic returns tool_use."""
        agent = _make_agent()

        tool_block       = MagicMock()
        tool_block.type  = "tool_use"
        tool_block.id    = "tool_abc"
        tool_block.name  = "fetch_recent_traces"
        tool_block.input = {"project_id": "test_proj", "hours": 24}

        resp1             = MagicMock()
        resp1.stop_reason = "tool_use"
        resp1.content     = [tool_block]
        resp1.usage       = MagicMock(input_tokens=50, output_tokens=20)

        text_block       = MagicMock()
        text_block.type  = "text"
        text_block.text  = "Found issues."
        resp2             = MagicMock()
        resp2.stop_reason = "end_turn"
        resp2.content     = [text_block]
        resp2.usage       = MagicMock(input_tokens=80, output_tokens=30)

        with patch("anthropic.Anthropic") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock,
                   return_value={"traces": [], "count": 0}) as mock_exec, \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [resp1, resp2]

            result = _run(agent._run_anthropic("find failing traces", 8))

        mock_exec.assert_called_once_with(
            "fetch_recent_traces",
            {"project_id": "test_proj", "hours": 24},
            "test_proj",
        )
        assert len(result["steps_taken"]) == 1
        assert result["steps_taken"][0]["tool"] == "fetch_recent_traces"

    def test_anthropic_steps_taken_has_success_flag(self):
        """steps_taken entries include success field."""
        agent = _make_agent()

        tool_block       = MagicMock()
        tool_block.type  = "tool_use"
        tool_block.id    = "t1"
        tool_block.name  = "fetch_recent_traces"
        tool_block.input = {"project_id": "x"}

        resp1             = MagicMock()
        resp1.stop_reason = "tool_use"
        resp1.content     = [tool_block]
        resp1.usage       = MagicMock(input_tokens=50, output_tokens=20)

        text_block       = MagicMock()
        text_block.type  = "text"
        text_block.text  = "Done."
        resp2             = MagicMock()
        resp2.stop_reason = "end_turn"
        resp2.content     = [text_block]
        resp2.usage       = MagicMock(input_tokens=60, output_tokens=25)

        with patch("anthropic.Anthropic") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock,
                   return_value={"found": 3}), \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [resp1, resp2]

            result = _run(agent._run_anthropic("test", 8))

        step = result["steps_taken"][0]
        assert "success" in step
        assert "latency" in step
        assert "tool"    in step
        assert "input"   in step

    def test_openai_calls_execute_tool_on_function_call(self):
        """execute_tool called when OpenAI returns tool_calls."""
        agent = _make_agent()

        tool_call           = MagicMock()
        tool_call.id        = "call_abc"
        tool_call.function  = MagicMock()
        tool_call.function.name      = "analyze_failure_pattern"
        tool_call.function.arguments = json.dumps({"pattern": "policy errors"})

        msg1            = MagicMock()
        msg1.content    = None
        msg1.tool_calls = [tool_call]

        msg2            = MagicMock()
        msg2.content    = "Root cause identified."
        msg2.tool_calls = None

        resp1          = MagicMock()
        resp1.choices  = [MagicMock(message=msg1)]
        resp1.usage    = MagicMock(prompt_tokens=80, completion_tokens=30)

        resp2          = MagicMock()
        resp2.choices  = [MagicMock(message=msg2)]
        resp2.usage    = MagicMock(prompt_tokens=100, completion_tokens=40)

        with patch("openai.OpenAI") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock,
                   return_value={"analysis": "prompt too vague"}) as mock_exec, \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = [resp1, resp2]

            result = _run(agent._run_openai("analyze failures", 8))

        mock_exec.assert_called_once_with(
            "analyze_failure_pattern",
            {"pattern": "policy errors"},
            "test_proj",
        )

    def test_groq_calls_execute_tool_on_valid_parse(self):
        """execute_tool called when Groq text returns valid TOOL:/INPUT: block."""
        agent = _make_agent()

        responses = [
            'TOOL: fetch_recent_traces\nINPUT: {"project_id": "test_proj", "hours": 24}',
            "ANSWER: Found the root cause.",
        ]

        with patch("backend.core.eval_agent.chat", side_effect=responses), \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock,
                   return_value={"count": 5}) as mock_exec, \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", 8))

        mock_exec.assert_called_once()
        assert result["steps_taken"][0]["tool"] == "fetch_recent_traces"

    def test_openai_handles_malformed_tool_arguments(self):
        """execute_tool called with empty dict when tool args are invalid JSON."""
        agent = _make_agent()

        tool_call           = MagicMock()
        tool_call.id        = "call_bad"
        tool_call.function  = MagicMock()
        tool_call.function.name      = "fetch_recent_traces"
        tool_call.function.arguments = "NOT VALID JSON {"

        msg1            = MagicMock()
        msg1.content    = None
        msg1.tool_calls = [tool_call]

        msg2            = MagicMock()
        msg2.content    = "Done."
        msg2.tool_calls = None

        resp1 = MagicMock()
        resp1.choices = [MagicMock(message=msg1)]
        resp1.usage   = MagicMock(prompt_tokens=50, completion_tokens=20)

        resp2 = MagicMock()
        resp2.choices = [MagicMock(message=msg2)]
        resp2.usage   = MagicMock(prompt_tokens=60, completion_tokens=25)

        with patch("openai.OpenAI") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock,
                   return_value={}) as mock_exec, \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = [resp1, resp2]

            # Should not raise — bad JSON becomes empty dict
            result = _run(agent._run_openai("test", 8))

        # Called with empty dict when JSON is malformed
        call_args = mock_exec.call_args[0]
        assert call_args[1] == {}


# ── TestParseToolCall ─────────────────────────────────────────────────────

class TestParseToolCall:

    def test_parses_valid_single_line_json(self):
        agent    = _make_agent()
        response = 'TOOL: run_targeted_eval\nINPUT: {"dataset_name": "support-v1"}'
        name, inp = agent._parse_tool_call(response)
        assert name == "run_targeted_eval"
        assert inp  == {"dataset_name": "support-v1"}

    def test_parses_multiline_json(self):
        agent    = _make_agent()
        response = (
            "TOOL: generate_test_cases\n"
            'INPUT: {\n'
            '  "failure_pattern": "date formatting",\n'
            '  "count": 5\n'
            '}'
        )
        name, inp = agent._parse_tool_call(response)
        assert name         == "generate_test_cases"
        assert inp["count"] == 5
        assert inp["failure_pattern"] == "date formatting"

    def test_returns_none_on_invalid_json(self):
        agent    = _make_agent()
        response = "TOOL: run_eval\nINPUT: {invalid json here"
        name, inp = agent._parse_tool_call(response)
        assert name is None
        assert inp  == {}

    def test_returns_none_when_no_input_line(self):
        agent    = _make_agent()
        response = "TOOL: run_eval"
        name, inp = agent._parse_tool_call(response)
        assert name is None

    def test_returns_none_on_empty_response(self):
        agent    = _make_agent()
        name, inp = agent._parse_tool_call("")
        assert name is None
        assert inp  == {}

    def test_never_raises(self):
        agent = _make_agent()
        for bad_input in [
            None,
            123,
            "TOOL: \nINPUT: null",
            "TOOL: test\nINPUT: []",
            "garbage text with no structure",
        ]:
            try:
                result = agent._parse_tool_call(str(bad_input) if bad_input else "")
                assert isinstance(result, tuple)
            except Exception as exc:
                pytest.fail(f"_parse_tool_call raised on input {bad_input!r}: {exc}")

    def test_handles_tool_name_with_extra_whitespace(self):
        agent    = _make_agent()
        response = 'TOOL:   fetch_recent_traces   \nINPUT: {"hours": 24}'
        name, inp = agent._parse_tool_call(response)
        assert name == "fetch_recent_traces"
        assert inp  == {"hours": 24}

    def test_handles_nested_json(self):
        agent    = _make_agent()
        response = (
            'TOOL: run_targeted_eval\n'
            'INPUT: {"criteria": ["accurate", "helpful"], "project": {"id": "x"}}'
        )
        name, inp = agent._parse_tool_call(response)
        assert name == "run_targeted_eval"
        assert inp["criteria"] == ["accurate", "helpful"]
        assert inp["project"]["id"] == "x"


# ── TestMaxIterations ─────────────────────────────────────────────────────

class TestMaxIterations:

    def test_groq_stops_at_max_iterations(self):
        """Groq text path respects max_iterations limit."""
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="I need to think about this..."), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", max_iterations=3))

        assert result["iterations"] == 3

    def test_groq_exits_after_3_consecutive_parse_failures(self):
        """Three consecutive parse failures cause early exit."""
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="TOOL: something\nINPUT: {broken"), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", max_iterations=10))

        # Should exit well before 10 iterations
        assert result["iterations"] <= 5

    def test_groq_parse_failure_counter_resets_on_success(self):
        """Successful parse resets the failure counter."""
        agent = _make_agent()

        responses = [
            "TOOL: x\nINPUT: {bad",                                           # fail 1
            "TOOL: x\nINPUT: {bad",                                           # fail 2
            'TOOL: fetch_recent_traces\nINPUT: {"project_id": "x"}',          # success — resets counter
            "TOOL: x\nINPUT: {bad",                                           # fail 1 again
            "TOOL: x\nINPUT: {bad",                                           # fail 2 again
            "ANSWER: Done after recovery.",                                    # answer
        ]

        with patch("backend.core.eval_agent.chat", side_effect=responses), \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock, return_value={"ok": True}), \
             patch.object(agent, "_save_episode"):

            result = _run(agent._run_groq_text("test", max_iterations=10))

        assert result["answer"] == "Done after recovery."

    def test_anthropic_stops_at_max_iterations(self):
        """Anthropic path respects max_iterations and returns final answer."""
        agent = _make_agent()

        tool_block       = MagicMock()
        tool_block.type  = "tool_use"
        tool_block.id    = "t1"
        tool_block.name  = "fetch_recent_traces"
        tool_block.input = {"project_id": "x"}

        tool_resp             = MagicMock()
        tool_resp.stop_reason = "tool_use"
        tool_resp.content     = [tool_block]
        tool_resp.usage       = MagicMock(input_tokens=50, output_tokens=20)

        text_block       = MagicMock()
        text_block.type  = "text"
        text_block.text  = "Final summary after max iterations."
        final_resp             = MagicMock()
        final_resp.stop_reason = "end_turn"
        final_resp.content     = [text_block]
        final_resp.usage       = MagicMock(input_tokens=60, output_tokens=25)

        with patch("anthropic.Anthropic") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock, return_value={"count": 0}), \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            # Return tool_use N times, then final answer
            mock_client.messages.create.side_effect = (
                [tool_resp] * 3 + [final_resp]
            )

            result = _run(agent._run_anthropic("test", max_iterations=3))

        assert result["iterations"] == 3

    def test_openai_stops_at_max_iterations(self):
        """OpenAI path respects max_iterations."""
        agent = _make_agent()

        tool_call           = MagicMock()
        tool_call.id        = "c1"
        tool_call.function  = MagicMock()
        tool_call.function.name      = "fetch_recent_traces"
        tool_call.function.arguments = '{"project_id": "x"}'

        msg = MagicMock()
        msg.content    = None
        msg.tool_calls = [tool_call]

        resp = MagicMock()
        resp.choices = [MagicMock(message=msg)]
        resp.usage   = MagicMock(prompt_tokens=50, completion_tokens=20)

        with patch("openai.OpenAI") as mock_cls, \
             patch("backend.core.eval_agent.execute_tool",
                   new_callable=AsyncMock, return_value={"count": 0}), \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = resp

            result = _run(agent._run_openai("test", max_iterations=3))

        assert result["iterations"] == 3


# ── TestSaveEpisode ───────────────────────────────────────────────────────

class TestSaveEpisode:

    def test_save_episode_called_on_groq_answer(self):
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="ANSWER: Done."), \
             patch.object(agent, "_save_episode") as mock_save:

            _run(agent._run_groq_text("test", 8))
            mock_save.assert_called_once()

    def test_save_episode_called_on_groq_max_iterations(self):
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="thinking..."), \
             patch.object(agent, "_save_episode") as mock_save:

            _run(agent._run_groq_text("test", max_iterations=2))
            mock_save.assert_called_once()

    def test_save_episode_called_on_groq_parse_failure_exit(self):
        agent = _make_agent()

        with patch("backend.core.eval_agent.chat",
                   return_value="TOOL: x\nINPUT: {bad"), \
             patch.object(agent, "_save_episode") as mock_save:

            _run(agent._run_groq_text("test", max_iterations=10))
            mock_save.assert_called_once()

    def test_save_episode_called_on_anthropic_end_turn(self):
        agent = _make_agent()

        text_block       = MagicMock()
        text_block.type  = "text"
        text_block.text  = "Done."
        resp             = MagicMock()
        resp.stop_reason = "end_turn"
        resp.content     = [text_block]
        resp.usage       = MagicMock(input_tokens=50, output_tokens=20)

        with patch("anthropic.Anthropic") as mock_cls, \
             patch.object(agent, "_save_episode") as mock_save:

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = resp

            _run(agent._run_anthropic("test", 8))
            mock_save.assert_called_once()

    def test_save_episode_called_on_openai_no_tool_calls(self):
        agent = _make_agent()

        msg            = MagicMock()
        msg.content    = "Analysis done."
        msg.tool_calls = None

        resp          = MagicMock()
        resp.choices  = [MagicMock(message=msg)]
        resp.usage    = MagicMock(prompt_tokens=50, completion_tokens=20)

        with patch("openai.OpenAI") as mock_cls, \
             patch.object(agent, "_save_episode") as mock_save:

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.return_value = resp

            _run(agent._run_openai("test", 8))
            mock_save.assert_called_once()


# ── TestToolSchemaConversion ──────────────────────────────────────────────

class TestToolSchemaConversion:

    def test_openai_converts_anthropic_tool_format(self):
        """
        OpenAI path converts EVAL_AGENT_TOOLS from Anthropic to OpenAI format.
        Anthropic: {name, description, input_schema}
        OpenAI:    {type: "function", function: {name, description, parameters}}
        """
        agent = _make_agent()

        msg            = MagicMock()
        msg.content    = "Done."
        msg.tool_calls = None

        resp          = MagicMock()
        resp.choices  = [MagicMock(message=msg)]
        resp.usage    = MagicMock(prompt_tokens=50, completion_tokens=20)

        captured_tools = []

        def capture_call(**kwargs):
            captured_tools.extend(kwargs.get("tools", []))
            return resp

        with patch("openai.OpenAI") as mock_cls, \
             patch.object(agent, "_save_episode"):

            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.chat.completions.create.side_effect = (
                lambda **kw: capture_call(**kw)
            )

            _run(agent._run_openai("test", 8))

        assert len(captured_tools) > 0
        for tool in captured_tools:
            assert tool["type"] == "function"
            assert "function" in tool
            assert "name"        in tool["function"]
            assert "description" in tool["function"]
            assert "parameters"  in tool["function"]