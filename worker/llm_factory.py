"""DeepSeek V4 Flash 的最小 OpenAI-compatible SSE 客户端。"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

import httpx


class DeepSeekChatStream:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        timeout_s: float = 30.0,
        max_tokens: int = 100,
    ) -> None:
        if not api_key.strip():
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.max_tokens = max_tokens
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout_s,
                trust_env=False,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    def chat(self, messages: list[dict], *, temperature: float = 0.65) -> AsyncIterator[str]:
        return self._stream(messages, temperature=temperature)

    async def _stream(self, messages: list[dict], *, temperature: float) -> AsyncIterator[str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            # V4 默认思考；实时语音必须显式关闭以降低首字延迟。
            "thinking": {"type": "disabled"},
        }
        started = time.monotonic()
        first = True
        async with self._get_client().stream(
            "POST",
            f"{self.base_url}/v1/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = (await response.aread()).decode("utf-8", errors="ignore")
                raise RuntimeError(f"DeepSeek HTTP {response.status_code}: {body[:300]}")
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    piece = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                except (ValueError, TypeError, IndexError):
                    continue
                if piece:
                    if first:
                        print(f"[timing] llm_ttfb={(time.monotonic() - started) * 1000:.0f}ms", flush=True)
                        first = False
                    yield piece

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["DeepSeekChatStream"]
