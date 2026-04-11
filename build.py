"""
build.py — PyInstaller build script for Bucko.
Run: python build.py
Requires: pip install pyinstaller
"""
import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"

def main():
    print("Building Bucko.exe...")

    # Clean previous build
    if BUILD.exists():
        shutil.rmtree(BUILD)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",                      # no console window
        "--name", "Bucko",
        "--icon", str(ROOT / "core" / "expressions" / "default.png"),
        # Include engine package
        "--add-data", f"{ROOT / 'engine'}{os.pathsep}engine",
        # Exclude data dirs from the exe — they stay separate
        str(ROOT / "Bucko.py"),
    ]

    import os
    result = subprocess.run(cmd, cwd=str(ROOT))

    if result.returncode != 0:
        print("\nBuild failed.")
        sys.exit(1)

    exe = DIST / "Bucko.exe"
    if exe.exists():
        print(f"\nBuild successful: {exe}")
        print("\nIMPORTANT: Copy these folders next to Bucko.exe:")
        print("  core/")
        print("  mods/")
        print("  saves/")
        print("  logs/")
        print("  client_config.yaml")
    else:
        print("\nBuild may have failed — exe not found at expected location")

if __name__ == "__main__":
    main()
