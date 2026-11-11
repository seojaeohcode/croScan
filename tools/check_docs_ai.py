"""문서·계획서 AI (design §6.3~6.5, §2.3): raw cell readings kept, reading links (MAP_CELL) offered and applied only
when confirmed, link relations and the values a link may bring, a link's plan digest, 허가 검토 신호, 관리자 요약,
게시 문안 보충 (WRITE: the model picks, the server writes).

  python tools/check_docs_ai.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_docs_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import docsum, link, llm, mapcell, pairs, permitsignal, posting, safety, workplan  # noqa: E402

OK = []
CALLS = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def fake(reply):
    async def call(kind, messages, schema, **kw):
        CALLS.append((kind, kw.get("pri")))
        if isinstance(reply, Exception):
            raise reply
        return (reply(messages) if callable(reply) else reply), {}
    return call


def main():
    real = llm.call_json
    try:
        # §6.4 raw readings: a label printed twice with two values keeps both readings, the first stays the value
        P = workplan._Plan("a.pdf")
        P.put("작업 일정과 범위", "작업명", "러그 절단", 1, "odl", "r1")
        P.put("작업 일정과 범위", "작업명", "러그 절단·회수", 2, "text", "r2")
        it = P.items[0]
        check("같은 칸 두 번: 값은 처음 것, 원시 읽기는 둘 다 보존", it["value"] == "러그 절단" and [r["value"] for r in it["raw"]] == ["러그 절단", "러그 절단·회수"])
        rec = {"items": [{"label": "작업명", "key": "title", "value": "러그 절단"}, {"label": "착수 예정", "key": None, "value": "2026-10-29 13:00", "page": 1},
                         {"label": "투입 인력", "key": None, "value": "4명", "page": 1}, {"label": "비고", "key": None, "value": "없음", "page": 2}],
               "doc": {"fields": {"p1.r0": {"value": "러그 절단"}}}, "start": "", "title": "러그 절단"}
        check("모르는 칸 목록(값 있는 것만)", [x["label"] for x in workplan.unknown_labels(rec)] == ["착수 예정", "투입 인력", "비고"])
        # MAP_CELL: the model picks a known item; the server keeps what fits
        llm.call_json = fake({"maps": [{"l": "L1", "k": "start"}, {"l": "L2", "k": "workers"}, {"l": "L3", "k": "start"}]})
        mapcell._CACHE.clear()
        out = asyncio.run(mapcell.suggest(rec))
        check("모델 선택 중 꼴이 맞는 것만(비고→시작일시는 날짜 아님, 같은 항목 두 번 아님)",
              [(m["label"], m["key"]) for m in out["maps"]] == [("착수 예정", "start"), ("투입 인력", "workers")])
        check("읽기 연결은 미리 준비 순서(PREPARED)", CALLS[-1] == ("MAP_CELL", llm.PREPARED))
        llm.call_json = fake({"maps": [{"l": "L1", "k": "title"}]})
        mapcell._CACHE.clear()
        check("이미 제 칸에서 읽은 항목에는 잇지 않음", asyncio.run(mapcell.suggest(rec))["maps"] == [])
        llm.call_json = fake(llm.LlmFail("timeout"))
        mapcell._CACHE.clear()
        check("모델 실패 → 제안 없음(fail)", asyncio.run(mapcell.suggest(rec))["status"] == "fail")
        m = workplan.mapped(rec, {"착수 예정": {"key": "start", "status": "confirmed"}, "투입 인력": {"key": "workers", "status": "refused"}})
        check("확인한 연결만 반영(시작일시), 거절한 것은 그대로", m["start"] == "2026-10-29T13:00" and
              not any(x.get("key") == "workers" for x in m["items"]) and rec["start"] == "")
        d = Path(tempfile.mkdtemp()) / "tok"
        # a stored upload: save_map accepts only a label of the plan and a key of the spec
        tok = "a" * 32
        (workplan.CACHE / tok).mkdir(parents=True, exist_ok=True)
        (workplan.CACHE / tok / "plans.json").write_text(json.dumps([rec], ensure_ascii=False), encoding="utf-8")
        workplan.save_map(tok, 0, "착수 예정", "start", True)
        check("확인한 연결은 저장되고 계획서 읽기에 반영", workplan.load_plans(tok)[0]["start"] == "2026-10-29T13:00")
        try:
            workplan.save_map(tok, 0, "작업명", "start", True)
            check("알려진 칸(작업명)은 연결 대상 아님", False)
        except ValueError:
            check("알려진 칸(작업명)은 연결 대상 아님", True)
        check("계획서가 바뀌면 다이제스트가 바뀜", workplan.plan_digest(rec) != workplan.plan_digest(rec, {"p1.r0": "러그 절단(수정)"}))
        del d

        # LINK: relations and what a link may bring
        q = lambda item, ch, keys: {"qid": f"{item}:P", "item": item, "text": item, "keys": keys,
                                     "choices": [{"id": ch, "label": "x", "ask": "값"}, {"id": "unknown", "label": "모름"}]}
        fields = {"p1.date_1": {"key": "date_1", "name": "작업일자", "value": "2026-10-29"},
                  "p1.from_1": {"name": "작업시작", "value": "08:00"}, "p1.location": {"name": "작업장소", "value": "대조립21공장"}}
        plan = {"start": "2026-10-29T13:00", "end": "2026-10-29T15:00", "location": "3BAY 12-14 칼럼 E41P 블록",
                "items": [{"key": "workers", "value": "작업자 4명"}, {"key": "manager", "value": "홍길동"}]}
        oq = [q("T1", "partial", ["p1.from_1"]), q("L1", "place", ["p1.location"]), q("B1.workers", "value", [])]
        same = {x["item"]: x for x in link.imports(fields, plan, "same_work", oq)}
        check("같은 작업: 시간(전체 예정)·작업점·팀 인원을 가져올 값으로", set(same) == {"T1", "L1", "B1.workers"}
              and same["T1"]["value"] == "10/29 13:00~15:00" and same["T1"]["kind"] == "전체 예정 시간")
        check("가져올 값은 목적지·지금 값(전)과 함께", same["L1"]["dest"] == "작업장소" and same["L1"]["before"] == "대조립21공장")
        ph = {x["item"]: x for x in link.imports(fields, plan, "phase_of", oq)}
        check("한 단계: 단계 시간·작업점만(팀 인원 없음)", set(ph) == {"T1", "L1"} and ph["T1"]["kind"] == "이 단계의 시간")
        check("관련 작업은 아무것도 가져오지 않음", link.imports(fields, plan, "related", oq) == [])
        check("책임자 이름 등은 가져올 값이 아님", all("홍길동" not in x["value"] for x in same.values()))
        check("관계 6종(같은·포함·단계·관련·다른·미상), 다른·미상은 연결 아님", link.RELS == ("same_work", "contains", "phase_of", "related", "different", "unknown")
              and set(link.LINKED) == {"same_work", "contains", "phase_of", "related"})

        # 허가 검토 신호
        D = {"date": "2026-10-29", "permits": [{"id": "8175", "kind": "hot", "title": "E41P 러그 절단", "detail": "", "place": "3BAY 12-14 칼럼",
                                               "spans": [{"bay": 3, "c0": 12, "c1": 14}], "windows": [{"start": "13:00", "end": "15:00"}]}],
             "plans": [{"id": "WP-1", "title": "E41P 가용접", "place": "3BAY 12칼럼", "spans": [{"bay": 3, "c0": 12, "c1": 12}],
                        "windows": [{"start": "14:00", "end": "16:00"}], "_items": [{"label": "작업명", "value": "E41P 가용접으로 임시 고정"}]},
                       {"id": "WP-2", "title": "E52S 크레인 인양", "place": "1BAY 02칼럼", "spans": [{"bay": 1, "c0": 2, "c1": 2}],
                        "windows": [{"start": "09:00", "end": "10:00"}], "_items": [{"label": "1단계", "value": "OH-21-02로 블록 인양"},
                                                                                      {"label": "2단계", "value": "용접부 검사 UT"},
                                                                                      {"label": "3단계", "value": "반경 내 화기 금지 표지"}]},
                       {"id": "WP-3", "title": "도장", "place": "", "spans": [], "windows": [], "_items": [{"label": "작업명", "value": "E41P 블록 도장 터치업"}]}]}
        S = permitsignal.signals(D)
        by = {(s["plan"], s["kind_ko"]): s for s in S}
        check("같은 날 같은 곳·시간의 화기 허가서가 있으면 신호 없음", not any(s["plan"] == "WP-1" for s in S))
        check("인양 허가서를 이 범위에서 못 찾으면 「대응 허가서를 확인해 주세요」", ("WP-2", "중량물인양") in by
              and by[("WP-2", "중량물인양")]["title"] == "대응 허가서를 확인해 주세요" and by[("WP-2", "중량물인양")]["found"] == "이 범위에서 찾지 못함")
        check("용접부 검사·화기 금지 표지는 화기 작업 아님", ("WP-2", "화기") not in by)
        check("지원 5종 밖(도장)은 범위 밖 신호", ("WP-3", "도장·유기용제") in by and by[("WP-3", "도장·유기용제")]["kind"] is None)
        check("신호 문구에 단정(「허가서가 없다」·「허가 대상」) 없음", all("없다" not in s["found"] and "허가 대상" not in s["title"] for s in S))
        llm.call_json = fake({"k": [{"c": "C1", "t": "height"}]})
        D["plans"].append({"id": "WP-4", "rev": "r", "title": "족", "place": "", "spans": [], "windows": [],
                           "_items": [{"label": "작업명", "value": "E41P 외판 작업발판 설치 작업"}]})
        ai = asyncio.run(permitsignal.suggest_ai(D["plans"][-1]))
        S2 = permitsignal.signals(D, ai)
        check("규칙이 못 읽은 구절은 모델이 종류만 고르고, 신호에 AI 제안 표시", any(s["plan"] == "WP-4" and s["ai"] and s["kind"] == "height" for s in S2))
        check("모델 신호 판별은 미리 데우기 순서(WARM)", CALLS[-1] == ("PERMIT_SIGNAL", llm.WARM))

        # 관리자 요약 (the demo day when it is there)
        try:
            Dd, det = safety.data(), pairs.detect()
        except FileNotFoundError:
            Dd = None
        if Dd:
            b = docsum.build(Dd, det)
            r0 = b[Dd["plans"][0]["id"]]["rows"]
            check("요약 순서: 시간·장소·대상·공유 설비·단계·상충·미확인", [r[0] for r in r0] == list(docsum.ORDER))
            check("모든 문서에 요약과 AI 읽기 결과", all("rows" in v and "ai" in v and "signals" in v for v in b.values()) and len(b) == len(Dd["permits"]) + len(Dd["plans"]))
            check("제출본이 없는 허가서는 「AI 읽기 결과 없음」으로(감추지 않음)",
                  any("제출본 없음" in " ".join(v["ai"]["lines"]) for k, v in b.items() if any(p["id"] == k for p in Dd["permits"])))
        else:
            print("(시연 하루 없음: 요약 시험 3건 건너뜀)")

        # 게시 문안 보충: the model picks, the server writes the fixed shape
        det2 = {"pairs": [{"key": "8175|WP-1", "a": "8175", "b": "WP-1", "reasons": [{"rule": "FIRE", "cause": "8175", "exposed": "WP-1",
                                                                                         "measures": ["가연물 제거", "감시자 배치"], "ask": "도장 종료 시각"}]}],
                "rules": [{"id": "FIRE", "post": {"cause": "도장과 겹치는 동안 화기 금지", "exposed": "화기 끝난 뒤 착수", "start": "잔불 없음 확인 뒤 알림"}}]}
        safety_find = safety.find
        safety.find = lambda i: {"id": i, "title": "러그 절단", "place": "대조립21공장 3BAY 12-14 칼럼", "windows": [{"start": "13:00", "end": "15:00"}]}
        try:
            llm.call_json = fake({"a": "A1", "f": "F1", "c": "C1"})
            out = asyncio.run(posting.draft(det2, "8175|WP-1", "8175", [{"item": "HT1", "value": "가스절단 4개"}]))
            check("문안 틀: 우리 반은 {시점·대상}에 {할 일} → 착수조건 → 중지·변경 시 연락", out["status"] == "ok" and out["lines"][0] ==
                  "우리 반은 13:00~15:00 3BAY 12-14 칼럼 (가스절단 4개)에 도장과 겹치는 동안 화기 금지." and out["lines"][1].startswith("착수조건: ")
                  and out["lines"][2].startswith("중지·변경 시: "))
            check("문안의 출처: 규칙 문구와 반장 답변 확인", [s["kind"] for s in out["sources"]] == ["규칙 문구", "규칙 문구", "반장 답변 확인"])
            check("추가조치 3줄·TBM 초안도 같은 고름에서", len(out["extra"]) == 3 and out["tbm"][0].startswith("오늘 러그 절단:"))
            posting._DRAFTS.clear()
            llm.call_json = fake({"a": "A1", "f": "none", "c": "C1", "text": "16시에 시작하기로 합의"})
            out = asyncio.run(posting.draft(det2, "8175|WP-1", "8175", [{"item": "HT1", "value": "가스절단 4개"}]))
            check("모델이 문장을 덧붙이면 받지 않음(fail)", out["status"] == "fail" and not out["lines"])
            posting._DRAFTS.clear()
            CALLS.clear()
            out = asyncio.run(posting.draft({**det2, "pairs": [{**det2["pairs"][0], "reasons": [{**det2["pairs"][0]["reasons"][0], "measures": [], "ask": ""}]}]},
                                            "8175|WP-1", "8175", []))
            check("고를 것이 하나뿐이면 모델 없이 서버 문장(fixed)", out["status"] == "fixed" and not CALLS)
            check("없는 쌍이면 문안 없음", asyncio.run(posting.draft(det2, "x|y", "8175"))["status"] == "none")
        finally:
            safety.find = safety_find
    finally:
        llm.call_json = real
    law_status()
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


def law_status():
    """Codex A9: a citation, a collected article and a fit check are kept apart on the screen as on the server; only
    an article checked 「맞음」 (and collected) counts as 확인된 — a weak or unchecked link is labelled a citation only"""
    import re
    from server import evidencemap
    M = evidencemap.build()
    f, cells = M["flow"], [r["법령"] for r in M["rows"] if r["법령"]]
    check("근거 지도: 확인된 조문 = 검수 「맞음」·원문 수집만", f["law_confirmed"] == sum(1 for c in cells if c["fit"] == "맞음" and all(x["in_corpus"] for x in c["links"])))
    check("근거 지도: 약함·검수 기록 없음은 확인된 근거가 아님", all(not c["confirmed"] for c in cells if c["fit"] != "맞음")
          and {c["status"] for c in cells if c["fit"] != "맞음"} <= {"약함", "미검수"})
    check("근거 지도: 인용 수 = 맞음 + 약함 + 검수 기록 없음 (인용 수를 확인 수로 쓰지 않음)",
          f["with_law"] == f["law_fit_ok"] + f["law_weak"] + f["law_unchecked"] and f["law_confirmed"] <= f["law_fit_ok"])
    web = Path(__file__).resolve().parent.parent / "web"
    html, ejs, ajs = ((web / n).read_text(encoding="utf-8") for n in ("evidence.html", "evidence.js", "app.js"))
    check("근거 지도 화면: 법령 열 제목이 「확인된 조문」이 아님", "확인된 조문</th>" not in html and "인용 조문 · 적합성 검수" in html)
    check("근거 지도 화면: 맞음이 아닌 칸은 「인용만(확인된 근거 아님)」", "인용만(확인된 근거 아님)" in ejs and "f.law_confirmed" in ejs)
    check("관리자 화면 근거 지도: 인용 수(with_law)를 「확인된 조문」으로 세지 않음",
          not re.search(r"확인된 조문 \$\{f\.with_law\}", ajs) and "확인된 조문 ${f.law_confirmed}" in ajs and "확인된 근거는 [법령] 칸뿐" not in ajs)


if __name__ == "__main__":
    main()
