"""托盘：首次最小化提示不得因设置写盘失败而阻断隐藏/恢复。"""

from __future__ import annotations

from hushplayer.ui import main_window as main_window_module


class _SettingsStub:
    def __init__(self, *, explode: bool) -> None:
        self.values = {"general.tray_hint_shown": False}
        self.explode = explode
        self.flushes = 0

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value, **_kwargs):
        self.values[key] = value
        return True

    def flush(self):
        self.flushes += 1
        if self.explode:
            raise OSError(28, "No space left on device")
        return True


class _CtxStub:
    def __init__(self, settings) -> None:
        self.settings = settings


class _WindowStub:
    """只实现 _hide_to_tray 需要的最小接口。"""

    _tray = None

    def __init__(self) -> None:
        self.hidden = False
        self.background_calls = 0

    def hide(self) -> None:
        self.hidden = True

    def _tray_available(self) -> bool:
        return True

    def _background_without_tray(self) -> None:
        self.background_calls += 1


def _call_hide_to_tray(monkeypatch, *, explode: bool):
    settings = _SettingsStub(explode=explode)
    ctx = _CtxStub(settings)
    notices: list[str] = []
    monkeypatch.setattr(main_window_module, "ctx", lambda: ctx)
    monkeypatch.setattr(
        main_window_module, "notify", lambda _parent, title, _text: notices.append(title)
    )
    window = _WindowStub()
    main_window_module.MainWindow._hide_to_tray(window)
    return window, settings, notices


def test_first_tray_hint_does_not_block_hiding(monkeypatch) -> None:
    window, settings, notices = _call_hide_to_tray(monkeypatch, explode=False)
    assert window.hidden is True
    assert notices == ["已最小化到系统托盘"]
    assert settings.values["general.tray_hint_shown"] is True
    assert settings.flushes == 1


def test_tray_hint_written_once(monkeypatch) -> None:
    window, settings, notices = _call_hide_to_tray(monkeypatch, explode=False)
    assert window.hidden is True
    # 第二次最小化：提示已记录，不再弹窗，也不再写盘。
    monkeypatch.setattr(main_window_module, "ctx", lambda: _CtxStub(settings))
    window2 = _WindowStub()
    main_window_module.MainWindow._hide_to_tray(window2)
    assert window2.hidden is True
    assert notices == ["已最小化到系统托盘"]
    assert settings.flushes == 1


def test_tray_hint_write_failure_still_hides(monkeypatch) -> None:
    """设置写盘失败时窗口仍必须隐藏，且异常不能冒泡到 Qt 事件循环。"""
    window, settings, notices = _call_hide_to_tray(monkeypatch, explode=True)
    assert window.hidden is True, "写盘失败不能导致最小化失效"
    assert notices == ["已最小化到系统托盘"]
    assert settings.values["general.tray_hint_shown"] is True


def test_tray_hint_save_uses_existing_api(monkeypatch) -> None:
    """Settings 没有 save()；提示状态必须通过 set()/flush() 落盘。"""
    from hushplayer.core.settings import Settings

    assert not hasattr(Settings, "save"), "若将来新增 save()，本测试需重新评估"
    source = main_window_module.MainWindow._hide_to_tray.__code__
    names = set(source.co_names)
    assert "save" not in names, "禁止调用不存在的 Settings.save()"
