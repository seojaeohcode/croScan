"""Pull QA reports sent from the web page's QA button into qa_inbox/ (one folder per report).

  python tools/qa_pull.py                    reports not handled yet (handled = false) -> qa_inbox/<id>/report.md, context.json, files
  python tools/qa_pull.py --all              every report, handled ones too
  python tools/qa_pull.py --handled 3 부분수용 "무엇을 어떻게"   handled, with how (수용 · 부분수용 · 거절 · 보류) and a note
  python tools/qa_pull.py --unhandled 3      set it back to false
  python tools/qa_pull.py --run-start        the waiting 「QA 시작하기」 request → 수행 중 (prints its id)
  python tools/qa_pull.py --run-done 7 "메모" --ids 103 104   that run → 완료, with the reports it handled (--run-fail: 실패)

Server address and token come from the environment or the .env at the repository root:
  CROSCAN_URL=http://<server address>   QA_TOKEN=...   (the token is never printed)
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
INBOX = APP / "qa_inbox"


def env():
    vals = {}
    f = APP / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    vals.update({k: os.environ[k] for k in ("CROSCAN_URL", "QA_TOKEN") if os.environ.get(k)})
    if not vals.get("QA_TOKEN"):
        raise SystemExit("QA_TOKEN이 없습니다 (저장소 루트의 .env 또는 환경변수)")
    if not vals.get("CROSCAN_URL"):
        raise SystemExit("CROSCAN_URL이 없습니다: 저장소 루트의 .env에 서버 주소를 적으세요 (예: CROSCAN_URL=http://1.2.3.4)")
    return vals["CROSCAN_URL"].rstrip("/"), vals["QA_TOKEN"]


def call(base, token, path, body=None):
    req = urllib.request.Request(base + path, json.dumps(body).encode() if body is not None else None,
                                 {"X-QA-Token": token, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        why = {403: "QA_TOKEN이 서버와 다릅니다", 404: "그 번호의 QA가 없습니다"}.get(e.code, e.reason)
        raise SystemExit(f"{base}{path}: {e.code} {why}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SystemExit(f"서버에 연결하지 못했습니다 ({base}): {getattr(e, 'reason', e)}")


def report_md(q):
    c = q["context"]
    lines = [f"# QA #{q['id']} (처리: {'true' if q['handled'] else 'false'})", "",
             f"- 보낸 시각: {q['created']} (KST)", f"- 보낸 사람: {q['author'] or '(없음)'}",
             f"- 화면: {c.get('screen')} · 보기 {c.get('view')} · {c.get('page')}쪽 · 창 {c.get('window')}",
             f"- 파일: {c.get('file')} · 허가서 종류: {c.get('kind')} · 화면 버전: {c.get('assets')}",
             f"- 답변 {len(c.get('answers') or [])}건 · 남은 질문: {', '.join(c.get('open_questions') or []) or '-'}",
             f"- 브라우저: {c.get('ua')}"]
    if q.get("note"):
        lines.append(f"- 처리 메모: {q['note']}")
    lines += ["", "## 내용", "", q["text"] or "(설명 없음)", ""]
    for f, local in zip(q["files"], q["_local"]):
        lines.append(f"![{f['name']}]({local})" if f["mime"].startswith("image/") else f"- 첨부: [{f['name']}]({local}) ({f['size'] // 1024} KB)")
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--handled", nargs="+", metavar=("ID", "NOTE"))
    ap.add_argument("--unhandled", nargs="+", metavar=("ID", "NOTE"))
    ap.add_argument("--run-start", action="store_true")
    ap.add_argument("--run-done", nargs="+", metavar=("RUN", "NOTE"))
    ap.add_argument("--run-fail", nargs="+", metavar=("RUN", "NOTE"))
    ap.add_argument("--ids", nargs="*", type=int, default=None)
    a = ap.parse_args()
    base, token = env()
    if a.run_start:                              # the waiting request is taken by this session
        board = json.loads(call(base, token, "/api/qa/board"))
        run = next((r for r in board["runs"] if r["status"] == "requested"), None)
        if not run:
            raise SystemExit("기다리는 「QA 시작하기」 요청이 없습니다")
        call(base, token, f"/api/qa/run/{run['id']}", {"status": "running"})
        print(f"run {run['id']} → running (요청 {run['requested']} · {run['by'] or '-'} · 그때 미처리 {run['open_at_request']}건)")
        return
    for status, arg in (("done", a.run_done), ("failed", a.run_fail)):
        if arg:
            call(base, token, f"/api/qa/run/{int(arg[0])}", {"status": status, "note": " ".join(arg[1:]) or None, "done": a.ids})
            print(f"run {arg[0]} → {status}")
            return
    for value, arg in ((True, a.handled), (False, a.unhandled)):
        if arg:
            rest = arg[1:]
            how = {"수용": "수용", "전부수용": "수용", "부분수용": "부분 수용", "부분": "부분 수용", "거절": "거절", "거부": "거절", "보류": "보류"}.get(rest[0].replace(" ", "")) if rest else None
            if how:
                rest = rest[1:]
            call(base, token, f"/api/qa/{int(arg[0])}/handled", {"handled": value, "note": " ".join(rest) or None, "decision": how if value else None})
            print(f"QA #{arg[0]} → handled = {str(value).lower()}" + (f" · {how}" if how else ""))
            return
    reports = json.loads(call(base, token, "/api/qa" + ("" if a.all else "?handled=false")))
    for q in reports:
        d = INBOX / f"{q['id']:04d}"
        d.mkdir(parents=True, exist_ok=True)
        q["_local"] = []
        for f in q["files"]:
            local = f"{f['n']:02d}_{Path(f['name']).name}"      # numbered: two attachments may share a name
            req = urllib.request.Request(f"{base}/api/qa/{q['id']}/file/{f['n']}", headers={"X-QA-Token": token})
            with urllib.request.urlopen(req, timeout=120) as r:
                (d / local).write_bytes(r.read())
            q["_local"].append(local)
        (d / "context.json").write_text(json.dumps(q["context"], ensure_ascii=False, indent=1), encoding="utf-8")
        (d / "report.md").write_text(report_md(q), encoding="utf-8")
        print(f"#{q['id']:>3} {'true' if q['handled'] else 'false':5} {q['created']}  {q['author'] or '-':8}  첨부 {len(q['files'])}  {(q['text'] or '').splitlines()[0][:50] if q['text'] else ''}")
    print(f"{len(reports)}건 → {INBOX}")


if __name__ == "__main__":
    main()
