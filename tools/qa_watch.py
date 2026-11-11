"""Wait for 「QA 시작하기」 on the QA screen (the team's request to the QA session on this PC).

    python tools/qa_watch.py            check the server every 20 s; exit when a request is waiting (prints it)

The Claude Code session that works on the QA runs this in the background: the script ends when someone presses the
button, which wakes the session; the session then marks the run 수행 중 (tools/qa_pull.py --run-start), works through
the reports, marks them handled with how (수용 · 부분수용 · 거절 · 보류) and the run 완료, and starts this again.
When it exits it prints the request and the fixed prompt (tools/qa_prompt.txt) the session works by.
Nothing is sent by this script; it only reads GET /api/qa/board. Server address from the environment or the .env at the
repository root (CROSCAN_URL), as qa_pull.py.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from qa_pull import env

EVERY = 20


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    base, token = env()
    misses = 0
    while True:
        try:
            req = urllib.request.Request(base + "/api/qa/board?show=open", headers={"X-QA-Token": token})
            with urllib.request.urlopen(req, timeout=30) as r:     # the token lets it through a company login too
                board = json.loads(r.read())
            misses = 0
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):                 # not a passing network fault: the token or the login is wrong
                raise SystemExit(f"서버가 거절했습니다({e.code}): QA_TOKEN·로그인 설정을 확인해 주세요")
            misses += 1
            time.sleep(EVERY)
            continue
        except Exception as e:                       # the server or the network away for a while: keep waiting
            misses += 1
            if misses in (1, 10, 100):
                print(f"(서버 확인 실패 {misses}회: {e})", flush=True)
            time.sleep(EVERY)
            continue
        run = next((x for x in board.get("runs", []) if x["status"] == "requested"), None)
        if run:
            print(json.dumps({"run": run["id"], "requested": run["requested"], "by": run["by"], "left": board.get("left")},
                             ensure_ascii=False), flush=True)
            print("[고정 프롬프트]", (Path(__file__).parent / "qa_prompt.txt").read_text(encoding="utf-8").strip(), sep="\n", flush=True)
            return
        time.sleep(EVERY)


if __name__ == "__main__":
    main()
