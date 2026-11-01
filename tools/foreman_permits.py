"""작업반장 test permits: one 안전부서 제출용 permit per file, two per kind (data for tools/make_form.py).

They follow how the two photographed permits (실물 0453, 0400) were actually filled in:
  - the work time is the whole shift, 08:00~16:59, copied over several days (both 실물)
  - the place is a team name ("UNIT2공장 유니트4팀", 0453) or a factory without BAY·칼럼
  - 호선/공사 left empty (0453), 병행여부 left empty (both)
  - 유해위험요소 in a few words ("질식,소음" with 아르곤 ticked, 0453)
  - several blocks listed in one 작업내용 ("B11, F31, E11 ...", 0400)
Case A of each kind carries those habits; case B is filled in carefully. "asked" is exactly what
the 작업반장 view must ask (server/augment.py, the research rule: only what is needed and missing,
unclear or contradictory; never the day-of-work boxes); "assumed" are blanks that are normal for the
kind of work and only noted on page 2. tools/check_questions.py checks both. Names and numbers are
masked (XX). Why case B still gets a question:
  0706 고소 B  HT1 the cutting method is not written (it decides sparks and the time model),
               HT2 how the cut lugs come down and where is not written
  0708 인양 B  T6 40 minutes for a whole lift (prepare → land → unhook) is far below the matching
               reference model (N4-EST-A 120~240 min, author estimate): is it the moving part only?
  0710 정전 B  LO3 restore / test-run times are not written; T6 120 minutes against the module
               replacement model (EST-C 150~360 min)

The filing date is the day before the work (전날 15시 마감); approval rows are empty
because the permit is checked before 전산승인.
"""

REQ = "2026-10-26"


def days(first, n, a="08:00", b="16:59"):
    return [(f"2026-10-{first + i:02d}", a, b) for i in range(n)]


def common(no, **kw):
    d = {"permit_no": f"AC00-IH-202610{kw.pop('day', 27):02d}-{no}", "supervisor": "김XX", "supervisor_phone": "010-XXXX-XXXX",
         "manager": "박XX", "manager_phone": "010-XXXX-XXXX", "req_name": "김XX", "req_date": REQ, "req_sign": "김XX"}
    d.update(kw)
    return d


