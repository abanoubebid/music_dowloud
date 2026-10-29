"""Streams media straight to the HTTP response: yt-dlp -> (ffmpeg) -> client. No temp files, no re-encoding
except MP3. Merged video uses a fragmented MP4 / Matroska stream copy."""
import os, subprocess, sys

PIPE, NULL = subprocess.PIPE, subprocess.DEVNULL
YTDLP = [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings", "--no-playlist", "--socket-timeout", "15", "--retries", "3"]


def _ytdlp(sel: str, url: str, info: str | None = None) -> subprocess.Popen:
    # With a saved analysis (--load-info-json) yt-dlp skips re-fetching the page and re-solving YouTube's
    # JS challenge, which is most of the wait before a download starts. Falls back to the URL if the file is gone.
    src = ["--load-info-json", info] if info and os.path.isfile(info) else [url]
    return subprocess.Popen([*YTDLP, "-f", sel, "-o", "-", *src], stdout=PIPE, stderr=NULL)


def _ffmpeg(inputs: list[subprocess.Popen], out_args: list[str]) -> subprocess.Popen:
    fds = tuple(p.stdout.fileno() for p in inputs)
    args = ["ffmpeg", "-v", "error", "-nostdin"]
    for fd in fds:
        args += ["-i", f"pipe:{fd}"]
    ff = subprocess.Popen(args + out_args + ["pipe:1"], stdout=PIPE, stderr=NULL, pass_fds=fds)
    for p in inputs:
        p.stdout.close()  # ffmpeg owns the read end now
    return ff


def open_stream(plan: dict, url: str, info: str | None = None):
    procs: list[subprocess.Popen] = []
    try:
        if plan["mode"] == "direct":
            p = _ytdlp(plan["a"], url, info); procs = [p]; return p.stdout, procs
        if plan["mode"] == "mp3":
            src = _ytdlp(plan["a"], url, info); procs = [src]
            ff = _ffmpeg([src], ["-vn", "-c:a", "libmp3lame", "-b:a", f"{plan['kbps']}k", "-f", "mp3"])
            return ff.stdout, [ff, src]
        v, a = _ytdlp(plan["v"], url, info), _ytdlp(plan["a"], url, info); procs = [v, a]
        fmt = ["-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof"] if plan["ext"] == "mp4" else ["-f", "matroska"]
        ff = _ffmpeg([v, a], ["-map", "0:v:0", "-map", "1:a:0", "-c", "copy", *fmt])
        return ff.stdout, [ff, v, a]
    except Exception:
        kill(procs); raise


def kill(procs) -> None:
    for p in procs:
        if p.poll() is None: p.kill()
    for p in procs:
        try: p.wait(timeout=5)
        except Exception: pass


def open_first(plan: dict, url: str, info: str | None = None):
    """Start the stream and wait for its first bytes. Tries the saved analysis first, then the plain URL.
    Returns (out, procs, first_chunk) or None if nothing could be produced."""
    for src in ([info, None] if info else [None]):
        procs: list = []
        try:
            out, procs = open_stream(plan, url, src)
            first = out.read1(65536)
            if first: return out, procs, first
        except Exception:
            pass
        kill(procs)
    return None


def iter_stream(out, procs, release):
    try:
        while chunk := out.read1(65536):
            yield chunk
    finally:
        kill(procs); release()
