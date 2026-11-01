"""제출 스냅숏 (server/submissions.py): the checklist confirmed against the server's draft, a snapshot made once.

  python tools/check_submissions.py
"""
import copy
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_sub_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import submissions  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def refused(name, fn, code):
    try:
        fn()
        check(name, False)
    except submissions.Refused as e:
        check(name, e.code == code)


DRAFT = {"version": 1, "permits": [{"permit_no": "P-1", "kind": "hot", "label": "화기", "who": "용접2팀", "items": [
    {"id": "hot_spark", "basis": "b1", "basis_ctl": "k1", "title": "불티", "state": "yes", "auto": "yes", "reasons": ["화기 작업"], "common": False, "memo": "",
     "controls": [{"id": "c1", "text": "불티 방지포", "on": True}, {"id": "c2", "text": "화재감시자", "on": False}]},
    {"id": "common_ppe", "basis": "b2", "title": "보호구", "state": "check", "auto": "check", "reasons": [], "common": True, "memo": "", "controls": []}]}]}


def sent(**over):
    s = {"permits": [{"permit_no": "P-1", "kind": "hot", "items": [
        {"id": "hot_spark", "basis": "b1", "basis_ctl": "k1", "state": "yes", "auto": "yes", "touched": True, "ctl_touched": True, "memo": "감시자 1명",
         "controls": [{"id": "c2", "on": True}, {"id": "zz", "text": "만든 조치", "on": True}]},
        {"id": "common_ppe", "basis": "b2", "state": "no", "auto": "check", "touched": True, "controls": []},
        {"id": "U1", "title": "직접 추가: 바닥 미끄럼", "state": "yes", "touched": True, "controls": [{"id": "u1", "text": "미끄럼 매트", "on": True}]}]}]}
    for k, v in over.items():
        s["permits"][0]["items"][int(k[1:])].update(v)
    return s


def main():
    ck = submissions.confirm_checklist(copy.deepcopy(DRAFT), sent())
    items = {it["id"]: it for it in ck["permits"][0]["items"]}
    check("반장이 고른 상태·메모가 확정본에", items["hot_spark"]["state"] == "yes" and items["common_ppe"]["state"] == "no" and items["hot_spark"]["memo"] == "감시자 1명")
    check("안전조치는 서버 초안의 것만(id로), 화면이 만든 다른 조치는 버림",
          [k["id"] for k in items["hot_spark"]["controls"] if k["on"]] == ["c2"] and len(items["hot_spark"]["controls"]) == 2)
    check("반장이 직접 더한 항목(U…)은 그대로", items["U1"]["title"].startswith("직접 추가") and items["U1"]["controls"][0]["text"] == "미끄럼 매트")
    refused("확인하지 않은 항목이 있으면 거절", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i1={"touched": False})), "checklist_left")
    refused("고른 뒤 croScan 제안이 바뀐 항목은 거절(다시 확인)", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i0={"auto": "check"})), "checklist_changed")
    refused("초안에 있는 항목이 빠지면 거절", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), {"permits": []}), "checklist_left")
    refused("항목 근거(작업·조치)가 바뀌면 같은 제안이어도 거절", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i0={"basis": "old"})), "checklist_changed")
    # design §7: 해당 여부와 준비할 안전조치는 따로 확인하고, 각자의 근거가 바뀌면 그 확인만 만료
    refused("해당 항목은 안전조치 확인 전이면 거절", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i0={"ctl_touched": False})), "checklist_left")
    refused("안전조치 근거(작업 방법·장비)가 바뀌면 그 확인은 만료", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i0={"basis_ctl": "old"})), "checklist_changed")
    ck2 = submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i1={"state": "check"}))
    check("해당 아닌 항목은 안전조치 확인이 따로 필요 없음", {it["id"]: it["state"] for it in ck2["permits"][0]["items"]}["common_ppe"] == "check")
    # an AI reading found words that the hazard is there: his 「해당 없음」 counts only once chosen after that was shown
    mk = {"common_ppe": {"m": "support", "id": "mk1", "quote": "보안면 없이 그라인딩"}}
    refused("AI가 해당 근거를 찾은 항목의 「해당 없음」은 다시 확인 전 거절", lambda: submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(), marks=mk), "checklist_changed")
    ck3 = submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(i1={"ai_ack": "mk1"}), marks=mk)
    check("근거를 본 뒤 다시 고른 「해당 없음」은 그대로(모델이 바꾸지 않음)", {it["id"]: it["state"] for it in ck3["permits"][0]["items"]}["common_ppe"] == "no")
    check("AI가 하지 않는다는 말을 찾아도 확인은 그대로", submissions.confirm_checklist(copy.deepcopy(DRAFT), sent(),
          marks={"hot_spark": {"m": "conflict", "id": "mk2"}})["permits"][0]["items"][0]["state"] == "yes")
    pdf = b"%PDF-1.4 test"
    k1 = submissions.key_of("s1", 3, ["h", {"f": 1}, ck])
    check("같은 입력의 멱등 키는 시각과 무관하게 같음", k1 == submissions.key_of("s1", 3, ["h", {"f": 1}, ck]))
    a = submissions.create("s1", 3, k1, {"permit": pdf, "checklist": b"%PDF ck"}, {"x": 1}, {"permit_no": "P-1", "answers": 2}, time.time())
    check("이미 만든 제출본은 찾아서 그대로", submissions.find("s1", 3, k1)["id"] == a["id"])
    b = submissions.create("s1", 3, k1, {"permit": b"%PDF other"}, {"x": 9}, {"permit_no": "P-1", "answers": 9}, time.time() + 1)
    check("같은 키로 다시 만들면 처음 것(두 번째 행 없음)", b["id"] == a["id"] and b["again"])
    c = submissions.create("s1", 4, submissions.key_of("s1", 4, ["h2"]), {"permit": pdf}, {"x": 2}, {"permit_no": "P-1", "answers": 3}, time.time() + 2)
    snap, files, summ = submissions.get(a["id"])
    check("제출본 문서는 제출 때 만든 바이트 그대로", submissions.file(files, "permit") == pdf and submissions.file(files, "checklist") == b"%PDF ck")
    check("제출본은 그때의 내용 그대로(나중 제출과 섞이지 않음)", snap["x"] == 1 and summ["answers"] == 2 and summ["files"] == ["checklist", "permit"])
    check("안전관리자 보기에는 허가서별 가장 최근 제출본", submissions.latest()["P-1"]["id"] == c["id"])
    check("없는 제출본은 없음", submissions.get("없음") is None)
    submissions.create("s9", 1, "k9", {"permit": pdf}, {"x": 9}, {"permit_no": "P-9", "dates": ["2026-10-30"]}, time.time())
    check("다른 작업일의 제출본은 그날 판정에 안 들어감", "P-9" not in submissions.latest("2026-10-29") and "P-9" in submissions.latest("2026-10-30"))
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
