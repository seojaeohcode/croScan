"""Where croScan puts each answer (QA #37 반영본), for a reviewer to judge row by row.

  python tools/dump_reflect.py > reflect_cases.md      (on the server: needs the ODL reader)

For each demo permit, and for copies of it with fields emptied (작업일시, 작업장소, 작업내용, 작업인원), every question
croScan asks is answered with each of its choices (a typed choice gets the example its own hint gives), one answer at a
time, and the plan is printed: what goes into which field of the 반영본, what goes to the 별지, what is to be checked.
"""
import copy
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_dr_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import augment, extract, reflect  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402


def example(c):
    """The value a typed choice's hint shows ('예) 3BAY 12-14 칼럼 E41P 블록 / 여러 곳이면 …' → the first example)."""
    ask = c.get("ask") or ""
    m = re.search(r"예\)\s*([^/]+)", ask)
    return (m.group(1) if m else ask).strip(" .")


def blank(fields, keys):
    f = copy.deepcopy(fields)
    for k, x in f.items():
        if x["key"] in keys:
            x["value"] = x["original"] = ""
    return f


def show(fields, R):
    out = []
    for P in R.values():
        for x in P["fills"]:
            out.append(f"칸 「{x['name']}」 {x['mode']}: '{x['original']}' → '{x['text']}'")
        out += [f"별지 보충 「{a}」: {b}" for a, b in P["extra"]]
        out += [f"확인 필요 「{a}」: {b}" for a, b in P["pending"]]
    return " / ".join(out) or "(아무것도 없음)"


VARIANTS = [("원본", ()), ("작업일시 빈칸", tuple(f"{a}_{i}" for i in range(1, 8) for a in ("date", "from", "to"))),
            ("작업 종료시각만 빈칸", ("to_1",)),
            ("작업장소 빈칸", ("location", "location_detail")), ("작업내용 빈칸", ("job", "job_detail")), ("작업인원 빈칸", ("workers",))]
n = 0
for d in load("permits.json")["permits"]:
    doc = extract.build(DIR / "허가서" / permit_name(d), d["kind"])
    for vname, keys in VARIANTS:
        if vname != "원본" and d["permit_no"][-4:] not in ("6733", "8175", "8741", "9488"):
            continue                                  # the emptied copies on one permit of each kind group
        fields = blank(doc["fields"], set(keys))
        qs = augment.summary(fields, [])["questions"]
        print(f"\n## {d['permit_no'][-4:]} {permit_name(d)} · {vname} · 질문 {len(qs)}개\n")
        print("| # | 질문 | 고른 답 | 입력 값 | croScan이 넣는 곳 |\n|---|---|---|---|---|")
        for q in qs:
            for c in q["choices"]:
                v = example(c) if c.get("ask") else ""
                if q["item"].startswith(("B1.", "B2.")) and c["id"] == "value":     # a real value of the field's type
                    t = next((f["type"] for f in fields.values() if f["key"] == q["item"].split(".", 1)[1]), "text")
                    v = {"count": "4", "number": "4.5", "phone": "010-1234-5678", "name": "홍길동", "date": "2026-10-29",
                         "time": "13:00", "yn": "Y"}.get(t, {"job": "E42P 블록 론지 균열부 가우징·재용접", "department": "대조립3부 용접2팀",
                                                             "hazards": "화재·불티, 용접흄"}.get(q["item"].split(".", 1)[1], v))
                a = {"qid": q["qid"], "choice": c["id"], "value": v, "q": q}
                if augment.check_value(fields, a):
                    continue                          # a value croScan would ask again for is not a final answer
                n += 1
                R = reflect.plan(fields, [a])
                txt = q["text"].replace("|", "/")
                print(f"| {n} | [{q['item']}] {txt} | {c['label']} | {v.replace('|', '/')} | {show(fields, R).replace('|', '/')} |")
print(f"\n전체 {n}행")
