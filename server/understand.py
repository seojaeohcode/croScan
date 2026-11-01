"""AI 답 이해 (TURN, design §1.4·§4): a foreman's free answer read by the on-premise model for the other open
questions it also answers. The model only proposes; this module checks every proposal and the foreman confirms it
(the 「AI 읽음」 card) before it becomes an answer. Nothing here writes a field.

What the model may do: pick an open question of this permit (by a short id), one of that question's own choices, a
short value, who it is about (우리/다른 팀) and whether it is planned or said done, with the words of the answer it
read it from. What the server checks: the reply has the schema's shape; the question is open and of this permit;
the choice is its own; a value is given only where the choice asks for one; the quoted words are one run of words
of the answer; the numbers and IDs of the value are in the sentence the words come from; that sentence does not
correct itself (「…이 아니라 …」: asked, not proposed) or speak of another team when the model says 우리; and the
value passes the same check as a typed answer (augment.check_value). Another team's words never become our answer
(kept apart), except 「다른 작업이 있음」 for the 병행여부 question. A failed or late call gives nothing: the rules'
reading stands.
"""
import re

from . import addendum, augment, cases, llm, need_catalog

SYSTEM = ("너는 조선소 위험작업허가서 사전검토에서 작업반장의 답을 읽는 도우미다. "
          "반장의 답(원문)을 읽고, '남은 질문' 가운데 이 답이 이미 답한 것만 고른다.\n"
          "규칙:\n"
          "1. 답에서 이어진 한 구절을 그대로 quote로 붙인다(여러 곳을 이어 붙이지 않는다). 구절이 없으면 고르지 않는다.\n"
          "2. 보기 c는 그 질문의 보기 id 중에서만 고른다. (값) 표시가 있는 보기만 v에 값을 짧게 쓴다. v는 quote 안의 말로만, 그 질문에 해당하는 내용만 쓴다(다른 질문의 내용을 섞지 않는다). 개수·인원은 숫자만 쓴다(두 군데 → 2).\n"
          "3. 다른 팀·다른 작업 이야기는 who=other로 표시한다. 우리 작업이면 who=self.\n"
          "4. 앞으로 할 일은 when=plan, 이미 했다고 말한 것은 when=done, 둘 다 아니면 none.\n"
          "5. 말하지 않은 값은 만들지 않는다. 모름은 고르지 않는다. 애매하면 고르지 않는다.")

# one made-up example (reviewed, marked synthetic in the design): the pattern, not values to copy
_EX_Q = ("남은 질문:\n"
         "Q1 실제 작업 인원은 몇 명인가요? 보기: value=인원(값)\n"
         "Q2 같은 시간·장소에 다른 작업이 있나요? 보기: yes=있음(값), no=없음\n"
         "Q3 진입 전에 전원을 차단하나요? 보기: yes=차단함, no=차단 안 함\n"
         "질문: 작업 방법을 알려 주세요.\n"
         "반장의 답: 저희는 다섯 명이 들어가고요, 옆에서 배관팀 두 명이 용접한다고 들었어요. 전원은 들어가기 전에 내릴 겁니다.")
_EX_A = ('{"props":[{"q":"Q1","c":"value","v":"5","who":"self","when":"plan","quote":"저희는 다섯 명이 들어가고요"},'
         '{"q":"Q2","c":"yes","v":"배관팀 2명 용접","who":"other","when":"plan","quote":"옆에서 배관팀 두 명이 용접한다고"},'
         '{"q":"Q3","c":"yes","v":"","who":"self","when":"plan","quote":"전원은 들어가기 전에 내릴 겁니다"}]}')
_EX2_Q = ("남은 질문:\n"
          "Q1 배관을 어떤 방법으로 자르나요? 보기: torch=가스 절단(값), saw=톱·그라인더 절단(값), none=자르지 않음\n"
          "Q2 잘라 낸 배관은 어떻게 옮기나요? 보기: text=옮기는 방법(값)\n"
          "질문: 작업 시간은요?\n"
          "반장의 답: 오전에만 해요. 배관은 그라인더로 두 군데 자르고, 자른 건 체인블록으로 내려 놓습니다.")
_EX2_A = ('{"props":[{"q":"Q1","c":"saw","v":"2","who":"self","when":"plan","quote":"배관은 그라인더로 두 군데 자르고"},'
          '{"q":"Q2","c":"text","v":"체인블록으로 내려 놓음","who":"self","when":"plan","quote":"자른 건 체인블록으로 내려 놓습니다"}]}')
# ---- 예시 은행 (design §4.5·§9): reviewed synthetic examples, one per slot group, written apart from the evaluation
# set's wording (tools/eval_phase1_cases.py). A reading shows 1~2 of them: the one of the group most of its open
# questions belong to, and the general one (another team, a no) — chosen from the question list alone, so a warm-up
# and the reading of the same question pick the same ones (the prompt cache holds).
GROUP = {"T": "time", "L1": "place", "L2": "place", "L7": "place", "D1": "place", "L3": "height", "HT2": "recovery", "H3": "recovery",
         "HT1": "method", "H1": "method", "H2": "method", "CF1": "method", "LO1": "method", "LI1": "equipment", "L5": "equipment",
         "D2": "equipment", "D4": "equipment", "LO3": "power", "LO4": "height", "B3": "other", "C3": "other", "LI2": "other",
         "CF2": "system", "D3": "system", "D5": "system", "workers": "workers", "W1": "workers"}
