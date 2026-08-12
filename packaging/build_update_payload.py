"""Build a portable ZIP payload for the in-app HushPlayer updater."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


REQUIRED_FILES = {"HushPlayer.exe", "HushPlayerUpdater.exe"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_NAMES = {"__pycache__"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_payload(source_dir: Path, output_path: Path) -> dict[str, object]:
    source_dir = source_dir.resolve()
    output_path = output_path.resolve()
    if not source_dir.is_dir():
        raise ValueError(f"发布目录不存在：{source_dir}")

    files: list[Path] = []
    names: set[str] = set()
    for candidate in sorted(source_dir.rglob("*")):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(source_dir)
        if any(part in EXCLUDED_NAMES for part in relative.parts[:-1]):
            continue
        if candidate.suffix.casefold() in EXCLUDED_SUFFIXES:
            continue
        name = relative.as_posix()
        files.append(candidate)
        names.add(name)

    missing = REQUIRED_FILES - names
    if missing:
        raise ValueError(f"发布目录缺少应用内更新必要文件：{', '.join(sorted(missing))}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    with zipfile.ZipFile(
        output_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for candidate in files:
            relative = candidate.relative_to(source_dir)
            archive.write(candidate, relative.as_posix())

    return {
        "filename": output_path.name,
        "size": output_path.stat().st_size,
        "sha256": _sha256(output_path),
        "files": len(files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    print(json.dumps(build_payload(arguments.source_dir, arguments.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
