"""합성 허가 신청 5건 (대조립) - data for tools/make_form.py.

Scenario after the team's research file (N01~N05, 2026-10-27, one 대조립 bay), as each
작업반장 would file it the day before (2026-10-26): approval rows empty, day-of-work
boxes empty, only the category heads that apply are ticked, planned values filled in.
Places, numbers and equipment are made up to look like the real permits (masked
names, hull 3611, 대조립21공장 3BAY). N02 follows the research file's current
definition (아르곤 사용 조건의 배관 내부 진입), not the older 폐쇄 블록 회수.

Built-in links between them (the research file's risk pairs P01~P05):
  P01 N01×N02  same block E41P: cutting/welding outside, pipe entry inside
  P02 N02×N04  the block with people inside its pipe is lifted out
  P03 N03×N04  the lift route passes the lug-removal platform in the same bay
  P04 N04×N05  lift and repair need the same crane OH-21-03
  P05 N01×N04  the block under repair is lifted out
Filing gaps a reviewer should catch: N03 and N04 leave 병행여부 empty, N05 answers
병행여부 N although its crane is the one N04 lifts with.
"""

REQ_DAY = "2026-10-26"

SYN = [
    {"kind": "hot", "permit_no": "BS22-IV-20261027-2236", "permit_type": "[안전현장허가]",
     "hull_no": "3611-E41P", "jsp_no": "HHIS-CW-A0001123-021-003",
     "location": "대조립21공장 3BAY 12-16 칼럼 E41P 블록 동측 측판", "location_detail": "대조립 21공장 3BAY 12-16 칼럼",
     "job": "E41P 블록 중대 불량부 절단·가우징·재취부·재용접",
     "job_detail": "동측 측판·보강재 불량부 절단 후 신규 부재 취부·재용접, 작업높이 3.6m",
     "department": "대조립3부-구조보수1팀", "supervisor": "김XX", "supervisor_phone": "010-XXXX-XXXX",
     "manager": "박XX", "manager_phone": "010-XXXX-XXXX", "workers": "5",
     "hazards": "절단물 낙하·전도, 불티 비산(화재), 용접흄·소음, 3.6m 작업면 추락 / 같은 블록 내부 배관 진입작업 예정",
     "concurrent": "Y",
     "days": [("2026-10-27", "09:00", "12:00"), ("2026-10-28", "09:00", "11:30")],
     "req_name": "김XX", "req_date": REQ_DAY, "req_sign": "김XX", "double_check": "Y",
     "work_height": "3.6",
     "checks": {"day": "set", "weld_cut": "set", "gouging": "set", "hot_at_height": "set"}},
    {"kind": "confined", "permit_no": "BS22-IV-20261027-3359", "permit_type": "[안전현장허가]",
     "hull_no": "3611-E41P", "jsp_no": "HHIS-CN-C6B0-021",
     "location": "대조립21공장 3BAY 12-16 칼럼 E41P 블록 내부", "location_detail": "E41P 블록 내부 배관 P-07 퍼지 구간",
     "job": "아르곤 퍼지 배관 내부 진입 (용접부 비드 확인)",
     "job_detail": "배관 내 사람이 들어가는 작업 / 진입 2명, 외부 감시 1명",
     "department": "대조립3부-배관취부2팀", "supervisor": "이XX", "supervisor_phone": "010-XXXX-XXXX",
     "manager": "정XX", "manager_phone": "010-XXXX-XXXX", "workers": "3",
     "hazards": "질식(아르곤 산소결핍), 소음, 좁은 통로 대피 곤란 / 같은 블록 외판 절단·용접작업 있음",
     "concurrent": "Y",
     "days": [("2026-10-27", "09:30", "11:00")],
     "req_name": "이XX", "req_date": REQ_DAY, "req_sign": "이XX", "double_check": "Y",
     "checks": {"day": "set", "confined_space": "set", "argon": "set"}},
    {"kind": "height", "permit_no": "BS22-IV-20261027-3590", "permit_type": "[전산허가]",
     "hull_no": "3611-E42P", "jsp_no": "HHIS-CW-A0001123-034-002",
     "location": "대조립21공장 3BAY 17-20 칼럼 E42P 블록 상부", "location_detail": "E42P 블록 상부 동측, 작업발판 WP-02",
     "job": "E42P 블록 상부 임시 인양러그 절단·제거",
     "job_detail": "사용 완료 러그 6EA 절단·회수 및 그라인딩",
     "department": "대조립3부-취부3팀", "supervisor": "오XX", "supervisor_phone": "010-XXXX-XXXX",
     "manager": "윤XX", "manager_phone": "010-XXXX-XXXX", "workers": "4",
     "hazards": "추락(4.8m), 러그·공구 낙하, 절단 불티 / 하부 통로 통행 통제 필요",
     "concurrent": "",
     "days": [("2026-10-27", "10:00", "12:00")],
     "req_name": "오XX", "req_date": REQ_DAY, "req_sign": "오XX", "double_check": "N",
     "work_height": "4.8",
     "checks": {"day": "set", "scaffold": "set"}},
    {"kind": "lifting", "permit_no": "BS22-IV-20261027-3702", "permit_type": "[안전현장허가]",
     "hull_no": "3611-E41P", "jsp_no": "HHIS-CW-A0001123-008-001",
     "location": "대조립21공장 3BAY 12-16 칼럼 → 1BAY 4-6 칼럼 반출장", "location_detail": "E41P 블록 반출, 3BAY 동측 통로 경유",
     "job": "E41P 블록 반출 인양·이동·안착 (천장크레인 OH-21-03)",
     "job_detail": "기존 받침에서 인양, 1BAY 반출장 정반에 안착 후 줄걸이 해제",
     "department": "대조립3부-운반1팀", "supervisor": "장XX", "supervisor_phone": "010-XXXX-XXXX",
     "manager": "서XX", "manager_phone": "010-XXXX-XXXX", "workers": "5",
     "hazards": "인양물 낙하·전도, 협착, 크레인 간 충돌 / 블록 내부 인원·임시 지지재 확인 필요",
     "concurrent": "",
     "days": [("2026-10-27", "10:30", "11:30")],
     "req_name": "장XX", "req_date": REQ_DAY, "req_sign": "장XX", "double_check": "Y",
     "load_weight": "38", "crane_swl": "50", "lift_height": "3",
     "checks": {"day": "set", "overhead_crane": "set"}},
    {"kind": "loto", "permit_no": "BS22-IV-20261027-3987", "permit_type": "[전산허가]",
     "hull_no": "", "jsp_no": "HHIS-CE-B0000412-005-001",
     "location": "대조립21공장 3BAY 천장크레인 OH-21-03 제어반", "location_detail": "3BAY 크레인 거더 상부 제어반 CP-01",
     "job": "천장크레인 OH-21-03 제어반 전기계통 고장 수리",
     "job_detail": "주행 인버터 제어 접점·배선 점검 및 교체, 정전 후 작업",
     "department": "설비보전부-전기2팀", "supervisor": "황XX", "supervisor_phone": "010-XXXX-XXXX",
     "manager": "안XX", "manager_phone": "010-XXXX-XXXX", "workers": "3",
     "hazards": "감전·아크, 재가동 시 끼임, 거더 상부 추락 / 수리 중 크레인 사용 금지 통보 필요",
     "concurrent": "N",
     "days": [("2026-10-27", "08:30", "11:30")],
     "req_name": "황XX", "req_date": REQ_DAY, "req_sign": "황XX", "double_check": "N",
     "rated_voltage": "380", "lock_count": "2",
     "checks": {"day": "set", "low_voltage": "set", "crane_power": "set"}},
]
