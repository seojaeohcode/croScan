"""The 작업반장 questions the research book and the other material add (2026-10-31 material reinforcement, multi-turn).

    python tools/check_questions_material.py

Each new or changed question: it is asked when its rule holds (trigger), it is not asked when the permit already says
it or the rule does not hold (no trigger), and it keeps the order (rule questions first, the 12-ask budget). Then the
time windows kept apart for the matching (windows_req / windows_stage / full_end), the reference models' conditions
(a single word decides nothing), the 「없음」 typed in words (Codex trace §B), and the block IDs of the real form.
Sources: research412.txt (pages in each line), interview, 위험작업신고서 실물, 신고서양식.
"""
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_mat_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import augment, extract, need_catalog as N, reflect  # noqa: E402
from foreman_permits import FOREMAN  # noqa: E402
from server.permit_kinds import KINDS  # noqa: E402

ok = bad = 0


def expect(cond, what):
    global ok, bad
    ok += bool(cond)
    bad += not cond
    print(("  PASS " if cond else "  FAIL ") + what)


DOCS = {}
for d in FOREMAN:
    no = d["permit_no"][-4:]
    DOCS[no] = extract.build(ROOT / "samples/반장_테스트" / f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{no}.pdf", d["kind"])


def F(no, **kv):
    """the test permit no with some field values changed (a value written on the form: original too)"""
    f = copy.deepcopy(DOCS[no]["fields"])
    for k, v in kv.items():
        f[f"p1.{k}"]["value"] = v
        if not isinstance(v, bool):
            f[f"p1.{k}"]["original"] = v
    return f


def S(f, ans=()):
    return augment.summary(f, list(ans))


def Q(s, item):
    return next((q for q in s["questions"] if q["item"] == item), None)


def A(q, choice, value=""):
    return {"qid": q["qid"], "choice": choice, "value": value, "q": q}


def OLD(a):
    """an answer without the form mark (given before 2026-11-01): it stands when the form is not the one asked on"""
    return {**a, "q": {k: v for k, v in a["q"].items() if k != "fp"}}


def neutral(q):
    return q and not any(w in q["text"] for w in ("오류", "잘못", "위반", "금지"))



def win(s, d):
    return s["effective"][0]["windows"].get(d)


print("T7 (Codex #12): 확인된 현장 근무시간이 없으면 묻지 않음 (N4-MT15 p315 「08~18 가정만으로 질문 금지」)")
expect(augment.SITE_SHIFT is None and not Q(S(F("4403", from_1="20:00", to_1="23:00")), "T7"), "확인된 근무시간 없음 → 「주간」 체크 + 20~23시도 T7 없음")
expect(augment.night_part(360, 600, (480, 1080)) and not augment.night_part(360, 600, None), "night_part: 06:00~10:00은 확인된 08~18 근무 밖에 걸침")
augment.SITE_SHIFT = (8 * 60, 18 * 60)                       # a site that confirmed its day shift (CROSCAN_SITE_SHIFT)
try:
    f = F("4012", from_2="20:00", to_2="23:00")
    t7 = Q(S(f), "T7")
    expect(t7 and "p1.from_2" in t7["keys"] and "2026-10-28" in t7["text"] and neutral(t7), f"확인된 근무시간 + 2일차 20~23시 → T7 (그 날·그 행): {t7 and t7['keys']}")
    s = S(f, [A(t7, "check", "13:00~15:00")])
    w = s["effective"][0]["windows"]
    expect(w["2026-10-28"] == ["13:00~15:00"] and w["2026-10-27"] == ["08:00~16:59"] and w["2026-10-29"] == ["08:00~16:59"],
           f"(Codex #1) T7 「체크가 맞음」 13~15시 → 2일차만 고침, 다른 날은 그대로 ({w})")
    expect(not Q(S(F("4403", from_1="09:00", to_1="11:00")), "T7"), "근무시간 안 → T7 없음")
finally:
    augment.SITE_SHIFT = None

print("T7 법정 야간(근로기준법 제56조 제3항 22:00~06:00)으로 명백한 경우만 — 확인된 근무시간이 없을 때")
NIGHT = dict(day=False, night=True)
t7 = Q(S(F("4403", from_1="01:00", to_1="04:00")), "T7")
expect(t7 and neutral(t7) and "근로기준법 제56조" in t7["text"] and "p1.from_1" in t7["keys"], "「주간」 + 01:00~04:00(통째로 법정 야간) → T7")
for a, b, why in (("21:00", "23:00", "22시에 걸침"), ("20:00", "23:00", "저녁 연장")):
    expect(not Q(S(F("4403", from_1=a, to_1=b)), "T7"), f"「주간」 + {a}~{b}({why}) → T7 없음")
f = F("4403", from_1="23:00", to_1="04:00")
t5 = Q(S(f), "T5")
expect(t5 and not Q(S(f), "T7"), "「주간」 + 23:00~04:00: 종료<시작은 T5가 먼저, T7은 기다림")
t7 = Q(S(f, [A(t5, "overnight")]), "T7")
expect(t7 and "익일 04:00" in t7["text"], "T5 「다음 날 끝남」 → 23:00~익일 04:00 통째로 법정 야간 → T7")
expect(not Q(S(f, [A(t5, "fix", "09:00~12:00")]), "T7"), "T5 「잘못 적음」 → 그 행은 T7로 다시 묻지 않음")
t7 = Q(S(F("4403", **NIGHT, from_1="10:00", to_1="15:00")), "T7")
expect(t7 and neutral(t7) and "낮 12시" in t7["text"], "「야간」 + 10:00~15:00(정오를 지나고 법정 야간 0분) → T7")
for a, b, why in (("18:00", "21:00", "현장이 야간이라 부를 수 있는 저녁"), ("20:00", "23:00", "법정 야간에 걸침"), ("13:00", "17:00", "정오를 지나지 않음")):
    expect(not Q(S(F("4403", **NIGHT, from_1=a, to_1=b)), "T7"), f"「야간」 + {a}~{b}({why}) → T7 없음")
expect(not Q(S(F("4012", **NIGHT, from_1="10:00", to_1="15:00", from_2="20:00", to_2="23:00")), "T7"),
       "「야간」: 한 날이라도 야간 시간이면 T7 없음 (모든 날이 낮일 때만)")
expect(not Q(S(F("4403", day=True, night=True, from_1="01:00", to_1="04:00")), "T7"), "주간·야간 둘 다 체크 → T7 없음 (서식 점검이 따로 봄)")
expect(not Q(S(F("5067", from_1="01:00", to_1="04:00")), "T8") and Q(S(F("5067", from_1="01:00", to_1="04:00")), "T7"),
       "비화기도 T7은 묻고, T8(화기 야간 지원)은 묻지 않음")
f = F("4403", from_1="01:00", to_1="04:00")
t7 = Q(S(f), "T7")
expect(not Q(S(f), "T8"), "T7이 열려 있으면 T8은 기다림")
expect(Q(S(f, [A(t7, "time")]), "T8") is not None, "T7 「적힌 시간이 맞음(체크를 고침)」 → 야간 화기: T8")
s = S(f, [A(t7, "check", "09:00~11:00")])
expect(not Q(s, "T8") and win(s, "2026-10-27") == ["09:00~11:00"], f"T7 「주간 체크가 맞음」 09~11시 → 그 날 시간을 고침, T8 없음 ({win(s, '2026-10-27')})")
f = F("4403", **NIGHT, from_1="10:00", to_1="15:00")
expect(not Q(S(f, [A(Q(S(f), "T7"), "time")]), "T8"), "「야간」 + 10~15시에 「적힌 시간이 맞음」 → 주간 작업: T8 없음")
print("T7 Codex 검토(astra) 지적 재현")
from server import review  # noqa: E402
expect(augment._m("24:00") == 1440 and augment._m("24:30") is None, "24:00만 하루 끝으로 읽고 24:30은 시각이 아님")
f = F("4403", from_1="23:00", to_1="00:00")
expect(Q(S(f), "T5") and not Q(S(f), "T7"), "#3 「주간」 23:00~00:00: 종료≤시작이라 T5 먼저 (T7 없음)")
expect(not Q(S(F("4403", from_1="24:00", to_1="00:00")), "T7"), "#3 24:00~00:00(길이 0) → T7 없음")
f = F("4012", **NIGHT, from_1="10:00", to_1="15:00", from_2="23:00", to_2="04:00")
expect(not Q(S(f), "T7"), "#3 「야간」 10~15시 + 미확정 역전 행 → 「모든 행이 낮」으로 보지 않음 (T7 없음)")
expect(not Q(S(f, [A(Q(S(f), "T5.2"), "fix", "22:00~23:00")]), "T7"), "#3 역전 행을 T5로 고쳐도 확인되지 않은 행을 낮으로 치지 않음")
expect(not Q(S(F("4403", **NIGHT, from_1="12:00", to_1="15:00")), "T7"), "#6 「야간」 12:00~15:00: 정오를 「지나는」 행만 (12시 시작은 아님)")
f = F("4012", from_1="10:00", to_1="15:00", from_2="01:00", to_2="04:00", job_detail="화재감시자 1명 배치")
t7 = Q(S(f), "T7")
expect(t7 and "p1.from_2" in t7["keys"], f"2일차 01~04시 → T7은 2일차를 물음 ({t7 and t7['keys']})")
t8 = Q(S(f, [A(t7, "time")]), "T8")
expect(t8 and "01:00~04:00" in t8["text"] and "10:00" not in t8["text"] and "p1.from_2" in t8["keys"],
       f"#4 T7 「적힌 시간이 맞음」 뒤 T8은 그 야간 행(01~04시)을 말함, 낮 행 아님 ({t8 and t8['text'][:40]})")
t8 = Q(S(f, [A(t7, "both")]), "T8")
expect(t8 and "01:00~04:00" in t8["text"], "T7 「둘 다 맞음」 → 그 시간에 실제로 일함: T8")
f = F("4012", from_1="01:00", to_1="04:00", job_detail="화재감시자 1명 배치")
old = A(Q(S(f), "T7"), "time")                       # same permit: row 1 asked, then the form edited
f2 = F("4012", from_2="02:00", to_2="05:00", job_detail="화재감시자 1명 배치")
t7 = Q(S(f2, [old]), "T7")
expect(t7 and "p1.from_2" in t7["keys"] and old["q"]["original"] != t7["original"],
       "#1 서류가 바뀌어 대상 행이 달라지면 예전 T7 답은 쓰지 않고 새 행을 다시 물음")
expect(not Q(S(f2, [old]), "T8") and Q(S(f, [old]), "T8"), "#1 예전 T7 답으로 T8이 열리지 않음 (원래 행에서는 열림)")
expect(not any(r.get("item") == "T7" for r in S(f2, [old]).get("records", [])), "#1 예전 T7 답은 2쪽 기록에도 없음")
f = F("4403", date_1="", from_1="01:00", to_1="04:00")
t0 = next((q for q in S(f)["questions"] if q["item"].startswith("T0")), None)
s = S(f, [A(t0, "value", "10/27 01:00~04:00")]) if t0 else None
expect(t0 and Q(s, "T7") is not None, f"#5 날짜 빈 행을 T0로 채우면 T7 대조에 들어감 ({t0 and t0['item']})")
f = F("4403", from_1="01:00", to_1="04:00")
t7 = Q(S(f), "T7")
expect(any(c["id"] == "both" for c in t7["choices"]) and "서로 맞나요" in t7["text"], "질문은 「서로 맞나요」 + 「둘 다 맞음(현장 분류)」 선택지")
pl = reflect.plan(f, [A(t7, "check", "09:00~11:00")])
fills = {x["base"]: x["final"] for P_ in pl.values() for x in P_["fills"]}
expect(fills.get("from_1") == "09:00" and fills.get("to_1") == "11:00", f"#2 「체크가 맞음」 09~11시 → 반영본 1행 시간이 고쳐짐 ({fills.get('from_1')}~{fills.get('to_1')})")
pl = reflect.plan(f, [A(t7, "time")])
pend = [t for P_ in pl.values() for _, t in P_["pending"]]
expect(any("체크 정정 필요" in t and "01:00~04:00" in t for t in pend), f"#2 「적힌 시간이 맞음」 → 체크 칸 정정 필요로 남김(대상 행 포함) ({pend})")
msgs = lambda f_: [x["msg"] for x in review.check(f_)]
expect(any("22:00~다음 날 06:00" in m for m in msgs(F("4403", from_1="01:00", to_1="04:00"))), "서식 점검: 주간 + 01~04시를 같은 기준으로 표시")
expect(not any("22" in m and "주간" in m for m in msgs(F("4403", from_1="20:00", to_1="23:00"))), "서식 점검: 주간 + 20~23시(저녁 연장)는 표시 안 함")

print("T7 Codex 마지막 회차(astra) 지적 재현")
EMPTY = dict(date_1="", from_1="", to_1="")
f = F("4403", **EMPTY)
t0 = next(q for q in S(f)["questions"] if q["item"].startswith("T0"))
a0 = A(t0, "value", "10/27 01:00~04:00; 10/28 09:00~11:00")
t7 = Q(S(f, [a0]), "T7")
s = S(f, [a0, A(t7, "check", "10:00~12:00")]) if t7 else None
expect(t7 and win(s, "2026-10-27") == ["10:00~12:00"] and win(s, "2026-10-28") == ["09:00~11:00"],
       f"#1 T0로 채운 행의 T7 정정은 그 날만 ({s and s['effective'][0]['windows']})")
f = F("4403", from_1="01:00", to_1="04:00")
t7 = Q(S(f), "T7")
s = S(f, [A(t7, "check", "10/28 09:00~11:00")])
expect(win(s, "2026-10-27") == ["01:00~04:00"] and not win(s, "2026-10-28"), f"#2 다른 날을 말한 T7 답은 계산에 넣지 않음 ({s['effective'][0]['windows']})")
pl = reflect.plan(f, [A(t7, "check", "10/28 09:00~11:00")])
pend = [t for P_ in pl.values() for _, t in P_["pending"]]
fills = {x["base"]: x["final"] for P_ in pl.values() for x in P_["fills"]}
expect("from_1" not in fills and any("정해지지 않아" in t for t in pend), f"#2 반영본도 시간 칸 그대로 + 확인 필요 ({pend})")
TWIN = dict(date_2="2026-10-27", from_1="01:00", to_1="04:00", from_2="01:00", to_2="04:00")
f = F("4012", **TWIN)
t7 = Q(S(f), "T7")
s = S(f, [A(t7, "check", "09:00~11:00")])
expect(win(s, "2026-10-27") == ["01:00~04:00", "09:00~11:00"], f"#5 같은 날 같은 시간의 다른 행은 남음 ({win(s, '2026-10-27')})")
old = A(t7, "check", "09:00~11:00")
f2 = F("4012", **{**TWIN, "from_1": "10:00", "to_1": "12:00"})
t7b = Q(S(f2, [old]), "T7")
expect(t7b and "p1.from_2" in t7b["keys"] and t7b["original"] == old["q"]["original"],
       "#3 대상이 같은 날짜·시간의 다른 행으로 바뀌면 예전 답은 쓰지 않고 다시 물음 (행 번호까지 대조)")
f = F("4403", **EMPTY)
t0 = next(q for q in S(f)["questions"] if q["item"].startswith("T0"))
a0 = A(t0, "value", "10/27 01:00~04:00")
t7 = Q(S(f, [a0]), "T7")
pl = reflect.plan(f, [a0, A(t7, "check", "09:00~11:00")]) if t7 else {}
fills = {x["base"]: x["final"] for P_ in pl.values() for x in P_["fills"]}
expect(t7 and fills.get("from_1") == "09:00" and fills.get("to_1") == "11:00", f"#4 T0로 채운 행의 T7 정정이 반영본에 그대로 ({fills.get('from_1')}~{fills.get('to_1')})")
f = F("4403", from_1="23:00", to_1="04:00")
t5 = Q(S(f), "T5")
t7 = Q(S(f, [A(t5, "overnight")]), "T7")
s = S(f, [A(t5, "overnight"), A(t7, "check", "09:00~11:00")])
expect(win(s, "2026-10-27") == ["09:00~11:00"] and not Q(s, "T8"), f"#6 다음 날 종료를 T7로 낮 시간으로 고치면 T8 없음 ({win(s, '2026-10-27')})")
for a, b in (("23:00", "04:00"), ("24:00", "00:00"), ("24:30", "04:00")):
    expect(not any("22:00~다음 날 06:00" in m for m in msgs(F("4403", from_1=a, to_1=b))), f"#7 서식 점검: {a}~{b}는 확정된 야간 구간으로 말하지 않음")

print("T8 야간·교대 지원과 인계 — 화기, 서류·답이 말한 야간만 (N1 MT12 p205)")
s = S(F("4403", day=False, night=True, from_1="20:00", to_1="23:00"))
t8 = Q(s, "T8")
expect(t8 and neutral(t8) and "인계" in t8["text"], "야간 체크 + 20~23시 화기 → T8")
expect(not Q(S(F("4403", from_1="20:00", to_1="23:00")), "T8"), "야간 체크·다음 날 종료가 없으면 시간만으로는 T8 없음 (작성자 가정 안 씀)")
expect(not Q(S(F("4012", day=False, night=True, from_1="20:00", to_1="23:00", job_detail="E42P 론지 용접")), "T8"),
       "(최종 검토) 교대·인계·지원 언급이 하나도 없으면 야간 체크만으로는 T8 없음 (자료 MT14·N4-MT15: 야간 자체로 묻지 않음)")
expect(Q(S(F("4403", day=False, night=True, from_1="20:00", to_1="23:00", job_detail="야간 교대 있음")), "T8") is not None,
       "(Codex #6) 「교대」 한 단어로는 T8이 닫히지 않음")
expect(not Q(S(F("4403", day=False, night=True, from_1="20:00", to_1="23:00", job_detail="투광등 2대, 22시 야간조에 인계")), "T8"),
       "지원(투광등)과 인계가 모두 적혀 있으면 T8 없음")
for no in ("5067", "5325", "6623"):
    s = S(F(no, day=False, night=True, from_1="20:00", to_1="23:00"))
    expect(not Q(s, "T8") and not Q(s, "T7"), f"{no}: 비화기 야간 → 야간 자체로는 묻지 않음")
f = F("4403", to_1="01:30")
t5 = Q(S(f), "T5")
expect(not Q(S(f), "T8"), "T5(종료<시작)가 열려 있으면 T8은 기다림")
expect(not Q(S(f, [A(t5, "unknown")]), "T8"), "(Codex #11) T5 「모름」이면 시간의 뜻이 그대로 미상: T8 없음")
expect(Q(S(f, [A(t5, "overnight")]), "T8") is not None, "T5 「다음 날 끝남」 → T8")

print("T9 대기·중단·교대 중 상태 (N1 MT07, N2 MT09, N3 MT11, N5 MT07)")
for no, kv, kind in (("4403", {"job_detail": "검사 대기 후 재용접"}, "hot"), ("5067", {"job_detail": "진입 2명, 점심 휴식 후 재진입"}, "confined"),
                     ("5325", {"job_detail": "러그 6EA 절단, 점심 휴식 후 이어서 절단·회수"}, "height"),
                     ("6623", {"job_detail": "정전·잠금 후 작업, 부품 대기 후 교체, 복구 전 시험운전"}, "loto")):
    t9 = Q(S(F(no, **kv)), "T9")
    expect(t9 and t9["text"] == augment.WAIT_Q[kind][0], f"{no}: '{kv['job_detail']}' → T9 ({kind} 문구)")
expect(Q(S(F("5067", job_detail="진입 2명, 점심 휴식 후 재진입, 재진입 전 재측정")), "T9") is not None,
       "(Codex #6) 「재측정」만으로는 T9가 닫히지 않음(공급·환기 유지가 없음)")
expect(not Q(S(F("5067", job_detail="진입 2명, 점심 휴식 후 재진입, 재진입 전 산소·가스 재측정, 휴식 중 환기 유지")), "T9"),
       "재측정과 환기 유지가 모두 적혀 있으면 T9 없음")
expect(not Q(S(F("4403", job_detail="검사 대기 중 가스 밸브 차단 유지, 14:00 재개")), "T9"), "(Codex #11) 대기 중 상태와 재개 시각이 적혀 있으면 T9 없음")
f = F("5325", from_1="20:00", to_1="02:00")
t5 = Q(S(f), "T5")
expect(not Q(S(f, [A(t5, "overnight")]), "T9"), "(Codex #11) 고소: 멈춤 없이 자정을 넘기는 것만으로는 T9 없음")
expect(not Q(S(F("5435", job_detail="정반 안착 후 줄걸이 해제, 크레인 대기")), "T9"), "인양에는 T9 없음 (N4에 해당 항목 없음)")
e = S(F("4403", job_detail="검사 대기 후 재용접"))["effective"][0]
expect(e["fit"]["state"] == "defer" and "대기" in e["fit"]["why"], f"길이 모르는 대기 → 참고시간 비교 보류 (p203 T08): {e['fit']['why']}")

print("T4 종료의 뜻(잔불 확인) — 화기·가스/플라즈마 고소 (N1 MT13 p205, N3 MT12 p275, LU15-FIRE p266)")
s = S(DOCS["4403"]["fields"])
t4 = Q(s, "T4")
expect(t4 and t4["tier"] == "extra" and "15:30" in t4["text"] and [c["id"] for c in t4["choices"]] == ["incl", "time", "unknown"],
       "4403 → T4 (extra, 종료 15:30이 잔불 확인까지인지)")
o = N.order(s["questions"])
expect(o[0]["item"] == "H2" and {x["item"] for x in o[-2:]} == {"T4", "L6"}, f"순서: 규칙 core 먼저, extra(T4·L6)는 끝 ({[q['item'] for q in o]})")
expect(Q(S(F("4403", job_detail="지상 작업, 잔불 확인")), "T4") is not None, "(Codex #6) 「잔불」 한 단어로는 T4가 닫히지 않음")
expect(not Q(S(F("4403", job_detail="지상 작업, 화재감시 16시까지")), "T4"), "잔불·화재감시 끝 시각이 적혀 있으면 T4 없음")
s2 = S(DOCS["4403"]["fields"], [A(t4, "time", "16시 30분")])
expect(s2["effective"][0]["residual"] == "16:30" and s2["effective"][0]["windows"]["2026-10-27"] == ["13:00~16:30"]
       and s2["effective"][0]["windows_work"] == {"2026-10-27": ["13:00~15:30"]},
       f"T4 '16시 30분' → 잔류 끝 16:30, windows는 늘고 windows_work는 작업 시간 그대로 ({s2['effective'][0]['windows']})")
for v in ("4시 반", "오전 12시 30분", "곧"):
    expect(augment.check_value({}, {"qid": "T4:X", "choice": "time", "value": v}) != "", f"(Codex #7) T4 '{v}' → 오전·오후·날짜를 다시 받음")
f = F("4403", from_1="20:00", to_1="23:00")
t4n = Q(S(f), "T4")
s3 = S(f, [A(t4n, "time", "다음날 01:00")])
expect(s3["effective"][0]["windows"]["2026-10-27"] == ["20:00~익일 01:00"], f"(Codex #7) T4 '다음날 01:00' → 날짜를 넘는 끝 ({s3['effective'][0]['windows']})")
s4 = S(f, [A(t4n, "time", "01:00")])
a5 = Q(s4, "A5.T4")
expect(a5 is not None and s4["effective"][0]["residual"] == "", "T4 '01:00'(작업 끝 23:00보다 이름, 날짜 없음) → 쓰지 않고 다음 날인지 되물음")
expect(S(f, [A(t4n, "time", "01:00"), A(a5, "next")])["effective"][0]["windows"]["2026-10-27"] == ["20:00~익일 01:00"], "「다음 날」 → 익일 01:00")
expect(not Q(S(DOCS["4012"]["fields"]), "T4"), "4012: 시간의 뜻(T1)이 열려 있으면 T4는 기다림 (DEFER)")
q1 = Q(S(DOCS["4012"]["fields"]), "T1")
expect(not Q(S(DOCS["4012"]["fields"], [A(q1, "unknown")]), "T4"), "(Codex #11) T1 「모름」 → 시간의 뜻 미상 그대로: T4 없음")
t6q = {"qid": t4["qid"].replace("T4", "T6"), "item": "T6", "choices": [{"id": "yes", "label": "잔불 확인까지 전체 시간이 맞음"}], "keys": []}
expect(not Q(S(DOCS["4403"]["fields"], [A(t6q, "yes")]), "T4"), "(Codex #11) 화기 T6 「잔불 확인까지 전체 시간이 맞음」 → T4 다시 묻지 않음")
h = Q(S(DOCS["5325"]["fields"]), "HT1")
s2 = S(DOCS["5325"]["fields"], [A(h, "gas", "6개")])
expect(Q(s2, "T6") and not Q(s2, "T4"), "5325 HT1 가스절단 → T6가 열려 있는 동안 T4 없음")
t6 = Q(s2, "T6")
expect("절단만 적었나요, 회수·사상·철수까지" in t6["text"], "고소 T6 「짧다」 문구 = 자료 N3 MT12")
expect(Q(S(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "yes")]), "T4") is not None, "T6 답 뒤 가스절단 고소 → T4")
expect(not Q(S(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "unknown")]), "T4"), "(Codex #11) T6 「모름」 → T4 없음")
expect(any(q["item"] == "T4" for q in augment.summary(DOCS["5325"]["fields"], [A(h, "gas", "6개")], True)["questions"]),
       "안전관리자 화면에도 가스절단 고소의 T4")

