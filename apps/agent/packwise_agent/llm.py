from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class OpenAICompatibleChatClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("PACKWISE_LLM_API_KEY")
        self.base_url = (base_url or os.environ.get("PACKWISE_LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
        self.model = model or os.environ.get("PACKWISE_LLM_MODEL") or "deepseek-v4-pro"
        self.timeout_seconds = timeout_seconds

    def complete(self, messages: List[ChatMessage]) -> str:
        if not self.api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY or PACKWISE_LLM_API_KEY")

        payload = {
            "model": self.model,
            "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
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
