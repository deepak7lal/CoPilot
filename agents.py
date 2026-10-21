"""Compatibility entry point. Prefer python -m codepilot; originals live in legacy/."""

import sys

from codepilot.agent import Agent
from codepilot.cli import main
from codepilot.client import OllamaClient
from codepilot.tools import WorkspaceTools


def agent(task, workspace=".", *, allow_exec=False):
    report = Agent(OllamaClient(), WorkspaceTools(workspace, allow_exec=allow_exec)).run(task)
    return f"Status: {report.status}\n{report.final}"


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments:
        task = input("What should I do? ").strip()
        if not task:
            raise SystemExit("No task entered.")
        arguments = [task]
    raise SystemExit(main(arguments))