print("T6 단계·정정 (Codex #9): stage는 따로, retime은 바꿈, 구간은 합집합, full_end는 날짜별")
s4 = S(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "stage", "10:00~15:00")])
e = s4["effective"][0]
expect(e["windows"]["2026-10-27"] == ["10:00~15:00"] and e["windows_stage"] == {"written": {"2026-10-27": ["10:00~12:00"]}}
       and e["full_end"] == {"2026-10-27": "15:00"} and e["time_meaning"] == "full" and e["windows_req"]["2026-10-27"] == ["10:00~12:00"],
       f"stage 10:00~15:00 → windows 전체(합집합 한 구간), windows_stage.written, full_end 날짜별 ({e['windows']}, {e['windows_stage']}, {e['full_end']})")
s5 = S(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "retime", "13:00~14:00")])
expect(s5["effective"][0]["windows"] == {"2026-10-27": ["13:00~14:00"]} and not s5["effective"][0]["full_end"],
       f"T6 「실제 시간 다시 입력」 13~14시 → 창을 바꿈(기준본 동작) ({s5['effective'][0]['windows']})")
s6 = S(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "stage", "다음 날 00:00~02:00")])
expect(s6["effective"][0]["windows"].get("2026-10-28") == ["00:00~02:00"], f"(Codex #7) T6 '다음 날 00:00~02:00' → 다음 날짜 ({s6['effective'][0]['windows']})")
for kind, no in (("lifting", "5435"), ("loto", "6623")):
    t6k = Q(S(DOCS[no]["fields"]), "T6")
    expect(t6k and augment.END_Q[kind] in t6k["text"], f"{kind} T6 「짧다」 문구는 자료의 종료 의미 질문")

