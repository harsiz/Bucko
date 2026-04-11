# Mod Documentation — The Bible

everything you need to know to build a Bucko mod. this document covers every BDL expression, every config field, every namespace, every console command, every edge case.

---

## Table of Contents

1. [Mod Structure](#1-mod-structure)
2. [mod.yaml Fields](#2-modyaml-fields)
3. [Dialogue Block Fields](#3-dialogue-block-fields)
4. [BDL Reference](#4-bdl-reference)
5. [Memory Namespaces](#5-memory-namespaces)
6. [Mood System](#6-mood-system)
7. [Interest Vectors](#7-interest-vectors)
8. [Affection System](#8-affection-system)
9. [Repeat Handling](#9-repeat-handling)
10. [Trigger System](#10-trigger-system)
11. [Console Commands](#11-console-commands)
12. [Mod Permissions](#12-mod-permissions)
13. [Dialogue ID Namespacing](#13-dialogue-id-namespacing)
14. [Edge Cases & Gotchas](#14-edge-cases--gotchas)

---

## 1. Mod Structure

A mod is a folder inside `mods/`. The folder name doesn't matter much — Bucko uses the `id` field from `mod.yaml` as the internal identifier.

```
mods/
└── my_cool_mod/
    ├── mod.yaml           ← required. metadata.
    ├── dialogue.yaml      ← any .yaml file except mod.yaml gets loaded as dialogue
    ├── topics.yaml        ← you can split dialogue across multiple files
    └── assets/            ← optional. images, etc.
```

All `.yaml` files in the mod folder (except `mod.yaml`) are loaded as dialogue files. The namespace for all of them is the mod's `id`.

---

## 2. mod.yaml Fields

```yaml
name: "My Cool Mod"           # display name. spaces OK.
id: "my_cool_mod"             # internal ID. lowercase, underscores only. NO spaces.
mod_version: 1                # single integer. increment on each release. NOT semver.
version_support: [1]          # list every Bucko client version this was tested on.
description: "does stuff"
author: "yourname"

console_commands:             # optional. register custom console commands.
  - name: "status"
    description: "Show mod status info"
  - name: "reset"
    description: "Reset mod state"
```

**id validation**: must match `^[a-z0-9_]+$`. Spaces, uppercase, dashes = error on load.

**version_support**: if the running client version isn't in this list, the console shows:
```
⚠️  My Cool Mod (v1) does not explicitly support client v2
```
The mod still loads — it's just a warning.

**mod_version**: single integer. `1`, `2`, `3`, etc. not `1.0.0`.

---

## 3. Dialogue Block Fields

Full example with all fields:

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
    input_store: "user.name"
```

### Field reference

| Field | Type | Description |
|-------|------|-------------|
| `dialogue_id` | string | Unique ID within this file. Namespaced as `mod_id::dialogue_id`. |
| `triggers` | list | Conditions that fire this block. |
| `mood_condition` | BDL string | Block only fires if this evaluates truthy. |
| `expression` | string | Expression state to set when this block starts. |
| `lines` | list | Lines to display. Can be strings or `pause:` items. |
| `next_label` | string | Label for the NEXT button on any line in this block. |
| `next` | string | Dialogue ID to chain to after all lines. |
| `mood_effect` | dict | Deltas to apply to mood when this block fires. |
| `on_repeat` | dict | Behaviour when user triggers this block repeatedly. |
| `input_capture` | bool | If true, the input bar captures user text for storage. |
| `input_store` | string | Where to store captured input (e.g. `user.name`). |

---

## 4. BDL Reference

BDL expressions go inside `{{ }}` in any string value. Single `{ }` is normal YAML.

### 4.1 dep — fetch from config file

```yaml
"{{dep: setup.yaml | user.name}}"
"{{dep: stats.yaml | interest['osu!'].frequency}}"
```

Format: `{{dep: filename.yaml | key.path}}`

- `filename.yaml` — relative to `core/` or mod dir
- `key.path` — dot-notation path through the YAML structure
- Results are cached after first read

### 4.2 if / elif / else / endif — conditionals

```yaml
"{{if mood.energy > 70}} locked in {{endif}}"

"{{if datetime.hour < 12}} morning
 {{elif datetime.hour < 18}} afternoon  
 {{else}} night owl {{endif}}"

"{{if interest['anime'].frequency > 10 and mood.warmth > 60}} you really into this huh {{endif}}"
```

Supported operators: `>` `<` `>=` `<=` `==` `!=` `and` `or` `not`

### 4.3 choice — random pick

```yaml
"{{choice: ['option one', 'option two', 'option three']}}"
```

- Picks randomly from the list
- Can repeat — no memory between evaluations
- If a value matches a loaded dialogue ID, that block is triggered instead

### 4.4 choice.cycle — sequential without repeats

```yaml
"{{choice.cycle: ['story one', 'story two', 'story three']}}"
```

- Cycles through options without repeating until all have been used
- Cycle state persists across sessions
- Works exactly like `choice` for dialogue ID resolution

### 4.5 wait — inline delay

```yaml
"hold on...{{wait: 2.5}}ok I'm back"
```

- Float (seconds). Pauses the typewriter mid-line.
- Used INSIDE a line string, not as a standalone line.

### 4.6 pause — standalone line pause

```yaml
lines:
  - "first thing"
  - pause: 1.5
  - "second thing"
```

- Used as a SEPARATE item in the `lines` list, not in a string.
- If `pause` is the LAST line AND there's a `next:`, auto-chains (no NEXT button).
- Anywhere else: just waits, user still clicks NEXT at end.

### 4.7 datetime

```yaml
"{{datetime.hour}}"        # 0–23
"{{datetime.minute}}"      # 00–59 (zero-padded)
"{{datetime.day_of_week}}" # Monday, Tuesday, etc.
"{{datetime.date}}"        # YYYY-MM-DD
"{{datetime.timestamp}}"   # unix timestamp integer
```

### 4.8 memory read

```yaml
"{{memory.global.times_talked}}"
"{{memory.user.name}}"
"{{memory.mod['my_cool_mod'].high_score}}"
```

Reading from any namespace is allowed in mods. Memory values are stored as `{value: ..., _ts: ..., _hash: ...}` internally but BDL returns just the value.

### 4.9 memory.set — write memory

```yaml
"{{memory.set: mod['my_cool_mod'].score | 9001}}"
"{{memory.set: mod['my_cool_mod'].last_seen | math: memory.global.times_talked + 1}}"
```

**Mods can ONLY write to `memory.mod['their_id'].*`**. Attempting to write to other namespaces is silently blocked.

Format: `{{memory.set: namespace.key | value}}`

### 4.10 memory.repeat

```yaml
"{{memory.repeat['setup::name_change'].count}}"
"{{memory.repeat['base_game::greeting_general'].last_time}}"
```

Repeat data tracks how many times each dialogue block has been triggered and when it was last triggered.

### 4.11 flag — boolean persistent values

```yaml
# set
"{{flag.set: 'did_something'}}"

# check (use in conditions)
"{{if flag.get: 'did_something'}} second time {{else}} first time {{endif}}"
```

Flags are persistent booleans. Once set, they stay set until cleared via console.

### 4.12 counter — persistent integer counters

```yaml
"{{counter.increment: 'times_talked'}}"
"{{counter.get: 'times_talked'}} sessions so far"
```

### 4.13 math

```yaml
"{{math: interest['osu!'].frequency * 2}}"
"{{math: memory.global.times_talked + 1}}"
"{{math: round(mood.energy / 10)}}"
```

Available functions: `abs`, `min`, `max`, `round`, `int`, `float`

### 4.14 string operations

```yaml
"{{upper: dep: setup.yaml | user.name}}"       # HARRY
"{{lower: dep: setup.yaml | user.name}}"       # harry
"{{capitalize: dep: setup.yaml | user.name}}"  # Harry
```

These wrap another BDL expression.

### 4.15 random numbers

```yaml
"{{random.int: 1-100}}"
"{{random.float: 0.0-1.0}}"
```

### 4.16 HTTP requests

```yaml
"{{request: GET 'https://api.example.com/data' | response['result']['value']
    on_fail: skip}}"

"{{request: GET 'https://api.example.com/score' | response['score']
    on_fail: 'couldn\\'t load score lol'}}"
```

- `on_fail: skip` — silently skips the whole dialogue line if status != 200
- `on_fail: 'message'` — displays that string instead
- All requests logged to console with status code
- Navigation: `response['key']['nested']` or `response['key'][0]` for arrays

### 4.17 mood references

```yaml
"{{mood.energy}}"     # 0–100
"{{mood.patience}}"
"{{mood.chaos}}"
"{{mood.warmth}}"
```

Read-only. Apply changes via `mood_effect` in the dialogue block.

### 4.18 affection

```yaml
"{{memory.affection}}"   # displayed value 0–1000
```

Read-only in BDL. Apply changes via `mood_effect: affection: increase` or `decrease`.

### 4.19 interest vectors

```yaml
"{{interest['osu!'].frequency}}"
"{{interest['anime'].depth}}"
"{{interest['music'].recency}}"
"{{interest['gaming'].sentiment}}"
```

- `depth` — 0–1000, how deep conversations on this topic have gone
- `frequency` — integer, times mentioned
- `recency` — unix timestamp of last mention
- `sentiment` — -1.0 to 1.0

---

## 5. Memory Namespaces

| Namespace | Description | Mod can read? | Mod can write? |
|-----------|-------------|---------------|----------------|
| `memory.global.*` | Persistent cross-session data | ✅ | ❌ |
| `memory.user.*` | Learned user data | ✅ | ❌ |
| `memory.session.*` | Current session only, cleared on close | ✅ | ❌ |
| `memory.repeat['ns::id'].*` | Per-dialogue repeat tracking | ✅ | ❌ |
| `memory.mod['mod_id'].*` | Sandboxed per-mod storage | ✅ (own) | ✅ (own only) |

**memory.mod sandboxing**: a mod can only write to `memory.mod['their_own_id'].*`. Writing to any other namespace is silently ignored.

---

## 6. Mood System

Bucko's mood is a 4D vector: `energy`, `patience`, `chaos`, `warmth`. All 0–100.

It's calculated from:
- Active interest vectors (depth, frequency, recency)
- Affection level (higher affection → higher baseline warmth)
- `mood_effect` deltas from triggered dialogue blocks

Mood decays back toward the configured baseline over time. Default decay rate: 1 unit per minute per dimension.

**You cannot set mood directly.** You can only:
1. Read it in BDL: `{{mood.energy}}`
2. Apply deltas via `mood_effect:`

```yaml
mood_effect:
  energy: +10     # can be negative
  patience: -15
  chaos: +5
  warmth: +3
```

Signs are optional — `+10` and `10` are both valid. `-15` is a decrease.

---

## 7. Interest Vectors

Every topic mentioned in conversation gets tracked as a 4D vector:

```
interest['topic_name']:
  depth      # 0–1000 — conversation depth on this topic
  frequency  # integer — times mentioned
  recency    # unix timestamp — last mention
  sentiment  # -1.0 to 1.0 — negative = love-hate, positive = genuine love
```

Topics are detected automatically based on conversation content. You can read them in BDL:

```yaml
"{{if interest['osu!'].depth > 200}} you know your stuff {{endif}}"
"{{if interest['anime'].sentiment > 0.7}} you genuinely love this {{endif}}"
```

Topics are free-form strings — whatever appears in conversation gets tracked.

---

## 8. Affection System

`memory.affection` is a global reserved value. Displayed as 0–1000. Stored internally as 0–1,000,000.

### Applying changes

```yaml
mood_effect:
  affection: increase   # or: decrease
```

That's it. You never specify an amount.

### How the curve works

- Getting closer to 1,000,000 makes each `increase` give less affection (diminishing returns)
- Getting closer to max also makes each `decrease` remove less (comfort zone effect)
- The client calculates amounts — mod authors never see the numbers

### Anti-exploit rules

1. Only ONE affection change per dialogue block counts. Extra `affection` fields are ignored.
2. The client tracks the last 5 delta amounts and calculates their mean.
3. If the current delta exceeds that mean, the change is silently ignored.
4. Chaining blocks to keep triggering affection is caught by this system.

**Bottom line**: you can't farm affection. Design dialogue that earns it naturally.

---

## 9. Repeat Handling

When a user triggers the same dialogue block multiple times, you can define escalating responses:

```yaml
on_repeat:
  threshold: 3          # starts escalating after this many repeats
  escalate:
    - "{{choice.cycle: ['repeat_1', 'repeat_2', 'repeat_3']}}"
  max_escalations: 3    # after this many, goes silent on that input
  cooldown: 300         # seconds before input works normally again
  forget_after_cooldown: false  # if true, reset repeat count after cooldown
```

**escalate** must use `choice` or `choice.cycle` — never a plain string. It's a list, so you can have different escalation levels:

```yaml
escalate:
  - "ok you've said this before"          # first escalation
  - "yeah I know, you said this already"  # second
  - "bro I'm ignoring you now"            # third
```

Repeat data in BDL:
```yaml
"{{memory.repeat['my_mod::my_block'].count}}"     # how many times triggered
"{{memory.repeat['my_mod::my_block'].last_time}}" # unix timestamp of last trigger
```

---

## 10. Trigger System

### Trigger types

```yaml
triggers:
  - keywords: ["word1", "word2", "phrase"]   # any keyword appears in input
  - exact: "exact phrase to match"           # exact match (case insensitive)
  - pattern: "regex (pattern|here)"          # regex match
  priority: 10
  condition: "{{if interest['osu!'].frequency > 5}}"
  cooldown: 60
```

The `priority`, `condition`, and `cooldown` fields go in the triggers list alongside the match conditions.

### Priority resolution

When multiple blocks match the same input:
1. Higher `priority` wins (default: 0)
2. On tie: `exact` > `pattern` > `keywords`
3. On further tie: first loaded wins (core loads before mods, mods load alphabetically)

**Give your mod triggers explicit priority values** to avoid conflicts with base game dialogue.

### "next" is reserved

The string `"next"` typed as input ALWAYS advances dialogue. It is intercepted before any trigger matching. Mods cannot override this. Don't add triggers for `"next"`.

### no_match

```yaml
no_match:
  - "{{choice.cycle: ['no_match_1', 'no_match_2', 'no_match_3']}}"
```

Fires when no trigger matches. Must use `choice` or `choice.cycle`. The IDs referenced must be dialogue blocks in the `no_match_responses` list in the same file.

---

## 11. Console Commands

### Custom mod commands

Register commands in `mod.yaml`:

```yaml
console_commands:
  - name: "leaderboard"
    description: "Show leaderboard data"
  - name: "settings"
    description: "Configure mod settings"
```

Users access them as `mod.[mod_id].[command]`.

### mod.[id].clean

Built-in for every mod. Clears `memory.mod['mod_id']` and cached data.

### Full command list

```
client.version
client.restart
client.quit
client.config.reload
client.config.validate

cache.clean

logs.clean
logs.export [path]

mod.list
mod.install [path/url]
mod.uninstall [mod_id]
mod.reload [mod_id]
mod.info [mod_id]
mod.validate [mod_id]
mod.enable [mod_id]
mod.disable [mod_id]
mod.[mod_id].clean
mod.[mod_id].[custom_command]

dialogue.list
dialogue.search [query]
dialogue.trigger [config::dialogue_id]
dialogue.reload
dialogue.clean

memory.dump
memory.get [namespace.key]
memory.clear [namespace]      ← asks for confirmation
memory.clean                  ← asks for confirmation

bucko.affection               ← shows displayed/internal value

debug.mood                    ← all 4 mood dimensions
debug.interest [topic]        ← all 4 interest dimensions for a topic
debug.hash.verify             ← verify save/memory hashes
debug.triggers.list           ← all loaded trigger labels
debug.triggers.search [query]

bucko.clean                   ← runs cache + logs + memory clean. asks first.
```

---

## 12. Mod Permissions

### What mods CAN do

- Add dialogue blocks and triggers
- Read `memory.user.*`, `memory.global.*`, `memory.repeat['*'].*`
- Write to `memory.mod['their_id'].*`
- Apply mood deltas via `mood_effect`
- Apply affection changes via `mood_effect: affection: increase/decrease`
- Add expressions/images
- Register console commands
- Make HTTP requests from BDL
- Chain to core dialogue blocks using `namespace::id` format

### What mods CANNOT do

- Override the `"next"` reserved keyword
- Directly set affection to a specific value
- Write to `memory.user.*`, `memory.global.*`, `memory.repeat.*`
- Access `saves/player.dat` directly
- Execute Python code
- Modify core loading behaviour

---

## 13. Dialogue ID Namespacing

Dialogue IDs are scoped to their config file. Full ID = `namespace::dialogue_id`.

| File | Namespace | Example full ID |
|------|-----------|-----------------|
| `core/setup.yaml` | `setup` | `setup::name_input` |
| `core/dialogue/base_game.yaml` | `base_game` | `base_game::greeting_general` |
| `mods/my_mod/dialogue.yaml` | `my_mod` | `my_mod::ask_osu` |

**Shorthand**: Within the same file, use just the ID. Cross-file requires `namespace::id`.

```yaml
# same file shorthand
next: "part2"

# cross-file (namespace required)
next: "setup::name_confirm"
next: "base_game::greeting_general"
```

In BDL `choice`:
```yaml
"{{choice: ['my_mod::local_dialogue', 'base_game::fallback']}}"
```

---

## 14. Edge Cases & Gotchas

**pause as last line + next = auto-chain**
If `pause:` is the final item in `lines:` AND the block has a `next:`, the next block loads automatically — no NEXT button shown.

**pause anywhere else**
Just waits, then continues. User still clicks NEXT at the end of the block.

**choice returning a dialogue ID**
If any option in `choice:` or `choice.cycle:` exactly matches a loaded full dialogue ID (`namespace::id`) or a shorthand ID in the same file, that block is triggered. Otherwise it's treated as raw text.

**BDL in next:**
```yaml
next: "{{if mood.chaos > 70}} chaos_path {{else}} normal_path {{endif}}"
```
Conditional chaining works in `next:`. The result is used as a dialogue ID lookup.

**HTTP on_fail: skip**
If the request fails AND `on_fail: skip`, the entire line is dropped silently. The typewriter never starts for that line.

**mod ID collision**
If two mod folders have the same `id` in their `mod.yaml`, the second one gets an error and doesn't load.

**choice.cycle state**
Cycle state is saved in the save file and persists across sessions. A cycle of 5 items will remember which have been used even after a restart.

**mood_effect parsing**
Both `+10` and `10` work as positive deltas. `-10` is negative. Quoted strings work too: `"+10"`.

**memory entry format**
Internally, memory entries are stored as `{value: ..., _ts: ..., _hash: ...}`. BDL always returns just the `value`. You don't need to worry about the wrapper.

**YAML apostrophes in strings**
Use single-quoted YAML strings and escape apostrophes: `'it\\'s fine'`. Or use double-quoted YAML strings: `"it's fine"`.

**dialogue_id uniqueness**
IDs must be unique within a single YAML file. Across files is fine — the namespace makes them unique globally.

**mod load order**
Core loads first, then mods in alphabetical order by folder name. If you need to guarantee load order relative to another mod, name your folder accordingly (e.g. `00_my_base_mod`, `01_my_extension`).

---

*that's everything. if something's not documented here, it's either not implemented yet or it's a bug. open an issue at [harsiz/Bucko](https://github.com/harsiz/Bucko).*
