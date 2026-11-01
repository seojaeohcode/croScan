"""확인 사례 개선 루프 (server/cases, design §4.5): a card decision → waiting → a person's review → de-identified →
published version → shown as a prompt example and found as similar / counter-examples. Runs on a throwaway store.

  python tools/check_cases.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_cases_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import cases, store, understand  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


F = {"p1.permit_no": {"key": "permit_no", "page": 1, "value": "P-1"}, "p1.date_1": {"key": "date_1", "page": 1, "value": "2026-10-31"}}
QT1 = {"qid": "T1:P-1", "item": "T1", "page": 1, "text": "실제 작업 시간은?"}
QHT = {"qid": "HT1:P-1", "item": "HT1", "page": 1, "text": "러그 몇 개를 어떤 방법으로 떼나요?",
       "choices": [{"id": "gas", "label": "가스절단", "ask": "개수"}, {"id": "na", "label": "떼는 러그 없음"}, {"id": "unknown", "label": "모름"}]}
QB3 = {"qid": "B3:P-1", "item": "B3", "page": 1, "text": "다른 작업이 있나요?",
       "choices": [{"id": "yes", "label": "있음", "ask": "무엇"}, {"id": "no", "label": "없음"}, {"id": "unknown", "label": "모름"}]}
SAID = "13시~15시요. 러그 6개는 가스로 떼고, 김철수 반장 010-1234-5678로 연락 주세요. 옆에 도장팀이 있다고 들었어요."
SRC = {"qid": "T1:P-1", "choice": "partial", "value": SAID, "q": QT1, "at": 1}


def main():
    check("비식별: 이름·전화가 가려짐", cases.deidentify("김철수 반장 010-1234-5678, AB12-CD-20261031-0001") == "[이름] 반장 [전화], [허가번호]")
    sid = store.create()
    _, r0, _ = store.answers_for(sid, [SRC], F, 0)
    got, _ = store.propose(sid, "ai", SRC, [{"qid": "HT1:P-1", "choice": "gas", "value": "6", "q": QHT, "by": "T1:P-1", "quote": "러그 6개는 가스로 떼고", "who": "self", "when": "plan"},
                                            {"qid": "B3:P-1", "choice": "no", "value": "", "q": QB3, "by": "T1:P-1", "quote": "옆에 도장팀이 있다고 들었어요", "who": "self", "when": "plan"}], basis=r0)
    ok_id, no_id = got[0]["pid"], got[1]["pid"]
    store.decide(sid, "act-c1", adopt=[ok_id], reject=[no_id], fields=F)
    ids = cases.record(sid, [ok_id], [no_id])
    rows = cases.listing("queued")
    check("확인·거절한 카드는 검토 대기 사례 하나로(같은 답)", len(ids) == 1 and len(rows) == 1)
    r = rows[0]
    check("저장된 답은 비식별", "010-" not in r["answer"] and "김철수" not in r["answer"] and "[전화]" in r["answer"])
    check("확인한 읽기는 예시 답, 거절한 읽기는 반례로", json.loads(r["out"])[0]["c"] == "gas" and json.loads(r["refused"])[0]["c"] == "no")
    check("같은 결정을 다시 기록해도 하나", cases.record(sid, [ok_id], [no_id]) == [] and len(cases.listing()) == 1)
    check("검수 전에는 예시로 쓰지 않음", cases.example(r["grp"]) is None)
    try:
        cases.review(r["id"], True, "")
        check("검수자 없는 검수는 거절", False)
    except ValueError:
        check("검수자 없는 검수는 거절", True)
    cases.review(r["id"], True, "안전팀 검수자")
    v, done, held = cases.publish()
    check("검수한 사례는 새 버전으로 발행", v == 1 and done == [r["id"]] and not held)
    ex = cases.example(r["grp"])
    check("발행된 사례가 그 슬롯군의 예시로(질문 목록·답·답 JSON)", ex and "남은 질문:" in ex[0] and json.loads(ex[1])["props"][0]["c"] == "gas")
    qs = [{"qid": "HT1:P-9", "item": "HT1", "text": "x", "choices": []}]
    check("읽기의 예시 선택이 발행 사례를 먼저 씀", understand.examples(qs)[0] == ex)
    sim = cases.similar("HT1", "러그 가스로 떼요")
    check("유사 사례·반례 검색", sim["cases"] and sim["counter"])
    # a published case that does not hold against its own words is held back
    s2 = store.create()
    src2 = dict(SRC, value="러그 3개 그라인더로 떼요.", at=2)
    _, r1, _ = store.answers_for(s2, [src2], F, 0)
    g2, _ = store.propose(s2, "ai", src2, [{"qid": "HT1:P-1", "choice": "gas", "value": "3", "q": QHT, "by": "T1:P-1", "quote": "러그 3개 그라인더로 떼요", "who": "self", "when": "plan"}], basis=r1)
    store.decide(s2, "act-c2", adopt=[g2[0]["pid"]], fields=F)
    cid = cases.record(s2, [g2[0]["pid"]], [])[0]
    with cases._db() as c:
        c.execute("UPDATE cases SET out=? WHERE id=?", (json.dumps([{"q": "Q1", "c": "gas", "v": "3", "who": "self", "when": "plan", "quote": "없는 구절"}]), cid))
    cases.review(cid, True, "검수자")
    v2, done2, held2 = cases.publish()
    check("구절이 답에 없는 사례는 발행 보류", held2 == [cid] and not done2)
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
