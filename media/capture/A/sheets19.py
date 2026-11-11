"""Contact sheets from the finished clips: one frame every 2 s, time in the top-left corner of each cell.
usage: python sheets19.py v01 v02 …   → work19/sheets/V01_sheet.png …
"""
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

PRAI = Path("C:/Users/seoco/OneDrive/Desktop/PRAI")
FF = str(PRAI / "node_modules/ffmpeg-static/ffmpeg.exe")
OUT = Path(__file__).parent.parent / "sheets"
OUT.mkdir(exist_ok=True)
font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 18)
for v in sys.argv[1:]:
    mp4 = PRAI / "out" / v / f"{v}.mp4"
    tmp = OUT / f"_{v}_%03d.png"
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", str(mp4), "-vf", "fps=0.5,scale=640:-1", str(tmp)], check=True)
    frames = sorted(OUT.glob(f"_{v}_[0-9][0-9][0-9].png"))
    cols = 5
    sheet = Image.new("RGB", (640 * cols, 360 * ((len(frames) + cols - 1) // cols)), "#111")
    d = ImageDraw.Draw(sheet)
    for i, f in enumerate(frames):
        x, y = (i % cols) * 640, (i // cols) * 360
        sheet.paste(Image.open(f), (x, y))
        d.rectangle([x, y, x + 64, y + 24], fill="black")
        d.text((x + 5, y + 1), f"{i * 2}s", fill="#FFE14D", font=font)
        f.unlink()
    name = "V" + v[1:].upper()
    sheet.save(OUT / f"{name}_sheet.png")
    print(name, len(frames), "frames")
