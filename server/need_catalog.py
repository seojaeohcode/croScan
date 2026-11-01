"""「왜 묻나요?」 (design §3.1·§3.3·§19.2): for each question item, what croScan uses the answer for, and the law a
rule that reads the answer cites. Shown: the observation (the question's own signal: what is missing or does not fit
in the document), the need (one line: what the answer is used for — the code's real use, not a wish) and the basis.

A basis is shown only when it holds (design §3.4): an article of a pair rule that actually reads this answer, checked
against the current text on 국가법령정보센터 (`law_checked` in pair_rules.json) and fitting what the rule checks
(`law_fit` 맞음). A weak or unchecked one is not shown, nor a company procedure whose text croScan does not have; a
question about the document's own words needs no basis beyond the observation. No new duty is stated.
"""
import json
import re
from pathlib import Path

RULES = {r["id"]: r for r in json.loads((Path(__file__).resolve().parent / "pair_rules.json").read_text(encoding="utf-8"))["rules"]}
# the current text the citations were checked against (2026-10-31)
SOURCES = {
    "안전보건규칙": ("산업안전보건기준에 관한 규칙", "시행 2026.3.2 고용노동부령 제450호", "https://www.law.go.kr/법령/산업안전보건기준에관한규칙"),
    "원자력안전법": ("원자력안전법", "시행 2026.5.19", "https://www.law.go.kr/법령/원자력안전법"),
    "산업안전보건법": ("산업안전보건법", "시행 2026.10.27 법률 제22122호", "https://www.law.go.kr/법령/산업안전보건법"),
}
ARTICLE = re.compile(r"(안전보건규칙|원자력안전법|산업안전보건법)?\s*(제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?)(?:\(([^()]*)\))?")

