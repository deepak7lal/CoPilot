import ollama

try:
    response = ollama.generate(model="qwen3:4b", prompt="Hello")
    print(response)
except Exception as e:
    print(f"Error: {e}")