BANK = {
    "general": (_EX_Q, _EX_A),
    "recovery": (_EX2_Q, _EX2_A),
    "time": ("남은 질문:\n"
             "Q1 실제로 작업하는 시간대는요? 보기: partial=일부 시간만(값), yes=내내 함\n"
             "Q2 작업 장소의 BAY·칼럼은요? 보기: place=위치 입력(값)\n"
             "질문: 작업 방법을 알려 주세요.\n"
             "반장의 답: 점심 지나서 1시 반부터 3시까지만 하고, 나머지는 자재 준비예요.",
             '{"props":[{"q":"Q1","c":"partial","v":"13:30~15:00","who":"self","when":"plan","quote":"1시 반부터 3시까지만 하고"}],"next":"Q2"}'),
    "place": ("남은 질문:\n"
              "Q1 실제 작업 위치(BAY·칼럼)는요? 보기: place=위치 입력(값), whole=BAY 전체\n"
              "Q2 작업 인원은 몇 명인가요? 보기: value=인원(값)\n"
              "질문: 작업 시간은요?\n"
              "반장의 답: 오전에만 해요. 자리는 2BAY 20번 기둥 옆 블록 앞입니다.",
              '{"props":[{"q":"Q1","c":"place","v":"2BAY 20칼럼 블록 앞","who":"self","when":"plan","quote":"자리는 2BAY 20번 기둥 옆 블록 앞입니다"}],"next":"Q2"}'),
    "height": ("남은 질문:\n"
               "Q1 블록 위·옆·아래·안 중 어디서, 몇 m 높이에서 하나요? 보기: text=위치 입력(값)\n"
               "Q2 떼어낸 것은 어디로 내리나요? 보기: text=회수 방법(값)\n"
               "질문: 작업 시간은요?\n"
               "반장의 답: 2시부터 4시까지요. 블록 꼭대기, 바닥에서 대략 6미터쯤 되는 데서 합니다.",
               '{"props":[{"q":"Q1","c":"text","v":"블록 상부 6m","who":"self","when":"plan","quote":"블록 꼭대기, 바닥에서 대략 6미터쯤 되는 데서 합니다"}],"next":"Q2"}'),
    "method": ("남은 질문:\n"
               "Q1 무엇을 몇 개, 어떤 방법으로 자르나요? 보기: gas=가스절단(값), mech=그라인더(값), na=자를 것 없음\n"
               "Q2 같은 시간·장소에 다른 작업이 있나요? 보기: yes=있음(값), no=없음\n"
               "질문: 작업 위치는요?\n"
               "반장의 답: 3BAY 쪽이고, 고정 피스 네 개를 산소로 따낼 겁니다.",
               '{"props":[{"q":"Q1","c":"gas","v":"4","who":"self","when":"plan","quote":"고정 피스 네 개를 산소로 따낼 겁니다"}],"next":"Q2"}'),
    "equipment": ("남은 질문:\n"
                  "Q1 어느 크레인으로 옮기나요? 보기: text=크레인·방법(값)\n"
                  "Q2 옮기는 길(출발·지나는 곳·도착)은요? 보기: text=경로(값)\n"
                  "질문: 작업 시간은요?\n"
                  "반장의 답: 10시쯤 들어요. 천장크레인 OH-12-04 하나로 들고, 뒤집지는 않습니다.",
                  '{"props":[{"q":"Q1","c":"text","v":"OH-12-04 한 대, 반전 없음","who":"self","when":"plan","quote":"천장크레인 OH-12-04 하나로 들고, 뒤집지는 않습니다"}],"next":"Q2"}'),
    "power": ("남은 질문:\n"
              "Q1 전원은 언제 끊고 언제 복구하나요? 보기: text=시각·설비(값)\n"
              "Q2 제어반 앞에서만 하나요, 거더 위에도 올라가나요? 보기: front=제어반 앞만, text=거더·상부(값)\n"
              "질문: 작업 범위는요?\n"
              "반장의 답: 접촉기 교체예요. 판넬 PN-7은 8시에 내리고 10시 반에 다시 올립니다.",
              '{"props":[{"q":"Q1","c":"text","v":"PN-7 08:00 차단 10:30 복구","who":"self","when":"plan","quote":"판넬 PN-7은 8시에 내리고 10시 반에 다시 올립니다"}],"next":"Q2"}'),
    "other": ("남은 질문:\n"
              "Q1 같은 시간·장소에 알고 있는 다른 작업이 있나요? 보기: yes=있음(값), no=없음\n"
              "Q2 작업 인원은요? 보기: value=인원(값)\n"
              "질문: 작업 위치는요?\n"
              "반장의 답: 4BAY 18칼럼이에요. 바로 아래서 사상팀이 그라인딩한다고 들었고, 우리는 세 명입니다.",
              '{"props":[{"q":"Q1","c":"yes","v":"사상팀 그라인딩, 바로 아래","who":"other","when":"plan","quote":"바로 아래서 사상팀이 그라인딩한다고 들었고"},'
              '{"q":"Q2","c":"value","v":"3","who":"self","when":"plan","quote":"우리는 세 명입니다"}],"next":"none"}'),
    "system": ("남은 질문:\n"
               "Q1 들어가는 곳에 이어진 가스·공기 계통이 있나요? 보기: none=연결 없음, text=있음(값)\n"
               "Q2 안에서 무엇을 하나요? 보기: inspect=검사(값), clean=청소(값)\n"
               "질문: 작업 시간은요?\n"
               "반장의 답: 9시부터 한 시간이요. 질소 라인 N-3이 붙어 있는데 들어가기 전에 밸브 잠가 둡니다.",
               '{"props":[{"q":"Q1","c":"text","v":"질소 라인 N-3, 진입 전 밸브 잠금","who":"self","when":"plan","quote":"질소 라인 N-3이 붙어 있는데 들어가기 전에 밸브 잠가 둡니다"}],"next":"Q2"}'),
    "workers": ("남은 질문:\n"
                "Q1 작업 인원은 몇 명인가요? 보기: value=인원(값)\n"
                "Q2 감시·입회 인원은요? 보기: text=인원(값)\n"
                "질문: 작업 시간은요?\n"
                "반장의 답: 오후 내내요. 용접사 둘에 보조 하나 들어가고, 화기감시는 따로 한 명 붙습니다.",
                '{"props":[{"q":"Q1","c":"value","v":"3","who":"self","when":"plan","quote":"용접사 둘에 보조 하나 들어가고"},'
                '{"q":"Q2","c":"text","v":"화기감시 1명","who":"self","when":"plan","quote":"화기감시는 따로 한 명 붙습니다"}],"next":"none"}'),
    "negation": ("남은 질문:\n"
                 "Q1 떼는 러그가 있나요? 있으면 몇 개를 어떤 방법으로? 보기: gas=가스절단(값), na=떼는 러그 없음\n"
                 "Q2 같은 시간·장소의 다른 작업은요? 보기: yes=있음(값), no=없음\n"
                 "질문: 작업 내용은요?\n"
                 "반장의 답: 이번엔 떼는 러그는 없고 용접 상태만 봅니다. 옆 작업은 아직 모르겠어요.",
                 '{"props":[{"q":"Q1","c":"na","v":"","who":"self","when":"plan","quote":"이번엔 떼는 러그는 없고 용접 상태만 봅니다"}],"next":"Q2"}'),
}
_CASES = {"v": None, "at": 0.0}


