"""End-to-end tests for the offline (mock) path.

Runs under pytest, or directly: python tests/test_mock_pipeline.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from inbox_triage.providers import MockProvider, ProviderUnavailable, get_provider
from inbox_triage.report import write_html, write_json
from inbox_triage.triage import CATEGORIES, Email, RunStats, load_emails, run_triage

SAMPLE_CSV = Path(__file__).resolve().parents[1] / "sample_data" / "emails.csv"


def test_load_sample_csv():
    emails = load_emails(SAMPLE_CSV)
    assert len(emails) == 15
    assert emails[0].id == "em-001"
    assert all(e.sender and e.subject and e.body for e in emails)


def test_mock_provider_is_deterministic():
    emails = load_emails(SAMPLE_CSV)
    a = MockProvider().triage_batch(emails)
    b = MockProvider().triage_batch(emails)
    assert [vars(r) for r in a] == [vars(r) for r in b]


def test_mock_classifications_are_sane():
    emails = load_emails(SAMPLE_CSV)
    results = {e.id: r for e, r in zip(emails, MockProvider().triage_batch(emails))}
    assert results["em-003"].category == "outage"
    assert results["em-003"].urgency == 5
    assert results["em-005"].category == "spam"
    assert results["em-004"].category == "praise"
    assert results["em-004"].sentiment == "positive"
    assert results["em-002"].category == "refund"
    for r in results.values():
        assert r.category in CATEGORIES
        assert 1 <= r.urgency <= 5
        assert r.suggested_reply


def test_run_triage_batching_preserves_order():
    emails = load_emails(SAMPLE_CSV)
    progress: list[tuple[int, int]] = []
    items = run_triage(emails, MockProvider(), batch_size=4, on_progress=lambda d, t: progress.append((d, t)))
    assert [i.email.id for i in items] == [e.id for e in emails]
    assert progress[-1] == (15, 15)
    assert len(progress) == 4  # ceil(15 / 4) batches


def test_normalization_clamps_bad_values():
    from inbox_triage.triage import TriageResult

    r = TriageResult(category="Nonsense", urgency=99, sentiment="angry", summary=" x ", suggested_reply=" y ").normalized()
    assert r.category == "other"
    assert r.urgency == 5
    assert r.sentiment == "neutral"
    assert (r.summary, r.suggested_reply) == ("x", "y")


def test_outputs_are_wellformed(tmp_dir: Path | None = None):
    emails = load_emails(SAMPLE_CSV)
    items = run_triage(emails, MockProvider(), batch_size=5)
    stats = RunStats.from_results(items)

    out = tmp_dir or Path(tempfile.mkdtemp(prefix="triage-test-"))
    html_path = out / "report.html"
    json_path = out / "results.json"
    write_html(items, stats, html_path, "mock")
    write_json(items, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["count"] == 15
    assert {"id", "category", "urgency", "sentiment", "summary", "suggested_reply"} <= set(data["emails"][0])

    html_text = html_path.read_text(encoding="utf-8")
    assert html_text.startswith("<!DOCTYPE html>")
    assert html_text.count("<tr") == 16  # header + 15 rows
    assert "URGENT: dashboard completely down" in html_text
    # user-supplied text must be escaped, not raw
    assert "?!" in load_emails(SAMPLE_CSV)[0].subject
    assert "<script>alert" not in html_text


def test_html_escapes_injection():
    hostile = Email(id="x", sender="a@example.com", subject="<script>alert(1)</script>", body="hello")
    items = run_triage([hostile], MockProvider())
    out = Path(tempfile.mkdtemp(prefix="triage-test-"))
    write_html(items, RunStats.from_results(items), out / "r.html", "mock")
    text = (out / "r.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_anthropic_provider_unavailable_without_key():
    """Without the SDK or a key, the factory must raise (CLI then falls back to mock)."""
    import os

    key = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        try:
            get_provider("anthropic")
        except ProviderUnavailable:
            pass  # expected on machines without the SDK or key
        else:
            raise AssertionError("expected ProviderUnavailable")
    finally:
        if key is not None:
            os.environ["ANTHROPIC_API_KEY"] = key


def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_main())
