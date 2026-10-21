from __future__ import annotations

from types import SimpleNamespace

from hushplayer.model.track import Track
from hushplayer.services.playlist_import import (
    PlaylistEntry,
    import_playlist_file,
    match_tracks,
    parse_playlist_file,
)


def _track(track_id: str, title: str, artist: str, kind: str = "local", path: str = "") -> Track:
    return Track(id=track_id, title=title, artist=artist, kind=kind, path=path)


class _StubRepository:
    def __init__(self, tracks, by_path=None):
        self._tracks = tracks
        self._by_path = by_path or {}

    def track_by_path(self, path):
        return self._by_path.get(path)

    def search_local(self, term, limit=20):
        lowered = term.casefold()
        return [
            track
            for track in self._tracks
            if lowered and (lowered.split()[0] in track.title.casefold() or lowered in track.title.casefold() or track.title.casefold() in lowered)
        ][:limit]


class _StubLibrary:
    def __init__(self, tracks, by_path=None):
        self.tracks = _StubRepository(tracks, by_path)
        self.created: list[str] = []
        self.added: list[tuple[int, list[str]]] = []
        self.playlists = SimpleNamespace(add_tracks=self._add)

    def _add(self, playlist_id, ids):
        self.added.append((playlist_id, list(ids)))

    def create_playlist(self, name):
        self.created.append(name)
        return len(self.created)

    def playlists_all(self):
        return [SimpleNamespace(id=index + 1, name=name) for index, name in enumerate(self.created)]


def test_parse_m3u8_with_bom_and_extinf(tmp_path):
    file = tmp_path / "iTunes 歌单.m3u8"
    file.write_text(
        "\ufeff#EXTM3U\n#EXTINF:242,加木 - 家书\nF:\\Music\\家书.flac\n"
        "#EXTINF:180,弹壳Danko - Colt.45\nF:\\Music\\Colt.45.mp3\n",
        encoding="utf-8",
    )
    entries = parse_playlist_file(file)
    assert [entry.title for entry in entries] == ["家书", "Colt.45"]
    assert entries[0].artist == "加木"
    assert entries[0].duration_ms == 242000
    assert entries[0].path.endswith("家书.flac")


def test_parse_pls_and_csv_and_txt(tmp_path):
    pls = tmp_path / "list.pls"
    pls.write_text(
        "[playlist]\nFile1=F:\\Music\\a.mp3\nTitle1=弹壳Danko - Colt.45\nLength1=180\nFile2=F:\\Music\\b.flac\n",
        encoding="utf-8",
    )
    entries = parse_playlist_file(pls)
    assert entries[0].title == "Colt.45" and entries[0].artist == "弹壳Danko"
    assert entries[1].title == "b" and entries[1].path.endswith("b.flac")

    csv_file = tmp_path / "list.csv"
    csv_file.write_text("标题,歌手,专辑\n家书,加木,羲和\n", encoding="utf-8")
    entries = parse_playlist_file(csv_file)
    assert entries[0].title == "家书" and entries[0].album == "羲和"

    txt = tmp_path / "list.txt"
    txt.write_text("加木 - 家书\nColt.45\n", encoding="utf-8")
    entries = parse_playlist_file(txt)
    assert [entry.title for entry in entries] == ["家书", "Colt.45"]


def test_match_tracks_prefers_path_then_title_artist():
    by_path = {"F:/Music/家书.flac": _track("local:1", "家书", "加木", path="F:/Music/家书.flac")}
    library = _StubLibrary(
        [
            _track("local:1", "家书", "加木", path="F:/Music/家书.flac"),
            _track("local:2", "Colt.45", "弹壳Danko"),
            _track("local:9", "Colt.45", "别人翻唱"),
            _track("online:7", "家书", "加木", kind="online"),
        ],
        by_path,
    )
    entries = [
        PlaylistEntry(path="F:/Music/家书.flac"),
        PlaylistEntry(title="Colt.45", artist="弹壳Danko"),
        PlaylistEntry(title="不存在", artist="无人"),
    ]
    tracks, missing = match_tracks(entries, library)
    assert [track.id for track in tracks] == ["local:1", "local:2"]
    assert missing == ["不存在"]


def test_import_playlist_file_creates_playlist_and_adds(tmp_path):
    library = _StubLibrary([_track("local:1", "家书", "加木"), _track("local:2", "Colt.45", "弹壳Danko")])
    file = tmp_path / "周末.m3u"
    file.write_text("#EXTM3U\n#EXTINF:0,加木 - 家书\n\n#EXTINF:0,弹壳Danko - Colt.45\n\n", encoding="utf-8")
    summary = import_playlist_file(file, library)
    assert summary.playlist_name == "周末"
    assert summary.matched == 2 and summary.total == 2
    assert library.created == ["周末"]
    assert library.added[0][1] == ["local:1", "local:2"]
