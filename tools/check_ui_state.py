"""반장 화면 상태 함수 (Codex 검토 A1·A2·A11) — app.js의 순수 함수를 꺼내 node로 돌린다.

  python tools/check_ui_state.py

A1  mergeState: 409로 서버 답을 받아도 아직 보내지 않은 답(새로 적은 답·고친 답·지운 답)이 남는다. 서버에 같은
    질문의 다른 답(카드 확인·다른 화면)이 있으면 덮어쓰지 않고 clash로 돌려준다.
A2  staleReadings·pruneReadings·resumeClose: 답을 지우거나 바꾸면 그 읽기가 끝나고, 마지막 읽기가 끝나면
    (어느 갈래든) 마무리 대기가 이어진다.
A11 ckSig·ckTakeAi: 늦게 온 빈·실패 AI 결과는 체크리스트(제출 내용)를 바꾸지 않는다.
QA2 (Codex QA #99 검토) 1 출력 목록=그날 문서 전부 · 2 확인 기록은 작업일 키 · 3 출력 직전 최신 판 검증 · 4 제출본 ID에
    묶인 확인·출력 · 5 읽기 둘이면 warm·phrase 즉시 취소.
PS  preSubmitView (팀장 요청 2026-10-31): 제출 직전 확인 창의 핵심 정보 — 제출되는 값(검토 결과·반영본 칸 값)
    그대로, 날짜 묶기·다음 날 표시·팀 이름 위치·모름/답하지 않음/빈칸·체크리스트 남은 수를 맨 위에.
입력칸 초안이 다른 질문으로 가지 않는 흐름(draftQ)은 DOM이 있어야 해서 브라우저에서 손으로 확인한다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OK = []


def check(name, cond):
    OK.append(bool(cond))
    print(("OK   " if cond else "FAIL ") + name)


def part(js, start):
    """one top-level statement of app.js from its first line: a function to its closing brace, a const to its ';'"""
    a = js.find(start)
    if a < 0:
        raise KeyError(start)
    depth, seen, i, fn = 0, False, a, start.startswith(("function", "async function"))
    quote = None
    while i < len(js):
        ch = js[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
            seen = seen or ch == "{"
        elif ch in ")]}":
            depth -= 1
            if fn and seen and depth == 0 and ch == "}":
                return js[a:i + 1]
        elif ch == ";" and depth == 0 and not fn:
            return js[a:i + 1]
        i += 1
    raise ValueError(start)


def run(code):
    try:
        r = subprocess.run(["node", "-e", code], capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        print(r.stderr)
        return {}
    return json.loads(r.stdout.strip().splitlines()[-1])


JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
LIB = "\n".join(part(JS, s) for s in ("const saidKey = ", "const sentOf = ", "const ansSig = ", "function mergeState(",
                                       "const staleReadings = ", "function pruneReadings(", "function resumeClose(",
                                       "const ckSig = ", "function ckTakeAi(", "const draftStays = "))

A1 = r"""
const q = (qid, choice, value, x = {}) => ({ qid, choice, value, ...x });
const ids = (l) => l.map((a) => `${a.qid}=${a.value}${a.pid ? "@" + a.pid : ""}`);
const out = {};
// a card confirmed (revision moved) while Q2 was being sent: the server has Q1 and the reading for Q5, not Q2
let m = mergeState([q("Q1", "t", "3명")], [q("Q5", "t", "가스절단", { pid: "p1" })], [q("Q1", "t", "3명"), q("Q2", "t", "09시 시작")], { Q1: saidKey(q("Q1", "t", "3명")) });
out.keep = [ids(m.answers), m.clash.length];
// the card's reading answered Q2 itself: not sent over it, given back as clash
m = mergeState([q("Q1", "t", "3명")], [q("Q2", "t", "10시", { pid: "p2" })], [q("Q1", "t", "3명"), q("Q2", "t", "09시 시작")], sentOf([q("Q1", "t", "3명")]));
out.clashAdopted = [ids(m.answers), ids(m.clash)];
// another screen typed Q2 otherwise
m = mergeState([q("Q1", "t", "3명"), q("Q2", "t", "11시")], [], [q("Q1", "t", "3명"), q("Q2", "t", "09시 시작")], sentOf([q("Q1", "t", "3명")]));
out.clashTyped = [ids(m.answers), ids(m.clash)];
// taken back here (Q3) and not yet sent: it stays gone
m = mergeState([q("Q1", "t", "3명"), q("Q3", "t", "A")], [], [q("Q1", "t", "3명")], sentOf([q("Q1", "t", "3명"), q("Q3", "t", "A")]));
out.removed = ids(m.answers);
// taken back here but changed elsewhere since: the server's stays
m = mergeState([q("Q1", "t", "3명"), q("Q3", "t", "B")], [], [q("Q1", "t", "3명")], sentOf([q("Q1", "t", "3명"), q("Q3", "t", "A")]));
out.removedElse = ids(m.answers);
// changed here only (모름 after taking the first answer back): the new one goes
m = mergeState([q("Q1", "t", "가스절단 6개")], [], [q("Q1", "unknown", "")], sentOf([q("Q1", "t", "가스절단 6개")]));
out.changed = [m.answers.map((a) => a.choice), m.clash.length];
// the server has it already as it is here (spaces aside): no clash, no double
m = mergeState([q("Q2", "t", "09시 시작")], [], [q("Q2", "t", "09시 시작 ")], {});
out.same = [ids(m.answers), m.clash.length];
// not known what the server had (an older 임시저장): the server's answers as they are
m = mergeState([q("Q1", "t", "3명")], [], [q("Q1", "t", "3명"), q("Q2", "t", "x")], null);
out.unknown = ids(m.answers);
// an adopted reading for a question with a typed answer is not shown twice
m = mergeState([q("Q1", "t", "3명")], [q("Q1", "t", "4명", { pid: "p9" }), q("Q7", "t", "y", { pid: "p8" })], [q("Q1", "t", "3명")], sentOf([q("Q1", "t", "3명")]));
out.adopted = ids(m.answers);
// Codex final A1: 「모름」 pressed on the next question keeps the draft written for the one a card answered
out.draft = [draftStays("L1", "H2", ""), draftStays("H2", "H2", ""), draftStays("L1", "H2", "가스절단"), draftStays(null, "H2", "")];
console.log(JSON.stringify(out));
"""

AHEAD = r"""
const READING = new Map(), out = {};
const s1 = aheadSignal("warm"), s2 = aheadSignal("warm"), p1 = aheadSignal("phrase");
out.one = [!!s1, s1.aborted, s2.aborted, p1.aborted];
READING.set("Q1", {}); READING.set("Q2", {});
const s3 = aheadSignal("warm");
out.busy = [s3, s2.aborted];
// Codex QA2 #5: two readings start while both are out (no new question asked): both are cut off at once
READING.clear(); const s4 = aheadSignal("warm"), p2 = aheadSignal("phrase");
READING.set("Q1", {}); aheadCap(); out.oneReading = [s4.aborted, p2.aborted];
READING.set("Q2", {}); aheadCap(); out.cap = [s4.aborted, p2.aborted, AHEAD.warm, AHEAD.phrase];
// nothing to prepare (no next question / no typed choice): the earlier one is cut off all the same
READING.clear(); const s5 = aheadSignal("warm"), none = aheadSignal("warm", true); out.none = [s5.aborted, none, AHEAD.warm];
console.log(JSON.stringify(out));
"""

A2 = r"""
const st = { answers: [], waitClose: false, busy: false }, READING = new Map(), log = [];
let againN = 0; const again = () => { againN++; };
const read = (qid, said, choice) => { const tok = {}; tok.cancel = () => log.push("cancel:" + qid); READING.set(qid, { said, choice, tok, gen: 1 }); return tok; };
const out = {};
read("Q1", "가스절단 6개 러그", "gas");
out.gone = staleReadings(READING, []);
out.unknown = staleReadings(READING, [{ qid: "Q1", choice: "unknown", value: "" }]);
out.same = staleReadings(READING, [{ qid: "Q1", choice: "gas", value: " 가스절단 6개 러그" }]);
out.adoptedOnly = staleReadings(READING, [{ qid: "Q1", choice: "gas", value: "가스절단 6개 러그", pid: "p1" }]);
// the answer taken back while the end waits for its reading: the reading ends, the end goes on (once)
st.answers = [{ qid: "Q1", choice: "unknown", value: "" }]; st.waitClose = true;
pruneReadings();
out.pruned = [READING.size, log.slice()];
resumeClose(); resumeClose();
out.resumed = [againN, st.waitClose];
// another reading still running: the end keeps waiting
read("Q2", "고소작업 2m", "yes"); st.answers = [{ qid: "Q2", choice: "yes", value: "고소작업 2m" }]; st.waitClose = true; againN = 0;
resumeClose(); out.stillWaits = [againN, st.waitClose];
// it ends (any branch: the reading is taken off) while a refresh runs: after the refresh, once
READING.delete("Q2"); st.busy = true; resumeClose();
out.busy = againN;
setTimeout(() => { st.busy = false; }, 100);
setTimeout(() => { out.afterBusy = [againN, st.waitClose]; console.log(JSON.stringify(out)); }, 900);
"""

A11 = r"""
const item = (id, x = {}) => ({ id, title: id, state: "yes", auto: "yes", basis: "b1", basis_ctl: "c1", touched: true, ctl_touched: true,
  memo: "", controls: [{ id: "k1", text: "환기", on: true }, { id: "k2", text: "감시", on: false }], ...x });
