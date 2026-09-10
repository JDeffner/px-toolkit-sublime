"""Pinned, verified release installation outside packed Sublime packages."""
from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .core import SERVER_VERSION

LOCK = threading.Lock()
BASE = "https://github.com/JDeffner/paradox-modding-toolkit/releases/download/v0.4.3/"
SERVER = (BASE + "px-lsp-server-0.3.4.tar.gz", "0d6d0dc37229d3a7e1e82b72abcff2d248a57ef7e0b9f327f2f5c0d70ebee7a7")
WINDOWS = (BASE + "px-lsp-win-x64-0.3.4.zip", "2f308b7de406df02aa3ed75112ce0e6ed09d616157f1c1f30e8b6443c5af422b")
TIGER_VERSION = "1.19.0"
TIGER = {
    "Windows": ("https://github.com/amtep/tiger/releases/download/v1.19.0/ck3-tiger-windows-v1.19.0.zip", "ddafd73abcff8e802b82bf3ae622d02c04dfc8a9dd0cad44b2dbf67568a10505"),
    "Linux": ("https://github.com/amtep/tiger/releases/download/v1.19.0/ck3-tiger-linux-v1.19.0.tar.gz", "6d72d276c2b2a953f63221ff8050d1276a085b5a2ffe74977675fdf6e17e9ff3"),
}


def hidden_process():
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def download(url, sha256):
    request = urllib.request.Request(url, headers={"User-Agent": "LSP-px/0.1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024:
        raise ValueError("Download exceeds 128 MiB")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError("Download checksum does not match the pinned release")
    return data


def safe_extract(data, destination, zipped=False):
    destination = Path(destination).resolve()
    total = 0

    def target(name, size):
        nonlocal total
        # Reject Windows paths too when tests run on POSIX.
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or any(":" in p for p in path.parts):
            raise ValueError("Unsafe archive path")
        total += size
        if total > 512 * 1024 * 1024:
            raise ValueError("Expanded archive exceeds 512 MiB")
        result = destination.joinpath(*path.parts)
        result.parent.mkdir(parents=True, exist_ok=True)
        return result

    if zipped:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                mode = entry.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("Archive links are not allowed")
                dest = target(entry.filename, entry.file_size)
                if entry.is_dir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    dest.write_bytes(archive.read(entry))
                    if mode & 0o111:
                        dest.chmod(0o755)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            for entry in archive:
                if not entry.isdir() and not entry.isfile():
                    raise ValueError("Archive links/devices are not allowed")
                dest = target(entry.name, entry.size)
                if entry.isdir():
                    dest.mkdir(parents=True, exist_ok=True)
                else:
                    with archive.extractfile(entry) as source, dest.open("wb") as out:
                        shutil.copyfileobj(source, out)
                    dest.chmod(entry.mode & 0o777)


def node_path(override=None):
    candidates = [override, shutil.which("node"), "/opt/homebrew/bin/node", "/usr/local/bin/node", "/usr/bin/node",
                  os.path.join(os.environ.get("PROGRAMFILES", "C:/Program Files"), "nodejs", "node.exe")]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            version = subprocess.check_output([candidate, "--version"], timeout=10, **hidden_process()).decode().strip()
            if int(version.lstrip("v").split(".")[0]) < 18:
                raise ValueError("px-lsp requires Node.js 18 or newer")
            return candidate
    return None


def install_release(storage, name, artifact, expected):
    destination = Path(storage) / name
    with LOCK:
        marker = destination / "installed.json"
        if marker.is_file():
            saved = json.loads(marker.read_text(encoding="utf-8"))
            entry = destination / saved["entry"]
            if entry.is_file() and saved.get("sha256") == artifact[1]:
                return entry
        Path(storage).mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".install-", dir=str(storage)))
        try:
            safe_extract(download(*artifact), staging, artifact[0].endswith(".zip"))
            matches = list(staging.rglob(expected))
            if len(matches) != 1:
                raise ValueError("Release does not contain exactly one " + expected)
            rel = matches[0].relative_to(staging)
            (staging / "installed.json").write_text(json.dumps({"entry": str(rel), "sha256": artifact[1]}), encoding="utf-8")
            # Never erase a previously working installation on a failed update.
            if destination.exists():
                raise ValueError("Incomplete installation at {}. Close Sublime, move that directory aside, then restart to download a fresh copy.".format(destination))
            os.replace(str(staging), str(destination))
            return destination / rel
        finally:
            if staging.exists():
                shutil.rmtree(str(staging))


def server_command(storage, options):
    command = options.get("server_command")
    if command:
        if not isinstance(command, list) or not all(isinstance(p, str) for p in command):
            raise ValueError("server_command must be an argument array")
        return command
    node = node_path(options.get("node_path"))
    if not node and platform.system() == "Windows" and platform.machine().lower() in ("amd64", "x86_64"):
        script = install_release(storage, "server-" + SERVER_VERSION + "-win", WINDOWS, "server.js")
        node = str(script.parent.parent / "node.exe")
    elif node:
        script = install_release(storage, "server-" + SERVER_VERSION, SERVER, "server.js")
    else:
        raise ValueError("Install Node.js (https://nodejs.org), or set node_path / server_command in LSP-px Settings")
    heap = options.get("heap_mb")
    if heap is None:
        # Ask the already validated runtime for physical RAM on all platforms.
        total = int(subprocess.check_output([node, "-p", "require('os').totalmem()"], timeout=10, **hidden_process()))
        heap = max(2048, min(4096, total // 1024 // 1024 // 2))
    if not isinstance(heap, int) or not 512 <= heap <= 32768:
        raise ValueError("heap_mb must be between 512 and 32768")
    return [node, "--max-old-space-size=" + str(heap), str(script), "--stdio"]


def install_tiger(storage):
    system = platform.system()
    if system not in TIGER or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("No pinned Tiger binary for this platform. Build/install ck3-tiger and set tiger_path.")
    return str(install_release(storage, "tiger-" + TIGER_VERSION, TIGER[system],
                               "ck3-tiger.exe" if system == "Windows" else "ck3-tiger"))
