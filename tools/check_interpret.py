"""QA #39 check: one long typed answer that also answers other open questions (place, time, workers, a watcher).

  python tools/check_interpret.py          (on the server: needs the ODL reader, like make_demo_day)

The permit 0731 (hot work) with 작업일시·작업장소·작업인원 emptied, as in the QA report, answered once with the reporter's
sentence. What must hold: the place, the time and the workers are taken for their questions with the clause they came
from; '12–14' after a BAY is never a time; the watcher goes to the 별지 and is not added to 작업인원; a condition, a hedge
or another team's work is not taken; the source answer's own value is its part only; the questions answered are not
asked again; and the 반영본 writes what was read.
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_ip_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import augment, app as webapp, extract, store  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402

ok = bad = 0


def expect(c, what):
    global ok, bad
    ok, bad = ok + bool(c), bad + (not c)
    print(("  ok   " if c else "  FAIL ") + what)


def blank(fields, keys):
    f = copy.deepcopy(fields)
    for x in f.values():
        if x["key"] in keys:
            x["value"] = x["original"] = ""
    return f


def run(fields, answers, confirm=True, sid=None):
    """the review as the client does it (design §2): what a long answer also says comes as proposals; confirmed here
    (all of them, as 「N건 확인」) unless confirm is False. s["derived"] is what was proposed."""
    sid = sid or store.create()
    s = webapp._augment(fields, answers, sid, store.revision(sid))
    props = s["proposals"]
    if confirm and props:
        store.decide(sid, f"t{len(props)}", adopt=[p["pid"] for p in props])
        s = webapp._augment(fields, answers, sid, store.revision(sid))
    s["derived"], s["sid"] = props, sid
    return s


d = next(x for x in load("permits.json")["permits"] if x["permit_no"].endswith("0731"))
doc = extract.build(DIR / "허가서" / permit_name(d), d["kind"])
EMPTY = {f"{a}_{i}" for i in range(1, 8) for a in ("date", "from", "to")} | {"location", "location_detail", "workers"}
F = blank(doc["fields"], EMPTY)
s0 = run(F, [])
qs = {q["item"]: q for q in s0["questions"]}
print("질문:", ", ".join(qs))
expect({"T0.1", "L1", "B1.workers"} <= set(qs), "빈 작업일시·작업장소·작업인원 → T0.1·L1·B1.workers 질문")
SAY = "장소는 3BAY 12–14입니다. 실제 작업은 기존 9시가 아니라 13시부터 15시까지이고, 종일 작업은 아닙니다. 작업자 4명과 감시인 1명이 들어갑니다."
t0 = qs["T0.1"]
src = {"qid": t0["qid"], "choice": "value", "value": SAY, "q": t0, "spill": True}
pre = run(F, [src], confirm=False)
Pp = next(iter(pre["reflect"].values()))
expect(not any(x["base"] in ("location", "workers") for x in Pp["fills"]) and {"L1", "B1.workers"} <= {q["item"] for q in pre["questions"]},
       "확인 전에는 읽은 장소·인원이 반영되지 않고 질문도 남음 (design §2·§4.2)")
s1 = run(F, [src])
got = {x["qid"].split(":")[0]: x for x in s1["derived"]}
for k, x in got.items():
    print(f"  읽음 {k} {x['choice']} '{x['value']}' ← 「{x['quote']}」")
print("  원래 질문의 값:", s1["read"])
expect(not s1["errors"], "예문은 오류 없이 받음")
expect(got.get("L1", {}).get("value") == "3BAY 12-14 칼럼", "장소 → L1 '3BAY 12-14 칼럼'")
expect("3BAY" in got.get("L1", {}).get("quote", ""), "장소의 근거 문장")
expect(got.get("B1.workers", {}).get("value") == "4", "작업자 4명 → 작업인원 4 (감시인은 더하지 않음)")
expect(got.get("W1", {}).get("value") == "감시인 1명", "감시인 1명 → 별지 기록")
expect(s1["read"].get(t0["qid"], "").endswith("13:00~15:00"), "T0 자기 값은 13:00~15:00 (12–14는 시간이 아님)")
left = {q["item"] for q in s1["questions"]}
expect(not ({"T0.1", "L1", "B1.workers"} & left), "답이 된 질문은 다시 묻지 않음")
P = next(iter(s1["reflect"].values()))
fills = {x["base"]: x for x in P["fills"]}
for x in P["fills"]:
    print(f"  반영 {x['mark'] if 'mark' in x else ''}{x['name']}: '{x['text']}' ({', '.join(x['src'])})")
expect(fills.get("location", {}).get("text") == "3BAY 12-14 칼럼", "반영본 작업장소 = 3BAY 12-14 칼럼")
expect(fills.get("workers", {}).get("text") == "4", "반영본 작업인원 = 4")
expect(not any(x["base"].startswith(("date_", "from_", "to_")) for x in P["fills"]) and any("날짜" in b for _, b in P["pending"]),
       "날짜 없는 시간 → 작업일시 행은 비우고 날짜 확인 필요 (행은 통째로만 채움)")
expect(not any("12:00" in x["text"] or "14:00" in x["text"] for x in P["fills"]), "12–14가 시간으로 들어가지 않음")
expect(any("감시인 1명" in b for _, b in P["extra"]), "감시인은 별지에")
expect(any("「" in s for x in P["fills"] for s in x["src"]), "반영본 출처에 근거 문장")
sd = run(F, [{"qid": t0["qid"], "choice": "value", "value": SAY.replace("실제 작업은", "10/29 실제 작업은"), "q": t0, "spill": True}])
fd = {x["base"]: x["text"] for x in next(iter(sd["reflect"].values()))["fills"]}
expect((fd.get("date_1"), fd.get("from_1"), fd.get("to_1")) == ("2026-10-29", "13:00", "15:00"), f"날짜도 말하면 작업일시 1행 = 2026-10-29 13:00~15:00 ({fd.get('date_1')} {fd.get('from_1')} {fd.get('to_1')})")
# the session keeps what was confirmed: the same answers again (spill off, derived ones sent too) give the same result
keep = [dict(src, spill=False, read=s1["read"].get(src["qid"], ""))] + [dict(d, ai=True) for d in s1["derived"]]
s2 = run(F, keep, sid=s1["sid"])
expect({q["qid"] for q in s2["questions"]} == {q["qid"] for q in s1["questions"]} and s2["reflect"] == s1["reflect"], "같은 세션에서 다시 계산해도 같음(보낸 파생 답은 받지 않음)")
# what must not be taken
for say, item, why in [
        ("다른 팀이 3BAY 12-14 칼럼에서 도장 작업을 합니다. 우리 작업은 13시부터 15시까지입니다", "L1", "다른 팀 장소는 내 장소가 아님"),
        ("아마 3BAY 12-14 칼럼일 거예요, 13시부터 15시까지", "L1", "추측은 받지 않음"),
        ("비가 오면 3BAY 12-14 칼럼에서 합니다, 13시부터 15시까지", "L1", "조건은 받지 않음"),
        ("13시부터 15시까지, 그리고 16시부터 17시까지 합니다", "T1", "시간대가 둘이면 나누지 않음")]:
    s = run(F, [{"qid": t0["qid"], "choice": "value", "value": say, "q": t0, "spill": True}])
    expect(item not in {x["qid"].split(":")[0] for x in s["derived"]}, f"{why}: '{say[:24]}…'")
# Codex review: denials, a condition over its commas, another team's answer, a long answer to 작업인원 itself
L1q = qs["L1"]
def got_of(item_q, choice, say):
    s = run(F, [{"qid": item_q["qid"], "choice": choice, "value": say, "q": item_q, "spill": True}])
    return s, {x["qid"].split(":")[0]: x["value"] for x in s["derived"]}
_, g = got_of(L1q, "place", "3BAY 12-14 칼럼입니다. 작업자 4명이 아니라 6명입니다")
expect(g.get("B1.workers") == "6", f"'4명이 아니라 6명' → 6 ({g.get('B1.workers')})")
_, g = got_of(L1q, "place", "3BAY 12-14 칼럼입니다. 작업자는 4명이 아닙니다")
expect("B1.workers" not in g, "'4명이 아닙니다' → 작업인원 넣지 않음")
_, g = got_of(L1q, "place", "3BAY 12-14 칼럼, 13시부터 15시까지는 작업하지 않습니다")
expect("T0.1" not in g, "'13~15시는 작업하지 않습니다' → 작업시간으로 넣지 않음")
_, g = got_of(L1q, "place", "3BAY 12-14 칼럼입니다. 비가 오면, 작업자 4명과 감시인 1명이 들어갑니다")
expect(not ({"B1.workers", "W1"} & set(g)), "'비가 오면, …' 쉼표 뒤도 조건 → 넣지 않음")
b3 = next((q for q in s0["questions"] if q["item"] == "B3"), None)
if b3:
    _, g = got_of(b3, "yes", "3BAY 12-14 칼럼에서 용접합니다. 작업자 8명입니다")
    expect(not g, "병행작업(B3) 답의 장소·인원은 내 칸에 넣지 않음")
s, g = got_of(qs["B1.workers"], "value", "작업자 4명입니다. 장소는 3BAY 12-14 칼럼입니다")
P = next(iter(s["reflect"].values()))
expect(not s["errors"] and g.get("L1") == "3BAY 12-14 칼럼" and any(x["base"] == "workers" and x["text"] == "4" for x in P["fills"]),
       f"작업인원 질문에 긴 답 → 인원 4, 장소도 함께 (오류 {s['errors']})")
# a filled permit: the actual time (T1) and a narrower place; nothing written over the 신청 작업일시
F2 = doc["fields"]
q2 = {q["item"]: q for q in run(F2, [])["questions"]}
print("원본 질문:", ", ".join(q2))
first = next(iter(q2.values()))
if "T1" in q2:
    s = run(F2, [{"qid": q2["T1"]["qid"], "choice": "partial", "value": SAY, "q": q2["T1"], "spill": True}])
    P = next(iter(s["reflect"].values()))
    expect(not any(x["base"].startswith(("from_", "to_", "date_")) for x in P["fills"]), "T1 긴 답: 신청 작업일시는 그대로")
    expect(any("실제 작업 예정 13:00~15:00" in x["text"] for x in P["fills"]), "T1 긴 답: 상세에 '실제 작업 예정 13:00~15:00'만")
# Codex review (2026-10-31): nothing reaches the calculation without a confirmation — a free answer, a forged
# 'read', another answer's 「다른 작업 없음」
FREE_SAY = "작업장소는 3BAY 12-14 칼럼입니다. 실제 작업은 13시부터 15시까지 합니다. 같은 시간 같은 장소 다른 작업 없음."
fs = run(F, [{"qid": "FREE:1", "choice": "text", "value": FREE_SAY}], confirm=False)
Pf = next(iter(fs["reflect"].values()))
expect(not any(x["base"] in ("location", "concurrent") for x in Pf["fills"]) and {"L1", "B3"} <= {q["item"] for q in fs["questions"]},
       "추가 전달(자유 입력)은 확인 전에 장소·병행여부로 쓰이지 않고 질문도 남음")
expect(any(d["qid"].startswith("L1:") for d in fs["derived"]), "추가 전달에서 읽은 장소는 제안으로 나옴")
fc = run(F, [{"qid": "FREE:1", "choice": "text", "value": FREE_SAY}])
expect(any(x["base"] == "location" for x in next(iter(fc["reflect"].values()))["fills"]), "제안을 확인하면 그때 반영")
wq = qs["B1.workers"]
forged = run(F, [{"qid": wq["qid"], "choice": "value", "value": "4", "read": "99", "q": wq}], confirm=False)
expect(any(x["base"] == "workers" and x["text"] == "4" for x in next(iter(forged["reflect"].values()))["fills"]), "클라이언트가 보낸 read(99)는 쓰지 않음 → 인원 4")
nb = run(F, [{"qid": qs["L1"]["qid"], "choice": "place", "value": "3BAY 12-14 칼럼, 같은 시간 같은 장소 다른 작업 없음", "q": qs["L1"], "spill": True}], confirm=False)
expect("B3" in {q["item"] for q in nb["questions"]}, "다른 답의 「다른 작업 없음」으로 병행여부 질문을 건너뛰지 않음")
# server long eval 2026-10-31: a time and a spoken ending said in the place clause stay out of the 작업장소 value
for said, want in [("오후 1시부터 3시까지 3BAY 12~14칼럼 블록 위", "3BAY 12~14칼럼 블록 위"), ("위치는 3BAY 12-14 칼럼 블록 상부요", "3BAY 12-14 칼럼 블록 상부"),
                   ("오후 01:00~03:00 3BAY 12~14칼럼 블록 위", "3BAY 12~14칼럼 블록 위"), ("말씀드리면 3BAY 12-14", "3BAY 12-14 칼럼"),
                   ("대조립21공장 2BAY 05-06 칼럼 B22S 블록 내부", "대조립21공장 2BAY 05-06 칼럼 B22S 블록 내부"),
                   ("3BAY 14~16칼럼 블록 내부에서 용접해", "3BAY 14~16칼럼 블록 내부")]:
    expect(augment._place_value(said) == want, f"장소 값에 시간·말끝을 넣지 않음: {said} → {augment._place_value(said)}")
print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
