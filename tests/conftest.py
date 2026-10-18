"""pytest 公共夹具。

原则：
- 每个测试使用独立临时数据目录，绝不接触真实用户数据；
- Qt 使用 offscreen 平台，只验证逻辑与控件构造，不做像素断言；
- 音频夹具来自 tests/fixtures/audio（由 tools/make_fixtures.py 生成）。
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP_ROOT = Path(__file__).resolve().parent.parent / ".pytest-tmp"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault(
    "HUSHPLAYER_DATA_DIR", tempfile.mkdtemp(prefix="hush-tests-boot-", dir=_TMP_ROOT)
)
os.environ.setdefault("HUSH_CONSOLE", "0")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

from hushplayer.core import paths  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "audio"


@pytest.fixture(scope="session")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        from PySide6.QtWidgets import QApplication

        app = QApplication([])
    yield app


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    directory = tmp_path / "data"
    paths.set_data_dir(directory)
    monkeypatch.setenv("HUSHPLAYER_DATA_DIR", str(directory))
    yield directory


@pytest.fixture()
def music_dir(tmp_path):
    target = tmp_path / "music"
    shutil.copytree(FIXTURES, target)
    return target


@pytest.fixture()
def library(data_dir, qapp):
    from hushplayer.services.library import LibraryService
    from hushplayer.store.db import Database

    database = Database(paths.database_file())
    database.initialize()
    service = LibraryService(database)
    yield service
    try:
        service.close()
    except Exception:  # noqa: BLE001
        pass
    database.close_current_thread()


@pytest.fixture()
def loaded_library(library, music_dir):
    result = library.import_files([str(path) for path in music_dir.rglob("*") if path.is_file()])
    assert result.added >= 8, result
    return library
