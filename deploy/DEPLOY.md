# Deploying Neoarcana

Single FastAPI process behind Caddy. No build step, no container, no database.

Assumes `/srv/neoarcana` as the app root and a `neoarcana` service user —
adjust both consistently in `neoarcana.service` and `Caddyfile` if you
prefer somewhere else.

## Two constraints that are not negotiable

**One worker.** Readings and the per-IP rate limiter live in process
memory. A second worker will not see readings the first one created, so
users get "this reading has drifted beyond recall" immediately after
drawing. `--workers 1` until `ReadingStore` moves to SQLite.

**Proxy headers on.** Behind Caddy every request arrives from 127.0.0.1.
Without `--proxy-headers`, the rate limiter treats the whole internet as
one visitor and the 11th reading of the hour is refused for everyone.

Both are already set in `neoarcana.service`.

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

# 2. Code (from your laptop). archive/ is 203MB of source scans and
#    .venv is platform-specific — neither belongs on the server.
rsync -av --delete \
  --exclude '.git' --exclude '.venv' --exclude 'archive' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.env' \
  ./ user@neoarcana.net:/tmp/neoarcana/
sudo rsync -a --delete /tmp/neoarcana/ /srv/neoarcana/
sudo chown -R neoarcana:neoarcana /srv/neoarcana

# 3. Virtualenv on the server
sudo -u neoarcana python3 -m venv /srv/neoarcana/.venv
sudo -u neoarcana /srv/neoarcana/.venv/bin/pip install -r /srv/neoarcana/requirements.txt

# 4. Secrets — never rsynced, never committed
sudo -u neoarcana tee /srv/neoarcana/.env >/dev/null <<'ENV'
GEMINI_API_KEY=...
RANDOM_API_KEY=
LLM_PROVIDERS=gemini,mistral,deepseek
READINGS_PER_HOUR=10
ENV
sudo chmod 600 /srv/neoarcana/.env

# 5. Service
sudo cp /srv/neoarcana/deploy/neoarcana.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now neoarcana
systemctl status neoarcana

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
rsync -av --delete --exclude '.git' --exclude '.venv' --exclude 'archive' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude '.env' \
  ./ user@neoarcana.net:/tmp/neoarcana/
sudo rsync -a --delete /tmp/neoarcana/ /srv/neoarcana/
sudo chown -R neoarcana:neoarcana /srv/neoarcana
sudo -u neoarcana /srv/neoarcana/.venv/bin/pip install -r /srv/neoarcana/requirements.txt
sudo systemctl restart neoarcana
```

Restarting drops in-flight readings and the reading store — permalinks
from before the restart 404. Fine for a hobby deploy; the fix when it
starts to matter is SQLite behind `ReadingStore`.

## Rollback

`sudo systemctl stop neoarcana`, then bring the old service back up. The
legacy code is in git history (`git log --all -- tarot-main/`), so keep a
copy of the old tree on the server until you're happy with the new one.

## Vendor changes

Model IDs and provider order are `.env` values. When a provider retires a
model or reprices (both happened in 2026), edit `.env` and
`systemctl restart neoarcana` — no redeploy.
