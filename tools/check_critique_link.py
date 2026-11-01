"""의미 검사(CRITIQUE)와 계획서 연결 제안(LINK)의 서버 쪽: the model is made up here (no model is called).

  python tools/check_critique_link.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_link_")    # the plan-correction part writes: a throwaway place
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import analyze, augment, critique, link, llm, workplan  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


CALLS = []


def fake(reply, v="supports"):
    """the model made up; a relation check (CRITIQUE) inside LINK answers v"""
    async def call(kind, messages, schema, **kw):
        CALLS.append((kind, kw.get("pri")))
        if isinstance(reply, Exception):
            raise reply
        if kind == "CRITIQUE" and "v" not in (reply if isinstance(reply, dict) else {}):
            return {"v": v}, {"ms": 1}
        return (reply(messages) if callable(reply) else reply), {"ms": 1}
    return call


Q = {"item": "B3", "text": "같은 시간·장소에 다른 작업이 있나요?", "choices": [{"id": "yes", "label": "있음"}, {"id": "no", "label": "없음"}]}
SRC = {"qid": "T1:P", "value": "13시~15시요. 같은 시간에 다른 작업은 없어요. 러그는 가스로 4개 잘라요."}


def prop(choice, quote, **kw):
    return {"qid": "B3:P", "choice": choice, "value": "", "q": Q, "quote": quote, "slot": "병행작업", **kw}


def plan_rec(title, start, end, loc="3BAY 12칼럼"):
    """a 작업계획서 record as workplan reads it: one field per printed value, items tied to their field (fk)"""
    rows = [("작업명", "title", title), ("시작일시", "start", start), ("종료일시", "end", end), ("작업위치", "location", loc)]
    F = {f"p1.r{i}": {"name": lab, "key": f"r{i}", "value": v, "original": v} for i, (lab, _, v) in enumerate(rows)}
    items = [{"label": lab, "key": k, "value": v, "fk": f"p1.r{i}"} for i, (lab, k, v) in enumerate(rows)]
    return {"title": title, "start": workplan._iso(start), "end": workplan._iso(end), "location": loc, "steps": [],
            "items": items, "doc": {"fields": F}}


TQ = {"qid": "T1:P", "item": "T1", "page": 1, "text": "시간?", "keys": ["p1.from_1", "p1.to_1"],
      "choices": [{"id": "yes", "label": "내내 함"}, {"id": "partial", "label": "일부 시간만", "ask": "시간"}, {"id": "unknown", "label": "모름"}]}


def corrected_plan():
    """A3: a plan corrected in step 1 is linked and imported as corrected (its day, its time), its digest of that plan"""
    fields = {"p1.date_1": {"key": "date_1", "page": 1, "name": "작업일자", "value": "2026-10-29"},
              "p1.from_1": {"key": "from_1", "page": 1, "name": "1일차 시작", "value": "08:00"},
              "p1.to_1": {"key": "to_1", "page": 1, "name": "1일차 종료", "value": "16:59"},
              "p1.job": {"key": "job", "page": 1, "name": "작업내용", "value": "E41P 블록 상부 러그 절단"}}
    plans = [plan_rec("E41P 러그 절단", "2026-10-30 13:00", "2026-10-30 15:00"),       # read as 10-30, corrected to 10-29
             plan_rec("E41P 러그 회수", "2026-10-29 13:00", "2026-10-29 15:00")]       # read as 10-29, corrected to 10-31
    saved = {"0": {"p1.r1": "2026-10-29 09:00", "p1.r2": "2026-10-29 11:00"}, "1": {"p1.r1": "2026-10-31 13:00", "p1.r2": "2026-10-31 15:00"}}
    cor = workplan.edited(plans[0], saved["0"])
    check("A3 수정본: 시작·종료가 고친 값으로(원래 기록은 그대로)", cor["start"] == "2026-10-29T09:00" and cor["end"] == "2026-10-29T11:00"
          and plans[0]["start"] == "2026-10-30T13:00" and cor["doc"]["fields"]["p1.r1"]["value"] == "2026-10-29 09:00")
    check("A3 날짜 거르기는 고친 날짜로: 원래 10-30 → 고쳐 10-29면 후보, 원래 10-29 → 고쳐 10-31이면 아님",
          [i for i, _ in link.candidates(fields, plans, [0, 1], saved)] == [0] and [i for i, _ in link.candidates(fields, plans, [0, 1])] == [1])
    real_inputs = analyze.inputs
    analyze.inputs = lambda f, a, *x, **k: ([("F1", "p1.job", "허가서", "작업내용", "E41P 블록 상부 러그 절단")], {}, {"no": 1})
    try:
        critique._CACHE.clear()
        llm.call_json = fake({"links": [{"p": "P1", "r": "same_work", "f": "F1", "w": "P1.W1"}]})
        out = asyncio.run(link.suggest(fields, plans, [0, 1], saved, open_qs=[TQ]))
        L = (out.get("links") or [{}])[0]
        imp = {x["item"]: x for x in L.get("imports") or []}
        check("A3 가져올 시간은 고친 계획서 값(10/29 09:00~11:00), 원래 값(13:00~15:00) 아님",
              out["status"] == "ok" and L["plan"] == 0 and imp.get("T1", {}).get("value") == "10/29 09:00~11:00")
        check("A3 근거 칸·범위도 같은 수정본에서", L["scope"]["when"].startswith("2026-10-29 09:00"))
        check("A3 연결 다이제스트는 고친 계획서의 것(다시 고치면 달라짐)", L["digest"] == workplan.plan_digest(plans[0], saved["0"])
              != workplan.plan_digest(plans[0], {**saved["0"], "p1.r2": "2026-10-29 12:00"}))
    finally:
        analyze.inputs = real_inputs


def sample_permit():
    """the 4-day permit of the foreman test set (10-27…10-30, 08:00~16:59 every day) and its T1 question"""
    from foreman_permits import FOREMAN
    from server import extract
    from server.permit_kinds import KINDS
    d = next(d for d in FOREMAN if "T1" in d["asked"])
    name = f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf"
    F = extract.build(ROOT / "samples/반장_테스트" / name, d["kind"])["fields"]
    return F, next(q for q in augment.summary(F, [])["questions"] if q["item"] == "T1")


def dated_time():
    """A4: a plan's time goes with its day, to that day only; a plan of a day not on the permit brings no time"""
    F, q = sample_permit()
    days = sorted(augment.summary(F, [])["effective"][0]["windows"])
    check("A4 시험 허가서는 여러 날(10-27~10-30)", days == ["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30"])
    notes = []
    imp = link.imports(F, {"start": "2026-10-29T09:00", "end": "2026-10-29T11:00"}, "same_work", [q], notes)
    check("A4 가져올 시간에 날짜가 붙음(10/29 09:00~11:00), 들어갈 곳은 그날 행", len(imp) == 1 and imp[0]["value"] == "10/29 09:00~11:00"
          and "3일차" in imp[0]["dest"] and not notes)
    w = augment.summary(F, [{"qid": q["qid"], "choice": "partial", "value": imp[0]["value"], "q": q}])["effective"][0]["windows"]
    check("A4 가져온 시간은 10-29에만, 다른 작업일은 적힌 시간 그대로", w == {"2026-10-27": ["08:00~16:59"], "2026-10-28": ["08:00~16:59"],
                                                         "2026-10-29": ["09:00~11:00"], "2026-10-30": ["08:00~16:59"]})
    w = augment.summary(F, [{"qid": q["qid"], "choice": "partial", "value": "09:00~11:00", "q": q}])["effective"][0]["windows"]
    check("A4 날짜 없이 반장이 적은 시간은 전과 같이 모든 작업일에", set(w) == set(days) and all(v == ["09:00~11:00"] for v in w.values()))
    notes = []
    imp = link.imports(F, {"start": "2026-10-31T09:00", "end": "2026-10-31T11:00"}, "same_work", [q], notes)
    check("A4 허가서 작업일에 없는 날(10-31)의 계획서 시간은 가져오지 않고 이유를 남김", imp == [] and len(notes) == 1
          and "10/31" in notes[0] and "가져오지 않음" in notes[0])


