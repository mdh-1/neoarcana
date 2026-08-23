#!/usr/bin/env bash
#
# Neoarcana deploy — pull, sync deps, test, restart, health-check, smoke-test.
#
# Run as root (it needs systemctl) from anywhere:
#     sudo /srv/neoarcana/deploy/deploy.sh
#
#     --smoke     only check the live site; change nothing
#     --no-test   skip the suite (not advised; it is the gate that keeps a
#                 broken commit from reaching the running service)
#
# Every application step runs as the unprivileged service account
# (sudo -u neoarcana -H); only the restart runs as root. The script re-execs
# from a temporary copy first, so a `git pull` that updates this very file
# cannot pull the rug out from under a run in progress.
#
# It is safe to re-run: pip install and the checkout are both idempotent.
#
# Unlike amozgrada there is no database and no migration step — readings live
# in SQLite at /var/lib/neoarcana/readings.db, which the app creates and
# never migrates. Losing it costs old permalinks and nothing else, so there
# is no pre-deploy dump.

set -euo pipefail

# --- run from a stable copy, since `git pull` may rewrite this file -------
if [[ "${_DEPLOY_REEXEC:-}" != 1 ]]; then
  _self="$(mktemp)"
  cp -- "$0" "$_self"
  _DEPLOY_REEXEC=1 exec bash "$_self" "$@"
fi
trap 'rm -f -- "$0"' EXIT   # after re-exec, $0 is the temp copy

# --- configuration (matches DEPLOY.md and the systemd unit) --------------
APP_USER=neoarcana
APP_DIR=/srv/neoarcana
ENV_FILE=/srv/neoarcana/.env
STATE_DIR=/var/lib/neoarcana         # readings.db (systemd StateDirectory)
SERVICE=neoarcana
HEALTH_URL=http://127.0.0.1:8001/health
SITE=https://www.neoarcana.net
APEX=https://neoarcana.net
CADDY_SITE=/etc/caddy/sites/neoarcana.caddy

DO_DEPLOY=1 DO_TEST=1
for arg in "$@"; do
  case "$arg" in
    --smoke)   DO_DEPLOY=0 ;;
    --no-test) DO_TEST=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *)         printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '  \033[33mwarn\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

