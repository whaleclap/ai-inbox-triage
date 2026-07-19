"""HTML and JSON output. Plain HTML + CSS + vanilla JS — no build step."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from .triage import RunStats, TriagedEmail

_URGENCY_LABELS = {1: "Low", 2: "Minor", 3: "Normal", 4: "High", 5: "Critical"}


def write_json(items: Sequence[TriagedEmail], path: str | Path) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(items),
        "emails": [
            {
                "id": i.email.id,
                "from": i.email.sender,
                "subject": i.email.subject,
                "received_at": i.email.received_at,
                "category": i.result.category,
                "urgency": i.result.urgency,
                "sentiment": i.result.sentiment,
                "summary": i.result.summary,
                "suggested_reply": i.result.suggested_reply,
            }
            for i in items
        ],
    }
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_html(items: Sequence[TriagedEmail], stats: RunStats, path: str | Path, provider_name: str) -> None:
    Path(path).write_text(_render_html(items, stats, provider_name), encoding="utf-8")


def _render_html(items: Sequence[TriagedEmail], stats: RunStats, provider_name: str) -> str:
    rows = "\n".join(_render_row(i) for i in items)
    cards = _render_cards(stats)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Inbox Triage Report</title>
<style>
  :root {{
    --bg: #f6f7f9; --card: #ffffff; --ink: #1f2733; --muted: #67707d;
    --line: #e3e7ec; --accent: #2455a4;
    --u1: #e7f0e7; --u2: #eef3e2; --u3: #fdf3d8; --u4: #fbe3d4; --u5: #f9d7d5;
    --u1-ink: #2e6b34; --u2-ink: #5a7020; --u3-ink: #8a6d1a; --u4-ink: #a04d17; --u5-ink: #a02420;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 15px/1.5 Georgia, 'Times New Roman', serif; background: var(--bg); color: var(--ink); }}
  header {{ padding: 28px 32px 18px; border-bottom: 1px solid var(--line); background: var(--card); }}
  h1 {{ margin: 0 0 4px; font-size: 24px; font-weight: 600; }}
  .meta {{ color: var(--muted); font-size: 13px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 14px; padding: 20px 32px 4px; }}
  .card {{ background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 12px 18px; min-width: 130px; }}
  .card .num {{ font-size: 22px; font-weight: 700; }}
  .card .lbl {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
  main {{ padding: 20px 32px 48px; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 10px 12px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }}
  th {{ background: #eef1f5; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; cursor: pointer; user-select: none; white-space: nowrap; }}
  th .arrow {{ opacity: .45; font-size: 10px; margin-left: 4px; }}
  tr:last-child td {{ border-bottom: none; }}
  .badge {{ display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; white-space: nowrap; }}
  .u1 .badge {{ background: var(--u1); color: var(--u1-ink); }}
  .u2 .badge {{ background: var(--u2); color: var(--u2-ink); }}
  .u3 .badge {{ background: var(--u3); color: var(--u3-ink); }}
  .u4 .badge {{ background: var(--u4); color: var(--u4-ink); }}
  .u5 .badge {{ background: var(--u5); color: var(--u5-ink); }}
  tr.u4 td, tr.u5 td {{ background: #fffaf7; }}
  .cat {{ font-variant: small-caps; letter-spacing: .03em; }}
  .sent-positive {{ color: #2e6b34; }} .sent-negative {{ color: #a02420; }} .sent-neutral {{ color: var(--muted); }}
  details summary {{ cursor: pointer; color: var(--accent); font-size: 13px; }}
  details p {{ margin: 8px 0 0; padding: 10px 12px; background: #f4f6f9; border-left: 3px solid var(--accent); font-size: 14px; white-space: pre-wrap; }}
  .subject {{ font-weight: 600; }}
  .from {{ color: var(--muted); font-size: 13px; }}
</style>
</head>
<body>
<header>
  <h1>Inbox Triage Report</h1>
  <div class="meta">Generated {generated} &middot; provider: {html.escape(provider_name)} &middot; {stats.total} messages &middot; click a column header to sort</div>
</header>
<div class="cards">{cards}</div>
<main>
<table id="triage">
  <thead>
    <tr>
      <th data-key="urgency" data-num="1">Urgency<span class="arrow">&#8597;</span></th>
      <th data-key="category">Category<span class="arrow">&#8597;</span></th>
      <th data-key="sentiment">Sentiment<span class="arrow">&#8597;</span></th>
      <th data-key="from">From<span class="arrow">&#8597;</span></th>
      <th data-key="subject">Subject &amp; summary<span class="arrow">&#8597;</span></th>
      <th>Suggested reply</th>
    </tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>
</main>
<script>
(function () {{
  var table = document.getElementById('triage');
  var tbody = table.tBodies[0];
  var dir = {{}};
  table.tHead.addEventListener('click', function (e) {{
    var th = e.target.closest('th');
    if (!th || !th.dataset.key) return;
    var key = th.dataset.key;
    var numeric = th.dataset.num === '1';
    dir[key] = -(dir[key] || (numeric ? 1 : -1));
    var rows = Array.prototype.slice.call(tbody.rows);
    rows.sort(function (a, b) {{
      var av = a.dataset[key], bv = b.dataset[key];
      if (numeric) return (Number(av) - Number(bv)) * dir[key];
      return av.localeCompare(bv) * dir[key];
    }});
    rows.forEach(function (r) {{ tbody.appendChild(r); }});
  }});
}})();
</script>
</body>
</html>
"""


def _render_cards(stats: RunStats) -> str:
    critical = stats.by_urgency.get(5, 0) + stats.by_urgency.get(4, 0)
    negative = stats.by_sentiment.get("negative", 0)
    top_cat = max(stats.by_category.items(), key=lambda kv: kv[1])[0] if stats.by_category else "-"
    cards = [
        (str(stats.total), "messages"),
        (str(critical), "high urgency"),
        (str(negative), "negative"),
        (html.escape(top_cat), "top category"),
    ]
    return "".join(
        f'<div class="card"><div class="num">{num}</div><div class="lbl">{lbl}</div></div>'
        for num, lbl in cards
    )


def _render_row(item: TriagedEmail) -> str:
    e, r = item.email, item.result
    label = _URGENCY_LABELS[r.urgency]
    return (
        f'    <tr class="u{r.urgency}" data-urgency="{r.urgency}" '
        f'data-category="{html.escape(r.category, quote=True)}" '
        f'data-sentiment="{html.escape(r.sentiment, quote=True)}" '
        f'data-from="{html.escape(e.sender, quote=True)}" '
        f'data-subject="{html.escape(e.subject, quote=True)}">\n'
        f'      <td><span class="badge">{r.urgency} &middot; {label}</span></td>\n'
        f'      <td class="cat">{html.escape(r.category)}</td>\n'
        f'      <td class="sent-{r.sentiment}">{html.escape(r.sentiment)}</td>\n'
        f'      <td class="from">{html.escape(e.sender)}</td>\n'
        f'      <td><div class="subject">{html.escape(e.subject)}</div>'
        f'<div>{html.escape(r.summary)}</div></td>\n'
        f'      <td><details><summary>show draft</summary>'
        f'<p>{html.escape(r.suggested_reply)}</p></details></td>\n'
        f"    </tr>"
    )