# item -> (what the answer is used for, the pair rules that read it). Checked against where each answer is used
# (augment.py, pairs.py, checklist_spec.json, reflect.py; Codex review 2026-10-31): a rule is linked only when the
# answer changes what it finds.
NEED = {
    "T0": ("다른 작업과 시간이 겹치는지 계산하려고 묻습니다", []),
    "T1": ("신청 시간 전체인지 실제 작업 구간인지 나눠 겹침을 계산하려고 묻습니다", []),
    "T2": ("날마다 작업하는지 나눠 겹침을 계산하려고 묻습니다", []),
    "T3": ("위험 단계 시각으로 겹친 쌍의 검토 순서를 정하려고 묻습니다", []),
    "T4": ("잔불 감시 종료까지 시간 겹침을 확인하려고 묻습니다", []),
    "T5": ("끝나는 시각이 다음 날로 넘어가는지 확인하려고 묻습니다", []),
    "T6": ("참고 작업시간과 크게 다른 이유를 확인하려고 묻습니다", []),
    # research412 2.7 (2026-10-31 자료 보강): 주야간 체크와 시간의 상충(N2~N5 MT14·N4-MT15), 야간·교대 지원과 인계(N1
    # MT12), 대기·중단·교대 중 상태(N1 MT07·N2 MT09·N3 MT11·N5 MT07) — answers are recorded, they decide no pair
    "T7": ("서류에 체크한 주간·야간과 적힌 시간이 다른지 확인하려고 묻습니다", []),
    "T8": ("야간·교대 시간의 지원(조명·감시·구조)과 인계를 기록하려고 묻습니다", []),
    "T9": ("멈추거나 교대하는 동안 차단·받침·통제가 유지되는지 기록하려고 묻습니다", []),
    "L1": ("같은 BAY·칼럼의 다른 작업과 겹치는지 보려고 묻습니다", []),
    "L2": ("실제로 작업하는 지점을 다른 작업과 맞춰 보려고 묻습니다", []),
    "L3": ("위아래로 겹치는 작업(떨어짐)을 보려고 묻습니다", ["DROP_BELOW"]),
    "L4": ("블록별 작업 날짜와 순서를 기록하려고 묻습니다", []),
    "L5": ("매단 하물·차량이 지나는 길 아래의 작업을 보려고 묻습니다", ["LOAD_OVER", "VEHICLE"]),
    "L6": ("통제 예정 범위를 기록해 출입 위험을 확인하려고 묻습니다", []),
    "L7": ("적힌 칼럼 범위가 실제 작업점인지 보려고 묻습니다", []),
    "B": ("빈칸을 채워 서류를 완성하려고 묻습니다", []),
    "B3": ("같은 시간·장소의 다른 작업을 알려고 묻습니다", []),
    "C3": ("같은 시간·장소의 다른 작업을 알려고 묻습니다", []),
    "B4": ("누락된 호선·공사 정보를 보완하려고 묻습니다", []),
    "C1": ("빠진 위험의 관리 설명을 기록하려고 묻습니다", []),
    "C2": ("추가정보가 어떤 위험에 해당하는지 나누려고 묻습니다", []),
    "C2h": ("추가정보의 작업 분류를 채우려고 묻습니다", []),
    "C4": ("중량·정격하중의 상충 값을 기록하려고 묻습니다", []),
    "C5": ("앞 답과 추가 전달이 다른 것을 정리하려고 묻습니다", []),
    "C6": ("답과 서류가 다른 것이 정정인지 확인하려고 묻습니다", []),
    "D1": ("같은 블록·설비를 쓰는 다른 작업을 찾으려고 묻습니다", ["CRANE_LOTO", "POWER_LOTO", "TARGET_OCCUPIED"]),
    "D2": ("같은 크레인을 쓰거나 그 크레인이 정비 중인지 보려고 묻습니다", ["CRANE_LOTO", "CRANE_SHARE", "CRANE_CROSS"]),
    "D3": ("가스가 사람이 들어간 공간으로 들어가는지 보려고 묻습니다", ["CONF_GAS"]),
    "D4": ("같은 전원을 쓰는 다른 작업을 보려고 묻습니다", ["POWER_LOTO"]),
    "D5": ("진입 구획에 이어진 공급 계통을 보려고 묻습니다", ["CONF_GAS"]),
    "X1": ("같은 크레인을 쓰거나 정비 중인지 보려고 묻습니다", ["CRANE_LOTO", "CRANE_SHARE"]),
    "X2": ("가스 공급이 다른 작업 공간과 이어지는지 기록하려고 묻습니다", []),
    "X3": ("인양 전 퇴실 확인 담당자를 기록하려고 묻습니다", []),
    "X4": ("자르는 부재가 다른 작업을 받치는지 기록하려고 묻습니다", []),
    "X5": ("끊는 전원을 다른 작업이 쓰는지 기록하려고 묻습니다", []),
    "X6": ("반장 간 시간 협의에 쓸 후보를 기록하려고 묻습니다", []),
    "H1": ("보수 범위·개수로 참고시간과 분리 위험을 확인하려고 묻습니다", []),
    "H2": ("불티·흄·가스가 생기는 방식을 알려고 묻습니다", []),
    "H3": ("떼어 낸 부재가 떨어지지 않게 받치는지 보려고 묻습니다", ["DROP_BELOW"]),
    "CF1": ("안에서 하는 일과 진입 방식에 따라 위험을 나누려고 묻습니다", ["CONF_HOT"]),
    "CF2": ("밀폐공간에 이어진 배관·계통이 차단되는지 보려고 묻습니다", ["CONF_GAS"]),
    "CF3": ("진입 공간의 환기·송기·조명이 어느 전원에 물려 있는지 기록하려고 묻습니다", []),
    "CF4": ("밀폐공간 안에서 화기(용접·절단)를 하는지와 그 방법을 알려고 묻습니다", []),
    "CF5": ("도장·세정할 구획에 남은 화기가 있는지 들은 것을 기록하려고 묻습니다", []),
    "D6": ("수전구역의 통전·시운전 설비와 차단 확인자를 기록하려고 묻습니다", []),
    "D7": ("압력시험의 매체와 가압·감압 시각을 기록하려고 묻습니다", []),
    "HT1": ("러그 수량·공법으로 참고시간과 위험을 확인하려고 묻습니다", []),
    "HT2": ("잘라 낸 러그를 어떻게 내리는지, 아래에 작업이 있는지 보려고 묻습니다", ["DROP_BELOW"]),
    "LI1": ("인양 방법과 경로 아래의 작업을 보려고 묻습니다", ["LOAD_OVER", "CRANE_SHARE"]),
    "LI2": ("들어 옮길 블록 안·위의 작업을 보려고 묻습니다", []),
    "LI3": ("같은 크레인 정비나 같은 주행로의 다른 크레인 운행을 알려고 묻습니다", []),
    "LO1": ("정비 범위에 따른 참고시간과 위험을 확인하려고 묻습니다", []),
    "LO3": ("차단·복구 계획과 함께 멈추는 설비를 기록하려고 묻습니다", []),
    "LO4": ("정비자의 상부 접근에 따른 추락 위험을 확인하려고 묻습니다", []),
    "LO5": ("전원이 들어간 상태로 측정하는 단계(아크·감전 노출)가 있는지 확인하려고 묻습니다", []),
    "LO6": ("같은 주행로의 다른 크레인 운행이나 복구 전 확인할 다른 팀 작업을 알려고 묻습니다", []),
    "W1": ("감시·입회 인원을 작업인원과 구분해 기록하려고 묻습니다", []),
    "workers": ("작업 공간에 있는 사람 수(위험에 노출되는 인원)를 알려고 묻습니다", []),
    "A1": ("적으신 시간을 오전·오후 하나로 읽으려고 다시 묻습니다", []),
    "A2": ("적으신 시간이 어느 날짜인지 정하려고 다시 묻습니다", []),
    "A3": ("숫자 없는 시간을 시각으로 바꾸려고 다시 묻습니다", []),
    "A4": ("거꾸로 적힌 칼럼 범위를 한 가지로 읽으려고 다시 묻습니다", []),
    "A5": ("작업 끝보다 이른 잔불 확인 시각이 다음 날인지 다시 묻습니다", []),
    "U1": ("적으신 말을 한 가지 뜻으로 읽으려고 다시 묻습니다", []),
}


