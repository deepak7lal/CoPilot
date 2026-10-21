import json
from pathlib import Path
import tempfile
import unittest

from codepilot.agent import Agent
from codepilot.tools import WorkspaceTools


def call(name, **arguments):
    return {"function": {"name": name, "arguments": arguments}}


def message(*calls, content=""):
    return {"role": "assistant", "content": content, "tool_calls": list(calls)}


class ScriptedClient:
    """Deterministic test double, not a model-quality benchmark."""
    model = "scripted-test-client"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.histories = []

    def chat(self, messages, tools):
        self.histories.append(list(messages))
        return next(self.responses)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = WorkspaceTools(self.root, allow_exec=True)
        (self.root / "calc.py").write_text("def add(a, b): return a - b\n")
        (self.root / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\nclass T(unittest.TestCase):\n"
            " def test_add(self): self.assertEqual(add(2, 3), 5)\n")

    def test_inspect_fail_fix_retest_with_real_subprocesses(self):
        client = ScriptedClient([
            message(call("read_file", filename="calc.py")),
            message(call("run_tests")),
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(call("run_tests")), message(content="Fixed addition and ran the tests."),
        ])
        report = Agent(client, self.tools).run("Fix addition")
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.changed_files, ["calc.py"])
        tool_events = [e for e in report.events if e["type"] == "tool"]
        self.assertFalse(tool_events[1]["result"]["ok"])
        self.assertTrue(tool_events[-1]["result"]["ok"])
        self.assertEqual(client.histories[1][-1]["tool_name"], "read_file")
        destination = self.root / "report.json"
        report.save(destination)
        self.assertEqual(json.loads(destination.read_text())["status"], "completed")

    def test_model_claim_does_not_override_unverified_status(self):
        report = Agent(ScriptedClient([message(content="Everything passed!")]), self.tools,
                       max_completion_retries=0).run("Fix it")
        self.assertEqual(report.status, "unverified")

    def test_writing_after_pass_invalidates_verification(self):
        client = ScriptedClient([
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(call("run_tests")),
            message(call("write_file", filename="calc.py", content="def add(a, b): return 0\n")),
            message(content="Done"),
        ])
        self.assertEqual(Agent(client, self.tools, max_completion_retries=0).run("Fix it").status, "unverified")

    def test_python_execution_invalidates_previous_test_evidence(self):
        client = ScriptedClient([
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(call("run_tests")), message(call("run_python", code="print('hi')")),
            message(content="Done"),
        ])
        self.assertEqual(Agent(client, self.tools, max_completion_retries=0,
                               verify_on_finish=False).run("Fix it").status, "unverified")

    def test_runner_verifies_changed_code_when_model_forgets_tests(self):
        client = ScriptedClient([
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(content="Done"),
        ])
        report = Agent(client, self.tools).run("Fix addition")
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.tool_calls, 2)
        self.assertEqual(report.events[-1]["origin"], "final_verification")
        self.assertEqual(report.events[-1]["result"]["data"]["tests_run"], 1)

    def test_runner_final_verification_respects_tool_budget(self):
        client = ScriptedClient([
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(content="Done"),
        ])
        report = Agent(client, self.tools, max_tool_calls=1).run("Fix addition")
        self.assertEqual(report.status, "unverified")
        self.assertEqual(report.tool_calls, 1)

    def test_repeated_calls_are_stopped(self):
        client = ScriptedClient([message(call("list_files"))] * 8)
        report = Agent(client, self.tools).run("Inspect")
        self.assertEqual(report.status, "repetition_stopped")
        self.assertEqual(report.tool_calls, 3)

    def test_step_budget(self):
        report = Agent(ScriptedClient([message(call("list_files"))]), self.tools,
                       max_steps=1).run("Inspect")
        self.assertEqual(report.status, "budget_exceeded")

    def test_tool_budget_in_single_response(self):
        client = ScriptedClient([message(call("list_files"), call("read_file", filename="calc.py"))])
        report = Agent(client, self.tools, max_tool_calls=1).run("Inspect")
        self.assertEqual(report.status, "budget_exceeded")
        self.assertEqual(report.tool_calls, 1)

    def test_tool_error_is_fed_back_for_recovery(self):
        client = ScriptedClient([message(call("bad_tool")), message(content="Tool unsupported")])
        report = Agent(client, self.tools, max_completion_retries=0).run("Inspect")
        self.assertFalse(report.events[1]["result"]["ok"])
        self.assertIn("Unknown tool", client.histories[1][-1]["content"])

    def test_premature_final_gets_one_bounded_recovery_turn(self):
        client = ScriptedClient([
            message(content="Here is the fixed code: def add(a, b): return a + b"),
            message(call("read_file", filename="calc.py")),
            message(call("write_file", filename="calc.py", content="def add(a, b): return a + b\n")),
            message(call("run_tests")), message(content="Applied and tested."),
        ])
        report = Agent(client, self.tools).run("Fix addition")
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.completion_retries, 1)
        self.assertEqual(client.histories[1][-1]["role"], "user")
        self.assertIn("actual tool calls", client.histories[1][-1]["content"])

    def test_premature_final_retries_are_bounded(self):
        client = ScriptedClient([message(content="Done"), message(content="Still done")])
        report = Agent(client, self.tools).run("Fix addition")
        self.assertEqual(report.status, "unverified")
        self.assertEqual(report.steps, 2)
        self.assertEqual(report.completion_retries, 1)

    def test_malformed_response_and_provider_error(self):
        for response in (message({"bad": 1}), {"tool_calls": "invalid"}, None):
            with self.subTest(response=response):
                report = Agent(ScriptedClient([response]), self.tools).run("Inspect")
                self.assertEqual(report.status, "error")
        class BrokenClient:
            model = "broken"
            def chat(self, *_):
                raise RuntimeError("offline")
        self.assertEqual(Agent(BrokenClient(), self.tools).run("Inspect").final, "offline")

    def test_dry_run_reports_preview_and_preserves_original(self):
        client = ScriptedClient([
            message(call("write_file", filename="calc.py", content="changed")),
            message(content="Proposed fix"),
        ])
        tools = WorkspaceTools(self.root, dry_run=True)
        report = Agent(client, tools).run("Fix it")
        self.assertEqual(report.status, "preview")
        self.assertEqual(report.changed_files, [])
        self.assertIn("return a - b", (self.root / "calc.py").read_text())

    def test_empty_task_rejected(self):
        with self.assertRaises(ValueError):
            Agent(ScriptedClient([]), self.tools).run(" ")
