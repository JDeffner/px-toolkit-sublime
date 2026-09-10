"""Development-only test controller, copied to an isolated portable profile."""
import importlib
import json
import os
import sys
import threading
import traceback
from pathlib import Path

import sublime
import sublime_plugin

DATA = Path(sublime.packages_path()).parent


def record(name, data):
    (DATA / (name + ".json")).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def plugin_loaded():
    record("harness", {"build": sublime.version(), "python": sys.version, "packages": sublime.packages_path()})
    def install_lsp():
        try:
            preferences = sublime.load_settings("Package Control.sublime-settings")
            preferences.set("installed_packages", ["Package Control", "LSP"])
            preferences.set("auto_upgrade", False)
            sublime.save_settings("Package Control.sublime-settings")
            PackageManager = importlib.import_module("Package Control.package_control.package_manager").PackageManager
            manager = PackageManager()
            result = manager.install_package("LSP")
            manager.install_libraries(manager.get_libraries("LSP"))
            record("bootstrap", {"installed": result})
        except Exception:
            record("bootstrap", {"error": traceback.format_exc()})
    if not (DATA / "Installed Packages/LSP.sublime-package").exists():
        sublime.set_timeout_async(install_lsp, 2500)


class PxTestCommand(sublime_plugin.WindowCommand):
    def run(self, script=None):
        try:
            if script:
                namespace = {"window": self.window, "record": record, "DATA": DATA}
                exec(compile(Path(script).read_text(encoding="utf-8-sig"), script, "exec"), namespace)
            else:
                module = importlib.import_module("LSP-px.plugin")
                record("plugin", {"loaded": True, "has_lsp": module.HAS_LSP,
                                  "syntaxes": [(s.name, s.scope) for s in sublime.list_syntaxes() if "paradox" in s.scope],
                                  "instance": bool(module.instance(self.window))})
        except Exception:
            record("plugin", {"error": traceback.format_exc()})


class PxTestRunCommand(PxTestCommand):
    def run(self):
        super().run(str(DATA / "integration.py"))
