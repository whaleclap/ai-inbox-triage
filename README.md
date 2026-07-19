# inbox-triage

[![tests](https://github.com/whaleclap/ai-inbox-triage/actions/workflows/ci.yml/badge.svg)](https://github.com/whaleclap/ai-inbox-triage/actions)

CLI tool for small support teams drowning in email. Point it at a batch of
customer messages (CSV or `.mbox`), and it classifies each one (category,
urgency 1-5, sentiment), writes a one-line summary, and drafts a suggested
reply — then produces a sortable HTML report, a JSON export, and terminal
summary stats.

Classification runs on Claude (Haiku 4.5 by default) via the Anthropic API.
A deterministic offline mock mode is included so you can try everything
without an API key.

## 30-second quickstart

Requires Python 3.10+. No dependencies for mock mode.

```
git clone <this repo>
cd ai-inbox-triage

# Offline demo — no API key, no install:
python -m inbox_triage sample_data/emails.csv --provider mock --out demo_output

# Real mode — uses Claude:
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...        # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m inbox_triage sample_data/emails.csv

# Also real, no API key — routes through a locally installed Claude Code CLI:
python -m inbox_triage sample_data/emails.csv --provider claude-cli
```

Then open `demo_output/report.html` in a browser. The pre-generated copy
checked in at [`demo_output/report.html`](demo_output/report.html) is real
Claude output (produced via the `claude-cli` provider on the synthetic sample
data — no real customer data anywhere).

## What a run looks like

```
Triaging 15 emails with provider 'mock'...
  5/15 processed
  10/15 processed
  15/15 processed

=== Summary (15 messages) ===
By category:
  billing            3  ###
  spam               2  ##
  ...
By urgency:
  5 (critical)       1  #
  ...
Needs attention first:
  [5] URGENT: dashboard completely down  (ops@brightlane-logistics.example.com)

HTML report: demo_output\report.html
JSON export: demo_output\results.json
```

## Architecture

```
                 +-------------------+
 emails.csv ---> |  triage.py        |         +----------------------+
 inbox.mbox ---> |  load_emails()    | ------> |  providers/          |
                 |  run_triage()     | batches |    anthropic  (Claude)|
                 +-------------------+ <------ |    mock  (heuristics)|
                          |           results  +----------------------+
                          v
                 +-------------------+
                 |  report.py        | ---> report.html  (sortable, color-coded)
                 |                   | ---> results.json
                 +-------------------+
                          |
                 cli.py --+--> terminal summary + cost readout
```

- `inbox_triage/cli.py` — argument parsing, provider selection/fallback, output
- `inbox_triage/triage.py` — data model, CSV/mbox loaders, batching engine
- `inbox_triage/providers/` — the two backends behind one small interface
- `inbox_triage/report.py` — HTML (plain HTML/CSS + vanilla JS, no build step) and JSON

## Providers

### `--provider anthropic` (default)

Calls the Anthropic Messages API with `claude-haiku-4-5-20251001` (override
with `--model`). Emails are sent in batches (default 5 per request,
`--batch-size`) as a JSON array; the model returns one JSON object per email.

- Reads `ANTHROPIC_API_KEY` from the environment. Never hardcode keys.
- Retries with exponential backoff + jitter on rate limits, 5xx, and
  connection errors (up to 4 retries).
- Prints a cost estimate before running (rough: ~4 chars/token in, ~150
  tokens out per email, at Haiku 4.5 pricing of $1/$5 per million tokens)
  and asks for confirmation. After the run it prints the *actual* token
  usage and cost from the API's usage numbers. The 15-email sample costs
  well under a cent.
- If the `anthropic` package or the API key is missing, the CLI prints a
  notice and falls back to mock mode rather than crashing.

### `--provider mock`

An honest fake: deterministic keyword heuristics, no network, no key, free.
It exists so the tool can be demoed offline and tested in CI — it is not an
LLM and will misread anything subtle (sarcasm, mixed intent, unusual
phrasing). Real classification quality comes from the Anthropic provider.

## Input formats

- **CSV** with columns `id, from, subject, body` (optional `received_at`).
  See `sample_data/emails.csv`.
- **mbox** — standard Unix mailbox files, parsed with Python's stdlib
  `mailbox` module. Plain-text parts are used; bodies are capped at 4,000
  characters per message before being sent to the model.

`sample_data/emails.csv` is entirely synthetic — invented senders on
`example.com` domains, written to cover the common shapes of a support
inbox (billing dispute, refund, outage, bug report, praise, spam, feature
request, angry escalation, etc.). No real customer data anywhere in this repo.

## Tests

```
python tests/test_mock_pipeline.py     # no dependencies needed
# or, if you have pytest:
pytest tests/
```

The tests run the full mock pipeline end-to-end: loading the sample CSV,
batching, classification sanity checks, JSON well-formedness, HTML escaping
of hostile input, and the no-key fallback path.

## Screenshots

To capture the report for a portfolio or client deck: open
`demo_output/report.html` in a browser, set the window to ~1280px wide,
and screenshot the top of the page so the stat cards and the first few
color-coded rows (including the red critical row) are visible. Click the
Urgency header first so critical items sort to the top.

## License

MIT — see [LICENSE](LICENSE).
