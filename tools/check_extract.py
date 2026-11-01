"""Grade the extractor on every PDF the generator wrote: samples/_truth.json is the key.
    python tools/check_extract.py            all files
    python tools/check_extract.py 시연        demo set only (samples/시연/); '보관' for the archive
Every page: the permit kind, every common value, the work-date rows, the kind's value
lines, and every checkbox of the common sections and of the kind's 추가정보 block."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import extract, form_spec, permit_kinds as PK  # noqa: E402

truth = json.loads((ROOT / "samples" / "_truth.json").read_text(encoding="utf-8"))
only = sys.argv[1] if len(sys.argv) > 1 else ""
total_ok = total = 0
for name, pages in truth.items():
    if only not in name:
        continue
    doc = extract.build(ROOT / "samples" / name, [p["kind"] for p in pages])   # the kind the applicant would pick
    fs = doc["fields"]
    ok = bad = 0
    misses = []
    for no, key in enumerate(pages, 1):
        kind = key["kind"]
        got_kind = doc["pages"][no - 1]["kind"]
        ok += got_kind == kind; bad += got_kind != kind
        if got_kind != kind:
            misses.append(f"p{no}.kind: want {kind} got {got_kind}")
        want = {k: v for k, v in key.items() if k not in ("days", "checks", "kind")}
        for i in range(form_spec.DATE_ROWS):
            d = key["days"][i] if i < len(key["days"]) else ("", "", "")
            want.update({f"date_{i + 1}": d[0], f"from_{i + 1}": d[1], f"to_{i + 1}": d[2]})
        for k, _, t, _ in form_spec.FIELDS:
            if t != "image":
                want.setdefault(k, "")
        for k, *_ in PK.values(kind):
            want.setdefault(k, "")
        for k, _, _ in form_spec.CHECKS + PK.checks(kind):
            want[k] = k in key["checks"]
        for k, v in want.items():
            f = fs.get(f"p{no}.{k}")
            if f is None and (k.startswith("face_") or v in ("", False)):
                continue          # not on this copy (e.g. no 안전대면허가 row on 게시용)
            if f is not None and f["type"] == "image":
                continue
            got = None if f is None else f["value"]
            good = got == v or (isinstance(v, str) and str(got).replace(" ", "") == v.replace(" ", ""))
            ok += good; bad += not good
            if not good:
                misses.append(f"p{no}.{k}: want {v!r} got {got!r}")
    total_ok += ok; total += ok + bad
    kinds = " ".join(p["kind_label"] for p in doc["pages"])
    print(f"{name}: {ok}/{ok + bad}  [{kinds}]")
    for m in misses[:15]:
        print("   ", m)
print(f"\nall: {total_ok}/{total}")
