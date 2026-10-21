
import ollama
from tools import read_file, list_files, write_file, run_python, run_file


def agent(task):

    system_instruction = """
You are CodePilot, an autonomous coding agent.

Your job is to complete the user's coding task, not just explain what should be done.

For every coding task, follow this workflow:

PHASE 1 — UNDERSTAND
1. Understand exactly what the user wants.
2. Inspect the relevant project files using list_files() and read_file().
3. Identify which files need to be created or modified.

PHASE 2 — PLAN
4. Decide the smallest correct change needed.
5. Preserve existing functionality unless the user asks for a change.

PHASE 3 — EXECUTE
6. Actually create or modify files using write_file().
7. Never merely show code that should be written. Perform the change.

PHASE 4 — TEST
8. Actually run the relevant Python file using run_file().
9. Check the actual execution result.

PHASE 5 — FIX
10. If the program produces an error, identify the cause.
11. Fix the ORIGINAL file using write_file().
12. Run the file again.
13. Repeat until the task works correctly.

PHASE 6 — VERIFY
14. Compare the actual output with the user's requested behavior.
15. Do not claim success unless the result has actually been tested.
16. Always report the actual final output returned by the execution tool.

IMPORTANT RULES:
- Do not stop after reading a file when the task requires modification.
- Do not stop after generating code when the task requires execution.
- Do not create *_fixed.py files unless explicitly requested.
- Do not change inputs or expected behavior just to make an error disappear.
- Preserve the original purpose of the program.
- Use the available tools whenever they are needed.
"""

    messages = [
        {
            "role": "system",
            "content": system_instruction
        },
        {
            "role": "user",
            "content": task
        }
    ]

    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The path of the file to read"
                        }
                    },
                    "required": ["filename"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files in the current project directory",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create or overwrite a file with the given content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The file to create or modify"
                        },
                        "content": {
                            "type": "string",
                            "description": "The complete new file content"
                        }
                    },
                    "required": ["filename", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_python",
                "description": "Execute Python code and return the actual output or error",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python code to execute"
                        }
                    },
                    "required": ["code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_file",
                "description": "Run a Python file and return its actual output or error",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "The Python file to execute"
                        }
                    },
                    "required": ["filename"]
                }
            }
        }
    ]

    while True:

        response = ollama.chat(
            model="qwen3:4b",
            messages=messages,
            tools=tools
        )

        if not response.message.tool_calls:
            return response.message.content

        messages.append(response.message)

        for call in response.message.tool_calls:

            tool_name = call.function.name
            arguments = call.function.arguments

            if tool_name == "read_file":

                filename = arguments["filename"]

                print(f"\n[Agent is reading: {filename}]")

                result = read_file(filename)

                messages.append({
                    "role": "tool",
                    "content": result
                })

            elif tool_name == "list_files":

                print("\n[Agent is listing files...]")

                result = list_files()

                messages.append({
                    "role": "tool",
                    "content": str(result)
                })

            elif tool_name == "write_file":

                filename = arguments["filename"]
                content = arguments["content"]

                print(f"\n[Agent is writing: {filename}]")

                result = write_file(filename, content)

                messages.append({
                    "role": "tool",
                    "content": result
                })

            elif tool_name == "run_python":

                code = arguments["code"]

                print("\n[Agent is running Python code...]")

                result = run_python(code)

                messages.append({
                    "role": "tool",
                    "content": result
                })

            elif tool_name == "run_file":

                filename = arguments["filename"]

                print(f"\n[Agent is running file: {filename}]")

                result = run_file(filename)

                messages.append({
                    "role": "tool",
                    "content": result
                })


task = input("What should I do? ")

result = agent(task)

print("\nAgent result:")
print(result)
