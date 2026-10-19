"""ReplayGain: 解析标签并映射为音量倍数。"""

from __future__ import annotations

import shutil

import pytest
from mutagen import File as MutagenFile

from hushplayer.audio import replaygain
from hushplayer.audio.engine import PlaybackEngine


@pytest.fixture()
def tagged(tmp_path, music_dir):
    source = next(music_dir.rglob("*.mp3"))
    target = tmp_path / "tagged.mp3"
    shutil.copy2(source, target)
    audio = MutagenFile(target, easy=True)
    audio["replaygain_track_gain"] = ["-6.00 dB"]
    audio["replaygain_album_gain"] = ["-3.00 dB"]
    audio.save()
    replaygain.clear_cache()
    return target


def test_track_and_album_gain_scale(tagged):
    assert replaygain.scale_for(str(tagged), "track") == pytest.approx(10 ** (-6 / 20), rel=1e-3)
    assert replaygain.scale_for(str(tagged), "album") == pytest.approx(10 ** (-3 / 20), rel=1e-3)
    assert replaygain.scale_for(str(tagged), "off") == 1.0


def test_missing_tags_and_files_fall_back_to_unity(tmp_path, music_dir):
    plain = next(music_dir.rglob("*.flac"))
    replaygain.clear_cache()
    assert replaygain.scale_for(str(plain), "track") == 1.0
    assert replaygain.scale_for(str(tmp_path / "nope.mp3"), "track") == 1.0


def test_engine_gain_changes_output_without_touching_volume(qapp):
    engine = PlaybackEngine()
    engine.set_volume(0.8)
    base = engine.output.volume()
    engine.set_gain(0.5)
    assert engine.volume == 0.8
    assert engine.output.volume() < base
    engine.set_gain(1.0)
    assert engine.output.volume() == pytest.approx(base, rel=1e-3)
