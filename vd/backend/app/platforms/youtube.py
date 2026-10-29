import re
from urllib.parse import urlparse, parse_qs
import yt_dlp
from .base import Adapter

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
BASE = {"quiet": True, "no_warnings": True, "socket_timeout": 15, "retries": 3}


def classify(url: str) -> tuple[bool, bool]:
    u = urlparse(url)
    q = parse_qs(u.query)
    has_video = "v" in q or u.hostname == "youtu.be" or u.path.startswith(("/shorts/", "/live/"))
    return has_video, "list" in q


CODEC = {"mp4a": "AAC", "opus": "Opus", "vorbis": "Vorbis"}
NATIVE = ("m4a", "webm")  # audio containers we can stream as-is (no conversion)


def summarize_formats(info: dict) -> tuple[list[int], dict, dict]:
    """Reads yt-dlp's format list: available video heights, the container per height,
    and the best original audio stream per container (m4a / webm)."""
    fmts = info.get("formats") or []
    vids = [f for f in fmts if f.get("vcodec") not in (None, "none") and f.get("acodec") == "none" and f.get("height")]
    heights = sorted({f["height"] for f in vids})
    containers = {str(h): "mp4" if any(f["height"] == h and f.get("ext") == "mp4" for f in vids) else "mkv" for h in heights}
    audio: dict[str, dict] = {}
    for f in fmts:
        ext = f.get("ext")
        if f.get("vcodec") != "none" or f.get("acodec") in (None, "none") or ext not in NATIVE: continue
        abr = round(f.get("abr") or f.get("tbr") or 0)
        if ext not in audio or abr > audio[ext]["abr"]:
            audio[ext] = {"abr": abr, "codec": CODEC.get(str(f.get("acodec", "")).split(".")[0], "")}
    return heights, containers, audio


def audio_options(native: dict) -> list[dict]:
    """Original audio formats actually offered by the video, then MP3 conversions."""
    o = []
    for ext in NATIVE:
        if ext in native:
            n = native[ext]
            d = " · ".join(x for x in (n["codec"], f"{n['abr']} kbps" if n["abr"] else "", "original") if x)
            o.append({"id": f"native:{ext}", "label": ext.upper(), "detail": d})
    return o + [{"id": f"mp3:{k}", "label": "MP3", "detail": f"{k} kbps · converted"} for k in (128, 192, 320)]


class YouTube(Adapter):
    id, name = "youtube", "YouTube"

    def validate(self, url: str) -> str:
        url = (url or "").strip()
        u = urlparse(url)
        if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in HOSTS:
            raise ValueError("Enter a valid YouTube video or playlist URL.")
        if not any(classify(url)) and "/playlist" not in u.path:
            raise ValueError("This URL does not point to a video or playlist.")
        return url

    def analyze(self, url, scope, max_items):
        has_v, has_l = classify(url)
        playlist = has_l and (scope == "playlist" or not has_v)
        opts = {**BASE, "skip_download": True, "noplaylist": not playlist}
        if playlist:
            opts.update(extract_flat="in_playlist", playlistend=max_items)
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
            raw = None if playlist else y.sanitize_info(info, True)  # kept server-side so downloads start fast
        if not playlist:
            heights, containers, nat = summarize_formats(info)
            return {"kind": "single", "title": info.get("title"), "thumbnail": info.get("thumbnail"),
                    "duration": info.get("duration"), "uploader": info.get("uploader"),
                    "has_playlist": has_l, "heights": heights, "containers": containers,
                    "audio": audio_options(nat), "entries": [], "_info": raw}
        entries = [{"index": i + 1, "id": e.get("id"), "title": e.get("title") or "Unavailable video",
                    "duration": e.get("duration"),
                    "thumbnail": (e.get("thumbnails") or [{}])[-1].get("url"),
                    "available": bool(e.get("id")) and not str(e.get("title", "")).startswith(("[Private", "[Deleted"))}
                   for i, e in enumerate(info.get("entries") or []) if e]
        if not entries:
            raise ValueError("This playlist is empty.")
        first = next((e for e in entries if e["available"]), entries[0])
        with yt_dlp.YoutubeDL({**BASE, "skip_download": True}) as y:
            sample = y.extract_info(f"https://www.youtube.com/watch?v={first['id']}", download=False)
        heights, containers, nat = summarize_formats(sample)
        return {"kind": "playlist", "title": info.get("title"), "uploader": info.get("uploader"),
                "thumbnail": entries[0]["thumbnail"], "duration": None, "has_playlist": True,
                "heights": heights, "containers": containers, "entries": entries, "audio": audio_options(nat)}

    def entry_url(self, entry_id):
        if not re.fullmatch(r"[\w-]{6,20}", entry_id or ""):
            raise ValueError("Invalid video id.")
        return f"https://www.youtube.com/watch?v={entry_id}"

    def stream_plan(self, kind, quality, containers):
        if kind == "video":
            h = int(quality)
            mp4 = containers.get(str(h)) == "mp4"
            return {"mode": "merge", "ext": "mp4" if mp4 else "mkv", "a": "ba[ext=m4a]" if mp4 else "ba",
                    "v": f"bv[height={h}][ext=mp4]" if mp4 else f"bv[height={h}]"}
        if quality.startswith("native:"):
            ext = quality.split(":")[1]
            if ext not in NATIVE: raise ValueError("Unsupported audio format.")
            return {"mode": "direct", "ext": ext, "a": f"ba[ext={ext}]"}
        return {"mode": "mp3", "ext": "mp3", "a": "ba", "kbps": int(quality.split(":")[1])}
