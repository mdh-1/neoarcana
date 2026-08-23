import hashlib
import json
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from .config import get_settings
from .domain.deck import load_deck
from .domain.spreads import SPREADS, resolve_spread
from .services import reading as reading_service

BASE_DIR = Path(__file__).resolve().parent

def _asset_version(*names: str) -> str:
    """Short content hash of the CSS and JS, appended to their URLs.

    Caddy serves /static/* with `immutable, max-age=2592000`, which is right
    for the card images (their filenames never change) but would pin a
    returning visitor to a month-old stylesheet, since style.css keeps its
    name across deploys. Changing the query string changes the URL, so a
    deploy invalidates the cache the moment content changes and never
    otherwise.
    """
    h = hashlib.sha256()
    for name in names:
        h.update((BASE_DIR / "static" / name).read_bytes())
    return h.hexdigest()[:8]


app = FastAPI(title="Neoarcana", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _interpretation_html(text: str) -> Markup:
    """Render a stored interpretation as paragraphs with bold leads.

    The streaming path does this in reading.js as chunks arrive; without the
    same treatment here, a completed reading rendered from storage showed
    literal ** on every reload and every shared permalink, with the drop cap
    landing on an asterisk.

    Escaped before any markup is added: the text is model output, and the
    prompt permits only **bold**, so nothing else should survive.
    """
    out = []
    for para in re.split(r"\n\n+", text.strip()):
        if not para.strip():
            continue
        safe = str(escape(para.strip()))
        safe = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe, flags=re.S)
        out.append(f"<p>{safe}</p>")
    return Markup("".join(out))


templates.env.filters["interpretation"] = _interpretation_html
templates.env.globals["asset_v"] = _asset_version("style.css", "reading.js")
templates.env.globals["site_url"] = get_settings().site_url.rstrip("/")

load_deck()  # validate card data at startup, not first request


# --- tiny per-IP rate limit on reading creation (LLM calls cost money) ---
_hits: dict[str, deque[float]] = defaultdict(deque)


def _rate_limited(ip: str, per_hour: int) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= per_hour:
        return True
    q.append(now)
    return False


def _page(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    # Site copy about the shuffle must match the configuration, not the
    # aspiration: without a random.org key every draw is local CSPRNG.
    ctx.setdefault("random_org", bool(get_settings().random_api_key))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def _language_hint(request: Request) -> str:
    """First tag of Accept-Language, e.g. "es" from "es-ES,es;q=0.9,en;q=0.8".

    English and wildcard yield no hint — English is already the default,
    and the hint only serves as a tiebreaker for general readings and
    short questions whose language the model can't detect."""
    first = request.headers.get("accept-language", "")
    first = first.split(",")[0].split(";")[0].strip().lower()
    if not first or first == "*" or first.startswith("en"):
        return ""
    return first


# ------------------------------- pages -------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return _page(request, "index.html", spreads=list(SPREADS.values()))


@app.get("/ask/{spread_key}", response_class=HTMLResponse)
async def ask(request: Request, spread_key: str):
    spread = resolve_spread(spread_key)
    if spread is None:
        raise HTTPException(404)
    return _page(request, "ask.html", spread=spread)


@app.post("/readings")
async def create_reading(request: Request, spread_key: str = Form(...), question: str = Form("")):
    spread = resolve_spread(spread_key)
    if spread is None:
        raise HTTPException(400, "Unknown spread")
    settings = get_settings()
    ip = request.client.host if request.client else "?"
    if _rate_limited(ip, settings.readings_per_hour):
        return _page(request, "error.html", status_code=429,
                     message="The deck needs a rest — please try again in a while.")
    r = await reading_service.create_reading(
        settings, spread, question, language_hint=_language_hint(request)
    )
    return RedirectResponse(f"/readings/{r.id}", status_code=303)


@app.get("/readings/{reading_id}", response_class=HTMLResponse)
async def show_reading(request: Request, reading_id: str):
    r = reading_service.store.get(reading_id)
    if r is None:
        return _page(request, "error.html", status_code=404,
                     message="This reading has drifted beyond recall. Draw a fresh one.")
    return _page(request, "reading.html", reading=r)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Served from the root as well as /static: it is the path crawlers
    request by default, and Google uses it for the search-result icon."""
    return FileResponse(BASE_DIR / "static" / "favicon.ico")


@app.get("/robots.txt", include_in_schema=False, response_class=PlainTextResponse)
async def robots():
    """Individual readings carry the querent's question, so they are kept
    out of the index. The public pages are the ones worth crawling."""
    return (
        "User-agent: *\n"
        "Disallow: /readings/\n"
        "Disallow: /api/\n"
        "Allow: /\n"
        f"\nSitemap: {get_settings().site_url.rstrip('/')}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    base = get_settings().site_url.rstrip("/")
    paths = ["/", "/faq"] + [f"/ask/{k}" for k in SPREADS]
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p in paths)
    return Response(
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
        media_type="application/xml",
    )


@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    return _page(request, "faq.html")


# ---------------------------- streaming ------------------------------


@app.get("/readings/{reading_id}/stream")
async def stream_reading(reading_id: str):
    r = reading_service.store.get(reading_id)
    if r is None:
        raise HTTPException(404)

    async def event_source():
        settings = get_settings()
        async for chunk in reading_service.interpret(settings, r):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------- minimal JSON API --------------------------
# The tidy exit hatch: a future SPA or mobile app talks to these.


@app.get("/api/v1/readings/{reading_id}")
async def api_reading(reading_id: str):
    r = reading_service.store.get(reading_id)
    if r is None:
        raise HTTPException(404)
    return {
        "id": r.id,
        "spread": r.spread.key,
        "question": r.question,
        "entropy_source": r.entropy_source,
        "status": r.status,
        "interpretation": r.interpretation,
        "cards": [
            {
                "position": c.position,
                "position_name": c.position_name,
                "name": c.display_name,
                "reversed": c.is_reversed,
                "picture": c.picture,
                "meaning": c.meaning,
                "crowley_meaning": c.crowley_meaning,
            }
            for c in r.cards
        ],
    }


@app.get("/health")
async def health():
    return {"ok": True}