const mk = () => ({ permits: [{ permit_no: "0701", items: [item("F1"), item("F2", { state: "no" }), item("A:h1", { quote: "그라인더", basis: "b9" })] }] });
const out = {};
const empty = { status: "none", items: [], kept: {}, marks: {} }, fail = { status: "fail", items: [], kept: {}, marks: {} };
let ck = mk(), s0 = ckSig(ck), n = ckTakeAi(ck, empty);
out.empty = [ckSig(ck) === s0, n];
ck = mk(); s0 = ckSig(ck); n = ckTakeAi(ck, fail);
out.fail = [ckSig(ck) === s0, n];
// candidates only (nothing of his list): the submission is the same
ck = mk(); s0 = ckSig(ck); ckTakeAi(ck, { status: "ok", items: [{ id: "A:x" }], kept: {}, marks: { F1: { m: "support", id: "m1" } } });
out.candOnly = ckSig(ck) === s0;
// an AI item he put in, still as it is for the work: nothing changes
ck = mk(); s0 = ckSig(ck); ckTakeAi(ck, { status: "ok", items: [], kept: { "A:h1": { ok: true, item: { ...item("A:h1"), basis: "b9" } } }, marks: {} });
out.keptSame = ckSig(ck) === s0;
// a 「해당 없음」 the AI found words against: chosen again -> the submission is out of date
ck = mk(); s0 = ckSig(ck); n = ckTakeAi(ck, { status: "ok", items: [], kept: {}, marks: { F2: { m: "support", id: "m2", quote: "용접" } } });
out.support = [ckSig(ck) !== s0, n];
// an AI item whose basis moved: checked again
ck = mk(); s0 = ckSig(ck); n = ckTakeAi(ck, { status: "ok", items: [], kept: { "A:h1": { ok: true, item: { ...item("A:h1"), basis: "b10" } } }, marks: {} });
out.rebased = [ckSig(ck) !== s0, n];
// his own changes are seen
const own = (f) => { const c = mk(), a = ckSig(c); f(c.permits[0].items[0]); return ckSig(c) !== a; };
out.own = [own((it) => { it.state = "no"; }), own((it) => { it.touched = false; }), own((it) => { it.memo = "메모"; }), own((it) => { it.controls[1].on = true; })];
console.log(JSON.stringify(out));
"""

# QA #99: 최종 서류 출력 opens only after the safety manager's 자료 확인 (문서 목록) of every part of the document
OUT = r"""
const DAY = "2026-10-29", sf = { seen: {}, data: { date: DAY }, subs: {} }, sfNo = (d) => d.type === "permit" ? d.id : "WP-" + d.id.slice(-2), out = {};
const P = { type: "permit", id: "0734", permit_no: "PTW-0734", rev: "h1" }, W = { type: "plan", id: "WP-1029-03", rev: "w1" };
const K = (id, day = DAY) => sfSeenKey(day, id);
const gate = (d) => outGate(sfState(d)).ok;
out.todo = gate(P);
sf.seen[K("0734")] = { h: "h1", sub: null, day: DAY, parts: { permit: true, addendum: true } }; out.part = [gate(P), outGate(sfState(P)).label];
sf.seen[K("0734")].parts.checklist = true; out.done = [gate(P), outGate(sfState(P)).label];
out.changed = gate({ ...P, rev: "h2" });                       // the document changed after the 확인: not until checked again
sf.seen[K("0734")].parts.addendum = false; out.unchecked = gate(P); // taken back in 문서 목록: closed again
sf.seen[K("WP-1029-03")] = { h: "w1", sub: null, day: DAY, parts: { plan: true } }; out.plan = gate(W);
const nm = (fs) => fs.map((f) => [f.name, f.url, f.body ? f.body.kind : null]);
out.permitNew = nm(outFiles(P, null));
out.permitIssued = nm(outFiles(P, { no: "S-0734/R2", sheet: { title: "x" } }));
out.plan2 = nm(outFiles(W, null));
// Codex QA2 #1: the output list is every document of the day; the 별지 part only for those in a pair (or still out)
const X = { type: "permit", id: "0732", permit_no: "PTW-0732", rev: "x1" };
out.list = outDocs([W, P, X]).map((d) => d.id);
out.postable = [...postIds(["0734", "WP-1029-03"], { "0730": [{ status: "void", taken: null }], "0729": [{ status: "void", taken: "10:00" }] })];
// Codex QA2 #2: yesterday's 확인 of the same 7-day permit does not open today's output
const all = { permit: true, addendum: true, checklist: true };
sf.seen = { [K("0734", "2026-10-28")]: { h: "h1", sub: null, day: "2026-10-28", parts: all } };
out.yesterday = [gate(P), sfState(P)];
const rec = { h: "h1", sub: null, day: DAY, parts: all }, now = { day: DAY, rev: "h1", sub: null }, PP = SF_PARTS.permit;
out.dayV = [outVerdict(sf.seen[K("0734", "2026-10-28")], DAY, now, PP), outVerdict(rec, DAY, { ...now, day: "2026-10-30" }, PP), outVerdict(rec, DAY, now, PP)];
// Codex QA2 #3: the server's document changed after the 확인 (the list still has the old rev): refused before the output
out.revV = outVerdict(rec, DAY, { ...now, rev: "h2" }, PP);
out.partV = outVerdict({ ...rec, parts: { permit: true } }, DAY, now, PP);
// Codex QA2 #4: a new submission drops the 확인; the output is the submission the 확인 was made on
sf.seen = { [K("0734")]: { h: "h1", sub: "S1", day: DAY, parts: all } };
sf.subs = { "PTW-0734": { id: "S1" } }; out.subSame = [gate(P), sfState(P)];
sf.subs = { "PTW-0734": { id: "S2" } }; out.subNew = [gate(P), sfState(P)];
sf.subs = undefined; out.subUnknown = gate(P);                  // not read yet: the list keeps the mark, the output reads it again
out.subV = [outVerdict({ ...rec, sub: "S1" }, DAY, { ...now, sub: "S2" }, PP), outVerdict(rec, DAY, { ...now, sub: "S1" }, PP), outVerdict({ ...rec, sub: "S1" }, DAY, { ...now, sub: "S1" }, PP)];
out.subFiles = nm(outFiles(P, null, "S1"));
out.subIssued = nm(outFiles(P, { no: "S-0734/R2", sheet: { title: "x" } }, "S1"));
console.log(JSON.stringify(out));
"""


# 제출 직전 확인 창: 실수하기 쉬운 핵심 정보만, 제출되는 값으로
PS = r"""
const F = (no, key, value) => ({ [`p${no}.${key}`]: { page: no, key, value, original: value } });
const A = (qid, choice, value, q = {}) => ({ qid, choice, value, q });
const out = {};
// 화기 one permit: four days, three of them in a row at the same time; the answers changed the time (T1)
const hot = { permit_no: "PTW-0701", no: 1, label: "화기", windows: { "2026-10-27": ["13:00~15:00"], "2026-10-28": ["13:00~15:00"],
  "2026-10-29": ["13:00~15:00"], "2026-10-31": ["09:00~11:00"] }, windows_src: "신청자 답변",
  place: { text: "4BAY 12-14 칼럼", level: "L3", bays: ["4"], cols: "12-14 칼럼", whole: false }, targets: ["E41P"], cranes: [] };
