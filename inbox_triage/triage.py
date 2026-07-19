"""Core data model, input loading, and the batch triage engine."""

from __future__ import annotations

import csv
import mailbox
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

CATEGORIES = (
    "billing",
    "refund",
    "outage",
    "bug",
    "feature-request",
    "praise",
    "spam",
    "question",
    "other",
)

SENTIMENTS = ("positive", "neutral", "negative")

MAX_BODY_CHARS = 4000  # safety cap so one huge email can't blow up a batch prompt


@dataclass(frozen=True)
class Email:
    id: str
    sender: str
    subject: str
    body: str
    received_at: str = ""


@dataclass
class TriageResult:
    category: str
    urgency: int
    sentiment: str
    summary: str
    suggested_reply: str

    def normalized(self) -> "TriageResult":
        """Clamp model output into the contract the report relies on."""
        category = self.category.strip().lower().replace("_", "-")
        if category not in CATEGORIES:
            category = "other"
        sentiment = self.sentiment.strip().lower()
        if sentiment not in SENTIMENTS:
            sentiment = "neutral"
        urgency = min(5, max(1, int(self.urgency)))
        return TriageResult(
            category=category,
            urgency=urgency,
            sentiment=sentiment,
            summary=self.summary.strip(),
            suggested_reply=self.suggested_reply.strip(),
        )


@dataclass
class TriagedEmail:
    email: Email
    result: TriageResult


@dataclass
class RunStats:
    total: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    by_sentiment: dict[str, int] = field(default_factory=dict)
    by_urgency: dict[int, int] = field(default_factory=dict)
    high_urgency: list[TriagedEmail] = field(default_factory=list)

    @classmethod
    def from_results(cls, items: Sequence[TriagedEmail]) -> "RunStats":
        stats = cls(total=len(items))
        for item in items:
            r = item.result
            stats.by_category[r.category] = stats.by_category.get(r.category, 0) + 1
            stats.by_sentiment[r.sentiment] = stats.by_sentiment.get(r.sentiment, 0) + 1
            stats.by_urgency[r.urgency] = stats.by_urgency.get(r.urgency, 0) + 1
        stats.high_urgency = sorted(
            (i for i in items if i.result.urgency >= 4),
            key=lambda i: -i.result.urgency,
        )
        return stats


def load_emails(path: str | Path) -> list[Email]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    if path.suffix.lower() == ".mbox":
        return _load_mbox(path)
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    raise ValueError(f"Unsupported input format: {path.suffix} (expected .csv or .mbox)")


def _load_csv(path: Path) -> list[Email]:
    emails: list[Email] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        required = {"id", "from", "subject", "body"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            emails.append(
                Email(
                    id=row["id"].strip(),
                    sender=row["from"].strip(),
                    subject=row["subject"].strip(),
                    body=row["body"].strip()[:MAX_BODY_CHARS],
                    received_at=(row.get("received_at") or "").strip(),
                )
            )
    return emails


def _load_mbox(path: Path) -> list[Email]:
    emails: list[Email] = []
    box = mailbox.mbox(str(path))
    for i, msg in enumerate(box):
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                        break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")
        emails.append(
            Email(
                id=msg.get("Message-ID", f"mbox-{i + 1}").strip("<> "),
                sender=msg.get("From", "unknown"),
                subject=msg.get("Subject", "(no subject)"),
                body=body.strip()[:MAX_BODY_CHARS],
                received_at=msg.get("Date", ""),
            )
        )
    return emails


def run_triage(
    emails: Sequence[Email],
    provider,
    batch_size: int = 5,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[TriagedEmail]:
    """Triage emails in batches, preserving input order."""
    results: list[TriagedEmail] = []
    for batch in _batched(emails, batch_size):
        batch_results = provider.triage_batch(batch)
        if len(batch_results) != len(batch):
            raise RuntimeError(
                f"Provider returned {len(batch_results)} results for a batch of {len(batch)}"
            )
        for email, result in zip(batch, batch_results):
            results.append(TriagedEmail(email=email, result=result.normalized()))
        if on_progress:
            on_progress(len(results), len(emails))
    return results


def _batched(items: Sequence[Email], size: int) -> Iterable[Sequence[Email]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
