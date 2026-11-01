"""Redraw the 작업계획서 samples in the tidy form (server/workplan_pdf.py):

  samples/작업계획서/정리본_12건/작업계획서_<작업번호>_<업체>.pdf   the 12 plans, same values
  samples/작업계획서/정리본_6사12건24쪽.pdf                        all 12 in one file
  samples/작업계획서/빈양식/작업계획서_빈양식_<업체>.pdf          every value empty, one per company logo (+ 6사)

The team's original synthetic file stays as it is. Every redrawn file is read back and must give the same values.
  python tools/make_workplan_forms.py
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pymupdf

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))
# uploads made by this run go to a throwaway data folder (the app keeps uploads 7 days; a test run must not pile up)
_DATA = Path(tempfile.mkdtemp(prefix="croscan_test_data_"))
os.environ["CROSCAN_DATA"] = str(_DATA)
atexit.register(shutil.rmtree, _DATA, True)
from server import workplan as W, workplan_pdf as WP  # noqa: E402

SRC = APP / "samples/작업계획서/낱건_12건"
OUT = APP / "samples/작업계획서/정리본_12건"
BLANK = APP / "samples/작업계획서/빈양식"

files = sorted(SRC.glob("*.pdf"))
done = list(W.read_many([(f.name, f.read_bytes()) for f in files]))[-1]
d = W.CACHE / done["token"]
recs = done["plans"]
logos = [W._logo(d, r) for r in recs]

OUT.mkdir(parents=True, exist_ok=True)
for r, logo, f in zip(recs, logos, files):
    (OUT / f.name).write_bytes(WP.render([(r, {})], [logo]))
bundle = WP.render([(r, {}) for r in recs], logos)
(APP / "samples/작업계획서/정리본_6사12건24쪽.pdf").write_bytes(bundle)

BLANK.mkdir(parents=True, exist_ok=True)
for old in BLANK.glob("*.pdf"):
    old.unlink()
seen = {}
for r, logo in zip(recs, logos):
    seen.setdefault(r["company"], (r, logo))
for company, (r, logo) in seen.items():
    empty = {fk: "" for fk in r["doc"]["fields"]}
    (BLANK / f"작업계획서_빈양식_{company}.pdf").write_bytes(WP.render([(r, empty)], [logo]))
(BLANK / "작업계획서_빈양식_6사.pdf").write_bytes(WP.render([(r, {fk: "" for fk in r["doc"]["fields"]}) for r, _ in seen.values()],
                                                       [lg for _, lg in seen.values()]))

# read everything back
again = list(W.read_many([(f.name, f.read_bytes()) for f in sorted(OUT.glob("*.pdf"))]))[-1]["plans"]
bad = 0
for a, b in zip(recs, again):
    va = {x["label"]: x["value"] for x in a["items"]}
    vb = {x["label"]: x["value"] for x in b["items"]}
    diff = [k for k in va if va[k] != vb.get(k)] + [k for k in W.HEAD.values() if a[k] != b[k]]
    diff += ["확인 기록 표"] if (a["grid"] or {}).get("rows") != (b["grid"] or {}).get("rows") else []
    bad += len(diff)
    if diff:
        print("다름", a["work_no"], diff[:5])
blanks = list(W.read_many([(f.name, f.read_bytes()) for f in sorted(BLANK.glob("*.pdf"))]))[-1]["plans"]
print(f"정리본 {len(again)}건 다시 읽기: 값 차이 {bad}개 · 빈 양식 {len(seen)}종 + 6사 → {len(blanks)}건, "
      f"빈 칸 경고 {sum('빈 양식: 채워진 칸이 없음' in p['warnings'] for p in blanks)}건")
