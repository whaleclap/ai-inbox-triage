"""Provider interface shared by the real and mock backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

from ..triage import Email, TriageResult


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


class ProviderUnavailable(RuntimeError):
    """Raised when a provider can't be constructed (missing SDK, missing key)."""


class Provider(ABC):
    name: str = "base"

    def __init__(self) -> None:
        self.usage = Usage()

    @abstractmethod
    def triage_batch(self, emails: Sequence[Email]) -> list[TriageResult]:
        """Return one TriageResult per email, in the same order."""

    def cost_usd(self) -> float:
        """Actual (or estimated) cost of API usage so far. Mock is free."""
        return 0.0