def _group(q):
    item = q["item"].split(":")[0]
    return GROUP.get(item) or GROUP.get(item.split(".")[0]) or ("workers" if item.endswith("workers") else GROUP.get(item[:1], "general"))


def examples(qs):
    """the 1~2 examples a reading of these open questions shows: its main slot group's (a published case of that
    group first, when one is published: design §4.5) and the general one"""
    groups = {}
    for q in qs:
        g = _group(q)
        groups[g] = groups.get(g, 0) + 1
    order = list(BANK)
    top = max(groups, key=lambda g: (groups[g], -order.index(g) if g in order else -99)) if groups else "general"
    first = cases.example(top) or BANK.get(top) or BANK["general"]
    return [first] + ([BANK["general"]] if first is not BANK["general"] else [BANK["negation"]])


MAX_Q = 14          # the prompt stays short on a CPU: at most this many open questions, the most important first
MAX_PROPS, MAX_V, MAX_QUOTE = 5, 40, 40
WHO, WHEN = ("self", "other", "unknown"), ("plan", "done", "none")
KO_NUM = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "석": 3, "네": 4, "넷": 4, "다섯": 5, "여섯": 6, "일곱": 7,
          "여덟": 8, "아홉": 9, "열": 10, "스무": 20, "스물": 20}
OTHER_TEAM = re.compile(r"(?:옆|다른|타|상대|저쪽)\s*(?:팀|업체|반|작업|회사)|[가-힣]{1,6}팀(?:은|이|도|의|에서|이랑|하고|\s)")
PAST = re.compile(r"어제|그저께|지난\s*주|끝냈|끝났|마쳤|마친|했었")
CORRECTION = re.compile(r"아니라|아니고|정정|잘못\s*(?:적|썼|말)|바꿔\s*(?:주|말)")
# a 「없음·해당 없음·안 함」 choice needs the sentence to say no (measured 2026-10-31: 「3BAY 12-14 칼럼」 was read as
# 「떼는 러그 없음」, 「해당 없음」 and 「병행 없음」 at once)
NEGATIVE = ("no", "none", "na")
# not yet decided, or said under a condition (「바람 세면」, 「배정 보고 정할 거예요」): never a plan (Codex review 2026-10-31);
# 「측면·단면·도면…」 are nouns, not 「…면」 conditions
UNDECIDED = re.compile(r"미정|정할\s*(?:거|게|예정)|정해지|정하지\s*않|배정\s*(?:보고|봐서)|봐서|상황\s*(?:보고|봐)|그때\s*가서|아직\s*(?:모르|안\s*정)")
COND_V = re.compile(r"[가-힣](?<![측단전표후정반평곡상내외지노벽양앞옆도])면(?:\s|,)")
SET_PHRASE = re.compile(r"말씀드리면|다시\s*말하면|말하자면|그러면|그럼|이를테면")     # 「…면」 that is no condition


def _conditional(sent):
    return COND_V.search(SET_PHRASE.sub(" ", sent))


