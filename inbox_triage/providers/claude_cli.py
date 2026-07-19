"""Claude Code CLI-backed provider.

Runs the same prompt as the API provider through a locally installed,
already-authenticated `claude` CLI (https://claude.com/claude-code). Useful for
demos and small batches on machines with a Claude subscription but no API key.
Token accounting isn't available through the CLI, so cost reads as $0.00 here;
real per-token costs apply on the API provider.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Sequence

from ..triage import Email, TriageResult
from .anthropic_provider import AnthropicProvider, _SYSTEM_PROMPT
from .base import Provider, ProviderUnavailable

TIMEOUT_S = 240


class ClaudeCliProvider(Provider):
    name = "claude-cli"

    def __init__(self) -> None:
        super().__init__()
        self._bin = shutil.which("claude")
        if not self._bin:
            raise ProviderUnavailable("The 'claude' CLI is not installed or not on PATH.")

    def triage_batch(self, emails: Sequence[Email]) -> list[TriageResult]:
        payload = json.dumps(
            [
                {"id": e.id, "from": e.sender, "subject": e.subject, "body": e.body}
                for e in emails
            ],
            ensure_ascii=False,
        )
        prompt = f"{_SYSTEM_PROMPT}\n\nEmails:\n{payload}"
        proc = subprocess.run(
            [self._bin, "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_S,
            shell=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed (exit {proc.returncode}): {proc.stderr[:300]}")
        # Same parsing/normalization path as the API provider.
        parser = AnthropicProvider.__new__(AnthropicProvider)
        parser.usage = self.usage
        return AnthropicProvider._parse(parser, proc.stdout, emails)
