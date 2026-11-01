"""쌍작업 위험탐지: every pair of one work day's documents (일상×비일상, 비일상×비일상), judged by rules only.

The researcher's six steps (조사자료 6절) are followed as they are:
  1. two different works            → one row per document, a document never pairs with itself
  2. time overlap or residual risk  → the windows of the risky phase (the move of a lift, a scheduled crane step);
                                      after a work ends its residual risk (embers, vapour, gas, people still inside)
                                      lasts until someone confirms it is gone, so any later work the same day is
                                      kept as 「확인 필요」 — there is no time after which it is assumed gone
  3. the path that joins them       → a rule (pair_rules.json): fire, falling, load path, shared crane/power, gas …
  4. people / functions exposed     → the rule's cause side and exposed side, from what each document says
  5. cause → exposure → accident    → the rule's chain, filled with the two works, worded as what *can* happen
  6. unknown stays unknown          → no time, no place, no head count: 노출 1 (확인 필요), never 'safe'
Being in the same BAY, or even the same column address, is not a confirmed path: a path is confirmed by the same
block, a stated route, the same equipment, or a stated above/below relation; a shared address alone is 노출 2.

Priority: a forbidden combination (법·멘토: 도장×화기, 상하 동시, 인양물 아래, 정비 중 사용 …) confirmed by the
documents (노출 3) is 1순위; otherwise 강도 S × 노출 E: 6 and more 2순위, 3 to 5 3순위, below 3 not raised.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from . import safety

RULES_PATH = Path(__file__).with_name("pair_rules.json")
FIRE_REACH_M = 11          # 안전보건규칙 제241조의2: 화재감시자 반경 11m


@lru_cache(maxsize=1)
def rules():
    R = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    R["by_id"] = {r["id"]: r for r in R["rules"]}
    return R


HM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def _m(hm):
    h, m = map(int, hm.split(":"))
    return h * 60 + m


def _hm(m):
    return f"{(m // 60) % 24:02d}:{m % 60:02d}" + ("(+1)" if m >= 1440 else "")


def _win_m(w):
    a, b = _m(w["start"]), _m(w["end"])
    if w.get("days"):                                   # a work running on for days (dated plan): not cut at 23:59
        return (a, b + 1440 * w["days"])
    return (a, b + 1440) if w.get("next_day") or b <= a else (a, b)


# ---------------------------------------------------------------- what each work is (from what its document says)
DASH = str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "－": "-"})
SPARK = re.compile(r"용접|용단|가우징|절단|그라인더|그라인딩|사상|연삭|연마(?!지)|토치|브레이징|가열\s*교정|선상\s*가열|라인\s*히팅|가열\s*작업")
SPARK_TOOL = re.compile(r"용접기|그라인더|토치|절단기|가우징|플라즈마")
# a thing named with 용접, not the act (자료 17번 범위: 용접재료 선정·불출은 용접 수행이 아님): '용접부 그라인딩' is still grinding
WELD_THING = re.compile(r"용접부|용접기|용접\s*재료|용접봉|용접\s*와이어|플럭스")
WELD_TOOL = re.compile(r"용접부|용접기")              # the v1 reading: a welding-material word alone is still read as before
# the one exception (자료 84쪽 17번 「불출·포장 확인을 용접 수행으로 확대하지 않음」): issuing, receiving or storing welding
# material is no hot work; carrying it (용접봉 운반) or any other wording keeps the v1 reading
ISSUE = re.compile(r"불출|지급|수령|보관|선정|재고|반납")
NOT_ACTION = re.compile(r"확인|여부|점검|검사|탐상|측정|판독|금지|표지|준비|계획|없음|미사용|제외|보고|기록|관찰|모니터링")
SOLVENT = re.compile(r"유기용제|희석제|시너|신너|신나|thinner|세정제|솔벤트|용제형|인화성", re.I)
PAINT_JOB = re.compile(r"도장|세정|탈지|프라이머|코팅|터치업|페인트|도료|에폭시|래커")
NOT_FLAM = re.compile(r"수성|불연|무용제|비인화")
NEGATED = re.compile(r"미사용|사용 안|사용하지|없음|제외|금지")
UPKEEP = re.compile(r"점검|정비|정리|보관|수리|교체|판독")
SYSTEM_ID = re.compile(r"\b[A-Z]{1,3}-\d{1,3}\b(?![-\d])")
CRANE_ID = re.compile(r"OH-\d+-\d+")
PANEL_ID = re.compile(r"(?:MCC|DB|PNL|LP|PP)-\d+")
# a block number as the yard writes it: E41P, B11, F31, E170(A), and B-01 only with 「블록」 (실물 허가서·양식, others 감사);
# not a crane (OH-21-03), a panel (MCC-4), a pipe (P-12), a gas or steel grade (CO2, AH36) or a book ID (R42-01)
BLOCK_ID = re.compile(r"(?<![A-Za-z0-9-])[A-Z]\d{2,3}[A-Z]?(?:\([A-Z]\))?(?![A-Za-z0-9]|-\d|\s*(?:축|칼럼|밸브|번\s*밸브|열|라인|펌프))"
                      r"|(?<![A-Za-z0-9-])[A-Z]-\d{2}(?=\s*블록)")
BLOCK_FIELD = re.compile(r"(?<![A-Za-z0-9-])[A-Z]{1,2}-?\d{2,3}[A-Z]?(?:\([A-Z]\))?(?![A-Za-z0-9])")      # the 대상ID field: 「B-01」 alone too
NOT_BLOCK = re.compile(r"^(?:AH|DH|EH|FH)\d|^(?:SS|SM|SUS)\d")
SEPARATE = re.compile(r"절단|해체|제거|분리|러그")
PRESSURE = re.compile(r"압력시험|압력 시험|가압|수압|기밀시험|에어 ?테스트|리크 ?테스트|누설\s*시험")
RADIATION = re.compile(r"방사선|선원|이리듐|감마선|(?<![A-Za-z])RT(?![A-Za-z])")
# a radiography phrase is the work even with 「검사」 in it (방사선투과검사), but not its reading or report
RAD_NOT = re.compile(r"판독|결과|기록|보고|계획|정리|없음|미사용|제외|금지|여부|표지")
# vehicles (augment li_vehicle 「차량|트레일러|트랜스포터」와 맞춤, 자료 N4-MT14·MT-TRANSPORT); a hand cart is CART, not a vehicle
VEHICLE = re.compile(r"차량\s*(?:으로|로)?\s*(?:[가-힣]+\s*)?(?:운반|인계|이동|통행|진입|하역|운행|반입|반출)|(?:운반|이송|수송|하역)\s*차량|지게차|운반차|트럭|카고|화물차|트레일러|트랜스포터|(?<![A-Za-z])T/?P(?![A-Za-z])|SPMT|셀프\s*프로펠|스키드\s*로더|이동식\s*크레인|(?<!수동)(?<!수동 )(?<!손)(?<!핸드)대차")
CART = re.compile(r"수동\s*대차|손수레|수레|핸드\s*카트|핸드\s*카|운반\s*카트|카트")
MEWP = re.compile(r"고소작업대|고소작업차|MEWP|시저리프트|붐리프트|스카이|곤돌라")
OFF_FLOOR = re.compile(r"사무동|사무실|검사실|회의실|공장 밖")
INERT = re.compile(r"아르곤|TIG|퍼지|질소|불활성\s*가스|" + r"(?:CO2|CO₂|이산화탄소)\s*(?:가스)?\s*(?:로|를|을)?\s*(?:주입|치환|봉입|투입)")            # 「N2」 is the book's work number, never nitrogen (자료 2.1)
# general combustibles (자료 R42-18·34 IGNITION): solid ones only make a fire, never an explosion
COMBUST = re.compile(r"포장재|골판지|폐지|종이|박스|목재|합판|각재|비닐|스티로폼|우레탄|천막|기름\s*걸레|폐기물|보온재|단열재|방수포")
NOT_COMBUST = re.compile(r"미네랄\s*울|글라스\s*울|세라믹|불연")       # 난연(flame-retardant) still burns: not here
# flammable gas or mist handled by a work (interview 00:21: 화기 옆 「미스트 … 가스를 취급」): a cylinder changed, carried
# or connected, not oxygen (that is hot_oxygen)
FLAM_GAS = re.compile(r"LPG|프로판|부탄|아세틸렌|수소\s*가스|(?<!비)가연성\s*가스|오일\s*미스트")
GAS_CYL = re.compile(r"가스\s*(?:용기|실린더|봄베|통)|봄베")
NONFLAM = re.compile(r"산소|아르곤|질소|불활성|비가연|탄산|CO2|CO₂|이산화탄소|헬륨|압축\s*공기")
GAS_HANDLE = re.compile(r"교체|운반|연결|취급|충전|이송|하역|반입|반출|설치|분리|보관|적치|가동|발생|분무")
# what stays in a passage after it is put down (자료 R42-12·14·23·29·30·34·41-EGRESS)
STAGE = re.compile(r"적치|임시\s*보관|임시\s*적재|수거함|하역|자재\s*정리|잔재\s*정리|정차|차광막|방화포|통제대|펜스|바리케이드")
# overhead handling (자료 R42-09-DROP: 족장 설치·의장품 거치·케이블 트레이)
OVERHEAD = re.compile(r"설치|거치|족장|비계|트레이|의장|덕트")
ARC = re.compile(r"용접|가우징|플라즈마|아크|TIG|MIG|CO2|피복|FCAW|SMAW|브레이징")
GAS_CUT = re.compile(r"용단|가스\s*절단|산소\s*절단|토치|가열")
GRIND = re.compile(r"그라인더|그라인딩|사상|연삭|연마(?!지)|디스크|기계\s*절단|커터")
DEP = re.compile(r"환기|송기|배기|송풍|팬|조명|연락|통신|무전\s*중계|인터폰")
GIRDER = re.compile(r"거더|트롤리|크레인\s*상부|주행로|런웨이|레일")
TEST_RUN = re.compile(r"시험\s*운전|시운전|시험\s*주행|주행\s*시험|권상\s*시험|시험")      # a plain 「복구」 is not a test run
# what a power cut stops, by function (자료 p235·341: 기능별 결과) and an answer that says nothing else stops
DEP_AIR = re.compile(r"환기|송기|배기|송풍|팬")
DEP_LIGHT = re.compile(r"조명|작업등|투광등")
DEP_COMM = re.compile(r"연락|통신|무전\s*중계|인터폰")
DEP_NONE = re.compile(r"(?:환기|조명|다른\s*설비|함께\s*(?:멈추|꺼지)[^,.;]{0,6}|멈추는\s*(?:설비|것))[^,.;]{0,6}(?:영향\s*)?없|무관|해당\s*없")
ELEC_TOOL = re.compile(r"전동\s*공구|전동\s*드릴|임팩트\s*렌치|전동\s*그라인더|전기\s*공구|충전\s*공구|발전기")
PANEL_OPEN = re.compile(r"제어반|배전반|분전반|판넬|패널|반\s*(?:개방|열|문|내부)|결선|차단기|분기\s*(?:증설|공사)")
HELD = re.compile(r"크레인으로\s*잡|크레인에?\s*(?:걸|매단)|매단\s*채|잡은\s*채|들고\s*있는")
RETURN_PATH = re.compile(r"어스|귀환|접지\s*클램프|귀선")
LINES = re.compile(r"덕트|송기|호스|전선|케이블|용접선")
# goods brought in or out, tool boxes, returns (자료 R42-12·19·23-EGRESS): they may stand in a passage — not written that
# they do, so held to check, never a confirmed obstruction (Codex batch-1 #11)
STAGE_SOFT = re.compile(r"자재\s*반입|자재\s*반출|반입\s*대기|공구함|반납품")
# what a pulled or cut line does, by its kind (자료 p306 MV10: 연결선의 실제 기능·물질별 결과)
LINE_KIND = (("불활성가스 호스", r"아르곤|질소|불활성", "질식"), ("산소 호스", r"산소\s*(?:가스\s*)?호스", "산소 누출·연소 확대"),
             ("가연성 가스 호스", r"LPG|아세틸렌|프로판", "가스 누출·화재"), ("가스 호스", r"가스\s*호스", "가스 종류에 따라 질식·화재"),
             ("통신선", r"통신|무전|인터폰|랜\s*케이블", "연락 두절"), ("배기·집진 덕트", r"배기|집진|국소\s*배기", "흄 흡입"),
             ("송기·환기 덕트", r"덕트|송기|환기", "질식"), ("전선·케이블", r"전선|케이블|용접선", "감전"), ("호스", r"호스", "당김·끼임"))
# what is left of a hot work and handled after it at the same place (자료 R42-23·33-HOT: 잔재·청소·수거)
RESIDUE = re.compile(r"잔재|청소|수거|스크랩|슬래그|분진|정리")
LOCAL_EXH = re.compile(r"국소\s*배기|집진|배기\s*팬|흄\s*(?:추출|흡입|포집)")
SUPPORT_CUT = re.compile(r"받침|지그|쐐기|서포트|지지대|버팀")
# changing what holds a block up (사고사례집 C02·C03·C22: 받친 블록 아래 작업): jacking, adjusting, moving supports
SUPPORT_ADJ = re.compile(r"(?:잭|유압\s*램|서포트|받침|트레슬|지지대|버팀)[^,·/]{0,8}(?:조정|해체|교체|제거|이동|올림|내림|높이|업)|높이\s*조정|잭\s*업")
TOOL_UP = re.compile(r"그라인더|공구|볼트|정비|교체|와이어|취부|조립|운반|반입|연마")
NIGHT_OK = re.compile(r"다음\s*날|익일|야간|자정")
# a route written as a range of columns: '03→08칼럼', '03칼럼에서 08칼럼까지', '06↔16' (자료 일상 14·21·26·33)
ROUTE_COLS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:칼럼|축)?\s*(?:→|->|↔|에서)\s*(\d{1,2})\s*(?:칼럼|축)")
# a route through several points ('04→12→09→04축'): every number on it (자료 일상 30 순회)
ROUTE_CHAIN = re.compile(r"(?<!\d)\d{1,2}(?!\d|\s*BAY)(?:\s*(?:칼럼|축))?(?:\s*(?:→|->|↔|에서)\s*\d{1,2}(?!\d|\s*BAY)(?:\s*(?:칼럼|축|까지))?)+")


def _tokens(value):
    """A field cut into short phrases: '크레인·체인블록으로 부재 취부 / 가용접·치수 확인' → each part on its own."""
    value = re.sub(r"(?<![A-Za-z])T/P(?![A-Za-z])", "TP", value or "")       # 트랜스포터 「T/P」 is one word, not two
    return [t.strip() for t in re.split(r"[/,;·]|\s및\s", value) if t.strip()]


# one phrase cut into its acts (Codex A8): a check or a no qualifies the act it is written with, not the whole phrase.
# '가용접 후 치수 확인' → '가용접' | '치수 확인'; '절단 없이 볼트 해체' → '절단 없이' | '볼트 해체' (the no stays with its act)
ACT_SPLIT = re.compile(r"\s*(?:→|->|=>|\+|&)\s*|(?<=[가-힣])\s*(?:하고|한\s*(?:후|뒤|다음)|후|뒤|다음|이후)\s+|\s+(?:그리고|또는|이후)\s+"
                       r"|(?<=없이|않고|말고|대신)\s+")


ACT_NO = re.compile(r"없이|않고|말고|대신|않음|안\s*함|하지\s*않")      # a no written with the act itself


def _acts(t):
    return [a.strip() for a in ACT_SPLIT.split(t) if a and a.strip()]


def _says_no(a):
    """a no written with the act in plain words: 「안 씀」「안 써요」「쓰지 않음」"""
    return re.search(r"안\s*(?:씀|써|쓰|함|해)|않|없음|없다", a) is not None


def _dep_fn(text):
    """the functions a power cut takes away, as written: {air, light, comm}"""
    return {k for k, rx in (("air", DEP_AIR), ("light", DEP_LIGHT), ("comm", DEP_COMM)) if rx.search(text or "")}


def _heights(text, field=False):
    """(lowest, highest) m from '지상 ~ 블록 상부 3.0m', '최고 4.8m', '4.5m', or (None, None); a plan's own 작업높이
    field '지상 작업' (field=True) is a known ground height (0), not an unknown one."""
    hs = [float(x) for x in re.findall(r"(\d+(?:\.\d+)?)\s*m\b", text or "")]
    if not hs:
        ground = field and re.search(r"지상|바닥", text or "") and not re.search(r"상부|갑판|높", text or "")
        return (0.0, 0.0) if ground else (None, None)
    low = 0.0 if re.search(r"지상|최고|~", text) else min(hs)
    return low, max(hs)


def profile(d):
    """Tags with the field and words they come from: {tag: [(field, value), …]}, plus ids, heights, place and time."""
    tags, ids = {}, {"crane_use": set(), "crane_loto": set(), "power_use": set(), "power_loto": set(), "blocks": set(), "systems": set()}

    def tag(t, field, value):
        if (field, value) not in tags.setdefault(t, []):
            tags[t].append((field, value))

    if d["type"] == "permit":
        checks = [v["name"] for v in d["_fields"].values() if v["type"] == "check" and v["value"]]
        rec = {r["item"]: r.get("value") or "" for r in d["_records"]}
        fields = [("작업명", d["title"]), ("작업 상세", d["detail"]), ("유해위험요소", d["hazards"]), ("위치(답변 반영)", d["place"]),
                  ("이동 경로(답변)", d["route"])] + [(f"답변 {k}", v) for k, v in rec.items() if v]

        if d["kind"] == "hot":
            tag("SPARK", "허가서 종류", "화기작업 허가서")
        for c in checks:
            if re.search(r"용접|용단|가우징", c):
                tag("SPARK", "체크 항목", c)
        if d["kind"] == "confined" or "밀폐구역출입" in checks:
            tag("CONFINED", "허가서 종류" if d["kind"] == "confined" else "체크 항목", "밀폐공간 허가서" if d["kind"] == "confined" else "밀폐구역출입")
        if d["kind"] == "lifting":
            tag("LIFT", "허가서 종류", "중량물인양 허가서")
        if "고소작업대" in checks:
            tag("MEWP", "체크 항목", "고소작업대")
        if "아르곤가스 사용" in checks:
            tag("INERT", "체크 항목", "아르곤가스 사용")
        # the confined form's 「압력사용」 box or a test pressure written: a pressure test is part of the work (실물 양식)
        tp = next((v["value"] for v in d["_fields"].values() if v.get("key") == "test_pressure" and v.get("value")), "")
        if any(c.startswith("압력사용") for c in checks) or tp:
            tag("PRESSURE", "체크 항목", "압력사용" + (f" {tp}" if tp else ""))
        lows, highs = _heights(" ".join([rec.get("L3", ""), d["hazards"], d["detail"]]))
        title = d["title"]
        # 정전: what the foreman said stops with the power (LO3·D4·X5): 환기·조명이 물림 / 모름·빈칸 / 다른 것만
        said = [rec.get(k, "") for k in ("LO3", "D4", "X5") if rec.get(k)]
        dep_said = [s for s in said + [d["title"], d["detail"]] if (DEP.search(s) or DEP_LIGHT.search(s)) and not NEGATED.search(s) and not DEP_NONE.search(s)]
        # times alone or a general answer do not say nothing else stops: only an explicit no-relation answer is 「no」 (p235·341)
        dep = "yes" if dep_said else "no" if any(DEP_NONE.search(s) for s in said) else "unknown"
        girder = [s for s in (rec.get("LO4", ""), d["place"], d["title"], d["detail"]) if GIRDER.search(s or "")]
        test_run = d["kind"] == "loto" and bool(TEST_RUN.search(" ".join([rec.get("LO3", ""), d["title"], d["detail"]])))
        test_drive = d["kind"] == "loto" and any(re.search(r"시험\s*운전|시운전|시험\s*주행|주행\s*시험|권상\s*시험", a)
                                                 and not NEGATED.search(a) and not ACT_NO.search(a) and not _says_no(a)
                                                 for s in (rec.get("LO3", ""), d["title"], d["detail"]) for t in _tokens(s) for a in _acts(t))
        dep_fn = _dep_fn(" ".join(dep_said))
    else:
        it = {i["label"]: i["value"] for i in d["_items"]}
        steps = [(k, v) for k, v in it.items() if re.fullmatch(r"\d+단계", k)]
        fields = [("작업명", it.get("작업명", "")), ("작업장비", it.get("작업장비", "")), ("사용물질", it.get("사용물질", ""))] + steps
        upkeep = UPKEEP.search(it.get("작업명", "")) and not SPARK.search(WELD_TOOL.sub("", it.get("작업명", "")))
        if not upkeep and any(SPARK_TOOL.search(t) and not NEGATED.search(t) for t in _tokens(it.get("작업장비", ""))):
            tag("SPARK", "작업장비", it.get("작업장비", ""))
        lows, highs = _heights(it.get("작업높이", ""), field=True)
        hv = it.get("작업높이", "")
        title = it.get("작업명", "") or d["title"]
        dep, test_run, dep_fn, test_drive = "no", False, set(), False
        girder = [v for _, v in [("작업명", title)] + steps if GIRDER.search(v or "")]
    fields = [(f, re.sub(r"[ \t]+", " ", (v or "").translate(DASH))) for f, v in fields if v]
    work_f = ("작업명", "작업 상세") + tuple(k for k, _ in fields if k.endswith("단계"))
    overhead, lines, dep_panels, dep_blocks, tools_up, dep_fn_b = [], [], set(), set(), [], {}
    solvent_word = any(SOLVENT.search(v) and not NOT_FLAM.search(v) for f, v in fields if f not in ("유해위험요소",))
    # 「미네랄울 보온재」: that insulation does not burn — only the material named with it, nothing else (others·Codex)
    noncomb = {w for _, v in fields for t in _tokens(v) if NOT_COMBUST.search(t) for w in COMBUST.findall(t)}
    # one extractor for both kinds of document: an action phrase, not a check ('화기작업 여부 확인', '용접부 검사')
    for f, v in fields:
        for t in _tokens(v):
            # each act on its own: '가용접 후 치수 확인' keeps 가용접 (화기); '용접부 검사만 실시', '절단 없음' are no act
            for a in _acts(t):
                act = not NOT_ACTION.search(a) and not NEGATED.search(a) and not ACT_NO.search(a)
                # '용접부'·'용접기'·'용접재료' name a thing, not the act: '용접부 그라인딩' is still grinding,
                # '용접재료 선정·불출' is no hot work (자료 17번 작업특성)
                weld_thing = WELD_THING if ISSUE.search(v) else WELD_TOOL
                if act and SPARK.search(weld_thing.sub("", a)) and f not in ("유해위험요소", "위치(답변 반영)", "이동 경로(답변)"):
                    tag("SPARK", f, v)
                # flammability is judged per phrase: '수성 도료, 유기용제 세정제' still has a solvent; a paint job with no
                # solvent written anywhere keeps the tag but says it is read from the job name (자료 10번 범위)
                if act and (SOLVENT.search(a) or (PAINT_JOB.search(a) and f in ("작업명", "작업 상세"))) and not NOT_FLAM.search(a):
                    tag("SOLVENT", f if SOLVENT.search(a) or solvent_word else f"{f}({INFERRED})", v)
                if act and SEPARATE.search(a) and f in work_f:
                    tag("SEP", f, v)
                if act and PRESSURE.search(a):
                    tag("PRESSURE", f, v)
                if RADIATION.search(a) and not RAD_NOT.search(a) and not NEGATED.search(a) and f not in ("유해위험요소",):
                    tag("RADIATION", f, v)
                elif act and re.search(r"방사선|선원|이리듐|감마선|RT 촬영", a) and f == "유해위험요소":
                    tag("RADIATION", f, v)           # the v1 reading kept: a hazard written there is not dropped (Codex final #2)
                if act and SUPPORT_ADJ.search(a) and f in work_f + ("작업장비",):
                    tag("SUPPORT_ADJ", f, v)
                # what is handled: a tool, a part — also while 「준비」 (사고사례집 C43: 기밀시험 준비 중 덮개 낙하)
                if (act or re.search(r"준비|세팅|셋업", a)) and not NEGATED.search(a) and not ACT_NO.search(a) and (
                        TOOL_UP.search(a) or re.search(r"준비|세팅|셋업", a)) and f in work_f + ("작업장비",):
                    tools_up.append((f, v))
                if act and ELEC_TOOL.search(a) and f in work_f + ("작업장비",):
                    tag("ELEC_TOOL", f, v)
                if act and VEHICLE.search(a) and f in ("작업명", "작업장비", "작업 상세", "이동 경로(답변)") + work_f[2:]:
                    tag("VEHICLE", f, v)
                if act and CART.search(a) and f in ("작업명", "작업장비", "작업 상세", "이동 경로(답변)") + work_f[2:]:
                    tag("CART", f, v)
                if act and any(w not in noncomb for w in COMBUST.findall(a)) and not NOT_COMBUST.search(a) and f in work_f + ("사용물질", "작업장비"):
                    tag("COMBUST", f, v)
                if act and STAGE.search(a) and f in work_f + ("작업장비",):
                    tag("STAGE", f, v)
                elif act and STAGE_SOFT.search(a) and f in work_f + ("작업장비",):
                    tag("STAGE_SOFT", f, v)
                if act and GAS_HANDLE.search(a) and f in work_f + ("작업장비", "사용물질"):
                    if FLAM_GAS.search(a):
                        tag("FLAM_GAS", f, v)
                    elif GAS_CYL.search(a) and not NONFLAM.search(a):
                        tag("GAS_UNK", f, v)              # a gas cylinder of a kind not written: held, asked
                if act and f == "작업장비" and re.search(r"차량", a):
                    tag("VEHICLE", f, v)
                if act and OVERHEAD.search(a) and not SEPARATE.search(a) and f in work_f:
                    overhead.append((f, v))
            if MEWP.search(t) and f != "유해위험요소":
                tag("MEWP", f, v)
            # nitrogen per act: 「질소 없이」「질소 안 씀」 is no gas (the older words keep their phrase rule)
            n2 = any(re.search(r"질소", a) and not NEGATED.search(a) and not ACT_NO.search(a) and not _says_no(a) for a in _acts(t))
            purge_only = re.search(r"퍼지", t) and not re.search(r"아르곤|TIG|질소|불활성|CO2|CO₂|이산화탄소", t) and (
                re.search(r"압축\s*공기|에어|산소|공기\s*퍼지|퍼지\s*캡", t) or not any(not NOT_ACTION.search(a) for a in _acts(t) if "퍼지" in a))
            if (re.search(r"아르곤|TIG|퍼지|질소 치환|불활성\s*가스|(?:CO2|CO₂|이산화탄소)\s*(?:가스)?\s*(?:로|를|을)?\s*(?:주입|치환|봉입|투입)", t)
                    and not NEGATED.search(t) and not purge_only) \
                    or (n2 and f != "유해위험요소"):
                tag("INERT", f, v)
            if LINES.search(t) and not NEGATED.search(t) and f != "유해위험요소":
                lines.append((f, v))
            light_only = DEP_LIGHT.search(t) and not DEP.search(t) and f != "답변 CF3"
            if light_only and (not re.search(r"전원|급전|연결|물려|분기|공급", t) or re.search(r"배터리|충전식|자체\s*전원", t)):
                pass                                  # 「MCC-4 옆에서 배터리 작업등」: a place, not a power (Codex batch-1 #8)
            elif (DEP.search(t) or DEP_LIGHT.search(t) or f == "답변 CF3") and not NEGATED.search(t) and not DEP_NONE.search(t):
                for pid in PANEL_ID.findall(t):
                    dep_panels.add(pid)
                    dep_fn_b.setdefault(pid, set()).update(_dep_fn(t) or {"unknown"})
                dep_blocks |= set(BLOCK_ID.findall(t)) if f.startswith("답변") else set()
            if re.search(r"배관|계통|라인|퍼지", t):
                for sid in SYSTEM_ID.findall(t):
                    if not CRANE_ID.fullmatch(sid) and not PANEL_ID.fullmatch(sid):
                        ids["systems"].add(sid)
            if f in ("작업명", "작업 상세", "위치(답변 반영)") and re.search(r"이중저|탱크 내부|밀폐|맨홀 진입|코퍼\s*댐|보이드|내부\s*진입", t) and d["type"] == "plan":
                tag("CONFINED", f, v)
            # equipment: per phrase, so 'OH-21-03 사용, OH-21-02 미사용' keeps only the one in use
            for c in CRANE_ID.findall(t):
                if re.search(r"미사용|사용 안|제외", t) or f in ("유해위험요소",):
                    continue
                if d["type"] == "permit" and d["kind"] == "loto":
                    ids["crane_loto"].add(c); tag("CRANE_LOTO", f, v)
                elif d["type"] == "plan" and f == "작업명":
                    continue
                else:
                    ids["crane_use"].add(c); tag("CRANE_USE", f, v)
            for p in PANEL_ID.findall(t):
                if d["type"] == "permit" and d["kind"] == "loto":
                    ids["power_loto"].add(p); tag("POWER_LOTO", f, v)
                elif "전원" in t and not NEGATED.search(t):
                    ids["power_use"].add(p); tag("POWER_USE", f, v)
    # 쌍 하이브리드: the facts the foreman confirmed in his submission (an explicit table, see confirmed_facts)
    from_answer = {}
    for x in d.get("_confirmed", []):
        f = f"{CONFIRMED} {x['item']}"
        if x.get("tag"):
            tag(x["tag"], f, x["value"])
        if x.get("ids") and x["ids"][0] == "dep_panel":         # CF3: the panel the space's fan·light hangs on
            dep_panels.add(x["ids"][1])
            dep_fn_b.setdefault(x["ids"][1], set()).update(_dep_fn(x["value"]) or {"unknown"})
        elif x.get("ids"):
            kind, i = x["ids"]
            ids[kind].add(i)
            from_answer[i] = (f, x["value"])
            tag({"crane_use": "CRANE_USE", "power_use": "POWER_USE"}[kind], f, x["value"])
    if ids["crane_use"]:
        tag("LIFT", "크레인 사용", ", ".join(sorted(ids["crane_use"])))
        for i in sorted(ids["crane_use"] & set(from_answer)):        # a lift known from a confirmed answer says so
            tag("LIFT", *from_answer[i])
    place = d["place"].translate(DASH)
    if lows is None and re.search(r"상부|갑판", place + title):
        lows = highs = None
    known_up = (highs or 0) >= 2 or re.search(r"상부|갑판", place) is not None
    height_permit = d["type"] == "permit" and d["kind"] == "height"
    # up: where something can fall from (a height permit, a MEWP); the level below is only what is known (Codex P1:
    # a height permit with no height is not 「top」 — a vehicle path still reaches it, as before)
    up = known_up or height_permit or "MEWP" in tags
    up_said = highs is None and not up and any(re.search(r"상부|높은\s*곳", a) and not NEGATED.search(a) and not ACT_NO.search(a)
                                                 and not _says_no(a) for t in _tokens(title + " / " + (d.get("detail") or "")) for a in _acts(t))
    # a high place is not needed to be known (자료 LU02·R42-38-DROP·Q04: 높이 미상·2m 미만만으로 낙하를 빼지 않는다):
    # cutting on a height permit, or with no height written at all, still drops — the unknown height caps it (작업 높이 미확인)
    drop_unknown = highs is None and not re.search(r"상부|갑판", place)
    # the work itself separates a piece (작업명·상세; a step's '녹 제거' is not cutting a piece off)
    sep_work = any(f in ("작업명", "작업 상세") for f, _ in tags.get("SEP", [])) or SEPARATE.search(title + " " + (d.get("detail") or ""))
    # cut low (0 < height < 2m) still drops (자료 LU02·R42-38-DROP·Q04: 2m 미만만으로 낙하를 빼지 않는다): held to check
    drop_low = highs is not None and 0 < highs < 2
    if sep_work and (up or drop_unknown or drop_low):
        tag("DROP", "작업명", title)
    # what is handled high up and can fall (자료 R42-09-DROP, 사고사례집 C23·C43·C56, 멘토 「상하 병행 불가」): installing,
    # and also hot work, grinding, tools and maintenance at height or on a crane girder
    loto_girder = d["type"] == "permit" and d["kind"] == "loto" and bool(girder)
    if up or loto_girder or up_said:
        for f, v in overhead + tools_up + [x for x in tags.get("SPARK", []) if x[0] not in ("체크 항목", "허가서 종류")]:
            tag("OVERHEAD", f, v)
        if loto_girder and "OVERHEAD" not in tags:
            tag("OVERHEAD", "답변 LO4", girder[0])
    level = "inside" if re.search(r"내부|이중저|탱크|배관", place) and "외판" not in place else "top" if known_up else "ground"
    # 'ground' for a work whose height nobody wrote is a default, not a fact (자료 3값 논리): kept for the rules that
    # treat it as below, and said so where a rule would need the real level
    level_known = (level != "ground" or highs is not None or (d["type"] == "permit" and d["kind"] in ("lifting", "loto"))) and not height_permit
    ids["blocks"] = {b for b in BLOCK_ID.findall(" ".join([title, place])) + BLOCK_FIELD.findall(d.get("target") or "")
                     if not NOT_BLOCK.search(b)}
    # the method from what the work says (not the form's generic 「용접·용단」 check box)
    spark_raw = [v for f, v in tags.get("SPARK", []) if f not in ("체크 항목", "허가서 종류")] + [title, d.get("detail") or ""]
    spark_text = [a for s in spark_raw for t in _tokens(s) for a in _acts(t)
                  if not NEGATED.search(a) and not ACT_NO.search(a) and not _says_no(a)]
    arc_text = [re.sub(r"용접부|용접\s*재료|용접봉|용접\s*와이어|플럭스", "", s) for s in spark_text]
    hot_kind = {k for k, rx, src in (("arc", ARC, arc_text), ("gas", GAS_CUT, spark_text), ("grind", GRIND, spark_text))
                if any(rx.search(s) for s in src)} if "SPARK" in tags else set()
    if hot_kind and any(re.search(r"가우징|그라인|연삭|사상", s) for s in spark_text):
        hot_kind.add("noise")                        # 가우징·연삭 소음 (자료 HW08-NOISE·PE12: 반경 없이 신호 방해로만)
    wins = [_win_m(w) for w in d["windows"]]
    move = _win_m(d["move"]) if d.get("move") else None
    move_off = bool(move and wins and not any(a <= move[0] and move[1] <= b for a, b in wins))
    # the moving part of a lift: its planned move, plus any re-entry window the safety team added (완료 후 재진입:
    # the block may be lifted again then, so the whole added window counts, not only the old move)
    moves = ([move] if move else []) + [_win_m(w) for w in d.get("extra_windows") or []]
    # a lift's stage from the submission (the moving part, T1/T6): its risky phase, the whole window kept apart
    stage = [_win_m(w) for w in d.get("stage_windows") or []]
    if stage and d["type"] == "permit" and d["kind"] == "lifting":
        # the moving part the foreman confirmed replaces the document's move for this computation; the document's own
        # alarm on the old move stays through floor() (Codex final #6)
        moves = stage + [_win_m(w) for w in d.get("extra_windows") or []]
        move = None
    # a crane step with a stated start: '(10:30)'. Its end is not stated, so it runs to the end of the plan's window
    lift_at = []
    if d["type"] == "plan":
        for _, s in fields:
            if CRANE_ID.search(s) and (m := re.search(r"\((\d{1,2}:\d{2})\)", s)) and wins:
                t0 = _m(m.group(1))
                # the step runs from its stated start to the end of the window it falls in; a step whose time is no
                # longer inside the work's hours (stopped or moved) is not done at that time
                lift_at += [(t0, b) for a, b in wins if a <= t0 < b]
    sp, route_read = _route_spans(d)
    where = "known" if sp else "off" if OFF_FLOOR.search(place) else "unknown"
    # an answer that says another work is below this one (B3 '하부에서 족장 해체 13:00~15:30 (삼녹)')
    below = [v for f, v in fields if f.startswith("답변") and re.search(r"하부|아래|밑", v)]
    # a time whose end is before its start, read as ending the next day without anyone saying so (자료 MT04: 익일인지 오기인지)
    assumed = [f"{w['start']}~{w['end']}" for w in d["windows"] if w.get("assumed_next_day")]
    rev_cols = [f"{s['bay']}BAY {s['c1']:02d}-{s['c0']:02d}" for s in sp if s.get("rev")]
    fit = [v for f, v in fields if f in work_f and re.search(r"취부|가용접|가고정|볼트\s*체결|정렬", v)]
    text_all = " ".join(v for _, v in fields)
    return {"d": d, "tags": tags, "ids": ids, "level": level, "level_known": level_known, "height_permit": height_permit,
            "low": lows, "high": highs, "wins": wins, "move": move, "moves": moves, "move_off": move_off, "lift_at": lift_at,
            "fields": fields, "where": where, "below": below, "spans": sp, "route_read": route_read,
            "drop_unknown": drop_unknown and "DROP" in tags, "drop_low": drop_low and "DROP" in tags and not up, "up_said": up_said,
            "hot_kind": hot_kind, "fit": fit, "text_all": text_all,
            "held": bool(HELD.search(text_all)), "return_path": bool(RETURN_PATH.search(text_all)), "panel_open": bool(PANEL_OPEN.search(text_all)),
            "dep": dep, "dep_fn": dep_fn, "dep_fn_b": dep_fn_b, "dep_panels": dep_panels, "dep_blocks": dep_blocks,
            "girder": girder, "test_run": test_run, "test_drive": test_drive, "lines": lines,
            "support_cut": any(SUPPORT_CUT.search(v) for _, v in tags.get("SEP", [])), "assumed_nd": assumed, "rev_cols": rev_cols,
            "res_end": _m(d["residual_end"]) + (1440 if d.get("residual_next_day") else 0) if d.get("residual_end") else None, "stage": stage,
            "people": d.get("workers")}           # None = 미상, 0 = 서류상 아무도 없음(실제 퇴실 확인은 아님)


def _route_spans(d):
    """the document's BAY + column ranges, with a route written as '03→08칼럼' or '03칼럼에서 08칼럼까지' read across the
    whole range, not only its ends (자료 일상 2·14~16·21·26·33 경로형 장소) -> (spans, read a route?)"""
    sp = [dict(s) for s in d.get("spans") or []]
    text = " ".join([d.get("place") or "", d.get("route") or ""]).translate(DASH)
    out, bay = [], None
    for m in re.finditer(r"(?<!\d)(\d)\s*BAY|(" + ROUTE_CHAIN.pattern + ")", text):
        if m.group(1):
            bay = int(m.group(1))
            continue
        if not re.search(r"칼럼|축", m.group(2)):
            continue
        nums = [int(x) for x in re.findall(r"\d{1,2}", m.group(2))]
        nums = [x for x in nums if 1 <= x <= safety.COLS]
        if bay and len(nums) >= 2 and min(nums) != max(nums):
            out.append({"bay": bay, "c0": min(nums), "c1": max(nums)})
    if not out:
        return sp, False
    keep = [s for s in sp if not any(s["bay"] == r["bay"] and (s["c0"] is None or (r["c0"] <= s["c0"] and s["c1"] <= r["c1"])) for r in out)]
    return keep + out, True


# ---------------------------------------------------------------- where and when two works meet
def _spans(P, path=False):
    """BAY + column ranges; a route as one range from its first to its last column (the load passes over all of it)."""
    sp = P.get("spans", P["d"]["spans"])
    if (path and P["d"]["is_route"]) or P.get("route_read"):
        out = []
        for b in sorted({s["bay"] for s in sp}):
            cs = [s for s in sp if s["bay"] == b and s["c0"]]
            out.append({"bay": b, "c0": min(s["c0"] for s in cs), "c1": max(s["c1"] for s in cs)} if cs else {"bay": b, "c0": None, "c1": None})
        return out
    return sp


def place_rel(A, B, path_a=False, path_b=False):
    """same (shared column range) · near (next column) · unknown (a side without columns or place) · far · none · off."""
    if A["where"] == "off" or B["where"] == "off":
        return {"kind": "off", "bay": None, "gap": None}
    if A["where"] == "unknown" or B["where"] == "unknown":
        return {"kind": "unknown", "bay": None, "gap": None}
    order = {"same": 0, "near": 1, "unknown": 2, "far": 3, "none": 4}
    best = {"kind": "none", "bay": None, "gap": None}
    for a in _spans(A, path_a):
        for b in _spans(B, path_b):
            if a["bay"] != b["bay"]:
                continue
            if a["c0"] is None or b["c0"] is None:
                r = {"kind": "unknown", "bay": a["bay"], "gap": None}
            else:
                gap = max(a["c0"], b["c0"]) - min(a["c1"], b["c1"])
                r = {"kind": "same" if gap <= 0 else "near" if gap == 1 else "far", "bay": a["bay"], "gap": max(gap, 0)}
            if order[r["kind"]] < order[best["kind"]] or (r["kind"] == best["kind"] == "far" and r["gap"] < best["gap"]):
                best = r
    return best


def overlaps(wa, wb):
    """The overlap of two window lists as separate pieces, merged: [(start, end)] (no minute counted twice)."""
    out = []
    for a0, a1 in wa:
        for b0, b1 in wb:
            s, e = max(a0, b0), min(a1, b1)
            if e > s:
                out.append((s, e))
    merged = []
    for s_, e_ in sorted(out):
        if merged and s_ <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e_))
        else:
            merged.append((s_, e_))
    return merged


def gap_after(first, then):
    """Minutes from the end of `first` to the start of `then` (`then` starting after `first` ended), smallest; None if never."""
    g = [b0 - a1 for a0, a1 in first for b0, b1 in then if b0 >= a1]
    return min(g) if g else None


# ---------------------------------------------------------------- the rules: does the path exist? (A = cause, B = exposed)
# 서류상 인원 0 is not proof that nobody is there (자료 MV03·Q06: 「인원 합계 0만으로 무인을 확정하지 않는다」): the path
# stays and _judge caps it at 노출 1 with that said. (A document without a head count is 미상: 노출 2 at most.)
def _people(B):
    return True


def _pick(P):
    return P["moves"] if P["moves"] else P["lift_at"] or P["wins"]


def _path(rule, A, B):
    """→ (windows of A, windows of B, place-mode, notes) or None. place-mode: which place evidence the rule needs;
    notes: [(E cap, words)] this pair's own unknowns (a height or a level nobody wrote)."""
    t, a, b = rule["id"], A["tags"], B["tags"]
    wa, wb = A["wins"], B["wins"]
    loto = lambda P: P["d"]["type"] == "permit" and P["d"]["kind"] == "loto"  # noqa: E731
    over = lambda P: P["level"] == "top" or "MEWP" in P["tags"] or bool(P["girder"]) or P["height_permit"]  # noqa: E731
    if t == "FIRE":
        return (wa, wb, "reach", []) if "SPARK" in a and "SOLVENT" in b else None
    if t == "FIRE_GAS":
        if "SPARK" not in a or not ({"FLAM_GAS", "GAS_UNK"} & set(b)):
            return None
        return (wa, wb, "reach", [] if "FLAM_GAS" in b else [(1, "가스 용기의 가스 종류(가연성인지) 서류에 없음")])
    if t == "CONF_HOT":
        return (wa, wb, "block", []) if "SPARK" in a and "CONFINED" in b else None
    if t == "CONF_GAS":
        # the gas reaches by a pipe or by the air of the same inside space (자료 PE01·PE09: 배관 OR 공기 경로)
        if "INERT" not in a:
            return None
        if "CONFINED" in b or B["level"] == "inside":
            return (wa, wb, "system", [])
        if not B["level_known"] and A["ids"]["blocks"] & B["ids"]["blocks"]:
            return (wa, wb, "system_any", [(2, "블록 안·위인지(탱크·구획 안 작업인지) 서류에 없음")])
        return None
    if t == "LOAD_OVER":
        if "LIFT" not in a or A["ids"]["crane_use"] & B["ids"]["crane_loto"]:
            return None                              # a crane over its own repair is CRANE_LOTO
        return (_pick(A) if A["moves"] or A["lift_at"] else wa, wb, "path", [])
    if t == "TARGET_OCCUPIED":
        if A["d"]["type"] != "permit" or A["d"]["kind"] != "lifting":
            return None
        if B["level"] in ("inside", "top"):
            return (A["moves"] if A["moves"] else wa, wb, "same_block", [])
        if not B["level_known"] and A["ids"]["blocks"] & B["ids"]["blocks"]:   # nobody wrote where in the block: 안·위일 수 있음
            return (A["moves"] if A["moves"] else wa, wb, "same_block", [(2, "블록 안·위인지(작업 높이·위치) 서류에 없음")])
        # after the lift: work by the landed block before its supports, fixing and rigging are released (자료 MV05·MV06·MV13)
        return (A["moves"] if A["moves"] else wa, wb, "landed", [])
    if t == "CRANE_LOTO":
        if not (A["ids"]["crane_loto"] & B["ids"]["crane_use"]):
            return None
        return (wa, B["moves"] if B["moves"] else B["lift_at"] or wb, "link", [])
    if t == "POWER_LOTO":
        return (wa, wb, "link", []) if A["ids"]["power_loto"] & B["ids"]["power_use"] else None
    if t == "DROP_BELOW":
        if "DROP" not in a:
            return None
        if A["drop_low"]:
            return (wa, wb, "below", [(2 if A["below"] else 1, "작업 높이 2m 미만으로 적힘: 낮아도 떨어지는 부재에 맞거나 깔릴 수 있음(실제 하부 노출 확인)")])
        return (wa, wb, "below", [(2, "작업 높이 미확인(서류에 높이 없음)")] if A["drop_unknown"] else [])
    if t == "PRESSURE":
        return (wa, wb, "reach", []) if "PRESSURE" in a else None
    if t == "RADIATION":
        return (wa, wb, "reach", []) if "RADIATION" in a else None
    if t == "VEHICLE":
        if "VEHICLE" not in a or (B["level"] != "ground" and "MEWP" not in b):
            return None
        return (wa, wb, "covered", [])
    if t == "CART":
        if "CART" not in a or "VEHICLE" in a or (B["level"] != "ground" and "MEWP" not in b):
            return None
        return (wa, wb, "covered", [])
    if t == "CRANE_SHARE":
        if not (A["ids"]["crane_use"] & B["ids"]["crane_use"]) or A["d"]["id"] > B["d"]["id"]:
            return None
        return (_pick(A), _pick(B), "link", [])
    if t == "CRANE_CROSS":
        if "LIFT" not in a or "LIFT" not in b or A["d"]["id"] > B["d"]["id"] or A["ids"]["crane_use"] & B["ids"]["crane_use"] \
                or not A["ids"]["crane_use"] or not B["ids"]["crane_use"]:
            return None
        return (_pick(A), _pick(B), "bay", [])
    if t == "SUPPORT":
        lifted = A["d"]["type"] == "permit" and A["d"]["kind"] == "lifting" and any(SUPPORT_CUT.search(v) for _, v in A["fields"])
        if lifted and not ("SEP" in a or "DROP" in a or "SUPPORT_ADJ" in a):
            # the block to be lifted holds up another structure (자료 MV07·Q07 p305: 이동으로 이웃 구조의 받침 상실): the
            # blocks written with the support words are the ones held up; the lifted block's own work is asked
            held = {b_ for _, v in A["fields"] for t in _tokens(v) if SUPPORT_CUT.search(t) for b_ in BLOCK_ID.findall(t)} - A["ids"]["blocks"]
            if held & B["ids"]["blocks"]:
                return (wa, wb, "held_by", [(2, f"인양할 블록이 받치는 블록 {', '.join(sorted(held & B['ids']['blocks']))}: 들어 옮기면 받침이 빠짐")])
            return (wa, wb, "same_block", [(2, "인양할 블록이 다른 구조·작업의 받침·지지로 쓰이는지 확인 필요")])
        if "SEP" not in a and "DROP" not in a and "SUPPORT_ADJ" not in a:
            return None
        # those on top, those inside an attached pipe or space (자료 PE16), and, when supports or jigs are taken out,
        # anyone by the same block (자료 R42-09-SUPPORT: 블록 주변·위·아래 의존 작업자)
        if B["level"] in ("top", "inside"):
            return (wa, wb, "same_block", [])
        if A["support_cut"] or "SUPPORT_ADJ" in a:
            return (wa, wb, "same_block", [(2, "받침·지그 해체·조정: 블록 아래·주변 작업과의 높이 관계 미확인")])
        if not B["level_known"] and A["ids"]["blocks"] & B["ids"]["blocks"]:
            return (wa, wb, "same_block", [(2, "블록 위·안인지(작업 높이·위치) 서류에 없음")])
        return None
    if t == "ACCESS":
        hard = {"LIFT", "VEHICLE", "DROP", "SEP", "STAGE", "CART"} & set(a)
        if not (hard or "STAGE_SOFT" in a) or "CONFINED" not in b:
            return None
        return (_pick(A) if A["moves"] or A["lift_at"] else wa, wb, "path",
                [] if hard else [(1, "반입·반출 물품이 출입구·통로에 놓이는지 서류에 없음")])
    if t == "HOT_PERSON":
        return (wa, wb, "hot", []) if "SPARK" in a and "SOLVENT" not in b and "CONFINED" not in b else None
    if t == "VENT_LOTO":
        if loto(A) and "CONFINED" not in b:
            # what else a power cut stops (자료 EL09-FUME·EL09-LIGHT-FALL p341): a hot work's local exhaust, the light of
            # a work up high — not known to hang on that power: held to check. A function written on another panel is
            # not it (시연 N04: 환기팬·작업등 MCC-5); a welder's own power says nothing of its exhaust (Codex batch-1 #3)
            other = lambda fn: any(fn in f_ for p_, f_ in B["dep_fn_b"].items()) and not any(  # noqa: E731
                fn in f_ and p_ in A["ids"]["power_loto"] for p_, f_ in B["dep_fn_b"].items())
            if "SPARK" in b and LOCAL_EXH.search(B["text_all"]) and not other("air"):
                return (wa, wb, "dep", [(1, "차단 전원에 이 화기 작업의 국소배기·집진기가 물렸는지 서류에 없음")])
            if over(B) and ("light" in A["dep_fn"] or DEP_LIGHT.search(B["text_all"])) and not other("light"):
                return (wa, wb, "dep", [(1, "차단 전원에 상부 작업 조명이 물렸는지 서류에 없음")])
            return None
        if not loto(A):
            return None
        linked = (B["dep_panels"] & A["ids"]["power_loto"]) or (A["dep_blocks"] & B["ids"]["blocks"])
        if A["dep"] == "no" and not linked:
            # the foreman said nothing else stops: kept as a question to confirm, never dropped on a denial
            return (wa, wb, "dep", [(1, "정전 반장 답: 환기·조명 영향 없음(현장 확인 전)")])
        return (wa, wb, "dep", [])
    if t == "CRANE_TEST":
        if not (loto(A) and A["ids"]["crane_loto"]) or loto(B) or A["ids"]["crane_loto"] & B["ids"]["crane_use"]:
            return None
        if not over(B):
            # a test run stated: the work on the floor under its runway and hook (자료 EL05-MOTION p340): held to check
            if A["test_drive"] and B["level"] == "ground":
                return (wa, wb, "crane_bay", [(1, "시험 주행 구간·훅 아래 지상 작업인지 미확인")])
            return None
        notes = [] if A["test_run"] else [(1, "시험운전·주행 계획이 서류에 없음(복구 뒤 시험이 보통 따름)")]
        if not (B["girder"] or "MEWP" in b):         # a block top, not the crane's own height: the hook's path is not known
            notes.append((1, "블록 상부 작업: 시험 주행 구간·훅 높이와 겹치는지 미확인"))
        return (wa, wb, "crane_bay", notes)
    if t == "SHARED_LOTO":
        if not (loto(A) and loto(B)) or A["d"]["id"] > B["d"]["id"]:
            return None
        shared = (A["ids"]["crane_loto"] & B["ids"]["crane_loto"]) | (A["ids"]["power_loto"] & B["ids"]["power_loto"])
        return (wa, wb, "shared", []) if shared else None
    if t == "OTHER_CRANE_REPAIR":
        if "LIFT" not in a or not A["ids"]["crane_use"] or not loto(B) or not B["ids"]["crane_loto"] \
                or A["ids"]["crane_use"] & B["ids"]["crane_loto"]:
            return None
        return (_pick(A), wb, "bay2", [])
    if t == "HOT_PANEL":
        if not ("SPARK" in a and loto(B) and (B["ids"]["power_loto"] or B["ids"]["crane_loto"])):
            return None
        return (wa, wb, "hot", [] if B["panel_open"] else [(1, "반을 열어 두는지 서류에 없음")])
    if t == "FIRE_SOLID":
        return (wa, wb, "reach", []) if "SPARK" in a and "COMBUST" in b else None
    if t == "EGRESS_BLOCK":
        hard = {"STAGE", "CART"} & set(a)
        if not (hard or "STAGE_SOFT" in a) or "CONFINED" in b:
            return None                              # a confined entry's exit is ACCESS
        need = "SPARK" in b or B["level"] in ("top", "inside") or "MEWP" in b or B["height_permit"]
        return (wa, wb, "same_only", [] if hard else [(1, "반입·반출 물품이 대피 통로에 놓이는지 서류에 없음")]) if need else None
    if t == "OVERHEAD_WORK":
        if "OVERHEAD" not in a or "DROP" in a:
            return None
        return (wa, wb, "below", [(1, "작업 높이·위아래 관계 미확인(작업명에 「상부」만 적힘)")] if A["up_said"] else [])
    if t == "CABLE_RUN":
        if not ({"VEHICLE", "CART"} & set(a)) or "SPARK" not in b or "arc" not in B["hot_kind"]:
            return None
        return (wa, wb, "covered", [])
    if t == "NOISE_SIGNAL":
        return (wa, wb, "same_only", []) if "SPARK" in a and "noise" in A["hot_kind"] and "LIFT" in b else None
    if t == "WELD_RETURN":
        if "SPARK" not in a or "arc" not in A["hot_kind"] or not ("CONFINED" in b or B["level"] == "inside"):
            return None
        return (wa, wb, "same_block", [] if A["return_path"] else [(1, "귀환 클램프 위치·전류 경로가 서류에 없음")])
    if t == "LIFT_LINE":
        if A["d"]["type"] != "permit" or A["d"]["kind"] != "lifting" or not B["lines"]:
            return None
        return (A["moves"] if A["moves"] else wa, wb, "same_block", [])
    if t == "CONF_PAINT":
        # painting inside the same confined space counts too: two documents are two works (Codex P1-2)
        if "SOLVENT" not in a:
            return None
        return (wa, wb, "paint", []) if "CONFINED" in b or B["level"] == "inside" else None
    if t == "MEWP_OVER":
        if "MEWP" not in a or "MEWP" in b or B["level"] != "ground":
            return None
        return (wa, wb, "covered", [])
    if t == "FIRE_SPREAD":
        if "SPARK" not in a or "COMBUST" not in a or "SOLVENT" in b or "COMBUST" in b:
            return None
        return (wa, wb, "hot", [])
    if t == "HELD_FIT":
        if A["d"]["type"] != "permit" or A["d"]["kind"] != "lifting" or not ("SPARK" in b or B["fit"]):
            return None
        held = A["held"] or B["held"]
        return (wa, wb, "same_block", [] if held else [(1, "크레인이 잡은 그 부재를 취부하는지 서류에 없음")])
    if t == "EQUIP_IGNITION":
        if not ({"MEWP", "POWER_USE", "ELEC_TOOL"} & set(a)) or "SOLVENT" not in b or "SPARK" in a:
            return None
        return (wa, wb, "same_only", [])
    if t == "GRIND_FLY":
        return (wa, wb, "hot", []) if "SPARK" in a and "grind" in A["hot_kind"] and "CONFINED" not in b else None
    return None


