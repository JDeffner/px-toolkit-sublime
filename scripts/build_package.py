"""Build a deterministic packed package and optional isolated test install."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = {"lib", "syntaxes", "data", "vendor", "messages", "docs"}
INCLUDE_FILES = {"plugin.py", ".python-version", "README.md", "LICENSE", "THIRD-PARTY-NOTICES.md", "CHANGELOG.md", "sublime-package.json", "messages.json"}


def build(destination=None):
    target = ROOT / "dist/LSP-px.sublime-package"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        candidates = list(ROOT.iterdir())
        for directory in INCLUDE_DIRS:
            if (ROOT / directory).is_dir():
                candidates.extend((ROOT / directory).rglob("*"))
        for file in sorted(candidates):
            rel = file.relative_to(ROOT)
            if not file.is_file() or "__pycache__" in rel.parts:
                continue
            if rel.parts[0] not in INCLUDE_DIRS and not (len(rel.parts) == 1 and (file.name in INCLUDE_FILES or ".sublime-" in file.name or file.suffix == ".tmPreferences")):
                continue
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 9, 10, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, file.read_bytes())
    if destination:
        Path(destination).mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, Path(destination) / target.name)
    print(target)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", help="An isolated Installed Packages directory")
    args = parser.parse_args()
    build(args.install)
