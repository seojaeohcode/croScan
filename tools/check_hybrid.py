"""쌍 하이브리드 (design §8.1): a foreman's confirmed answers go into the rule inputs; the alarms before and after.

  python tools/check_hybrid.py        # needs the demo day (samples/시연_하루)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import pairs, safety  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def ans(item, choice, value="", **kw):
    q = {"choices": [{"id": "gas", "label": "가스절단"}, {"id": "text", "label": "입력"}]}
    return {"qid": f"{item}:P", "choice": choice, "value": value, "q": q, **kw}


def main():
    f = pairs.confirmed_facts
    check("HT1 「가스절단」 선택 + 개수 4 → 화기(SPARK)", [(x["item"], x.get("tag")) for x in f([ans("HT1", "gas", "4")])] == [("HT1", "SPARK")])
    check("다른 팀 이야기(LI2 「블록 내부 다른 팀이 가스절단 중」)는 입력 안 됨", f([ans("LI2", "text", "블록 내부 다른 팀이 가스절단 중")]) == [])
    check("인원 칸 답(B1.workers)·AI 질문 답은 입력 안 됨", f([ans("B1.workers", "value", "우리 3명, 옆 팀 가스절단"), ans("AI1", "text", "용접할 수도 있음")]) == [])
    check("「아르곤 가스 안 씀」은 불활성가스가 아님", f([ans("H2", "text", "아르곤 가스 안 씀")]) == [])
    check("「아르곤 퍼지」는 불활성가스(INERT)", [x.get("tag") for x in f([ans("CF2", "text", "아르곤 퍼지 라인 V-12 차단")])] == ["INERT"])
    got = f([ans("D2", "text", "OH-21-02 사용, OH-21-03 미사용")])
    check("크레인: 쓰는 것만(「미사용」 절의 번호는 뺌)", [x["ids"] for x in got] == [("crane_use", "OH-21-02")])
    check("「모름」·「해당 없음」·다른 팀 읽기는 입력 안 됨", f([ans("HT1", "unknown"), ans("HT1", "na"), ans("D2", "text", "OH-21-01", pid="x", who="other")]) == [])
    D = safety.data()
    P = next(p for p in D["permits"] if p["kind"] in ("height", "lifting") and not pairs.profile(p)["tags"].get("SPARK"))
    facts = f([ans("HT1", "gas", "4")])
    prof = pairs.profile({**P, "_confirmed": facts})
    check("확인된 「가스절단」이 그 허가서의 SPARK 태그로(출처 표시)", any(x.startswith(pairs.CONFIRMED) for x, _ in prof["tags"].get("SPARK", [])))
    lift = pairs.profile({**P, "_confirmed": f([ans("LI1", "text", "OH-21-02 한 대, 반전 없음")])})
    check("확인된 크레인에서 생긴 인양(LIFT)도 출처가 남음", any(x.startswith(pairs.CONFIRMED) for x, _ in lift["tags"].get("LIFT", [])))
    base = pairs.detect()
    after = pairs.detect(confirmed={P["permit_no"]: facts})
    c = pairs.compare(base, after, {P["id"]: facts})
    mine = [x for x in c["new"] + c["kept"] if P["id"] in (x["cause"], x["exposed"])]
    check("보강 뒤 그 허가서가 낀 새 경보가 있음", any(x for x in c["new"] if P["id"] in (x["cause"], x["exposed"])))
    check("행마다 변경을 만든 확인 사실(문서·답)이 붙음", mine and all(x["from"] and x["from"][0]["doc"] == P["id"] for x in mine))
    check("점수·순위는 규칙 값 그대로(AI 점수 없음)", all(set(x["after"]) == {"priority", "S", "E", "score"} for x in mine if x["after"]))
    check("확인 사실이 없으면 전후가 같음", pairs.compare(base, pairs.detect(confirmed={})) == {"new": [], "kept": [], "gone": []})
    gone = pairs.compare(base, {"pairs": base["pairs"][1:]}, {base["pairs"][0]["a"]: facts})["gone"]
    check("사라진 경보는 기록에 남고 그 쌍의 확인 사실이 붙음", gone and gone[0]["after"] is None and gone[0]["from"])
    # a reading never lifts or lowers an alarm (pairs.floor): what the documents raise stays, at the documents' level
    import copy
    first = base["pairs"][0]
    fl = pairs.floor(base, {**base, "pairs": base["pairs"][1:]})
    kept = next((p for p in fl["pairs"] if p["key"] == first["key"]), None)
    check("답으로 사라진 쌍도 현재 목록에 문서 기준으로 남음", kept and kept["priority"] == first["priority"] and all(r.get("floor") == "gone" for r in kept["reasons"]))
    check("현재 쌍 수는 문서 기준보다 줄지 않음", fl["stats"]["pairs"] >= base["stats"]["pairs"])
    weak = copy.deepcopy(base)
    r0 = weak["pairs"][0]["reasons"][0]
    r0.update(priority=3, score=1)
    fl = pairs.floor(base, weak)
    p0 = next(p for p in fl["pairs"] if p["key"] == first["key"])
    check("답으로 낮아진 경보는 문서의 순위·점수 유지", p0["priority"] == first["priority"] and p0["score"] == first["score"]
          and any(r.get("floor") == "lowered" for r in p0["reasons"]))
    fl = pairs.floor(base, after)
    keys = lambda D: {(p["key"], r["rule"], r["cause"], r["exposed"]) for p in D["pairs"] for r in p["reasons"]}
    check("보강 뒤 목록 ⊇ 문서 기준 목록 ∪ 새 경보", keys(fl) >= keys(base) | keys(after))
    best = lambda D: {(p["key"], r["rule"], r["cause"], r["exposed"]): (r["priority"], -r["score"]) for p in D["pairs"] for r in p["reasons"]}
    b, a2 = best(base), best(fl)
    check("어느 경보도 문서 기준보다 순위·점수가 낮아지지 않음", all(a2[k] <= v for k, v in b.items()))
    submitted_cases(D, base, keys, best)
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


def submitted_cases(D, base, keys, best):
    """Codex A6: the latest submission's confirmed place and times go in through the same path (floor keeps the
    documents' alarms); a submission whose number is not in the day's list is listed apart, never dropped"""
    day = D["date"]
    p32 = next(p for p in D["permits"] if p["id"] == "0732")
    no = p32["permit_no"]
    ans = [{"qid": f"L1:{no}", "choice": "place", "value": "3BAY 08-10 칼럼 E42P 블록 상부"},
           {"qid": f"T2:{no}", "choice": "partial", "value": "13:00~14:00"}]
    vals = safety.submitted_values({"fields": p32["_fields"], "answers": ans}, day, no)
    check("제출본 답의 위치·이날 시간 정정을 읽음", vals == {"place": "3BAY 08-10 칼럼 E42P 블록 상부", "windows": [{"start": "13:00", "end": "14:00"}]})
    check("정정이 없으면 아무것도 넣지 않음(서류 기준)", safety.submitted_values({"fields": p32["_fields"], "answers": []}, day, no) == {})
    check("「모름」 위치 답은 정정이 아님", safety.submitted_values({"fields": p32["_fields"], "answers": [
        {"qid": f"L1:{no}", "choice": "unknown", "value": "모름"}]}, day, no) == {})
    raw = pairs.detect(submitted={"0732": vals})
    fl = pairs.floor(base, raw)
    p = next((x for x in fl["pairs"] if x["key"] == "0732|WP-1029-01"), None)
    check("제출본 위치·시간으로 새 경보가 생김(0732 × 같은 블록 도장)", p and any(r["rule"] == "FIRE" for r in p["reasons"]))
    ev = [e for e in (p or {"reasons": [{"evidence": []}]})["reasons"][0]["evidence"] if e["doc"] == "0732"]
    check("근거에 「위치(제출본 반영)」「시간(제출본 반영)」 표시", {e["field"] for e in ev if e.get("submitted")} == {"위치(제출본 반영)", "시간(제출본 반영)"})
    check("제출본 반영 뒤에도 서류 기준 경보는 모두 남음(floor)", keys(fl) >= keys(base) and all(best(fl)[k] <= v for k, v in best(base).items()))
    away = pairs.detect(submitted={"0731": {"place": "1BAY 01-02 칼럼 B10S 블록", "windows": [{"start": "06:00", "end": "07:00"}]}})
    fl2 = pairs.floor(base, away)
    c01 = next((x for x in fl2["pairs"] if x["key"] == "0731|WP-1029-01"), None)
    # 2026-10-31: 0731의 작업명에 블록 E42P가 그대로 있어, 위치만 옮긴 제출본에서도 같은 블록 관계(잔류 3순위)가 남을 수 있음
    # (자료 p398~399: 명시적 연결이 거친 주소보다 우선). 확인하는 것은 floor의 계약: 문서 기준 경보가 모두 남고 낮아지지 않음
    b01 = next(p for p in base["pairs"] if p["key"] == "0731|WP-1029-01")
    now = {(r["rule"], r["cause"], r["exposed"]): (r["priority"], -r["score"]) for r in (c01 or {"reasons": []})["reasons"]}
    check("제출본이 작업을 옮겨도 서류의 경보는 문서 기준으로 남음", c01 and all(
        now.get((r["rule"], r["cause"], r["exposed"]), (9, 0)) <= (r["priority"], -r["score"]) for r in b01["reasons"]))
    check("읽을 수 없는 시간은 넣지 않음", pairs._submitted(p32, {"windows": [{"start": "25:00", "end": "x"}]}) is p32 or "_sub" not in pairs._submitted(p32, {"windows": [{"start": "25:00", "end": "x"}]}))
    # the submissions of the day, as the manager's view gets them (a fake store: id -> (payload, files, summary))
    pno_out = no[:-4] + "0701"
    store_ = {"s1": ({"fields": p32["_fields"], "answers": ans}, {}, {}), "s2": ({"answers": []}, {}, {}),
              "s3": ({"answers": [], "plan_values": [{"doc_no": "WP-1029-02", "place": "3BAY 08-10 칼럼 E42P 블록", "start": f"{day}T13:00",
                                                      "end": f"{day}T14:00", "changed": ["location", "start"]}]}, {}, {})}
    get = store_.get
    s = lambda i, pn, dates, t: {"id": i, "permit_no": pn, "dates": dates, "created": t, "files": ["permit", "checklist"]}  # noqa: E731
    latest_day = {no: s("s1", no, [day], 2), pno_out: s("s2", pno_out, [day], 3)}
    conf, sub, ver = safety.hybrid_inputs(D, latest_day, get)
    check("작업 목록 안의 제출본: 위치·시간이 판정 입력으로", sub.get("0732") == vals and ver["0732"]["version"] == safety.VERSION_SUB
          and ver["0732"]["used"][:2] == ["위치", "시간"])
    check("작업 목록 밖 번호(0701)는 판정 입력에 넣지 않음", not any(k.endswith("0701") for k in list(conf) + list(sub)))
    p33 = next(p for p in D["permits"] if p["id"] == "0733")
    _, sub3, ver3 = safety.hybrid_inputs(D, {p33["permit_no"]: s("s3", p33["permit_no"], [day], 4)}, get)
    check("제출본에서 고친 작업계획서의 위치·시간도 그 계획서의 판정 입력으로", sub3.get("WP-1029-02", {}).get("place") == "3BAY 08-10 칼럼 E42P 블록"
          and sub3["WP-1029-02"]["windows"] == [{"start": "13:00", "end": "14:00"}] and ver3["WP-1029-02"]["by"] == "0733")
    check("제출본에 반영할 값이 없으면 「서류 기준」", ver3["0733"]["version"] == safety.VERSION_DOC)
    other = s("s9", no, ["2026-11-02"], 9)
    view = safety.submission_view(D, latest_day, {**latest_day, no: other}, get)
    out = {x["permit_no"]: x for x in view["_outside"]}
    check("0701 제출은 「이 날 작업 목록에 없는 제출」로 문서와 함께 따로 표시", out.get(pno_out, {}).get("why") == safety.OUTSIDE
          and out[pno_out]["files"] == ["permit", "checklist"] and pno_out not in view)
    check("같은 번호의 다른 작업일 제출도 버리지 않고 따로 표시", out.get(no, {}).get("id") == "s9" and out[no]["why"] == safety.OTHER_DAY
          and view[no]["id"] == "s1" and view[no]["used"]["version"] == safety.VERSION_SUB)
    check("제출 안내: 작업 목록에 없는 번호는 연결 안 됨으로", safety.placement(pno_out, [day]) == {"day": day, "listed": False}
          and safety.placement(no, [day]) == {"day": day, "listed": True} and not safety.placement(no, ["2026-11-02"])["listed"])


if __name__ == "__main__":
    main()