def _place(mode, A, B, rule=None):
    """How sure the place link is: (E cap 3/2/1 or None = no path, words)."""
    rid = (rule or {}).get("id")
    common = sorted(A["ids"]["blocks"] & B["ids"]["blocks"])
    if mode == "system":
        shared = sorted(A["ids"]["systems"] & B["ids"]["systems"])
        if shared:
            return 3, f"같은 배관·계통 {', '.join(shared)}"
        if not common:
            # the same column with no block or system written: held as a question, not dropped (others 꼭 보강)
            rel0 = place_rel(A, B)
            if rel0["kind"] == "unknown" and rel0.get("bay"):          # a BAY with no column: where in it is not known
                return 1, f"{rel0['bay']}BAY(칼럼 미기재): 같은 공간·가스 계통인지 미확인"
            if rel0["kind"] == "near":            # 멘토 #45 아르곤 × 밀폐 병행 불가: the next column is not left out either
                return 1, f"{rel0['bay']}BAY 바로 옆 칼럼: 같은 공간·가스 계통인지 미확인"
            return (1, f"{rel0['bay']}BAY 같은 칼럼: 같은 공간·가스 계통인지 미확인") if rel0["kind"] == "same" else (None, "")
        # the same block, both inside: the gas can reach by the air of one space, not only by a pipe (자료 PE01, ACC-AR2013)
        if A["level"] == "inside" and B["level"] == "inside":
            return 2, f"같은 블록 {', '.join(common)} 내부 공기 구획을 함께 쓸 수 있음(가스 계통 연결은 서류에 없음)"
        return (1, f"같은 블록 {', '.join(common)}이지만 가스 계통 연결은 서류에 없음") if "CONFINED" in B["tags"] else (None, "")
    if mode == "link":
        ids = sorted((A["ids"]["crane_loto"] | A["ids"]["power_loto"] | A["ids"]["crane_use"]) & (B["ids"]["crane_use"] | B["ids"]["power_use"]))
        return 3, f"같은 설비 {', '.join(ids)}"
    if mode == "shared":
        ids = sorted((A["ids"]["crane_loto"] & B["ids"]["crane_loto"]) | (A["ids"]["power_loto"] & B["ids"]["power_loto"]))
        return 3, f"같은 설비 {', '.join(ids)}를 두 정비 작업이 함께 잠금"
    if mode == "dep":
        link = sorted(B["dep_panels"] & A["ids"]["power_loto"]) or sorted(A["dep_blocks"] & B["ids"]["blocks"])
        if link:
            return 3, f"차단 범위({', '.join(link)})에 진입 공간의 환기·송기·조명이 물려 있다고 서류·답에 적힘"
    if mode == "crane_bay":
        said = [c for c in sorted(A["ids"]["crane_loto"]) if any(c in v for _, v in B["fields"])]
        if said:
            return 3, f"상대 서류에 같은 크레인 {', '.join(said)}이 적힘"
    if mode == "paint" and common:
        if A["level"] == "inside" and B["level"] == "inside":
            return 3, f"블록 {', '.join(common)} 안 같은 공간일 수 있음(도장·진입 모두 내부)"
        return 2, f"같은 블록 {', '.join(common)}: 도장 구역과 진입 공간이 이어지는지 미확인"
    if mode == "paint":
        mode = "block"
    if mode == "held_by":
        held = sorted({b_ for _, v in A["fields"] for t in _tokens(v) if SUPPORT_CUT.search(t) for b_ in BLOCK_ID.findall(t)} & B["ids"]["blocks"])
        return 3, f"인양 블록이 받치는 블록 {', '.join(held)}(인양 허가서에 적힘)"
    if mode == "system_any":
        if A["where"] == "off" or B["where"] == "off":
            return None, ""
        return 2, f"같은 블록 {', '.join(common)}: 같은 탱크·구획 안이면 가스가 닿을 수 있음(작업 위치 미확인)"
    if rid == "PRESSURE" and A["ids"]["systems"] & B["ids"]["systems"]:
        # the same pipe is one system wherever it is written (Codex final P5·L113: 다른 BAY라도 계통이 이어짐)
        return 3, f"같은 배관·계통 {', '.join(sorted(A['ids']['systems'] & B['ids']['systems']))}(시험 매체·압력이 들어올 수 있음)"
    rel = place_rel(A, B, path_a=mode == "path")
    if rid in ("FIRE", "FIRE_SOLID", "FIRE_GAS") and rel["kind"] == "none" and not common and any(
            abs(a["bay"] - b["bay"]) == 1 and (a["c0"] is None or b["c0"] is None or max(a["c0"], b["c0"]) - min(a["c1"], b["c1"]) <= 1)
            for a in A["spans"] for b in B["spans"]):
        # sparks over the BAY line (자료 HW05 15m 예시·B22): the distance and the partition are not known — held, not left out
        return 1, "옆 BAY 같은 칼럼대: 불티·열이 넘어가는지(거리·칸막이·개구부) 미확인"
    if rid == "RADIATION" and rel["kind"] == "none" and any(abs(a["bay"] - b["bay"]) == 1 for a in A["spans"] for b in B["spans"]):
        # the controlled area can be wider than a BAY (선원 세기·차폐·방향에 따라 수십 m 이상일 수 있음, 참고): held, not left out
        return 1, "옆 BAY: 방사선 통제구역 범위 미확인(촬영 담당에게 통제 범위 확인)"
    forced = False
    if common and rel["kind"] in ("none", "near", "far", "unknown"):
        # a stated relation (the same block) comes before a coarse address: another BAY or column on paper does not
        # drop it (Codex B 13, 자료 398~399: 명시적 연결이 주소보다 우선)
        rel, forced = {"kind": "same", "bay": rel.get("bay"), "gap": 0}, True
    if mode in ("dep", "crane_bay", "bay2"):
        if rel["kind"] in ("off", "none"):
            return None, ""
        if rel["kind"] == "unknown" and not rel.get("bay"):
            return 1, "위치(BAY)를 알 수 없어 같은 BAY인지 확인 못 함"
        bay = f"{rel['bay']}BAY" if rel.get("bay") else "같은 블록"
        if mode == "dep":
            return 1, f"같은 {bay}: 차단 전원에 {'진입 공간' if 'CONFINED' in B['tags'] else '그 작업'}의 환기·배기·조명·연락이 물렸는지 서류에 없음"
        return 2, f"같은 {bay}(주행 구간 미확인)" if mode == "crane_bay" else f"같은 {bay}(같은 주행로인지 미확인)"
    if rel["kind"] in ("off", "none"):
        return None, ""
    if rel["kind"] == "unknown":
        return 1, "위치(칼럼)를 알 수 없어 같은 곳인지 확인 못 함"
    if mode in ("same_block", "landed"):
        return (3, f"같은 블록 {', '.join(common)}") if common else (None, "")
    if mode == "bay":
        return (2, f"같은 {rel['bay']}BAY(주행 구간 미확인)") if rel["kind"] in ("same", "near", "far") and rel.get("bay") else (None, "")
    if mode == "path":
        if rel["kind"] == "near" and rid == "LOAD_OVER":
            # the column next to a stated path: the load's width, turn and swing are not known (자료 p316 포괄외곽의 한계, B10)
            return 1, f"{rel['bay']}BAY 경로 바로 옆 칼럼: 하물 폭·회전·흔들림 외곽 미확인"
        if rel["kind"] != "same":
            return None, ""
        if common and (forced or not A["d"]["is_route"]):
            return 3, f"같은 블록 {', '.join(common)}"
        return (3, f"명시된 이동 경로가 {rel['bay']}BAY 그 칼럼 위를 지남(평면 경로: 실제 하물 외곽·높이는 서류에 없음)") if A["d"]["is_route"] else             (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 위치 미확인)")
    if mode == "covered":
        if rel["kind"] != "same":
            return None, ""
        return (3, f"운반 구간 안 · 같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 운반 구간과 같은 칼럼 주소")
    if mode == "below":
        if rel["kind"] == "near" and not common:
            # a cut piece can turn, slide or bounce past its column (자료 HW03-FALL p210): not left out, held
            return 1, f"{rel['bay']}BAY 바로 옆 칼럼: 떨어지는 물체의 크기·회전·미끄러짐 범위 미확인"
        if rel["kind"] != "same":
            return None, ""
        stated = [v for v in A["below"] if (B["d"].get("company") and B["d"]["company"] in v) or (B["d"]["type"] == "permit" and B["d"]["id"] in v)]
        if stated:
            return 3, f"작업반장이 아래 작업이라고 답함: '{stated[0]}'"
        if B["low"] is not None and A["high"] is not None and B["low"] > A["high"]:
            return None, ""                          # the other work is clearly above: nothing falls on it
        if B["level"] in ("ground", "inside") or (B["high"] is not None and A["low"] is not None and B["high"] < A["low"]):
            return (3 if common else 2), (f"같은 블록 {', '.join(common)} · 아래 높이" if common else "같은 칼럼 주소 · 아래 높이")
        return 2, "같은 칼럼이지만 위아래 높이를 확정할 수 없음"
    if mode == "block":
        if common:
            return 3, f"같은 블록 {', '.join(common)}"
        if rel["kind"] == "near":
            return 1, f"{rel['bay']}BAY 바로 옆 칼럼 다른 블록: 개구부까지 거리 미확인(화재감시자 11m 안일 수 있음·차폐 확인)"
        if rel["kind"] == "far":
            return 1, f"{rel['bay']}BAY 칼럼 {rel['gap']}칸 떨어진 다른 블록: 거리 미확인(개구부·차폐 확인 필요)"
        return (2, f"{rel['bay']}BAY 같은 칼럼 주소(다른 블록)") if rel["kind"] == "same" else (None, "")
    if mode in ("same_only", "hot"):
        if rel["kind"] == "near" and mode == "hot":
            # 11m is the fire-watch radius of 제241조의2 (not a ban radius); the column spacing is not measured, so the next
            # column may be inside it: held as 「거리 미확인」, never left out (자료 HW01·LU07·Q01, p382 2번)
            return 1, f"{rel['bay']}BAY 바로 옆 칼럼: 거리 미확인(화재감시자 11m 안일 수 있음·차폐 확인)"
        if rel["kind"] != "same":
            return None, ""
        return (3, f"같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 거리 미확인)")
    # reach: fire, pressure, radiation — same block / same columns; anywhere else in the BAY the real distance and
    # shielding are not known (the column spacing is an estimate, and 11m is the fire-watch radius of 제241조의2, not the
    # edge of every hazard), so a farther column is not left out: it stays 「거리 미확인」 to be checked (Codex A7)
    if rel["kind"] == "same":
        return (3, f"같은 블록 {', '.join(common)}") if common else (2, f"{rel['bay']}BAY 같은 칼럼 주소(실제 거리 미확인)")
    if rel["kind"] == "near":
        return 1, f"{rel['bay']}BAY 바로 옆 칼럼: 거리 미확인(실제 거리·차폐 확인 필요)"
    if rel["kind"] == "far":
        return 1, f"{rel['bay']}BAY 칼럼 {rel['gap']}칸 떨어짐: 거리 미확인(실제 거리·차폐 확인 필요)"
    return None, ""


