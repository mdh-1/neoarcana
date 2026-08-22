#!/usr/bin/env bash
#
# Neoarcana deploy — test locally, push, then verify the live site.
#
# Runs from your laptop (not on the server, unlike amozgrada's deploy.sh):
#     ./deploy/deploy.sh                # test, push to both remotes, smoke test
#     ./deploy/deploy.sh --smoke        # only smoke-test what is already live
#     ./deploy/deploy.sh --no-reading   # skip the LLM-backed reading (saves quota)
#     ./deploy/deploy.sh --allow-dirty  # deploy with uncommitted changes present
#
# The server half is the post-receive hook in this directory: it checks out,
# installs dependencies, restarts the service and curls /health, failing the
# push if the app does not come back. This script covers what the hook cannot:
# the test suite before pushing, the GitHub backup, and end-to-end checks
# against the public URL once the deploy has landed.

set -euo pipefail
cd "$(dirname "$0")/.."

SITE=https://www.neoarcana.net
APEX=https://neoarcana.net
BRANCH=main
PY=.venv/bin/python

DO_DEPLOY=1 DO_READING=1 ALLOW_DIRTY=0
for arg in "$@"; do
  case "$arg" in
    --smoke)       DO_DEPLOY=0 ;;
    --no-reading)  DO_READING=0 ;;
    --allow-dirty) ALLOW_DIRTY=1 ;;
    -h|--help)     sed -n '2,16p' "$0"; exit 0 ;;
    *)             printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m   %s\n' "$*"; }
warn() { printf '  \033[33mwarn\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

code() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$@"; }

# --- deploy ---------------------------------------------------------------
if [[ $DO_DEPLOY -eq 1 ]]; then
  log "Pre-flight"
  branch="$(git rev-parse --abbrev-ref HEAD)"
  [[ "$branch" == "$BRANCH" ]] || die "on branch '$branch', expected '$BRANCH'"
  ok "on $BRANCH"

  if [[ -n "$(git status --porcelain)" ]]; then
    [[ $ALLOW_DIRTY -eq 1 ]] || die "uncommitted changes (commit them, or pass --allow-dirty)"
    warn "uncommitted changes present; they will NOT be deployed"
  else
    ok "working tree clean"
  fi

  [[ -x "$PY" ]] || die "no virtualenv — run ./run.sh once to build it"
  if ! "$PY" -m pytest tests/ -q >/tmp/neoarcana-tests.log 2>&1; then
    tail -25 /tmp/neoarcana-tests.log
    die "tests failed — nothing was pushed"
  fi
  ok "$(grep -oE '[0-9]+ passed' /tmp/neoarcana-tests.log | tail -1)"

  log "Pushing"
  git push -q origin "$BRANCH" && ok "github (backup)"
  # The hook prints its own progress; surface it rather than swallowing it.
  git push production "$BRANCH" 2>&1 | sed -n 's/^remote: /  /p'
  ok "deployed $(git rev-parse --short HEAD)"
fi

# --- smoke test -----------------------------------------------------------
log "Smoke test: $SITE"

[[ "$(code "$SITE/health")" == 200 ]] || die "health check did not return 200"
ok "health"

[[ "$(code "$APEX/")" =~ ^30 ]] || die "apex does not redirect to www"
ok "apex redirects"

home="$(curl -s --max-time 20 "$SITE/")"
grep -q "Seventy" <<<"$home"      || die "home page missing its heading"
grep -q "Celtic Cross" <<<"$home" || die "home page missing the spread list"
ok "home page renders"

# An immutable Cache-Control proves Caddy served this from disk, not the app.
hdrs="$(curl -sI --max-time 20 "$SITE/static/tarot-images/the_fool.jpg")"
grep -qi '^HTTP.* 200' <<<"$hdrs" || die "card image did not return 200"
grep -qi 'immutable'   <<<"$hdrs" || warn "card image not served by Caddy"
ok "static assets"

[[ "$(code "$SITE/faq")" == 200 ]] || die "FAQ did not return 200"
ok "faq"

dashes=$(grep -o '—' <<<"$home" | wc -l | tr -d ' ') || dashes=0
if [[ "$dashes" -eq 0 ]]; then
  ok "no em dashes in site copy"
else
  warn "$dashes em dash(es) back on the home page"
fi

# --- end-to-end reading ---------------------------------------------------
if [[ $DO_READING -eq 1 ]]; then
  log "End-to-end reading (draws cards, calls the model)"

  loc="$(curl -s --max-time 20 -X POST "$SITE/readings" \
         -d 'spread_key=three_card&question=Is the deploy healthy?' \
         -o /dev/null -w '%{redirect_url}')"
  if [[ -z "$loc" ]]; then
    status="$(code -X POST "$SITE/readings" -d 'spread_key=one_card&question=')"
    if [[ "$status" == 429 ]]; then
      warn "rate limited (429); the cap is per IP per hour, so this is expected on repeat runs"
      log "All checks passed (reading skipped)."
      exit 0
    fi
    die "could not create a reading (HTTP $status)"
  fi
  id="${loc##*/}"
  ok "drew $id"

  curl -sN --max-time 150 "$SITE/readings/$id/stream" >/dev/null || die "stream failed"
  ok "streamed"

  json="$(curl -s --max-time 20 "$SITE/api/v1/readings/$id")"
  READING_JSON="$json" "$PY" <<'CHECK' || die "reading did not complete"
import json, os, sys

d = json.loads(os.environ['READING_JSON'])
text = d['interpretation']

if d['status'] != 'complete':
    print('  \033[31mfail\033[0m status=%s' % d['status'])
    sys.exit(1)
if len(text) < 300:
    print('  \033[31mfail\033[0m interpretation only %d chars' % len(text))
    sys.exit(1)

print('  \033[32mok\033[0m   %d chars, shuffled by %s' % (len(text), d['entropy_source']))
if '—' in text:
    print('  \033[33mwarn\033[0m %d em dash(es) in the reading' % text.count('—'))
CHECK
fi

log "All checks passed."
