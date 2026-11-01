"""검색 자료의 메타·필터·인용 검사·연구 ref (design §3.4·§3.4.1; server/retrieval.py, server/evidencemap.py).

  python tools/check_retrieval.py      # needs server/knowledge/corpus.json (tools/build_corpus.py)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import evidencemap, retrieval  # noqa: E402

OK = []
META = ("source_id", "revision", "hash", "pdf_page", "printed_page", "company_scope", "work_kind", "topic", "authority",
        "effective_status", "supersedes", "synthetic", "estimate", "legal_verified", "extraction_quality")


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    C = retrieval.corpus()
    docs = C["docs"]
    check(f"모든 청크에 §3.4 메타 {len(META)}개", all(all(k in d for k in META) for d in docs))
    check("4층(법령·공공·조선사·팀)이 모두 있음", {d["authority"] for d in docs} >= {"법령", "공공", "조선사", "팀"})
    check("가상 청크는 효력 상태도 「예시」", all(d["effective_status"].startswith("예시") for d in docs if d["synthetic"] and d["authority"] == "팀"))
    check("현행 여부 미확인 지침(B-5-2011)은 그렇게 표시", all("미확인" in d["effective_status"] for d in docs if d["source_id"] == "kosha:B-5-2011"))
    # filters before scoring
    h = retrieval.search("크레인 신호", k=20, work_kind="lifting")
    check("작업 종류 필터: 인양이거나 공통인 구절만", h and all("lifting" in x["work_kind"] or "common" in x["work_kind"] for x in h))
    h = retrieval.search("불티", k=30, effective=False)
    check("효력 필터: 예시·현행 미확인 구절 없음", h and not any(str(x["effective_status"]).startswith(("예시", "현행 여부 미확인")) for x in h))
    h = retrieval.search("작업중지권", k=10, company="삼성중공업", authority="조선사")
    check("회사 필터: 그 회사 구절만", all(x["company_scope"] == "삼성중공업" for x in h))
    h = retrieval.search("화재감시자", k=5, topic="control", authority="법령")
    check("주제 필터: 조치 구절만", h and all("control" in x["topic"] for x in h))
    # citations
    d = retrieval.search("화재감시자", k=1, authority="법령")[0]
    c = retrieval.cite(d)
    check("인용(source_id/revision/span)이 그대로면 통과", retrieval.check_cite(c) == (True, ""))
    check("개정이 다르면 거절", retrieval.check_cite({**c, "revision": "시행 2019.1.1"})[0] is False)
    check("없는 구절이면 거절", retrieval.check_cite({**c, "quote": "화재감시자를 두지 않아도 된다"})[0] is False)
    check("없는 자료면 거절", retrieval.check_cite({**c, "id": "law:안전보건규칙:제9999조"})[0] is False)
    check("빠진 사실은 MissingObservation(가짜 인용 아님)", retrieval.missing("작업 높이", "허가서")["type"] == "MissingObservation")
    rel = retrieval.related("용접 불티 화재 감시를 확인하려고 묻습니다")
    check("「왜 묻나요?」 관련 자료는 인용 검사를 통과한 것만", rel and all(retrieval.check_cite(x["cite"])[0] for x in rel))
    # field corrections (현장 정정 D01·D02): the old approval / face-to-face notes never come back, even asked for word by word
    bad = set(retrieval.CORRECTED)
    check("정정된 팀 메모 3건이 corpus에 있고 제외 목록에 있음",
          {"team:notion:p2:0", "team:notion:p3:0", "team:notion:p9:0"} <= bad and bad <= {d["id"] for d in docs})
    old = ["전산허가는 안전대면허가 불필요 이중 점검", "밀폐공간 감시자 환기 가스측정 전산허가 안전대면허가 불필요",
           "안전관리자 위험작업허가서 최종적으로 승인", "안전팀이 전산승인한다고 설명", "허가구분과 2중점검 Y/N 안전팀 결정"]
    check("정정된 메모는 검색에 나오지 않음", not any(x["id"] in bad for q in old for x in retrieval.search(q, k=50)))
    check("정정된 메모는 「왜 묻나요?」에도 나오지 않음",
          not any(x["id"] in bad for q in old + ["밀폐공간 감시자·환기를 확인하려고 묻습니다", "고소작업 추락 방지를 확인하려고 묻습니다"]
                  for x in retrieval.related(q, k=5)))
    check("업로드 분석 참고 자료에도 정정된 메모 없음", not any(x["id"] in bad for q in old for x in retrieval.for_analysis(q, k=5)))
    ana = retrieval.for_analysis("화기 블록 내부 용접 불티", kind="hot")
    check("업로드 분석 참고 자료: 2~3개, 법령·공공, 가상 없음", 2 <= len(ana) <= 3 and all(x["grade"] in ("법령", "공공") for x in ana))
    # research references: linked only where written; else 미연결 with a candidate, never cited
    refs = json.loads((retrieval.CORPUS.parent / "research_refs.json").read_text(encoding="utf-8"))["refs"]
    check("연구 ref 표가 있음", len(refs) > 0)
    check("원문에 없는 ref는 「미연결」(인용하지 않음)", all(r["status"] in ("연결", "미연결") for r in refs.values())
          and all(r.get("quote") for r in refs.values() if r["status"] == "연결"))
    check("미연결 ref의 후보는 검수 전", all(not r.get("candidate") or r["candidate"]["reviewed"] is False for r in refs.values() if r["status"] == "미연결"))
    # the research book defines the codes (2026-11-01: the 119-page Notion export searched before carries none of them)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_corpus as B
    book = ("===== PAGE 192 =====\nHW02-SPARK —\n불티·열 전달\n===== PAGE 197 =====\nHW09-CABLE-ELECT\nRIC — 전기 케이블 손상\n"
            "===== PAGE 237 =====\nPE12 — 소음 노출·필요 신호 방해\n노출이 관련되면, 강한 소음이나 누적 노출로\nPE12-HEARING: 청력 손상 위험이 있습니다. 본문 HW02-SPARK 언급\n"
            "===== PAGE 240 =====\n1.2 재검토 보완 — PE15-HEAT 열 축적·온열질환\n===== PAGE 343 =====\nEL13-ELECTRIC — 종료 후 전기 상태\n")
    codes = B.book_codes(book)
    check("조사본 정의 읽기: 줄 첫머리·두 줄로 잘린 코드·묶음 안 하위 코드·절 제목",
          codes.get("HW02-SPARK", (0, ""))[0] == 192 and codes["HW02-SPARK"][1].startswith("HW02-SPARK — 불티·열 전달")
          and codes.get("HW09-CABLE-ELECTRIC", (0, ""))[1].startswith("HW09-CABLE-ELECTRIC — 전기 케이블 손상")
          and codes.get("PE12-HEARING", (0, ""))[1] == "강한 소음이나 누적 노출로 PE12-HEARING: 청력 손상 위험이 있습니다."
          and codes.get("PE15-HEAT", (0,))[0] == 240 and "재검토" not in codes.get("PE12", (0, ""))[1])
    check("코드가 아닌 ref(사례·보고서)는 미연결, 이유가 적힘",
          all(r["status"] == "미연결" and "코드가 아님" in r["why"] for k, r in refs.items() if not re.search(B.CODE, k)))
    check("조사본 코드 ref는 정의된 쪽·원문으로 연결", refs.get("HW02-SPARK", {}).get("ref") == "팀 조사본(412쪽) 192쪽"
          and refs.get("EL13", {}).get("status") == "연결" and refs["EL13"].get("codes") == ["EL13-ELECTRIC", "EL13-FALL", "EL13-MOTION"]
          and all(c in refs["EL13"]["quote"] for c in refs["EL13"]["codes"]))
    M = evidencemap.build()
    rows = [r for r in M["rows"] if r["팀"]["research"]]
    check("근거 지도: 연구 ref 행에 연결 기록이 붙음", rows and all(r["팀"]["research_link"] for r in rows))
    check("근거 지도: 공공 층 후보가 보임", M["flow"]["public"] > 0 and M["flow"]["by_authority"].get("공공", 0) > 0)
    check("근거 지도: 연구 ref 연결 수는 실제 연결만", M["flow"]["research_linked"] == sum(1 for r in rows if r["팀"]["research_link"]["status"] == "연결"))
    ck = [r for r in M["rows"] if r["kind"].startswith("체크리스트") and r["법령"]]
    check("체크리스트 법령 인용의 검수 기록(맞음·약함)이 지도에 그대로", ck and all(r["법령"]["fit"] in ("맞음", "약함") for r in ck)
          and M["flow"]["law_fit_ok"] + M["flow"]["law_weak"] + M["flow"]["law_unchecked"] == M["flow"]["with_law"])
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
