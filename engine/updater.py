"""
Bucko self-updater.

Two update paths:
  - Content update: downloads latest core/ YAML files, hot-reloads dialogue.
                    No restart needed.
  - Engine update:  downloads a new Bucko.exe. On Windows (frozen), writes a .bat
                    that swaps the EXE after the process exits and relaunches.
                    On script mode, git-pulls or downloads source zip.

This module is intentionally free of Tkinter imports so it can run safely on a
background thread. All results are returned to the caller, who then schedules
GUI updates via root.after(0, ...).
"""

import json
import sys
import zipfile
import tempfile
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# ── Constants ──────────────────────────────────────────────────────────────────

GITHUB_OWNER = "harsiz"
GITHUB_REPO  = "Bucko"
GITHUB_API   = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
GITHUB_URL   = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
REQUEST_TIMEOUT  = 15   # seconds for API / small requests
DOWNLOAD_TIMEOUT = 120  # seconds for binary downloads
CHUNK_SIZE = 65536       # 64 KiB

# Guard: prevent two concurrent update operations
_update_in_progress: bool = False

IS_FROZEN: bool = getattr(sys, "frozen", False)


# ── Exceptions ─────────────────────────────────────────────────────────────────

class UpdateError(Exception):
    """Raised for any update-related failure."""


# ── Data ───────────────────────────────────────────────────────────────────────

@dataclass
class ReleaseInfo:
    tag: str            # e.g. "v2.1.0"
    name: str           # display name
    notes: str          # release notes (Markdown)
    release_url: str    # browser URL to release page
    exe_url: str        # download URL for Bucko.exe asset, "" if not in release
    exe_size: int       # bytes, 0 if unknown
    content_url: str    # download URL for core.zip asset, "" if not in release
    content_size: int   # bytes, 0 if unknown
    zip_url: str        # repo source zip URL (fallback content source)
    is_newer: bool      # True if tag > current running version


# ── Version comparison ─────────────────────────────────────────────────────────
# Bucko uses integer versions: v1, v2, v3, ...
# GitHub release tags are expected to be "v2", "v3", etc.

def _parse_version(v) -> int:
    """Parse "v3", "3", or 3 into integer 3. Returns 0 on failure."""
    try:
        return int(str(v).lstrip("v").strip())
    except (ValueError, AttributeError):
        return 0


def is_newer(remote_tag: str, local_version: int) -> bool:
    """Return True if remote_tag is a higher integer version than local_version."""
    return _parse_version(remote_tag) > int(local_version)


