"""
BDL — Bucko Dialogue Language evaluator.
Parses {{expressions}} embedded in YAML string values.

Key design: if/elif/else/endif blocks SPAN multiple {{}} tokens with literal
text between them. We tokenise first, then process as a token stream so that
if-blocks are resolved before simple expressions.
"""
import re
import random
import time
import datetime as dt
from typing import Any, Optional, TYPE_CHECKING

try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

if TYPE_CHECKING:
    from engine.state import GameState

# Placeholder injected into text for inline {{wait:}} — decoded by the renderer
WAIT_PLACEHOLDER = "\x00WAIT:{:.3f}\x00"
WAIT_RE = re.compile(r"\x00WAIT:([0-9.]+)\x00")


class BDLEvaluationError(Exception):
    pass


class BDLEngine:
    def __init__(self, state: "GameState"):
        self.state = state

    # ──────────────────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────────────────

    def evaluate(self, text: str, context: dict = None) -> str:
        """Evaluate all BDL expressions in text and return the result string."""
        if "{{" not in text:
            return text
        ctx = context or {}
        tokens = _tokenize(text)
        return self._process_tokens(tokens, ctx)

    def extract_waits(self, text: str) -> list:
        """
        Split an evaluated string into segments: strings and float wait times.
        Returns e.g. ['hello ', 1.5, 'world'].
        """
        parts = []
        last = 0
        for m in WAIT_RE.finditer(text):
            chunk = text[last:m.start()]
            if chunk:
                parts.append(chunk)
            parts.append(float(m.group(1)))
            last = m.end()
        tail = text[last:]
        if tail:
            parts.append(tail)
        return parts if parts else [text]

    # ──────────────────────────────────────────────────────────────────────
    #  Token-stream processor
    # ──────────────────────────────────────────────────────────────────────

    def _process_tokens(self, tokens: list, ctx: dict) -> str:
        result = []
        i = 0
        while i < len(tokens):
            t_type, t_val = tokens[i]
            if t_type == "text":
                result.append(t_val)
                i += 1
            elif t_type == "expr":
                expr = t_val.strip()
                if expr.startswith("if "):
                    # Collect the full if-block token span
                    block_tokens, consumed = self._collect_if_block(tokens, i)
                    result.append(self._eval_if_block_tokens(block_tokens, ctx))
                    i += consumed
                else:
                    try:
                        val = self._eval_expr(expr, ctx)
                    except Exception:
                        val = ""
                    result.append(str(val))
                    i += 1
            else:
                i += 1
        return "".join(result)

    # ──────────────────────────────────────────────────────────────────────
    #  if / elif / else / endif  (text-spanning blocks)
    # ──────────────────────────────────────────────────────────────────────

    def _collect_if_block(self, tokens: list, start_idx: int) -> tuple[list, int]:
        """
        Collect tokens from {{if ...}} through {{endif}}, handling nesting.
        Returns (block_tokens, num_tokens_consumed).
        """
        block = []
        depth = 0
        i = start_idx
        while i < len(tokens):
            t_type, t_val = tokens[i]
            block.append((t_type, t_val))
            if t_type == "expr":
                stripped = t_val.strip()
                if stripped.startswith("if "):
                    depth += 1
                elif stripped == "endif":
                    depth -= 1
                    if depth == 0:
                        return block, i - start_idx + 1
            i += 1
        return block, i - start_idx

    def _eval_if_block_tokens(self, block_tokens: list, ctx: dict) -> str:
        """
        Evaluate a collected if/elif/else/endif token sequence.
        Returns the content of the first matching branch.
        """
        # Parse into sections: list of (condition_str_or_None, content_tokens)
        # condition_str is None for the else branch
        sections: list[tuple[Optional[str], list]] = []
        current_cond: Optional[str] = None
        current_content: list = []
        started = False

        for t_type, t_val in block_tokens:
            if t_type != "expr":
                if started:
                    current_content.append((t_type, t_val))
                continue

            stripped = t_val.strip()

            if stripped.startswith("if ") and not started:
                started = True
                current_cond = stripped[3:].strip()
                current_content = []
            elif stripped.startswith("elif "):
                sections.append((current_cond, current_content))
                current_cond = stripped[5:].strip()
                current_content = []
            elif stripped == "else":
                sections.append((current_cond, current_content))
                current_cond = None
                current_content = []
            elif stripped == "endif":
                sections.append((current_cond, current_content))
                break
            else:
                # Nested expression inside a branch
                current_content.append((t_type, t_val))

        # Find the first true branch
        for cond, content_tokens in sections:
            if cond is None:
                # else — always taken if we get here
                return self._process_tokens(content_tokens, ctx)
            if self._eval_condition(cond):
                return self._process_tokens(content_tokens, ctx)

        return ""

    def _eval_condition(self, cond: str) -> bool:
        """Evaluate a BDL condition string as a Python bool."""
        py_expr = self._to_python_expr(cond)
        try:
            return bool(eval(py_expr, {"__builtins__": {}}, {}))
        except Exception:
            return False

    def _to_python_expr(self, expr: str) -> str:
        """Translate BDL condition tokens to safe Python-evaluatable expression."""
        result = expr

        # datetime
        now = dt.datetime.now()
        result = result.replace("datetime.hour", str(now.hour))
        result = result.replace("datetime.minute", str(now.minute))
        result = result.replace("datetime.day_of_week", f'"{now.strftime("%A")}"')
        result = result.replace("datetime.date", f'"{now.strftime("%Y-%m-%d")}"')
        result = result.replace("datetime.timestamp", str(int(time.time())))

        # mood
        mood = self.state.mood.get()
        for k, v in mood.items():
            result = result.replace(f"mood.{k}", str(v))

        # affection
        result = result.replace("memory.affection", str(self.state.affection.display_value))

        # memory.repeat[...].field
        result = re.sub(
            r"memory\.repeat\['([^']+)'\]\.(\w+)",
            lambda m: str(self._get_repeat(m.group(1), m.group(2))),
            result
        )

        # interest['topic'].field
        result = re.sub(
            r"interest\['([^']+)'\]\.(\w+)",
            lambda m: str(self._get_interest(m.group(1), m.group(2))),
            result
        )

        # counter.get: 'key'
        result = re.sub(
            r"counter\.get:\s*'([^']+)'",
            lambda m: str(self.state.counters.get(m.group(1), 0)),
            result
        )

        # flag.get: 'key'
        result = re.sub(
            r"flag\.get:\s*'([^']+)'",
            lambda m: str(bool(self.state.flags.get(m.group(1), False))),
            result
        )

        # memory.namespace.key  (must come after repeat/affection replacements)
        result = re.sub(
            r"memory\.(\w+)\.(\w+)",
            lambda m: str(self._get_memory(m.group(1), m.group(2))),
            result
        )

        return result

    # ──────────────────────────────────────────────────────────────────────
    #  Simple expression router
    # ──────────────────────────────────────────────────────────────────────

    def _eval_expr(self, expr: str, ctx: dict) -> Any:
        expr = expr.strip()

        if expr.startswith("dep:"):
            return self._eval_dep(expr[4:].strip())

        if expr.startswith("choice.cycle:"):
            return self._eval_choice(expr[13:].strip(), cycle=True)

        if expr.startswith("choice:"):
            return self._eval_choice(expr[7:].strip(), cycle=False)

        if expr.startswith("wait:"):
            secs = float(expr[5:].strip())
            return WAIT_PLACEHOLDER.format(secs)

        if expr.startswith("datetime."):
            return self._eval_datetime(expr[9:])

        if expr.startswith("memory.set:"):
            return self._eval_memory_set(expr[11:].strip())

        if expr.startswith("memory.repeat["):
            return self._eval_memory_repeat(expr)

        if expr == "memory.affection":
            return self.state.affection.display_value

        if expr.startswith("memory."):
            return self._eval_memory_get(expr[7:])

        if expr.startswith("flag.set:"):
            self.state.flags[expr[9:].strip().strip("'")] = True
            return ""

        if expr.startswith("flag.get:"):
            key = expr[9:].strip().strip("'")
            return self.state.flags.get(key, False)

        if expr.startswith("counter.increment:"):
            key = expr[18:].strip().strip("'")
            self.state.counters[key] = self.state.counters.get(key, 0) + 1
            return ""

        if expr.startswith("counter.get:"):
            key = expr[12:].strip().strip("'")
            return self.state.counters.get(key, 0)

        if expr.startswith("math:"):
            return self._eval_math(expr[5:].strip())

        if expr.startswith("upper:"):
            return str(self._eval_expr(expr[6:].strip(), ctx)).upper()

        if expr.startswith("lower:"):
            return str(self._eval_expr(expr[6:].strip(), ctx)).lower()

        if expr.startswith("capitalize:"):
            return str(self._eval_expr(expr[11:].strip(), ctx)).capitalize()

        if expr.startswith("random.int:"):
            return self._eval_random_int(expr[11:].strip())

        if expr.startswith("random.float:"):
            return self._eval_random_float(expr[13:].strip())

        if expr.startswith("request:"):
            return self._eval_request(expr[8:].strip())

        if expr.startswith("mood."):
            key = expr[5:]
            return self.state.mood.get().get(key, 0)

        if expr.startswith("interest["):
            return self._eval_interest(expr)

        # elif / else / endif appearing as bare expressions — consumed by if-block
        # collector but just in case
        if expr in ("else", "endif") or expr.startswith("elif "):
            return ""

        return ""

    # ──────────────────────────────────────────────────────────────────────
    #  dep: filename.yaml | key.path
    # ──────────────────────────────────────────────────────────────────────

    def _eval_dep(self, expr: str) -> Any:
        if "|" not in expr:
            raise BDLEvaluationError(f"dep missing '|': {expr}")
        filename, keypath = expr.split("|", 1)
        data = self.state.get_config_data(filename.strip())
        return self._navigate_path(data, keypath.strip())

    # ──────────────────────────────────────────────────────────────────────
    #  choice / choice.cycle
    # ──────────────────────────────────────────────────────────────────────

    def _eval_choice(self, expr: str, cycle: bool) -> str:
        options = _parse_list(expr)
        if not options:
            return ""

        if cycle:
            key = f"_cycle_{hash(expr)}"
            state = self.state.cycle_state.setdefault(key, {"used": []})
            used = state["used"]
            remaining = [o for o in options if o not in used]
            if not remaining:
                remaining = list(options)
                state["used"] = []
            chosen = random.choice(remaining)
            state["used"].append(chosen)
        else:
            chosen = random.choice(options)

        # If chosen is a loaded dialogue ID, return it for the caller to resolve
        if self.state.dialogue_manager:
            block = self.state.dialogue_manager.get_dialogue_by_id(chosen)
            if block:
                return chosen  # caller handles resolution
        return chosen

    # ──────────────────────────────────────────────────────────────────────
    #  memory
    # ──────────────────────────────────────────────────────────────────────

    def _eval_memory_get(self, path: str) -> Any:
        parts = path.split(".", 1)
        ns = parts[0]
        key = parts[1] if len(parts) > 1 else ""
        if ns == "affection":
            return self.state.affection.display_value
        return self._get_memory(ns, key)

    def _get_memory(self, ns: str, key: str) -> Any:
        store = self.state.memory.get(ns, {})
        val = store.get(key)
        if isinstance(val, dict) and "value" in val:
            return val["value"]
        return val if val is not None else ""

    def _get_repeat(self, dialogue_id: str, field: str) -> Any:
        entry = self.state.memory.get("repeat", {}).get(dialogue_id, {})
        return entry.get(field, 0)

    def _get_interest(self, topic: str, field: str) -> Any:
        iv = self.state.interests.get(topic)
        return iv.get(field, 0) if iv else 0

    def _eval_memory_set(self, expr: str) -> str:
        if "|" not in expr:
            return ""
        path, value_expr = expr.split("|", 1)
        path = path.strip()
        value_expr = value_expr.strip()

        if value_expr.startswith("math:"):
            value = self._eval_math(value_expr[5:].strip())
        else:
            value = value_expr.strip("'\"")

        parts = path.split(".", 1)
        ns = parts[0]
        key = parts[1] if len(parts) > 1 else path

        ns_store = self.state.memory.setdefault(ns, {})
        ns_store[key] = {"value": value, "_ts": time.time()}
        return ""

    def _eval_memory_repeat(self, expr: str) -> Any:
        m = re.match(r"memory\.repeat\['([^']+)'\]\.(\w+)", expr)
        if m:
            return self._get_repeat(m.group(1), m.group(2))
        return ""

    def _eval_interest(self, expr: str) -> Any:
        m = re.match(r"interest\['([^']+)'\]\.(\w+)", expr)
        if m:
            return self._get_interest(m.group(1), m.group(2))
        return 0

    # ──────────────────────────────────────────────────────────────────────
    #  datetime
    # ──────────────────────────────────────────────────────────────────────

    def _eval_datetime(self, key: str) -> Any:
        now = dt.datetime.now()
        return {
            "hour": now.hour,
            "minute": f"{now.minute:02d}",
            "day_of_week": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": int(time.time()),
        }.get(key, "")

    # ──────────────────────────────────────────────────────────────────────
    #  math
    # ──────────────────────────────────────────────────────────────────────

    def _eval_math(self, expr: str) -> Any:
        py_expr = self._to_python_expr(expr)
        safe = {"abs": abs, "min": min, "max": max, "round": round, "int": int, "float": float}
        try:
            return eval(py_expr, {"__builtins__": {}}, safe)
        except Exception:
            return 0

    # ──────────────────────────────────────────────────────────────────────
    #  random
    # ──────────────────────────────────────────────────────────────────────

    def _eval_random_int(self, expr: str) -> int:
        m = re.match(r"(\d+)\s*-\s*(\d+)", expr)
        return random.randint(int(m.group(1)), int(m.group(2))) if m else 0

    def _eval_random_float(self, expr: str) -> float:
        m = re.match(r"([0-9.]+)\s*-\s*([0-9.]+)", expr)
        return random.uniform(float(m.group(1)), float(m.group(2))) if m else 0.0

    # ──────────────────────────────────────────────────────────────────────
    #  HTTP request
    # ──────────────────────────────────────────────────────────────────────

    def _eval_request(self, expr: str) -> str:
        if not HAS_REQUESTS:
            return ""
        m = re.match(r"(GET|POST)\s+'([^']+)'\s*\|\s*(.*?)(?:\s+on_fail:\s*(.*))?$", expr, re.DOTALL)
        if not m:
            return ""
        method, url, path_expr = m.group(1), m.group(2), m.group(3).strip()
        on_fail = (m.group(4) or "skip").strip()
        log = self.state.console_log
        try:
            resp = _requests.request(method, url, timeout=5)
            log(f"[REQUEST] {method} {url} → {resp.status_code} {resp.reason}")
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            data = resp.json()
            result = self._navigate_response(data, path_expr)
            return str(result)
        except Exception:
            if on_fail == "skip":
                return "\x00SKIP\x00"
            return on_fail.strip("'\"")

    def _navigate_response(self, data: Any, path: str) -> Any:
        for str_key, int_key in re.findall(r"\['([^']+)'\]|\[(\d+)\]", path):
            k = str_key if str_key else int(int_key)
            data = data[k]
        return data

    # ──────────────────────────────────────────────────────────────────────
    #  dep key navigation
    # ──────────────────────────────────────────────────────────────────────

    def _navigate_path(self, data: Any, path: str) -> Any:
        if not path or data is None:
            return data
        parts = re.split(r"\.(?![^[]*\])", path)
        for part in parts:
            if data is None:
                return ""
            bracket = re.match(r"(\w+)\['([^']+)'\]", part)
            if bracket:
                data = data.get(bracket.group(1), {})
                data = data.get(bracket.group(2), "")
            elif isinstance(data, dict):
                data = data.get(part, "")
            else:
                return ""
        return data


# ──────────────────────────────────────────────────────────────────────────
#  Tokeniser
# ──────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[tuple[str, str]]:
    """
    Split text into ('text', literal) and ('expr', content) tokens.
    Each {{...}} block becomes one 'expr' token.
    """
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        start = text.find("{{", i)
        if start == -1:
            tokens.append(("text", text[i:]))
            break
        if start > i:
            tokens.append(("text", text[i:start]))
        end = text.find("}}", start + 2)
        if end == -1:
            tokens.append(("text", text[start:]))
            break
        tokens.append(("expr", text[start + 2:end]))
        i = end + 2
    return tokens


def _parse_list(expr: str) -> list[str]:
    """Parse ['a', 'b', 'c'] style list from a BDL choice expression."""
    expr = expr.strip()
    if expr.startswith("[") and expr.endswith("]"):
        expr = expr[1:-1]
    items = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", expr)
    return [s if s else d for s, d in items]