def _other(sent):
    """another team spoken of in the sentence (「우리 배관팀」 is ours)"""
    return OTHER_TEAM.search(re.sub(r"우리\s*(?:[가-힣]{1,6})?팀", "", sent))


# what a sentence speaks of when it answers these (eval 2026-10-31: 「러그는 가스절단으로 6개 떼요」 was read as the 회수
# answer). A word list does not decide for the model (최종 검토 2026-11-01: 「예열 2시간 포함입니다」 was thrown away for T6):
# a reading without these words is still shown, marked and not checked by default — the foreman decides
ITEM_NEEDS = {"HT2": re.compile(r"로프|체인\s*블록|달아|내려|내리|회수|모아|모은|적치|하부|아래"),
              # eval 2026-10-31: 「9시부터 11시까지」 alone was proposed as the 차단·복구 answer
              "LO3": re.compile(r"차단|끊|내리|내려|복구|살리|투입|잠금|LOTO|정지|멈추|멈춤"),
              # NL eval 2026-10-31: 「아까 러그 4개라고 했는데 잘못 말했고」 was proposed as 병행작업 있음 — another work must be said
              "B3": re.compile(r"옆|다른|타\s*(?:팀|업체|부서|반)|병행|동시|같이|함께|협력사|업체|[가-힣A-Za-z]{1,8}(?:팀|반)(?:이|은|도|에서|하고|이랑|랑|과|와|\s|$)|들었|한다고"),
              # and the whole window 「01:00~03:00요」 as the reason the time differs from the reference — a reason or a stage must be said
              "T6": re.compile(r"단계|절단|인양|분리|용접|가우징|준비|대기|기다|나눠|나누|먼저|다음|이후|때문|이유|걸리|걸려|오래|빨리|늦|추가|더\s")}
SAYS_NO = re.compile(r"없|않|아니|말고|무관|안\s*(?:함|합|해|하|씀|써|쓰|들어|나)|못\s*(?:함|합|해|하)")
WEAK = "질문 내용이 문장에 직접 보이지 않음: 맞으면 「다시 넣기」"


def _norm(s):
    return re.sub(r"[\s\"'“”‘’「」『』.,·…]", "", s or "")


def _sentence(quote, text):
    """the sentence (between . ? ! or line ends) in which the quoted words stand, or ''"""
    for sent in re.split(r"(?<=[.?!。])\s+|\n+", text):
        if _norm(quote) and _norm(quote) in _norm(sent):
            return sent
    return ""


UNITS = "명|군데|개|곳|대|번|시|분|칸|층|m|미터"


def _numbers(s, units=UNITS):
    """the numbers said in s with one of these units (any number when units is None), words too (두 군데 → 2)"""
    if units is None:
        out = {int(x) for x in re.findall(r"\d+", s)}
    else:
        out = {int(x) for x in re.findall(rf"(\d+)\s*(?:{units})", s)}
    for w, n in KO_NUM.items():
        if re.search(rf"(?<![가-힣]){w}\s*(?:{units or UNITS})", s):
            out.add(n)
    return out


def _ids(s):
    return {x.upper() for x in re.findall(r"[A-Za-z]+-?\d+(?:-\d+)*[A-Za-z0-9-]*|\d+[A-Za-z]+[A-Za-z0-9-]*", s)}


def _supported(q, v, sent):
    """every number and ID of the value is said in the sentence for what the question asks (a value is not made up
    or changed): people are numbers with 명, counts with 군데·개·곳, times may be said in the afternoon's 1~12"""
    if not v:
        return True
    item, text = q["item"], q.get("text", "")
    if item.endswith("workers") or re.search(r"인원|몇\s*명", text):
        nums = _numbers(sent, "명")
    elif re.search(r"몇\s*(?:군데|개|곳)|개수", text):
        nums = _numbers(sent, "군데|개|곳")
    elif item.startswith(("T0", "T1")) or re.search(r"\d\s*(?::|시)", v):
        said = _numbers(sent, None)
        nums = said | {n + 12 for n in said if 1 <= n <= 12 and re.search(rf"오후\s*{n}\s*시", sent)}
    else:
        nums = _numbers(sent, None)
    if any(int(x) not in nums for x in re.findall(r"\d+", v)):
        return False
    if not set(re.findall(r"\d+\.\d+", v)) <= set(re.findall(r"\d+\.\d+", sent)):   # 1.5m is not 15m
        return False
    return _ids(v) <= _ids(sent) | {x.upper() for x in re.findall(r"\d+", sent)}


def _slot(q):
    it = q["item"].split(":")[0]
    return addendum.ITEM.get(it) or addendum.ITEM.get(it.split(".")[0]) or re.sub(r"\s+", " ", q["text"])[:24]


def _qline(i, q):
    ch = ", ".join(f"{c['id']}={c['label']}{'(값)' if c.get('ask') else ''}" for c in q["choices"] if c["id"] != "unknown")
    return f"Q{i} {re.sub(r'\s+', ' ', q['text']).strip()[:120]} 보기: {ch}"


