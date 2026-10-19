"""失效文件重定位：按相对路径与按文件名找回丢失的本地歌曲。"""

from __future__ import annotations

import shutil
from pathlib import Path

from hushplayer.model.track import Track


def _import(library, music_dir: Path) -> int:
    files = [str(p) for p in music_dir.rglob("*") if p.suffix.lower() in {".mp3", ".flac", ".wav", ".ogg"}]
    result = library.import_files(files)
    return result.added


def test_missing_tracks_detects_deleted_files(library, music_dir, tmp_path) -> None:
    _import(library, music_dir)
    assert library.missing_count() == 0

    victim = next(p for p in music_dir.rglob("*.mp3"))
    victim.unlink()
    missing = library.missing_tracks()
    assert len(missing) == 1
    assert missing[0].path == str(victim)


def test_relocate_folder_rewrites_relative_paths(library, music_dir, tmp_path) -> None:
    _import(library, music_dir)
    moved_root = tmp_path / "moved-music"
    shutil.copytree(music_dir, moved_root)
    shutil.rmtree(music_dir)

    assert library.missing_count() > 0
    moved, still = library.relocate_folder(str(music_dir), str(moved_root))
    assert moved >= 8
    assert still == 0
    assert library.missing_count() == 0
    sample = library.tracks.list(kind="local")[0]
    assert sample.path.startswith(str(moved_root))


def test_relocate_by_name_finds_moved_files(library, music_dir, tmp_path) -> None:
    _import(library, music_dir)
    scattered = tmp_path / "elsewhere"
    scattered.mkdir()
    for path in sorted(music_dir.rglob("*")):
        if path.is_file():
            shutil.copy2(path, scattered / path.name)
    shutil.rmtree(music_dir)

    moved, still = library.relocate_by_name(str(scattered))
    assert moved >= 8
    assert still == 0
    assert library.missing_count() == 0
