"""
Discord Rich Presence — optional, fails silently if Discord is not running.
Uses pypresence if available, otherwise no-ops.
"""
import time
import threading
from typing import Optional


class DiscordRPC:
    def __init__(self, app_id: str, log=print):
        self.app_id = app_id
        self.log = log
        self._rpc = None
        self._enabled = False
        self._session_start = time.time()

    def connect(self) -> bool:
        """Attempt to connect. Returns True if successful."""
        try:
            from pypresence import Presence, exceptions
            rpc = Presence(self.app_id)
            rpc.connect()
            self._rpc = rpc
            self._enabled = True
            self.log("[INFO] Discord RPC connected")
            return True
        except ImportError:
            self.log("[INFO] pypresence not installed — Discord RPC disabled")
            return False
        except Exception as e:
            self.log(f"[INFO] Discord RPC unavailable: {e}")
            return False

    def update(self, session_count: int = 0) -> None:
        if not self._enabled or not self._rpc:
            return
        try:
            self._rpc.update(
                state="Chatting with Bucko",
                details=f"Session #{session_count}",
                start=int(self._session_start),
                large_image="bucko",
                large_text="Bucko",
            )
        except Exception:
            # Silently fail — Discord may have closed
            self._enabled = False

    def disconnect(self) -> None:
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
        self._enabled = False
