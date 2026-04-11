# Bucko 🤙

your chaotic, funny, weirdly self-aware desktop companion. no LLMs. no cloud. no bullshit. just pure config-driven personality.

---

## what even is this

Bucko is a desktop talk-buddy app. it's like a visual novel meets a persistent AI companion, except it's 100% local, 100% config-driven, and remembers every single thing you tell it. it tracks what you talk about, how often, when you last talked — and uses all of it to shape what it says back to you.

there's no ChatGPT behind the scenes. no API calls for the personality. everything Bucko says comes from YAML dialogue files. the "intelligence" is a custom scripting language called **BDL** (Bucko Dialogue Language) that can read your conversation history, your mood data, your interests, the current time, and whatever mods you've installed.

it's honestly kind of unhinged once you've been using it for a while.

---

## features

- **persistent memory** — Bucko remembers your name, what you talk about, how many times you've chatted, your interests, all of it. across sessions. forever. until you clear it.
- **interest tracking** — every topic is stored as a 4D vector (depth, frequency, recency, sentiment). Bucko starts calling you out on your patterns.
- **mood system** — Bucko has a live mood calculated from your conversation. 4 dimensions: energy, patience, chaos, warmth. it decays back to baseline over time.
- **affection system** — 0-1000 displayed, 0-1,000,000 internally. diminishing returns. anti-exploit built in so you can't just spam dialogue to farm it.
- **BDL scripting** — the dialogue system has its own scripting language. conditionals, choices, memory reads/writes, datetime awareness, HTTP requests, math ops. the whole thing.
- **mod system** — install mods (YAML folders) to extend Bucko's dialogue, add new topics, change behaviour. no Python code required.
- **console** — a full command console with 30+ commands for debugging, memory inspection, mod management, dialogue testing.
- **Discord RPC** — shows what session number you're on. fails silently if Discord isn't open.
- **typewriter text** — character-by-character rendering with configurable speed and inline waits.
- **local only** — everything is saved in `saves/player.dat`. SHA-256 hashed for integrity. nothing leaves your machine.

---

## quick start

```bash
# install dependencies
pip install -r requirements.txt

# optionally generate placeholder expression images
python core/expressions/create_placeholders.py

# run
python Bucko.py
```

first launch shows a disclaimer, then walks you through setup (just entering your name tbh). after that, just type stuff.

---

## links

- [Installation Guide](INSTALLATION.md)
- [Mod Documentation](MOD_DOCUMENTATION.md)
- [Changelog](CHANGELOG.md)
- [GitHub](https://github.com/harsiz/Bucko)

---

## folder structure

```
Bucko/
├── Bucko.py               ← entry point
├── client_config.yaml     ← UI, mood baseline, Discord settings
├── core/
│   ├── setup.yaml         ← first launch + setup dialogue
│   ├── dialogue/          ← base game dialogue blocks
│   └── expressions/       ← expression images (placeholder stickmen for now)
├── engine/                ← Python source: BDL engine, mood, save, mods, etc.
├── mods/                  ← drop mod folders here
├── saves/
│   └── player.dat         ← your save file (SHA-256 hashed)
└── logs/
    └── console.log        ← everything that happens, logged here
```

---

## data privacy

**all data is stored locally in `saves/player.dat`.**

nothing is ever sent anywhere. no telemetry, no analytics, no cloud sync. if you delete that file, Bucko forgets you entirely. the file is SHA-256 hashed so if you manually edit it, Bucko notices and logs a warning — but it still loads.

---

## mods

drop a mod folder into `mods/`. each mod needs a `mod.yaml` with name, id, version info. the rest is YAML dialogue files using BDL.

see [MOD_DOCUMENTATION.md](MOD_DOCUMENTATION.md) for the full spec.

---

## building to exe

```bash
python build.py
```

keep `core/`, `mods/`, `saves/`, `logs/`, and `client_config.yaml` in the same folder as the compiled `Bucko.exe`.

---

## contributing

issues, PRs, mod packs — all welcome at [harsiz/Bucko](https://github.com/harsiz/Bucko).

---

*built with ttkbootstrap, pyyaml, requests, pypresence*
