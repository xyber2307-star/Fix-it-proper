"""Thin Groq wrapper returning parsed JSON or a typed error."""

import json
from typing import Any, Literal, Protocol

from groq import APIConnectionError, APIError, APITimeoutError, Groq

AIErrorKind = Literal[
    "timeout", "transport", "unauthorized", "not_found", "rate_limited", "malformed", "empty"
]


class AIError(Exception):
    """A Groq call failure classified for retry decisions."""

    def __init__(self, kind: AIErrorKind) -> None:
        super().__init__(kind)
        self.kind = kind


class AIClient(Protocol):
    """Anything that turns prompts into a parsed JSON object."""

    def complete_json(self, system: str, user: str) -> dict[str, Any]: ...


class GroqClient:
    """Groq chat client pinned to JSON object output."""

    def __init__(self, api_key: str, *, model: str, timeout_s: float = 30.0) -> None:
        self._client = Groq(api_key=api_key, timeout=timeout_s)
        self._model = model

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        """Complete one chat and return the response as a JSON object."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except APITimeoutError as exc:
            raise AIError("timeout") from exc
        except (APIConnectionError, APIError) as exc:
            status = getattr(exc, "status_code", None)
            if status == 401:
                raise AIError("unauthorized") from exc
            if status == 404:
                raise AIError("not_found") from exc
            if status == 429:
                raise AIError("rate_limited") from exc
            raise AIError("transport") from exc
        if not response.choices:
            raise AIError("empty")
        text = response.choices[0].message.content or ""
        if not text.strip():
            raise AIError("empty")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AIError("malformed") from exc
        if not isinstance(payload, dict):
            raise AIError("malformed")
        return payload