print("인양 T1 「움직이는 구간」은 따로, 전체 창 유지, T6 단계와 따로 보존 (N4-MT03)")
q1 = Q(S(DOCS["5388"]["fields"]), "T1")
e = S(DOCS["5388"]["fields"], [A(q1, "partial", "10/27 10:30~11:30")])["effective"][0]
expect(e["windows"]["2026-10-27"] == ["08:00~16:59"] and e["windows_stage"] == {"move": {"2026-10-27": ["10:30~11:30"]}} and e["time_meaning"] == "stage",
       f"인양 T1 10:30~11:30 → windows 유지, windows_stage.move ({e['windows_stage']})")
s = S(DOCS["5388"]["fields"], [A(q1, "partial", "10/27 17:30~18:30")])
e = s["effective"][0]
expect("17:30~18:30" in e["windows"]["2026-10-27"] and Q(s, "C6.T1") is not None, "신청 창 밖 단계 → 잘라내지 않고 보존, 한 번 확인(C6)")

print("날짜별 대조·확인된 오전·오후로 대조 (Codex #7, N2 MT15, N5 MT13)")
f = F("4012", from_1="09:00", to_1="12:00", from_2="13:00", to_2="16:59")
q1 = Q(S(f), "T1")
expect(Q(S(f, [A(q1, "partial", "10/27 13:00~15:00")]), "C6.T1") is not None, "10/27은 09~12인데 답이 10/27 13~15 → C6")
expect(not Q(S(f, [A(q1, "partial", "10/27 09:00~11:00")]), "C6.T1"), "그날 창 안이면 C6 없음")
q1 = Q(S(DOCS["5151"]["fields"]), "T1")
s = S(DOCS["5151"]["fields"], [A(q1, "partial", "6시~8시")])
a1 = Q(s, "A1.T1")
s = S(DOCS["5151"]["fields"], [A(q1, "partial", "6시~8시"), A(a1, "pm")])
expect(Q(s, "C6.T1") is not None, "T1 '6시~8시' + A1 「오후」 → 18~20시는 신청 창 밖: C6 (확인된 해석으로 대조)")

