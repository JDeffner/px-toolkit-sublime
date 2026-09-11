"""Bounded, cancellable mod-only watcher; no dependency on another package."""
from __future__ import annotations

import os
import threading

EXTENSIONS = {".txt", ".yml", ".yaml", ".gui", ".mod", ".asset", ".info"}
CONFIGS = {"calendar.json", "schema.json", "playset.json"}
SKIP = {".git", "node_modules", ".svn", "__pycache__"}


def snapshot(roots, stopped=None):
    files = {}
    for root in roots:
        for folder, dirs, names in os.walk(root, followlinks=False):
            if stopped and stopped.is_set():
                return files
            dirs[:] = [d for d in dirs if d not in SKIP and not os.path.islink(os.path.join(folder, d))]
            for name in names:
                if os.path.splitext(name)[1].lower() not in EXTENSIONS and name not in CONFIGS:
                    continue
                file = os.path.join(folder, name)
                try:
                    if os.path.islink(file):
                        continue
                    s = os.stat(file)
                    files[file] = (s.st_mtime_ns, s.st_size)
                except OSError:
                    pass
    return files


def changes(before, after):
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


class ModWatcher:
    def __init__(self, roots, callback, interval=3):
        self.roots = list(roots)
        self.callback = callback
        self.interval = max(1, interval)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="LSP-px watcher", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def run(self):
        previous = snapshot(self.roots, self.stop_event)
        while not self.stop_event.wait(self.interval):
            current = snapshot(self.roots, self.stop_event)
            updated = changes(previous, current)
            if updated and not self.stop_event.is_set():
                self.callback(updated)
            previous = current
