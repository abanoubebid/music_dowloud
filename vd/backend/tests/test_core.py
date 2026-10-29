import pytest
from app.platforms import registry
from app.platforms.youtube import YouTube, classify, summarize_formats, audio_options


def test_registry():
    assert [p["id"] for p in registry.enabled()] == ["youtube"]
    with pytest.raises(KeyError): registry.get("nope")


def test_validate():
    y = YouTube()
    assert y.validate("https://youtu.be/abc")
    for bad in ["http://evil.com/watch?v=1", "ftp://youtube.com/watch?v=1", "https://youtube.com/"]:
        with pytest.raises(ValueError): y.validate(bad)


def test_classify():
    assert classify("https://www.youtube.com/watch?v=a&list=b") == (True, True)
    assert classify("https://www.youtube.com/playlist?list=b") == (False, True)


def y_audio_ids(n): return [o["id"] for o in audio_options(n)]


def test_formats_and_plans():
    info = {"formats": [{"vcodec": "avc1", "acodec": "none", "height": 720, "ext": "mp4"},
                        {"vcodec": "vp9", "acodec": "none", "height": 2160, "ext": "webm"},
                        {"vcodec": "none", "acodec": "mp4a.40.2", "ext": "m4a", "abr": 129.5},
                        {"vcodec": "none", "acodec": "opus", "ext": "webm", "abr": 50},
                        {"vcodec": "none", "acodec": "opus", "ext": "webm", "abr": 130}]}
    h, c, nat = summarize_formats(info)
    assert h == [720, 2160] and c == {"720": "mp4", "2160": "mkv"}
    assert nat == {"m4a": {"abr": 130, "codec": "AAC"}, "webm": {"abr": 130, "codec": "Opus"}}
    assert y_audio_ids(nat) == ["native:m4a", "native:webm", "mp3:128", "mp3:192", "mp3:320"]
    y = YouTube()
    assert y.stream_plan("video", "720", c)["ext"] == "mp4" and y.stream_plan("video", "2160", c)["ext"] == "mkv"
    assert y.stream_plan("audio", "mp3:192", c)["kbps"] == 192
    assert y_audio_ids({}) == ["mp3:128", "mp3:192", "mp3:320"]
    p = y.stream_plan("audio", "native:webm", c)
    assert p["ext"] == "webm" and p["mode"] == "direct" and p["a"] == "ba[ext=webm]"
    with pytest.raises(ValueError): y.stream_plan("audio", "native:exe", c)
    with pytest.raises(ValueError): y.entry_url("../x")
