"""체크리스트 출력의 기본 목록 재구성 (design §7: clean()은 서버 기본 목록을 재구성하고 사용자 선택을 병합): a base item
the page left out, or chose on another basis, is still printed — as the draft has it, 「반장 확인 전」.

  python tools/check_ckmerge.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import checklist  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    items = checklist.items_for("hot")[:3]
    draft = {"permits": [{"permit_no": "P-1", "kind": "hot", "items": [
        {"id": it["id"], "title": it["title"], "state": "check", "auto": "check", "basis": f"b{i}", "reasons": [], "sources": [],
         "controls": [{"id": c["id"], "text": c["text"], "on": True} for c in it["controls"]], "common": False} for i, it in enumerate(items)]}]}
    a, b, c = (it["id"] for it in items)
    sent = {"permits": [{"permit_no": "P-1", "kind": "hot", "items": [
        {"id": a, "state": "yes", "auto": "check", "basis": "b0", "touched": True, "ctl_touched": True, "controls": []},
        {"id": b, "state": "no", "auto": "check", "basis": "OLD", "touched": True},
        {"id": "U1", "title": "인접 도장", "state": "yes", "touched": True, "controls": [{"id": "u1", "text": "시간 분리", "on": True}]}]}]}
    out = checklist.merge(draft, sent)["permits"][0]["items"]
    by = {x["id"]: x for x in out}
    check("기본 항목은 빠지지 않음(보내지 않은 항목도 출력)", {a, b, c} <= set(by))
    check("같은 근거로 고른 항목은 반장 선택 그대로", by[a]["state"] == "yes" and by[a]["touched"])
    check("다른 근거로 고른 항목은 확인 전 초안으로", not by[b]["touched"] and by[b]["state"] == "check")
    check("보내지 않은 항목은 확인 전 초안으로", not by[c]["touched"])
    check("반장이 직접 추가한 항목은 유지", "U1" in by)
    sheet = checklist.layout({"permit_no": "P-1", "kind": "hot", "items": out}, "2026-10-31 09:00", "화기 · 작업반장")
    check("종이에 「반장 확인 전」 표시", "반장 확인 전" in str(sheet))
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
