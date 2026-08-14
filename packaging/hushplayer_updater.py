"""Small Windows helper that replaces a stopped HushPlayer installation."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


_WAIT_TIMEOUT_MS = 120_000
_REPLACE_RETRY_TIMEOUT_MS = 30_000
_REPLACE_RETRY_INITIAL_DELAY_MS = 100
_REPLACE_RETRY_MAX_DELAY_MS = 1_000
_REQUIRED_FILES = {"HushPlayer.exe", "HushPlayerUpdater.exe"}
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200
_CREATE_NO_WINDOW = 0x08000000
_MAX_PACKAGE_MEMBERS = 20_000
_MAX_PACKAGE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


class UpdateApplyError(RuntimeError):
    pass


def _safe_member_name(name: str) -> str:
    normalized = str(name or "").replace("\\", "/").rstrip("/")
    parts = normalized.split("/")
    if (
        not normalized
        or "\x00" in normalized
        or normalized.startswith("/")
        or Path(normalized).drive
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise UpdateApplyError("更新包包含不安全的文件路径。")
    return normalized


def _wait_for_parent(pid: int) -> None:
    if pid <= 0 or pid == os.getpid():
        raise UpdateApplyError("更新助手收到无效的父进程 PID。")
    if os.name != "nt":
        deadline = time.monotonic() + (_WAIT_TIMEOUT_MS / 1000)
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return
            time.sleep(0.1)
        raise UpdateApplyError("等待 HushPlayer 退出超时。")

    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        result = ctypes.windll.kernel32.WaitForSingleObject(
            handle,
            _WAIT_TIMEOUT_MS,
        )
        if result != 0:
            raise UpdateApplyError("等待 HushPlayer 退出超时。")
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Replace a Windows directory after short-lived child-process locks clear."""

    deadline = time.monotonic() + (_REPLACE_RETRY_TIMEOUT_MS / 1000)
    delay = _REPLACE_RETRY_INITIAL_DELAY_MS / 1000
    while True:
        try:
            os.replace(source, destination)
            return
        except OSError:
            # A PermissionError is how Python exposes the Windows sharing and
            # directory-lock errors raised while a child still has the old
            # install directory as its working directory.  The bounded retry
            # also tolerates antivirus/indexer handles without hiding a
            # permanent failure indefinitely.
            if time.monotonic() >= deadline:
                raise
            time.sleep(delay)
            delay = min(delay * 2, _REPLACE_RETRY_MAX_DELAY_MS / 1000)


def _extract_package(package: Path, install_dir: Path) -> Path:
    stage_dir = Path(
        tempfile.mkdtemp(
            prefix=".HushPlayer-update-",
            dir=str(install_dir.parent),
        )
    )
    names: set[str] = set()
    try:
        with zipfile.ZipFile(package) as archive:
            members = archive.infolist()
            if len(members) > _MAX_PACKAGE_MEMBERS:
                raise UpdateApplyError("更新包包含过多文件。")
            total_uncompressed = 0
            for member in members:
                normalized = _safe_member_name(member.filename)
                if normalized in names:
                    raise UpdateApplyError("更新包包含重复的文件路径。")
                names.add(normalized)
                mode = (member.external_attr >> 16) & 0o170000
                if member.create_system == 3 and mode == stat.S_IFLNK:
                    raise UpdateApplyError("更新包不允许包含符号链接。")
                total_uncompressed += max(0, int(member.file_size))
                if total_uncompressed > _MAX_PACKAGE_UNCOMPRESSED_BYTES:
                    raise UpdateApplyError("更新包解压后超过安全大小限制。")
                if member.is_dir():
                    (stage_dir / normalized).mkdir(parents=True, exist_ok=True)
                    continue
                target = stage_dir / normalized
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
        if not _REQUIRED_FILES.issubset(names):
            missing = ", ".join(sorted(_REQUIRED_FILES - names))
            raise UpdateApplyError(f"更新包缺少必要文件：{missing}。")
        return stage_dir
    except (OSError, zipfile.BadZipFile, UpdateApplyError) as error:
        shutil.rmtree(stage_dir, ignore_errors=True)
        if isinstance(error, UpdateApplyError):
            raise
        raise UpdateApplyError(f"解压应用内更新包失败：{error}") from error


def _start_application(executable: Path, working_dir: Path) -> None:
    if not executable.is_file():
        raise UpdateApplyError("更新后的 HushPlayer.exe 不存在。")
    flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            [str(executable)],
            cwd=str(working_dir),
            close_fds=True,
            creationflags=flags if os.name == "nt" else 0,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise UpdateApplyError(f"更新后无法重新启动 HushPlayer：{error}") from error


def apply_update(
    *,
    parent_pid: int,
    install_dir: Path,
    package: Path,
    restart_exe: Path,
) -> None:
    install_dir = install_dir.expanduser().resolve()
    package = package.expanduser().resolve()
    restart_exe = restart_exe.expanduser().resolve()
    if not install_dir.is_dir():
        raise UpdateApplyError("HushPlayer 安装目录不存在。")
    if not package.is_file():
        raise UpdateApplyError("应用内更新包不存在。")
    if restart_exe.parent != install_dir or restart_exe.name != "HushPlayer.exe":
        raise UpdateApplyError("重启程序路径不在 HushPlayer 安装目录中。")

    _wait_for_parent(parent_pid)
    stage_dir = _extract_package(package, install_dir)
    backup_dir = install_dir.parent / f".HushPlayer-backup-{os.getpid()}"
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)
    cleanup_backup = False
    try:
        _replace_with_retry(install_dir, backup_dir)
        try:
            _replace_with_retry(stage_dir, install_dir)
        except OSError:
            _replace_with_retry(backup_dir, install_dir)
            raise
        try:
            _start_application(restart_exe, install_dir)
        except UpdateApplyError:
            shutil.rmtree(install_dir, ignore_errors=True)
            _replace_with_retry(backup_dir, install_dir)
            raise
        cleanup_backup = True
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
        # The old application is no longer needed once the new process starts.
        # If cleanup is blocked by antivirus software, leave the backup for the
        # next update attempt instead of risking the new installation.
        if cleanup_backup and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)


def _write_failure_log(install_dir: Path, message: str) -> None:
    try:
        (install_dir.parent / "HushPlayer-update-error.log").write_text(
            message + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="HushPlayerUpdater")
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--install-dir", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--restart-exe", required=True, type=Path)
    parser.add_argument("--cleanup-helper", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    install_dir = arguments.install_dir.expanduser().resolve()
    try:
        apply_update(
            parent_pid=arguments.parent_pid,
            install_dir=install_dir,
            package=arguments.package,
            restart_exe=arguments.restart_exe,
        )
        return 0
    except Exception as error:
        _write_failure_log(install_dir, str(error))
        try:
            _start_application(install_dir / "HushPlayer.exe", install_dir)
        except UpdateApplyError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
