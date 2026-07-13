from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from app.services.source_registry import SourceRegistryError, SourceRegistryManager
from app.ui.online_source_pages import SourceManagerPage


class FakeClient(QObject):
    sourceListReceived = Signal(list)
    sourceTestFinished = Signal(int, str, dict)
    requestFailed = Signal(int, str, str)
    processError = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.reloaded: list[str] = []

    def reload_sources(self, source_id: str = "") -> int:
        self.reloaded.append(source_id)
        return 1


def write_registry(manager: SourceRegistryManager, sources: list[dict]) -> None:
    manager.runtime_dir.mkdir(parents=True, exist_ok=True)
    manager.registry_path.write_text(
        json.dumps({"version": 1, "sources": sources}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def source_entry(source_id: str, filename: str) -> dict:
    return {
        "id": source_id,
        "name": source_id,
        "filename": filename,
        "enabled": True,
        "capabilities": {"search": True},
    }


def test_registry_removal(root: Path) -> None:
    manager = SourceRegistryManager(root)
    builtin = manager.sources_dir / "builtin.js"
    active = manager.active_dir / "imported.js"
    external = manager.user_sources_dir / "external.js"
    builtin.parent.mkdir(parents=True, exist_ok=True)
    active.parent.mkdir(parents=True, exist_ok=True)
    external.parent.mkdir(parents=True, exist_ok=True)
    builtin.write_text("module.exports = {};", encoding="utf-8")
    active.write_text("module.exports = {};", encoding="utf-8")
    external.write_text("module.exports = {};", encoding="utf-8")
    write_registry(
        manager,
        [
            source_entry("builtin", "sources/builtin.js"),
            source_entry("imported", "sources/active/imported.js"),
            source_entry("external", "../user_sources/external.js"),
            source_entry("missing", "sources/missing.js"),
        ],
    )

    builtin_result = manager.remove_source("builtin")
    builtin_backup = Path(builtin_result["backupPath"])
    assert not builtin.exists()
    assert builtin_backup.exists()
    assert builtin_backup.read_text(encoding="utf-8") == "module.exports = {};"

    imported_result = manager.remove_source("imported")
    assert not active.exists()
    assert Path(imported_result["backupPath"]).exists()

    external_result = manager.remove_source("external")
    assert external_result["externalFilePreserved"] is True
    assert external.exists()
    assert not external_result["backupPath"]

    missing_result = manager.remove_source("missing")
    assert not missing_result["backupPath"]
    assert manager.list_sources() == []

    try:
        manager.remove_source("unknown")
    except SourceRegistryError:
        pass
    else:
        raise AssertionError("missing source removal did not fail")


def test_registry_rollback(root: Path) -> None:
    manager = SourceRegistryManager(root)
    source_path = manager.sources_dir / "rollback.js"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("module.exports = {};", encoding="utf-8")
    write_registry(manager, [source_entry("rollback", "sources/rollback.js")])
    original_save = manager._save_registry_document

    def fail_save(_document: dict) -> None:
        raise OSError("fixture save failure")

    manager._save_registry_document = fail_save
    try:
        manager.remove_source("rollback")
    except SourceRegistryError:
        pass
    else:
        raise AssertionError("registry save failure did not abort removal")
    finally:
        manager._save_registry_document = original_save
    assert source_path.exists()
    assert manager.list_sources()[0]["id"] == "rollback"


def test_manager_button(root: Path, app: QApplication) -> None:
    manager = SourceRegistryManager(root)
    source_path = manager.sources_dir / "ui_source.js"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("module.exports = {};", encoding="utf-8")
    source = source_entry("ui_source", "sources/ui_source.js")
    write_registry(manager, [source])
    client = FakeClient()
    page = SourceManagerPage(client, manager)
    page.on_source_list_received([{**source, "fileExists": True, "scanError": ""}])
    page.source_tree.setCurrentItem(page.source_tree.topLevelItem(0))
    assert page.delete_button.isEnabled()

    original_warning = QMessageBox.warning
    QMessageBox.warning = staticmethod(lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    try:
        page.delete_selected_source()
    finally:
        QMessageBox.warning = original_warning
    assert manager.list_sources() == []
    assert client.reloaded == ["ui_source"]
    assert not source_path.exists()
    assert any(manager.backups_dir.iterdir())
    page.deleteLater()
    client.deleteLater()
    app.processEvents()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    with tempfile.TemporaryDirectory(prefix="hushplayer_remove_source_") as temp_dir:
        root = Path(temp_dir)
        test_registry_removal(root / "registry")
        test_registry_rollback(root / "rollback")
        test_manager_button(root / "ui", app)
    print("source removal smoke: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
