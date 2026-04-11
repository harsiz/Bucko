"""
Bucko — desktop companion app.
Entry point. Run this directly or compile via build.py.
"""
import sys
import os
import time
import threading
import tkinter as tk
from tkinter import scrolledtext
from pathlib import Path
import yaml

# Ensure project root is in path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

try:
    import ttkbootstrap as ttk
    from ttkbootstrap.constants import *
except ImportError:
    print("ttkbootstrap not installed. Run: pip install ttkbootstrap")
    sys.exit(1)

from engine.save_manager import load_save, write_save
from engine.state import GameState
from engine.dialogue import DialogueManager
from engine.mods import ModManager
from engine.cache import ConfigCache
from engine.console import ConsoleSystem
from engine.discord_rpc import DiscordRPC

# ── Paths ─────────────────────────────────────────────────────────────────────
CORE_DIR = ROOT / "core"
MODS_DIR = ROOT / "mods"
SAVES_DIR = ROOT / "saves"
LOGS_DIR = ROOT / "logs"
CONFIG_FILE = ROOT / "client_config.yaml"

LOGS_DIR.mkdir(exist_ok=True)
SAVES_DIR.mkdir(exist_ok=True)


# ── Logging ───────────────────────────────────────────────────────────────────
_log_file = open(LOGS_DIR / "console.log", "a", encoding="utf-8")
_log_listeners: list = []  # GUI callbacks

def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    _log_file.write(line + "\n")
    _log_file.flush()
    for cb in list(_log_listeners):
        try:
            cb(line)
        except Exception:
            pass


# ── Config loading ─────────────────────────────────────────────────────────────
def _load_client_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return {}

_cfg = _load_client_config()
CLIENT_VERSION = _cfg.get("client_version", 1)
TYPEWRITER_SPEED = _cfg.get("ui", {}).get("typewriter_speed", 0.03)
DEFAULT_NEXT_LABEL = _cfg.get("ui", {}).get("default_next_label", "NEXT")
WINDOW_WIDTH = _cfg.get("ui", {}).get("window_width", 900)
WINDOW_HEIGHT = _cfg.get("ui", {}).get("window_height", 650)
THEME = _cfg.get("ui", {}).get("theme", "darkly")
# Lines within a block auto-advance after this delay (seconds). 0 = require NEXT click per line.
AUTO_ADVANCE_DELAY = _cfg.get("ui", {}).get("auto_advance_delay", 0.55)
# Delay before Bucko "starts typing" after user input (ms)
THINKING_DELAY_MS = _cfg.get("ui", {}).get("thinking_delay_ms", 350)
MOOD_BASELINE = _cfg.get("mood", {}).get("baseline", {
    "energy": 70, "patience": 80, "chaos": 40, "warmth": 75
})
DECAY_RATE = _cfg.get("mood", {}).get("decay_rate", 1.0)
DISCORD_ENABLED = _cfg.get("discord_rpc", {}).get("enabled", True)
DISCORD_APP_ID = str(_cfg.get("discord_rpc", {}).get("app_id", "0"))


# ── Cache + config loader ──────────────────────────────────────────────────────
_cache = ConfigCache(log=_log)

def _config_loader(filename: str):
    # Search core/ first, then mods/
    for search_dir in [CORE_DIR, CORE_DIR / "dialogue"]:
        p = search_dir / filename
        if p.exists():
            return _cache.load_yaml(p)
    # Try absolute
    p = ROOT / filename
    if p.exists():
        return _cache.load_yaml(p)
    return {}


# ── Expressions ───────────────────────────────────────────────────────────────
EXPRESSIONS_DIR = CORE_DIR / "expressions"

def _load_expressions() -> dict[str, tk.PhotoImage]:
    """Load expression images from core/expressions/. Returns name -> PhotoImage."""
    expressions = {}
    if EXPRESSIONS_DIR.exists():
        for img_file in EXPRESSIONS_DIR.glob("*.png"):
            name = img_file.stem
            try:
                expressions[name] = tk.PhotoImage(file=str(img_file))
            except tk.TclError:
                pass
        for img_file in EXPRESSIONS_DIR.glob("*.gif"):
            name = img_file.stem
            try:
                expressions[name] = tk.PhotoImage(file=str(img_file))
            except tk.TclError:
                pass
    _log(f"[INFO] Loaded {len(expressions)} expression states for Bucko")
    return expressions


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Application
# ═══════════════════════════════════════════════════════════════════════════════

