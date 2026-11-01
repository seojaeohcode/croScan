"""규칙 밖 「AI 검토 권장」 (server/pairreview, design §8.2) and 판정보류 담당별 질문 (server/holdq, §8.3).

  python tools/check_pairreview.py      # the demo day (samples/시연_하루); a fake model; a throwaway database
"""
import asyncio
import copy
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_pairreview_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import holdq, llm, pairreview, pairs, safety, store  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def fake(reply, v="supports"):
    """the model made up: the pair review's reply, and the relation check's verdict"""
    async def call(kind, messages, schema, **kw):
        fake.seen.append((kind, kw.get("pri"), messages))
        return ({"v": v} if kind == "CRITIQUE" else reply), {"ms": 1}
    return call


fake.seen = []


def main():
    D = safety.data()
    det = pairs.detect()
    before = copy.deepcopy(det)
    ids = [d["id"] for d in D["permits"] + D["plans"]]
    raised = {frozenset((p["a"], p["b"])) for p in det["pairs"]}
    # ---- §8.2 prefilter
    far = None
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if frozenset((a, b)) in raised:
                continue
            try:
                pairreview.prefilter(det, a, b)
            except pairreview.Refused:
                far = (a, b)
                break
        if far:
            break
    check("시간·위치·설비가 이어지지 않는 쌍은 검토 거절", far is not None)
    rp = det["pairs"][0]
    out = asyncio.run(pairreview.review(det, rp["a"], rp["b"]))
    check("규칙 경보가 있는 쌍은 AI 검토 대상이 아님", out["status"] == "refused" and "규칙" in out["why"])
    near = det["near"][0]
    X, Y, close = pairreview.prefilter(det, near["a"], near["b"])
    check("근접 쌍은 통과하고 이어진 까닭이 남음", close)
    ra = pairreview._rows(X, 1)
    rb = pairreview._rows(Y, len(ra) + 1)
    real = llm.call_json
    try:
        llm.call_json = fake({"rel": "shared_equipment", "a": ra[0][0], "b": rb[0][0], "ask": "Q_EQUIP"})
        out = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("모델은 관계·행·질문만 고르고 문장은 서버 틀(양쪽 근거)", out["status"] == "ok" and len(out["evidence"]) == 2
              and out["evidence"][0]["doc"] == near["a"] and out["evidence"][1]["doc"] == near["b"] and out["label"] == pairreview.LABEL
              and out["text"].startswith(out["evidence"][0]["no"]))
        check("검토 요청은 사람이 부른 순서(ASKED)로", [p for k, p, _ in fake.seen if k == "PAIR_REVIEW"][-1:] == [llm.ASKED])
        check("관계는 양쪽 행과 한 번 대조(CRITIQUE)한 뒤에만 권장", [k for k, _, _ in fake.seen][-2:] == ["PAIR_REVIEW", "CRITIQUE"])
        n0 = len(fake.seen)
        check("거꾸로 물어도 같은 쌍(a|b 정렬, 다시 묻지 않음)", asyncio.run(pairreview.review(det, near["b"], near["a"])) == out
              and len(fake.seen) == n0)
        pairreview._CACHE.clear()
        pairreview.critique._CACHE.clear()
        llm.call_json = fake({"rel": "shared_equipment", "a": ra[0][0], "b": rb[0][0], "ask": "Q_EQUIP"}, v="not_supported")
        held = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("대조가 지지하지 않으면 권장이 아니라 「근거 부족으로 보류」(질문·문장 없음)", held["status"] == "held"
              and held["why"] == pairreview.critique.HELD_REL and not held.get("text") and not held["question"])
        # Codex persona A12: one deadline for the review and its CRITIQUE (the screen's 「최대 60초」); too little left → 보류
        pick = {"rel": "shared_equipment", "a": ra[0][0], "b": rb[0][0], "ask": "Q_EQUIP"}
        dl = []

        async def slow(kind, messages, schema, **kw):
            fake.seen.append((kind, kw.get("pri"), messages))
            dl.append((kind, kw.get("deadline")))
            if kind == "PAIR_REVIEW":
                await asyncio.sleep(0.3)
                return pick, {"ms": 300}
            return {"v": "supports"}, {"ms": 1}
        app_js = (Path(__file__).resolve().parent.parent / "web" / "app.js").read_text(encoding="utf-8")
        check("화면의 최대 시간 = 서버의 총기한(60초)", pairreview.DEADLINE == 60 and f"최대 {int(pairreview.DEADLINE)}초" in app_js)
        pairreview._CACHE.clear()
        pairreview.critique._CACHE.clear()
        real_dl, pairreview.DEADLINE = pairreview.DEADLINE, 10.0
        llm.call_json = slow
        ok10 = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        dd = dict(dl)
        check("검토와 CRITIQUE가 한 기한을 나눠 씀(CRITIQUE는 남은 시간만)", ok10["status"] == "ok" and dd.get("PAIR_REVIEW") == 10.0
              and dd.get("CRITIQUE") is not None and dd["CRITIQUE"] <= 10.0 - 0.3)
        pairreview._CACHE.clear()
        pairreview.critique._CACHE.clear()
        pairreview.DEADLINE, dl[:] = pairreview.critique.MIN_LEFT, []          # the review leaves less than a check needs
        late = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("남은 시간이 모자라면 확인 없이 보여 주지 않고 보류(문장·질문 없음, CRITIQUE 부르지 않음)", late["status"] == "held"
              and late.get("critique") == "late" and late["why"] == pairreview.critique.HELD_LATE and not late.get("text")
              and not late["question"] and [k for k, _ in dl] == ["PAIR_REVIEW"])
        sa, sb = sorted((near["a"], near["b"]))
        check("시간 부족 보류는 보관하지 않음(다시 물으면 새로 검토)·상태는 실패", not any(k[1:3] == (sa, sb) for k in pairreview._CACHE)
              and pairreview.states(det).get(f"{sa}|{sb}", {}).get("state") == "fail")
        pairreview.DEADLINE = real_dl
        again = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("시간이 있으면 다시 물어 대조 후 권장", again["status"] == "ok")
        pairreview._FAIL.clear()
        pairreview._CACHE.clear()
        pairreview.critique._CACHE.clear()
        llm.call_json = fake({"rel": "shared_equipment", "a": ra[0][0], "b": rb[0][0], "ask": "Q_EQUIP"})
        pairreview._CACHE.clear()
        llm.call_json = fake({"rel": "shared_equipment", "a": rb[0][0], "b": rb[1][0], "ask": "Q_EQUIP"})
        out = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("A 근거가 B 작업의 행이면 쓰지 않음(양쪽 근거 필수)", out["status"] == "none" and not out["evidence"])
        pairreview._CACHE.clear()
        llm.call_json = fake({"rel": "same_path", "a": ra[0][0], "b": rb[0][0], "ask": "Q_AIR"})
        out = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("관계에 맞지 않는 질문은 관계의 질문으로", out["status"] == "ok" and out["ask"] == "Q_PATH")
        n = len(fake.seen)
        out2 = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("같은 쌍·같은 서류는 다시 묻지 않음(캐시)", out2 == out and len(fake.seen) == n)
        pairreview._CACHE.clear()
        llm.call_json = fake({"rel": "none", "a": "", "b": "", "ask": ""})
        out = asyncio.run(pairreview.review(det, near["a"], near["b"]))
        check("못 찾으면 「관계 없음」이 아니라 「찾지 못함」", out["status"] == "none" and "뜻은 아님" in out["why"])
        pairreview._CACHE.clear()
        llm.call_json = fake({"rel": "overhead", "a": ra[0][0], "b": rb[0][0], "ask": "Q_OVERHEAD"})
        got = asyncio.run(pairreview.batch(det, 2))
        check("미리 검토(batch)는 가장 낮은 순서(WARM)로, 건수 보고", fake.seen[-1][1] == llm.WARM and got["done"] <= 2 and got["candidates"] >= got["done"])
        L = pairreview.listing(det["date"], det)
        check("목록은 따로 세고 규칙 판정과 섞이지 않음", L["count"]["all"] >= 1 and L["count"]["targets"] >= L["count"]["all"]
              and all(x["key"] not in {p["key"] for p in det["pairs"]} for x in L["items"]))
        k0 = next(k for k in pairreview._CACHE if k[0] == det["date"])
        pairreview._CACHE[(k0[0], k0[1], k0[2], "olddigest")] = {**pairreview._CACHE.pop(k0)}
        check("서류가 바뀐 뒤(다른 다이제스트)의 옛 결과는 목록에 없음", all((x["a"], x["b"]) != (k0[1], k0[2])
                                                         for x in pairreview.listing(det["date"], det)["items"]))
        check("못 돌린 대상 수도 지금 대상 기준으로 셈", pairreview.listing(det["date"], det)["count"]["not_run"] >= 1)
        # the states of the current targets (§19.1: 미분석/대기 중/처리 중/실패/검토 완료) and the 20-pair batch
        st = pairreview.states(det)
        check("대상마다 상태가 있고 말은 정해진 다섯 가지", st and all(v["ko"] in pairreview.STATE_KO.values() for v in st.values()))
        check("미리 검토 배치 크기는 20(제외 기준이 아님)", pairreview.BATCH == 20 and pairreview.batch.__defaults__ == (20,))
        pairreview._CACHE.clear()
        pairreview.critique._CACHE.clear()
        calls = {"n": 0}

        async def flaky(kind, messages, schema, **kw):
            fake.seen.append((kind, kw.get("pri"), messages))
            if kind == "PAIR_REVIEW":
                calls["n"] += 1
                if calls["n"] == 1:                                # the first try fails: tried once more at the end
                    raise llm.LlmFail("timeout", "x")
                return {"rel": "none", "a": "", "b": "", "ask": ""}, {"ms": 1}
            return {"v": "supports"}, {"ms": 1}
        llm.call_json = flaky
        got = asyncio.run(pairreview.batch(det, 1))
        check("미리 검토에서 실패한 쌍은 한 번 더 시도", calls["n"] == 2 and got["done"] == 1 and got["failed"] == 0)
        first = pairreview.targets(det)[0]
        check("검토한 쌍은 「검토 완료」", pairreview.states(det)[f"{first[0]}|{first[1]}"]["state"] == "done")
        pairreview._CACHE.clear()

        async def always_fail(kind, messages, schema, **kw):
            raise llm.LlmFail("down", "x")
        llm.call_json = always_fail
        asyncio.run(pairreview.batch(det, 1))
        check("두 번 다 실패하면 「실패」(이 서류에 대해)", pairreview.states(det)[f"{first[0]}|{first[1]}"]["state"] == "fail")
        pairreview._CACHE.clear()
        pairreview._FAIL.clear()

        async def preempt(kind, messages, schema, **kw):
            if kind == "PAIR_REVIEW" and not preempt.done:
                preempt.done = True
                asyncio.current_task().cancel()                    # a person's call took the slot (llm._Slot cancels the holder)
                await asyncio.sleep(0)
            return ({"rel": "none", "a": "", "b": "", "ask": ""} if kind == "PAIR_REVIEW" else {"v": "supports"}), {"ms": 1}
        preempt.done = False
        llm.call_json = preempt
        got = asyncio.run(pairreview.batch(det, 1))
        check("사람에게 자리를 내준(취소된) 미리 검토는 끝에 다시 함", got["done"] == 1 and got["failed"] == 0)
        L = pairreview.listing(det["date"], det)
        check("목록 머리: 검토 완료 N / 대상 M (권장·없음·보류와 미분석·대기·실패를 나눠 셈)",
              {"done", "targets", "ok", "none", "held", "not_run", "waiting", "running", "fail"} <= set(L["count"])
              and L["count"]["done"] + L["count"]["not_run"] + L["count"]["fail"] + L["count"]["waiting"] + L["count"]["running"] == L["count"]["targets"])
    finally:
        llm.call_json = real
    check("AI 검토 뒤에도 규칙 쌍·순위·점수가 그대로", det == before and pairs.detect()["pairs"] == before["pairs"])
    # ---- §8.3 per-side questions
    docs = {d["id"]: d for d in D["permits"] + D["plans"]}
    A, B, Cc = ids[0], ids[1], ids[2]
    r_gas = {"rule": "CONF_GAS", "cause": A, "exposed": B, "E": 1, "gaps": ["경로가 생기려면 사건이 하나 더 있어야 함(재통전·같은 시각 배차·주행 구간 겹침 등)"]}
    got = holdq._asks(r_gas, docs)
    check("차단 측은 계통·복구, 진입 측은 환기·진입 계획을 자기 작업으로", (A, "gas_line") in [(i, f) for i, f, _ in got] and (B, "vent_entry") in [(i, f) for i, f, _ in got])
    r_seq = {"rule": "TARGET_OCCUPIED", "cause": A, "exposed": B, "E": 1, "sequence": {"gap": 40, "first": "B"},
             "gaps": ["작업 시간은 겹치지 않지만, 앞 작업이 끝나고 40분 뒤 시작: 잔류위험(잔불·증기·가스·잔압·잔류 인원)이 없어졌다는 확인 기록이 없음"]}
    got = {(i, f) for i, f, _ in holdq._asks(r_seq, docs)}
    check("선후 쌍: 먼저 끝나는 쪽에 종료·정리, 뒤 작업에 시작·확인 절차", got == {(B, "end_residual"), (A, "start_check")})
    syn = {"date": det["date"], "pairs": [
        {"key": f"{A}|{B}", "a": A, "b": B, "judgement": "판정보류", "reasons": [r_gas]},
        {"key": f"{A}|{Cc}", "a": A, "b": Cc, "judgement": "판정보류", "reasons": [{**r_gas, "exposed": Cc}]},
        {"key": f"{B}|{Cc}", "a": B, "b": Cc, "judgement": "보수위험", "reasons": [{**r_gas, "cause": B, "exposed": Cc, "E": 2}]}]}
    H = holdq.build(syn)
    qa_ = [q for d in H["docs"] for q in d["questions"]]
    gas = [q for q in qa_ if q["doc"] == A and q["fact"] == "gas_line"]
    check("여러 쌍이 같은 사실을 필요로 하면 한 번만 묻고 쌍을 모두 적음", len(gas) == 1 and set(gas[0]["pairs"]) == {f"{A}|{B}", f"{A}|{Cc}"})
    check("미확인(E1) 사유가 없는 쌍은 질문을 만들지 않음", not any(f"{B}|{Cc}" in q["pairs"] for q in qa_))
    up = {"date": det["date"], "pairs": [{"key": f"{B}|{Cc}", "a": B, "b": Cc, "judgement": "확인위험",
                                          "reasons": [{**r_gas, "rule": "FIRE", "cause": B, "exposed": Cc, "E": 3, "gaps": []},
                                                      {**r_gas, "cause": B, "exposed": Cc, "floor": "gone"}]}]}
    check("다른 사유로 확인위험이 된 쌍도 남은 판정보류 사유의 질문은 그대로", any(f"{B}|{Cc}" in q["pairs"] for d in holdq.build(up)["docs"]
                                                               for q in d["questions"]))
    titles = {i: docs[i].get("title") or "" for i in ids}
    cross = [q for q in qa_ if any(o != q["doc"] and (o in q["text"] or (titles[o] and titles[o] in q["text"])) for o in ids)
             or re.search(r"(상대|다른)\s*(?:팀|작업)[^.]*(?:완료|끝났)", q["text"])]
    msgs = "\n".join(d["message"] for d in H["docs"])
    check("한쪽 반장에게 상대 작업·완료를 확답시키지 않음(문안·질문)", not cross and not re.search(r"(상대|다른)\s*(?:팀|작업)[^\n]*(?:완료|끝났)", msgs))
    check("문안은 반장별로, 질문 번호와 함께", all(d["message"].count("\n1. ") == 1 for d in H["docs"]) and H["count"]["미전달"] == len(qa_))
    real_det = det
    hold = holdq.build(real_det)
    check("시연 하루의 판정보류 쌍에도 담당별 질문이 생김", hold["count"]["questions"] >= 2 and len(hold["docs"]) >= 2)
    k = gas[0]["key"]
    try:
        holdq.mark(syn, k, "응답 받음")
        check("미전달에서 바로 응답 받음은 거절", False)
    except holdq.HoldError as e:
        check("미전달에서 바로 응답 받음은 거절", e.status == 409)
    check("「전달함 표시」를 눌러야 전달함(croScan은 보내지 않음)", holdq.mark(syn, k, "전달함")["state"] == "전달함")
    check("응답 받음으로", holdq.mark(syn, k, "응답 받음")["state"] == "응답 받음")
    check("상태는 저장되어 다시 불러와도 같음", next(q for d in holdq.build(syn)["docs"] for q in d["questions"] if q["key"] == k)["state"] == "응답 받음")
    # the work changed: a new question, the old marks shown as history, not carried over
    real_data = holdq.safety.data
    try:
        D2 = copy.deepcopy(D)
        for d in D2["permits"] + D2["plans"]:
            if d["id"] == A:
                d["place"] = (d.get("place") or "") + " (변경)"
        holdq.safety.data = lambda: D2
        q2 = next(q for d in holdq.build(syn)["docs"] for q in d["questions"] if q["doc"] == A and q["fact"] == "gas_line")
        check("작업이 바뀌면 새 질문(상태 승계 없음), 이전 표시는 이력으로", q2["key"] != k and q2["state"] == "미전달"
              and [h["state"] for h in q2["history"]] == ["응답 받음"])
    finally:
        holdq.safety.data = real_data
    # the permit's own budget is shared
    sid = store.create()
    for i in range(store.ASKS):
        store.issue(sid, f"Q{i}", "question")
    real_s = holdq._session_of
    try:
        holdq._session_of = lambda no, day: sid
        k2 = next(q["key"] for q in qa_ if q["doc"] == B)
        got = holdq.mark(syn, k2, "전달함")
        check("질문 한도를 다 써도 전달 사실은 기록하고 「반장 대화 질문 한도 밖」 표시", got["state"] == "전달함"
              and got["flag"] == "반장 대화 질문 한도 밖" and store.budget(sid)["used"] == store.ASKS)
        holdq.mark(syn, k2, "미전달")
        with holdq._db() as c:
            c.execute("UPDATE marks SET counted=NULL WHERE key=?", (k2,))
        sid2 = store.create()
        holdq._session_of = lambda no, day: sid2
        u0 = store.budget(sid2)["used"]
        holdq.mark(syn, k2, "전달함")
        check("열린 검토면 그 검토의 질문 예산으로 셈", store.budget(sid2)["used"] == u0 + 1)
        holdq.mark(syn, k2, "미전달")
        holdq.mark(syn, k2, "전달함")
        check("되돌렸다 다시 표시해도 두 번 세지 않음", store.budget(sid2)["used"] == u0 + 1)
        store.close_review(sid2)
        u1 = store.budget(sid2)["used"]
        k3 = next(q["key"] for q in qa_ if q["doc"] == Cc)
        got = holdq.mark(syn, k3, "전달함")
        check("마무리한 검토면 전달은 기록하고 「검토 마감 뒤 전달」 표시(그 검토에 새 질문을 열지 않음, 따로 세는 장부 없음)",
              got["state"] == "전달함" and got["flag"] == "검토 마감 뒤 전달" and store.budget(sid2)["used"] == u1)
        with holdq._db() as c:
            check("별도 장부(hold) 없음", not c.execute("SELECT 1 FROM marks WHERE counted='hold'").fetchone())
    finally:
        holdq._session_of = real_s
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