print("거꾸로 된 시간: 확인 없이 다음 날로 바꾸지 않음 (MT04)")
expect(augment.check_value({}, A(q1, "partial", "22:00~02:00")) != "" and augment.time_ranges("22:00~02:00") == [],
       "T1 '22:00~02:00'은 읽지 않고 다시 받음(자동 익일 없음)")
e = S(F("4403", to_1="01:30"))["effective"][0]
expect(e["windows"] == {} and Q(S(F("4403", to_1="01:30")), "T5") is not None, "서류 종료<시작: T5 답 전에는 창 없음, T5를 물음")

print("H2·H3 (MT10·MT08 p205, p200 국부 파내기)")
h2 = Q(S(DOCS["4403"]["fields"]), "H2")
expect(h2 and h2.get("m") == 0.5 and "가스" in h2["text"], "가우징은 적혀 있고 가스가 없음 → 가스만 묻는 H2 (M 0.5)")
expect(not Q(S(F("4403", job_detail="지상 작업, CO2 용접·가우징 압축공기")), "H2"), "가스가 적혀 있으면 H2 없음")
h3 = Q(S(F("4403", job="E33S 블록 종통재 깊은 균열부 가우징·재용접 1군데")), "H3")
expect(h3 and [c["id"] for c in h3["choices"]] == ["none", "text", "unknown"], "깊은 국부 파내기 → H3 (받치는 구조)")
expect(not Q(S(F("4403", job="E33S 블록 종통재 깊은 균열부 가우징·재용접 1군데, 받치는 것 없음")), "H3"), "받침 여부가 적혀 있으면 H3 없음")

print("밀폐: CF1 진입 방식, CF2·CF3·D6·D7은 원자로만 닫힘 (Codex #6), CF4, CF5")
fc = F("5067", job_detail="맨홀 외부에서 부분 점검")
c1 = Q(S(fc), "CF1")
expect(c1 and [c["id"] for c in c1["choices"]] == ["head", "full", "unknown"], "(Codex #6) '맨홀 외부에서 부분 점검'(+ '진입 전 측정') → 진입 방식 CF1")
expect(not Q(S(DOCS["5067"]["fields"]), "CF1"), "5067 '진입 2명' → CF1 없음")
P1 = augment.effective(fc, [A(c1, "full", "맨홀 M-2")])[0]
expect(augment._scope(P1, {c1["qid"]: A(c1, "full", "맨홀 M-2")}) == "inspect", "CF1 「몸 전체」 답은 목적(점검)을 지우지 않음")
c2 = Q(S(DOCS["4676"]["fields"]), "CF2")
expect(c2 and "압력시험" in c2["text"], "CF2 문구에 다른 팀 공급·압력시험·복구 예정 (N2 MT07)")
for jd, want in (("파이프 내부 진입, 아르곤 배관, 밸브 잠금, 유지", True), ("파이프 내부 진입, 아르곤 퍼지 라인 차단, 진입 중 유지", True),
                 ("파이프 내부 진입, 아르곤 퍼지 라인 차단, 진입 중 유지, 배관팀 압력시험 없음", False)):
    expect((Q(S(F("4676", job_detail=jd)), "CF2") is not None) == want, f"CF2 '{jd}' → {'묻기(원자 부족)' if want else '닫힘(차단·유지·다른 팀/복구)'}")
for jd, want in (("진입 2명, 환기팬 전원", True), ("진입 2명, 환기팬은 3BAY 분전반 DB-2", False)):
    expect((Q(S(F("5067", job_detail=jd)), "CF3") is not None) == want, f"CF3 '{jd}' → {'묻기' if want else '닫힘(전원 이름)'}")
c3 = Q(S(DOCS["5067"]["fields"]), "CF3")
e = S(DOCS["5067"]["fields"], [A(c3, "text", "3BAY 분전반 DB-2 환기팬 2개, 다른 팀은 DB-3 차단")])["effective"][0]
expect(e["facts"]["CF3"]["sources"] == ["DB-2"] and "DB-2" not in e["targets"] and "DB-3" not in e["targets"] and e["count"] is None,
       f"(Codex #10) CF3 답 → facts.CF3.sources ['DB-2'], 대상·검사 지점 수가 아님, 다른 팀 DB-3 아님 ({e['facts']}, {e['targets']}, {e['count']})")
