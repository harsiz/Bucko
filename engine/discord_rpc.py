"""
Discord Rich Presence — optional, fails silently if Discord is not running.
Uses pypresence if available, otherwise no-ops.

Setup instructions (if you see 'Client ID is Invalid'):
  1. Go to https://discord.com/developers/applications
  2. Click "New Application" and give it any name (e.g. "Bucko")
  3. Copy the "Application ID" from the General Information page
  4. Open client_config.yaml and set:
       discord_rpc:
         app_id: "YOUR_APPLICATION_ID_HERE"
  5. Restart Bucko — RPC will connect automatically.
"""
import time
from typing import Optional

# Known Discord error codes
_INVALID_CLIENT_ID_CODE = 4000


class DiscordRPC:
    def __init__(self, app_id: str, log=print):
        self.app_id = app_id.strip()
        self.log = log
        self._rpc = None
        self._enabled = False
        self._connected = False
        self._session_start = time.time()
        self._last_error: str = ""

    def _is_placeholder_id(self) -> bool:
        """Detect obviously invalid / placeholder app IDs."""
        bad = {"0", "1234567890123456789", "YOUR_APPLICATION_ID_HERE", ""}
        return self.app_id in bad or len(self.app_id) < 17

    def connect(self) -> bool:
        """Attempt to connect. Returns True if successful."""
        if self._is_placeholder_id():
            self.log(
                "[WARN] Discord RPC: app_id is not configured.\n"
                "       To enable Rich Presence:\n"
                "         1. Visit https://discord.com/developers/applications\n"
                "         2. Create a New Application (name it 'Bucko' or anything)\n"
                "         3. Copy the Application ID from General Information\n"
                "         4. Paste it into client_config.yaml under discord_rpc.app_id\n"
                "         5. Restart Bucko"
            )
            return False

        try:
            from pypresence import Presence
            rpc = Presence(self.app_id)
            rpc.connect()
            self._rpc = rpc
            self._enabled = True
            self._connected = True
            self._last_error = ""
            self.log("[INFO] Discord RPC connected successfully")
            return True

        except ImportError:
            self.log("[INFO] Discord RPC: pypresence not installed (pip install pypresence)")
            return False

        except Exception as e:
            err_str = str(e)
            self._last_error = err_str

            # Error Code 4000 = invalid / unrecognised Application ID
            if "4000" in err_str or "Client ID" in err_str or "invalid" in err_str.lower():
                self.log(
                    f"[WARN] Discord RPC: Invalid Application ID ({self.app_id!r}).\n"
                    "       The app_id in client_config.yaml doesn't match any Discord application.\n"
                    "       To fix:\n"
                    "         1. Visit https://discord.com/developers/applications\n"
                    "         2. Create or select your application\n"
                    "         3. Copy the Application ID (NOT the Client Secret)\n"
                    "         4. Update discord_rpc.app_id in client_config.yaml\n"
                    "         5. Run 'discord.reconnect' in the console or restart Bucko"
                )
            elif "Cannot connect" in err_str or "FileNotFoundError" in err_str or "No such file" in err_str:
                self.log("[INFO] Discord RPC: Discord is not running — RPC disabled until restart")
            elif "ConnectionRefused" in err_str or "WinError" in err_str:
                self.log("[INFO] Discord RPC: Could not reach Discord client — make sure Discord is open")
            else:
                self.log(f"[INFO] Discord RPC unavailable: {e}")

            return False

    def reconnect(self) -> bool:
        """Disconnect and attempt a fresh reconnect. Useful after config change."""
        self.disconnect()
        self._enabled = False
        self._connected = False
        return self.connect()

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
        except Exception as e:
            # Silently drop — Discord may have been closed mid-session
            self._enabled = False
            self._last_error = str(e)

    def status(self) -> str:
        """Return a human-readable status string for the console."""
        if self._connected and self._enabled:
            return f"Connected (app_id={self.app_id})"
        elif self._last_error:
            return f"Disconnected — last error: {self._last_error}"
        else:
            return "Disconnected (never connected or disabled)"

    def disconnect(self) -> None:
        if self._rpc:
            try:
                self._rpc.close()
            except Exception:
                pass
            self._rpc = None
        self._enabled = False
        self._connected = False