# the risk weight W (1~5) of an item: what goes wrong in the pair and checklist judgement when it is not known
W = {"T0": 5, "T1": 5, "T2": 4, "L1": 5, "L7": 4, "L2": 4, "L3": 4, "L5": 4, "B3": 4, "C3": 4, "CF1": 5, "CF2": 5, "HT2": 4,
     "H3": 4, "LI1": 4, "LI2": 4, "LO1": 3, "LO3": 4, "LO4": 3, "H1": 3, "H2": 3, "HT1": 3, "workers": 3, "W1": 2, "B": 2,
     "C1": 2, "C2": 2, "C2h": 2, "C4": 2, "B4": 1, "T5": 2, "T6": 2, "T3": 3, "T4": 3, "L4": 2, "L6": 3,
     "T7": 3, "T8": 3, "T9": 3, "CF3": 4, "LI3": 4, "LO5": 4, "LO6": 4, "CF4": 4, "CF5": 3, "D6": 4, "D7": 3,
     "AI:referent": 3, "AI:act_scope": 3, "AI:dependency": 4, "AI:doc_mismatch": 4}
# C6: the answer and the document disagree (asked once: which is right; design §3.5)
CHECKING = ("A1.", "A2.", "A3.", "A4.", "A5.", "U1.", "C5.", "C6.")

# ---- 카탈로그 행 (design §3.1): what each slot is, what makes it asked, when it counts as met, whether it is
# required, its weight, the effort, who can answer it and the plain fallback wording (when a phrasing is not ready)
TYPE = {"T": "시간", "L": "장소", "B": "빈칸", "C": "상충·설명", "D": "설비·계통", "X": "쌍 확인", "H": "공법", "CF": "공법", "HT": "공법",
        "LI": "인양", "LO": "정비", "W": "인원", "A": "다시 묻기", "U": "다시 묻기", "workers": "인원"}
# required: a pair rule, the checklist or the document's own completeness reads it; it keeps its ask (issue(reserve))
# and comes before the optional ones; an AI cannot lower it (design §3.1)
REQUIRED = {"T0", "T1", "T2", "L1", "L3", "L5", "L7", "B", "B3", "workers", "D1", "D2", "D3", "D4", "D5", "H1", "H2", "H3",
            "CF1", "CF2", "HT1", "HT2", "LI1", "LI2", "LO1", "LO3", "LO4", "C4", "C5", "C6"}
