"""V12–V19 + V14B + V17B PRAI projects for the 21-clip conti (captions 30–57), from the shots of cap1 (V12–V14, V14B ask),
capF (0735 foreman resubmission), cap2 (V14B after, V15–V19). Captions are read verbatim from the 57-caption file; 42 and 40
are chosen from the real results in the logs (see CHOICE). Writes v12..v19, v14b, v17b /prai.json and scenemap21.json.
usage: python build21.py
"""
import json
import re
import shutil
from pathlib import Path

S = Path(__file__).parent
W19 = S.parent
WORK = W19.parent / "work"
CAPS = [S / "cap1", S / "capF", S / "cap2"]
MERGED = S / "capM" / "public" / "shots"
C = json.loads((WORK / "common.json").read_text(encoding="utf-8"))
SUBS = W19 / "croScan_최종자막_57개_수정반영본_2026-11-02.md"
URL = "위험작업 허가서 사전검토 · 스테이징 화면"
CAPT = {}
for line in SUBS.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\|\s*(\d+)\s*\|\s*V\d+B?-\d+\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$", line)
    if m:
        CAPT[int(m.group(1))] = (m.group(2), None if m.group(3) == "—" else m.group(3))
assert len(CAPT) == 57, len(CAPT)


def events(p):
    return {e["k"]: e["v"] for e in json.loads(p.read_text(encoding="utf-8"))["events"]} if p.exists() else {}


L1, LF, L2 = events(S / "cap1" / "log_S21_1.json"), events(S / "capF" / "log_F.json"), events(S / "cap2" / "log_S21_2.json")
# 42: the real AI review result → the conti's line for it
rv = L2.get("pair_review_api") or {}
C42 = {"held": "근거가 부족한 내용은 보류로 남깁니다.", "ok": "AI의 추가 제안을 양쪽 서류와 대조합니다.", "suggest": "AI의 추가 제안을 양쪽 서류와 대조합니다.",
       "none": "이번 검토에서는 추가 관계를 찾지 못했습니다."}.get(rv.get("status"), "추가 검토를 완료하지 못했습니다.")
CAPT[42] = (C42, CAPT[42][1])
# 40: the completed line only when the resubmission really went in and the manager's screen used it
sub_new = (LF.get("submission_0735_after") or {}).get("id")
sub_old = (LF.get("submission_0735_before") or {}).get("id")
used = ((L2.get("detect_after_resubmit") or {}).get("versions") or {}).get("0735") or {}
RESUBMITTED = bool(sub_new and sub_new != sub_old and used.get("sub") == sub_new)
if not RESUBMITTED:
    CAPT[40] = ("확인한 답은 반장이 보완·재제출해 다시 검토하도록 합니다.", CAPT[40][1])
CHOICE = {"42": {"status": rv.get("status"), "why": rv.get("why"), "caption": C42},
          "40": {"resubmitted": RESUBMITTED, "sub_before": sub_old, "sub_after": sub_new, "used_by_manager": used, "caption": CAPT[40][0]}}
BPM = C["music"]["bpm"]
SPECS, SCENEMAP = {}, {}


def B(x, y, w, h):
    return {"box": [x, y, w, h]}


