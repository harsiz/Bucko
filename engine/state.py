"""
GameState — the single shared state object passed to BDLEngine and all subsystems.
"""
from typing import Any, Optional, Callable, TYPE_CHECKING
from engine.mood import MoodSystem, InterestSystem, AffectionSystem

if TYPE_CHECKING:
    from engine.dialogue import DialogueManager


class GameState:
    def __init__(
        self,
        save_data: dict,
        baseline: dict,
        decay_rate: float,
        config_loader: Callable[[str], Any],
        console_log: Callable[[str], None] = None,
    ):
        self._config_loader = config_loader
        self.console_log = console_log or print

        self.user_name: str = save_data.get("user", {}).get("name", "")
        self.memory: dict = save_data.get("memory", {
            "global": {}, "user": {}, "repeat": {}, "mod": {}
        })
        self.flags: dict = save_data.get("flags", {})
        self.counters: dict = save_data.get("counters", {})
        self.cycle_state: dict = save_data.get("cycle_state", {})

        # Subsystems
        self.mood = MoodSystem(baseline, decay_rate)
        if "mood_state" in save_data:
            self.mood.set_from_save(save_data["mood_state"])

        self.interests = InterestSystem(save_data.get("interests", {}))

        aff = save_data.get("affection", 0)
        hist = save_data.get("affection_history", [])
        self.affection = AffectionSystem(aff, hist)

        # Dialogue manager reference — set after construction
        self.dialogue_manager: Optional["DialogueManager"] = None

        # Per-block affection tracking (anti-exploit: one per block)
        self._block_affection_used = False

    def get_config_data(self, filename: str) -> Any:
        return self._config_loader(filename)

    def to_save_dict(self) -> dict:
        return {
            "meta": {
                "first_launch": False,
                "first_session_date": self.memory.get("global", {}).get("first_session_date", {}).get("value"),
                "client_version": 1,
            },
            "user": {"name": self.user_name},
            "memory": self.memory,
            "flags": self.flags,
            "counters": self.counters,
            "cycle_state": self.cycle_state,
            "mood_state": self.mood.to_dict(),
            "interests": self.interests.to_dict(),
            "affection": self.affection.internal_value,
            "affection_history": self.affection.to_dict()["history"],
        }

    def apply_affection_change(self, direction: str) -> None:
        """Apply affection change with one-per-block anti-exploit guard."""
        if self._block_affection_used:
            return
        if self.affection.change(direction):
            self._block_affection_used = True

    def reset_block_affection(self) -> None:
        """Call at start of each new dialogue block."""
        self._block_affection_used = False
