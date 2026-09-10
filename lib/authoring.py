"""Loss-aware localization/descriptor writers and validation."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .core import under

KEY = re.compile(r"^[A-Za-z0-9_.-]+$")
LOC_ENTRY = re.compile(r'^(\s*)([A-Za-z0-9_.-]+)(\s*:\s*\d*\s*)"((?:\\.|[^"\\])*)"(.*)$')


def quote(value):
    return json.dumps(value, ensure_ascii=False)


def validate_loc_target(file, root, language):
    if not under(file, root) or not under(file, os.path.join(root, "localization")):
        raise ValueError("Localization must be written inside the editable mod's localization folder")
    if not os.path.basename(file).endswith("_l_" + language + ".yml"):
        raise ValueError("Localization filename does not match the selected language")


def upsert_localization(text, key, value, language):
    if not KEY.fullmatch(key):
        raise ValueError("Invalid localization key")
    if not re.fullmatch(r"[a-z_]+", language):
        raise ValueError("Invalid language")
    eol = "\r\n" if "\r\n" in text else "\n"
    text = text.lstrip("\ufeff")
    header = re.search(r"^\s*l_([a-z_]+):\s*(?:#.*)?$", text, re.M)
    if text.strip() and (not header or header.group(1) != language):
        raise ValueError("Existing localization header does not match the selected language")
    if not text.strip():
        text = "l_" + language + ":" + eol
    lines = text.splitlines(keepends=True)
    sites = []
    for i, line in enumerate(lines):
        match = LOC_ENTRY.match(line.rstrip("\r\n"))
        if match and match.group(2) == key:
            sites.append((i, match))
        elif re.match(r"^\s*" + re.escape(key) + r"\s*:", line):
            raise ValueError("The existing entry for " + key + " is malformed; fix it before editing")
    if len(sites) > 1:
        raise ValueError("This file contains duplicate entries for " + key + "; resolve them before editing")
    if sites:
        i, match = sites[0]
        ending = "\r\n" if lines[i].endswith("\r\n") else "\n" if lines[i].endswith("\n") else ""
        lines[i] = match.group(1) + key + match.group(3) + quote(value) + match.group(5) + ending
        return "".join(lines)
    if text and not text.endswith("\n"):
        text += eol
    return text + " " + key + ":0 " + quote(value) + eol


def localization_target(root, language, key, entries, read_text=None):
    """Prefer a mod definition, then siblings, otherwise a new ordinary file.

    The caller presents choices when the index contains multiple editable sites.
    A key inherited from vanilla/parents is intentionally placed in replace/.
    """
    candidates = [e["file"] for e in entries if e.get("source") == "mod" and under(e["file"], root)
                  and e["file"].endswith("_l_" + language + ".yml")]
    if candidates:
        return candidates[0]
    loc = Path(root) / "localization"
    if any(not under(e.get("file"), root) for e in entries):
        return str(loc / "replace" / ("000_px_sublime_overrides_l_" + language + ".yml"))
    prefix = re.split(r"[._]", key)[0]
    best = None
    score = 0
    if prefix and loc.is_dir():
        for file in sorted(loc.rglob("*_l_" + language + ".yml")):
            if "replace" in file.relative_to(loc).parts or not under(str(file), root):
                continue
            try:
                text = read_text(str(file)) if read_text else file.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            if re.search(r"^\s*" + re.escape(key) + r"\s*:", text, re.M):
                return str(file)
            count = len(re.findall(r"^\s*" + re.escape(prefix) + r"[._][\w.-]*\s*:", text, re.M))
            if count > score:
                score, best = count, str(file)
    return best or str(loc / language / ("px_sublime_l_" + language + ".yml"))


def descriptor_entries(text):
    """Tokenize braces/strings/comments so # and braces inside names stay data."""
    token = re.compile(r'#[^\r\n]*|"(?:\\.|[^"\\])*"|[{}=]|[A-Za-z_][A-Za-z0-9_]*|[^\s{}=]+')
    depth = 0
    tokens = list(token.finditer(text.lstrip("\ufeff")))
    result = []
    for i, item in enumerate(tokens):
        word = item.group()
        if word.startswith("#") or word.startswith('"'):
            continue
        if word == "{":
            depth += 1
        elif word == "}":
            depth = max(0, depth - 1)
        elif depth == 0 and i + 1 < len(tokens) and tokens[i + 1].group() == "=":
            before = text.lstrip("\ufeff")[:item.start()]
            result.append({"key": word, "line": before.count("\n"),
                           "startCol": len(before.rsplit("\n", 1)[-1]), "endCol": len(before.rsplit("\n", 1)[-1]) + len(word)})
    return result


def descriptor_issues(text, fields, inner=True):
    known = {f["key"]: f for f in fields}
    seen, issues = set(), []
    for entry in descriptor_entries(text):
        key = entry["key"]
        field = known.get(key)
        code = message = None
        if not field:
            code, message = "descriptor-unknown-key", "Unknown launcher descriptor field: " + key
        elif key in seen and not field["repeatable"]:
            code, message = "descriptor-duplicate-key", "Duplicate field: " + key
        elif inner and field["outerOnly"]:
            code, message = "descriptor-path-ignored", key + " belongs in the outer launcher .mod file"
        seen.add(key)
        if code:
            issues.append(dict(entry, code=code, severity="warning", message=message))
    for key, field in known.items():
        if field["required"] and key not in seen:
            issues.append({"line": 0, "startCol": 0, "endCol": 0, "code": "descriptor-missing-field",
                           "severity": "warning" if key == "supported_version" else "error", "message": "Missing required descriptor field: " + key})
    return issues


def scaffold_descriptor(name, version):
    if any(c in name + version for c in '\r\n"'):
        raise ValueError("Descriptor values cannot contain quotes or newlines")
    return 'version="0.1.0"\ntags={\n\t"Gameplay"\n}\nname="' + name + '"\nsupported_version="' + version + '"\n'


def new_mod(parent, folder, name, version):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", folder):
        raise ValueError("Use letters, digits, underscores and hyphens for the folder name")
    text = scaffold_descriptor(name, version)
    root = Path(parent) / folder
    root.mkdir(parents=True, exist_ok=False)
    (root / "descriptor.mod").write_text(text, encoding="utf-8-sig")
    for path in ("common", "events", "localization/english", ".px-toolkit"):
        (root / path).mkdir(parents=True, exist_ok=True)
    (root / (folder + ".sublime-project")).write_text(json.dumps({"folders": [{"path": "."}]}, indent=2) + "\n", encoding="utf-8")
    return str(root)
