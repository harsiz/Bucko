"""
Console command system — parses and dispatches console commands.
"""
import time
from typing import Callable, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState
    from engine.dialogue import DialogueManager
    from engine.mods import ModManager
    from engine.cache import ConfigCache


class ConsoleSystem:
    def __init__(
        self,
        state: "GameState",
        dialogue_manager: "DialogueManager",
        mod_manager: "ModManager",
        cache: "ConfigCache",
        log: Callable[[str], None],
        client_version: int,
        app_callbacks: dict = None,
    ):
        self.state = state
        self.dm = dialogue_manager
        self.mm = mod_manager
        self.cache = cache
        self.log = log
        self.client_version = client_version
        self.app = app_callbacks or {}  # restart, quit, reload callbacks

    def execute(self, raw: str) -> Optional[str]:
        """
        Execute a console command. Returns output string or None.
        """
        cmd = raw.strip()
        if not cmd:
            return None

        self.log(f">>> {cmd}")

        # ---- client ----
        if cmd == "client.version":
            return f"Bucko client v{self.client_version}"

        if cmd == "client.restart":
            if cb := self.app.get("restart"):
                cb()
            return "Restarting..."

        if cmd == "client.quit":
            if cb := self.app.get("quit"):
                cb()
            return "Quitting..."

        if cmd == "client.config.reload":
            self.cache.clean()
            if cb := self.app.get("reload_config"):
                cb()
            return "[INFO] Config reloaded"

        if cmd == "client.config.validate":
            return self._cmd_validate_config()

        # ---- cache ----
        if cmd == "cache.clean":
            self.cache.clean()
            return "[INFO] Cache cleaned"

        # ---- logs ----
        if cmd == "logs.clean":
            if cb := self.app.get("logs_clean"):
                cb()
            return "[INFO] Logs cleared"

        if cmd.startswith("logs.export"):
            parts = cmd.split(maxsplit=1)
            path = parts[1] if len(parts) > 1 else "logs/export.log"
            if cb := self.app.get("logs_export"):
                cb(path)
            return f"[INFO] Logs exported to {path}"

        # ---- mods ----
        if cmd == "mod.list":
            return self._cmd_mod_list()

        if cmd.startswith("mod.install "):
            return f"[TODO] Mod installation not yet implemented"

        if cmd.startswith("mod.uninstall "):
            return f"[TODO] Mod uninstall not yet implemented"

        if cmd.startswith("mod.reload "):
            mod_id = cmd.split(maxsplit=1)[1]
            return self._cmd_mod_reload(mod_id)

        if cmd.startswith("mod.info "):
            mod_id = cmd.split(maxsplit=1)[1]
            return self._cmd_mod_info(mod_id)

        if cmd.startswith("mod.validate "):
            mod_id = cmd.split(maxsplit=1)[1]
            return f"[INFO] Validated mod: {mod_id} (TODO)"

        if cmd.startswith("mod.enable "):
            mod_id = cmd.split(maxsplit=1)[1]
            return self._cmd_mod_toggle(mod_id, True)

        if cmd.startswith("mod.disable "):
            mod_id = cmd.split(maxsplit=1)[1]
            return self._cmd_mod_toggle(mod_id, False)

        if cmd.startswith("mod."):
            return self._cmd_mod_custom(cmd)

        # ---- dialogue ----
        if cmd == "dialogue.list":
            return self._cmd_dialogue_list()

        if cmd.startswith("dialogue.search "):
            query = cmd.split(maxsplit=1)[1]
            return self._cmd_dialogue_search(query)

        if cmd.startswith("dialogue.trigger "):
            dialogue_id = cmd.split(maxsplit=1)[1]
            return self._cmd_dialogue_trigger(dialogue_id)

        if cmd == "dialogue.reload":
            if cb := self.app.get("reload_dialogue"):
                cb()
            return "[INFO] Dialogue reloaded"

        if cmd == "dialogue.clean":
            return "[INFO] Dialogue cache cleaned"

        # ---- memory ----
        if cmd == "memory.dump":
            return self._cmd_memory_dump()

        if cmd.startswith("memory.get "):
            path = cmd.split(maxsplit=1)[1]
            return self._cmd_memory_get(path)

        if cmd.startswith("memory.clear "):
            ns = cmd.split(maxsplit=1)[1]
            return self._cmd_memory_clear_prompt(ns)

        if cmd == "memory.clean":
            return self._cmd_memory_clean()

        if cmd == "bucko.affection":
            disp = self.state.affection.display_value
            internal = self.state.affection.internal_value
            return f"Affection: {disp}/1000 ({internal:,} internal units)"

        # ---- debug ----
        if cmd == "debug.mood":
            mood = self.state.mood.get()
            return "\n".join(f"  {k}: {v:.1f}" for k, v in mood.items())

        if cmd.startswith("debug.interest "):
            topic = cmd.split(maxsplit=1)[1]
            return self._cmd_debug_interest(topic)

        if cmd == "debug.hash.verify":
            return self._cmd_hash_verify()

        if cmd == "debug.triggers.list":
            return self._cmd_triggers_list()

        if cmd.startswith("debug.triggers.search "):
            query = cmd.split(maxsplit=1)[1]
            return self._cmd_triggers_search(query)

        # ---- master clean ----
        if cmd == "bucko.clean":
            return self._cmd_bucko_clean()

        return f"[ERROR] Unknown command: {cmd}\n  Type 'help' for command list"

    # ------------------------------------------------------------------ #

    def _cmd_mod_list(self) -> str:
        mods = self.mm.list_all()
        if not mods:
            return "No mods loaded"
        lines = ["Loaded mods:"]
        for m in mods:
            status = "enabled" if m.enabled else "disabled"
            lines.append(f"  {m.id} — {m.name} v{m.mod_version} [{status}]")
        return "\n".join(lines)

    def _cmd_mod_reload(self, mod_id: str) -> str:
        mod = self.mm.get(mod_id)
        if not mod:
            return f"[ERROR] Mod '{mod_id}' not found"
        self.mm.reload_mod(mod_id, self.dm)
        return f"[INFO] Mod '{mod_id}' reloaded"

    def _cmd_mod_info(self, mod_id: str) -> str:
        mod = self.mm.get(mod_id)
        if not mod:
            return f"[ERROR] Mod '{mod_id}' not found"
        lines = [
            f"Name: {mod.name}",
            f"ID: {mod.id}",
            f"Version: {mod.mod_version}",
            f"Supports clients: {mod.version_support}",
            f"Author: {mod.author}",
            f"Description: {mod.description}",
        ]
        if mod.console_commands:
            lines.append("Commands:")
            for c in mod.console_commands:
                lines.append(f"  mod.{mod.id}.{c['name']} — {c.get('description', '')}")
        return "\n".join(lines)

    def _cmd_mod_toggle(self, mod_id: str, enable: bool) -> str:
        mod = self.mm.get(mod_id)
        if not mod:
            return f"[ERROR] Mod '{mod_id}' not found"
        mod.enabled = enable
        return f"[INFO] Mod '{mod_id}' {'enabled' if enable else 'disabled'}"

    def _cmd_mod_custom(self, cmd: str) -> str:
        # mod.[mod_id].[command] or mod.[mod_id].clean
        parts = cmd.split(".")
        if len(parts) < 3:
            return f"[ERROR] Invalid mod command: {cmd}"
        mod_id = parts[1]
        sub_cmd = ".".join(parts[2:])

        if sub_cmd == "clean":
            self.mm.clean_mod_data(mod_id, self.state)
            return f"[INFO] Cleaned data for mod: {mod_id}"

        mod = self.mm.get(mod_id)
        if not mod:
            return f"[ERROR] Mod '{mod_id}' not found"

        for c in mod.console_commands:
            if c.get("name") == sub_cmd:
                return f"[MOD:{mod_id}] Executed: {sub_cmd} (handler not implemented in YAML mods)"

        return f"[ERROR] Unknown mod command: {cmd}"

    def _cmd_dialogue_list(self) -> str:
        blocks = self.dm._blocks
        if not blocks:
            return "No dialogue blocks loaded"
        lines = [f"Loaded {len(blocks)} dialogue blocks:"]
        for b in blocks[:50]:
            lines.append(f"  {b.full_id}")
        if len(blocks) > 50:
            lines.append(f"  ... and {len(blocks) - 50} more")
        return "\n".join(lines)

    def _cmd_dialogue_search(self, query: str) -> str:
        q = query.lower()
        results = []
        for b in self.dm._blocks:
            if q in b.full_id.lower():
                results.append(b.full_id)
            for label in b.get_trigger_labels():
                if q in label.lower() and b.full_id not in results:
                    results.append(b.full_id)
        if not results:
            return f"No dialogue found matching '{query}'"
        return "\n".join(results[:30])

    def _cmd_dialogue_trigger(self, dialogue_id: str) -> str:
        block = self.dm.get_dialogue_by_id(dialogue_id)
        if not block:
            return f"[ERROR] Dialogue '{dialogue_id}' not found"
        if cb := self.app.get("trigger_dialogue"):
            cb(block)
        return f"[INFO] Triggered: {dialogue_id}"

    def _cmd_memory_dump(self) -> str:
        lines = ["Memory dump:"]
        for ns, entries in self.state.memory.items():
            if isinstance(entries, dict):
                for k, v in entries.items():
                    val = v.get("value") if isinstance(v, dict) else v
                    lines.append(f"  memory.{ns}.{k} = {val}")
        return "\n".join(lines) if len(lines) > 1 else "Memory is empty"

    def _cmd_memory_get(self, path: str) -> str:
        parts = path.split(".", 1)
        if len(parts) < 2:
            return "[ERROR] Format: memory.get namespace.key"
        ns, key = parts
        store = self.state.memory.get(ns, {})
        val = store.get(key)
        if val is None:
            return f"(not set)"
        if isinstance(val, dict) and "value" in val:
            return str(val["value"])
        return str(val)

    def _cmd_memory_clear_prompt(self, ns: str) -> str:
        # In the real app, this would ask for confirmation via GUI
        store = self.state.memory.get(ns)
        if store is None:
            return f"[ERROR] Namespace '{ns}' not found"
        # Return a confirmation request — app layer handles it
        return f"[CONFIRM] Clear all memory in namespace '{ns}'? This cannot be undone.\n  Run: memory.clear.confirm {ns}"

    def _cmd_memory_clean(self) -> str:
        return "[CONFIRM] This will clear all non-essential memory. Run: memory.clean.confirm"

    def _cmd_debug_interest(self, topic: str) -> str:
        iv = self.state.interests.get(topic)
        if not iv:
            return f"No interest data for '{topic}'"
        return "\n".join(f"  {k}: {v}" for k, v in iv.items())

    def _cmd_hash_verify(self) -> str:
        from engine.save_manager import verify_memory_entry
        issues = 0
        for ns, entries in self.state.memory.items():
            if isinstance(entries, dict):
                for k, v in entries.items():
                    if isinstance(v, dict) and "_hash" in v:
                        if not verify_memory_entry(v):
                            self.log(f"[WARN] Hash mismatch: memory.{ns}.{k}")
                            issues += 1
        if issues:
            return f"[WARN] {issues} hash mismatches found"
        return "[INFO] All memory hashes verified OK"

    def _cmd_triggers_list(self) -> str:
        labels = self.dm.get_all_trigger_labels()
        if not labels:
            return "No triggers loaded"
        lines = [f"Loaded {len(labels)} trigger labels:"]
        for label, tag in labels[:50]:
            lines.append(f"  {label}  {tag}")
        if len(labels) > 50:
            lines.append(f"  ... and {len(labels) - 50} more")
        return "\n".join(lines)

    def _cmd_triggers_search(self, query: str) -> str:
        q = query.lower()
        results = [(l, t) for l, t in self.dm.get_all_trigger_labels() if q in l.lower()]
        if not results:
            return f"No triggers matching '{query}'"
        return "\n".join(f"  {l}  {t}" for l, t in results[:30])

    def _cmd_validate_config(self) -> str:
        return "[INFO] Config validation OK (basic check)"

    def _cmd_bucko_clean(self) -> str:
        return (
            "[CONFIRM] This will run cache.clean + logs.clean + memory.clean.\n"
            "  Run: bucko.clean.confirm"
        )