# 쌍 하이브리드 (design §8.1): a submission's answers the foreman confirmed, about his own work, go into the
# profile of that permit like its other answers — marked, so the evidence says where they came from. Only these
# items (what the work does, where, with what); not another team's work (B3·C3·C5), not a free remark, not a
# checking answer, not 「모름」 or 「해당 없음」 (an answer adds what it says; it never takes away what the documents say).
CONFIRMED = "작업반장 답변 · 반장 답변 확인"
# (question, choice) -> the tag the confirmed choice says of this work (the choice itself, whatever number came with it)
HYBRID_CHOICE = {("HT1", "gas"): "SPARK", ("HT1", "plasma"): "SPARK", ("HT1", "mech"): "SPARK",
                 ("CF1", "repair"): "SPARK", ("CF4", "yes"): "SPARK"}  # CF4: hot work done inside the confined space      # 밀폐 안 「보수·용접」: hot work inside a confined permit (실물 허가서 감사)
# a typed answer naming the equipment this work uses: the IDs it names, clause by clause, not in a clause that says no
HYBRID_IDS = {"D2": "crane_use", "LI1": "crane_use", "D4": "power_use", "CF3": "dep_panel"}   # CF3: the space's fan·light panel
# a typed answer naming the gas or line: argon·nitrogen in a clause that does not say no
HYBRID_INERT = ("H2", "D3", "CF2", "D7")             # D7: the pressure-test medium (질소 → 불활성가스)
SAYS_NO = re.compile(r"안\s*(?:씀|써|쓰|함|해|하|합|들)|않|없|미사용|사용\s*안|제외|아님|아니|말고|금지|빼고")
OTHERS = re.compile(r"(?:옆|다른|타|상대|저쪽)\s*(?:팀|업체|반|작업|회사)|[가-힣]{1,6}팀(?:은|는|이|가|도|의|에서|이랑|하고)|들었")
CLAUSE = re.compile(r"[,·/;.]|\s(?:그리고|또는|및)\s")


