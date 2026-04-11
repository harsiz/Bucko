# Installation Guide

## Requirements

- Python 3.10+
- pip

## Install

```bash
git clone https://github.com/harsiz/Bucko
cd Bucko
pip install -r requirements.txt
```

## Optional: Generate placeholder expression images

```bash
python core/expressions/create_placeholders.py
```

This creates small PNG images for each expression state. Bucko falls back to ASCII faces if images aren't found, so this step is optional.

## Run

```bash
python Bucko.py
```

## Build to exe (Windows)

```bash
pip install pyinstaller
python build.py
```

The compiled `Bucko.exe` will be in `dist/`. Copy these alongside it:

```
Bucko.exe
client_config.yaml
core/
mods/
saves/
logs/
```

## Installing mods

1. Download a mod folder (should contain `mod.yaml`)
2. Drop the folder into `mods/`
3. Restart Bucko or run `mod.reload [mod_id]` in the console

## Troubleshooting

**"ttkbootstrap not installed"** — run `pip install ttkbootstrap`

**Save file hash mismatch warning** — you (or something) manually edited `saves/player.dat`. Bucko will still load but warns you.

**Discord RPC not showing** — make sure Discord is open. Bucko silently skips RPC if Discord isn't running.

**Mod not loading** — check console for errors. Common issues: invalid mod ID (no spaces/special chars), missing `mod.yaml`, YAML syntax errors.
