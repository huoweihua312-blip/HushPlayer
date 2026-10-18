"""歌词服务：sidecar 发现、缓存、偏移、翻译与错误降级。"""

from __future__ import annotations

import time
from pathlib import Path

from hushplayer.lyrics.service import LyricsService, find_sidecar, find_translation_sidecar
from hushplayer.model.track import Track

LRC_TEXT = """[ti:夜航信号]
[00:01.00]第一行
[00:04.00]第二行
[00:08.50]第三行
"""


def make_track(path: Path) -> Track:
    return Track(
        id="local:lyrics-test",
        title="夜航信号",
        artist="Aurora Field",
        album="夜航信号",
        duration_ms=12000,
        path=str(path),
        kind="local",
    )


def wait_for(predicate, timeout: float = 6.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("等待歌词服务回调超时")


def make_service(library, qapp) -> LyricsService:
    return LyricsService(library.tracks, library.bindings, library.meta, client=None)


def test_sidecar_discovery(tmp_path) -> None:
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"")
    assert not find_sidecar(str(audio))
    lrc = tmp_path / "song.lrc"
    lrc.write_text(LRC_TEXT, encoding="utf-8")
    assert find_sidecar(str(audio)) == str(lrc)
    assert not find_translation_sidecar(str(audio))
    trans = tmp_path / "song.trans.lrc"
    trans.write_text("line1\nline2\nline3\n", encoding="utf-8")
    assert find_translation_sidecar(str(audio)) == str(trans)


def test_lyrics_subfolder(tmp_path) -> None:
    audio = tmp_path / "album" / "track.mp3"
    audio.parent.mkdir()
    audio.write_bytes(b"")
    folder = audio.parent / "Lyrics"
    folder.mkdir()
    lrc = folder / "track.lrc"
    lrc.write_text(LRC_TEXT, encoding="utf-8")
    assert find_sidecar(str(audio)) == str(lrc)


def test_sidecar_lyrics_resolved_with_translation(loaded_library, music_dir, qapp) -> None:
    track = loaded_library.search_local("夜航")[0]
    audio = Path(track.path)
    audio.with_suffix(".lrc").write_text(LRC_TEXT, encoding="utf-8")
    (audio.with_suffix(".trans.lrc")).write_text("line one\nline two\nline three\n", encoding="utf-8")

    service = make_service(loaded_library, qapp)
    results = []
    service.resolved.connect(results.append)
    service.request(track)
    wait_for(lambda: results)
    result = results[-1]
    assert result.track_id == track.id
    assert result.status == "ok"
    assert result.document is not None
    assert len(result.document.lines) == 3
    assert result.document.has_translation is True
    assert result.document.lines[0].translation == "line one"


def test_offset_applied_and_clamped(loaded_library, music_dir, qapp) -> None:
    track = loaded_library.search_local("夜航")[0]
    Path(track.path).with_suffix(".lrc").write_text(LRC_TEXT, encoding="utf-8")
    service = make_service(loaded_library, qapp)
    service.request(track)
    wait_for(lambda: service.cached(track.id) is not None)

    service.set_offset(track, 500)
    assert service.offset_for(track) == 500
    document = service.cached(track.id).document
    assert document.offset_ms == 500, "偏移记录在文档上，由 index_at/line_progress 统一扣除"
    assert document.index_at(1400) == -1, "正偏移表示歌词整体延后出现"
    assert document.index_at(1600) == 0

    service.set_offset(track, 120_000)
    assert service.offset_for(track) == 60_000, "偏移应被钳制在 ±60s"
    assert loaded_library.track(track.id).lyrics_offset_ms == 60_000


def test_second_request_uses_cache(loaded_library, music_dir, qapp) -> None:
    track = loaded_library.search_local("夜航")[0]
    path = Path(track.path).with_suffix(".lrc")
    path.write_text(LRC_TEXT, encoding="utf-8")
    service = make_service(loaded_library, qapp)
    service.request(track)
    wait_for(lambda: service.cached(track.id) is not None)
    path.unlink()

    results = []
    service.resolved.connect(results.append)
    service.request(track)
    wait_for(lambda: results)
    assert results[-1].document is not None
    assert len(results[-1].document.lines) == 3


def test_missing_lyrics_status(loaded_library, qapp, monkeypatch) -> None:
    track = loaded_library.search_local("Static Bloom")[0]
    service = make_service(loaded_library, qapp)

    def offline_request(track_arg, generation):  # noqa: ANN001
        service._on_lrclib_result(track_arg, None)

    monkeypatch.setattr(service, "_request_lrclib", offline_request, raising=False)
    results = []
    service.resolved.connect(results.append)
    service.request(track)
    wait_for(lambda: results)
    assert results[-1].status in {"none", "error"}


def test_manual_binding(loaded_library, music_dir, qapp, tmp_path) -> None:
    track = loaded_library.search_local("凌晨四点的海")[0]
    custom = tmp_path / "custom.lrc"
    custom.write_text("[00:00.50]绑定歌词\n", encoding="utf-8")
    service = make_service(loaded_library, qapp)
    service.bind_local(track, str(custom))
    results = []
    service.resolved.connect(results.append)
    service.request(track)
    wait_for(lambda: results)
    assert results[-1].provider.split(":")[0] in {"manual", "local"}
    assert results[-1].document.lines[0].text == "绑定歌词"
