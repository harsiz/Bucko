"""
Run this once to generate placeholder expression PNG files.
Requires Pillow: pip install Pillow
"""
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("Pillow not available — skipping PNG generation")

EXPRESSIONS = {
    "default":   ("(^_^)",  "#1a1a2e", "#7ec8e3"),
    "happy":     ("(^▽^)",  "#1a2e1a", "#7ee38f"),
    "surprised": ("(O_O)",  "#2e1a2e", "#e37ec8"),
    "confused":  ("(?_?)",  "#2e2a1a", "#e3c87e"),
    "sad":       ("(;_;)",  "#1a1a2e", "#7ea8e3"),
    "smug":      ("(¬‿¬)",  "#1a1a1a", "#c8c8c8"),
    "angry":     ("(>_<)",  "#2e1a1a", "#e37e7e"),
    "thinking":  ("(._. )", "#1a2a2e", "#7ec8c8"),
}

def create_placeholder(name: str, face: str, bg: str, fg: str, size=(160, 160)) -> None:
    if not HAS_PILLOW:
        return
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except (IOError, OSError):
        font = ImageFont.load_default()

    # Center the text
    bbox = draw.textbbox((0, 0), face, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size[0] - tw) // 2
    y = (size[1] - th) // 2
    draw.text((x, y), face, fill=fg, font=font)

    out = Path(__file__).parent / f"{name}.png"
    img.save(out)
    print(f"Created: {out.name}")

if __name__ == "__main__":
    if HAS_PILLOW:
        for name, (face, bg, fg) in EXPRESSIONS.items():
            create_placeholder(name, face, bg, fg)
        print("Done!")
    else:
        print("Install Pillow to generate placeholder images: pip install Pillow")