# who can answer it: 본인 계획 1, 본인 범위의 일부 정보 0.5 (what he heard of other work), 타 팀·당일 측정 0 (never asked)
OWNER = {"B3": "self_partial", "C3": "self_partial", "LI2": "self_partial", "X6": "self_partial", "LI3": "self_partial",
         "LO6": "self_partial", "CF5": "self_partial"}
A_VALUE = {"self": 1.0, "self_partial": 0.5, "other": 0.0}
FALLBACK = {
    "T0": "작업하는 날짜와 시작·끝 시각을 알려 주세요.", "T1": "실제로 작업하는 시간대를 알려 주세요.", "T2": "날마다 같은 시간에 작업하나요?",
    "T5": "끝나는 시각이 다음 날로 넘어가나요?", "T6": "참고 작업시간과 다른 이유를 알려 주세요.",
    "L1": "실제 작업 위치(BAY·칼럼)를 알려 주세요.", "L3": "블록 위·옆·아래·안 중 어디서, 몇 m 높이에서 하나요?",
    "L5": "옮기는 길(출발·지나는 곳·도착)을 알려 주세요.", "L7": "적힌 칼럼 범위가 실제 작업 위치인가요?",
    "B": "빈칸의 값을 알려 주세요.", "B3": "같은 시간·장소에 알고 있는 다른 작업이 있나요?", "workers": "작업 인원은 몇 명인가요?",
    "D1": "어느 블록·설비에서 하나요?", "H1": "용접부 보수인가요, 부재 교체인가요? 몇 군데인가요?", "H2": "어떤 방법·가스로 자르거나 용접하나요?",
    "H3": "떼어낸 부재는 무엇으로 받쳐 어디로 내리나요?", "CF1": "안에 들어가서 무엇을 하나요?", "CF2": "들어가는 곳에 이어진 가스·공기 계통이 있나요?",
    "HT1": "러그 몇 개를 어떤 방법으로 떼나요?", "HT2": "떼어낸 러그는 무엇으로 받아 어디에 내리나요?",
    "LI1": "어느 크레인으로 옮기나요?", "LI2": "옮기기 전 블록 안·위의 작업이나 붙은 것이 있나요?", "LO1": "점검인가요, 수리·교체인가요?",
    "LO3": "전원은 언제 끊고 언제 복구하나요?", "LO4": "제어반 앞에서만 하나요, 거더·상부에도 올라가나요?",
    "C4": "중량과 정격하중 중 어느 값이 맞나요?", "C5": "앞 답과 추가 전달 중 어느 쪽이 맞나요?", "C6": "답과 서류 중 어느 쪽이 맞나요?",
    "T4": "작업 뒤 잔불 확인은 몇 시까지 하나요?", "T7": "체크한 주간·야간과 적힌 시간이 서로 맞나요?",
    "T8": "야간·교대 시간의 조명·감시·구조 지원과 인계는 어떻게 하나요?", "T9": "멈추거나 교대하는 동안 차단·받침·통제는 유지하나요?",
    "CF3": "안의 환기팬·송기·조명은 어느 전원에 물려 있나요?", "LI3": "같은 크레인 정비나 같은 주행로의 다른 크레인 운행이 있나요?",
    "LO5": "전원이 들어간 상태로 측정하는 단계가 있나요?", "LO6": "같은 주행로의 다른 크레인 운행이나 복구 전 확인할 다른 팀 작업이 있나요?",
    "A4": "거꾸로 적힌 칼럼 범위는 어느 범위인가요?", "CF4": "안에서 용접·절단 같은 화기를 하나요?",
    "CF5": "도장할 구획의 화기가 끝났다고 들었나요?", "D6": "통전·시운전 중인 설비가 있나요?", "D7": "압력시험 매체와 가압·감압 시각은요?",
}


def _type(key):
    m = re.match(r"[A-Z]+", key)
    return TYPE.get(key) or TYPE.get(m.group(0) if m else "", "기타")