class BuckoApp:
    def __init__(self, root: ttk.Window):
        self.root = root
        self.root.title("Bucko")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.resizable(True, True)
        self.root.minsize(600, 450)

        # ── Load save ──────────────────────────────────────────────────────
        save_data, tampered = load_save()
        if tampered:
            _log("[WARN] Save file hash mismatch — data may have been modified")

        self.is_first_launch = save_data.get("meta", {}).get("first_launch", True)

        # ── State ──────────────────────────────────────────────────────────
        self.state = GameState(
            save_data=save_data,
            baseline=MOOD_BASELINE,
            decay_rate=DECAY_RATE,
            config_loader=_config_loader,
            console_log=_log,
        )

        # ── Dialogue manager ───────────────────────────────────────────────
        self.dm = DialogueManager(self.state)

        # ── Mod manager ────────────────────────────────────────────────────
        self.mm = ModManager(MODS_DIR, CLIENT_VERSION, _log)

        # ── Load core dialogue ─────────────────────────────────────────────
        self._load_core_dialogue()

        # ── Load mods ──────────────────────────────────────────────────────
        self._load_mods()

        # ── Log block counts ───────────────────────────────────────────────
        _log(f"[INFO] Loaded {len(self.dm._blocks)} dialogue blocks for Bucko")

        # ── Console ────────────────────────────────────────────────────────
        self.console_sys = ConsoleSystem(
            state=self.state,
            dialogue_manager=self.dm,
            mod_manager=self.mm,
            cache=_cache,
            log=_log,
            client_version=CLIENT_VERSION,
            app_callbacks={
                "restart": self._restart,
                "quit": self._quit,
                "reload_config": self._reload_config,
                "reload_dialogue": self._reload_dialogue,
                "logs_clean": self._logs_clean,
                "logs_export": self._logs_export,
                "trigger_dialogue": self._trigger_dialogue_from_console,
                "install_mod": self._install_mod_async,
            }
        )

        # ── Discord RPC ────────────────────────────────────────────────────
        self.discord = DiscordRPC(DISCORD_APP_ID, _log) if DISCORD_ENABLED else None
        if self.discord:
            threading.Thread(target=self._connect_discord, daemon=True).start()

        # ── Build GUI ──────────────────────────────────────────────────────
        self._build_gui()

        # ── Register log listener ──────────────────────────────────────────
        _log_listeners.append(self._on_log_line)

        # ── Dialogue state ─────────────────────────────────────────────────
        self._current_block = None
        self._pending_lines: list = []
        self._typewriter_active = False
        self._awaiting_input = False
        self._input_capture_mode = False
        self._input_capture_key = ""
        self._next_auto = False
        self._autocomplete_cache: list[tuple[str, str]] = []
        self._typing_indicator_active = False
        self._autosave_id = None
        # Follow-up context: set after each block fires, cleared on non-match
        self._context_follow_ups: list = []
        self._context_expiry: float = 0.0

        # ── Cache warmup ───────────────────────────────────────────────────
        threading.Thread(target=self._warmup_cache, daemon=True).start()

        # ── Start session ──────────────────────────────────────────────────
        self.root.after(200, self._start_session)

    # ────────────────────────────────────────────────────────────────────────
    #  Loading helpers
    # ────────────────────────────────────────────────────────────────────────

    def _load_core_dialogue(self) -> None:
        setup_yaml = CORE_DIR / "setup.yaml"
        if setup_yaml.exists():
            count = self.dm.load_yaml(setup_yaml, "setup")
            _log(f"[INFO] Loaded {count} dialogue blocks from setup.yaml")

        dialogue_dir = CORE_DIR / "dialogue"
        if dialogue_dir.exists():
            for yaml_file in sorted(dialogue_dir.glob("*.yaml")):
                ns = yaml_file.stem
                count = self.dm.load_yaml(yaml_file, ns)
                _log(f"[INFO] Loaded {count} dialogue blocks from {yaml_file.name}")

    def _load_mods(self) -> None:
        mods = self.mm.load_all()
        for mod in mods:
            for yaml_file in sorted(mod.dir.glob("*.yaml")):
                if yaml_file.name == "mod.yaml":
                    continue
                count = self.dm.load_yaml(yaml_file, mod.id)
                if count:
                    _log(f"[INFO] Mod '{mod.id}': loaded {count} dialogue blocks from {yaml_file.name}")

    # ────────────────────────────────────────────────────────────────────────
    #  GUI Construction
    # ────────────────────────────────────────────────────────────────────────

    def _build_gui(self) -> None:
        self.expressions = _load_expressions()

        # Main notebook with Chat + Console tabs
        self.notebook = ttk.Notebook(self.root, bootstyle="dark")
        self.notebook.pack(fill=BOTH, expand=True)

        # ── Chat tab ───────────────────────────────────────────────────────
        self.chat_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.chat_frame, text="  Chat  ")

        # ── Console tab ───────────────────────────────────────────────────
        self.console_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.console_frame, text="  Console  ")

        self._build_chat_tab()
        self._build_console_tab()

    def _build_chat_tab(self) -> None:
        frame = self.chat_frame

        # Top area: expression image + dialogue text side by side
        top = ttk.Frame(frame)
        top.pack(fill=BOTH, expand=True, padx=10, pady=10)

        # Expression panel (left)
        self.expr_frame = ttk.Frame(top, width=160)
        self.expr_frame.pack(side=LEFT, fill=Y, padx=(0, 10))
        self.expr_frame.pack_propagate(False)

        self.expr_label = ttk.Label(
            self.expr_frame,
            text="(^_^)",
            font=("Consolas", 36),
            anchor="center",
        )
        self.expr_label.pack(fill=BOTH, expand=True)

        # Dialogue area (right)
        right = ttk.Frame(top)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        # Dialogue text display
        self.dialogue_text = tk.Text(
            right,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 12),
            bg="#1a1a2e",
            fg="#e0e0e0",
            relief=tk.FLAT,
            padx=12,
            pady=10,
            cursor="arrow",
            selectbackground="#2d2d6e",
        )
        self.dialogue_text.pack(fill=BOTH, expand=True)

        # Configure text tags
        self.dialogue_text.tag_config("bucko", foreground="#c9e8f5", font=("Consolas", 12))
        self.dialogue_text.tag_config("speaker", foreground="#7ec8e3", font=("Consolas", 11, "bold"))
        self.dialogue_text.tag_config("system", foreground="#555577", font=("Consolas", 10, "italic"))
        self.dialogue_text.tag_config("user_label", foreground="#6ab87a", font=("Consolas", 11, "bold"))
        self.dialogue_text.tag_config("user", foreground="#a8d8a8", font=("Consolas", 12))

        # Bottom area: NEXT button + input bar
        bottom = ttk.Frame(frame)
        bottom.pack(fill=X, padx=10, pady=(0, 10))

        # NEXT button (hidden by default)
        self.next_btn = ttk.Button(
            bottom,
            text=DEFAULT_NEXT_LABEL,
            bootstyle="info-outline",
            command=self._on_next,
            width=12,
        )
        self.next_btn.pack(side=RIGHT, padx=(5, 0))
        self.next_btn.pack_forget()

        # Input frame with autocomplete
        input_frame = ttk.Frame(bottom)
        input_frame.pack(fill=X, side=LEFT, expand=True)

        self.input_var = tk.StringVar()
        self.input_var.trace_add("write", self._on_input_change)

        self.input_entry = ttk.Entry(
            input_frame,
            textvariable=self.input_var,
            font=("Consolas", 12),
            bootstyle="secondary",
        )
        self.input_entry.pack(fill=X)
        self.input_entry.bind("<Return>", self._on_submit)
        self.input_entry.bind("<Up>", self._autocomplete_up)
        self.input_entry.bind("<Down>", self._autocomplete_down)
        self.input_entry.bind("<Escape>", self._autocomplete_hide)

        # Autocomplete dropdown
        self.autocomplete_frame = ttk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        self.autocomplete_listbox = tk.Listbox(
            self.autocomplete_frame,
            font=("Consolas", 11),
            bg="#2a2a3e",
            fg="#d0d0d0",
            selectbackground="#4a4a8e",
            selectforeground="white",
            activestyle="none",
            relief=tk.FLAT,
            height=5,
        )
        self.autocomplete_listbox.pack(fill=BOTH, expand=True)
        self.autocomplete_listbox.bind("<Return>", self._autocomplete_select)
        self.autocomplete_listbox.bind("<Double-Button-1>", self._autocomplete_select)
        self._autocomplete_visible = False

    def _build_console_tab(self) -> None:
        frame = self.console_frame

        # Console output
        self.console_output = scrolledtext.ScrolledText(
            frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10),
            bg="#0d0d0d",
            fg="#00ff88",
            relief=tk.FLAT,
            padx=8,
            pady=8,
        )
        self.console_output.pack(fill=BOTH, expand=True, padx=5, pady=5)

        # Console input
        console_input_frame = ttk.Frame(frame)
        console_input_frame.pack(fill=X, padx=5, pady=(0, 5))

        ttk.Label(console_input_frame, text=">>> ", font=("Consolas", 11), foreground="#00ff88").pack(side=LEFT)

        self.console_var = tk.StringVar()
        self.console_var.trace_add("write", self._on_console_input_change)
        self.console_entry = ttk.Entry(
            console_input_frame,
            textvariable=self.console_var,
            font=("Consolas", 11),
            bootstyle="success",
        )
        self.console_entry.pack(fill=X, side=LEFT, expand=True)
        self.console_entry.bind("<Return>", self._on_console_submit)
        self.console_entry.bind("<Escape>", self._console_autocomplete_hide)
        self.console_entry.bind("<Up>", self._console_up_key)
        self.console_entry.bind("<Down>", self._console_down_key)

        # Console autocomplete dropdown
        self.console_ac_frame = ttk.Frame(self.root, relief=tk.RAISED, borderwidth=1)
        self.console_ac_listbox = tk.Listbox(
            self.console_ac_frame,
            font=("Consolas", 10),
            bg="#0a1a0a",
            fg="#00ff88",
            selectbackground="#003300",
            selectforeground="#00ff88",
            activestyle="none",
            relief=tk.FLAT,
            height=6,
        )
        self.console_ac_listbox.pack(fill=BOTH, expand=True)
        self.console_ac_listbox.bind("<Return>", self._console_autocomplete_select)
        self.console_ac_listbox.bind("<Double-Button-1>", self._console_autocomplete_select)
        self._console_ac_visible = False
        self._console_ac_data: list[str] = []

        # Console history
        self._console_history: list[str] = []
        self._console_history_idx = -1

    # ────────────────────────────────────────────────────────────────────────
    #  Session start
    # ────────────────────────────────────────────────────────────────────────

    def _start_session(self) -> None:
        import datetime as dt
        self.state.counters["times_talked"] = self.state.counters.get("times_talked", 0) + 1
        session_num = self.state.counters["times_talked"]

        # Store first session date
        if not self.state.memory.get("global", {}).get("first_session_date"):
            mem = self.state.memory.setdefault("global", {})
            mem["first_session_date"] = {"value": dt.date.today().isoformat()}

        # Discord RPC
        if self.discord:
            self.discord.update(session_num)

        if self.is_first_launch or not self.state.user_name:
            self._trigger_dialogue_id("setup::disclaimer")
        else:
            self._trigger_dialogue_id("setup::returning_user")

    # ────────────────────────────────────────────────────────────────────────
    #  Dialogue rendering
    # ────────────────────────────────────────────────────────────────────────

    def _trigger_dialogue_id(self, dialogue_id: str) -> None:
        block = self.dm.get_dialogue_by_id(dialogue_id)
        if block:
            self._start_block(block)
        else:
            _log(f"[WARN] Dialogue not found: {dialogue_id}")

    def _trigger_dialogue_from_console(self, block) -> None:
        self.root.after(0, lambda: self._start_block(block))

    def _start_block(self, block) -> None:
        self._hide_typing_indicator()
        self.state.reset_block_affection()
        block.last_triggered = time.time()
        self.dm.apply_mood_effect(block)

        if block.expression:
            self._set_expression(block.expression)

        rendered_lines = self.dm.render_lines(block)
        self._current_block = block
        self._pending_lines = rendered_lines
        self._next_id = block.next_id

        # Register follow-up context for this block (2 minute window)
        fu = getattr(block, "follow_ups", [])
        if fu:
            self._context_follow_ups = fu
            self._context_expiry = time.time() + 120.0
        else:
            self._context_follow_ups = []
            self._context_expiry = 0.0

        # Visual: blank line + speaker label before each new block
        self._append_text("\n", tag="")
        self._append_text("Bucko", tag="speaker")

        self._process_next_line()

    def _start_followup(self, fu_block) -> None:
        """Fire a follow-up block (context-aware reply)."""
        self._hide_typing_indicator()
        self.state.reset_block_affection()

        # Apply mood/affection
        effect = dict(fu_block.mood_effect)
        aff_dir = effect.pop("affection", None)
        if effect:
            self.state.mood.apply_effect(effect)
        if aff_dir in ("increase", "decrease"):
            self.state.apply_affection_change(aff_dir)

        if fu_block.expression:
            self._set_expression(fu_block.expression)

        # Render lines (BDL evaluation)
        rendered = []
        for line in fu_block.lines:
            if isinstance(line, dict) and "pause" in line:
                rendered.append(("pause", float(line["pause"])))
            elif isinstance(line, str):
                ev = self.dm.bdl.evaluate(line)
                if "\x00SKIP\x00" not in ev:
                    rendered.append(ev)

        self._current_block = None
        self._pending_lines = rendered
        self._next_id = fu_block.next_id

        # Set nested follow-ups as next context
        nested = fu_block.follow_ups
        if nested:
            self._context_follow_ups = nested
            self._context_expiry = time.time() + 120.0
        else:
            self._context_follow_ups = []
            self._context_expiry = 0.0

        self._append_text("\n", tag="")
        self._append_text("Bucko", tag="speaker")
        self._process_next_line()

    def _process_next_line(self) -> None:
        if not self._pending_lines:
            # All lines done — check for auto-chain or show NEXT
            self._on_block_complete()
            return

        line = self._pending_lines.pop(0)

        if isinstance(line, tuple) and line[0] == "pause":
            pause_secs = float(line[1])
            # If this was the last line and there's a next block — auto chain
            if not self._pending_lines and self._next_id:
                self.root.after(int(pause_secs * 1000), self._chain_to_next)
            else:
                self.root.after(int(pause_secs * 1000), self._process_next_line)
            return

        if isinstance(line, tuple) and line[0] == "input_capture":
            self._input_capture_mode = True
            self._input_capture_key = line[1]
            self._show_input_prompt()
            return

        if isinstance(line, str):
            # Handle typewriter for this line
            self._typewrite_line(line, callback=self._on_line_complete)

    def _on_line_complete(self) -> None:
        """Called after a line finishes typewriting."""
        if self._pending_lines:
            peek = self._pending_lines[0]
            if isinstance(peek, tuple) and peek[0] in ("pause", "input_capture"):
                # These never need a NEXT click
                self._process_next_line()
            elif AUTO_ADVANCE_DELAY > 0:
                # Auto-advance to next line within the same block
                self.root.after(int(AUTO_ADVANCE_DELAY * 1000), self._process_next_line)
            else:
                # Manual NEXT required per line
                self._show_next_button()
        else:
            self._on_block_complete()

    def _on_block_complete(self) -> None:
        """Called when all lines in current block are done."""
        if self._next_id and not self._pending_lines:
            self._show_next_button(label=self._current_block.next_label or DEFAULT_NEXT_LABEL)
        else:
            # Ready for user input
            self._awaiting_input = True
            self._hide_next_button()
            self._enable_input()

    def _chain_to_next(self) -> None:
        """Chain to next block without user input (auto-chain after pause)."""
        if self._current_block:
            next_block = self.dm.resolve_next(self._current_block)
            if next_block:
                self._start_block(next_block)
            else:
                self._awaiting_input = True
                self._enable_input()

    def _on_next(self) -> None:
        """User clicked NEXT button."""
        self._hide_next_button()
        if self._pending_lines:
            self._process_next_line()
        elif self._next_id:
            next_block = self.dm.resolve_next(self._current_block)
            if next_block:
                self._start_block(next_block)
            else:
                self._awaiting_input = True
                self._enable_input()
        else:
            self._awaiting_input = True
            self._enable_input()

    # ────────────────────────────────────────────────────────────────────────
    #  Typewriter effect
    # ────────────────────────────────────────────────────────────────────────

    def _typewrite_line(self, text: str, callback=None) -> None:
        """Render text character by character using after() scheduling."""
        from engine.bdl import WAIT_RE

        # Break into segments (text + waits)
        segments = []
        last = 0
        for m in WAIT_RE.finditer(text):
            chunk = text[last:m.start()]
            if chunk:
                segments.append(("text", chunk))
            segments.append(("wait", float(m.group(1))))
            last = m.end()
        tail = text[last:]
        if tail:
            segments.append(("text", tail))
        if not segments:
            segments = [("text", text)]

        self._append_text("\n  ", tag="bucko")  # indent each line under the speaker label
        self._typewrite_segments(segments, 0, 0, callback)

    def _typewrite_segments(self, segments: list, seg_idx: int, char_idx: int, callback) -> None:
        if seg_idx >= len(segments):
            if callback:
                self.root.after(50, callback)
            return

        seg_type, seg_val = segments[seg_idx]

        if seg_type == "wait":
            self.root.after(int(seg_val * 1000),
                lambda: self._typewrite_segments(segments, seg_idx + 1, 0, callback))
            return

        # text segment
        text = seg_val
        if char_idx >= len(text):
            self._typewrite_segments(segments, seg_idx + 1, 0, callback)
            return

        char = text[char_idx]
        self._append_text(char, tag="bucko")

        delay = int(TYPEWRITER_SPEED * 1000)
        # Slightly longer pause at punctuation for rhythm
        if char in ".!?":
            delay = int(delay * 4)
        elif char in ",;:":
            delay = int(delay * 2)

        self.root.after(delay,
            lambda: self._typewrite_segments(segments, seg_idx, char_idx + 1, callback))

    # ────────────────────────────────────────────────────────────────────────
    #  Text display helpers
    # ────────────────────────────────────────────────────────────────────────

    def _append_text(self, text: str, tag: str = "") -> None:
        self.dialogue_text.config(state=tk.NORMAL)
        if tag:
            self.dialogue_text.insert(tk.END, text, tag)
        else:
            self.dialogue_text.insert(tk.END, text)
        self.dialogue_text.see(tk.END)
        self.dialogue_text.config(state=tk.DISABLED)

    def _append_user_line(self, text: str) -> None:
        user_label = self.state.user_name or "You"
        self._append_text(f"\n{user_label}", tag="user_label")
        self._append_text(f"\n  {text}", tag="user")

    def _append_system_line(self, text: str) -> None:
        self._append_text(f"\n{text}", tag="system")

    def _show_typing_indicator(self) -> None:
        """Show an animated '...' indicator. Line-number based for clean removal."""
        if self._typing_indicator_active:
            return  # already showing
        self._typing_indicator_active = True
        self.dialogue_text.config(state=tk.NORMAL)
        # Record the last content line BEFORE inserting anything.
        # "end" always returns "{N}.0" where N includes the implicit trailing line,
        # so (N-1) is the last visible content line.
        n = int(self.dialogue_text.index("end").split(".")[0])
        self._typing_indicator_line = max(1, n - 1)
        self.dialogue_text.insert(tk.END, "\n", "")
        self.dialogue_text.insert(tk.END, "Bucko", "speaker")
        self.dialogue_text.insert(tk.END, "\n  ", "bucko")
        self.dialogue_text.insert(tk.END, "   ", "bucko")  # placeholder for dots
        self.dialogue_text.see(tk.END)
        self.dialogue_text.config(state=tk.DISABLED)
        self._typing_anim_id = self.root.after(100, lambda: self._animate_typing(0))

    def _animate_typing(self, frame: int) -> None:
        if not self._typing_indicator_active:
            return
        dots = ["   ", ".  ", ".. ", "..."][frame % 4]
        self.dialogue_text.config(state=tk.NORMAL)
        # Replace only the last 3 characters (the dot placeholder)
        self.dialogue_text.delete("end -4c", "end -1c")
        self.dialogue_text.insert("end -1c", dots, "bucko")
        self.dialogue_text.see(tk.END)
        self.dialogue_text.config(state=tk.DISABLED)
        self._typing_anim_id = self.root.after(200, lambda: self._animate_typing(frame + 1))

    def _hide_typing_indicator(self) -> None:
        if not self._typing_indicator_active:
            return
        self._typing_indicator_active = False
        if hasattr(self, "_typing_anim_id"):
            try:
                self.root.after_cancel(self._typing_anim_id)
            except Exception:
                pass
        # Delete from the end of the stored line to widget END.
        # "{line}.end" in Tkinter = the '\n' delimiter at the end of that line,
        # which is exactly the '\n' separator we inserted to start the indicator.
        # Deleting from there to END removes the indicator completely.
        self.dialogue_text.config(state=tk.NORMAL)
        try:
            line = getattr(self, "_typing_indicator_line", 1)
            self.dialogue_text.delete(f"{line}.end", tk.END)
        except Exception:
            pass
        self.dialogue_text.config(state=tk.DISABLED)

    def _set_expression(self, name: str) -> None:
        img = self.expressions.get(name)
        if img:
            self.expr_label.config(image=img, text="")
            self.expr_label.image = img
        else:
            # Fallback text expressions
            text_exprs = {
                "default": "(^_^)",
                "happy": "(^▽^)",
                "surprised": "(O_O)",
                "confused": "(?_?)",
                "sad": "(;_;)",
                "smug": "(¬‿¬)",
                "angry": "(>_<)",
                "thinking": "(._. )",
            }
            self.expr_label.config(text=text_exprs.get(name, "(^_^)"), image="")

    # ────────────────────────────────────────────────────────────────────────
    #  Input handling
    # ────────────────────────────────────────────────────────────────────────

    def _enable_input(self) -> None:
        self.input_entry.config(state=tk.NORMAL)
        self.input_entry.focus_set()

    def _disable_input(self) -> None:
        self.input_entry.config(state=tk.DISABLED)

    def _show_input_prompt(self) -> None:
        self._enable_input()
        self._awaiting_input = True
        self._input_capture_mode = True

    def _show_next_button(self, label: str = None) -> None:
        self.next_btn.config(text=label or DEFAULT_NEXT_LABEL)
        self.next_btn.pack(side=RIGHT, padx=(5, 0))

    def _hide_next_button(self) -> None:
        self.next_btn.pack_forget()

    def _on_submit(self, event=None) -> None:
        text = self.input_var.get().strip()
        if not text:
            return

        self._autocomplete_hide()

        # "next" is globally reserved
        if text.lower() == "next":
            self.input_var.set("")
            self._on_next()
            return

        self.input_var.set("")

        if self._input_capture_mode and self._awaiting_input:
            # Store captured input
            self._handle_input_capture(text)
            return

        if not self._awaiting_input:
            return

        self._append_user_line(text)
        self._awaiting_input = False
        self._disable_input()

        # Show typing indicator then process
        self._show_typing_indicator()
        self.root.after(THINKING_DELAY_MS, lambda: self._process_input(text))

    def _handle_input_capture(self, text: str) -> None:
        """Store input from input_capture dialogue lines."""
        key = self._input_capture_key  # e.g. "user.name"
        self._input_capture_mode = False
        self._awaiting_input = False
        self._disable_input()

        self._append_user_line(text)

        # Store in appropriate place
        if key == "user.name":
            self.state.user_name = text
            # Also persist in setup.yaml structure via memory
            mem = self.state.memory.setdefault("user", {})
            mem["name"] = {"value": text}

        _log(f"[INFO] Input captured: {key} = {text!r}")

        # Continue to next block
        if self._current_block and self._current_block.next_id:
            next_block = self.dm.resolve_next(self._current_block)
            if next_block:
                self.root.after(300, lambda: self._start_block(next_block))
                return

        self._awaiting_input = True
        self._enable_input()

    def _process_input(self, user_input: str) -> None:
        # Update interests
        words = user_input.lower().split()
        topics = ["osu", "osu!", "anime", "gaming", "music", "valorant", "fps", "cs", "csgo", "cs2"]
        for topic in topics:
            if topic in words or any(topic in w for w in words):
                self.state.interests.mention(topic)

        # ── Check active follow-up context FIRST ──────────────────────────────
        if self._context_follow_ups and time.time() < self._context_expiry:
            for fu in self._context_follow_ups:
                if fu.matches_input(user_input):
                    self._start_followup(fu)
                    return
        # Context didn't match — clear it and fall through to global matching
        self._context_follow_ups = []

        # Find matching dialogue
        block = self.dm.find_match(user_input)

        if block:
            # Handle repeat tracking
            repeat_count = self.dm.record_repeat(block)
            on_repeat = block.on_repeat

            if on_repeat and repeat_count > 1:
                threshold = on_repeat.get("threshold", 3)
                if repeat_count >= threshold:
                    escalations = on_repeat.get("escalate", [])
                    max_esc = on_repeat.get("max_escalations", 3)
                    esc_idx = min(repeat_count - threshold, max_esc - 1)
                    if esc_idx >= 0 and escalations:
                        if esc_idx < len(escalations):
                            esc_text = self.dm.bdl.evaluate(escalations[esc_idx])
                            # If it's a dialogue ID, trigger it
                            esc_block = self.dm.get_dialogue_by_id(esc_text.strip())
                            if esc_block:
                                self._start_block(esc_block)
                                return
                            else:
                                self._typewrite_line(esc_text, callback=self._re_enable_input)
                                return
                        else:
                            # Max escalations reached — go silent
                            cooldown = on_repeat.get("cooldown", 300)
                            self._append_system_line(f"(Bucko ignores you... try again later)")
                            self.root.after(int(cooldown * 1000), self._re_enable_input)
                            return

            self._start_block(block)
        else:
            # No match
            no_match = self.dm.get_no_match_block()
            if no_match:
                self._start_block(no_match)
            else:
                self._append_system_line("...")
                self._awaiting_input = True
                self._enable_input()

    def _re_enable_input(self) -> None:
        self._awaiting_input = True
        self._enable_input()

    # ────────────────────────────────────────────────────────────────────────
    #  Autocomplete
    # ────────────────────────────────────────────────────────────────────────

    def _on_input_change(self, *args) -> None:
        text = self.input_var.get().strip().lower()
        if not text or text == "next":
            self._autocomplete_hide()
            return

        if not self._autocomplete_cache:
            self._autocomplete_cache = self.dm.get_all_trigger_labels()

        matches = [
            (label, tag) for label, tag in self._autocomplete_cache
            if text in label.lower()
        ][:8]

        if matches:
            self._autocomplete_show(matches)
        else:
            self._autocomplete_hide()

    def _autocomplete_show(self, matches: list[tuple[str, str]]) -> None:
        self.autocomplete_listbox.delete(0, tk.END)
        for label, tag in matches:
            self.autocomplete_listbox.insert(tk.END, f"  {label}  {tag}")

        # Position above input entry
        x = self.input_entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.input_entry.winfo_rooty() - self.root.winfo_rooty()
        w = self.input_entry.winfo_width()
        h = min(len(matches), 5) * 24 + 4

        self.autocomplete_frame.place(
            x=x, y=y - h,
            width=w, height=h
        )
        self.autocomplete_frame.lift()
        self._autocomplete_visible = True
        self._autocomplete_data = [label for label, _ in matches]

    def _autocomplete_hide(self, event=None) -> None:
        self.autocomplete_frame.place_forget()
        self._autocomplete_visible = False

    def _autocomplete_up(self, event=None) -> None:
        if not self._autocomplete_visible:
            return
        cur = self.autocomplete_listbox.curselection()
        if cur:
            idx = max(0, cur[0] - 1)
        else:
            idx = self.autocomplete_listbox.size() - 1
        self.autocomplete_listbox.selection_clear(0, tk.END)
        self.autocomplete_listbox.selection_set(idx)
        return "break"

    def _autocomplete_down(self, event=None) -> None:
        if not self._autocomplete_visible:
            return
        cur = self.autocomplete_listbox.curselection()
        if cur:
            idx = min(self.autocomplete_listbox.size() - 1, cur[0] + 1)
        else:
            idx = 0
        self.autocomplete_listbox.selection_clear(0, tk.END)
        self.autocomplete_listbox.selection_set(idx)
        return "break"

    def _autocomplete_select(self, event=None) -> None:
        cur = self.autocomplete_listbox.curselection()
        if not cur:
            return
        data = getattr(self, "_autocomplete_data", [])
        if cur[0] < len(data):
            self.input_var.set(data[cur[0]])
            self._autocomplete_hide()
            self.input_entry.focus_set()
            self.input_entry.icursor(tk.END)

    # ────────────────────────────────────────────────────────────────────────
    #  Console tab
    # ────────────────────────────────────────────────────────────────────────

    def _on_log_line(self, line: str) -> None:
        """Called on every log line — update console tab."""
        self.root.after(0, lambda: self._append_console(line))

    def _append_console(self, text: str) -> None:
        self.console_output.config(state=tk.NORMAL)
        self.console_output.insert(tk.END, text + "\n")
        self.console_output.see(tk.END)
        self.console_output.config(state=tk.DISABLED)

    def _on_console_submit(self, event=None) -> None:
        cmd = self.console_var.get().strip()
        if not cmd:
            return
        self.console_var.set("")
        self._console_history.append(cmd)
        self._console_history_idx = -1

        result = self._handle_console_command(cmd)
        if result:
            self._append_console(result)

    def _handle_console_command(self, cmd: str) -> str:
        # Handle confirm commands
        if cmd == "memory.clean.confirm":
            for ns in list(self.state.memory.keys()):
                if ns != "repeat":
                    self.state.memory[ns] = {}
            _log("[INFO] Memory cleaned")
            return "[INFO] Memory cleaned"

        if cmd.startswith("memory.clear.confirm "):
            ns = cmd.split(maxsplit=1)[1]
            self.state.memory[ns] = {}
            _log(f"[INFO] Cleared memory namespace: {ns}")
            return f"[INFO] Cleared: memory.{ns}"

        if cmd == "bucko.clean.confirm":
            _cache.clean()
            self._logs_clean()
            for ns in list(self.state.memory.keys()):
                if ns not in ("repeat",):
                    self.state.memory[ns] = {}
            _log("[INFO] Full clean complete")
            return "[INFO] bucko.clean complete"

        if cmd == "chat.clear":
            self.dialogue_text.config(state=tk.NORMAL)
            self.dialogue_text.delete(1.0, tk.END)
            self.dialogue_text.config(state=tk.DISABLED)
            return "[INFO] Chat cleared"

        if cmd == "discord.status":
            if not self.discord:
                return "[INFO] Discord RPC is disabled in client_config.yaml"
            return f"[INFO] Discord RPC — {self.discord.status()}"

        if cmd == "discord.reconnect":
            if not self.discord:
                return "[INFO] Discord RPC is disabled in client_config.yaml"
            _log("[INFO] Discord RPC — attempting reconnect...")
            ok = self.discord.reconnect()
            if ok:
                session_num = self.state.memory.get("meta", {}).get("times_talked", 1)
                self.discord.update(session_num)
                return "[INFO] Discord RPC reconnected successfully"
            return "[WARN] Discord RPC reconnect failed — check console log for details"

        if cmd == "discord.setup":
            return (
                "Discord RPC Setup\n"
                "─────────────────────────────────────────────────\n"
                "1. Visit  https://discord.com/developers/applications\n"
                "2. Click  New Application  (name it 'Bucko' or anything)\n"
                "3. Copy the  Application ID  from General Information\n"
                "4. Open  client_config.yaml  and set:\n"
                "       discord_rpc:\n"
                "         app_id: \"YOUR_ID_HERE\"\n"
                "5. Save the file, then run  discord.reconnect"
            )

        if cmd == "help":
            return HELP_TEXT

        return self.console_sys.execute(cmd) or ""

    def _console_up_key(self, event=None) -> None:
        if self._console_ac_visible:
            self._console_ac_up()
        else:
            self._console_history_up()
        return "break"

    def _console_down_key(self, event=None) -> None:
        if self._console_ac_visible:
            self._console_ac_down()
        else:
            self._console_history_down()
        return "break"

    def _console_history_up(self) -> None:
        if not self._console_history:
            return
        self._console_history_idx = max(0, self._console_history_idx - 1
            if self._console_history_idx >= 0
            else len(self._console_history) - 1)
        self.console_var.set(self._console_history[self._console_history_idx])

    def _console_history_down(self) -> None:
        if self._console_history_idx < 0:
            return
        if self._console_history_idx >= len(self._console_history) - 1:
            self._console_history_idx = -1
            self.console_var.set("")
        else:
            self._console_history_idx += 1
            self.console_var.set(self._console_history[self._console_history_idx])

    # ── Console autocomplete ──────────────────────────────────────────────────

    def _on_console_input_change(self, *args) -> None:
        text = self.console_var.get().strip().lower()
        if not text:
            self._console_autocomplete_hide()
            return
        matches = [(cmd, desc) for cmd, desc in CONSOLE_COMMANDS if text in cmd.lower()][:8]
        if matches:
            self._console_autocomplete_show(matches)
        else:
            self._console_autocomplete_hide()

    def _console_autocomplete_show(self, matches: list[tuple[str, str]]) -> None:
        self.console_ac_listbox.delete(0, tk.END)
        for cmd, desc in matches:
            self.console_ac_listbox.insert(tk.END, f"  {cmd}   — {desc}")
        self._console_ac_data = [cmd for cmd, _ in matches]

        x = self.console_entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.console_entry.winfo_rooty() - self.root.winfo_rooty()
        w = self.console_entry.winfo_width() + 60  # label width
        h = min(len(matches), 6) * 22 + 4

        self.console_ac_frame.place(x=x, y=y - h, width=w, height=h)
        self.console_ac_frame.lift()
        self._console_ac_visible = True

    def _console_autocomplete_hide(self, event=None) -> None:
        self.console_ac_frame.place_forget()
        self._console_ac_visible = False

    def _console_ac_up(self) -> None:
        cur = self.console_ac_listbox.curselection()
        idx = max(0, cur[0] - 1) if cur else self.console_ac_listbox.size() - 1
        self.console_ac_listbox.selection_clear(0, tk.END)
        self.console_ac_listbox.selection_set(idx)

    def _console_ac_down(self) -> None:
        cur = self.console_ac_listbox.curselection()
        idx = min(self.console_ac_listbox.size() - 1, cur[0] + 1) if cur else 0
        self.console_ac_listbox.selection_clear(0, tk.END)
        self.console_ac_listbox.selection_set(idx)

    def _console_autocomplete_select(self, event=None) -> None:
        cur = self.console_ac_listbox.curselection()
        if cur and cur[0] < len(self._console_ac_data):
            self.console_var.set(self._console_ac_data[cur[0]])
            self._console_autocomplete_hide()
            self.console_entry.focus_set()
            self.console_entry.icursor(tk.END)

    # ────────────────────────────────────────────────────────────────────────
    #  App control callbacks
    # ────────────────────────────────────────────────────────────────────────

    def _restart(self) -> None:
        self._do_shutdown(restart=True)

    def _quit(self) -> None:
        self._do_shutdown(restart=False)

    def _do_shutdown(self, restart: bool = False) -> None:
        """Graceful shutdown — save, log, then destroy."""
        # Remove log listener so we don't write to closed file
        if self._on_log_line in _log_listeners:
            _log_listeners.remove(self._on_log_line)

        # Cancel pending timers
        if self._autosave_id:
            try:
                self.root.after_cancel(self._autosave_id)
            except Exception:
                pass
        self._hide_typing_indicator()

        # Show console message
        self._append_console("\n[INFO] Backing up data...")

        # Save
        try:
            write_save(self.state.to_save_dict())
            self._append_console("[INFO] Save complete.")
        except Exception as e:
            self._append_console(f"[ERROR] Save failed: {e}")

        # Disconnect Discord
        if self.discord:
            try:
                self.discord.disconnect()
            except Exception:
                pass

        # Write final log line and close file
        try:
            _log_file.write(f"[{time.strftime('%H:%M:%S')}] [INFO] Session ended\n")
            _log_file.flush()
            _log_file.close()
        except Exception:
            pass

        if restart:
            self.root.destroy()
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Brief pause so the console message is readable, then destroy
            self.root.after(800, self.root.destroy)

    def _reload_config(self) -> None:
        global _cfg, TYPEWRITER_SPEED, DEFAULT_NEXT_LABEL
        _cfg = _load_client_config()
        TYPEWRITER_SPEED = _cfg.get("ui", {}).get("typewriter_speed", 0.03)
        DEFAULT_NEXT_LABEL = _cfg.get("ui", {}).get("default_next_label", "NEXT")
        _log("[INFO] Config reloaded")

    def _reload_dialogue(self) -> None:
        self.dm._blocks.clear()
        self.dm._id_map.clear()
        self._load_core_dialogue()
        self._load_mods()
        self._autocomplete_cache = []
        _log("[INFO] Dialogue reloaded")

    def _logs_clean(self) -> None:
        self.console_output.config(state=tk.NORMAL)
        self.console_output.delete(1.0, tk.END)
        self.console_output.config(state=tk.DISABLED)
        try:
            (LOGS_DIR / "console.log").write_text("", encoding="utf-8")
        except OSError:
            pass
        _log("[INFO] Logs cleared")

    def _logs_export(self, path: str) -> None:
        try:
            export_path = Path(path)
            export_path.parent.mkdir(parents=True, exist_ok=True)
            content = self.console_output.get(1.0, tk.END)
            export_path.write_text(content, encoding="utf-8")
            _log(f"[INFO] Logs exported to {path}")
        except OSError as e:
            _log(f"[ERROR] Export failed: {e}")

    def _save_quietly(self) -> None:
        """Silent background save (no log file close)."""
        try:
            write_save(self.state.to_save_dict())
        except Exception as e:
            _log(f"[ERROR] Autosave failed: {e}")

    # ────────────────────────────────────────────────────────────────────────
    #  Background tasks
    # ────────────────────────────────────────────────────────────────────────

    def _warmup_cache(self) -> None:
        config_files = list(CORE_DIR.rglob("*.yaml"))
        _cache.warmup(config_files)
        _cache.start_watcher(config_files)

    def _install_mod_async(self, source: str) -> None:
        """Run mod installation in a background thread to keep the GUI responsive."""
        def _worker():
            ok, msg = self.mm.install_mod(source, self.dm)
            # Schedule the log output back on the main thread so Tkinter is happy
            self.root.after(0, lambda: _log(msg))
        threading.Thread(target=_worker, daemon=True).start()

    def _connect_discord(self) -> None:
        if self.discord:
            self.discord.connect()

    # ────────────────────────────────────────────────────────────────────────
    #  Periodic autosave
    # ────────────────────────────────────────────────────────────────────────

    def _schedule_autosave(self) -> None:
        self._save_quietly()
        self._autosave_id = self.root.after(60_000, self._schedule_autosave)