def D(proj, cap, id, shot, camera=None, marks=None, clicks=None, swaps=None, typing=None, cues=None, beats="auto", hat=None):
    """one demo scene; caption `cap` starts half a beat after the first mark unless `hat` is given"""
    first = min(m["at"] for m in marks) if marks else 2
    hat = hat if hat is not None else first + 0.5
    last = max([m.get("until", m["at"] + 2) for m in marks or []] + [c["at"] + 1.5 for c in camera or []] + [s["at"] + 2 for s in swaps or []]
               + [c["at"] + 1.5 for c in clicks or []] + [0])
    need = max(8, -(-(hat + 5) // 2) * 2 if cap else 0, -(-last // 2) * 2)
    beats = max(beats, need) if isinstance(beats, int) else int(need)
    d = {"id": id, "type": "demo", "shot": shot, "url": URL, "camera": camera or [], "marks": marks or [], "clicks": clicks or [], "swaps": swaps or [],
         "typing": typing or [], "cues": cues or [], "beats": beats}
    return _cap(proj, cap, d, hat, [shot] + [s["shot"] for s in swaps or []])


def M(proj, cap, id, cues, beats, hat=2, bg="brand"):
    """one motion scene (PRAI blocks only: no app screen)"""
    d = {"id": id, "type": "motion", "bg": bg, "intensity": "low", "cues": cues, "beats": beats}
    return _cap(proj, cap, d, hat, [])


def _cap(proj, cap, d, hat, shots):
    if cap:
        head, sub = CAPT[cap]
        d["headline"] = {"text": head, **({"sub": sub} if sub else {}), "at": hat}
    SCENEMAP.setdefault(proj, []).append({"scene": d["id"], "caption": cap, "hat": hat if cap else None, "beats": d["beats"],
                                          "headline": CAPT[cap][0] if cap else None, "sub": CAPT[cap][1] if cap else None, "shots": shots})
    return d


def spec(title, scenes):
    s = {"$schema": "C:/Users/seoco/OneDrive/Desktop/PRAI/schema/prai.schema.json", **json.loads(json.dumps(C))}
    s["theme"].pop("logo", None)
    s["video"] = {**C["video"], "title": title}
    s["scenes"] = scenes
    return s


def K(text, y=58):
    return [{"block": "kicker", "text": text, "tone": "brand", "at": 0, "y": y, "enter": "cut"}]


# scene definitions live in scenes21.py (boxes measured on the shots of this capture)
exec((S / "scenes21.py").read_text(encoding="utf-8"))

# merge the three captures' shots and rects into one folder
MERGED.mkdir(parents=True, exist_ok=True)
rects = {}
for cap in CAPS:
    d = cap / "public" / "shots"
    if (d / "rects.json").exists():
        rects.update(json.loads((d / "rects.json").read_text(encoding="utf-8")))
    for f in d.glob("*.png"):
        shutil.copy(f, MERGED / f.name)
rects["_page"] = {"w": 1920, "h": 1080}
(MERGED / "rects.json").write_text(json.dumps(rects, ensure_ascii=False, indent=1), encoding="utf-8")

for name, s in SPECS.items():
    d = S / name
    if (d / "public" / "shots").exists():
        shutil.rmtree(d / "public" / "shots")
    (d / "public" / "shots").mkdir(parents=True, exist_ok=True)
    (d / "public" / "music").mkdir(parents=True, exist_ok=True)
    shutil.copy(WORK / "groove.mp3", d / "public" / "music" / "groove.mp3")
    used_shots = set()
    for sc in s["scenes"]:
        if sc["type"] != "demo":
            continue
        used_shots.add(sc["shot"]); used_shots.update(x["shot"] for x in sc["swaps"])
        for k in ("camera", "marks", "clicks"):
            for x in sc[k]:
                refs = x.get("to", x.get("on"))
                for r in refs if isinstance(refs, list) else [refs]:
                    if isinstance(r, str) and "." in r:
                        used_shots.add(r.split(".")[0])
    for f in used_shots:
        shutil.copy(MERGED / f"{f}.png", d / "public" / "shots" / f"{f}.png")
    keep = {k: v for k, v in rects.items() if k == "_page" or k in used_shots}
    (d / "public" / "shots" / "rects.json").write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8")
    (d / "prai.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
sec = 60 / BPM
for proj, rows in SCENEMAP.items():
    t = 0
    for r in rows:
        r["start_s"] = round(t * sec, 2)
        if r["caption"]:
            r["cap_start_s"] = round((t + r["hat"]) * sec, 2)
            r["cap_end_s"] = round((t + r["beats"]) * sec, 2)
        t += r["beats"]
    rows.append({"total_s": round(t * sec, 2)})
(S / "scenemap21.json").write_text(json.dumps({"choice": CHOICE, "clips": SCENEMAP}, ensure_ascii=False, indent=1), encoding="utf-8")
print("specs:", {p: r[-1]["total_s"] for p, r in SCENEMAP.items()}, "| 42:", C42, "| 40 resubmitted:", RESUBMITTED)