def row(item):
    """the catalog row of a question item (design §3.1): slot_id, type, trigger, met, required, W, burden, owner, fallback"""
    k = key_of(item)
    need, rules = NEED.get(k, ("", []))
    atoms_ = ATOMS.get(k, [])
    return {"slot_id": k, "type": _type(k), "trigger": need, "met": " + ".join(a[1] for a in atoms_ if a[3]) or "답 또는 「해당 없음」",
            "required": k in REQUIRED, "W": W.get(k, 2), "burden": "선택" if k in ("T2", "L7", "LO4", "B3", "LI2", "CF2") else "입력",
            "owner": OWNER.get(k, "self"), "fallback": FALLBACK.get(k, ""), "rules": rules,
            "atoms": [{"id": a[0], "label": a[1], "required": a[3]} for a in atoms_]}


def catalog():
    """every row, for the tools and the 근거 지도"""
    return [row(k) for k in NEED]


# ---- 원자 슬롯 (design §3.1): a question that bundles facts keeps them apart — LO3's 차단·복구·시험운전·영향 설비 are
# four facts. (id, label, how it is said: a regex or the choices that say it, required to count as met)
ATOMS = {
    "LO3": [("cut", "차단 시각", r"(?:\d{1,2}(?::\d{2})?\s*시?(?:\s*\d{1,2}\s*분)?|오전|오후|점심|아침|저녁|정오|작업\s*(?:전|후|끝))[^,.]{0,10}(?:차단|끊|내리|내려)|(?:차단|끊|내리|내려)[^,.]{0,10}(?:\d{1,2}(?::\d{2})?\s*시?(?:\s*\d{1,2}\s*분)?|오전|오후|점심|아침|저녁|정오|작업\s*(?:전|후|끝))", True),
            ("restore", "복구 시각", r"(?:\d{1,2}(?::\d{2})?\s*시?(?:\s*\d{1,2}\s*분)?|오전|오후|점심|아침|저녁|정오|작업\s*(?:전|후|끝))[^,.]{0,10}(?:복구|살리|살려|투입|재가동)|(?:복구|살리|살려|투입|재가동)[^,.]{0,10}(?:\d{1,2}(?::\d{2})?\s*시?(?:\s*\d{1,2}\s*분)?|오전|오후|점심|아침|저녁|정오|작업\s*(?:전|후|끝))", True),
            ("test", "시험운전", r"시험\s*운전|시운전|주행|권상|시험\s*없|안\s*함", False),
            ("affect", "함께 멈추는 설비", r"환기|조명|팬|함께\s*(?:멈|꺼)|영향|멈추는\s*(?:설비|것)\s*없|다른\s*설비", False),
            # N5 MT12 (p355): the end written is the repair's, or the test·withdrawal·hand-over's; N5 MT05: a restore midway
            ("handover", "종료의 뜻(수리 완료/인계까지)", r"인계|운전\s*(?:부서|팀)|철수|수리\s*(?:완료|만)|시험\s*(?:까지|후\s*종료)", False),
            ("midway", "중간 복구", r"중간\s*(?:에\s*)?(?:복구|투입)|다시\s*(?:끊|차단)|재차단|중간\s*복구\s*없", False),
            ("other_lock", "다른 팀 잠금", r"다른\s*팀[^,.]{0,8}잠금|잠금[^,.]{0,6}(?:없|있)|공동\s*잠금", False)],
    # N3 MT09 (p274): by what means it is lowered and where it is put — said as an act ('로프로 내려', '하부 적치함에'),
    # not a word ('로프 점검', '하부 작업자 있음' answer neither)
    "HT2": [("means", "회수 수단", r"(?:로프|체인\s*블록|호이스트|크레인|슬링|바구니|윈치)\S{0,3}\s*(?:으로|로)?\s*(?:내려|내리|받아|달아|매달아|회수)|"
                                  r"(?:내려|내리|받아|달아)[^,.;\n]{0,6}(?:로프|체인|호이스트|크레인|바구니)|손으로\s*(?:내려|받아|들어)", False),
            ("where", "내릴 곳", r"(?:하부|바닥|지상|정반|적치장|수거함|적치함|팔레트|보관함|반출장)\s*(?:에|으로|로)?\s*(?:적치|안착|내려\s*놓|놓|보관|적재|모아)|"
                                 r"(?:적치장|수거함|적치함|팔레트|보관함|반출장)(?:에|으로|로)|하부\s*적치", False)],
    # N2 MT07 (p246): the supply cut, kept while inside, and its restore·other teams' supply or test — all three
    "CF2": [("isolate", "차단·격리", r"(?:차단|격리|맹판|블라인드|밸브\s*잠|공급\s*중지)(?![^,.;\n]{0,6}(?:안\s*(?:함|해)|않|불가|못))", True),
            ("keep", "진입 중 유지", r"진입\s*(?:중|동안)[^,.;\n]{0,8}(?:유지|계속)|(?:유지|계속)[^,.;\n]{0,8}(?:진입|퇴실)|퇴실\s*(?:후|까지)", True),
            ("restore", "복구·다른 팀 공급·시험", r"복구[^,.;\n]{0,10}\d|\d{1,2}\s*(?::\d{2}|시)[^,.;\n]{0,10}복구|다른\s*팀[^,.;\n]{0,15}(?:없|안)|"
                                                 r"(?:압력\s*)?시험[^,.;\n]{0,6}(?:없|안)|공급\s*(?:예정\s*)?없", True)],
    "HT1": [("method", "절단 방법", ("gas", "plasma", "mech", "na"), True), ("count", "러그 개수", r"\d+\s*개|(?<![가-힣])(?:한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*개", False)],
    "H1": [("scope", "보수 범위", ("local", "replace"), True), ("count", "개수", r"\d+\s*(?:군데|곳|개|장)|(?<![가-힣])(?:한|두|세|네|다섯)\s*(?:군데|곳|개|장)", False)],
    "LI2": [("inside", "블록 안·위 작업", r"작업|인원|명|취부|용접|도장|사람|없", False), ("attached", "붙어 있는 것", r"배관|발판|전선|케이블|호스|붙|없", False)],
    "B3": [("what", "다른 작업", ("no",) + ("yes",), True), ("when_where", "시간·장소", r"\d|시|오전|오후|BAY|칼럼|옆|아래|위|같은|근처", False)],
}