def expired_import():
    """A3: after a link, a correction of its plan makes the values it brought stop counting on the server (rules,
    analysis, submission) until confirmed again; the same words typed again later are the foreman's own"""
    from server import app as webapp, store
    F, q = sample_permit()
    sid, tok = store.create(), "c" * 32
    rec = plan_rec("E41P 러그 절단", "2026-10-29 09:00", "2026-10-29 11:00")
    (workplan.CACHE / tok).mkdir(parents=True, exist_ok=True)
    (workplan.CACHE / tok / "plans.json").write_text(json.dumps([rec], ensure_ascii=False), encoding="utf-8")
    v = "10/29 09:00~11:00"
    store.put_job(sid, f"link:{tok}:0", "confirmed", {"plan": 0, "token": tok, "rel": "same_work", "digest": workplan.plan_digest(rec, {}),
                                                      "imports": [{"qid": q["qid"], "choice": "partial", "value": v, "at": 5000}]})
    a = {"qid": q["qid"], "choice": "partial", "value": v, "q": q, "at": 5000}
    s = webapp._augment(F, [a], sid, store.revision(sid))
    check("A3 연결 직후 가져온 값은 반장 답으로 셈", not s["dropped"] and not any(x["item"] == "T1" for x in s["questions"])
          and s["effective"][0]["windows"]["2026-10-29"] == ["09:00~11:00"])
    workplan.save_edits(tok, {"0": {"p1.r2": "2026-10-29 12:00"}})          # the plan corrected again after the link
    s = webapp._augment(F, [a], sid, store.revision(sid))
    check("A3 연결 뒤 계획서를 고치면 서버가 가져온 값을 빼고 다시 묻는다", q["qid"] in s["dropped"] and any(x["item"] == "T1" for x in s["questions"])
          and s["effective"][0]["windows"]["2026-10-29"] == ["08:00~16:59"])
    check("A3 그 만료를 한 번 알림(작업계획서 수정)", (s.get("expired") or {}).get("plan") and s["expired"]["lost"][0]["qid"] == q["qid"])
    rev = store.revision(sid)
    got, _, dropped = webapp._calc_answers([], sid, F, rev, write=False)
    check("A3 제출·체크리스트 경로(읽기 전용)에서도 그 값은 확정 답 아님", not any(x["qid"] == q["qid"] for x in got) and q["qid"] in dropped)
    got, _, _ = webapp._unlinked(sid, *store.current(sid, F, rev))
    check("A3 분석이 읽는 답에도 없음", not any(x["qid"] == q["qid"] for x in got))
    s = webapp._augment(F, [dict(a, at=9000)], sid, store.revision(sid))
    check("A3 반장이 나중에 같은 값을 직접 다시 적으면 그의 답으로 셈", not s["dropped"] and not any(x["item"] == "T1" for x in s["questions"]))
    store.put_job(sid, f"link:{tok}:0", "confirmed", {"plan": 0, "token": tok, "rel": "same_work",
                                                      "digest": workplan.plan_digest(rec, workplan.load_edits(tok)["0"]),
                                                      "imports": [{"qid": q["qid"], "choice": "partial", "value": v, "at": 5000}]})
    s = webapp._augment(F, [a], sid, store.revision(sid))
    check("A3 바뀐 계획서로 다시 확인(그대로 둠)하면 다시 셈", not s["dropped"] and not any(x["item"] == "T1" for x in s["questions"]))


