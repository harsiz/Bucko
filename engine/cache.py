"""
In-memory cache for BDL dep: resolutions and config data.
Never written to disk. File watcher invalidates on changes.
"""
import time
import threading
from pathlib import Path
from typing import Any, Optional, Callable
import yaml


class ConfigCache:
    def __init__(self, log: Callable[[str], None] = print):
        self._store: dict[str, Any] = {}
        self._timestamps: dict[str, float] = {}
        self._dep_cache: dict[str, Any] = {}  # dep expression results
        self._lock = threading.Lock()
        self._watchers: dict[str, float] = {}  # path -> last mtime
        self._watched_paths: list[Path] = []
        self.log = log
        self._watch_thread: Optional[threading.Thread] = None
        self._running = False

    def load_yaml(self, path: Path, namespace: str = None) -> Any:
        """Load a YAML file, using cache if available."""
        key = str(path.resolve())
        mtime = path.stat().st_mtime if path.exists() else 0

        with self._lock:
            if key in self._store and self._timestamps.get(key, 0) >= mtime:
                return self._store[key]

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            with self._lock:
                self._store[key] = data
                self._timestamps[key] = time.time()
                self._watchers[key] = mtime
            return data
        except (yaml.YAMLError, OSError) as e:
            self.log(f"[ERROR] Cache load failed for {path}: {e}")
            return {}

    def get_dep(self, filename: str, keypath: str) -> tuple[bool, Any]:
        """Check dep cache. Returns (hit, value)."""
        key = f"{filename}|{keypath}"
        with self._lock:
            if key in self._dep_cache:
                return True, self._dep_cache[key]
        return False, None

    def set_dep(self, filename: str, keypath: str, value: Any) -> None:
        key = f"{filename}|{keypath}"
        with self._lock:
            self._dep_cache[key] = value

    def clean(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._store.clear()
            self._timestamps.clear()
            self._dep_cache.clear()
            self._watchers.clear()
        self.log("[INFO] Cache cleared")

    def start_watcher(self, paths: list[Path]) -> None:
        """Start background file watcher for cache invalidation."""
        self._watched_paths = paths
        for p in paths:
            if p.exists():
                with self._lock:
                    self._watchers[str(p.resolve())] = p.stat().st_mtime

        self._running = True
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="bucko-file-watcher"
        )
        self._watch_thread.start()

    def stop_watcher(self) -> None:
        self._running = False

    def _watch_loop(self) -> None:
        while self._running:
            time.sleep(2.0)
            for path in self._watched_paths:
                if not path.exists():
                    continue
                key = str(path.resolve())
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                with self._lock:
                    stored = self._watchers.get(key, mtime)
                if mtime != stored:
                    with self._lock:
                        self._watchers[key] = mtime
                        # Invalidate this file's cache
                        if key in self._store:
                            del self._store[key]
                        if key in self._timestamps:
                            del self._timestamps[key]
                        # Invalidate dep cache entries for this filename
                        fname = path.name
                        to_del = [k for k in self._dep_cache if k.startswith(fname)]
                        for k in to_del:
                            del self._dep_cache[k]
                    self.log(f"[CACHE] Invalidated {path.name} (file changed)")

    def warmup(self, config_files: list[Path]) -> None:
        """Pre-load all config files into cache."""
        count = 0
        for path in config_files:
            if path.exists():
                self.load_yaml(path)
                count += 1
        self.log(f"[INFO] Cache warmup complete — {count} files pre-loaded")
