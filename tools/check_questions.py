"""Check the follow-up questions: the 작업반장 test set first, then the pair priorities
(안전관리자 view, for later) on the archived permits.

    python tools/check_questions.py

Expectations come from the design (croScan_멀티턴_추가검토_설계.md) and from what the
permits say, not from tuning: e.g. 실물 0453 has a whole-day time, a team name as the
place and an empty 호선, so T1, L1 and B4 must be asked; 합성 0611 already ticks
「고소 화기작업」, so C2 must not be asked. The last block answers questions and checks
that the answers move the pair priorities the way they should.
"""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import addendum, augment, extract, reflect  # noqa: E402
from foreman_permits import FOREMAN  # noqa: E402
from server.permit_kinds import KINDS  # noqa: E402

ok = bad = 0


def expect(cond, what):
    global ok, bad
    ok += bool(cond); bad += not cond
    print(("  PASS " if cond else "  FAIL ") + what)


def asked(s, pno, item):
    return any(q["item"] == item and q["permit_no"].endswith(pno) for q in s["questions"])


def level(s, a, b):
    for x in s["pairs"]:
        if {x["a_no"][-4:], x["b_no"][-4:]} == {a, b}:
            return x["level"]
    return None


print("작업반장 시점: 반장_테스트 10건 (파일마다 기대한 질문이 정확히 나오는지)")
# questions the research book (research412, 2026-10-31 material reinforcement) adds to the test permits, with the
# reason; tools/foreman_permits.py keeps the earlier expectation (other tools read it)
MATERIAL = {
    "0701": ["L4", "L6"],      # 3 blocks over 4 days: which on which day (실물 0400 pattern); control range not written (interview p41, extra)
    "0702": ["H2", "T4", "L6"],      # gouging written, gas not (MT10 p205); end 15:30 with 「화재감시자 1명」 but no ember-check end (N1 MT13)
    "0703": ["CF3"],           # fan·air·light power not written (N2 MT08 p247)
    "0704": ["CF3"],           # same
    "0705": ["L6"],            # control range not written (extra)
    "0706": ["L7"],            # 17-20 칼럼 with 6 lugs: the lugs' places or the access·recovery path too (N3 MT07 p274)
    "0707": ["L6"],            # control range not written (extra)
    "0708": ["LI3", "L6"],           # crane OH-21-01: its maintenance or another crane on the rail (N4-MT11 p314)
    "0709": ["LO5"],           # 「점검」 = looking for the cause: measuring with the power on? (ACC-E14 p372, 4-5 p378)
    "0710": ["LO6"],           # crane OH-21-03: another crane on the rail, another team before the restore (N5 MT11 p355)
}
DOCS = {}
for d in FOREMAN:
    name = f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf"
    DOCS[d["permit_no"][-4:]] = doc = extract.build(ROOT / "samples/반장_테스트" / name, d["kind"])
    s = augment.summary(doc["fields"], [])
    got = sorted(q["item"] for q in s["questions"])
    est = sorted(a["item"] for a in s["assumed"])
    want = sorted(d["asked"] + MATERIAL.get(d["permit_no"][-4:], []))
    good = got == want and est == sorted(d["assumed"]) and not s["pairs"]
    expect(good, f"{name}: 질문 {', '.join(got) or '-'} | 추정 {', '.join(est) or '-'}"
           + ("" if good else f"  (기대 질문 {want} 추정 {sorted(d['assumed'])})"))

print("작업반장 시점: 실물 2건 (밀폐)")
real = extract.build(ROOT / "samples/보관/위험작업신고서_양식.pdf", "confined")
s = augment.summary(real["fields"], [])
for pno, item in [("0453", "T1"), ("0453", "L1"), ("0453", "B3"), ("0453", "CF2"), ("0400", "T1"), ("0400", "B3")]:
    expect(asked(s, pno, item), f"{pno} {item} 질문")
expect(not asked(s, "0400", "L1"), "0400은 BAY·칼럼이 있어 L1 없음")
expect(not asked(s, "0400", "L7"), "0400 칼럼 28-32는 넓지만 블록 9개를 적어 L7 없음")
expect(not any(q["item"].startswith(("T3", "T4", "X", "C3", "C1", "C2", "B2", "L6", "D3", "D4", "D5")) for q in s["questions"]),
       "반장 시점: 작업쌍·당일 칸·종류만으로 묻던 질문 없음")
expect(any(x["name"] == "호선/공사" for x in s["deferred"]), "호선 빈칸은 묻지 않고 2쪽 안전팀 확인으로")


def confirmed(fields, answers):
    """design §2 (2026-10-31): what a free or long answer says for other questions is proposed (interpret) and counts
    once confirmed; this gives the answers as they are after the foreman confirmed every proposal"""
    out = list(answers)
    for a in answers:
        got, _ = augment.interpret(fields, out, a)
        out += [d for d in got if d["qid"] not in {x["qid"] for x in out}]
    return out


def run(doc, answer):
    """Answer every question in turn with answer(q) -> (choice, value); returns the answers and the asked items."""
    ans, seen = [], []
    for _ in range(40):
        s = augment.summary(doc["fields"], ans)
        if not s["questions"]:
            return ans, seen, s
        q = s["questions"][0]
        assert q["qid"] not in seen, f"재질문: {q['qid']}"
        seen.append(q["qid"])
        c, v = answer(q)
        ans.append({"qid": q["qid"], "choice": c, "value": v, "q": q})
    raise AssertionError("40번 넘게 질문함")


