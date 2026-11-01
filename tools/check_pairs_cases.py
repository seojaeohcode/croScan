"""쌍작업 규칙의 반례 시험 (GPT 검토에서 나온 경우들): made-up documents, no DB.
  python tools/check_pairs_cases.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import pairs  # noqa: E402
from server.safety import spans  # noqa: E402


def win(s):
    a, _, b = s.partition("~")
    return {"start": a, "end": b, **({"next_day": True} if b < a else {})}


def plan(i, title, place, time, equip="", mat="", height="지상 작업", steps=(), workers=2):
    items = [{"label": "작업명", "value": title}, {"label": "작업장비", "value": equip}, {"label": "사용물질", "value": mat},
             {"label": "작업높이", "value": height}] + [{"label": f"{k + 1}단계", "value": s} for k, s in enumerate(steps)]
    return {"type": "plan", "id": f"WP-T-{i:02d}", "company": "시험", "title": title, "place": place, "spans": spans(place), "is_route": False,
            "windows": [win(t) for t in time], "move": None, "workers": workers, "target": "", "_items": items}


def permit(i, kind, title, place, time, detail="", hazards="", checks=(), records=None, workers=3, move=None, route=""):
    f = {f"c{k}": {"name": c, "type": "check", "value": True} for k, c in enumerate(checks)}
    return {"type": "permit", "id": f"T{i:03d}", "kind": kind, "label": {"hot": "화기", "confined": "밀폐", "height": "고소", "lifting": "중량물인양", "loto": "정전·LOTO"}[kind],
            "title": title, "detail": detail, "hazards": hazards, "place": place, "route": route, "spans": spans(place + " " + route),
            "is_route": bool(route), "windows": [win(t) for t in time], "move": win(move) if move else None, "workers": workers,
            "_fields": f, "_records": [{"item": k, "value": v} for k, v in (records or {}).items()]}


def judge(a, b):
    A, B = pairs.profile(a), pairs.profile(b)
    out = []
    for rule in pairs.rules()["rules"]:
        for x, y in ((A, B), (B, A)):
            h = pairs._judge(rule, x, y)
            if h and h["priority"]:
                out.append(h)
    return sorted(out, key=lambda h: (h["priority"], -h["score"])), A, B


ok = bad = 0


def check(name, cond, info=""):
    global ok, bad
    ok += bool(cond); bad += not cond
    print(("OK   " if cond else "틀림 ") + name + (f"  ({info})" if info and not cond else ""))


# 1. residual risk has no time limit: hot work, then a solvent paint on the same block 3 h later → 3순위 확인
h, *_ = judge(permit(1, "hot", "E42P 보강재 용접", "3BAY 08-10 칼럼 E42P 블록 상부", ["09:00~10:00"], checks=["용접·용단"]),
              plan(1, "E42P 블록 상부 도장", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], mat="에폭시 도료, 희석제(유기용제)"))
check("잔류위험: 화기 3시간 뒤 같은 블록 도장 → 3순위 확인", h and h[0]["priority"] == 3 and h[0]["when"]["kind"] == "sequence", h and h[0]["name"])
# 2. a missing time is asked, whatever the score (S2 rule)
h, *_ = judge(permit(2, "hot", "D31C 절단", "4BAY 03-05 칼럼 D31C 블록", ["09:00~11:00"], checks=["용접·용단"]),
              plan(2, "D31C 블록 치수 측정", "4BAY 03-05 칼럼 D31C 블록", [], equip="줄자"))
check("시간 미상 + 화기 → 3순위 확인", h and h[0]["priority"] == 3 and h[0]["when"]["kind"] == "unknown", h and h[0]["name"])
# 3. 서류상 0명 is not proof that nobody is inside (2026-10-31 기대값 변경 — 자료 MV03 「인원 합계 0만으로 무인을 확정하지
# 않는다」, Q06): the rule stays, held at 노출 1 (3순위 확인 필요) saying so, never 1·2순위
h, *_ = judge(permit(3, "confined", "E41P 탱크 내부 점검", "3BAY 12-14 칼럼 E41P 블록 이중저 내부", ["09:00~11:00"], workers=0),
              plan(3, "E41P 갑판 용접", "3BAY 12-14 칼럼 E41P 블록", ["10:00~12:00"], equip="CO2 용접기 2대", height="블록 상부 3.6m"))
c = [x for x in h if x["rule"] == "CONF_HOT"]
check("밀폐 인원 0명 + 화기 → 제외 아님: 노출 1·3순위, 「서류상 인원 0: 실제 퇴실 확인 아님」",
      c and c[0]["E"] == 1 and c[0]["priority"] == 3 and any("서류상 인원 0" in w for w in c[0]["why_E"]), c and (c[0]["E"], c[0]["why_E"]))
# 4. gas: the same block is not a system link; the same pipe is
h, *_ = judge(permit(4, "confined", "B22S 배관 P-99 진입", "2BAY 05-06 칼럼 B22S 블록 내부 배관 P-99", ["13:00~15:00"], checks=["밀폐구역출입"]),
              plan(4, "B22S 배관 P-01 아르곤 퍼지 용접", "2BAY 05-06 칼럼 B22S 블록", ["13:00~14:00"], equip="TIG 용접기, 아르곤", steps=["배관 P-01 아르곤 퍼지"]))
g = [x for x in h if x["rule"] == "CONF_GAS"]
check("같은 블록·다른 배관 가스 → 확인 필요(노출 1)", g and g[0]["E"] == 1, g and g[0]["E"])
h, *_ = judge(permit(5, "confined", "B22S 배관 P-12 진입", "2BAY 05-06 칼럼 B22S 블록 내부 배관 P-12", ["13:00~15:00"], checks=["밀폐구역출입"]),
              plan(5, "B22S 배관 P-12 아르곤 퍼지 용접", "1BAY 18-19 칼럼 B30S 블록", ["13:00~14:00"], equip="TIG 용접기, 아르곤", steps=["배관 P-12 아르곤 퍼지"]))
g = [x for x in h if x["rule"] == "CONF_GAS"]
check("다른 BAY라도 같은 배관 P-12 → 확인(1순위)", g and g[0]["E"] == 3 and g[0]["priority"] == 1, g and (g[0]["E"], g[0]["relation"]))
# 5. a move outside the permit hours is a schedule mismatch, not a confirmed path
h, *_ = judge(permit(6, "lifting", "E45P 블록 이동", "3BAY", ["10:00~11:00"], move="12:00~13:00", route="3BAY 06칼럼에서 16칼럼"),
              plan(6, "E41P 갑판 취부", "3BAY 12-14 칼럼 E41P 블록", ["11:30~13:30"], height="블록 상부 3.6m"))
g = [x for x in h if x["rule"] == "LOAD_OVER"]
check("허가 시간 밖 이동 → 일정 불일치(노출 2)", g and g[0]["E"] == 2 and any("일정 불일치" in w for w in g[0]["why_E"]), g and g[0]["why_E"])
# 6. extractor: upkeep, negation, mixed materials
P = pairs.profile(plan(7, "공용 용접기 점검·케이블 정리", "4BAY 08-10 칼럼", ["08:00~09:00"], equip="용접기, 절연저항계"))
check("'공용 용접기 점검' → 화기 아님", "SPARK" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(8, "배관 내부 육안 확인", "2BAY 05-06 칼럼 B22S 블록", ["08:00~09:00"], equip="랜턴", steps=["아르곤 미사용, 자연환기"]))
check("'아르곤 미사용' → 불활성가스 아님", "INERT" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(9, "D33C 비드 사상", "4BAY 17-19 칼럼 D33C 블록", ["13:00~14:00"], equip="충전 그라인더", steps=["MCC-4 전원 미사용(충전식)"]))
check("'MCC-4 전원 미사용' → 전원 사용 아님", not P["ids"]["power_use"], P["ids"]["power_use"])
P = pairs.profile(plan(10, "E44P 도장", "3BAY 17-20 칼럼 E44P 블록", ["13:00~14:00"], mat="수성 도료, 유기용제 세정제"))
check("'수성 도료, 유기용제 세정제' → 유기용제 있음", "SOLVENT" in P["tags"], P["tags"].keys())
# 7. common support: dismantling supports on the ground, work on top of the same block
h, *_ = judge(plan(11, "D31C 블록 받침대 해체", "4BAY 03-05 칼럼 D31C 블록", ["09:00~10:00"], equip="유압잭"),
              permit(7, "height", "D31C 블록 상부 보강재 취부", "4BAY 03-05 칼럼 D31C 블록 상부", ["09:00~11:00"], records={"L3": "6m"}))
check("지상 받침대 해체 × 같은 블록 상부 6m 작업 → 공통지지", any(x["rule"] == "SUPPORT" for x in h), [x["rule"] for x in h])
# 8. a fall the wrong way is not raised
h, *_ = judge(permit(8, "height", "B21S 러그 절단", "1BAY 14-16 칼럼 B21S 블록 상부", ["14:00~15:00"], records={"L3": "4m"}),
              plan(12, "B21S 상부 족장 작업", "1BAY 14-16 칼럼 B21S 블록", ["14:00~15:00"], height="블록 상부 6.0m"))
d = [x for x in h if x["rule"] == "DROP_BELOW" and x["cause"] == "T008"]
check("4m 절단 → 6m 작업자 낙하 없음", not d, [(x["cause"], x["E"]) for x in d])
# 9. overlap pieces: 09–10 and 14–15 against 08–16 → two pieces, 120 min (not 09:00–15:00)
ovs = pairs.overlaps([(540, 600), (840, 900)], [(480, 960)])
check("겹침은 조각별: 2조각 120분", ovs == [(540, 600), (840, 900)] and sum(b - a for a, b in ovs) == 120, ovs)
# 10. a night window crosses midnight
check("야간 23:00~01:00 → 다음 날까지", pairs._win_m({"start": "23:00", "end": "01:00", "next_day": True}) == (1380, 1500))
# 15. a pressure test then work by the same pipe after it: the residual pressure is not cleared by the time split (통합본 09)
h, *_ = judge(plan(15, "P-12 배관 수압시험", "2BAY 05-06 칼럼 B22S 블록", ["09:00~10:00"], equip="수압 펌프", steps=("P-12 배관 수압시험 가압",)),
              plan(16, "P-12 배관 서포트 취부", "2BAY 05-06 칼럼 B22S 블록", ["10:30~12:00"], equip="용접기"))
check("압력시험 30분 뒤 같은 곳 작업 → 잔압 확인(3순위 sequence)", any(x["rule"] == "PRESSURE" and x["when"]["kind"] == "sequence" for x in h),
      [(x["rule"], x["when"]["kind"]) for x in h])

# 16. 완료 후 재진입: a lift whose block is lifted again in an added window — the risk counts in that window, not only the old move
L = permit(17, "lifting", "B22S 블록 반출 인양", "2BAY 05-06 칼럼 → 2BAY 20칼럼 반출장", ["15:30~16:30"], route="2BAY 05-06 칼럼 → 2BAY 20칼럼",
           checks=["천장크레인"], move="15:40~16:10", records={"LI1": "천장크레인 OH-21-02"})
W = plan(18, "B27P 블록 소조립 취부 용접", "2BAY 09-11 칼럼 B27P 블록", ["17:00~17:30"], equip="용접기")
h0, *_ = judge(L, W)
h1, *_ = judge(pairs._override(L, [{"start": "15:30", "end": "16:30"}, {"start": "17:00", "end": "17:30", "extra": True}]), W)
check("재진입 시간대(17:00~17:30)의 인양 경로 × 아래 작업 → 경보", not h0 and any(x["rule"] in ("LOAD_OVER", "TARGET_OCCUPIED") for x in h1), [x["rule"] for x in h1])
# 17. units are not IDs: 'm3' stays a unit, 'oh-21-01' becomes the crane
from server import augment  # noqa: E402
check("norm_ids: 'oh-21-01, 3 m3, co2' → 'OH-21-01, 3 m3, CO2'", augment.norm_ids("oh-21-01, 3 m3, co2") == "OH-21-01, 3 m3, CO2", augment.norm_ids("oh-21-01, 3 m3, co2"))
check("ids(): M3·CO2는 대상 번호가 아님", augment.ids("3 M3 CO2 E41P") == {"E41P"}, augment.ids("3 M3 CO2 E41P"))

# 18. Codex A7: a farther column of the same BAY is not 「도달 범위 밖」 — the distance is not known, so it is held
# (3순위 판정보류, 「거리 미확인」), never left out; another BAY or another time still meets nobody
HOT = lambda i, t="13:00~14:00": permit(i, "hot", "E42P 론지 가우징", "3BAY 08-10 칼럼 E42P 블록 상부", [t], checks=["용접·용단"])  # noqa: E731
for gap_place, label in (("3BAY 13-14 칼럼 E43P 블록", "칼럼 3칸"), ("3BAY 17-20 칼럼 E44P 블록", "칼럼 7칸")):
    h, *_ = judge(HOT(20), plan(20, "E44P 세정·탈지", gap_place, ["13:00~14:00"], mat="세정제(유기용제)"))
    f = [x for x in h if x["rule"] == "FIRE"]
    check(f"같은 BAY {label} 떨어진 화기 × 유기용제 → 판정보류(거리 미확인), 제외 아님",
          f and f[0]["priority"] == 3 and f[0]["E"] == 1 and "거리 미확인" in f[0]["relation"] and not any("도달 범위 밖" in w for w in f[0]["why_E"]),
          f and (f[0]["priority"], f[0]["E"], f[0]["relation"]))
for rule, doc in (("PRESSURE", plan(21, "P-12 배관 수압시험", "3BAY 17-18 칼럼 E44P 블록", ["13:00~14:00"], equip="수압 펌프", steps=("P-12 배관 가압",))),
                  ("RADIATION", plan(22, "E44P 용접부 RT 촬영", "3BAY 17-18 칼럼 E44P 블록", ["13:00~14:00"], equip="이리듐 선원"))):
    h, *_ = judge(doc, plan(23, "E43P 블록 마킹", "3BAY 08-09 칼럼 E43P 블록", ["13:00~14:00"], equip="마킹펜"))
    g = [x for x in h if x["rule"] == rule]
    check(f"같은 BAY 멀리 떨어진 {rule} → 판정보류(거리 미확인)", g and g[0]["E"] == 1 and "거리 미확인" in g[0]["relation"], [x["rule"] for x in h])
h, *_ = judge(HOT(24), plan(24, "세정", "2BAY 08-10 칼럼 B22S 블록", ["13:00~14:00"], mat="세정제(유기용제)"))
f = [x for x in h if x["rule"] == "FIRE"]
# 2026-11-01 최종 검토(자료 HW05 15m 예시·B22 옆 BAY 불티): the next BAY at the same columns is held to check, never
# a confirmed alarm; a BAY farther away stays out
check("옆 BAY 같은 칼럼대 유기용제 → 화기 FIRE 판정보류(E1·「옆 BAY」 거리·칸막이 미확인)만",
      f and f[0]["E"] == 1 and f[0]["priority"] == 3 and "옆 BAY" in f[0]["relation"], [(x["rule"], x["E"]) for x in h])
h, *_ = judge(HOT(24), plan(25, "세정", "1BAY 08-10 칼럼 B12S 블록", ["13:00~14:00"], mat="세정제(유기용제)"))
check("두 BAY 떨어진 유기용제 → 화기 규칙 경보 없음", not any(x["rule"] == "FIRE" for x in h), [x["rule"] for x in h])
q = pairs._quiet(pairs.profile(HOT(25)), pairs.profile(plan(25, "마킹", "3BAY 17-20 칼럼 E44P 블록", ["13:00~14:00"], equip="마킹펜")),
                 {"kind": "far", "bay": 3, "gap": 7})
check("근접 목록 문구에 추정 거리(약 Nm)·「도달 범위 밖」 없음", q and "m)" not in q["text"] and "도달 범위" not in q["text"] and "거리 미확인" in q["text"], q)

# 19. Codex A8: a check or a no qualifies only its own act; the work written with it keeps its tag
P = pairs.profile(plan(26, "E42P 블록 취부", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("크레인으로 부재 취부", "가용접 후 치수 확인")))
check("'가용접 후 치수 확인' → 화기(가용접) 유지", "SPARK" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(27, "E42P 블록 취부", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("가용접후 치수확인",)))
check("'가용접후 치수확인'(붙여 씀) → 화기 유지", "SPARK" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(28, "E42P 용접부 검사", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("용접부 검사만 실시",)))
check("'용접부 검사만 실시' → 화기 아님", "SPARK" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(29, "E42P 볼트 체결", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("절단 없음",)))
check("'절단 없음' → 화기·절단 아님", "SPARK" not in P["tags"] and "SEP" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(30, "E42P 받침 정리", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("절단 없이 볼트 해체",)))
check("'절단 없이 볼트 해체' → 해체(SEP)는 유지, 화기 아님", "SEP" in P["tags"] and "SPARK" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(31, "E42P 비드 정리", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("용접부 그라인딩 후 검사",)))
check("'용접부 그라인딩 후 검사' → 화기(그라인딩) 유지", "SPARK" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(32, "P-12 배관 시험", "2BAY 05-06 칼럼 B22S 블록", ["09:00~10:00"], steps=("압력시험 후 누설 확인",)))
check("'압력시험 후 누설 확인' → 압력시험 유지", "PRESSURE" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(33, "E42P 용접부 RT", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], steps=("RT 촬영 후 판독",)))
check("'RT 촬영 후 판독' → 방사선 유지", "RADIATION" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(34, "공용 장비 확인", "4BAY 08-10 칼럼", ["08:00~09:00"], steps=("화기작업 여부 확인", "용접기 점검")))
check("'화기작업 여부 확인'·'용접기 점검' → 화기 아님(그대로)", "SPARK" not in P["tags"], P["tags"].keys())
# the missing-equipment case: no 작업장비, the act in a step still raises the alarm with the solvent beside it
h, *_ = judge(plan(35, "E42P 취부", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], steps=("가용접 후 치수 확인",)),
              plan(36, "E42P 세정", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], mat="세정제(유기용제)"))
check("장비 칸 없이 '가용접 후 치수 확인' × 같은 블록 유기용제 → 화기 경보", any(x["rule"] == "FIRE" for x in h), [x["rule"] for x in h])

print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
