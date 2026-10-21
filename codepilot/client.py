"""Small Ollama HTTP adapter; the application has no third-party dependencies."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OllamaClient:
    def __init__(self, model="qwen3:4b", host="http://127.0.0.1:11434", timeout=120, *, cpu=False):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.cpu = cpu

    def chat(self, messages, tools):
        # Some older Qwen3 templates unconditionally open a thinking block even
        # with think=False. The model's documented soft switch keeps tool turns short.
        if self.model.split(":")[0].lower() == "qwen3":
            messages = [dict(message) for message in messages]
            for message in messages:
                if message.get("role") == "system":
                    message["content"] = message.get("content", "") + "\n/no_think"
                    break
        options = {"temperature": 0, "num_predict": 2048}
        if self.cpu:
            options["num_gpu"] = 0
        payload = {"model": self.model, "messages": messages, "tools": tools,
                   "stream": False, "think": False, "options": options}
        request = Request(self.host + "/api/chat", json.dumps(payload).encode(),
                          {"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except HTTPError as error:
            detail = error.read(2000).decode(errors="replace")
            raise RuntimeError(f"Ollama HTTP {error.code}: {detail}") from error
        except TimeoutError as error:
            raise RuntimeError(
                f"Ollama generation exceeded the {self.timeout}s request timeout. "
                "Try --model-timeout with a larger value, --cpu for GPU issues, "
                "or check the Ollama server logs."
            ) from error
        except (URLError, OSError) as error:
            raise RuntimeError(
                f"Cannot reach Ollama at {self.host}. Start Ollama and install "
                f"{self.model} with 'ollama pull {self.model}'. ({error})"
            ) from error
        message = data.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            raise ValueError("Ollama returned an invalid assistant message.")
        return message
