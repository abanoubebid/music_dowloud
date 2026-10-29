import hashlib, hmac, json, os, re, secrets, shutil, tempfile, threading, time, logging
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from pydantic import BaseModel, Field
from .platforms import registry
from .streamer import open_first, iter_stream, kill

log = logging.getLogger("vd")
MAX_PL = int(os.getenv("VD_MAX_PLAYLIST", "100"))
A_TTL = int(os.getenv("VD_ANALYSIS_TTL", "900"))
T_TTL = int(os.getenv("VD_TICKET_TTL", "600"))
INFO_DIR = Path(tempfile.gettempdir()) / "vd-info"
INFO_TTL = A_TTL + T_TTL + 60
DL_ID = re.compile(r"[A-Za-z0-9_-]{8,64}")
sem = threading.BoundedSemaphore(int(os.getenv("VD_WORKERS", "3")))
app = FastAPI(title="Video Downloader API")


class AccessGate:
    """Optional shared secret. Open the link once with ?key=SECRET; a cookie then keeps that browser in."""
    def __init__(self, app, key: str):
        self.app, self.key = app, key.encode()
        self.token = hashlib.sha256(self.key).hexdigest()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http": return await self.app(scope, receive, send)
        req = Request(scope)
        if hmac.compare_digest(req.cookies.get("vd_access", "").encode(), self.token.encode()):
            return await self.app(scope, receive, send)
        if hmac.compare_digest(req.query_params.get("key", "").encode(), self.key):
            res = RedirectResponse("/", status_code=303)
            res.set_cookie("vd_access", self.token, max_age=30 * 86400, httponly=True, samesite="lax",
                           secure=req.headers.get("x-forwarded-proto") == "https")
        else:
            res = PlainTextResponse("Access key required. Open the full link you were given.", status_code=401)
        await res(scope, receive, send)


if os.getenv("VD_ACCESS_KEY"): app.add_middleware(AccessGate, key=os.environ["VD_ACCESS_KEY"])
analyses: dict[str, dict] = {}
tickets: dict[str, dict] = {}
MIME = {"mp4": "video/mp4", "mkv": "video/x-matroska", "mp3": "audio/mpeg", "m4a": "audio/mp4", "webm": "audio/webm"}


class AnalyzeReq(BaseModel):
    platform: str
    url: str = Field(max_length=2048)
    scope: Literal["auto", "playlist"] = "auto"


class DownloadReq(BaseModel):
    analysis_id: str
    kind: Literal["video", "audio"]
    quality: str
    entries: list[int] | None = None


def err(code: int, msg: str, headers: dict | None = None):
    raise HTTPException(code, msg, headers=headers)


def signal(dl: str | None, ok: bool) -> dict:
    """Tells the page (via a short-lived cookie) that the browser got a response, so it can close its loading popup."""
    if not dl or not DL_ID.fullmatch(dl): return {}
    return {"Set-Cookie": f"vd_{dl}={'ok' if ok else 'err'}; Max-Age=120; Path=/; SameSite=Lax"}


def save_info(aid: str, info: dict | None) -> str | None:
    """Keeps yt-dlp's analysis on disk so the download can skip a second slow extraction."""
    if not info: return None
    try:
        INFO_DIR.mkdir(mode=0o700, exist_ok=True)
        p = INFO_DIR / f"{aid}.json"
        with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f: json.dump(info, f)
        return str(p)
    except (OSError, TypeError, ValueError): return None


def sweep_info() -> None:
    now = time.time()
    try:
        for f in INFO_DIR.glob("*.json"):
            if now - f.stat().st_mtime > INFO_TTL: f.unlink(missing_ok=True)
    except OSError: pass


def friendly(e: Exception) -> str:
    s = str(e).lower()
    if "private" in s or "sign in" in s: return "This content is private or requires sign-in."
    if "unavailable" in s or "removed" in s: return "This video is unavailable."
    if "429" in s or "rate" in s: return "YouTube is rate limiting requests. Try again later."
    if "timed out" in s or "timeout" in s: return "The network timed out. Try again."
    return "The request failed. Check the URL and try again."


