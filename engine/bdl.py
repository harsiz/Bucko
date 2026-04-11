"""
BDL — Bucko Dialogue Language evaluator.
Parses {{expressions}} embedded in YAML string values.
"""
import re
import random
import time
import math
import datetime as dt
import requests
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.state import GameState

# Matches {{...}} blocks, non-greedy, allowing newlines
BDL_PATTERN = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

# Seconds per character wait in typewriter — injected externally for {{wait:}}
WAIT_PLACEHOLDER = "\x00WAIT:{:.3f}\x00"
WAIT_RE = re.compile(r"\x00WAIT:([0-9.]+)\x00")


class BDLEvaluationError(Exception):
    pass


class BDLEngine:
    def __init__(self, state: "GameState"):
        self.state = state

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def evaluate(self, text: str, context: dict = None) -> str:
        """
        Evaluate all {{...}} expressions in text and return the result.
        Inline {{wait:}} becomes a special placeholder decoded by the renderer.
        """
        context = context or {}

        def replacer(match):
            expr = match.group(1).strip()
            try:
                return str(self._eval_expr(expr, context))
            except BDLEvaluationError:
                return ""
            except Exception:
                return ""

        return BDL_PATTERN.sub(replacer, text)

    def extract_waits(self, text: str) -> list:
        """
        Split an evaluated string into segments: strings and float wait times.
        Returns a list like ['hello ', 1.5, 'world'].
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

    # ------------------------------------------------------------------ #
    #  Expression router
    # ------------------------------------------------------------------ #

    def _eval_expr(self, expr: str, ctx: dict) -> Any:
        expr = expr.strip()

        if expr.startswith("dep:"):
            return self._eval_dep(expr[4:].strip())

        if expr.startswith("if "):
            return self._eval_if_block(expr, ctx)

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
            mood = self.state.mood.get()
            return mood.get(key, 0)

        if expr == "memory.affection":
            return self.state.affection.display_value

        if expr.startswith("interest["):
            return self._eval_interest(expr)

        # Bare counter/flag reference (from older shorthand)
        return ""

    # ------------------------------------------------------------------ #
    #  dep: filename.yaml | key.path
    # ------------------------------------------------------------------ #

    def _eval_dep(self, expr: str) -> Any:
        if "|" not in expr:
            raise BDLEvaluationError(f"dep expression missing '|': {expr}")
        filename, keypath = expr.split("|", 1)
        filename = filename.strip()
        keypath = keypath.strip()
        data = self.state.get_config_data(filename)
        return self._navigate_path(data, keypath)

    # ------------------------------------------------------------------ #
    #  if / elif / else / endif
    # ------------------------------------------------------------------ #

    def _eval_if_block(self, expr: str, ctx: dict) -> str:
        # Minimal line: "if COND"  (no elif/else in single expr — those appear in full line text)
        # When used in a full text line, the entire line content between {{ }} is the block.
        # Format: if COND content [elif COND content] [else content] endif
        tokens = re.split(r'\b(elif|else|endif)\b', expr)
        # tokens[0] = "if COND content"
        # Remainder alternates: keyword, content
        result = ""
        branch_taken = False

        first = tokens[0].strip()
        if first.startswith("if "):
            rest = first[3:].strip()
            # Split on first whitespace-only? Actually condition can be complex.
            # Strategy: evaluate condition which is everything up to the content
            # We separate condition from content by looking for }} end — but we're already inside
            # Use a heuristic: condition ends at first }} equivalent token boundary.
            # Actually the full if block is already extracted from {{...}}, so parse carefully.
            cond, content = self._split_cond_content(rest)
            if self._eval_condition(cond):
                result = self.evaluate(content.strip(), ctx)
                branch_taken = True

        i = 1
        while i < len(tokens):
            kw = tokens[i].strip()
            content = tokens[i + 1].strip() if i + 1 < len(tokens) else ""
            i += 2
            if kw == "elif" and not branch_taken:
                cond, body = self._split_cond_content(content)
                if self._eval_condition(cond):
                    result = self.evaluate(body.strip(), ctx)
                    branch_taken = True
            elif kw == "else" and not branch_taken:
                result = self.evaluate(content.strip(), ctx)
                branch_taken = True
            elif kw == "endif":
                break

        return result

    def _split_cond_content(self, text: str) -> tuple[str, str]:
        """
        Split 'CONDITION content text here' where condition is a logical expression.
        Heuristic: condition ends after a balanced expression that evaluates as bool.
        We scan tokens to find where condition keywords end.
        """
        # Condition tokens: identifiers, operators, literals, brackets
        # Content is everything after the condition expression
        # Simple approach: find the first 'word' boundary after a valid condition
        cond_end = _find_condition_end(text)
        return text[:cond_end].strip(), text[cond_end:].strip()

    def _eval_condition(self, cond: str) -> bool:
        """Evaluate a BDL condition string as a Python bool expression."""
        # Replace BDL-specific tokens with Python equivalents
        py_expr = self._condition_to_python(cond)
        try:
            return bool(eval(py_expr, {"__builtins__": {}}, self._build_eval_namespace()))
        except Exception:
            return False

    def _condition_to_python(self, cond: str) -> str:
        """Convert BDL condition syntax to Python-evaluatable expression."""
        result = cond

        # Replace datetime references
        now = dt.datetime.now()
        result = result.replace("datetime.hour", str(now.hour))
        result = result.replace("datetime.minute", str(now.minute))
        result = result.replace("datetime.day_of_week", f'"{now.strftime("%A")}"')
        result = result.replace("datetime.date", f'"{now.strftime("%Y-%m-%d")}"')
        result = result.replace("datetime.timestamp", str(int(time.time())))

        # Replace mood references
        mood = self.state.mood.get()
        for k, v in mood.items():
            result = result.replace(f"mood.{k}", str(v))

        # Replace memory.affection
        result = result.replace("memory.affection", str(self.state.affection.display_value))

        # Replace memory.global.x
        result = re.sub(
            r"memory\.global\.(\w+)",
            lambda m: str(self._get_memory("global", m.group(1))),
            result
        )

        # Replace memory.repeat[...].count / .last_time
        result = re.sub(
            r"memory\.repeat\['([^']+)'\]\.(\w+)",
            lambda m: str(self._get_repeat(m.group(1), m.group(2))),
            result
        )

        # Replace interest[...].field
        result = re.sub(
            r"interest\['([^']+)'\]\.(\w+)",
            lambda m: str(self._get_interest(m.group(1), m.group(2))),
            result
        )

        # Replace counter.get: 'x'
        result = re.sub(
            r"counter\.get:\s*'([^']+)'",
            lambda m: str(self.state.counters.get(m.group(1), 0)),
            result
        )

        # Replace flag.get: 'x'
        result = re.sub(
            r"flag\.get:\s*'([^']+)'",
            lambda m: str(bool(self.state.flags.get(m.group(1), False))),
            result
        )

        # Replace memory.global.times_talked style shorthand
        result = re.sub(
            r"memory\.(\w+)\.(\w+)",
            lambda m: str(self._get_memory(m.group(1), m.group(2))),
            result
        )

        return result

    def _build_eval_namespace(self) -> dict:
        return {}

    # ------------------------------------------------------------------ #
    #  choice / choice.cycle
    # ------------------------------------------------------------------ #

    def _eval_choice(self, expr: str, cycle: bool) -> str:
        options = self._parse_list(expr)
        if not options:
            return ""

        if cycle:
            key = f"_cycle_{hash(expr)}"
            state = self.state.cycle_state.setdefault(key, {"idx": 0, "used": []})
            used = state["used"]
            remaining = [o for o in options if o not in used]
            if not remaining:
                remaining = list(options)
                state["used"] = []
            chosen = random.choice(remaining)
            state["used"].append(chosen)
        else:
            chosen = random.choice(options)

        # If chosen matches a loaded dialogue ID, resolve it
        resolved = self.state.dialogue_manager.get_dialogue_by_id(chosen) if self.state.dialogue_manager else None
        if resolved:
            return chosen  # return ID — caller handles resolution
        return chosen

    def _parse_list(self, expr: str) -> list[str]:
        """Parse ['a', 'b', 'c'] style list."""
        expr = expr.strip()
        if expr.startswith("[") and expr.endswith("]"):
            expr = expr[1:-1]
        items = re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", expr)
        result = []
        for single, double in items:
            result.append(single if single else double)
        return result

    # ------------------------------------------------------------------ #
    #  memory
    # ------------------------------------------------------------------ #

    def _eval_memory_get(self, path: str) -> Any:
        # memory.global.key, memory.user.key, etc.
        parts = path.split(".", 2)
        if len(parts) < 2:
            return ""
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
        repeat = self.state.memory.get("repeat", {})
        entry = repeat.get(dialogue_id, {})
        return entry.get(field, 0)

    def _get_interest(self, topic: str, field: str) -> Any:
        iv = self.state.interests.get(topic)
        if iv:
            return iv.get(field, 0)
        return 0

    def _eval_memory_set(self, expr: str) -> str:
        if "|" not in expr:
            return ""
        path, value_expr = expr.split("|", 1)
        path = path.strip()
        value_expr = value_expr.strip()

        # Evaluate value
        if value_expr.startswith("math:"):
            value = self._eval_math(value_expr[5:].strip())
        else:
            value = value_expr.strip("'\"")

        parts = path.split(".", 1)
        ns = parts[0]
        key = parts[1] if len(parts) > 1 else path

        # Mods can only write to their own namespace — enforced at higher level
        ns_store = self.state.memory.setdefault(ns, {})
        ns_store[key] = {"value": value, "_ts": time.time()}
        return ""

    def _eval_memory_repeat(self, expr: str) -> Any:
        # memory.repeat['dialogue_id'].field
        m = re.match(r"memory\.repeat\['([^']+)'\]\.(\w+)", expr)
        if m:
            return self._get_repeat(m.group(1), m.group(2))
        return ""

    # ------------------------------------------------------------------ #
    #  interest[...].field
    # ------------------------------------------------------------------ #

    def _eval_interest(self, expr: str) -> Any:
        m = re.match(r"interest\['([^']+)'\]\.(\w+)", expr)
        if m:
            return self._get_interest(m.group(1), m.group(2))
        return 0

    # ------------------------------------------------------------------ #
    #  datetime
    # ------------------------------------------------------------------ #

    def _eval_datetime(self, key: str) -> Any:
        now = dt.datetime.now()
        mapping = {
            "hour": now.hour,
            "minute": f"{now.minute:02d}",
            "day_of_week": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d"),
            "timestamp": int(time.time()),
        }
        return mapping.get(key, "")

    # ------------------------------------------------------------------ #
    #  math
    # ------------------------------------------------------------------ #

    def _eval_math(self, expr: str) -> Any:
        # Build safe namespace
        safe_ns = {
            "abs": abs, "min": min, "max": max,
            "round": round, "int": int, "float": float,
        }
        # Replace memory/interest references
        py_expr = self._condition_to_python(expr)
        try:
            return eval(py_expr, {"__builtins__": {}}, safe_ns)
        except Exception:
            return 0

    # ------------------------------------------------------------------ #
    #  random
    # ------------------------------------------------------------------ #

    def _eval_random_int(self, expr: str) -> int:
        m = re.match(r"(\d+)\s*-\s*(\d+)", expr)
        if m:
            return random.randint(int(m.group(1)), int(m.group(2)))
        return 0

    def _eval_random_float(self, expr: str) -> float:
        m = re.match(r"([0-9.]+)\s*-\s*([0-9.]+)", expr)
        if m:
            return random.uniform(float(m.group(1)), float(m.group(2)))
        return 0.0

    # ------------------------------------------------------------------ #
    #  HTTP request
    # ------------------------------------------------------------------ #

    def _eval_request(self, expr: str) -> str:
        # Format: GET 'url' | response['key'] on_fail: skip|'message'
        m = re.match(r"(GET|POST)\s+'([^']+)'\s*\|\s*(.*?)(?:\s+on_fail:\s*(.*))?$", expr, re.DOTALL)
        if not m:
            return ""

        method = m.group(1)
        url = m.group(2)
        path_expr = m.group(3).strip()
        on_fail = (m.group(4) or "skip").strip()

        log = self.state.console_log if self.state.console_log else print
        try:
            resp = requests.request(method, url, timeout=5)
            log(f"[REQUEST] {method} {url} → {resp.status_code} {resp.reason}")
            if resp.status_code != 200:
                raise ValueError(f"HTTP {resp.status_code}")
            data = resp.json()
            # Navigate path: response['key']['nested']
            result = self._navigate_response(data, path_expr)
            return str(result)
        except Exception as e:
            if on_fail == "skip":
                return "\x00SKIP\x00"
            on_fail_str = on_fail.strip("'\"")
            return on_fail_str

    def _navigate_response(self, data: Any, path: str) -> Any:
        """Navigate response['key']['nested'] style paths."""
        keys = re.findall(r"\['([^']+)'\]|\[(\d+)\]", path)
        for str_key, int_key in keys:
            k = str_key if str_key else int(int_key)
            data = data[k]
        return data

    # ------------------------------------------------------------------ #
    #  dep key navigation
    # ------------------------------------------------------------------ #

    def _navigate_path(self, data: Any, path: str) -> Any:
        """Navigate a dot-notation + bracket path through a dict."""
        if not path or data is None:
            return data

        # Handle interest['topic'].field style
        m = re.match(r"interest\['([^']+)'\]\.(\w+)", path)
        if m:
            return self._get_interest(m.group(1), m.group(2))

        parts = re.split(r"\.(?![^[]*\])", path)
        for part in parts:
            if data is None:
                return ""
            bracket = re.match(r"(\w+)\['([^']+)'\]", part)
            if bracket:
                data = data.get(bracket.group(1), {})
                data = data.get(bracket.group(2), "")
            else:
                if isinstance(data, dict):
                    data = data.get(part, "")
                else:
                    return ""
        return data


# ------------------------------------------------------------------ #
#  Helper: find where a condition expression ends
# ------------------------------------------------------------------ #

def _find_condition_end(text: str) -> int:
    """
    Scan text for the boundary between condition and content.
    Condition ends when we hit a token that can't be part of a logical expr.
    Returns the char index where content begins.
    """
    # Strategy: tokenise and look for the first non-condition token
    # This is a heuristic — handles most BDL cases
    i = 0
    n = len(text)
    paren_depth = 0
    bracket_depth = 0
    in_str = False
    str_char = None
    last_valid = 0

    COND_TOKENS = {
        "and", "or", "not", "true", "false",
        "True", "False", "None", "none",
    }

    while i < n:
        c = text[i]

        if in_str:
            if c == str_char:
                in_str = False
            i += 1
            last_valid = i
            continue

        if c in ('"', "'"):
            in_str = True
            str_char = c
            i += 1
            continue

        if c == "(":
            paren_depth += 1
            i += 1
            continue
        if c == ")":
            if paren_depth > 0:
                paren_depth -= 1
                last_valid = i + 1
            i += 1
            continue
        if c == "[":
            bracket_depth += 1
            i += 1
            continue
        if c == "]":
            if bracket_depth > 0:
                bracket_depth -= 1
                last_valid = i + 1
            i += 1
            continue

        if paren_depth > 0 or bracket_depth > 0:
            i += 1
            continue

        # Check for comparison/logical operators
        if c in "><=!":
            last_valid = i + 2 if i + 1 < n and text[i + 1] == "=" else i + 1
            i += 2 if i + 1 < n and text[i + 1] == "=" else 1
            continue

        if c.isdigit() or c == "-" or c == "." or c == "_":
            last_valid = i + 1
            i += 1
            continue

        if c.isalpha():
            # Collect word
            j = i
            while j < n and (text[j].isalnum() or text[j] in ("_", ".", "'", "[")):
                j += 1
            word = text[i:j]
            if (word in COND_TOKENS or
                word.startswith("mood.") or
                word.startswith("memory.") or
                word.startswith("datetime.") or
                word.startswith("interest[") or
                word.startswith("counter.") or
                word.startswith("flag.") or
                word[0].isdigit()):
                last_valid = j
                i = j
                continue
            # It's a word that could be start of content
            # If we've already consumed some condition, this is likely content
            if last_valid > 0:
                return last_valid
            i = j
            continue

        if c == " ":
            i += 1
            continue

        # Unknown char — content starts here
        if last_valid > 0:
            return last_valid
        i += 1

    return last_valid if last_valid > 0 else n
