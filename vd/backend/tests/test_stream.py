import shutil, subprocess, pytest
from app import streamer
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg missing")


def _run(*a): subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)


def _collect(out, procs): return b"".join(streamer.iter_stream(out, procs, lambda: None))


def test_merge_and_mp3(tmp_path, monkeypatch):
    v, a = tmp_path / "v.mp4", tmp_path / "a.m4a"
    _run("-f", "lavfi", "-i", "testsrc=d=2:s=160x120:r=15", "-c:v", "libx264", "-movflags", "frag_keyframe+empty_moov", str(v))
    _run("-f", "lavfi", "-i", "sine=d=2", "-c:a", "aac", str(a))
    files = {"V": v, "A": a}
    monkeypatch.setattr(streamer, "_ytdlp", lambda sel, url, info=None: subprocess.Popen(["cat", str(files[sel])], stdout=subprocess.PIPE))
    out, procs = streamer.open_stream({"mode": "merge", "ext": "mp4", "v": "V", "a": "A"}, "u")
    o = tmp_path / "o.mp4"; o.write_bytes(_collect(out, procs))
    kinds = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(o)], capture_output=True, text=True).stdout.split()
    assert sorted(kinds) == ["audio", "video"]
    out, procs = streamer.open_stream({"mode": "mp3", "ext": "mp3", "a": "A", "kbps": 128}, "u")
    d = _collect(out, procs)
    assert d[:3] == b"ID3" or d[0] == 0xFF


def test_info_json_is_used_when_present(tmp_path, monkeypatch):
    seen = []
    class P:  # records the yt-dlp command line instead of running it
        def __init__(self, args, **kw): seen.append(args); self.stdout = None
    monkeypatch.setattr(streamer.subprocess, "Popen", P)
    info = tmp_path / "i.json"; info.write_text("{}")
    streamer._ytdlp("ba", "https://x/y", str(info))
    streamer._ytdlp("ba", "https://x/y", str(tmp_path / "missing.json"))
    assert "--load-info-json" in seen[0] and "https://x/y" not in seen[0]
    assert "--load-info-json" not in seen[1] and seen[1][-1] == "https://x/y"


def test_open_first_falls_back_to_url(monkeypatch):
    # the attempt with a saved analysis yields no bytes -> the plain-URL attempt is used
    monkeypatch.setattr(streamer, "_ytdlp", lambda sel, url, info=None: subprocess.Popen(["true"] if info else ["echo", "data"], stdout=subprocess.PIPE))
    plan = {"mode": "direct", "ext": "m4a", "a": "A"}
    out, procs, first = streamer.open_first(plan, "u", "/some/info.json")
    assert first.startswith(b"data")
    streamer.kill(procs)
    assert streamer.open_first(plan, "u", None) is not None
