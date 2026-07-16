from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.version import (
    APP_NUMERIC_VERSION_TEXT,
    APP_VERSION,
    UPDATE_ARCHITECTURE,
)


POWERSHELL = Path(
    r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
ISCC_CANDIDATES = (
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
)


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as error:
        raise AssertionError(
            f"command failed ({error.returncode}): {command}\n{error.stdout}"
        ) from error


def check_metadata_generator(temp_root: Path) -> None:
    output_dir = temp_root / "version"
    result = run(
        [
            sys.executable,
            str(PROJECT_ROOT / "packaging" / "prepare_version_metadata.py"),
            "--output-dir",
            str(output_dir),
        ]
    )
    metadata = json.loads(result.stdout.strip())
    assert metadata["app_version"] == APP_VERSION
    assert metadata["numeric_version"] == APP_NUMERIC_VERSION_TEXT
    assert metadata["architecture"] == UPDATE_ARCHITECTURE
    assert metadata["installer_filename"] == (
        "HushPlayer-0.5.0-beta.2-win-x64-setup.exe"
    )
    version_info_path = Path(metadata["version_info_file"])
    version_info = version_info_path.read_text(encoding="utf-8")
    compile(version_info, str(version_info_path), "eval")
    assert "filevers=(0, 5, 0, 2)" in version_info
    assert "prodvers=(0, 5, 0, 2)" in version_info
    assert "FileVersion', '0.5.0-beta.2'" in version_info
    assert "ProductVersion', '0.5.0-beta.2'" in version_info


def check_sources() -> None:
    static_version_info = (
        PROJECT_ROOT / "packaging" / "version_info.txt"
    ).read_text(encoding="utf-8")
    assert "prepare_version_metadata.py" in static_version_info
    assert "0.5.0-beta" not in static_version_info

    for name in ("HushPlayer.debug.spec", "HushPlayer.release.spec"):
        source = (PROJECT_ROOT / "packaging" / name).read_text(encoding="utf-8")
        compile(source, name, "exec")
        assert 'os.environ["HUSHPLAYER_VERSION_INFO"]' in source
        assert 'version=str(VERSION_INFO_FILE)' in source
        assert '"packaging" / "version_info.txt"' not in source

    for name in ("build_windows_debug.ps1", "build_windows_release.ps1"):
        source = (PROJECT_ROOT / "packaging" / name).read_text(encoding="utf-8")
        assert "(3, 13)" in source
        assert "prepare_version_metadata.py" in source
        assert "HUSHPLAYER_VERSION_INFO" in source
        assert "3.12" not in source

    installer_source = (
        PROJECT_ROOT / "packaging" / "installer" / "HushPlayer.iss"
    ).read_text(encoding="utf-8")
    assert "AppId={{8A9C184E-32A0-4D9E-A3D4-51C492A5D7B6}" in installer_source
    assert "UsePreviousAppDir=yes" in installer_source
    assert "CloseApplications=yes" in installer_source
    assert "RestartApplications=no" in installer_source
    assert "[UninstallDelete]" not in installer_source
    assert "#ifndef MyAppVersion" in installer_source
    assert "#ifndef MyAppNumericVersion" in installer_source
    assert "#ifndef MyAppArchitecture" in installer_source
    assert "0.5.0-beta.1" not in installer_source
    assert "0.5.0-beta.2" not in installer_source
    assert (
        "OutputBaseFilename=HushPlayer-{#MyAppVersion}-"
        "{#MyAppArchitecture}-setup"
    ) in installer_source

    lock_source = (PROJECT_ROOT / "requirements-lock.txt").read_text(
        encoding="utf-8"
    )
    assert "CPython 3.13 / Windows x64 build lock" in lock_source
    assert "fe2c7201c642b7c308f1675355ad7ff7b66acfe3541625efe5a3ad38f29d6115" in lock_source


def check_diagnostic_scripts() -> None:
    for name in (
        "build_windows_debug.ps1",
        "build_windows_release.ps1",
        "build_windows_installer.ps1",
    ):
        result = run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(PROJECT_ROOT / "packaging" / name),
                "-DiagnosticOnly",
            ]
        )
        assert "DiagnosticOnly=OK" in result.stdout, (name, result.stdout)


def check_inno_define_syntax(temp_root: Path) -> None:
    iscc = next((candidate for candidate in ISCC_CANDIDATES if candidate.is_file()), None)
    if iscc is None:
        print("Inno Setup compiler unavailable; macro compile probe skipped")
        return
    output_dir = temp_root / "inno-output"
    output_dir.mkdir(parents=True, exist_ok=True)
    script = temp_root / "macro-probe.iss"
    script.write_text(
        """#ifndef MyAppVersion
  #error MyAppVersion missing
#endif
#ifndef MyAppNumericVersion
  #error MyAppNumericVersion missing
#endif
#ifndef MyAppArchitecture
  #error MyAppArchitecture missing
#endif
[Setup]
AppId=HushPlayerVersionMacroProbe
AppName=HushPlayer Version Macro Probe
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppNumericVersion}
DefaultDirName={tmp}\\HushPlayerVersionMacroProbe
PrivilegesRequired=lowest
Uninstallable=no
OutputDir="""
        + str(output_dir)
        + """
OutputBaseFilename=Macro-{#MyAppVersion}-{#MyAppArchitecture}
""",
        encoding="utf-8",
    )
    run(
        [
            str(iscc),
            "/Qp",
            f"/DMyAppVersion={APP_VERSION}",
            f"/DMyAppNumericVersion={APP_NUMERIC_VERSION_TEXT}",
            f"/DMyAppArchitecture={UPDATE_ARCHITECTURE}",
            str(script),
        ]
    )
    assert (
        output_dir
        / "Macro-0.5.0-beta.2-win-x64.exe"
    ).is_file()


def main() -> None:
    check_sources()
    with tempfile.TemporaryDirectory(prefix="hushplayer_packaging_version_") as temp_dir:
        temp_root = Path(temp_dir)
        check_metadata_generator(temp_root)
        check_inno_define_syntax(temp_root)
    check_diagnostic_scripts()
    print("packaging version smoke: OK")


if __name__ == "__main__":
    main()