# ── Network helpers ────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = REQUEST_TIMEOUT) -> bytes:
    """Simple GET, returns response body as bytes. Raises UpdateError on failure."""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"Bucko-Updater/1.0 (github.com/{GITHUB_OWNER}/{GITHUB_REPO})",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if code == 403:
                raise UpdateError("GitHub rate limit reached — try again later")
            if code == 404:
                raise UpdateError("No releases found on GitHub")
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 403:
            raise UpdateError("GitHub rate limit reached — try again later")
        if e.code == 404:
            raise UpdateError("No releases found on this repository")
        raise UpdateError(f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise UpdateError(f"Network error: {e.reason}")
    except TimeoutError:
        raise UpdateError("Request timed out — check your internet connection")


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_release_info(current_version: int) -> ReleaseInfo:
    """
    Fetch the latest GitHub release and compare to current_version.
    Safe to call from a background thread.
    Raises UpdateError on any failure.
    """
    raw = _get(GITHUB_API)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UpdateError(f"Bad response from GitHub API: {e}")

    tag  = data.get("tag_name", "")
    name = data.get("name", tag)
    notes = (data.get("body") or "").strip()
    release_url = data.get("html_url", "")

    if not tag:
        raise UpdateError("GitHub returned a release with no tag_name")

    # Find assets
    exe_url = exe_size = ""
    content_url = content_size = ""
    exe_size = content_size = 0

    for asset in data.get("assets", []):
        aname = asset.get("name", "")
        aurl  = asset.get("browser_download_url", "")
        asize = int(asset.get("size", 0))
        if aname.lower() == "bucko.exe":
            exe_url  = aurl
            exe_size = asize
        elif aname.lower() == "core.zip":
            content_url  = aurl
            content_size = asize

    # Source zip fallback for content updates (tag is e.g. "v3")
    zip_url = f"{GITHUB_URL}/archive/refs/tags/{tag}.zip"

    return ReleaseInfo(
        tag=tag,
        name=name,
        notes=notes,
        release_url=release_url,
        exe_url=exe_url,
        exe_size=exe_size,
        content_url=content_url,
        content_size=content_size,
        zip_url=zip_url,
        is_newer=is_newer(tag, current_version),
    )


def download_file(
    url: str,
    dest: Path,
    log: Callable = print,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> None:
    """
    Stream-download url to dest.
    progress_cb(downloaded_bytes, total_bytes) called each chunk.
    Raises UpdateError on failure. Cleans up partial file on error.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": f"Bucko-Updater/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except urllib.error.URLError as e:
        dest.unlink(missing_ok=True)
        raise UpdateError(f"Download failed: {e.reason}")
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise UpdateError(f"Download error: {e}")


def apply_engine_update_frozen(
    new_exe: Path,
    current_exe: Path,
    log: Callable = print,
) -> None:
    """
    Schedule replacement of current_exe with new_exe using a .bat file,
    then return. Caller should exit the process after this (e.g. via root.after(1500, quit)).

    Windows only. No-ops with a warning on other platforms.
    """
    if sys.platform != "win32":
        log("[WARN] EXE self-update is only supported on Windows")
        return

    bat_path = current_exe.parent / "_bucko_update.bat"

    # All paths wrapped in double-quotes to handle spaces.
    # Written in ASCII/OEM so cmd.exe can read it on any Windows locale.
    bat = (
        "@echo off\n"
        "setlocal\n"
        "set ATTEMPTS=0\n"
        "\n"
        ":waitloop\n"
        f'  tasklist /FI "IMAGENAME eq {current_exe.name}" 2>NUL | find /I "{current_exe.name}" >NUL\n'
        "  if errorlevel 1 goto doreplace\n"
        "  set /a ATTEMPTS=ATTEMPTS+1\n"
        "  if %ATTEMPTS% geq 60 goto timedout\n"
        "  timeout /t 1 /nobreak >NUL\n"
        "  goto waitloop\n"
        "\n"
        ":doreplace\n"
        f'  del /f /q "{current_exe}"\n'
        f'  move /y "{new_exe}" "{current_exe}"\n'
        "  if errorlevel 1 goto failed\n"
        f'  start "" "{current_exe}"\n'
        "  goto cleanup\n"
        "\n"
        ":timedout\n"
        f'  echo Timed out waiting for {current_exe.name} to exit. Update not applied.\n'
        "  goto cleanup\n"
        "\n"
        ":failed\n"
        "  echo Failed to replace EXE. Try running as administrator.\n"
        "  goto cleanup\n"
        "\n"
        ":cleanup\n"
        '  del /f /q "%~f0"\n'
        "  exit /b 0\n"
    )

    try:
        bat_path.write_text(bat, encoding="ascii", errors="replace")
    except OSError as e:
        raise UpdateError(f"Could not write update script: {e}")

    import subprocess
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", str(bat_path)],
            creationflags=(
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW
            ),
            close_fds=True,
        )
    except Exception as e:
        bat_path.unlink(missing_ok=True)
        raise UpdateError(f"Could not launch update script: {e}")

    log("[INFO] Update script launched — Bucko will relaunch automatically after closing")


def apply_engine_update_script(repo_root: Path, log: Callable = print) -> None:
    """
    Update engine when running as a Python script (not frozen).
    Tries git pull first, falls back to source zip download.
    Does NOT restart — caller should prompt the user to restart.
    """
    import subprocess

    # Try git pull
    if (repo_root / ".git").exists():
        log("[INFO] Detected git repo — running git pull...")
        try:
            result = subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                out = result.stdout.strip() or "Already up to date."
                log(f"[INFO] git pull succeeded: {out}")
                return
            log(f"[WARN] git pull failed: {result.stderr.strip()}")
        except FileNotFoundError:
            log("[INFO] git not found in PATH")
        except subprocess.TimeoutExpired:
            log("[WARN] git pull timed out")

    # Fallback: download source zip and overwrite .py files
    log(f"[INFO] Downloading source zip from {GITHUB_URL}...")
    zip_url = f"{GITHUB_URL}/archive/refs/heads/main.zip"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            zip_dest = tmp_path / "src.zip"
            download_file(zip_url, zip_dest, log=log)

            updated = 0
            with zipfile.ZipFile(zip_dest) as zf:
                names = zf.namelist()
                # Strip single wrapper folder (repo-main/)
                folders = {n.split("/")[0] for n in names if "/" in n}
                prefix = (folders.pop() + "/") if len(folders) == 1 else ""
                for member in names:
                    if not member.endswith(".py"):
                        continue
                    rel = member[len(prefix):]
                    if not rel:
                        continue
                    dest = repo_root / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(member))
                    updated += 1

            log(f"[INFO] Source update applied: {updated} .py files updated")
            log("[INFO] Please restart Bucko to use the new version")

    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError(f"Source zip update failed: {e}")


def apply_content_update(
    zip_path: Path,
    core_dir: Path,
    log: Callable = print,
) -> int:
    """
    Extract YAML files from zip_path into core_dir.
    Only overwrites existing files — does not delete anything.
    Returns number of files updated.
    Zip may be a core.zip (flat) or a full repo zip (with core/ subfolder).
    """
    updated = 0
    try:
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()

            # Detect if this is a full repo zip (has a single wrapper folder)
            top_dirs = {n.split("/")[0] for n in names if "/" in n}
            prefix = (top_dirs.pop() + "/") if len(top_dirs) == 1 else ""

            for member in names:
                if not member.endswith(".yaml"):
                    continue
                rel = member[len(prefix):]  # e.g. "core/dialogue/base_game.yaml"

                # Only update files that live under core/
                if not rel.startswith("core/"):
                    continue
                # Strip "core/" prefix to get path relative to core_dir
                sub = rel[len("core/"):]
                if not sub:
                    continue

                dest = core_dir / sub
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))
                log(f"[INFO] Updated: core/{sub}")
                updated += 1

    except zipfile.BadZipFile as e:
        raise UpdateError(f"Downloaded file is not a valid zip: {e}")
    except Exception as e:
        raise UpdateError(f"Content update extraction failed: {e}")

    return updated


# ── Guard helper ───────────────────────────────────────────────────────────────

def acquire_update_lock() -> bool:
    """Return True and set lock if no update is running. Thread-safe enough for UI use."""
    global _update_in_progress
    if _update_in_progress:
        return False
    _update_in_progress = True
    return True


def release_update_lock() -> None:
    global _update_in_progress
    _update_in_progress = False