def main():
    real = llm.call_json
    try:
        # CRITIQUE: only the proposals that could lower a signal are looked at again
        CALLS.clear(); critique._CACHE.clear()
        llm.call_json = fake({"v": "supports"})
        yes = prop("yes", "다른 작업은 없어요")
        out, held = asyncio.run(critique.review({}, SRC, [yes], sid=None))
        check("「있음」 같은 부정이 아닌 제안은 검사하지 않음(모델 안 부름)", out == [yes] and not held and not CALLS)
        no = prop("no", "같은 시간에 다른 작업은 없어요")
        out, held = asyncio.run(critique.review({}, SRC, [no], sid=None))
        check("부정 제안 + supports → 그대로(반장이 확인)", out == [no] and not held and CALLS == [("CRITIQUE", llm.FG)])
        asyncio.run(critique.review({}, SRC, [no], sid=None))
        check("같은 문장·같은 해석은 한 번만 검사(캐시)", len(CALLS) == 1)
        critique._CACHE.clear()
        for v in ("not_supported", "unclear"):
            llm.call_json = fake({"v": v})
            critique._CACHE.clear()
            out, held = asyncio.run(critique.review({}, SRC, [no], sid=None))
            check(f"부정 제안 + {v} → 확인 카드에서 빼고 「{critique.HELD}」", out == [] and held and held[0]["why"] == critique.HELD)
        critique._CACHE.clear()
        llm.call_json = fake(llm.LlmFail("timeout"))
        out, held = asyncio.run(critique.review({}, SRC, [prop("na", "다른 작업은 없어요")], sid=None))
        check("검사 실패 → 보류(자동 확정 없음)", out == [] and held and held[0]["critique"] == "fail")
        llm.call_json = fake({"v": "maybe"})
        out, held = asyncio.run(critique.review({}, SRC, [no], sid=None))
        check("약속 밖 답 → 보류", out == [] and held)
        check("실패는 캐시하지 않음", ("said", "같은 시간에 다른 작업은 없어요.", critique.claim(no)) not in critique._CACHE)
        # one deadline for the reading and its checks: no time left, the negations are held unchecked
        critique._CACHE.clear(); CALLS.clear()
        llm.call_json = fake({"v": "supports"})
        out, held = asyncio.run(critique.review({}, SRC, [no, prop("na", "다른 작업은 없어요")], sid=None, deadline=1.0))
        check("남은 시간이 없으면 부정 제안은 검사 없이 보류(통과시키지 않음)", out == [] and len(held) == 2
              and all(h["critique"] == "late" for h in held) and not CALLS)
        out, held = asyncio.run(critique.review({}, SRC, [no], sid=None, deadline=30.0))
        check("남은 시간 안에서는 그대로 검사", out == [no] and not held and CALLS == [("CRITIQUE", llm.FG)])
        critique._CACHE.clear()
        ok_, v = asyncio.run(critique.relation("A 장비: OH-21-02", "B 장비: OH-21-02", "같은 설비를 함께 쓰는 관계"))
        check("관계 대조는 서버 틀로 한 번(지지할 때만 유지)", ok_ and v == "supports" and ("relation", "A 장비: OH-21-02 / B 장비: OH-21-02",
                                                                                  "같은 설비를 함께 쓰는 관계") in critique._CACHE)
        check("해석 문장은 서버 틀(질문 → 보기)", critique.claim(no) == "같은 시간·장소에 다른 작업이 있나요? → 없음")

        # LINK
        fields = {"p1.date": {"name": "작업일자", "value": "2026-10-29"}, "p1.job": {"name": "작업내용", "value": "E41P 블록 상부 러그 절단"}}
        plan = lambda title, start, extra="": {"start": start, "doc": {"fields": {
            "w.title": {"name": "작업명", "value": title}, "w.sign": {"name": "작성자 서명", "value": "홍길동"},
            "w.loc": {"name": "작업장소", "value": f"3BAY 12칼럼 {extra}"}}}}
        plans = [plan("E41P 블록 러그 절단", "2026-10-29"), plan("E41P 블록 도장", "2026-10-30"), plan("E52S 블록 용접", "2026-10-29"),
                 plan("E41P 반전", "2026-10-29", "OH-21-03"), plan("E41P 취부", "2026-10-29"), plan("E41P 검사", "2026-10-29")]
        cand = link.candidates(fields, plans, [0, 1, 2, 3, 4, 5])
        check("후보는 번호를 함께 쓰는 같은 날 계획서만, 최대 3개", [i for i, _ in cand] == [0, 3, 4] and len(cand) <= link.MAX_CAND)
        check("다른 날(10-30) 계획서는 후보 아님", 1 not in [i for i, _ in cand])
        real_inputs = analyze.inputs
        analyze.inputs = lambda f, a, *x, **k: ([("F1", "p1.job", "허가서", "작업내용", "E41P 블록 상부 러그 절단")], {}, {"no": 1})
        try:
            seen = {}

            def reply(messages):
                seen["text"] = messages[-1]["content"]
                return {"links": [{"p": "P1", "r": "same_work", "f": "F1", "w": "P1.W1"}]}
            CALLS.clear()
            llm.call_json = fake(reply)
            out = asyncio.run(link.suggest(fields, plans, [0, 3, 4]))
            check("같은 작업 + 양쪽 근거 → 연결 제안", out["status"] == "ok" and out["links"][0]["plan"] == 0 and out["links"][0]["rel"] == "same_work")
            check("서명·작성자 칸은 모델에게 주지 않음", "홍길동" not in seen["text"] and "서명" not in seen["text"])
            check("연결은 미리 계산 순서(PREPARED), 관계 대조 한 번", CALLS == [("LINK", llm.PREPARED), ("CRITIQUE", llm.PREPARED)])
            critique._CACHE.clear()
            llm.call_json = fake(reply, v="unclear")
            out = asyncio.run(link.suggest(fields, plans, [0, 3, 4]))
            check("관계 대조가 지지하지 않으면 연결 제안 없음(근거 부족으로 보류)", out["links"] == [] and out["held"]
                  and out["why"] == critique.HELD_REL)
            critique._CACHE.clear()
            llm.call_json = fake({"links": [{"p": "P1", "r": "same_work", "f": "F1", "w": "P2.W1"}]})
            check("다른 계획서의 칸을 근거로 대면 연결 안 함", asyncio.run(link.suggest(fields, plans, [0, 3, 4]))["status"] == "none")
            llm.call_json = fake({"links": [{"p": "P1", "r": "different", "f": "F1", "w": "P1.W1"}]})
            check("different → 연결 안 함", asyncio.run(link.suggest(fields, plans, [0, 3, 4]))["links"] == [])
            llm.call_json = fake(llm.LlmFail("timeout"))
            out = asyncio.run(link.suggest(fields, plans, [0, 3, 4]))
            check("모델 실패 → 연결하지 않음(fail)", out["status"] == "fail" and out["links"] == [])
            llm.call_json = fake({"links": "x"})
            check("형식 밖 답 → 연결하지 않음", asyncio.run(link.suggest(fields, plans, [0]))["status"] == "fail")
            CALLS.clear()
            out = asyncio.run(link.suggest(fields, plans, [2]))
            check("번호를 함께 쓰는 후보가 없으면 모델 안 부름", out["status"] == "none" and not CALLS)
            analyze.inputs = lambda f, a, *x, **k: ([("F1", "p1.job", "허가서", "작업내용", "도장 준비")], {}, {"no": 1})
            llm.call_json = fake({"links": [{"p": "P1", "r": "same_work", "f": "F1", "w": "P1.W2"}]})
            check("두 칸이 같은 말을 하나도 안 하면 연결 안 함", asyncio.run(link.suggest(fields, plans, [0]))["links"] == [])
        finally:
            analyze.inputs = real_inputs
        corrected_plan()
        dated_time()
        expired_import()
    finally:
        llm.call_json = real
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
