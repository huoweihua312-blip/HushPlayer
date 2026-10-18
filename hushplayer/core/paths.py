"""应用路径解析。

设计要点：
* 程序文件（源码 / 打包资源）与用户数据严格分离。
* 开发态、PyInstaller 打包态、便携态都能正确定位。
* 数据目录可以通过 ``HUSHPLAYER_DATA_DIR`` 覆盖，测试与 UI 截图流程使用临时目录，
  绝不会触碰真实用户数据。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "HushPlayerReimagined"
PORTABLE_FLAG = "portable.txt"

_cached_data_dir: Path | None = None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_dir() -> Path:
    """exe 所在目录（开发态为项目根目录）。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return project_root()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """只读资源根目录（打包后位于 ``_internal`` / ``_MEIPASS``）。"""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return project_root()


def resource_path(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def runtime_dir() -> Path:
    """Node 在线音源运行时目录。"""
    bundled = resource_path("hushplayer", "runtime", "source_runtime")
    if bundled.is_dir():
        return bundled
    # 打包时若资源被平铺到根目录
    flat = resource_path("source_runtime")
    return flat if flat.is_dir() else bundled


def bundled_node() -> Path | None:
    for candidate in (
        resource_path("hushplayer", "runtime", "node", "node.exe"),
        resource_path("runtime", "node", "node.exe"),
        executable_dir() / "node.exe",
    ):
        if candidate.is_file():
            return candidate
    return None


def _portable_requested() -> bool:
    env = os.environ.get("HUSHPLAYER_PORTABLE", "").strip().lower()
    if env in {"1", "true", "yes"}:
        return True
    return (executable_dir() / PORTABLE_FLAG).is_file()


def default_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def _writable(path: Path) -> bool:
    """尝试创建目录并写一个探针文件，判断是否真的可写。"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_bytes(b"0")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir() -> Path:
    """可写用户数据目录（设置、数据库、日志、缓存）。

    解析顺序：``HUSHPLAYER_DATA_DIR`` → 便携模式（exe 同级 ``Data``）→
    ``%LOCALAPPDATA%\\HushPlayerReimagined``。若首选位置不可写（受限账户、
    组策略、沙箱等），自动退回到 exe 同级 ``Data``，最后退回临时目录，
    避免启动时因权限问题直接崩溃。
    """
    global _cached_data_dir
    if _cached_data_dir is not None:
        return _cached_data_dir
    override = os.environ.get("HUSHPLAYER_DATA_DIR", "").strip()
    if override:
        path = Path(override).expanduser()
    elif _portable_requested():
        path = executable_dir() / "Data"
    else:
        path = default_data_dir()
    if not _writable(path):
        fallback = executable_dir() / "Data"
        if fallback != path and _writable(fallback):
            path = fallback
        else:
            import tempfile

            path = Path(tempfile.mkdtemp(prefix="HushPlayer-"))
    _cached_data_dir = path
    return path


def set_data_dir(path: str | Path) -> Path:
    """测试 / 截图流程使用：切换数据目录并重建缓存。"""
    global _cached_data_dir
    os.environ["HUSHPLAYER_DATA_DIR"] = str(Path(path).resolve())
    _cached_data_dir = Path(path).resolve()
    ensure_dirs()
    return _cached_data_dir


def ensure_dirs() -> None:
    for path in (data_dir(), logs_dir(), cache_dir(), artwork_cache_dir(), audio_cache_dir(), lyrics_cache_dir()):
        path.mkdir(parents=True, exist_ok=True)


def settings_file() -> Path:
    return data_dir() / "settings.json"


def database_file() -> Path:
    return data_dir() / "hushplayer.db"


def logs_dir() -> Path:
    return data_dir() / "logs"


def cache_dir() -> Path:
    return data_dir() / "cache"


def artwork_cache_dir() -> Path:
    return cache_dir() / "artwork"


def audio_cache_dir() -> Path:
    return cache_dir() / "audio"


def lyrics_cache_dir() -> Path:
    return cache_dir() / "lyrics"


def lyrics_dir() -> Path:
    """用户自定义歌词（手工绑定）目录。"""
    return data_dir() / "lyrics"


def downloads_dir() -> Path:
    """默认下载目录：优先用户「音乐」目录，不可写时退回数据目录下的 Downloads。

    Windows 上 ``%USERPROFILE%\\Music`` 可能被组策略/OneDrive 重定向导致不可写，
    因此这里只做「可创建」探测，失败就使用随应用数据目录走的稳定位置。
    """
    candidates = [Path.home() / "Music" / "HushPlayer Downloads", data_dir() / "Downloads"]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_bytes(b"0")
            probe.unlink()
            return candidate
        except OSError:
            continue
    return data_dir() / "Downloads"


def backups_dir() -> Path:
    return data_dir() / "backups"


def default_cover_path() -> Path:
    return resource_path("assets", "default-cover.png")
