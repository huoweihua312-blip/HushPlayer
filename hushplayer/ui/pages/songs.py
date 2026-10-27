"""Library song list page."""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QMenu, QPushButton

from ...services.library import LibraryQuery
from ...model.track import Track
from ..context import ctx
from ..widgets.common import IconButton, TextButton
from .trackpage import TrackListPage
from ..widgets.menu import themed_menu


class SongsPage(TrackListPage):
    route = "songs"
    title = "歌曲"
    default_sort = "title"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.header.set_subtitle("音乐库中的全部歌曲")

    def load_tracks(self) -> list[Track]:
        query = LibraryQuery(
            sort=self._sort_key,
            descending=not self._sort_asc,
        )
        return ctx().library.tracks_page(query)

    def context_label(self) -> str:
        return "歌曲"

    def empty_text(self) -> tuple[str, str]:
        return ("音乐库还是空的", "添加音乐文件夹后，HushPlayer 会自动扫描并读取歌曲信息")

    def build_actions(self, layout: QHBoxLayout) -> None:
        add = TextButton("添加音乐", icon_name="plus")
        add.clicked.connect(self._show_add_menu)
        layout.addWidget(add)
        refresh = IconButton("refresh", size=32, icon_size=16, tooltip="重新扫描音乐库")
        refresh.clicked.connect(self._rescan)
        layout.addWidget(refresh)

    def _show_add_menu(self) -> None:
        menu = themed_menu(self)
        menu.addAction("添加文件…", self._add_files)
        menu.addAction("添加文件夹…", self._add_folder)
        menu.addSeparator()
        menu.addAction("管理扫描目录…", self._open_settings)
        menu.addAction("重新扫描全部目录", self._rescan)
        button = self.sender()
        if button is not None:
            menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        else:
            menu.exec(self.mapToGlobal(self.rect().center()))

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "添加音乐文件",
            "",
            "音频文件 (*.mp3 *.flac *.wav *.m4a *.aac *.ogg *.opus *.wma *.ape *.aiff);;所有文件 (*.*)",
        )
        if not paths:
            return
        window = ctx().window
        try:
            result = ctx().library.import_files(paths)
        except Exception as exc:  # noqa: BLE001
            if window is not None:
                window.toast(f"导入失败：{exc}", "error")
            return
        if window is not None:
            window.toast(f"已导入 {result.added} 首歌曲", "success")
        self.reload()

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "添加音乐文件夹")
        if not folder:
            return
        settings = ctx().settings
        folders = list(settings.get("library.folders", []) or [])
        if folder not in folders:
            folders.append(folder)
            settings.set("library.folders", folders)
        window = ctx().window
        if window is not None:
            window.toast("正在扫描音乐文件夹…", "info")
        ctx().library.scan(folders)

    def _rescan(self) -> None:
        folders = list(ctx().settings.get("library.folders", []) or [])
        if not folders:
            self._add_folder()
            return
        ctx().library.scan(folders, force=True)
        window = ctx().window
        if window is not None:
            window.toast("正在重新扫描音乐库…", "info")

    def _open_settings(self) -> None:
        window = ctx().window
        if window is not None:
            window.navigate("settings", "library")