print("작업반장 대화: 끝나는지, 다시 묻지 않는지, 답이 다른 질문을 닫는지")
for no, doc in DOCS.items():
    ans, seen, s = run(doc, lambda q: ("unknown", ""))
    expect(not s["questions"] and s["closing"] == "추가로 말씀하실 것이 있나요? 없으면 「없음 · 검토 마치기」를 눌러 주세요.",
           f"{no}: 모두 「모름」 → {len(seen)}번 묻고 마무리 문구, 재질문 없음")
ans, seen, s = run(DOCS["0706"], lambda q: ("gas", "") if q["item"] == "HT1" else ("unknown", ""))
t6 = next((q for q in augment.summary(DOCS["0706"]["fields"], ans[:1])["questions"] if q["item"] == "T6"), None)
expect(t6 and "340~680분" in t6["text"] and "짧습니다" in t6["text"],
       "0706 러그 6개 가스절단이라 답하면 → 2시간이 참고 340~680분보다 짧아 T6 (전체인지 단계인지)")
expect("T6" in [x.split(":")[0] for x in seen], "0706 T6은 HT1 답 뒤에 한 번 나옴")
free = [{"qid": "FREE:1", "choice": "text", "value": "OH-21-01로 3BAY 12칼럼에서 1BAY 반출장으로 옮깁니다. 블록 안 작업 없음, 반전 없음"}]
s = augment.summary(DOCS["0707"]["fields"], free)
left = sorted(q["item"] for q in s["questions"])
expect({"LI1", "LI2", "L5"} <= set(left), f"0707 자유 답변은 확인 전에는 크레인·경로·블록 안 작업 질문을 닫지 않음 (design §2) → {left}")
expect(any("OH-21-01" in x for x in s["free_found"]["FREE:1"]), f"자유 답변에서 뽑은 값: {s['free_found']['FREE:1']}")
qs = {q["item"]: q for q in augment.summary(DOCS["0707"]["fields"], [])["questions"]}
a = [{"qid": qs["T1"]["qid"], "choice": "partial", "value": "10/27 10:30~11:30", "q": qs["T1"]}]
s = augment.summary(DOCS["0707"]["fields"], a)
expect(not any(q["item"] == "T6" for q in s["questions"]), "인양 T1에 '움직이는 시간'을 받으면 전체 인양 참고와 다시 비교(T6)하지 않음")
a += [{"qid": qs["LI2"]["qid"], "choice": "none", "value": "", "q": qs["LI2"]},
      {"qid": "FREE:1", "choice": "text", "value": "블록 안에 2명 취부 작업 있다가 10시에 나옵니다"}]
s = augment.summary(DOCS["0707"]["fields"], a)
expect(any(q["item"] == "C5.LI2" for q in s["questions"]), "앞에서 블록 안 작업 '없음' → 자유 답변에 '블록 안 2명 작업' → 상충 질문 C5 한 번")
s = augment.summary(DOCS["0705"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "다른 작업 없으면 바로 시작합니다"}])
expect(any(q["item"] == "B3" for q in s["questions"]) and not s["free_found"]["FREE:1"],
       "'다른 작업 없으면'은 조건문: 병행작업 없음으로 확정하지 않고 B3 유지")
expect(augment.said("가스는 안 쓰고 용접만 합니다", r"가스") is False and augment.said("가스는 안 쓰고 용접만 합니다", r"용접") is True,
       "부정은 구절 단위: '가스는 안 쓰고 용접' → 가스 아님, 용접 맞음")
# Codex 3차 검증에서 재현된 5건
expect(augment.said("안 쓰는 가스입니다", r"가스") is False, "앞에 붙은 부정: '안 쓰는 가스' → 가스 아님")
expect(augment.count_in("러그 6개 있으면 높이 4.8m 에서 절단") is None and augment.height_in("러그 6개 있으면 높이 4.8m 에서 절단") is None
       and augment.count_in("러그 6개 아님, 2개") == 2, "조건·부정 속 숫자는 확정하지 않음: '6개 있으면' → 없음, '6개 아님, 2개' → 2")
f = copy.deepcopy(DOCS["0702"]["fields"])
f["p1.job"]["value"], f["p1.job_detail"]["value"] = "E42P 블록 국부 보수", "가스절단은 안 함"
f["p1.gouging"]["value"] = ""
expect(any(q["item"] == "H2" for q in augment.summary(f, [])["questions"]), "쓰지 않는 공법만 적으면 실제 공법은 미상 → H2 유지")
fr = [{"qid": "FREE:1", "choice": "text", "value": "실제 작업 시간은 09:00~13:00 입니다"}]
s = augment.summary(DOCS["0702"]["fields"], fr)
expect(s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]} and any(x.startswith("시간") for x in s["free_found"]["FREE:1"]),
       f"자유 답변의 작업 시간은 읽되 확인 전에는 쓰지 않음 ({s['effective'][0]['windows']})")

s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "옆 BAY 도장은 14~16시예요"}])
expect(s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]}, "다른 작업의 시간은 이 작업 시간으로 쓰지 않음")
for t in ("옆 BAY 도장 작업 시간은 14~16시예요", "실제 작업 시간은 09:00~13:00이 아닙니다"):
    s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": t}])
    expect(s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]} and not any(x.startswith("시간") for x in s["free_found"]["FREE:1"]),
           f"Codex 4차 재현 '{t}' → 이 작업 시간으로 쓰지 않음")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "옆 BAY 도장은 오후예요"}])
