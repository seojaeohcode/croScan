"""쌍작업 위험탐지 채점: the demo day's answer key (samples/시연_하루/skeleton.json) against server.pairs.detect().

The key is used here only, to score: the rules never read it.
In scope: 일상×비일상 and 비일상×비일상 (a 일상×일상 pair in the key is reported apart).
  python tools/check_pairs.py           summary
  python tools/check_pairs.py -v        every detected pair with its reasons
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import pairs  # noqa: E402

key = json.loads((ROOT / "samples/시연_하루/skeleton.json").read_text(encoding="utf-8"))
short = lambda x: x[-4:] if x.startswith("BS22") else ("WP-1029-" + x[2:] if x.startswith("WP") and len(x) == 4 else x)  # noqa: E731
res = pairs.detect()
found = {frozenset((p["a"], p["b"])): p for p in res["pairs"]}
quiet = {frozenset((n["a"], n["b"])): n for n in res["near"]}
ok = bad = 0
print(f"후보 {res['stats']['candidates']}쌍 (비일상×비일상 {res['stats']['nn']} · 일상×비일상 {res['stats']['rn']}) → 경보 {len(res['pairs'])}쌍 {res['stats']['by_priority']}")
print("\n[정답 겹침]")
hit_keys = set()
for c in key["clashes"]:
    a, b = short(c["a"]), short(c["b"])
    k = frozenset((a, b))
    if not (a[0].isdigit() or b[0].isdigit()):
        print(f"  {c['id']} {a}×{b} 정답 {c['priority']}순위 — 일상×일상: 이번 범위 밖")
        continue
    p = found.get(k)
    hit_keys.add(k)
    mark = "OK " if p and p["priority"] == c["priority"] else "차이" if p else "놓침"
    ok += bool(p)
    bad += not p
    print(f"  {mark} {c['id']} {a}×{b} 정답 {c['priority']}순위 → " + (f"{p['priority']}순위 {p['title']} (S{p['S']}×E{p['E']})" if p else "경보 없음"))
# Codex A7 (2026-10-31): the key's N05 says 「칼럼 7칸(84m) 떨어짐」, but 12m per column is an estimate and 11m is the
# fire-watch radius (제241조의2), not the edge of every hazard: without a measured distance the rules no longer leave
# the pair out. It may be raised only as 3순위 판정보류 (E1) saying 「거리 미확인」 — a question, not a confirmed alarm.
HELD = {"N05": "실제 거리·차폐가 서류에 없어 판정보류(거리 미확인)로 남김 · Codex A7",
        # 2026-10-31 자료 412쪽 대조: 6988 절단·재용접(09:00~11:30, 높이 미기재)이 끝나고 90분 뒤 같은 B21S 블록 족장 해체가
        # 시작. 「잔류는 활동시간 비중첩·종료만으로 해제하지 않는다」(p24 residual, LU15·HW10-LOOSE/CONTACT): 미회수 분리물·잔열의
        # 해제 확인 기록이 없으니 3순위 확인 필요(노출 1)로 남김 — 동시 위험 경보가 아니라 질문
        "N01": "앞 작업의 잔류위험(분리물·잔열) 해제 확인 기록이 없어 3순위 확인 필요(시간 분리만으로 해제 안 함) · 자료 p24·LU15",
        # 2026-11-01 Codex 검토: 8602 고소작업대 위 보강재 취부(09:00~11:00)가 끝나고 120분 뒤 같은 칼럼 아래 마킹. 위에 남은
        # 공구·부재가 떨어질 수 있음(p24 residual·p346 미해제, 사례집 C43) — 3순위 확인 필요로만
        "N03": "상부 작업 뒤 남은 공구·부재(잔존물) 회수 확인 기록이 없어 3순위 확인 필요 · 자료 p24·p346, 사례집 C43"}
# each held near-miss is held for its own reason only (Codex 14: no broad condition)
_e1 = lambda p: p["priority"] == 3 and p["E"] == 1 and all(r["E"] == 1 for r in p["reasons"])  # noqa: E731
_seq = lambda p, rules: all(r["when"]["kind"] == "sequence" and r["rule"] in rules  # noqa: E731
                            and any("잔류위험" in w for w in r["why_E"]) for r in p["reasons"])
HELD_OK = {"N05": lambda p: _e1(p) and all(r["rule"] == "FIRE" and "거리 미확인" in r["relation"] and r["when"]["kind"] == "overlap"
                                          for r in p["reasons"]),
           "N01": lambda p: _e1(p) and _seq(p, {"DROP_BELOW", "SUPPORT", "HOT_PERSON"}),
           "N03": lambda p: _e1(p) and _seq(p, {"OVERHEAD_WORK"})}
held = lambda p, i: HELD_OK[i](p)  # noqa: E731
print("\n[근접: 경보하면 안 됨]")
fp_near = 0
for n in key["near_misses"]:
    a, b = short(n["a"]), short(n["b"])
    p = found.get(frozenset((a, b)))
    if p and n["id"] in HELD and held(p, n["id"]):
        hit_keys.add(frozenset((a, b)))
        print(f"  보류 {n['id']} {a}×{b} → 3순위 판정보류 {p['title']} · {HELD[n['id']]}")
        continue
    fp_near += bool(p)
    q = quiet.get(frozenset((a, b)))
    print(f"  {'틀림' if p else 'OK  '} {n['id']} {a}×{b} → " + (f"경보 {p['priority']}순위 {p['title']}" if p else f"경보 없음 · {q['why']['text'] if q else '(근접 목록 밖)'}"))
extra = [p for k, p in found.items() if k not in hit_keys]
print(f"\n[정답표 밖 경보 {len(extra)}쌍]")
for p in extra:
    r = p["reasons"][0]
    print(f"  {p['id']} {p['a']}×{p['b']} {p['priority']}순위 {p['title']} S{p['S']}×E{p['E']} · {r['when']['kind']} {r['when']['start']}–{r['when']['end']} · {r['relation']} · {' / '.join(r['why_E'])}")
n_key = sum(1 for c in key["clashes"] if short(c["a"])[0].isdigit() or short(c["b"])[0].isdigit())
print(f"\n찾음 {ok}/{n_key} · 근접 오경보 {fp_near}/{len(key['near_misses'])} · 정답표 밖 {len(extra)}")
if "-v" in sys.argv:
    for p in res["pairs"]:
        print(f"\n{p['id']} {p['a']} × {p['b']} [{p['kind']}] {p['priority']}순위 {p['title']} ({p['judgement']})")
        for r in p["reasons"]:
            print(f"   · [{r['priority']}] {r['name']} S{r['S']}×E{r['E']}={r['score']}{' 금지조합' if r['forbidden'] else ''} {r['when']['kind']} {r['when']['start']}–{r['when']['end']} · {r['relation']}")
            print("     " + " → ".join(r["chain"]))
sys.exit(0 if bad == 0 and fp_near == 0 else 1)
