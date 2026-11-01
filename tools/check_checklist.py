"""Check the 위험 체크리스트 (작업반장 시점): the spec, the draft on the 작업반장 test permits, the PDF and the 제출.

    python tools/check_checklist.py

1. The spec (server/checklist_spec.json) only uses things that exist: head keys of that kind's form, day-of keys
   for permit_key, permit text fields, question items the multi-turn asks, effective() values; ids are unique and
   preselected controls are controls of the item.
   The checklist comes from the permit alone (its values and the answers about it), never from the 작업계획서.
2. Every test permit gets a draft: only 해당 / 해당 없음 / 확인 필요; 해당 and 해당 없음 always carry a reason
   (croScan says why); nothing is 해당 없음 without a rule (default is 확인 필요).
3. Each single-signal rule really moves its item: a ticked head box, an answer, a height.
4. The PDF opens and says what was chosen; the day-of block of the permit is never written by croScan.
5. The 제출 is a demo: nothing is stored; the three PDFs are made when asked for.
"""
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_ck_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import addendum, augment, checklist, extract  # noqa: E402
from server import form_spec  # noqa: E402
from server.permit_kinds import KINDS  # noqa: E402
from foreman_permits import FOREMAN  # noqa: E402

ok = bad = 0


def expect(cond, what):
    global ok, bad
    ok += bool(cond); bad += not cond
    if not cond or os.environ.get("VERBOSE"):
        print(("  PASS " if cond else "  FAIL ") + what)


SPEC = checklist.SPEC
DAY_COMMON = {k for k, _, g in form_spec.CHECKS if g == "현장 안전조치"} if hasattr(form_spec, "CHECKS") else set()
TEXT_OK = set(checklist.TEXT_FIELDS) | {"hull_no", "extra_measures", "test_pressure", "concurrent"}   # 'notes' has no field yet: harmless, empty
# fields of the confined form read only to keep 연결 계통 from 「해당 없음」 (Codex review 2026-11-01 #1): reading a
# value the permit has is not writing the day-of check
READ_HEADS = {"confined": {"pressure_use", "commissioning"}}
ITEMS_OK = set(addendum.ITEM) | {"FREE", "C5", "X1", "X2", "X3", "X4", "X5", "X6"}
EFF_OK = {"height", "concurrent", "layer", "place.layer", "kind", "workers", "said"}


def rules(r):
    yield r
    for k in ("any", "all"):
        for x in r.get(k, []):
            yield from rules(x)
    if "not" in r:
        yield from rules(r["not"])


print("1. 명세(checklist_spec.json)가 실제 칸·질문만 쓰는지")
ids = set()
for kind in KINDS:
    expect(kind in SPEC["kinds"], f"{kind}: 항목 있음")
    heads = {k for k, _ in KINDS[kind]["heads"]}
    day = {k for k, _ in KINDS[kind]["col1"] + KINDS[kind]["col2"]} | {KINDS[kind]["a"][0], KINDS[kind]["c"][0], KINDS[kind]["d"][0]}
    for it in checklist.items_for(kind):
        key = f"{kind}:{it['id']}"
        expect(it["id"] not in ids or it in SPEC["common"], f"{key} id 하나뿐")
        ids.add(it["id"])
        cids = [c["id"] for c in it["controls"]]
        expect(len(cids) == len(set(cids)) and 1 <= len(cids) <= 6, f"{key} 조치 {len(cids)}개, id 겹치지 않음")
        expect(set(it.get("preselect", [])) <= set(cids), f"{key} 미리 고른 조치가 그 항목의 조치")
        for c in it["controls"]:
            pk = checklist._key(c, kind)
            expect(not pk or pk in day or pk in DAY_COMMON, f"{key}.{c['id']} 당일 칸 {pk}")
            expect(not re.search(r"완료|실시함|확인함|했음", c["text"]), f"{key}.{c['id']} 조치는 계획 문장: {c['text']}")
        for side in ("yes", "no"):
            for top in it.get("prefill", {}).get(side, []):
                for r in rules(top):
                    if "head" in r:
                        expect(r["head"] in heads | READ_HEADS.get(kind, set()) or it in SPEC["common"], f"{key} head {r['head']} (이 종류의 칸)")
                    for tk in ("text", "denied"):
                        if tk in r:
                            expect(set(r.get("fields") or []) <= TEXT_OK, f"{key} {tk} 칸 {r.get('fields')}")
                            try:
                                re.compile(r[tk])
                            except re.error as e:
                                expect(False, f"{key} 정규식 {r[tk]}: {e}")
                    if "answer" in r:
                        expect(r["answer"].split(".")[0] in ITEMS_OK, f"{key} answer {r['answer']}")
                    if "eff" in r:
                        expect(r["eff"] in EFF_OK or r["eff"].startswith(("notes.", "facts.")), f"{key} eff {r['eff']}")
                    expect("plans" not in r, f"{key} 작업계획서 규칙 없음 (허가서만으로 만듦)")
                if side == "no":
                    expect(top.get("reason"), f"{key} 해당 없음 규칙에 이유가 있음")
                    # 해당 없음 needs the permit's own words and a confirmed answer of this permit, together (Codex #2)
                    leaves = list(rules(top))
                    expect("all" in top and any("answer" in x for x in leaves)
                           and any("denied" in x or "concurrent" in (x.get("fields") or []) for x in leaves),
                           f"{key} 해당 없음은 허가서 부재 표기와 같은 허가서의 답이 함께(all)")