def standing(answers):
    """the answers that stand (the contract of impl/multiturn.md): augment's own function when it has one, else
    augment.live_answers (C6 「서류가 맞음」 takes an answer back) with an answer X the foreman corrected by
    C5.X 「추가로 적은 내용이 맞음」 read as what he wrote there — the same reading as checklist.standing"""
    from . import augment                              # lazy: augment imports heavy helpers
    own = getattr(augment, "standing", None) or getattr(augment, "standing_answers", None)
    if own:
        return own(answers or [])
    live = augment.live_answers(answers or [])
    fixed = {}
    for a in live:
        q = str(a.get("qid", ""))
        if q.startswith("C5.") and a.get("choice") == "free" and ":" in q:
            fixed[q.split(":")[0][3:] + ":" + q.split(":", 1)[1]] = (a.get("read") or a.get("value") or "").strip()
    out = [{**a, "choice": "text", "value": fixed[a["qid"]], "read": fixed[a["qid"]]} if a.get("qid") in fixed else a for a in live]
    # a correction whose earlier answer is not in the list still stands as that item's answer
    have = {a.get("qid") for a in live}
    out += [{"qid": k, "choice": "text", "value": v, "read": v} for k, v in fixed.items() if k not in have and v]
    return out


def confirmed_facts(answers):
    """the answers of a submission the foreman confirmed — his own typed answers and the readings of his own work he
    confirmed on the card — as facts of his work: [{item, value, tag | ids}]. Nothing from another team's work, a
    free remark, a checking question, an AI question, a blank-field fill, 「모름」 or a no; a typed sentence is read
    only for what the table above names."""
    from . import augment                              # lazy: augment imports heavy helpers
    out = []
    for a in standing(answers):                        # taken back (C6) or corrected (C5): what stands now
        item, v = str(a.get("qid", "")).split(":")[0], (a.get("value") or "").strip()
        # a plain written denial counts as its no-choice; that only keeps the answer from adding a fact — the
        # documents' own alarms are never removed by it (floor)
        ch = augment.eff_choice(item, a)
        if ch in ("unknown", "na", "none", "no") or (a.get("pid") and a.get("who") not in (None, "self")):
            continue
        q = a.get("q") or {}
        label = next((c.get("label") for c in q.get("choices", []) if c.get("id") == ch), ch)
        if (item, ch) in HYBRID_CHOICE:                      # the choice, and the count typed with it (nothing else said)
            n = re.search(r"(?<!\d)(\d{1,3})\s*개", v) or re.fullmatch(r"\s*(\d{1,3})\s*", v)
            out.append({"item": item, "value": f"{label} {n.group(1)}개" if n else str(label), "tag": HYBRID_CHOICE[(item, ch)]})
        for cl in CLAUSE.split(v) if v and (item in HYBRID_IDS or item in HYBRID_INERT) else []:
            if SAYS_NO.search(cl) or OTHERS.search(cl):    # a no, or another team's work: nothing of this one
                continue
            if item in HYBRID_IDS:
                for i in (CRANE_ID if HYBRID_IDS[item] == "crane_use" else PANEL_ID).findall(cl):
                    out.append({"item": item, "value": f"{i}: {v[:40]}" if item == "CF3" else f"{i} 사용", "ids": (HYBRID_IDS[item], i)})
            elif re.search(r"아르곤|질소|TIG|퍼지", cl) and not any(x.get("tag") == "INERT" and x["item"] == item for x in out):
                out.append({"item": item, "value": cl.strip()[:40], "tag": "INERT"})
        if item == "D7" and v and ch not in ("unknown", "na", "none", "no"):      # a pressure test with its medium and times
            out.append({"item": item, "value": v[:40], "tag": "PRESSURE"})
    return out