expect(any(q["item"] == "C5.concurrent" for q in s["questions"]), "병행여부 N인데 자유 답변에 '옆 BAY 도장' → 같은 시간·장소인지 한 번 확인")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "도장 작업 시간은 14~16시예요"}])
expect(any(q["item"] == "C5.concurrent" for q in s["questions"]) and s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]},
       "Codex 5차 재현 '도장 작업 시간은 14~16시' (화기) → 시간은 그대로, 병행 확인 C5 한 번")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "재용접 뒤 검사까지 제가 합니다"}])
expect(not any(q["item"] == "C5.concurrent" for q in s["questions"]), "화기 작업의 재용접·검사는 다른 작업이 아님 → C5 없음")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "도장 작업은 오늘 진행하지 않습니다"}])
expect(not any(q["item"] == "C5.concurrent" for q in s["questions"]), "Codex 6차 재현 '도장 작업은 오늘 진행하지 않습니다' → 부정이라 C5 없음")
for t, want in (("도장 작업 시간은 14~16시이며 가스 사용은 없음", True), ("도장은 하지 않고 용접만 합니다", False)):
    s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": t}])
    expect(any(q["item"] == "C5.concurrent" for q in s["questions"]) == want, f"부정 범위는 연결어까지: '{t}' → C5 {'있음' if want else '없음'}")
f = copy.deepcopy(DOCS["0710"]["fields"])
f["p1.job_detail"]["value"] = "13:00 차단, 14:30 복구, 14:45 시험운전"
expect(not any(q["item"] == "LO3" for q in augment.summary(f, [])["questions"]), "'14:30 복구'처럼 시각이 앞에 와도 LO3 다시 묻지 않음")
# 코드리뷰(high, 2026-10-27): 현장 말투·입력에서 터질 수 있던 것
tr = lambda t: [f"{augment.hm(a)}~{augment.hm(b)}" for a, b in augment.time_ranges(t)]
for t, want in (("오후 2시~4시", ["14:00~16:00"]), ("2시~4시", []), ("9시~11시", ["09:00~11:00"]), ("6시~8시", []), ("9시 30분~11시", ["09:30~11:00"]),
                ("9시 반부터 11시까지", ["09:30~11:00"]), ("09:00～11:00", ["09:00~11:00"]), ("13:00∼15:30", ["13:00~15:30"]),
                ("11시~1시", ["11:00~13:00"]), ("새벽 2시~4시", ["02:00~04:00"]), ("06:00~08:00", ["06:00~08:00"]),
                ("3BAY 12-14 칼럼에서 09~11시", ["09:00~11:00"]), ("10-27 09~11", ["09:00~11:00"]), ("러그 2-3개", []),
                ("E41P-12~14", [])):
    expect(tr(t) == want, f"시간 읽기 '{t}' → {tr(t)} (기대 {want})")
expect(augment._parse_windows("10/27 09~11", ["10/27", "2026.10.27"]) == {}, "날짜 칸이 '10/27'처럼 ISO가 아니어도 오류 없이 넘어감")
f = copy.deepcopy(DOCS["0702"]["fields"])
for k in [k for k in f if k.startswith("p1.date_")]:
    f[k]["value"] = "10/27" if f[k]["value"] else ""
qs = {q["item"]: q for q in augment.summary(f, [])["questions"]}
s = augment.summary(f, [{"qid": "FREE:1", "choice": "text", "value": "실제 작업 시간은 10/27 09~11시"}])
expect(isinstance(s["questions"], list), "날짜가 '10/27'인 허가서에 시간 답을 해도 /api/augment가 죽지 않음")
expect(augment.ids("CO2 용접, AH36 판재 교체, N2 퍼지, E41P 블록, OH-21-03") == {"E41P", "OH-21-03"}, "가스(CO2·N2)·강재(AH36)는 블록 번호가 아님")
f = copy.deepcopy(DOCS["0702"]["fields"])
f["p1.job"]["value"], f["p1.job_detail"]["value"], f["p1.location_detail"]["value"], f["p1.hull_no"]["value"] = "용접부 국부 보수", "CO2 용접", "", ""
expect(any(q["item"] == "D1" for q in augment.summary(f, [])["questions"]), "작업내용에 'CO2'만 있고 블록 번호가 없으면 D1 (어느 블록?)")
expect(augment.height_in("하부 반경 5m 통행 통제") is None and augment.height_in("블록 상부 4.8m, 하부 반경 5m 통제") == 4.8,
       "'반경 5m'는 거리라 높이가 아님")
s = augment.summary(DOCS["0705"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "옆 5BAY에서 E99P 블록 도장 작업 있음"}])
e = s["effective"][0]
expect("5" not in e["place"]["bays"] and "E99P" not in e["targets"], f"다른 팀 작업의 장소·블록은 이 허가서 값이 아님 ({e['place']['bays']}, {e['targets']})")
expect(not any(x.startswith(("위치", "번호")) for x in s["free_found"]["FREE:1"]), f"반영 안내에도 다른 팀 장소를 넣지 않음 ({s['free_found']['FREE:1']})")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "실제 작업은 오후 1시부터 2시 반까지"}])
expect(any("13:00~14:30" in x for x in s["free_found"]["FREE:1"]) and s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]},
       f"'오후 1시부터 2시 반까지' → 13:00~14:30으로 읽되 확인 전에는 쓰지 않음 ({s['free_found']['FREE:1']})")
