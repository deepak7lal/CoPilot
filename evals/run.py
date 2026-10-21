"""Run the real model against independent assertions in fresh temporary projects."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import uuid4

from codepilot.agent import Agent
from codepilot.client import OllamaClient
from codepilot.tools import WorkspaceTools


CASES = {
    "sum": {
        "source": "def sum_numbers(numbers):\n    total = 0\n    for number in numbers:\n        total = number\n    return total\n",
        "task": "Fix sum_numbers(numbers) to return the sum of all values, including negative numbers and empty lists. Preserve the existing test file. Inspect the files, fix solution.py, run_tests, and report the result.",
        "visible": "self.assertEqual(sum_numbers([1, 2, 3]), 6)",
        "imports": "sum_numbers",
        "checks": "assert m.sum_numbers([10, 20, 30]) == 60\nassert m.sum_numbers([]) == 0\nassert m.sum_numbers([-2, 7, -8]) == -3\nassert m.sum_numbers([0, 0]) == 0\nassert m.sum_numbers([1.5, 2.25]) == 3.75\n",
    },
    "slug": {
        "source": "def slugify(text):\n    return text.lower().replace(' ', '-')\n",
        "task": "Fix slugify(text). Strip whitespace, lowercase, replace each run of characters other than ASCII a-z or 0-9 with a single hyphen, and strip leading/trailing hyphens. Empty or punctuation-only input returns an empty string. Preserve the existing test file. Inspect, fix solution.py, run_tests, and summarize.",
        "visible": "self.assertEqual(slugify(' Hello, World! '), 'hello-world')",
        "imports": "slugify",
        "checks": "assert m.slugify('  Hello, World!  ') == 'hello-world'\nassert m.slugify('a___b   c') == 'a-b-c'\nassert m.slugify('!!!') == ''\nassert m.slugify('') == ''\nassert m.slugify('Python 3.12') == 'python-3-12'\nassert m.slugify('---READY---') == 'ready'\n",
    },
    "discount": {
        "source": "def discounted_price(price, percent):\n    return price - percent\n",
        "task": "Fix discounted_price(price, percent): subtract percent percent of price, round the result to two decimal places using Python round, and raise ValueError for negative price or percent outside 0 through 100 inclusive. Preserve the existing test file. Inspect, fix solution.py, run_tests, and summarize.",
        "visible": "self.assertEqual(discounted_price(200, 10), 180)",
        "imports": "discounted_price",
        "checks": "assert m.discounted_price(200, 10) == 180\nassert m.discounted_price(25, 0) == 25\nassert m.discounted_price(25, 100) == 0\nassert m.discounted_price(19.99, 15) == round(19.99 * .85, 2)\nfor args in [(-1, 10), (10, -1), (10, 101)]:\n    try: m.discounted_price(*args)\n    except ValueError: pass\n    else: raise AssertionError('Expected ValueError for ' + str(args))\n",
    },
}


def grade(root, checks):
    # Checker is run by the evaluator, outside the agent's conversational tools.
    harness = (
        "import importlib.util, pathlib, sys\n"
        "p = pathlib.Path(sys.argv[1]) / 'solution.py'\n"
        "spec = importlib.util.spec_from_file_location('solution', p)\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n" + checks
    )
    try:
        result = subprocess.run([sys.executable, "-I", "-B", "-c", harness, str(root)],
                                capture_output=True, timeout=10)
        return {"passed": result.returncode == 0,
                "detail": result.stderr.decode(errors="replace")[-2000:]}
    except subprocess.TimeoutExpired:
        return {"passed": False, "detail": "Evaluator timed out."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--cpu", action="store_true", help="Request CPU inference")
    parser.add_argument("--model-timeout", type=int, default=120)
    parser.add_argument("--case", choices=list(CASES), help="Default: run all three cases")
    parser.add_argument("--output", default=".codepilot/evaluations")
    args = parser.parse_args(argv)
    if args.model_timeout <= 0:
        parser.error("--model-timeout must be positive")
    destination = Path(args.output) / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                                       + "-" + uuid4().hex[:6])
    destination.mkdir(parents=True, exist_ok=True)
    results = []
    for name in ([args.case] if args.case else CASES):
        case = CASES[name]
        print(f"Running {name} with {args.model}...", flush=True)
        with tempfile.TemporaryDirectory(prefix=f"codepilot-{name}-") as directory:
            root = Path(directory)
            (root / "solution.py").write_text(case["source"], encoding="utf-8")
            test_source = ("import unittest\nfrom solution import " + case["imports"] +
                           "\nclass Tests(unittest.TestCase):\n    def test_example(self):\n        "
                           + case["visible"] + "\n")
            test_file = root / "test_solution.py"
            test_file.write_text(test_source, encoding="utf-8")
            original_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
            baseline = grade(root, case["checks"])

            def progress(event):
                if event["type"] == "tool":
                    print(f"  {event['name']}: {'OK' if event['result']['ok'] else 'FAILED'}", flush=True)

            report = Agent(OllamaClient(args.model, args.host, args.model_timeout, cpu=args.cpu),
                           WorkspaceTools(root, allow_exec=True),
                           max_steps=12, max_tool_calls=30, on_event=progress).run(case["task"])
            report.save(destination / f"{name}-run.json")
            after = grade(root, case["checks"])
            preserved = test_file.is_file() and hashlib.sha256(test_file.read_bytes()).hexdigest() == original_hash
            passed = not baseline["passed"] and after["passed"] and preserved
            result = {"case": name, "passed": passed, "baseline": baseline,
                      "after": after, "original_tests_preserved": preserved,
                      "agent_status": report.status, "steps": report.steps,
                      "tool_calls": report.tool_calls, "seconds": report.duration_seconds}
            results.append(result)
            print(f"  Result: {'PASS' if passed else 'FAIL'} ({report.status}, {report.duration_seconds}s)", flush=True)
            if (root / "solution.py").is_file():
                (destination / f"{name}-solution.py").write_bytes((root / "solution.py").read_bytes())
        summary = {"model": args.model, "cpu": args.cpu, "model_timeout": args.model_timeout,
                   "cases_passed": sum(r["passed"] for r in results),
                   "cases_run": len(results), "results": results}
        (destination / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nPassed {summary['cases_passed']}/{summary['cases_run']} tasks. Reports: {destination.resolve()}")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
