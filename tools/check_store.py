"""The review session store (server/store.py, design §2): proposals are not answers until confirmed.

  python tools/check_store.py

Runs on a throwaway database (CROSCAN_DATA is set to a temp folder before the server modules are loaded).
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_store_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import store  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def raises(name, fn, code):
    try:
        fn()
        check(name, False)
    except store.StoreError as e:
        check(name, e.code == code)


def fields(date="2026-10-31", pno="P-1", date2=None):
    f = {"p1.permit_no": {"key": "permit_no", "page": 1, "value": pno}, "p1.date_1": {"key": "date_1", "page": 1, "value": date}}
    if date2:
        f.update({"p2.permit_no": {"key": "permit_no", "page": 2, "value": "P-2"}, "p2.date_1": {"key": "date_1", "page": 2, "value": date2}})
    return f


F = fields()
QT1 = {"qid": "T1:P-1", "item": "T1", "page": 1, "text": "시간?"}
QB3 = {"qid": "B3:P-1", "item": "B3", "page": 1, "text": "병행?", "choices": [{"id": "yes", "label": "있음", "ask": "무엇"}, {"id": "no", "label": "없음"}]}
SRC = {"qid": "T1:P-1", "choice": "partial", "value": "13시부터 15시까지, 옆에서 도장팀이 터치업해요", "q": QT1}
PROP = {"qid": "B3:P-1", "choice": "yes", "value": "도장팀 터치업", "q": QB3, "by": "T1:P-1", "quote": "옆에서 도장팀이 터치업해요"}
qids = lambda answers: [a["qid"] for a in answers]


def ans(sid, answers, f=F):
    """the review's request as the client sends it: with the revision it last saw"""
    return store.answers_for(sid, answers, f, store.revision(sid))


def prop(sid, origin, src, items):
    return store.propose(sid, origin, src, items, basis=store.revision(sid))[0]


def chk(item, choice="ok", at=1, page=1, value=""):
    return {"qid": f"{item}:P-1", "choice": choice, "value": value, "at": at, "q": {"qid": f"{item}:P-1", "item": item, "page": page}}