def clean_name(t: str | None) -> str:
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", t or "")
    return re.sub(r"\s+", " ", t).strip(". ")[:150] or "download"


@app.get("/api/platforms")
def platforms(): return registry.enabled()


@app.post("/api/analyze")
def analyze(r: AnalyzeReq):
    try: a = registry.get(r.platform)
    except KeyError: err(400, "Unsupported platform.")
    try: url = a.validate(r.url)
    except ValueError as e: err(422, str(e))
    try: data = a.analyze(url, r.scope, MAX_PL)
    except ValueError as e: err(422, str(e))
    except Exception as e:
        log.warning("analyze failed: %s", type(e).__name__); err(502, friendly(e))
    info = data.pop("_info", None)  # server-side only, never sent to the browser
    aid = secrets.token_urlsafe(16)
    now = time.time()
    for k in [k for k, v in analyses.items() if now - v["ts"] > A_TTL]: del analyses[k]
    analyses[aid] = {"ts": now, "platform": r.platform, "url": url, "data": data, "info": save_info(aid, info)}
    sweep_info()
    return {"analysis_id": aid, "max_playlist_items": MAX_PL, **data}


@app.post("/api/download")
def download(r: DownloadReq):
    """Validates the selection and returns one stream ticket per file; the browser then downloads each ticket natively."""
    a = analyses.get(r.analysis_id)
    if not a or time.time() - a["ts"] > A_TTL: err(410, "Analysis expired. Analyze the URL again.")
    d = a["data"]
    if r.kind == "video":
        if not r.quality.isdigit() or int(r.quality) not in d["heights"]: err(422, "That video quality is not available.")
    elif r.quality not in {x["id"] for x in d["audio"]}: err(422, "That audio format is not available.")
    if (r.kind == "video" or not r.quality.startswith("native:")) and not shutil.which("ffmpeg"):
        err(503, "FFmpeg is required for this format but was not found on the server.")
    ad = registry.get(a["platform"])
    plan = ad.stream_plan(r.kind, r.quality, d["containers"])
    if d["kind"] == "playlist":
        ok = {e["index"]: e for e in d["entries"] if e["available"]}
        idx = sorted(set(r.entries)) if r.entries is not None else sorted(ok)
        if not idx or not set(idx) <= set(ok): err(422, "Select at least one available playlist item.")
        todo = [(ad.entry_url(ok[i]["id"]), ok[i]["title"]) for i in idx]
    else:
        todo = [(a["url"], d["title"])]
    now = time.time()
    for k in [k for k, v in tickets.items() if now - v["ts"] > T_TTL]: del tickets[k]
    info = a.get("info") if d["kind"] != "playlist" else None
    items = []
    for url, title in todo:
        tok, name = secrets.token_urlsafe(24), f"{clean_name(title)}.{plan['ext']}"
        tickets[tok] = {"ts": now, "url": url, "plan": plan, "name": name, "info": info}
        items.append({"token": tok, "filename": name})
    return {"items": items}


@app.get("/api/stream/{token}")
def stream(token: str, dl: str | None = None):
    bad = signal(dl, False)
    t = tickets.get(token)
    if not t or time.time() - t["ts"] > T_TTL: err(410, "This download link expired. Start the download again.", bad)
    if not sem.acquire(timeout=300): err(503, "The server is busy. Try again shortly.", bad)
    try:
        got = open_first(t["plan"], t["url"], t.get("info"))
    except Exception as e:
        sem.release(); log.warning("stream failed: %s", type(e).__name__); err(502, "Could not start the download.", bad)
    if not got:
        sem.release(); err(502, "This item could not be downloaded in the selected format.", bad)
    out, procs, first = got
    fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", t["name"])
    cd = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(t['name'])}"
    def gen():
        yield first
        yield from iter_stream(out, procs, sem.release)
    return StreamingResponse(gen(), media_type=MIME[t["plan"]["ext"]], headers={"Content-Disposition": cd, "Cache-Control": "no-store", **signal(dl, True)})


# One-port mode: if the frontend was built (npx vite build), the API also serves the web app, so a single tunnel is enough.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.is_dir(): app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
