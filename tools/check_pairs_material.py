"""쌍작업 매칭 보강 시험 (2026-10-31, 자료 412쪽 감사표 part1~8·Codex A/B): made-up documents, no DB.
Each new rule or branch has a case: residual branches, the next column of a hot work, an unknown height, 서류상 인원 0,
the new rules, the vehicle words, the false hot tag of 용접재료, a route read across its range, the hot wording by
method, the labels, and the questions they leave (holdq).
  python tools/check_pairs_material.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server import holdq, pairs, safety  # noqa: E402
from server.safety import spans  # noqa: E402


def win(s):
    a, _, b = s.partition("~")
    return {"start": a, "end": b, **({"next_day": True} if b < a else {})}


def plan(i, title, place, time, equip="", mat="", height="지상 작업", steps=(), workers=2):
    items = [{"label": "작업명", "value": title}, {"label": "작업장비", "value": equip}, {"label": "사용물질", "value": mat},
             {"label": "작업높이", "value": height}] + [{"label": f"{k + 1}단계", "value": s} for k, s in enumerate(steps)]
    return {"type": "plan", "id": f"WP-M-{i:02d}", "company": "시험", "title": title, "place": place, "spans": spans(place), "is_route": False,
            "windows": [win(t) for t in time], "move": None, "workers": workers, "target": "", "_items": items}


def permit(i, kind, title, place, time, detail="", hazards="", checks=(), records=None, workers=3, move=None, route="", windows=None):
    f = {f"c{k}": {"name": c, "type": "check", "value": True} for k, c in enumerate(checks)}
    return {"type": "permit", "id": f"M{i:03d}", "kind": kind, "label": {"hot": "화기", "confined": "밀폐", "height": "고소", "lifting": "중량물인양", "loto": "정전·LOTO"}[kind],
            "title": title, "detail": detail, "hazards": hazards, "place": place, "route": route, "spans": spans(place + " " + route),
            "is_route": bool(route), "windows": windows or [win(t) for t in time], "move": win(move) if move else None, "workers": workers,
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


def got(h, rule, cause=None):
    return [x for x in h if x["rule"] == rule and (cause is None or x["cause"] == cause)]


ok = bad = 0


def check(name, cond, info=""):
    global ok, bad
    ok += bool(cond); bad += not cond
    print(("OK   " if cond else "틀림 ") + name + (f"  ({info})" if info and not cond else ""))


R = {r["id"]: r for r in pairs.rules()["rules"]}
HOT = lambda i, place="3BAY 08-10 칼럼 E42P 블록 상부", t="13:00~14:00", title="E42P 론지 CO2 용접": permit(  # noqa: E731
    i, "hot", title, place, [t], checks=["용접·용단"])

# ---- 1. HOT_PERSON next column: 노출 1 「거리 미확인(화재감시자 11m 안일 수 있음·차폐 확인)」, 2 columns away still out
h, *_ = judge(HOT(1), plan(1, "E43P 블록 마킹", "3BAY 11-12 칼럼 E43P 블록", ["13:00~14:00"], equip="마킹펜"))
x = got(h, "HOT_PERSON")
check("화기 바로 옆 칼럼 일반 작업 → HOT_PERSON 노출 1·3순위, 「거리 미확인(화재감시자 11m…)」",
      x and x[0]["E"] == 1 and x[0]["priority"] == 3 and "11m" in x[0]["relation"] and "거리 미확인" in x[0]["relation"], x and x[0]["relation"])
docs = {d["id"]: d for d in (HOT(1), plan(1, "E43P 블록 마킹", "3BAY 11-12 칼럼 E43P 블록", ["13:00~14:00"]))}
q = holdq._asks(x[0], docs) if x else []
check("옆 칼럼 판정보류 → 반장 질문(화기 쪽 차광·차폐·실제 거리, 상대 쪽 작업 위치)", {f for _, f, _ in q} >= {"shield", "work_zone"}, q)
h, *_ = judge(HOT(2), plan(2, "E44P 블록 마킹", "3BAY 13-14 칼럼 E44P 블록", ["13:00~14:00"], equip="마킹펜"))
check("화기에서 2칸 이상 떨어진 일반 작업 → HOT_PERSON 없음(근접 목록)", not got(h, "HOT_PERSON"), [r["rule"] for r in h])

# ---- 2. residual branches (sequence, cause first)
h, *_ = judge(HOT(3, t="09:00~10:00"), plan(3, "E42P 블록 표면 청소", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="와이어 브러시"))
x = got(h, "HOT_PERSON")
check("화기 뒤 같은 블록 청소 → 잔열·불씨 잔류 3순위(시간 분리로 해제 안 함)", x and x[0]["when"]["kind"] == "sequence" and x[0]["priority"] == 3, [r["rule"] for r in h])
check("같은 블록 잔류는 표기 「보수위험」(점수·순위는 3순위 그대로)", x and x[0]["judgement"] == "보수위험" and x[0]["E"] == 1, x and x[0]["judgement"])
h, *_ = judge(HOT(4, t="09:00~10:00"), plan(4, "E40P 블록 표면 청소", "3BAY 08-10 칼럼 E40P 블록", ["13:00~14:00"]))
check("화기 뒤 같은 칼럼 다른 블록 → HOT_PERSON 잔류 없음(같은 대상만)", not got(h, "HOT_PERSON"), [r["rule"] for r in h])
CUT = lambda i, t="09:00~10:00": permit(i, "height", "B21S 블록 상부 러그 절단·제거", "1BAY 14-16 칼럼 B21S 블록 상부", [t], records={"L3": "4.5m"})  # noqa: E731
h, *_ = judge(CUT(5), plan(5, "B21S 블록 하부 마킹", "1BAY 14-16 칼럼 B21S 블록", ["13:00~14:00"]))
x = got(h, "DROP_BELOW", "M005")
check("상부 절단 뒤 같은 칼럼 하부 작업 → DROP_BELOW 잔류(미회수 분리물) 3순위", x and x[0]["when"]["kind"] == "sequence" and "분리물" in x[0]["why_E"][-1] + R["DROP_BELOW"]["residual"], [r["rule"] for r in h])
h, *_ = judge(CUT(6, t="13:00~14:00"), plan(6, "B21S 블록 하부 마킹", "1BAY 14-16 칼럼 B21S 블록", ["09:00~10:00"]))
check("하부 작업이 먼저 끝나고 절단 → DROP_BELOW 잔류 없음(원인이 앞일 때만)", not got(h, "DROP_BELOW", "M006"), [(r["rule"], r["cause"]) for r in h])
h, *_ = judge(CUT(7), plan(7, "B21S 블록 내부 배관 취부", "1BAY 14-16 칼럼 B21S 블록 내부", ["13:00~14:00"], height="블록 내부"))
check("절단 뒤 같은 블록 내부 작업 → SUPPORT 잔류(지지 상실, 내부도 노출)", got(h, "SUPPORT", "M007") and got(h, "SUPPORT", "M007")[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
h, *_ = judge(plan(8, "D31C 블록 받침대 해체", "4BAY 03-05 칼럼 D31C 블록", ["09:00~10:00"], equip="유압잭"),
              plan(9, "D31C 블록 옆 마킹", "4BAY 03-05 칼럼 D31C 블록", ["09:00~10:00"]))
x = got(h, "SUPPORT")
check("받침대 해체 × 같은 블록 지상 작업 → SUPPORT 노출 2 이하(블록 주변 붕괴 영향)", x and x[0]["E"] <= 2 and any("받침·지그" in w for w in x[0]["why_E"]), [r["rule"] for r in h])
LOTO = lambda i, t="10:00~12:00", lo3="10:00 차단, 11:50 복구 후 시험운전", place="3BAY 천장크레인 OH-21-03 제어반 CP-03", **k: permit(  # noqa: E731
    i, "loto", "천장크레인 OH-21-03 제어반 수리", place, [t], records={"LO3": lo3, **k.pop("rec", {})}, **k)
LIFT = lambda i, t, crane="OH-21-03", place="3BAY 06-08 칼럼 E45P 블록": permit(  # noqa: E731
    i, "lifting", f"E45P 블록 인양 ({crane})", place, [t], detail=f"천장크레인 {crane} 사용")
h, *_ = judge(LOTO(10), LIFT(11, "14:00~15:00"))
x = got(h, "CRANE_LOTO")
check("크레인 정비 뒤 같은 크레인 인양 → CRANE_LOTO 잔류(복구·시험운전·인계) 3순위", x and x[0]["when"]["kind"] == "sequence" and x[0]["priority"] == 3, [r["rule"] for r in h])
h, *_ = judge(LOTO(12, t="13:00~15:00"), LIFT(13, "08:00~09:00"))
check("인양이 먼저 끝나고 정비 → CRANE_LOTO 잔류 없음(정비가 앞일 때만)", not got(h, "CRANE_LOTO"), [r["rule"] for r in h])
P1 = lambda i, t="13:00~14:00", **k: permit(i, "loto", "MCC-4 분기 증설", "4BAY 10칼럼 배전반 MCC-4", [t], records={"LO3": "13:00 차단, 14:00 복구"}, **k)  # noqa: E731
h, *_ = judge(P1(14), plan(14, "D32C 볼트 체결", "4BAY 11-13 칼럼 D32C 블록", ["15:00~16:00"], equip="전동공구 (전원 MCC-4)"))
check("정전 뒤 같은 분기 사용 → POWER_LOTO 잔류(복구·인계) 3순위", got(h, "POWER_LOTO") and got(h, "POWER_LOTO")[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
CONF = lambda i, t="13:00~15:00", place="3BAY 12-14 칼럼 E41P 블록 이중저 내부", w=3: permit(i, "confined", "E41P 이중저 탱크 내부 검사", place, [t], workers=w)  # noqa: E731
h, *_ = judge(plan(15, "E41P 블록 옆 자재 적치", "3BAY 12-14 칼럼 E41P 블록", ["09:00~10:00"], steps=("강재 적치",)), CONF(15))
x = got(h, "ACCESS")
check("적치 뒤 같은 블록 밀폐 진입 → ACCESS 잔류(적치물·잔해) 3순위", x and x[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
check("ACCESS 문구에 송기·환기 덕트·호스·케이블 손상", "덕트" in R["ACCESS"]["chain"][1] and "적치물" in R["ACCESS"]["chain"][1])
pl = pairs.sequence_plan({"a": "M016", "b": "WP-M-16", "reasons": [{"rule": "CONF_GAS", "cause": "M016", "exposed": "WP-M-16", "name": "x",
                                                                       "when": {"kind": "sequence", "start": "10:00", "end": "11:00", "gap": 60}, "sequence": {"first": "A"}}]}, {})
check("CONF_GAS 잔류 표시가 밸브 잠금이 아니라 호흡 위치 측정(「가스 밸브 잠금」 아님)",
      pl and not any("가스 밸브 잠금" in x for x in pl["left"]) and any("측정" in x for x in pl["left"]), pl and pl["left"])
check("잔류 문구가 밸브 잠금·종료로 해제되는 것처럼 읽히지 않음", all("잠금" not in (r.get("residual") or "").split("(")[0] or "해제" in r["residual"]
                                                    for r in R.values()), [r.get("residual") for r in R.values()])

# ---- 3. an unknown height, a height permit under 2m
h, *_ = judge(permit(17, "hot", "B21S 외판 불량부 절단·재용접", "1BAY 14-16 칼럼 B21S 블록 외판", ["09:00~11:00"], checks=["용접·용단"]),
              plan(17, "B21S 블록 표면 청소", "1BAY 14-16 칼럼 B21S 블록", ["09:00~11:00"]))
x = got(h, "DROP_BELOW", "M017")
check("높이 미기재 절단 → DROP 태그, 노출 상한 2·「작업 높이 미확인」(2m 요구 안 함)",
      x and x[0]["E"] <= 2 and any("작업 높이 미확인" in w for w in x[0]["why_E"]), [r["rule"] for r in h])
P = pairs.profile(permit(18, "height", "B21S 러그 절단", "1BAY 14-16 칼럼 B21S 블록", ["09:00~11:00"], records={"L3": "1.5m"}))
check("고소 허가 1.5m 절단 → DROP(2m 미만도 낙하 원인)", "DROP" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(19, "B21S 받침 정리", "1BAY 14-16 칼럼 B21S 블록", ["09:00~11:00"], height="지상 작업", steps=("볼트 해체",)))
check("지상 작업(높이 기재) 해체 → DROP 아님(높이 0이 적힘)", "DROP" not in P["tags"], P["tags"].keys())

# ---- 4. 서류상 인원 0
h, *_ = judge(HOT(20), plan(20, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], workers=0))
x = got(h, "HOT_PERSON")
check("상대 인원 0명 → 제외 아님, 노출 1·「서류상 인원 0: 실제 퇴실 확인 아님」", x and x[0]["E"] == 1 and any("서류상 인원 0" in w for w in x[0]["why_E"]), x and x[0]["why_E"])
q = holdq._asks(x[0], {"M020": HOT(20), "WP-M-20": plan(20, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"])}) if x else []
check("인원 0 판정보류 → 그 작업 반장에게 실제 들어가는 인원 질문", any(f == "workers_zero" and i == "WP-M-20" for i, f, _ in q), q)

# ---- 5. new rules
V = lambda i, lo3, t="13:00~15:00": permit(i, "loto", "MCC-4 분기 증설", "3BAY 배전반 MCC-4", [t], records={"LO3": lo3})  # noqa: E731
h, *_ = judge(V(21, "13:00 차단, 환기팬·조명도 같이 꺼짐, 14:50 재투입"), CONF(21))
x = got(h, "VENT_LOTO")
check("정전(환기·조명 같이 꺼짐) × 같은 BAY 밀폐 진입, 연결 미확인 → VENT_LOTO 노출 1", x and x[0]["E"] == 1 and x[0]["priority"] == 3, [r["rule"] for r in h])
h, *_ = judge(V(22, "13:00 차단, 14:50 재투입"),
              permit(22, "confined", "E41P 탱크 내부 검사", "3BAY 12-14 칼럼 E41P 블록 이중저 내부", ["13:00~15:00"], detail="송풍기 전원 MCC-4 사용, 환기팬 가동"))
x = got(h, "VENT_LOTO")
check("밀폐 서류에 환기팬 전원 MCC-4 → 같은 분기 확인: VENT_LOTO 노출 3", x and x[0]["E"] == 3 and x[0]["priority"] == 2, x and (x[0]["E"], x[0]["relation"]))
h, *_ = judge(V(23, "13:00 차단, 환기·조명 영향 없음, 14:50 재투입"), CONF(23))
x = got(h, "VENT_LOTO")
check("정전 답 「환기·조명 영향 없음」 → 쌍은 빠지지 않고 노출 1·확인 질문(부정은 경보를 지우지 않음)",
      x and x[0]["E"] == 1 and any("영향 없음" in g for g in x[0]["gaps"]), x and x[0]["gaps"])
h, *_ = judge(V(231, "13:00 차단, 14:00 복구"), CONF(231))
x = got(h, "VENT_LOTO")
check("정전 답이 시각뿐(Codex P1-3) → 의존 미확인: VENT_LOTO 노출 1로 남음", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(V(232, "13:00 차단, 14:50 재투입"),
              permit(232, "confined", "E41P 탱크 내부 검사", "3BAY 12-14 칼럼 E41P 블록 이중저 내부", ["13:00~15:00"], detail="조명 전원 MCC-4"))
x = got(h, "VENT_LOTO")
check("조명만 같은 분기 → E3이지만 결과는 조명 상실·대피 지연(산소결핍 아님, p235·341)", x and x[0]["E"] == 3 and "조명" in x[0]["accident"] and "산소결핍" not in x[0]["accident"],
      x and (x[0]["E"], x[0]["accident"]))
h, *_ = judge(V(233, "09:00 차단, 10:00 복구", t="09:00~10:00"), CONF(233, t="11:00~12:00"))
x = got(h, "VENT_LOTO")
check("정전이 끝난 뒤 진입 → VENT_LOTO 잔류(환기·조명 복구 확인 전) 3순위", x and x[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
h, *_ = judge(LOTO(24), plan(24, "3BAY 크레인 레일 주변 조명 교체", "3BAY 06-08 칼럼", ["10:00~12:00"], equip="고소작업대", height="거더 높이 14m"))
x = got(h, "CRANE_TEST")
check("크레인 정비(시험운전) × 같은 BAY 고소작업대 작업 → CRANE_TEST 노출 2·2순위", x and x[0]["E"] == 2 and x[0]["priority"] == 2, x and x[0]["why_E"])
h, *_ = judge(LOTO(25), plan(25, "E43S 블록 상부 볼트 체결", "3BAY 01-04 칼럼 E43S 블록", ["10:00~12:00"], height="블록 상부 3.0m"))
x = got(h, "CRANE_TEST")
check("크레인 정비 × 같은 BAY 블록 상부 작업 → CRANE_TEST 노출 1(훅 높이·구간 미확인)", x and x[0]["E"] == 1, x and x[0]["why_E"])
h, *_ = judge(V(26, "13:00 차단"), V(27, "13:30 차단"))
x = got(h, "SHARED_LOTO")
check("두 정비가 같은 MCC-4를 잠금 → SHARED_LOTO 노출 2·2순위(한 팀 복구가 다른 팀을 침)", x and x[0]["E"] == 2 and x[0]["priority"] == 2, [r["rule"] for r in h])
h, *_ = judge(LIFT(28, "10:30~11:30", crane="OH-21-02"), LOTO(28, rec={"LO4": "거더 위 주행부까지 올라감"}))
x = got(h, "OTHER_CRANE_REPAIR")
check("다른 크레인 인양 × 같은 BAY 크레인 수리 → OTHER_CRANE_REPAIR 노출 2, 거더면 추락 문구",
      x and x[0]["E"] == 2 and "추락" in x[0]["chain"][2], x and x[0]["chain"])
q = pairs._quiet(pairs.profile(LIFT(29, "10:30~11:30", crane="OH-21-02", place="1BAY 06-08 칼럼 E45P 블록")), pairs.profile(LOTO(29)), {"kind": "same", "bay": 3, "gap": 0})
check("다른 크레인 번호의 근접 문구: 「이어지지 않음」 단정 없이 상위·하위·주행로 미확인", q and "이어지지 않음" not in q["text"] and "미확인" in q["text"], q)
h, *_ = judge(HOT(30, place="4BAY 09-10 칼럼 D34C 블록"), permit(30, "loto", "MCC-4 분기 증설", "4BAY 10칼럼 배전반 MCC-4", ["13:00~14:00"]))
x = got(h, "HOT_PANEL")
check("화기 × 같은 칼럼 열린 배전반 → HOT_PANEL 노출 2", x and x[0]["E"] == 2, [r["rule"] for r in h])
h, *_ = judge(HOT(31), plan(31, "E42P 포장재·목재 받침 정리", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], steps=("포장재 수거",)))
x = got(h, "FIRE_SOLID")
check("화기 × 같은 블록 포장재·목재 → FIRE_SOLID 노출 2(새 규칙은 같은 블록만으로 E3 아님), 화재·화상만",
      x and x[0]["E"] == 2 and "전달 경로 미확인" in x[0]["relation"] and "폭발" not in " ".join(x[0]["chain"] + [x[0]["accident"]]), x and (x[0]["E"], x[0]["relation"]))
P = pairs.profile(plan(32, "B24S 보온재 부착", "2BAY 18-19 칼럼 B24S 블록", ["10:00~11:00"], mat="미네랄울 보온재"))
check("미네랄울 보온재 → 가연물(COMBUST) 아님", "COMBUST" not in P["tags"], P["tags"].keys())
h, *_ = judge(plan(33, "E42P 블록 옆 자재 임시 적치", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], steps=("강재 적치",)), HOT(33))
x = got(h, "EGRESS_BLOCK")
check("적치 × 같은 블록 화기 → EGRESS_BLOCK(아직 불이 없다는 이유로 빼지 않음) 3순위", x and x[0]["priority"] == 3 and x[0]["S"] == 2, [r["rule"] for r in h])
h, *_ = judge(plan(34, "B28P 블록 케이블 트레이 설치", "2BAY 13-15 칼럼 B28P 블록", ["13:00~15:00"], height="블록 상부 4.8m"),
              plan(35, "B28P 블록 하부 마킹", "2BAY 13-15 칼럼 B28P 블록", ["13:00~15:00"]))
x = got(h, "OVERHEAD_WORK")
check("상부 케이블 트레이 설치 × 아래 작업 → OVERHEAD_WORK 노출 2(보수위험)", x and x[0]["E"] == 2 and x[0]["judgement"] == "보수위험", [r["rule"] for r in h])
h, *_ = judge(HOT(36, title="E42P 론지 그라인딩"), permit(36, "lifting", "E42P 블록 인양", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"))
check("연삭 소음 × 같은 곳 인양 → NOISE_SIGNAL", got(h, "NOISE_SIGNAL"), [r["rule"] for r in h])
h, *_ = judge(HOT(37), CONF(37, place="3BAY 08-10 칼럼 E42P 블록 내부"))
check("아크 용접 × 같은 블록 내부 → WELD_RETURN(귀환전류, 노출 2 이하)", got(h, "WELD_RETURN") and got(h, "WELD_RETURN")[0]["E"] <= 2, [r["rule"] for r in h])
h, *_ = judge(permit(38, "lifting", "E42P 블록 인양", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"),
              plan(38, "E42P 블록 내부 송기 덕트 설치", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="송기 덕트, 케이블"))
check("블록 인양 × 그 블록에 덕트·케이블 연결한 작업 → LIFT_LINE", got(h, "LIFT_LINE"), [r["rule"] for r in h])
h, *_ = judge(HOT(39, title="E42P 비드 그라인딩"), plan(39, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("그라인딩 × 같은 블록 → GRIND_FLY(파편 비산)", got(h, "GRIND_FLY"), [r["rule"] for r in h])
h, *_ = judge(plan(40, "강재 지게차 운반", "3BAY 08-10 칼럼", ["13:00~14:00"], equip="지게차"), HOT(40))
check("지게차 경로 × 같은 칼럼 아크 용접 케이블 → CABLE_RUN", got(h, "CABLE_RUN"), [r["rule"] for r in h])

# ---- 6. words
for w, tagname in (("블록 트레일러 운반", "VEHICLE"), ("SPMT 블록 이송", "VEHICLE"), ("트랜스포터 블록 운반", "VEHICLE"), ("블록 대차 이동", "VEHICLE")):
    P = pairs.profile(plan(41, w, "3BAY 08-10 칼럼", ["09:00~10:00"]))
    check(f"'{w}' → {tagname}", tagname in P["tags"], P["tags"].keys())
P = pairs.profile(plan(42, "소형 자재 수동 대차 공급", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'수동 대차' → CART(차량 VEHICLE 아님)", "CART" in P["tags"] and "VEHICLE" not in P["tags"], P["tags"].keys())
h, *_ = judge(plan(43, "소형 자재 수동 대차 공급", "3BAY 08-10 칼럼", ["09:00~10:00"]), plan(44, "E42P 마킹", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"]))
check("수동 대차 × 같은 칼럼 보행 작업 → CART 규칙(S2)", got(h, "CART") and got(h, "CART")[0]["S"] == 2, [r["rule"] for r in h])
for w in ("용접재료 선정·불출", "용접봉·와이어 불출", "플럭스 보관 확인"):
    P = pairs.profile(plan(45, w, "3BAY 08-10 칼럼", ["09:00~10:00"]))
    check(f"'{w}' → 화기(SPARK) 아님", "SPARK" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(46, "E42P 부재 가열 교정", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'가열 교정' → 화기(열원)", "SPARK" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(47, "P-12 배관 누설시험", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'누설시험' → 압력시험", "PRESSURE" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(48, "외판 곤돌라 작업", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'곤돌라' → 고소작업대(MEWP)", "MEWP" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(49, "배관 질소 치환 후 용접", "3BAY 08-10 칼럼", ["09:00~10:00"], mat="질소"))
check("'질소' → 불활성가스(INERT)", "INERT" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(50, "배관 내부 확인", "3BAY 08-10 칼럼", ["09:00~10:00"], steps=("질소 미사용",)))
check("'질소 미사용' → 불활성가스 아님", "INERT" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(51, "N2 작업 배관 진입", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'N2'(작업 번호) → 질소 아님", "INERT" not in P["tags"], P["tags"].keys())
h, *_ = judge(plan(52, "B22S 탱크 내부 아르곤 퍼지 용접", "2BAY 05-06 칼럼 B22S 블록 탱크 내부", ["13:00~14:00"], equip="TIG 용접기", height="블록 내부"),
              plan(53, "B22S 탱크 내부 피스 정리", "2BAY 05-06 칼럼 B22S 블록 탱크 내부", ["13:00~14:00"], height="블록 내부"))
x = got(h, "CONF_GAS")
check("같은 블록 탱크 안 아르곤 × 같은 탱크 안 다른 작업 → 공기 경로 노출 2(ACC-AR2013)", x and x[0]["E"] == 2 and "공기" in x[0]["relation"], x and x[0]["relation"])

# ---- 7. a route read across its range; a block before an address
P = pairs.profile(plan(54, "소형 자재 공급", "1BAY 03→08칼럼", ["09:00~10:00"]))
check("'1BAY 03→08칼럼' → 03~08 전체 범위", any(s["c0"] == 3 and s["c1"] == 8 for s in P["spans"]), P["spans"])
h, *_ = judge(plan(55, "소형 자재 공급(수동 대차)", "1BAY 03→08칼럼", ["09:00~10:00"]), HOT(55, place="1BAY 05-06 칼럼 B26S 블록", t="09:00~10:00"))
check("경로 중간 칼럼(05)의 화기 → 같은 곳으로 판정(끝점만 보지 않음)", got(h, "HOT_PERSON") and got(h, "HOT_PERSON")[0]["E"] >= 2, [r["rule"] for r in h])
h, *_ = judge(HOT(56, place="3BAY 08-10 칼럼 E42P 블록 상부"), plan(56, "E42P 블록 마킹", "2BAY 01-02 칼럼 E42P 블록", ["13:00~14:00"]))
check("주소는 다른 BAY라도 같은 블록 E42P → 관계 유지(명시 연결이 주소보다 우선)", got(h, "HOT_PERSON") and got(h, "HOT_PERSON")[0]["E"] == 3, [r["rule"] for r in h])

# ---- 8. wording by method, oxygen, the case reference
h, *_ = judge(HOT(57, title="E42P 론지 가스절단"), plan(57, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "HOT_PERSON")
check("가스절단 → 「아크광」을 쓰지 않음(강한 빛·열)", x and "아크광" not in " ".join(x[0]["chain"]) + x[0]["headline"] and "강한 빛" in x[0]["chain"][1], x and x[0]["chain"])
check("흄은 같은 공기 공간일 때로 조건부", x and "같은 공기 공간" in x[0]["chain"][2], x and x[0]["chain"])
h, *_ = judge(HOT(58), plan(58, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "HOT_PERSON")
check("CO2 용접 → 「아크광」", x and "아크광" in x[0]["chain"][1] and "{" not in x[0]["headline"], x and (x[0]["chain"], x[0]["headline"]))
h, *_ = judge(HOT(59, title="E42P 론지 그라인딩"), plan(59, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "HOT_PERSON")
check("그라인딩 → 파편·소음(신호 방해), 아크광 없음", x and "연삭 파편" in x[0]["chain"][1] and "소음" in x[0]["chain"][2] and "아크광" not in x[0]["chain"][1], x and x[0]["chain"])
check("CONF_HOT: 산소 누출(과다) 문구·질문·23.5% 정지 기준(제618조)", "산소" in R["CONF_HOT"]["chain"][2] and "산소 호스" in R["CONF_HOT"]["ask"]
      and "23.5%" in R["CONF_HOT"]["post"]["stop"] and "제618조" in R["CONF_HOT"]["law"])
check("CRANE_SHARE 참고에 E16(한 인양 안의 잔류 연결 사고) 없음", not any("E16" in c for c in R["CRANE_SHARE"]["cases"]), R["CRANE_SHARE"]["cases"])
check("새 규칙의 조문은 재대조 전: 근거로 표시하지 않음(law_fit 맞음 아님)", all(R[k].get("law_fit") != "맞음" for k in ("VENT_LOTO", "FIRE_SOLID", "HOT_PANEL", "EGRESS_BLOCK")))
check("1순위 안내 문구에 「승인」 없음(croScan은 승인·일정 권한 없음)", "승인" not in pairs.rules()["priority"]["1"]["action"].replace("승인·일정 권한 없음", ""))

# ---- 9. a touching end and start, the next column of a lift and a fall, a reversed time
h, *_ = judge(permit(60, "lifting", "E45P 블록 이동", "3BAY 06-08 칼럼 E45P 블록", ["10:00~11:00"], detail="천장크레인 OH-21-03 사용"),
              plan(60, "E45P 블록 마킹", "3BAY 06-08 칼럼 E45P 블록", ["11:00~12:00"]))
x = got(h, "LOAD_OVER")
check("인양 끝 = 마킹 시작(맞닿음) → LOAD_OVER 노출 1 「앞 작업이 늦어지면 겹침」", x and x[0]["E"] == 1 and any("늦어지면 겹침" in w for w in x[0]["why_E"]), [r["rule"] for r in h])
docs = {"M060": permit(60, "lifting", "E45P", "3BAY 06-08 칼럼 E45P 블록", ["10:00~11:00"]), "WP-M-60": plan(60, "E45P 블록 마킹", "3BAY 06-08 칼럼 E45P 블록", ["11:00~12:00"])}
q = holdq._asks(x[0], docs) if x else []
check("맞닿음 → 앞 작업 반장에게 실제 종료 시각 질문", any(f == "end_time" for _, f, _ in q), q)
h, *_ = judge(permit(61, "lifting", "E45P 블록 이동", "3BAY 06-08 칼럼", ["10:00~11:00"], route="3BAY 06칼럼에서 08칼럼"),
              plan(61, "E46P 블록 마킹", "3BAY 09-10 칼럼 E46P 블록", ["10:00~11:00"]))
x = got(h, "LOAD_OVER")
check("인양 경로 바로 옆 칼럼 → LOAD_OVER 노출 1(하물 폭·회전·흔들림 외곽 미확인)", x and x[0]["E"] == 1 and "흔들림" in x[0]["relation"], [r["rule"] for r in h])
h, *_ = judge(CUT(62, t="13:00~14:00"), plan(62, "B22S 블록 마킹", "1BAY 17-18 칼럼 B22S 블록", ["13:00~14:00"]))
x = got(h, "DROP_BELOW", "M062")
check("상부 절단 바로 옆 칼럼 동시 작업 → DROP_BELOW 노출 1(회전·미끄러짐 범위 미확인)", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(CUT(63, t="09:00~10:00"), plan(63, "B22S 블록 마킹", "1BAY 17-18 칼럼 B22S 블록", ["13:00~14:00"]))
check("바로 옆 칼럼은 잔류(시간 분리) 쪽으로는 잡지 않음", not got(h, "DROP_BELOW", "M063"), [r["rule"] for r in h])
w = safety._win("22:00~02:00")
check("시간 역전 22:00~02:00 → 다음 날로 계산하되 「추정」 표시", w.get("next_day") and w.get("assumed_next_day"), w)
check("반장이 다음 날이라고 답했으면(T5) 추정 표시 없음", "assumed_next_day" not in safety._win("22:00~02:00", True))
h, *_ = judge(permit(64, "hot", "E42P 야간 용접", "3BAY 08-10 칼럼 E42P 블록", [], checks=["용접·용단"], windows=[w]),
              plan(64, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["23:00~23:30"]))
x = got(h, "HOT_PERSON")
check("역전 시간 쌍 → 「시간 역전: 익일인지 오기인지 확인」 표시, 창은 보수적으로 유지", x and x[0]["when"]["kind"] == "overlap" and any("시간 역전" in g for g in x[0]["gaps"]), x and x[0]["gaps"])
check("작업계획서 날짜가 다음 날이면 23:59로 자르지 않음", safety._dated_win("2026-10-29T22:00", "2026-10-30T02:00", "2026-10-29") == {"start": "22:00", "end": "02:00", "next_day": True})
check("제출본 계획서 정정도 날짜별(다음 날 종료 유지)", safety._plan_sub({"changed": ["end"], "start": "2026-10-29T22:00", "end": "2026-10-30T02:00"}, "2026-10-29")
      == {"windows": [{"start": "22:00", "end": "02:00", "next_day": True}]})
sp = spans("3BAY 14-12칼럼")
check("역순 칼럼 범위 14-12 → 범위로 읽되 표시(오기 확인)", sp and sp[0]["c0"] == 12 and sp[0]["c1"] == 14 and sp[0].get("rev"), sp)

# ---- 10. inferred solvent, plan × plan, sequence label
h, *_ = judge(HOT(65), plan(65, "E42P 블록 도장 터치업", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "FIRE")
check("사용물질 없이 작업명 「도장」 → 경보 유지, 근거에 「작업명에서 추정」", x and x[0]["priority"] == 1 and any("작업명에서 추정" in e["field"] for e in x[0]["evidence"]), x and x[0]["evidence"])
check("1순위 FIRE 표기는 확인위험(노출 3)", x and x[0]["judgement"] == "확인위험")
# plan × plan is not a candidate by design (설계 §8): checked through detect at the end of this file

# ---- 11. others 감사(인터뷰·멘토 손글씨·실물 양식·사고사례집·보고서·노션)
for w in ("B22S 맞대기 이음부 방사선투과검사(RT)", "P-12 용접부 RT 검사", "E44P 감마선 촬영"):
    P = pairs.profile(plan(70, w, "3BAY 08-10 칼럼", ["09:00~10:00"]))
    check(f"'{w}' → 방사선(RADIATION)", "RADIATION" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(71, "RT 판독·결과 정리", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'RT 판독·결과 정리' → 방사선 아님", "RADIATION" not in P["tags"], P["tags"].keys())
RT = lambda i, place="3BAY 08-10 칼럼 E42P 블록", t="13:00~14:00": plan(i, "E42P 용접부 방사선투과검사", place, [t], equip="이리듐 선원")  # noqa: E731
h, *_ = judge(RT(72), plan(72, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "RADIATION")
check("RT × 같은 블록 작업(서류 확인) → 1순위(멘토: RT×다른 작업 병행 불가, 제575조)", x and x[0]["priority"] == 1 and x[0]["forbidden"], x and x[0]["priority"])
h, *_ = judge(RT(73, t="09:00~10:00"), plan(73, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("RT 뒤 같은 곳 작업 → 잔류(선원 회수·측량) 3순위", got(h, "RADIATION") and got(h, "RADIATION")[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
h, *_ = judge(RT(74, place="3BAY 08-10 칼럼"), plan(74, "D34C 마킹", "4BAY 08-10 칼럼 D34C 블록", ["13:00~14:00"]))
x = got(h, "RADIATION")
check("RT × 옆 BAY 작업 → 노출 1(통제구역 범위 미확인), 제외 아님", x and x[0]["E"] == 1 and "통제구역" in x[0]["relation"], [r["rule"] for r in h])
for t, want in (("(준)밀폐공간 내부 작업(B11, F31, E11)", {"B11", "F31", "E11"}), ("E170(A) 블록 상부", {"E170(A)"}), ("B-01 블록 하부", {"B-01"}),
                ("OH-21-03 MCC-4 P-12 CO2 AH36 R42-01 LO3", set())):
    got_ = {b for b in pairs.BLOCK_ID.findall(t) if not pairs.NOT_BLOCK.search(b)}
    check(f"블록 번호 '{t}' → {sorted(want) or '없음'}", got_ == want, got_)
from server import explain, reflect  # noqa: E402
check("reflect·explain의 블록 번호 형식이 pairs와 같음", reflect.BLOCK.pattern in pairs.BLOCK_ID.pattern and pairs.BLOCK_ID.pattern in explain._IDS.pattern)
h, *_ = judge(permit(75, "confined", "B11 블록 탱크 내부 검사", "2BAY 05-06 칼럼 B11 블록 탱크 내부", ["13:00~14:00"]),
              plan(75, "B11 블록 외판 도장", "2BAY 05-06 칼럼 B11 블록", ["13:00~14:00"], mat="에폭시 도료, 신나"))
x = got(h, "CONF_PAINT")
check("실물형 블록 B11: 외판 도장(신나) × 같은 블록 탱크 내부 → CONF_PAINT 노출 2(이어지는지 미확인)·2순위", x and x[0]["E"] == 2 and x[0]["priority"] == 2, x and (x[0]["E"], x[0]["relation"]))
h, *_ = judge(permit(751, "confined", "E42P 내부 도장", "3BAY 08-10 칼럼 E42P 블록 탱크 내부", ["13:00~14:00"], detail="신나 사용"),
              permit(752, "confined", "E42P 내부 검사", "3BAY 08-10 칼럼 E42P 블록 탱크 내부", ["13:00~14:00"]))
x = got(h, "CONF_PAINT", "M751")
check("밀폐 안 도장 × 같은 공간 다른 밀폐 진입(Codex P1-2) → CONF_PAINT 1순위(둘 다 내부)", x and x[0]["priority"] == 1 and x[0]["E"] == 3, [(r["rule"], r["cause"]) for r in h])
P = pairs.profile(plan(76, "B11 신나 소분", "2BAY 05-06 칼럼", ["09:00~10:00"]))
check("'신나' → 유기용제(SOLVENT)", "SOLVENT" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(77, "지지대 연마", "2BAY 05-06 칼럼", ["09:00~10:00"]))
check("'연마' → 화기(SPARK)", "SPARK" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(78, "손 연마지 표면 정리", "2BAY 05-06 칼럼", ["09:00~10:00"]))
check("'연마지'(사포) → 화기 아님", "SPARK" not in P["tags"], P["tags"].keys())
UP = plan(79, "E42P 상부 지지대 그라인딩", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="그라인더", height="블록 상부 3.0m")
h, *_ = judge(UP, plan(80, "E42P 블록 하부 자재 정리", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "OVERHEAD_WORK", "WP-M-79")
check("높은 곳 연마 × 아래 자재 정리 → OVERHEAD_WORK 노출 2(공구·부스러기 낙하)", x and x[0]["E"] == 2, [r["rule"] for r in h])
h, *_ = judge(plan(81, "E42P 상부 지지대 그라인딩", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], equip="그라인더", height="블록 상부 3.0m"),
              plan(82, "E42P 블록 하부 자재 정리", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "OVERHEAD_WORK", "WP-M-81")
check("높은 곳 공구 작업 뒤 같은 블록 아래 작업 → 남은 공구 잔류 3순위(Codex 7, p24·346)", x and x[0]["when"]["kind"] == "sequence" and x[0]["E"] == 1, [r["rule"] for r in h])
P = pairs.profile(LOTO(83, rec={"LO4": "거더 위 주행부까지 올라감"}))
check("크레인 거더 위 정비(LO4) → 상부 낙하 원인(OVERHEAD)", "OVERHEAD" in P["tags"], P["tags"].keys())
h, *_ = judge(plan(84, "E45P 블록 서포트 높이 조정(잭업)", "3BAY 06-08 칼럼 E45P 블록", ["09:00~10:00"], equip="유압잭"),
              plan(85, "E45P 블록 하부 용접", "3BAY 06-08 칼럼 E45P 블록", ["09:00~10:00"], equip="CO2 용접기"))
x = got(h, "SUPPORT", "WP-M-84")
check("받친 블록 서포트 조정 × 그 블록 아래 용접 → SUPPORT 노출 2 이하(사례집 C02·C03)", x and x[0]["E"] <= 2, [r["rule"] for r in h])
cp = permit(86, "confined", "B22S 탱크 내부 압력 확인", "2BAY 05-06 칼럼 B22S 블록 탱크 내부", ["13:00~14:00"], checks=["압력사용"])
check("밀폐 양식 「압력사용」 체크 → 압력시험(PRESSURE) 태그", "PRESSURE" in pairs.profile(cp)["tags"], pairs.profile(cp)["tags"].keys())
h, *_ = judge(plan(87, "E41P 탱크 배관 아르곤 퍼지 용접", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"], equip="TIG 용접기", height="블록 내부"),
              permit(87, "hot", "E41P 블록 배관 절단", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"]))
x = got(h, "CONF_GAS")
check("아르곤 팀 × 같은 블록, 탱크 안인지 모르는 화기 작업 → CONF_GAS 노출 2(사례집 C45)", x and x[0]["E"] == 2, [r["rule"] for r in h])
q = holdq._asks(x[0], {"WP-M-87": plan(87, "x", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"]), "M087": permit(87, "hot", "x", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"])}) if x else []
check("→ 그 작업 반장에게 「블록 안·위·옆 중 실제 작업 위치」 질문", any(f == "position" and i == "M087" for i, f, _ in q), q)
h, *_ = judge(plan(88, "외판 고소작업대 용접", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="붐 고소작업대"),
              plan(89, "E42P 블록 옆 통행·마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("고소작업대 × 아래·옆 지상 작업 → MEWP_OVER(사례집 C26)", got(h, "MEWP_OVER", "WP-M-88"), [r["rule"] for r in h])
h, *_ = judge(permit(90, "hot", "B28P 보온재 주변 용단", "2BAY 13-15 칼럼 B28P 블록", ["13:00~14:00"], checks=["용접·용단"], detail="우레탄 보온재 옆"),
              plan(90, "B29P 블록 마킹", "2BAY 16-17 칼럼 B29P 블록", ["13:00~14:00"]))
x = got(h, "FIRE_SPREAD")
check("가연물 옆 화기 × 옆 칼럼 작업 → FIRE_SPREAD 노출 1(사례집 C16)", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(permit(91, "lifting", "E42P 부재 인양·잡기", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"),
              plan(91, "E42P 부재 취부·가용접", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("크레인이 잡은 부재 × 같은 블록 취부 → HELD_FIT(사례집 C11)", got(h, "HELD_FIT"), [r["rule"] for r in h])
h, *_ = judge(plan(92, "외판 고소작업대 볼트 체결", "3BAY 08-10 칼럼", ["13:00~14:00"], equip="고소작업대"),
              plan(93, "E42P 블록 도장", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], mat="유기용제 도료"))
check("고소작업대 × 같은 칼럼 도장 → EQUIP_IGNITION(방폭 확인)", got(h, "EQUIP_IGNITION"), [r["rule"] for r in h])
pl = pairs.sequence_plan({"a": "M094", "b": "WP-M-94", "reasons": [{"rule": "FIRE", "cause": "M094", "exposed": "WP-M-94", "name": "x",
                                                                       "when": {"kind": "sequence", "start": "10:00", "end": "11:00", "gap": 60}, "sequence": {"first": "B"}}]}, {})
check("도장이 먼저 끝나고 화기 → 남은 확인이 「용제 증기·젖은 도막」(잔불 아님)", pl and any("증기" in x for x in pl["left"]) and not any(x.endswith("잔불") for x in pl["left"]), pl and pl["left"])
check("남은 확인에 「남은 작업·재진입 계획 없음」", pl and any("재진입" in x for x in pl["left"]))
h, *_ = judge(HOT(95, place="3BAY 11-12 칼럼 E43P 블록"), CONF(95, place="3BAY 08-10 칼럼 E41P 블록 이중저 내부", t="13:00~14:00"))
x = got(h, "CONF_HOT")
check("다른 블록 바로 옆 칼럼 화기 × 밀폐 진입 → CONF_HOT 노출 1(개구부 거리 미확인)", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(permit(96, "lifting", "E45P 블록 이동", "3BAY 06-08 칼럼 E45P 블록", ["10:00~11:00"], detail="천장크레인 OH-21-03 사용"),
              permit(96, "height", "E45P 블록 상부 러그 절단", "3BAY 06-08 칼럼 E45P 블록 상부", ["10:00~11:00"], records={"L3": "4m"}))
x = got(h, "LOAD_OVER")
check("인양 × 같은 칼럼 고소 작업 → 문구에 작업발판 충격·추락", x and "작업발판" in x[0]["chain"][1], x and x[0]["chain"])
check("LOAD_OVER 참고에 E10(운반 사고) 없음", not any("E10" in c for c in R["LOAD_OVER"]["cases"]))
fx = pairs.confirmed_facts([{"qid": "CF1:P", "choice": "repair", "value": "", "q": {"choices": [{"id": "repair", "label": "보수·용접"}]}}])
check("밀폐 허가 CF1 「보수·용접」 확인 → 화기(SPARK) 사실", [x.get("tag") for x in fx] == ["SPARK"], fx)
P = pairs.profile(permit(97, "lifting", "블록 반출", "2BAY 05-06 칼럼", ["13:00~14:00"], detail="이동식 크레인으로 트레일러에 상차"))
check("작업 상세의 이동식 크레인·트레일러 → VEHICLE", "VEHICLE" in P["tags"], P["tags"].keys())


# ---- 12. Codex 검토(2026-11-01): 공개 경로 detect → floor → holdq.build, 제출본 경로, 기준본(v1) 대비 경보 보존
import types  # noqa: E402

V1_DIR = ROOT / "tools/fixtures/pairs_v1"           # the matching as it was before this reinforcement (frozen copy)
v1 = types.ModuleType("pairs_v1")
v1.__file__ = str(V1_DIR / "pairs.py")
exec(compile((V1_DIR / "pairs.py").read_text(encoding="utf-8").replace("from . import safety", "from server import safety"), v1.__file__, "exec"), v1.__dict__)
REAL = safety.data
LR = {"판정보류": 1, "보수위험": 2, "확인위험": 3}


def on_day(permits, plans, fn):
    D = {"date": "2026-10-29", "factory": "", "bays": 4, "cols": 20, "permits": permits, "plans": plans}
    safety.data = lambda: D
    try:
        return fn()
    finally:
        safety.data = REAL


def lost(old, new, skip=()):
    """every reason the v1 matching raised is still there, not lower in rank, S, E or label (skip: the deliberate exception)"""
    N = {(p["key"], r["rule"], r["cause"], r["exposed"]): r for p in new["pairs"] for r in p["reasons"]}
    bad = []
    for p in old["pairs"]:
        for r in p["reasons"]:
            k = (p["key"], r["rule"], r["cause"], r["exposed"])
            n = N.get(k)
            old_lab = "확인위험" if r["E"] == 3 else "보수위험" if r["E"] == 2 else "판정보류"
            if r["cause"] in skip:
                continue
            if not n or (n["priority"], -n["score"]) > (r["priority"], -r["score"]) or n["E"] < r["E"] or n["S"] != r["S"] \
                    or LR[pairs._label(n)] < LR[old_lab]:
                bad.append(k)
    return bad


old, new = v1.detect(), pairs.detect()
check("시연일: 기준본(v1)의 모든 경보가 남고 순위·S·E·판정 표기가 낮아지지 않음", not lost(old, new), lost(old, new)[:3])
ROD = plan(100, "용접봉·용접재료 불출", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"])
SYN_P = [permit(101, "height", "E42P 검사", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]),
         permit(102, "confined", "E42P 내부 도장", "3BAY 08-10 칼럼 E42P 블록 탱크 내부", ["13:00~14:00"], detail="신나 사용"),
         permit(103, "confined", "E42P 내부 검사", "3BAY 08-10 칼럼 E42P 블록 탱크 내부", ["13:00~14:00"]),
         permit(104, "loto", "MCC-4 정비", "3BAY 배전반 MCC-4", ["13:00~14:00"], records={"LO3": "13:00 차단, 14:00 복구"}),
         permit(105, "loto", "MCC-4 분기 증설", "3BAY 배전반 MCC-4", ["09:00~10:00"]),
         permit(106, "loto", "MCC-4 차단기 교체", "3BAY 배전반 MCC-4", ["11:00~12:00"]),
         permit(107, "hot", "E43P 론지 용접", "3BAY 11-12 칼럼 E43P 블록", ["13:00~14:00"], checks=["용접·용단"]),
         permit(108, "hot", "E42P 야간 용접", "3BAY 08-10 칼럼 E42P 블록", [], checks=["용접·용단"], windows=[safety._win("22:00~02:00")]),
         permit(109, "hot", "B21S 외판 절단", "1BAY 14-16 칼럼 B21S 블록", ["09:00~10:00"], checks=["용접·용단"]),
         permit(113, "hot", "E42P 블록 하부 외판 취부", "3BAY 08-10 칼럼 E42P 블록 하부", ["11:00~12:00"], checks=["용접·용단"])]
SYN_W = [plan(110, "E42P 지게차 운반", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="지게차"), ROD,
         plan(111, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["12:00~13:00"]),
         plan(112, "E42P 상부 지지대 연마", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], equip="그라인더", height="블록 상부 3.0m"),
         plan(114, "E42P 블록 야간 마킹", "3BAY 08-10 칼럼 E42P 블록", ["23:00~23:30"]),
         plan(115, "B21S 블록 표면 청소", "1BAY 14-16 칼럼 B21S 블록", ["09:00~10:00"])]
o2, n2 = on_day(SYN_P, SYN_W, v1.detect), on_day(SYN_P, SYN_W, pairs.detect)
check("Codex 재현 하루: 기준본 경보가 모두 남음(예외: 용접봉 불출의 화기 오탐 하나)", not lost(o2, n2, skip={"WP-M-100"}), lost(o2, n2, skip={"WP-M-100"})[:3])
k = lambda D: {(r["rule"], r["cause"], r["exposed"]) for p in D["pairs"] for r in p["reasons"]}  # noqa: E731
check("높이 미상 고소 허가 × 지게차 경로 → 기준본의 VEHICLE 경보 그대로(Codex P1-1)", ("VEHICLE", "WP-M-110", "M101") in k(n2), sorted(k(n2))[:5])
check("의도한 예외 하나: 「용접봉·용접재료 불출」만 적힌 작업은 화기가 아님(자료 84쪽 17번 작업특성)",
      any(r[1] == "WP-M-100" for r in k(o2)) and not any(r[1] == "WP-M-100" for r in k(n2)))
P = pairs.profile(plan(116, "용접봉 불출 후 보강재 용접", "3BAY 08-10 칼럼", ["13:00~14:00"]))
check("불출과 함께 실제 용접 행위가 적히면 화기 유지", "SPARK" in P["tags"], P["tags"].keys())
check("밀폐 안 도장 × 같은 공간 다른 밀폐(공개 경로) → CONF_PAINT", ("CONF_PAINT", "M102", "M103") in k(n2))
check("정전 답이 시각뿐 × 같은 BAY 밀폐 → VENT_LOTO(공개 경로)", ("VENT_LOTO", "M104", "M103") in k(n2))
check("같은 MCC-4를 앞뒤로 잠근 두 정비 → SHARED_LOTO 잔류(공개 경로)", any(r[0] == "SHARED_LOTO" for r in k(n2)), sorted(r for r in k(n2) if "LOTO" in r[0]))
check("상부 연마 뒤 같은 블록 아래 마킹 → OVERHEAD_WORK 잔류(공개 경로)", ("OVERHEAD_WORK", "WP-M-112", "M113") in k(n2))
check("마킹 12–13 뒤 화기 13–14(맞닿음, 원인이 뒤) → 「늦어지면 겹침」 확인(원인 선행과 별도)", any(r[0] == "HOT_PERSON" and r[2] == "WP-M-111" for r in k(n2)),
      sorted(r for r in k(n2) if "WP-M-111" in r))
fl2 = pairs.floor(n2, n2)
hb = on_day(SYN_P, SYN_W, lambda: holdq.build(fl2))
facts = {(q["doc"], q["fact"]) for x in hb["docs"] for q in x["questions"]}
check("holdq.build(공개 경로): 높이 미상 절단의 DROP E2 → 「바닥 기준 높이」 질문", ("M109", "height") in facts, sorted(facts)[:8])
check("holdq.build: 역전 시간(22:00~02:00) E3 경보에도 「익일인지 오기인지」 질문", ("M108", "time_rev") in facts, sorted(f for f in facts if f[0] == "M108"))
h, *_ = judge(plan(117, "E41P 탱크 배관 아르곤 퍼지 용접", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"], equip="TIG 용접기", height="블록 내부"),
              permit(117, "hot", "E41P 블록 배관 절단", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"]))
h3 = on_day([permit(117, "hot", "E41P 블록 배관 절단", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"])],
            [plan(117, "E41P 탱크 배관 아르곤 퍼지 용접", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"], equip="TIG 용접기", height="블록 내부")],
            lambda: holdq.build(pairs.detect()))
check("holdq.build: 탱크 안인지 모르는 CONF_GAS E2 → 「실제 작업 위치」 질문", any(q["fact"] == "position" for x in h3["docs"] for q in x["questions"]),
      [(q["doc"], q["fact"]) for x in h3["docs"] for q in x["questions"]])
# floor keeps the label with the numbers (Codex 9): the 0731 submission that moves the work
base = pairs.detect()
away = pairs.detect(submitted={"0731": {"place": "1BAY 01-02 칼럼 B10S 블록", "windows": [{"start": "06:00", "end": "07:00"}]}})
fl = pairs.floor(base, away)
b0 = next(p for p in base["pairs"] if p["key"] == "0731|WP-1029-01")
f0 = next(p for p in fl["pairs"] if p["key"] == "0731|WP-1029-01")
check("floor: 문서 기준 1순위·E3 경보는 판정 표기도 「확인위험」으로 유지", f0["judgement"] == b0["judgement"] == "확인위험"
      and all(pairs._label(r) == "확인위험" for r in f0["reasons"] if r["rule"] == "FIRE"), (f0["judgement"], [pairs._label(r) for r in f0["reasons"]]))
# dates through the submission (Codex P1-4): safety.hybrid_inputs → pairs.detect(submitted)
D = safety.data()
p33 = next(p for p in D["permits"] if p["id"] == "0733")
store_ = {"s4": ({"answers": [], "plan_values": [{"doc_no": "WP-1029-02", "place": "", "start": f"{D['date']}T10:00", "end": f"{D['date'][:8]}{int(D['date'][8:]) + 2:02d}T02:00",
                                                  "changed": ["end"]}]}, {}, {})}
_, sub4, _ = safety.hybrid_inputs(D, {p33["permit_no"]: {"id": "s4", "permit_no": p33["permit_no"], "dates": [D["date"]], "created": 1}}, store_.get)
w4 = (sub4.get("WP-1029-02") or {}).get("windows") or [{}]
check("제출본 계획서: 이틀 뒤 02:00 종료 → 날짜째 보존(23:59로 자르지 않음, days=2)", w4[0].get("days") == 2 and w4[0].get("end") == "02:00", w4)
wp2 = next(p for p in D["plans"] if p["id"] == "WP-1029-02")
P = pairs.profile(pairs._submitted(wp2, sub4["WP-1029-02"]))
check("적용 단계(pairs._submitted → profile)도 이틀 뒤까지 창 유지", P["wins"] and P["wins"][0][1] == 2 * 1440 + 120, P["wins"])
d1 = {"start": "08:00", "end": "10:00"}
check("08:00→10:00과 08:00→다음 날 10:00은 다른 창(정정이 버려지지 않음)",
      pairs._submitted({**wp2, "windows": [d1]}, {"windows": [{**d1, "next_day": True}]}).get("_sub"))
p32 = next(p for p in D["permits"] if p["id"] == "0732")
ans = [{"qid": f"T4:{p32['permit_no']}", "choice": "time", "value": "16:30"}]
vals = safety.submitted_values({"fields": p32["_fields"], "answers": ans}, D["date"], p32["permit_no"])
check("T4 잔불 확인 끝 16:30 → submitted_values에 잔류 전용 값(residual_end)", vals.get("residual_end") == "16:30", vals)
raw = pairs.detect(submitted={"0732": vals})
notes = [w for p in raw["pairs"] for r in p["reasons"] if r["cause"] == "0732" and r["when"]["kind"] == "sequence" for w in r["why_E"]]
check("감시 종료는 표시만, 해제 근거 아님: 0732 잔류 사유에 「감시 종료는 잔류 해제 확인이 아님」", any("감시 종료는 잔류 해제 확인이 아님" in w for w in notes)
      and all(r["E"] == 1 for p in raw["pairs"] for r in p["reasons"] if r["cause"] == "0732" and r["when"]["kind"] == "sequence"), notes[:2])
# routes, tags, negation, wording (Codex 5·6·10·11)
P = pairs.profile(plan(120, "소형 자재 순회 공급(수동 대차)", "3BAY 04→12→09→04축", ["09:00~10:00"]))
check("여러 지점 경로 04→12→09→04 → 04~12 전체", any(s["c0"] == 4 and s["c1"] == 12 for s in P["spans"]), P["spans"])
nC = on_day([permit(121, "hot", "E44P 마킹 보조", "3BAY 12칼럼", ["09:00~10:00"])], [plan(120, "소형 자재 순회 공급(수동 대차)", "3BAY 04→12→09→04축", ["09:00~10:00"])], pairs.detect)
check("그 경로 중간 12칼럼 작업과 CART(공개 경로)", any(r[0] == "CART" for r in k(nC)), sorted(k(nC)))
for w, t, fld in (("T/P 운반", "VEHICLE", "title"), ("수동 대차 운반", "CART", "detail"), ("E42P 연삭", "SPARK", "title")):
    d = permit(122, "hot", w if fld == "title" else "자재 이동", "3BAY 08-10 칼럼", ["09:00~10:00"], detail=w if fld == "detail" else "")
    check(f"'{w}'({fld}) → {t}", t in pairs.profile(d)["tags"], pairs.profile(d)["tags"].keys())
P = pairs.profile(plan(123, "외판 볼트 체결", "3BAY 08-10 칼럼", ["09:00~10:00"], equip="고소작업대, 전동공구", height=""))
check("높이 숫자 없는 고소작업대 작업 → 상부 낙하 후보(OVERHEAD), 전동공구 → 점화원(ELEC_TOOL)", "OVERHEAD" in P["tags"] and "ELEC_TOOL" in P["tags"], P["tags"].keys())
P = pairs.profile(plan(124, "블록 기밀시험 준비", "3BAY 08-10 칼럼", ["09:00~10:00"], height="블록 상부 3.0m"))
check("높은 곳 「기밀시험 준비」 → 상부 취급(OVERHEAD, 사례집 C43)", "OVERHEAD" in P["tags"], P["tags"].keys())
for w in ("질소 없이 작업", "질소 안 씀"):
    check(f"'{w}' → 불활성가스 아님", "INERT" not in pairs.profile(plan(125, "배관 작업", "3BAY 08-10 칼럼", ["09:00~10:00"], steps=(w,)))["tags"])
P = pairs.profile(plan(126, "수동  대차 운반", "3BAY 08-10 칼럼", ["09:00~10:00"]))
check("'수동  대차'(공백 둘) → CART, 차량 아님", "CART" in P["tags"] and "VEHICLE" not in P["tags"], P["tags"].keys())
P = pairs.profile(plan(127, "보온재 설치", "3BAY 08-10 칼럼", ["09:00~10:00"], mat="불연성 장갑"))
check("다른 물건의 「불연성」이 보온재를 비가연으로 만들지 않음", "COMBUST" in P["tags"], P["tags"].keys())
check("「난연 단열재」는 가연물(난연은 불연이 아님)", "COMBUST" in pairs.profile(plan(128, "난연 단열재 부착", "3BAY 08-10 칼럼", ["09:00~10:00"]))["tags"])
h, *_ = judge(HOT(129, title="E42P TIG 용접"), permit(129, "lifting", "E42P 블록 인양", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"))
check("소음 사실 없는 TIG 용접 × 인양 → NOISE_SIGNAL 없음", not got(h, "NOISE_SIGNAL"), [r["rule"] for r in h])
h, *_ = judge(permit(130, "lifting", "E42P 블록 인양", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"),
              plan(130, "E42P 블록 살수 호스 설치", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="살수 호스"))
x = got(h, "LIFT_LINE")
check("인양 × 살수 호스 → 결과는 당김·끼임(질식·감전 아님, 자료 p306)", x and "끼임" in x[0]["accident"] and "질식" not in x[0]["accident"] and "감전" not in x[0]["accident"], x and x[0]["accident"])
h, *_ = judge(HOT(131), permit(131, "loto", "OH-21-03 윤활", "3BAY 08-10 칼럼 천장크레인 OH-21-03", ["13:00~14:00"]))
x = got(h, "HOT_PANEL")
check("반을 여는지 모르는 정비 × 화기 → HOT_PANEL 노출 1·질문(반 개방 조건부)", x and x[0]["E"] == 1 and any("반을 열어" in g for g in x[0]["gaps"]), x and x[0]["gaps"])
h, *_ = judge(permit(132, "lifting", "E42P 부재 인양", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="천장크레인 OH-21-03 사용"),
              plan(132, "E42P 부재 취부", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("잡은 부재인지 모르는 HELD_FIT → 노출 1(조건부·질문)", got(h, "HELD_FIT") and got(h, "HELD_FIT")[0]["E"] == 1)
h, *_ = judge(HOT(133), CONF(133, place="3BAY 08-10 칼럼 E42P 블록 내부"))
check("귀환 경로가 적히지 않은 WELD_RETURN → 노출 1(조건부·질문)", got(h, "WELD_RETURN") and got(h, "WELD_RETURN")[0]["E"] == 1)
h, *_ = judge(permit(134, "loto", "OH-21-03 제어반 수리", "3BAY 천장크레인 OH-21-03", ["10:00~12:00"], records={"LO3": "10:00 차단, 11:50 복구"}),
              plan(134, "레일 조명 교체", "3BAY 06-08 칼럼", ["10:00~12:00"], equip="고소작업대", height="거더 높이 14m"))
check("「복구」만 적힌 크레인 정비 → 시험운전 미확인: CRANE_TEST 노출 1", got(h, "CRANE_TEST") and got(h, "CRANE_TEST")[0]["E"] == 1)
h, *_ = judge(plan(135, "배관 아르곤 퍼지 용접", "3BAY 08-10 칼럼", ["13:00~14:00"], equip="TIG 용접기"), CONF(135, place="3BAY 08-10 칼럼 내부"))
x = got(h, "CONF_GAS")
check("같은 칼럼, 블록·계통 번호 없음 → CONF_GAS 노출 1(빠지지 않음, others 꼭 보강)", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(HOT(136), plan(136, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
x = got(h, "HOT_PERSON")
hv, *_ = judge(V(137, "13:00 차단"), CONF(137))
xv = got(hv, "VENT_LOTO")
check("검수된 조문만 화면 필드로(기존 규칙 law 있음, 새 규칙 law 빈칸·law_note)", x and x[0]["law"] and xv and xv[0]["law"] == "" and xv[0].get("law_note"),
      xv and (xv[0]["law"], xv[0].get("law_note")))
for t, want in (("B11축", set()), ("V12 밸브", set()), ("B11 블록", {"B11"})):
    check(f"블록 문맥 '{t}' → {sorted(want) or '없음'}", set(pairs.BLOCK_ID.findall(t)) == want, pairs.BLOCK_ID.findall(t))
P = pairs.profile({**plan(138, "마킹", "3BAY 08-10 칼럼", ["09:00~10:00"]), "target": "B-01"})
check("대상ID 칸의 단독 「B-01」 → 블록", "B-01" in P["ids"]["blocks"], P["ids"]["blocks"])
from server import explain as EX  # noqa: E402
dP = plan(139, "E42P 도장", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], mat="유기용제 도료")
dH = HOT(139, t="11:00~12:00")
h, *_ = judge(dH, dP)
x = got(h, "FIRE")
cl = EX.claims({"reasons": [x[0]]}, {dP["id"]: dP, dH["id"]: dH}) if x else {"U": []}
check("explain: 도장이 먼저면 남는 위험을 「용제 증기」로(순서별 잔류)", any("증기" in u["text"] for u in cl["U"]), [u["text"] for u in cl["U"]])
fx = pairs.confirmed_facts([{"qid": "CF3:P", "choice": "text", "value": "DB-2에서 환기팬·조명", "q": {"choices": []}},
                            {"qid": "CF4:P", "choice": "yes", "value": "CO2 용접 1곳", "q": {"choices": [{"id": "yes", "label": "함"}]}},
                            {"qid": "D7:P", "choice": "text", "value": "질소, 10:00 가압 ~ 11:30 감압", "q": {"choices": []}}])
check("확인 답 CF3(분전반)·CF4(안에서 화기)·D7(질소 시험) → dep_panel·SPARK·INERT·PRESSURE",
      {"dep_panel", "SPARK", "INERT", "PRESSURE"} <= {x.get("tag") or x.get("ids", ("",))[0] for x in fx}, fx)
cpm = {**CONF(140), "permit_no": "PN-140", "_confirmed": fx}
lt = permit(141, "loto", "DB-2 분기 정비", "3BAY 배전반 DB-2", ["13:00~15:00"], records={"LO3": "13:00 차단"})
nv = on_day([lt, {**CONF(140), "permit_no": "PN-140"}], [], lambda: pairs.detect(confirmed={"PN-140": fx}))
xv = [r for p in nv["pairs"] for r in p["reasons"] if r["rule"] == "VENT_LOTO"]
check("확인된 CF3가 같은 분기(DB-2) → VENT_LOTO E3, 결과는 환기·조명 각각", xv and xv[0]["E"] == 3 and "산소결핍" in xv[0]["accident"] and "조명" in xv[0]["accident"],
      xv and (xv[0]["E"], xv[0]["accident"]))
two_plans = on_day([], [plan(142, "지게차 운반", "3BAY 08-10 칼럼", ["09:00~10:00"], equip="지게차"), plan(143, "마킹", "3BAY 08-10 칼럼", ["09:00~10:00"])], pairs.detect)
check("계획서×계획서는 설계상 후보 아님(설계 §8): 계획서만 있는 날은 후보 0", two_plans["stats"]["candidates"] == 0 and not two_plans["pairs"])


# ---- 13. multiturn 최종 계약(impl/multiturn.md): 시간 필드·facts·live_answers·eff_choice — 공개 경로
D = safety.data()
p32 = next(p for p in D["permits"] if p["id"] == "0732")
no = p32["permit_no"]
t4 = {"qid": f"T4:{no}", "choice": "time", "value": "16:30"}
vals = safety.submitted_values({"fields": p32["_fields"], "answers": [t4]}, D["date"], no)
check("계약: 작업 창은 windows_work(잔불 끝으로 늘리지 않음), 잔불 끝은 residual_end로만", "windows" not in vals and vals.get("residual_end") == "16:30", vals)
vals_c6 = safety.submitted_values({"fields": p32["_fields"], "answers": [t4, {"qid": f"C6.T4:{no}", "choice": "doc", "value": ""}]}, D["date"], no)
check("C6 「서류가 맞음」으로 철회한 T4는 쓰지 않음(live_answers)", "residual_end" not in vals_c6, vals_c6)
raw = pairs.detect(submitted={"0732": vals})
base = pairs.detect()
fl = pairs.floor(base, raw)
rk = lambda D: {(p["key"], r["rule"], r["cause"], r["exposed"]): (r["priority"], -r["score"]) for p in D["pairs"] for r in p["reasons"]}  # noqa: E731
check("잔불 감시 끝은 해제 근거가 아님: 반영 뒤에도 문서 기준 경보가 그대로(순위·점수)", all(rk(fl).get(k_, (9, 0)) <= v for k_, v in rk(base).items()))
fx = pairs.confirmed_facts([{"qid": "CF3:P1", "choice": "text", "value": "DB-2에서 환기팬", "q": {}},
                            {"qid": "C6.CF3:P1", "choice": "doc", "value": ""}])
check("철회한 CF3 답은 사실이 아님(live_answers)", not fx, fx)
fx = pairs.confirmed_facts([{"qid": "CF2:P1", "choice": "text", "value": "아르곤 퍼지 라인 없음", "q": {}}])
check("CF2 글 「아르곤 퍼지 라인 없음」(eff_choice 부정) → 불활성가스 사실 아님", not fx, fx)
fx = pairs.confirmed_facts([{"qid": "CF2:P1", "choice": "text", "value": "퍼지 라인이 있으면 차단 예정", "q": {}}])
check("조건문(「있으면」)은 부정으로 읽지 않음 → 그대로 글(사실로 남음)", [x.get("tag") for x in fx] == ["INERT"], fx)
L = permit(150, "lifting", "E45P 블록 이동", "3BAY 06-08 칼럼 E45P 블록", ["13:00~16:00"], detail="천장크레인 OH-21-03 사용")
Pm = pairs.profile(pairs._submitted(L, {"stage": [{"start": "14:00", "end": "14:30"}], "stage_written": [{"start": "13:00", "end": "13:30"}]}))
check("인양 stage(move)는 움직이는 구간으로만, 작업 창(13~16)은 그대로", Pm["moves"] == [(840, 870)] and Pm["wins"] == [(780, 960)], (Pm["moves"], Pm["wins"]))
Pr = pairs.profile(pairs._submitted(HOT(151), {"residual_end": "01:00", "residual_next_day": True}))
check("익일 잔불 끝(01:00 다음 날) → 분으로 1500(창은 늘리지 않음)", Pr["res_end"] == 1500 and Pr["wins"] == [(780, 840)], (Pr["res_end"], Pr["wins"]))


# ---- 14. 마지막 Codex 검토(codex_final_out.md #2·#3·#6·#7): 기준본 보존 확대, C5 정정, 확정 이동 구간, 날짜 교차
RAD_P = [permit(160, "height", "E42P 상부 점검", "3BAY 08-10 칼럼 E42P 블록", ["09:00~11:00"], hazards="방사선"),
         permit(161, "confined", "E41P 탱크 내부 검사", "3BAY 12-14 칼럼 E41P 블록 탱크 내부", ["13:00~14:00"])]
RAD_W = [plan(160, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["09:00~11:00"]),
         plan(161, "용접봉 운반", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"]),
         plan(162, "용접봉 불출", "3BAY 12-14 칼럼 E41P 블록", ["13:00~14:00"])]
o3, n3 = on_day(RAD_P, RAD_W, v1.detect), on_day(RAD_P, RAD_W, pairs.detect)
check("기준본 보존(확대): 유해위험요소의 방사선·「용접봉 운반」도 기준본 경보 유지(예외는 「불출」만)", not lost(o3, n3, skip={"WP-M-162"}), lost(o3, n3, skip={"WP-M-162"}))
x = [r for p in n3["pairs"] for r in p["reasons"] if r["rule"] == "RADIATION" and r["cause"] == "M160"]
check("유해위험요소 칸에만 적힌 방사선 → 기준본처럼 2순위·9점, 「이 작업이 촬영하는지 확인」 질문", x and x[0]["priority"] == 2 and x[0]["score"] == 9
      and any("유해위험요소 칸에만" in g for g in x[0]["gaps"]), x and (x[0]["priority"], x[0]["score"], x[0]["gaps"]))
hq = on_day(RAD_P, RAD_W, lambda: holdq.build(pairs.detect()))
check("그 질문이 holdq.build에 생김(방사선 쪽 반장)", any(q["doc"] == "M160" for d_ in hq["docs"] for q in d_["questions"]))
check("「용접봉 운반」 × 밀폐 → 기준본 CONF_HOT 그대로, 「용접봉 불출」만 예외", ("CONF_HOT", "WP-M-161", "M161") in k(n3) and ("CONF_HOT", "WP-M-162", "M161") not in k(n3)
      and ("CONF_HOT", "WP-M-162", "M161") in k(o3))
# #3: a C5 correction stands as that item's answer
fx = pairs.confirmed_facts([{"qid": "CF2:P9", "choice": "none", "value": ""},
                            {"qid": "C5.CF2:P9", "choice": "free", "value": "아르곤 퍼지 라인 V-12 연결 있음"}])
check("CF2 「없음」 뒤 C5.CF2 정정 「아르곤 퍼지 라인 V-12 연결 있음」 → 불활성가스 사실", [x_.get("tag") for x_ in fx] == ["INERT"], fx)
cf = {**CONF(163), "permit_no": "PN-163"}
gp = plan(163, "E41P 배관 마킹", "3BAY 12-14 칼럼 E41P 블록 이중저 내부", ["13:00~15:00"], height="블록 내부")
nc = on_day([cf], [gp], lambda: pairs.detect(confirmed={"PN-163": fx}))
check("그 정정으로 CONF_GAS가 생김(공개 경로 detect)", any(r[0] == "CONF_GAS" and r[1] == "M163" for r in k(nc)), sorted(k(nc)))
# #6: the confirmed moving part is used now even with an old move; floor keeps the old document alarm
LM = {**permit(164, "lifting", "E45P 블록 이동", "3BAY 06-08 칼럼 E45P 블록", ["09:00~17:00"], detail="천장크레인 OH-21-03 사용", move="13:00~14:00")}
W15 = plan(164, "E45P 블록 옆 마킹", "3BAY 06-08 칼럼 E45P 블록", ["15:00~16:00"])
b6 = on_day([LM], [W15], pairs.detect)
r6 = on_day([LM], [W15], lambda: pairs.detect(submitted={"M164": {"stage": [{"start": "15:00", "end": "16:00"}],
                                                                   "stage_written": [{"start": "13:00", "end": "14:00"}], "full_end": "17:00"}}))
check("확정한 이동 구간 15–16시가 옛 이동(13–14시) 대신 쓰임 → LOAD_OVER(Codex final #6)", ("LOAD_OVER", "M164", "WP-M-164") in k(r6) and
      ("LOAD_OVER", "M164", "WP-M-164") not in k(b6), sorted(k(r6)))
f6 = pairs.floor(b6, r6)
check("floor: 문서 기준 경보는 모두 남음", not lost(b6, f6))
ev = [e["value"] for p in r6["pairs"] for r in p["reasons"] for e in r["evidence"] if e["doc"] == "M164" and e["field"].startswith("시간")]
check("stage_written·full_end가 _submitted를 지나 근거에 표시", ev and "서류에 적힌 단계 13:00–14:00" in ev[0] and "전체 작업 끝 17:00" in ev[0], ev[:1])
# #7: a dated change cut by each review day; a night window shows on the next date
pv = {"changed": ["start", "end"], "start": "2026-10-31T10:00", "end": "2026-11-02T02:00"}
check("10/31 10:00 → 11/2 02:00 정정: 11/1에 하루 종일(다음 날까지 이어짐)", safety._plan_sub(pv, "2026-11-01").get("windows") == [{"start": "00:00", "end": "02:00", "next_day": True}],
      safety._plan_sub(pv, "2026-11-01"))
check("같은 정정이 11/2에는 00:00~02:00", safety._plan_sub(pv, "2026-11-02").get("windows") == [{"start": "00:00", "end": "02:00"}], safety._plan_sub(pv, "2026-11-02"))
dw = safety._day_wins({"2026-11-01": ["22:00~02:00"]}, "2026-11-02", True)
check("허가서 11/1 22:00~익일 02:00 → 11/2 조회에도 00:00~02:00", [(w["start"], w["end"]) for w in dw] == [("00:00", "02:00")], dw)
check("제출 날짜 색인: 밤 작업은 다음 날짜도", safety.spanned_dates({"2026-11-01": ["22:00~익일 02:00"]}) == ["2026-11-01", "2026-11-02"]
      and safety.spanned_dates({"2026-11-01": ["08:00~17:00"]}) == ["2026-11-01"])

print(f"\n{ok}/{ok + bad}")
sys.exit(1 if bad else 0)
