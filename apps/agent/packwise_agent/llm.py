from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


DEFAULT_LLM_MODEL = "deepseek-v4-pro"
MODEL_CHECK_SCHEMA_VERSION = "packwise.model_check.v1"


class OpenAICompatibleChatClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.environ.get("PACKWISE_LLM_BASE_URL")
        self.api_key = api_key if api_key is not None else os.environ.get("PACKWISE_LLM_API_KEY")
        self.base_url = _normalize_base_url(raw_base_url) if raw_base_url else None
        self.model = model or os.environ.get("PACKWISE_LLM_MODEL") or DEFAULT_LLM_MODEL
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: List[ChatMessage], max_tokens: int | None = None) -> str:
        self._require_api_key()
        base_url = self._require_base_url()
        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        request = urllib.request.Request(
            _openai_endpoint(base_url, "chat/completions"),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body: Mapping[str, object] = json.loads(response.read().decode("utf-8"))
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("LLM response did not include choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise RuntimeError("LLM response did not include message.content")
        return message["content"]

    def model_ids(self) -> list[str]:
        self._require_api_key()
        base_url = self._require_base_url()
        request = urllib.request.Request(
            _openai_endpoint(base_url, "models"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body: Mapping[str, object] = json.loads(response.read().decode("utf-8"))
        return _extract_model_ids(body)

    def check_model(self, require_chat_smoke: bool = True) -> Dict[str, Any]:
        report: Dict[str, Any] = {
            "schema_version": MODEL_CHECK_SCHEMA_VERSION,
            "valid": False,
            "base_url": self.base_url,
            "models_endpoint": _openai_endpoint(self.base_url, "models") if self.base_url else None,
            "chat_endpoint": _openai_endpoint(self.base_url, "chat/completions") if self.base_url else None,
            "model": self.model,
            "models_reachable": False,
            "model_present": False,
            "available_model_count": 0,
            "matching_model_ids": [],
            "chat_smoke_requested": require_chat_smoke,
            "chat_smoke_passed": None,
            "errors": [],
        }
        errors: list[str] = []
        model_ids: list[str] = []
        try:
            model_ids = self.model_ids()
            report["models_reachable"] = True
            report["available_model_count"] = len(model_ids)
            matching_model_ids = [model_id for model_id in model_ids if model_id == self.model]
            report["matching_model_ids"] = matching_model_ids
            report["model_present"] = bool(matching_model_ids)
            if not matching_model_ids:
                errors.append(f"Model {self.model} was not listed by /v1/models")
        except Exception as error:  # pragma: no cover - exact urllib failures vary by platform
            errors.append(_redacted_error(error, self.api_key))

        if require_chat_smoke and report["models_reachable"] and report["model_present"]:
            try:
                self.complete([ChatMessage(role="user", content="Reply with: ok")], max_tokens=1)
                report["chat_smoke_passed"] = True
            except Exception as error:  # pragma: no cover - exact urllib failures vary by platform
                report["chat_smoke_passed"] = False
                errors.append(_redacted_error(error, self.api_key))

        report["errors"] = errors
        report["valid"] = bool(
            report["models_reachable"]
            and report["model_present"]
            and (not require_chat_smoke or report["chat_smoke_passed"])
        )
        return report

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("Missing PACKWISE_LLM_API_KEY")

    def _require_base_url(self) -> str:
        if not self.base_url:
            raise RuntimeError("Missing PACKWISE_LLM_BASE_URL")
        return self.base_url


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _openai_endpoint(base_url: str, path: str) -> str:
    normalized = _normalize_base_url(base_url)
    suffix = path.lstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/{suffix}"
    return f"{normalized}/v1/{suffix}"


def _extract_model_ids(body: Mapping[str, object]) -> list[str]:
    data = body.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Models response did not include data[]")
    model_ids: list[str] = []
    for item in data:
        if isinstance(item, Mapping) and isinstance(item.get("id"), str):
            model_ids.append(item["id"])
    return model_ids


def _redacted_error(error: Exception, configured_api_key: str | None = None) -> str:
    text = str(error) if str(error) else error.__class__.__name__
    api_key = configured_api_key or os.environ.get("PACKWISE_LLM_API_KEY")
    if api_key:
        text = text.replace(api_key, "<redacted>")
    return text
