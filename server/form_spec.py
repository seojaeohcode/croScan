"""The 기타위험 작업 허가서 form: where each common value sits and what type it is.
The parts that differ by kind (title, 추가정보 items and value lines) are in
server/permit_kinds.py.

Only printed form text is used here (labels, item names, fixed words). Nothing is
taken from filled-in permits.

Field types (the web form enforces them, the reviewer checks them):
  code   upper-case letters / digits joined by hyphens
  text   free text
  name   person name (masked values such as 최XX allowed)
  phone  010-1234-5678
  count  whole number of people
  number decimal number
  date   YYYY-MM-DD
  time   HH:MM
  yn     Y / N
  check  checkbox (checked / not)
  image  handwriting or signature kept as an image
"""

# (key, Korean name, type, required)
FIELDS = [
    ("permit_no", "승인번호", "code", True),
    ("permit_type", "허가구분", "text", True),
    ("hull_no", "호선/공사", "code", False),
    ("jsp_no", "작업표준", "code", True),
    ("location", "작업장소", "text", True),
    ("location_detail", "작업장소(상세)", "text", False),
    ("job", "작업내용", "text", True),
    ("job_detail", "작업내용(상세)", "text", False),
    ("department", "작업부서", "text", True),
    ("supervisor", "작업책임자", "name", True),
    ("supervisor_phone", "작업책임자 연락처", "phone", True),
    ("manager", "관리자", "name", True),
    ("manager_phone", "관리자 연락처", "phone", True),
    ("workers", "작업인원", "count", True),
    ("hazards", "유해위험요소/추가전달사항", "text", True),
    ("concurrent", "병행여부", "yn", False),
    ("req_name", "허가신청자", "name", True),
    ("req_date", "허가신청 일시", "date", True),
    ("req_sign", "허가신청 서명", "name", True),
    ("app_name", "전산승인자", "name", False),           # filled by the approver, empty when filed
    ("app_date", "전산승인 일시", "date", False),
    ("app_sign", "전산승인 서명", "name", False),
    ("face_name", "안전대면허가자", "image", False),
    ("face_date", "안전대면허가 일시", "image", False),
    ("face_sign", "안전대면허가 서명", "image", False),
    ("double_check", "2중점검 대상", "yn", True),
    ("extra_measures", "추가조치 요청사항(안전요원)", "image", False),
]

DATE_ROWS = 7     # rows of the work-date table

# value printed right after a label inside the same paragraph
INLINE = {
    "permit_no": r"승인번호\s*\(PERMIT NO\.?\)\s*:",
    "hull_no": r"호선\s*/\s*공사\s*\(HULL NO\.?\)\s*:",
    "jsp_no": r"작업표준\s*\(JSP NO\.?\)\s*:",
    "location": r"작업장소\s*\(LOCATION\)\s*:",
    "job": r"작업내용\s*\(JOB DESCRIPTION\)\s*:",
    "supervisor": r"작업책임자\s*\(SUPERVISOR\)\s*:",
    "manager": r"관리자\s*\(MANAGER\)\s*:",
    "workers": r"작업인원\s*\(NO\. OF WORKER\)\s*:",
}
# fixed word after the value (stays printed)
INLINE_TAIL = {"workers": r"명"}

# whole cell is the value; the cell is found from a label cell by grid relation
CELL_BELOW = {"location_detail": r"작업장소\s*\(LOCATION\)", "job_detail": r"작업내용\s*\(JOB DESCRIPTION\)",
              "hazards": r"유해위험요소", "concurrent": r"병행여부"}
CELL_RIGHT = {"department": r"작업부서\s*\(DEPARTMENT\)", "permit_type": r"허가구분\s*\(PERMIT TYPE\)"}
PHONE_ROW = {"supervisor_phone": r"작업책임자", "manager_phone": r"관리자\s*\(MANAGER\)"}
# sign-off rows: row label -> (name, 일시, 서명) keys
SIGN_ROWS = {
    r"허가신청": ("req_name", "req_date", "req_sign"),
    r"전산승인": ("app_name", "app_date", "app_sign"),
    r"안전대면허가": ("face_name", "face_date", "face_sign"),
}
DOUBLE_CHECK = r"2중점검\s*대상\s*:"
EXTRA_MEASURES = r"추가조치\s*요청사항"

# checkbox items common to every kind (key, item text start, group);
# the 추가정보 items come from permit_kinds.checks(kind)
CHECKS = [
    ("day", "주간", "작업 일시"), ("night", "야간", "작업 일시"),
    ("notice_sign", "공지문/경고표지 부착", "현장 안전조치"), ("area_control", "작업구역 통제조치 실시", "현장 안전조치"),
    ("loto", "전원차단 및 브레이커 잠금 실시", "현장 안전조치"), ("simops", "병행작업 확인", "현장 안전조치"),
    ("flammables", "인화성물질 제거", "현장 안전조치"), ("fire_equipment", "소화장비 배치", "현장 안전조치"),
    ("accessway", "통행로 확보", "현장 안전조치"), ("night_lighting", "야간 작업시 조명 설치", "현장 안전조치"),
]
# items written on the day of work only ("사전 작성금지"): blank is normal before approval
DAY_OF_WORK_GROUPS = {"현장 안전조치", "추가정보"}
