import pathlib
p = pathlib.Path("tools/shot_app.py")
t = p.read_text(encoding="utf-8")

helper = '''
LYRICS_ZH = """[00:00.60]<00:00.60>夜<00:01.00>航<00:01.35>信<00:01.70>号
[00:02.40]<00:02.40>穿<00:02.80>过<00:03.10>无<00:03.45>人<00:03.80>的<00:04.10>跑<00:04.45>道
[00:05.00]<00:05.00>城<00:05.40>市<00:05.75>在<00:06.10>身<00:06.40>后<00:06.70>退<00:07.00>潮
[00:07.60]<00:07.60>我<00:08.00>把<00:08.35>频<00:08.70>率<00:09.05>调<00:09.40>到<00:09.70>最<00:10.00>高
[00:10.80]<00:10.80>听<00:11.10>见<00:11.45>海<00:11.80>的<00:12.10>心<00:12.45>跳
"""

LYRICS_EN = """[00:00.60]Night flight signal
[00:02.40]Running through the empty lanes
[00:05.00]The city ebbing far behind
[00:07.60]I tune the frequency up high
[00:10.80]And hear the ocean's heart
"""


def write_lyrics(media: Path) -> None:
    target = media / "夜航信号" / "01 - 夜航信号.lrc"
    if target.exists():
        return
    target.write_text(LYRICS_ZH, encoding="utf-8")
    target.with_name("01 - 夜航信号.trans.lrc").write_text(LYRICS_EN, encoding="utf-8")
    plain = media / "Long Way Home" / "01 - Long Way Home.lrc"
    plain.write_text(
        "[00:00.80]Long way home\\n[00:03.20]Paper lanterns in the rain\\n[00:06.20]Every mile a quiet song\\n",
        encoding="utf-8",
    )


'''
anchor = "def prepare_library() -> None:"
assert anchor in t
t = t.replace(anchor, helper + anchor, 1)
old = '''    if not any(media.iterdir()):
        shutil.copytree(FIXTURES, media, dirs_exist_ok=True)
'''
new = '''    if not any(media.iterdir()):
        shutil.copytree(FIXTURES, media, dirs_exist_ok=True)
    write_lyrics(media)
'''
assert old in t
t = t.replace(old, new, 1)

old_shoot = '''        elif scene == "immersive":
            window.open_immersive()
            app.processEvents()'''
new_shoot = '''        elif scene == "lyrics":
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None and ctx().player.current is not track:
                ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                app.processEvents()
                ctx().player.seek(4200)
                ctx().player.pause()
                app.processEvents()
            window.navigate("lyrics")
            app.processEvents()
        elif scene == "immersive":
            track = next((item for item in ctx().library.tracks_page() if "夜航" in item.title), None)
            if track is not None and ctx().player.current is not track:
                ctx().player.play_tracks([track], 0, context="专辑 · 夜航信号")
                app.processEvents()
                ctx().player.seek(4200)
                ctx().player.pause()
                app.processEvents()
            window.open_immersive()
            app.processEvents()'''
assert old_shoot in t
t = t.replace(old_shoot, new_shoot, 1)
p.write_text(t, encoding="utf-8")
print("ok")
