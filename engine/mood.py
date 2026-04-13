"""
Mood system — 4D vector: energy, patience, chaos, warmth.
Interest vectors — 4D: depth, frequency, recency, sentiment.
Affection system with anti-exploit curve.
"""
import time
import math
from typing import Optional


MOOD_KEYS = ("energy", "patience", "chaos", "warmth")
INTEREST_KEYS = ("depth", "frequency", "recency", "sentiment")

# Affection curve config
AFFECTION_MAX_INTERNAL = 1_000_000
AFFECTION_DISPLAY_MAX = 1000
AFFECTION_HISTORY_SIZE = 5


class MoodSystem:
    def __init__(self, baseline: dict, decay_rate: float = 1.0):
        self.baseline = {k: float(baseline.get(k, 50)) for k in MOOD_KEYS}
        self.decay_rate = decay_rate
        self._state = dict(self.baseline)
        self._last_decay = time.time()

    def get(self) -> dict:
        self._apply_decay()
        return dict(self._state)

    def apply_effect(self, effect: dict) -> None:
        """Apply a mood_effect dict (e.g. {'patience': -15, 'chaos': +10})."""
        for key in MOOD_KEYS:
            if key in effect:
                delta = effect[key]
                if isinstance(delta, str):
                    delta = float(delta.replace("+", ""))
                self._state[key] = max(0.0, min(100.0, self._state[key] + float(delta)))

    def set_from_save(self, state: dict) -> None:
        for k in MOOD_KEYS:
            if k in state:
                self._state[k] = float(state[k])

    def to_dict(self) -> dict:
        return dict(self._state)

    @property
    def label(self) -> str:
        """Single-word mood summary derived from the 4D state vector."""
        s = self._state
        e, p, c, w = s["energy"], s["patience"], s["chaos"], s["warmth"]
        if p <= 25:
            return "angry"
        if p <= 40:
            return "annoyed"
        if e <= 25:
            return "tired"
        if c >= 80:
            return "chaotic"
        if w >= 80 and e >= 70:
            return "cheerful"
        if w >= 65 and e >= 55:
            return "happy"
        if w <= 30:
            return "cold"
        if e >= 80:
            return "hyper"
        if c >= 60:
            return "playful"
        if e <= 40:
            return "mellow"
        return "neutral"

    def _apply_decay(self) -> None:
        now = time.time()
        elapsed_minutes = (now - self._last_decay) / 60.0
        if elapsed_minutes < 0.01:
            return
        for k in MOOD_KEYS:
            delta = self.baseline[k] - self._state[k]
            step = self.decay_rate * elapsed_minutes
            if abs(delta) <= step:
                self._state[k] = self.baseline[k]
            else:
                self._state[k] += step * (1 if delta > 0 else -1)
        self._last_decay = now


class InterestSystem:
    def __init__(self, data: dict):
        # data: {topic: {depth, frequency, recency, sentiment}}
        self._interests: dict[str, dict] = {}
        for topic, vals in data.items():
            self._interests[topic] = {
                "depth": float(vals.get("depth", 0)),
                "frequency": int(vals.get("frequency", 0)),
                "recency": float(vals.get("recency", 0)),
                "sentiment": float(vals.get("sentiment", 0.0)),
            }

    def get(self, topic: str) -> Optional[dict]:
        return self._interests.get(topic)

    def get_all(self) -> dict:
        return dict(self._interests)

    def mention(self, topic: str, sentiment_delta: float = 0.0) -> None:
        """Called when a topic is brought up in conversation."""
        now = time.time()
        if topic not in self._interests:
            self._interests[topic] = {
                "depth": 1.0,
                "frequency": 1,
                "recency": now,
                "sentiment": max(-1.0, min(1.0, sentiment_delta)),
            }
        else:
            iv = self._interests[topic]
            iv["frequency"] += 1
            iv["recency"] = now
            iv["depth"] = min(1000.0, iv["depth"] + 1.0)
            iv["sentiment"] = max(-1.0, min(1.0,
                iv["sentiment"] * 0.9 + sentiment_delta * 0.1))

    def to_dict(self) -> dict:
        return {t: dict(v) for t, v in self._interests.items()}


class AffectionSystem:
    def __init__(self, internal_value: int = 0, history: list = None):
        self._value = max(0, min(AFFECTION_MAX_INTERNAL, int(internal_value)))
        # history: list of up to 5 recent delta amounts (absolute values)
        self._history: list[int] = list(history or [])

    @property
    def display_value(self) -> int:
        return self._value // 1000

    @property
    def internal_value(self) -> int:
        return self._value

    def _compute_delta(self, direction: str) -> int:
        """
        Compute the delta for an increase/decrease.
        Curve: closer to max = smaller delta.
        """
        ratio = self._value / AFFECTION_MAX_INTERNAL
        # Sigmoid-like: delta shrinks as ratio approaches 1
        base = 500  # base delta
        delta = int(base * (1.0 - ratio ** 0.5))
        delta = max(1, delta)
        if direction == "decrease":
            # Decreases also shrink near max (comfort effect)
            delta = int(delta * (0.3 + 0.7 * ratio))
            delta = max(1, delta)
        return delta

    def _anti_exploit_check(self, delta: int) -> bool:
        """
        Returns True if this change should be ALLOWED.
        Blocked if delta exceeds mean of last 5 changes.
        """
        if len(self._history) < 2:
            return True
        mean = sum(self._history) / len(self._history)
        return delta <= mean * 1.5  # 50% tolerance

    def change(self, direction: str) -> bool:
        """
        Apply an affection increase or decrease.
        Returns True if change was applied, False if blocked.
        """
        if direction not in ("increase", "decrease"):
            return False
        delta = self._compute_delta(direction)
        if not self._anti_exploit_check(delta):
            return False  # silently ignored

        if direction == "increase":
            self._value = min(AFFECTION_MAX_INTERNAL, self._value + delta)
        else:
            self._value = max(0, self._value - delta)

        self._history.append(delta)
        if len(self._history) > AFFECTION_HISTORY_SIZE:
            self._history.pop(0)
        return True

    def to_dict(self) -> dict:
        return {
            "value": self._value,
            "history": self._history,
        }