for kv, want in (({"commissioning": True}, True), ({"commissioning": True, "job_detail": "수전"}, True),
                 ({"commissioning": True, "job_detail": "진입 2명, 통전 설비 없음"}, False)):
    expect((Q(S(F("5067", **kv)), "D6") is not None) == want, f"D6 {kv} → {want}")
for kv, want in (({"pressure_use": True}, True), ({"pressure_use": True, "job_detail": "질소"}, True),
                 ({"pressure_use": True, "job_detail": "질소 기밀시험, 10:00 가압 11:30 감압"}, False)):
    expect((Q(S(F("5067", **kv)), "D7") is not None) == want, f"D7 {kv} → {want}")
c4 = Q(S(F("5067", hazards="화기작업시 개인보호구 착용, 이면부 확인, 작업구역 통제(병행 작업 금지)")), "CF4")
expect(c4 is not None and not Q(S(F("5067", job="F12C 이중저 내부 용접 상태 점검")), "CF4"), "CF4: 밀폐 허가서의 화기, '용접 상태 점검'은 아님")
fc4 = F("5067", hazards="화기작업시 개인보호구 착용, 이면부 확인, 작업구역 통제(병행 작업 금지)")   # the form it was asked on
e = S(fc4, [A(c4, "yes", "CO2 용접 1곳, 화기작업 허가서 0712")])["effective"][0]
expect(e["facts"].get("CF4", {}).get("choice") == "yes", "(Codex #8) CF4 답 → effective facts")
c1b = Q(S(F("5067", job="F12C 이중저 내부 작업", job_detail="")), "CF1")
s = S(F("5067", job="F12C 이중저 내부 작업", job_detail=""), [A(c1b, "text", "이중저 내부 도장")])
expect(Q(s, "CF5") is not None, "(Codex #10) CF1 답이 '내부 도장' → CF5")
expect(N.row("CF5")["owner"] == "self_partial", "CF5는 들은 정보(A 0.5)")
e = S(F("5067", pressure_use=True), [A(Q(S(F("5067", pressure_use=True)), "D7"), "text", "질소, 10:00 가압 ~ 11:30 감압")])["effective"][0]
expect(e["facts"].get("D7", {}).get("value", "").startswith("질소"), "(Codex #8) D7 답 → effective facts")

print("고소: L7 여러 러그(N3 MT07), HT2 원자(MT09), L6 원자, L4 블록만")
expect(Q(S(DOCS["5325"]["fields"]), "L7") is not None, "러그 6개, 17-20 칼럼 → L7 (여러 러그 위치인지)")
for jd, want in (("러그 6EA 절단, 로프로 내림", True), ("러그 6EA 절단, 로프 점검, 하부 작업자 있음", True),
                 ("러그 6EA 절단, 로프로 내려 하부 적치함에 모음", False)):
    expect((Q(S(F("5325", job_detail=jd)), "HT2") is not None) == want, f"HT2 '{jd}' → {'묻기' if want else '닫힘(내리는 수단·놓을 곳)'}")
for hz, want in (("러그 낙하, 통제", True), ("러그 낙하 / 하부 반경 5m 통제", False)):
    expect((Q(S(F("5325", hazards=hz)), "L6") is not None) == want, f"L6 '{hz}' → {'묻기' if want else '닫힘(범위)'}")
expect(not Q(S(F("4676", job="배관 P-01, 밸브 V-12 점검")), "L4"), "(Codex #10) 배관 P-01·밸브 V-12는 블록이 아님 → L4 없음")
expect(Q(S(DOCS["4012"]["fields"]), "L4") is not None, "B11·F31·E11 블록 4일 → L4")

print("인양·정전: LI1, L5, LI3·LO6(레일 관계가 적혀 있으면 닫힘), LO3 원자, LO5")
li = Q(S(F("5435", hull_no="", job="블록 반출 인양·이동·안착 (천장크레인 OH-21-01)")), "LI1")
expect(li and li["choices"][0]["id"] == "blocks", "크레인은 있고 블록 번호·개수가 없음 → LI1 블록 질문")
l5 = Q(S(F("5388", job_detail="천장크레인 사용, 반전 있음")), "L5")
expect(l5 and "회전·반전하는 위치" in l5["text"], "반전이 적혀 있고 경로가 없음 → L5에 회전 위치")
expect(Q(S(DOCS["5435"]["fields"]), "LI3") is not None, "크레인 번호 → LI3")
expect(not Q(S(F("5435", job_detail="정반 안착 후 줄걸이 해제, 같은 레일 다른 크레인 운행 없음")), "LI3"), "(Codex #11) 서류에 같은 레일 관계 → LI3 없음")
expect(not Q(S(F("6623", job_detail="정전·잠금 후 작업, 크레인 정비 중 같은 레일 운행 없음")), "LO6"), "(Codex #11) 서류에 레일 관계 → LO6 없음")
q3 = Q(S(DOCS["5435"]["fields"]), "LI3")
e = S(DOCS["5435"]["fields"], [A(q3, "text", "OH-21-02 10시 정비, 같은 레일")])["effective"][0]
expect(e["cranes"] == ["OH-21-01"] and e["facts"]["LI3"]["value"].startswith("OH-21-02"), "LI3 답의 다른 크레인은 이 허가서 크레인이 아님, facts로 남음")
expect(Q(S(F("6623", job_detail="정전·잠금 후 작업, 14:30 복구")), "LO3") is not None, "(Codex #6) '14:30 복구'만(차단 시각 없음) → LO3 그대로")
expect(not Q(S(F("6623", job_detail="13:00 차단, 14:30 복구, 14:45 시험운전")), "LO3"), "차단·복구 둘 다 → LO3 없음")
lo5 = Q(S(DOCS["5488"]["fields"]), "LO5")
expect(lo5 is not None and not Q(S(DOCS["6623"]["fields"]), "LO5"), "원인 찾는 점검이면 LO5")
expect(S(DOCS["5488"]["fields"], [A(lo5, "live", "인버터 출력 전압 측정 13:20")])["effective"][0]["facts"]["LO5"]["choice"] == "live",
       "(Codex #8) LO5 「있음」 → effective facts")

print("A4·L7 정정은 칼럼을 바꿈 (Codex #2)")
f = F("4403", location="대조립21공장 3BAY 16-14 칼럼")
a4 = Q(S(f), "A4.cols")
expect(a4 and "14~16" in a4["text"], "'16-14 칼럼' → 한 번 되물음")
e = S(f, [A(a4, "place", "18-20 칼럼")])["effective"][0]
expect(e["place"]["cols"].startswith("18-20") and "3" in e["place"]["bays"], f"A4 '18-20 칼럼' → 칼럼을 18-20으로 바꾸고 BAY는 유지 ({e['place']})")
f = F("6623", location="대조립21공장 3BAY 10-16 칼럼")
l7 = Q(S(f), "L7")
e = S(f, [A(l7, "place", "14-15 칼럼 제어반 앞")])["effective"][0]
expect(e["place"]["cols"].startswith("14-15"), f"L7 실제 위치 14-15 칼럼 → 10-16을 바꿈 ({e['place']['cols']})")
expect(augment.ids("E170(A), B-01, B11, E52, F31") == {"E170(A)", "B-01", "B11", "E52", "F31"}, "E170(A)·B-01·B11 블록 번호를 읽음")

print("C5.concurrent (Codex #4): 금지 지침 구절만 빼고 실제 작업 진술은 읽음")
expect(not Q(S(DOCS["4403"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "작업구역 통제(병행 작업 금지)"}]), "C5.concurrent"),
       "'작업구역 통제(병행 작업 금지)' → C5 없음")
expect(Q(S(DOCS["4403"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "병행 작업 금지인데 다른 팀이 같은 장소에서 도장 중입니다"}]),
         "C5.concurrent") is not None, "'병행 작업 금지인데 다른 팀이 같은 장소에서 도장 중' → C5 (기준본처럼)")

print("「없음」을 글로 답함 (Codex trace §B·#5): 하나의 무조건 부정만 확정")
for v, want in (("가스·공기 배관 연결 없음", "none"), ("없음", "none"), ("연결 계통 없음", "none"),
                ("아르곤 퍼지 라인 V-12, 진입 전 차단", None), ("배관 연결 없으면 바로 진입", None), ("아마 없을 거예요", None),
                ("옆 팀 배관은 연결 없음", None), ("가스 배관 연결 없음, 공기 호스는 있음", None),
                ("배관 연결은 없는 줄 알았는데 있어요", None), ("배관 연결이 없지 않아요", None), ("배관 연결 없이는 못 해요", None),
                ("가스 배관 연결 있음 공기 호스 없음", None)):
    expect(augment.negated("CF2", {"choice": "text", "value": v}) == want, f"CF2 '{v}' → {want}")
