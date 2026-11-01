"""협조 문자의 「협의할 점」 (server/coordnote): only from a confirmed fact; the model picks, the server writes.

  python tools/check_coordnote.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import coordnote, llm, pairs  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def pair(ask, evidence):
    return {"reasons": [{"name": "화기 발생물 × 같은 곳 작업자", "headline": "불티", "cause": "0735", "exposed": "0736", "rule": "HOT_PERSON",
                         "ask": ask, "evidence": evidence}]}


FACT = {"doc": "0735", "field": "작업반장 답변 · 반장 답변 확인 HT1", "value": "가스절단 4개", "confirmed": True}
DOCV = {"doc": "0735", "field": "작업명", "value": "블록 상부 임시 러그 절단·제거"}
NO = lambda i: i


def fake(reply):
    async def call(kind, messages, schema, **kw):
        return reply, {}
    return call


def main():
    p = pair("불티 비산방지 조치, 작업자 위치", [FACT, DOCV])
    check("출처는 확인된 사실만", [x["value"] for x in coordnote.sources(p, NO)] == ["가스절단 4개"])
    check("규칙의 확인할 것은 항목별로", coordnote.items("불티 비산방지 조치, 작업자 위치") == ["불티 비산방지 조치", "작업자 위치"])
    out = asyncio.run(coordnote.note(pair("작업자 위치", [DOCV]), NO))
    check("확인된 사실이 없으면 제안 없음(모델 안 부름)", out["status"] == "none" and not out["text"])
    out = asyncio.run(coordnote.note(pair("작업자 위치", [FACT]), NO))
    check("고를 것이 하나뿐이면 모델 없이 서버 문장", out["status"] == "fixed" and out["text"] == "0735 반장 확인 답 「가스절단 4개」에 맞춰 작업자 위치를 서로 확인해 주세요.")
    real = llm.call_json
    try:
        llm.call_json = fake({"f": "F1", "c": "C2"})
        out = asyncio.run(coordnote.note(p, NO))
        check("모델은 사실·확인할 것만 고르고 문장은 서버 틀", out["status"] == "ok" and out["text"] == "0735 반장 확인 답 「가스절단 4개」에 맞춰 작업자 위치를 서로 확인해 주세요.")
        llm.call_json = fake({"f": "F1", "c": "C2", "text": "4시에 시작하기로 확인해 주세요"})
        out = asyncio.run(coordnote.note(p, NO))
        check("모델이 문장을 덧붙이면 받지 않고 서버 문장", out["status"] == "fixed" and "4시" not in out["text"])
    finally:
        llm.call_json = real
    # the fact itself carries only this work's part (Codex: another team's words rode along)
    q = {"choices": [{"id": "gas", "label": "가스절단"}]}
    got = pairs.confirmed_facts([{"qid": "HT1:P", "choice": "gas", "value": "러그 4개. 도장팀은 오후에 작업한다고 들었습니다.", "q": q}])
    check("확인 사실 값은 보기와 개수만(다른 팀 전언은 빠짐)", [x["value"] for x in got] == ["가스절단 4개"])
    got = pairs.confirmed_facts([{"qid": "CF2:P", "choice": "text", "value": "옆 팀이 아르곤 퍼지, 우리는 산소만", "q": {}}])
    check("다른 팀 절의 아르곤은 우리 작업 사실이 아님", got == [])
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
