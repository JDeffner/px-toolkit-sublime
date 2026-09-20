"""Verified release installation outside packed Sublime packages."""
from __future__ import annotations

import hashlib
import http.client
import io
import json
import logging
import os
import platform
import re
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

LOCK = threading.RLock()
RELEASES = "https://api.github.com/repos/JDeffner/paradox-modding-toolkit/releases/latest"
RELEASE_HISTORY = "https://api.github.com/repos/JDeffner/paradox-modding-toolkit/releases"
DOWNLOADS = "https://github.com/JDeffner/paradox-modding-toolkit/releases/download/"
RELEASE_ERRORS = (OSError, ValueError, EOFError, http.client.HTTPException, tarfile.TarError, zipfile.BadZipFile)
# Bootstrap release for a first install when release discovery is unavailable.
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
        raise ValueError("Download checksum does not match the release")
    return data


def version_tuple(version):
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid stable server version")
    return tuple(int(part) for part in version.split("."))


def release_metadata(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "LSP-px/0.1.0", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=5) as response:
        data = response.read(2 * 1024 * 1024 + 1)
    if len(data) > 2 * 1024 * 1024:
        raise ValueError("Release metadata exceeds 2 MiB")
    return json.loads(data)


def server_assets(release, bundled_node=False):
    if (not isinstance(release, dict) or release.get("draft") is not False
            or release.get("prerelease") is not False or not isinstance(release.get("assets"), list)):
        raise ValueError("Expected a stable upstream release")
    pattern = (r"px-lsp-win-x64-(\d+\.\d+\.\d+)\.zip" if bundled_node
               else r"px-lsp-server-(\d+\.\d+\.\d+)\.tar\.gz")
    candidates = []
    for asset in release["assets"]:
        if not isinstance(asset, dict) or not isinstance(asset.get("name"), str):
            continue
        match = re.fullmatch(pattern, asset["name"])
        if match and version_tuple(match[1]) >= version_tuple(SERVER_VERSION):
            candidates.append((version_tuple(match[1]), match[1], asset))
    return candidates


def server_artifact(asset):
    digest, url = asset.get("digest"), asset.get("browser_download_url")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("Server archive has no SHA-256 digest")
    if (asset.get("state") != "uploaded" or not isinstance(url, str)
            or not re.fullmatch(re.escape(DOWNLOADS) + r"[^/?#]+/" + re.escape(asset["name"]), url)):
        raise ValueError("Server archive is not an uploaded upstream release asset")
    return url, digest[7:].lower()


def latest_server(bundled_node=False):
    candidates = server_assets(release_metadata(RELEASES), bundled_node)
    if not candidates:
        raise ValueError("Latest release has no supported stable server archive")
    _, version, asset = max(candidates, key=lambda item: item[0])
    return version, server_artifact(asset)


def released_servers(bundled_node=False):
    """List supported stable servers, including older pages of release history."""
    versions = {}
    page = 1
    while True:
        releases = release_metadata(RELEASE_HISTORY + "?per_page=100&page=" + str(page))
        if not isinstance(releases, list):
            raise ValueError("Expected upstream release history")
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
                continue
            for _, version, asset in server_assets(release, bundled_node):
                try:
                    artifact = server_artifact(asset)
                except ValueError:
                    continue
                # Several toolkit releases can ship the same LSP version.
                versions.setdefault(version, artifact)
        if len(releases) < 100:
            return versions
        page += 1


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


def installed_entry(destination, expected, sha256=None, bundled_node=False):
    """Read an installation marker without trusting paths outside its directory."""
    try:
        saved = json.loads((destination / "installed.json").read_text(encoding="utf-8"))
        if not isinstance(saved, dict) or not isinstance(saved.get("entry"), str):
            return None
        digest = saved.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return None
        if sha256 is not None and digest != sha256:
            return None
        entry = (destination / saved["entry"]).resolve()
        entry.relative_to(destination.resolve())
        if entry.name != expected or not entry.is_file():
            return None
        if bundled_node:
            node = entry.parent.parent / "node.exe"
            node.resolve().relative_to(destination.resolve())
            if not node.is_file():
                return None
        return entry
    except (OSError, ValueError):
        return None


