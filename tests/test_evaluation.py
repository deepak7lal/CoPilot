from pathlib import Path
import tempfile
import unittest

from evals.run import CASES, grade


class EvaluationTests(unittest.TestCase):
    def test_every_seeded_bug_fails_independent_grader(self):
        for name, case in CASES.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "solution.py").write_text(case["source"], encoding="utf-8")
                self.assertFalse(grade(root, case["checks"])["passed"])

    def test_grader_accepts_correct_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "solution.py").write_text("def sum_numbers(numbers): return sum(numbers)\n")
            self.assertTrue(grade(root, CASES["sum"]["checks"])["passed"])
