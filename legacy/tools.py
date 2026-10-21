
import os
import io
import contextlib


def read_file(filename):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read()


def list_files():
    return os.listdir(".")


def write_file(filename, content):
    with open(filename, "w", encoding="utf-8") as file:
        file.write(content)

    return f"File '{filename}' created successfully."


def run_python(code):
    output = io.StringIO()

    try:
        with contextlib.redirect_stdout(output):
            exec(code, {})

        result = output.getvalue().strip()

        if result:
            return f"Execution successful.\nOutput: {result}"
        else:
            return "Execution successful.\nOutput: No output."

    except Exception as e:
        return f"Execution failed.\nError: {type(e).__name__}: {e}"


def run_file(filename):
    output = io.StringIO()

    try:
        with contextlib.redirect_stdout(output):

            with open(filename, "r", encoding="utf-8") as file:
                code = file.read()

            exec(code, {})

        result = output.getvalue().strip()

        if result:
            return f"Execution successful.\nOutput: {result}"
        else:
            return "Execution successful.\nOutput: No output."

    except Exception as e:
        return f"Execution failed.\nError: {type(e).__name__}: {e}"