print("2. 반장 시험 허가서 10건의 초안")
DOCS = []
for d in FOREMAN:
    name = f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf"
    doc = extract.build(ROOT / "samples/반장_테스트" / name, d["kind"])
    DOCS.append((name, d["kind"], doc))
    ck = checklist.draft(doc["fields"], [])
    expect(len(ck["permits"]) == 1 and ck["permits"][0]["kind"] == d["kind"], f"{name}: 허가서 1건, 종류 {d['kind']}")
    items = ck["permits"][0]["items"]
    n = {s: sum(it["state"] == s for it in items) for s in checklist.STATES}
    print(f"  {name}: 해당 {n['yes']} · 확인 필요 {n['check']} · 해당 없음 {n['no']} / {len(items)}")
    for it in items:
        expect(it["state"] in checklist.STATES, f"{name} {it['id']} 상태")
        expect(it["state"] == "check" or it["reasons"], f"{name} {it['id']} {it['state']}에 근거 있음")
        expect(all(c["on"] == (it["state"] == "yes" and c["pre"]) for c in it["controls"]), f"{name} {it['id']} 미리 고른 조치는 해당일 때만")
    # the day-of block of the permit is untouched by the draft
    before = json.dumps(doc["fields"], sort_keys=True, ensure_ascii=False)
    checklist.draft(doc["fields"], [])
    expect(json.dumps(doc["fields"], sort_keys=True, ensure_ascii=False) == before, f"{name}: 허가서 값은 그대로")

print("3. 규칙 하나가 실제로 항목을 움직이는지 (칸 체크·답·높이)")
by_kind = {k: doc for _, k, doc in DOCS}
moved = tried = 0
for kind, doc in by_kind.items():
    perm = augment._permits(doc["fields"])[0]
    pno, page = perm["permit_no"], perm["no"]
    for it in checklist.items_for(kind):
        for top in it.get("prefill", {}).get("yes", []):
            for r in ([top] + top.get("any", [])):
                if not {"head", "answer", "eff"} & set(r):
                    continue
                f = copy.deepcopy(doc["fields"])
                answers = []
                if "head" in r:
                    hit = [k for k, x in f.items() if x["page"] == page and k.split(".")[-1] == r["head"]]
                    if not hit:
                        continue
                    for k in hit:
                        f[k]["value"] = True
                elif "answer" in r:
                    ch = r.get("choice")
                    ch = ch[0] if isinstance(ch, list) else ch
                    val = {"\\d": "6", "m": "4.8m"}.get(r.get("value", ""), "")
                    if r.get("value") and not val:
                        alt = re.sub(r"\(\?[!=<][^)]*\)", "", r["value"].split("|")[0])      # drop look-arounds
                        alt = re.sub(r"\\s[*+?]?", " ", alt)
                        alt = re.sub(r"\\d[*+?]?", "6", alt)
                        val = re.sub(r"[\\^$()|?*+\[\]{}]", "", alt) or "있음"
                    answers = [{"qid": f"{r['answer']}:{pno}", "choice": ch or "other", "value": val, "q": {}}]
                elif r["eff"] == "height" and r.get("op") in (">=", ">"):
                    hit = [k for k, x in f.items() if x["page"] == page and k.split(".")[-1] == "work_height"]
                    if not hit:
                        continue
                    f[hit[0]]["value"] = str(float(r["value"]) + 1)
                else:
                    continue
                tried += 1
                got = {x["id"]: x for x in checklist.draft(f, answers)["permits"][0]["items"]}[it["id"]]
                # a permit value that says the opposite (병행 N and an answer 있음) makes it 확인 필요, with both reasons
                good = got["state"] == "yes" or (got["state"] == "check" and got["reasons"] and got["reasons"][0].startswith("근거가 엇갈림"))
                moved += bool(good)
                expect(good, f"{kind} {it['id']}: {json.dumps({k: v for k, v in r.items() if k != 'reason'}, ensure_ascii=False)} → 해당 ({got['state']})")
