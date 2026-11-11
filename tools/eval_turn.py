"""1차 시연 평가 (design §11.1, small): TURN on a real permit with the model on the server. Counts, not rates.

  python tools/eval_turn.py      # inside a container on the model's network (LLM_URL set)

Each case is a foreman's answer to the 작업시간 question (T1, 「일부 시간만」) that also says something else, in two
phrasings. Expected: what the server should end up proposing (item: choice), and what it must not propose. Reported:
right / wrong / missed proposals, another team's work proposed as ours, and the time per call.
"""
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import augment, extract, understand  # noqa: E402
from make_demo_day import DIR, load, permit_name  # noqa: E402

CASES = [  # (name, [phrasing 1, phrasing 2], expected {item: choice}, must not propose {items})
    ("러그 가스절단 6개", ["13시부터 15시까지 해요. 러그는 가스절단으로 6개 떼요.", "오후 1시~3시입니다, 임시 러그 여섯 개를 산소 가스로 절단합니다."], {"HT1": "gas"}, set()),
    ("러그 그라인더", ["13~15시에 합니다. 러그 3개는 그라인더로 잘라요.", "1시부터 3시까지요. 그라인더로 러그 세 개를 갈아서 떼어냅니다."], {"HT1": "mech"}, set()),
    ("작업 위치", ["13시~15시, 위치는 3BAY 12-14 칼럼 블록 상부요.", "오후 1시부터 3시까지 3BAY 12~14칼럼 블록 위에서 해요."], {"L1": "place"}, set()),
    ("옆 팀 도장(다른 팀)", ["13시~15시. 옆에서 도장팀이 터치업한다고 들었어요.", "1시부터 3시까지요. 바로 옆에 도장팀 3명이 붓으로 터치업 합니다."], {"B3": "yes"}, {"HT1", "L1"}),
    ("다른 작업 없음(주체 불분명)", ["13시~15시. 다른 작업은 없어요.", "오후 1~3시이고 같은 시간 같은 장소에 다른 작업 없습니다."], {}, {"B3"}),
    ("러그 없음", ["13시~15시. 이번엔 떼는 러그가 없어요, 위치 확인만 해요.", "1시부터 3시까지인데 러그 절단은 안 합니다."], {"HT1": "na"}, set()),
    ("러그 회수", ["13시~15시. 떼어낸 러그는 로프로 내려서 하부에 모아요.", "1~3시요. 자른 러그는 로프에 묶어 아래로 내리고 하부는 통행 막아요."], {"HT2": "text"}, set()),
    ("확실하지 않음", ["13~15시인데 아마 가스절단일 것 같아요.", "1시~3시요. 절단 방법은 아직 정해지지 않았어요."], {}, {"HT1"}),
]


async def main():
    ps = load("permits.json")
    ps = ps if isinstance(ps, list) else ps.get("permits", [])
    d = next(x for x in ps if permit_name(x).startswith("8175"))
    doc = extract.build(DIR / "허가서" / permit_name(d), d["kind"])
    fields = doc["fields"]
    open_, _, _, _ = augment.questions(fields, [])
    t1 = next(q for q in open_ if q["item"] == "T1")
    print("open:", sorted(q["item"] for q in open_))
    right = wrong = missed = leak = 0
    times, fails, rows = [], 0, []
    for name, texts, want, never in CASES:
        for text in texts:
            src = {"qid": t1["qid"], "choice": "partial", "value": text, "q": t1}
            t = time.time()
            rule, _ = augment.interpret(fields, [src], src)              # the rules first, as /api/augment does
            out = await understand.read(fields, [src] + rule, src)      # the AI on what the rules left open
            times.append(time.time() - t)
            if out["status"] == "fail":
                fails += 1
            got = {p["q"]["item"]: (p["choice"], "rule") for p in rule}
            got.update({p["q"]["item"]: (p["choice"], p.get("who")) for p in out.get("props", []) if p["q"]["item"] not in got})
            r = sum(1 for k, c in want.items() if k in got and got[k][0] == c)
            w = sum(1 for k, (c, _) in got.items() if k not in want or want[k] != c)
            m = sum(1 for k, c in want.items() if not (k in got and got[k][0] == c))
            lk = sum(1 for k in got if k in never)
            right, wrong, missed, leak = right + r, wrong + w, missed + m, leak + lk
            rows.append((name, text[:28], out["status"], {k: v[0] for k, v in got.items()}, [a["slot"] for a in out.get("apart", [])], r, w, m))
            print(f"{name} | {text[:30]} | {out['status']} {round(times[-1], 1)}s | 제안 {dict((k, v[0]) for k, v in got.items())} | 따로 {[a['slot'] for a in out.get('apart', [])]} | 맞음{r} 틀림{w} 놓침{m}", flush=True)
    exp = sum(len(c[2]) for c in CASES) * 2
    print(f"\n총 {len(rows)}건 · 기대 제안 {exp} · 맞음 {right} · 틀림 {wrong} · 놓침 {missed} · 금지 항목 제안 {leak} · 실패 {fails}"
          f" · 시간 중앙값 {statistics.median(times):.1f}s 최대 {max(times):.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
