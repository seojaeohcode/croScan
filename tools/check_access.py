"""접근 통제의 자리 (server/app.py _gate): under the company gateway (CROSCAN_AUTH=proxy) the manager's side needs the
role 안전관리자 and a review a signed-in user; without it (demo) everything is open and says so.

  python tools/check_access.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_access_"))   # a throwaway store
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402
from server import app as A  # noqa: E402

OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def main():
    c = TestClient(A.app)
    check("시연 모드: health가 demo를 알림", c.get("/api/health").json().get("auth") == A.AUTH == "demo")
    check("시연 모드: 근거 지도 열림", c.get("/api/knowledge/map").status_code == 200)
    A.AUTH = "proxy"
    try:
        check("게이트웨이: 로그인 없으면 근거 지도 401", c.get("/api/knowledge/map").status_code == 401)
        check("게이트웨이: 반장 역할은 관리자 화면 403", c.get("/api/knowledge/map", headers={A.ROLE_HEADER: "foreman"}).status_code == 403)
        check("게이트웨이: 안전관리자는 열림", c.get("/api/knowledge/map", headers={A.ROLE_HEADER: "manager"}).status_code == 200)
        check("게이트웨이: 사용자 정보 없는 반장은 401", c.get("/api/submissions/x/permit.pdf", headers={A.ROLE_HEADER: "foreman"}).status_code == 401)
        check("게이트웨이: 남의 제출 문서는 없음(404)", c.get("/api/submissions/x/permit.pdf", headers={A.ROLE_HEADER: "foreman", A.USER_HEADER: "kim"}).status_code == 404)
        os.environ["QA_TOKEN"] = "qa-test-token"
        check("게이트웨이: QA 현황은 로그인 없으면 401", c.get("/api/qa/board").status_code == 401)
        check("게이트웨이: 팀 PC 도구는 QA 토큰으로 통과(현황)", c.get("/api/qa/board", headers={"X-QA-Token": "qa-test-token"}).status_code == 200)
        check("게이트웨이: 틀린 QA 토큰은 통과 못 함", c.get("/api/qa/board", headers={"X-QA-Token": "zz"}).status_code == 401)
        check("게이트웨이: QA 토큰은 QA 경로에만", c.get("/api/knowledge/map", headers={"X-QA-Token": "qa-test-token"}).status_code == 401)
        check("게이트웨이: 근거 지도는 반장에게 403", c.get("/api/knowledge/search?q=불티", headers={A.ROLE_HEADER: "foreman", A.USER_HEADER: "kim"}).status_code == 403)
        check("게이트웨이: 쌍 설명(explanations/query kind=pair)은 반장에게 403", c.post("/api/explanations/query", json={"target": {"kind": "pair", "key": "x"}}, headers={A.ROLE_HEADER: "foreman", A.USER_HEADER: "kim"}).status_code == 403)
        check("게이트웨이: 반장 검토 API는 로그인 필요", c.post("/api/review", json={"fields": {}}).status_code == 401)
        check("게이트웨이: health는 열림", c.get("/api/health").status_code == 200)
        check("게이트웨이: 화면 파일은 열림(로그인은 게이트웨이가)", c.get("/").status_code == 200)
    finally:
        A.AUTH = "demo"
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
