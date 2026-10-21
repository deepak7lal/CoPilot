"""Small intentionally broken project for the CodePilot demo."""


def add(a, b):
    return a - b


def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
