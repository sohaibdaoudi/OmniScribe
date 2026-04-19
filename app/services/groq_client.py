from __future__ import annotations

from pathlib import Path
from typing import Any

import requests


class GroqClient:
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, whisper_model: str, chat_model: str) -> None:
        self.api_key = api_key
        self.whisper_model = whisper_model
        self.chat_model = chat_model

    def _authorization_header(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("GROQ_API_KEY is not configured. Set it in .env before using AI features.")
        return {"Authorization": f"Bearer {self.api_key}"}

    def health_check(self, timeout_seconds: int = 10) -> dict[str, Any]:
        """Perform a lightweight API reachability/auth check.

        Groq's OpenAI-compatible API does not expose a dedicated /health endpoint,
        so we use /models as an availability probe.
        """
        url = f"{self.BASE_URL}/models"
        headers = {
            **self._authorization_header(),
            "Content-Type": "application/json",
        }
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        if response.status_code >= 400:
            raise RuntimeError(f"Groq health check failed: {response.status_code} {response.text}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Groq health check returned an invalid payload.")
        return payload

    def transcribe_audio(self, audio_file_path: str | Path) -> str:
        file_path = Path(audio_file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        url = f"{self.BASE_URL}/audio/transcriptions"
        headers = self._authorization_header()
        payload = {
            "model": self.whisper_model,
            "response_format": "verbose_json",
        }

        with file_path.open("rb") as handle:
            files = {
                "file": (file_path.name, handle, "application/octet-stream"),
            }
            response = requests.post(url, headers=headers, data=payload, files=files, timeout=300)

        if response.status_code >= 400:
            raise RuntimeError(f"Groq transcription failed: {response.status_code} {response.text}")

        data = response.json()
        transcript_text = data.get("text", "").strip()
        if not transcript_text:
            raise RuntimeError("Groq transcription returned an empty transcript.")
        return transcript_text

    def chat_completion(self, user_prompt: str, system_prompt: str, temperature: float = 0.2) -> str:
        url = f"{self.BASE_URL}/chat/completions"
        headers = {
            **self._authorization_header(),
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.chat_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        response = requests.post(url, headers=headers, json=payload, timeout=180)
        if response.status_code >= 400:
            raise RuntimeError(f"Groq chat completion failed: {response.status_code} {response.text}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError("Groq chat completion returned an unexpected payload.") from exc

        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            content = "".join(text_parts)

        content_text = str(content).strip()
        if not content_text:
            raise RuntimeError("Groq chat completion returned empty content.")

        return content_text