for v, want in (("전기 용접만", "na"), ("가스 안 씀", "na"), ("전기 용접만, 산소 LPG 절단도 함", None), ("CO2 용접", None),
                ("가스 없이는 못 해요", None), ("전기 용접만, 질소 퍼지 있음", None)):
    expect(augment.negated("H2", {"choice": "text", "value": v}) == want, f"H2 '{v}' → {want}")
c2 = Q(S(DOCS["4676"]["fields"]), "CF2")
for v, want in (("가스·공기 배관 연결 없음", True), ("배관 연결 없으면 바로 진입", False), ("배관 연결은 없는 줄 알았는데 있어요", False)):
    s = S(DOCS["4676"]["fields"], [A(c2, "text", v), {"qid": "FREE:1", "choice": "text", "value": "아르곤 퍼지 라인 V-12 연결 있음"}])
    expect((Q(s, "C5.CF2") is not None) == want, f"CF2 '{v}' 뒤 '아르곤 퍼지 라인 V-12 연결 있음' → C5.CF2 {want}")
f = F("4012", job_detail="산소 LPG 절단")
h2 = Q(S(DOCS["4012"]["fields"]), "H2")
for v, want in (("전기 용접만", True), ("전기 용접만 하면 됩니다, 아마", False), ("가스 없이는 못 해요", False)):
    pend = json.dumps(reflect.plan(f, [OLD(A(h2, "text", v))]), ensure_ascii=False)        # the form was not changed after it
    expect(("허가서 내용과 다름" in pend) == want, f"원본 '산소 LPG 절단' + H2 '{v}' → 문서와 다름 {want}")

print("C6 「서류가 맞음」은 앞 답을 철회 (Codex #3), 재질문은 사실 지문으로")
h = Q(S(DOCS["5151"]["fields"]), "HT1")
# an answer that carries no form mark (given before 2026-11-01, or not tied to fields) stands when the form differs:
# the answer and the document disagree — C6 asks which is right (Codex #3)
ans = [{**A(h, "plasma", "6개"), "q": {k: v for k, v in h.items() if k != "fp"}}]
f = F("5151", job_detail="러그 2개 가스절단")
c6 = Q(S(f, ans), "C6.HT1")
expect(c6 is not None and "~" in c6["qid"], "HT1 플라즈마 6개 → 서류가 '러그 2개 가스절단' → C6.HT1 (qid에 지문)")
s = S(f, ans + [A(c6, "doc")])
e = s["effective"][0]
P0 = augment.effective(f, ans + [A(c6, "doc")])[0]
pl = json.dumps(reflect.plan(f, ans + [A(c6, "doc")]), ensure_ascii=False)
rec = next(r for r in s["records"] if r["qid"] == h["qid"])
expect(e["count"] == 2 and augment._scope(P0, {}) == "gas" and "플라즈마" not in pl and rec["status"].startswith("철회"),
       f"「서류가 맞음」 → 개수 2·가스절단, 반영본에 플라즈마 없음, 기록은 철회 ({e['count']}, {rec['status']})")
expect(not any(q["item"] == "C6.HT1" for q in s["questions"]), "철회 뒤 같은 상충을 다시 묻지 않음")
# 최종 검토 2026-11-01 「관련값이 바뀌면 다시 묻기」: the foreman changes the form after answering — the answer about the old
# values is not used, and its question is asked again on the new values (no C6 between his own two statements)
f2 = F("5151", job_detail="러그 3개")
h0 = Q(S(DOCS["5151"]["fields"]), "HT1")
s2 = S(f2, [A(h0, "plasma", "6개")])
expect(Q(s2, "HT1") is not None and not Q(s2, "C6.HT1") and s2["effective"][0]["count"] == 3,
       f"답한 뒤 반장이 서류를 '러그 3개'로 고침 → 예전 HT1 답은 쓰지 않고 HT1을 다시 물음 ({s2['effective'][0]['count']})")
cf2 = Q(S(F("5067", hazards="아르곤 퍼지 배관 연결")), "CF2")
s3 = S(F("5067", hazards="아르곤 퍼지 배관 연결, 질소 라인 추가"), [A(cf2, "text", "아르곤 V-12 진입 전 차단")])
expect(cf2 is not None and Q(s3, "CF2") is not None, "CF2에 답한 뒤 그 칸(유해위험요소)을 고침 → CF2를 다시 물음")
s4 = S(F("5067", hazards="아르곤 퍼지 배관 연결"), [A(cf2, "text", "아르곤 V-12 진입 전 차단")])
expect(not Q(s4, "CF2"), "칸을 고치지 않으면 답은 그대로")

print("모름의 종류·당일 값")
for v, want in (("담당자에게 확인 중입니다", "확인 예정"), ("상황 봐서", "미정"), ("아마 6개", "불확실"), ("", "모름")):
    expect(augment.unknown_kind(v) == want, f"「모름」 + '{v}' → {want}")
nyd = S(DOCS["4403"]["fields"])["effective"][0]["not_yet_due"]
expect(isinstance(nyd, list) and set(nyd) <= augment.DAY_OF_VALUES, f"당일 값은 묻지 않고 not_yet_due로 남김 ({nyd})")

print("참고모델 조건 (2.6: 한 단어로 모델을 고르지 않음, 미상은 비교 보류, 합집합)")
tm = lambda no, ans=(), **kv: augment.time_model(augment.effective(F(no, **kv), list(ans))[0], {a["qid"]: a for a in ans})
expect(tm("4403", job="E33S 블록 깊은 균열부 가우징 1군데")[0] is None, "'깊은' 한 단어로 T02를 고르지 않음")
expect(tm("4403", job="E33S, F31 블록 균열부 가우징 2군데")[0] is None, "다른 블록 여러 개: T04 보류")
expect(tm("4403", job="E33S 블록 재용접만")[0] is None and tm("4403", job="E33S 블록 재용접만 1군데")[0] == "T06 재용접·검사만", "T06 개수 미상 보류")
expect(tm("4403", job="E33S 블록 같은 불량 재보수 균열부 가우징")[0].startswith("T07"), "같은 불량 재작업 → T07")
m = tm("5067", job_detail="진입 2명, 3곳 점검")
expect(m[0].startswith("R-I") and (m[1], m[2]) == (110, 220), f"R-I 검사 3곳 → 110~220 ({m})")
expect(tm("5067")[0] is None, "R-I 검사 지점 수 미상 → 보류")
m = tm("5067", job_detail="2곳 점검, 2회 진입 반복")
expect(m[0] and m[0].startswith("R-N") and (m[1], m[2]) == (155, 310), f"R-N 2곳·2회 → 155~310 ({m})")
expect(tm("5325", job="E42P, E43P 블록 상부 임시 인양러그 절단·제거")[0] is None, "고소 여러 블록 → 보류")
expect(tm("5325", job_detail="러그 6EA 가스절단 두께 50mm")[0] is None, "두께 50mm → 보류")
m = tm("5325", [A(Q(S(DOCS["5325"]["fields"]), "HT1"), "plasma", "6개")])
expect(m[0] and (m[1], m[2]) == (40 + 45 * 6, 80 + 95 * 6), f"플라즈마 6개 → 40+45n~80+95n ({m})")
expect(tm("5435")[0].startswith("N4-EST-B"), "2BAY → 1BAY 경로 → EST-B")
expect(tm("6623", job_detail="인버터 교체 2회 반복 시험")[1:] == (300, 720) and tm("6623", job_detail="인버터 교체 반복")[0] is None, "EST-D")
e = S(F("4403", from_1="13:00", to_1="15:00", from_2="14:00", to_2="16:00", date_2="2026-10-27"))["effective"][0]
expect(e["windows"]["2026-10-27"] == ["13:00~16:00"], f"같은 날 겹친 두 행 → 합집합 한 구간 ({e['windows']})")

print("예산·순서: 모든 질문 「모름」이어도 12문 안, 규칙 필수 질문이 먼저")
for no, doc in DOCS.items():
    ans, seen = [], []
    for _ in range(40):
        s = S(doc["fields"], ans)
        o = [q for q in N.order(s["questions"]) if q.get("tier") != "extra"]
        if not o:
            break
        seen.append(o[0]["item"])
        ans.append(A(o[0], "unknown"))
    req = [N.row(i)["required"] for i in seen]
    expect(len(seen) <= 12 and req == sorted(req, reverse=True), f"{no}: core {len(seen)}문 {seen}")

