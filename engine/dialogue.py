"""
Dialogue manager — loads YAML dialogue blocks, resolves triggers, chains blocks.
"""
import re
import time
import hashlib
import random
from pathlib import Path
from typing import Optional, Any
import yaml

from engine.bdl import BDLEngine
from engine.state import GameState


def _ns_hash(ns_id: str) -> str:
    """Short hash for namespace::id strings (collision prevention)."""
    return hashlib.sha256(ns_id.encode()).hexdigest()[:12]


class FollowUpBlock:
    """
    A context-aware follow-up response. Only fires when the user replies to
    the specific block that declared it. Can be nested arbitrarily deep.
    """
    def __init__(self, data: dict, namespace: str, parent_id: str, idx: int):
        self.namespace = namespace
        self.raw_id = f"{parent_id}_fu{idx}"
        self.full_id = f"{namespace}::{self.raw_id}"
        self.triggers: list[dict] = data.get("triggers", [])
        self.lines: list = data.get("lines", [])
        self.mood_effect: dict = data.get("mood_effect", {})
        self.expression: str = data.get("expression", "")
        self.next_id: str = data.get("next", "")
        self.input_capture: bool = False
        self.input_store: str = ""
        # Nested follow-ups
        self.follow_ups: list["FollowUpBlock"] = [
            FollowUpBlock(fu, namespace, self.raw_id, i)
            for i, fu in enumerate(data.get("follow_ups", []))
        ]

    def matches_input(self, user_input: str) -> bool:
        lowered = user_input.lower().strip()
        for t in self.triggers:
            if not isinstance(t, dict):
                continue
            # YAML parses unquoted yes/no/true/false as booleans — coerce to str
            if "exact" in t and lowered == str(t["exact"]).lower():
                return True
            if "keywords" in t:
                for kw in t["keywords"]:
                    if str(kw).lower() in lowered:
                        return True
            if "pattern" in t:
                try:
                    if re.search(t["pattern"], lowered):
                        return True
                except re.error:
                    pass
        return False


class DialogueBlock:
    def __init__(self, data: dict, namespace: str):
        self.raw_id: str = data.get("dialogue_id", "")
        self.namespace: str = namespace
        self.full_id: str = f"{namespace}::{self.raw_id}" if self.raw_id else ""
        self.hash_id: str = _ns_hash(self.full_id) if self.full_id else ""

        self.triggers: list[dict] = data.get("triggers", [])
        # priority, condition, cooldown are block-level fields (not inside triggers list)
        self.priority: int = int(data.get("priority", 0))
        self.trigger_condition: str = data.get("condition", "")
        self.cooldown_sec: int = int(data.get("cooldown", 0))
        self.last_triggered: float = 0.0

        self.mood_condition: str = data.get("mood_condition", "")
        self.lines: list = data.get("lines", [])
        self.next_id: str = data.get("next", "")
        self.next_label: str = data.get("next_label", "")
        self.mood_effect: dict = data.get("mood_effect", {})
        self.on_repeat: dict = data.get("on_repeat", {})
        self.expression: str = data.get("expression", "")
        self.input_capture: bool = data.get("input_capture", False)
        self.input_store: str = data.get("input_store", "")

        # Follow-up context: replies that only fire when user responds to THIS block
        self.follow_ups: list[FollowUpBlock] = [
            FollowUpBlock(fu, namespace, self.raw_id, i)
            for i, fu in enumerate(data.get("follow_ups", []))
        ]

    def matches_input(self, user_input: str) -> bool:
        """Check if any trigger matches user_input. Returns True/False."""
        lowered = user_input.lower().strip()
        for t in self.triggers:
            if not isinstance(t, dict):
                continue
            if "exact" in t:
                if lowered == str(t["exact"]).lower():
                    return True
            if "keywords" in t:
                for kw in t["keywords"]:
                    if str(kw).lower() in lowered:
                        return True
            if "pattern" in t:
                try:
                    if re.search(t["pattern"], lowered):
                        return True
                except re.error:
                    pass
        return False

    def trigger_type_priority(self) -> int:
        """Specificity: exact=3, pattern=2, keywords=1, none=0."""
        best = 0
        for t in self.triggers:
            if not isinstance(t, dict):
                continue
            if "exact" in t:
                best = max(best, 3)
            elif "pattern" in t:
                best = max(best, 2)
            elif "keywords" in t:
                best = max(best, 1)
        return best

    def is_on_cooldown(self) -> bool:
        if self.cooldown_sec <= 0:
            return False
        return (time.time() - self.last_triggered) < self.cooldown_sec

    def get_trigger_labels(self) -> list[str]:
        """Return human-readable trigger labels for autocomplete."""
        labels = []
        for t in self.triggers:
            if not isinstance(t, dict):
                continue
            if "exact" in t:
                labels.append(t["exact"])
            if "keywords" in t:
                labels.extend(t["keywords"])
        return labels


