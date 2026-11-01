"""시연용 하루 (2026-10-29 목, 대조립21공장 1~4BAY): 허가서 10건 + 작업계획서 40건 + 겹침 정답표. Claude 작성, GPT 검토.

    python tools/demo_day_data.py     -> samples/시연_하루/permits.json, workplans.json, skeleton.json

Why this day (sources: 조사자료 추가본, 멘토링):
  - 안전팀 한 팀에 하루 40~50건이 몰리면 바쁜 날이다(멘토). 그래서 50건: 비일상(허가서) 10건 = 5종 × 2건,
    일상(작업계획서) 40건 = 6개 업체.
  - 허가서마다 A(실물 0453·0400처럼 대충: 하루 내내 시간, 팀 이름 장소, 병행여부·호선 빈칸)와 B(꼼꼼)를 하나씩 둔다.
    작업반장 시점에서 croScan이 무엇을 묻는지, 묻지 않는지를 같이 보여 주기 위해서다.
  - 공장: 조사자료 F01 모델(3BAY·01~21축·50t)을 4BAY·01~20칼럼으로 늘린 시연용 변형판(BAY 폭 36m, 칼럼 간격 12m),
    BAY마다 천장크레인 1대(OH-21-01~04). 블록 하나는 한 곳에만 있다(블록 번호 = 위치).
  - 겹침 정답 11쌍(C01~C03·C05~C10·C12·C13)은 조사자료의 위험쌍 유형(화기×도장·유기용제, 밀폐 내부 인원×같은 블록
    인양, 인양 경로×사람·밀폐 진입, 같은 크레인 정비×사용, 상하 작업, 공유 전원 정전×전원 사용 작업, 지게차×고소작업대·
    마킹)에서 골랐다. 구본의 방사선투과×출입(C04)·도장×그라인딩(C11)은 QA #55~#57에서 없앴다(README).
    가까워 보이지만 겹치지 않는 5쌍(시간이 떨어짐, 칼럼이 멀리 떨어짐, 다른 배전반)도 넣어 과잉 경보를 보여 준다.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "samples" / "시연_하루"
DAY, REQ = "2026-10-29", "2026-10-28"


def permit(no, first=DAY, **kw):
    # the number carries the first work day; a 7-day permit (같은 작업장 연속 작업, 인터뷰 2026-10-29) began earlier
    d = {"permit_no": f"AC00-IH-{first.replace('-', '')}-{no}", "supervisor": "김XX", "supervisor_phone": "010-XXXX-XXXX",
         "manager": "박XX", "manager_phone": "010-XXXX-XXXX", "req_name": "김XX", "req_date": REQ, "req_sign": "김XX",
         "double_check": "N"}
    d.update(kw)
    return d


def shift(a="08:00", b="16:59"):
    return [(DAY, a, b)]


# 7일 단위 신청: 같은 작업장에서 이어지는 작업은 7일로 묶어 한 번 신청하고, 허가기간 중 매일 새로 쓰지 않는다
# (사용자 채택 해석, 2026-10-29). 10/27(화)~11/02(월) 중 작업하는 날(일요일 11/01 쉼), 날마다 같은 시간.
WEEK = ["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-02"]


def week(a, b):
    return [(d, a, b) for d in WEEK]


# ---------------------------------------------------------------- 허가서 10건 (비일상)
PERMITS = [
    # 화기 A: 팀 이름 장소, 하루 내내, 호선·병행 빈칸. 실제로는 오후 3BAY 08-10 칼럼 E42P 상부 → 도장 터치업(WP01)과 겹침(C01)
    permit("0731", double_check="Y", kind="hot", case="A", permit_type="[안전현장허가]", hull_no="", jsp_no="HHIS-CW-A0001190-012-001",
           location="대조립3부 용접2팀", location_detail="", job="론지 균열부 가우징·재용접 (E42P)", job_detail="",
           department="대조립3부-용접2팀", workers="3", hazards="용접흄, 소음", concurrent="", days=shift(),
           checks={"day": "set", "weld_cut": "set", "gouging": "set"},
           answers_truth={"T1": {"choice": "partial", "value": "13:00~15:00"},
                          "L1": {"choice": "place", "value": "3BAY 08-10 칼럼 E42P 블록 상부"},
                          "H1": {"choice": "local", "value": ""}, "H2": {"choice": "text", "value": "CO2 용접, 아크 가우징"},
                          "B3": {"choice": "no", "value": ""}, "L3": {"choice": "text", "value": "블록 상부 갑판, 높이 3m"}}),
    # 화기 B: 꼼꼼. 1BAY 14-16 B21S 외판 오전 → 같은 곳 오후 족장 해체(WP04)와 시간이 떨어져 겹치지 않음(N01)
    permit("0732", first="2026-10-27", req_date="2026-10-26", app_name="이XX", app_date="2026-10-26", app_sign="이XX", double_check="Y", kind="hot", case="B", permit_type="[안전현장허가]", hull_no="3612-B21S", jsp_no="HHIS-CW-A0001190-015-002",
           location="대조립21공장 1BAY 14-16 칼럼", location_detail="B21S 블록 외판 하부", job="B21S 블록 외판 취부 불량부 절단·재용접",
           job_detail="지상 작업, 화재감시자 1명", department="대조립1부-구조보수1팀", workers="3",
           hazards="불티 비산(화재), 용접흄, 절단물 낙하 / 하부 가연물 제거", concurrent="Y", days=week("09:00", "11:30"),
           checks={"day": "set", "weld_cut": "set"},
           answers_truth={"T1": {"choice": "yes", "value": ""},
                          "B3": {"choice": "yes", "value": "같은 칼럼 오후 13:00부터 족장 해체 예정, 시간 분리"},
                          "H1": {"choice": "local", "value": ""}, "H2": {"choice": "text", "value": "가스절단, CO2 용접"}}),
    # 밀폐 A: 팀 이름, 하루 내내, 병행 빈칸. 실제 09:00~11:30 3BAY 12-14 E41P 이중저 → 같은 블록 의장품 인양(WP02, C02)·인양 경로(0737, C03)
    permit("0733", double_check="Y", kind="confined", case="A", permit_type="[안전현장허가]", hull_no="", jsp_no="HHIS-CN-C6B0-031",
           location="대조립3부 취부1팀", location_detail="", job="이중저 탱크 내부 검사·잔재 정리", job_detail="",
           department="대조립3부-취부1팀", workers="3", hazards="질식, 소음", concurrent="", days=shift(),
           checks={"day": "set", "confined_space": "set"},
           answers_truth={"T1": {"choice": "partial", "value": "09:00~11:30"},
                          "L1": {"choice": "place", "value": "3BAY 12-14 칼럼 E41P 블록 이중저 내부"},
                          "CF1": {"choice": "inspect", "value": ""}, "CF2": {"choice": "none", "value": ""},
                          "B3": {"choice": "no", "value": ""}}),
    # 밀폐 B: 아르곤 퍼지 배관 진입, 2BAY 05-06 B22S, 13:00~15:00. WP03은 초음파탐상(UT)이다: 구본의 방사선투과(RT)
    #   통제구역·작업쌍(C04)은 QA #55·#56에서 없앴고 정답표에 다시 넣지 않는다(현장 정정 D33, 2026-10-31)
    permit("0734", first="2026-10-27", req_date="2026-10-26", app_name="이XX", app_date="2026-10-26", app_sign="이XX", double_check="Y", kind="confined", case="B", permit_type="[안전현장허가]", hull_no="3612-B22S", jsp_no="HHIS-CN-C6B0-032",
           location="대조립21공장 2BAY 05-06 칼럼", location_detail="B22S 블록 내부 배관 P-12 퍼지 구간",
           job="아르곤 퍼지 배관 내부 진입 (용접부 비드 확인)", job_detail="진입 2명, 맨홀 외부 감시 1명",
           department="대조립2부-배관1팀", workers="3", hazards="아르곤 질식, 좁은 통로 대피 곤란 / 진입 전 산소 측정",
           concurrent="N", days=week("13:00", "15:00"), checks={"day": "set", "confined_space": "set", "argon": "set"},
           answers_truth={"T1": {"choice": "yes", "value": ""}, "CF1": {"choice": "inspect", "value": ""}, "CF2": {"choice": "text", "value": "P-12 아르곤 공급 밸브 잠금, 퍼지 후 측정"}}),
    # 고소 A: 공장만, 하루 내내, 높이 빈칸. 실제 14:00~16:00 1BAY 14-16 B21S 상부 러그 → 아래 족장 해체(WP04)와 상하 겹침(C05)
    permit("0735", double_check="N", kind="height", case="A", permit_type="[전산허가]", hull_no="3612-B21S", jsp_no="HHIS-CW-A0001190-034-001",
           location="대조립21공장", location_detail="", job="블록 상부 임시 러그 절단·제거", job_detail="",
           department="대조립1부-취부2팀", workers="3", hazards="안전대 착용", concurrent="", days=shift(),
           checks={"day": "set"},
           answers_truth={"T1": {"choice": "partial", "value": "14:00~16:00"},
                          "L1": {"choice": "place", "value": "1BAY 14-16 칼럼 B21S 블록 상부"},
                          "HT1": {"choice": "gas", "value": "3"}, "L3": {"choice": "text", "value": "4.5m"},
                          "HT2": {"choice": "text", "value": "로프로 하부 적치함에 내림, 하부 통행 통제"},
                          "B3": {"choice": "yes", "value": "하부에서 족장 해체 13:00~15:30 (삼녹)"}}),
    # 고소 B: 고소작업대, 4BAY 03-05 D31C 측판, 09:00~11:00 → 지게차 통로(WP05, C06). 같은 곳 오후 마킹(WP12)은 겹치지 않음(N03)
    permit("0736", double_check="N", kind="height", case="B", permit_type="[전산허가]", hull_no="3615-D31C", jsp_no="HHIS-CW-A0001190-036-002",
           location="대조립21공장 4BAY 03-05 칼럼", location_detail="D31C 블록 동측 측판, 고소작업대 MEWP-04",
           job="D31C 블록 측판 상부 보강재 취부", job_detail="고소작업대 1대, 작업자 2명 탑승",
           department="대조립4부-취부1팀", workers="3", hazards="추락(6.0m), 작업대 전도, 공구 낙하 / 하부 출입 통제",
           concurrent="N", days=shift("09:00", "11:00"), work_height="6.0", checks={"day": "set", "mewp": "set"},
           answers_truth={"HT1": {"choice": "text", "value": "러그 없음, 보강재 취부만"},
                          "HT2": {"choice": "text", "value": "해당 없음"}}),
    # 중량물 A: 공장만, 하루 내내, 정격하중 빈칸. 실제 10:30~11:30 OH-21-03 E45P 3BAY 06→16 칼럼
    #   → 경로 아래 밀폐 진입 E41P(0733, C03), 같은 크레인 정전 수리(0739, C07)
    permit("0737", double_check="Y", kind="lifting", case="A", permit_type="[안전현장허가]", hull_no="3611-E45P", jsp_no="HHIS-CW-A0001190-008-001",
           location="대조립21공장 3BAY", location_detail="", job="E45P 블록 반전 후 이동", job_detail="천장크레인 사용",
           department="대조립3부-운반1팀", workers="5", hazards="신호수 배치", concurrent="", days=shift(),
           load_weight="42", lift_height="4", checks={"day": "set", "overhead_crane": "set"},
           answers_truth={"T1": {"choice": "partial", "value": "10:30~11:30"},
                          "LI1": {"choice": "text", "value": "천장크레인 OH-21-03, 반전 후 2점 인양"},
                          "L5": {"choice": "text", "value": "3BAY 06칼럼에서 16칼럼 정반까지 중앙 통로 위"},
                          "LI2": {"choice": "none", "value": ""}, "B3": {"choice": "no", "value": ""}}),
    # 중량물 B: 꼼꼼. 2BAY B22S 반출 15:30~16:30 OH-21-02, 경로 2BAY 05→20 → 경로 아래 취부 용접(WP06, C08)
    permit("0738", double_check="Y", kind="lifting", case="B", permit_type="[안전현장허가]", hull_no="3612-B22S", jsp_no="HHIS-CW-A0001190-008-002",
           location="대조립21공장 2BAY 05-06 칼럼 → 2BAY 20칼럼 반출장", location_detail="2BAY 중앙 통로 경유",
           job="B22S 블록 반출 인양·이동·안착 (천장크레인 OH-21-02)", job_detail="정반 안착 후 줄걸이 해제",
           department="대조립2부-운반1팀", workers="5", hazards="인양물 낙하·협착, 크레인 충돌 / 블록 내부 인원 확인",
           concurrent="N", days=shift("15:30", "16:30"), load_weight="28", crane_swl="40", lift_height="3",
           checks={"day": "set", "overhead_crane": "set"},
           answers_truth={"LI2": {"choice": "none", "value": ""}, "T6": {"choice": "stage", "value": "15:40~16:10 실제 이동"}}),
    # 정전 A: 팀 이름, 하루 내내, 크레인 번호 없음, 병행 N(잘못). 실제 10:00~12:00 OH-21-03 제어반 → 같은 크레인 인양(0737, C07)
    permit("0739", double_check="N", kind="loto", case="A", permit_type="[전산허가]", hull_no="", jsp_no="HHIS-CE-B0000420-007-001",
           location="설비보전부 전기2팀", location_detail="", job="천장크레인 제어반 고장 수리", job_detail="",
           department="설비보전부-전기2팀", workers="2", hazards="감전", concurrent="N", days=shift(),
           checks={"day": "set", "low_voltage": "set"},
           answers_truth={"T1": {"choice": "partial", "value": "10:00~12:00"},
                          "L1": {"choice": "place", "value": "3BAY 천장크레인 OH-21-03 제어반 CP-03"},
                          "LO1": {"choice": "diag", "value": ""}, "LO3": {"choice": "text", "value": "10:00 차단, 11:50 복구 후 시험운전"},
                          "LO4": {"choice": "text", "value": "거더 위 주행부까지 올라감"}}),
    # 정전 B: 꼼꼼. 4BAY 배전반 MCC-4 정전 13:00~15:00 → 같은 배전반에서 전원을 받는 용접(WP07, C10). 4BAY 17-19 사상(WP13)은 다른 배전반(N04)
    permit("0740", double_check="N", kind="loto", case="B", permit_type="[전산허가]", hull_no="", jsp_no="HHIS-CE-B0000420-005-002",
           location="대조립21공장 4BAY 배전반 MCC-4", location_detail="4BAY 10칼럼 벽면 배전반", job="MCC-4 용접기 전원 분기 증설",
           job_detail="정전·잠금 후 작업, 복구 전 절연 측정", department="설비보전부-전기1팀", workers="3",
           hazards="감전·아크, 오통전 / 4BAY 용접기 전원 차단 영향", concurrent="Y", days=shift("13:00", "15:00"),
           rated_voltage="380", lock_count="3", checks={"day": "set", "low_voltage": "set"},
           answers_truth={"B3": {"choice": "yes", "value": "4BAY 11-13 칼럼 전동공구 볼트 체결 작업, 전원 차단 시간 협의 필요"},
                          "LO3": {"choice": "text", "value": "13:00 차단, 14:40 절연 측정, 14:50 복구"},
                          "L1": {"choice": "place", "value": "4BAY 10칼럼 벽면 배전반 MCC-4"},
                          "LO1": {"choice": "repair", "value": ""}, "LO4": {"choice": "front", "value": ""}}),
]
# answers to questions found on the first run (croScan asked them; the scenario had no answer → 「모름」)
PERMITS[5]["answers_truth"]["HT1"] = {"choice": "na", "value": ""}           # 보강재 취부만: 떼는 러그 없음 → HT2도 묻지 않음
PERMITS[4]["answers_truth"]["T6"] = {"choice": "text", "value": "러그 3개 절단·회수만, 3명이 2시간"}


# ---------------------------------------------------------------- 작업계획서 40건 (일상)
# (id, company, kind of work, 작업명, start, end, BAY, columns, 블록, 인원, 혼재작업 as the writer knows it)
# 혼재작업 "" = the writer did not know of the clash (what the 안전관리자 has to find)
# QA #55·#56 (2026-10-30): 일상 작업만 둔다. 용접(가용접 포함)·사상은 불티가 나서 화기작업 허가서, 방사선투과검사는 이리듐
#   선원으로 옆 작업자가 피폭될 수 있어 허가 대상(비일상)이다. 그 자리는 불티·선원이 없는 대조립 일상 작업(의장품 볼트 체결,
#   부재 배치, 초음파탐상, 표면 청소, 계측, 환기팬·작업등 설치 등)으로 바꿨다. 50건(허가서 10 + 계획서 40)은 그대로다.
# QA #57: 40건 중 10건은 본청 생산부서(직영), 30건은 협력사가 보낸 계획서다. 본청은 업체 자리에 부서-팀을 쓴다.
INHOUSE = {"WP10", "WP11", "WP12", "WP14", "WP15", "WP17", "WP20", "WP26", "WP32", "WP33"}
CRANE = {"1BAY": "OH-21-01", "2BAY": "OH-21-02", "3BAY": "OH-21-03", "4BAY": "OH-21-04"}
HULL = {"E41P": "3611", "E42P": "3611", "E43S": "3611", "E44P": "3611", "E45P": "3611", "B21S": "3612", "B22S": "3612",
        "B23P": "3612", "B24S": "3612", "B25S": "3612", "B26S": "3612", "B27P": "3612", "B28P": "3612", "B29S": "3612",
        "D31C": "3615", "D32C": "3615", "D33C": "3615", "D34C": "3615", "D35C": "3615", "D36C": "3615", "B31S": "3612"}
PLANS = [
    # 겹침·근접 비교에 쓰는 13건
    ("WP01", "동성화인텍", "paint", "E42P 블록 상부 도장 터치업", "13:30", "15:00", "3BAY", "08-10", "E42P", 3, ""),
    ("WP02", "세진중공업", "outfit_crane", "E41P 블록 상부 갑판 의장품 거치·볼트 체결", "10:00", "12:00", "3BAY", "12-14", "E41P", 4, ""),
    ("WP03", "동화엔텍", "ut", "B22S 블록 맞대기 이음부 초음파탐상검사", "13:30", "14:30", "2BAY", "05-07", "B22S", 2, ""),
    ("WP04", "삼녹", "scaffold_down", "B21S 블록 측면 족장 해체", "13:00", "15:30", "1BAY", "14-16", "B21S", 4,
     "같은 칼럼 오전 외판 용접 09:00-11:30 종료 후 시작"),
    ("WP05", "현대힘스", "forklift", "강재 부재 지게차 운반", "09:30", "10:30", "4BAY", "01-08", "D31C", 2, ""),
    ("WP06", "세진중공업", "outfit", "B27P 블록 소조립 의장품 브래킷 볼트 체결", "15:30", "17:00", "2BAY", "09-11", "B27P", 3, ""),
    ("WP07", "현대힘스", "bolt_mcc4", "D32C 블록 론지 브래킷 볼트 체결 (전동공구)", "13:00", "16:00", "4BAY", "11-13", "D32C", 4, ""),
    ("WP08", "동성화인텍", "paint", "B24S 블록 내판 도장 터치업", "09:00", "11:00", "2BAY", "17-19", "B24S", 3, ""),
    ("WP09", "한국카본", "insulation", "B24S 블록 보온재 부착 (도장 완료면)", "10:00", "11:30", "2BAY", "18-19", "B24S", 2, ""),
    ("WP10", "대조립1부-운반1팀", "forklift", "입고 강재 지게차 반입", "08:30", "09:30", "1BAY", "01-05", "B26S", 2, ""),
    ("WP11", "대조립1부-정도관리팀", "marking", "B26S 블록 심출·조립위치 마킹", "08:00", "10:00", "1BAY", "02-04", "B26S", 2, ""),
    ("WP12", "대조립4부-정도관리팀", "marking", "D31C 블록 하부 내부재 위치 마킹", "13:00", "14:00", "4BAY", "03-05", "D31C", 2,
     "같은 칼럼 오전 고소작업대 작업 09:00-11:00 종료 후"),
    ("WP13", "한국카본", "fan_mcc5", "D33C 블록 내부 환기팬·작업등 설치 (MCC-5 전원)", "13:00", "15:00", "4BAY", "17-19", "D33C", 2,
     "MCC-4 정전과 무관, 4BAY 18칼럼 MCC-5 사용"),
    # 겹치지 않게 배치한 일상 작업 27건
    ("WP14", "대조립1부-취부3팀", "fitup", "B23P 블록 소조립 부재 배치·정렬", "08:00", "10:20", "1BAY", "06-09", "B23P", 4, "10:30 정렬 작업에 크레인 인계"),
    ("WP15", "대조립1부-정도관리팀", "measure", "B23P 블록 정도 계측·치수 기록", "13:00", "15:00", "1BAY", "06-09", "B23P", 2, "오전 부재 배치 완료 후 같은 구역"),
    ("WP16", "동화엔텍", "measure", "B25S 블록 치수·형상 측정", "08:30", "10:00", "1BAY", "10-12", "B25S", 2, "없음"),
    ("WP17", "대조립1부-운반1팀", "align", "B25S 블록 정렬·받침대 설치", "10:30", "12:00", "1BAY", "10-12", "B25S", 3, "치수 측정 종료 후, 크레인 인수"),
    ("WP18", "한국카본", "surface", "B29S 소조립 검사 부위 표면 청소", "08:00", "10:30", "1BAY", "17-20", "B29S", 2, "없음"),
    ("WP19", "동화엔텍", "vt", "B29S 소조립 이음부 육안검사", "16:00", "17:00", "1BAY", "17-20", "B29S", 2, "인근 러그 절단 종료 후"),
    ("WP20", "대조립1부-생산관리팀", "receive", "입고 부재 인수 확인", "13:00", "14:00", "1BAY", "01-02", "B26S", 2, "오전 지게차 반입 종료 후"),
    ("WP21", "세진중공업", "pipe", "B31S 블록 배관 스풀 거치·플랜지 볼트 체결", "08:00", "11:30", "2BAY", "01-03", "B31S", 3, "없음"),
    ("WP22", "동성화인텍", "primer", "배관 플랜지부 방청 프라이머 터치업", "15:00", "16:30", "2BAY", "01-03", "B31S", 2, "오전 배관 설치 종료 후"),
    ("WP23", "한국카본", "insulation", "B28P 블록 보온재 부착 (용접 완료면)", "09:00", "12:00", "2BAY", "13-15", "B28P", 3, "없음"),
    ("WP24", "동화엔텍", "cable", "B28P 블록 케이블 트레이 설치", "13:00", "15:00", "2BAY", "13-15", "B28P", 3, "15:30 B22S 반출 경로 통과 전 종료"),
    ("WP25", "삼녹", "scaffold_up", "E43S 블록 측면 족장 설치", "07:30", "09:00", "3BAY", "01-04", "E43S", 4, "없음"),
    ("WP26", "대조립3부-취부3팀", "fitup_nc", "E43S 블록 내부 부재 반입·배치", "09:30", "12:00", "3BAY", "01-04", "E43S", 4, "족장 설치 완료 후"),
    ("WP27", "현대힘스", "outfit", "E43S 블록 내부 사다리·난간 브래킷 볼트 체결", "13:00", "16:30", "3BAY", "01-04", "E43S", 4, "오전 부재 배치 완료 후"),
    ("WP28", "한국카본", "surface", "E44P 블록 검사 부위 표면 청소", "08:00", "10:00", "3BAY", "17-20", "E44P", 2, "없음"),
    ("WP29", "동화엔텍", "mt", "E44P 블록 자분탐상검사", "10:30", "12:00", "3BAY", "17-20", "E44P", 2, "표면 청소 종료 후"),
    ("WP30", "동성화인텍", "degrease", "E44P 블록 도장 전 세정·탈지", "13:00", "14:00", "3BAY", "17-20", "E44P", 2, "화기작업 없음 확인"),
    ("WP31", "삼녹", "cleaning", "E41P 블록 주변 청소·잔재 정리", "15:00", "16:00", "3BAY", "12-14", "E41P", 2, "인근 의장품 작업 종료 후"),
    ("WP32", "대조립3부-운반1팀", "jig", "3BAY 16칼럼 정반 지그 정리", "14:00", "15:30", "3BAY", "16-17", "E45P", 2, "오전 E45P 안착 후"),
    ("WP33", "대조립4부-취부2팀", "fitup", "D32C 블록 론지 부재 배치·정렬", "08:00", "12:00", "4BAY", "11-13", "D32C", 4, "없음"),
    ("WP34", "한국카본", "surface", "D35C 블록 검사 부위 표면 청소", "08:30", "11:30", "4BAY", "14-16", "D35C", 2, "없음"),
    ("WP35", "동화엔텍", "ut", "D35C 블록 초음파탐상검사", "13:00", "14:00", "4BAY", "14-16", "D35C", 2, "없음"),
    ("WP36", "동성화인텍", "coat_check", "방청 도장 건조 상태 확인", "08:00", "09:00", "4BAY", "18-20", "D33C", 1, "없음"),
    ("WP37", "삼녹", "haul", "잔재·자투리 강재 반출 정리", "13:00", "14:00", "4BAY", "01-02", "D36C", 2, "없음"),
    ("WP38", "현대힘스", "welder_check", "공용 용접기 점검·케이블 정리", "07:30", "08:00", "4BAY", "08-10", "D34C", 1, "08:00 부재 배치 전 종료"),
    ("WP39", "세진중공업", "tidy", "B23P 블록 야간 자재·공구 정리", "18:00", "20:00", "1BAY", "06-09", "B23P", 3, "주간 작업 종료 후 야간"),
    ("WP40", "동화엔텍", "report", "비파괴검사(UT·MT) 결과 정리", "17:30", "18:30", "사무동", "", "B22S", 2, "없음"),
]

# what each kind of work needs: steps, crew, equipment, material, spec, height, protection, hazards grid, end record
T = {
    "paint": dict(steps=["표면 이물 제거·마스킹, 화기작업 여부 확인", "붓·롤러로 손상부 터치업 도장", "건조 확인, 유기용제 용기 회수"],
                  roles="도장공 2명 / 감시 1명", equip="붓·롤러, 국소배기 송풍기 1대", material="에폭시 도료, 희석제(유기용제)",
                  spec="손상부 터치업 약 {a}m²", height="블록 상부 {h}m", hazard="유기용제 증기·인화",
                  protect="환기·방독마스크 / 반경 내 화기 금지 표지", end="건조 확인 후 용제 용기 회수", area=6),
    # 부재 배치: crane / chain block and clamps only. 가용접(tack welding) is hot work, so it is not part of these plans
    "fitup": dict(steps=["도면·부재 번호 확인", "크레인·체인블록으로 부재 배치", "클램프 고정·치수 확인"],
                  roles="취부사 {w1}명 / 신호수 1명", equip="체인블록, 클램프, 크레인 {crane}", material="보강재·론지 부재",
                  spec="부재 약 {n}개 배치", height="지상 ~ {h}m", hazard="부재 낙하·협착",
                  protect="신호수 배치 / 하부 출입 통제", end="배치·고정 상태 기록", area=8),
    "outfit_crane": dict(steps=["OH-21-03로 의장품 인양 (10:30)", "갑판 위 브래킷에 의장품 거치·볼트 체결", "체결 토크 확인, 공구·자재 회수"],
                         roles="의장공 2명 / 취부사 1명 / 신호수 1명", equip="크레인 OH-21-03, 토크렌치, 체인블록", material="의장품(사다리·난간), 볼트·너트",
                         spec="의장품 {n}개 거치·체결", height="블록 상부 갑판 {h}m", hazard="부재 낙하·협착",
                         protect="신호수 배치 / 하부 출입 통제", end="체결 상태 기록", area=6),
    "outfit": dict(steps=["도면·의장품 번호 확인", "브래킷·의장품 볼트 체결", "체결 토크 확인·기록"],
                   roles="의장공 {w}명", equip="토크렌치, 충전 임팩트렌치", material="의장품 브래킷, 볼트·너트",
                   spec="브래킷 {n}개 체결", height="지상 ~ {h}m", hazard="공구 낙하·협착",
                   protect="작업구역 표지 / 하부 출입 통제", end="체결 상태 기록", area=4),
    "bolt_mcc4": dict(steps=["작업 구역·전원 상태 확인", "전동 임팩트렌치로 론지 브래킷 볼트 체결 (전원 MCC-4)", "체결 토크 확인·전원 정리"],
                      roles="의장공 3명 / 조공 1명", equip="전동 임팩트렌치 3대·작업등 (전원 MCC-4)", material="론지 브래킷, 볼트·너트",
                      spec="브래킷 약 {n}개 체결", height="지상 작업", hazard="공구 협착·감전",
                      protect="누전차단기 확인 / 작업구역 표지", end="체결 상태·전원 정리 기록", area=6),
    "fitup_nc": dict(steps=["도면·부재 번호 확인", "체인블록으로 부재 반입·배치 (크레인 미사용)", "클램프 고정·치수 확인"],
                     roles="취부사 {w1}명 / 조공 1명", equip="체인블록 2대, 지그·클램프", material="내부 보강재 부재",
                     spec="부재 약 {n}개 배치", height="블록 내부 {h}m", hazard="부재 낙하·협착",
                     protect="체인블록 점검 / 하부 출입 통제", end="배치·고정 상태 기록", area=8),
    "surface": dict(steps=["검사 범위·도면 확인", "솔·걸레로 검사 부위 이물·녹 제거", "청소 상태 확인·검사 인계"],
                    roles="조공 {w}명", equip="와이어 솔, 청소 걸레, 진공청소기", material="해당 없음",
                    spec="검사 부위 약 {a}m 청소", height="지상 작업", hazard="분진",
                    protect="방진마스크·보안경", end="청소 완료·검사 인계 기록", area=0),
    "fan_mcc5": dict(steps=["전원 위치(MCC-5)·케이블 경로 확인", "환기팬·작업등 설치, 전원 MCC-5 연결", "작동·누전차단기 확인"],
                     roles="전장공 {w}명", equip="환기팬 2대, LED 작업등 (전원 MCC-5)", material="연장 케이블·케이블 행거",
                     spec="환기팬 2대·작업등 {n}개 설치", height="블록 내부 {h}m", hazard="감전·케이블 걸림",
                     protect="누전차단기 확인 / 케이블 정리", end="설치·작동 확인 기록", area=0),
    "tidy": dict(steps=["야간 작업 범위 확인", "자재·공구 정리, 자투리 수거", "통로·조명 확인"],
                 roles="조공 {w}명", equip="수레, 이동식 조명", material="해당 없음",
                 spec="구역 약 {a}m² 정리", height="지상 작업", hazard="야간 조도 부족·걸림",
                 protect="이동식 조명 / 통로 확보", end="정리 완료 기록", area=0),
    "scaffold_down": dict(steps=["상부 작업 여부·자재 낙하 위험 확인", "위에서부터 족장 해체·하강", "해체 자재 정리·반출"],
                          roles="족장공 {w}명", equip="족장 해체 공구, 로프", material="강관 족장·발판",
                          spec="족장 약 {a}m 해체", height="최고 {h}m", hazard="해체 자재 낙하·추락",
                          protect="안전대 / 하부 출입 통제", end="해체 완료·자재 반출 기록", area=10),
    "scaffold_up": dict(steps=["바닥·받침 상태 확인", "족장 설치·발판 고정", "난간·승강로 점검 후 사용 표지"],
                        roles="족장공 {w}명", equip="족장 설치 공구, 로프", material="강관 족장·발판",
                        spec="족장 약 {a}m 설치", height="최고 {h}m", hazard="추락·자재 낙하",
                        protect="안전대 / 하부 출입 통제", end="사용 가능 표지 부착", area=10),
    "forklift": dict(steps=["운반 경로·통행 인원 확인", "지게차로 부재 운반", "적치 상태·통로 확보 확인"],
                     roles="지게차 운전 1명 / 유도원 1명", equip="지게차 5톤 1대", material="강재 부재",
                     spec="부재 약 {n}회 운반", height="지상 작업", hazard="지게차 충돌·협착",
                     protect="유도원 배치 / 경광등", end="통로 정리 확인", area=0),
    "marking": dict(steps=["도면 기준선 확인", "먹줄·마커로 조립위치 표시", "표시 확인·기록"],
                    roles="마킹공 {w}명", equip="줄자, 먹줄, 마커", material="마킹 도료",
                    spec="기준선 약 {a}m 표시", height="지상 작업", hazard="통행 차량 충돌",
                    protect="작업구역 표지", end="마킹 확인 기록", area=0),
    "measure": dict(steps=["측정 기준점 확인", "토탈스테이션으로 치수·형상 측정", "측정값 기록·보정 요청"],
                    roles="측정원 {w}명", equip="토탈스테이션 1대", material="해당 없음",
                    spec="측정점 약 {n}개", height="지상 ~ {h}m", hazard="통행 차량 충돌",
                    protect="작업구역 표지", end="측정 결과 보고", area=0),
    "align": dict(steps=["받침대 위치 확인", "크레인으로 블록 정렬", "받침대 고정·수평 확인"],
                  roles="취부사 2명 / 신호수 1명", equip="크레인 {crane}, 유압잭", material="받침대·쐐기",
                  spec="받침대 {n}개 설치", height="지상 작업", hazard="블록 전도·협착",
                  protect="신호수 배치 / 하부 출입 통제", end="수평 측정 기록", area=0),
    "vt": dict(steps=["검사 범위·도면 확인", "용접부 육안검사", "불합격부 표시·보고"],
               roles="검사원 {w}명", equip="검사 게이지, 랜턴", material="해당 없음",
               spec="용접부 약 {a}m 검사", height="지상 작업", hazard="통행 차량 충돌",
               protect="작업구역 표지", end="검사 결과 보고", area=0),
    "receive": dict(steps=["입고 목록·부재 번호 확인", "부재 수량·상태 확인", "인수 기록·적치 위치 표시"],
                    roles="생산관리 1명 / 조공 1명", equip="해당 없음", material="입고 부재",
                    spec="부재 약 {n}개 확인", height="지상 작업", hazard="적치 부재 전도",
                    protect="적치 상태 확인", end="인수 기록", area=0),
    "pipe": dict(steps=["스풀 번호·도면 확인", "체인블록으로 스풀 거치·플랜지 볼트 체결", "가스켓·체결 상태 확인"],
                 roles="배관사 {w}명", equip="체인블록, 토크렌치", material="배관 스풀, 가스켓·볼트",
                 spec="스풀 {n}개 설치", height="블록 내부 {h}m", hazard="부재 낙하·협착",
                 protect="체인블록 점검 / 하부 출입 통제", end="체결 상태 기록", area=4),
    "primer": dict(steps=["플랜지부 청소·건조 확인", "프라이머 터치업", "건조 확인·용기 회수"],
                   roles="도장공 {w}명", equip="붓, 송풍기 1대", material="방청 프라이머",
                   spec="플랜지 {n}개소 터치업", height="블록 내부 {h}m", hazard="용제 증기",
                   protect="환기·방독마스크 / 화기 금지", end="건조 확인", area=2),
    "insulation": dict(steps=["부착 면 청소·확인", "보온재 재단·부착", "고정 상태 확인"],
                       roles="보온공 {w}명", equip="커터, 고정 핀 공구", material="미네랄울 보온재",
                       spec="보온재 약 {a}m² 부착", height="블록 내부 {h}m", hazard="분진·가연물 적치",
                       protect="방진마스크 / 화기 금지 표지", end="자투리 회수", area=8),
    "cable": dict(steps=["트레이 위치·도면 확인", "트레이 브래킷·트레이 설치", "고정 상태 확인"],
                  roles="전장공 {w}명", equip="충전 드릴, 이동식 작업대", material="케이블 트레이·볼트",
                  spec="트레이 약 {a}m 설치", height="블록 내부 {h}m", hazard="사다리 추락",
                  protect="작업대 난간 확인 / 안전대", end="설치 확인", area=0),
    "mt": dict(steps=["검사 부위 청소 확인", "자분탐상검사", "결함 표시·보고"],
               roles="검사원 {w}명", equip="요크형 자화기 1대", material="형광 자분액",
               spec="용접부 약 {a}m 검사", height="지상 작업", hazard="자분액 미끄럼",
               protect="작업구역 표지", end="검사 결과 보고", area=0),
    "degrease": dict(steps=["화기작업 없음·환기 확인", "세정제로 탈지", "세정제 회수·건조 확인"],
                     roles="도장공 {w}명", equip="송풍기 1대, 세정 걸레", material="세정제(유기용제)",
                     spec="세정 면적 약 {a}m²", height="지상 ~ {h}m", hazard="유기용제 증기·인화",
                     protect="환기·방독마스크 / 화기 금지", end="세정제 용기 회수", area=6),
    "cleaning": dict(steps=["잔재 범위 확인", "잔재·자투리 수거", "통로 정리 확인"],
                     roles="조공 {w}명", equip="수레, 집게", material="해당 없음",
                     spec="구역 약 {a}m² 정리", height="지상 작업", hazard="날카로운 잔재",
                     protect="장갑·안전화", end="정리 완료 기록", area=0),
    "jig": dict(steps=["정반 사용 일정 확인", "지그 해체·정리", "정반 상태 확인"],
                roles="조공 {w}명", equip="크레인 {crane}, 렌치", material="지그·쐐기",
                spec="지그 {n}개 정리", height="지상 작업", hazard="지그 낙하·협착",
                protect="신호수 배치", end="정반 사용 가능 표지", area=0),
    "ut": dict(steps=["검사 부위 확인", "초음파탐상검사", "결함 기록·보고"],
               roles="검사원 {w}명", equip="초음파탐상기 1대 (배터리)", material="접촉 매질",
               spec="용접부 약 {a}m 검사", height="지상 작업", hazard="통행 차량 충돌",
               protect="작업구역 표지", end="검사 결과 보고", area=0),
    "coat_check": dict(steps=["건조 시간 확인", "도막 두께·건조 상태 측정", "결과 기록"],
                       roles="도장 검사원 1명", equip="도막 두께 측정기", material="해당 없음",
                       spec="측정점 약 {n}개", height="지상 작업", hazard="통행 차량 충돌",
                       protect="작업구역 표지", end="측정 결과 기록", area=0),
    "haul": dict(steps=["반출 대상 확인", "수레·지게차 요청으로 반출", "적치장 정리"],
                 roles="조공 {w}명", equip="수레", material="자투리 강재",
                 spec="약 {n}회 반출", height="지상 작업", hazard="적치 전도",
                 protect="통로 확보", end="반출 완료 기록", area=0),
    "welder_check": dict(steps=["용접기 외관·접지 확인", "케이블 손상 점검·정리", "점검 결과 기록"],
                         roles="전기 담당 1명", equip="절연저항계", material="해당 없음",
                         spec="용접기 {n}대 점검", height="지상 작업", hazard="감전",
                         protect="전원 차단 후 점검", end="점검표 기록", area=0),
    "report": dict(steps=["검사 기록 수집", "결과 정리·불합격부 목록 작성", "결과 통보"],
                   roles="검사원 {w}명", equip="노트북", material="해당 없음",
                   spec="검사 {n}건 정리", height="사무 작업", hazard="해당 없음",
                   protect="해당 없음", end="결과 통보 기록", area=0),
}
PROCESS = {"paint": "선행도장", "primer": "선행도장", "degrease": "선행도장", "coat_check": "선행도장", "pipe": "선행의장",
           "insulation": "선행의장", "cable": "선행의장", "outfit": "선행의장", "outfit_crane": "선행의장", "bolt_mcc4": "선행의장",
           "fan_mcc5": "선행의장"}
WRITERS = ["윤XX", "이XX", "정XX", "최XX", "한XX", "오XX"]
LEADS = ["김XX", "박XX", "강XX", "조XX", "임XX", "서XX"]


def plan(i, p):
    pid, company, kind, title, a, b, bay, cols, blk, workers, simops = p
    t, n = T[kind], int(pid[2:])
    place = f"대조립21공장 {bay} {cols} 칼럼 {blk} 블록" if cols else f"대조립21공장 {bay} 2층 검사실"
    fill = dict(w=workers, w1=max(1, workers - 1), a=6 + n % 9 * 2, n=3 + n % 7, h=[2.5, 3.0, 3.6, 4.2, 4.8][n % 5],
                crane=CRANE.get(bay, "해당 없음"))
    fmt = lambda s: s.format(**fill)
    hull = HULL.get(blk, "3611")
    area = t["area"]
    items = {
        "작업명": title, "수행업체": f"{company} / {'본청 생산부서' if pid in INHOUSE else '협력사 배정'}", "작성자": f"{WRITERS[n % 6]} / 생산관리",
        "책임자": f"{LEADS[n % 6]} / 현장 작업책임자", "호선": f"{hull} / {blk} 블록",
        "시작일시": f"{DAY} {a}", "종료일시": f"{DAY} {b}", "시간대": "Asia/Seoul",
        "작업상태": "계획 / 전일 작성", "작업범위": f"{blk} 블록 {fmt(t['spec'])}"[:40],
        "작업위치": place, "대상ID": f"{blk}-{kind.upper()[:3]}-{n:02d} / {bay} {cols} 칼럼" if cols else f"{blk} 검사 기록",
        "연결정보": f"{bay} 중앙 통로 / 크레인 {CRANE.get(bay, '없음')}" if cols else "검사실 / 해당 없음",
        "도면자료": f"F01 배치도 R1 / {blk} 블록 도면 Rev.B",
        "작업인원": f"{workers}명", "담당배치": fmt(t["roles"]), "작업장비": fmt(t["equip"]), "사용물질": t["material"],
        "작업사양": fmt(t["spec"]), "작업높이": fmt(t["height"]),
        "1단계": t["steps"][0], "2단계": t["steps"][1], "3단계": t["steps"][2],
        "공정단계": PROCESS.get(kind, "대조립"), "분류근거": "블록 조립 단계 작업 (조사자료 일상작업 목록)",
        "선행작업": "작업 구역 정리·도면 확인", "선행조건": f"{t['protect'].split(' / ')[0]} 준비 확인",
        "혼재작업": simops or "확인된 혼재작업 없음", "방호조치": t["protect"],
        "확인자": "직반장 확인 예정", "기록근거": f"작업지시서 WO-1029-{n:02d}",
        "유효조건": "조건이 바뀌면 작업을 멈추고 다시 확인", "출입구": f"{bay} 측면 출입구" if cols else "사무동 출입구",
        "통로대피": f"{bay} 중앙 통로 → 비상구" if cols else "2층 계단 → 1층 출구",
        "이전상태": "이전 작업 잔류물 없음 확인 예정", "종료기록": t["end"],
        "해제기록": "작업구역 통제 해제 기록 예정" if area else "해당 없음",
        "후속요건": "다음 공정 인계 시 상태 전달", "검토승인": "직반장 검토 예정 / 승인 아님",
    }
    grid = [["공간·대상", f"{blk} {bay}", a, f"{cols} 칼럼" if cols else "검사실"],
            ["위험요소", t["hazard"][:16], "계획 위험", "작업 구역"],
            ["방호 상태", t["protect"].split(" / ")[0][:16], "작업 전", "작업 구역"],
            ["가동·위험 기간", f"{a}-{b}", "계획값", "당일"],
            ["위험 종료", t["end"][:16], "미기재", "종료 후 확인"]]
    head = {"doc_no": f"WP-1029-{n:02d}", "work_no": f"D{n:02d}", "rev": "R0", "issued": REQ, "plan_date": DAY,
            "drawing_basis": "F01-R1"}
    # the blank form: a 협력사's own (its logo), the 본청 one for a 본청 department
    return {"id": pid, "company": company, "form": "본청" if pid in INHOUSE else company, "kind": kind, "head": head, "items": items, "grid": grid}


WORKPLANS = [plan(i, p) for i, p in enumerate(PLANS)]
P = {x["permit_no"][-4:]: x["permit_no"] for x in PERMITS}
CLASHES = [
    dict(id="C01", a=P["0731"], b="WP01", type="화기 × 도장(유기용제)", priority=1,
         why="3BAY 08-10 칼럼 E42P 상부, 13:30-15:00 겹침. 반장은 장소·시간을 대충 적었고(팀 이름, 하루 내내) 확인 질문에서 실제 시간·위치가 드러남"),

    # QA #56: WP02 is no longer hot work (C02 used to be 밀폐 내부 × 상부 화기); the crane still brings the 의장품 onto E41P
    dict(id="C02", a=P["0733"], b="WP02", type="밀폐 내부 인원 × 같은 블록 인양", priority=1,
         why="E41P 이중저 내부 진입 09:00-11:30 중 10:30에 OH-21-03로 같은 블록 갑판에 의장품 인양(WP02). 내부 인원 위로 인양물이 지남"),
    dict(id="C03", a=P["0737"], b=P["0733"], type="인양 경로 × 밀폐 진입", priority=1,
         why="OH-21-03 E45P 이동 10:30-11:30, 경로 3BAY 06→16칼럼이 E41P(12-14칼럼) 위를 지남. 이중저 안에 2명, 맨홀 밖 감시 1명"),

    dict(id="C05", a=P["0735"], b="WP04", type="고소 러그 절단 × 하부 족장 해체", priority=1,
         why="1BAY 14-16 칼럼 B21S, 14:00-15:30 상부 러그 절단(불티·낙하) 아래에서 족장 해체. 반장은 알고 있다고 답함"),
    dict(id="C06", a=P["0736"], b="WP05", type="고소작업대 × 지게차 통로", priority=2,
         why="4BAY 03-05 칼럼 MEWP 09:00-11:00, 지게차가 4BAY 01-08칼럼 통로로 09:30-10:30 운반"),
    dict(id="C07", a=P["0737"], b=P["0739"], type="같은 크레인 정비 × 사용", priority=1,
         why="OH-21-03 제어반 정전 수리 10:00-12:00 중 같은 크레인으로 10:30 인양 계획. 정전 허가서는 병행 N"),
    dict(id="C08", a=P["0738"], b="WP06", type="인양 경로 × 하부 작업자", priority=2,
         why="OH-21-02 B22S 반출(허가 15:30-16:30, 실제 이동 15:40-16:10), 경로 2BAY 05→20칼럼 아래 09-11칼럼에서 의장품 볼트 체결 15:30-17:00"),
    dict(id="C09", a=P["0739"], b="WP02", type="크레인 정전 × 크레인 필요 작업", priority=2,
         why="WP02는 10:30에 OH-21-03로 의장품을 올리는 계획인데 그 크레인이 10:00-12:00 정전 수리 중"),
    dict(id="C10", a=P["0740"], b="WP07", type="공유 전원 정전 × 전원 사용 작업", priority=2,
         why="MCC-4 정전 13:00-15:00, 전동공구·작업등 전원을 MCC-4 분기에서 받는 4BAY 11-13칼럼 볼트 체결 13:00-16:00. 정전 허가서는 협의 필요라고 적음"),
    dict(id="C13", a=P["0737"], b="WP02", type="인양 경로 × 상부 작업자", priority=1,
         why="E45P 인양 경로 3BAY 06→16칼럼이 10:30-11:30에 E41P 갑판(12-14칼럼) 위를 지남. 갑판에서 10:00-12:00 의장품 거치·볼트 체결 4명"),
    dict(id="C12", a="WP10", b="WP11", type="지게차 × 바닥 마킹 작업자", priority=3,
         why="1BAY 01-05 칼럼, 지게차 반입 08:30-09:30과 마킹 08:00-10:00 겹침 (통행 관리로 조정 가능)"),
]
NEAR = [
    dict(id="N01", a=P["0732"], b="WP04", why="같은 1BAY 14-16 칼럼이지만 용접 09:00-11:30, 족장 해체 13:00 시작: 시간이 떨어짐"),
    dict(id="N02", a=P["0734"], b="WP06", why="같은 2BAY지만 05-06 칼럼 13:00-15:00과 09-11 칼럼 15:30-: 칼럼 3칸 이상, 시간도 떨어짐"),
    dict(id="N03", a=P["0736"], b="WP12", why="같은 4BAY 03-05 칼럼이지만 고소작업대 09:00-11:00, 마킹 13:00-14:00"),
    dict(id="N05", a=P["0731"], b="WP30", why="같은 3BAY 13:00-14:00이지만 화기 08-10칼럼과 세정(유기용제) 17-20칼럼: 칼럼 7칸(84m) 떨어짐"),
    dict(id="N04", a=P["0740"], b="WP13", why="같은 4BAY 13:00-15:00이지만 환기팬·작업등은 MCC-5 전원 사용: MCC-4 정전과 무관"),
]


def write(part="all"):
    OUT.mkdir(parents=True, exist_ok=True)
    if part in ("permits", "all"):
        (OUT / "permits.json").write_text(json.dumps({"date": DAY, "factory": "대조립21공장", "permits": PERMITS}, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    if part in ("plans", "all") and "WORKPLANS" in globals():
        (OUT / "workplans.json").write_text(json.dumps({"workplans": WORKPLANS}, ensure_ascii=False, indent=1), encoding="utf-8")
        (OUT / "skeleton.json").write_text(json.dumps({"clashes": CLASHES, "near_misses": NEAR}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    import sys
    write(sys.argv[1] if len(sys.argv) > 1 else "all")
