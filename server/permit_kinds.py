"""The five 기타위험 작업 허가서 kinds used in 대조립, and what differs between them:
the title and the 「추가정보」 block. Everything else on the form is common.

The 밀폐 block is the real printed form. The other four keep the same grid (three
category heads, two columns of five items, a third column with one item, one
item with two value lines, and one item with a value). Their items come from the
safety rules for that kind of work (산업안전보건기준에 관한 규칙, checked against the current text 2026-10-31):
  화기  제241조②(가연물 방호·비산방지·환기·소화기·피난교육), 제241조의2(화재감시자), 제232조②(가스 검지·경보장치 설치)·제241조의2②2(작동 확인)
  고소  제14조(낙하물·출입금지), 제42조(작업발판·방호망), 제43조(안전난간·개구부), 제44조(안전대 부착설비)
  중량물 제38조(작업계획서), 제40조(신호), 제146조(인양물 하부 출입통제), 제137조·제149조(크레인·이동식 크레인 해지장치), 제163조(달기구)
  정전  제319조②(도면 확인·차단·잠금·꼬리표·방전·검전·접지), 제319조③(통전 전 접지기구 제거·작업자 이격 확인·설치자 잠금 철거)
  밀폐  제618~625조(적정공기·환기·인원 점검·감시인·보호구)
Used by both the PDF generator (tools/make_form.py) and the extractor (server/extract.py).
The kind is not guessed from the PDF: the applicant picks it on the first screen.

Each kind:
  heads   three category boxes, ticked when the permit is filed (■ = applies)
  col1/2  five day-of-work items each (사전 작성금지: empty when filed)
  col3    a: one item; c: one item with two value lines; d: one item with a value
          value line = (field key, printed label, printed unit, name for the field)
"""
import re

