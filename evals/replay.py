"""Deterministic workflow demo. Uses scripted tool calls, not LLM inference."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from uuid import uuid4

from codepilot.agent import Agent
from codepilot.tools import WorkspaceTools
from .run import CASES, grade


class ReplayClient:
    model = "scripted-replay-no-llm"

    def __init__(self):
        def call(name, **arguments):
            return {"role": "assistant", "content": "", "tool_calls": [
                {"function": {"name": name, "arguments": arguments}}]}
        self.responses = iter([
            call("list_files"),
            call("read_file", filename="solution.py"),
            call("read_file", filename="test_solution.py"),
            call("run_tests"),
            call("write_file", filename="solution.py",
                 content="def sum_numbers(numbers):\n    return sum(numbers)\n"),
            call("run_tests"),
            {"role": "assistant", "content": "Fixed accumulation; the regression test now passes."},
        ])

    def chat(self, messages, tools):
        return next(self.responses)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=".codepilot/replays")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = Path(args.output) / (stamp + "-" + uuid4().hex[:6])
    print("SCRIPTED REPLAY: no language model is used. This demonstrates orchestration only.")

    def show(event):
        if event["type"] == "tool":
            result = event["result"]
            print(f"\n{event['name']}: {'OK' if result['ok'] else 'FAILED'}")
            print(result["output"])
            if result["data"].get("stderr"):
                print(result["data"]["stderr"])

    with tempfile.TemporaryDirectory(prefix="codepilot-replay-") as directory:
        root = Path(directory)
        (root / "solution.py").write_text(CASES["sum"]["source"], encoding="utf-8")
        (root / "test_solution.py").write_text(
            "import unittest\nfrom solution import sum_numbers\nclass Tests(unittest.TestCase):\n"
            "    def test_sum(self): self.assertEqual(sum_numbers([1, 2, 3]), 6)\n", encoding="utf-8")
        report = Agent(ReplayClient(), WorkspaceTools(root, allow_exec=True), on_event=show).run(
            "Fix sum_numbers and verify the result (scripted demonstration).")
        report.save(destination / "run.json")
        independent = grade(root, CASES["sum"]["checks"])
        print(f"Status: {report.status}; independent checks passed: {independent['passed']}")
        print(f"Report: {(destination / 'run.json').resolve()}")
        return 0 if report.status == "completed" and independent["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
