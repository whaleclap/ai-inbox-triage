"""Offline demo provider.

This is NOT an LLM. It classifies with deterministic keyword heuristics so the
tool can be demoed, tested, and CI-run with no API key and no network access.
Expect it to be roughly right on obvious emails and wrong on subtle ones —
that gap is exactly what the Anthropic provider is for.
"""

from __future__ import annotations

import re
from typing import Sequence

from ..triage import Email, TriageResult
from .base import Provider

# Order matters: first matching category wins.
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("spam", ("unsubscribe", "limited time offer", "act now", "winner", "crypto", "seo services", "guaranteed ranking")),
    ("outage", ("down", "outage", "cannot access", "can't access", "unreachable", "503", "500 error", "not loading")),
    ("refund", ("refund", "money back", "charge back", "chargeback", "cancel my subscription")),
    ("billing", ("invoice", "billed", "billing", "charged", "charge", "payment", "receipt", "overcharged")),
    ("bug", ("bug", "broken", "error", "crash", "doesn't work", "does not work", "glitch")),
    ("feature-request", ("feature request", "would be great if", "please add", "any plans to", "wish there was", "suggestion")),
    ("praise", ("love", "thank you", "thanks so much", "amazing", "great job", "fantastic", "awesome")),
    ("question", ("how do i", "how can i", "is it possible", "question", "wondering", "?")),
]

_URGENT_WORDS = ("urgent", "asap", "immediately", "right now", "emergency", "critical", "losing money", "production")
_POSITIVE_WORDS = ("love", "great", "amazing", "thank", "fantastic", "awesome", "happy", "excellent", "perfect")
_NEGATIVE_WORDS = ("angry", "frustrated", "terrible", "worst", "unacceptable", "disappointed", "furious", "ridiculous", "awful", "broken", "refund")

_REPLIES: dict[str, str] = {
    "billing": (
        "Thanks for flagging this — I'm looking into your billing history now. "
        "Could you confirm the last 4 digits of the card and the invoice date so I can trace the charge? "
        "If anything was billed in error we'll correct it right away."
    ),
    "refund": (
        "Sorry this didn't work out. I've started the refund review on our side — "
        "could you confirm the order or invoice number? Approved refunds are returned "
        "to the original payment method within 5-7 business days."
    ),
    "outage": (
        "Thanks for the report — we're treating this as a priority and investigating now. "
        "I'll follow up as soon as we've identified the cause. You can also watch our status page for live updates."
    ),
    "bug": (
        "Thanks for the detailed report. I've logged this with our engineering team. "
        "Could you share what device/browser you're on and roughly when it last happened? "
        "That will help us reproduce it quickly."
    ),
    "feature-request": (
        "Thanks for the suggestion — I've passed it to our product team and added your vote to the request. "
        "We can't promise a timeline, but we'll let you know if it ships."
    ),
    "praise": (
        "Thank you so much for the kind words — messages like this genuinely make our week. "
        "If there's ever anything we can improve, we're all ears."
    ),
    "spam": "No reply recommended — flagged as spam.",
    "question": (
        "Thanks for reaching out. Happy to help — I've included the most relevant details below, "
        "and if anything is still unclear just reply to this email."
    ),
    "other": (
        "Thanks for getting in touch. I've routed your message to the right person on our team "
        "and you'll hear back within one business day."
    ),
}


class MockProvider(Provider):
    name = "mock"

    def triage_batch(self, emails: Sequence[Email]) -> list[TriageResult]:
        return [self._triage_one(e) for e in emails]

    def _triage_one(self, email: Email) -> TriageResult:
        text = f"{email.subject} {email.body}".lower()

        category = "other"
        for cat, keywords in _CATEGORY_RULES:
            if any(kw in text for kw in keywords):
                category = cat
                break

        urgency = 2
        if category == "outage":
            urgency = 5
        elif category in ("billing", "refund", "bug"):
            urgency = 3
        elif category in ("praise", "spam"):
            urgency = 1
        if any(w in text for w in _URGENT_WORDS):
            urgency = min(5, urgency + 1)

        pos = sum(text.count(w) for w in _POSITIVE_WORDS)
        neg = sum(text.count(w) for w in _NEGATIVE_WORDS)
        sentiment = "positive" if pos > neg else "negative" if neg > pos else "neutral"

        return TriageResult(
            category=category,
            urgency=urgency,
            sentiment=sentiment,
            summary=self._summarize(email),
            suggested_reply=_REPLIES[category],
        )

    @staticmethod
    def _summarize(email: Email) -> str:
        first_sentence = re.split(r"(?<=[.!?])\s", email.body.strip(), maxsplit=1)[0]
        if len(first_sentence) > 110:
            first_sentence = first_sentence[:107].rstrip() + "..."
        return first_sentence or email.subject