# 애매하면 넘어가지 않고 다시 묻기 (사용자 요청 2026-10-27: "2시면 2시인지 14시인지 모르니까")
expect(augment.time_ranges("2시~4시", "pm") == [(840, 960)] and augment.time_ranges("2시~4시", "am") == [(120, 240)],
       "'2시~4시'에 오후/새벽 답을 받으면 그대로 14:00~16:00 / 02:00~04:00")
qs = {q["item"]: q for q in augment.summary(DOCS["0705"]["fields"], [])["questions"]}
a = [{"qid": qs["T1"]["qid"], "choice": "partial", "value": "2시~4시", "q": qs["T1"]}]
s = augment.summary(DOCS["0705"]["fields"], a)
q1 = next((q for q in s["questions"] if q["item"] == "A1.T1"), None)
expect(q1 is not None and s["questions"][0]["item"] == "A1.T1" and s["effective"][0]["windows_src"] == "원본",
       f"T1에 '2시~4시' → 시간은 아직 쓰지 않고 바로 오전·오후를 다시 물음 ({q1 and q1['text']})")
expect(q1 and [c["label"] for c in q1["choices"]] == ["오후 14:00~16:00", "새벽·오전 02:00~04:00", "모름"], f"보기: {q1 and [c['label'] for c in q1['choices']]}")
s = augment.summary(DOCS["0705"]["fields"], a + [{"qid": q1["qid"], "choice": "pm", "value": "", "q": q1}])
expect(set(map(tuple, s["effective"][0]["windows"].values())) == {("14:00~16:00",)} and not any(q["item"].startswith("A1") for q in s["questions"]),
       f"'오후'라고 답하면 14:00~16:00으로 반영, 다시 묻지 않음 ({s['effective'][0]['windows']})")
a = [{"qid": qs["T1"]["qid"], "choice": "partial", "value": "내일 9시~11시", "q": qs["T1"]}]
s = augment.summary(DOCS["0705"]["fields"], a)
q2 = next((q for q in s["questions"] if q["item"] == "A2.T1"), None)
expect(q2 is not None and [c["id"] for c in q2["choices"]][:3] == ["2026-10-27", "2026-10-28", "2026-10-29"],
       "여러 날 허가서에 '내일 9시~11시' → 며칠인지 날짜 보기로 다시 물음")
s = augment.summary(DOCS["0705"]["fields"], a + [{"qid": q2["qid"], "choice": "2026-10-28", "value": "", "q": q2}])
expect(s["effective"][0]["windows"] == {"2026-10-28": ["09:00~11:00"]}, f"'10월 28일'이라고 답하면 그날만 09:00~11:00 ({s['effective'][0]['windows']})")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "실제 작업은 2시~4시예요"}])
expect(any(q["item"] == "A1.F1" for q in s["questions"]) and s["effective"][0]["windows"] == {"2026-10-27": ["13:00~15:30"]}
       and any("다시 여쭙니다" in x for x in s["free_found"]["FREE:1"]), "자유 답변의 '2시~4시'도 반영하지 않고 오전·오후를 물음")
for item, choice, v, bad in (("T1", "partial", "오후에 해요", True), ("T1", "partial", "오후 1시~3시", False), ("L1", "place", "저쪽 블록 옆", True),
                             ("L1", "place", "3BAY 12-14 칼럼", False), ("HT1", "gas", "2~3개", True), ("HT1", "gas", "6개", False),
                             ("HT1", "gas", "아마 6개", True), ("D1", "text", "이중저 배관", True), ("D1", "text", "E41P 블록", False),
                             ("LI1", "text", "천장크레인 한 대", True), ("LI1", "text", "OH-21-01 한 대", False)):
    err = augment.check_value({}, {"qid": f"{item}:X", "choice": choice, "value": v})
    expect(bool(err) == bad, f"{item} '{v}' → {'다시 물음: ' + err if err else '받음'}")
expect(augment.said("블록 안 작업은 아마 없을 거예요", augment.RX["li_inside"]) is None and augment.count_in("러그는 아마 6개") is None,
       "'아마 없을 거예요', '아마 6개'는 확정하지 않음")
q7 = {q["item"]: q for q in augment.summary(DOCS["0707"]["fields"], [])["questions"]}
a = [{"qid": q7["LI2"]["qid"], "choice": "none", "value": "", "q": q7["LI2"]},
     {"qid": "FREE:1", "choice": "text", "value": "블록 안에 사람이 있을걸요"}]
s = augment.summary(DOCS["0707"]["fields"], a)
expect(any(q["item"] == "C5.LI2" for q in s["questions"]), "앞에서 '없음'인데 '블록 안에 사람이 있을걸요' → 확정은 안 해도 상충이라 한 번 확인")
# 알아듣지 못한 말도 넘어가지 않기 (사용자 요청: "AI가 딱 봤을 때 이해 안가는거 그냥 막 넘어가지 마라")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "그건 좀 그래요"}])
expect(s["questions"] and s["questions"][0]["item"] == "U1.F1", f"알아듣지 못한 자유 답변 → 무엇에 대한 말인지 바로 물음 ({[q['item'] for q in s['questions']]})")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "실제로는 오후에 해요"}])
q3 = next((q for q in s["questions"] if q["item"] == "A3.F1"), None)
expect(q3 is not None, "자유 답변의 '오후에'(숫자 없는 시간) → 몇 시부터 몇 시까지인지 물음")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "실제로는 오후에 해요"},
                                             {"qid": q3["qid"], "choice": "time", "value": "13:00~14:00", "q": q3}])
