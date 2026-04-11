# Mod Documentation >> All Mod Related..

everything you need to know to build a Bucko mod. reference + worked examples.

---

## Table of Contents

1. [Building a Mod From Scratch](#1-building-a-mod-from-scratch)
2. [Mod Structure](#2-mod-structure)
3. [mod.yaml Fields](#3-modyaml-fields)
4. [Dialogue Block Fields](#4-dialogue-block-fields)
5. [Follow-Ups — Dialogue Within Dialogue](#5-follow-ups--dialogue-within-dialogue)
6. [BDL Reference](#6-bdl-reference)
7. [Memory Namespaces](#7-memory-namespaces)
8. [Mood System](#8-mood-system)
9. [Interest Vectors](#9-interest-vectors)
10. [Affection System](#10-affection-system)
11. [Repeat Handling](#11-repeat-handling)
12. [Trigger System](#12-trigger-system)
13. [Console Commands](#13-console-commands)
14. [Mod Permissions](#14-mod-permissions)
15. [Dialogue ID Namespacing](#15-dialogue-id-namespacing)
16. [Edge Cases & Gotchas](#16-edge-cases--gotchas)

---

## 1. Building a Mod From Scratch

This section walks through building a complete, working mod from nothing. Everything else in this doc is reference material — come here first if you just want to see how it all fits together.

**Goal**: A mod where Bucko talks about coffee. Remembers your order. Gets hyper if you say you drink a lot.

### Step 1 — Create the folder

```
mods/
└── coffee_mod/
    ├── mod.yaml
    └── dialogue.yaml
```

That's all you need. Two files.

### Step 2 — Write mod.yaml

```yaml
name: "Coffee Mod"
id: "coffee_mod"
mod_version: 1
version_support: [1, 2]
description: "Bucko talks about coffee and remembers your order."
author: "yourname"
```

Done. No optional fields needed for a basic mod.

### Step 3 — Write your first dialogue block

`dialogue.yaml`:

```yaml
dialogues:
  - dialogue_id: "coffee_general"
    triggers:
      - keywords: ["coffee", "espresso", "latte", "cappuccino", "caffeine"]
    priority: 3
    lines:
      - "oh we're doing coffee talk"
      - "{{choice.cycle: ['what do you take', 'regular order or something new', 'black or are you a milk person']}}"
    mood_effect:
      energy: +5
      chaos: +3
```

Save it. Run Bucko. Say "I love coffee". It fires.

### Step 4 — Add follow-ups (dialogue within dialogue)

Now add inline follow-up replies so the conversation can continue naturally without the user needing to ask a new question. Bucko asked "what do you take" — let's make him respond to the answer.

```yaml
dialogues:
  - dialogue_id: "coffee_general"
    triggers:
      - keywords: ["coffee", "espresso", "latte", "cappuccino", "caffeine"]
    priority: 3
    lines:
      - "oh we're doing coffee talk"
      - "{{choice.cycle: ['what do you take', 'regular order or something new', 'black or are you a milk person']}}"
    mood_effect:
      energy: +5
      chaos: +3
    follow_ups:
      - triggers:
          - keywords: ["black", "no milk", "straight", "espresso", "americano"]
        lines:
          - "respect. purist."
          - "you're not messing around."
        mood_effect:
          chaos: +5

      - triggers:
          - keywords: ["latte", "cappuccino", "oat milk", "almond milk", "flat white", "with milk"]
        lines:
          - "ok milk drinker"
          - "{{wait: 0.6}}i don't judge. much."

      - triggers:
          - keywords: ["a lot", "too much", "six cups", "seven cups", "constantly", "all day", "always"]
        lines:
          - "bro."
          - "{{wait: 0.8}}how are you alive"
        mood_effect:
          chaos: +15
          energy: +10
```

Now when the user answers Bucko's question, Bucko reacts to the specific answer. The follow-ups only fire for 2 minutes after the parent block plays — if the user types something else first, the context resets.

### Step 5 — Remember the order

Use `input_capture` to save the user's coffee order and reference it later.

```yaml
  - dialogue_id: "coffee_order_ask"
    triggers:
      - keywords: ["take my order", "remember my order", "save my order", "what do i drink"]
    priority: 5
    lines:
      - "aight. what's your order."
    input_capture: true
    input_store: "mod['coffee_mod'].order"
    follow_ups:
      - triggers:
          - keywords: ["coffee", "latte", "espresso", "black", "oat", "flat white"]
        lines:
          - "got it."
          - "{{memory.mod['coffee_mod'].order}} — locked in."

  - dialogue_id: "coffee_recall"
    triggers:
      - keywords: ["what's my order", "what do i drink", "my order"]
    priority: 6
    lines:
      - "{{if memory.mod['coffee_mod'].order}}your order is {{memory.mod['coffee_mod'].order}}.{{else}}you haven't told me yet. say 'take my order'.{{endif}}"
```

### Step 6 — Conditional based on mood

Add a block that changes depending on Bucko's current chaos level (which went up from all those coffee conversations):

```yaml
  - dialogue_id: "coffee_chaos_check"
    triggers:
      - keywords: ["are you okay", "you good", "bucko you good"]
    priority: 4
    lines:
      - "{{if mood.chaos > 70}}YEAH I'M FINE THE COFFEE TALK GOT ME GOING{{elif mood.chaos > 40}}yeah i'm good. bit wired.{{else}}yeah. calm. why.{{endif}}"
```

### That's a full mod

Here's the complete `dialogue.yaml` for the coffee mod:

```yaml
dialogues:
  - dialogue_id: "coffee_general"
    triggers:
      - keywords: ["coffee", "espresso", "latte", "cappuccino", "caffeine"]
    priority: 3
    lines:
      - "oh we're doing coffee talk"
      - "{{choice.cycle: ['what do you take', 'regular order or something new', 'black or are you a milk person']}}"
    mood_effect:
      energy: +5
      chaos: +3
    follow_ups:
      - triggers:
          - keywords: ["black", "no milk", "straight", "espresso", "americano"]
        lines:
          - "respect. purist."
          - "you're not messing around."
        mood_effect:
          chaos: +5
      - triggers:
          - keywords: ["latte", "cappuccino", "oat milk", "almond milk", "flat white", "with milk"]
        lines:
          - "ok milk drinker"
          - "{{wait: 0.6}}i don't judge. much."
      - triggers:
          - keywords: ["a lot", "too much", "six cups", "seven cups", "constantly", "all day", "always"]
        lines:
          - "bro."
          - "{{wait: 0.8}}how are you alive"
        mood_effect:
          chaos: +15
          energy: +10

  - dialogue_id: "coffee_order_ask"
    triggers:
      - keywords: ["take my order", "remember my order", "save my order"]
    priority: 5
    lines:
      - "aight. what's your order."
    input_capture: true
    input_store: "mod['coffee_mod'].order"

  - dialogue_id: "coffee_recall"
    triggers:
      - keywords: ["what's my order", "what do i drink", "my order"]
    priority: 6
    lines:
      - "{{if memory.mod['coffee_mod'].order}}your order is {{memory.mod['coffee_mod'].order}}.{{else}}you haven't told me yet. say 'take my order'.{{endif}}"

  - dialogue_id: "coffee_chaos_check"
    triggers:
      - keywords: ["are you okay", "you good", "bucko you good"]
    priority: 4
    lines:
      - "{{if mood.chaos > 70}}YEAH I'M FINE THE COFFEE TALK GOT ME GOING{{elif mood.chaos > 40}}yeah i'm good. bit wired.{{else}}yeah. calm. why.{{endif}}"
```

---

## 2. Mod Structure

A mod is a folder inside `mods/`. The folder name doesn't matter — Bucko uses the `id` field from `mod.yaml` as the internal identifier.

```
mods/
└── my_cool_mod/
    ├── mod.yaml           ← required. metadata.
    ├── dialogue.yaml      ← any .yaml file except mod.yaml gets loaded as dialogue
    ├── topics.yaml        ← you can split dialogue across multiple files
    └── assets/            ← optional. images, etc (not auto-loaded yet)
```

All `.yaml` files in the mod folder (except `mod.yaml`) are loaded as dialogue files. The namespace for all of them is the mod's `id`.

---

## 3. mod.yaml Fields

```yaml
name: "My Cool Mod"           # display name. spaces OK.
id: "my_cool_mod"             # internal ID. lowercase, underscores, numbers only. NO spaces or dashes.
mod_version: 1                # single integer. increment on each release. NOT semver.
version_support: [1, 2]          # list every Bucko client version this was tested on.
description: "does stuff"
author: "yourname"

console_commands:             # optional. register custom console commands.
  - name: "status"
    description: "Show mod status info"
  - name: "reset"
    description: "Reset mod state"
```

**id validation**: must match `^[a-z0-9_]+$`. Spaces, uppercase, dashes → error on load.

**version_support**: if the running client version isn't in this list:
```
⚠️  My Cool Mod (v1) does not explicitly support client v2
```
The mod still loads — it's just a warning.

**mod_version**: single integer. `1`, `2`, `3`, etc. Not `1.0.0`.

---

## 4. Dialogue Block Fields

Full example with every field:

```yaml
dialogues:
  - dialogue_id: "my_block"
    
    triggers:
      - keywords: ["osu", "osu!", "rhythm game"]
      - exact: "what games do you play"
      - pattern: "do you (know|play|like) osu"
    
    priority: 10
    condition: "{{if interest['osu!'].frequency > 5}}"
    cooldown: 60
    
    mood_condition: "{{if mood.energy > 40}}"
    
    expression: "happy"
    
    lines:
      - "first line"
      - pause: 1.5
      - "second line after pause"
      - "{{wait: 0.8}}this has an inline wait"
    
    next_label: "ok..."
    next: "another_block"
    
    mood_effect:
      energy: +10
      patience: -5
      chaos: +15
      warmth: +5
      affection: increase
    
    on_repeat:
      threshold: 3
      escalate:
        - "{{choice.cycle: ['repeat_1', 'repeat_2']}}"
      max_escalations: 2
      cooldown: 120
      forget_after_cooldown: false
    
    input_capture: true
    input_store: "mod['my_cool_mod'].user_input"
    
    follow_ups:
      - triggers:
          - keywords: ["yes", "yeah", "yep"]
        lines:
          - "nice"
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `dialogue_id` | string | Unique ID within this file. Namespaced as `mod_id::dialogue_id` globally. |
| `triggers` | list | Match conditions that fire this block. |
| `priority` | int | Higher wins when multiple blocks match. Default: 0. |
| `condition` | BDL string | Block only fires if this evaluates truthy. |
| `cooldown` | int | Seconds before this block can fire again. |
| `mood_condition` | BDL string | Block only fires if this mood condition is truthy. |
| `expression` | string | Expression image to show (matches filename in `core/expressions/`). |
| `lines` | list | Lines to display. Strings or `pause:` items. |
| `next_label` | string | Label for the NEXT button (default: "NEXT"). |
| `next` | string | Dialogue ID to chain to after all lines are done. |
| `mood_effect` | dict | Mood deltas applied when this block fires. |
| `on_repeat` | dict | Escalating behaviour when block is triggered multiple times. |
| `input_capture` | bool | If true, input bar captures user text for storage. |
| `input_store` | string | Memory key to store captured input (e.g. `mod['my_mod'].name`). |
| `follow_ups` | list | Context-aware replies that only fire as a response to this block. |

**Important**: `priority`, `condition`, and `cooldown` are **block-level** fields. They go directly under the `dialogue_id`, NOT inside the `triggers` list.

```yaml
# CORRECT
- dialogue_id: "my_block"
  priority: 10
  condition: "{{if mood.energy > 50}}"
  cooldown: 60
  triggers:
    - keywords: ["hello"]

# WRONG — these fields inside triggers: will be ignored
- dialogue_id: "my_block"
  triggers:
    - keywords: ["hello"]
      priority: 10        ← wrong
      condition: "..."    ← wrong
```

---

## 5. Follow-Ups — Dialogue Within Dialogue

Follow-ups let Bucko reply contextually to what the user says **in response to a specific block**. Instead of matching globally, they only activate for 2 minutes after the parent block fires. Then the context resets.

### Basic follow-up

```yaml
- dialogue_id: "ask_favourite_game"
  triggers:
    - keywords: ["favourite game", "best game", "game recommendation"]
  priority: 4
  lines:
    - "Elden Ring. no question."
    - "{{choice: ['what did you want to hear', 'fight me', 'it\\'s not even close']}}"
  follow_ups:
    - triggers:
        - keywords: ["i've played it", "already played", "played it"]
      lines:
        - "ok so you know then"
        - "what'd you think"

    - triggers:
        - keywords: ["never played it", "haven't played it", "not played", "never heard of it"]
      lines:
        - "you're missing out bro"
        - "open world, punishing, insane boss fights"
        - "it's not for everyone but you should try it"

    - triggers:
        - keywords: ["i disagree", "bad take", "wrong", "nah"]
      lines:
        - "ok what's your pick then"
```

### Nested follow-ups

Follow-ups can be nested arbitrarily deep. Each level is another exchange in the conversation.

```yaml
- dialogue_id: "anime_rec"
  triggers:
    - keywords: ["recommend anime", "good anime", "what anime"]
  priority: 5
  lines:
    - "Mob Psycho 100. that's my answer."
  follow_ups:
    - triggers:
        - keywords: ["why", "why that", "explain"]
      lines:
        - "the character writing is genuinely S-tier"
        - "Mob goes through one of the best arcs in anime. no cap."
      follow_ups:
        - triggers:
            - keywords: ["i've seen it", "already watched", "seen it"]
          lines:
            - "oh so you already know."
            - "{{choice: ['what did you think', 'rate it out of 10', 'favourite arc?']}}"
          follow_ups:
            - triggers:
                - keywords: ["10", "10/10", "amazing", "peak", "goated"]
              lines:
                - "correct opinion. you're welcome."
            - triggers:
                - keywords: ["mid", "ok", "overrated", "meh"]
              lines:
                - "bro."
                - pause: 0.8
                - "wrong. but ok."

        - triggers:
            - keywords: ["sounds good", "ok", "i'll watch it", "fair"]
          lines:
            - "yeah. just watch it."
            - "you'll see what i mean within 3 episodes."

    - triggers:
        - keywords: ["different one", "something else", "another recommendation", "what else"]
      lines:
        - "ok different vibe. try Vinland Saga — brutal but amazing."
```

### How follow-up context works

1. User says something → parent block fires → follow-up context is set
2. User replies → Bucko checks follow-ups first (before global triggers)
3. If a follow-up matches → it fires and optionally sets its own nested context
4. If nothing matches → context is cleared and global matching resumes
5. Context expires after **2 minutes** regardless

This means conversations flow naturally without the user having to be specific about framing. They just reply and Bucko picks it up.

### Follow-up with mood_effect

```yaml
follow_ups:
  - triggers:
      - keywords: ["awesome", "love it", "great"]
    lines:
      - "yeah i thought you'd like that"
    mood_effect:
      warmth: +5
      affection: increase
```

Follow-ups support all the same fields as dialogue blocks: `lines`, `mood_effect`, `expression`, and nested `follow_ups`. They do NOT support `triggers`-level matching options like `priority` or `cooldown` — those are parent-block concepts.

---

## 6. BDL Reference

BDL expressions go inside `{{ }}` in any string value. Single `{ }` is normal YAML and is ignored.

### 6.1 if / elif / else / endif — conditionals

**Single condition, single branch:**
```yaml
"{{if mood.energy > 70}}locked in{{endif}}"
```

**With else:**
```yaml
"{{if memory.affection > 500}}we go way back{{else}}still getting to know you{{endif}}"
```

**Full if / elif / else:**
```yaml
"{{if mood.chaos > 70}}feeling chaotic ngl{{elif mood.warmth > 70}}feeling warm rn{{elif mood.patience < 30}}my patience is cooked{{else}}mood's stable{{endif}}"
```

**Combined conditions:**
```yaml
"{{if interest['anime'].frequency > 10 and mood.warmth > 60}}you really into this huh{{endif}}"
"{{if datetime.hour >= 22 or datetime.hour < 6}}why are you up{{endif}}"
```

**Time-based:**
```yaml
"{{if datetime.hour < 12}}morning vibes{{elif datetime.hour < 18}}afternoon{{else}}night owl{{endif}}"
```

Supported operators: `>` `<` `>=` `<=` `==` `!=` `and` `or` `not`

---

### 6.2 choice — random pick

```yaml
"{{choice: ['option one', 'option two', 'option three']}}"
```

Picks randomly each time. No memory between calls.

**Practical example:**
```yaml
lines:
  - "{{choice: ['ayo', 'hey', 'wassup', 'yo what up']}}"
```

If a value exactly matches a loaded dialogue ID, that block fires instead of showing the text. Use this to route to different blocks randomly:
```yaml
"{{choice: ['my_mod::happy_path', 'my_mod::grumpy_path']}}"
```

---

### 6.3 choice.cycle — round-robin without repeats

```yaml
"{{choice.cycle: ['story one', 'story two', 'story three']}}"
```

Goes through options in order, doesn't repeat until all have been shown. Cycle state persists across sessions.

**Practical example** — Bucko's greeting never repeats:
```yaml
"{{choice.cycle: ['fps player detected', 'ah a shooter kid', 'the classic FPS enjoyer']}}"
```

---

### 6.4 wait — inline delay

```yaml
"hold on...{{wait: 2.5}}ok I'm back"
"bro.{{wait: 0.8}}that's a lot"
```

Pauses the typewriter mid-line. Float value = seconds.
Used INSIDE a string, not as a separate line item.

---

### 6.5 pause — standalone line pause

```yaml
lines:
  - "first thing"
  - pause: 1.5
  - "second thing after 1.5 seconds"
```

Used as a SEPARATE item in the `lines` list (not in a string).

Special case: if `pause` is the **last line** AND the block has a `next:`, it auto-chains immediately — no NEXT button shown.

---

### 6.6 datetime

```yaml
"{{datetime.hour}}"         # 0–23
"{{datetime.minute}}"       # 00–59 (zero-padded)
"{{datetime.day_of_week}}"  # Monday, Tuesday, etc.
"{{datetime.date}}"         # YYYY-MM-DD
"{{datetime.timestamp}}"    # unix timestamp integer
```

**Practical example** — time-aware greeting:
```yaml
- dialogue_id: "greeting_morning"
  triggers:
    - keywords: ["good morning", "morning"]
  mood_condition: "{{if datetime.hour < 12}}"
  lines:
    - "morning. it's {{datetime.hour}}:{{datetime.minute}} btw"
```

---

### 6.7 memory.user and memory.global

```yaml
"{{memory.user.name}}"
"{{memory.global.times_talked}}"
```

Reading from these namespaces is allowed. Writing is blocked (mods can't write here).

---

### 6.8 memory.mod — mod-private storage

**Reading:**
```yaml
"{{memory.mod['coffee_mod'].order}}"
"{{if memory.mod['coffee_mod'].order}}you told me{{else}}you haven't told me{{endif}}"
```

**Writing:**
```yaml
"{{memory.set: mod['coffee_mod'].order | double espresso}}"
"{{memory.set: mod['my_mod'].score | 9001}}"
```

Mods can ONLY write to `memory.mod['their_own_id'].*`. Writing anywhere else is silently ignored.

---

### 6.9 mood references

```yaml
"{{mood.energy}}"     # 0–100
"{{mood.patience}}"
"{{mood.chaos}}"
"{{mood.warmth}}"
```

Read-only. Change mood via `mood_effect` in the block definition.

**Practical example:**
```yaml
lines:
  - "energy: {{mood.energy}} | patience: {{mood.patience}} | chaos: {{mood.chaos}} | warmth: {{mood.warmth}}"
  - "{{if mood.chaos > 70}}feeling chaotic ngl{{elif mood.patience < 30}}patience is cooked{{else}}mood's stable{{endif}}"
```

---

### 6.10 interest vectors

```yaml
"{{interest['osu!'].frequency}}"    # int — times mentioned
"{{interest['anime'].depth}}"       # 0–1000 — conversation depth
"{{interest['music'].recency}}"     # unix timestamp — last mention
"{{interest['gaming'].sentiment}}"  # -1.0 to 1.0
```

**Practical example:**
```yaml
"{{if interest['anime'].frequency > 10}}you bring this up a lot btw{{endif}}"
"{{if interest['osu!'].depth > 200}}you really know your stuff{{endif}}"
```

---

### 6.11 memory.affection

```yaml
"{{memory.affection}}"   # displayed value 0–1000
```

Read-only. Change via `mood_effect: affection: increase` or `decrease`.

**Practical example:**
```yaml
lines:
  - "my affection rating for you is {{memory.affection}}/1000"
  - "{{if memory.affection > 700}}that's pretty high ngl{{elif memory.affection > 400}}we're getting there{{elif memory.affection > 200}}you're ok{{else}}still figuring each other out{{endif}}"
```

---

### 6.12 counter — persistent integer counters

```yaml
"{{counter.increment: 'times_talked'}}"
"session #{{counter.get: 'times_talked'}} for us"
```

---

### 6.13 flag — persistent booleans

```yaml
# Set a flag
"{{flag.set: 'completed_intro'}}"

# Read in a condition
"{{if flag.get: 'completed_intro'}}welcome back{{else}}first time here{{endif}}"
```

Flags persist across sessions until cleared via console.

---

### 6.14 math

```yaml
"{{math: interest['osu!'].frequency * 2}}"
"{{math: memory.global.times_talked + 1}}"
"{{math: round(mood.energy / 10)}}"
```

Available functions: `abs`, `min`, `max`, `round`, `int`, `float`

---

### 6.15 random numbers

```yaml
"{{random.int: 1-100}}"
"{{random.float: 0.0-1.0}}"
```

---

### 6.16 string operations

```yaml
"{{upper: memory.user.name}}"       # HARRY
"{{lower: memory.user.name}}"       # harry
"{{capitalize: memory.user.name}}"  # Harry
```

---

### 6.17 HTTP requests

```yaml
"{{request: GET 'https://api.example.com/data' | response['result']['value']
    on_fail: skip}}"

"{{request: GET 'https://api.example.com/score' | response['score']
    on_fail: 'couldn\\'t load score'}}"
```

- `on_fail: skip` — if status != 200, the entire line is silently dropped
- `on_fail: 'message'` — show this string instead on failure
- Navigate response: `response['key']['nested']` or `response['key'][0]` for arrays

---

### 6.18 dep — fetch from config file

```yaml
"{{dep: my_data.yaml | settings.value}}"
```

Reads from a static YAML file in `core/` or the mod dir. Results are cached. This is for static data — for runtime data use `memory.*`.

---

## 7. Memory Namespaces

| Namespace | Description | Mod can read? | Mod can write? |
|-----------|-------------|---------------|----------------|
| `memory.global.*` | Persistent cross-session data | ✅ | ❌ |
| `memory.user.*` | Learned user data (name, etc.) | ✅ | ❌ |
| `memory.session.*` | Current session only, cleared on close | ✅ | ❌ |
| `memory.repeat['ns::id'].*` | Per-dialogue repeat tracking | ✅ | ❌ |
| `memory.mod['mod_id'].*` | Sandboxed per-mod storage | ✅ (own) | ✅ (own only) |

**Mod sandboxing**: a mod with `id: "coffee_mod"` can only write to `memory.mod['coffee_mod'].*`. Writing to any other namespace is silently ignored — no error, no effect.

---

## 8. Mood System

Bucko's mood is a 4D vector: `energy`, `patience`, `chaos`, `warmth`. All values are 0–100.

**Apply deltas** with `mood_effect`:

```yaml
mood_effect:
  energy: +10     # can be positive or negative
  patience: -15
  chaos: +5
  warmth: +3
```

Signs are optional — `+10` and `10` both work. `-15` is a decrease.

**Read in BDL:**

```yaml
"{{mood.energy}}"
"{{if mood.chaos > 60}}chaotic response{{else}}calm response{{endif}}"
```

**Mood decays** back toward the configured baseline over time. Default: 1 unit per minute per dimension. Baseline is set in `client_config.yaml`.

You cannot set mood directly — only apply deltas. The decay handles the rest.

**Practical example:**
```yaml
- dialogue_id: "gaming_fps"
  triggers:
    - keywords: ["valorant", "csgo", "apex", "fps"]
  lines:
    - "fps player detected"
    - "what rank"
  mood_effect:
    energy: +8      # gets energised by gaming talk
    chaos: +3
```

---

## 9. Interest Vectors

Every topic mentioned gets tracked automatically as a 4D vector:

```
interest['topic_name']:
  depth      # 0–1000 — how deep conversations on this topic have gone
  frequency  # integer — how many times it's been mentioned
  recency    # unix timestamp — when it was last mentioned
  sentiment  # -1.0 to 1.0 — negative = hate-love, positive = genuine enthusiasm
```

Topics are free-form strings — whatever gets mentioned gets tracked. Read them in BDL:

```yaml
"{{if interest['osu!'].depth > 200}}you know your stuff{{endif}}"
"{{if interest['anime'].frequency > 10}}you bring this up a lot btw{{endif}}"
"{{if interest['anime'].sentiment > 0.7}}you genuinely love this{{endif}}"
```

Use these to make dialogue adapt over time as you learn more about the user.

---

## 10. Affection System

`memory.affection` is displayed as 0–1000. Stored internally as 0–1,000,000.

### Applying changes

```yaml
mood_effect:
  affection: increase   # or: decrease
```

Never specify an amount — the curve handles it.

### How the curve works

- Getting close to max: each `increase` gives diminishing returns
- Anti-exploit: tracks the last 5 delta amounts; if current exceeds the mean, it's ignored
- Only ONE affection change per dialogue block counts

**You cannot farm affection.** Design dialogue that earns it naturally.

---

## 11. Repeat Handling

When a user triggers the same block multiple times, `on_repeat` lets you escalate responses:

```yaml
on_repeat:
  threshold: 3              # starts escalating after 3 triggers
  escalate:
    - "ok you've said this before"
    - "yeah, you said this already"
    - "bro i'm ignoring you now"
  max_escalations: 3        # after 3 escalations, goes silent
  cooldown: 300             # seconds before it works normally again
  forget_after_cooldown: false
```

Read repeat data in BDL:
```yaml
"{{memory.repeat['my_mod::my_block'].count}}"
"{{memory.repeat['my_mod::my_block'].last_time}}"
```

**Practical example** — block that gets annoyed if you say "hello" too much:
```yaml
- dialogue_id: "greeting_general"
  triggers:
    - keywords: ["hey", "hi", "hello"]
  priority: 3
  lines:
    - "{{choice: ['ayo', 'hey', 'wassup']}}"
  on_repeat:
    threshold: 5
    escalate:
      - "you've said hi like {{memory.repeat['base_game::greeting_general'].count}} times now"
      - "i'm counting btw"
      - "ok we're done greeting each other"
    max_escalations: 3
    cooldown: 600
```

---

## 12. Trigger System

### Trigger types

```yaml
triggers:
  - keywords: ["word1", "word2", "phrase"]   # fires if ANY keyword appears in input
  - exact: "exact phrase to match"           # fires only on exact match (case insensitive)
  - pattern: "regex (pattern|here)"          # regex match
```

Multiple entries in `triggers` are OR'd — any one matching fires the block.

### Block-level fields (NOT inside triggers)

```yaml
- dialogue_id: "my_block"
  triggers:
    - keywords: ["hello"]
    - exact: "hi there"
  priority: 10                               # ← block level, not inside triggers
  condition: "{{if mood.energy > 50}}"       # ← block level
  cooldown: 60                               # ← block level
```

### Priority resolution

When multiple blocks match the same input:
1. Higher `priority` wins (default: 0)
2. On tie: `exact` > `pattern` > `keywords`
3. On further tie: first loaded wins (core loads before mods, mods load alphabetically)

**Give your mod blocks explicit priority values** to avoid conflicts with base game dialogue.

### mood_condition

Prevents the block from firing unless a mood condition is met:

```yaml
mood_condition: "{{if mood.energy > 40}}"
```

Useful for blocks that should only appear when Bucko is in a specific state.

### no_match

Define fallback responses for when nothing matches:

```yaml
no_match_responses:
  - dialogue_id: "no_match_1"
    lines:
      - "huh?"
  - dialogue_id: "no_match_2"
    lines:
      - "say what now"
  - dialogue_id: "no_match_3"
    lines:
      - "idk what you mean by that"

no_match:
  - "{{choice.cycle: ['no_match_1', 'no_match_2', 'no_match_3']}}"
```

### "next" is reserved

The string `"next"` typed as input ALWAYS advances dialogue. It's intercepted before trigger matching. Don't add triggers for `"next"`.

---

## 13. Console Commands

### Custom mod commands

Register in `mod.yaml`:

```yaml
console_commands:
  - name: "leaderboard"
    description: "Show leaderboard data"
  - name: "reset"
    description: "Reset all mod data"
```

Users access them as `mod.[mod_id].[command]` (e.g. `mod.coffee_mod.reset`).

### Installing mods

```
mod.install https://github.com/someone/their-mod
mod.install https://github.com/someone/their-mod.git
mod.install C:\Users\you\Downloads\my_mod_folder
```

- Tries `git clone --depth 1` first (fast, requires git in PATH)
- Falls back to GitHub zip download if git fails or isn't installed
- Works with any GitHub URL — public repos only for zip download
- Local path: copies the folder into `mods/`
- No restart needed — mod loads and its dialogue blocks go live immediately
- Fails cleanly if there's no `mod.yaml`, an invalid id, or the folder already exists

### Built-in commands

```
client.version         client.restart        client.quit
client.config.reload   client.config.validate

cache.clean            chat.clear

logs.clean             logs.export [path]

mod.list               mod.install [url/path]   mod.uninstall [id]
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

help
```

---

## 14. Mod Permissions

### What mods CAN do

- Add dialogue blocks and triggers
- Read `memory.user.*`, `memory.global.*`, `memory.repeat['*'].*`
- Write to `memory.mod['their_id'].*`
- Apply mood deltas via `mood_effect`
- Apply affection changes via `mood_effect: affection: increase/decrease`
- Register console commands
- Make HTTP requests from BDL
- Chain to core dialogue blocks using `namespace::id` format
- Use follow-ups for multi-turn conversation

### What mods CANNOT do

- Override the `"next"` reserved keyword
- Set affection to a specific value directly
- Write to `memory.user.*`, `memory.global.*`, `memory.repeat.*`
- Access `saves/player.dat` directly
- Execute Python code
- Modify core loading behaviour

---

## 15. Dialogue ID Namespacing

Dialogue IDs are scoped to their file. Full ID = `namespace::dialogue_id`.

| File | Namespace | Example full ID |
|------|-----------|-----------------|
| `core/setup.yaml` | `setup` | `setup::name_input` |
| `core/dialogue/base_game.yaml` | `base_game` | `base_game::greeting_general` |
| `mods/coffee_mod/dialogue.yaml` | `coffee_mod` | `coffee_mod::coffee_general` |

**Shorthand**: Within the same file, just use the ID. Cross-file requires `namespace::id`.

```yaml
# same file — shorthand is fine
next: "part2"

# cross-file — namespace required
next: "setup::name_confirm"
next: "base_game::greeting_general"
```

In BDL `choice`:
```yaml
"{{choice: ['coffee_mod::coffee_general', 'base_game::gaming_general']}}"
```

---

## 16. Edge Cases & Gotchas

**`priority`, `condition`, `cooldown` go at the block level, not inside triggers**
```yaml
# WRONG
triggers:
  - keywords: ["hello"]
    priority: 10       ← won't work

# CORRECT
priority: 10
triggers:
  - keywords: ["hello"]
```

**pause as last line + next = auto-chain, no NEXT button**
If `pause:` is the final item in `lines:` AND the block has `next:`, the next block loads immediately — user never sees the NEXT button.

**choice values can be dialogue IDs**
If a value in `choice:` or `choice.cycle:` exactly matches a loaded dialogue ID, that block fires instead of printing the text.

**BDL in `next:`**
```yaml
next: "{{if mood.chaos > 70}}chaos_path{{else}}normal_path{{endif}}"
```
Conditional chaining works in `next:`. The evaluated result is used as a dialogue ID.

**HTTP `on_fail: skip`**
If the request fails AND `on_fail: skip`, the entire line is silently dropped. The typewriter never starts for that line.

**YAML strings with apostrophes**
Two options:
```yaml
# Option 1: double-quoted YAML, apostrophes are fine
- "it's fine"

# Option 2: single-quoted YAML, escape the apostrophe
- 'it\\'s fine'
```

**mod load order**
Core loads first, then mods in alphabetical order by folder name. Name your folders with a prefix if order matters: `00_base_mod`, `01_extension`.

**mod ID collision**
Two mods with the same `id` in `mod.yaml` → second one fails to load with an error.

**choice.cycle state persists**
Cycle state is saved and survives restarts. A cycle of 5 items remembers which have been shown even after closing and reopening Bucko.

**memory entry internal format**
Internally stored as `{value: ..., _ts: ..., _hash: ...}`. BDL always returns just the value — you don't deal with the wrapper.

**mood_effect parsing**
Both `+10` and `10` work as positive. `-10` is negative. Quoted strings work too: `"+10"`.

**follow-up context expiry**
Context expires after 2 minutes of inactivity OR immediately when no follow-up matches and the user input falls through to global triggers. If you want a follow-up to "catch" inputs that don't match anything else, add a broad fallback:
```yaml
follow_ups:
  - triggers:
      - keywords: ["specific answer"]
    lines:
      - "specific response"
  - triggers:
      - pattern: ".*"    # catch-all — matches anything
    lines:
      - "wait that wasn't the answer i expected"
```

---

*if something's not documented here, it's either not implemented yet or it's a bug. open an issue.*