def install_release(storage, name, artifact, expected, bundled_node=False):
    destination = Path(storage) / name
    with LOCK:
        entry = installed_entry(destination, expected, artifact[1], bundled_node)
        if entry:
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
            if not installed_entry(staging, expected, artifact[1], bundled_node):
                raise ValueError("Release is missing the expected executable or bundled Node runtime")
            # Never erase a previously working installation on a failed update.
            if destination.exists():
                raise ValueError("Incomplete installation at {}. Close Sublime, move that directory aside, then restart to download a fresh copy.".format(destination))
            os.replace(str(staging), str(destination))
            return destination / rel
        finally:
            if staging.exists():
                shutil.rmtree(str(staging))


def cached_servers(storage, bundled_node=False):
    pattern = r"server-(\d+\.\d+\.\d+)" + ("-win" if bundled_node else "")
    cached = {}
    for directory in Path(storage).glob("server-*"):
        match = re.fullmatch(pattern, directory.name)
        if match and version_tuple(match[1]) >= version_tuple(SERVER_VERSION):
            entry = installed_entry(directory, "server.js", bundled_node=bundled_node)
            if entry:
                cached[match[1]] = entry
    return cached


def managed_server(storage, bundled_node=False, auto_update=True, version=None):
    """Select the newest verified installation, updating only between sessions."""
    if not isinstance(auto_update, bool):
        raise ValueError("auto_update_server must be true or false")
    if version is not None and version_tuple(version) < version_tuple(SERVER_VERSION):
        raise ValueError("This package requires px-lsp " + SERVER_VERSION + " or newer")
    suffix = "-win" if bundled_node else ""
    with LOCK:
        cached = cached_servers(storage, bundled_node)
        if version is not None:
            if version in cached:
                return cached[version]
            artifact = ((WINDOWS if bundled_node else SERVER) if version == SERVER_VERSION
                        else released_servers(bundled_node).get(version))
            if artifact is None:
                raise ValueError("No verified stable px-lsp " + version + " release is available")
            return install_release(storage, "server-" + version + suffix, artifact, "server.js", bundled_node)
        current = max(cached, key=version_tuple) if cached else None
        if auto_update:
            try:
                version, artifact = latest_server(bundled_node)
                if current is None or version_tuple(version) > version_tuple(current):
                    return install_release(storage, "server-" + version + suffix, artifact,
                                           "server.js", bundled_node)
            except RELEASE_ERRORS as exc:
                logging.getLogger(__name__).warning(
                    "LSP-px: server update failed; using %s: %s",
                    "cached server" if current else "bootstrap release", exc)
        if current:
            return cached[current]
        return install_release(storage, "server-" + SERVER_VERSION + suffix,
                               WINDOWS if bundled_node else SERVER, "server.js", bundled_node)


def server_runtime(options):
    """Return installed Node, or None when the Windows bundle is needed."""
    node = node_path(options.get("node_path"))
    if not node and not (platform.system() == "Windows" and platform.machine().lower() in ("amd64", "x86_64")):
        raise ValueError("Install Node.js (https://nodejs.org), or set node_path / server_command in LSP-px Settings")
    return node


def server_command(storage, options):
    command = options.get("server_command")
    if command:
        if not isinstance(command, list) or not all(isinstance(p, str) for p in command):
            raise ValueError("server_command must be an argument array")
        return command
    node = server_runtime(options)
    script = managed_server(storage, bundled_node=node is None,
                            auto_update=options.get("auto_update_server", True), version=options.get("server_version"))
    if node is None:
        node = str(script.parent.parent / "node.exe")
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