expect(s["effective"][0]["windows"] == {"2026-10-27": ["13:00~14:00"]}, f"그 답 13:00~14:00을 작업 시간으로 반영 ({s['effective'][0]['windows']})")
for item, choice, v, bad in (("B3", "yes", "상황 봐서 해요", True), ("HT2", "text", "ㅇㅇ", True), ("HT2", "text", "알아서 내릴게요", True),
                             ("HT2", "text", "로프로 내려 하부 적치함", False), ("U1.F1", "time", "오후", True), ("U1.F1", "note", "", False)):
    err = augment.check_value({}, {"qid": f"{item}:X", "choice": choice, "value": v})
    expect(bool(err) == bad, f"{item} '{v}' → {'다시 물음: ' + err if err else '받음'}")
# Codex 9차 검증 재현
qs = {q["item"]: q for q in augment.summary(DOCS["0705"]["fields"], [])["questions"]}
a = [{"qid": qs["T1"]["qid"], "choice": "partial", "value": "2시~4시, 5시~6시", "q": qs["T1"]}]
s = augment.summary(DOCS["0705"]["fields"], a)
two = [q for q in s["questions"] if q["item"].startswith("A1.T1")]
expect([q["item"] for q in two] == ["A1.T1", "A1.T1.2"], f"애매한 시간이 둘이면 따로따로 물음 ({[q['item'] for q in two]})")
a += [{"qid": two[0]["qid"], "choice": "pm", "value": "", "q": two[0]}, {"qid": two[1]["qid"], "choice": "am", "value": "", "q": two[1]}]
s = augment.summary(DOCS["0705"]["fields"], a)
expect(s["effective"][0]["windows"]["2026-10-27"] == ["05:00~06:00", "14:00~16:00"], f"각자 답한 대로 반영 ({s['effective'][0]['windows']['2026-10-27']})")
expect(augment.count_in("러그 2~3개") is None and augment.height_in("높이 3~4m") is None and augment.count_in("3개입니다") == 3,
       "'2~3개', '3~4m'는 큰 쪽으로 확정하지 않음, '3개입니다'는 3")
a = [{"qid": qs["HT1"]["qid"], "choice": "unknown", "value": "2~3개", "q": qs["HT1"]}]
expect(augment.summary(DOCS["0705"]["fields"], a)["effective"][0]["count"] is None, "「모름」으로 넘긴 '2~3개'는 개수로 쓰지 않음")
a = [{"qid": qs["HT2"]["qid"], "choice": "text", "value": "로프로 내려 하부 적치함, 같은 시간 같은 장소 다른 작업 없음", "q": qs["HT2"]}]
expect(any(q["item"] == "B3" for q in augment.summary(DOCS["0705"]["fields"], a)["questions"]),
       "다른 답의 '다른 작업 없음'은 확인 전이라 병행여부(B3)를 그대로 물음 (design §2)")
s = augment.summary(DOCS["0705"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "블록 옆에서 3BAY E41P 러그 6개 절단"}])
e = s["effective"][0]
expect("E41P" not in e["targets"] and e["count"] != 6 and not any(q["item"].startswith("C5") for q in s["questions"]),
       f"'블록 옆에서' 자유 답변: 확인 전에는 블록·개수로 쓰지 않고, 다른 팀 작업으로 보지도 않음 ({e['targets']}, {e['count']})")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "오전 작업은 안 합니다"}])
expect(not any(q["item"].startswith("A3") for q in s["questions"]), "'오전 작업은 안 합니다'는 시간을 묻지 않음")
expect(augment.check_value({}, {"qid": "FREE:1", "choice": "text", "value": "블록 안에 사람이 아마 있을 거예요"}) == "",
       "확실하지 않은 자유 답변도 거절하지 않고 그대로 남김")
# Codex 10차 재검증 재현
f1 = [{"qid": "FREE:1", "choice": "text", "value": "실제 작업 시간은 2시~4시; 실제 작업 시간은 5시~6시"}]
s = augment.summary(DOCS["0702"]["fields"], f1)
two = [q for q in s["questions"] if q["item"].startswith("A1.F1")]
expect([q["item"] for q in two] == ["A1.F1", "A1.F1.2"], f"자유 답변의 두 문장에 나뉜 애매한 시간도 하나씩 물음 ({[q['item'] for q in two]})")
s = augment.summary(DOCS["0702"]["fields"], f1 + [{"qid": two[0]["qid"], "choice": "pm", "value": "", "q": two[0]},
                                                  {"qid": two[1]["qid"], "choice": "am", "value": "", "q": two[1]}])
expect(s["effective"][0]["windows"] == {"2026-10-27": ["05:00~06:00", "14:00~16:00"]}, f"각자 답한 대로 ({s['effective'][0]['windows']})")
expect(all(augment.count_in(t) is None for t in ("러그 2개~3개", "러그 3개 또는 4개", "3개나 4개")) and augment.height_in("높이 3m~4m") is None,
       "'2개~3개', '3개 또는 4개', '3m~4m'도 하나로 확정하지 않음")
qs5 = {q["item"]: q for q in augment.summary(DOCS["0705"]["fields"], [])["questions"]}
a = [{"qid": qs5["L3"]["qid"], "choice": "unknown", "value": "아마 5BAY 상부 4.8m일 것 같아요", "q": qs5["L3"]}]
e = augment.summary(DOCS["0705"]["fields"], a)["effective"][0]
expect("5" not in e["place"]["bays"] and e["height"] is None, f"「모름」으로 남긴 위치·높이는 값에 넣지 않음 ({e['place']['bays']}, {e['height']})")
for t in ("오전 작업은 안 합니다", "오후에는 안 했습니다", "저녁엔 안 할 겁니다"):
    s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": t}])
    expect(not any(q["item"].startswith(("A3", "U1")) for q in s["questions"]), f"'{t}' → 알아들은 말: 다시 묻지 않음")
