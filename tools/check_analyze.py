"""업로드 분석의 서버 검사 (server/analyze.check): the model's pointers are made up here, no model is called.

  python tools/check_analyze.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import analyze  # noqa: E402

ROWS = [("F1", "p1.job", "허가서", "작업내용", "블록 내부 보강재 용접 및 그 크레인으로 반출"),
        ("F2", "p1.location", "허가서", "작업장소", "3BAY 08칼럼"),
        ("F3", "p1.job_detail", "허가서", "작업내용(상세)", "론지 균열부 가우징·재용접, 천장크레인 제어반 정비"),
        ("F4", "p1.hazards", "허가서", "위험요인", "안전대 착용"),
        ("W1", "plan:p1.r3", "작업계획서", "작업장소", "3BAY 10칼럼"),
        ("W2", "plan:p1.r4", "작업계획서", "이동 경로", "3BAY 중앙 통로 / 크레인 OH-21-03"),
        ("F5", "p1.department", "허가서", "작업부서", "대조립3부 용접2팀"), ("F6", "p1.location2", "허가서", "작업장소", "대조립3부-용접2팀"),
        ("F7", "p1.job_detail2", "허가서", "작업내용(상세)", "발판 위 높이 2.5m 구간 포함, 그라인딩 후 이동")]
COVERED = {"F2": {"L1"}}


def need(t, f, q, f2="", q2=""):
    return {"t": t, "f": f, "q": q, "f2": f2, "q2": q2}


CASES = [
    ("「그 크레인」 → 가리키는 대상 질문", need("referent", "F1", "그 크레인으로 반출"), "keep"),
    ("가리키는 말이 없는 구절 → 버림", need("referent", "F2", "3BAY 08칼럼"), "drop"),
    ("공간의 「위」(발판 위)는 가리키는 말이 아님 → 버림 (스테이징 실사용 2026-10-31)", need("referent", "F7", "발판 위 높이 2.5m 구간 포함"), "drop"),
    ("「그라인딩」「이동」 안의 그·이는 가리키는 말이 아님 → 버림", need("referent", "F7", "그라인딩 후 이동"), "drop"),
    ("작업이 둘(가우징·재용접) → 범위 질문", need("act_scope", "F3", "론지 균열부 가우징·재용접"), "keep"),
    ("작업이 하나뿐 → 버림", need("act_scope", "F1", "블록 내부 보강재 용접"), "drop"),
    ("「안전대 착용」은 설비가 아님 → 버림 (실측 2026-10-31)", need("dependency", "F4", "안전대 착용"), "drop"),
    ("제어반 정비 → 이어진 설비 질문", need("dependency", "F3", "천장크레인 제어반 정비"), "keep"),
    ("통로·크레인 이름만(멈춤 없음) → 버림 (실측 2026-10-31)", need("dependency", "W2", "3BAY 중앙 통로 / 크레인 OH-21-03"), "drop"),
    ("구절이 칸에 없음 → 버림", need("referent", "F1", "저 크레인으로 반출"), "drop"),
    ("허가서 08칼럼 ↔ 계획서 10칼럼 → 대조 질문", need("doc_mismatch", "F2", "3BAY 08칼럼", "W1", "3BAY 10칼럼"), "keep"),
    ("대조인데 둘째 칸이 없음 → 버림", need("doc_mismatch", "F2", "3BAY 08칼럼"), "drop"),
    ("대조인데 같은 말 → 버림", need("doc_mismatch", "F2", "3BAY 08칼럼", "F2", "3BAY 08칼럼"), "drop"),
    ("붙임표만 다른 말(대조립3부 용접2팀 / 대조립3부-용접2팀) → 버림", need("doc_mismatch", "F5", "대조립3부 용접2팀", "F6", "대조립3부-용접2팀"), "drop"),
]


EXTRA = 8


def fake(reply, seen):
    async def call(kind, messages, schema, **kw):
        seen.append({"kind": kind, "user": messages[-1]["content"], "ids": schema["properties"]["needs"]["items"]["properties"]["f"]["enum"], **kw})
        return reply, {}
    return call


def extra():
    """reference passages (design §3.4) and DISCOVER_DELTA (§1.4), with a made-up model reply"""
    import asyncio
    from server import llm, retrieval
    ok = 0
    P = {"label": "화기", "permit_no": "P-1"}
    rows = [("F1", "p1.job", "허가서", "작업내용", "블록 내부 보강재 용접, 불티 비산 우려"), ("F2", "p1.location", "허가서", "작업장소", "3BAY 08칼럼")]
    refs = analyze.references(rows, P)
    good = 1 <= len(refs) <= 3 and all(r["grade"] in ("법령", "공공") and retrieval.check_cite(r["cite"])[0] for r in refs)
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 업로드 분석 참고 자료: 법령·공공 2~3개, 인용 검사 통과 ({[r['ref'] for r in refs]})")
    block = analyze._ref_block(refs)
    good = "판단 근거 아님" in block and all(f"R{i}" in block for i in range(1, len(refs) + 1)) and "F" not in block.split("\n", 2)[1][:2]
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 참고 자료는 칸이 아닌 R 번호로(모델이 고를 수 있는 f에 없음)")
    h1 = analyze.rowhash(ROWS)
    good = "plan:p1.r3" not in h1 and "p1.job" in h1
    ok += good
    print(f"{'PASS' if good else 'FAIL'} rowhash는 허가서 칸만(계획서 칸은 허가서 편집이 아님)")
    h2 = dict(h1, **{"p1.job": "x"})
    good = analyze.changed(h1, h2) == ["p1.job"] and analyze.changed(h1, h1) == []
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 바뀐 칸만 찾음")
    # delta on a demo permit (8175 고소): only changed fields are given and may be pointed at
    real = llm.call_json
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from server import extract
    from make_demo_day import DIR, load, permit_name
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))
    F = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    rows_now, _, Pn = analyze.inputs(F, [])
    before = analyze.rowhash(rows_now)
    F2 = {**F, "p1.job": {**F["p1.job"], "value": "그 크레인으로 블록 반출, 제어반 정비 및 정전"}}
    seen = []
    try:
        job_id = next(r[0] for r in analyze.inputs(F2, [])[0] if r[1] == "p1.job")
        llm.call_json = fake({"needs": [{"t": "referent", "f": job_id, "q": "그 크레인으로 블록 반출", "f2": "", "q2": ""}]}, seen)
        out = asyncio.run(analyze.delta(F2, [], before))
        good = seen and seen[0]["kind"] == "DISCOVER_DELTA" and seen[0]["ids"] == [job_id] and seen[0].get("pri") == llm.PREPARED
        ok += good
        print(f"{'PASS' if good else 'FAIL'} 변경 구역 재분석: 바뀐 칸만 모델에 줌(준비 작업 순서)")
        good = out["changed"] == ["p1.job"] and out["status"] == "ok" and out["needs"][0]["key"] == "p1.job"
        ok += good
        print(f"{'PASS' if good else 'FAIL'} 바뀐 칸의 애매한 점은 질문 후보")
        seen.clear()
        out = asyncio.run(analyze.delta(F2, [], analyze.rowhash(analyze.inputs(F2, [])[0])))
        good = not seen and out["why"] == "바뀐 칸 없음"
        ok += good
        print(f"{'PASS' if good else 'FAIL'} 바뀐 칸이 없으면 모델을 부르지 않음")
        llm.call_json = fake({"needs": [{"t": "referent", "f": "F1", "q": "그 크레인으로 블록 반출", "f2": "", "q2": ""}]}, seen)
        F3 = {**F2, "p1.location": {**F2["p1.location"], "value": "대조립21공장 3BAY 09칼럼"}}
        seen.clear()
        out = asyncio.run(analyze.delta(F3, [], analyze.rowhash(analyze.inputs(F2, [])[0])))
        loc_id = next(r[0] for r in analyze.inputs(F3, [])[0] if r[1] == "p1.location")
        good = seen[0]["ids"] == [loc_id] and not out["needs"] and out["status"] == "fail"     # F1 (unchanged) is not even a choice
        ok += good
        print(f"{'PASS' if good else 'FAIL'} 바뀌지 않은 칸은 고를 수조차 없음(형식 밖 → 버림)")
    finally:
        llm.call_json = real
    return ok


def main():
    ok = 0
    for name, n, want in CASES:
        got, dropped = analyze.check(ROWS, {}, [n], "P-1")
        res = "keep" if got else "drop"
        good = res == want and (not got or (got[0]["text"] and got[0]["quote"] == n["q"]))
        ok += good
        print(f"{'PASS' if good else 'FAIL'} {name}: {res}" + (f" {dropped}" if not good else ""))
    # a rule question asks the same kind of thing about the field: the rules win
    got, dropped = analyze.check(ROWS, {"F1": {"D2"}}, [need("referent", "F1", "그 크레인으로 반출")], "P-1")
    good = not got and dropped[0][1] == "규칙 질문이 같은 것을 묻는 칸"
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 규칙 질문(D2)이 같은 칸의 대상을 물으면 AI 질문은 버림")
    got, _ = analyze.check(ROWS, {"F1": {"H1"}}, [need("referent", "F1", "그 크레인으로 반출")], "P-1")
    good = len(got) == 1
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 같은 칸이라도 다른 종류(작업 범위 H1)를 묻는 규칙이면 남김")
    # the question is croScan's sentence, never the model's; the schema is checked again
    got, _ = analyze.check(ROWS, {}, [need("referent", "F1", "그 크레인으로 반출")], "P-1")
    good = got[0]["text"].startswith("허가서의 「그 크레인으로 반출」")
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 질문 문장은 검수한 틀")
    ids = [r[0] for r in ROWS]
    bad = [{"needs": [need("referent", "F9", "x")]}, {"needs": [dict(need("referent", "F1", "그"), w=5)]}, {"needs": [need("x", "F1", "그")]},
           {"needs": [need("referent", "F1", "그")] * 3}, {"needs": []}]
    good = [analyze._valid(d, ids) for d in bad] == [False, False, False, False, True]
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 형식 재검사(없는 칸·덧붙인 키·없는 종류·3개)")
    # hidden fields: names, phones, approvals, dates are never given to the model
    good = all(analyze._hidden(k, n) for k, n in (("supervisor_phone", ""), ("date_1", ""), ("x", "허가구분"), ("signer", ""), ("h_doc_no", "")))
    good = good and not analyze._hidden("job", "작업내용")
    ok += good
    print(f"{'PASS' if good else 'FAIL'} 이름·연락처·서명·허가구분·날짜 칸은 모델에 주지 않음")
    # an AI question (weight 4) never comes before a rule question (HT1, weight 3) within the asks
    from server import need_catalog
    ch = [{"id": "gas", "label": "가스절단", "ask": "개수"}]
    qs = [{"qid": "AI1:P", "item": "AI1", "ai_kind": "doc_mismatch", "choices": ch, "prio": 0}, {"qid": "HT1:P", "item": "HT1", "choices": ch, "prio": 5}]
    good = [q["item"] for q in need_catalog.order(qs)] == ["HT1", "AI1"]
    ok += good
    print(f"{'PASS' if good else 'FAIL'} AI 질문은 규칙 질문을 앞지르지 않음(12회 안에서 밀어내지 않음)")
    ok += extra()
    n = len(CASES) + 6 + EXTRA
    print(f"\n{ok}/{n}")
    sys.exit(0 if ok == n else 1)


if __name__ == "__main__":
    main()
