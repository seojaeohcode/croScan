"""쌍작업 매칭 — 최종 전수 검토(2026-11-01, Codex astra 2묶음 + 검토자 7명)에서 확인된 빠짐의 보강 시험.
Each case is a finding reproduced on the code before the fix (a danger the safety team was not told of), now raised;
a new one with a weak link is 3순위 판정보류 (E1), never a confirmed alarm. The v1 baseline (check_pairs_material §12)
still holds: no alarm of before is lowered.
  python tools/check_pairs_final.py
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
    return {"type": "plan", "id": f"WP-F-{i:02d}", "company": "시험", "title": title, "place": place, "spans": spans(place), "is_route": False,
            "windows": [win(t) for t in time], "move": None, "workers": workers, "target": "", "_items": items}


def permit(i, kind, title, place, time, detail="", checks=(), records=None, workers=3):
    f = {f"c{k}": {"name": c, "type": "check", "value": True} for k, c in enumerate(checks)}
    return {"type": "permit", "id": f"F{i:03d}", "kind": kind, "label": kind, "title": title, "detail": detail, "hazards": "",
            "place": place, "route": "", "spans": spans(place), "is_route": False, "windows": [win(t) for t in time], "move": None,
            "workers": workers, "_fields": f, "_records": [{"item": k, "value": v} for k, v in (records or {}).items()]}


def judge(a, b):
    A, B = pairs.profile(a), pairs.profile(b)
    out = []
    for rule in pairs.rules()["rules"]:
        for x, y in ((A, B), (B, A)):
            h = pairs._judge(rule, x, y)
            if h and h["priority"]:
                out.append(h)
    return sorted(out, key=lambda h: (h["priority"], -h["score"])), A, B


got = lambda h, rule: [x for x in h if x["rule"] == rule]  # noqa: E731
ok = bad = 0


def check(name, cond, info=""):
    global ok, bad
    ok += bool(cond); bad += not cond
    print(("OK   " if cond else "틀림 ") + name + (f"  ({info})" if info and not cond else ""))


HOT = lambda i, place="3BAY 08-10 칼럼", t="13:00~15:00", title="E42P 론지 용접": permit(i, "hot", title, place, [t], checks=["용접·용단"])  # noqa: E731
GROUND = lambda i, place="3BAY 08-10 칼럼", t="13:00~15:00", title="블록 마킹": plan(i, title, place, [t], equip="마킹펜")  # noqa: E731

print("상부·낙하 (Codex P1·L112·153, P4 높이 2m 미만, 멘토 #50 상하 병행)")
h, *_ = judge(plan(1, "E42P 블록 상부 배관 서포트 설치", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], equip="임팩트 렌치", height=""),
              plan(2, "E42P 블록 치수 측정", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], equip="줄자"))
x = got(h, "OVERHEAD_WORK")
check("계획서 작업명에만 「상부 설치」(높이 칸 빈칸) → 아래 작업과 OVERHEAD_WORK 판정보류(높이·위아래 미확인)",
      x and x[0]["E"] == 1 and "위아래 관계 미확인" in " ".join(x[0]["why_E"]), [r["rule"] for r in h])
h, *_ = judge(permit(3, "hot", "E42P 블록 상부 브래킷 취부 용접", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], checks=["용접·용단"]),
              plan(3, "E42P 블록 치수 측정", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], equip="줄자"))
check("화기 허가 작업명에 「상부」(높이 칸 없음) → OVERHEAD_WORK도", got(h, "OVERHEAD_WORK"), [r["rule"] for r in h])
h, *_ = judge(permit(4, "hot", "브래킷 절단", "3BAY 08-10 칼럼", ["13:00~15:00"], detail="작업높이 1.5m", checks=["용접·용단"]), GROUND(4))
x = got(h, "DROP_BELOW")
check("높이 1.5m(2m 미만)로 적힌 절단 → DROP_BELOW 판정보류(빼지 않음)", x and x[0]["E"] == 1 and "2m 미만" in " ".join(x[0]["why_E"]), [r["rule"] for r in h])
h, *_ = judge(permit(5, "hot", "브래킷 절단", "3BAY 08-10 칼럼", ["13:00~15:00"], detail="작업높이 0m 지상", checks=["용접·용단"]), GROUND(5))
check("바닥(0m)에서 하는 절단은 낙하로 보지 않음", not got(h, "DROP_BELOW"), [r["rule"] for r in h])
a = permit(6, "height", "E42P 블록 상부 그라인딩", "3BAY 08-10 칼럼 E42P 블록 상부", ["13:00~15:00"], detail="작업높이 4m",
           records={"B3": "하부에서 마킹 작업 13:00~15:00 (시험)"})
h, *_ = judge(a, GROUND(6))
x = got(h, "OVERHEAD_WORK")
check("상하 동시, 반장이 「아래 작업」이라고 답함 → 금지 조합 1순위(멘토 「상·하 병행 절대 불가」)", x and x[0]["priority"] == 1 and x[0]["forbidden"], x and (x[0]["priority"], x[0]["E"]))
h, *_ = judge(permit(7, "height", "E42P 블록 상부 그라인딩", "3BAY 08-10 칼럼 E42P 블록 상부", ["13:00~15:00"], detail="작업높이 4m"),
              plan(7, "E42P 블록 하부 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], equip="마킹펜"))
x = got(h, "OVERHEAD_WORK")
check("같은 블록이라는 사실만으로는 금지 조합 아님(바로 아래인지 미확인: 2순위)", x and x[0]["priority"] == 2 and not x[0]["forbidden"], x and x[0]["priority"])

print("화재 (Codex P3·L80, P5·L20, 인터뷰 00:21)")
h, *_ = judge(plan(8, "포장재·종이 박스 임시 적치", "3BAY 08-10 칼럼", ["08:00~09:00"]), HOT(8, t="10:00~12:00"))
x = got(h, "FIRE_SOLID")
check("가연물을 먼저 쌓고 나중에 화기 → FIRE_SOLID 판정보류 「남은 가연물」", x and "남은 가연물" in " ".join(x[0]["why_E"]), [r["rule"] for r in h])
check("「종이」도 가연물", "COMBUST" in pairs.profile(plan(9, "종이 수거", "3BAY 08-10 칼럼", ["08:00~09:00"]))["tags"])
h, *_ = judge(HOT(10), plan(10, "F11 블록 도장(유기용제)", "4BAY 09-10 칼럼", ["13:00~15:00"], mat="신나"))
x = got(h, "FIRE")
check("옆 BAY 같은 칼럼대 화기 × 도장 → FIRE 판정보류(불티가 넘어가는지 미확인)", x and x[0]["E"] == 1 and "옆 BAY" in x[0]["relation"], [r["rule"] for r in h])
h, *_ = judge(plan(11, "LPG 가스 용기 교체", "3BAY 08-10 칼럼", ["13:00~14:00"]), HOT(11))
x = got(h, "FIRE_GAS")
check("LPG 용기 교체 × 같은 칼럼 화기 → FIRE_GAS(새 규칙, 2순위)", x and x[0]["priority"] == 2, [r["rule"] for r in h])
check("산소는 가연성 가스 태그 아님", "FLAM_GAS" not in pairs.profile(plan(12, "산소 용기 교체", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])

print("잔류 (Codex P3·L47, 재독 A: 블록 번호 없이 같은 칼럼)")
h, *_ = judge(HOT(13, t="09:00~10:00"), plan(13, "잔재 청소·수거", "3BAY 08-10 칼럼", ["13:00~14:00"], equip="빗자루"))
x = got(h, "HOT_PERSON")
check("화기 뒤 같은 칼럼 잔재 청소(블록 번호 없음) → 잔열·불씨 잔류 판정보류", x and x[0]["when"]["kind"] == "sequence" and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(HOT(14, t="09:00~10:00"), GROUND(14, t="13:00~14:00"))
check("화기 뒤 같은 칼럼 잔재와 무관한 작업 → 잔류 없음", not got(h, "HOT_PERSON"), [r["rule"] for r in h])

print("크레인·정전 (part7 EL05·EL09·EL13, 재독 B L437)")
LOTO = lambda i, t="08:00~12:00", title="OH-21-03 크레인 브레이크 교체 후 시험운전": permit(i, "loto", title, "3BAY 01-20 칼럼", [t])  # noqa: E731
h, *_ = judge(LOTO(15), permit(16, "height", "주행로 레일 상부 점검 보수", "3BAY 05-06 칼럼", ["13:00~15:00"]))
x = got(h, "CRANE_TEST")
check("크레인 정비 허가 시간 뒤 주행로 상부 작업 → 시험운전 잔류 판정보류", x and x[0]["when"]["kind"] == "sequence", [r["rule"] for r in h])
h, *_ = judge(LOTO(17), permit(17, "height", "E42P 블록 상부 마킹", "3BAY 05-06 칼럼 E42P 블록 상부", ["13:00~15:00"], detail="작업높이 3m"))
check("정비 뒤 블록 상부 작업(주행로 높이 아님)에는 시험운전 잔류를 붙이지 않음", not any(r["rule"] == "CRANE_TEST" and r["when"]["kind"] == "sequence" for r in h))
h, *_ = judge(LOTO(18, t="08:00~12:00", title="OH-21-03 크레인 정비 후 시험운전"), GROUND(18, place="3BAY 05-06 칼럼", t="09:00~11:00"))
x = got(h, "CRANE_TEST")
check("시험운전이 적힌 정비 × 같은 BAY 지상 작업(동시) → 판정보류 「훅 아래 지상 작업인지」", x and x[0]["E"] == 1, [r["rule"] for r in h])
h, *_ = judge(permit(19, "loto", "MCC-4 분전반 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
              permit(19, "hot", "E42P 용접(국소배기 사용)", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]))
check("정전 × 국소배기를 쓰는 화기 → VENT_LOTO 판정보류", got(h, "VENT_LOTO"), [r["rule"] for r in h])
h, *_ = judge(permit(20, "loto", "MCC-4 분전반 정비", "4BAY 17-19 칼럼", ["13:00~15:00"]),
              plan(20, "D33C 블록 내부 환기팬·작업등 설치 (MCC-5 전원)", "4BAY 17-19 칼럼 D33C 블록", ["13:00~15:00"], height="블록 내부 4.2m"))
check("그 작업의 환기·작업등이 다른 전원(MCC-5)이라고 적힘 → VENT_LOTO 없음(시연 N04)", not got(h, "VENT_LOTO"), [r["rule"] for r in h])

print("계통·지지·가스 (Codex P5·L113, part6·7 MV07, 멘토 #45·사례3)")
h, *_ = judge(plan(21, "P-12 배관 수압시험", "2BAY 05-06 칼럼", ["13:00~15:00"], equip="수압펌프"),
              permit(21, "hot", "P-12 배관 플랜지 용접 보수", "3BAY 05-06 칼럼", ["13:00~15:00"], checks=["용접·용단"]))
x = got(h, "PRESSURE")
check("같은 배관 P-12, 다른 BAY → PRESSURE 1순위(계통이 주소보다 우선)", x and x[0]["priority"] == 1, [r["rule"] for r in h])
h, *_ = judge(permit(22, "lifting", "E42P 블록 이동 인양(OH-21-03)", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="E42P 위에 E43P 받침 지지대 있음"),
              plan(22, "E42P 블록 그라인딩", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="그라인더"))
check("받침·지지로 쓰이는 블록의 인양 × 같은 블록 작업 → SUPPORT(확인 필요)", got(h, "SUPPORT"), [r["rule"] for r in h])
h, *_ = judge(plan(23, "탱크 CO2 치환", "3BAY 08-10 칼럼", ["13:00~14:00"]), permit(23, "confined", "탱크 내부 진입 검사", "3BAY 08-10 칼럼", ["13:00~14:00"]))
check("「CO2 치환」 × 탱크 진입 → CONF_GAS", got(h, "CONF_GAS"), [r["rule"] for r in h])
check("「CO2 용접」은 불활성가스 아님", "INERT" not in pairs.profile(plan(24, "CO2 용접", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
h, *_ = judge(plan(25, "배관 아르곤 퍼지", "3BAY 08-10 칼럼", ["13:00~14:00"]), permit(25, "confined", "탱크 내부 진입", "3BAY 11-12 칼럼", ["13:00~14:00"]))
check("아르곤 퍼지 × 바로 옆 칼럼 밀폐 진입 → CONF_GAS 판정보류(멘토 병행 불가)", got(h, "CONF_GAS"), [r["rule"] for r in h])

print("판독 (Codex P2·L50·L67, part7 N4-MT14, part6 MV10)")
P = pairs.profile(plan(26, "받침대 제거 상태 관찰", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("「받침대 제거 상태 관찰」은 받침 제거 작업이 아님", not ({"SEP", "SUPPORT_ADJ"} & set(P["tags"])), P["tags"].keys())
check("「차량 운반」은 차량", "VEHICLE" in pairs.profile(plan(27, "자재 차량 운반", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
P = pairs.profile(plan(28, "핸드카로 소형 자재 공급", "3BAY 08-10 칼럼", ["13:00~14:00"]))
check("핸드카는 수동 대차(CART), 차량 아님", "CART" in P["tags"] and "VEHICLE" not in P["tags"], P["tags"].keys())
check("「자재 반입」은 통로에 놓일 수 있는 물건(STAGE_SOFT: 확인 필요)", "STAGE_SOFT" in pairs.profile(plan(29, "자재 반입", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
B = pairs.profile(plan(30, "E42P 배관 아르곤 퍼지(아르곤 호스 연결)", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
w = pairs._line_words(B)
check("끌린 아르곤 호스의 결과는 「질식」(가스 누출·화재 아님)", w["line_harm"] == "질식", w)
B = pairs.profile(plan(31, "E42P 흄 배기 덕트 설치", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]))
check("배기 덕트는 「흄 흡입」(질식 아님)", pairs._line_words(B)["line_harm"] == "흄 흡입", pairs._line_words(B))
ctx = pairs._ctx({"id": "HOT_PERSON"}, pairs.profile(permit(32, "hot", "E42P 작업", "3BAY 08-10 칼럼", ["13:00~14:00"], checks=["용접·용단"])),
                 pairs.profile(GROUND(32)), 2)
check("공법을 모르는 화기의 사고 요약은 「눈 손상(아크 용접이면)」 조건을 남김", "아크 용접이면" in ctx["hot_accident"], ctx["hot_accident"])

print("문구 (재독 B L16·L505, Codex P1·L113, P5·L123·L25)")
A_ = pairs.profile(permit(33, "hot", "E42P 가우징", "3BAY 08-10 칼럼", ["13:00~14:00"], checks=["용접·용단"]))
c = pairs._ctx({"id": "CONF_HOT"}, A_, pairs.profile(permit(34, "confined", "탱크 진입", "3BAY 08-10 칼럼", ["13:00~14:00"])), 2)
check("가우징 화기 → 밀폐 쪽 문구에 아크광·소음 연락 방해, 사람 쪽에 청력 손상", c["arc_in"] and c["noise_in"] and "청력 손상" in c["hot_harm"], c)
c = pairs._ctx({"id": "CONF_HOT"}, pairs.profile(permit(35, "hot", "E42P 가스 절단", "3BAY 08-10 칼럼", ["13:00~14:00"], checks=["용접·용단"])),
               pairs.profile(GROUND(35)), 2)
check("가스 절단은 아크광·소음 문구 없음", not c["arc_in"] and not c["noise_in"], c)
h, *_ = judge(permit(36, "lifting", "E42P 부재 인양(섬유 슬링)", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="크레인으로 잡은 채 취부"),
              permit(36, "hot", "E42P 부재 취부 용접", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], checks=["용접·용단"]))
x = got(h, "HELD_FIT")
check("섬유 슬링 인양 × 같은 블록 취부 용접 → 「슬링이 불티·열에 끊어짐」", x and any("섬유 슬링" in s for s in x[0]["chain"]), x and x[0]["chain"])
lift = permit(37, "lifting", "E42P 블록 이동(OH-21-03)", "3BAY 02-12 칼럼", ["13:00~15:00"])
lift["move"] = win("13:30~14:00")
ev = " ".join(str(e) for e in pairs._evidence(pairs.rules()["rules"][0], pairs.profile(lift), pairs.profile(GROUND(37))))
check("반장이 적은 이동 시각은 「이동 예정」(관찰한 실제 이동이 아님)", "이동 예정" in ev and "실제 이동" not in ev, ev[:200])

print("Codex 1단계 검토(astra) 17건 재현")
CONF = lambda i, place="3BAY 08-10 칼럼 E42P 블록 탱크 내부": permit(i, "confined", "E42P 탱크 내부 진입", place, ["13:00~14:00"])  # noqa: E731
h, *_ = judge(plan(50, "반장 입회하에 E42P 용접", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="CO2 용접기"), CONF(50))
check("#1 「입회하에 용접」은 용접(밀폐 진입과 CONF_HOT 그대로)", got(h, "CONF_HOT"), [r["rule"] for r in h])
a = permit(51, "height", "E42P 블록 상부 그라인딩", "3BAY 08-10 칼럼 E42P 블록 상부", ["13:00~15:00"], detail="작업높이 4m",
           records={"B3": "하부에서 마킹 작업 16:00~17:00 (시험)"})
x = got(judge(a, GROUND(51))[0], "OVERHEAD_WORK")
check("#2 반장 답의 「아래 작업」 시각이 그 작업과 안 겹치면 금지 조합 아님", x and not x[0]["forbidden"], x and (x[0]["priority"], x[0]["forbidden"]))
h, *_ = judge(permit(52, "loto", "MCC-4 분전반 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
              permit(52, "hot", "E42P 용접(국소배기 사용), 용접기 전원 MCC-5", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]))
check("#3 용접기 전원 번호만 다르면 국소배기 확인은 그대로(VENT_LOTO E1)", got(h, "VENT_LOTO"), [r["rule"] for r in h])
h, *_ = judge(HOT(53, place="3BAY 08-10 칼럼 E42P 블록"), plan(53, "E42P 블록 도장(신나)", "4BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], mat="신나"))
x = got(h, "FIRE")
check("#4 BAY가 달라도 같은 블록이면 FIRE 1순위(옆 BAY 보류보다 블록 연결 먼저)", x and x[0]["priority"] == 1, x and x[0]["priority"])
h, *_ = judge(permit(54, "lifting", "E42P 블록 이동 인양(OH-21-03)", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="E42P 위에 E43P 받침 지지대 있음"),
              plan(54, "E43P 블록 상부 마킹", "3BAY 08-10 칼럼 E43P 블록", ["13:00~14:00"], equip="마킹펜"))
x = got(h, "SUPPORT")
check("#5 인양 블록이 받치는 E43P의 작업 → SUPPORT, 문구는 「들어 옮긴다」", x and "들어 옮긴다" in x[0]["chain"][0], x and x[0]["chain"][0])
h, *_ = judge(HOT(55), permit(55, "hot", "LPG 용기 교체 및 토치 가열", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]))
check("#6 가스 취급 작업이 화기여도 다른 화기와 FIRE_GAS", got(h, "FIRE_GAS"), [r["rule"] for r in h])
for t in ("산소가스 용기 교체", "아르곤 가스 용기 교체", "비가연성 가스 용기 교체", "LPG 가스절단 용접"):
    P_ = pairs.profile(plan(56, t, "3BAY 08-10 칼럼", ["13:00~14:00"]))
    check(f"#7 「{t}」 → 가연성 가스 아님", not ({"FLAM_GAS", "GAS_UNK"} & set(P_["tags"])), P_["tags"].keys())
h, *_ = judge(HOT(57), plan(57, "가스 용기 교체", "3BAY 08-10 칼럼", ["13:00~14:00"]))
x = got(h, "FIRE_GAS")
check("#7 종류를 안 쓴 가스 용기 → FIRE_GAS 판정보류(가스 종류 미확인)", x and x[0]["E"] == 1, x and x[0]["E"])
h, *_ = judge(permit(58, "loto", "MCC-4 분전반 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
              permit(58, "confined", "탱크 내부 점검(MCC-4 옆에서 배터리 작업등 사용)", "3BAY 08-10 칼럼 탱크 내부", ["13:00~15:00"]))
x = got(h, "VENT_LOTO")
check("#8 「MCC-4 옆 배터리 작업등」은 MCC-4 전원 연결이 아님(확인위험 아님)", not x or x[0]["E"] < 3, x and x[0]["E"])
for t in ("CO2 가스 치환", "이산화탄소 가스 주입", "CO2로 치환", "CO₂ 치환"):
    check(f"#9 「{t}」 → 불활성가스", "INERT" in pairs.profile(plan(59, t, "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
h, *_ = judge(permit(60, "loto", "MCC-4 작업등 전원 차단 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
              permit(60, "height", "브래킷 상부 설치", "3BAY 08-10 칼럼", ["13:00~15:00"], detail="작업높이 4m"))
check("#10 차단 쪽에 「작업등」이라고 써도 상부 조명 확인(VENT_LOTO)", got(h, "VENT_LOTO"), [r["rule"] for r in h])
h, *_ = judge(plan(61, "자재 반입", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]), CONF(61))
x = got(h, "ACCESS")
check("#11 「자재 반입」 × 밀폐 진입 → ACCESS 판정보류(통로에 놓이는지 미확인)", x and x[0]["E"] == 1, x and x[0]["E"])
for t in ("천장크레인 부품 운반", "상부 작업 없이 지상에서 배관 설치"):
    check(f"#12 「{t}」 → 상부 작업 아님", "OVERHEAD" not in pairs.profile(plan(62, t, "3BAY 08-10 칼럼", ["13:00~14:00"], height=""))["tags"])
for t in ("OH-21-03 크레인 절연저항 시험", "OH-21-03 크레인 정비(시험운전 없음)"):
    h, *_ = judge(permit(63, "loto", t, "3BAY 01-20 칼럼", ["08:00~12:00"]), GROUND(63, place="3BAY 05-06 칼럼", t="09:00~11:00"))
    check(f"#13 「{t}」 → 지상 작업에 시험운전 확인 없음", not got(h, "CRANE_TEST"), [r["rule"] for r in h])
for t, want in (("아르곤 가스 호스 연결", "질식"), ("산소 가스 호스 연결", "산소 누출·연소 확대"), ("배기용 덕트 설치", "흄 흡입"), ("집진기 덕트 설치", "흄 흡입")):
    w = pairs._line_words(pairs.profile(plan(64, t, "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"])))
    check(f"#14 「{t}」 → {want}만", w["line_harm"] == want, w)
for t in ("차량으로 자재 운반", "자재 운반 차량"):
    check(f"#15 「{t}」 → 차량", "VEHICLE" in pairs.profile(plan(65, t, "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
check("#16 「종이컵 대량 수거」도 가연물", "COMBUST" in pairs.profile(plan(66, "종이컵 대량 수거", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
h, *_ = judge(HOT(67), plan(67, "오일 미스트 발생 설비 가동", "3BAY 08-10 칼럼", ["13:00~15:00"]))
x = got(h, "FIRE_GAS")
check("#17 오일 미스트 → 「미스트가 퍼지면」(가스 용기·호스 아님)", x and "미스트" in x[0]["chain"][0] and "용기" not in x[0]["chain"][0], x and x[0]["chain"][0])

print("보류 질문 연결 (holdq: 새 미확인 → 그 작업에 묻는 말)")
from server import holdq  # noqa: E402


def asks(a, b, rule):
    h, A_, B_ = judge(a, b)
    x = got(h, rule)
    return {f for _, f, _ in holdq._asks(x[0], {a["id"]: a, b["id"]: b}, only_explicit=False)} if x else set()


check("가스 종류 미상 용기 → 그 작업에 「가스 종류」를 물음", "gas_kind" in asks(HOT(70), plan(70, "가스 용기 교체", "3BAY 08-10 칼럼", ["13:00~14:00"]), "FIRE_GAS"))
check("높이 2m 미만 절단 → 「바닥 기준 높이」를 물음",
      "height" in asks(permit(71, "hot", "브래킷 절단", "3BAY 08-10 칼럼", ["13:00~15:00"], detail="작업높이 1.5m", checks=["용접·용단"]), GROUND(71), "DROP_BELOW"))
check("받침으로 쓰이는 블록의 인양 → 「받침을 옮기는 계획」을 물음",
      "lift_support" in asks(permit(72, "lifting", "E42P 블록 이동 인양(OH-21-03)", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], detail="E42P 위에 E43P 받침 지지대 있음"),
                             plan(72, "E42P 블록 그라인딩", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"], equip="그라인더"), "SUPPORT"))
check("국소배기 쓰는 화기 × 정전 → 「국소배기 전원」을 물음",
      "exhaust_power" in asks(permit(73, "loto", "MCC-4 분전반 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
                              permit(73, "hot", "E42P 용접(국소배기 사용)", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]), "VENT_LOTO"))
check("CONF_HOT 진입 쪽 질문에 「감시인이 화재감시자를 겸하는지」", "화재감시자를 겸하는지" in holdq.RULE_SIDE["CONF_HOT"][1][1])
check("「이동 예정 시각이 허가 시간 밖」 → 「크레인 실제 이동 예정 시각」을 물음(문구 변경 뒤에도 연결)",
      [f for _, f, _ in holdq._asks({"rule": "LOAD_OVER", "cause": "F074", "exposed": "WP-F-74",
                                     "gaps": ["F074의 이동 예정 시각이 허가 시간 밖: 일정 불일치 확인"]},
                                    {"F074": {"spans": [1]}, "WP-F-74": {"spans": [1]}})] == ["move_time"])

h, *_ = judge(HOT(80, place="3BAY 08-10 칼럼 E42P 블록", t="09:00~10:00"), plan(80, "E42P 블록 표면 청소", "3BAY 08-10 칼럼 E42P 블록", ["10:00~11:00"], equip="와이어 브러시"))
x = [r for r in h if r["when"]["kind"] == "sequence"]
check("맞닿은 시간(간격 0)에 잔류도 있으면 화면용 표시가 둘 다(touch·residual)", x and x[0]["when"].get("touch") and x[0]["when"].get("residual"),
      x and x[0]["when"])

print("Codex 최종 회차(9묶음 astra xhigh) 재현")
P_ = pairs.profile(permit(90, "hot", "러그 가스절단 / 아크용접 없음", "3BAY 08-10 칼럼", ["13:00~14:00"], checks=["용접·용단"]))
check("「아크용접 없음」 → 아크로 보지 않음(가스절단만)", "arc" not in P_["hot_kind"] and "gas" in P_["hot_kind"], P_["hot_kind"])
for t in ("압축공기 퍼지", "산소 퍼지", "퍼지캡 확인"):
    check(f"「{t}」 → 불활성가스 아님", "INERT" not in pairs.profile(plan(91, t, "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
check("「아르곤 퍼지」는 그대로 불활성가스", "INERT" in pairs.profile(plan(92, "배관 아르곤 퍼지", "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
for t in ("RT 검사 여부 확인", "방사선 표지 확인"):
    check(f"「{t}」 → 방사선 촬영 아님", "RADIATION" not in pairs.profile(plan(93, t, "3BAY 08-10 칼럼", ["13:00~14:00"]))["tags"])
w = pairs._line_words(pairs.profile(plan(94, "통신 케이블 포설", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"])))
check("통신 케이블 → 「연락 두절」(감전 아님)", w["line_harm"] == "연락 두절", w)
h, *_ = judge(permit(95, "hot", "브래킷 절단", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]), GROUND(95))
x = got(h, "DROP_BELOW")
check("높이 미상 절단의 문구에 「높은 곳(높은 곳)」 없음", x and not any("높은 곳(높은 곳)" in c for c in x[0]["chain"]), x and x[0]["chain"])
lift = permit(96, "lifting", "E42P 부재 인양(OH-21-03)", "3BAY 08-10 칼럼 E42P 블록", ["09:00~12:00"], detail="크레인으로 잡은 채 취부")
lift["move"] = win("11:00~12:00")
h, *_ = judge(lift, permit(96, "hot", "E42P 부재 취부 용접", "3BAY 08-10 칼럼 E42P 블록", ["09:00~10:00"], checks=["용접·용단"]))
check("매단 채 취부(09~10) × 이동은 11~12 → HELD_FIT 그대로(사례집 C11)", got(h, "HELD_FIT"), [r["rule"] for r in h])
h, *_ = judge(plan(97, "질소 공급", "3BAY", ["13:00~14:00"]), permit(97, "confined", "탱크 내부 진입", "3BAY 08-10 칼럼", ["13:00~14:00"]))
check("질소 공급 위치가 「3BAY」뿐 → CONF_GAS 판정보류(빼지 않음)", got(h, "CONF_GAS"), [r["rule"] for r in h])
h, *_ = judge(permit(98, "loto", "MCC-4 분전반 정비", "3BAY 08-10 칼럼", ["13:00~15:00"]),
              permit(98, "hot", "E42P 용접(국소배기 사용)", "3BAY 08-10 칼럼", ["13:00~15:00"], checks=["용접·용단"]))
x = got(h, "VENT_LOTO")
check("국소배기 화기의 정전 결과는 「흄 흡입」(밀폐 산소결핍 아님)", x and "흄 흡입" in " ".join(x[0]["chain"]) and "산소결핍" not in " ".join(x[0]["chain"]), x and x[0]["chain"])
c = pairs._ctx({"id": "HOT_PERSON"}, pairs.profile(permit(99, "hot", "E42P CO2 용접", "3BAY 08-10 칼럼", ["13:00~14:00"], checks=["용접·용단"])), pairs.profile(GROUND(99)), 2)
check("공법을 아는 화기도 사고 요약에 조건(같은 공기 공간이면)을 남김", "같은 공기 공간" in c["hot_accident"], c["hot_accident"])
r_ = {"rule": "LOAD_OVER", "cause": "F100", "exposed": "WP-F-100", "gaps": ["평면 경로: 실제 하물 외곽·높이 확인 필요"]}
check("평면 경로 경보 → 인양 쪽에 「실제 하물 크기·높이」 질문", [f for _, f, _ in holdq._asks(r_, {"F100": {"spans": [1]}, "WP-F-100": {"spans": [1]}})] == ["lift_outline"])
h, *_ = judge(plan(101, "자재 차량 운반", "3BAY 08-10 칼럼 E42P 블록", ["13:00~14:00"]), permit(101, "confined", "E42P 탱크 내부 진입", "3BAY 08-10 칼럼 E42P 블록 탱크 내부", ["13:00~14:00"]))
x = got(h, "ACCESS")
docs_ = {"WP-F-101": {"spans": [1]}, "F101": {"spans": [1]}}
fs = [f for _, f, _ in holdq._asks({**x[0], "gaps": ["경로가 생기려면 사건이 하나 더"]}, docs_)] if x else []
check("ACCESS 원인이 차량이면 「운반 경로와 통과 시각」을 물음(인양 시각 아님)", "route_time" in fs and "lift_time" not in fs, fs)

x = got(judge(HOT(110, place="3BAY 08-10 칼럼 E42P 블록"), plan(110, "E42P 블록 마킹", "3BAY 08-10 칼럼 E42P 블록", ["13:00~15:00"], equip="마킹펜", workers=None))[0], "HOT_PERSON")
check("인원 칸이 빈 작업도 노출을 낮추지 않음(같은 블록 동시 → E3), 인원 수는 따로 물음", x and x[0]["E"] == 3 and any("인원 수" in g for g in x[0]["gaps"]),
      x and (x[0]["E"], x[0]["gaps"]))

print(f"\n{ok}/{ok + bad}")
sys.exit(0 if bad == 0 else 1)