a = [{"qid": qs5["HT2"]["qid"], "choice": "text", "value": "로프로 내려 하부 적치함, 다른 작업 여부는 확인 중입니다", "q": qs5["HT2"]}]
expect(any(q["item"] == "B3" for q in augment.summary(DOCS["0705"]["fields"], a)["questions"]),
       "'다른 작업 여부는 확인 중'은 확인된 게 아니라 병행여부(B3)를 그대로 물음")
# Codex 11차 재검증 재현
for v in ("3BAY에서 6개 가스절단", "3BAY 12-14칼럼 러그 6개 가스절단", "OH-21-03으로 러그 6개 회수"):
    err = augment.check_value({}, {"qid": "HT1:X", "choice": "gas", "value": v})
    expect(not err and augment.count_in(v) == 6, f"HT1 '{v}' → 받고 6개로 읽음 ({err or augment.count_in(v)})")
expect(not augment.check_value({}, {"qid": "CF1:X", "choice": "inspect", "value": "배관 내부 2곳에 전신 진입해 용접 상태 확인 중입니다"}),
       "'용접 상태 확인 중'은 하는 일이라 확실하지 않은 말이 아님")
s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": "오전에는 가스 안 쓰고 용접합니다"}])
expect(not any("일하지 않는 시간" in x for x in s["free_found"]["FREE:1"]), f"'오전에는 가스 안 쓰고 용접합니다'는 일하지 않는 시간이 아님 ({s['free_found']['FREE:1']})")
# Codex 12차(마지막) 재검증 재현
expect(augment.check_value({}, {"qid": "HT1:X", "choice": "gas", "value": "러그가 6개인지 담당자에게 확인 중입니다"}) != "",
       "'6개인지 담당자에게 확인 중'은 아직 모르는 값: 다시 받음")
a = [{"qid": qs5["HT2"]["qid"], "choice": "text", "value": "로프로 내려 하부 적치함, 다른 작업 없는지 담당자에게 확인 중입니다", "q": qs5["HT2"]}]
expect(any(q["item"] == "B3" for q in augment.summary(DOCS["0705"]["fields"], a)["questions"]), "'없는지 담당자에게 확인 중' → B3 그대로 물음")
for t in ("오전에는 작업하지 않습니다", "오전 작업은 하지 않습니다", "오전에는 작업이 없습니다"):
    s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": t}])
    expect(not any(q["item"].startswith(("A3", "U1")) for q in s["questions"]), f"'{t}' → 알아들은 말: 다시 묻지 않음")
for t in ("오전에는 가스 안 쓰고 용접합니다", "오후 작업은 문제없습니다"):
    s = augment.summary(DOCS["0702"]["fields"], [{"qid": "FREE:1", "choice": "text", "value": t}])
    expect(not any("일하지 않는 시간" in x for x in s["free_found"]["FREE:1"]), f"'{t}'는 일하지 않는 시간이 아님")
# 되묻기는 끝이 있다: 일부러 애매한 답만 계속해도 대화가 끝나는지 (사용자 요청: "무한루프 안 걸리게")
BAD = ["2시~4시", "ㅇㅇ", "상황 봐서", "아마 그럴걸요", "내일 3시~5시", "그쪽"]


def stubborn(doc, frees=6):
    """A 작업반장 who answers everything vaguely, as the web page does: a value croScan cannot read is typed once more,
    then kept as 「모름」; and who keeps adding unclear free answers. Returns (answers, steps)."""
    ans, steps, k = [], 0, 0
    for f in range(frees + 1):
        while True:
            steps += 1
            assert steps < 300, "끝나지 않음"
            s = augment.summary(doc["fields"], ans)
            if not s["questions"]:
                break
            q = s["questions"][0]
            c = next((x for x in q["choices"] if x.get("ask")), None) or next(x for x in q["choices"] if x["id"] != "unknown")
            v = BAD[k % len(BAD)] if c.get("ask") else ""
            k += 1
            a = {"qid": q["qid"], "choice": c["id"], "value": v, "q": q}
            if augment.check_value(doc["fields"], a):
                a = dict(a, value=BAD[k % len(BAD)]); k += 1
                if augment.check_value(doc["fields"], a):
                    a = dict(a, choice="unknown")
            ans.append(a)
        if f < frees:
            ans.append({"qid": f"FREE:{f + 1}", "choice": "text", "value": BAD[f % len(BAD)]})
    return ans, steps


for no, doc in DOCS.items():
    ans, steps = stubborn(doc)
    backs = [a["qid"] for a in ans if a["qid"].split(".")[0] in ("A1", "A2", "A3", "U1")]
    per = {}
    for q in backs:
        per[q.split(":")[1]] = per.get(q.split(":")[1], 0) + 1
    expect(max(per.values(), default=0) <= augment.ASK_BACK and len({a["qid"] for a in ans}) == len(ans),
           f"{no}: 애매한 답만 계속해도 {steps}단계에 끝남, 되묻기 {len(backs)}번(한도 {augment.ASK_BACK}), 같은 질문 반복 없음")