const aug1 = { effective: [hot], questions: [],
  reflect: { "PTW-0701": { fills: [{ base: "job", final: "E41P 블록 러그 절단·용접 보수" }, { base: "workers", final: "4" }] } } };
const f1 = { ...F(1, "job", "용접 보수"), ...F(1, "workers", ""), ...F(1, "concurrent", "Y"), ...F(1, "location", "4BAY") };
const ans1 = [A("H2:PTW-0701", "text", "가스절단, 산소·LPG"), A("W1:PTW-0701", "text", "화재감시인 1명"),
  A("B3:PTW-0701", "yes", "도장팀 4BAY 도장"), A("T1:PTW-0701", "partial", "13시~15시")];
let v = preSubmitView(aug1, f1, ans1, 0, false);
const rowsOf = (v, i = 0) => Object.fromEntries(v.permits[i].rows.map((r) => [r.k, [r.v, r.warn, r.flag, r.note]]));
out.hot = rowsOf(v); out.hotOpen = v.open; out.hotTitle = v.permits[0].title;
// 정전·LOTO, overnight, place written as a team name, 병행 모름, 작업인원 빈칸, 차단 시각 not answered yet, checklist left
const lo = { permit_no: "PTW-0702", no: 1, label: "정전·LOTO", windows: { "2026-10-30": ["22:00~익일 02:00"] }, windows_src: "원본",
  place: { text: "전기설비팀", level: "L0", bays: [], cols: "" }, targets: [], cranes: [] };
