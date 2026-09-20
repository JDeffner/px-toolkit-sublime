"""Tiger process management and report normalization, separate from LSP diagnostics."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path

from .core import parents_for, under
from .install import hidden_process


def glob_match(pattern, file):
    pattern, file = pattern.replace("\\", "/").lower(), file.replace("\\", "/").lower()
    expression, i = "", 0
    while i < len(pattern):
        if pattern[i:i+3] == "**/":
            expression += "(?:.*/)?"
            i += 3
        elif pattern[i:i+2] == "**":
            expression += ".*"
            i += 2
        else:
            expression += "[^/]*" if pattern[i] == "*" else "[^/]" if pattern[i] == "?" else re.escape(pattern[i])
            i += 1
    return bool(re.fullmatch(expression, file) or ("/" not in pattern and re.fullmatch(expression, file.rsplit("/", 1)[-1])))


def suppressed(text, line, code, file, settings):
    if code in settings.get("diagnosticsIgnore", []):
        return True
    if any(glob_match(p, file) for p in settings.get("diagnosticsIgnorePatterns", [])):
        return True
    lines = text.splitlines()
    for n in (line - 1, line):
        if n < 0 or n >= len(lines):
            continue
        match = re.search(r"#\s*px:ignore(-next-line)?\b(.*)", lines[n], re.I)
        if match and n + bool(match.group(1)) == line:
            codes = match.group(2).split("--", 1)[0].strip().split()
            if not codes or code in codes:
                return True
    return False


def parse_reports(text):
    try:
        raw = json.loads(text)
    except ValueError:
        # Progress messages may contain brackets too: seek a complete JSON array.
        raw = None
        for match in re.finditer(r"\[", text):
            try:
                raw = json.loads(text[match.start():])
                break
            except ValueError:
                continue
    if not isinstance(raw, list):
        raise ValueError("Tiger did not return a JSON report")
    return [r for r in raw if isinstance(r, dict) and isinstance(r.get("message"), str)]


def diagnostics(reports, root, settings, read_text=None):
    out, cache = [], {}
    for report in reports:
        for loc in report.get("locations", []):
            if not isinstance(loc, dict):
                continue
            file = loc.get("fullpath") or loc.get("path")
            if not isinstance(file, str):
                continue
            file = os.path.abspath(os.path.join(root, file))
            if not under(file, root):
                continue
            line = max(0, int(loc.get("linenr") or loc.get("line") or 1) - 1)
            code = report.get("key", "unknown")
            if file not in cache:
                try:
                    cache[file] = read_text(file) if read_text else Path(file).read_text(encoding="utf-8-sig")
                except (OSError, UnicodeError):
                    cache[file] = ""
            if suppressed(cache[file], line, code, os.path.relpath(file, root), settings):
                continue
            out.append({"file": file, "line": line, "column": max(0, int(loc.get("column") or 1) - 1),
                        "length": max(1, int(loc.get("length") or 1)), "code": code,
                        "severity": report.get("severity", "warning"), "message": report["message"],
                        "info": report.get("info", "")})
    return out


def command(executable, root, settings, config_directory):
    args = [executable, "--json"]
    explicit = Path(root) / ".px-toolkit/ck3-tiger.conf"
    if explicit.is_file():
        args += ["--config", str(explicit)]
    elif not (Path(root) / "ck3-tiger.conf").is_file():
        blocks = []
        for parent in parents_for(settings, root):
            descriptor = Path(parent) / "descriptor.mod"
            if descriptor.is_file() and not under(root, parent):
                value = str(descriptor).replace("\\", "/")
                if '"' in value or "\n" in value:
                    raise ValueError("Tiger dependency paths cannot contain quotes/newlines")
                blocks.append('load_mod = {\n\tmodfile = "' + value + '"\n}\n')
        if blocks:
            Path(config_directory).mkdir(parents=True, exist_ok=True)
            conf = Path(config_directory) / "ck3-tiger.conf"
            conf.write_text("".join(blocks), encoding="utf-8")
            args += ["--config", str(conf)]
    game = settings.get("gamePath")
    if game:
        args += ["--ck3", str(Path(game).parent if Path(game).name.lower() == "game" else Path(game))]
    return args + [root]


class TigerRun:
    def __init__(self):
        self.cancelled = threading.Event()
        self.child = None

    def cancel(self):
        self.cancelled.set()
        child = self.child
        if child and child.poll() is None:
            child.terminate()

    def run(self, args, root, timeout=180):
        # Spool to disk: large validator outputs must not exhaust plugin_host.
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            if self.cancelled.is_set():
                return None
            self.child = subprocess.Popen(args, cwd=root, stdout=output, stderr=errors, **hidden_process())
            if self.cancelled.is_set():
                self.child.terminate()
            try:
                self.child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait()
                raise ValueError("Tiger exceeded the configured timeout")
            if self.cancelled.is_set():
                return None
            if output.tell() > 128 * 1024 * 1024:
                raise ValueError("Tiger report exceeds 128 MiB")
            output.seek(0)
            text = output.read().decode("utf-8-sig", errors="replace")
            try:
                return parse_reports(text)
            except ValueError:
                errors.seek(0)
                raise ValueError("Tiger exited with code {}: {}".format(self.child.returncode, errors.read(8192).decode("utf-8", errors="replace")))