print(f"  규칙 {tried}개 중 {moved}개가 항목을 해당으로 바꿈")

print("3-2. 불확실한 말은 '해당 없음'을 만들지 않음")
_, _, cdoc = next(x for x in DOCS if x[1] == "confined")
cp = augment._permits(cdoc["fields"])[0]
f = copy.deepcopy(cdoc["fields"])
hz = [k for k, x in f.items() if x["page"] == cp["no"] and k.split(".")[-1] == "hazards"]
for kk in [k for k, x in f.items() if x["page"] == cp["no"] and k.split(".")[-1] in ("argon", "pressure_use", "commissioning", "test_pressure")]:
    f[kk]["value"] = False if not kk.endswith("test_pressure") else ""      # 아르곤·압력·수전 칸 미체크: the answer and the text decide
for kk in hz:
    f[kk]["value"] = "질식. 아마 공급 배관이 연결되어 있음"
ans = [{"qid": f"CF2:{cp['permit_no']}", "choice": "none", "value": "", "q": {}}]
got = {x["id"]: x for x in checklist.draft(f, ans)["permits"][0]["items"]}
expect(got["confined_inflow"]["state"] != "no", f"CF2 '연결 계통 없음' + 허가서 '아마 연결' → {got['confined_inflow']['state']} (해당 없음 아님)")
for kk in hz:
    f[kk]["value"] = "질식"
got = {x["id"]: x for x in checklist.draft(f, ans)["permits"][0]["items"]}
# Codex review #2: the answer alone over a silent permit is 확인 필요 (the old expectation was 해당 없음)
expect(got["confined_inflow"]["state"] == "check", f"CF2 '연결 계통 없음'만, 허가서는 말 없음 → {got['confined_inflow']['state']} (확인 필요)")
for kk in hz:
    f[kk]["value"] = "질식, 연결 계통 없음"
got = {x["id"]: x for x in checklist.draft(f, ans)["permits"][0]["items"]}
expect(got["confined_inflow"]["state"] == "no", f"CF2 '연결 계통 없음' + 허가서 「연결 계통 없음」 → {got['confined_inflow']['state']}")
f2 = copy.deepcopy(cdoc["fields"])
for kk in hz:
    f2[kk]["value"] = "아르곤 가스 안 씀"
P2 = augment.effective(f2, [])[0]
c2 = checklist._Ctx(P2, [])
for t, want in (("아르곤 가스 안 씀", False), ("아르곤 사용", True), ("아마 아르곤 쓸 듯", None), ("아르곤 쓰면", None), ("질식", False)):
    for kk in hz:
        f2[kk]["value"] = t
    c2 = checklist._Ctx(augment.effective(f2, [])[0], [])
    got = checklist._match({"text": "아르곤", "fields": ["hazards"]}, c2)[0]
    expect(got is want, f"'{t}' → {got} (기대 {want})")
    expect(checklist._match({"not": {"text": "아르곤", "fields": ["hazards"]}}, c2)[0] is (None if want is None else not want), f"not '{t}'")

print("3-3. 허가서만으로 만듦: 작업계획서를 보내도 결과가 같고, 명세에 계획서 규칙이 없음")
expect('"plans"' not in json.dumps(SPEC), "명세에 작업계획서 규칙 없음")
for name, kind, doc in DOCS:
    P0 = augment.effective(doc["fields"], [])[0]
    base = {x["id"]: x["state"] for x in checklist.draft(doc["fields"], [])["permits"][0]["items"]}
    expect(base["common_mixed"] in ("yes", "no", "check"), f"{name}: 병행 {base['common_mixed']} (허가서 병행여부 '{P0['concurrent']}')")
    if P0["concurrent"] == "N":
        # Codex review #2: 병행 N alone (no confirming answer) is 확인 필요, never 해당 (the old expectation was 해당 없음)
        expect(base["common_mixed"] == "check", f"{name}: 허가서 병행 N만 → 확인 필요 (계획서와 무관, 답 없이 해당 없음 아님)")