class DialogueManager:
    def __init__(self, state: GameState):
        self.state = state
        self.bdl = BDLEngine(state)
        self._blocks: list[DialogueBlock] = []
        self._id_map: dict[str, DialogueBlock] = {}  # full_id -> block
        self._no_match_expr: str = ""
        self._no_match_responses: list[DialogueBlock] = []
        state.dialogue_manager = self

    # ------------------------------------------------------------------ #
    #  Loading
    # ------------------------------------------------------------------ #

    def load_yaml(self, path: Path, namespace: str) -> int:
        """Load dialogue blocks from a YAML file. Returns count loaded."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except (yaml.YAMLError, OSError) as e:
            self.state.console_log(f"[ERROR] Failed to load {path}: {e}")
            return 0

        if not isinstance(data, dict):
            return 0

        count = 0
        for block_data in data.get("dialogues", []):
            block = DialogueBlock(block_data, namespace)
            if block.full_id:
                self._blocks.append(block)
                self._id_map[block.full_id] = block
                self._id_map[block.raw_id] = block  # shorthand
                count += 1

        # Load no_match_responses
        for block_data in data.get("no_match_responses", []):
            block = DialogueBlock(block_data, namespace)
            if block.full_id:
                self._no_match_responses.append(block)
                self._id_map[block.full_id] = block
                self._id_map[block.raw_id] = block

        # Load no_match expression
        if "no_match" in data:
            nm = data["no_match"]
            if isinstance(nm, list) and nm:
                self._no_match_expr = nm[0]
            elif isinstance(nm, str):
                self._no_match_expr = nm

        return count

    # ------------------------------------------------------------------ #
    #  Lookup
    # ------------------------------------------------------------------ #

    def get_dialogue_by_id(self, dialogue_id: str) -> Optional[DialogueBlock]:
        return self._id_map.get(dialogue_id)

    def get_all_trigger_labels(self) -> list[tuple[str, str]]:
        """Returns list of (label, source_tag) for autocomplete."""
        result = []
        for block in self._blocks:
            ns = block.namespace
            tag = f"[{ns}]"
            for label in block.get_trigger_labels():
                result.append((label, tag))
        return result

    # ------------------------------------------------------------------ #
    #  Matching
    # ------------------------------------------------------------------ #

    def find_match(self, user_input: str) -> Optional[DialogueBlock]:
        """Find best-matching dialogue block for user input."""
        candidates = []
        for block in self._blocks:
            if not block.triggers:
                continue
            if block.is_on_cooldown():
                continue
            if not block.matches_input(user_input):
                continue
            if block.mood_condition:
                if not self._check_condition(block.mood_condition):
                    continue
            if block.trigger_condition:
                if not self._check_condition(block.trigger_condition):
                    continue
            candidates.append(block)

        if not candidates:
            return None

        # Sort by: priority DESC, then specificity DESC
        candidates.sort(
            key=lambda b: (b.priority, b.trigger_type_priority()),
            reverse=True
        )
        # If multiple blocks tie on (priority, specificity), pick randomly.
        # This prevents load-order bias when two mods both handle the same trigger.
        top_score = (candidates[0].priority, candidates[0].trigger_type_priority())
        tied = [b for b in candidates if (b.priority, b.trigger_type_priority()) == top_score]
        return random.choice(tied)

    def _check_condition(self, cond_str: str) -> bool:
        """Evaluate a BDL condition string (may include {{ }})."""
        # Strip outer {{ }} if present
        inner = cond_str.strip()
        if inner.startswith("{{") and inner.endswith("}}"):
            inner = inner[2:-2].strip()
        # Strip leading 'if '
        if inner.startswith("if "):
            inner = inner[3:].strip()
        return self.bdl._eval_condition(inner)

    # ------------------------------------------------------------------ #
    #  No-match
    # ------------------------------------------------------------------ #

    def get_no_match_block(self) -> Optional[DialogueBlock]:
        """Return a random no-match response block."""
        if self._no_match_responses:
            return random.choice(self._no_match_responses)
        return None

    # ------------------------------------------------------------------ #
    #  Repeat tracking
    # ------------------------------------------------------------------ #

    def record_repeat(self, block: DialogueBlock) -> int:
        """Record that this block was triggered. Returns repeat count."""
        key = block.full_id
        repeat_store = self.state.memory.setdefault("repeat", {})
        entry = repeat_store.setdefault(key, {"count": 0, "last_time": 0})
        entry["count"] = entry.get("count", 0) + 1
        entry["last_time"] = time.time()
        return entry["count"]

    def get_repeat_count(self, block: DialogueBlock) -> int:
        repeat_store = self.state.memory.get("repeat", {})
        return repeat_store.get(block.full_id, {}).get("count", 0)

    # ------------------------------------------------------------------ #
    #  Line rendering
    # ------------------------------------------------------------------ #

    def render_lines(self, block: DialogueBlock) -> list:
        """
        Evaluate BDL in all lines and return a list of render items:
        - str: normal text line
        - ("pause", float): pause item
        - ("input_capture", str): input capture with store key
        """
        result = []
        for line in block.lines:
            if isinstance(line, dict) and "pause" in line:
                result.append(("pause", float(line["pause"])))
            elif isinstance(line, str):
                if line == "{{memory.set:":
                    continue
                evaluated = self.bdl.evaluate(line)
                if "\x00SKIP\x00" in evaluated:
                    continue  # HTTP on_fail: skip
                result.append(evaluated)
            # Ignore unknown line types

        # If this block captures user input, append a capture sentinel as the last item
        if block.input_capture and block.input_store:
            result.append(("input_capture", block.input_store))

        return result

    def resolve_next(self, block: DialogueBlock) -> Optional["DialogueBlock"]:
        """Resolve the next block from block.next_id."""
        if not block.next_id:
            return None
        # Check for conditional next
        next_id = block.next_id.strip()
        if "{{" in next_id:
            evaluated = self.bdl.evaluate(next_id).strip()
            next_id = evaluated

        if not next_id:
            return None

        # Try direct lookup
        found = self.get_dialogue_by_id(next_id)
        if found:
            return found

        # Try namespace-qualified
        if "::" not in next_id:
            # try with block's namespace
            full = f"{block.namespace}::{next_id}"
            found = self.get_dialogue_by_id(full)
            if found:
                return found
        return None

    def apply_mood_effect(self, block: DialogueBlock) -> None:
        """Apply the block's mood_effect to the mood system."""
        effect = dict(block.mood_effect)
        affection_dir = effect.pop("affection", None)
        if effect:
            self.state.mood.apply_effect(effect)
        if affection_dir in ("increase", "decrease"):
            self.state.apply_affection_change(affection_dir)
