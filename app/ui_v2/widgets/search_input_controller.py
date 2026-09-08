"""Debounce typing while keeping explicit search actions immediate."""

from PySide6.QtCore import QObject, QSignalBlocker, QTimer, Signal
from PySide6.QtWidgets import QLineEdit


class SearchInputController(QObject):
    query_ready = Signal(str)

    def __init__(self, editor: QLineEdit, delay_ms: int = 180) -> None:
        super().__init__(editor)
        self.editor = editor
        self._edited_text: str | None = None
        self._last_text = editor.text()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.flush)
        editor.textEdited.connect(self._on_edited)
        editor.textChanged.connect(self._on_changed)
        editor.returnPressed.connect(self.flush)

    def _on_edited(self, text: str) -> None:
        self._edited_text = text

    def _on_changed(self, text: str) -> None:
        typed = text == self._edited_text
        self._edited_text = None
        if typed and text.strip():
            self._timer.start()
        else:
            self.flush()

    def flush(self) -> None:
        self._timer.stop()
        text = self.editor.text()
        if text != self._last_text:
            self._last_text = text
            self.query_ready.emit(text)

    def sync_text(self, text: str) -> None:
        """Restore a page's query without submitting a pending query elsewhere."""

        self._timer.stop()
        self._edited_text = None
        self._last_text = str(text or "")
        with QSignalBlocker(self.editor):
            self.editor.setText(self._last_text)