const aug2 = { effective: [lo], reflect: {}, questions: [{ qid: "LO3:PTW-0702", item: "LO3", permit_no: "PTW-0702" }] };
const f2 = { ...F(1, "job", "OH-21 크레인 제어반 수리"), ...F(1, "workers", ""), ...F(1, "concurrent", "") };
v = preSubmitView(aug2, f2, [A("B3:PTW-0702", "unknown", "")], 2, true);
out.loto = rowsOf(v); out.lotoOpen = v.open;
// a place with BAY but no column; no time at all
const nocol = { ...lo, permit_no: "PTW-0703", label: "고소", windows: {}, place: { text: "3BAY 상부", level: "L2", bays: ["3"], cols: "" }, height: 6 };
v = preSubmitView({ effective: [nocol], reflect: {}, questions: [] }, { ...F(1, "job", "배관 지지대 설치"), ...F(1, "workers", "2"), ...F(1, "concurrent", "N") }, [], 0, false);
out.nocol = rowsOf(v); out.nocolOpen = v.open;
// no review yet: nothing made up, the checklist still counted
v = preSubmitView(null, {}, [], 1, false); out.none = [v.none, v.permits.length, v.open];
// 밀폐: CF2 「없음」 then C5.CF2 「추가로 적은 내용이 맞음」 (the earlier answer withdrawn); CF1 choice label kept beside the
// typed value; workers did not fit the field (별지); the work time apart from the residual watch; a pending for the safety team
const cf = { permit_no: "PTW-0704", no: 1, label: "밀폐", windows: { "2026-11-02": ["09:00~12:00"] }, windows_work: { "2026-11-02": ["09:00~11:00"] },
  residual: "12:00", windows_src: "원본", place: { text: "2BAY 05-07 칼럼 B11 블록", level: "L3", bays: ["2"], cols: "05-07 칼럼" }, targets: ["B11", "E170", "MCC-3"], cranes: [] };
const fx = { effective: [cf], questions: [], reflect: { "PTW-0704": { fills: [], extra: [["작업인원", "3 (B1 답)"]], pending: [["연결 계통", "확인 필요 — 답 '없음'이 허가서 내용과 다름"]] } } };
const fcf = { ...F(1, "job", ""), ...F(1, "job_detail", "탱크 내부 용접"), ...F(1, "workers", ""), ...F(1, "concurrent", "N") };
fcf["p1.workers"].name = "작업인원";
const ch = (id, label) => ({ choices: [{ id, label }] });
v = preSubmitView(fx, fcf, [A("CF2:PTW-0704", "none", "", ch("none", "연결 계통 없음")), A("C5.CF2:PTW-0704", "free", "아르곤 퍼지 라인 V-12 연결 있음", ch("free", "추가로 적은 내용이 맞음")),
  A("CF1:PTW-0704", "full", "맨홀 M-2, 안쪽 10m", ch("full", "전신 진입")), A("T9:PTW-0704", "unknown", "")], 0, false);
