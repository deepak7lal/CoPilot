import json
from pathlib import Path
import tempfile
import unittest

from codepilot.tools import WorkspaceTools


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = WorkspaceTools(self.root, allow_exec=True, timeout=2)

    def write(self, name, content):
        (self.root / name).write_text(content, encoding="utf-8")

    def test_nested_write_read_and_diff(self):
        result = self.tools.write_file("src/hello.py", "print('hello')\n")
        self.assertTrue(result.data["applied"])
        self.assertIn("+print('hello')", result.output)
        self.assertEqual(self.tools.read_file("src/hello.py").output, "print('hello')\n")

    def test_unchanged_write_has_no_applied_change(self):
        self.write("a.py", "x = 1\n")
        self.assertFalse(self.tools.write_file("a.py", "x = 1\n").data["applied"])

    def test_paths_and_metadata_are_rejected(self):
        for path in ("../outside.py", str(self.root / "absolute.py"), ".git/config",
                     ".env", "nested/.env.local", ".codepilot/run.json", "a:b"):
            with self.subTest(path=path):
                result = self.tools.execute("write_file", {"filename": path, "content": "secret"})
                self.assertFalse(result.ok)

    def test_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            try:
                (self.root / "link").symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest("Creating symlinks requires permissions on this host")
            self.assertFalse(self.tools.execute("write_file", {
                "filename": "link/outside.py", "content": "x"}).ok)

    def test_file_size_limits(self):
        self.write("large.txt", "x" * (self.tools.MAX_FILE_BYTES + 1))
        self.assertFalse(self.tools.execute("read_file", {"filename": "large.txt"}).ok)
        self.assertFalse(self.tools.execute("write_file", {
            "filename": "new.txt", "content": "x" * (self.tools.MAX_FILE_BYTES + 1)}).ok)

    def test_dry_run_preserves_files_and_disables_execution(self):
        self.write("a.py", "old\n")
        tools = WorkspaceTools(self.root, allow_exec=True, dry_run=True)
        result = tools.write_file("a.py", "new\n")
        self.assertIn("+new", result.output)
        self.assertFalse(result.data["applied"])
        self.assertEqual((self.root / "a.py").read_text(), "old\n")
        self.assertFalse(tools.run_python("print(1)").ok)

    def test_execution_requires_opt_in(self):
        self.assertFalse(WorkspaceTools(self.root).run_python("print(1)").ok)

    def test_script_runs_as_main_in_workspace(self):
        self.write("helper.py", "VALUE = 42\n")
        self.write("main.py", "from helper import VALUE\nif __name__ == '__main__': print(VALUE)\n")
        result = self.tools.run_file("main.py")
        self.assertTrue(result.ok, result)
        self.assertEqual(result.data["stdout"].strip(), "42")

    def test_failure_preserves_exit_code_and_stderr(self):
        result = self.tools.run_python("raise ValueError('bad input')")
        self.assertFalse(result.ok)
        self.assertNotEqual(result.data["returncode"], 0)
        self.assertIn("ValueError: bad input", result.data["stderr"])

    def test_timeout_terminates_infinite_loop(self):
        tools = WorkspaceTools(self.root, allow_exec=True, timeout=0.2)
        result = tools.run_python("while True: pass")
        self.assertFalse(result.ok)
        self.assertTrue(result.data["timed_out"])

    def test_output_is_bounded(self):
        result = self.tools.run_python("print('x' * 20000)")
        self.assertTrue(result.ok)
        self.assertTrue(result.data["truncated"])
        self.assertLessEqual(len(result.data["stdout"]), self.tools.MAX_OUTPUT)

    def test_empty_suite_is_not_success(self):
        result = self.tools.run_tests()
        self.assertFalse(result.ok)
        self.assertIn("No tests", result.output)

    def test_nonempty_suite_passes_and_failure_is_visible(self):
        self.write("test_example.py", "import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.assertEqual(2 + 2, 4)\n")
        self.assertTrue(self.tools.run_tests().ok)
        self.write("test_example.py", "import unittest\nclass T(unittest.TestCase):\n def test_one(self): self.fail('regression')\n")
        result = self.tools.run_tests()
        self.assertFalse(result.ok)
        self.assertIn("regression", result.data["stderr"])

    def test_early_zero_exit_does_not_count_as_test_verification(self):
        self.write("test_early.py", "import os\nos._exit(0)\n")
        result = self.tools.run_tests()
        self.assertFalse(result.ok)
        self.assertEqual(result.data["tests_run"], 0)

    def test_list_hides_secrets_and_generated_metadata(self):
        self.write("main.py", "")
        self.write(".env", "secret")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("metadata")
        self.assertEqual(self.tools.list_files().output, "main.py")

    def test_bad_arguments_and_unknown_tools_return_errors(self):
        for name, args in (("read_file", "{"), ("list_files", []),
                           ("delete_file", {}), ("write_file", {"filename": "x"}),
                           ("read_file", {"filename": "missing"})):
            with self.subTest(name=name, args=args):
                self.assertFalse(self.tools.execute(name, args).ok)
        self.write("a.txt", "hello")
        result = self.tools.execute("read_file", json.dumps({"file_path": "a.txt"}))
        self.assertEqual(result.output, "hello")
