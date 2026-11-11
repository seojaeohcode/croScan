"""체크리스트 AI 추가 위험요인 (server/checkai, design §7): catalog items only, the work's own words, nothing changed in
the base list, nothing added until the foreman puts it in.

  python tools/check_checkai.py      # the demo permits (samples/시연_하루); the model is replaced by a fake
"""
import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_ckai_")      # a throwaway database
from server import augment, checkai, checklist, extract, llm, store, submissions  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def fake(reply, calls=None):
    async def call(kind, messages, schema, **kw):
        if calls is not None:
            calls.append((kind, messages, schema, kw))
        if isinstance(reply, Exception):
            raise reply
        return reply, {"ms": 1}
    return call


def main():
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))              # 고소: 「블록 상부 임시 러그 절단·제거」
    fields = extract.build(DIR / "허가서" / permit_name(d), d["kind"])["fields"]
    P = augment.effective(fields, [])[0]
    base = checklist.draft(fields, [])
    before = [dict(x) for x in base["permits"][0]["items"]]
    cands = checkai.candidates(P["kind"], base["permits"][0]["items"], checkai.facts(P, []))     # as _run chooses them
    ids = [it["id"] for _, it in cands]
    check("후보는 다른 작업 종류의 카탈로그 항목만(이 허가서 목록·공통 제외)", ids and all(not i.startswith(("height_", "common_")) for i in ids))
    check("후보는 제목이 겹치지 않음", len({checkai._norm(it["title"]) for _, it in cands}) == len(cands))
    # Codex review #4: relevance first — an item the work speaks of is reachable whatever the catalog order
    reach = [("hot", ["작업명: 블록 외판 가우징, 그라인더 사상", "유해위험요소: 소음, 불티"], "height_noise"),
             ("height", ["작업명: 블록 상부 러그 가우징 제거", "유해위험요소: 소음, 불티, 잔불"], "hot_noise"),
             ("height", ["작업명: 블록 상부 러그 가우징 제거", "유해위험요소: 잔불, 불씨"], "hot_embers"),
             ("loto", ["작업명: 제어반 부스바 교체, 아크 용접 브래킷", "유해위험요소: 아크광, 감전"], "hot_arc"),
             ("hot", ["작업명: 탱크 내부 보강 용접", "유해위험요소: 폭염, 더운 내부 열사병"], "confined_heat"),
             ("lifting", ["작업명: 블록 반출 인양", "유해위험요소: 밀폐 탱크 내부 잔류 인원 질식"], "confined_watch")]
    for kk, ln, want in reach:
        got = [it["id"] for _, it in checkai.candidates(kk, checklist.items_for(kk), ln)]
        check(f"{kk} 허가서 「{ln[1]}」 → 후보에 {want}", want in got)
    check("AI 보관 키에 카탈로그·후보 정책이 들어감(명세 버전만으로 예전 결과를 쓰지 않음)",
          checkai.CATALOG and checkai.POLICY and checkai._key(P, ["x"]) != "checkai:" + checkai.digest([checklist.SPEC.get("version", 1), P["kind"], "x"]))
    # the catalog grew (2026-10-31 material reinforcement): every other kind is still offered within the limit
    for kk in checklist.SPEC["kinds"]:
        cc = checkai.candidates(kk, checklist.items_for(kk))
        check(f"{kk} 허가서 후보에 다른 네 작업 종류가 모두 들어감(한도 {checkai.MAX_CANDIDATES})",
              {k for k, _ in cc} == set(checklist.SPEC["kinds"]) - {kk} and len(cc) <= checkai.MAX_CANDIDATES)
    lines = checkai.facts(P, [])
    check("작업 사실에 작업명이 들어감", any("러그 절단" in x for x in lines))
    ci = lambda iid: f"C{ids.index(iid) + 1}"
    hot = next(i for i in ids if i.startswith("hot_spark") or i.startswith("hot_"))

    items, dropped = checkai.check([{"c": ci(hot), "quote": "임시 러그 절단"}], cands, lines)
    check("작업 사실의 구절·그 종류의 말(절단) → 추가 후보", [x["id"] for x in items] == ["A:" + hot] and items[0]["state"] == "check")
    check("후보는 확인 전(touched 없음)·근거 구절이 이유에", "touched" not in items[0] and "임시 러그 절단" in items[0]["reasons"][0])
    _, dr = checkai.check([{"c": ci(hot), "quote": "러그 용접 보수"}], cands, lines)
    check("작업 사실에 없는 구절은 버림", dr and dr[0][1] == "구절이 작업 사실에 없음")
    _, dr = checkai.check([{"c": "C99", "quote": "임시 러그 절단"}], cands, lines)
    check("후보 밖 id는 버림", dr and dr[0][1] == "후보가 아님")
    _, dr = checkai.check([{"c": ci(hot), "quote": "블록 상부"}], cands, lines)
    check("그 작업 종류의 말이 없는 구절은 버림(블록 상부 → 화기 아님)", dr and dr[0][1] == "그 작업 종류의 말이 구절에 없음")
    neg = ["작업명: 블록 상부 러그 정리", "반장 답(추가정보): 가스 절단은 하지 않음"]
    _, dr = checkai.check([{"c": ci(hot), "quote": "가스 절단은 하지 않음"}], cands, neg)
    check("하지 않는다는 문장은 근거가 아님", dr and dr[0][1] == "하지 않는다는 문장")
    oth = ["작업명: 블록 상부 러그 정리", "반장 답(추가정보): 옆 팀이 용접함"]
    _, dr = checkai.check([{"c": ci(hot), "quote": "옆 팀이 용접함"}], cands, oth)
    check("다른 팀 이야기는 근거가 아님", dr and dr[0][1] == "다른 팀 이야기")

    real = llm.call_json
    try:
        calls = []
        llm.call_json = fake({"picks": [{"c": ci(hot), "quote": "임시 러그 절단"}, {"c": "C1", "quote": "없는 말"}]}, calls)
        sid = store.create()
        out = asyncio.run(checkai.suggest(fields, [], sid))
        check("모델 결과 중 검사 통과한 것만", out["status"] == "ok" and [x["id"] for x in out["items"]] == ["A:" + hot])
        check("모델 호출은 준비 작업 순위(PREPARED)", calls and calls[0][3].get("pri") == llm.PREPARED)
        check("기본 체크리스트는 그대로", [dict(x) for x in checklist.draft(fields, [])["permits"][0]["items"]] == before)
        if sid:
            n = len(calls)
            again = asyncio.run(checkai.suggest(fields, [], sid))
            check("같은 작업 사실이면 모델을 다시 부르지 않음", len(calls) == n and again["items"] == out["items"])
            sent = {"permits": [{"permit_no": P["permit_no"], "items": [{"id": "A:" + hot, "basis": out["items"][0]["basis"], "auto": "check",
                                                                        "state": "yes", "touched": True, "controls": [], "quote": "임시 러그 절단"}]}]}
            got = checkai.attach(checklist.draft(fields, []), sid, fields, [], sent)
            check("넣은 AI 항목은 초안 항목으로 붙음(기본 항목 유지)", [x["id"] for x in got["permits"][0]["items"]] == [x["id"] for x in before] + ["A:" + hot])
            check("붙은 AI 항목의 근거는 지금 작업 사실로 다시 만든 것(같은 사실이면 같음)", got["permits"][0]["items"][-1]["basis"] == out["items"][0]["basis"])
            # #5: a later model result without it does not take it out; it is checked against the work as it is now
            llm.call_json = fake({"picks": []})
            keep = [{"id": "A:" + hot, "quote": "임시 러그 절단"}]
            ans2 = [{"qid": "L2:" + P["permit_no"], "choice": "text", "value": "블록 상부 3번 러그 쪽", "q": {}}]
            later = asyncio.run(checkai.suggest(fields, ans2, sid, keep=keep))
            k = later["kept"].get("A:" + hot) or {}
            check("새 모델 결과에 없어도 넣은 항목은 남음(지금 작업으로 다시 확인)", later["items"] == [] and k.get("ok") and k["item"]["id"] == "A:" + hot)
            check("작업이 바뀌면 넣은 항목의 근거가 바뀜(재확인 필요)", k.get("item", {}).get("basis") != out["items"][0]["basis"])
            gone = asyncio.run(checkai.suggest(fields, [], sid, keep=[{"id": "A:" + hot, "quote": "러그 용접 보수"}]))
            g = gone["kept"].get("A:" + hot) or {}
            check("근거 구절이 작업에 없으면 「재확인 필요」로 보고(지우지 않음)", g.get("ok") is False and g.get("why") == "구절이 작업 사실에 없음")
            try:
                checkai.attach(checklist.draft(fields, []), sid, fields, [], {"permits": [{"permit_no": P["permit_no"], "items": [
                    {"id": "A:" + hot, "basis": "x", "state": "yes", "touched": True, "quote": "러그 용접 보수"}]}]})
                check("근거 구절이 없어진 넣은 항목은 제출 거절(빼거나 반장 항목으로 유지)", False)
            except checkai.Stale:
                check("근거 구절이 없어진 넣은 항목은 제출 거절(빼거나 반장 항목으로 유지)", True)
            d2 = checkai.attach(checklist.draft(fields, ans2), sid, fields, ans2, sent)
            try:
                submissions.confirm_checklist(d2, {"permits": [{"permit_no": P["permit_no"], "items": [
                    {**x, "touched": True, "state": x["auto"], "controls": []} for x in before] + sent["permits"][0]["items"]}]})
                check("작업이 바뀐 뒤 예전 근거로 확인한 항목은 제출 거절(checklist_changed)", False)
            except submissions.Refused as e:
                check("작업이 바뀐 뒤 예전 근거로 확인한 항목은 제출 거절(checklist_changed)", e.code == "checklist_changed")
            check("보관 키에 명세 판·허가 종류가 들어감", checkai._key(P, lines) != checkai._key({**P, "kind": "hot"}, lines))
            bad = {"permits": [{"permit_no": P["permit_no"], "items": [{"id": "A:" + hot, "basis": "xxxx", "auto": "check", "state": "yes", "touched": True}]}]}
            try:
                checkai.attach(checklist.draft(fields, []), sid, fields, [], bad)
                check("근거가 다른 AI 항목은 거절", False)
            except checkai.Stale:
                check("근거가 다른 AI 항목은 거절", True)
            check("넣지 않으면 초안 그대로", checkai.attach(checklist.draft(fields, []), sid, fields, [], {"permits": []})["permits"][0]["items"] == before)
        # #3: every item's basis stands on the work facts (not only on croScan's own reasons)
        b0 = {x["id"]: x["basis"] for x in checklist.draft(fields, [])["permits"][0]["items"]}
        job = next(k for k, f in fields.items() if isinstance(f, dict) and f.get("key", k) == "job" or k == "job")
        f2 = {**fields, job: {**fields[job], "value": str(fields[job].get("value", "")) + " 크레인 OH-21-02 아래에서 용접"}}
        b1 = {x["id"]: x["basis"] for x in checklist.draft(f2, [])["permits"][0]["items"]}
        check("작업 내용이 바뀌면 모든 항목의 근거가 바뀜(예전 확인 만료)", b0.keys() == b1.keys() and all(b0[i] != b1[i] for i in b0))
        who = next((k for k, f in fields.items() if isinstance(f, dict) and checklist.PEOPLE.search(str(k)) and str(f.get("value") or "").strip()), None)
        if who:
            f3 = {**fields, who: {**fields[who], "value": str(fields[who].get("value")) + "x"}}
            check("사람 이름·연락처만 바뀌면 근거 그대로", {x["id"]: x["basis"] for x in checklist.draft(f3, [])["permits"][0]["items"]} == b0)
        a1 = [{"qid": "L2:" + P["permit_no"], "choice": "text", "value": "블록 상부", "q": {}}]
        check("작업을 설명하는 반장 답(위치)이 바뀌면 모든 항목의 해당 여부 근거가 바뀜", all(b0[x["id"]] != x["basis"] for x in checklist.draft(fields, a1)["permits"][0]["items"]))
        # design §7: only the confirmation that stands on what changed expires
        c0 = {x["id"]: x["basis_ctl"] for x in checklist.draft(fields, [])["permits"][0]["items"]}
        t1 = [{"qid": "T1:" + P["permit_no"], "choice": "partial", "value": "13:00~15:00", "q": {}}]
        d_t = {x["id"]: x for x in checklist.draft(fields, t1)["permits"][0]["items"]}
        check("시간 답만 바뀌면 해당 여부·안전조치 근거 그대로", all(d_t[i]["basis"] == b0[i] and d_t[i]["basis_ctl"] == c0[i] for i in b0))
        d_a = {x["id"]: x for x in checklist.draft(fields, a1)["permits"][0]["items"]}
        check("위치 답은 안전조치 근거를 바꾸지 않음(작업 방법·장비 그대로)", sum(d_a[i]["basis_ctl"] == c0[i] for i in c0) >= len(c0) - 2)
        c2 = {x["id"]: x["basis_ctl"] for x in checklist.draft(f2, [])["permits"][0]["items"]}
        check("작업 방법·장비 말이 바뀌면 안전조치 근거가 바뀜", all(c2[i] != c0[i] for i in c0))
        srcs = [s for x in checklist.draft(fields, [])["permits"][0]["items"] for s in x["sources"]]
        check("근거마다 출처(서류/반장 답)", srcs and set(srcs) <= {"서류", "반장 답", "서류·반장 답"})
        b3 = [{"qid": "B3:" + P["permit_no"], "choice": "yes", "value": "도장팀", "q": {}}]
        mx = {x["id"]: x for x in checklist.draft(fields, b3)["permits"][0]["items"]}.get("common_mixed")
        check("반장 답으로 정한 근거는 「반장 답」", mx and mx["state"] in ("yes", "check") and any("반장 답" in s for s in mx["sources"]))
        # #30 (design §7 table): the same call reads the base items — support / conflict with the work's words; it never
        # changes a state; a 「해당 없음」 where the words show the hazard is chosen again (submissions)
        bitems = [x for x in before]
        bi = lambda iid: f"B{[x['id'] for x in bitems].index(iid) + 1}"
        L2 = lines + ["반장 답(추가정보): 사다리는 쓰지 않음", "반장 답(추가정보): 옆 팀이 그라인더 작업"]
        mk, mdr = checkai.check_marks([{"b": bi("height_spark"), "m": "support", "quote": "임시 러그 절단", "k": ["height_spark_c1", "hot_spark_c1"]},
                                       {"b": bi("height_fall"), "m": "conflict", "quote": "사다리는 쓰지 않음"},
                                       {"b": bi("height_crane"), "m": "support", "quote": "대조립21공장"},
                                       {"b": bi("height_fume"), "m": "support", "quote": "옆 팀이 그라인더 작업"},
                                       {"b": bi("common_mixed"), "m": "support", "quote": "사다리는 쓰지 않음"},
                                       {"b": "B99", "m": "support", "quote": "임시 러그 절단"}], bitems, L2)
        check("근거 구절·그 항목의 말 → support, 조치는 그 항목의 것만", mk.get("height_spark", {}).get("m") == "support"
              and mk["height_spark"]["controls"] == ["height_spark_c1"] and mk["height_spark"]["src"] == "서류")
        check("하지 않는다는 말 → conflict(반장 답 출처)", mk.get("height_fall", {}).get("m") == "conflict" and mk["height_fall"]["src"] == "반장 답")
        why = {d_[0]: d_[1] for d_ in mdr}
        check("그 항목의 말이 없는 구절은 버림", why.get("height_crane") == "그 항목의 말이 구절에 없음")
        check("다른 팀 이야기는 버림", why.get("height_fume") == "다른 팀 이야기")
        check("하지 않는다는 문장을 support로는 못 씀", why.get("common_mixed") in ("하지 않는다는 문장", "그 항목의 말이 구절에 없음"))
        check("목록 밖 항목은 버림", why.get("B99") == "항목이 아님")
        # staging use 2026-10-31: 「병행·혼재작업」 stands on another team's work; a quote with its field's name is the field's words
        mk2, mdr2 = checkai.check_marks([{"b": bi("common_mixed"), "m": "support", "quote": "옆 팀이 그라인더 작업"}], bitems, L2)
        check("병행·혼재작업 항목은 다른 팀 작업이 곧 근거", mk2.get("common_mixed", {}).get("m") == "support")
        named = next((ln for ln in lines if ": " in ln and not ln.startswith("반장 답")), "")
        nm, _, val = named.partition(": ")
        check("칸 이름을 붙인 인용(「칸: 값」)도 그 칸의 말로 찾음", bool(val) and checkai._clause(f"{nm}: {val[:12]}", lines) != "")
        s2 = store.create()
        calls2 = []
        llm.call_json = fake({"picks": [], "marks": [{"b": bi("height_spark"), "m": "support", "quote": "임시 러그 절단", "k": []}]}, calls2)
        o2 = asyncio.run(checkai.suggest(fields, [], s2))
        check("한 번의 CHECKLIST 호출로 추가 후보와 기본 항목 읽기", len(calls2) == 1 and calls2[0][0] == "CHECKLIST" and "marks" in calls2[0][2]["properties"])
        check("기본 항목 읽기는 표시만 — 상태·근거는 그대로", "height_spark" in o2["marks"] and [dict(x) for x in checklist.draft(fields, [])["permits"][0]["items"]] == before)
        check("제출 때는 보관한 읽기만(모델 다시 안 부름)", checkai.marks_cached(s2, fields, []) == o2["marks"] and len(calls2) == 1)
        check("모델이 언급 안 한 항목은 아무 표시 없음(해당 없음으로 안 바꿈)", set(o2["marks"]) == {"height_spark"})
        # Codex persona A10: a quote with its line's name (「반장 답(추가정보): …」) is found and sourced without it
        hq = "반장 답(추가정보): 사다리는 쓰지 않음"
        check("머리말 붙은 인용도 출처는 그 줄(반장 답)", checkai.source(hq, L2) == "반장 답" and checkai._clause(hq, L2) != "")
        mk3, _ = checkai.check_marks([{"b": bi("height_fall"), "m": "conflict", "quote": hq}], bitems, L2)
        check("머리말 붙은 인용의 conflict도 출처 「반장 답」", mk3.get("height_fall", {}).get("src") == "반장 답")
        check("머리말 붙은 서류 칸 인용은 「서류」", named and checkai.source(f"{nm}: {val[:12]}", lines) == "서류")
        L3 = lines + ["반장 답(용접 위치): 블록 상부 3번 기둥 쪽"]
        _, dr3 = checkai.check([{"c": ci(hot), "quote": "반장 답(용접 위치): 블록 상부 3번 기둥 쪽"}], cands, L3)
        check("줄 이름의 말(용접 위치)은 그 작업 종류의 말로 치지 않음", dr3 and dr3[0][1] == "그 작업 종류의 말이 구절에 없음")
        # Codex persona A5: the head count is a work fact — 작업인원 3→5 expires the 해당 여부 and the 안전조치 confirmations;
        # a time-only change on the permit expires none; a kept AI suggestion is served on the basis of the work now
        wk = next(k for k, f in fields.items() if isinstance(f, dict) and (f.get("key", k) == "workers" or k == "workers"))
        fw3 = {**fields, wk: {**fields[wk], "value": "3"}}
        fw5 = {**fields, wk: {**fields[wk], "value": "5"}}
        d3 = {x["id"]: x for x in checklist.draft(fw3, [])["permits"][0]["items"]}
        d5 = {x["id"]: x for x in checklist.draft(fw5, [])["permits"][0]["items"]}
        check("작업인원 3→5: 모든 항목의 해당 여부 근거가 바뀜", all(d3[i]["basis"] != d5[i]["basis"] for i in d3))
        check("작업인원 3→5: 안전조치 근거도 바뀜(작업자별 잠금·인원 대조)", all(d3[i]["basis_ctl"] != d5[i]["basis_ctl"] for i in d3))
        old = {"permits": [{"permit_no": P["permit_no"], "items": [{**x, "touched": True, "ctl_touched": True, "state": x["auto"], "controls": []}
                                                                    for x in d3.values()]}]}
        try:
            submissions.confirm_checklist(checklist.draft(fw5, []), old)
            check("인원이 바뀐 뒤 예전 확인으로 제출하면 거절(checklist_changed)", False)
        except submissions.Refused as e:
            check("인원이 바뀐 뒤 예전 확인으로 제출하면 거절(checklist_changed)", e.code == "checklist_changed")
        tk = next(k for k, f in fields.items() if isinstance(f, dict) and re.fullmatch(r"(?:from|to)_1", str(f.get("key", k))))
        ft = {**fw3, tk: {**fw3[tk], "value": "13:00"}}
        dt = {x["id"]: x for x in checklist.draft(ft, [])["permits"][0]["items"]}
        check("서류의 시간만 바뀌면 해당 여부·안전조치 근거 그대로", all(dt[i]["basis"] == d3[i]["basis"] and dt[i]["basis_ctl"] == d3[i]["basis_ctl"] for i in d3))
        s3, calls3 = store.create(), []
        llm.call_json = fake({"picks": [{"c": ci(hot), "quote": "임시 러그 절단"}],
                              "marks": [{"b": bi("height_spark"), "m": "support", "quote": "임시 러그 절단", "k": []}]}, calls3)
        o3 = asyncio.run(checkai.suggest(fw3, [], s3))
        o5 = asyncio.run(checkai.suggest(fw5, [], s3))
        check("인원만 바뀌면 같은 작업 말이라 모델을 다시 부르지 않음", len(calls3) == 1 and [x["id"] for x in o5["items"]] == ["A:" + hot])
        put5 = checkai.attach(checklist.draft(fw5, []), s3, fw5, [], {"permits": [{"permit_no": P["permit_no"], "items": [
            {"id": "A:" + hot, "quote": o5["items"][0]["quote"]}]}]})["permits"][0]["items"][-1]
        check("보관 후보는 지금 작업의 근거로 제시(제출 때 다시 확인 요구 없음)", o5["items"][0]["basis"] == put5["basis"]
              and o5["items"][0]["basis_ctl"] == put5["basis_ctl"] and o5["items"][0]["basis"] != o3["items"][0]["basis"])
        check("보관한 기본 항목 읽기도 지금 사실로 다시 확인해 제시", o5["marks"] == checkai.marks_cached(s3, fw5, []) and "height_spark" in o5["marks"])
        stale = {"status": "ok", "items": [{**o3["items"][0], "quote": "없는 말"}],
                 "marks": {"height_spark": {**o5["marks"]["height_spark"], "quote": "없는 말"}}}
        P5, base5 = checkai._one(fw5, [])
        nw = checkai._now(stale, P5, base5, checkai.facts(P5, []), [])
        check("지금 사실로 성립하지 않는 보관 후보·읽기는 빼고 제시", nw["items"] == [] and nw["marks"] == {} and nw["status"] == "none")
        llm.call_json = fake(llm.LlmFail("timeout"))
        out = asyncio.run(checkai.suggest(fields, [{"qid": "X:" + P["permit_no"], "choice": "value", "value": "새 사실"}], None))
        check("모델 실패 → 후보 없음(기본 목록만)", out["status"] == "fail" and out["items"] == [])
    finally:
        llm.call_json = real
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
