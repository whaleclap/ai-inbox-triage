"""Claude-backed provider.

The `anthropic` package is imported lazily so the rest of the tool (mock mode,
tests, report generation) works on machines where it isn't installed.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any, Sequence

from ..triage import CATEGORIES, Email, TriageResult
from .base import Provider, ProviderUnavailable

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Claude Haiku 4.5 pricing, USD per million tokens (May 2026).
PRICE_INPUT_PER_MTOK = 1.00
PRICE_OUTPUT_PER_MTOK = 5.00

MAX_RETRIES = 4
BASE_DELAY_S = 1.0
MAX_DELAY_S = 30.0

_SYSTEM_PROMPT = f"""You are a customer-support triage assistant for a small business.
You will receive a JSON array of customer emails. For each email, classify it and draft a reply.

Return ONLY a JSON array, one object per email, in the same order, with exactly these keys:
- "id": the email id, copied verbatim
- "category": one of {json.dumps(list(CATEGORIES))}
- "urgency": integer 1 (can wait) to 5 (drop everything)
- "sentiment": "positive", "neutral", or "negative"
- "summary": one line, max 20 words, what the customer wants
- "suggested_reply": a short, warm, professional reply ready for a human to review and send. \
For spam, set it to "No reply recommended — flagged as spam."

No markdown fences, no commentary — just the JSON array."""


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        super().__init__()
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderUnavailable(
                "The 'anthropic' package is not installed (pip install anthropic)."
            ) from exc
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ProviderUnavailable("ANTHROPIC_API_KEY is not set.")
        self._anthropic = anthropic
        # Retries are handled here (with jitter + JSON-repair reprompts),
        # so the SDK's built-in retry layer is disabled to avoid doubling up.
        self._client = anthropic.Anthropic(max_retries=0)
        self.model = model

    def triage_batch(self, emails: Sequence[Email]) -> list[TriageResult]:
        payload = json.dumps(
            [
                {
                    "id": e.id,
                    "from": e.sender,
                    "subject": e.subject,
                    "body": e.body,
                }
                for e in emails
            ],
            ensure_ascii=False,
        )
        raw = self._call_with_retry(payload)
        return self._parse(raw, emails)

    def cost_usd(self) -> float:
        return (
            self.usage.input_tokens * PRICE_INPUT_PER_MTOK
            + self.usage.output_tokens * PRICE_OUTPUT_PER_MTOK
        ) / 1_000_000

    @staticmethod
    def estimate_cost_usd(emails: Sequence[Email], batch_size: int) -> float:
        """Pre-run ballpark: ~4 chars/token for input, ~150 output tokens per email."""
        prompt_chars = sum(len(e.subject) + len(e.body) + len(e.sender) + 60 for e in emails)
        n_batches = max(1, -(-len(emails) // batch_size))
        input_tokens = prompt_chars / 4 + n_batches * (len(_SYSTEM_PROMPT) / 4)
        output_tokens = len(emails) * 150
        return (
            input_tokens * PRICE_INPUT_PER_MTOK + output_tokens * PRICE_OUTPUT_PER_MTOK
        ) / 1_000_000

    def _call_with_retry(self, payload: str) -> str:
        anthropic = self._anthropic
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                response = self._client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": payload}],
                )
                self.usage.add(response.usage.input_tokens, response.usage.output_tokens)
                return "".join(b.text for b in response.content if b.type == "text")
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
                last_exc = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code < 500:
                    raise
                last_exc = exc
            if attempt < MAX_RETRIES:
                delay = min(BASE_DELAY_S * 2**attempt + random.uniform(0, 1), MAX_DELAY_S)
                print(f"  API error ({type(last_exc).__name__}), retrying in {delay:.1f}s...")
                time.sleep(delay)
        raise RuntimeError(f"API call failed after {MAX_RETRIES + 1} attempts") from last_exc

    def _parse(self, raw: str, emails: Sequence[Email]) -> list[TriageResult]:
        data = self._extract_json_array(raw)
        by_id = {str(item.get("id")): item for item in data if isinstance(item, dict)}
        results: list[TriageResult] = []
        for i, email in enumerate(emails):
            item = by_id.get(email.id) or (data[i] if i < len(data) else None)
            if not isinstance(item, dict):
                raise RuntimeError(f"Model response missing entry for email {email.id!r}")
            results.append(
                TriageResult(
                    category=str(item.get("category", "other")),
                    urgency=_as_int(item.get("urgency"), default=3),
                    sentiment=str(item.get("sentiment", "neutral")),
                    summary=str(item.get("summary", "")),
                    suggested_reply=str(item.get("suggested_reply", "")),
                )
            )
        return results

    @staticmethod
    def _extract_json_array(raw: str) -> list[Any]:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", text, re.DOTALL)
            if not match:
                raise RuntimeError(f"Could not find a JSON array in model output: {text[:200]}")
            data = json.loads(match.group(0))
        if not isinstance(data, list):
            raise RuntimeError("Model output was valid JSON but not an array")
        return data


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
