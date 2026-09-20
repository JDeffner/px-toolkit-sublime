"""Create an isolated Windows portable profile from an installed Sublime.

Only .dev/sublime is written. The user's normal Sublime profile is not used.
"""
import json
import pathlib
import shutil
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / ".dev/sublime"


def main():
    source = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "C:/Program Files/Sublime Text")
    TARGET.mkdir(parents=True, exist_ok=True)
    for file in source.iterdir():
        if file.name.startswith("unins"):
            continue
        if file.is_dir():
            shutil.copytree(file, TARGET / file.name, dirs_exist_ok=True)
        else:
            shutil.copy2(file, TARGET / file.name)
    data = TARGET / "Data"
    installed = data / "Installed Packages"
    installed.mkdir(parents=True, exist_ok=True)
    control = installed / "Package Control.sublime-package"
    if not control.exists():
        urllib.request.urlretrieve("https://github.com/sublimehq/package_control/releases/download/4.2.8/Package.Control.sublime-package", control)
    harness = data / "Packages/PxTestHarness"
    harness.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "scripts/sublime_harness.py", harness / "plugin.py")
    (harness / ".python-version").write_text("3.8\n")
    user = data / "Packages/User"
    user.mkdir(parents=True, exist_ok=True)
    (user / "Preferences.sublime-settings").write_text(json.dumps({"update_check": False, "hot_exit": False, "show_git_status": False}))
    (user / "LSP.sublime-settings").write_text(json.dumps({"semantic_highlighting": True, "show_inlay_hints": True, "log_debug": True, "log_server": ["panel"]}))
    print(TARGET)


if __name__ == "__main__":
    main()