# ── Console commands list (for autocomplete) ──────────────────────────────────
CONSOLE_COMMANDS: list[tuple[str, str]] = [
    ("client.version",           "Show client version"),
    ("client.restart",           "Restart the app"),
    ("client.quit",              "Quit the app"),
    ("client.config.reload",     "Reload client_config.yaml"),
    ("client.config.validate",   "Validate config files"),
    ("cache.clean",              "Clear in-memory cache"),
    ("chat.clear",               "Clear the chat display (keeps all data)"),
    ("logs.clean",               "Clear console log output"),
    ("logs.export",              "Export logs to a file"),
    ("mod.list",                 "List all loaded mods"),
    ("mod.install",              "Install a mod from a URL or local path"),
    ("mod.uninstall",            "Uninstall a mod by id"),
    ("mod.reload",               "Reload a mod by id"),
    ("mod.info",                 "Show mod info by id"),
    ("mod.validate",             "Validate a mod by id"),
    ("mod.enable",               "Enable a mod by id"),
    ("mod.disable",              "Disable a mod by id"),
    ("dialogue.list",            "List all loaded dialogue blocks"),
    ("dialogue.search",          "Search dialogue blocks by query"),
    ("dialogue.trigger",         "Manually trigger a dialogue block"),
    ("dialogue.reload",          "Reload all dialogue files"),
    ("dialogue.clean",           "Clean dialogue cache"),
    ("memory.dump",              "Dump all memory values"),
    ("memory.get",               "Get a memory value by path"),
    ("memory.clear",             "Clear a memory namespace (asks confirmation)"),
    ("memory.clean",             "Clean all non-essential memory"),
    ("bucko.affection",          "Show affection value"),
    ("bucko.clean",              "Run cache + logs + memory clean"),
    ("debug.mood",               "Show current mood values"),
    ("debug.interest",           "Show interest vector for a topic"),
    ("debug.hash.verify",        "Verify all memory entry hashes"),
    ("debug.triggers.list",      "List all loaded trigger labels"),
    ("debug.triggers.search",    "Search trigger labels"),
    ("discord.status",           "Show Discord RPC connection status"),
    ("discord.reconnect",        "Reconnect Discord RPC"),
    ("discord.setup",            "Show Discord RPC setup instructions"),
    ("help",                     "Show all commands"),
]

# ── Help text ─────────────────────────────────────────────────────────────────
HELP_TEXT = """
Bucko Console Commands
──────────────────────
client.version         client.restart        client.quit
client.config.reload   client.config.validate

cache.clean            chat.clear

logs.clean             logs.export [path]

mod.list               mod.install [path]    mod.uninstall [id]
mod.reload [id]        mod.info [id]         mod.validate [id]
mod.enable [id]        mod.disable [id]
mod.[id].clean         mod.[id].[command]

dialogue.list          dialogue.search [q]   dialogue.trigger [id]
dialogue.reload        dialogue.clean

memory.dump            memory.get [ns.key]   memory.clear [ns]
memory.clean

bucko.affection        bucko.clean

debug.mood             debug.interest [topic]
debug.hash.verify      debug.triggers.list   debug.triggers.search [q]

discord.status         discord.reconnect     discord.setup
""".strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    root = ttk.Window(themename=THEME)
    app = BuckoApp(root)

    # Autosave — track ID so it can be cancelled on quit
    app._autosave_id = root.after(60_000, app._schedule_autosave)

    root.protocol("WM_DELETE_WINDOW", app._quit)

    root.mainloop()


if __name__ == "__main__":
    main()
