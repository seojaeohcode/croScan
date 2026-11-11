"""QA #37 check: the 사전검토 반영본 on the 10 demo permits with their scenario answers (and some bad answers).

  python tools/check_reflect.py          (on the server: needs the ODL reader, like make_demo_day)

What must hold, whatever the permit: nothing written in a day-of-work, signature, approval or check field; 「모름」 and
button names never written; an actual working window (T1) never changes the 신청 작업일시; another team's details not in
this permit's fields; the same input gives the same plan; the PDF has the planned values on its pages and the uploaded
bytes are unchanged. It prints each permit's fields written and kept aside, to read against the design (QA #37).
"""
import copy
import hashlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_rf_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import pymupdf  # noqa: E402

from server import addendum, augment, extract, reflect  # noqa: E402
from make_demo_day import converse, load, permit_name  # noqa: E402

PERMITS = load("permits.json")["permits"]

DIR = ROOT / "samples" / "시연_하루" / "허가서"
ok = bad = 0


def expect(c, what):
    global ok, bad
    ok, bad = ok + bool(c), bad + (not c)
    if not c:
        print("  FAIL", what)


LABELS = ("위치 입력", "값 입력", "맞는 값 입력", "높이 입력", "번호 입력", "경로 입력", "시각·설비 입력", "방법·가스 입력", "실제 시간대 입력")
for d in PERMITS:
    name = permit_name(d)
    kind = d["kind"]
    src = DIR / name
    doc = extract.build(src, kind)
    answers, s, _ = converse(doc["fields"], d.get("answers_truth", {}), d["permit_no"])
    R = reflect.plan(doc["fields"], answers)
    R2 = reflect.plan(doc["fields"], copy.deepcopy(answers))
    pid = next(iter(R))
    P = R[pid]
    print(f"\n== {d['permit_no']} {name} · 답 {len(answers)}")
    for x in P["fills"]:
        print(f"  {x['mark']} {x['name']}: '{x['original']}' → {x['mode']} '{x['text']}'  ({', '.join(x['src'])})")
    for a, b in P["extra"]:
        print(f"  [보충] {a}: {b}")
    for a, b in P["pending"]:
        print(f"  [확인] {a}: {b}")
    expect(R == R2, f"{name}: 같은 입력이면 같은 반영")
    expect(not any(x["base"] in reflect.NEVER for x in P["fills"]), f"{name}: 당일·서명·승인 칸에 쓰지 않음")
    expect(not any("모름" in x["text"] for x in P["fills"]), f"{name}: 「모름」을 칸에 쓰지 않음")
    expect(not any(lb in x["text"] for x in P["fills"] for lb in LABELS), f"{name}: 버튼 이름을 칸에 쓰지 않음")
    t1 = next((a for a in answers if a["qid"].startswith("T1:")), None)
    expect(not any(x["base"].startswith(("from_", "to_", "date_")) for x in P["fills"]) or not t1, f"{name}: T1 답은 신청 작업일시를 바꾸지 않음")
    b3 = next((a for a in answers if a["qid"].startswith("B3:")), None)
    if b3 and b3["choice"] in ("yes", "no"):
        cc = next((x for x in P["fills"] if x["base"] == "concurrent"), None)
        expect(cc and cc["text"] == ("Y" if b3["choice"] == "yes" else "N"), f"{name}: 병행여부 {b3['choice']} → Y/N 칸")
        if b3["choice"] == "yes" and b3.get("value"):
            expect(not any(b3["value"] in x["text"] for x in P["fills"]), f"{name}: 다른 팀 작업 내용은 내 칸에 넣지 않음")
    # the PDF: the planned values are on the pages, the uploaded bytes are not touched
    data = src.read_bytes()
    h0 = hashlib.sha256(data).hexdigest()
    s["reflect"] = R
    out = addendum.pdf(data, addendum.build(s, doc["fields"]), doc["fields"], R)
    expect(hashlib.sha256(data).hexdigest() == h0 and hashlib.sha256(src.read_bytes()).hexdigest() == h0, f"{name}: 업로드 원본은 그대로")
    with pymupdf.open(stream=out, filetype="pdf") as o:
        n = o.page_count - 1 if o.page_count > 1 else 1
        text = " ".join(o[i].get_text() for i in range(len(doc["pages"]))).replace("\n", " ")
        for x in P["fills"]:
            words = [w for w in x["text"].replace(",", " ").split() if len(w) > 1][:3]
            expect(all(w in text for w in words), f"{name}: 반영본에 '{x['text']}'이(가) 있음")
            if x["mode"] == "replace" and x["original"].strip() and x["original"].strip() not in x["text"]:
                expect(x["original"].strip() not in text.replace(x["text"], ""), f"{name}: 바꾼 칸의 이전 값 '{x['original']}'은 반영본 글자층에 남지 않음")
        expect(("사전검토 반영본" in o[0].get_text()) == bool(P["fills"]), f"{name}: 반영이 있으면 반영본 표시")
        p1 = " ".join(o[0].get_text().split())
        for lab in ("작업장소(LOCATION)", "작업내용(JOB DESCRIPTION)", "병행여부", "승인번호(PERMIT NO.)"):
            expect(lab in p1, f"{name}: 바꾼 칸 옆의 양식 라벨 '{lab}'은 그대로")
    if d["permit_no"].endswith("8741"):            # 「추가로 적은 내용이 맞음」 withdraws the earlier 'none' (C5)
        pid0 = d["permit_no"]
        c5 = answers + [{"qid": f"C5.LI2:{pid0}", "choice": "free", "value": "블록 안 취부 2명, 10:00 철수", "q": {}}]
        P5 = reflect.plan(doc["fields"], c5)[pid0]
        filled = " ".join(x["text"] for x in P5["fills"])
        expect("부착물 없음" not in filled and any("블록 안 취부 2명" in b for _, b in P5["extra"]),
               "C5 「추가로 적은 내용이 맞음」: 앞의 '없음'은 반영본에서 빠지고, 블록 안 다른 작업은 별지로")

