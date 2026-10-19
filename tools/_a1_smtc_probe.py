import asyncio, datetime
from winrt.windows.media.playback import MediaPlayer
from winrt.windows.media import (
    MediaPlaybackType, SystemMediaTransportControlsButton,
    SystemMediaTransportControlsTimelineProperties,
)

mp = MediaPlayer()
smtc = mp.system_media_transport_controls
print("smtc", smtc)
smtc.is_enabled = True
smtc.is_play_enabled = True
smtc.is_pause_enabled = True
smtc.is_next_enabled = True
smtc.is_previous_enabled = True

updater = smtc.display_updater
updater.type = MediaPlaybackType.MUSIC
props = updater.music_properties
props.title = "测试歌曲"
props.artist = "测试歌手"
props.album_title = "测试专辑"
updater.update()
print("metadata updated")

tl = SystemMediaTransportControlsTimelineProperties()
tl.start_time = datetime.timedelta(0)
tl.end_time = datetime.timedelta(seconds=180)
tl.position = datetime.timedelta(seconds=42)
tl.min_seek_time = datetime.timedelta(0)
tl.max_seek_time = datetime.timedelta(seconds=180)
smtc.update_timeline_properties(tl)
print("timeline updated")

def on_button(sender, args):
    print("button", args.button)

smtc.add_button_pressed(on_button)
print("button handler registered")
print("status enum", [name for name in dir(__import__("winrt.windows.media", fromlist=["MediaPlaybackStatus"]).MediaPlaybackStatus) if name.isupper()][:8])
try:
    from winrt.windows.storage.streams import RandomAccessStreamReference
    print("rasr methods", [m for m in dir(RandomAccessStreamReference) if m.startswith("create")])
except Exception as exc:
    print("streams err", exc)