as_app() { sudo -u "$APP_USER" -H "$@"; }
code()   { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

if [[ $DO_DEPLOY -eq 1 ]]; then
  # --- preconditions -----------------------------------------------------
  [[ $EUID -eq 0 ]]           || die "run as root (needs systemctl): sudo $APP_DIR/deploy/deploy.sh"
  id "$APP_USER" &>/dev/null  || die "service account '$APP_USER' does not exist"
  [[ -f "$ENV_FILE" ]]        || die "env file $ENV_FILE is missing"
  [[ -d "$APP_DIR/.git" ]]    || die "$APP_DIR is not a git checkout"
  [[ -x "$APP_DIR/.venv/bin/python" ]] || die "no virtualenv at $APP_DIR/.venv"

  install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR"

  # --- 1. pull -----------------------------------------------------------
  log "Fetching latest code"
  old_rev="$(as_app git -C "$APP_DIR" rev-parse HEAD)"
  as_app git -C "$APP_DIR" pull --ff-only \
    || die "git pull is not a fast-forward — reconcile on the box, then re-run"
  new_rev="$(as_app git -C "$APP_DIR" rev-parse HEAD)"
  if [[ "$old_rev" == "$new_rev" ]]; then
    log "Already at ${new_rev:0:9} — continuing (deps may still change)"
  else
    log "Code ${old_rev:0:9} -> ${new_rev:0:9}"
  fi

  # Changing the unit or the Caddy site is a deliberate root action.
  for pair in "$APP_DIR/deploy/$SERVICE.service:/etc/systemd/system/$SERVICE.service" \
              "$APP_DIR/deploy/neoarcana.caddy:$CADDY_SITE"; do
    repo="${pair%%:*}"; installed="${pair##*:}"
    if ! diff -q "$repo" "$installed" &>/dev/null; then
      warn "$(basename "$repo") differs from the installed copy. If intended:"
      warn "  cp $repo $installed"
      [[ "$installed" == *caddy* ]] \
        && warn "  caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy" \
        || warn "  systemctl daemon-reload && systemctl restart $SERVICE"
    fi
  done

  # --- 2. dependencies ---------------------------------------------------
  log "Installing dependencies"
  as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
  ok "pip install"

  # --- 3. test before touching the running service -----------------------
  if [[ $DO_TEST -eq 1 ]]; then
    log "Running the test suite"
    # Tests force keyless settings and a temporary database, so this never
    # touches .env, the live database, or a provider.
    if ! as_app bash -c "cd '$APP_DIR' && .venv/bin/python -m pytest tests/ -q" >/tmp/neoarcana-tests.log 2>&1; then
      tail -25 /tmp/neoarcana-tests.log
      die "tests failed — the running service was NOT restarted"
    fi
    ok "$(grep -oE '[0-9]+ passed' /tmp/neoarcana-tests.log | tail -1)"
  fi

  # --- 4. restart --------------------------------------------------------
  log "Restarting $SERVICE"
  systemctl restart "$SERVICE"
  systemctl is-active --quiet "$SERVICE" \
    || { journalctl -u "$SERVICE" -n 30 --no-pager; die "$SERVICE is not active after restart"; }

  for _ in $(seq 1 10); do
    [[ "$(code "$HEALTH_URL")" == 200 ]] && break
    sleep 1
  done
  [[ "$(code "$HEALTH_URL")" == 200 ]] \
    || { journalctl -u "$SERVICE" -n 30 --no-pager; die "no 200 from $HEALTH_URL"; }
  ok "healthy on 127.0.0.1:8001"
fi

# --- 5. smoke test the public site ---------------------------------------
log "Smoke test: $SITE"

[[ "$(code "$SITE/health")" == 200 ]] || die "health check did not return 200 through Caddy"
ok "health"

[[ "$(code "$APEX/")" == 301 ]] || warn "apex redirect is $(code "$APEX/"), expected 301"
ok "apex redirects"

home="$(curl -s --max-time 20 "$SITE/")"
grep -q "Seventy" <<<"$home"      || die "home page missing its heading"
grep -q "Celtic Cross" <<<"$home" || die "home page missing the spread list"
ok "home page renders"

hdrs="$(curl -sI --max-time 20 "$SITE/static/tarot-images/the_fool.jpg")"
grep -qi '^HTTP.* 200' <<<"$hdrs" || die "card image did not return 200"
grep -qi 'immutable'   <<<"$hdrs" || warn "card image not served by Caddy"
ok "static assets"

sec="$(curl -sI --max-time 20 "$SITE/")"
missing=0
for h in Strict-Transport-Security X-Content-Type-Options Content-Security-Policy; do
  grep -qi "^$h:" <<<"$sec" || { warn "missing header: $h"; missing=$((missing+1)); }
done
grep -qi '^server:' <<<"$sec" && { warn "Server header still advertised"; missing=$((missing+1)); }
[[ $missing -eq 0 ]] && ok "security headers" || warn "$missing header issue(s): install the Caddy site file (see above)"

dashes=$(grep -o '—' <<<"$home" | wc -l | tr -d ' ') || dashes=0
[[ "$dashes" -eq 0 ]] && ok "no em dashes in site copy" || warn "$dashes em dash(es) on the home page"

# --- 6. end-to-end reading -----------------------------------------------
log "End-to-end reading (draws cards, calls the model)"
loc="$(curl -s --max-time 20 -X POST "$SITE/readings" \
       -d 'spread_key=three_card&question=Is the deploy healthy?' \
       -o /dev/null -w '%{redirect_url}')"
if [[ -z "$loc" ]]; then
  status="$(code -X POST "$SITE/readings" -d 'spread_key=one_card&question=')"
  [[ "$status" == 429 ]] && { warn "rate limited (429) — expected on repeat runs"; log "Done."; exit 0; }
  die "could not create a reading (HTTP $status)"
fi
id="${loc##*/}"
curl -sN --max-time 150 "$SITE/readings/$id/stream" >/dev/null || die "stream failed"

json="$(curl -s --max-time 20 "$SITE/api/v1/readings/$id")"
READING_JSON="$json" "$APP_DIR/.venv/bin/python" <<'CHECK' || die "reading did not complete"
import json, os, sys

d = json.loads(os.environ['READING_JSON'])
text = d['interpretation']
if d['status'] != 'complete':
    print('  \033[31mfail\033[0m status=%s' % d['status']); sys.exit(1)
if len(text) < 300:
    print('  \033[31mfail\033[0m interpretation only %d chars' % len(text)); sys.exit(1)
print('  \033[32mok\033[0m   %d chars, shuffled by %s' % (len(text), d['entropy_source']))
if '—' in text:
    print('  \033[33mwarn\033[0m %d em dash(es) in the reading' % text.count('—'))
CHECK

log "Done."