FOREMAN = [
    # 화기 A: whole shift for 4 days, team name as place, 호선·병행여부 empty, a height in the text without
    # 「고소 화기작업」, hazards without fire/spark, several blocks in one line
    dict(common("0701", kind="hot", case="A", permit_type="[안전현장허가]", hull_no="", jsp_no="HHIS-CW-A0001187-012-004",
                location="대조립1부 용접3팀", location_detail="", job="취부 불량부 절단·재용접(B11, F31, E11 블록)",
                job_detail="발판 위 높이 2.5m 구간 포함", department="대조립1부-용접3팀", workers="4", hazards="용접흄, 소음",
                concurrent="", days=days(27, 4), double_check="Y", checks={"day": "set", "weld_cut": "set"}),
         asked=['T1', 'L1', 'H1', 'H2', 'B3'], assumed=[]),
    dict(common("0702", kind="hot", case="B", permit_type="[안전현장허가]", hull_no="3611-E33S", jsp_no="HHIS-CW-A0001187-015-002",
                location="대조립21공장 3BAY 14-16 칼럼", location_detail="E33S 블록 하부 종통재", job="E33S 블록 종통재 균열부 가우징·재용접",
                job_detail="지상 작업, 화재감시자 1명 배치", department="대조립3부-구조보수2팀", workers="3",
                hazards="불티 비산(화재), 용접흄, 절단물 낙하 / 하부 가연물 제거", concurrent="N", days=days(27, 1, "13:00", "15:30"),
                double_check="Y", checks={"day": "set", "weld_cut": "set", "gouging": "set"}),
         asked=[], assumed=[]),
    # 밀폐 A: the 실물 0453 pattern on new values
    dict(common("0703", kind="confined", case="A", permit_type="[안전현장허가]", hull_no="", jsp_no="HHIS-CN-C6B0-019",
                location="UNIT3공장 유니트2팀", location_detail="", job="배관 내 사람이 들어가는 작업", job_detail="파이프 내부 진입",
                department="UNIT생산부-생산1과-UNIT2팀", workers="2", hazards="질식,소음", concurrent="", days=days(27, 5),
                double_check="Y", checks={"day": "set", "confined_space": "set", "argon": "set"}),
         asked=['T1', 'L1', 'CF1', 'CF2', 'B3'], assumed=[]),
    dict(common("0704", kind="confined", case="B", permit_type="[전산허가]", hull_no="3611-F12C", jsp_no="HHIS-CN-C6B0-022",
                location="대조립22공장 1BAY 8-10 칼럼", location_detail="F12C 블록 이중저 내부", job="F12C 이중저 내부 취부 상태 점검",
                job_detail="진입 2명, 맨홀 외부 감시 1명", department="대조립2부-취부1팀", workers="3",
                hazards="산소결핍·질식, 좁은 통로 대피 곤란 / 진입 전 산소·가스 측정", concurrent="Y", days=days(27, 1, "09:00", "11:30"),
                double_check="N", checks={"day": "set", "confined_space": "set"}),
         asked=[], assumed=[]),
    # 고소 A: factory only, whole shift, 작업높이 empty, no category ticked, hazards without fall
    dict(common("0705", kind="height", case="A", permit_type="[전산허가]", hull_no="3611-E42P", jsp_no="HHIS-CW-A0001187-034-001",
                location="대조립21공장", location_detail="", job="블록 상부 임시 러그 절단·제거", job_detail="",
                department="대조립3부-취부3팀", workers="4", hazards="안전대 착용, 공구 휴대", concurrent="", days=days(27, 3),
                double_check="N", checks={"day": "set"}),
         asked=['T1', 'L1', 'HT1', 'L3', 'HT2', 'B3'], assumed=[]),
    dict(common("0706", kind="height", case="B", permit_type="[전산허가]", hull_no="3611-E42P", jsp_no="HHIS-CW-A0001187-034-002",
                location="대조립21공장 3BAY 17-20 칼럼", location_detail="E42P 블록 상부 동측, 작업발판 WP-02", job="E42P 블록 상부 임시 인양러그 절단·제거",
                job_detail="사용 완료 러그 6EA 절단·회수", department="대조립3부-취부3팀", workers="4",
                hazards="추락(4.8m), 러그·공구 낙하 / 하부 통행 통제", concurrent="N", days=days(27, 1, "10:00", "12:00"),
                double_check="N", work_height="4.8", checks={"day": "set", "scaffold": "set"}),
         asked=['HT1', 'HT2'], assumed=[]),
    # 중량물 A: no route, 정격하중 empty, whole shift, hazards without falling/crushing
    dict(common("0707", kind="lifting", case="A", permit_type="[안전현장허가]", hull_no="3611-E21P", jsp_no="HHIS-CW-A0001187-008-003",
                location="대조립21공장 3BAY", location_detail="", job="E21P 블록 반출", job_detail="천장크레인 사용",
                department="대조립3부-운반1팀", workers="5", hazards="신호수 배치, 유도로프 사용", concurrent="", days=days(27, 2),
                double_check="Y", load_weight="38", lift_height="3", checks={"day": "set", "overhead_crane": "set"}),
         asked=['T1', 'LI1', 'L5', 'LI2', 'B3'], assumed=[]),
    dict(common("0708", kind="lifting", case="B", permit_type="[안전현장허가]", hull_no="3611-E25S", jsp_no="HHIS-CW-A0001187-008-004",
                location="대조립21공장 2BAY 5-8 칼럼 → 1BAY 반출장", location_detail="2BAY 서측 통로 경유", job="E25S 블록 반출 인양·이동·안착 (천장크레인 OH-21-01)",
                job_detail="정반 안착 후 줄걸이 해제", department="대조립3부-운반1팀", workers="5",
                hazards="인양물 낙하·협착, 크레인 충돌 / 블록 내부 인원 확인", concurrent="N", days=days(27, 1, "11:00", "11:40"),
                double_check="Y", load_weight="12", crane_swl="20", lift_height="2", checks={"day": "set", "overhead_crane": "set"}),
         asked=['T6'], assumed=[]),
    # 정전 A: team name as place, whole shift, 정격전압 empty, 호선 empty
    dict(common("0709", kind="loto", case="A", permit_type="[전산허가]", hull_no="", jsp_no="HHIS-CE-B0000412-007-001",
                location="설비보전부 전기2팀", location_detail="", job="천장크레인 제어반 점검", job_detail="",
                department="설비보전부-전기2팀", workers="2", hazards="감전", concurrent="N", days=days(27, 3),
                double_check="N", checks={"day": "set", "low_voltage": "set"}),
         asked=['T1', 'L1', 'LO3', 'LO4'], assumed=['B4']),
    # 정전 B: filled in carefully; 호선 is empty because it is plant equipment: noted as an estimate, not asked
    dict(common("0710", kind="loto", case="B", permit_type="[전산허가]", hull_no="", jsp_no="HHIS-CE-B0000412-005-002",
                location="대조립21공장 3BAY 천장크레인 OH-21-03", location_detail="크레인 거더 상부 제어반 CP-01", job="천장크레인 OH-21-03 제어반 인버터 교체",
                job_detail="정전·잠금 후 작업, 복구 전 시험운전", department="설비보전부-전기2팀", workers="3",
                hazards="감전·아크, 재가동 시 끼임, 거더 상부 추락", concurrent="N", days=days(27, 1, "13:00", "15:00"),
                double_check="N", rated_voltage="380", lock_count="2", checks={"day": "set", "low_voltage": "set", "crane_power": "set"}),
         asked=['LO3', 'T6'], assumed=['B4']),
]
