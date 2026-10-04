"""Generate assets/icon.png and assets/icon.ico (an 'on air' broadcast mark). Requires Pillow."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

out = Path(sys.argv[1] if len(sys.argv) > 1 else "assets")
out.mkdir(parents=True, exist_ok=True)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((40, 40, S - 40, S - 40), radius=210, fill=(24, 26, 33, 255))
cx, cy = S // 2, S // 2 + 30
for i, r in enumerate((300, 210)):
    w = 52
    color = (229, 57, 53, 255) if i else (229, 57, 53, 170)
    d.arc((cx - r, cy - r, cx + r, cy + r), start=215, end=325, fill=color, width=w)
    d.arc((cx - r, cy - r, cx + r, cy + r), start=35, end=145, fill=color, width=w)
d.ellipse((cx - 95, cy - 95, cx + 95, cy + 95), fill=(255, 255, 255, 255))
d.ellipse((cx - 55, cy - 55, cx + 55, cy + 55), fill=(229, 57, 53, 255))

img.resize((256, 256), Image.LANCZOS).save(out / "icon.png")
img.save(out / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(f"icons written to {out}")