def compare(before, after, facts=None):
    """the alarms before and after the confirmed answers went in (design §8.1): new; kept (the same alarm — changed
    when its priority, E or score moved, or it stands on a confirmed answer now); gone. Every row of a pair one of
    whose works has confirmed facts carries those facts (what made the change, or what was weighed)."""
    facts = facts or {}
    k = lambda p, r: (p["key"], r["rule"], r["cause"], r["exposed"])
    B = {k(p, r): (p, r) for p in before["pairs"] for r in p["reasons"]}
    A = {k(p, r): (p, r) for p in after["pairs"] for r in p["reasons"]}
    num = lambda r: {x: r[x] for x in ("priority", "S", "E", "score")}

    def row(key, was, now):
        p, r = now or was
        src = [{"doc": d, "item": x["item"], "value": x["value"]} for d in (key[2], key[3]) for x in facts.get(d, [])]
        return {"key": key[0], "pair": p.get("id"), "rule": r["rule"], "name": r["name"], "cause": key[2], "exposed": key[3],
                "before": was and num(was[1]), "after": now and num(now[1]), "from": src,
                "moved": bool(was and now and num(was[1]) != num(now[1]))}
    new = [row(x, None, A[x]) for x in A if x not in B]
    gone = [row(x, B[x], None) for x in B if x not in A]
    kept = [row(x, B[x], A[x]) for x in A if x in B and (num(A[x][1]) != num(B[x][1])
            or any(e.get("confirmed") or e.get("submitted") for e in A[x][1].get("evidence", [])) or facts.get(x[2]) or facts.get(x[3]))]
    return {"new": new, "kept": kept, "gone": gone}


