"""Workspace file tools and opt-in Python subprocess execution.

Path checks protect file tools. They do NOT sandbox executed Python.
"""

from dataclasses import asdict, dataclass, field
import difflib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile


@dataclass
class ToolResult:
    ok: bool
    output: str
    data: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class WorkspaceTools:
    MAX_FILE_BYTES = 128_000
    MAX_OUTPUT = 12_000
    BLOCKED = {".git", ".codepilot", ".ssh", ".aws", ".venv", "__pycache__"}

    def __init__(self, root, *, allow_exec=False, dry_run=False, timeout=10):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Workspace must be a directory.")
        if timeout <= 0:
            raise ValueError("Execution timeout must be positive.")
        self.allow_exec = allow_exec
        self.dry_run = dry_run
        self.timeout = timeout

    def resolve(self, filename):
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("A non-empty filename is required.")
        raw = Path(filename)
        if raw.is_absolute() or raw.drive or ".." in raw.parts:
            raise ValueError("Use a workspace-relative path without '..'.")
        for part in raw.parts:
            if part not in {"."} and part.rstrip(" .") != part:
                raise ValueError("Path components cannot end in spaces or dots.")
            if part.lower() in self.BLOCKED or part.lower().startswith(".env"):
                raise ValueError("Access to metadata or secret paths is blocked.")
            if ":" in part:
                raise ValueError("Alternate data streams are not allowed.")
        resolved = (self.root / raw).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Path leaves the workspace, possibly through a symlink.")
        # Also check resolved names so symlink aliases cannot bypass exclusions.
        for part in resolved.relative_to(self.root).parts:
            if part.lower() in self.BLOCKED or part.lower().startswith(".env"):
                raise ValueError("Access to metadata or secret paths is blocked.")
        return resolved

    def read_file(self, filename):
        path = self.resolve(filename)
        if path.stat().st_size > self.MAX_FILE_BYTES:
            raise ValueError("File exceeds the 128 KB read limit.")
        return ToolResult(True, path.read_text(encoding="utf-8"))

    def list_files(self):
        files = []
        # Do not follow symlink directories or traverse dependency trees.
        import os
        for directory, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d.lower() not in self.BLOCKED
                             and d not in {"node_modules", "venv"}
                             and not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                relative = (Path(directory) / name).relative_to(self.root).as_posix()
                try:
                    self.resolve(relative)
                except ValueError:
                    continue
                files.append(relative)
                if len(files) >= 500:
                    return ToolResult(True, "\n".join(files), {"truncated": True})
        return ToolResult(True, "\n".join(files), {"truncated": False})

    def write_file(self, filename, content):
        path = self.resolve(filename)
        if not isinstance(content, str):
            raise ValueError("content must be a string.")
        if len(content.encode("utf-8")) > self.MAX_FILE_BYTES:
            raise ValueError("Content exceeds the 128 KB write limit.")
        old = self.read_file(filename).output if path.exists() else ""
        changed = old != content
        diff = "".join(difflib.unified_diff(
            old.splitlines(keepends=True), content.splitlines(keepends=True),
            fromfile=f"a/{filename}", tofile=f"b/{filename}",
        ))
        if changed and not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return ToolResult(True, diff[:self.MAX_OUTPUT] or "No changes.", {
            "filename": filename, "changed": changed,
            "applied": changed and not self.dry_run,
            "dry_run": self.dry_run, "diff_truncated": len(diff) > self.MAX_OUTPUT,
        })

    def _run(self, arguments):
        if self.dry_run:
            return ToolResult(False, "Execution is disabled during dry runs.")
        if not self.allow_exec:
            return ToolResult(False, "Python execution requires --allow-exec.")
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                [sys.executable, "-B", *arguments], cwd=self.root,
                stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
            )
            timed_out = False
            try:
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
            stdout.seek(0)
            stderr.seek(0)
            out = stdout.read(self.MAX_OUTPUT + 1)
            err = stderr.read(self.MAX_OUTPUT + 1)
        truncated = len(out) > self.MAX_OUTPUT or len(err) > self.MAX_OUTPUT
        data = {
            "returncode": process.returncode, "timed_out": timed_out,
            "stdout": out[:self.MAX_OUTPUT].decode("utf-8", errors="replace"),
            "stderr": err[:self.MAX_OUTPUT].decode("utf-8", errors="replace"),
            "truncated": truncated,
        }
        ok = not timed_out and process.returncode == 0
        return ToolResult(ok, "Execution timed out." if timed_out else
                          ("Execution passed." if ok else "Execution failed."), data)

    def run_file(self, filename):
        path = self.resolve(filename)
        if path.suffix != ".py" or not path.is_file():
            raise ValueError("run_file requires an existing .py file.")
        return self._run([str(path)])

    def run_python(self, code):
        if not isinstance(code, str) or len(code) > self.MAX_FILE_BYTES:
            raise ValueError("code must be a string of at most 128,000 characters.")
        return self._run(["-c", code])

    def run_tests(self, directory="."):
        path = self.resolve(directory)
        if not path.is_dir():
            raise ValueError("Test directory does not exist.")
        result = self._run(["-m", "unittest", "discover", "-s", str(path),
                            "-p", "test_*.py"])
        # Some Python versions exit 0 for empty suites; imports can also exit 0
        # before discovery finishes. Require a confirmed nonzero runner count.
        count = re.search(r"^Ran (\d+) tests? in ", result.data.get("stderr", ""), re.MULTILINE)
        result.data["tests_run"] = int(count.group(1)) if count else 0
        if count and result.data["tests_run"] == 0:
            return ToolResult(False, "No tests discovered; verification is incomplete.",
                              result.data)
        if result.ok and not count:
            return ToolResult(False, "No confirmed test count; verification is incomplete.", result.data)
        return result

    def execute(self, name, arguments):
        allowed = {"read_file", "list_files", "write_file", "run_file",
                   "run_python", "run_tests"}
        try:
            if isinstance(arguments, str):
                arguments = json.loads(arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
            if name not in allowed:
                raise ValueError(f"Unknown tool: {name}")
            arguments = dict(arguments)
            if "file_path" in arguments and "filename" not in arguments:
                arguments["filename"] = arguments.pop("file_path")
            return getattr(self, name)(**arguments)
        except (OSError, ValueError, TypeError) as error:
            return ToolResult(False, f"{type(error).__name__}: {error}")


def tool_schema(name, description, properties=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {},
                       "required": required or [], "additionalProperties": False},
    }}


STRING = {"type": "string"}
TOOLS = [
    tool_schema("list_files", "List project files."),
    tool_schema("read_file", "Read a UTF-8 project file.", {"filename": STRING}, ["filename"]),
    tool_schema("write_file", "Write a complete file and return a diff.",
                {"filename": STRING, "content": STRING}, ["filename", "content"]),
    tool_schema("run_file", "Execute a Python project file.", {"filename": STRING}, ["filename"]),
    tool_schema("run_python", "Run Python code to inspect or check behavior.", {"code": STRING}, ["code"]),
    tool_schema("run_tests", "Run unittest discovery; an empty suite is a failure.", {"directory": STRING}),
]
