# rensi-claude-dashboard

A self-hosted, mobile-first dashboard for tracking [Claude Code](https://claude.com/claude-code) usage: official 5-hour and weekly rate limits, per-project token/cost estimates, and a **live view of every running session** — active subagents, workflows and their phases, open tasks/goals, and a full tool-use timeline, refreshed independently on a fast ~15s cycle.

No dependencies, no build step: a Python stdlib server + two small cron-style scripts, and one vanilla-JS `index.html`.

If you find this useful, **a star helps other people find it** → see the link at the bottom.

## What it shows

- **Bloque de 5h / Semana** — the official rate-limit percentages, straight from Anthropic's usage API (same numbers as claude.ai), with a sustainability projection ("at this pace you have ~N days left").
- **Conversaciones** — one card per active/recent project: context-window occupancy, cost estimate, and a one-line status ("5/6 tareas · 1 subagente en curso · 1 workflow en curso").
- **Session detail** (tap/click a card) — full detail for that session: goals/tasks with status and blockers, subagents with their descriptions and state, workflows with their phase pipeline, a tool-use histogram, and a scrollable activity timeline. On a wide screen this opens as a right-anchored panel with an independently-scrolling state column and activity column; on a phone it's a full-bleed sheet.
- **Hoy / Esta semana / Historial** — token and cost trends over time.

Everything except the two official rate-limit percentages is explicitly labeled as a local estimate.

## Architecture

```
aggregate.py   -- parses ~/.claude/projects/**/*.jsonl, calls the official usage API,
                  writes data.json + session/<slug>.json. Runs every 180s via systemd timer.
aggregate.py --fast
               -- lightweight pass: re-parses transcripts and refreshes only the
                  sessions/workflows/agents view, skipping the slow API call.
                  Runs every ~15s so an open session feels live.
serve.py       -- stdlib http.server, whitelist routes only (/, /data.json,
                  /session/<slug>.json). Requires a shared-secret header
                  (see Security below) -- fails closed if unset.
index.html     -- the whole frontend. No build step, no framework.
```

Deployed as three systemd units: `claude-usage-web.service` (the server), `claude-usage-data.timer` (full refresh, 180s), `claude-usage-sessions.timer` (fast sessions-only refresh, 15s).

## Security

This dashboard reads local Claude Code transcripts, which can contain business-sensitive detail (project names, file paths, commands). It's designed to sit behind a reverse proxy that handles real authentication (this deployment uses [Authentik](https://goauthentik.io/) forward-auth via Traefik) — `serve.py` itself only checks a shared-secret header (`X-Dashboard-Token`) injected by the proxy *after* that auth step, and refuses to start if the token isn't configured. It does not implement its own login.

A regex-based redactor strips common secret formats (API keys, tokens, PEM blocks) and filesystem paths from anything written to disk. It's a best-effort net, not a guarantee — don't put this on the open internet without a real auth layer in front of it.

## Setup

1. Point the three systemd units at your own paths / usage-monitor CLI (this build shells out to [`claude-monitor`](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) for official rate-limit percentages).
2. Generate a token and put it in an env file: `openssl rand -hex 32`.
3. Put a reverse proxy with real auth in front of `serve.py`, and have it inject `X-Dashboard-Token` matching that env file.
4. `systemctl enable --now claude-usage-web.service claude-usage-data.timer claude-usage-sessions.timer`.

## License

MIT — see [LICENSE](LICENSE).

---

Built by [Breisner Lopez](https://breisner.info) · [GitHub](https://github.com/breisnerlopez)

⭐ **If this is useful to you, starring the repo is the easiest way to say so** — it's how other people find small tools like this.