KINDS = {
    "confined": {
        "label": "밀폐", "title": "기타위험(밀폐)작업 허가서", "title_en": "OTHER RISKY WORK PERMIT",
        "heads": [("confined_space", "밀폐구역출입 (CONFINED SPACE)"), ("height_work", "고소작업(WORKING AT HEIGHTS)"),
                  ("argon", "아르곤가스 사용(USE OF ARGON GAS)")],
        "col1": [("entry_board", "출입현황판 설치(ENTRY BOARD)"), ("watchman", "출입감시자 배치(WATCHMAN)"),
                 ("ventilation", "환기(VENTILATION)"), ("gas_test", "가스측정(GAS TEST)"), ("lighting", "조명설치(LIGHTING)")],
        "col2": [("access_means", "출입수단(SAFE ACCESS/EGRESS)"), ("platform", "작업대(WORK PLATFORM)"),
                 ("harness", "안전벨트(SAFETY HARNESS)"), ("lifeline", "생명줄(LIFE LINE)"),
                 ("fall_protection", "기타안전조치(FALL PROTECTION)")],
        "a": ("commissioning", "수전구역(COMMISSIONING AREA)"),
        "c": ("pressure_use", "압력사용(PRESSURE)", [
            ("test_pressure", "- 테스트압력(TEST PRESSURE):", "BAR/KG", "테스트압력(BAR/KG)"),
            ("pipe_diameter", "- 파이프직경(PIPE DIAMETER):", "인치(IN.)", "파이프직경(인치)")]),
        "d": ("height_box", "작업높이(HEIGHT OF WORK):", ("work_height", "미터(M)", "작업높이(미터)")),
        "required": [],
    },
    "hot": {
        "label": "화기", "title": "기타위험(화기작업)작업 허가서", "title_en": "HOT WORK PERMIT",
        "heads": [("weld_cut", "용접·용단(WELDING/CUTTING)"), ("gouging", "가우징(ARC GOUGING)"),
                  ("hot_at_height", "고소 화기작업(HOT WORK AT HEIGHT)")],
        "col1": [("hw_combustibles", "가연물 제거·방호(COMBUSTIBLES)"), ("hw_spark_cover", "불티 비산방지덮개(SPARK COVER)"),
                 ("hw_extinguisher", "소화기 비치(EXTINGUISHER)"), ("hw_fire_watch", "화재감시자 배치(FIRE WATCH)"),
                 ("hw_post_check", "작업 후 잔불 확인(FIRE CHECK)")],
        "col2": [("hw_ventilation", "환기·국소배기(VENTILATION)"), ("hw_gas_alarm", "가스검지·경보장치(GAS DETECTOR)"),
                 ("hw_hose", "호스·역화방지기(HOSE/ARRESTOR)"), ("hw_earthing", "용접기 접지·케이블(EARTHING)"),
                 ("hw_drill", "화재예방·피난교육(FIRE DRILL)")],
        "a": ("hw_cut_support", "절단물 지지·회수(CUT PIECE SUPPORT)"),
        "c": ("hw_gas_test", "가스농도 측정(GAS TEST)", [
            ("gas_lel", "- 가연성가스(FLAMMABLE GAS):", "%LEL", "가연성가스 농도(%LEL)"),
            ("oxygen", "- 산소농도(OXYGEN):", "%(O2)", "산소농도(%)")]),
        "d": ("hw_height", "작업높이(HEIGHT OF WORK):", ("work_height", "미터(M)", "작업높이(미터)")),
        "required": [],
    },
    "height": {
        "label": "고소", "title": "기타위험(고소작업)작업 허가서", "title_en": "WORK AT HEIGHT PERMIT",
        "heads": [("scaffold", "비계·작업발판(SCAFFOLD)"), ("mewp", "고소작업대(MEWP)"), ("ladder", "이동식 사다리(LADDER)")],
        "col1": [("wh_platform", "작업발판 고정·손상 점검(PLATFORM)"), ("wh_guardrail", "안전난간 설치(GUARDRAIL)"),
                 ("wh_opening", "개구부 덮개·표시(OPENING COVER)"), ("wh_access", "승강로 확보(ACCESS)"),
                 ("wh_net", "추락방호망(SAFETY NET)")],
        "col2": [("wh_mewp_check", "작업대 작업 전 점검(PRE-USE CHECK)"), ("wh_overrise", "과상승방지장치(OVER-RISE GUARD)"),
                 ("wh_harness", "그네식 안전대 착용(FULL HARNESS)"), ("wh_anchor", "안전대 부착설비(ANCHORAGE)"),
                 ("wh_tool_lanyard", "공구 낙하방지끈(TOOL LANYARD)")],
        "a": ("wh_exclusion", "하부 출입금지구역 설정(EXCLUSION ZONE)"),
        "c": ("wh_weather", "기상 확인(WEATHER CHECK)", [
            ("wind_speed", "- 순간풍속(WIND SPEED):", "m/s", "순간풍속(m/s)"),
            ("mewp_swl", "- 작업대 정격하중(MEWP SWL):", "kg", "작업대 정격하중(kg)")]),
        "d": ("wh_height", "작업높이(HEIGHT OF WORK):", ("work_height", "미터(M)", "작업높이(미터)")),
        "required": ["work_height"],
    },
    "lifting": {
        "label": "중량물인양", "title": "기타위험(중량물인양)작업 허가서", "title_en": "HEAVY LIFTING PERMIT",
        "heads": [("overhead_crane", "천장크레인(OVERHEAD CRANE)"), ("mobile_crane", "이동식 크레인(MOBILE CRANE)"),
                  ("tandem", "공동 인양(TANDEM LIFT)")],
        "col1": [("hl_plan", "인양계획서 작성(LIFTING PLAN)"), ("hl_director", "작업지휘자 지정(LIFT DIRECTOR)"),
                 ("hl_signal", "신호수 배치(SIGNALER)"), ("hl_crane_check", "크레인 작업 전 점검(CRANE CHECK)"),
                 ("hl_latch", "훅 해지장치(HOOK LATCH)")],
        "col2": [("hl_rigging", "줄걸이 용구 점검(RIGGING GEAR)"), ("hl_lug", "인양점·러그 확인(LIFTING LUG)"),
                 ("hl_tagline", "유도로프(TAG LINE)"), ("hl_no_entry", "인양물 하부 출입금지(NO ENTRY)"),
                 ("hl_route", "이동경로 확인(ROUTE CLEAR)")],
        "a": ("hl_no_person", "블록 내부 잔류인원 확인(NO PERSON INSIDE)"),
        "c": ("hl_load_check", "하중 확인(LOAD CHECK)", [
            ("load_weight", "- 인양물 중량(LOAD WEIGHT):", "톤(T)", "인양물 중량(톤)"),
            ("crane_swl", "- 크레인 정격하중(CRANE SWL):", "톤(T)", "크레인 정격하중(톤)")]),
        "d": ("hl_height", "최대 인양높이(LIFT HEIGHT):", ("lift_height", "미터(M)", "최대 인양높이(미터)")),
        "required": ["load_weight", "crane_swl"],
    },
    "loto": {
        "label": "정전·LOTO", "title": "기타위험(정전·LOTO)작업 허가서", "title_en": "ELECTRICAL ISOLATION / LOTO PERMIT",
        "heads": [("low_voltage", "저압(LOW VOLTAGE)"), ("high_voltage", "고압(HIGH VOLTAGE)"),
                  ("crane_power", "크레인 전원(CRANE POWER)")],
        "col1": [("lt_drawing", "전원 도면 확인(SINGLE LINE CHECK)"), ("lt_isolate", "차단·단로기 개방(ISOLATION)"),
                 ("lt_lock_tag", "잠금장치·꼬리표(LOCK & TAG)"), ("lt_discharge", "잔류전하 방전(DISCHARGE)"),
                 ("lt_test", "검전기 확인(VOLTAGE TEST)")],
        "col2": [("lt_earth", "단락 접지(SHORT EARTHING)"), ("lt_backfeed", "예비전원·역송전 차단(BACKFEED)"),
                 ("lt_notice", "운전부서 정지 통보(OPERATOR NOTICE)"), ("lt_personal", "작업자별 개인 잠금(PERSONAL LOCK)"),
                 ("lt_ppe", "절연용 보호구(INSULATED PPE)")],
        "a": ("lt_no_restart", "재가동 금지 표지(NO RESTART SIGN)"),
        "c": ("lt_source", "전원 정보(POWER SOURCE)", [
            ("rated_voltage", "- 정격전압(RATED VOLTAGE):", "볼트(V)", "정격전압(V)"),
            ("lock_count", "- 잠금 개수(LOCKS APPLIED):", "개(EA)", "잠금 개수(개)")]),
        "d": ("lt_zero", "무전압 측정값(MEASURED):", ("measured_voltage", "볼트(V)", "무전압 측정값(V)")),
        "required": ["rated_voltage"],
    },
}


def ko(label):
    """Korean part of a printed item label: '가연물 제거·방호(COMBUSTIBLES)' -> '가연물 제거·방호'."""
    return label.split("(")[0].strip()


def checks(kind):
    """(key, item text, group) for every ticked item of this kind's 추가정보 block."""
    k = KINDS[kind]
    items = list(k["heads"]) + list(k["col1"]) + list(k["col2"]) + [k["a"], k["c"][:2], k["d"][:2]]
    return [(key, ko(label), "추가정보") for key, label in items]


def values(kind):
    """(key, start regex, end regex, name) for every value line of this kind."""
    k = KINDS[kind]
    out = [(key, label, unit, name) for key, label, unit, name in k["c"][2]]
    dk, dlabel, (vkey, unit, name) = k["d"]
    out.append((vkey, dlabel, unit, name))
    flex = lambda s: r"\s*".join(re.escape(ch) for ch in s if not ch.isspace())
    return [(key, flex(label.lstrip("- ")), flex(unit), name) for key, label, unit, name in out]
