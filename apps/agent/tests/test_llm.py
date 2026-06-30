import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from packwise_agent.__main__ import main as cli_main
from packwise_agent.llm import ChatMessage, OpenAICompatibleChatClient


class LlmClientTest(unittest.TestCase):
    def test_chat_endpoint_accepts_base_url_with_or_without_v1(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return _FakeResponse({"choices": [{"message": {"content": "ok"}}]})

        with patch("packwise_agent.llm.urllib.request.urlopen", fake_urlopen):
            OpenAICompatibleChatClient(
                api_key="unit-placeholder-secret",
                base_url="https://provider.example/v1",
                model="deepseek-v4-pro",
            ).complete([ChatMessage(role="user", content="hello")])
            OpenAICompatibleChatClient(
                api_key="unit-placeholder-secret",
                base_url="https://provider.example",
                model="deepseek-v4-pro",
            ).complete([ChatMessage(role="user", content="hello")])

        self.assertEqual("https://provider.example/v1/chat/completions", requests[0].full_url)
        self.assertEqual("https://provider.example/v1/chat/completions", requests[1].full_url)

    def test_model_check_reports_model_presence_and_chat_smoke_without_leaking_key(self):
        requests = []

        def fake_urlopen(request, timeout):
            self.assertEqual("Bearer unit-placeholder-secret", request.get_header("Authorization"))
            requests.append(request)
            if request.full_url == "https://provider.example/v1/models":
                return _FakeResponse({"data": [{"id": "deepseek-v4-pro"}, {"id": "other-model"}]})
            if request.full_url == "https://provider.example/v1/chat/completions":
                payload = json.loads(request.data.decode("utf-8"))
                self.assertEqual("deepseek-v4-pro", payload["model"])
                self.assertEqual(1, payload["max_tokens"])
                return _FakeResponse({"choices": [{"message": {"content": "o"}}]})
            self.fail(f"unexpected request URL: {request.full_url}")

        client = OpenAICompatibleChatClient(
            api_key="unit-placeholder-secret",
            base_url="https://provider.example/v1",
            model="deepseek-v4-pro",
        )
        with patch("packwise_agent.llm.urllib.request.urlopen", fake_urlopen):
            report = client.check_model()

        self.assertTrue(report["valid"])
        self.assertTrue(report["models_reachable"])
        self.assertTrue(report["model_present"])
        self.assertTrue(report["chat_smoke_requested"])
        self.assertTrue(report["chat_smoke_passed"])
        self.assertEqual(["deepseek-v4-pro"], report["matching_model_ids"])
        self.assertEqual(
            ["https://provider.example/v1/models", "https://provider.example/v1/chat/completions"],
            [request.full_url for request in requests],
        )
        self.assertNotIn("unit-placeholder-secret", json.dumps(report))

    def test_model_check_cli_reads_backend_env_and_redacts_output(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            if request.full_url == "https://provider.example/v1/models":
                return _FakeResponse({"data": [{"id": "deepseek-v4-pro"}]})
            if request.full_url == "https://provider.example/v1/chat/completions":
                return _FakeResponse({"choices": [{"message": {"content": "o"}}]})
            self.fail(f"unexpected request URL: {request.full_url}")

        stdout = io.StringIO()
        env = {
            "PACKWISE_LLM_API_KEY": "unit-placeholder-secret",
            "PACKWISE_LLM_BASE_URL": "https://provider.example/v1",
            "PACKWISE_LLM_MODEL": "deepseek-v4-pro",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("packwise_agent.llm.urllib.request.urlopen", fake_urlopen), redirect_stdout(stdout):
                cli_main(["model-check", "--pretty"])

        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertEqual("https://provider.example/v1/models", report["models_endpoint"])
        self.assertEqual("https://provider.example/v1/chat/completions", report["chat_endpoint"])
        self.assertEqual("deepseek-v4-pro", report["model"])
        self.assertTrue(report["chat_smoke_requested"])
        self.assertTrue(report["chat_smoke_passed"])
        self.assertEqual(
            ["https://provider.example/v1/models", "https://provider.example/v1/chat/completions"],
            [request.full_url for request in requests],
        )
        self.assertNotIn("unit-placeholder-secret", stdout.getvalue())

    def test_model_check_cli_can_skip_chat_smoke(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            if request.full_url == "https://provider.example/v1/models":
                return _FakeResponse({"data": [{"id": "deepseek-v4-pro"}]})
            self.fail(f"unexpected request URL: {request.full_url}")

        stdout = io.StringIO()
        env = {
            "PACKWISE_LLM_API_KEY": "unit-placeholder-secret",
            "PACKWISE_LLM_BASE_URL": "https://provider.example/v1",
            "PACKWISE_LLM_MODEL": "deepseek-v4-pro",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch("packwise_agent.llm.urllib.request.urlopen", fake_urlopen), redirect_stdout(stdout):
                cli_main(["model-check", "--skip-chat-smoke", "--pretty"])

        report = json.loads(stdout.getvalue())
        self.assertTrue(report["valid"])
        self.assertFalse(report["chat_smoke_requested"])
        self.assertIsNone(report["chat_smoke_passed"])
        self.assertEqual(["https://provider.example/v1/models"], [request.full_url for request in requests])

    def test_legacy_deepseek_api_key_is_not_used(self):
        env = {
            "DEEPSEEK_API_KEY": "legacy-secret",
            "PACKWISE_LLM_BASE_URL": "https://provider.example/v1",
            "PACKWISE_LLM_MODEL": "deepseek-v4-pro",
        }
        with patch.dict(os.environ, env, clear=True):
            report = OpenAICompatibleChatClient().check_model(require_chat_smoke=False)

        self.assertFalse(report["valid"])
        self.assertIn("Missing PACKWISE_LLM_API_KEY", report["errors"])
        self.assertNotIn("legacy-secret", json.dumps(report))

    def test_base_url_must_be_explicit(self):
        env = {
            "PACKWISE_LLM_API_KEY": "unit-placeholder-secret",
            "PACKWISE_LLM_MODEL": "deepseek-v4-pro",
        }
        with patch.dict(os.environ, env, clear=True):
            report = OpenAICompatibleChatClient().check_model(require_chat_smoke=False)

        self.assertFalse(report["valid"])
        self.assertIsNone(report["models_endpoint"])
        self.assertIn("Missing PACKWISE_LLM_BASE_URL", report["errors"])


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


if __name__ == "__main__":
    unittest.main()
