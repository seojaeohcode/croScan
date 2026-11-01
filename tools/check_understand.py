"""AI 답 이해의 서버 검사 (server/understand.check): the model's proposals are made up here, no model is called.

  python tools/check_understand.py

Each case is a proposal and what the check must do with it: keep it (an answer to confirm), keep it apart (another
team's words) or drop it (and why).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import understand  # noqa: E402

ANSWER = ("실제로는 13시부터 15시까지만 해요. 가우징은 아크 가우징에 CO2 용접입니다. 옆에서 도장팀 세 명이 터치업 한다고 들었어요. "
          "우리 작업자는 네 명이에요. 아까 4명이 아니라 6명입니다. 도장팀은 오늘 작업 없어요. 위치는 3BAY 08번 칼럼이에요. "
          "우리 작업자는 4명이고 장비는 9대입니다. 우리는 용접하고 도장팀 세 명이 옆에서 작업합니다. 도장팀은 어제 옆에서 작업을 끝냈습니다.")
SRC = {"qid": "T1:P-1", "choice": "partial", "value": ANSWER, "q": {"text": "실제 작업 시간은?"}}


def q(item, choices):
    return {"qid": f"{item}:P-1", "item": item, "permit_no": "P-1", "text": f"{item} 질문", "choices": choices, "keys": [], "prio": (0, 0)}


H2 = q("H2", [{"id": "text", "label": "방법·가스", "ask": "방법"}, {"id": "na", "label": "해당 없음"}, {"id": "unknown", "label": "모름"}])
B3 = q("B3", [{"id": "yes", "label": "있음", "ask": "무슨 작업"}, {"id": "no", "label": "없음"}, {"id": "unknown", "label": "모름"}])
L1 = q("L1", [{"id": "place", "label": "위치", "ask": "BAY·칼럼"}, {"id": "whole", "label": "공장 전체"}, {"id": "unknown", "label": "모름"}])
W = q("B1.workers", [{"id": "value", "label": "인원", "ask": "몇 명"}, {"id": "unknown", "label": "모름"}])
QS = [H2, B3, L1, W]

CASES = [
    ("우리 작업, 구절이 답에 있음 → 확인할 답", {"q": "Q1", "c": "text", "v": "아크 가우징, CO2 용접", "who": "self", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"}, "keep"),
    ("병행여부는 다른 팀 이야기가 답 → 확인할 답", {"q": "Q2", "c": "yes", "v": "도장팀 3명 터치업", "who": "other", "when": "plan", "quote": "옆에서 도장팀 세 명이 터치업 한다고"}, "keep"),
    ("다른 질문에 다른 팀 이야기 → 따로 남김", {"q": "Q1", "c": "text", "v": "도장", "who": "other", "when": "plan", "quote": "도장팀 세 명이 터치업"}, "apart"),
    ("구절이 답에 없음 → 버림", {"q": "Q3", "c": "place", "v": "3BAY 08칼럼", "who": "self", "when": "plan", "quote": "3BAY 08번 칼럼에서"}, "drop"),
    ("여러 곳을 …로 이은 구절 → 버림(이어진 한 구절만)", {"q": "Q1", "c": "text", "v": "아크 가우징", "who": "self", "when": "plan", "quote": "가우징은 아크 가우징…CO2 용접입니다"}, "drop"),
    ("「네 명」을 9로 → 9는 버리고 반장 원문을 값으로", {"q": "Q4", "c": "value", "v": "9", "who": "self", "when": "plan", "quote": "우리 작업자는 네 명이에요"}, "verbatim"),
    ("「네 명」을 4로 → 확인할 답", {"q": "Q4", "c": "value", "v": "4", "who": "self", "when": "plan", "quote": "우리 작업자는 네 명이에요"}, "keep"),
    ("「4명이 아니라 6명」의 앞부분만 → 버림(정정 문장)", {"q": "Q4", "c": "value", "v": "4", "who": "self", "when": "plan", "quote": "아까 4명이"}, "drop"),
    ("3BAY 구절에 값 9BAY → 9BAY는 버리고 반장 원문을 값으로", {"q": "Q3", "c": "place", "v": "9BAY 08칼럼", "who": "self", "when": "plan", "quote": "위치는 3BAY 08번 칼럼이에요"}, "verbatim"),
    ("다른 팀 문장에 who=self → 따로 남김", {"q": "Q1", "c": "text", "v": "터치업", "who": "self", "when": "plan", "quote": "옆에서 도장팀 세 명이 터치업"}, "apart"),
    ("병행여부 「없음」은 다른 팀 이야기로 안 됨 → 따로 남김", {"q": "Q2", "c": "no", "v": "", "who": "other", "when": "plan", "quote": "도장팀은 오늘 작업 없어요"}, "apart"),
    ("그 질문의 보기가 아님 → 버림", {"q": "Q1", "c": "yes", "v": "", "who": "self", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"}, "drop"),
    ("값이 필요한 보기에 값 없음 → 버림", {"q": "Q1", "c": "text", "v": "", "who": "self", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"}, "drop"),
    ("모름은 제안이 아님 → 버림", {"q": "Q1", "c": "unknown", "v": "", "who": "self", "when": "none", "quote": "아크 가우징에 CO2 용접입니다"}, "drop"),
    ("「네 명」을 16으로 → 16은 버림", {"q": "Q4", "c": "value", "v": "16", "who": "self", "when": "plan", "quote": "우리 작업자는 네 명이에요"}, "verbatim"),
    ("「4명이고 장비는 9대」 인원 9 → 9는 버림", {"q": "Q4", "c": "value", "v": "9", "who": "self", "when": "plan", "quote": "우리 작업자는 4명이고 장비는 9대입니다"}, "verbatim"),
    ("같은 문장의 「우리」가 다른 팀 구절을 우리 것으로 만들지 않음 → 따로 남김", {"q": "Q4", "c": "value", "v": "3", "who": "self", "when": "plan", "quote": "도장팀 세 명이 옆에서 작업합니다"}, "apart"),
    ("어제 끝낸 다른 팀 작업은 병행이 아님 → 따로 남김", {"q": "Q2", "c": "yes", "v": "도장팀 작업", "who": "other", "when": "done", "quote": "도장팀은 어제 옆에서 작업을 끝냈습니다"}, "apart"),
    ("Q0 같은 없는 번호 → 버림", {"q": "Q0", "c": "text", "v": "x", "who": "self", "when": "plan", "quote": "아크 가우징"}, "drop"),
    ("없는 질문 번호 → 버림", {"q": "Q9", "c": "text", "v": "x", "who": "self", "when": "plan", "quote": "아크 가우징"}, "drop"),
    ("누구 이야기인지 불분명 → 따로 남김", {"q": "Q1", "c": "text", "v": "아크", "who": "unknown", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"}, "apart"),
]


def main():
    ok = 0
    for name, prop, want in CASES:
        props, apart, dropped = understand.check({}, [SRC], SRC, QS, [prop])
        got = ("verbatim" if props[0].get("verbatim") and props[0]["value"] == prop["quote"] else "keep") if props else "apart" if apart else "drop"
        good = bool(got == want and (not props or (props[0]["by"] == SRC["qid"] and props[0]["ai"] and props[0]["quote"])))
        ok += good
        print(f"{'PASS' if good else 'FAIL'} {name}: {got}" + (f" {dropped}" if dropped and not good else ""))
    # the same question twice: the second is dropped
    props, _, dropped = understand.check({}, [SRC], SRC, QS, [CASES[0][1], CASES[0][1]])
    good = len(props) == 1 and len(dropped) == 1
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 같은 질문 두 번 → 하나만")
    # measured 2026-10-31: one place answer read as 「러그 없음」「해당 없음」「병행 없음」 at once
    place = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 12-14 칼럼", "q": {"text": "작업 위치는?"}}
    qs = [H2, B3, W]
    stretched = [{"q": "Q1", "c": "na", "v": "", "who": "self", "when": "plan", "quote": "3BAY 12-14 칼럼"},
                 {"q": "Q2", "c": "no", "v": "", "who": "self", "when": "plan", "quote": "3BAY 12-14 칼럼"}]
    props, _, dropped = understand.check({}, [place], place, qs, stretched)
    good = not props and len(dropped) == 2
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 없다는 말이 없는 구절로 「없음」 보기 → 버림 {dropped if not good else ''}")
    said = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 12-14 칼럼, 전기 용접만 해서 가스는 안 써요", "q": {"text": "작업 위치는?"}}
    props, _, _ = understand.check({}, [said], said, qs, [{"q": "Q1", "c": "na", "v": "", "who": "self", "when": "plan", "quote": "가스는 안 써요"}])
    good = len(props) == 1
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 「가스는 안 써요」 → 해당 없음은 남음")
    C1 = q("C1", [{"id": "text", "label": "설명", "ask": "설명"}, {"id": "unknown", "label": "모름"}])
    twice = [{"q": "Q1", "c": "text", "v": "아크 가우징", "who": "self", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"},
             {"q": "Q2", "c": "text", "v": "용접", "who": "self", "when": "plan", "quote": "아크 가우징에 CO2 용접입니다"}]
    props, _, dropped = understand.check({}, [SRC], SRC, [H2, C1], twice)
    good = not props and all(d[1] == "같은 구절을 여러 질문에 씀" for d in dropped)
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 같은 구절을 숫자·번호 없이 두 질문에 → 둘 다 버림")
    place = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 08-10 칼럼", "q": {"text": "작업 위치는?"}}
    props, _, dropped = understand.check({}, [place], place, qs, [{"q": "Q2", "c": "yes", "v": "3BAY 08-10 칼럼", "who": "self", "when": "plan", "quote": "3BAY 08-10 칼럼"}])
    good = not props
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 위치 답 전체를 병행여부 「있음」으로 → 버림 (실측) {dropped if not good else ''}")
    near = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 08-10 칼럼, 블록 위에서 해요", "q": {"text": "작업 위치는?"}}
    props, _, dropped = understand.check({}, [near], near, qs, [{"q": "Q2", "c": "yes", "v": "블록 위", "who": "self", "when": "plan", "quote": "블록 위에서 해요"}])
    good = not props
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 다른 작업이 없는 문장으로 병행여부 「있음」 → 버림 {dropped if not good else ''}")
    more = extra()
    n = len(CASES) + 6 + len(more)
    ok += sum(more)
    print(f"\n{ok}/{n}")
    sys.exit(0 if ok == n else 1)


def _parse(qtext):
    """an example's question list as questions (for checking its reply with the server's own check)"""
    qs = []
    for line in qtext.split("\n"):
        m = re.match(r"Q(\d+) (.*?) 보기: (.*)$", line)
        if m:
            ch = [{"id": c.split("=")[0], "label": c.split("=")[1].replace("(값)", ""), **({"ask": "값"} if "(값)" in c else {})}
                  for c in m.group(3).split(", ")]
            qs.append({"qid": f"X{m.group(1)}:P-1", "item": f"X{m.group(1)}", "permit_no": "P-1", "text": m.group(2), "choices": ch + [{"id": "unknown", "label": "모름"}]})
    return qs


def extra():
    """the example bank, the reply's next question, NORMALIZE, PHRASE and the unread facts (design §1.4·§4.5·§5.1)"""
    import asyncio
    import json
    from server import llm
    out = []

    def check(name, cond):
        out.append(bool(cond))
        print(f"{'PASS' if cond else 'FAIL'} {name}")
    bad = []
    for g, (qt, at) in understand.BANK.items():
        qs = _parse(qt.split("\n반장의 답: ")[0])
        said = qt.split("\n반장의 답: ")[1]
        data = json.loads(at)
        src = {"qid": "T1:P-1", "choice": "partial", "value": said, "q": {"text": "x"}}
        props, apart, dropped = understand.check({}, [src], src, qs, data["props"])
        if len(props) + len(apart) != len(data["props"]) or not understand._valid(data, [f"Q{i}" for i in range(1, len(qs) + 1)],
                                                                                   sorted({c["id"] for q in qs for c in q["choices"]})):
            bad.append((g, dropped))
    check(f"예시 은행 {len(understand.BANK)}개: 각 예시의 답이 서버 검사를 그대로 통과 {bad}", len(understand.BANK) >= 12 and not bad)
    qs = [{"qid": "LO3:P", "item": "LO3", "text": "x", "choices": []}, {"qid": "B3:P", "item": "B3", "text": "x", "choices": []}]
    check("예시 선택은 질문 목록만으로 정해짐(미리 읽기와 읽기가 같은 예시)", understand.examples(qs) == understand.examples(list(qs)) and len(understand.examples(qs)) == 2)
    check("다음 질문(next)은 남은 질문 번호나 none만", understand._valid({"props": [], "next": "Q1"}, ["Q1"], ["x"])
          and not understand._valid({"props": [], "next": "Q9"}, ["Q1"], ["x"]) and understand._valid({"props": []}, ["Q1"], ["x"]))
    real = llm.call_json

    def fake(reply):
        async def call(kind, messages, schema, **kw):
            return reply, {}
        return call
    try:
        HT = {"qid": "HT1:P-1", "item": "HT1", "permit_no": "P-1", "text": "러그 몇 개를 어떤 방법으로?",
              "choices": [{"id": "gas", "label": "가스절단", "ask": "개수"}, {"id": "na", "label": "떼는 러그 없음"}, {"id": "unknown", "label": "모름"}]}
        src = {"qid": "T1:P-1", "choice": "partial", "value": "13~15시. 러그는 4개가 아니라 6개를 가스로 잘라요.", "q": {"text": "시간?"}}
        llm.call_json = fake({"part": "after", "c": "gas", "v": "6"})
        got = asyncio.run(understand.normalize({}, [src], src, HT, "러그는 4개가 아니라 6개를 가스로 잘라요"))
        check("NORMALIZE: 정정 문장의 뒷부분(6개 가스절단)만 제안, 구절은 그 부분", got and got["value"] == "6" and "6개" in got["quote"] and got["normalized"])
        llm.call_json = fake({"part": "after", "c": "gas", "v": "4"})
        check("NORMALIZE: 고른 부분에 없는 값(4)은 버림", asyncio.run(understand.normalize({}, [src], src, HT, "러그는 4개가 아니라 6개를 가스로 잘라요")) is None)
        llm.call_json = fake({"part": "none", "c": "none", "v": ""})
        check("NORMALIZE: 알 수 없음이면 제안 없음", asyncio.run(understand.normalize({}, [src], src, HT, "러그는 4개가 아니라 6개를 가스로 잘라요")) is None)
        # the H2 question (used by the quote-repair checks below)
        QH2 = {"qid": "H2:P-1", "item": "H2", "permit_no": "P-1", "text": "절단·가우징·용접은 어떤 방법으로 하고, 어떤 가스(산소·LPG·CO2·아르곤 등)를 쓰나요?",
               "choices": [{"id": "text", "label": "방법·가스 입력", "ask": "방법"}, {"id": "na", "label": "가스 안 씀(전기 용접만)"}, {"id": "unknown", "label": "모름"}]}
        # Codex review 2026-10-31 (one round): undecided / conditional / past statements, our own team, hyphen IDs
        QLX = {"qid": "LI1:P-1", "item": "LI1", "permit_no": "P-1", "text": "어떤 크레인으로 어떻게 옮기나요?", "choices": [{"id": "text", "label": "크레인·방법 입력", "ask": "무엇"}]}
        for said, quote, v, ok_ in (("10~12시. 크레인은 그날 배정 보고 정할 거예요.", "크레인은 그날 배정 보고 정할 거예요", "배정", False),
                                    ("10~12시. 바람 세면 OH-21-01 써요.", "바람 세면 OH-21-01 써요", "OH-21-01", False),
                                    ("10~12시. 어제 OH-21-03으로 옮겼어요.", "어제 OH-21-03으로 옮겼어요", "OH-21-03", False),
                                    ("10~12시. OH-21-03으로 블록 측면 잡고 옮겨요.", "OH-21-03으로 블록 측면 잡고 옮겨요", "OH-21-03", True),
                                    ("10~12시. OH-21-03으로 옮겨요.", "OH-21-03으로 옮겨요", "MC-21-03", True)):
            sx = {"qid": "T1:P-1", "choice": "partial", "value": said}
            pr, _, _ = understand.check({}, [sx], sx, [QLX], [{"q": "Q1", "c": "text", "v": v, "who": "self", "when": "plan", "quote": quote}])
            check(f"{'제안' if ok_ else '버림'}: {quote} ({v})", bool(pr) == ok_ and not (pr and "MC-" in pr[0]["value"]))
        check("「우리 배관팀」은 다른 팀이 아님", not understand._other("우리 배관팀은 13시부터 해요") and understand._other("옆에서 도장팀이 해요"))
        check("말머리 제거가 「아래」를 자르지 않음", understand.augment._place_value("아래 3BAY 12-14 칼럼").startswith("아래"))
        # NL eval 2026-10-31: a quote running over a sentence end is checked on every sentence it touches (the hedge after it too)
        QLI = {"qid": "LI1:P-1", "item": "LI1", "permit_no": "P-1", "text": "어떤 크레인으로 어떻게 옮기나요?", "choices": [{"id": "text", "label": "크레인·방법 입력", "ask": "무엇"}]}
        sx = {"qid": "T1:P-1", "choice": "partial", "value": "10~12시. 바람 세면 OH-21-02 대신 OH-21-01 쓸 수도 있어요."}
        pr, _, dr = understand.check({}, [sx], sx, [QLI], [{"q": "Q1", "c": "text", "v": "OH-21-01", "who": "self", "when": "plan", "quote": "10~12시. 바람 세면 OH-21-02 대신 OH-21-01"}])
        check("문장 경계를 걸친 인용은 버림(무엇이 걸리는지 불분명 → 다시 물음)", not pr and dr and dr[0][1] == "인용이 문장 하나에 들지 않음")
        # NL eval 2026-10-31: a typed value that only states absence is the question's own 「없음」 choice (any question)
        QCF = {"qid": "CF2:P-1", "item": "CF2", "permit_no": "P-1", "text": "그 구획에 가스·공기를 넣는 배관이나 연결 계통이 있나요?",
               "choices": [{"id": "text", "label": "계통 입력", "ask": "무엇"}, {"id": "none", "label": "연결 계통 없음"}, {"id": "unknown", "label": "모름"}]}
        for said, quote, v, want in (("1~2시. 그 구획엔 가스나 공기 넣는 배관 연결이 없어요.", "그 구획엔 가스나 공기 넣는 배관 연결이 없어요", "가스·공기 배관 연결 없음", "text"),
                                     ("1~2시. 산소는 없고 아르곤 배관이 있어요.", "산소는 없고 아르곤 배관이 있어요", "아르곤 배관", "text")):
            sx = {"qid": "T1:P-1", "choice": "partial", "value": said}
            pr, _, _ = understand.check({}, [sx], sx, [QCF], [{"q": "Q1", "c": "text", "v": v, "who": "self", "when": "plan", "quote": quote}])
            check(f"보기는 AI가 고른 그대로(서버가 다른 보기로 바꾸지 않음): {v} → {want}", pr and pr[0]["choice"] == want)
        # NL eval 2026-10-31: the right reading quoted from the wrong sentence, or the whole answer: the one sentence that says it
        QH1 = {"qid": "H1:P-1", "item": "H1", "permit_no": "P-1", "text": "불량부는 용접부만 파내는 보수인가요, 부재를 떼어 교체하나요? 몇 군데인가요?",
               "choices": [{"id": "local", "label": "용접부만 보수", "ask": "몇 군데"}, {"id": "replace", "label": "부재를 떼어 교체", "ask": "몇 개"}]}
        sx = {"qid": "T1:P-1", "choice": "partial", "value": "매일 9시~10시 반만 해요. 용접부만 파내는 보수고 네 군데입니다."}
        pr, _, _ = understand.check({}, [sx], sx, [QH1], [{"q": "Q1", "c": "local", "v": "4", "who": "self", "when": "plan", "quote": "매일 9시~10시 반만 해요"}])
        check("엉뚱한 문장을 짚은 제안은 버림(서버가 근거를 다시 고르지 않음 → 다시 물음)", not pr)
        sx = {"qid": "T1:P-1", "choice": "partial", "value": "매일 9~11시요. 작업자 4명이고 용접부만 손봐요."}
        pr, _, _ = understand.check({}, [sx], sx, [QH1], [{"q": "Q1", "c": "local", "v": "4", "who": "self", "when": "plan", "quote": "매일 9~11시요"}])
        check("근거 보정: 「4명」은 몇 군데가 아니므로 보정하지 않음", not pr)
        sx = {"qid": "T1:P-1", "choice": "partial", "value": "매일 9~11시요. 산소랑 LPG로 절단하고 에어 아크 가우징 해요."}
        pr, _, _ = understand.check({}, [sx], sx, [QH2], [{"q": "Q1", "c": "text", "v": "산소·LPG 절단, 에어 아크 가우징", "who": "self", "when": "plan", "quote": sx["value"].rstrip(".")}])
        check("답 전체를 인용한 제안은 버림(인용이 문장 하나에 들지 않음)", not pr)
        sx = {"qid": "T1:P-1", "choice": "partial", "value": "매일 9~11시요."}
        pr, _, _ = understand.check({}, [sx], sx, [QH2], [{"q": "Q1", "c": "text", "v": "9~11시", "who": "self", "when": "plan", "quote": "매일 9~11시요"}])
        check("근거 보정: 원래 질문의 답만 있는 문장은 다른 질문의 답이 아님", not pr)
        # NL eval 2026-10-31: a correction of the lug count read again for 병행여부 came back 「있음」
        QB = {"qid": "B3:P-1", "item": "B3", "permit_no": "P-1", "text": "같은 시간·장소의 다른 작업은?",
              "choices": [{"id": "yes", "label": "있음", "ask": "무엇"}, {"id": "no", "label": "없음"}, {"id": "unknown", "label": "모름"}]}
        s2 = {"qid": "T1:P-1", "choice": "partial", "value": "1시~3시요. 아까 러그 4개라고 했는데 잘못 말했고 6개 가스절단입니다.", "q": {"text": "시간?"}}
        llm.call_json = fake({"part": "after", "c": "yes", "v": "있음"})
        check("NORMALIZE: 정정 문장에서 병행작업(다른 작업)은 다시 읽지 않음", asyncio.run(understand.normalize({}, [s2], s2, QB, "아까 러그 4개라고 했는데 잘못 말했고 6개 가스절단입니다")) is None)
        LO = {"qid": "LO3:P-1", "item": "LO3", "permit_no": "P-1", "text": "언제 차단하고 언제 복구하나요?", "choices": [{"id": "text", "label": "적기", "ask": "시각"}]}
        s3 = {"qid": "T1:P-1", "choice": "partial", "value": "9시가 아니라 10시부터 12시까지 해요.", "q": {"text": "시간?"}}
        llm.call_json = fake({"part": "after", "c": "text", "v": "10시부터 12시까지"})
        check("NORMALIZE: 질문의 내용(차단·복구) 말이 없는 부분은 제안 없음", asyncio.run(understand.normalize({}, [s3], s3, LO, "9시가 아니라 10시부터 12시까지 해요")) is None)
        T2 = {"qid": "HT2:P-1", "item": "HT2", "permit_no": "P-1", "text": "떼어낸 러그는 무엇으로 받아 어디에 내리나요?", "choices": []}
        ans = [{"qid": "T1:P-1", "value": "러그 6개 가스절단, 13~15시"}]
        llm.call_json = fake({"out": [{"t": "T1", "v": "ref", "r": "R1"}]})
        got = asyncio.run(understand.phrase(ans, [T2], sid="s-ph"))
        check("PHRASE: 모델은 방식만 고르고 문장은 서버 틀(앞 답 짚기)", got["HT2:P-1"]["text"].startswith("앞에서 「러그 6개") and got["HT2:P-1"]["how"] == "ref")
        llm.call_json = fake({"out": [{"t": "T1", "v": "short", "r": "none", "text": "아무 말"}]})
        got = asyncio.run(understand.phrase([{"qid": "L1:P-1", "value": "3BAY"}], [T2], sid="s-ph2"))
        check("PHRASE: 덧붙인 문장은 쓰지 않고 짧은 기본 문구", got["HT2:P-1"]["text"] == understand.need_catalog.FALLBACK["HT2"])
        understand._PHRASE_N["s-max"] = understand.PHRASE_MAX
        check("PHRASE: 회차당 상한을 넘으면 준비하지 않음(규칙 문구 그대로)", asyncio.run(understand.phrase(ans, [T2], sid="s-max")) == {})
    finally:
        llm.call_json = real
    p = {"q": HT, "choice": "gas", "value": "가스절단"}
    check("미확인 표시: 가스절단만 읽으면 「러그 개수」가 미확인",
          understand.need_catalog.atoms(p["q"]["item"], p["choice"], p["value"])["missing"] == ["러그 개수"])
    return out


if __name__ == "__main__":
    main()
