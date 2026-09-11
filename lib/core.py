"""Paths, configuration, protocol coordinates and safe source edits.

This module deliberately has no Sublime imports so its boundary behavior can
be tested on every platform. Game vocabulary comes from px-lsp.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

SERVER_VERSION = "0.3.4"
PACKAGE_VERSION = "0.1.0"
SETTINGS = {
    "gameId": "ck3", "gamePath": None, "logsPath": None, "modPath": None,
    "parentPaths": [], "workspaceMods": [], "locLanguage": "english",
    "completionMode": "minimal", "hoverDetail": "standard",
    "scopeInlayHints": False, "indexAssets": True, "calendar": None,
    "diagnosticsIgnore": [], "diagnosticsIgnorePatterns": [],
    "diagnosticsVanilla": False, "tracePerf": False,
}
LANGUAGES = {"script": "paradox", "loc": "paradox-loc", "gui": "paradox-gui",
             "mod": "paradox-mod", "info": "paradox-info"}
SCRIPT_DIRS = {"common", "events", "history", "decisions", "gfx", "map_data",
               "on_action", "gui", "content_source", "sound", "music", "dlc"}


def under(file, root):
    if not file or not root:
        return False
    try:
        f, r = os.path.normcase(os.path.realpath(file)), os.path.normcase(os.path.realpath(root))
        return os.path.commonpath([f, r]) == r
    except (ValueError, OSError):
        return False


def expand_path(value, base=None):
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError("Paths must be strings")
    p = os.path.expandvars(os.path.expanduser(value))
    return os.path.abspath(os.path.join(base or os.getcwd(), p))


def unique_paths(paths):
    out, seen = [], set()
    for p in paths:
        if p:
            key = os.path.normcase(os.path.realpath(p))
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def mod_root(file):
    if not file:
        return None
    p = Path(file)
    p = p if p.is_dir() else p.parent
    for candidate in (p, *p.parents):
        if (candidate / "descriptor.mod").is_file():
            return str(candidate)
    return None


def resolve_settings(raw, folders=(), active_file=None, excluded=()):
    result = copy.deepcopy(SETTINGS)
    result.update({k: copy.deepcopy(v) for k, v in raw.items() if k in SETTINGS})
    if result["gameId"] != "ck3":
        raise ValueError("LSP-px currently supports gameId 'ck3' only")
    if result["completionMode"] not in ("minimal", "examples", "names"):
        raise ValueError("completionMode must be minimal, examples or names")
    if result["hoverDetail"] not in ("compact", "standard", "full"):
        raise ValueError("hoverDetail must be compact, standard or full")
    if not isinstance(result["locLanguage"], str) or not re.fullmatch(r"[a-z_]+", result["locLanguage"]):
        raise ValueError("locLanguage must be a lowercase language identifier")
    for key in ("scopeInlayHints", "indexAssets", "diagnosticsVanilla", "tracePerf"):
        if not isinstance(result[key], bool):
            raise ValueError(key + " must be true or false")
    for key in ("parentPaths", "workspaceMods", "diagnosticsIgnore", "diagnosticsIgnorePatterns"):
        if not isinstance(result[key], list) or not all(isinstance(v, str) for v in result[key]):
            raise ValueError(key + " must be a list of strings")
    base = folders[0] if folders else (os.path.dirname(active_file) if active_file else None)
    for key in ("gamePath", "logsPath", "modPath"):
        result[key] = expand_path(result[key], base)
    game = result["gamePath"]
    if game and os.path.isdir(os.path.join(game, "game")):
        result["gamePath"] = os.path.join(game, "game")
    result["parentPaths"] = unique_paths(expand_path(p, base) for p in result["parentPaths"])
    roots = [expand_path(p, base) for p in result["workspaceMods"]]
    # Explicit editable roots win. Detect only folder roots (and one active mod),
    # never recursively turn a user's entire mod collection into a workspace.
    if not roots:
        roots = [mod_root(p) for p in folders]
        if not any(roots):
            roots = [mod_root(active_file)]
    if result["modPath"]:
        roots.insert(0, result["modPath"])
    excludes = [expand_path(p, base) for p in excluded]
    roots = unique_paths(p for p in roots if p and not any(under(p, x) for x in excludes)
                         and not under(p, result["gamePath"])
                         and not any(under(p, x) for x in result["parentPaths"]))
    result["workspaceMods"] = roots
    parents = dependency_roots(result)
    roots = [p for p in roots if not any(under(p, parent) for parent in parents)]
    result["workspaceMods"] = roots
    result["modPath"] = roots[0] if roots else None
    return result


def language_for(file, settings):
    if not file:
        return None
    roots = settings["workspaceMods"] + dependency_roots(settings) + [settings["gamePath"]]
    root = max((r for r in roots if under(file, r)), key=len, default=None)
    if not root:
        return None
    rel = os.path.relpath(file, root).replace("\\", "/").lower()
    suffix = Path(file).suffix.lower()
    if suffix == ".mod":
        return "mod"
    if suffix == ".info":
        return "info"
    if suffix == ".gui":
        return "gui"
    if suffix in (".yml", ".yaml") and rel.split("/")[0] in ("localization", "localisation"):
        return "loc"
    if suffix in (".txt", ".asset") and rel.split("/")[0] in SCRIPT_DIRS:
        return "script"
    return None


def editable_root(file, settings):
    if under(file, settings["gamePath"]) or any(under(file, p) for p in dependency_roots(settings)):
        return None
    return max((r for r in settings["workspaceMods"] if under(file, r)), key=len, default=None)


def file_uri(file):
    return Path(os.path.abspath(file)).as_uri()


def uri_path(uri):
    parts = urlsplit(uri)
    if parts.scheme != "file":
        raise ValueError("Expected a file URI")
    p = unquote(parts.path)
    if parts.netloc:
        p = "//" + parts.netloc + p
    elif os.name == "nt" and re.match(r"^/[A-Za-z]:", p):
        p = p[1:]
    return os.path.normpath(p)


def utf16_offset(text, units):
    if not isinstance(units, int) or units < 0:
        raise ValueError("Invalid UTF-16 offset")
    count = 0
    for i, char in enumerate(text):
        if count == units:
            return i
        count += 2 if ord(char) > 0xFFFF else 1
        if count > units:
            raise ValueError("Offset splits a UTF-16 surrogate pair")
    if count == units:
        return len(text)
    raise ValueError("Offset outside document")


def position(text, point):
    before = text[:point]
    return {"line": before.count("\n"), "character": len(before.rsplit("\n", 1)[-1].encode("utf-16-le")) // 2}


def point_at(text, pos):
    lines = text.splitlines(keepends=True)
    line = pos["line"]
    if line == len(lines) and pos["character"] == 0:
        return len(text)
    if line < 0 or line >= len(lines):
        if not text and line == 0 and pos["character"] == 0:
            return 0
        raise ValueError("Line outside document")
    return sum(map(len, lines[:line])) + utf16_offset(lines[line].rstrip("\r\n"), pos["character"])


def offset_edits(text, edits):
    normalized = []
    for edit in edits:
        start, end = utf16_offset(text, edit["start"]), utf16_offset(text, edit["end"])
        if end < start:
            raise ValueError("Reversed edit")
        normalized.append((start, end, edit.get("text", edit.get("newText", ""))))
    normalized.sort(key=lambda e: (e[0], e[1]))
    for left, right in zip(normalized, normalized[1:]):
        if left[1] > right[0] or left[0] == right[0]:
            raise ValueError("Overlapping edits")
    for start, end, value in reversed(normalized):
        text = text[:start] + value + text[end:]
    return text


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def parents_for(settings, root):
    file = Path(root) / ".px-toolkit/playset.json"
    try:
        playset = json.loads(file.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        playset = {}
    except (OSError, ValueError) as exc:
        raise ValueError("Cannot read playset {}: {}".format(file, exc)) from exc
    if not isinstance(playset, dict):
        raise ValueError("Playset must be a JSON object: " + str(file))
    paths = playset.get("parents", [])
    if not isinstance(paths, list) or not all(isinstance(p, str) and p.strip() for p in paths):
        raise ValueError("Playset parents must be a list of nonempty path strings: " + str(file))
    return unique_paths(settings["parentPaths"] + [expand_path(p, root) for p in paths])


def dependency_roots(settings):
    return unique_paths(settings["parentPaths"] + [
        parent for root in settings["workspaceMods"] for parent in parents_for(settings, root)])


def detect_game():
    home = Path.home()
    steam = [Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam",
             home / ".local/share/Steam", home / ".steam/steam", home / "Library/Application Support/Steam"]
    libraries = list(steam)
    for root in steam:
        try:
            content = (root / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8")
            libraries.extend(Path(p.replace("\\\\", "\\")) for p in re.findall(r'"path"\s+"([^"]+)"', content))
        except OSError:
            pass
    game = next((str(p / "steamapps/common/Crusader Kings III/game") for p in libraries
                 if (p / "steamapps/common/Crusader Kings III/game").is_dir()), None)
    userdirs = [home / "Documents", home / "OneDrive/Documents", home / ".local/share",
                home / "Library/Application Support"]
    logs = next((str(p / "Paradox Interactive/Crusader Kings III/logs") for p in userdirs
                 if (p / "Paradox Interactive/Crusader Kings III/logs").is_dir()), None)
    return game, logs