def main():
    sid = store.create()
    raises("개정 번호 없이 답을 바꾸면 428", lambda: store.answers_for(sid, [SRC], F), "revision_required")
    ans(sid, [SRC])
    pid = prop(sid, "rule", SRC, [PROP])[0]["pid"]
    calc, rev, _ = ans(sid, [SRC])
    check("제안은 확인 전에 계산에 들어가지 않음", qids(calc) == ["T1:P-1"])
    calc, _, _ = ans(sid, [SRC, dict(PROP, ai=True)])
    check("클라이언트가 보낸 파생 답(by·ai)은 받지 않음", qids(calc) == ["T1:P-1"])
    calc, _, _ = ans(sid, [dict(SRC, read="99")])
    check("클라이언트가 보낸 read는 버림", "read" not in calc[0])
    r0 = store.revision(sid)
    got, r1 = store.propose(sid, "rule", SRC, [PROP], basis=r0)
    check("같은 답의 같은 읽기는 두 번 저장하지 않고 개정도 그대로", got[0]["pid"] == pid and len(store.pending(sid)) == 1 and r1 == r0 == store.revision(sid))
    r = store.decide(sid, "act-1", adopt=[pid], fields=F)
    calc, _, _ = ans(sid, [SRC])
    check("확인하면 채택되어 계산에 들어감", qids(calc) == ["T1:P-1", "B3:P-1"] and r["adopted"][0]["by"] == "T1:P-1")
    check("같은 동작 번호를 다시 보내면 처음 결과(응답 유실 뒤 재시도)", store.decide(sid, "act-1", adopt=[pid], fields=F) == r)
    raises("같은 번호·다른 내용은 충돌", lambda: store.decide(sid, "act-1", reject=[pid]), "action_conflict")
    calc, _, _ = ans(sid, [SRC], fields(pno="P-9"))
    check("승인번호만 바꾸면 직접 답·채택 모두 새 번호로(by도)", qids(calc) == ["T1:P-9", "B3:P-9"] and calc[1]["by"] == "T1:P-9"
          and calc[0]["q"]["permit_no"] == "P-9")
    calc, _, _ = ans(sid, [SRC], fields(date="2026-11-01"))
    check("양식 날짜가 바뀌면 그 쪽의 채택은 무효", qids(calc) == ["T1:P-1"] and not store.adopted(sid))
    ans(sid, [SRC])
    p2 = prop(sid, "rule", SRC, [PROP])
    check("같은 말·같은 양식으로 돌아오면 새 번호로 다시 제안(확인은 다시)", p2 and p2[0]["status"] == "proposed" and p2[0]["pid"] != pid and not store.adopted(sid))
    store.decide(sid, "act-2", reject=[p2[0]["pid"]], fields=F)
    check("뺀 제안은 같은 말로는 다시 제안하지 않음", prop(sid, "rule", SRC, [PROP]) == [])

    # the revision: every change needs the one last seen; the one returned is the one stored
    s2 = store.create()
    _, r0, _ = store.answers_for(s2, [SRC], F, 0)
    _, r1, _ = store.answers_for(s2, [dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요")], F, expected=r0)
    raises("늦게 온 옛 요청은 새 답을 덮지 못함(409)", lambda: store.answers_for(s2, [SRC], F, expected=r0), "stale_revision")
    calc, _, _ = store.answers_for(s2, [dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요")], F, expected=r1)
    check("최신 개정으로는 그대로 진행", calc[0]["value"].startswith("13시부터 16시까지"))
    raises("양식만 바뀌어도 개정 번호가 필요", lambda: store.answers_for(s2, [dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요")],
                                                        fields(date="2026-11-02")), "revision_required")
    S2 = dict(SRC, value="13시부터 16시까지, 옆에서 도장팀이 터치업해요")
    before = store.revision(s2)
    _, after = store.propose(s2, "rule", S2, [PROP], basis=before)
    check("제안을 저장하면 개정이 하나 오르고, 돌려준 개정이 저장된 것과 같음", after == before + 1 == store.revision(s2))
    raises("읽는 동안 개정이 바뀌면 그 제안은 저장하지 않음", lambda: store.propose(s2, "ai", S2, [dict(PROP, value="x")], basis=before), "stale_revision")
    raises("체크리스트·미리보기·제출: 개정 번호 없으면 428", lambda: store.current(s2, F, None), "revision_required")
    raises("체크리스트·미리보기·제출: 옛 개정이면 409", lambda: store.current(s2, F, before), "stale_revision")
    calc, rv, _ = store.current(s2, F, store.revision(s2))
    check("현재 개정으로는 세션의 답을 그대로 읽음(쓰지 않음)", qids(calc) == ["T1:P-1"] and rv == store.revision(s2))

    # checking answers: tied to what they checked
    s3 = store.create()
    A1 = chk("A1.T1", "pm")
    ans(s3, [SRC, A1])
    calc, _, dropped = ans(s3, [SRC, A1])
    check("확인 질문 답은 바탕 답이 그대로면 쓰임", "A1.T1:P-1" in qids(calc) and not dropped)
    B = dict(SRC, value="2시부터 4시까지 하고, 옆에서 도장팀이 터치업해요")
    calc, _, dropped = ans(s3, [B, A1])
    check("바탕 답이 바뀌면 그 확인 질문 답은 쓰지 않고 알림", "A1.T1:P-1" not in qids(calc) and dropped == ["A1.T1:P-1"])
    calc, _, dropped = ans(s3, [SRC, A1])
    check("바탕 답이 원래 말로 돌아와도(A→B→A) 그 확인 답은 되살아나지 않음", "A1.T1:P-1" not in qids(calc) and dropped == ["A1.T1:P-1"])
    calc, _, dropped = ans(s3, [SRC, dict(A1, at=2)])
    check("다시 물어 새로 답하면 그때부터 쓰임", "A1.T1:P-1" in qids(calc) and not dropped)
    s3b = store.create()
    A12 = chk("A1.T1.2", "am")
    ans(s3b, [SRC, A12])
    calc, _, dropped = ans(s3b, [B, A12])
    check("둘째 불분명 부분(A1.T1.2)도 바탕(T1)이 바뀌면 빠짐", dropped == ["A1.T1.2:P-1"])
    s3c = store.create()
    FR1 = {"qid": "FREE:1", "choice": "text", "value": "옆에서 용접팀이 블록 작업합니다"}
    A3 = chk("A3.F1", "mine")
    A1A3 = chk("A1.A3.F1", "pm")
    C5 = chk("C5.B3", "same")
    C5c = chk("C5.concurrent", "yes")
    ans(s3c, [SRC, PROP | {"q": QB3, "by": None}, FR1, A3, A1A3, C5, C5c])
    calc, _, dropped = ans(s3c, [SRC, PROP | {"q": QB3, "by": None}, FR1, A3, A1A3, C5, C5c])
    check("자유 답변에 걸린 확인 답들은 그대로면 모두 쓰임", {"A3.F1:P-1", "A1.A3.F1:P-1", "C5.B3:P-1", "C5.concurrent:P-1"} <= set(qids(calc)))
    calc, _, dropped = ans(s3c, [SRC, PROP | {"q": QB3, "by": None}, A3, A1A3, C5, C5c])
    check("자유 답변을 지우면 그에 걸린 확인 답(A3.F1)과 그 확인의 확인(A1.A3.F1), C5 모두 빠짐",
          {"A3.F1:P-1", "A1.A3.F1:P-1", "C5.B3:P-1", "C5.concurrent:P-1"} == set(dropped))
    s3d = store.create()
    ans(s3d, [FR1, C5c])
    calc, _, dropped = ans(s3d, [FR1, C5c], fields(date="2026-11-03"))
    check("양식이 바뀌면 병행 확인(C5.concurrent)은 빠짐", dropped == ["C5.concurrent:P-1"])

    # one adopted reading per question; another session's ids; a direct answer wins
    s4 = store.create()
    QL1 = {"qid": "L1:P-1", "item": "L1", "page": 1}
    SRC2 = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 08칼럼, 옆 도장팀 작업 있어요", "q": QL1}
    ans(s4, [SRC, SRC2])
    a = prop(s4, "rule", SRC, [PROP])[0]["pid"]
    b = prop(s4, "ai", SRC2, [dict(PROP, by="L1:P-1", value="도장 작업", quote="옆 도장팀 작업 있어요")])[0]["pid"]
    store.decide(s4, "x1", adopt=[a], fields=F)
    raises("같은 질문에 두 번째 채택은 막음", lambda: store.decide(s4, "x2", adopt=[b], fields=F), "stale_proposal")
    check("채택이 있는 질문에는 새 제안을 만들지 않음", prop(s4, "ai", SRC2, [dict(PROP, value="다른 값", quote="옆 도장팀 작업 있어요")]) == [])
    s5 = store.create()
    ans(s5, [SRC])
    p5 = prop(s5, "ai", SRC, [PROP])[0]["pid"]
    raises("다른 세션의 제안은 채택할 수 없음", lambda: store.decide(sid, "x3", adopt=[p5], fields=F), "stale_proposal")
    store.decide(s5, "x4", adopt=[p5], fields=F)
    store.decide(s5, "x5", withdraw=[p5], fields=F)
    check("확인한 것도 「이것 빼기」로 철회", not store.adopted(s5))
    raises("이미 뺀 것을 다시 빼면 409", lambda: store.decide(s5, "x6", withdraw=[p5], fields=F), "stale_proposal")
    calc, _, _ = ans(s5, [SRC, {"qid": "B3:P-1", "choice": "no", "value": "", "q": QB3}])
    check("그 질문에 직접 답하면 직접 답이 이김", [x for x in calc if x["qid"] == "B3:P-1"][0]["choice"] == "no")
    raises("없는 세션은 404", lambda: store.answers_for("없는세션", [SRC], F, 0), "session_missing")
    raises("바뀐 답에서 온 제안은 저장하지 않음", lambda: prop(s5, "rule", dict(SRC, value="바뀐 답입니다 아주 길게"), [PROP]), "stale_answer")

    # a pair question: its reading holds against both pages
    s6 = store.create()
    F2 = fields(date2="2026-10-31")
    QP = {"qid": "E1:P-1>P-2", "item": "E1", "page": 1, "other": 2}
    ans(s6, [SRC], F2)
    pp = prop(s6, "rule", SRC, [{"qid": "E1:P-1>P-2", "choice": "yes", "value": "", "q": QP, "quote": "옆에서"}])[0]["pid"]
    store.decide(s6, "y1", adopt=[pp], fields=F2)
    calc, _, _ = ans(s6, [SRC], F2)
    check("짝 질문의 채택은 두 쪽 양식이 그대로면 쓰임", "E1:P-1>P-2" in qids(calc))
    calc, _, _ = ans(s6, [SRC], fields(date2="2026-11-05"))
    check("상대 허가서 쪽 양식이 바뀌면 짝 질문의 채택도 무효", "E1:P-1>P-2" not in qids(calc))

    s7 = store.create()
    calc, _, _ = ans(s7, [dict(SRC, qid="T1:P-1"), {"qid": "FREE:3", "choice": "text", "value": "말"}, dict(QL1, qid="L1:P-1", choice="place", value="3BAY", q=QL1)])
    check("답은 준 순서대로(별지 줄 순서)", qids(calc) == ["T1:P-1", "FREE:3", "L1:P-1"])

    # state: for a reload, what counts and what waits, read together
    st = store.state(s2, F)
    check("다시 열 때: 개정·직접 답·기다리는 제안", st["revision"] == store.revision(s2) and qids(st["typed"]) == ["T1:P-1"] and len(st["proposals"]) == 1)

    # the budgets (design §3.5·§3.7): one count per ask as shown, at most 12, clarifications 3 (one per need), the
    # closing request once, model calls 30, AI needs 2 a call and 8 a review, the analysis once
    b8 = store.create()
    r1, r2 = store.issue(b8, "T1@1", "question"), store.issue(b8, "T1@1", "question")
    check("같은 질문을 다시 보여도(새로고침·다른 탭) 한 번만 셈", r1["used"] == 1 and r2["again"] and r2["used"] == 1)
    store.issue(b8, "A1.T1@1", "clarify", "T1@1")
    raises("같은 내용은 한 번만 다시 묻기", lambda: store.issue(b8, "RETRY:T1@1", "clarify", "T1@1"), "clarify")
    store.issue(b8, "RETRY:L1@1", "clarify", "L1@1")
    store.issue(b8, "C5.B3@1", "clarify", "B3@1")
    raises("다시 묻기는 검토 전체에서 3회까지", lambda: store.issue(b8, "U1.F1@1", "clarify", "FREE:1"), "clarify")
    for i in range(8):
        store.issue(b8, f"Q{i}@1", "question")
    raises("질문은 12회까지(13번째는 거절)", lambda: store.issue(b8, "Q9@1", "question"), "budget")
    check("한도를 넘어도 이미 보인 질문은 다시 보일 수 있음(그 답은 받음)", store.issue(b8, "Q7@1", "question")["again"])
    b9 = store.create()
    store.issue(b9, "CLOSE", "close")
    check("마무리 요청은 한 번: 두 번째는 「이미 물음」", store.issue(b9, "CLOSE", "close")["again"])
    for _ in range(store.LLM_CALLS):
        store.charge_llm(b9)
    raises("모델 호출은 검토당 30회까지", lambda: store.charge_llm(b9), "llm_budget")
    nd = lambda k: {"mkey": k, "t": "referent", "key": "p1.job", "quote": k}
    b9 = store.create()                                     # (the one above has ended: its closing request was shown)
    got = store.add_needs(b9, [nd("a"), nd("b"), nd("c")])
    check("AI 필요정보는 한 번에 2개까지", [x["n"] for x in got] == [1, 2])
    check("같은 뜻의 필요정보는 다시 넣지 않음", store.add_needs(b9, [nd("a")]) == [])
    for i in range(5):
        store.add_needs(b9, [nd(f"x{i}"), nd(f"y{i}")])
    check("AI 필요정보는 검토당 8개까지", len(store.needs(b9)) == 8)
    check("업로드 분석은 검토당 한 번", store.start_job(b9, "analyze") and not store.start_job(b9, "analyze"))
    check("둘째 불분명 부분의 다시 묻기도 같은 답(T1)으로 셈", store.clarify_base("A1.T1.2@1") == store.clarify_base("A1.T1@1") == "T1@1")
    b10 = store.create()
    for i in range(12):
        store.issue(b10, f"Q{i}@1", "question")
    try:
        store.issue(b10, "CLOSE", "close")
    except store.StoreError:
        store.close_review(b10)
    check("질문 한도로 끝난 검토에는 늦게 온 AI 필요정보를 넣지 않음", store.add_needs(b10, [nd("late")]) is None and store.budget(b10)["close"])

    # an older database: the columns added since, its readings without a form context no longer count
    old = Path(tempfile.mkdtemp(prefix="croscan_old_")) / "review.sqlite3"
    c = sqlite3.connect(old)
    c.executescript("""CREATE TABLE sessions (id TEXT PRIMARY KEY, created REAL, used REAL, revision INTEGER DEFAULT 0);
        CREATE TABLE typed (session_id TEXT, skey TEXT, qid TEXT, hash TEXT, data TEXT, PRIMARY KEY (session_id, skey));
        CREATE TABLE proposals (id TEXT PRIMARY KEY, session_id TEXT, skey TEXT, origin TEXT, src_skey TEXT, src_hash TEXT,
            payload TEXT, status TEXT, created REAL, decided REAL);
        CREATE TABLE actions (session_id TEXT, action_id TEXT, kind TEXT, request TEXT, result TEXT, created REAL, PRIMARY KEY (session_id, action_id));""")
    c.execute("INSERT INTO sessions VALUES ('old', 0, 9e9, 3)")
    for i in (1, 2):
        c.execute("INSERT INTO proposals VALUES (?, 'old', 'B3@1', 'rule', 'T1@1', 'h', ?, 'adopted', ?, ?)", (f"o{i}", json.dumps({"qid": "B3:P-1"}), i, i))
    c.commit()
    c.close()
    store.DB, store._READY = old, False
    st = store.state("old")
    left = [r[0] for r in sqlite3.connect(old).execute("SELECT status FROM proposals")]
    check("옛 DB: 열이 더해지고, 양식 기준이 없던 채택은 무효", st["revision"] == 3 and not st["adopted"] and left == ["invalidated", "invalidated"])
    store.DB, store._READY = old.parent / "review.sqlite3", False

    # design §10.7 / Codex #1: a reading stored while the foreman answered the next question does not refuse his answer
    s5 = store.create()
    _, r0, _ = store.answers_for(s5, [SRC], F, 0)
    store.propose(s5, "ai", SRC, [PROP], basis=r0)                       # the reading lands (revision +1)
    QL1 = {"qid": "L1:P-1", "item": "L1", "page": 1, "text": "위치?"}
    nxt = {"qid": "L1:P-1", "choice": "place", "value": "3BAY 12칼럼", "q": QL1}
    calc, r2, _ = store.answers_for(s5, [SRC, nxt], F, r0)                   # sent with the revision before the reading
    check("읽기 저장만 있었으면 반장의 다음 답은 거절하지 않음(답 유실 없음)", "L1:P-1" in qids(calc) and r2 > r0)
    store.decide(s5, "a-x", reject=[store.pending(s5)[0]["pid"]], fields=F) if store.pending(s5) else None
    raises("다른 변경(채택·거절)이 끼었으면 예전 개정은 거절", lambda: store.answers_for(s5, [SRC], F, r0), "stale_revision")
    # Codex #2: what is not a rule question leaves the asks the open rule questions need
    s6 = store.create()
    for i in range(9):
        store.issue(s6, f"Q{i}", "question")
    check("규칙 질문 몫(2개)이 남아 있으면 확인 카드는 10번째로 받음", store.issue(s6, "CARD:a", "card", reserve=2)["used"] == 10)
    raises("규칙 질문 몫(2개)을 쓰게 되는 카드는 거절", lambda: store.issue(s6, "CARD:b", "card", reserve=2), "reserved")
    check("규칙 질문 자체는 그 몫을 씀", store.issue(s6, "Q-rule", "question")["used"] == 11)
    # #2 after close: nothing new is asked (an ask shown before is shown again)
    store.issue(s6, "CLOSE", "close")
    raises("마무리한 검토에는 새로 묻지 않음", lambda: store.issue(s6, "Q-new", "question"), "closed")
    check("마무리 전에 보인 질문은 다시 보여도 됨", store.issue(s6, "Q-rule", "question")["again"])
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
