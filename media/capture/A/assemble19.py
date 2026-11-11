"""Split the foreman shots into the PRAI clip projects v01..v11 and turn the submission's own PDF into viewer shots.
usage: python assemble19.py [v01 …]
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import fitz  # PyMuPDF

W = Path(__file__).parent
CAPS = {"A": W / "capA", "B": W / "capB"}
PLAN = {  # clip → shot-name prefixes it needs (2026-11-02 15h conti: V05–V11 continue from take B; take A only in V03)
    "v01": ["B_s01", "B_s02", "B_s03", "B_s05"],
    "v02": ["B_s06", "B_s07", "B_s08"],
    "v03": ["A_s08", "A_s09", "A_s10"],
    "v04": ["B_s08", "B_s09", "B_s10", "A_s10"],
    "v05": ["B_s10", "B_s11", "B_s12", "B_s13"],
    "v06": ["B_s14", "B_s15", "B_s16"],
    "v07": ["B_s16", "B_s17", "B_s18"],
    "v08": ["B_s19", "B_s20"],
    "v09": ["B_s18", "B_s21"],
    "v10": ["B_s22", "B_s23", "B_s24"],
    "v11": ["B_s25", "B_s26", "B_s27", "B_s28", "PDF_"],
}
BLUE = lambda c: ((c >> 16) & 255) < 90 and (c & 255) > 140   # the blue text croScan writes into the reflected copy


def pdf_shots():
    """render the submission's permit PDF (page 1 = 사전검토 반영본, page 2 = 추가검토서) in a viewer frame, and find what to zoom on"""
    out = W / "pdfshots"
    out.mkdir(exist_ok=True)
    f = next(iter(sorted((CAPS["B"] / "pdf").glob("*_permit.pdf"))), None)   # the take-B submission
    if not f:
        return out, {}
    doc = fitz.open(f)
    DPI = 160
    k = DPI / 72
    info, html = {}, []
    for i, pg in enumerate(doc):
        if i >= 2:
            break
        png = out / f"PDF_p{i + 1}.png"
        pg.get_pixmap(dpi=DPI).save(png)
        boxes = {}
        if i == 0:   # blue (reflected) spans
            bl = [s["bbox"] for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip() and BLUE(s["color"])]
            boxes["blue"] = bl
            boxes["blue_text"] = [s["text"] for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip() and BLUE(s["color"])]
            boxes["permit"] = [r for r in pg.search_for("0731")][:1]
            boxes["t0800"] = [r for r in pg.search_for("08:00")][:1]
            boxes["t1659"] = [r for r in pg.search_for("16:59")][:1]
        else:
            words = pg.get_text("dict")
            boxes["lines"] = [(s["text"], s["bbox"]) for b in words["blocks"] for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]
        info[f"PDF_p{i + 1}"] = {"png": png, "size": (pg.rect.width, pg.rect.height), "boxes": boxes, "total": doc.page_count}
    for name, d in info.items():
        n = int(name[-1])
        page = f"""<!doctype html><meta charset=utf-8><style>body{{margin:0;width:1920px;height:1080px;background:#525659;font:16px 'Malgun Gothic',sans-serif;overflow:hidden}}
.bar{{height:44px;background:#323639;color:#eee;display:flex;align-items:center;padding:0 20px;gap:14px}}.bar b{{color:#fff}}
img{{display:block;margin:18px auto 0;height:1000px;box-shadow:0 4px 18px rgba(0,0,0,.5);background:#fff}}</style>
<div class=bar><b>제출본 {f.name.split('_')[0][:6]} · 허가서(원본+추가검토서).pdf</b><span>{n} / {d['total']}쪽</span></div><img id=pg src="{d['png'].as_uri()}">"""
        (out / f"{name}.html").write_text(page, encoding="utf-8")
    js = "const { chromium } = require('C:/Users/seoco/OneDrive/Desktop/PRAI/node_modules/playwright-core');\n(async () => {\n const b = await chromium.launch({ channel: 'msedge', headless: true });\n const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });\n const R = {};\n"
    for name in info:
        hp = out / f"{name}.html"
        js += f" await p.goto({json.dumps(hp.as_uri())}); await p.waitForTimeout(500);\n R[{json.dumps(name)}] = await p.evaluate(() => {{ const r = document.querySelector('#pg').getBoundingClientRect(); return {{ x: r.left, y: r.top, w: r.width, h: r.height }}; }});\n await p.screenshot({{ path: {json.dumps(str(out / (name + '.shot.png')))} }});\n"
    js += f" require('fs').writeFileSync({json.dumps(str(out / 'pages.json'))}, JSON.stringify(R));\n await b.close();\n}})();\n"
    (out / "shoot.cjs").write_text(js, encoding="utf-8")
    subprocess.run(["node", str(out / "shoot.cjs")], check=True)
    pages = json.loads((out / "pages.json").read_text(encoding="utf-8"))
    rects = {}
    for name, d in info.items():
        pr = pages[name]
        s = pr["w"] / d["size"][0]
        to = lambda bb: {"x": round(pr["x"] + bb[0] * s), "y": round(pr["y"] + bb[1] * s), "w": max(1, round((bb[2] - bb[0]) * s)), "h": max(1, round((bb[3] - bb[1]) * s))}
        r = {"page": {k2: round(v) for k2, v in pr.items()}}
        r["top"] = {"x": r["page"]["x"], "y": r["page"]["y"], "w": r["page"]["w"], "h": round(r["page"]["h"] * 0.45)}
        if d["boxes"].get("blue"):
            bb = d["boxes"]["blue"]
            r["blue"] = to((min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb)))
            for j, b in enumerate(bb):
                r[f"blue{j}"] = to(b)
        if d["boxes"].get("permit"):
            r["permit"] = to(tuple(d["boxes"]["permit"][0]))
        for k in ("t0800", "t1659"):
            if d["boxes"].get(k):
                r[k] = to(tuple(d["boxes"][k][0]))
        for j, (t, b) in enumerate(d["boxes"].get("lines", [])):
            r[f"l{j}"] = to(b)
        rects[name] = r
    (out / "pdfinfo.json").write_text(json.dumps({n: {"boxes": {k2: v for k2, v in d["boxes"].items()}, "size": d["size"]} for n, d in info.items()}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out, rects


def main():
    pdir, prects = pdf_shots()
    allr = {}
    for d in CAPS.values():
        f = d / "public" / "shots" / "rects.json"
        if f.exists():
            allr.update(json.loads(f.read_text(encoding="utf-8")))
    allr.update(prects)
    allr["_page"] = {"w": 1920, "h": 1080}
    (W / "allrects.json").write_text(json.dumps(allr, ensure_ascii=False, indent=1), encoding="utf-8")
    music = W.parent.parent / "work" / "groove.mp3"
    only = sys.argv[1:]
    for proj, prefixes in PLAN.items():
        if only and proj not in only:
            continue
        sd = W / proj / "public" / "shots"
        if sd.exists():
            shutil.rmtree(sd)
        sd.mkdir(parents=True)
        (W / proj / "public" / "music").mkdir(parents=True, exist_ok=True)
        shutil.copy(music, W / proj / "public" / "music" / "groove.mp3")
        keep = {"_page": allr["_page"]}
        for name, r in allr.items():
            if any(name.startswith(p) for p in prefixes):
                src = next((d / "public" / "shots" / f"{name}.png" for d in CAPS.values() if (d / "public" / "shots" / f"{name}.png").exists()), None)
                if src is None and (pdir / f"{name}.shot.png").exists():
                    src = pdir / f"{name}.shot.png"
                if src is not None:
                    shutil.copy(src, sd / f"{name}.png")
                    keep[name] = r
        (sd / "rects.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
        print(proj, len(keep) - 1, "shots")


if __name__ == "__main__":
    main()
