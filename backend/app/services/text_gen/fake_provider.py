"""Deterministic fake provider for tests/dev (LLM_BACKEND=fake, the default)."""
from __future__ import annotations

import hashlib
import re

from app.services.text_gen.base import TextGenError


class FakeTextGenProvider:
    name = "fake"

    def generate(self, prompt: str, platform: str, *, max_tokens: int, temperature: float,
                 timeout_sec: int) -> str:
        # derive a stable seed from the prompt so output is deterministic per clip
        seed = hashlib.sha256(f"{platform}|{prompt}".encode()).hexdigest()[:8]
        topic = self._topic(prompt)
        titles = [
            f"{topic}: главное за 60 секунд",
            f"Секрет про {topic}, о котором молчат",
            f"{topic} — 3 ошибки, которые совершают все",
        ]
        description = (
            f"Разбираем {topic} коротко и по делу. Клип #{seed} подготовлен локальным "
            f"AI Clipper'ом. Смотри до конца и подписывайся!"
        )
        hashtags = ["#shorts", "#fyp", f"#{re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', topic)[:12]}",
                    "#clipper", "#вирально", "#смотри"]
        import json

        return json.dumps(
            {"titles": titles, "description": description, "hashtags": hashtags},
            ensure_ascii=False,
        )

    @staticmethod
    def _topic(prompt: str) -> str:
        match = re.search(r"Тема клипа: (.+)", prompt)
        if match:
            return match.group(1).strip()[:60]
        return "момент из видео"