# a clause that settles nothing: undecided, to be checked, unable, uncertain (its atom does not count as said)
UNSURE = re.compile(r"미정|확인\s*필요|확인\s*중|확인\s*예정|가능한지|여부|불가|모름|모르|할지|될지|인지\s*(?:확인|모름|모르)|아마|협의\s*중")


def atoms(item, choice, value):
    """an answer's atomic facts -> {have: [labels], missing: [labels], required_missing: [labels]}. A no-choice
    (없음·해당 없음) meets the whole question; 「모름」 meets nothing."""
    out = {"have": [], "missing": [], "required_missing": []}
    k = key_of(item)
    if choice in ("na", "none", "no") and k in ATOMS:
        out["have"] = [a[1] for a in ATOMS[k]]
        return out
    for aid, label, how, req in ATOMS.get(k, []):
        if choice == "unknown":
            ok = False
        elif isinstance(how, tuple):
            ok = choice in how
        else:                       # said in a settled clause (not 「미정」·「확인 필요」·「불가」 …)
            ok = any(re.search(how, cl) and not UNSURE.search(cl)
                     for cl in re.split(r"[,;\n/]|(?<!\d)\.(?!\d)|그리고|지만", value or ""))
        out["have" if ok else "missing"].append(label)
        if req and not ok:
            out["required_missing"].append(label)
    return out


def score(q):
    """S = W·M·A − B (design §3.2): W the item's weight; M how much is missing (1 not known or conflicting, 0.5 a part
    known — the rules set q['m']); A whether the foreman can answer it (1 his own plan, 0.5 what he heard of other
    work, 0 another team's or the day's measurement); B the effort (0.2 a tap, 0.5 something to type)"""
    key = f"AI:{q['ai_kind']}" if q.get("ai_kind") else key_of(q["item"])
    tap = any(not c.get("ask") and c["id"] != "unknown" for c in q.get("choices", []))
    m = q.get("m", 1.0)
    a = A_VALUE.get(OWNER.get(key, "self"), 1.0) if not q.get("ai_kind") else 1.0
    return W.get(key, 2) * m * a - (0.2 if tap else 0.5)