# answers that must not be written: 「모름」, a value that only says it is unknown, a blank's 「해당 없음」
d = next(x for x in PERMITS if x["permit_no"].endswith("6733"))
doc = extract.build(DIR / permit_name(d), d["kind"])
qs = {q["qid"]: q for q in augment.summary(doc["fields"], [])["questions"]}
bad_ans = []
for qid, q in qs.items():
    ids = [c["id"] for c in q["choices"]]
    if "unknown" in ids:
        bad_ans.append({"qid": qid, "choice": "unknown", "value": "", "q": q})
R = reflect.plan(doc["fields"], bad_ans)
P = next(iter(R.values()))
expect(not P["fills"], "모두 「모름」이면 반영본에 적는 칸 없음")
expect(len(P["pending"]) >= len(bad_ans), "「모름」은 모두 안전팀 확인으로")
loc = next((q for q in qs.values() if q["item"] == "L1"), None)
if loc:
    R = reflect.plan(doc["fields"], [{"qid": loc["qid"], "choice": "place", "value": "모름", "q": loc}])
    expect(not next(iter(R.values()))["fills"], "값이 '모름'뿐이면 칸에 쓰지 않음")
# a blank's value that only says it is not decided ('미정') is not written, and not counted as a screen edit
f3 = copy.deepcopy(doc["fields"])
kj = next(k for k, f in f3.items() if f["key"] == "job")
f3[kj]["value"] = f3[kj]["original"] = ""
q3 = {q["qid"]: q for q in augment.summary(f3, [])["questions"]}
bj = next((k for k in q3 if k.startswith("B1.job:")), None)
expect(bj is not None, "빈 작업내용 → B1 질문")
if bj:
    P = next(iter(reflect.plan(f3, [{"qid": bj, "choice": "value", "value": "미정", "q": q3[bj]}]).values()))
    expect(not any(x["base"] == "job" for x in P["fills"]) and any("미정" in b for _, b in P["pending"]), "B1 '미정' → 칸에 쓰지 않고 확인 필요")
    P = next(iter(reflect.plan(f3, [{"qid": bj, "choice": "value", "value": "E42P 블록 론지 보수", "q": q3[bj]}]).values()))
    x = next((x for x in P["fills"] if x["base"] == "job"), None)
    expect(x and x["src"] == ["빈칸 답변"], "B1 값 → 작업내용 칸, 출처 '빈칸 답변'(화면 수정 아님)")
# a place given when croScan asked back about a free answer (U1.F1 place) goes to 작업장소(상세)
pid1 = next(iter(reflect.plan(doc["fields"], []).keys()))
P = next(iter(reflect.plan(doc["fields"], [{"qid": f"U1.F1:{pid1}", "choice": "place", "value": "3BAY 08-10 칼럼", "q": {"permit_no": pid1}}]).values()))
expect(any(x["base"] in ("location", "location_detail") and "3BAY 08-10" in x["text"] for x in P["fills"]),
       "U1.F1 장소 → 작업장소(팀 이름이면 교체)·작업장소(상세)")
# a screen edit in a protected field is listed, not written
f2 = copy.deepcopy(doc["fields"])
k = next(k for k, f in f2.items() if f["key"] == "app_sign")
f2[k]["value"] = "홍길동"
P = next(iter(reflect.plan(f2, []).values()))
expect(not any(x["base"] == "app_sign" for x in P["fills"]) and any("서명" in a or "승인" in a for a, _ in P["pending"]),
       "승인 서명 칸을 화면에서 고쳐도 반영본에 쓰지 않고 확인 목록에")
print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
