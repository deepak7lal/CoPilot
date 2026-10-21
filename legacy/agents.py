
import json
import ollama

from tools import (
    read_file,
    list_files,
    write_file,
    run_python,
    run_file,
)

MODEL = "qwen3:4b"
MAX_STEPS = 12
MAX_REPEATED_CALLS = 2


SYSTEM_INSTRUCTION = """
You are CodePilot, an autonomous coding agent.

Complete coding tasks instead of merely describing what to do.

For each task:
1. Understand the requested behavior.
2. Inspect relevant files before changing them.
3. Make a short plan.
4. Use write_file to create or modify files when needed.
5. Use run_file to execute Python files.
6. Check actual execution results.
7. Fix errors and test again when appropriate.
8. Preserve existing functionality.
9. Never claim success without verification.
10. If a task is already complete, avoid unnecessary changes.

IMPORTANT:
- Use the provided tools to perform the work.
- Do not merely print tool-call JSON.
- After receiving a tool result, decide what to do next.
- Do not repeat an identical tool call unnecessarily.
- Tool arguments for read_file and run_file use 'filename'.
- For write_file, provide both 'filename' and 'content'.
- Only report tests as passed if the execution result confirms success.
"""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "file_path": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in the project directory.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a project file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_file",
            "description": "Execute a Python file and return its output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "file_path": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


def normalize_arguments(arguments):
    """Convert tool arguments to a dictionary."""
    if isinstance(arguments, str):
        arguments = json.loads(arguments)

    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be a dictionary.")

    return arguments


def get_filename(arguments):
    """Accept both filename and file_path."""
    return (
        arguments.get("filename")
        or arguments.get("file_path")
    )


def execute_tool(name, arguments):
    """Validate arguments and execute a supported tool."""

    try:
        arguments = normalize_arguments(arguments)

        if name == "list_files":
            print("\n[Agent is listing files...]")
            return str(list_files())

        if name == "read_file":
            filename = get_filename(arguments)

            if not filename:
                return "Tool error: filename is required."

            print(f"\n[Agent is reading: {filename}]")
            return str(read_file(filename))

        if name == "write_file":
            filename = get_filename(arguments)
            content = arguments.get("content")

            if not filename or content is None:
                return (
                    "Tool error: write_file requires "
                    "filename and content."
                )

            print(f"\n[Agent is writing: {filename}]")
            result = write_file(filename, content)
            return str(result)

        if name == "run_python":
            code = arguments.get("code")

            if code is None:
                return "Tool error: run_python requires code."

            print("\n[Agent is running Python code...]")
            return str(run_python(code))

        if name == "run_file":
            filename = get_filename(arguments)

            if not filename:
                return "Tool error: filename is required."

            print(f"\n[Agent is running file: {filename}]")
            return str(run_file(filename))

        return f"Tool error: unknown tool '{name}'."

    except Exception as error:
        return (
            f"Tool execution failed: "
            f"{type(error).__name__}: {error}"
        )


def get_tool_call_signature(name, arguments):
    """Build a stable signature for detecting repeated calls."""
    try:
        normalized = normalize_arguments(arguments)
        return json.dumps(
            {"name": name, "arguments": normalized},
            sort_keys=True,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        return f"{name}:{str(arguments)}"


def agent(task):
    messages = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": task},
    ]

    last_signature = None
    repeated_calls = 0

    for step in range(MAX_STEPS):
        print(f"\n[Agent step {step + 1}/{MAX_STEPS}]")

        try:
            response = ollama.chat(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
            )
        except Exception as error:
            return (
                "Ollama request failed. Check that Ollama is running "
                f"and {MODEL} is installed.\n"
                f"{type(error).__name__}: {error}"
            )

        message = response.message
        calls = message.tool_calls or []

        if not calls:
            return message.content or "No final answer was returned."

        # Preserve the assistant's tool-call message.
        messages.append(message)

        for call in calls:
            name = call.function.name
            arguments = call.function.arguments

            signature = get_tool_call_signature(name, arguments)

            if signature == last_signature:
                repeated_calls += 1
            else:
                last_signature = signature
                repeated_calls = 0

            if repeated_calls >= MAX_REPEATED_CALLS:
                return (
                    f"Stopped because the agent repeated the same "
                    f"tool call: {name}. Try a more specific task "
                    "or inspect the tool implementation."
                )

            print(f"[Tool requested: {name}]")

            result = execute_tool(name, arguments)

            # Ollama's conversation history expects tool results
            # to identify which tool produced the result.
            messages.append({
                "role": "tool",
                "name": name,
                "content": str(result),
            })

    return (
        f"Stopped after {MAX_STEPS} steps to prevent an endless loop. "
        "Try breaking the task into smaller steps."
    )


if __name__ == "__main__":
    task = input("What should I do? ").strip()

    if task:
        result = agent(task)
        print("\nAgent result:")
        print(result)
    else:
        print("No task entered.")
