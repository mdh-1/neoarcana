# Neoarcana

A tarot reading, plainly given. No candles, no costumes: a deck shuffled by
atmospheric noise, read by a language model, and set down in clear prose.

FastAPI-native — one codebase, one process, no Node toolchain. The frontend is
six Jinja templates, one hand-written stylesheet and a 40-line script; the
interpretation streams into the page over Server-Sent Events as the model
writes it.

## Quick start

```bash
./run.sh
```

That's it. First run creates a virtualenv and installs dependencies; then it
serves http://localhost:8001. **No API keys are required** — without them the
app shuffles with the OS CSPRNG and streams a stand-in interpretation from a
mock provider, so the whole flow works offline.

For real readings:

```bash
cp .env.example .env   # then add whichever keys you have
```

| Key | Provides | Without it |
|---|---|---|
| `DEEPSEEK_API_KEY` / `GEMINI_API_KEY` / `MISTRAL_API_KEY` | interpretations (first configured provider wins, falls through on errors) | mock interpreter |
| `RANDOM_API_KEY` ([random.org](https://api.random.org)) | true atmospheric-noise shuffles | OS cryptographic randomness |

Model IDs live in config (`DEEPSEEK_MODEL`, `GEMINI_MODEL`, `MISTRAL_MODEL` in
`.env`), so when a vendor retires a model the fix is an env edit, not a deploy.

The reading page honestly reports which entropy source shuffled it.

## How a reading works

1. **Draw** — `POST /readings` samples unique card indices `0..77` plus an
   independent reversal bit per card (every card, including The Fool, has
   equal odds either way), assigns spread positions server-side, and stores
   the reading under a permalink id.
2. **Show** — the reading page renders immediately: cards, traditional
   Rider–Waite and Thoth meanings, position descriptions. No waiting on the
   model to see your draw.
3. **Interpret** — the page opens an `EventSource` to
   `/readings/{id}/stream`; the LLM's prose streams in token by token and is
   persisted onto the reading, so refreshing or sharing the permalink shows
   the finished text.

Positions are server truth and never round-trip through the model — the
model receives the spread and returns only prose, so there is nothing to
mis-parse.

## Layout

```
app/
├── main.py              # routes: pages, SSE stream, /api/v1 JSON, rate limit
├── config.py            # pydantic-settings; every key optional
├── domain/
│   ├── deck.py          # card schema + pure draw/assembly logic
│   └── spreads.py       # position definitions — single source of truth
├── providers/
│   ├── entropy.py       # random.org → CSPRNG fallback
│   └── llm.py           # deepseek/gemini/mistral via one httpx streaming client
├── services/reading.py  # reading lifecycle + bounded in-memory store
├── templates/           # Jinja pages
└── static/              # style.css, reading.js, 640px card images
data/cards.json          # all 78 cards, schema-validated at startup
tests/                   # offline-friendly; no keys, no network
deploy/                  # Caddyfile, systemd unit, runbook
archive/                 # full-res source scans (untracked; site serves 640px)
```

The legacy codebases this grew from live in git history (`git log --all --
-- tarot-main/` for the original backend); the working tree carries only
the current app.

## Development

```bash
.venv/bin/python -m pytest        # run the tests
PORT=9000 ./run.sh                # different port
```

Useful endpoints: `GET /health`, `GET /api/v1/readings/{id}` (JSON view of a
reading — the seam where a future SPA or mobile app would attach).

Design notes:

- **The deck is data, not code.** `data/cards.json` is validated by a
  Pydantic schema at startup; a malformed entry fails the boot, not a
  rendering three weeks later.
- **Readings persist to SQLite** (`data/readings.db`, newest 5000).
  Permalinks survive restarts and deploys. Only the draw is stored —
  card numbers and orientations — because the deck and spreads are
  static, so rehydration replays the same assembly the draw used.
- **Rate limiting** is per-IP (default 10 readings/hour,
  `READINGS_PER_HOUR` in `.env`) because each reading spends LLM credit.
- **No build step, on purpose.** The stylesheet is plain modern CSS with
  design tokens in `:root`; there is nothing to compile, watch or update.

## Deploying

See [deploy/DEPLOY.md](deploy/DEPLOY.md) — single uvicorn process behind
Caddy, no build step. `git push`, then `sudo /srv/neoarcana/deploy/deploy.sh`
on the server: it pulls, tests, restarts and smoke-tests the live site. Two constraints matter: run **one worker** (readings
and the rate limiter are in process memory) and keep `--proxy-headers` on
(so the rate limiter sees real client IPs rather than Caddy's).

Offered for reflection.