def _schema(qids, cids):
    return {"type": "object", "additionalProperties": False, "required": ["props"], "properties": {
        "next": {"type": "string", "enum": qids + ["none"]}, "props": {
        "type": "array", "maxItems": MAX_PROPS, "items": {"type": "object", "additionalProperties": False,
            "required": ["q", "c", "v", "who", "when", "quote"],
            "properties": {"q": {"type": "string", "enum": qids}, "c": {"type": "string", "enum": cids},
                           "v": {"type": "string", "maxLength": MAX_V}, "who": {"type": "string", "enum": list(WHO)},
                           "when": {"type": "string", "enum": list(WHEN)}, "quote": {"type": "string", "maxLength": MAX_QUOTE}}}}}}


def _valid(data, qids, cids):
    """the reply checked again against the schema it was asked for (the model server is not trusted to keep it)"""
    props = data.get("props") if isinstance(data, dict) else None
    if not isinstance(data, dict) or not ({"props"} <= set(data) <= {"props", "next"}) or not isinstance(props, list) or len(props) > MAX_PROPS:
        return False
    if "next" in data and data["next"] not in list(qids) + ["none"]:
        return False
    keys = {"q", "c", "v", "who", "when", "quote"}
    return all(isinstance(p, dict) and set(p) == keys and all(isinstance(p[k], str) for k in keys)
               and p["q"] in qids and p["c"] in cids and p["who"] in WHO and p["when"] in WHEN
               and len(p["v"]) <= MAX_V and len(p["quote"]) <= MAX_QUOTE for p in props)


def candidates(fields, answers, src):
    """The questions of src's permit still open after the rules have read src (what they already took from it is
    not asked of the model again): not src itself, not answered."""
    done = {a["qid"] for a in answers}
    open_, perms, _, _ = augment.questions(fields, answers)
    if src["qid"].startswith("FREE:"):                        # a free answer: read for the one permit of the file
        if len(perms) != 1:
            return []
        pid = perms[0]["permit_no"]
    else:
        pid = src["qid"].split(":")[1].split(">")[0]
    qs = [q for q in open_ if q["permit_no"] == pid and q["qid"] not in done and q["qid"] != src["qid"]
          and q.get("tier") != "extra" and any(c["id"] != "unknown" for c in q["choices"])
          and not q["item"].startswith(need_catalog.CHECKING)]      # checking questions: the foreman's own
    return sorted(qs, key=lambda q: q["prio"])[:MAX_Q]


def check(fields, answers, src, qs, props):
    """The model's proposals -> (props we may show, things kept apart, dropped [item, why, …]). Every rule above."""
    text, out, apart, dropped, seen = src.get("value") or "", [], [], [], set()
    qmap = {f"Q{i}": q for i, q in enumerate(qs, 1)}
    for p in props:
        q = qmap.get(str(p.get("q", "")))
        if not q:
            dropped.append([p.get("q"), "없는 질문"]); continue
        quote = (p.get("quote") or "").strip()
        if not quote or _norm(quote) not in _norm(text):                 # one run of the answer's own words
            dropped.append([q["item"], "구절이 답에 없음", quote]); continue
        sent = _sentence(quote, text)
        if not sent:                                                     # over a sentence end: what governs it is unclear
            dropped.append([q["item"], "인용이 문장 하나에 들지 않음", quote]); continue
        if CORRECTION.search(sent):                                      # 「4명이 아니라 6명」: asked, not proposed
            dropped.append([q["item"], "정정이 섞인 문장(따로 확인)", sent]); continue
        if augment.HEDGE.search(sent):                                   # 「아마 … 것 같아요」: not proposed (eval 2026-10-31)
            dropped.append([q["item"], "확실하지 않은 말", sent]); continue
        if UNDECIDED.search(sent) or _conditional(sent):                # 「배정 보고 정할 거예요」「바람 세면」: not a plan yet
            dropped.append([q["item"], "미정·조건이 붙은 말", sent]); continue
        # the whole answer to its own question given as the answer to another one (measured 2026-10-31: the place
        # 「3BAY 08-10 칼럼」 proposed as 「병행여부: 있음 · 3BAY 08-10 칼럼」); a free answer has no question of its own
        if not src["qid"].startswith("FREE:") and _norm(quote) == _norm(text):
            dropped.append([q["item"], "원래 질문의 답 전체를 다른 질문에 씀", quote]); continue
        who = p.get("who")
        if who == "self" and _other(sent):
            who = "unknown"                                              # the sentence also speaks of another team
        # another team's words never become our answer; only 「다른 작업이 있음」 for 병행여부 is about the other work
        about_other = q["item"] in augment.ABOUT_OTHERS or q["item"].split(".")[0] in augment.ABOUT_OTHERS
        now = p.get("when") != "done" and not PAST.search(sent)          # a work done before is not a work alongside
        if who != "self" and not (about_other and who == "other" and p.get("c") == "yes" and now):
            apart.append({"slot": _slot(q), "quote": quote, "why": "다른 팀·다른 작업 이야기" if who == "other" else "누구 이야기인지 불분명"})
            continue
        if not about_other and p.get("when") != "done" and PAST.search(sent):   # 「어제 … 끝냈어요」 is not today's plan
            dropped.append([q["item"], "지난 일을 말한 문장", sent]); continue
        c = next((c for c in q["choices"] if c["id"] == p.get("c") and c["id"] != "unknown"), None)
        if about_other and c and c["id"] in ("yes", "no") and not (_other(sent) or re.search(augment.CONC, sent)):
            dropped.append([q["item"], "다른 작업이 문장에 없음", sent]); continue
        if not c or q["qid"] in seen:
            dropped.append([q["item"], "보기가 아님" if not c else "같은 질문 두 번", p.get("c")]); continue
        need = ITEM_NEEDS.get(q["item"])
        weak = WEAK if need and c["id"] not in NEGATIVE and not need.search(sent) else ""
        if c["id"] in NEGATIVE and not SAYS_NO.search(sent):
            dropped.append([q["item"], "없다는 말이 문장에 없음", c["id"], sent]); continue
        v = augment.norm_ids((p.get("v") or "").strip()) if c.get("ask") else ""
        if c.get("ask") and not v:
            dropped.append([q["item"], "값 없음", c["id"]]); continue
        verbatim = False
        if not _supported(q, v, sent):                                      # 「네 명」 read as 9: not what was said
            # the foreman's own words for it instead — only when the quote stands in the answer letter for letter
            # (spaces aside): 「1.5m」 is never matched by a quote 「15m」 (Codex review 2026-10-31)
            lit = re.sub(r"\s+", "", quote) in re.sub(r"\s+", "", text)
            if lit and not augment.check_value(fields, {"qid": q["qid"], "choice": c["id"], "value": augment.norm_ids(quote), "q": q}):
                v, verbatim = augment.norm_ids(quote), True
            else:
                dropped.append([q["item"], "값이 문장과 다름", v, sent]); continue
        a = {"qid": q["qid"], "choice": c["id"], "value": v, "q": q, "by": src["qid"], "quote": quote}
        if (why := augment.check_value(fields, a)):                      # the same check as a typed answer
            dropped.append([q["item"], why, v]); continue
        seen.add(q["qid"])
        out.append({**a, "ai": True, "slot": _slot(q), "label": c["label"], "who": who, "when": p.get("when") or "none", "verbatim": verbatim,
                    **({"weak": weak} if weak else {})})
    # the same words read as the answer to several questions: kept only where a number or an ID of the value is in
    # them (「작업자 4명, 감시인 1명」); otherwise one phrase is being stretched over questions it does not answer
    uses = {}
    for x in out:
        uses.setdefault(_norm(x["quote"]), []).append(x)
    for x in [x for xs in uses.values() if len(xs) > 1 for x in xs]:
        if not (re.search(r"\d", x["value"]) or _ids(x["value"])) or x["verbatim"]:
            out.remove(x)
            dropped.append([x["q"]["item"], "같은 구절을 여러 질문에 씀", x["quote"]])
    return out, apart, dropped