print("4. PDF")
import pymupdf  # noqa: E402
for name, kind, doc in DOCS[:5]:
    ck = checklist.draft(doc["fields"], [])
    for it in ck["permits"][0]["items"]:
        it["touched"] = True
    ck["permits"][0]["items"][0]["memo"] = "하부 통행로는 2B 쪽으로 돌림"
    ck["permits"][0]["items"].append({"id": "Uabc", "title": "인접 BAY 도장 유기용제", "state": "yes", "controls": [{"id": "u1", "text": "작업 전 환기 확인", "on": True}], "touched": True})
    raw = checklist.pdf(ck, doc["fields"])
    expect(len(raw) < 600_000, f"{name}: PDF 크기 {len(raw) // 1024}KB (글꼴은 쓴 글자만)")
    pdf = pymupdf.open(stream=raw, filetype="pdf")
    text = re.sub(r"\s+", " ", "".join(p.get_text() for p in pdf))      # nbsp and line breaks inside cells
    expect(pdf.page_count >= 1 and "위험 체크리스트" in text, f"{name}: PDF {pdf.page_count}쪽")
    expect("하부 통행로는 2B" in text and "인접 BAY 도장" in text, f"{name}: 메모·직접 추가 항목이 PDF에 있음")
    expect(not re.search(r"(실시|완료)함", text), f"{name}: PDF에 '실시함/완료함' 없음")
    ck["permits"][0]["items"][1]["touched"] = False
    t2 = re.sub(r"\s+", " ", "".join(p.get_text() for p in pymupdf.open(stream=checklist.pdf(ck, doc["fields"]), filetype="pdf")))
    expect("반장 확인 전" in t2 and "확인 전 1개" in t2, f"{name}: 확인 안 한 항목은 PDF에 「반장 확인 전」")

print("5. 제출은 시연용: 서버에 저장하지 않고, 서류 PDF는 그때그때 만듦")
try:
    from fastapi.testclient import TestClient
    from server import qa
    from server.app import app
    cli = TestClient(app)
    name, kind, doc = DOCS[0]
    src = ROOT / "samples/반장_테스트" / name
    ck = checklist.draft(doc["fields"], [])
    before = sorted(p.name for p in qa.DATA.iterdir()) if qa.DATA.exists() else []
    expect(cli.post("/api/package", data={"payload": "{}"}).status_code in (404, 405), "제출 저장 API(/api/package) 없음")
    expect(cli.get("/api/submissions/CS-20260101-AAAAAAAAAA").status_code == 404, "제출 조회 API 없음")
    r = cli.post("/api/submit", files={"file": (name, src.read_bytes(), "application/pdf")},
                 data={"payload": json.dumps({"fields": doc["fields"], "answers": []})})
    expect(r.status_code == 200 and r.content[:4] == b"%PDF", f"허가서(원본+추가검토서) PDF ({r.status_code})")
    r2 = cli.post("/api/checklist/pdf", json={"fields": doc["fields"], "checklist": ck})
    expect(r2.status_code == 200 and r2.content[:4] == b"%PDF", f"위험 체크리스트 PDF ({r2.status_code})")
    after = sorted(p.name for p in qa.DATA.iterdir()) if qa.DATA.exists() else []
    expect("submissions" not in after and before == after, f"서버 데이터 폴더에 아무것도 쌓이지 않음 ({after})")
    pno0 = ck["permits"][0]["permit_no"]
    big = {"permits": [{"permit_no": pno0, "kind": kind, "items": [{"id": f"U{i}", "title": "x" * 500, "state": "yes"} for i in range(5000)]}] * 50}
    r5 = cli.post("/api/checklist/pdf", json={"fields": doc["fields"], "checklist": big})
    expect(r5.status_code == 400, f"한도를 넘는 체크리스트는 잘라 내지 않고 거절 ({r5.status_code})")
    r6 = cli.post("/api/checklist/pdf", json={"fields": doc["fields"], "checklist": {"permits": [{"permit_no": "AC00-XX-0000", "kind": kind, "items": []}]}})
    expect(r6.status_code == 400, f"이 파일에 없는 허가서 → 400 ({r6.status_code})")
    bad_r = cli.post("/api/submit", files={"file": (name, b"not a pdf", "application/pdf")}, data={"payload": json.dumps({"fields": doc["fields"]})})
    expect(bad_r.status_code == 400, f"PDF 아님 → 400 ({bad_r.status_code})")
    r3 = cli.post("/api/checklist", json={"fields": doc["fields"], "answers": []})
    r3p = cli.post("/api/checklist", json={"fields": doc["fields"], "answers": [], "plans": [{"title": "도장", "start": "2026-10-27 08:00", "end": "2026-10-27 17:00", "location": "대조립21공장 3BAY"}]})
    expect(r3.status_code == 200 and r3.json()["permits"], "체크리스트 초안 API")
    expect(r3p.status_code == 200 and r3p.json() == r3.json(), "작업계획서를 같이 보내도 초안이 같음 (허가서만 봄)")
    expect(cli.post("/api/checklist", json={"fields": {"x": 1}}).status_code in (400, 422), "엉뚱한 fields → 400")
except ImportError as e:
    print(f"  (건너뜀: {e})")

print(f"\n통과 {ok} / {ok + bad}" + ("" if not bad else f"  실패 {bad}"))
sys.exit(1 if bad else 0)
