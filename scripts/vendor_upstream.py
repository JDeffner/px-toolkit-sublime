"""Refresh syntax grammars from a checked-out, pinned upstream release.

Usage: python scripts/vendor_upstream.py ../paradox-modding-toolkit
Grammars are converted losslessly to Sublime's supported XML plist format.
"""
import json
import pathlib
import plistlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PIN = "f517501e0edb83fb0473a5db1c2a9c42afb06886"


def main():
    upstream = pathlib.Path(sys.argv[1]).resolve()
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != PIN:
        raise SystemExit("Expected upstream " + PIN)
    syntaxes = ROOT / "syntaxes"
    syntaxes.mkdir(exist_ok=True)
    names = {"paradox": "Paradox Script", "paradox-loc": "Paradox Localization",
             "paradox-gui": "Paradox GUI", "paradox-mod": "Paradox Descriptor",
             "paradox-info": "Paradox Info", "paradox-datafunction": "Paradox Datafunction"}
    for stem, name in names.items():
        source = upstream / "packages/vscode/syntaxes" / (stem + ".tmLanguage.json")
        grammar = json.loads(source.read_text(encoding="utf-8"))
        grammar.pop("$schema", None)
        grammar.pop("fileTypes", None)  # Workspace-aware detection owns broad extensions.
        grammar["name"] = name
        if stem == "paradox-datafunction":
            grammar["hidden"] = True
        (syntaxes / (name + ".tmLanguage")).write_bytes(plistlib.dumps(grammar, sort_keys=False))
    shutil.copyfile(upstream / "LICENSE", ROOT / "LICENSE")
    (ROOT / "data").mkdir(exist_ok=True)
    # Keep the exact descriptor source as the provenance for generated field data.
    vendor = ROOT / "vendor"
    vendor.mkdir(exist_ok=True)
    shutil.copyfile(upstream / "packages/protocol/src/descriptorMod.ts", vendor / "descriptorMod.ts")
    (vendor / "README.md").write_text(
        "Descriptor vocabulary and validation reference from JDeffner/paradox-modding-toolkit, "
        + PIN + ", GPL-3.0-or-later. Syntax grammars share that provenance.\n\n"
        "The runtime Python validator uses the generated data/descriptor.json vocabulary; "
        "it tokenizes strings/comments to preserve braces and # inside quoted values.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