def _head(qs, src_q):
    """the open questions and the question asked: known before the foreman answers"""
    asked = re.sub(r"\s+", " ", (src_q or {}).get("text") or "").strip()[:120]
    return "남은 질문:\n" + "\n".join(_qline(i, q) for i, q in enumerate(qs, 1)) + f"\n질문: {asked}"


# design §10.7 (measured 2026-10-31): the model server kept its cache only up to the start of the last message, so the
# list is a message of its own (answered with a fixed line) and the foreman's words come as the last one; the
# examples have the same shape
ACK = "알겠습니다. 반장의 답을 주세요."


def _turn(head, said):
    return [{"role": "user", "content": head}, {"role": "assistant", "content": ACK}, {"role": "user", "content": f"반장의 답: {said}"}]


def _ex(q):
    head, said = q.split("\n반장의 답: ")
    return _turn(head, said)


def _msgs(head, said, exs=None):
    out = [{"role": "system", "content": SYSTEM}]
    for q, a in exs or [(_EX_Q, _EX_A), (_EX2_Q, _EX2_A)]:
        out += _ex(q) + [{"role": "assistant", "content": a}]
    return out + _turn(head, said)


# the list each shown question was warmed with, per review: (session, question) -> [q]
_WARM = {}


async def warm(fields, answers, q, sid):
    """design §10.7: when question q is shown, the open questions an answer to it could also answer are read into
    the model's cache, so that reading the answer later reads only his words. Nothing is proposed or kept but the
    list (the reading of his answer uses the same list and drops what was answered meanwhile)."""
    qs = candidates(fields, [a for a in answers if a["qid"] != q["qid"]], {"qid": q["qid"], "q": q})
    if not qs:
        return {"status": "none"}
    try:
        meta = await llm.prefill("TURN_WARM", _msgs(_head(qs, q), "", examples(qs)), pri=llm.WARM)
    except llm.LlmFail as e:
        return {"status": "fail", "why": e.code}
    _WARM[(sid, q["qid"])] = qs                                       # kept only once it is in the cache
    if len(_WARM) > 2000:
        _WARM.clear()
    return {"status": "ok", "meta": meta}


def _fp(q):
    """what of a question the prompt and the checks use: its words and choices"""
    return (q["qid"], q.get("text"), tuple((c["id"], c.get("label"), bool(c.get("ask"))) for c in q.get("choices", [])))


