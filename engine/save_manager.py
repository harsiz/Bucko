"""
Save manager — handles player.dat with SHA-256 integrity checking.
All data stored locally, never transmitted.
"""
import json
import hashlib
import time
import os
from pathlib import Path
from typing import Any


SAVES_DIR = Path("saves")
SAVE_FILE = SAVES_DIR / "player.dat"


def _hash_data(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_save() -> tuple[dict, bool]:
    """
    Returns (save_data, tampered).
    tampered=True means hash mismatch was detected.
    """
    SAVES_DIR.mkdir(exist_ok=True)

    if not SAVE_FILE.exists():
        return _default_save(), False

    try:
        raw = SAVE_FILE.read_text(encoding="utf-8")
        envelope = json.loads(raw)
        stored_hash = envelope.get("_hash", "")
        data = envelope.get("data", {})
        expected_hash = _hash_data(data)
        tampered = stored_hash != expected_hash
        return data, tampered
    except (json.JSONDecodeError, KeyError, OSError):
        return _default_save(), True


def write_save(data: dict) -> None:
    SAVES_DIR.mkdir(exist_ok=True)
    # Hash individual memory write entries
    if "memory" in data:
        for ns, entries in data["memory"].items():
            if isinstance(entries, dict):
                for key, val in entries.items():
                    if not isinstance(val, dict) or "_ts" not in val:
                        ts = time.time()
                        raw_val = val if not isinstance(val, dict) else val.get("value")
                        entry = {"value": raw_val, "_ts": ts}
                        entry["_hash"] = hashlib.sha256(
                            json.dumps({"key": key, "value": raw_val, "ts": ts},
                                       sort_keys=True).encode()
                        ).hexdigest()
                        entries[key] = entry

    envelope = {
        "data": data,
        "_hash": _hash_data(data)
    }
    SAVE_FILE.write_text(
        json.dumps(envelope, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _default_save() -> dict:
    return {
        "meta": {
            "first_launch": True,
            "first_session_date": None,
            "client_version": 1,
        },
        "user": {
            "name": "",
        },
        "memory": {
            "global": {},
            "user": {},
            "repeat": {},
            "mod": {},
        },
        "flags": {},
        "counters": {},
        "affection": 0,
        "interests": {},
        "mood_state": {
            "energy": 70,
            "patience": 80,
            "chaos": 40,
            "warmth": 75,
        },
        "affection_history": [],  # last 5 deltas
        "cycle_state": {},  # choice.cycle state per dialogue id
    }


def verify_memory_entry(entry: dict) -> bool:
    """Check if a memory entry's hash is valid."""
    if not isinstance(entry, dict) or "_hash" not in entry:
        return True  # old format, skip
    stored = entry["_hash"]
    expected = hashlib.sha256(
        json.dumps({
            "key": entry.get("_key", ""),
            "value": entry.get("value"),
            "ts": entry.get("_ts", 0)
        }, sort_keys=True).encode()
    ).hexdigest()
    return stored == expected