LABEL_RANK = {"판정보류": 1, "보수위험": 2, "확인위험": 3}


def _label(r):
    """확인위험 / 보수위험 / 판정보류 of a reason (a residual on a tied place is 보수위험: see _judge)"""
    return r.get("judgement") or ("확인위험" if r["E"] == 3 else "보수위험" if r["E"] == 2 else "판정보류")


def floor(before, after):
    """the day's judgement with the confirmed answers in, never below the documents' own: a reason the documents
    raised and the answers took away stays (marked 「문서 기준 유지」), a reason the answers made weaker keeps the
    documents' priority and score, and the pair keeps its place. Only a person lifts an alarm; a reading never does.
    -> a new judgement (after is not changed)."""
    k = lambda p, r: (p["key"], r["rule"], r["cause"], r["exposed"])
    rank = lambda r: (r["priority"], -r["score"], -LABEL_RANK.get(_label(r), 0))
    A = {p["key"]: p for p in after["pairs"]}
    pairs = []
    for p in after["pairs"]:
        pairs.append({**p, "reasons": list(p["reasons"])})
    by = {p["key"]: p for p in pairs}
    for p in before["pairs"]:
        if p["key"] not in A:
            by[p["key"]] = {**p, "reasons": [{**r, "floor": "gone"} for r in p["reasons"]]}
            pairs.append(by[p["key"]])
            continue
        q = by[p["key"]]
        now = {k(q, r): i for i, r in enumerate(q["reasons"])}
        for r in p["reasons"]:
            i = now.get(k(p, r))
            if i is None:
                q["reasons"].append({**r, "floor": "gone"})
            elif rank(r) < rank(q["reasons"][i]):          # the answers made it weaker: the documents' numbers stay
                q["reasons"][i] = {**q["reasons"][i], **{x: r[x] for x in ("priority", "S", "E", "score")}, "judgement": _label(r), "floor": "lowered"}
    for p in pairs:
        p["reasons"].sort(key=lambda h: (h["priority"], -h["score"], -h["when"]["min"]))
        top = p["reasons"][0]
        p.update(priority=top["priority"], score=top["score"], S=top["S"], E=top["E"], title=top["name"], forbidden=top["forbidden"],
                 judgement=_label(top))
    pairs.sort(key=lambda p: (p["priority"], -p["score"], -p["reasons"][0]["when"]["min"], -p["people"], p["a"], p["b"]))
    for i, p in enumerate(pairs, 1):
        p["id"] = f"P{i:02d}"
    stats = {**after["stats"], "pairs": len(pairs), "by_priority": {str(n): sum(p["priority"] == n for p in pairs) for n in (1, 2, 3)}}
    near = [n for n in after["near"] if not any(n["a"] in (p["a"], p["b"]) and n["b"] in (p["a"], p["b"]) for p in pairs)]
    return {**after, "pairs": pairs, "stats": stats, "near": near}


LAW_PENDING = "관련 조문은 국가법령정보센터 현행본 대조 전이라 표시하지 않음"
EQUIP_RULES = ("CRANE_LOTO", "POWER_LOTO", "CRANE_SHARE", "CRANE_CROSS", "SHARED_LOTO")
TOUCH = "앞 작업이 끝나는 시각에 바로 이어서 시작: 앞 작업이 늦어지면 겹침(실제 종료 확인 기록 없음)"
ZERO = "서류상 인원 0: 실제 퇴실 확인 아님"
REVERSED = "시간 역전"
REV_COLS = "칼럼 범위가 큰 번호부터 적힘"
NEXT_COL = "바로 옆 칼럼"


def _said_window_meets(place_txt, B):
    """the foreman's 「아래」 answer gives a time that overlaps that work's windows (no time: not enough for 금지)"""
    m = re.search(r"(\d{1,2}:\d{2})\s*[~-]\s*(\d{1,2}:\d{2})", place_txt)
    if not m:
        return False
    a, b = _m(m.group(1)), _m(m.group(2))
    b = b if b > a else b + 1440
    return any(a < y and x < b for x, y in B["wins"])


def _judge(rule, A, B):
    """One rule, A as its cause and B exposed → the reason (with S, E, words) or None."""
    p = _path(rule, A, B)
    if not p:
        return None
    wa, wb, mode, notes = p
    cap, place_txt = _place(mode, A, B, rule)
    if cap is None:
        return None
    why = []
    # upper and lower at once, the lower known to be below (same block, or the foreman said so): 멘토 손글씨 「상·하 병행
    # 절대로 불가」 — a forbidden pair like cutting over people, not a conditional one
    if rule.get("new_rule") and cap == 3 and place_txt.startswith("같은 블록"):
        cap, place_txt = 2, place_txt + "(같은 블록만으로는 전달 경로 미확인)"
    upper_lower = (rule["id"] == "OVERHEAD_WORK" and cap == 3 and place_txt.startswith("작업반장이 아래 작업이라고 답함")
                   and not (B["low"] is not None and A["high"] is not None and B["low"] >= A["high"])
                   and _said_window_meets(place_txt, B))         # the answer names that work and a time it overlaps
    e = 3 if rule["trigger"] == "direct" or upper_lower else 2
    if rule["trigger"] != "direct" and not upper_lower:
        why.append("경로가 생기려면 사건이 하나 더 있어야 함(재통전·같은 시각 배차·주행 구간 겹침 등)")
    if cap < 3:
        why.append(place_txt)
    e = min(e, cap)
    for c, words in notes:                             # this pair's own unknowns (a height, a level nobody wrote)
        e = min(e, c)
        why.append(words)
    # time
    ovs = overlaps(wa, wb) if wa and wb else []
    seq, touch, notes_after = None, False, []
    common = A["ids"]["blocks"] & B["ids"]["blocks"]
    if ovs and mode == "landed":
        return None                                  # the lift itself over ground work is LOAD_OVER; landed is what is left after
    if ovs:
        when = {"start": _hm(ovs[0][0]), "end": _hm(ovs[0][1]), "min": sum(b - a for a, b in ovs), "kind": "overlap",
                "segments": [[_hm(a), _hm(b)] for a, b in ovs]}
    elif not wa or not wb:
        if mode == "landed":
            return None
        when = {"start": "", "end": "", "min": 0, "kind": "unknown"}
        e = 1; why.append("한쪽의 작업 시간이 없어 겹치는지 확인 못 함")
    else:
        # the closest end -> start between the two works' own windows (with several windows the last end is not it);
        # a residual is left by the cause only (정비 뒤 사용, 절단 뒤 하부 작업) when the rule says so
        a_first = [(b0 - a1, "A", a1, b0) for a0, a1 in wa for b0, b1 in wb if b0 >= a1]
        b_first = [(a0 - b1, "B", b1, a0) for a0, a1 in wa for b0, b1 in wb if a0 >= b1]
        # a residual is left by the cause only (정비 뒤 사용, 절단 뒤 하부 작업) when the rule says so; the same block only
        # for 잔열·불씨 (sequence_same_block)
        # the same columns with no block number: only a work that handles what was left (잔재·청소·수거) is followed, as a
        # check (자료 R42-23·33-HOT: 같은 곳 잔재 취급; Codex final P3·L47)
        residue = (not common and not (A["ids"]["blocks"] and B["ids"]["blocks"]) and cap == 2
                   and RESIDUE.search(B["text_all"]) is not None)       # two different blocks written: not the same thing
        res_ok = (rule.get("sequence") or mode == "landed") and not (rule.get("sequence_same_block") and not common and not residue)
        # what is left up high falls where it was left: a residual is followed only to a place the documents tie to it
        # (a crane parked somewhere in the BAY, a place not written: asked while the work is on, not after)
        res_ok = res_ok and not (rule["id"] == "OVERHEAD_WORK" and cap == 1)
        # a test run after the repair reaches the runway's height (거더·고소작업대: 자료 EL13-FALL p343), not every block top
        # or the floor of the BAY afterwards
        res_ok = res_ok and not (rule["id"] == "CRANE_TEST" and not (B["girder"] or "MEWP" in B["tags"]))
        res_cands = (a_first if rule.get("sequence_first") == "cause" or mode == "landed" else a_first + b_first) if res_ok else []
        # an end that touches the other's start (간격 0) is asked whichever came first: a delay makes them meet
        touch_cands = [c for c in a_first + b_first if c[0] == 0] if mode != "landed" else []
        if res_cands:
            g, first, end, start = min(res_cands)
            residual = True
        elif touch_cands:
            g, first, end, start = min(touch_cands)
            residual = False
        else:
            return None
        touch = not residual
        seq = {"gap": g, "first": first}
        when = {"start": _hm(end), "end": _hm(start), "min": 0, "kind": "sequence", "gap": g,
                **({"touch": True} if g == 0 else {}), **({"residual": True} if residual else {})}
        e = 1
        if residual:
            left = (_residual(rule, first) or "잔불·증기·가스·잔압·잔류 인원").split("(")[0]
            why.append(f"작업 시간은 겹치지 않지만, 앞 작업이 끝나고 {g}분 뒤 시작: 잔류위험({left})이 없어졌다는 확인 기록이 없음")
            F = A if first == "A" else B
            if F.get("res_end") is not None:
                # the ember watch's end (T4) is a residual note only: never taken as the release (자료 HOT·p185 감시시간≠냉각 완료)
                notes_after.append(f"{F['d']['id']} 잔불 감시 종료 예정 {_hm(F['res_end'])}(반장 답) — 감시 종료는 잔류 해제 확인이 아님"
                                   + (" · 뒤 작업이 감시 중에 시작" if F["res_end"] > start else ""))
        else:
            why.append(TOUCH)                        # no residual rule: only a delay of the first work would make them meet
    touch = when["kind"] == "sequence" and touch
    if when["kind"] == "sequence" and not touch and mode in ("below", "path", "hot", "block", "paint") and (
            NEXT_COL in place_txt or "칸 떨어진 다른 블록" in place_txt):
        return None                                  # the next column is held for what moves or flies now, not for what is left
    zero = B["people"] == 0 and rule["id"] not in EQUIP_RULES
    if zero:                                         # 자료 MV03·Q06: 인원 합계 0만으로 무인을 확정하지 않는다
        e = 1; why.append(ZERO)
    elif B["people"] is None and rule["id"] not in EQUIP_RULES:
        why.append("위험을 받는 작업의 인원 수가 적혀 있지 않음")   # asked, not a lower exposure: a work has people (최종 검토 A12)
    for P in (A, B):
        if P["move_off"] and mode in ("path", "same_block", "link"):
            e = min(e, 2); why.append(f"{P['d']['id']}의 이동 예정 시각이 허가 시간 밖: 일정 불일치 확인")
    for P in (A, B):                                 # the window is kept (conservative), but not as a confirmed time
        if P["assumed_nd"]:
            why.append(f"{P['d']['id']} {REVERSED}({', '.join(P['assumed_nd'])}): 끝이 시작보다 일러 다음 날 종료로 계산함 — 익일인지 오기인지 확인")
        if P["rev_cols"] and mode not in ("link", "shared", "system"):
            why.append(f"{P['d']['id']} {REV_COLS}({', '.join(P['rev_cols'])}): 범위로 읽음 — 오기인지 확인")
    info_gap = e == 1 and (when["kind"] in ("unknown", "sequence") or cap == 1 or zero or any(c == 1 for c, _ in notes))
    gaps = list(why)                                   # every one of these is a thing not known or not confirmed
    if "평면 경로" in place_txt:                        # the score stands; the real outline and height are still asked
        gaps.append("평면 경로: 실제 하물 외곽·높이 확인 필요")
    why += notes_after                                 # shown, not a gap: the watch's end is said, its meaning is not release
    if not why:
        why.append("같은 시간에 " + place_txt + " — 두 작업이 이어지는 것이 서류로 확인됨")
    S = rule["S"]
    forbidden = bool(rule.get("forbidden")) or upper_lower
    if rule["id"] == "RADIATION" and all(f == "유해위험요소" for f, _ in A["tags"].get("RADIATION", [])):
        # the radiation is only in the hazards list: as before (2순위), and asked whether this work shoots it
        forbidden = False
        why.append(f"{A['d']['id']}의 방사선은 유해위험요소 칸에만 적힘: 이 작업이 촬영하는지 확인")
        gaps.append(why[-1])
    # a missing fact or an unconfirmed residual risk is asked about whatever the score (3순위 확인 필요)
    pri = 1 if forbidden and e == 3 else 2 if S * e >= 6 else 3 if S * e >= 3 or info_gap else 0
    # the label: a residual on a place the documents tie (same block · system · equipment: cap ≥ 2) is 보수위험 — the
    # relation is known and only its release is not (자료 p24 residual, p377); the score and priority stay as they are
    judgement = "확인위험" if e == 3 else "보수위험" if e == 2 or (when["kind"] == "sequence" and cap == 3 and not zero
                                                              and not any(c == 1 for c, _ in notes) and not touch) else "판정보류"
    ctx = _ctx(rule, A, B, cap)
    chain = [_fill(x, A, B, cap, ctx) for x in rule["chain"]]
    if rule["id"] == "TARGET_OCCUPIED" and "SEP" in B["tags"] and common:
        chain.insert(2, f"{_who(B)}가 그 블록의 러그·부재를 자르는 중이면 인양점·지지가 약해질 수 있다")
    return {"rule": rule["id"], "name": rule["name"], "mode": rule["mode"], "S": S, "E": e, "score": S * e, "priority": pri,
            "forbidden": forbidden, "cause": A["d"]["id"], "exposed": B["d"]["id"], "why_E": why, "gaps": gaps,
            **({"cause_kind": next(t_ for t_ in ("LIFT", "VEHICLE", "CART", "DROP", "SEP", "STAGE", "STAGE_SOFT") if t_ in A["tags"])}
               if rule["id"] == "ACCESS" else {}),
            "when": when, "sequence": seq, "relation": place_txt, "chain": chain, "judgement": judgement,
            "measures": rule["measures"], "cases": rule["cases"], "ask": rule["ask"],
            # an article is sent to the screen only when it was checked against the current text (law_checked); a new
            # rule's article waits for that check and is not shown as a basis (Codex 12)
            "law": rule["law"] if rule.get("law_checked") else "", **({} if rule.get("law_checked") else {"law_note": LAW_PENDING}),
            **{k: (_fill(rule[k], A, B, cap, ctx) if isinstance(rule.get(k), str) and "{" in rule[k] else rule.get(k))
               for k in ("headline", "accident", "story", "mechanism", "roles", "roles_short")},
            "evidence": _evidence(rule, A, B), "estimated": bool(B["lift_at"] and mode == "link") or bool(A["lift_at"] and not A["move"] and mode == "path")}


