import sys, tempfile, pathlib
sys.path.insert(0, ".")
from hushplayer.services.playlist_import import parse_playlist
import plistlib

tmp = pathlib.Path(tempfile.mkdtemp())
m3u = tmp / "list.m3u8"
m3u.write_text("#EXTM3U\n#PLAYLIST:\u591c\u822a\n#EXTINF:225,\u5468\u6770\u4f26 - \u6674\u5929\n/fake/a.mp3\n", encoding="utf-8")
p = parse_playlist(m3u)
print("M3U name=", repr(p.name), "kind=", p.kind)
for e in p.entries:
    print("  entry", repr(e.title), repr(e.artist), e.duration_ms, repr(e.path))

data = {"Tracks": {"1": {"Track ID": 1, "Name": "\u5bb6\u4e66", "Artist": "\u52a0\u6728", "Album": "\u7fb2\u548c", "Total Time": 242000, "Location": "file://localhost/F:/Music/x.mp3"}},
        "Playlists": [{"Name": "\u97f3\u4e50\u5e93", "Playlist Items": [{"Track ID": 1}]}]}
xml = tmp / "Library.xml"
xml.write_bytes(plistlib.dumps(data))
q = parse_playlist(xml)
print("PLIST name=", repr(q.name), "kind=", q.kind, "note=", getattr(q, "note", None))
for e in q.entries:
    print("  entry", repr(e.title), repr(e.artist), e.duration_ms, repr(e.path))
