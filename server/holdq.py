"""판정보류 쌍의 질문 생성·배정 (design §8.3): what a pair's 판정보류 reasons (E1: a fact missing) still lack — also when
another reason of the same pair raised it higher, or the reason is kept on the documents' word (pairs.floor) — as
questions to the foreman of each side about his own work — the side that cuts power or gas is asked about the equipment and its restoring, the side
that goes in about its own ventilation and entry. No foreman is asked to confirm the other side's work or its
completion. A fact several pairs need is asked once. No model: the rule's own gaps decide what is asked.

croScan sends nothing: each foreman's questions are a 문안 to copy into the yard's existing contacts. Showing it
costs nothing. The manager marks a question 「전달함」 (and later 「응답 받음」); unmarked it stays 「미전달」. A mark is
a fact and is always kept. Sent the first time, the ask is counted on the permit's own question budget (design §8.3:
no budget of its own) through the review session of the permit's submission; when that review has no asks left or
was closed, the mark still stands and says so (「반장 대화 질문 한도 밖」 / 「검토 마감 뒤 전달」) — nothing is
counted anywhere else. A question is tied to the work as written now (a fingerprint of the document): when the work
changes it is a new question, and what was marked before is shown as history, not carried over. Kept in
holdq.sqlite3 next to the reviews.
"""
import contextlib
import hashlib
import json
import re
import sqlite3
import threading
import time

from . import qa, safety, store, submissions