_BATCHIM_DIGIT = set("013678")


def _josa(word, pair):
    """은/는-style particle after a name: '0737 중량물인양이', 'WP-02가', 'OH-21-03을', 'MCC-4를'."""
    c = word.rstrip()[-1:]
    if "가" <= c <= "힣":
        has = (ord(c) - 0xAC00) % 28 != 0
    else:
        has = c in _BATCHIM_DIGIT or c in "LMNRlmnr"
    return word + (pair[0] if has else pair[1])


def _who(P):
    d = P["d"]
    return f"{d['id']} {d['label']}" if d["type"] == "permit" else f"WP-{d['id'][-2:]}"


def _residual(rule, first="A"):
    """what is left after the first work, by which one came first (화기가 먼저면 잔불, 도장이 먼저면 증기·도막)"""
    return (rule.get("residual_by_first") or {}).get(first) or rule.get("residual")


DEP_HARM = {"air": "산소결핍·흄 축적", "light": "조명 상실로 걸림·추락·대피 지연", "comm": "연락 두절로 구조 지연"}


def _dep_words(A, B):
    """VENT_LOTO's result by the function that stops (자료 p235·341): a fan → air, a light → light loss, not 산소결핍"""
    fn = set()
    for pid in B.get("dep_panels") or ():
        if pid in A["ids"]["power_loto"]:
            fn |= B["dep_fn_b"].get(pid, set())
    fn = (fn or set(A.get("dep_fn") or ())) - {"unknown"}
    if "CONFINED" not in B["tags"] and B.get("level") != "inside":
        if "SPARK" in B["tags"] and LOCAL_EXH.search(B.get("text_all") or ""):
            return {"dep_harm": "국소배기가 멈춰 흄 흡입", "dep_accident": "흄 흡입 위험"}
        return {"dep_harm": "조명이 꺼져 걸림·추락·대피 지연", "dep_accident": "조명 상실로 걸림·추락 위험"}
    if not fn:
        return {"dep_harm": "멈추는 기능에 따라 산소결핍·흄 축적(환기) 또는 대피 지연(조명)", "dep_accident": "기능 상실(종류 미확인) 위험"}
    harm = "·".join(DEP_HARM[k] for k in ("air", "light", "comm") if k in fn)
    return {"dep_harm": harm, "dep_accident": harm + " 위험"}


def _line_words(B):
    """LIFT_LINE's result by the kind of line the other work has on the block (자료 p306 MV10)"""
    kinds = []
    for t in (t for _, v in B.get("lines") or [] for t in _tokens(v)):
        k = next(((name, harm) for name, rx, harm in LINE_KIND if re.search(rx, t) and LINES.search(t)), None)
        if k and k not in kinds:
            kinds.append(k)
    if not kinds:
        return {"line_name": "연결선", "line_harm": "연결선 종류에 따라 질식·감전·끼임"}
    return {"line_name": "·".join(k[0] for k in kinds), "line_harm": "·".join(dict.fromkeys(k[1] for k in kinds))}


def _ctx(rule, A, B, cap):
    """the words a rule's text takes from this pair: what this hot work gives off (by its method — gas cutting is not
    an arc, grinding throws pieces; 자료 결과 후보 선택·LU11·HW08), and who can fall from a girder"""
    k = A.get("hot_kind") or set()
    if k:
        emit = ["불티"] + (["아크광"] if "arc" in k else []) + (["강한 빛·열"] if "gas" in k else []) + (["연삭 파편"] if "grind" in k else [])
        emit += ["흄"] + (["소음"] if "noise" in k else [])
        harm = ["화상"] + (["눈 손상(아크광)"] if "arc" in k else []) + (["눈 자극(강한 빛)"] if "gas" in k else []) \
            + (["파편 맞음"] if "grind" in k else []) + ["흄 흡입(같은 공기 공간·환기 방향이면)"]             + (["청력 손상(누적 소음)", "소음으로 신호·연락 방해"] if "noise" in k else [])
    else:                                             # the method is not written: no arc is claimed
        emit, harm = ["불티·열·흄(아크 용접이면 아크광)"], ["화상", "흄 흡입(같은 공기 공간이면)", "눈 손상(아크 용접이면)"]
    accident = "·".join(harm) + " 위험" if k else "화상·흄 흡입·눈 손상(아크 용접이면) 위험"
    return {"hot_emit": "·".join(emit), "hot_harm": "·".join(harm), "hot_accident": accident,
            "girder_fall": "·거더 위 정비자 추락" if A.get("girder") else "",
            "support_act": "블록을 들어 옮긴다" if A["d"]["type"] == "permit" and A["d"]["kind"] == "lifting" and not ({"SEP", "DROP", "SUPPORT_ADJ"} & set(A["tags"]))
            else "블록의 부재를 자르거나 해체한다",
            "gas_src": "오일 미스트가 퍼지면" if any(re.search(r"미스트", v) for _, v in B["tags"].get("FLAM_GAS", []))
            and not any(re.search(r"LPG|프로판|부탄|아세틸렌|수소|가연성", v) for _, v in B["tags"].get("FLAM_GAS", []))
            else "가스 용기·호스를 다루다 가연성 가스가 새면",
            # what a hot work outside sends into a confined space by its method (자료 PE15·PE12): an arc's light, gouging noise
            "arc_in": "·아크 용접이면 개구부로 들어오는 아크광에 눈 손상" if "arc" in k else "",
            "noise_in": "·가우징·연삭 소음으로 안팎 연락 방해" if "noise" in k else "",
            # a fibre sling by a hot work (재독 B L505): heat and sparks cut it
            "sling": "·섬유 슬링이면 불티·열에 끊어져 부재 낙하" if re.search(r"섬유\s*슬링|벨트\s*슬링|라운드\s*슬링|웨빙", A.get("text_all") or "")
            and "SPARK" in B["tags"] else "",
            "girder_fall_b": "·거더 위 수리자 추락" if B.get("girder") else "",
            **_dep_words(A, B), **_line_words(B),
            "load_extra": "(작업발판·작업대를 치면 흔들리거나 부서져 추락)" if B.get("level") == "top" or "MEWP" in B["tags"]
            else "(절단 중·임시 지지 부재를 치면 넘어짐)" if {"SEP", "DROP"} & set(B["tags"]) else "",
            "shared": ", ".join(sorted((A["ids"]["crane_loto"] & B["ids"]["crane_loto"]) | (A["ids"]["power_loto"] & B["ids"]["power_loto"]))) or "설비"}


def _fill(s, A, B, cap, ctx=None):
    a, b = _who(A), _who(B)
    crane = ", ".join(sorted(A["ids"]["crane_loto"] | A["ids"]["crane_use"])) or "크레인"
    panel = ", ".join(sorted(A["ids"]["power_loto"])) or "전원"
    hi = A["high"]
    ctx = ctx or {k: "" for k in ("hot_emit", "hot_harm", "hot_accident", "girder_fall", "girder_fall_b", "shared", "load_extra",
                                  "dep_harm", "dep_accident", "line_name", "line_harm", "arc_in", "noise_in", "sling", "support_act", "gas_src")}
    return s.format(a=a, b=b, a_ga=_josa(a, "이가"), b_ga=_josa(b, "이가"), a_ui=a + "의", b_ui=b + "의", a_wa=_josa(a, "과와"),
                    crane_eul=_josa(crane, "을를"), panel_eul=_josa(panel, "을를"), crane=crane, where=B["d"]["place"].replace("대조립21공장 ", ""),
                    block=", ".join(sorted(A["ids"]["blocks"] & B["ids"]["blocks"])) or "같은",
                    height=f"{hi:g}m" if hi else "높이 미확인",
                    reach=f"화재감시자 반경 {FIRE_REACH_M}m 기준" if cap == 3 else "실제 거리·차폐 미확인", **ctx)


_WANT = {"FIRE": ("SPARK", "SOLVENT"), "FIRE_GAS": ("SPARK", ("FLAM_GAS", "GAS_UNK")), "CONF_HOT": ("SPARK", "CONFINED"), "CONF_GAS": ("INERT", "CONFINED"), "LOAD_OVER": ("LIFT", None),
         "TARGET_OCCUPIED": ("LIFT", "CONFINED"), "CRANE_LOTO": ("CRANE_LOTO", "CRANE_USE"), "POWER_LOTO": ("POWER_LOTO", "POWER_USE"),
         "DROP_BELOW": ("DROP", None), "PRESSURE": ("PRESSURE", None), "RADIATION": ("RADIATION", None), "VEHICLE": ("VEHICLE", "MEWP"),
         "CRANE_SHARE": ("CRANE_USE", "CRANE_USE"), "CRANE_CROSS": ("CRANE_USE", "CRANE_USE"), "SUPPORT": (("SEP", "DROP"), None),
         "ACCESS": (("LIFT", "VEHICLE", "DROP", "SEP", "STAGE", "CART"), "CONFINED"), "HOT_PERSON": ("SPARK", None),
         "VENT_LOTO": (("POWER_LOTO", "CRANE_LOTO"), "CONFINED"), "CRANE_TEST": ("CRANE_LOTO", "MEWP"), "SHARED_LOTO": (("CRANE_LOTO", "POWER_LOTO"),) * 2,
         "OTHER_CRANE_REPAIR": ("CRANE_USE", "CRANE_LOTO"), "HOT_PANEL": ("SPARK", ("POWER_LOTO", "CRANE_LOTO")), "FIRE_SOLID": ("SPARK", "COMBUST"),
         "EGRESS_BLOCK": (("STAGE", "CART"), "SPARK"), "OVERHEAD_WORK": ("OVERHEAD", None), "CART": ("CART", "MEWP"), "CABLE_RUN": (("VEHICLE", "CART"), "SPARK"),
         "NOISE_SIGNAL": ("SPARK", "LIFT"), "WELD_RETURN": ("SPARK", "CONFINED"), "LIFT_LINE": ("LIFT", None), "GRIND_FLY": ("SPARK", None),
         "CONF_PAINT": ("SOLVENT", "CONFINED"), "MEWP_OVER": ("MEWP", None), "FIRE_SPREAD": ("COMBUST", None), "HELD_FIT": ("LIFT", "SPARK"),
         "EQUIP_IGNITION": (("MEWP", "POWER_USE"), "SOLVENT")}


def _evidence(rule, A, B):
    """The facts the judgement stands on: which document says what (what it is, when, where)."""
    out = []
    for P, t in zip((A, B), _WANT.get(rule["id"], (None, None))):
        t = next((x for x in t if x in P["tags"]), None) if isinstance(t, tuple) else t
        got = P["tags"].get(t) or []
        for field, value in got[:2] + [x for x in got[2:] if x[0].startswith(CONFIRMED)]:      # a confirmed answer is always shown
            out.append({"doc": P["d"]["id"], "field": field, "value": value, **({"confirmed": True} if field.startswith(CONFIRMED) else {})})
    for P in (A, B):
        t = ", ".join(f"{_hm(a)}–{_hm(b)}" for a, b in P["wins"]) or "시간 없음"
        if P["move"]:
            t += f" (이동 예정 {_hm(P['move'][0])}–{_hm(P['move'][1])})"          # planned, not observed (재독 B L16)
        if P.get("stage"):
            t += f" (확인된 이동 구간 {', '.join(f'{_hm(a)}–{_hm(b)}' for a, b in P['stage'])})"
        if P["d"].get("stage_written"):
            t += f" (서류에 적힌 단계 {', '.join(w['start'] + '–' + w['end'] for w in P['d']['stage_written'])})"
        if P["d"].get("full_end"):
            t += f" (전체 작업 끝 {P['d']['full_end']})"
        if P["lift_at"]:
            t += f" (크레인 인양 {', '.join(_hm(a) for a, _ in P['lift_at'])} 시작, 끝 시각 없음)"
        sub = P["d"].get("_sub") or {}               # a value from the foreman's submission says so (Codex A6)
        out.append({"doc": P["d"]["id"], "field": "시간" + (f"({SUBMITTED})" if sub.get("time") else ""), "value": t,
                    **({"submitted": True} if sub.get("time") else {})})
        out.append({"doc": P["d"]["id"], "field": "위치" + (f"({SUBMITTED})" if sub.get("place") else ""),
                    "value": P["d"]["place"].replace("대조립21공장 ", "") + (f" / 경로: {P['d']['route']}" if P["d"].get("route") else ""),
                    **({"submitted": True} if sub.get("place") else {})})
        if P["below"] and rule["id"] == "DROP_BELOW" and P is A:
            said = [v for v in A["below"] if (B["d"].get("company") and B["d"]["company"] in v) or (B["d"]["type"] == "permit" and B["d"]["id"] in v)]
            out.append({"doc": P["d"]["id"], "field": "답변(아래 작업)", "value": (said or P["below"])[0], "quote": True})
    return out


TAG_KO = {"SEP": "절단·해체", "SPARK": "화기", "SOLVENT": "유기용제", "CONFINED": "밀폐 진입", "INERT": "불활성가스", "LIFT": "크레인 인양", "DROP": "높은 곳 절단·해체",
          "PRESSURE": "압력시험", "RADIATION": "방사선", "VEHICLE": "차량 운반", "MEWP": "고소작업대", "CRANE_USE": "크레인 사용",
          "CRANE_LOTO": "크레인 정전", "POWER_LOTO": "전원 정전", "POWER_USE": "전원 사용", "CART": "수동 대차", "COMBUST": "가연물",
          "STAGE": "적치·통로 점유", "OVERHEAD": "상부 설치·취급"}
INFERRED = "작업명에서 추정: 사용물질에 용제 기재 없음"


