"""
Mod manager — loads, validates, and manages mods from the mods/ directory.
"""
import re
import hashlib
import time
from pathlib import Path
from typing import Optional, Callable
import yaml


MOD_ID_RE = re.compile(r"^[a-z0-9_]+$")


class ModInfo:
    def __init__(self, mod_dir: Path, meta: dict, file_hash: str):
        self.dir = mod_dir
        self.name: str = meta.get("name", mod_dir.name)
        self.id: str = meta.get("id", "")
        self.mod_version: int = int(meta.get("mod_version", 0))
        self.version_support: list[int] = [int(v) for v in meta.get("version_support", [])]
        self.description: str = meta.get("description", "")
        self.author: str = meta.get("author", "")
        self.console_commands: list[dict] = meta.get("console_commands", [])
        self.file_hash: str = file_hash
        self.enabled: bool = True
        self.loaded: bool = False

    def supports_client_version(self, version: int) -> bool:
        return version in self.version_support

    def __repr__(self) -> str:
        return f"<Mod {self.id} v{self.mod_version}>"


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


class ModManager:
    def __init__(
        self,
        mods_dir: Path,
        client_version: int,
        log: Callable[[str], None],
    ):
        self.mods_dir = mods_dir
        self.client_version = client_version
        self.log = log
        self._mods: dict[str, ModInfo] = {}
        self._hash_cache: dict[str, str] = {}  # mod_id -> stored hash at load time

    def load_all(self) -> list[ModInfo]:
        """Discover and load all mods. Returns loaded mods in order."""
        self.mods_dir.mkdir(exist_ok=True)
        loaded = []

        mod_dirs = sorted(
            [d for d in self.mods_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name
        )

        for mod_dir in mod_dirs:
            mod_yaml = mod_dir / "mod.yaml"
            if not mod_yaml.exists():
                self.log(f"[WARN] {mod_dir.name} has no mod.yaml — skipped")
                continue

            mod = self._load_mod(mod_dir, mod_yaml)
            if mod:
                loaded.append(mod)

        return loaded

    def _load_mod(self, mod_dir: Path, mod_yaml: Path) -> Optional[ModInfo]:
        try:
            raw = yaml.safe_load(mod_yaml.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            self.log(f"[ERROR] Failed to read {mod_yaml}: {e}")
            return None

        # Validate ID
        mod_id = raw.get("id", "")
        if not mod_id or not MOD_ID_RE.match(mod_id):
            self.log(f"[ERROR] Mod '{mod_dir.name}' has invalid id '{mod_id}' — spaces/special chars not allowed")
            return None

        if mod_id in self._mods:
            self.log(f"[ERROR] Duplicate mod id '{mod_id}' from {mod_dir.name} — skipped")
            return None

        # Hash verification
        current_hash = _hash_file(mod_yaml)
        stored_hash = self._hash_cache.get(mod_id, current_hash)
        if stored_hash != current_hash and mod_id in self._hash_cache:
            self.log(f"⚠️  [{mod_id}] mod.yaml hash mismatch — file may have changed")
        self._hash_cache[mod_id] = current_hash

        mod = ModInfo(mod_dir, raw, current_hash)
        mod.loaded = True

        # Version support check
        if not mod.supports_client_version(self.client_version):
            self.log(
                f"⚠️  {mod.name} (v{mod.mod_version}) does not explicitly support client v{self.client_version}"
            )

        self._mods[mod_id] = mod
        self.log(f"[INFO] Loaded mod: {mod.name} (v{mod.mod_version})")
        return mod

    def get(self, mod_id: str) -> Optional[ModInfo]:
        return self._mods.get(mod_id)

    def list_all(self) -> list[ModInfo]:
        return list(self._mods.values())

    def get_dialogue_dirs(self) -> list[tuple[Path, str]]:
        """Returns (dir, namespace) pairs for all loaded enabled mods."""
        result = []
        for mod in self._mods.values():
            if mod.enabled and mod.loaded:
                result.append((mod.dir, mod.id))
        return result

    def reload_mod(self, mod_id: str, dialogue_manager) -> bool:
        """Reload a single mod's dialogue files."""
        mod = self._mods.get(mod_id)
        if not mod:
            return False
        count = 0
        for yaml_file in sorted(mod.dir.glob("*.yaml")):
            if yaml_file.name == "mod.yaml":
                continue
            count += dialogue_manager.load_yaml(yaml_file, mod.id)
        return True

    def clean_mod_data(self, mod_id: str, state) -> None:
        """Clear cached/orphaned data for a mod (mod.[mod_id].clean)."""
        mod_memory = state.memory.get("mod", {})
        if mod_id in mod_memory:
            mod_memory[mod_id] = {}
        state.console_log(f"[INFO] Cleaned data for mod: {mod_id}")

    def register_console_commands(self, mod: ModInfo) -> dict[str, dict]:
        """Return a dict of registered console commands for this mod."""
        cmds = {}
        for cmd in mod.console_commands:
            name = cmd.get("name", "")
            if name:
                full_cmd = f"mod.{mod.id}.{name}"
                cmds[full_cmd] = cmd
        return cmds

    # ------------------------------------------------------------------ #
    #  Installation
    # ------------------------------------------------------------------ #

    def install_mod(self, source: str, dialogue_manager) -> tuple[bool, str]:
        """
        Install a mod from a URL or local path.
        Supports:
          - https://github.com/user/repo   (git clone, then zip fallback)
          - https://github.com/user/repo.git
          - git@github.com:user/repo.git   (SSH clone)
          - /path/to/mod_folder            (local copy)
        Returns (success, message).
        """
        source = source.strip().rstrip("/")
        if source.startswith(("http://", "https://", "git@")):
            return self._install_from_url(source, dialogue_manager)
        else:
            return self._install_from_local(source, dialogue_manager)

    # -- URL install ---------------------------------------------------

    def _install_from_url(self, url: str, dialogue_manager) -> tuple[bool, str]:
        import shutil

        # Derive a folder name from the URL
        clean = url.removesuffix(".git").rstrip("/")
        folder_name = clean.split("/")[-1].replace(".", "_")
        target_dir = self.mods_dir / folder_name

        if target_dir.exists():
            return False, f"[ERROR] '{folder_name}' already exists in mods/ — remove it first"

        # 1. Try git clone (shallow, fast)
        if self._try_git_clone(url, target_dir):
            return self._finalise_install(target_dir, dialogue_manager)

        # 2. Fall back to GitHub zip download
        if "github.com" in url:
            self.log("[INFO] git not available or failed — trying GitHub zip download...")
            ok, msg = self._install_from_github_zip(clean, target_dir, dialogue_manager)
            if ok:
                return ok, msg

        # Clean up partial folder if anything was left behind
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, f"[ERROR] Could not install from: {url}\n  Make sure git is installed or the URL points to a valid GitHub repo"

    def _try_git_clone(self, url: str, target_dir: Path) -> bool:
        """Attempt a shallow git clone. Returns True on success."""
        import subprocess, shutil
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", url, str(target_dir)],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                self.log(f"[INFO] git clone succeeded")
                return True
            # Clone failed — clean up and report
            self.log(f"[INFO] git clone failed: {result.stderr.strip() or result.stdout.strip()}")
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
        except FileNotFoundError:
            self.log("[INFO] git executable not found")
        except subprocess.TimeoutExpired:
            self.log("[INFO] git clone timed out after 60s")
            if target_dir.exists():
                import shutil as _s; _s.rmtree(target_dir, ignore_errors=True)
        return False

    def _install_from_github_zip(
        self, clean_url: str, target_dir: Path, dialogue_manager
    ) -> tuple[bool, str]:
        """Download a GitHub repo as a zip and extract to mods/."""
        import urllib.request, urllib.error, zipfile, tempfile, shutil

        for branch in ("main", "master"):
            zip_url = f"{clean_url}/archive/refs/heads/{branch}.zip"
            self.log(f"[INFO] Trying {zip_url} ...")
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp = Path(tmpdir)
                    zip_path = tmp / "mod.zip"

                    try:
                        urllib.request.urlretrieve(zip_url, str(zip_path))
                    except urllib.error.HTTPError as e:
                        self.log(f"[INFO] HTTP {e.code} — skipping {branch} branch")
                        continue

                    # Extract
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(tmpdir)

                    # Find the extracted folder (repo-branch/ or similar)
                    dirs = [d for d in tmp.iterdir() if d.is_dir() and d.name != "__MACOSX"]
                    if not dirs:
                        self.log(f"[INFO] No folder found in zip for {branch} branch")
                        continue

                    shutil.copytree(str(dirs[0]), str(target_dir))
                    return self._finalise_install(target_dir, dialogue_manager)

            except Exception as e:
                self.log(f"[INFO] Zip download error ({branch}): {e}")
                continue

        return False, f"[ERROR] GitHub zip download failed for both main/master branches"

    # -- Local install -------------------------------------------------

    def _install_from_local(self, source: str, dialogue_manager) -> tuple[bool, str]:
        import shutil
        src = Path(source)
        if not src.exists():
            return False, f"[ERROR] Path does not exist: {source}"
        if not src.is_dir():
            return False, f"[ERROR] Not a directory: {source}"

        target_dir = self.mods_dir / src.name
        if target_dir.exists():
            return False, f"[ERROR] '{src.name}' already exists in mods/ — remove it first"

        self.log(f"[INFO] Copying {src} → {target_dir} ...")
        shutil.copytree(str(src), str(target_dir))
        return self._finalise_install(target_dir, dialogue_manager)

    # -- Finalise ------------------------------------------------------

    def _finalise_install(self, mod_dir: Path, dialogue_manager) -> tuple[bool, str]:
        """Validate the installed folder, register the mod, load its dialogue."""
        import shutil

        mod_yaml = mod_dir / "mod.yaml"
        if not mod_yaml.exists():
            shutil.rmtree(mod_dir, ignore_errors=True)
            return False, (
                f"[ERROR] No mod.yaml in '{mod_dir.name}' — this doesn't look like a Bucko mod\n"
                f"  Removed the folder."
            )

        mod = self._load_mod(mod_dir, mod_yaml)
        if not mod:
            shutil.rmtree(mod_dir, ignore_errors=True)
            return False, f"[ERROR] mod.yaml in '{mod_dir.name}' is invalid — see log for details. Removed."

        # Load dialogue files into the live dialogue manager
        block_count = 0
        for yaml_file in sorted(mod_dir.glob("*.yaml")):
            if yaml_file.name == "mod.yaml":
                continue
            block_count += dialogue_manager.load_yaml(yaml_file, mod.id)

        return True, (
            f"[OK] Installed '{mod.name}' by {mod.author}\n"
            f"     id: {mod.id}  |  mod v{mod.mod_version}  |  {block_count} dialogue blocks loaded\n"
            f"     No restart needed — mod is active now"
        )
