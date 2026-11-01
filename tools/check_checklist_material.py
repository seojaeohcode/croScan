"""Check the checklist items and measures added from the 412-page research book (material reinforcement, 2026-10-31).

    python tools/check_checklist_material.py

Every new item is shown (해당) for the permit and the answers that speak of it, and is not 해당 for the others: a
name alone does not make it (「용접부 비드 확인」 is no welding, 「용접기 전원」 is no hot work near a panel,
「산소 측정」 is no oxygen use, 「밀폐·용접」 alone is no heat illness). Its measures stay plans (「…할 예정」), the old
items keep their ids and order, and a 「해당 없음」 needs an answer that says so and a permit that does not say
otherwise.
"""
import copy
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("CROSCAN_DATA", tempfile.mkdtemp(prefix="croscan_ckm_"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from server import augment, checkai, checklist, extract  # noqa: E402
from server.permit_kinds import KINDS  # noqa: E402
from foreman_permits import FOREMAN  # noqa: E402

ok = bad = 0


def expect(cond, what):
    global ok, bad
    ok += bool(cond); bad += not cond
    if not cond or os.environ.get("VERBOSE"):
        print(("  PASS " if cond else "  FAIL ") + what)


SPEC = checklist.SPEC
NEW = {"hot": ["hot_contact", "hot_oxygen", "hot_hose", "hot_heat", "hot_wheel", "hot_noise", "hot_arc",
               "hot_drop", "hot_under", "hot_tack", "hot_glare"],          # hot_glare: 2026-11-01 최종 검토(HW08-NONARC)
       "confined": ["confined_heat", "confined_fume", "confined_oxygen", "confined_electric", "confined_solvent", "confined_noise"],
       "height": ["height_cable", "height_wheel", "height_oxygen", "height_noise", "height_mewp", "height_heat", "height_explosion"],
       "lifting": ["lifting_egress", "lifting_fall"],
       "loto": ["loto_handover", "loto_ingress", "loto_temp", "loto_drop"]}
# the items as they were before (ids and order must not move)
OLD = {"hot": ["hot_spark", "hot_fire", "hot_explosion", "hot_piece", "hot_support", "hot_fall", "hot_asphyxia", "hot_fume",
               "hot_electric", "hot_embers"],
       "confined": ["confined_argon", "confined_residual", "confined_air", "confined_vent", "confined_inflow", "confined_move",
                    "confined_watch", "confined_rescue", "confined_access", "confined_fall"],
       "height": ["height_loaded", "height_drop", "height_fall", "height_support", "height_recovery", "height_crane",
                  "height_spark", "height_fume", "height_residual"],
       "lifting": ["lifting_route", "lifting_drop", "lifting_people", "lifting_rigging", "lifting_land", "lifting_release",
                   "lifting_support", "lifting_cranes", "lifting_lines", "lifting_signal"],
       "loto": ["loto_contact", "loto_backfeed", "loto_arc", "loto_restart", "loto_test", "loto_energy", "loto_other_crane",
                "loto_fall", "loto_dependencies", "loto_wiring"]}

print("1. 명세: 기존 id·순서 그대로, 새 항목은 뒤에, 조치는 계획 문장")
for kind, old in OLD.items():
    ids = [it["id"] for it in SPEC["kinds"][kind]["items"]]
    expect(ids[:len(old)] == old, f"{kind}: 기존 항목 id·순서 유지")
    expect(ids[len(old):] == NEW[kind], f"{kind}: 새 항목이 뒤에 붙음 {ids[len(old):]}")
    expect(len(checklist.items_for(kind)) <= checklist.MAX_ITEMS - 10, f"{kind}: 항목 수 {len(checklist.items_for(kind))} (한도 안, 반장 추가 여유)")
for kind, new in NEW.items():
    for iid in new:
        it = next(x for x in SPEC["kinds"][kind]["items"] if x["id"] == iid)
        expect(all(c["id"].startswith(iid + "_c") for c in it["controls"]), f"{iid}: 조치 id")
        expect(all(c["text"].endswith(("예정", "예정)")) or re.search(r"예정\([^)]*\)$", c["text"]) for c in it["controls"]),
               f"{iid}: 조치는 「…예정」 계획 문장")
        expect(not re.search(r"AI|판단|%\s*확률|승인|일정을\s*(?:바꾸|조정)", json.dumps(it, ensure_ascii=False)),
               f"{iid}: 「AI가 판단」·승인·일정 조정 문구 없음")
        expect(all(r.get("reason") for r in it["prefill"]["yes"] + it["prefill"]["no"]), f"{iid}: 규칙마다 이유")
        for kk in SPEC["kinds"]:
            expect((iid in [x["id"] for x in checklist.items_for(kk)]) == (kk == kind), f"{iid}: {kk} 목록에 {'있음' if kk == kind else '없음'}")
ctl = lambda kind, iid: [c["text"] for c in next(x for x in checklist.items_for(kind) if x["id"] == iid)["controls"]]
expect(any("하부 통제를 유지" in t for t in ctl("hot", "hot_piece")), "hot_piece: 회수·잔부 고정 확인 전 하부 통제 유지")
expect(any("귀환선" in t for t in ctl("hot", "hot_electric")), "hot_electric: 용접 귀환선 직결")
expect(any("23.5%" in t and "제618조" in t for t in ctl("hot", "hot_oxygen")), "hot_oxygen: 밀폐·구획 안 화기 산소 23.5% 이상 중지(제618조)")
expect(any("환기·먼지 털기" in t for t in ctl("hot", "hot_oxygen")), "hot_oxygen: 산소를 환기·먼지 털기에 쓰지 않음")
expect(any("경과 시간" in t for t in ctl("hot", "hot_contact")), "hot_contact: 작업명·종료 시각·경과 시간으로 해제하지 않음")
for kind in SPEC["kinds"]:
    expect(any("비상구" in t and "소화기" in t for t in ctl(kind, "common_rescue")), f"{kind}: 공통 구조에 비상구·통로·소화기 앞 확보")
    expect(any("호스·케이블·잔재" in t for t in ctl(kind, "common_access")), f"{kind}: 공통 출입에 통로의 호스·케이블 정리")
expect(any(a["ref"] == "안전보건규칙 제18조" for a in next(x for x in SPEC["common"] if x["id"] == "common_rescue")["law_articles"]),
       "common_rescue: 제18조(비상구 등의 유지) 근거")
expect(any("STO" in t for t in ctl("loto", "loto_wiring")), "loto_wiring: 정지 신호·STO는 전원 격리가 아님")
expect(any("다른 팀의 철수" in t for t in ctl("loto", "loto_restart")), "loto_restart: 같은 구동계 다른 팀 철수 뒤 복구(EL04-MOTION)")
expect(any("거더 위" in t for t in ctl("loto", "loto_other_crane")), "loto_other_crane: 거더 위 작업 중 다른 크레인 운행 정지 요청(EL07-FALL)")
expect(any("보호도체" in t for t in ctl("loto", "loto_arc")), "loto_arc: 보호도체·절연 복구 대조(EL12-ELECTRIC)")
expect(any("소음" in t for t in ctl("lifting", "lifting_signal")), "lifting_signal: 소음 속 신호")
expect(any("산소" in t for t in ctl("lifting", "lifting_lines")), "lifting_lines: 산소·연료가스 호스 분리")
expect(any("경과 시간" in t for t in ctl("lifting", "lifting_land")), "lifting_land: 해제 상태 인계")
expect(any("교대" in t for t in ctl("confined", "confined_watch")), "confined_watch: 교대 때 감시 공백 없음")

print("2. 새 항목: 맞는 허가서·답에만 해당")
DOCS = {}
for d in FOREMAN:
    if d["kind"] in DOCS:
        continue
    name = f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf"
    DOCS[d["kind"]] = extract.build(ROOT / "samples/반장_테스트" / name, d["kind"])["fields"]
HEADS = {k: [h for h, _ in KINDS[k]["heads"]] for k in KINDS}


def run(kind, text="", job="작업", heads=(), answers=(), vals=None, detail=""):
    """the draft of this kind's test permit with its work written as given (작업명 job, 유해위험요소 text, 상세 empty,
    a plain place),
    only the given head boxes ticked, and the given answers [(item, choice, value)] -> {id: item}"""
    f = copy.deepcopy(DOCS[kind])
    perm = augment._permits(f)[0]
    for k, x in f.items():
        if x["page"] != perm["no"]:
            continue
        key = k.split(".")[-1]
        if key == "hazards":
            x["value"] = text
        elif key == "job":
            x["value"] = job
        elif key in ("job_detail", "location_detail"):
            x["value"] = detail if key == "job_detail" else ""
        elif key == "location":                       # a sample writes the team (「용접3팀」) here
            x["value"] = "대조립21공장 3BAY 14 칼럼"
        elif key in HEADS[kind] or key in ("pressure_use", "commissioning"):
            x["value"] = key in heads
        if key in (vals or {}):
            x["value"] = vals[key]
        elif key in ("concurrent", "test_pressure"):
            x["value"] = ""
    pno = perm["permit_no"]
    ans = [{"qid": (f"FREE:{i}" if item == "FREE" else f"{item}:{pno}"), "choice": ch, "value": v, "q": {}}
           for i, (item, ch, v) in enumerate(answers)]
    return {x["id"]: x for x in checklist.draft(f, ans)["permits"][0]["items"]}


def case(kind, iid, want, what, **kw):
    got = run(kind, **kw)[iid]
    good = got["state"] != want[4:] if want.startswith("not-") else got["state"] == want
    expect(good, f"{iid}: {what} → {got['state']} ({'; '.join(got['reasons'])[:80]})")
    if want == "yes":
        expect(got["reasons"] and all(c["on"] == c["pre"] for c in got["controls"]), f"{iid}: 해당이면 이유와 미리 고른 조치")


# neutral work: none of the new items is 해당
for kind, new in NEW.items():
    base = run(kind)
    expect(all(base[i]["state"] != "yes" for i in new), f"{kind}: 중립 작업(「작업」)에는 새 항목이 해당 아님 "
           f"{[i for i in new if base[i]['state'] == 'yes']}")
    expect(all(base[i]["state"] != "no" for i in new), f"{kind}: 근거 없이 해당 없음 없음(기본 확인 필요)")

case("hot", "hot_contact", "yes", "용접·용단 칸 체크", heads=("weld_cut",))
case("hot", "hot_contact", "yes", "작업명 「가스절단」", job="러그 가스절단")
case("hot", "hot_contact", "not-yes", "화기 공법이 없는 작업(칸 체크 없음, hot_embers와 같은 조건)", job="도장면 육안 점검")
case("hot", "hot_oxygen", "yes", "유해위험요소 「산소·LPG 용기 사용」", text="산소·LPG 용기 사용, 화재")
case("hot", "hot_oxygen", "yes", "D3 답 「산소·LPG 용기」", answers=[("D3", "text", "산소·LPG 용기")])
case("hot", "hot_oxygen", "not-yes", "「산소결핍 주의」", text="산소결핍 주의")
case("hot", "hot_oxygen", "not-yes", "「산소·가스 측정 후 작업」", text="화재, 산소·가스 측정 후 작업")
case("hot", "hot_oxygen", "not-yes", "가스절단만(산소 표기 없음): 확인 필요로 둠", job="러그 가스절단")
case("hot", "hot_oxygen", "check", "D3 「가스 안 씀」만, 허가서는 말 없음(침묵은 부재가 아님)", job="CO2 용접", answers=[("D3", "na", "")])
case("hot", "hot_oxygen", "no", "D3 「가스 안 씀」 + 허가서 「가스 안 씀」", job="CO2 용접", text="가스 안 씀", answers=[("D3", "na", "")])
case("hot", "hot_oxygen", "yes", "D3 「가스 안 씀」이어도 허가서에 산소 절단이 적혀 있으면 해당 없음으로 내리지 않음", job="산소 절단", answers=[("D3", "na", "")])
case("hot", "hot_hose", "yes", "가우징 칸 체크", heads=("gouging",))
case("hot", "hot_hose", "not-yes", "CO2 용접만", job="CO2 용접")
case("hot", "hot_heat", "yes", "「폭염 속 작업」", text="폭염 속 작업, 화재")
case("hot", "hot_heat", "yes", "추가 전달에 「여름철 고온 작업」", answers=[("FREE", "text", "여름철 고온 작업입니다")])
case("hot", "hot_heat", "not-yes", "「밀폐 구획 내부 용접」(이름만으로 온열 확정 안 함)", job="구획 내부 용접", text="밀폐")
case("hot", "hot_wheel", "yes", "「그라인더 사상」", job="용접부 그라인더 사상")
case("hot", "hot_wheel", "not-yes", "가우징만", heads=("gouging",))
case("hot", "hot_noise", "yes", "가우징 칸 체크", heads=("gouging",))
case("hot", "hot_noise", "not-yes", "CO2 용접만", job="CO2 용접")
case("hot", "hot_arc", "yes", "「CO2 용접」", job="CO2 용접")
case("hot", "hot_arc", "yes", "H2 「가스 안 씀(전기 용접만)」", answers=[("H2", "na", "")])
case("hot", "hot_arc", "not-yes", "가스절단만(아크로 바꾸지 않음)", job="러그 가스절단")

case("confined", "confined_heat", "yes", "「고온 다습 환경」", text="질식, 고온 다습 환경")
case("confined", "confined_heat", "not-yes", "「배관 내부 진입 용접」(이름만으로 온열 확정 안 함)", job="배관 내부 진입 용접")
case("confined", "confined_fume", "yes", "CF1 「보수·용접」", answers=[("CF1", "repair", "국부 용접 1곳")])
case("confined", "confined_fume", "yes", "B3 「옆 블록 외판 용접」", answers=[("B3", "yes", "같은 블록 외판 용접, 오후")])
case("confined", "confined_fume", "not-yes", "「용접부 비드 확인」(검사는 용접 아님)", job="배관 내부 진입 (용접부 비드 확인)")
case("confined", "confined_oxygen", "yes", "「산소 호스 반입」", text="질식, 산소 호스 반입")
case("confined", "confined_oxygen", "not-yes", "「진입 전 산소 측정」", text="아르곤 질식 / 진입 전 산소 측정")
case("confined", "confined_oxygen", "not-yes", "「산소결핍」", text="산소결핍")
case("confined", "confined_electric", "yes", "「전동공구 사용」", text="질식, 전동공구 사용")
case("confined", "confined_electric", "not-yes", "「질식」만", text="질식")

case("height", "height_cable", "yes", "HT1 플라즈마", answers=[("HT1", "plasma", "")])
case("height", "height_cable", "not-yes", "HT1 가스절단", answers=[("HT1", "gas", "")])
case("height", "height_wheel", "yes", "HT1 그라인더·기계절단", answers=[("HT1", "mech", "")])
case("height", "height_wheel", "not-yes", "HT1 가스절단", answers=[("HT1", "gas", "")])
case("height", "height_spark", "yes", "HT1 그라인더도 불티(연삭)", answers=[("HT1", "mech", "")])
case("height", "height_oxygen", "yes", "「산소 절단」", job="러그 산소 절단")
case("height", "height_oxygen", "not-yes", "HT1 가스절단만(산소 사용 표기 없음)", answers=[("HT1", "gas", "")])
case("height", "height_noise", "yes", "HT1 그라인더·기계절단", answers=[("HT1", "mech", "")])
case("height", "height_noise", "not-yes", "HT1 가스절단", answers=[("HT1", "gas", "")])

case("lifting", "lifting_egress", "yes", "L5 「비상구 앞에 안착」", answers=[("L5", "text", "2BAY 20칼럼 비상구 앞에 안착")])
case("lifting", "lifting_egress", "not-yes", "L5 「동측 통로 경유」(지나가는 길)", answers=[("L5", "text", "3BAY → 동측 통로 경유 → 1BAY 반출장")])

case("loto", "loto_handover", "yes", "LO3 「14:30 복구, 14:45 시험운전」", answers=[("LO3", "text", "13:00 차단, 14:30 복구, 14:45 시험운전")])
case("loto", "loto_handover", "not-yes", "복구·시험 언급 없음")
case("loto", "loto_ingress", "yes", "B3 「옆 칼럼 용접」", answers=[("B3", "yes", "옆 칼럼 용접, 오전")])
case("loto", "loto_ingress", "not-yes", "「용접기 전원 분기 증설」(용접기 전원은 화기 아님)", job="용접기 전원 분기 증설")
case("loto", "loto_temp", "yes", "「임시 전원 가설」", job="임시 전원 가설")
case("loto", "loto_temp", "not-yes", "임시 전원 언급 없음", job="인버터 교체")

# second pass (others.md: interview, casebook, forms, safety report)
case("hot", "hot_drop", "yes", "고소 화기작업 칸 체크", heads=("hot_at_height",))
case("hot", "hot_drop", "not-yes", "지상 CO2 용접", job="지상 CO2 용접")
case("hot", "hot_under", "yes", "「블록 하부 종통재 용접」", job="E33S 블록 하부 종통재 용접")
case("hot", "hot_under", "yes", "L3 「블록 아래」", answers=[("L3", "text", "블록 아래 서포트 사이")])
case("hot", "hot_under", "not-yes", "「블록 상부 용접」", job="블록 상부 용접")
case("hot", "hot_tack", "yes", "「판넬 취부·가용접」", job="벽 판넬 취부·가용접")
case("hot", "hot_tack", "not-yes", "「균열부 재용접」", job="균열부 재용접")
case("confined", "confined_solvent", "yes", "「탱크 내부 터치업 도장」", job="탱크 내부 진입 터치업 도장")
case("confined", "confined_solvent", "yes", "B3 「같은 블록 신나 세척」", answers=[("B3", "yes", "같은 블록 외부 신나 세척, 오후")])
case("confined", "confined_solvent", "not-yes", "「질식」만", text="질식")
case("height", "height_mewp", "yes", "고소작업대 칸 체크", heads=("mewp",))
case("height", "height_mewp", "not-yes", "비계 칸만", heads=("scaffold",))
case("lifting", "lifting_fall", "yes", "「블록 위 줄걸이 해제」", text="블록 위 줄걸이 해제, 낙하")
case("lifting", "lifting_fall", "not-yes", "「정반 안착」만", text="정반 안착")
case("loto", "loto_drop", "yes", "LO4 「거더·상부에도 올라감」", answers=[("LO4", "text", "거더 상부 13m")])
case("loto", "loto_drop", "not-yes", "LO4 「제어반 앞에서만」", answers=[("LO4", "front", "")])
case("loto", "loto_other_crane", "yes", "LO4 「거더·상부에도 올라감」(같은 레일 다른 크레인)", answers=[("LO4", "text", "거더 상부")])
for kind in SPEC["kinds"]:
    got = run(kind, answers=[("B3", "yes", "옆 칼럼 RT 촬영, 오후")])["common_mixed"]          # 병행 N on the permit: 엇갈림
    expect(got["state"] != "no" and any("방사선투과검사" in r for r in got["reasons"]),
           f"common_mixed: {kind}: B3 「옆 칼럼 RT 촬영」 → {got['state']} (RT 근거가 보임, 해당 없음 아님)")
    case(kind, "common_access", "yes", f"{kind}: 허가 작업 주변 출입 통제")
expect(any("제575조" in t for t in ctl("hot", "common_mixed")), "common_mixed: RT 관리구역 출입금지(제575조제2항)")
expect(any("제241조의2제3항" in t for t in ctl("hot", "hot_spark")), "hot_spark: 화재감시자 확성기·조명·대피용 마스크(제241조의2제3항)")
expect(any("황화수소 10ppm" in t and "제618조" in t for t in ctl("confined", "confined_air")), "confined_air: 적정공기 기준(제618조)")
expect(any("겸하지 않는" in t for t in ctl("confined", "confined_watch")), "confined_watch: 전담 감시인")
expect(any("1차측" in t for t in ctl("loto", "loto_arc")), "loto_arc: 플러그 빼기 전 1차측 차단")
expect(any("원격·자동 기동" in t for t in ctl("loto", "loto_restart")), "loto_restart: 원격·자동 기동 명령 차단")
expect(any("아웃트리거" in t for t in ctl("lifting", "lifting_rigging")), "lifting_rigging: 이동식 크레인 아웃트리거·지반")
expect(any("풍속" in t for t in ctl("lifting", "lifting_route")), "lifting_route: 옥외 인양 풍속 중지 기준")

print("2-2. Codex 검토(2026-11-01) 1~8과 남은 보강")
# #1 압력사용·테스트압력·수전 and D6·D7 keep 연결 계통 from 해당 없음
NOCONN = dict(text="질식, 연결 계통 없음", answers=[("CF2", "none", "")])
case("confined", "confined_inflow", "no", "CF2 없음 + 허가서 「연결 계통 없음」, 칸 미체크", **NOCONN)
case("confined", "confined_inflow", "yes", "압력사용 칸 체크(답이 없음이어도)", heads=("pressure_use",), **NOCONN)
case("confined", "confined_inflow", "yes", "테스트압력 7 적힘", vals={"test_pressure": "7"}, **NOCONN)
case("confined", "confined_inflow", "yes", "수전구역 칸 체크", heads=("commissioning",), **NOCONN)
case("confined", "confined_inflow", "yes", "D6 「펌프 시운전 중」", answers=[("D6", "text", "펌프 P-3 시운전 중")])
case("confined", "confined_inflow", "yes", "D7 「질소, 10:00 가압」", answers=[("D7", "text", "질소, 10:00 가압 ~ 11:30 감압")])
case("confined", "confined_argon", "yes", "D7 시험 매체 질소", answers=[("D7", "text", "질소, 10:00 가압")])
# #2 해당 없음 = 허가서의 부재 문구 AND 같은 허가서의 확정 답
case("hot", "common_mixed", "check", "병행 N만(답 없음)", vals={"concurrent": "N"})
case("hot", "common_mixed", "no", "병행 N + C3 「다른 장소·설비」", vals={"concurrent": "N"}, answers=[("C3", "na", "다른 BAY")])
case("hot", "common_mixed", "check", "병행 빈칸 + B3 「없음」만", answers=[("B3", "no", "")])
case("hot", "hot_oxygen", "check", "H2 「전기 용접만」만, 허가서 말 없음", answers=[("H2", "na", "")])
for iid in ("height_loaded", "height_support", "height_recovery"):
    case("height", iid, "check", "HT1 「떼는 러그 없음」만, 허가서 말 없음", answers=[("HT1", "na", "")])
    case("height", iid, "no", "HT1 「떼는 러그 없음」 + 허가서 「떼는 러그 없음」", text="추락, 떼는 러그 없음", answers=[("HT1", "na", "")])
# #3 why in the basis: a widened scope asks again
it0 = run("hot")["hot_fall"]
orig = copy.deepcopy(checklist.SPEC)
next(x for x in checklist.SPEC["kinds"]["hot"]["items"] if x["id"] == "hot_fall")["why"] = "다른 범위"
expect(run("hot")["hot_fall"]["basis"] != it0["basis"], "hot_fall: 적용 설명(why)이 바뀌면 해당 여부 근거(basis)가 바뀜")
checklist.SPEC.clear()
checklist.SPEC.update(orig)
expect("오가" in next(x for x in SPEC["kinds"]["hot"]["items"] if x["id"] == "hot_fall")["title"], "hot_fall: 제목이 오가는 범위를 드러냄")
# #4 hot work inside a confined or LOTO permit carries the hot items in its own list
for kind, kw, want in (("confined", dict(job="탱크 내부 CO2 용접"), True), ("confined", dict(answers=[("CF4", "yes", "CO2 용접 1곳")]), True),
                       ("confined", dict(job="배관 내부 진입 (용접부 비드 확인)"), False), ("loto", dict(job="부스바 브래킷 절단·교체"), True),
                       ("loto", dict(job="용접기 전원 분기 증설"), False)):
    got = run(kind, **kw)
    have = {"hot_spark", "hot_embers", "hot_contact"} <= set(got)
    expect(have == want, f"{kind} {kw}: 화기 항목(잔불·불티·잔열) {'있음' if want else '없음'} ({have})")
cc = run("confined", job="탱크 내부 CO2 용접")
expect(cc["hot_embers"]["state"] in ("yes", "check") and cc["hot_arc"]["state"] == "yes", "밀폐 안 CO2 용접: 아크광 해당, 잔불 항목 있음")
pno = augment._permits(DOCS["confined"])[0]["permit_no"]
expect([x["id"] for x in checklist.clean({"permits": [{"permit_no": pno, "kind": "confined", "items": [{"id": "hot_embers", "state": "yes"}]}]})[0]["items"]] == ["hot_embers"],
       "clean(): 밀폐 허가서의 화기 항목 id를 버리지 않음")
# #5 preview merge: measures chosen on other wording are not confirmed
d0 = checklist.draft(DOCS["hot"], [])
it = next(x for x in d0["permits"][0]["items"] if x["id"] == "hot_fall")


def sent(ctl):
    return {"permits": [{"permit_no": d0["permits"][0]["permit_no"], "kind": "hot", "items": [
        {"id": "hot_fall", "basis": it["basis"], "basis_ctl": ctl, "state": "yes", "touched": True, "ctl_touched": True,
         "controls": [{"id": "hot_fall_c2", "on": True}]}]}]}


m_old = next(x for x in checklist.merge(d0, sent("old"))["permits"][0]["items"] if x["id"] == "hot_fall")
m_new = next(x for x in checklist.merge(d0, sent(it["basis_ctl"]))["permits"][0]["items"] if x["id"] == "hot_fall")
expect(m_old["touched"] and not m_old["ctl_touched"] and m_new["ctl_touched"], "merge(): 조치 문구가 바뀐 확인은 「조치 확인 전」으로")
# #6 names, negations, undecided words
case("hot", "hot_contact", "not-yes", "「용접부 비드 확인」", job="용접부 비드 확인")
case("hot", "hot_contact", "not-yes", "「용접기 전원 점검」", job="용접기 전원 점검")
case("hot", "hot_contact", "not-yes", "「용접·절단 없음」", job="용접·절단 없음")
case("hot", "hot_oxygen", "not-yes", "「산소를 측정할 예정」", job="러그 절단", text="산소를 측정할 예정")
case("hot", "hot_oxygen", "not-yes", "「산소 사용 미정」", text="산소 사용 미정")
case("hot", "hot_explosion", "not-yes", "「러더 육안 점검」", job="러더 육안 점검")
case("hot", "hot_explosion", "yes", "「러더 내부 보강 용접」", job="러더 내부 보강 용접")
case("lifting", "lifting_egress", "not-yes", "L5 「출입구 경유 후 정반 안착」", answers=[("L5", "text", "출입구 경유 후 정반 안착")])
case("lifting", "lifting_fall", "not-yes", "LI2 「안전 위해 통제」", answers=[("LI2", "text", "안전 위해 통제")])
got = run("confined", answers=[("CF2", "text", "연결 없음")])["confined_inflow"]
expect(got["state"] == "check" and not any("있다고" in r for r in got["reasons"]),
       f"confined_inflow: CF2 글 「연결 없음」 → {got['state']} (확인 필요, 잘못된 이유 없음)")
for t, want in (("용접·절단 없음", False), ("산소 사용 미정", None), ("가스 사용 여부 모름", None), ("CO2 용접", True), ("가스절단·용접 안 함", False)):
    expect(checklist.says(t, "(?i)용접|절단|산소|가스") is want, f"says('{t}') → {want}")
# #7 a free answer of a file with two permits moves none of them
two = dict(DOCS["hot"])
for k, x in DOCS["confined"].items():
    y = dict(x)
    y["page"] = x["page"] + 1
    two[f"p{x['page'] + 1}." + k.split(".", 1)[1]] = y
ck2 = checklist.draft(two, [{"qid": "FREE:0", "choice": "text", "value": "P2 작업만 폭염 속 작업", "q": {}}])
st = {i["id"]: i["state"] for P2 in ck2["permits"] for i in P2["items"] if i["id"] in ("hot_heat", "confined_heat")}
expect(len(ck2["permits"]) == 2 and "yes" not in st.values(), f"허가서 2건 파일의 자유 답변은 어느 항목도 켜지 않음 {st}")
case("hot", "hot_heat", "yes", "허가서 1건이면 자유 답변 「폭염」은 그 허가서 것", answers=[("FREE", "text", "폭염 속 작업")])
# 남은 보강
case("confined", "confined_noise", "yes", "「내부 그라인더 사상」", job="탱크 내부 그라인더 사상")
case("confined", "confined_noise", "not-yes", "「질식」만", text="질식")
case("height", "height_heat", "yes", "「폭염 속 블록 상부」", text="추락, 폭염")
case("height", "height_explosion", "yes", "「도장 블록 옆 러그 절단」", job="도장 블록 옆 러그 절단")
case("height", "height_explosion", "not-yes", "「러그 절단」만", job="러그 절단")
for kind in SPEC["kinds"]:
    g = run(kind)["common_ra"]
    expect(g["state"] == "check" and "위험성평가 원문" in g["controls"][0]["text"], f"{kind}: 위험성평가 원문 대조(반장 확인, 조문 없음)")
expect(any("현장 계획" in t and "제241조의2제1항제3호" in t for t in ctl("hot", "hot_fire")), "hot_fire_c4: 법의 배치 조건과 현장 계획을 나눔")
got = run("loto", answers=[("LO5", "live", "인버터 출력 전압 측정 13:20")])["loto_arc"]
expect(got["state"] == "yes" and any("통전 상태" in r for r in got["reasons"]) and next(c for c in got["controls"] if c["id"] == "loto_arc_c2")["on"],
       "LO5 「있음」 → loto_arc 해당·이유 표시·c2(절연 보호구) 선택")

print("2-3. 답 읽기: 철회(C6)·정정(C5)·글로 쓴 「없음」·effective.facts")
case("confined", "confined_inflow", "not-yes", "D6 「펌프 시운전 중」을 C6 「서류가 맞음」으로 철회",
     answers=[("D6", "text", "펌프 P-3 시운전 중"), ("C6.D6", "doc", "")])
case("confined", "confined_inflow", "yes", "CF2 「없음」을 C5 「추가로 적은 내용이 맞음」(퍼지 라인 V-12 연결)으로 정정",
     text="질식, 연결 계통 없음", answers=[("CF2", "none", ""), ("C5.CF2", "free", "아르곤 퍼지 라인 V-12 연결 있음")])
case("confined", "confined_inflow", "not-no", "CF2 글 「연결 없는 줄 알았는데 퍼지 라인 연결 있어요」(허가서는 「연결 계통 없음」)",
     text="질식, 연결 계통 없음", answers=[("CF2", "text", "연결 없는 줄 알았는데 퍼지 라인 연결 있어요")])
case("confined", "confined_inflow", "no", "CF2 글 「연결 계통 없음」 + 허가서 「연결 계통 없음」(글 「없음」은 선택지처럼)",
     text="질식, 연결 계통 없음", answers=[("CF2", "text", "연결 계통 없음")])
case("confined", "confined_inflow", "check", "CF2 글 「연결 계통 없음」만, 허가서는 말 없음(답만으로 해당 없음 아님)",
     answers=[("CF2", "text", "연결 계통 없음")])
case("confined", "hot_embers", "yes", "CF4 「함」(effective.facts)", answers=[("CF4", "yes", "CO2 용접 1곳")])
expect("hot_embers" not in run("confined", answers=[("CF4", "yes", "CO2 용접 1곳"), ("C6.CF4", "doc", "")]),
       "CF4 「함」을 C6으로 철회하면 밀폐 목록에 화기 항목이 붙지 않음")
case("loto", "loto_arc", "yes", "LO5 「있음」(effective.facts)", answers=[("LO5", "live", "13:20 인버터 출력 측정")])
_ap = augment._permits(DOCS["hot"])[0]["permit_no"]
_ans = [{"qid": f"H2:{_ap}", "choice": "text", "value": "산소 절단", "q": {}}, {"qid": f"C6.H2:{_ap}", "choice": "doc", "value": "", "q": {}}]
expect(not any("산소 절단" in ln for ln in checkai.facts(augment.effective(DOCS["hot"], _ans)[0], _ans)),
       "checkai 작업 사실: C6으로 철회한 답은 넣지 않음")

print("2-4. 마지막 Codex 검토: 다른 칸의 「미정」, 철회 답과 근거 해시, 혼합 문장, C5 정정")
# #10 an undecided word in one field does not lower a hazard another field confirms; baseline preservation with
# mixed-field inputs: the old reading (augment.said over the fields joined by spaces) as the baseline of the items
# that existed before, none of them lower now
case("hot", "hot_spark", "yes", "작업명 「CO2 용접」 + 상세 「감시자 미정」", job="CO2 용접", detail="감시자 미정")
for iid in ("hot_fume", "hot_electric", "hot_embers"):
    case("hot", iid, "yes", "작업명 「CO2 용접」 + 유해위험요소 「감시자 미정」", job="CO2 용접", text="감시자 미정")
case("hot", "hot_oxygen", "not-yes", "「산소 사용 미정」은 그 사실만 미정", job="CO2 용접", text="산소 사용 미정")
_old_says = checklist.says
RANK = {"no": 0, "check": 1, "yes": 2}
JOBS = ["CO2 용접", "러그 가스절단·제거", "균열부 가우징·재용접", "블록 상부 러그 절단", "배관 내부 진입 아르곤 퍼지",
        "인버터 교체 시험운전", "블록 반출 인양 안착", "탱크 내부 진입 청소", "부스바 브래킷 절단"]
NOTES = ["감시자 미정", "인원 미정", "종료 시각 모름", "병행 여부 확인 중", "순서는 현장에서 정함", "화재, 소음", ""]
lower = []
for kind in SPEC["kinds"]:
    for job in JOBS:
        for note in NOTES:
            for where in ("text", "detail"):
                kw = {"job": job, where: note}
                new = run(kind, **kw)
                checklist.says = lambda t, rx: augment.said(t.replace("\n", " "), rx) if re.search(rx, t.replace("\n", " ")) else False
                try:
                    old = run(kind, **kw)
                finally:
                    checklist.says = _old_says
                lower += [(kind, job, note, i, old[i]["state"], new[i]["state"]) for i in OLD[kind] + [x["id"] for x in SPEC["common"] if x["id"] != "common_ra"]
                          if i in old and RANK[new[i]["state"]] < RANK[old[i]["state"]]]
expect(not lower, f"기존 항목: 칸을 섞은 입력 {len(SPEC['kinds']) * len(JOBS) * len(NOTES) * 2}건에서 예전 읽기보다 낮아진 상태 없음 {lower[:4]}")
# #11 the basis hash reads the answers that stand: a withdrawn answer's words do not change it
pno_h = augment._permits(DOCS["hot"])[0]["permit_no"]
w1 = [{"qid": f"H2:{pno_h}", "choice": "text", "value": "산소 LPG 절단", "q": {}}, {"qid": f"C6.H2:{pno_h}", "choice": "doc", "value": "", "q": {}}]
w2 = [{"qid": f"H2:{pno_h}", "choice": "text", "value": "CO2 용접", "q": {}}, {"qid": f"C6.H2:{pno_h}", "choice": "doc", "value": "", "q": {}}]
P_h = augment.effective(DOCS["hot"], w1)[0]
expect(checklist.work_digest(P_h, w1) == checklist.work_digest(P_h, w2), "work_digest: C6으로 철회한 답의 글은 근거 해시에 들어가지 않음")
b1 = {x["id"]: x["basis"] for x in checklist.draft(DOCS["hot"], w1)["permits"][0]["items"]}
b2 = {x["id"]: x["basis"] for x in checklist.draft(DOCS["hot"], w2)["permits"][0]["items"]}
expect(b1 == b2, "항목 basis: 철회한 답의 글이 달라도 같음")
# #1 effect: a mixed sentence (no gas connection, nitrogen to be put in) is never 해당 없음
case("confined", "confined_inflow", "not-no", "CF2 「가스 연결 없음. 질소 투입 예정」 + 허가서 「연결 계통 없음」",
     text="질식, 연결 계통 없음", answers=[("CF2", "none", "가스 연결 없음. 질소 투입 예정")])
case("confined", "confined_inflow", "not-no", "CF2 글 「가스 연결 없음. 질소 투입 예정」 + 허가서 「연결 계통 없음」",
     text="질식, 연결 계통 없음", answers=[("CF2", "text", "가스 연결 없음. 질소 투입 예정")])
case("hot", "hot_oxygen", "not-no", "H2 「가스 안 씀. 산소 절단은 오후」 + 허가서 「가스 안 씀」",
     job="CO2 용접", text="가스 안 씀", answers=[("H2", "na", "가스 안 씀. 산소 절단은 오후")])
case("height", "height_loaded", "not-no", "HT1 「없음. 러그 1개는 절단 예정」 + 허가서 「떼는 러그 없음」",
     text="떼는 러그 없음", answers=[("HT1", "na", "없음. 러그 1개는 절단 예정")])
# #3 a C5 correction stands even when the shared live-answer function already dropped the corrected answer
_pc = augment._permits(DOCS["confined"])[0]["permit_no"]
st = checklist.standing([{"qid": f"C5.CF2:{_pc}", "choice": "free", "value": "아르곤 퍼지 라인 V-12 연결 있음", "q": {}}])
expect(any(a["qid"] == f"CF2:{_pc}" and a["choice"] == "text" and "퍼지" in a["value"] for a in st),
       "standing(): C5 정정만 남아 있어도 CF2를 정정 글로 읽음(공통 함수와 겹쳐도 같은 결과)")

print("3. 당일 칸은 그대로(사전 작성 금지)")
for kind, f in DOCS.items():
    before = json.dumps(f, sort_keys=True, ensure_ascii=False)
    checklist.draft(f, [])
    expect(json.dumps(f, sort_keys=True, ensure_ascii=False) == before, f"{kind}: 초안이 허가서 값을 바꾸지 않음")

print("최종 전수 검토(2026-11-01)로 더한 항목")
case("hot", "hot_glare", "yes", "가스절단이 적힌 화기", job="E42P 종통재 가스절단")
case("hot", "hot_glare", "not-yes", "CO2 용접만 적힌 화기", job="E42P 론지 CO2 용접")
case("hot", "common_sharp", "yes", "절단이 적힌 화기", job="E42P 러그 절단")
case("loto", "common_machine", "yes", "윈치 구동부 정비", job="OH-21-03 윈치 구동부 정비")
case("loto", "loto_other_crane", "yes", "LO6 「같은 레일 다른 크레인 운행 있음」 답", answers=[("LO6", "text", "OH-21-02 같은 레일 10시 운행")])
expect(any("시작 전 1분" in t and "바꾼 뒤 3분" in t for t in ctl("hot", "hot_wheel")), "시운전: 작업 시작 전 1분·숫돌 교체 후 3분 이상(안전보건규칙 제122조제2항, 사례집 C59·C60)")
expect(any("펜던트" in t for t in ctl("lifting", "lifting_rigging")), "크레인 펜던트·전원 소켓 점검(신고서양식)")

case("loto", "common_machine", "not-yes", "「안전벨트 착용」만", job="크레인 정비", text="안전벨트 착용")
case("loto", "loto_other_crane", "not-yes", "LO6가 다른 팀 작업 확인만 말함", answers=[("LO6", "text", "도장팀 거더 하부 작업 종료 확인")])

from server import explain  # noqa: E402
allit = SPEC["common"] + [x for k in SPEC["kinds"].values() for x in k["items"]]
withc = [x for x in allit if x.get("cases")]
expect(len(withc) >= 40 and all(isinstance(c.get("page"), int) and c.get("title") and len(c["title"]) <= 40 and len(x["cases"]) <= 3
                                for x in withc for c in x["cases"]),
       f"사고사례집 연결: {len(withc)}항목, 사례마다 쪽수·짧은 제목(40자 이하), 항목당 3건 이하")
it = run("hot", job="E42P 종통재 가스절단")["hot_spark"]
R = explain.checklist(it, "P-1")["R"]
expect(any("참고 사고 사례(조선업 중대재해 사례집" in r["text"] for r in R), "체크 항목 설명(왜?)에 같은 위험의 참고 사고 사례와 쪽수")

print(f"\n통과 {ok} / {ok + bad}" + ("" if not bad else f"  실패 {bad}"))
sys.exit(1 if bad else 0)
