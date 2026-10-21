"""Shared context menus.

Keeping menu construction in one module guarantees the same wording, ordering
and behaviour everywhere a track list appears.
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable, Sequence

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import QInputDialog, QMenu, QMessageBox, QWidget

from ..core.icons import icon as make_icon
from ..core.logging_setup import get_logger
from ..core.theme import theme
from ..model.track import Track
from .context import ctx
from .widgets.menu import themed_menu

log = get_logger(__name__)


def _action(
    menu: QMenu,
    text: str,
    *,
    icon_name: str = "",
    enabled: bool = True,
    checkable: bool = False,
    checked: bool = False,
) -> QAction:
    action = QAction(text, menu)
    if icon_name:
        action.setIcon(make_icon(icon_name, theme().palette.text_secondary, 16))
    action.setEnabled(enabled)
    if checkable:
        action.setCheckable(True)
        action.setChecked(checked)
    menu.addAction(action)
    return action


def track_menu(
    parent: QWidget,
    tracks: Sequence[Track],
    *,
    playlist_id: int | None = None,
    on_play: Callable[[], None] | None = None,
    on_remove: Callable[[], None] | None = None,
    on_download: Callable[[list[Track]], None] | None = None,
    on_go_to_album: Callable[[Track], None] | None = None,
    on_go_to_artist: Callable[[Track], None] | None = None,
) -> QMenu:
    """Build (but do not show) a context menu for ``tracks``."""
    app = ctx()
    menu = themed_menu(parent)
    items = [track for track in tracks if track is not None]
    if not items:
        return menu
    single = len(items) == 1
    first = items[0]

    if on_play is not None:
        play = _action(menu, "播放" if single else f"播放所选的 {len(items)} 首", icon_name="play")
        play.triggered.connect(on_play)
    else:
        play = _action(menu, "播放" if single else f"播放所选的 {len(items)} 首", icon_name="play")
        play.triggered.connect(lambda: app.player.play_tracks(items, 0, context="手动选择"))
    menu.addSeparator()

    next_action = _action(menu, "下一首播放", icon_name="queue_add")
    next_action.triggered.connect(lambda: app.player.play_next_in_queue(items))
    queue_action = _action(menu, "添加到播放队列", icon_name="queue")
    queue_action.triggered.connect(lambda: app.player.enqueue(items))

    favorite_ids = {track.id for track in items if app.library.is_favorite(track.id)}
    all_favorite = len(favorite_ids) == len(items)
    favorite = _action(
        menu,
        "取消喜欢" if all_favorite else "添加到「我喜欢」",
        icon_name="heart_fill" if all_favorite else "heart",
    )
    favorite.triggered.connect(lambda: _toggle_favorite(items, not all_favorite))

    playlist_menu = menu.addMenu("添加到歌单")
    playlist_menu.setIcon(make_icon("plus", theme().palette.text_secondary, 16))
    _fill_playlists(playlist_menu, items, parent)

    if any(track.kind == "online" for track in items):
        download = _action(menu, "下载到本地", icon_name="download")
        if on_download is not None:
            download.triggered.connect(lambda: on_download(items))
        else:
            download.triggered.connect(lambda: _download(items, parent))

    menu.addSeparator()
    if playlist_id is not None:
        remove = _action(menu, "从该歌单中移除", icon_name="minus")
        remove.triggered.connect(
            lambda: _remove_from_playlist(playlist_id, items, parent, on_remove)
        )

    if single and on_go_to_album is not None and first.album:
        go_album = _action(menu, f"前往专辑「{first.album}」", icon_name="disc")
        go_album.triggered.connect(lambda: on_go_to_album(first))
    if single and on_go_to_artist is not None and first.artist:
        go_artist = _action(menu, f"前往歌手「{first.artist}」", icon_name="mic")
        go_artist.triggered.connect(lambda: on_go_to_artist(first))

    if single and first.is_local and first.path:
        reveal = _action(menu, "在资源管理器中显示", icon_name="folder")
        reveal.triggered.connect(lambda: reveal_in_explorer(first.path))

    copy = _action(menu, "复制歌曲信息", icon_name="list")
    copy.triggered.connect(lambda: _copy_info(items))
    if single:
        copy_title = _action(menu, "复制歌曲名", icon_name="music_note")
        copy_title.triggered.connect(
            lambda: QGuiApplication.clipboard().setText(first.title)
        )

    if on_remove is not None and playlist_id is None:
        menu.addSeparator()
        remove = _action(menu, "从音乐库中移除", icon_name="trash")
        remove.triggered.connect(on_remove)

    return menu


def _download(items: Sequence[Track], parent: QWidget) -> None:
    """菜单内默认的下载入口：交给 DownloadService，并通过 toast 汇报结果。"""
    app = ctx()
    service = getattr(app, "downloads", None)
    if service is None:
        return
    created = service.download([track for track in items if track.kind == "online"])
    window = app.window
    if window is not None and hasattr(window, "toast"):
        if created:
            window.toast(f"已开始下载 {len(created)} 首歌曲")
        else:
            window.toast("所选歌曲不支持下载")


def _toggle_favorite(tracks: Sequence[Track], favorite: bool) -> None:
    app = ctx()
    for track in tracks:
        app.library.set_favorite(track, favorite)


def _fill_playlists(menu: QMenu, tracks: Sequence[Track], parent: QWidget) -> None:
    app = ctx()
    playlists = [item for item in app.library.playlists_all() if not item.system]
    if playlists:
        for playlist in playlists:
            action = menu.addAction(playlist.name)
            action.triggered.connect(
                lambda _checked=False, pid=playlist.id: _add_to_playlist(pid, tracks)
            )
        menu.addSeparator()
    create = menu.addAction("新建歌单…")
    create.triggered.connect(lambda: _create_playlist(tracks, parent))


def _add_to_playlist(playlist_id: int, tracks: Sequence[Track]) -> None:
    app = ctx()
    app.library.add_to_playlist(playlist_id, list(tracks))


def _create_playlist(tracks: Sequence[Track], parent: QWidget) -> None:
    app = ctx()
    name, ok = QInputDialog.getText(parent, "新建歌单", "歌单名称：")
    name = (name or "").strip()
    if not ok or not name:
        return
    playlist_id = app.library.create_playlist(name)
    if playlist_id:
        app.library.add_to_playlist(playlist_id, list(tracks))


def _remove_from_playlist(
    playlist_id: int,
    tracks: Sequence[Track],
    parent: QWidget,
    callback: Callable[[], None] | None,
) -> None:
    app = ctx()
    if len(tracks) > 1:
        answer = QMessageBox.question(
            parent,
            "从歌单中移除",
            f"确定要从该歌单中移除 {len(tracks)} 首歌曲吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
    app.library.remove_from_playlist(playlist_id, [track.id for track in tracks])
    if callback is not None:
        callback()


def _copy_info(tracks: Sequence[Track]) -> None:
    lines = []
    for track in tracks:
        parts = [track.title, track.artist, track.album]
        lines.append(" - ".join(part for part in parts if part))
    QGuiApplication.clipboard().setText("\n".join(lines))


def reveal_in_explorer(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    except OSError:
        log.exception("无法打开资源管理器")


def playlist_menu(parent: QWidget, playlist_id: int, name: str, position: QPoint) -> None:
    """Context menu for a sidebar playlist entry."""
    app = ctx()
    menu = themed_menu(parent)
    play = menu.addAction("播放")
    play.triggered.connect(lambda: _play_playlist(playlist_id))
    menu.addSeparator()
    rename = menu.addAction("重命名…")
    rename.triggered.connect(lambda: _rename_playlist(parent, playlist_id, name))
    delete = menu.addAction("删除歌单")
    delete.triggered.connect(lambda: _delete_playlist(parent, playlist_id, name))
    menu.exec(position)


def _play_playlist(playlist_id: int) -> None:
    app = ctx()
    tracks = app.library.playlist_tracks(playlist_id)
    if tracks:
        app.player.play_tracks(tracks, 0, context=f"歌单")


def _rename_playlist(parent: QWidget, playlist_id: int, current: str) -> None:
    app = ctx()
    name, ok = QInputDialog.getText(parent, "重命名歌单", "新的名称：", text=current)
    name = (name or "").strip()
    if ok and name and name != current:
        app.library.rename_playlist(playlist_id, name)


def _delete_playlist(parent: QWidget, playlist_id: int, name: str) -> None:
    app = ctx()
    answer = QMessageBox.question(
        parent,
        "删除歌单",
        f"确定要删除歌单「{name}」吗？\n歌单中的歌曲仍会保留在音乐库中。",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if answer == QMessageBox.Yes:
        app.library.delete_playlist(playlist_id)


__all__ = ["reveal_in_explorer", "playlist_menu", "track_menu"]



