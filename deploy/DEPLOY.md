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

The old Caddy site also served the React build as static files and
proxied only `/reading`. Replacing the site block with this one retires
both halves at once. The old JSON endpoint (`POST /reading`) disappears;
the new equivalent is `POST /readings` plus `GET /api/v1/readings/{id}`.

## First deploy

```sh
# 1. User and directory
sudo useradd --system --home /srv/neoarcana --shell /usr/sbin/nologin neoarcana
sudo mkdir -p /srv/neoarcana
sudo chown neoarcana:neoarcana /srv/neoarcana

# 2. Bare repo and deploy hook (same pattern as apt-maja on this box).
#    The hook lands in step 5, once the service exists to restart.
sudo mkdir -p /srv/git/neoarcana.git
sudo git init --bare /srv/git/neoarcana.git

#    From your laptop:
git remote add production ssh://root@neoarcana.net/srv/git/neoarcana.git
git push production main        # populates the bare repo; hook not yet live

#    On the server, do the first checkout by hand:
sudo git --git-dir=/srv/git/neoarcana.git --work-tree=/srv/neoarcana checkout -f main
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

# 5b. Deploy hook — from here on, `git push production main` deploys
sudo cp /srv/neoarcana/deploy/post-receive /srv/git/neoarcana.git/hooks/
sudo chmod +x /srv/git/neoarcana.git/hooks/post-receive

# 6. Caddy
sudo cp /srv/neoarcana/deploy/Caddyfile /etc/caddy/Caddyfile   # or import it
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
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

```sh
git push production main
```

The `post-receive` hook checks out the tree, updates dependencies,
restarts the service, and curls `/health`. A failed health check exits
non-zero, so the push itself reports the failure:

```
--> deploying a1b2c3d
--> healthy
```

Untracked files are left alone by the checkout, so `.env`, `.venv/` and
`archive/` survive every deploy. The reading database lives outside the
app directory entirely.

Restarting drops only in-flight generations; permalinks survive, since
readings are on disk. A reading interrupted mid-stream is regenerated on
the next visit to its page.

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