def _override(d, wins):
    """A work with the time the safety team set (일정 변경 / 한쪽 중지): its windows replaced; a lift's move shifted
    with its start, or dropped when it no longer fits."""
    if not wins:
        return d
    extra = [w for w in wins if w.get("extra")]
    wins = [{k: v for k, v in w.items() if k != "extra"} for w in wins]
    nd = {**d, "windows": wins, "start": wins[0]["start"], "end": wins[-1]["end"], "extra_windows": [{k: v for k, v in w.items() if k != "extra"} for w in extra]}
    if d.get("move") and d.get("windows"):
        base = [w for w in wins if w not in nd["extra_windows"]] or wins
        delta = _m(base[0]["start"]) - _m(d["windows"][0]["start"])
        a, b = _win_m(d["move"])
        a, b = a + delta, b + delta
        fits = any(_win_m(w)[0] <= a and b <= _win_m(w)[1] for w in wins)
        nd["move"] = {"start": _hm(a), "end": _hm(b)} if fits else None
    return nd


SUBMITTED = "제출본 반영"


def _windows_ok(ws):
    return isinstance(ws, list) and all(isinstance(w, dict) and HM.fullmatch(str(w.get("start"))) and HM.fullmatch(str(w.get("end"))) for w in ws)


def _submitted(d, s):
    """a document with the place and this day's times the foreman's latest submission confirms (Codex A6, design §8.1):
    the same hybrid path as the confirmed answers, so it can add an alarm; the documents' own alarms are kept by floor().
    s: {place?, windows?}; a value equal to the document's, or not readable, changes nothing."""
    if not s:
        return d
    nd, sub = dict(d), {}
    place = str(s.get("place") or "").strip()
    if place and place != d["place"]:
        route = d.get("route") or ""
        nd.update(place=place, spans=safety.spans(place + " " + route), is_route=bool(route) or "→" in place)
        sub["place"] = d["place"]
    ws = s.get("windows")
    # the dates count: 08:00→10:00 and 08:00→next day 10:00 are different windows (Codex P1-4)
    key = lambda w: (w["start"], w["end"], bool(w.get("next_day") or w["end"] <= w["start"]), w.get("days") or 0)  # noqa: E731
    if ws and _windows_ok(ws) and [key(w) for w in ws] != [key(w) for w in d["windows"]]:
        ws = [{"start": w["start"], "end": w["end"], **({"next_day": True} if w.get("next_day") or w["end"] <= w["start"] else {}),
               **({"days": w["days"]} if w.get("days") else {})} for w in ws]
        nd.update(windows=ws, start=ws[0]["start"], end=ws[-1]["end"])
        sub["time"] = [f"{w['start']}~{w['end']}" for w in d["windows"]]
    if s.get("residual_end") and HM.fullmatch(str(s["residual_end"])):
        nd["residual_end"] = s["residual_end"]          # the ember check's end: a residual note only, never its release
        nd["residual_next_day"] = bool(s.get("residual_next_day"))
        sub["residual"] = True
    if s.get("stage") and _windows_ok(s["stage"]):
        nd["stage_windows"] = s["stage"]               # the part written (a lift's moving part): kept apart from the work
        sub["stage"] = True
    if s.get("stage_written") and _windows_ok(s["stage_written"]):
        nd["stage_written"] = s["stage_written"]       # the stage the document had (T6 「특정 단계만」): shown, not computed
    if s.get("full_end") and HM.fullmatch(str(s["full_end"])):
        nd["full_end"] = s["full_end"]                 # the whole work's end that day (the windows already reach it)
    if sub:
        nd["_sub"] = sub
    return nd


def detect(overrides=None, confirmed=None, submitted=None):
    """overrides: {doc_id: [{"start": "HH:MM", "end": "HH:MM"}, …]} — tests only (a schedule tried).
    confirmed: {permit_no: [records]} — the foremen's confirmed answers from their submissions (쌍 하이브리드).
    submitted: {doc_id: {place?, windows?}} — the place and times the latest submission confirms (Codex A6)."""
    D = safety.data()
    if confirmed:
        D = {**D, "permits": [{**p, "_confirmed": confirmed[p["permit_no"]]} if confirmed.get(p.get("permit_no")) else p for p in D["permits"]]}
    if submitted:
        D = {**D, **{k: [_submitted(p, submitted.get(p["id"])) for p in D[k]] for k in ("permits", "plans")}}
    R = rules()
    ov = {}
    for k, ws in (overrides or {}).items():
        if not isinstance(ws, list) or not all(isinstance(w, dict) and HM.fullmatch(str(w.get("start"))) and HM.fullmatch(str(w.get("end"))) for w in ws):
            raise ValueError(f"{k}: 시각은 00:00~23:59 형식이어야 합니다")    # refused, not read as a stop
        good = ws
        ov[k] = [{**({"start": w["start"], "end": w["end"]}), **({"next_day": True} if w["end"] <= w["start"] else {}),
                  **({"extra": True} if w.get("extra") is True else {})} for w in good]
    # a work stopped for the whole day (no window left) is not done that day: it meets nobody
    off = {k for k, v in ov.items() if not v}
    permits = [profile(_override(p, ov.get(p["id"]))) for p in D["permits"] if p["id"] not in off]
    plans = [profile(_override(p, ov.get(p["id"]))) for p in D["plans"] if p["id"] not in off]
    cand = [(a, b) for i, a in enumerate(permits) for b in permits[i + 1:]] + [(a, b) for a in permits for b in plans]
    pairs, near = [], []
    stats = {"candidates": len(cand), "nn": len(permits) * (len(permits) - 1) // 2, "rn": len(permits) * len(plans),
             "time": 0, "time_bay": 0, "path": 0, "sequence": 0, "unknown_time": 0, "unknown_place": 0}
    for X, Y in cand:
        both_t = bool(X["wins"] and Y["wins"])
        ov = both_t and bool(overlaps(X["wins"], Y["wins"]))
        rel = place_rel(X, Y, True, True)
        stats["time"] += ov
        stats["time_bay"] += ov and rel["kind"] in ("same", "near", "far")
        stats["unknown_place"] += ov and rel["kind"] == "unknown"
        stats["unknown_time"] += not both_t
        hits, seen = [], set()
        for rule in R["rules"]:
            for A, B in ((X, Y), (Y, X)):
                h = _judge(rule, A, B)
                if h and h["priority"] and (h["rule"], h["cause"], h["exposed"]) not in seen:
                    seen.add((h["rule"], h["cause"], h["exposed"]))
                    hits.append(h)
        hits.sort(key=lambda h: (h["priority"], -h["score"], -h["when"]["min"]))
        if hits:
            top = hits[0]
            confirmed = top["when"]["kind"] == "overlap" and top["E"] > 1     # E1 = a missing fact or a residual risk to ask about
            stats["path"] += confirmed
            stats["sequence"] += not confirmed
            a, b = X["d"], Y["d"]
            pairs.append({"a": a["id"], "b": b["id"], "key": f"{a['id']}|{b['id']}", "kind": "NN" if b["type"] == "permit" else "RN", "priority": top["priority"],
                          "score": top["score"], "S": top["S"], "E": top["E"], "title": top["name"], "forbidden": top["forbidden"],
                          "reasons": hits, "judgement": _label(top),
                          "people": sum(x for x in (a.get("workers"), b.get("workers")) if x)})
        else:
            why = _quiet(X, Y, rel)
            if why:
                near.append({"a": X["d"]["id"], "b": Y["d"]["id"], "why": why})
    pairs.sort(key=lambda p: (p["priority"], -p["score"], -p["reasons"][0]["when"]["min"], -p["people"], p["a"], p["b"]))
    for i, p in enumerate(pairs, 1):
        p["id"] = f"P{i:02d}"
    stats["pairs"] = len(pairs)
    stats["by_priority"] = {str(k): sum(p["priority"] == k for p in pairs) for k in (1, 2, 3)}
    near.sort(key=lambda n: (n["why"]["rank"], n["a"], n["b"]))
    return {"date": D["date"], "stats": stats, "pairs": pairs, "near": near, "overrides": ov,
            "rules": [{k: r.get(k) for k in ("id", "name", "mode", "S", "trigger", "forbidden", "post", "measures", "residual")} for r in R["rules"]],
            "levels": {k: R[k] for k in ("severity", "exposure", "priority")}}


def _quiet(X, Y, rel):
    """A pair that looks close but is not raised, and why — the closest reason first (researcher's step 6). A rule whose
    works fit but whose place does not is said so, not as 「규칙이 없음」 (자료 1.2·p399: 근접 거짓만으로 배제하지 않음)."""
    if rel["kind"] in ("none", "off"):
        return None
    tx, ty = set(X["tags"]), set(Y["tags"])
    # a shared kind of equipment, but not the same ID — the upstream/downstream relation is not in the documents
    for kind, loto, use in (("전원", "power_loto", "power_use"), ("크레인", "crane_loto", "crane_use")):
        for P, Q in ((X, Y), (Y, X)):
            if P["ids"][loto] and Q["ids"][use] and not P["ids"][loto] & Q["ids"][use]:
                return {"rank": 0, "text": f"같은 {kind} 번호는 아님({', '.join(sorted(P['ids'][loto]))} 정전 · {', '.join(sorted(Q['ids'][use]))} 사용)"
                        " — 상위·하위 전원이나 같은 주행로인지는 서류에 없어 미확인", "kind": "link"}
    ov = overlaps(X["wins"], Y["wins"]) if X["wins"] and Y["wins"] else []
    fit = [r["name"] for r in rules()["rules"] for A, B in ((X, Y), (Y, X)) if _path(r, A, B)]
    if rel["kind"] in ("same", "near") and not ov:
        g = [x for x in (gap_after(X["wins"], Y["wins"]), gap_after(Y["wins"], X["wins"])) if x is not None]
        if g and min(g) <= 180:
            return {"rank": 1, "text": (f"같은 곳이지만 시간이 떨어짐({min(g)}분 간격)" if min(g) else "같은 곳이지만 한 작업이 끝난 뒤 이어서 시작")
                    + (" · 앞 작업 뒤에 남는 위험 규칙의 조건(같은 블록·원인 작업이 먼저)에 맞지 않음" if fit else " · 앞 작업에 잔류위험 규칙이 없음"),
                    "kind": "time"}
        return None
    if ov and rel["kind"] == "far":
        # no distance is claimed (the column spacing is not measured): what is said is which rules were looked at
        return {"rank": 2, "text": f"같은 시간·같은 {rel['bay']}BAY, 칼럼 {rel['gap']}칸 떨어짐(실제 거리 미확인): 떨어져도 닿을 수 있는 "
                "화기×유기용제·가연물·압력시험·방사선 작업이 아니고, 낙하·인양 경로·운반·불티 규칙은 같은 칼럼·블록(화기는 바로 옆 칼럼까지)일 때 봄 — "
                "아크광·불티·흄은 실제 차광·거리 확인 전에는 닿지 않는다고 판단하지 않음", "kind": "far"}
    if ov:
        if fit:
            return {"rank": 3, "text": f"같은 시간·가까운 곳: 「{fit[0]}」 규칙의 장소 조건(같은 칼럼·블록·설비)이 서류로 이어지지 않음(실제 위치 미확인)",
                    "kind": "path"}
        kx = "·".join(TAG_KO[t] for t in sorted(tx) if t in TAG_KO) or "일반 작업"
        ky = "·".join(TAG_KO[t] for t in sorted(ty) if t in TAG_KO) or "일반 작업"
        return {"rank": 3, "text": f"같은 시간·가까운 곳이지만 두 작업 성질({kx} × {ky}) 사이에 위험 전달 규칙이 없음", "kind": "path"}
    return None


# 서류상 선후 계획 · 남은 확인 (design §8.4·§19.1): display only — a pair whose documents plan one work after the other
# (a rule's sequence reason, or a document that says 「…완료 후」) shows the plan as written and what is not confirmed.
# It never lifts an alarm, lowers a priority or ticks anything done; a new or corrected document is judged again.
SEQ_TITLE = "서류상 선후 계획 · 남은 확인"
SEQ_TEXT = "문서에 선후 계획이 있으나 실제 완료·잔류위험 해제·상대 반장 합의는 확인되지 않았습니다."
SEQ_SAID = re.compile(r"[^.。\n]{0,24}(?:완료\s*(?:후|뒤|이후)|끝난\s*(?:뒤|후)|끝나면|종료\s*(?:후|뒤|이후)|마친\s*(?:뒤|후)|선행\s*작업|후행\s*작업|"
                      r"이후\s*(?:시작|진행|착수|작업))[^.。\n]{0,24}")


def _said_seq(d):
    """the first sentence of a document that plans an order (「도장 완료 후 진입」), or None"""
    for t in [d.get("title"), d.get("detail"), d.get("place"), d.get("route")] + [v for _, v in (d.get("fields") or []) if isinstance(v, str)]:
        m = SEQ_SAID.search(str(t or ""))
        if m:
            return m.group(0).strip()
    return None


def sequence_plan(p, docs, rules_=None):
    """-> {title, text, plan: [{first, later, end, start, gap, rule}], said: [{doc, text}], left: [...]} or None"""
    seqs = [r for r in p["reasons"] if (r.get("when") or {}).get("kind") == "sequence"]
    said = [{"doc": i, "text": t} for i in (p["a"], p["b"]) if (t := _said_seq(docs.get(i) or {}))]
    if not seqs and not said:
        return None
    R = {r["id"]: r for r in (rules_ or rules())["rules"]}
    plan, seen = [], set()
    for r in seqs:
        first, later = (r["cause"], r["exposed"]) if (r.get("sequence") or {}).get("first", "A") == "A" else (r["exposed"], r["cause"])
        if (first, later) in seen:
            continue
        seen.add((first, later))
        plan.append({"first": first, "later": later, "end": r["when"]["start"], "start": r["when"]["end"], "gap": r["when"].get("gap"), "rule": r["name"]})
    residual = list(dict.fromkeys(_residual(R[r["rule"]], (r.get("sequence") or {}).get("first", "A")) for r in seqs
                                  if _residual(R.get(r["rule"], {}), (r.get("sequence") or {}).get("first", "A"))))
    left = (["앞 작업의 실제 완료(현장 확인 기록 없음)", "앞 작업의 남은 작업·재진입 계획 없음 확인"] + [f"잔류위험 해제: {x}" for x in residual]
            + ["두 작업반장의 순서 합의"])
    return {"title": SEQ_TITLE, "text": SEQ_TEXT, "plan": plan, "said": said, "left": left}


def annotate(det, docs):
    """display data added to a judgement (nothing it decides changes): the sequence plan of each pair"""
    R = rules()
    for p in det["pairs"]:
        p["seq_plan"] = sequence_plan(p, docs, R)
    return det

