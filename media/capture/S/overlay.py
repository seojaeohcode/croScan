"""Draw every measured rect (name + box) on a shot, half size, for choosing marks. usage: python overlay.py <capdir> <shot> [<shot> ...]"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

cap = Path(sys.argv[1]) / "public" / "shots"
R = json.loads((cap / "rects.json").read_text(encoding="utf-8"))
out = Path(__file__).parent / "overlay"
out.mkdir(exist_ok=True)
font = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", 15)
for name in sys.argv[2:]:
    im = Image.open(cap / f"{name}.png").convert("RGB")
    sx = im.width / 1920
    im = im.resize((1280, 720))
    k = 1280 / 1920
    d = ImageDraw.Draw(im)
    for i, (rn, r) in enumerate((R.get(name) or {}).items()):
        rs = r if isinstance(r, list) else [r]
        for b in rs:
            if not b:
                continue
            x, y, w, h = b["x"] * k, b["y"] * k, b["w"] * k, b["h"] * k
            col = ["#E8710A", "#0A7BE8", "#18A050", "#C02060"][i % 4]
            d.rectangle([x, y, x + w, y + h], outline=col, width=2)
            d.text((x + 2, y + 1), f"{rn} {b['x']},{b['y']},{b['w']},{b['h']}", fill=col, font=font)
    im.save(out / f"{name}.png")
    print(name, {k2: (v if not isinstance(v, dict) else [v["x"], v["y"], v["w"], v["h"]]) for k2, v in (R.get(name) or {}).items()})