print("작업반장 시점: 시간·공간 적합도, 시각 역전, 당일 칸")
f = copy.deepcopy(DOCS["0706"]["fields"])
f["p1.location"]["value"] = "대조립21공장 3BAY 10-16 칼럼"
f["p1.job_detail"]["value"] = "사용 완료 러그 1개 가스절단, 로프로 내려 하부 적치"
s = augment.summary(f, [])
expect(any(q["item"] == "L7" for q in s["questions"]), "러그 1개인데 칼럼 10-16(6구간) → L7 (작업 위치인지 경로 포함인지)")
f["p1.job_detail"]["value"] = "사용 완료 러그 6개 가스절단, 로프로 내려 하부 적치"
s = augment.summary(f, [])
# changed 2026-10-31 (research412 N3 MT07 p274): several lugs may explain a wide range, or it takes in the access and
# recovery path — asked once in the book's words, not assumed
l7 = next((q for q in s["questions"] if q["item"] == "L7"), None)
expect(l7 and "여러 러그의 위치" in l7["text"], "러그 6개 + 칼럼 10-16 → L7 (여러 러그 위치인지, 접근·회수 경로 포함인지)")
e = next(x for x in s["effective"])
expect(e["fit"]["state"] == "short" and e["fit"]["model"].startswith("R-G"), f"러그 6개 가스절단 120분 → 참고 {e['fit'].get('lo')}~{e['fit'].get('hi')}분과 비교")
f = copy.deepcopy(DOCS["0702"]["fields"])
f["p1.to_1"]["value"] = "01:30"
s = augment.summary(f, [])
q5 = next((q for q in s["questions"] if q["item"] == "T5"), None)
expect(q5 is not None, "종료가 시작보다 빠르면 T5 (다음 날인지 잘못 적었는지)")
s = augment.summary(f, [{"qid": q5["qid"], "choice": "overnight", "value": "", "q": q5}])
w = s["effective"][0]["windows"]
expect(any("익일" in x for ws in w.values() for x in ws), f"T5 '다음 날 끝남' → {w}")
s = augment.summary(DOCS["0707"]["fields"], [])
expect(not any(q["item"].startswith("B") and "swl" in q["item"] for q in s["questions"]), "정격하중 빈칸(추가정보, 당일 기입)은 묻지 않음")
expect(augment.parse_place("F01 / 2B / 08~12축")["bays"] == {"2"} and augment.parse_place("F01 / 2B / 08~12축")["colrange"] == (8, 12)
       and augment.CRANE.findall("CR-2B 사용") == ["CR-2B"], "대조립 공장 모델 표기 '2B / 08~12축', 'CR-2B'를 읽음")

print("안전관리자 시점 (나중): 작업쌍 우선순위")
expect(level(augment.summary(real["fields"], [], True), "0453", "0400") == 3, "0453×0400: 장소 L0이라 3순위(정보 부족)")

syn = extract.build(ROOT / "samples/보관/합성_대조립_허가신청_5건.pdf", ["hot", "confined", "height", "lifting", "loto"])
s = augment.summary(syn["fields"], [], True)
for a, b in [("0611", "0612"), ("0611", "0614"), ("0612", "0614"), ("0614", "0615")]:
    expect(level(s, a, b) == 1, f"{a}×{b} 1순위 (같은 대상·설비, 조사자료 P01·P05·P02·P04)")
expect(level(s, "0613", "0614") == 2, "0613×0614 2순위 (같은 3BAY, 인양 경로: P03)")
x = next(x for x in s["pairs"] if {x["a_no"][-4:], x["b_no"][-4:]} == {"0611", "0613"})
expect(x["level"] == 2 and x["gap"] == 1, f"0611(12-16 칼럼)×0613(17-20 칼럼): 칼럼 1칸 차이라 2순위 ({x['why']})")
far = copy.deepcopy(syn["fields"])
far["p3.location"]["value"] = "대조립21공장 3BAY 40-44 칼럼"
x = next(x for x in augment.summary(far, [], True)["pairs"] if {x["a_no"][-4:], x["b_no"][-4:]} == {"0611", "0613"})
expect(x["level"] == 9, f"0613을 40-44 칼럼으로 옮기면 같은 BAY라도 기록만 ({x['why']})")
expect(asked(s, "0615", "C3"), "0615 병행여부 N인데 겹침 → C3")
expect(asked(s, "0613", "B3") and asked(s, "0614", "B3"), "0613·0614 병행여부 빈칸 → B3")
expect(not asked(s, "0611", "C2"), "0611은 고소 화기작업 체크돼 있어 C2 없음")
expect(not asked(s, "0614", "X1"), "0614는 크레인 번호(OH-21-03)가 이미 있어 X1 없음")
expect(not asked(s, "0614", "L5"), "0614는 경로(→, 경유)가 있어 L5 없음")
expect(asked(s, "0615", "X5"), "0615 정전 × 0612 밀폐 → 공유전원 X5")
expect(all(not q["item"].startswith(("B1.", "B2.")) for q in s["questions"]), "합성 5건은 필수 빈칸 없음")

