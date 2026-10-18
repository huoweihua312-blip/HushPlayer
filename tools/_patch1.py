import re, pathlib
p = pathlib.Path("hushplayer/ui/main_window.py")
s = p.read_text(encoding="utf-8")
s = s.replace("""        self.queue_panel = QueuePanel()""", """        self.queue_panel = QueuePanel(self.content)""")
s = s.replace("""        self._toasts.setGeometry(0, 0, self.container.width(), self.container.height())
        self._toasts._relayout()""", """        self._toasts.setGeometry(0, 0, self.container.width(), self.container.height())""")
s = s.replace("""                {
                    "songs": str(stats.tracks) if getattr(stats, "tracks", 0) else "",
                    "albums": str(stats.albums) if getattr(stats, "albums", 0) else "",
                    "favorites": str(stats.favorites) if getattr(stats, "favorites", 0) else "",
                }""", """                {
                    "songs": str(stats.track_count) if stats.track_count else "",
                    "albums": str(stats.album_count) if stats.album_count else "",
                    "favorites": str(stats.favorite_count) if stats.favorite_count else "",
                }""")
p.write_text(s, encoding="utf-8")

p = pathlib.Path("hushplayer/ui/pages/home.py")
s = p.read_text(encoding="utf-8")
s = s.replace('total_tracks = getattr(stats, "tracks", 0) if stats is not None else 0', 'total_tracks = stats.track_count if stats is not None else 0')
s = s.replace('albums = getattr(stats, "albums", 0)\n        artists = getattr(stats, "artists", 0)', 'albums = stats.album_count\n        artists = stats.artist_count')
p.write_text(s, encoding="utf-8")
print("patched")
