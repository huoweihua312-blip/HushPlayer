import pathlib
p = pathlib.Path("hushplayer/ui/main_window.py")
t = p.read_text(encoding="utf-8")
old = '''        title = getattr(page, "title", "") or route
'''
new = '''        title = getattr(page, "title", "") or ROUTE_TITLES.get(route, route)
'''
assert old in t
t = t.replace(old, new, 1)
anchor = "class MainWindow(FramelessWindow):"
assert anchor in t
t = t.replace(anchor, '''ROUTE_TITLES = {
    "home": "首页",
    "songs": "歌曲",
    "albums": "专辑",
    "album": "专辑",
    "artists": "歌手",
    "artist": "歌手",
    "favorites": "我喜欢",
    "recent": "最近播放",
    "playlist": "歌单",
    "search": "搜索",
    "settings": "设置",
    "lyrics": "歌词",
}


''' + anchor, 1)
p.write_text(t, encoding="utf-8")
print("ok")
