"""확인 사례 검수·발행 도구 (design §4.5): the person who reviews the cases uses this; nothing is published without it.

  python tools/cases_admin.py list [queued|reviewed|rejected|published]
  python tools/cases_admin.py show <id>
  python tools/cases_admin.py review <id> ok|no "<검수자>" ["메모"]
  python tools/cases_admin.py publish
  python tools/cases_admin.py similar <item> "<답 문장>"

Run where the data volume is (CROSCAN_DATA), e.g. inside the app container.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import cases  # noqa: E402


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "list":
        for r in cases.listing(argv[1] if len(argv) > 1 else None):
            print(f"{r['id']}  {r['status']:<9} v{r['version'] or '-'}  {r['item']:<10} {r['answer'][:50]}")
    elif cmd == "show":
        r = next((x for x in cases.listing() if x["id"] == argv[1]), None)
        if not r:
            print("없음")
            return 1
        print(json.dumps({**r, "questions": json.loads(r["questions"]), "out": json.loads(r["out"]), "refused": json.loads(r["refused"])},
                         ensure_ascii=False, indent=1))
    elif cmd == "review":
        cases.review(argv[1], argv[2] == "ok", argv[3], argv[4] if len(argv) > 4 else "")
        print("검수 기록함")
    elif cmd == "publish":
        v, done, held = cases.publish()
        print(f"버전 {v} · 발행 {len(done)}건 · 보류 {len(held)}건")
    elif cmd == "similar":
        got = cases.similar(argv[1], argv[2])
        print(json.dumps({k: [x["answer"] for x in v] for k, v in got.items()}, ensure_ascii=False, indent=1))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
