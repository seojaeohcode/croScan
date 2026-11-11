"""QA 현황 (2026-11-02): the team's board and the 「QA 시작하기」 request to the QA session.

    python tools/check_qa_board.py

The board lists every report newest first with how it was handled (수용 · 부분 수용 · 거절 · 보류) and the note, and
no screen state or attachment; one request at a time; the session's states need the QA token; a finished run lets a
new one be asked.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["CROSCAN_DATA"] = tempfile.mkdtemp(prefix="croscan_qab_")
os.environ["QA_TOKEN"] = "t0k"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402
from server import app as A  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("OK   " if cond else "FAIL ") + name)


sys.stdout.reconfigure(encoding="utf-8")
c, T = TestClient(A.app), {"X-QA-Token": "t0k"}
for i in range(3):
    c.post("/api/qa", data={"text": f"의견 {i} " + "가" * 400, "author": "팀", "context": '{"screen": "s-check", "fields": {"secret": 1}}'})
b = c.get("/api/qa/board").json()
check("최신 번호부터", [r["id"] for r in b["reports"]] == [3, 2, 1])
check("목록에는 화면 정보·첨부 내용이 없고 글 앞부분만", "context" not in b["reports"][0] and len(b["reports"][0]["text"]) == 300 and b["reports"][0]["more"])
r1, r2 = c.post("/api/qa/run", json={"by": "김"}).json(), c.post("/api/qa/run", json={"by": "이"}).json()
check("요청은 한 번에 하나(두 번째는 같은 요청)", r1["made"] and not r2["made"] and r1["run"]["id"] == r2["run"]["id"] and r1["run"]["open_at_request"] == 3)
rid = r1["run"]["id"]
check("상태 기록은 QA 토큰이 있어야", c.post(f"/api/qa/run/{rid}", json={"status": "running"}).status_code == 403)
check("없는 상태 이름은 거절", c.post(f"/api/qa/run/{rid}", json={"status": "zzz"}, headers=T).status_code == 422)
c.post(f"/api/qa/run/{rid}", json={"status": "running"}, headers=T)
check("수행 중이면 시작 시각", c.get("/api/qa/board").json()["runs"][0]["started"] != "")
check("처리 결과: 부분 수용 + 메모", c.post("/api/qa/2/handled", json={"handled": True, "note": "버튼 위치만 반영", "decision": "부분 수용"}, headers=T).json()["ok"])
check("처리 결과 이름이 아니면 거절", c.post("/api/qa/1/handled", json={"handled": True, "decision": "대충"}, headers=T).status_code == 422)
c.post(f"/api/qa/run/{rid}", json={"status": "done", "note": "1건", "done": [2]}, headers=T)
b = c.get("/api/qa/board").json()
r2_ = next(r for r in b["reports"] if r["id"] == 2)
check("목록에 처리 결과·메모·시각", r2_["handled"] and r2_["decision"] == "부분 수용" and r2_["note"] == "버튼 위치만 반영" and r2_["handled_at"])
check("완료 기록: 끝난 시각·처리한 번호", b["runs"][0]["status"] == "done" and b["runs"][0]["finished"] and b["runs"][0]["done"] == "2" and b["left"] == 2)
c.post("/api/qa/2/handled", json={"handled": False}, headers=T)
check("미처리로 되돌리면 처리 결과도 지움", next(r for r in c.get("/api/qa/board").json()["reports"] if r["id"] == 2)["decision"] == "")
check("끝난 뒤에는 새 요청", c.post("/api/qa/run", json={}).json()["made"])
c.post("/api/qa/3/handled", json={"handled": True, "note": "처음 메모", "decision": "부분 수용"}, headers=T)
c.post("/api/qa/3/handled", json={"handled": True, "note": "고친 메모"}, headers=T)
r3 = next(r for r in c.get("/api/qa/board").json()["reports"] if r["id"] == 3)
check("메모만 고치면 처리 결과는 그대로", r3["decision"] == "부분 수용" and r3["note"] == "고친 메모")
check("미처리·처리됨 거르기는 서버에서", [r["id"] for r in c.get("/api/qa/board?show=open").json()["reports"]] == [2, 1]
      and [r["id"] for r in c.get("/api/qa/board?show=done").json()["reports"]] == [3])
c.post("/api/qa", data={"text": "x", "context": '{"screen": {"fields": {"secret": 1}}}'})
check("공개 목록의 화면 이름은 알려진 이름만", c.get("/api/qa/board").json()["reports"][0]["screen"] == "" and
      next(r for r in c.get("/api/qa/board").json()["reports"] if r["id"] == 1)["screen"] == "s-check")
c.post("/api/qa/run/2", json={"status": "failed", "note": "시험"}, headers=T)
for i in (1, 2, 4):
    c.post(f"/api/qa/{i}/handled", json={"handled": True, "decision": "거절"}, headers=T)
check("미처리가 없으면 「QA 시작하기」는 409(빈 요청으로 세션을 깨우지 않음)", c.post("/api/qa/run", json={}).status_code == 409)
print(f"\n{sum(OK)}/{len(OK)}")
sys.exit(0 if all(OK) else 1)