async def read(fields, answers, src, deadline=60.0, think=0, out_tokens=480, sid=None, normalize_on=False):
    """-> {status: ok|none|fail, props, apart, meta, why}.
    think=0: measured 2026-10-31 on the CPU server, a per-request reasoning budget did not hold for a 3~5 proposal
    answer (608 tokens, 88 s, cut off); thinking off with the reviewed example read it in 18~31 s.
    When the question was warmed (warm), its list is used as it was read into the cache if it still holds every open
    question; what was answered or read by the rules meanwhile is in the list but not proposed."""
    qs = candidates(fields, answers, src)
    if not qs:
        return {"status": "none", "props": [], "apart": [], "why": "남은 질문이 없음"}
    open_ids = {q["qid"] for q in qs}
    wq = _WARM.get((sid, src["qid"])) if sid else None
    now_fp = {q["qid"]: _fp(q) for q in qs}
    if wq and open_ids <= {q["qid"] for q in wq} and len(wq) <= MAX_Q and all(_fp(q) == now_fp[q["qid"]] for q in wq if q["qid"] in now_fp):
        qs = wq        # the cached list (the same words and choices): only his words are read now; checked as they are now
    qids, cids = [f"Q{i}" for i in range(1, len(qs) + 1)], sorted({c["id"] for q in qs for c in q["choices"] if c["id"] != "unknown"})
    msgs = _msgs(_head(qs, src.get("q")), src.get("value", "").strip(), examples(qs))
    try:
        data, meta = await llm.call_json("TURN", msgs, _schema(qids, cids), think=think, out_tokens=out_tokens, deadline=deadline, sid=sid)
    except llm.LlmFail as e:
        return {"status": "fail", "props": [], "apart": [], "why": e.code, "detail": e.detail, "meta": e.meta}
    if not _valid(data, qids, cids):
        return {"status": "fail", "props": [], "apart": [], "why": "schema", "detail": "약속한 형식이 아님", "meta": meta}
    qmap = {f"Q{i}": q for i, q in enumerate(qs, 1)}
    late = [p for p in data["props"] if qmap.get(str(p.get("q", "")), {}).get("qid") not in open_ids]
    props, apart, dropped = check(fields, answers, src, qs, [p for p in data["props"] if p not in late])
    dropped += [[qmap[p["q"]]["item"], "이미 답했거나 규칙이 읽음"] for p in late if p.get("q") in qmap]
    # NORMALIZE (design §1.4·§4.1): a sentence that corrects itself is read once more, apart, for the one question
    # it was proposed for; what comes of it is checked like any reading and confirmed by the foreman
    fix = next(((qmap[p["q"]], p) for p in data["props"] if p.get("q") in qmap and p not in late
                and any(d[0] == qmap[p["q"]]["item"] and d[1].startswith("정정") for d in dropped)), None)
    if fix and not any(x["qid"] == fix[0]["qid"] for x in props) and normalize_on:
        got = await normalize(fields, answers, src, fix[0], fix[1].get("quote") or "", sid=sid)
        if got:
            props.append(got)
            meta["normalized"] = fix[0]["item"]
    for p in props:                                                   # 「미확인」: the facts of the question it did not say
        p["unread"] = need_catalog.atoms(p["q"]["item"], p["choice"], p.get("value") or "")["missing"]
    meta["dropped"] = dropped
    nxt = qmap.get(data.get("next") or "", {}).get("qid")
    return {"status": "ok" if props or apart else "none", "props": props, "apart": apart, "meta": meta,
            "next_qid": nxt if nxt in open_ids and nxt not in {p["qid"] for p in props} else None}


# ---- NORMALIZE (design §1.4): one more, narrow reading of a sentence that corrects itself (「4개가 아니라 6개」,
# 「아까 … 했는데 잘못 말했고 …」). The server splits it at the correction; the model only says which part holds the
# fact now, the choice and the value; the value must be said in that part. Nothing else is read.
def _sp(s):
    return re.sub(r"\s+", " ", s or "").strip()


NORM_SPLIT = re.compile(r"아니라|아니고|잘못\s*(?:적|썼|말)\S*|정정\S*|바꿔\s*(?:주|말)\S*")


