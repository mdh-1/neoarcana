# Deploying Neoarcana

Single FastAPI process behind Caddy. No build step, no container, no database.

Assumes `/srv/neoarcana` as the app root and a `neoarcana` service user —
adjust both consistently in `neoarcana.service` and `Caddyfile` if you
prefer somewhere else.

## Two things to get right

**Proxy headers on.** Behind Caddy every request arrives from 127.0.0.1.
Without `--proxy-headers`, the rate limiter treats the whole internet as
one visitor and the 11th reading of the hour is refused for everyone.
Verified: twelve distinct forwarded IPs all pass; one repeated IP is cut
off at exactly ten.

**One worker, by preference.** Readings live in SQLite, so workers do
share them (measured: 60/60 concurrent fetches across three workers
succeed, where 44 of 60 used to 404 with the in-memory store). But the
per-IP rate limiter is still process-local, so N workers means N x
`READINGS_PER_HOUR` before anyone is throttled — and one async worker
handles this traffic comfortably.

Both are already set in `neoarcana.service`.

## State

The reading database lives at `/var/lib/neoarcana/readings.db`, created
by systemd's `StateDirectory` (the app directory itself is read-only
under `ProtectSystem=strict`). It holds the draw — card numbers and
orientations — plus the question and interpretation; the deck and spread
definitions are static, so a reading read back from disk rehydrates
through the same code path that created it.

Nothing else is stateful. Back it up with `sqlite3 ... .backup`, or
don't: losing it costs old permalinks, nothing more.

## Retiring the old service

The legacy app also listened on 8001, so it has to stop before the new
one starts. If you don't remember how it was launched:

```sh
systemctl list-units --type=service | grep -iE 'tarot|neoarcana'
sudo ss -tlnp | grep :8001
ps aux | grep -iE 'uvicorn|tarot_reader|main.py' | grep -v grep
```

Then stop and disable whatever that turns up, e.g.:

```sh
sudo systemctl stop  old-tarot.service
sudo systemctl disable old-tarot.service
```

The old Caddy site served the React build from
`/var/lib/caddy/celtic-cross-journey/dist` and proxied only `/reading` to
the legacy API. Replacing the `# ---- Neoarcana ----` block with the one
in `deploy/Caddyfile` retires both halves at once; the old `dist`
directory is then orphaned and can be deleted once the new site is
confirmed working. The old JSON endpoint (`POST /reading`) disappears;
the new equivalent is `POST /readings` plus `GET /api/v1/readings/{id}`.

## First deploy

```sh
# 1. User and directory
sudo useradd --system --home /srv/neoarcana --shell /usr/sbin/nologin neoarcana
sudo mkdir -p /srv/neoarcana
sudo chown neoarcana:neoarcana /srv/neoarcana

# 2. Clone from GitHub (public repo, so no deploy key is needed)
sudo git clone https://github.com/mdh-1/neoarcana.git /srv/neoarcana
sudo chown -R neoarcana:neoarcana /srv/neoarcana

# 3. Virtualenv on the server
sudo -u neoarcana python3 -m venv /srv/neoarcana/.venv
sudo -u neoarcana /srv/neoarcana/.venv/bin/pip install -r /srv/neoarcana/requirements.txt

# 4. Secrets — never rsynced, never committed
sudo -u neoarcana tee /srv/neoarcana/.env >/dev/null <<'ENV'
GEMINI_API_KEY=...
RANDOM_API_KEY=...   # the site's copy claims atmospheric noise only when this is set
LLM_PROVIDERS=gemini,mistral,deepseek
READINGS_PER_HOUR=10
ENV
sudo chmod 600 /srv/neoarcana/.env

# 5. Service
sudo cp /srv/neoarcana/deploy/neoarcana.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now neoarcana
systemctl status neoarcana

# 5b. Caddy site file (imported by /etc/caddy/Caddyfile via `import sites/*.caddy`)
sudo install -d /etc/caddy/sites
sudo cp /srv/neoarcana/deploy/neoarcana.caddy /etc/caddy/sites/
sudo install -d -o caddy -g caddy /var/log/caddy   # the log block needs this
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy

# 6. Caddy
# (Caddy is handled in 5b above)
```

## Verify

```sh
curl -s localhost:8001/health                     # {"ok":true}
curl -sI https://neoarcana.net/ | head -1         # 200
curl -sI https://neoarcana.net/static/tarot-images/the_fool.jpg | head -1

# End to end: draw, stream, confirm the interpretation arrived
ID=$(curl -s -X POST https://neoarcana.net/readings \
      -d 'spread_key=one_card&question=Is the deploy healthy?' \
      -o /dev/null -w '%{redirect_url}'); ID=${ID##*/}
curl -sN --max-time 90 "https://neoarcana.net/readings/$ID/stream" >/dev/null
curl -s "https://neoarcana.net/api/v1/readings/$ID" | grep -o '"status":"[a-z]*"'
```

`"status":"complete"` means the whole chain works. `"error"` means every
provider failed — `journalctl -u neoarcana -n 50` names which and why.

Watch the first live reading stream in real time with
`journalctl -u neoarcana -f`.

## Updating

From your laptop:

```sh
git push          # to GitHub
```

Then on the server:

```sh
sudo /srv/neoarcana/deploy/deploy.sh
```

Pull-based, matching amozgrada on the same box. The script pulls, syncs
dependencies, **runs the test suite before touching the running service**,
restarts, health-checks on localhost, then smoke-tests the public site:
apex redirect, home page, static assets served by Caddy, security
headers, and a full end-to-end reading.

`--smoke` verifies the live site and changes nothing. `--no-test` skips
the suite, which defeats the point of the gate.

It warns (rather than acts) when `deploy/neoarcana.caddy` or
`deploy/neoarcana.service` differ from their installed copies, since
changing either is a deliberate root action.

## Rollback

To the previous commit, on the server:

```sh
sudo git --git-dir=/srv/git/neoarcana.git --work-tree=/srv/neoarcana checkout -f <sha>
sudo chown -R neoarcana:neoarcana /srv/neoarcana
sudo systemctl restart neoarcana
```

Then fix forward on your laptop and push; the next push overwrites the
rolled-back tree. To abandon the new app entirely, stop the service and
bring the old one back — the originals also live on GitHub
(`locran20/tarot` and `locran20/celtic-cross-journey`).

## Vendor changes

Model IDs and provider order are `.env` values. When a provider retires a
model or reprices (both happened in 2026), edit `.env` and
`systemctl restart neoarcana` — no redeploy.