# related facts of the same subject and stage asked in one bubble (design §3.2 step 9): the second is shown with the
# first and answered on its own (one 「예」 never settles both)
MERGE = [("HT1", "HT2"), ("H2", "H3"), ("LO3", "LO4"), ("LI1", "L5"), ("CF1", "CF2"), ("L1", "L3")]


def order(qs):
    """the order of asking (design §3.2): a check of what was said first (상충·주체·범위), then the rules' required
    questions by S, then the rules' others, then the AI's, then as the rules had it (prio), the page, the meaning key.
    The extra tier stays last. An AI question never takes the place of a rule question within the 12 asks
    (2026-10-31 safety review: an AI question of weight 4 came before HT1, the cutting method the pair rules read, and
    could push it to 「담당 확인」); it is asked only with asks left. Then at most two related rule questions of one
    permit go together (MERGE): the second follows the first and both carry each other's id."""
    out = sorted(qs, key=lambda q: (q.get("tier") == "extra", not q["item"].startswith(CHECKING), bool(q.get("ai_kind")),
                                    not row(q["item"])["required"], -score(q), q["prio"], q.get("page") or 0, q.get("qid", "")))
    for q in out:
        q.pop("with", None)
        q.pop("with_of", None)
    i = 0
    while i < len(out):
        q = out[i]
        if not q.get("ai_kind") and not q["item"].startswith(CHECKING) and "with_of" not in q:
            mate = next((b for a, b in MERGE if a == key_of(q["item"])), None) or next((a for a, b in MERGE if b == key_of(q["item"])), None)
            j = next((j for j in range(i + 1, len(out)) if key_of(out[j]["item"]) == mate and out[j].get("permit_no") == q.get("permit_no")
                      and out[j].get("tier") == q.get("tier") and "with_of" not in out[j] and not out[j].get("ai_kind")), None)
            if j is not None:
                p = out.pop(j)
                first, second = (q, p) if any(a == key_of(q["item"]) for a, _ in MERGE) else (p, q)   # the pair's own order
                out[i:i + 1] = [first, second]
                first["with"], second["with_of"] = second["qid"], first["qid"]
                i += 2
                continue
        i += 1
    return out


def articles(law):
    """'안전보건규칙 제146조제1항제4호(크레인 작업 시의 조치: …)·제139조(…)' -> [(law name, 조, title)]: each article
    with the law it belongs to (carried over from the one before)"""
    out, name = [], None
    for m in ARTICLE.finditer(law or ""):
        name = m.group(1) or name
        if name:
            out.append((name, m.group(2), (m.group(3) or "").strip()))
    return out


def basis_of(rule_ids):
    """the checked, fitting articles of these rules: [{grade, ref, title, rule, rev, url}] (each article once)"""
    out, seen = [], set()
    for rid in rule_ids:
        r = RULES.get(rid) or {}
        if r.get("law_fit") != "맞음" or not r.get("law_checked"):
            continue
        for name, art, title in articles(r.get("law")):
            if (name, art) in seen or name not in SOURCES:
                continue
            seen.add((name, art))
            full, rev, url = SOURCES[name]
            out.append({"grade": "법령", "ref": f"{name} {art}", "title": title, "rule": r.get("name") or rid,
                        "rev": f"{full} {rev} · {r['law_checked'][:10]} 대조", "url": url})
    return out


def key_of(item):
    item = item.split(":")[0]
    if item.endswith(".workers"):
        return "workers"
    if item.startswith(("B1.", "B2.")):
        return "B"
    if item.startswith("C5."):
        return "C5"
    if item.startswith("C6."):
        return "C6"
    return item if item in NEED else item.split(".")[0]


def why(q):
    """{observe, need, basis: [...]} for a question, or None"""
    need, rules = NEED.get(key_of(q["item"]), (None, []))
    if not need:
        return None
    return {"observe": q.get("signal") or "", "need": need, "basis": basis_of(rules)}
