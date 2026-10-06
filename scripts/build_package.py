"""Build a deterministic packed package and optional isolated test install."""
import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = {"lib", "syntaxes", "data", "vendor", "messages", "docs"}
INCLUDE_FILES = {"plugin.py", ".python-version", "README.md", "LICENSE", "COPYRIGHT", "THIRD-PARTY-NOTICES.md",
                 "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "SUPPORT.md", "CHANGELOG.md",
                 "sublime-package.json", "messages.json", ".github/assets/px-st-icon.svg"}


def build(destination=None):
    target = ROOT / "dist/LSP-px.sublime-package"
    target.parent.mkdir(exist_ok=True)
    # The package is small. Stored entries avoid zlib-version differences,
    # giving identical checksums even across CPython/Sublime build machines.
    with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as archive:
        candidates = list(ROOT.iterdir())
        candidates.extend(ROOT / name for name in INCLUDE_FILES if "/" in name)
        for directory in INCLUDE_DIRS:
            if (ROOT / directory).is_dir():
                candidates.extend((ROOT / directory).rglob("*"))
        for file in sorted(candidates, key=lambda p: p.relative_to(ROOT).as_posix()):
            rel = file.relative_to(ROOT)
            if not file.is_file() or "__pycache__" in rel.parts:
                continue
            if rel.parts[0] not in INCLUDE_DIRS and rel.as_posix() not in INCLUDE_FILES and not (len(rel.parts) == 1 and (".sublime-" in file.name or file.suffix == ".tmPreferences")):
                continue
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 9, 10, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            # Every included resource is text. Normalize developer working-tree
            # line endings as well as archive metadata across OS builds.
            archive.writestr(info, file.read_bytes().replace(b"\r\n", b"\n"))
    if destination:
        Path(destination).mkdir(parents=True, exist_ok=True)
        # Do not let Sublime's watcher read a partially copied package.
        with tempfile.NamedTemporaryFile(dir=destination, suffix=".tmp", delete=False) as staging:
            temporary = Path(staging.name)
        try:
            shutil.copyfile(target, temporary)
            os.replace(str(temporary), str(Path(destination) / target.name))
        finally:
            if temporary.exists():
                temporary.unlink()
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", help="An isolated Installed Packages directory; close that editor before installing")
    args = parser.parse_args()
    build(args.install)