print("답변이 판정을 바꾸는지")
qs = {q["qid"]: q for q in augment.summary(real["fields"], [], True)["questions"]}
pid = next(k for k in qs if k.startswith("L1:")).split(":")[1]
ans = [{"qid": f"L1:{pid}", "choice": "place", "value": "UNIT2공장 1BAY 5-7 칼럼", "q": qs[f"L1:{pid}"]}]
s2 = augment.summary(real["fields"], ans, True)
expect(level(s2, "0453", "0400") == 9, "0453 위치를 다른 공장으로 답하면 0453×0400은 기록만(겹치지 않음 근거)")
expect(not any(q["item"] == "T4" for q in s2["questions"]), "겹침이 풀리면 잔류위험 질문(T4)도 사라짐")
ans.append({"qid": f"T1:{pid}", "choice": "partial", "value": "09:00~11:00, 14:00~16:00", "q": qs[f"T1:{pid}"]})
s3 = augment.summary(real["fields"], ans, True)
e = next(x for x in s3["effective"] if x["permit_no"] == pid)
expect(e["windows"]["2026-10-12"] == ["09:00~11:00", "14:00~16:00"] and e["windows_src"] == "신청자 답변", "T1 답 → 위험시간대 09~11, 14~16")
sq = {q["qid"]: q for q in augment.summary(syn["fields"], [], True)["questions"]}
x5 = next(k for k in sq if k.startswith("X5:"))
s4 = augment.summary(syn["fields"], [{"qid": x5, "choice": "yes", "value": "", "q": sq[x5]}], True)
expect(level(s4, "0612", "0615") == 1, "0615 '차단 전원에 환기팬 물림=예' → 0612×0615 1순위(공유전원)")
s3["reflect"] = reflect.plan(real["fields"], ans)
sheets = addendum.build(s3, real["fields"])
expect(len(sheets) == 2 and "UNIT2공장 1BAY 5-7 칼럼" in sheets[0][1] and "업로드한 원본 파일은 바꾸지 않았습니다" in sheets[0][1], "추가검토서: 허가서마다 1장, 답변 반영")
print("카탈로그·점수·병합·원자 슬롯·서류와 답의 상충 (design §3.1·§3.2·§3.5)")
from server import need_catalog as N  # noqa: E402
rows = N.catalog()
expect(len(rows) >= 50 and all({"slot_id", "type", "trigger", "met", "required", "W", "burden", "owner", "fallback"} <= set(r) for r in rows),
       f"카탈로그 행 {len(rows)}개: slot_id·타입·트리거·충족·필수·W·부담·담당·대체 문구")
# 2026-10-31: + 종료의 뜻·중간 복구 (research412 N5 MT12·MT05 p355), 다른 팀 잠금 (노션추가본 4.12 p28), all optional
expect([a["label"] for a in N.row("LO3")["atoms"]][:4] == ["차단 시각", "복구 시각", "시험운전", "함께 멈추는 설비"]
       and len(N.row("LO3")["atoms"]) == 7 and N.row("LO3")["met"] == "차단 시각 + 복구 시각",
       "LO3 원자 슬롯 7개(차단·복구가 충족 조건; + 종료의 뜻·중간 복구·다른 팀 잠금)")
expect(N.atoms("LO3", "text", "13:00 차단, 14:30 복구")["required_missing"] == [] and N.atoms("LO3", "text", "오후에 함")["required_missing"] == ["차단 시각", "복구 시각"],
       "원자 분해: 차단·복구 시각을 각각 찾음")
expect(augment.check_value({}, {"qid": "LO3:P", "choice": "text", "value": "오후에 정비함"}) and not augment.check_value({}, {"qid": "LO3:P", "choice": "text", "value": "13:00 차단, 14:30 복구"}),
       "LO3 답에 차단·복구가 없으면 한 번 다시 묻기(그래도 없으면 안전팀 확인)")
mk = lambda item, **k: {"qid": f"{item}:P", "item": item, "choices": [{"id": "text", "ask": "x"}], "prio": (5, 0), "page": 1, "permit_no": "P", "tier": "core", **k}
expect(N.score(mk("HT1", m=0.5)) < N.score(mk("HT1")), "S=W·M·A−B: 일부만 빠지면(M 0.5) 점수가 낮음")
expect(N.score(mk("B3")) < N.score(mk("LI1")), "S=W·M·A−B: 들은 정보만 답할 수 있는 질문(A 0.5)은 낮음")
o = N.order([mk("HT2"), mk("T1"), mk("HT1"), mk("W1")])
expect([x["item"] for x in o] == ["T1", "HT1", "HT2", "W1"] and o[1].get("with") == "HT2:P" and o[2].get("with_of") == "HT1:P",
       "관련 질문 2개(러그 절단·회수)를 한 묶음으로, 필수 아닌 W1은 뒤로")
o = N.order([mk("HT1"), mk("AI1", ai_kind="dependency"), mk("HT2")])
expect(not o[1].get("ai_kind") and o[-1].get("ai_kind") and not any(x.get("with") == "AI1:P" for x in o), "AI 질문은 묶지 않고 규칙 질문 뒤")
tdoc = next((d for d in DOCS.values() if any(q["item"] == "T1" for q in augment.summary(d["fields"], [])["questions"])), None)
if tdoc:
    s0 = augment.summary(tdoc["fields"], [])
    t1 = next(q for q in s0["questions"] if q["item"] == "T1")
    far = [{"qid": t1["qid"], "choice": "partial", "value": "20:00~22:00", "q": t1}]
    near_ = [{"qid": t1["qid"], "choice": "partial", "value": "09:00~11:00", "q": t1}]
    c6 = [q for q in augment.summary(tdoc["fields"], far)["questions"] if q["item"] == "C6.T1"]
    expect(c6 and "서류에는" in c6[0]["text"] and {c["id"] for c in c6[0]["choices"]} == {"answer", "doc", "unknown"},
           "답 시간(20~22시)이 서류 시간 밖이면 정정인지 한 번 확인(C6)")
    expect(not any(q["item"] == "C6.T1" for q in augment.summary(tdoc["fields"], near_)["questions"]), "서류 시간 안의 답이면 확인하지 않음")
print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