out.cf = rowsOf(v); out.cfOpen = v.open;
// 인양: the moving stage apart from the whole work
const li = { permit_no: "PTW-0705", no: 1, label: "중량물인양", windows: { "2026-11-02": ["08:00~12:00"] }, windows_stage: { move: { "2026-11-02": ["10:00~10:30"] } },
  time_meaning: "stage", windows_src: "신청자 답변", place: { text: "3BAY 10-12 칼럼", level: "L3", bays: ["3"], cols: "10-12 칼럼" }, targets: [], cranes: ["OH-21"] };
v = preSubmitView({ effective: [li], questions: [], reflect: {} }, { ...F(1, "job", "블록 인양"), ...F(1, "workers", "4"), ...F(1, "concurrent", "N"),
  ...F(1, "load_weight", "80"), ...F(1, "crane_swl", "100t") }, [], 0, false);
out.li = rowsOf(v);
// 화기: the ember check end answered 「모름」 is its own line, the work time stays known (staging check 2026-11-01)
v = preSubmitView({ effective: [{ ...hot, permit_no: "PTW-0706", windows_work: hot.windows }], questions: [], reflect: {} }, f1,
  [A("T4:PTW-0706", "unknown", "")], 0, false);
out.t4 = rowsOf(v);
console.log(JSON.stringify(out));
"""

def real_summary():
    """the window drawn from what the server really sends (Codex final #9: a test fixture of another shape hid a crash):
    a lift with its moving part answered (T1 partial), and a 화기 permit whose HT1/H2 answer was taken back (C6 doc)"""
    try:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "tools"))
        from server import augment, extract
        from server.permit_kinds import KINDS
        from foreman_permits import FOREMAN
    except Exception as e:                      # noqa: BLE001 (pymupdf missing: this check is skipped, said so)
        print(f"SKIP 실제 검토 결과 시험: {e}")
        return None
    doc = lambda d: extract.build(ROOT / "samples/반장_테스트" / f"{KINDS[d['kind']]['label'].replace('·', '')}_{d['case']}_{d['permit_no'][-4:]}.pdf", d["kind"])
    lift = next(d for d in FOREMAN if d["permit_no"].endswith("0707"))
    f = doc(lift)["fields"]
    q = next(x for x in augment.summary(f, [])["questions"] if x["item"] == "T1")
    ans = [{"qid": q["qid"], "choice": "partial", "value": "10/27 10:30~11:30", "q": q}]
    s1 = augment.summary(f, ans)
    hot = next(d for d in FOREMAN if d["kind"] == "hot")
    fh = doc(hot)["fields"]
    s0 = augment.summary(fh, [])
    qh = next((x for x in s0["questions"] if x["item"] in ("H2", "H1")), None)
    pid = s0["effective"][0]["permit_no"]
    ah = ([{"qid": qh["qid"], "choice": "text", "value": "가스절단 6개", "q": qh},
           {"qid": f"C6.{qh['item']}:{pid}", "choice": "doc", "value": "", "q": {}}] if qh else [])
    s2 = augment.summary(fh, ah)
    code = "\n".join(part(JS, x) for x in ("const PS_KIND = ", "const PS_EXTRA = ", "const PS_COMMON = ", "const PS_INPUT_LABEL = ", "function preSubmitView("))
    code += f"""
const out = {{}};
try {{
  const v = preSubmitView({json.dumps(s1, ensure_ascii=False)}, {json.dumps(f, ensure_ascii=False)}, {json.dumps(ans, ensure_ascii=False)}, 0, false);
  out.move = (v.permits[0].rows.find((r) => r.k === "인양 이동 단계") || {{}}).v;
  const w = preSubmitView({json.dumps(s2, ensure_ascii=False)}, {json.dumps(fh, ensure_ascii=False)}, {json.dumps(ah, ensure_ascii=False)}, 0, false);
  out.hot = {json.dumps(bool(qh))} ? (w.permits[0].rows.find((r) => r.v.includes("철회")) || {{}}).v : "앞 답 철회 · 서류 값을 따름";
}} catch (e) {{ out.error = String(e); }}
console.log(JSON.stringify(out));
"""
    # the summaries are too long for a command line: the script goes through a file
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh_:
        fh_.write(code)
    try:
        r = subprocess.run(["node", fh_.name], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        Path(fh_.name).unlink(missing_ok=True)
    if r.returncode:
        print(r.stderr[-800:])
        return {}
    return json.loads(r.stdout.strip().splitlines()[-1])


def main():
    r1 = run(LIB + A1)
    if r1 is None:
        print("SKIP: 여기에는 node가 없음(로컬에서 확인)")
        sys.exit(0)
    check("A1 409 뒤에도 방금 적은 답(Q2)이 남음", r1.get("keep") == [["Q1=3명", "Q2=09시 시작", "Q5=가스절단@p1"], 0])
    check("A1 카드 확인이 같은 질문을 답함 → 덮어쓰지 않고 clash", r1.get("clashAdopted") == [["Q1=3명", "Q2=10시@p2"], ["Q2=09시 시작"]])
    check("A1 다른 화면이 같은 질문을 답함 → clash", r1.get("clashTyped") == [["Q1=3명", "Q2=11시"], ["Q2=09시 시작"]])
    check("A1 여기서 지운 답은 서버 답에서도 빠짐", r1.get("removed") == ["Q1=3명"])
    check("A1 지운 답이 그 사이 다른 곳에서 바뀌었으면 서버 답 유지", r1.get("removedElse") == ["Q1=3명", "Q3=B"])
    check("A1 여기서만 바꾼 답(지운 뒤 모름)은 새 답으로", r1.get("changed") == [["unknown"], 0])
    check("A1 서버에 같은 답이 있으면 중복·충돌 없음", r1.get("same") == [["Q2=09시 시작"], 0])
    check("A1 서버가 가진 것을 모르면(옛 임시저장) 서버 답 그대로", r1.get("unknown") == ["Q1=3명"])
    check("A1 직접 답이 있는 질문의 확인 읽기는 두 번 보이지 않음", r1.get("adopted") == ["Q1=3명", "Q7=y@p8"])
    check("A1 다른 질문 초안은 버튼 답(모름)에도 남고, 같은 질문·입력한 답은 비움", r1.get("draft") == [True, False, False, False])

    ra = run("\n".join(part(JS, s) for s in ("const AHEAD = ", "function aheadSignal(", "function aheadCap(")) + AHEAD) or {}
    check("미리 읽기 요청은 종류마다 하나: 앞 질문 것은 끊고 다른 종류는 그대로", ra.get("one") == [True, True, False, False])
    check("앞 답 읽기가 둘 이상 돌면 미리 읽기를 보내지 않음(연결 자리 비워 둠)", ra.get("busy") == [None, True])
    check("QA2-5 읽기가 하나면 미리 읽기는 그대로", ra.get("oneReading") == [False, False])
    check("QA2-5 읽기가 둘이 되는 즉시 warm·phrase 둘 다 끊음(새 질문 없이도)", ra.get("cap") == [True, True, None, None])
    check("QA2-5 미리 읽을 것이 없을 때(다음 질문·입력 선택지 없음)도 앞 요청은 끊음", ra.get("none") == [True, None, None])

    r2 = run(LIB + A2) or {}
    check("A2 원래 답을 지우면 그 읽기는 끝낼 대상", r2.get("gone") == ["Q1"])
    check("A2 지운 뒤 「모름」으로 답해도 이전 읽기는 끝낼 대상", r2.get("unknown") == ["Q1"])
    check("A2 같은 답(앞뒤 공백만 다름)이면 읽기 유지", r2.get("same") == [])
    check("A2 직접 답 없이 확인 읽기만 있으면 끝낼 대상", r2.get("adoptedOnly") == ["Q1"])
    check("A2 pruneReadings: 대기 목록에서 빼고 카드를 멈춤", r2.get("pruned") == [0, ["cancel:Q1"]])
    check("A2 마지막 읽기가 끝나면 마무리 대기가 한 번 이어짐", r2.get("resumed") == [1, False])
    check("A2 다른 읽기가 남아 있으면 계속 기다림", r2.get("stillWaits") == [0, True])
    check("A2 새로 고치는 중이면 그 뒤에 이어짐(바로 두 번 묻지 않음)", r2.get("busy") == 0 and r2.get("afterBusy") == [1, False])

    r3 = run(LIB + A11) or {}
    check("A11 빈 AI 결과는 제출 내용을 바꾸지 않음", r3.get("empty") == [True, {"again": 0, "re": 0}])
    check("A11 실패한 AI 결과는 제출 내용을 바꾸지 않음", r3.get("fail") == [True, {"again": 0, "re": 0}])
    check("A11 후보만 온 결과(목록 밖)는 제출 내용을 바꾸지 않음", r3.get("candOnly") is True)
    check("A11 넣은 AI 항목이 그대로 맞으면 바뀌지 않음", r3.get("keptSame") is True)
    check("A11 「해당 없음」에 반대 근거가 오면 다시 고를 항목(제출 만료)", r3.get("support") == [True, {"again": 1, "re": 0}])
    check("A11 넣은 AI 항목의 근거가 바뀌면 다시 확인(제출 만료)", r3.get("rebased") == [True, {"again": 0, "re": 1}])
    check("A11 반장이 바꾼 해당 여부·확인·메모·조치는 모두 변경으로 봄", r3.get("own") == [True, True, True, True])

    ro = run("\n".join(part(JS, s) for s in ("const SF_PARTS = ", "const sfSeenKey = ", "const sfSubId = ", "const markHolds = ", "const sfSeenOf = ",
                                             "function sfMarks(", "function sfState(", "const outGate = ", "function outFiles(", "function outVerdict(",
                                             "const postIds = ", "const docOrder = ", "const outDocs = ")) + OUT) or {}
    check("QA99 확인 전 서류는 출력 버튼이 잠김", ro.get("todo") is False)
    check("QA99 일부만 확인하면 잠김(확인 중)", ro.get("part") == [False, "확인 중"])
    check("QA99 문서 목록에서 확인을 마치면 출력이 열림", ro.get("done") == [True, "확인"])
    check("QA99 확인 뒤 문서가 바뀌면 다시 잠김", ro.get("changed") is False)
    check("QA99 문서 목록에서 확인을 풀면 다시 잠김", ro.get("unchecked") is False)
    check("QA99 작업계획서도 확인하면 출력이 열림", ro.get("plan") is True)
    check("QA99 별지 발행 전: 허가서+추가검토서와 위험 체크리스트", ro.get("permitNew") == [
        ["0734_허가서+추가검토서.pdf", "/api/safety/pdf/0734/full.pdf", None], ["0734_위험체크리스트.pdf", "/api/safety/pdf/0734/checklist.pdf", None]])
    check("QA99 별지 발행 뒤: 원본+별지(발행본)와 위험 체크리스트", ro.get("permitIssued") == [
        ["S-0734_R2_현장게시용_원본+별지.pdf", "/api/safety/sheet.pdf", "post"], ["0734_위험체크리스트.pdf", "/api/safety/pdf/0734/checklist.pdf", None]])
    check("QA99 작업계획서는 원본(전달문 발행 전)", ro.get("plan2") == [["WP-03_작업계획서.pdf", "/api/safety/pdf/WP-1029-03/original.pdf", None]])
    check("QA2-1 출력 목록은 그날 문서 전부(쌍 없는 0732 포함), 허가서 먼저", ro.get("list") == ["0732", "0734", "WP-1029-03"])
    check("QA2-1 별지 대상은 쌍 문서와 회수 전 개정본이 남은 문서만", ro.get("postable") == ["0734", "WP-1029-03", "0730"])
    check("QA2-1 출력 목록을 쌍 문서가 아니라 그날 문서 전체(sf.docs)로 만듦", "outDocs(sf.docs)" in part(JS, "function postIssueList("))
    check("QA2-2 전날 확인은 오늘 출력을 열지 않음(작업일 키)", ro.get("yesterday") == [False, "todo"])
    check("QA2-2 출력 직전: 다른 날 확인·서버 작업일 변경은 거절, 같은 날은 통과", ro.get("dayV") == ["day", "day", "ok"])
    check("QA2-3 확인 뒤 서버 문서가 바뀌면 출력 거절(다시 확인)", ro.get("revV") == "rev")
    check("QA2-3 확인을 다 하지 않은 기록은 출력 거절", ro.get("partV") == "todo")
    check("QA2-4 같은 제출본이면 확인 유지", ro.get("subSame") == [True, "done"])
    check("QA2-4 새 제출본이 오면 확인이 풀림(변경됨)", ro.get("subNew") == [False, "changed"])
    check("QA2-4 제출본을 아직 못 읽었으면 목록 표시는 유지(출력 직전에 다시 확인)", ro.get("subUnknown") is True)
    check("QA2-4 출력 직전: 확인한 제출본과 최신 제출본이 다르면 거절", ro.get("subV") == ["sub", "sub", "ok"])
    check("QA2-4 제출본이 있으면 그 제출본의 추가검토서·체크리스트를 출력", ro.get("subFiles") == [
        ["0734_허가서+추가검토서_제출본.pdf", "/api/submissions/S1/permit.pdf", None], ["0734_위험체크리스트_제출본.pdf", "/api/submissions/S1/checklist.pdf", None]])
    check("QA2-4 별지 발행 뒤: 원본+별지와 제출본 체크리스트", ro.get("subIssued") == [
        ["S-0734_R2_현장게시용_원본+별지.pdf", "/api/safety/sheet.pdf", "post"], ["0734_위험체크리스트_제출본.pdf", "/api/submissions/S1/checklist.pdf", None]])
    rp = run("\n".join(part(JS, x) for x in ("const PS_KIND = ", "const PS_EXTRA = ", "const PS_COMMON = ", "const PS_INPUT_LABEL = ", "function preSubmitView(")) + PS) or {}
    real = real_summary()
    h, lo, nc = rp.get("hot") or {}, rp.get("loto") or {}, rp.get("nocol") or {}
    check("PS 같은 시간 연속 날짜는 한 줄로(10/27~10/29 매일), 떨어진 날은 따로", (h.get("작업일·작업시간") or [""])[0] == "10/27~10/29 매일 13:00~15:00 · 10/31 09:00~11:00")
    check("PS 답으로 바뀐 시간이면 그 출처(신청자 답변), 표시할 것 없음", (h.get("작업일·작업시간") or [""] * 4)[1:] == ["", "", "신청자 답변"])
    check("PS 위치: BAY·칼럼·허가서 밖 블록 번호", h.get("작업 위치") == ["4BAY 12-14 칼럼 · 블록 E41P", "", "", ""])
    check("PS 작업내용·인원은 반영본 칸 값(답 반영 뒤) 그대로", (h.get("작업 내용") or [""])[0] == "화기 허가서 · E41P 블록 러그 절단·용접 보수"
          and (h.get("작업 인원") or [""])[0] == "4명 · 화재감시인 1명")
    check("PS 병행작업 있음(무엇)", (h.get("병행작업") or [""])[0] == "있음 · 도장팀 4BAY 도장")
    check("PS 화기: 절단·용접 방법·가스 답이 있으면 한 줄", (h.get("절단·용접 방법·가스") or [""])[0] == "가스절단, 산소·LPG")
    check("PS 빠진 것 없으면 맨 위 목록 비어 있음, 승인번호 표시", rp.get("hotOpen") == [] and rp.get("hotTitle") == "화기 허가서 · 승인번호 PTW-0701")
    check("PS 다음 날까지 이어지는 시간 표시, 허가서 시간 그대로면 그렇게 적음", lo.get("작업일·작업시간") == ["10/30 22:00~익일 02:00", "", "다음 날까지 이어짐", "허가서에 적힌 시간"])
    check("PS 팀 이름 같은 위치는 표시", (lo.get("작업 위치") or ["", ""])[1] == "부서·팀 이름처럼 보임 (BAY·칼럼 없음)")
    check("PS 병행 「모름」·인원 빈칸·차단 시각 답하지 않음", lo.get("병행작업") == ["미확인", "모름", "", ""]
          and lo.get("작업 인원") == ["(비어 있음)", "비어 있음", "", ""] and lo.get("차단·복구·시험 시각") == ["(비어 있음)", "답하지 않음", "", ""])
    check("PS 맨 위: 다시 살펴보는 중 → 열린 항목 → 체크리스트 확인 안 함 개수", rp.get("lotoOpen") == [
        "고친 값을 다시 살펴보는 중입니다. 끝나면 이 창이 새 값으로 바뀝니다", "작업 위치: 부서·팀 이름처럼 보임 (BAY·칼럼 없음)",
        "작업 인원: 비어 있음", "병행작업: 모름", "차단·복구·시험 시각: 답하지 않음", "위험 체크리스트: 확인 안 함 2개"])
    check("PS BAY만 있고 칼럼 없음 · 시간 비어 있음 · 고소 높이 · 병행 없음", (nc.get("작업 위치") or ["", ""])[1] == "칼럼 없음"
          and (nc.get("작업일·작업시간") or ["", ""])[:2] == ["(비어 있음)", "비어 있음"] and (nc.get("높이·위치") or [""])[0] == "높이 6m"
          and (nc.get("병행작업") or [""])[0] == "없음" and (nc.get("작업 인원") or [""])[0] == "2명")
    check("PS 검토 결과가 없으면 지어내지 않음(체크리스트만)", rp.get("none") == [True, 0, ["위험 체크리스트: 확인 안 함 1개"]])
    cf, li = rp.get("cf") or {}, rp.get("li") or {}
    check("PS 정정(C5 추가로 적은 내용이 맞음)이면 앞 답 대신 정정한 값", (cf.get("가스·공기 계통") or [""])[0] == "아르곤 퍼지 라인 V-12 연결 있음 (정정)")
    check("PS 선택 의미와 적은 값을 함께(전신 진입 · 맨홀)", (cf.get("진입·내부 작업") or [""])[0] == "전신 진입 · 맨홀 M-2, 안쪽 10m")
    check("PS 칸에 못 넣은 값은 별지 값으로, 작업내용 비면 상세", cf.get("작업 인원") == ["3명", "", "", "별지에 기록"]
          and (cf.get("작업 내용") or [""])[0] == "밀폐 허가서 · 탱크 내부 용접")
    check("PS 작업시간과 잔불·잔류 확인 끝을 따로", (cf.get("작업일·작업시간") or [""])[0] == "11/2 09:00~11:00" and (cf.get("잔불·잔류 확인 끝") or [""])[0] == "12:00까지")
    check("PS 실물 블록 번호(B11·E170)만 블록으로, 패널은 아님", (cf.get("작업 위치") or [""])[0] == "2BAY 05-07 칼럼 B11 블록 · 블록 E170")
    check("PS 대기·중단 중 유지(T9) 「모름」은 그 줄에만, 작업시간 줄은 아님", (cf.get("대기·중단 중 유지") or ["", ""])[1] == "모름"
          and (cf.get("작업일·작업시간") or ["", ""])[1] == "")
    t4 = rp.get("t4") or {}
    check("PS 잔불 확인 끝 「모름」은 그 줄에만, 작업시간 줄은 아님", (t4.get("잔불·잔류 확인 끝") or ["", ""])[1] == "모름"
          and (t4.get("작업일·작업시간") or ["", ""])[1] == "")
    check("PS 안전팀 확인으로 넘어가는 것도 맨 위에", any(t.startswith("안전팀 확인으로 넘어가는 것 1개: 연결 계통") for t in rp.get("cfOpen") or []))
    check("PS 인양 이동 단계는 전체 작업시간과 따로, 중량·정격", (li.get("인양 이동 단계") or [""])[0] == "11/2 10:00~10:30"
          and (li.get("작업일·작업시간") or [""])[0] == "11/2 08:00~12:00" and (li.get("중량·정격하중") or [""])[0] == "중량 80t · 정격 100t")
    if real is not None:
        check("PS 실제 검토 결과(augment.summary)로도 창이 열림: 인양 이동 단계·C6 철회", real.get("move") == "10/27 10:30~11:30"
              and real.get("error") is None and real.get("hot") == "앞 답 철회 · 서류 값을 따름")
        if not OK[-1]:
            print("     ", real)
    print(f"\n{sum(OK)}/{len(OK)}")
    sys.exit(0 if all(OK) else 1)


if __name__ == "__main__":
    main()
