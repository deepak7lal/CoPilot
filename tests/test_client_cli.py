import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from codepilot.cli import main
from codepilot.client import OllamaClient


class ClientTests(unittest.TestCase):
    def test_request_contract_and_response(self):
        response = {"message": {"role": "assistant", "content": "hello"}}
        with patch("codepilot.client.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
            self.assertEqual(OllamaClient().chat([], [])["content"], "hello")
            request = urlopen.call_args.args[0]
            self.assertTrue(request.full_url.endswith("/api/chat"))
            payload = json.loads(request.data)
            self.assertFalse(payload["stream"])
            self.assertIn("tools", payload)

    def test_connection_failure_is_actionable(self):
        with patch("codepilot.client.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(RuntimeError, "ollama pull"):
                OllamaClient().chat([], [])

    def test_http_error_preserves_server_detail(self):
        error = HTTPError("http://localhost", 404, "missing", {}, io.BytesIO(b"model missing"))
        with patch("codepilot.client.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "model missing"):
                OllamaClient().chat([], [])

    def test_malformed_response(self):
        with patch("codepilot.client.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(b'{"message": {"role": "user"}}')
            with self.assertRaises(ValueError):
                OllamaClient().chat([], [])

    def test_generation_timeout_is_distinct_from_connection_failure(self):
        with patch("codepilot.client.urlopen", side_effect=TimeoutError()):
            with self.assertRaisesRegex(RuntimeError, "generation exceeded"):
                OllamaClient(timeout=3).chat([], [])

    def test_cpu_option_and_generation_budget(self):
        with patch("codepilot.client.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                b'{"message": {"role": "assistant", "content": "OK"}}')
            OllamaClient(cpu=True).chat([], [])
            payload = json.loads(urlopen.call_args.args[0].data)
            self.assertEqual(payload["options"]["num_gpu"], 0)
            self.assertEqual(payload["options"]["num_predict"], 2048)

    def test_qwen_soft_switch_does_not_mutate_history(self):
        messages = [{"role": "system", "content": "Instructions"}]
        with patch("codepilot.client.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(
                b'{"message": {"role": "assistant", "content": "OK"}}')
            OllamaClient().chat(messages, [])
            payload = json.loads(urlopen.call_args.args[0].data)
            self.assertIn("/no_think", payload["messages"][0]["content"])
            self.assertEqual(messages[0]["content"], "Instructions")


class CliTests(unittest.TestCase):
    def test_cli_writes_report_and_returns_nonzero_for_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.json"
            with patch("codepilot.client.OllamaClient.chat", return_value={"content": "Done"}), patch("sys.stdout", new_callable=io.StringIO):
                exit_code = main(["Inspect", "--workspace", directory, "--report", str(report)])
            self.assertEqual(exit_code, 1)
            self.assertEqual(json.loads(report.read_text())["status"], "unverified")

    def test_cli_dry_run_exit_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "result.json"
            with patch("codepilot.client.OllamaClient.chat", return_value={"content": "Plan"}), patch("sys.stdout", new_callable=io.StringIO):
                exit_code = main(["Inspect", "--workspace", directory, "--dry-run", "--report", str(report)])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(report.read_text())["status"], "preview")

    def test_invalid_budget_is_rejected(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                main(["Task", "--max-steps", "0"])
        self.assertEqual(error.exception.code, 2)
