"""Compatibility file tools. Execution now requires explicit allow_exec=True.

New code should use codepilot.tools.WorkspaceTools for structured results.
The original prototype is preserved in legacy/tools.py.
"""

from codepilot.tools import WorkspaceTools


def read_file(filename):
    return WorkspaceTools(".").read_file(filename).output


def list_files():
    return WorkspaceTools(".").list_files().output.splitlines()


def write_file(filename, content):
    return WorkspaceTools(".").write_file(filename, content).output


def _format(result):
    return "\n".join(str(part) for part in (
        result.output, result.data.get("stdout"), result.data.get("stderr")) if part)


def run_python(code, *, allow_exec=False):
    return _format(WorkspaceTools(".", allow_exec=allow_exec).run_python(code))


def run_file(filename, *, allow_exec=False):
    return _format(WorkspaceTools(".", allow_exec=allow_exec).run_file(filename))
