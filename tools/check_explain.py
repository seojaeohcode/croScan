"""요청형 「왜?」의 서버 쪽 (server/explain): claims from a pair, the fixed answers, what a free question may become.

  python tools/check_explain.py        # needs the demo day (samples/시연_하루)
"""
import asyncio
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import explain, llm, pairs, safety  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def fake_model(reply):
    async def call(kind, messages, schema, **kw):
        return reply, {}
    return call


def main():
    det, D = pairs.detect(), safety.data()
    docs = {d["id"]: d for d in D["permits"] + D["plans"]}
    seq = next(p for p in det["pairs"] if p["reasons"][0]["when"]["kind"] == "sequence")
    ov = next(p for p in det["pairs"] if p["reasons"][0]["when"]["kind"] == "overlap")
    c = explain.claims(seq, docs)
    check("겹치지 않는 쌍: 「겹치지 않는데 왜」가 먼저", explain.applicable(seq)[0]["id"] == "seq")
    check("겹치는 쌍에는 「겹치지 않는데 왜」가 없음", "seq" not in [q["id"] for q in explain.applicable(ov)])
    f = explain.fixed(c, "seq")
    check("「겹치지 않는데 왜」: 잔류위험 확인이 「아직 확인할 것」에 있음", any("남는 위험" in u["text"] or "잔류위험" in u["text"] for u in f["left"]))
    check("어떤 질문이든 아직 확인할 것은 전부 보임", explain.fixed(c, "used")["left"] == c["U"])
    # what the judge did not know is passed whole (Codex: 「인원 수가 적혀 있지 않음」 was lost to a word filter)
    p2 = copy.deepcopy(ov)
    p2["reasons"][0]["gaps"] = ["위험을 받는 작업의 인원 수가 적혀 있지 않음"]
    check("판정기의 부족 정보(인원 미상)는 그대로 「아직 확인할 것」", any("인원 수" in u["text"] for u in explain.claims(p2, docs)["U"]))
    for q in ("두 작업 시간을 옮기면 괜찮나요?", "인양을 16시로 변경하면 어떻게 되나요?", "도장을 하루 쉬면 위험이 줄까요?", "한쪽을 취소하면요?"):
        fr, status, why = asyncio.run(explain.ask(c, q, {"seq", "used"}))
        check(f"일정 가정 「{q}」 → 모델 없이 계산하지 않는다고 답함", status == "fixed" and why == "what_if")
    # the model only picks the explanation and the order of facts; the sentences are the server's
    real = llm.call_json
    try:
        llm.call_json = fake_model({"intent": "seq", "facts": ["F3", "F1"]})
        fr, status, why = asyncio.run(explain.ask(c, "블록 안 작업이 끝났는데도 왜 확인하나요?", {"seq", "used"}))
        check("자유 질문 → 서버 문장의 「겹치지 않는데 왜」, 고른 사실이 먼저", status == "ok" and fr["judge"] == explain.fixed(c, "seq")["judge"]
              and [x["id"] for x in fr["facts"][:2]] == ["F3", "F1"])
        llm.call_json = fake_model({"intent": "none", "facts": []})
        fr, status, why = asyncio.run(explain.ask(c, "이 작업 안전한가요?", {"seq", "used"}))
        check("세 가지 밖의 질문 → 범위 안내", status == "fixed" and why == "out_of_scope")
        llm.call_json = fake_model({"intent": "defer", "facts": []})
        fr, status, why = asyncio.run(explain.ask(c, "왜죠?", {"seq", "used"}))
        check("이 쌍에 없는 설명(판정보류)을 고르면 실패로 알림", status == "fail")
    finally:
        llm.call_json = real
    check("근거 보기에는 두 문서", len(c["refs"]) == 2 and all(r["no"] for r in c["refs"]))
    rule = next(r for r in pairs.rules()["rules"] if r["id"] == seq["reasons"][0]["rule"])
    check("조문은 현행본 대조·맞음일 때만", any(r["id"] == "R2" for r in c["R"]) == (rule.get("law_fit") == "맞음"))
    # ---- 설명 검증기 (§5.4): every fixed answer of every pair passes; a changed one falls back to the claims
    allok = all(explain.verify(explain.fixed(cc, q["id"]), cc, docs)[1]["ok"]
                for p in det["pairs"] for cc in [explain.claims(p, docs)] for q in explain.applicable(p))
    check("시연 하루의 모든 쌍·모든 고정 설명이 검증 7항목 통과", allok)
    f = explain.fixed(c, "used")
    bad = {**f, "facts": f["facts"] + [{"id": "F99", "text": "없는 사실"}]}
    out, v = explain.verify(bad, c, docs)
    check("① 제공되지 않은 주장 → 근거 표로 대체", not v["ok"] and not v["checks"][0]["ok"] and out.get("fallback") and out["facts"] == c["F"])
    ev = next((i for i, s in (c.get("src") or {}).items() if s and not s["confirmed"] and s["field"] not in ("시간", "위치")), None)
    if ev:
        s = c["src"][ev]
        d2 = {**docs, s["doc"]: {"id": s["doc"], "type": docs[s["doc"]]["type"], "title": "바뀐 서류"}}   # the document as revised: the value is gone
        _, v = explain.verify(f, c, d2)
        check("② 지금 서류에 없는 값을 쓴 설명은 통과하지 않음", not v["checks"][1]["ok"])
    _, v = explain.verify({**f, "judge": "999점 · 1순위: x."}, c, docs)
    check("③ 규칙 결과와 다른 점수 → 통과하지 않음", not v["checks"][0]["ok"] or not v["checks"][2]["ok"])
    _, v = explain.verify({**f, "facts": f["facts"][:1] + [{"id": "F1", "text": "안전합니다"}]}, c, docs)
    check("④ 「안전합니다」 같은 변환은 통과하지 않음", not v["ok"])
    _, v = explain.verify({**f, "left": f["left"][:-1]}, c, docs)
    check("⑤ 아직 확인할 것이 빠지면 통과하지 않음", not c["U"] or not v["checks"][4]["ok"])
    _, v = explain.verify({**f, "rev": "old"}, c, docs)
    check("⑥ 다른 판의 판정에 기댄 설명은 통과하지 않음", not v["checks"][5]["ok"])
    out, v = explain.verify({**f, "facts": [{**f["facts"][0], "text": f["facts"][0]["text"]}]}, c, docs)
    check("⑦ 글자 값만(꺾쇠는 비슷한 글자로)", all("<" not in x["text"] for x in out["facts"]) and v["checks"][6]["ok"])
    # ---- 설명 대상 확장 (§5.2): checklist item, 반영본 change, revision, question — fixed, verified
    it = {"id": "hot_spark", "title": "불티가 아래·틈새로 번져 화상·화재", "why": "용접·용단 불티가", "auto": "yes", "state": "yes",
          "reasons": ["작업내용: 러그 가스절단"], "ref": "HW02-SPARK", "touched": False,
          "controls": [{"id": "c1", "text": "불티 차단덮개", "on": False}]}
    cc = explain.checklist(it, "0735")
    fr, v = explain.verify(explain.frame_of(cc), cc)
    check("체크리스트 「왜?」: 근거→항목→조치, 해당인데 조치 없음·미확인·이행은 현장", v["ok"] and any("근거: 작업내용" in x["text"] for x in fr["facts"])
          and any("조치가 없습니다" in u["text"] for u in fr["left"]) and any("현장에서" in u["text"] for u in fr["left"]))
    ch = explain.change({"name": "작업인원", "original": "", "final": "3명", "text": "3명", "mode": "fill", "src": ["반장 답(확인함)"]}, None, "0735")
    fr, v = explain.verify(explain.frame_of(ch), ch)
    check("반영본 변경 「왜?」: 이전→이후·방식·근거, 원본은 그대로", v["ok"] and "빈칸" in fr["judge"] and "3명" in fr["judge"] and fr["facts"])
    ex = explain.change(None, ("감시인 계획", "감시인 1명 밖"), "0735")
    check("별지로 간 까닭", "별지" in explain.frame_of(ex)["judge"])
    rv = explain.revision([{"qid": "A1.T1:0735", "slot": "실제 작업시간"}])
    check("개정 「왜?」: 바뀐 것과 다시 확인할 것", "다시 확인" in explain.frame_of(rv)["judge"] and explain.frame_of(rv)["left"])
    qq = explain.question({"item": "L3", "text": "아래에서 하는 작업이 있나요?"}, {"observe": "하부 작업 미기재", "need": "위아래로 겹치는 작업을 보려고 묻습니다", "basis": []})
    check("질문 「왜?」: 관측·필요 이유", explain.verify(explain.frame_of(qq), qq)[1]["ok"] and "관측" in explain.frame_of(qq)["facts"][0]["text"])
    # ---- 서류상 선후 계획 · 남은 확인 (§8.4): display only
    det2 = copy.deepcopy(det)
    pairs.annotate(det2, docs)
    sp = [p for p in det2["pairs"] if p.get("seq_plan")]
    check("선후 쌍에는 「서류상 선후 계획 · 남은 확인」(고정 제목·남은 확인)", sp and all(p["seq_plan"]["title"] == pairs.SEQ_TITLE and p["seq_plan"]["left"] for p in sp)
          and any(p["reasons"][0]["when"]["kind"] == "sequence" for p in sp))
    check("선후 표시는 경보·순위·점수를 바꾸지 않음", [(p["key"], p["priority"], p["score"], p["E"]) for p in det2["pairs"]]
          == [(p["key"], p["priority"], p["score"], p["E"]) for p in det["pairs"]])
    check("완료·해제로 쓰지 않음(남은 확인에 실제 완료·합의)", all(any("실제 완료" in x for x in p["seq_plan"]["left"]) and any("합의" in x for x in p["seq_plan"]["left"]) for p in sp))
    said = pairs._said_seq({"title": "도장 완료 후 진입", "detail": ""})
    check("서류에 적힌 선후 구절(「…완료 후」)도 찾음", said and "완료 후" in said)
    # ---- the query endpoint (once the app patch is in)
    try:
        from fastapi.testclient import TestClient
        from server import app as A
        routes = {r.path for r in A.app.routes}
        if "/api/explanations/query" in routes:
            tc = TestClient(A.app)
            r = tc.post("/api/explanations/query", json={"target": {"kind": "pair", "key": seq["key"]}, "which": "used"})
            check("설명 질의(쌍): 검증 결과와 함께", r.status_code == 200 and r.json()["verify"]["ok"])
            r = tc.post("/api/explanations/query", json={"target": {"kind": "revision", "qids": ["A1.T1:0735"]}})
            check("설명 질의(개정)", r.status_code == 200 and r.json()["verify"]["ok"])
            r = tc.post("/api/explanations/query", json={"target": {"kind": "bogus"}})
            check("모르는 대상은 422", r.status_code == 422)
        else:
            print("SKIP 설명 질의 API (app.py 패치 적용 전)")
    except ImportError:
        print("SKIP 설명 질의 API (fastapi 없음)")
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
