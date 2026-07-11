# Contributing

This is a small, solo-maintained tool. Issues and pull requests are welcome — no formal process, just a few things that'll make a PR easy to review.

## Running it locally

```bash
git clone https://github.com/breisnerlopez/rensi-claude-dashboard.git
cd rensi-claude-dashboard
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
rensi-dashboard start --foreground
```

`--foreground` runs the server (and its in-process scheduler) in your terminal instead of daemonizing, so `print()`/tracebacks are visible while you work.

## Adding a language

UI copy lives in one place: the `STRINGS` object near the top of the `<script>` block in `rensi_dashboard/web/index.html`. It has one object per language (currently `en`, `es`), keyed identically — every key that exists in `en` must exist in every other language too, or that string silently falls back to English.

To add a language:
1. Copy the `en` block, translate every value, keep every key name identical.
2. Add the new two-letter code to the `LANG` resolver right above `STRINGS` (the line that checks `BROWSER_TAG.slice(0, 2)`).
3. Add its abbreviated weekday names to `dayAbbr` (used for the "this week" chart).
4. Manually check `?lang=<code>` in a browser — specifically the session-detail modal and its timeline, the most string-dense part of the page.

"Rensi Dashboard" (the browser tab title and the in-app header) is a proper name and is never translated — same treatment as "Claude Code" elsewhere in the file.

Numbers (tokens, percentages, days) are deliberately **not** regionalized — they always use a dot as the decimal separator, app-wide, so a token count never misreads as a different number next to a percentage on this data-dense dashboard. Only dates/times/weekday names follow the visitor's locale.

## Reporting a bug

Open an issue with what you ran, what you expected, and what actually happened. If it's about the official rate-limit numbers being wrong/missing, include whether `claude-monitor` is installed (`pipx list` will show it) and the output of `rensi-dashboard status`.

## Code style

No linter/formatter is enforced — match the existing style in the file you're editing (the Python side is deliberately dense/terse; the JS side is plain ES5-ish vanilla, no build step, no framework — keep it that way).