DB = qa.DATA / "holdq.sqlite3"
STATES = ("미전달", "전달함", "응답 받음")
NEXT = {"미전달": ("전달함",), "전달함": ("응답 받음", "미전달"), "응답 받음": ("전달함",)}
_LOCK = threading.Lock()
# (rule) -> ((fact, what the cause side is asked of its own work), (fact, what the exposed side is asked of its own))
RULE_SIDE = {
    "FIRE": (("spark_reach", "화기 작업의 불티가 닿는 범위와 불티 차단 계획"), ("solvent_end", "도장·세정이 끝나는 시각과 건조·환기 계획")),
    # interview 「감시 기능 구분」: the confined-space watcher and the fire watcher are not one person by default
    "CONF_HOT": (("hot_point", "화기 작업 위치와 가장 가까운 개구부까지의 거리, 화재감시자"),
                 ("entry_plan", "밀폐 공간 진입 시간대와 출입 개구부 위치, 밀폐 감시인이 화재감시자를 겸하는지")),
    # 자료 N2 MT11·P5 L172: another entry sharing the same fan or air line
    "CONF_GAS": (("gas_line", "가스 공급 계통(배관 번호)과 차단·복구 계획"), ("vent_entry", "사용하는 환기설비와 진입 계획, 다른 진입 작업과 환기·송기 설비를 나눠 쓰는지")),
    "LOAD_OVER": (("lift_route", "인양 경로와 인양 시각"), ("work_zone", "작업 위치·시간과 인원 배치")),
    # 자료 MT12(p221): the end of the inside work and everyone's leaving are two events
    "TARGET_OCCUPIED": (("lift_time", "블록 인양 예정 시각"), ("exit_time", "블록 안 작업이 끝나는 시각과 마지막 인원이 나오는 시각(정리·인계 포함, 다르면 각각)")),
    "CRANE_LOTO": (("crane_repair", "크레인 정비 범위와 정비 후 복구·인계 예정 시각"), ("crane_need", "그 크레인을 쓰려는 시각과 대체 크레인 계획")),
    "POWER_LOTO": (("power_cut", "정전 범위(분기)와 복구 예정 시각"), ("power_need", "그 분기에서 쓰는 장비와 대체 전원 계획")),
    "DROP_BELOW": (("upper_work", "상부 작업의 실제 높이·시간, 아래로 뚫린 곳(양중구·맨홀·홀)과 덮개, 낙하물 방지 계획"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "PRESSURE": (("test_zone", "시험 매체(공기·질소·물)·압력·시험 구역과 시각, 호스 고정 방법"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "RADIATION": (("rt_zone", "방사선 통제구역 범위와 촬영 시각"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "VEHICLE": (("route_time", "운반 경로와 통과 시각"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "CRANE_SHARE": (("crane_time", "크레인 사용 시각"), ("crane_time", "크레인 사용 시각")),
    "CRANE_CROSS": (("crane_travel", "크레인 주행 구간과 시각"), ("crane_travel", "크레인 주행 구간과 시각")),
    # 사고사례집 C03·C22: what the block rests on and whether a jack adjusts it
    "SUPPORT": (("cut_member", "절단·해체·받침 조정(잭)하는 부재와 받침 계획, 블록이 무엇으로 받쳐 있는지"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "ACCESS": (("lift_time", "블록 인양 예정 시각과 경로"), ("entry_watch", "밀폐 출입구와 감시인 위치")),
    "HOT_PERSON": (("shield", "화기 작업의 차광·차폐 계획과 불티·흄이 닿는 범위(바로 옆 칼럼과의 실제 거리)"), ("work_zone", "작업 위치·시간과 인원 배치")),
    # 2026-10-31 자료 412쪽 대조로 더한 규칙
    "VENT_LOTO": (("power_func", "차단 범위에 물린 환기팬·송기·조명·연락 설비와 복구 시각"), ("vent_entry", "사용하는 환기설비와 진입 계획")),
    "CRANE_TEST": (("crane_test", "복구·시험운전 시각과 주행 구간"), ("upper_pos", "작업 위치(거더·레일·블록 상부)와 높이, 그 시간 인원 배치")),
    "SHARED_LOTO": (("lock_release", "본인 잠금 해제·복구 예정 시각과 다른 팀 잠금 확인 방법"), ("lock_release", "본인 잠금 해제·복구 예정 시각과 다른 팀 잠금 확인 방법")),
    "OTHER_CRANE_REPAIR": (("crane_travel", "크레인 주행 구간과 시각"), ("repair_pos", "수리 위치(지상·거더)와 같은 주행로 다른 크레인 운행 정지 요청 여부")),
    "HOT_PANEL": (("spark_reach", "화기 작업의 불티가 닿는 범위와 불티 차단 계획"), ("panel_cover", "반을 여는 시간과 반 덮개·복구 전 내부 확인 계획")),
    "FIRE_SOLID": (("spark_reach", "화기 작업의 불티가 닿는 범위와 불티 차단 계획"), ("combust_place", "가연물(포장재·목재·비닐·단열재)을 두는 위치·양")),
    "EGRESS_BLOCK": (("stage_place", "자재·대차·차광막을 두는 위치와 치우는 시각"), ("escape_route", "작업 구역의 대피 통로·소화기 위치")),
    "OVERHEAD_WORK": (("upper_work", "상부 작업의 실제 높이·시간과 낙하물 방지 계획"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "CART": (("route_time", "운반 경로와 통과 시각"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "CABLE_RUN": (("route_time", "운반 경로와 통과 시각"), ("cable_route", "용접 케이블 배선 경로와 보호 덮개")),
    "NOISE_SIGNAL": (("noise_time", "소음 작업(연삭·가우징) 시간"), ("signal_way", "인양 신호 방법(무전·수신호)과 신호수")),
    "WELD_RETURN": (("return_clamp", "용접 귀환(어스) 클램프 위치"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "LIFT_LINE": (("lift_time", "블록 인양 예정 시각"), ("line_release", "그 블록에 연결한 덕트·호스·케이블과 해제 시각")),
    "GRIND_FLY": (("grind_dir", "연삭 방향과 차폐 계획"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "CONF_PAINT": (("paint_end", "도장·세정 위치와 끝·환기 완료 시각"), ("entry_plan", "밀폐 공간 진입 시간대와 출입 개구부 위치")),
    "MEWP_OVER": (("mewp_pos", "고소작업대 위치와 붐 회전 범위"), ("work_zone", "작업 위치·시간과 인원 배치")),
    # 사고사례집 C16: what is on the other side of the plate (격벽 너머)
    "FIRE_SPREAD": (("combust_near", "화기 지점 주변과 판 반대편(격벽·이면)의 보온재·가연물, 방화포·이면 감시 계획"), ("work_zone", "작업 위치·시간과 인원 배치")),
    "FIRE_GAS": (("spark_reach", "화기 작업의 불티가 닿는 범위와 불티 차단 계획"),
                 ("gas_handle", "가스 용기·호스를 다루는 위치·시각과 가스 종류(LPG·아세틸렌 등), 누출 점검·환기 계획")),
    "HELD_FIT": (("hold_time", "크레인이 부재를 잡고 있는 시간과 신호 방법"), ("fit_order", "취부·가고정 순서와 크레인 조작 요청 방법")),
    "EQUIP_IGNITION": (("equip_kind", "쓰는 고소작업대·전기기기 종류(방폭형인지)와 시간"), ("solvent_end", "도장·세정이 끝나는 시각과 건조·환기 계획")),
}
# a residual left by the cause: what the first side is asked of its own end, what the later side of its own start
# (rules added 2026-10-31; the older ones keep the generic end_residual / start_check)
RULE_SEQ = {
    "DROP_BELOW": ("loose_end", "작업이 끝나는 예정 시각과 분리물·잔존물 회수·고정 확인 방법"),
    "OVERHEAD_WORK": ("loose_end", "작업이 끝나는 예정 시각과 분리물·잔존물 회수·고정 확인 방법"),
    "SUPPORT": ("support_end", "절단·해체가 끝나는 예정 시각과 임시 지지·하중 이전 확인 방법"),
    "CRANE_LOTO": ("restore_end", "정비 완료·복구·시험운전·인계 예정 시각과 인계받는 사람"),
    "POWER_LOTO": ("restore_end", "정비 완료·복구·시험운전·인계 예정 시각과 인계받는 사람"),
    "ACCESS": ("clear_end", "작업이 끝나는 예정 시각과 적치물·잔해를 치우는 계획"),
    "EGRESS_BLOCK": ("clear_end", "작업이 끝나는 예정 시각과 적치물·잔해를 치우는 계획"),
    "HOT_PERSON": ("hot_end", "화기 종료 시각과 그 면의 냉각·불씨·흄 확인 방법"),
    "FIRE_SOLID": ("hot_end", "화기 종료 시각과 그 면의 냉각·불씨·흄 확인 방법"),
    "HOT_PANEL": ("hot_end", "화기 종료 시각과 그 면의 냉각·불씨·흄 확인 방법"),
    "FIRE_SPREAD": ("hot_end", "화기 종료 시각과 그 면의 냉각·불씨·흄 확인 방법"),
    "RADIATION": ("rt_end", "촬영 종료·선원 회수·측정 확인 예정 시각과 알릴 사람"),
    "CRANE_TEST": ("test_end", "복구 뒤 시험운전·주행 예정 시각과 구간, 알릴 사람"),
    "FIRE_GAS": ("hot_end", "화기 종료 시각과 그 면의 냉각·불씨·흄 확인 방법"),
}
LATER = {"CRANE_LOTO": ("use_check", "그 설비를 쓰기 전에 정비 인계를 확인하는 방법"),
         "POWER_LOTO": ("use_check", "그 설비를 쓰기 전에 정비 인계를 확인하는 방법"),
         "HOT_PERSON": ("touch_check", "시작 전 그 면의 냉각·불씨 확인 방법(청소라면 분진 성상·포집 계획)"),
         "HOT_PANEL": ("panel_check", "복구 전 반 내부 불티·이물 확인 시각"),
         "FIRE_SOLID": ("clear_check", "시작 전 주변 가연물을 치웠는지·불씨 확인 방법")}
GENERIC = {"time": "작업 시작·끝 예정 시각", "place": "실제 작업 위치(BAY·칼럼·블록 번호)", "workers": "작업 인원 수",
           "move_time": "크레인 실제 이동 예정 시각", "end_residual": "작업이 끝나는 예정 시각과 끝난 뒤 남는 것(잔불·가스·잔압·자재·잔류 인원)의 정리 계획(개구부 덮개·난간·통로 복구 포함) · 남은 작업이 있어 다시 들어올 계획",
           "start_check": "작업 시작 예정 시각과 시작 전에 하는 본인 작업의 확인 절차",
           "end_time": "작업이 실제로 끝나는 예정 시각(늦어질 수 있는지)", "height": "작업 위치의 바닥 기준 높이(m)와 그 아래 작업·통행",
           "position": "블록 안·위·옆 중 실제 작업 위치와 높이", "workers_zero": "그 시간 실제로 작업 공간에 들어가는 인원(서류에는 0명)",
           "time_rev": "끝나는 시각이 시작보다 이른데, 다음 날 끝나는 것인지 적을 때 잘못 쓴 것인지",
           "solvent_kind": "사용하는 도료·세정제 이름과 수성·용제형 여부",
           "gas_kind": "다루는 가스 용기의 가스 종류(LPG·아세틸렌 같은 가연성인지)와 위치·시각",
           "lift_support": "인양할 블록이 다른 블록·구조를 받치고 있는지와 인양 전 받침을 옮기는 계획",
           "exhaust_power": "국소배기·집진기의 전원(분전반 번호)",
           "light_power": "상부 작업 조명의 전원(분전반 번호)",
           "lift_outline": "인양물의 실제 크기(폭·길이)·매단 높이와 회전·흔들림 범위, 그 아래를 지나는 시각"}


# how a first 「전달함」 was counted -> what the screen says of it (None: counted in the review, or no review)
FLAGS = {"over": "반장 대화 질문 한도 밖", "closed": "검토 마감 뒤 전달"}
# what a question depends on: the work's own facts — not the submission's revision (a checklist edit would make the
# same question new and push its 「전달함」 into history: 최종 검토 2026-11-01), nor who wrote it
FP_KEYS = ("title", "detail", "place", "route", "target", "windows", "move", "workers", "kind", "height", "equipment", "materials", "hazards")


def fingerprint(d):
    """the work as written now (what its questions depend on): a short hash of its document's own facts"""
    return hashlib.sha256(json.dumps({k: d.get(k) for k in FP_KEYS}, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:10]


class HoldError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


@contextlib.contextmanager
def _db():
    qa.DATA.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=5, isolation_level=None)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("CREATE TABLE IF NOT EXISTS marks (key TEXT PRIMARY KEY, day TEXT, doc TEXT, state TEXT, counted TEXT, at REAL)")
        yield c
    finally:
        if c.in_transaction:
            c.rollback()
        c.close()


# an unknown said in so many words (a height, inside or not, a reversed time …): asked whatever the reason's E — a
# stronger reason of the same pair does not answer it (Codex 8)
EXPLICIT = ("평면 경로", "방사선은 유해위험요소 칸에만", "정전 반장 답: 환기·조명 영향 없음", "서류상 인원 0", "작업 높이", "블록 안·위인지", "블록 위·안인지", "받침·지그 해체", "시간 역전", "칼럼 범위가 큰 번호부터",
            "시험운전·주행 계획이", "블록 상부 작업: 시험 주행", "반을 열어 두는지", "귀환 클램프 위치", "크레인이 잡은 그 부재",
            # 2026-11-01 최종 검토로 더한 미확인
            "가스 용기의 가스 종류", "반입·반출 물품이", "인양할 블록이", "국소배기·집진기가 물렸는지", "상부 작업 조명이 물렸는지", "시험 주행 구간·훅 아래")


def _explicit(g):
    return any(x in g for x in EXPLICIT)


def _asks(r, docs, only_explicit=False):
    """one 판정보류 reason -> [(doc id, fact, text)]: each gap the rule left, asked of the side whose own work it is;
    only_explicit: the unknowns named in so many words only (for a reason that is not 판정보류)"""
    A, B = r["cause"], r["exposed"]
    side = RULE_SIDE.get(r["rule"], (("work_zone", "작업 위치·시간과 인원 배치"),) * 2)
    if r["rule"] == "ACCESS":
        tags = set((docs.get(A) or {}).get("_tags") or ())
        kind = r.get("cause_kind") or ""
        cause = (("route_time", "운반 경로와 통과 시각") if kind in ("VEHICLE", "CART") else
                 ("loose_end", "분리물·잔재가 떨어지거나 놓이는 곳과 회수 계획") if kind in ("DROP", "SEP") else
                 ("stage_place", "자재·대차를 두는 위치와 치우는 시각") if kind in ("STAGE", "STAGE_SOFT") else side[0])
        side = (cause, side[1])
    out = []
    for g in r.get("gaps") or []:
        if only_explicit and not _explicit(g):
            continue
        if g.startswith("경로가 생기려면"):
            out += [(A, *side[0]), (B, *side[1])]
        elif g.startswith("한쪽의 작업 시간이 없어"):
            out += [(i, "time", GENERIC["time"]) for i in (A, B) if not docs[i].get("windows")]
        elif g.startswith("작업 시간은 겹치지 않지만"):
            first = A if (r.get("sequence") or {}).get("first", "A") == "A" else B
            later = B if first == A else A
            fe = RULE_SEQ.get(r["rule"], ("end_residual", GENERIC["end_residual"]))
            ls = LATER.get(r["rule"], ("start_check", GENERIC["start_check"]))
            out += [(first, *fe), (later, *ls)]
        elif g.startswith("앞 작업이 끝나는 시각에 바로"):
            first = A if (r.get("sequence") or {}).get("first", "A") == "A" else B
            later = B if first == A else A
            out += [(first, "end_time", GENERIC["end_time"]), (later, "start_check", GENERIC["start_check"])]
        elif g.startswith("위험을 받는 작업의 인원 수"):
            out.append((B, "workers", GENERIC["workers"]))
        elif g.startswith("서류상 인원 0"):
            out.append((B, "workers_zero", GENERIC["workers_zero"]))
        elif g.startswith("평면 경로"):
            out.append((A, "lift_outline", GENERIC["lift_outline"]))
        elif g.startswith("작업 높이"):                       # 미확인, 2m 미만, 위아래 관계 미확인
            out.append((A, "height", GENERIC["height"]))
        elif g.startswith("가스 용기의 가스 종류"):
            out.append((B, "gas_kind", GENERIC["gas_kind"]))
        elif g.startswith("반입·반출 물품이"):
            out.append((A, *RULE_SIDE["EGRESS_BLOCK"][0]))
        elif g.startswith("인양할 블록이"):
            out += [(A, "lift_support", GENERIC["lift_support"]), (B, "work_zone", "작업 위치·시간과 인원 배치")]
        elif "국소배기·집진기가 물렸는지" in g:
            out += [(A, *side[0]), (B, "exhaust_power", GENERIC["exhaust_power"])]
        elif "상부 작업 조명이 물렸는지" in g:
            out += [(A, *side[0]), (B, "light_power", GENERIC["light_power"])]
        elif g.startswith("시험 주행 구간·훅 아래"):
            out += [(A, *side[0]), (B, "work_zone", "작업 위치·시간과 인원 배치")]
        elif g.startswith("블록 안·위인지") or g.startswith("블록 위·안인지") or g.startswith("받침·지그 해체"):
            out.append((B, "position", GENERIC["position"]))
        elif "시간 역전" in g:
            i = g.split(" 시간 역전")[0]
            out.append((i if i in docs else A, "time_rev", GENERIC["time_rev"]))
        elif "칼럼 범위가 큰 번호부터" in g:
            i = g.split(" 칼럼 범위가")[0]
            out.append((i if i in docs else A, "place", GENERIC["place"]))
        elif g.startswith("시험운전·주행 계획이"):
            out.append((A, *side[0]))
        elif g.startswith("블록 상부 작업: 시험 주행"):
            out.append((B, *side[1]))
        elif "방사선은 유해위험요소 칸에만" in g:
            out.append((A, *side[0]))
        elif g.startswith("정전 반장 답: 환기·조명 영향 없음"):
            out.append((B, *side[1]))
        elif g.startswith("반을 열어 두는지"):
            out.append((B, *side[1]))
        elif g.startswith("귀환 클램프 위치"):
            out.append((A, *side[0]))
        elif g.startswith("크레인이 잡은 그 부재"):
            out += [(A, *side[0]), (B, *side[1])]
        elif "이동 예정 시각이 허가 시간 밖" in g or "실제 이동 시각이 허가 시간 밖" in g:
            i = re.split(r"의 (?:이동 예정|실제 이동) 시각", g)[0]
            out.append((i if i in docs else A, "move_time", GENERIC["move_time"]))
        else:                                     # a place the rule could not settle
            nowhere = [i for i in (A, B) if not docs[i].get("spans")]
            out += [(i, "place", GENERIC["place"]) for i in nowhere] or [(A, *side[0]), (B, *side[1])]
    return out


def _no(d):
    return d.get("permit_no") or d["id"] if d["type"] == "permit" else d["id"]


def _who(d):
    return d.get("dept") or d.get("company") or ""


def build(det):
    """-> {date, docs: [{doc, no, title, who, kind, questions: [{key, fact, text, pairs, rules, state, flag, history}],
    message}], count} for every 판정보류 reason (E1) of the day's pairs, whatever the pair's top judgement; a fact
    needed by several pairs is one question"""
    D = safety.data()
    day = det.get("date") or D["date"]
    docs = {d["id"]: d for d in D["permits"] + D["plans"]}
    qs = {}
    for p in det["pairs"]:
        for r in p["reasons"]:
            # a paint job's solvent read from its name only (자료 10번 범위): its kind is asked, the alarm stays
            asks = [(e["doc"], "solvent_kind", GENERIC["solvent_kind"]) for e in r.get("evidence") or []
                    if "작업명에서 추정" in str(e.get("field"))]
            asks = _asks(r, docs, only_explicit=r.get("E") != 1) + asks
            for i, fact, text in asks:
                if i not in docs:
                    continue
                k = f"{day}:{i}:{fact}:{fingerprint(docs[i])}"
                q = qs.setdefault(k, {"key": k, "doc": i, "fact": fact, "text": text, "pairs": [], "rules": []})
                if p["key"] not in q["pairs"]:
                    q["pairs"].append(p["key"])
                if r["rule"] not in q["rules"]:
                    q["rules"].append(r["rule"])
    with _db() as c:
        marks = {r["key"]: dict(r) for r in c.execute("SELECT * FROM marks WHERE day=?", (day,))}
    out = {}
    for k, q in qs.items():
        m = marks.get(k) or {}
        q["state"] = m.get("state") or "미전달"
        q["flag"] = FLAGS.get(m.get("counted"))
        base = k.rsplit(":", 1)[0] + ":"                  # the same question about an earlier version of the work
        q["history"] = [{"state": x["state"], "at": x["at"], "flag": FLAGS.get(x["counted"])}
                        for kk, x in sorted(marks.items(), key=lambda kv: kv[1]["at"] or 0) if kk.startswith(base) and kk != k]
        out.setdefault(q["doc"], []).append(q)
    rows = []
    for i, items in out.items():
        d = docs[i]
        msg = [f"[작업 확인 요청] {_no(d)} {d.get('title') or ''}", "안전관리자 위험 검토에 필요한 본인 작업 정보입니다. 아는 만큼 알려 주세요."]
        msg += [f"{n}. {q['text']}" for n, q in enumerate(items, 1)]
        msg.append("다른 팀 작업에 대해서는 답하지 않으셔도 됩니다.")
        rows.append({"doc": i, "no": _no(d), "title": d.get("title") or "", "who": _who(d), "kind": d["type"], "questions": items,
                     "message": "\n".join(msg)})
    rows.sort(key=lambda x: (x["kind"] != "permit", x["doc"]))
    allq = [q for x in rows for q in x["questions"]]
    return {"date": day, "docs": rows, "count": {"questions": len(allq), **{s: sum(q["state"] == s for q in allq) for s in STATES}}}


def _session_of(permit_no, day):
    """the review session of the permit's latest submission for the day, or None"""
    s = submissions.latest(day).get(permit_no) if permit_no else None
    if not s:
        return None
    with store._db() as c:
        c.executescript(submissions._SCHEMA)
        r = c.execute("SELECT session_id FROM submissions WHERE id=?", (s["id"],)).fetchone()
    return r["session_id"] if r else None


def mark(det, key, state):
    """the manager marks a question: 미전달 → 전달함 → 응답 받음 (and back one step). Always kept. 전달함 the first
    time is counted on the permit's question budget; with none left, or the review closed, it is kept with that said
    (flag). -> the question as now"""
    if state not in STATES:
        raise HoldError(422, "알 수 없는 상태")
    cur = build(det)
    q = next((x for d in cur["docs"] for x in d["questions"] if x["key"] == key), None)
    if not q:
        raise HoldError(404, "그런 확인 질문이 없습니다 (판정이 바뀌었을 수 있습니다)")
    if state == q["state"]:
        return q
    if state not in NEXT[q["state"]]:
        raise HoldError(409, f"「{q['state']}」에서 「{state}」로 바로 바꿀 수 없습니다")
    d = safety.data()
    doc = next((x for x in d["permits"] + d["plans"] if x["id"] == q["doc"]), {})
    with _LOCK, _db() as c:
        row = c.execute("SELECT counted FROM marks WHERE key=?", (key,)).fetchone()
        counted = row["counted"] if row else None
        if state == "전달함" and not counted:
            counted = _charge(doc, cur["date"], q)
        c.execute("INSERT INTO marks (key, day, doc, state, counted, at) VALUES (?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET state=excluded.state, counted=excluded.counted, at=excluded.at",
                  (key, cur["date"], q["doc"], state, counted, time.time()))
    return {**q, "state": state, "flag": FLAGS.get(counted)}


def _charge(doc, day, q):
    """count one ask on the permit's own budget -> how it was counted: 'store' (in its review), 'over' (no asks
    left), 'closed' (the review was closed), 'none' (the work has no review: another company's plan, or a permit not
    submitted through croScan). Never refuses: the delivery happened; the flag says it was past the budget."""
    sid = _session_of(doc.get("permit_no"), day) if doc.get("type") == "permit" else None
    if not sid:
        return "none"
    try:
        b = store.budget(sid)
    except store.StoreError:
        return "none"
    if b["close"]:
        return "closed"
    try:
        store.issue(sid, f"HOLD:{q['fact']}@{q['doc']}", "question")
        return "store"
    except store.StoreError as e:
        return "closed" if e.code == "closed" else "over"
