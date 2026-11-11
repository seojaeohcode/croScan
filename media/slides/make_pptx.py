"""Build croScan_발표_구성안.pptx from pptx_src/ (see export_slides.mjs).

Each slide = the rendered page as a full-bleed picture, the demo clips placed as real playable videos over their
.vid boxes (poster = the clip's 대표화면), and the slide's <aside class="notes"> text in the notes pane.
"""
import json
import re
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.util import Emu

W = Path(__file__).parent
SRC = W / "pptx_src"
CLIPS = W.parent / "croScan_demo_videos" / "final19"
OUT = W / "croScan_발표_구성안.pptx"
PX = 12192000 / 1920  # EMU per css px (16:9, 13.333 in wide)


def clip(v):
    hits = [p for p in CLIPS.glob("croScan_V*.mp4") if re.match(rf"croScan_{re.escape(v)}_", p.name)]
    if len(hits) != 1:
        raise SystemExit(f"clip {v}: {len(hits)} matches")
    return hits[0]


prs = Presentation()
prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
blank = prs.slide_layouts[6]
meta = json.loads((SRC / "slides.json").read_text(encoding="utf-8"))
nv = 0
for s in meta:
    sl = prs.slides.add_slide(blank)
    jpg = SRC / f"s{s['n']:02d}.jpg"   # 2880×1620 JPEG: crisp on a 4K projector, far smaller than the 2× PNG
    Image.open(SRC / f"s{s['n']:02d}.png").convert("RGB").resize((2880, 1620), Image.LANCZOS).save(jpg, quality=90, subsampling=0)
    sl.shapes.add_picture(str(jpg), 0, 0, prs.slide_width, prs.slide_height)
    for v in s["vids"]:
        mp4 = clip(v["v"])
        poster = mp4.with_name(mp4.stem + "_대표화면.png")
        sl.shapes.add_movie(str(mp4), Emu(round(v["x"] * PX)), Emu(round(v["y"] * PX)), Emu(round(v["w"] * PX)),
                            Emu(round(v["h"] * PX)), poster_frame_image=str(poster) if poster.exists() else None,
                            mime_type="video/mp4")
        nv += 1
    if s["notes"]:
        sl.notes_slide.notes_text_frame.text = s["notes"]
prs.save(OUT)
print(f"{OUT.name}: {len(meta)} slides, {nv} videos, {OUT.stat().st_size / 1e6:.1f}MB")