async def normalize(fields, answers, src, q, quote, sid=None, deadline=30.0):
    """-> a proposal like check()'s (marked normalized) or None"""
    # NL eval 2026-10-31: a correction about the lug count was read again for 병행여부 and came back 「있음」 — another
    # work is never read out of a corrected sentence (asked instead), and the item's own words are needed as in check()
    if q["item"] in augment.ABOUT_OTHERS or q["item"].split(".")[0] in augment.ABOUT_OTHERS:
        return None
    text = src.get("value") or ""
    sent = _sentence(quote, text) or quote
    parts = [x.strip(" ,.") for x in NORM_SPLIT.split(sent, maxsplit=1)]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    cids = [c["id"] for c in q["choices"] if c["id"] != "unknown"]
    user = (f"질문: {_sp(q['text'])[:120]}\n보기: " + ", ".join(f"{c['id']}={c['label']}" for c in q["choices"] if c["id"] != "unknown")
            + f"\n앞부분: {parts[0]}\n뒷부분: {parts[1]}\n어느 부분이 지금 맞는 사실인지(after=뒷부분, before=앞부분, none=알 수 없음), 보기와 값을 고르라.")
    schema = {"type": "object", "additionalProperties": False, "required": ["part", "c", "v"], "properties": {
        "part": {"type": "string", "enum": ["after", "before", "none"]}, "c": {"type": "string", "enum": cids + ["none"]},
        "v": {"type": "string", "maxLength": MAX_V}}}
    try:
        data, _ = await llm.call_json("NORMALIZE", [{"role": "system", "content": "정정이 섞인 말에서 지금 맞는 사실의 부분과 보기만 고른다. 말하지 않은 값은 만들지 않는다."},
                                                    {"role": "user", "content": user}], schema, think=0, out_tokens=60, deadline=deadline, sid=sid)
    except llm.LlmFail:
        return None
    if not isinstance(data, dict) or data.get("part") not in ("after", "before") or data.get("c") not in cids:
        return None
    part = parts[1] if data["part"] == "after" else parts[0]
    c = next(c for c in q["choices"] if c["id"] == data["c"])
    v = augment.norm_ids((data.get("v") or "").strip()) if c.get("ask") else ""
    if c.get("ask") and not v:
        return None
    if c["id"] in NEGATIVE and not SAYS_NO.search(part):
        return None
    need = ITEM_NEEDS.get(q["item"])
    weak = WEAK if need and c["id"] not in NEGATIVE and not need.search(part) else ""
    if OTHER_TEAM.search(part) or augment.HEDGE.search(part) or not _supported(q, v, part):
        return None
    a = {"qid": q["qid"], "choice": c["id"], "value": v, "q": q, "by": src["qid"], "quote": part}
    if augment.check_value(fields, a):
        return None
    return {**a, "ai": True, "slot": _slot(q), "label": c["label"], "who": "self", "when": "none", "verbatim": False, "normalized": True,
            **({"weak": weak} if weak else {})}


# ---- PHRASE (design §1.4·§10.3·§10.5): the wording of the next 1~2 questions, prepared in the background. The model
# picks one of the server's wordings — the rule question as it is, its plain short form, or the short form after one
# of the foreman's own earlier answers it relates to — never writes a question. At most PHRASE_MAX per review.
PHRASE_MAX, PHRASE_REFS = 8, 6
_PHRASED, _PHRASE_N = {}, {}


def _words(s):
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", s or "")} - {"작업", "있나요", "알려", "주세요", "하나요", "인가요"}


def phrase_text(q, how, ref=None):
    short = need_catalog.FALLBACK.get(need_catalog.key_of(q["item"]))
    if how == "short" and short:
        return short
    if how == "ref" and short and ref and (_words(ref) & (_words(q["text"]) | _words(_slot(q)))):
        return f"앞에서 「{ref[:40]}」라고 하셨습니다. {short}"
    return q["text"]


async def phrase(answers, targets, sid=None, deadline=40.0):
    """-> {qid: {text, how}} for up to 2 questions about to be asked; {} when not prepared (the rule wording stands)"""
    if not targets or (sid and _PHRASE_N.get(sid, 0) >= PHRASE_MAX):
        return {}
    targets = targets[:2]
    key = (sid, tuple(_fp(q) for q in targets), tuple((a["qid"], a.get("value")) for a in answers if not a.get("pid"))[-PHRASE_REFS:])
    if key in _PHRASED:
        return _PHRASED[key]
    refs = [a for a in answers if not a.get("pid") and len((a.get("value") or "").strip()) >= 4][-PHRASE_REFS:]
    tids, rids = [f"T{i}" for i in range(1, len(targets) + 1)], [f"R{i}" for i in range(1, len(refs) + 1)]
    user = ("다음 질문:\n" + "\n".join(f"{t} {_sp(q['text'])[:120]}" for t, q in zip(tids, targets))
            + "\n반장의 앞 답:\n" + ("\n".join(f"{r} {_sp(a['value'])[:60]}" for r, a in zip(rids, refs)) or "(없음)")
            + "\n질문마다 문구 방식을 고르라: keep=그대로, short=짧게, ref=관련된 앞 답 하나를 짚고 짧게(r에 그 번호).")
    schema = {"type": "object", "additionalProperties": False, "required": ["out"], "properties": {"out": {"type": "array", "maxItems": len(tids),
              "items": {"type": "object", "additionalProperties": False, "required": ["t", "v", "r"], "properties": {
                  "t": {"type": "string", "enum": tids}, "v": {"type": "string", "enum": ["keep", "short", "ref"]},
                  "r": {"type": "string", "enum": rids + ["none"]}}}}}}
    if sid:
        _PHRASE_N[sid] = _PHRASE_N.get(sid, 0) + 1
    try:
        data, _ = await llm.call_json("PHRASE", [{"role": "system", "content": "질문 문구 방식만 고른다. 새 문장을 쓰지 않는다."},
                                                 {"role": "user", "content": user}], schema, think=0, out_tokens=60, deadline=deadline,
                                      sid=sid, pri=llm.WARM)
    except llm.LlmFail:
        return {}
    out = {}
    for x in (data.get("out") or []) if isinstance(data, dict) else []:
        if not isinstance(x, dict) or x.get("t") not in tids or x.get("v") not in ("keep", "short", "ref"):
            continue
        q = targets[tids.index(x["t"])]
        ref = refs[rids.index(x["r"])]["value"] if x.get("r") in rids else None
        text = phrase_text(q, x["v"], ref)
        out[q["qid"]] = {"text": text, "how": x["v"] if text != q["text"] else "keep", "base": q["text"]}
    _PHRASED[key] = out
    if len(_PHRASED) > 2000:
        _PHRASED.clear()
    return out
