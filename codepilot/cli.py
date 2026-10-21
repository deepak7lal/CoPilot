"""Command line interface."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from .agent import Agent
from .client import OllamaClient
from .tools import WorkspaceTools


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description="CodePilot: inspect, edit, and verify Python code locally.")
    parser.add_argument("task", help="Coding task, quoted as one argument")
    parser.add_argument("--workspace", default=".", help="Project directory")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--cpu", action="store_true", help="Request CPU inference instead of GPU offload")
    parser.add_argument("--allow-exec", action="store_true", help="Allow Python execution with your user's permissions")
    parser.add_argument("--dry-run", action="store_true", help="Preview file diffs; do not write project files or execute code")
    parser.add_argument("--timeout", type=positive_int, default=10, help="Seconds per Python execution")
    parser.add_argument("--model-timeout", type=positive_int, default=120)
    parser.add_argument("--max-steps", type=positive_int, default=16)
    parser.add_argument("--max-tool-calls", type=positive_int, default=40)
    parser.add_argument("--report", help="JSON report path; defaults to .codepilot/runs/ in the current directory")
    parser.add_argument("--quiet", action="store_true", help="Show only the result and report location")
    args = parser.parse_args(argv)
    if not args.task.strip():
        parser.error("task cannot be empty")
    try:
        tools = WorkspaceTools(args.workspace, allow_exec=args.allow_exec,
                               dry_run=args.dry_run, timeout=args.timeout)
    except (ValueError, OSError) as error:
        parser.error(str(error))

    def show(event):
        if args.quiet:
            return
        if event["type"] == "tool":
            result = event["result"]
            print(f"[{event['step']}] {event['name']}: {'OK' if result['ok'] else 'FAILED'}")
            print(result["output"])
            for stream in ("stdout", "stderr"):
                if result["data"].get(stream):
                    print(result["data"][stream])
        elif event.get("content"):
            print(event["content"])

    client = OllamaClient(args.model, args.host, args.model_timeout, cpu=args.cpu)
    report = Agent(client, tools, max_steps=args.max_steps,
                   max_tool_calls=args.max_tool_calls, on_event=show).run(args.task)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = args.report or f".codepilot/runs/{stamp}-{uuid4().hex[:8]}.json"
    try:
        report.save(destination)
    except OSError as error:
        print(f"Could not save report: {error}", file=sys.stderr)
        return 1
    print(f"\nStatus: {report.status}\n{report.final}")
    print(f"Steps: {report.steps} | Tool calls: {report.tool_calls} | {report.duration_seconds}s")
    print(f"Report: {Path(destination).resolve()}")
    return 0 if report.status in {"completed", "preview"} else 1