print("최종 검토 (Codex final) — API 경로 _normalize 포함")
from fastapi.testclient import TestClient  # noqa: E402
from server import app as webapp, addendum  # noqa: E402


def norm(f, ans):
    """the API's normalisation (app._normalize), then the summary: the path every request takes"""
    ok_, errors, found = webapp._normalize(f, copy.deepcopy(list(ans)))
    return ok_, errors, found, augment.summary(f, ok_)


print("#1 negated: 답 전체가 하나의 무조건 부정일 때만")
for v in ("가스 연결 없음. 질소 투입 예정", "배관 연결 없다고 들었어요", "가스 연결 없음, 나중에 질소 넣을 거예요"):
    expect(augment.negated("CF2", {"choice": "text", "value": v}) is None, f"CF2 '{v}' → 부정 아님(글 그대로)")
c2 = Q(S(DOCS["4676"]["fields"]), "CF2")
ok_, _, _, s = norm(DOCS["4676"]["fields"], [A(c2, "text", "가스 연결 없음. 질소 투입 예정")])
expect(augment.eff_choice("CF2", ok_[0]) == "text", "API 경로에서도 '가스 연결 없음. 질소 투입 예정'은 「없음」이 아님")

print("#3 live_answers: C5 정정은 앞 답을 철회하고 정정 문장을 그 항목의 답으로")
ans = [A(c2, "none"), {"qid": "FREE:1", "choice": "text", "value": "아르곤 퍼지 라인 V-12 연결 있음"}]
c5 = Q(S(DOCS["4676"]["fields"], ans), "C5.CF2")
ans.append(A(c5, "free", "아르곤 퍼지 라인 V-12 연결 있음"))
live = augment.live_answers(ans)
cf2 = next(a for a in live if a["qid"] == c2["qid"])
s = S(DOCS["4676"]["fields"], ans)
expect(cf2["choice"] == "text" and "V-12" in cf2["value"] and "V-12" in s["effective"][0]["targets"]
       and next(r for r in s["records"] if r["qid"] == c2["qid"])["answer"] == "연결 계통 없음",
       f"C5.CF2 정정 → CF2 유효 답 '{cf2['value']}', 대상에 V-12, 기록(이력)은 원래 답 그대로")

print("#4 확정된 원자만 생략 (미정·확인 필요·불가·가능한지)")
for no, kv, item in (("4676", {"job_detail": "파이프 내부 진입, 가스 배관 연결 있음, 차단 불가, 진입 중 유지 미정, 복구 16:00"}, "CF2"),
                     ("5067", {"job_detail": "진입 2명, 환기팬 전원 DB-2인지 확인 필요"}, "CF3"),
                     ("5067", {"commissioning": True, "job_detail": "진입 2명, 통전 펌프 P-3 차단 담당 미정"}, "D6"),
                     ("5067", {"pressure_use": True, "job_detail": "진입 2명, 질소 10:00 가압, 감압 완료 시각 미정"}, "D7"),
                     ("4403", {"job_detail": "CO2 용접, 화재감시 16:00까지 가능한지 미정"}, "T4"),
                     ("5067", {"job_detail": "진입 2명, 점심 휴식 후 중간 재진입 전 재측정 예정, 환기 유지 여부 미정"}, "T9")):
    expect(Q(S(F(no, **kv)), item) is not None, f"{item}: '{kv.get('job_detail')}' → 그대로 물음")
expect(not Q(S(F("5067", pressure_use=True, job_detail="진입 2명, 질소, 10:00 가압, 11:30 감압 완료")), "D7"), "D7: 매체·가압 시작·감압 완료가 모두 있으면 생략")

print("서류가 이미 답한 사실 (facts src doc)")
e = S(F("5067", job_detail="진입 2명, 환기팬·조명 3BAY 분전반 DB-2"))["effective"][0]
expect(e["facts"].get("CF3", {}).get("src") == "doc" and "DB-2" in e["facts"]["CF3"]["value"], f"CF3를 서류가 답함 → facts.CF3 src doc ({e['facts'].get('CF3')})")
e = S(F("5067", pressure_use=True, job_detail="진입 2명, 질소, 10:00 가압, 11:30 감압 완료"))["effective"][0]
expect(e["facts"].get("D7", {}).get("src") == "doc", f"D7를 서류가 답함 → facts.D7 src doc ({e['facts'].get('D7')})")
c3 = Q(S(DOCS["5067"]["fields"]), "CF3")
expect(S(DOCS["5067"]["fields"], [A(c3, "text", "DB-2")])["effective"][0]["facts"]["CF3"]["src"] == "answer", "답한 사실은 src answer")

print("#5 API 정규화가 날짜·상대 날짜를 지킴, 허가서에 없는 날짜는 확인 질문")
h = Q(S(DOCS["5325"]["fields"]), "HT1")
t6 = Q(S(DOCS["5325"]["fields"], [A(h, "gas", "6개")]), "T6")
ok_, err, _, s = norm(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "stage", "전체로는 다음 날 00:00~02:00까지 이어집니다")])
expect(not err and s["effective"][0]["windows"].get("2026-10-28") == ["00:00~02:00"],
       f"T6 stage '다음 날 00:00~02:00'(긴 답) → API 경로에서도 10-28 ({s['effective'][0]['windows']})")
ok_, err, _, s = norm(DOCS["5325"]["fields"], [A(h, "gas", "6개"), A(t6, "stage", "10/28 00:00~02:00")])
a2 = next((q for q in s["questions"] if q["item"].startswith("A2.T6")), None)
expect(a2 and "2026-10-28" in [c["id"] for c in a2["choices"]], "허가서에 없는 10/28 → 버리지 않고 확인 질문(A2)")
s = S(DOCS["5325"]["fields"], ok_ + [A(a2, "2026-10-28")])
expect(s["effective"][0]["windows"].get("2026-10-28") == ["00:00~02:00"], f"「그날 작업함」 → 10-28 구간 ({s['effective'][0]['windows']})")

print("#11 철회된 답은 제안·출처·이해 호출에 쓰지 않음")
h5 = Q(S(DOCS["5151"]["fields"]), "HT1")
ans = [OLD(A(h5, "plasma", "플라즈마 6개, 작업 위치는 4BAY 12-14 칼럼 E42P"))]
f5 = F("5151", job_detail="러그 2개 가스절단")
c6 = Q(S(f5, ans), "C6.HT1")
ok_, _, found, s = norm(f5, ans + [A(c6, "doc")])
expect(not found and not any(p.get("by") == h5["qid"] for p in s.get("proposals", [])), "철회한 HT1의 긴 답에서 L1 제안을 만들지 않음")
c = TestClient(webapp.app)
r = c.post("/api/understand", json={"fields": f5, "answers": ans + [A(c6, "doc")], "qid": h5["qid"]}).json()
expect(r.get("status") == "none", f"/api/understand: 철회한 답은 읽지 않음 ({r.get('status')})")
f1 = F("4012", from_1="09:00", to_1="12:00", from_2="13:00", to_2="16:59")
q1 = Q(S(f1), "T1")
a1 = [A(q1, "partial", "10/27 13:00~15:00")]
c6t = Q(S(f1, a1), "C6.T1")
s = S(f1, a1 + [A(c6t, "doc")])
pno = s["effective"][0]["permit_no"]
expect(addendum._tag(s, pno, ("T0", "T1", "T2"), s["effective"][0]["windows_src"]) == "서류 기재 · 예정"
       and next(r for r in s["records"] if r["qid"] == q1["qid"])["withdrawn"], "추가검토서 출처: 철회한 T1은 「반장 답변」이 아님")

print("#12 T5는 행마다, 다른 역전 행은 미확인, windows_req는 정정 뒤")
f = F("4012", from_1="22:00", to_1="02:00", from_2="20:00", to_2="01:00")
t5 = Q(S(f), "T5")
s = S(f, [A(t5, "overnight")])
w = s["effective"][0]["windows"]
expect(w.get("2026-10-27") == ["22:00~익일 02:00"] and "2026-10-28" not in w and Q(s, "T5.2") is not None,
       f"1행 「다음 날 끝남」 → 1행만, 2행은 창 없이 T5.2를 따로 물음 ({w})")
s = S(f, [A(t5, "fix", "13:00~15:00")])
expect(s["effective"][0]["windows_req"].get("2026-10-27") == ["13:00~15:00"], f"T5 정정은 windows_req에도 ({s['effective'][0]['windows_req']})")

