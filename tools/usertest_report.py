"""사용자 시험 결과 모으기 (design §11.3·§19.10): the files saved by the user-test mode (?usertest=1, 「파일로 저장」)
-> per task: participants, successes, time (median / max), clicks, and every misreading as heard; and the §19.10
pass criteria where a file can tell them (success ≥90%, misreadings 0).

  python tools/usertest_report.py usertest_*.json [--md report.md]

It counts what the facilitator recorded; it does not judge a misreading (the words are listed as written).
"""
import glob
import json
import statistics
import sys
from pathlib import Path

PASS = {"R2": ("성공 90% 이상", 0.9), "R11": ("성공 90% 이상", 0.9)}       # §19.10 rows a success rate decides
ZERO = ("R3", "R4", "R5", "R6", "R7", "R8", "R9", "M1", "M2", "M3", "M4", "M5", "M6")      # rows that allow no misreading


def load(paths):
    runs = []
    for p in paths:
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"읽지 못함 {p}: {e}", file=sys.stderr)
            continue
        for r in d.get("runs", []):
            runs.append({**r, "who": r.get("who") or d.get("who") or Path(p).stem, "file": Path(p).name})
    return runs


def report(runs):
    tasks = {}
    for r in runs:
        tasks.setdefault(r["task"], []).append(r)
    lines = ["| 과제 | 참여자 | 성공 | 시간 중앙값·최대(초) | 클릭 중앙값 | 오해(들은 그대로) | 기준 |", "|---|---:|---:|---|---:|---|---|"]
    verdicts = {}
    for t in sorted(tasks, key=lambda x: (x[0], int(x[1:]) if x[1:].isdigit() else 0)):
        rs = tasks[t]
        ok = sum(1 for r in rs if r.get("ok"))
        secs = [r.get("ms", 0) / 1000 for r in rs]
        notes = [f"{r['who']}: {n['text']}" for r in rs for n in r.get("notes", [])]
        crit = ""
        if t in PASS:
            crit = f"{PASS[t][0]} → {'통과' if ok / len(rs) >= PASS[t][1] else '미달'}"
        elif t in ZERO:
            crit = f"오해 0건 → {'통과' if not notes else '미달'}"
        verdicts[t] = crit
        lines.append(f"| {t} | {len(rs)} | {ok}/{len(rs)} | {statistics.median(secs):.0f} · {max(secs):.0f} | "
                     f"{statistics.median([len(r.get('clicks', [])) for r in rs]):.0f} | {'<br>'.join(notes) or '없음'} | {crit} |")
    who = sorted({r["who"] for r in runs})
    head = f"참여자 {len(who)}명 · 과제 기록 {len(runs)}건 · 역할 {sorted({r.get('role', '') for r in runs})}"
    return head, "\n".join(lines), verdicts


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    paths = [p for a in args for p in glob.glob(a)]
    if not paths:
        print(__doc__)
        sys.exit(1)
    head, table, _ = report(load(paths))
    out = f"# croScan 사용자 시험 결과\n\n{head}\n\n{table}\n"
    if "--md" in sys.argv:
        Path(sys.argv[sys.argv.index("--md") + 1]).write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