print("#13 잔불 확인 끝은 그 날짜에만, 날짜 관계가 불분명하면 되물음")
f = F("4403", **NIGHT, from_1="22:00", to_1="02:00")        # 야간 체크: 「주간」이면 T7이 먼저 물음
t5 = Q(S(f), "T5")
t4 = Q(S(f, [A(t5, "overnight")]), "T4")
s = S(f, [A(t5, "overnight"), A(t4, "time", "03:00")])
expect(Q(s, "A5.T4") is not None and s["effective"][0]["residual"] == "", "22:00~익일 02:00 작업에 T4 '03:00' → 쓰지 않고 다음 날인지 되물음")
s = S(f, [A(t5, "overnight"), A(t4, "time", "03:00"), A(Q(s, "A5.T4"), "next")])
expect(s["effective"][0]["windows"]["2026-10-27"] == ["22:00~익일 03:00"], f"「다음 날」 → 익일 03:00 ({s['effective'][0]['windows']})")
t4q = {"qid": f"T4:{DOCS['4012']['fields']['p1.permit_no']['value'].upper()}", "item": "T4", "choices": [], "keys": []}
e = S(DOCS["4012"]["fields"], [A(t4q, "time", "10/28 18:00")])["effective"][0]
expect(e["residual_at"] == {"2026-10-28": "18:00"} and e["windows"]["2026-10-27"] == ["08:00~16:59"] and e["windows"]["2026-10-28"] == ["08:00~18:00"],
       f"여러 날 작업에 T4 '10/28 18:00' → 10/28에만 ({e['residual_at']})")
e = S(DOCS["4012"]["fields"], [A(t4q, "time", "18:00")])["effective"][0]
expect(len(e["residual_at"]) == len([d for d, w in e["windows_work"].items() if w]) > 1 and set(e["residual_at"].values()) == {"18:00"},
       f"날짜 없이 T4 '18:00' → 매 작업일(기존처럼, 마지막 날만이 아님) ({e['residual_at']})")

print("Codex 2·3단계 검토(astra) 재현 — 서류를 고친 뒤의 답, 「미정」의 범위")
from server import store  # noqa: E402
h0 = Q(S(DOCS["5151"]["fields"]), "HT1")
kept = store.clean(A(h0, "plasma", "6개"))["q"]
expect(kept.get("fp") == h0["fp"] and kept.get("fp_keys") == h0["fp_keys"], "#2 저장·복원(store.clean)해도 질문 지문(fp·fp_keys)이 남음")
s2 = S(F("5151", job_detail="러그 3개"), [A(h0, "plasma", "6개")])
expect(h0["qid"] in s2.get("stale_answers", []), f"#2 서류를 고친 뒤의 답은 summary가 알려 줌(화면이 지우고 다시 물음) ({s2.get('stale_answers')})")
h2 = Q(S(F("4403", job="E33S 균열부 보수", job_detail="")), "H2")
s3 = S(F("4403", job="E33S 균열부 보수", job_detail="CO2 용접으로 변경"), [A(h2, "text", "산소 LPG 절단")])
expect(h2 and h2["qid"] in s3.get("stale_answers", []), "#7 H2는 작업 상세도 봄: 상세를 고치면 예전 가스 답은 다시 물음")
expect(not Q(S(F("4403", job="E33S 균열부 CO2 용접", job_detail="감시자 미정")), "H2"), "#6 다른 칸의 「감시자 미정」은 작업명의 공법·가스를 지우지 않음")
expect(augment.said("가스절단 완료 여부 확인 필요 없음", r"가스\s*절단") is not None, "#6 「확인 필요 없음」은 미정이 아님")
expect(augment.said("CO2 용접 대금 분할지급", r"CO2") is True, "#6 「분할지급」의 「할지」는 미정이 아님")
expect(augment.said("가스 사용 여부 미정", r"가스") is None, "「가스 사용 여부 미정」은 여전히 말하지 않은 것")
q2 = {"qid": "X2:BS22-1>BS22-2", "permit_no": "BS22-1", "fp": "x", "fp_keys": ["p1.job"]}
expect(augment.owner({"qid": "X2:BS22-1>BS22-2", "q": q2}) == "BS22-1" and augment.owner({"qid": "X2:BS22-1>BS22-2"}) == "BS22-1",
       "#8 연결 질문(A>B)의 답은 A 허가서 것")
from server import holdq  # noqa: E402
expect({"height", "equipment", "materials", "hazards"} <= set(holdq.FP_KEYS) and "rev" not in holdq.FP_KEYS,
       "#9 보류 질문 지문: 높이·장비·물질·유해위험은 넣고 개정 번호는 뺌")


print("QA #106: 신청 시간을 다시 말하고 실제 시간을 준 답 · 허가서와 다른 블록이 든 답")
f106 = F("4403", from_1="08:00", to_1="16:59")
d106 = f106["p1.date_1"]["value"]
t1 = Q(S(f106), "T1")
said = "08:00~16:59는 하루 허가 신청 시간입니다. 실제 절단·용접은 09:00~11:30, 13:00~15:00에 하고, 나머지는 자재 준비와 대기 시간입니다."
s106 = S(f106, [A(t1, "partial", said)]) if t1 else None
expect(t1 and win(s106, d106) == ["09:00~11:30", "13:00~15:00"], f"신청 시간(08:00~16:59)을 다시 말한 구간은 실제 작업시간이 아님 ({s106 and win(s106, d106)})")
expect(t1 and win(S(f106, [A(t1, "partial", "08:00~16:59")]), d106) == ["08:00~16:59"], "신청 시간만 답하면 그대로")
pid106 = f106["p1.permit_no"]["value"]
r106 = reflect.plan(f106, [A(t1, "partial", said)]).get(pid106, {}) if t1 else {}
jd = next((x["text"] for x in r106.get("fills", []) if x["base"] == "job_detail"), "")
expect(jd.startswith("실제 작업 예정 09:00~11:30, 13:00~15:00") and said not in jd, f"반영본 상세 줄은 읽은 실제 시간만 ({jd[:60]})")
expect(any(said in t for _, t in r106.get("extra", [])), "긴 답 원문은 별지에 그대로")
l6 = {"qid": f"L6:{pid106}", "choice": "text", "value": "3BAY 12~14칼럼의 E99P 블록 내부와 출입구, 작업 지점 바로 아래 통로를 출입 통제합니다.", "q": {"permit_no": pid106}}
r6 = reflect.plan(f106, [l6]).get(pid106, {})
expect(not any(x["base"] == "location_detail" for x in r6.get("fills", [])) and any("E99P" in t and "작업 지점 바로 아래" in t for _, t in r6.get("pending", [])),
       "다른 블록이 든 통제 범위 답은 쉼표에서 잘라 뒷부분만 쓰지 않고 전체를 확인 필요로")
expect(t1 and win(S(f106, [A(t1, "partial", "08:00~16:59, 17:30~18:30")]), d106) == ["08:00~16:59", "17:30~18:30"],
       "신청 시간과 숫자만 같은 실제 시간은 지우지 않음 (Codex final #1)")
expect(augment.drop_restated({d106: [(480, 1019), (540, 660)]}, {d106: [(480, 1019)]}, "08:00~16:59는 신청 시간이고 실제는 09:00~11:00", [d106])
       == {d106: [(540, 660)]}, "「~이고」로 이어진 신청 시간 설명도 뺌")
if t1:
    r2 = reflect.plan(f106, [A(t1, "partial", "09:00~10:00, 2시~4시에 절단 작업합니다. 나머지는 자재 준비와 대기입니다.")]).get(pid106, {})
    jd2 = next((x["text"] for x in r2.get("fills", []) if x["base"] == "job_detail"), "")
    expect("09:00~10:00" in jd2 and "2시~4시" in jd2, f"오전·오후가 확인되지 않은 시간은 일부만 요약하지 않고 답 그대로 ({jd2[:50]})")
    nd = augment.summary(f106, [A(t1, "partial", "다음 날 00:00~02:00에 절단 작업합니다. 그 전에는 자재 준비와 대기입니다.")])["effective"][0]
    r3 = reflect.plan(f106, [A(t1, "partial", "다음 날 00:00~02:00에 절단 작업합니다. 그 전에는 자재 준비와 대기입니다.")]).get(pid106, {})
    jd3 = next((x["text"] for x in r3.get("fills", []) if x["base"] == "job_detail"), "")
    nxt = [d for d in nd["windows"] if d != d106]
    expect(not nxt or (nxt[0][5:7] + "/" + nxt[0][8:]) in jd3, f"다른 날의 실제 시간은 날짜를 붙여 씀 ({jd3[:50]} / {list(nd['windows'])})")

print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
