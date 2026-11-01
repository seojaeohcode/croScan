// croScan: 1 허가서 올리기 → 2 허가서 검토 (문서 + 확인 질문, 한 화면) → 3 작업계획서 확인 → 4 제출
const $ = (s) => document.querySelector(s);
const st = { doc: null, page: 1, zoom: 1, view: "form", findings: [], busy: false, step: 3, di: 0, checked: new Set(), reviewed: false,
  src: null, rev: 0, exportedRev: -1, answers: [] };
// every change to what the 제출본 would contain bumps rev; the 제출본 is current only while exportedRev === rev
// (an answer may fill the 「반장 답」 shown over a blank of the permit: the drawn fields are repainted)
const bump = () => { st.rev++; saveDraft(); if (st.doc && st.di === 0 && typeof sheet !== "undefined") sheet.querySelectorAll(".fi").forEach((n) => { const f = st.doc.fields[n.dataset.key]; if (f) decorate(n, f, null); });
  if (st.ck) { renderCkBar(); paintStepper(); } };
const exported = () => st.doc && st.exportedRev === st.rev;
// the review belongs to the file and kind it was read from; picking another file on step 1 starts a new review
const sameSource = () => !!(st.src && pick.file === st.src.file && pick.kind === st.src.kind);
const BASE = 1.55;                     // px per PDF point at 100 %
// QA #41: on the permit, with the chat beside the document, a field is edited in the chat's own box (phones: in place)
const NARROW = matchMedia("(max-width: 860px)");
const chatEdit = () => st.di === 0 && !!st.doc && !NARROW.matches;

const FORMATS = {
  code: /^[A-Z0-9]+(?:-[A-Z0-9]+)*$/, phone: /^0\d{1,2}-[\dX]{3,4}-[\dX]{4}$/, count: /^\d{1,3}$/,
  number: /^\d+(?:\.\d+)?$/, date: /^\d{4}-\d{2}-\d{2}$/, time: /^([01]\d|2[0-3]):[0-5]\d$/, yn: /^[YN]$/,
  name: /^[가-힣A-Za-z]{1,10}$/,
};
const TYPE_KO = { code: "코드(영문 대문자·숫자·-)", phone: "전화번호(010-0000-0000)", count: "인원 수(정수)",
  number: "숫자", date: "날짜(YYYY-MM-DD)", time: "시각(HH:MM)", yn: "Y 또는 N", name: "이름", text: "글", check: "체크", image: "이미지" };
const KIND_ICON = { confined: "i-confined", hot: "i-flame", height: "i-height", lifting: "i-lift", loto: "i-loto" };

function valid(f, v) {
  if (["check", "image", "text"].includes(f.type) || v === "" || v == null) return true;
  const r = RULE_OF.get(f);
  if (r) return !codeProblem(r, String(v).trim());
  return FORMATS[f.type] ? FORMATS[f.type].test(String(v).trim()) : true;
}
// QA #35: three code fields have their own rule. Loose on purpose where real numbers vary (a demo aid, not the
// company's full standard): 승인번호 4 segments with a real date, 호선/공사 a 4-digit hull then segments, 작업표준 HHIS-…
const CODE_RULES = {
  permit_no: { ex: "AC00-IH-20261014-0400", help: "4구간 · 영문 2자리+숫자 2자리 - 영문 2자리 - 날짜 8자리(연월일) - 숫자 4자리" },
  hull_no: { ex: "3612-B21S", help: "호선 숫자 4자리 - 블록·공사 구간(영문 대문자·숫자). 구간은 하이픈(-)으로 나눕니다" },
  jsp_no: { ex: "HHIS-CW-A0001190-012-001", help: "HHIS로 시작 - 영문 대문자·숫자 구간. 구간은 하이픈(-)으로 나눕니다" },
};
const RULE_OF = new WeakMap();
function tagRules(doc) {
  for (const [k, f] of Object.entries(doc.fields)) { const r = CODE_RULES[k.replace(/^p\d+\./, "")]; if (r && f.type === "code") RULE_OF.set(f, { ...r, key: k.replace(/^p\d+\./, "") }); }
}
const realDate = (d) => { const y = +d.slice(0, 4), m = +d.slice(4, 6), dd = +d.slice(6, 8), t = new Date(y, m - 1, dd);
  return t.getFullYear() === y && t.getMonth() === m - 1 && t.getDate() === dd; };
// what is wrong, in words that name the segment and the fix ("" = the format is right)
function codeProblem(r, v) {
  if (!/^[A-Z0-9-]*$/.test(v)) return `영문 대문자·숫자·하이픈(-)만 씁니다. 빈칸이나 다른 기호를 빼 주세요. 예: ${r.ex}`;
  const g = v.split("-");
  if (g.some((x) => !x)) return `하이픈(-) 사이가 비어 있습니다. 예: ${r.ex}`;
  if (r.key === "permit_no") {
    if (g.length !== 4) return `승인번호는 하이픈으로 나뉜 4구간입니다 (지금 ${g.length}구간). 예: ${r.ex}`;
    if (!/^[A-Z]{2}\d{2}$/.test(g[0])) return "첫 번째 구간은 영문 대문자 2자리와 숫자 2자리입니다. 예: AC00";
    if (!/^[A-Z]{2}$/.test(g[1])) return "두 번째 구간은 영문 대문자 2자리입니다. 예: IH";
    if (!/^\d{8}$/.test(g[2])) return "세 번째 구간은 날짜 숫자 8자리(연월일)입니다. 예: 20261014";
    if (!realDate(g[2])) return "세 번째 구간의 날짜를 확인해 주세요 (없는 날짜). 예: 20261014";
    if (!/^\d{4}$/.test(g[3])) return "네 번째 구간은 숫자 4자리입니다 (앞자리 0 포함). 예: 0400";
    return "";
  }
  if (r.key === "hull_no") {
    if (!/^\d{4}$/.test(g[0])) return "첫 번째 구간은 호선 번호 숫자 4자리입니다. 예: 3612";
    if (g.length < 2) return `호선 뒤에 하이픈(-)과 블록·공사 구간을 이어 적어 주세요. 예: ${r.ex}`;
    return "";
  }
  if (r.key === "jsp_no") {
    if (g[0] !== "HHIS") return `작업표준 번호는 HHIS로 시작합니다. 예: ${r.ex}`;
    if (g.length < 2) return `HHIS 뒤에 하이픈(-)과 구간을 이어 적어 주세요. 예: ${r.ex}`;
    return "";
  }
  return "";
}
const badMsg = (f) => { const r = RULE_OF.get(f); return r ? codeProblem(r, String(f.value).trim()) : `형식이 맞지 않습니다. ${TYPE_KO[f.type]}로 적어 주세요.`; };
// an unfinished value is not shown as an error while it is being typed: only after leaving the box (then it follows every edit)
const errUi = { shown: new Set(), typing: null };
const typingIn = (key) => { const a = document.activeElement; return errUi.typing === key && !!a && (a.dataset.key === key || a.dataset.fkey === key); };
const badShown = (key, f) => !valid(f, f.value) && (errUi.shown.has(key) || !typingIn(key));
function watchErr(inp, key, f, paint) {
  inp.addEventListener("focus", () => { errUi.typing = key; });
  inp.addEventListener("blur", () => { if (errUi.typing === key) errUi.typing = null; if (!valid(f, f.value)) errUi.shown.add(key); paint(); refreshNotes(key, f); });
}
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function esc(s) { return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
const icon = (id) => `<svg class="ic" aria-hidden="true"><use href="#${id}"/></svg>`;
const fmtKB = (n) => n >= 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + " MB" : Math.round(n / 1024) + " KB";
let toastTimer = null;
function toast(text) {
  const t = $("#toast"); t.textContent = text; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}

// ---------------------------------------------------------------- screens and the 4-step stepper
const SCREENS = ["s-login", "s-upload", "s-load", "s-edit", "s-plans", "s-check", "s-submit", "s-safety"];
function show(id) {
  for (const s of SCREENS) $("#" + s).hidden = s !== id;
  document.body.dataset.screen = id;
}
// what each step needs before it can be opened from the stepper
// QA #33: the stepper shows the screens in this order (작업계획서 first); POS is a screen's place, 1-5
const STEP_ORDER = [3, 1, 2, 4, 5], POS = (n) => STEP_ORDER.indexOf(n) + 1;
// QA #54: the 작업계획서 come first and every one is confirmed before the permit (no going on with some left)
const plansOk = () => !!(st.wp && st.wp.plans.length && st.checked.size === st.wp.plans.length);
// 받침에 맞는 조사 (QA #62): pp("작업일시", "은", "는") → "는"; with 으로/로 a ㄹ 받침 takes 로
function pp(w, a, b) {
  // read as spoken: no quotes or brackets, no trailing (…) note; a number with m/km is read 미터
  let s = String(w || "").replace(/[「」『』"'\]\s]+$/g, "").replace(/^[「『"'\s]+/, "");
  while (/\([^()]*\)$/.test(s)) s = s.replace(/\s*\([^()]*\)$/, "");
  if (/\d\s*k?m$/i.test(s)) return b;
  const c = s.charCodeAt(s.length - 1);
  if (c >= 0xAC00 && c <= 0xD7A3) { const j = (c - 0xAC00) % 28; return j && !(a === "으로" && j === 8) ? a : b; }
  return /[013678LMNRlmnr]$/.test(s) ? a : b;
}
// QA #96: 제출 확인(5) only after every 위험요인 is confirmed (it replaced QA #13's 「넘어감」)
// done only for the checklist drafted from what is there now (not while it is drafted again, failed or out of date)
const ckBasis = () => JSON.stringify({ fields: st.doc ? st.doc.fields : null, answers: st.answers, session_id: st.sid || "", expected_revision: st.srev ?? null });
const ckDone = () => !!st.ck && !st.ckLoading && !st.ckError && st.ckBasis === ckBasis() && ckCount().left === 0;
const canGo = (n) => !st.loading && (n === 3 || (plansOk() && (n === 1 || (!!st.doc && sameSource() && (n < 4 || (!!st.wp && !!st.sid)) && (n < 5 || ckDone())))));
function paintStepper() {
  document.querySelectorAll("#stepper li").forEach((li) => {
    const n = +li.dataset.step, b = li.querySelector("button");
    li.classList.toggle("current", n === st.step);
    // done by what is true now, not by having passed it
    const done = n === 1 ? !!st.doc && sameSource() : n === 2 ? st.reviewed && !st.reviewPending : n === 3 ? !!(st.wp && st.checked.size === st.wp.plans.length)
      : n === 4 ? ckDone() : exported();
    li.classList.toggle("done", !!done);
    // passed but not finished (작업계획서 not all checked, checklist items left): a mark of its own, not nothing (QA #13)
    const left = !done && POS(n) < POS(st.step) && (n === 3 || n === 4);
    li.classList.toggle("partial", left);
    b.setAttribute("aria-label", `${POS(n)}단계 ${b.querySelector("span").textContent}${n === st.step ? ", 지금 단계" : done ? ", 마침" : left ? ", 넘어감(남은 확인 있음)" : ""}`);
    b.title = left ? (n === 3 ? `작업계획서 확인 ${st.checked.size}/${st.wp ? st.wp.plans.length : 0} · 확인하지 않고 넘어감` : `위험 체크리스트 확인 필요 ${st.ck ? ckCount().left : 0}개 남음`) : "";
    b.disabled = !canGo(n) || n === st.step;
    if (n === st.step) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
  });
  if (typeof fitAppbar === "function") fitAppbar();
  const cur = document.querySelector("#stepper li.current"), sc = $(".stepper");   // a narrow stepper scrolls to the current step
  if (cur && sc.scrollWidth > sc.clientWidth) sc.scrollLeft = cur.offsetLeft - (sc.clientWidth - cur.offsetWidth) / 2;
}
function goStep(n) {
  if (!canGo(n)) return;
  st.step = n; if (st.doc) saveDraft();
  if (n === 5) st.fromSummary = false;
  if (document.body.dataset.role !== "foreman") { paintStepper(); return; }
  $("#back-sum").hidden = !(st.fromSummary && (n === 2 || n === 3));
  $("#ck-next").innerHTML = st.fromSummary && n === 4 ? `${icon("i-list")}제출 확인으로 돌아가기` : `다음: 제출 확인${icon("i-right")}`;
  if (n === 1) show("s-upload");
  else if (n === 2) {
    $("#go-plans").innerHTML = `${st.wp ? "다음: 위험 체크리스트" : "다음: 작업계획서 올리기"}${icon("i-right")}`;
    $("#go-plans-note").textContent = `허가서 검토를 마쳤습니다. 다음은 ${st.wp ? "위험 체크리스트" : "작업계획서 올리기"}입니다.`;   // plans not read yet: they come first
    openPane("chat"); show("s-edit"); showDoc(0);
  }
  else if (n === 3) {
    nextFromPlans();
    if (!st.wp) { show("s-plans"); renderPlanFiles(); }
    else { openPane("plans"); show("s-edit"); showDoc(firstPlan()); renderPlanList(); }
  } else if (n === 4) { show("s-check"); openChecklist(); }
  else if (n === 5) { renderSummary(); show("s-submit"); }
  paintStepper();
  $("#main").focus({ preventScroll: true });
  window.scrollTo(0, 0);
}
document.querySelectorAll("#stepper button").forEach((b) => b.onclick = () => goStep(+b.closest("li").dataset.step));
// 1 생산부서·작업반장 / 2 안전관리자: the foreman's review stays as it was while the other view is open
function setRole(role) {
  document.body.dataset.role = role;
  // the address keeps the view (#safety): a reload or a bookmark opens the same one
  if (role !== "safety") history.replaceState(null, "", location.pathname + location.search);
  else if (!location.hash.startsWith("#safety")) history.replaceState(null, "", "#safety");   // keeps #safety/<day>/<doc>
  if (role === "safety") { show("s-safety"); $("#main").focus({ preventScroll: true }); fitAppbar(); sfLoad(); }
  else if (st.loading) show("s-load");                 // back from the first screen while a file is being read
  else goStep(canGo(st.step) ? st.step : 3);          // back from the first screen: the review goes on where it was
}
// the first screen (QA #25): pick whose view and 로그인. Nothing is checked; the password is never kept or sent
const LOGIN_ID = "croscan.loginId";
function showLogin() {
  document.body.dataset.role = "login";
  history.replaceState(null, "", location.pathname + location.search);
  show("s-login"); fitAppbar();
  let id = ""; try { id = localStorage.getItem(LOGIN_ID) || ""; } catch (e) { /* storage off: nothing remembered */ }
  $("#login-id").value = id; $("#login-save").checked = !!id; $("#login-pw").value = "";
  $("#login-pw").type = "password"; loginEye(false);
  $("#main").focus({ preventScroll: true });
}
function loginRole(role, focus) {
  document.querySelectorAll("#login-roles [data-login]").forEach((b) => {
    const on = b.dataset.login === role;
    b.setAttribute("aria-checked", String(on)); b.tabIndex = on ? 0 : -1;
    if (on && focus) b.focus();
  });
}
function loginEye(on) {
  $("#login-pw").type = on ? "text" : "password";
  const b = $("#login-eye"); b.setAttribute("aria-pressed", String(on)); b.setAttribute("aria-label", on ? "비밀번호 숨기기" : "비밀번호 보기");
  b.querySelector("use").setAttribute("href", on ? "#i-eye-off" : "#i-eye");
}
$("#login-roles").addEventListener("click", (e) => { const b = e.target.closest("[data-login]"); if (b) loginRole(b.dataset.login); });
$("#login-roles").addEventListener("keydown", (e) => {          // a radio group: the arrows move the choice
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
  e.preventDefault();
  loginRole(document.querySelector('#login-roles [aria-checked="true"]').dataset.login === "foreman" ? "safety" : "foreman", true);
});
$("#login-eye").onclick = () => loginEye($("#login-pw").type === "password");
$("#login-find").onclick = () => toast("시연판은 계정 없이 쓰므로 비밀번호 찾기는 없습니다. 바로 「로그인」을 눌러 주세요.");
$("#login-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const id = $("#login-id").value.trim();
  try { if ($("#login-save").checked && id) localStorage.setItem(LOGIN_ID, id); else localStorage.removeItem(LOGIN_ID); } catch (err) { /* not kept */ }
  $("#login-pw").value = "";
  setRole(document.querySelector('#login-roles [aria-checked="true"]').dataset.login);
});
// the croScan logo goes back to the first screen (QA #9, #25); the review in progress stays as it was
$(".brand").addEventListener("click", showLogin);
$(".brand").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showLogin(); } });
// one row when everything fits at this width and text size; otherwise the stepper gets its own row
const bar = $(".appbar");
function fitAppbar() {
  bar.classList.remove("stack", "compact");
  const gap = parseFloat(getComputedStyle(bar).columnGap) || 0, pad = parseFloat(getComputedStyle(bar).paddingLeft) * 2;
  const need = () => $(".brand").scrollWidth + $("#stepper").scrollWidth + $(".appbar-tools").scrollWidth + gap * 2 + pad;
  // first the tool buttons lose their words (icons stay, with their names for screen readers), then the stepper wraps
  if (need() > bar.clientWidth) bar.classList.add("compact");
  bar.classList.toggle("stack", need() > bar.clientWidth);
}
new ResizeObserver(fitAppbar).observe(bar);
document.fonts && document.fonts.ready.then(fitAppbar);

// ---------------------------------------------------------------- loading: the server reports each real stage as it finishes
const PERMIT_STEPS = [["upload", "올리기"], ["open", "PDF 확인"], ["odl", "표·칸 구조 읽기"],
  ["map", "양식 칸에 값 넣기"], ["review", "빈칸·형식·시간·장소 살펴보기"]];
const PLAN_STEPS = [["upload", "올리기"], ["wp", "작업계획서 읽기 (문서번호로 한 건씩)"]];
let ORDER = [];
function resetSteps(title, name, size, list) {
  $("#load-eyebrow").textContent = title;
  $("#lname").textContent = name; $("#lsize").textContent = size ? fmtKB(size) : "";
  $("#lerr").hidden = true; $("#lback").hidden = true;
  const ol = $("#steps"); ol.innerHTML = ""; ORDER = list.map(([k]) => k);
  for (const [k, label] of list) {
    const li = el("li"); li.dataset.s = k;
    li.innerHTML = `<i aria-hidden="true"></i><div><b>${esc(label)}</b><span></span></div><em></em>`;
    ol.appendChild(li);
  }
}
function stepState(s, cls, msg, t) {
  const li = document.querySelector(`#steps li[data-s="${s}"]`);
  if (!li) return;
  li.className = cls;
  if (msg != null) li.querySelector("span").textContent = msg;
  if (t != null) li.querySelector("em").textContent = t + "초";
}
function nextRun(after) { const i = ORDER.indexOf(after); if (i >= 0 && i + 1 < ORDER.length) stepState(ORDER[i + 1], "run"); }
function progressBar(step) {
  const li = document.querySelector(`#steps li[data-s="${step}"] div`);
  const bar = el("div", "bar"); bar.innerHTML = "<b></b>"; li.appendChild(bar);
  return bar.firstChild;
}
function fail(msg, back) {
  const run = document.querySelector("#steps li.run");
  if (run) run.className = "fail";
  $("#lerr").textContent = msg; $("#lerr").hidden = false;
  $("#lback").hidden = false; $("#lback").onclick = back;
}
// NDJSON lines from one streamed request
function streamLines(xhr, handle) {
  let seen = 0;
  return () => {
    const txt = xhr.responseText;
    let nl;
    while ((nl = txt.indexOf("\n", seen)) >= 0) {
      const line = txt.slice(seen, nl); seen = nl + 1;
      if (line.trim()) handle(JSON.parse(line));
    }
  };
}

// ---------------------------------------------------------------- 1. 허가서 올리기: kind (picked, not guessed) + one PDF
const pick = { kind: null, file: null, plans: [] };
function updateStart() {
  $("#start").disabled = !(pick.kind && pick.file);
  const miss = [!pick.kind && "허가서 종류", !pick.file && "허가서 PDF"].filter(Boolean);
  $("#start-hint").textContent = miss.length === 2 ? "허가서 종류를 고르고 PDF를 올리면 시작할 수 있습니다."
    : miss.length ? `${miss[0]}만 남았습니다.`
    : st.doc && !sameSource() ? "다른 허가서(또는 종류)로 바꿨습니다. 「검토 시작」을 누르면 지금까지의 검토는 지우고 새로 읽습니다."
    : st.doc ? "지금 검토 중인 허가서입니다. 「검토 시작」을 누르면 처음부터 다시 읽습니다." : "준비됐습니다. 「검토 시작」을 눌러 주세요.";
  paintStepper();
}
fetch("/api/kinds").then((r) => r.json()).then((list) => {
  const box = $("#kinds");
  for (const k of list) {
    const b = el("button", "kind");
    b.type = "button"; b.setAttribute("role", "radio"); b.setAttribute("aria-checked", "false");
    b.innerHTML = `${icon(KIND_ICON[k.id] || "i-file")}<b>${esc(k.label)}</b>`;
    b.setAttribute("aria-label", `${k.label} 작업 허가서`);
    b.onclick = () => {
      if (st.loading) return;
      pick.kind = k.id;
      box.querySelectorAll(".kind").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); x.tabIndex = x === b ? 0 : -1; });
      updateStart();
    };
    box.appendChild(b);
  }
  // radio group keys: arrows move the choice, as a radio group does
  box.addEventListener("keydown", (e) => {
    const ks = [...box.querySelectorAll(".kind")], i = ks.indexOf(document.activeElement);
    if (i < 0 || !["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key)) return;
    e.preventDefault();
    const n = ks[(i + (["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : ks.length - 1)) % ks.length];
    n.focus(); n.click();
  });
}).catch(() => { $("#start-hint").textContent = "서버에 연결하지 못했습니다. 잠시 뒤 새로 고침해 주세요."; });
function openFile(file) {
  if (st.loading) return;                          // the file being read cannot be swapped
  if (!/\.pdf$/i.test(file.name) && file.type !== "application/pdf") { toast("PDF 파일만 올릴 수 있습니다."); return; }
  if (file.size > 50 * 1024 * 1024) { toast("50MB 이하 PDF만 올릴 수 있습니다."); return; }
  pick.file = file;
  $("#drop").classList.add("has");
  $("#drop-main").textContent = file.name;
  $("#drop-sub").textContent = `${fmtKB(file.size)} · 다른 파일로 바꾸려면 누르세요`;
  updateStart();
  fileHash(file).then((hash) => {
    if (pick.file !== file || !pick.kind) return;
    try { if (localStorage.getItem(draftKey({ kind: pick.kind, hash }))) $("#drop-sub").textContent += " · 이 기기에 검토하던 내용이 있습니다 (시작하면 이어서 할지 묻습니다)"; } catch (e) { /* blocked */ }
  });
}
function clearFile() {
  pick.file = null;
  $("#drop").classList.remove("has");
  $("#drop-main").innerHTML = "PDF를 여기로 끌어 놓거나 <u>눌러서 고르기</u>";
  $("#drop-sub").textContent = "전산에서 내려받은 PDF · 1개 · 50MB까지";
  updateStart();
}
$("#file").addEventListener("change", (e) => { if (e.target.files[0]) openFile(e.target.files[0]); e.target.value = ""; });
$("#start").onclick = async () => {
  if (st.loading || !(pick.kind && pick.file)) return;
  if (st.doc && !exported() && !confirm("지금 검토 중인 내용(답·고친 칸)은 지워지고 새로 읽습니다. 계속할까요?")) return;
  const src = { file: pick.file, kind: pick.kind };
  st.loading = true; $("#start").disabled = true; paintStepper();
  try { src.hash = await fileHash(src.file); } catch (e) { src.hash = `${src.file.size}-${src.file.lastModified}`; }
  const fd = new FormData(); fd.append("file", src.file); fd.append("kind", src.kind);
  parseRequest(fd, src);
};
// a checksum of the PDF's bytes (FNV-1a): the 임시저장 belongs to this exact file, not to any file of the same name
async function fileHash(file) {
  const b = new Uint8Array(await file.arrayBuffer());
  let h = 0x811c9dc5;
  for (let i = 0; i < b.length; i++) { h ^= b[i]; h = Math.imul(h, 0x01000193) >>> 0; }
  return `${b.length}-${h.toString(16)}`;
}
// one request does the upload and streams the server's stage reports back
function parseRequest(fd, src) {
  const file = src.file;
  st.loading = true; paintStepper();
  resetSteps("2단계 · 허가서 읽는 중", file.name, file.size, PERMIT_STEPS);
  if (document.body.dataset.role === "foreman") show("s-load");             // not over the first screen (로그인)
  stepState("upload", "run", "0%");
  const xhr = new XMLHttpRequest(), t0 = performance.now(), bar = progressBar("upload");
  const back = () => { st.loading = false; updateStart(); goStep(1); };
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const p = Math.round(e.loaded / e.total * 100);
    bar.style.width = p + "%";
    stepState("upload", "run", `${p}% · ${fmtKB(e.loaded)} / ${fmtKB(e.total)}`);
  };
  xhr.upload.onload = () => { stepState("upload", "done", "서버로 보냈습니다", ((performance.now() - t0) / 1000).toFixed(1)); bar.parentNode.remove(); nextRun("upload"); };
  xhr.onprogress = streamLines(xhr, (ev) => {
    if (ev.step === "error") return fail(ev.msg, back);
    if (ev.step === "done") return setTimeout(() => { st.loading = false; updateStart(); openDoc(ev.doc, src); }, 350);
    stepState(ev.step, "done", ev.msg, ev.t); nextRun(ev.step);
  });
  xhr.onload = () => { xhr.onprogress(); if (xhr.status >= 400) fail(`서버 오류 ${xhr.status}`, back); };
  xhr.onerror = () => fail("서버에 연결하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.", back);
  xhr.open("POST", "/api/parse"); xhr.send(fd);
}
function openDoc(doc, src) {
  tagRules(doc); errUi.shown.clear();
  st.doc = doc; st.findings = doc.findings || []; st.page = doc.pages[0].no;
  st.docs = [doc, ...(st.wp ? st.wp.plans.map((p) => p.doc || null) : [])]; st.di = 0; st.reviewed = false;
  st.src = src; st.rev = 0; st.exportedRev = -1; st.reviewPending = false; st.draftPlans = null; st.fromSummary = false;
  st.ck = null; st.draftCk = null; $("#sub-docs").hidden = true;
  st.answers = []; st.live = false; st.sid = null; st.srev = null; st.props = [];   // nothing is saved over the 임시저장 until it is resumed or dropped
  $("#fname").textContent = src.file.name;
  goStep(2);
  fit(); left.scrollTop = 0;
  offerResume();
}

// files from a drop, folders opened recursively (entries must be taken before the first await)
async function droppedFiles(dt) {
  const entries = [...(dt.items || [])].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return [...dt.files];
  const out = [];
  const walk = async (en) => {
    if (en.isFile) out.push(await new Promise((ok, no) => en.file(ok, no)));
    else if (en.isDirectory) {
      const r = en.createReader();
      for (let b; (b = await new Promise((ok, no) => r.readEntries(ok, no))).length;) for (const x of b) await walk(x);
    }
  };
  for (const en of entries) await walk(en);
  return out;
}
const isPdf = (f) => /\.pdf$/i.test(f.name) || f.type === "application/pdf";
for (const z of [$("#drop"), $("#wpdrop")]) {
  z.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); z.classList.add("drag"); });
  z.addEventListener("dragleave", () => z.classList.remove("drag"));
}
$("#drop").addEventListener("drop", (e) => {
  e.preventDefault(); e.stopPropagation(); $("#drop").classList.remove("drag");
  const fs = [...e.dataTransfer.files];
  if (fs.length > 1) { toast("허가서는 PDF 1개만 넣습니다. 작업계획서는 1단계에서 올립니다."); return; }
  if (fs[0]) openFile(fs[0]);
});
$("#wpdrop").addEventListener("drop", async (e) => {
  e.preventDefault(); e.stopPropagation(); $("#wpdrop").classList.remove("drag");
  addPlans(await droppedFiles(e.dataTransfer));
});
// a drop anywhere on an upload screen goes to that screen's box
document.body.addEventListener("dragover", (e) => e.preventDefault());
document.body.addEventListener("drop", async (e) => {
  e.preventDefault();
  if (!$("#s-upload").hidden) { const f = [...e.dataTransfer.files][0]; if (f) openFile(f); }
  else if (!$("#s-plans").hidden) addPlans(await droppedFiles(e.dataTransfer));
});

// ---------------------------------------------------------------- 3. 작업계획서: many files in one request
function addPlans(files) {
  const pdfs = files.filter(isPdf), have = new Set(pick.plans.map((f) => `${f.name}|${f.size}|${f.lastModified}`));
  let dup = 0;
  for (const f of pdfs) {
    const k = `${f.name}|${f.size}|${f.lastModified}`;
    if (have.has(k)) { dup++; continue; }
    have.add(k); pick.plans.push(f);
  }
  renderPlanFiles(files.length - pdfs.length, dup);
}
function renderPlanFiles(skipped = 0, dup = 0) {
  const ul = $("#wp-list"); ul.innerHTML = "";
  pick.plans.forEach((f, i) => {
    const li = el("li"), s = el("span", "", f.webkitRelativePath || f.name), em = el("em", "", fmtKB(f.size)), x = el("button", "btn icon small");
    x.type = "button"; x.innerHTML = icon("i-x"); x.setAttribute("aria-label", `${f.name} 빼기`);
    x.onclick = () => { pick.plans.splice(i, 1); renderPlanFiles(); };
    li.append(icon2("i-pdf"), s, em, x); ul.appendChild(li);
  });
  const n = pick.plans.length, total = pick.plans.reduce((a, f) => a + f.size, 0);
  $("#wp-bar").hidden = !n;
  $("#wp-count").textContent = `${n}개 · ${fmtKB(total)}` + (skipped ? ` · PDF가 아닌 ${skipped}개 뺌` : "") + (dup ? ` · 같은 파일 ${dup}개 뺌` : "");
  $("#wpdrop").classList.toggle("has", n > 0);
  $("#wp-main").innerHTML = n ? `${n}개 넣음 · 더 끌어 놓거나 <u>눌러서 더하기</u>` : "작업계획서 PDF를 끌어 놓거나 <u>눌러서 고르기</u>";
  $("#wp-start").disabled = !n;
}
function icon2(id) { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("class", "ic"); s.setAttribute("aria-hidden", "true"); s.innerHTML = `<use href="#${id}"/>`; return s; }
$("#wpfile").addEventListener("change", (e) => { addPlans([...e.target.files]); e.target.value = ""; });
$("#wpdir").addEventListener("change", (e) => { addPlans([...e.target.files]); e.target.value = ""; });
$("#wp-dirbtn").onclick = () => $("#wpdir").click();
$("#wp-clear").onclick = () => { pick.plans = []; renderPlanFiles(); };
$("#wp-back").onclick = () => goStep(3);                 // from 「더 올리기」 back to the list (hidden before any plan)
$("#plans-add").onclick = () => { show("s-plans"); renderPlanFiles(); };
$("#wp-start").onclick = () => pick.plans.length && planRequest();
function planRequest() {
  const n = pick.plans.length, size = pick.plans.reduce((a, f) => a + f.size, 0);
  resetSteps("1단계 · 작업계획서 읽는 중", `작업계획서 ${n}개`, size, PLAN_STEPS); show("s-load");
  st.loading = true; paintStepper();
  stepState("upload", "run", "0%");
  const fd = new FormData();
  pick.plans.forEach((f) => fd.append("files", f, f.name));
  const xhr = new XMLHttpRequest(), t0 = performance.now(), bar = progressBar("upload");
  let bad = 0;
  const back = () => { st.loading = false; paintStepper(); show("s-plans"); renderPlanFiles(); };
  xhr.upload.onprogress = (e) => {
    if (!e.lengthComputable) return;
    const p = Math.round(e.loaded / e.total * 100);
    bar.style.width = p + "%";
    stepState("upload", "run", `${p}% · ${fmtKB(e.loaded)} / ${fmtKB(e.total)}`);
  };
  xhr.upload.onload = () => { stepState("upload", "done", "서버로 보냈습니다", ((performance.now() - t0) / 1000).toFixed(1)); bar.parentNode.remove(); stepState("wp", "run", `파일 0/${n}`); };
  xhr.onprogress = streamLines(xhr, (ev) => {
    if (ev.step === "wp_error") return fail(ev.msg, back);
    if (ev.step === "wp_file") {
      if (ev.error) bad++;
      stepState("wp", "run", `파일 ${ev.i}/${ev.n} · 계획서 ${ev.plans}건${bad ? ` · 못 읽은 파일 ${bad}개` : ""}`);
    } else if (ev.step === "wp_done") {
      if (!ev.plans.length) {
        const why = ev.files.filter((f) => f.error).slice(0, 3).map((f) => `${f.name}: ${f.error}`).join(" / ");
        return fail(`작업계획서를 한 건도 읽지 못했습니다. ${why}`, back);
      }
      stepState("wp", "done", `계획서 ${ev.plans.length}건 · 파일 ${ev.files.length}개${bad ? ` (못 읽은 파일 ${bad}개)` : ""}`,
        ((performance.now() - t0) / 1000).toFixed(1));
      mergePlans(ev);
      setTimeout(() => { st.loading = false; goStep(3); }, 350);
    }
  });
  xhr.onload = () => { xhr.onprogress(); if (xhr.status >= 400) fail(`서버 오류 ${xhr.status}`, back); };
  xhr.onerror = () => fail("서버에 연결하지 못했습니다. 연결을 확인하고 다시 시도해 주세요.", back);
  xhr.open("POST", "/api/workplans"); xhr.send(fd);
}
// 「더 올리기」 reads every file again; a plan read before (the same pages of the same files: values can be edited,
// where they came from cannot) keeps its 확인 and its edits
const planId = (p) => {
  if (!p._id) { const size = Object.fromEntries(pick.plans.map((f) => [f.name, f.size]));
    p._id = p.pages.map((x) => `${x.file}:${size[x.file] || ""}:${x.page}`).join(","); }
  return p._id;
};
function mergePlans(ev) {
  // what was there before: the 임시저장 of an earlier visit (「이어서 하기」), overlaid by this visit's plans
  const old = new Map(Object.entries(st.draftPlans || {}).map(([id, d]) => [id, { p: { doc: { fields: Object.fromEntries(Object.entries(d.edits || {}).map(([k, v]) => [k, { value: v, original: null, editedBy: "직접 수정" }])) } }, checked: d.checked }]));
  if (st.wp) st.wp.plans.forEach((p, i) => old.set(planId(p), { p, checked: st.checked.has(i) }));
  ev.plans.forEach(planId);
  st.checked = new Set(); st.planOpen = null;
  let kept = 0;
  ev.plans.forEach((p, i) => {
    const o = old.get(planId(p));
    if (!o) return;
    if (o.checked) st.checked.add(i);
    if (o.p.doc && p.doc) for (const [k, f] of Object.entries(o.p.doc.fields)) {
      if (String(f.value) !== String(f.original) && p.doc.fields[k]) { p.doc.fields[k].value = f.value; p.doc.fields[k].editedBy = f.editedBy; kept++; }
    }
  });
  st.wp = ev; st.rev++;
  st.docs = [st.doc, ...ev.plans.map((p) => p.doc || null)];       // st.doc may still be null: the plans come first
  ev.plans.forEach((p) => p.doc && editCount(p.doc) && syncPlan(p));
  if (kept) scheduleSave();                         // the edits go to the new upload on the server too
  if (old.size) toast(`작업계획서 ${ev.plans.length}건을 다시 읽었습니다. 이미 확인한 ${st.checked.size}건과 고친 칸 ${kept}개는 그대로 두었습니다.`);
  wpPrepare();
}
// the 임시저장 of an earlier visit on plans read before it was resumed: its 확인 and the edits of fields not touched now
function applyDraftPlans() {
  let kept = 0;
  st.wp.plans.forEach((p, i) => {
    const d = st.draftPlans[planId(p)];
    if (!d) return;
    const edits = d.edits || {};
    let here = 0;
    if (p.doc) for (const [k, v] of Object.entries(edits)) {
      const f = p.doc.fields[k];
      if (f && String(f.value) === String(f.original) && String(v) !== String(f.value)) { f.value = v; f.editedBy = "직접 수정"; kept++; here++; }
    }
    const now = p.doc ? changedFields(p.doc) : {};
    const same = Object.keys(now).length === Object.keys(edits).length && Object.entries(edits).every(([k, v]) => String(now[k]) === String(v));
    if (d.checked && same) st.checked.add(i); else if (here) st.checked.delete(i);
    if (p.doc && editCount(p.doc)) syncPlan(p);
  });
  if (kept) scheduleSave();
  bump(); paintStepper();
}
const firstPlan = () => {
  const open = st.docs.findIndex((d, k) => k > 0 && d && !st.checked.has(k - 1));
  const any = st.docs.findIndex((d, k) => k > 0 && d);
  return open > 0 ? open : any > 0 ? any : 0;
};

// right pane: questions (2단계) or the plan list (3단계); on phones one pane at a time
function openPane(which) {
  $("#p-chat").hidden = which !== "chat"; $("#p-plans").hidden = which !== "plans";
  $("#ps-side-label").textContent = which === "chat" ? "질문" : "작업계획서 목록";
  $("#v-sheet").hidden = which !== "chat";
  if (which !== "chat" && st.view === "sheet") setView("form");
  phonePane("side");
}
function phonePane(p) {
  $("#s-edit").dataset.pane = p;
  $("#ps-doc").setAttribute("aria-selected", p === "doc"); $("#ps-side").setAttribute("aria-selected", p === "side");
  if (p === "doc" && D()) requestAnimationFrame(() => st.fitMode && fit());
}
$("#ps-doc").onclick = () => phonePane("doc");
$("#ps-side").onclick = () => phonePane("side");

// ---------------------------------------------------------------- document toolbar
// the document on screen: 0 = the permit (the one the review works on), 1.. = 작업계획서
const D = () => (st.docs && st.docs[st.di]) || st.doc;
const shownPlan = () => (st.di > 0 && st.wp ? st.wp.plans[st.di - 1] : null);
function showDoc(i, page) {
  if (!st.docs || i < 0 || i >= st.docs.length || !st.docs[i]) { renderNav(); return; }
  if (i > 0 && st.fedit) exitEdit(false);
  st.di = i; st.page = page || D().pages[0].no;
  if (i > 0 && st.view === "sheet") setView("form");
  closeInspector();
  renderTabs(); render(); fit(); left.scrollTop = 0; updateChanges();
  if (i === 0 && st.asked) setTimeout(() => markAsk(st.asked.keys));
  const nx = st.docs[i + 1];                                   // the next plan's pages load in the background
  if (nx) for (const p of nx.pages) { new Image().src = p.background; }
  if (i > 0) renderPlanList();
}
// ‹ › : pages of the permit; on a 작업계획서 they go to the previous / next plan (the 1쪽·2쪽 buttons switch pages: QA #16)
const planStep = (d) => { for (let i = st.di + d; i > 0 && i < st.docs.length; i += d) if (st.docs[i]) return i; return -1; };
function stepPage(d) {
  if (st.di > 0) { const i = planStep(d); if (i > 0) showDoc(i); return; }
  const ps = D().pages, k = ps.findIndex((p) => p.no === st.page) + d;
  if (k >= 0 && k < ps.length) goPage(ps[k].no);
}
function goPage(no) {
  st.page = no; closeInspector(); renderTabs();
  if (st.view === "list") { document.getElementById(`fl-page-${no}`)?.scrollIntoView({ block: "start" }); return; }
  render(); left.scrollTop = 0;
}
$("#pgprev").onclick = () => stepPage(-1);
$("#pgnext").onclick = () => stepPage(1);
function renderNav() {
  const p = shownPlan();
  $("#docname").textContent = p ? `작업계획서 ${st.di}/${st.wp.plans.length} · ${p.title || p.work_no || p.doc_no || ""}` : "허가서";
  $("#fname").textContent = p ? (p.company || "") : (st.src ? st.src.file.name : "");
  if (!D()) return;
  const ps = D().pages, k = ps.findIndex((x) => x.no === st.page);
  if (st.di > 0) {
    $("#pager").hidden = false;
    $("#pgprev").disabled = planStep(-1) < 0; $("#pgnext").disabled = planStep(1) < 0;
    $("#pgprev").setAttribute("aria-label", "이전 작업계획서"); $("#pgnext").setAttribute("aria-label", "다음 작업계획서");
    $("#pgprev").title = "이전 작업계획서"; $("#pgnext").title = "다음 작업계획서";
  } else {
    $("#pager").hidden = ps.length < 2;
    $("#pgprev").disabled = k <= 0; $("#pgnext").disabled = k >= ps.length - 1;
    $("#pgprev").setAttribute("aria-label", "이전 쪽"); $("#pgnext").setAttribute("aria-label", "다음 쪽");
    $("#pgprev").title = "이전 쪽"; $("#pgnext").title = "다음 쪽";
  }
  $("#wpsave").hidden = !st.di || (!st.wpSaved && !st.wpSaving && !$("#wpsave").classList.contains("bad"));
}
function renderTabs() {
  renderNav();
  const t = $("#tabs"), had = t.contains(document.activeElement); t.innerHTML = "";
  for (const p of D().pages) {
    const b = el("button", "", `${p.no}쪽`);
    if (st.di === 0) {
      const pm = st.doc.permits.find((x) => x.pages.includes(p.no));
      const copies = pm && pm.pages.length > 1 ? ` (사본 ${pm.pages.indexOf(p.no) + 1}/${pm.pages.length})` : "";
      b.textContent = `${p.no}쪽 · ${p.variant_label.split(" ").pop()}${copies}`;
      b.setAttribute("aria-label", `${p.no}쪽 ${p.kind_title} ${p.variant_label}, 승인번호 ${p.permit_no || "없음"}`);
    } else {
      b.setAttribute("aria-label", `${p.no}쪽, 원본 ${p.file} ${p.src_page}쪽`);
    }
    b.setAttribute("aria-pressed", p.no === st.page);
    b.onclick = () => goPage(p.no);
    t.appendChild(b);
    if (had && p.no === st.page) b.focus();
  }
}
function setView(v) {
  st.view = v;
  if (v !== "orig") st.origMark = null;
  document.querySelectorAll("#view button").forEach((x) => x.setAttribute("aria-pressed", x.dataset.v === v));
  if (v !== "sheet" && st.asked) setTimeout(() => markAsk(st.asked.keys));
  closeInspector();
  render();
}
document.querySelectorAll("#view button").forEach((b) => b.onclick = () => setView(b.dataset.v));

// ---------------------------------------------------------------- page viewer: zoom + pan
// Like common PDF / map viewers: the page stays centred while smaller than the pane, the wheel zooms around the
// cursor, the buttons zoom around the pane centre, and dragging the page moves it. Zooming only rescales the
// existing inputs, so a field being edited keeps its focus and caret.
const ZMIN = 0.25, ZMAX = 4;
const STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3, 4];
const clampZ = (z) => Math.min(ZMAX, Math.max(ZMIN, z));
const sheet = $("#sheet"), left = $("#left");
function setZoom(z, cx, cy) {
  z = clampZ(z);
  if (!D() || Math.abs(z - st.zoom) < 1e-4) return;
  const r = left.getBoundingClientRect();
  const mx = cx == null ? left.clientWidth / 2 : cx - r.left;        // anchor inside the pane
  const my = cy == null ? left.clientHeight / 2 : cy - r.top;
  const k = z / st.zoom;
  const px = left.scrollLeft + mx - sheet.offsetLeft;                // anchor point on the page (old px)
  const py = left.scrollTop + my - sheet.offsetTop;
  st.zoom = z; st.fitMode = false;
  applyScale();
  left.scrollLeft = px * k + sheet.offsetLeft - mx;                  // keep that point under the anchor
  left.scrollTop = py * k + sheet.offsetTop - my;
}
function stepZoom(dir) {
  const next = dir > 0 ? STEPS.find((s) => s > st.zoom + 1e-3) : [...STEPS].reverse().find((s) => s < st.zoom - 1e-3);
  setZoom(next ?? (dir > 0 ? ZMAX : ZMIN));
}
function fit() {
  if (!D() || !curPage() || htmlView()) return;
  const w = left.clientWidth - 32;
  if (w <= 0) { st.fitMode = true; return; }           // hidden (phone, other pane): fits when it is shown
  st.zoom = clampZ(w / (curPage().width * BASE));
  st.fitMode = true;
  applyScale();
}
$("#zin").onclick = () => stepZoom(1);
$("#zout").onclick = () => stepZoom(-1);
$("#zval").onclick = () => { fit(); left.scrollTop = 0; };
$("#zfit").onclick = () => { fit(); left.scrollTop = 0; };
new ResizeObserver(() => D() && st.fitMode && fit()).observe(left);
new ResizeObserver(() => { if (D() && st.view === "list" && splitList() !== !!sheet.querySelector(".fl-split")) render(); }).observe(left);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { if (closeDialogs()) return; if (st.fedit) { exitEdit(true); return; } closeInspector(); return; }
  if (!D() || $("#s-edit").hidden || document.querySelector(".sheet-modal:not([hidden])")) return;
  if (e.altKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) { e.preventDefault(); stepPage(e.key === "ArrowLeft" ? -1 : 1); }
});
// wheel over the page zooms at the cursor (smooth for trackpads, a step per notch for mice)
left.addEventListener("wheel", (e) => {
  if (!D() || htmlView() || !(e.ctrlKey || e.metaKey)) return;     // a plain wheel scrolls the page
  e.preventDefault();
  const dy = e.deltaMode === 1 ? e.deltaY * 33 : e.deltaY;
  setZoom(st.zoom * Math.exp(-Math.max(-120, Math.min(120, dy)) * 0.0018), e.clientX, e.clientY);
}, { passive: false });
// drag to pan (one finger or the mouse); two fingers pinch-zoom on touch screens
let pan = null;
const touches = new Map();
let pinch = null;
left.addEventListener("pointerdown", (e) => {
  if (htmlView()) return;
  if (e.pointerType === "touch") touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (touches.size === 2) {
    const [a, b] = [...touches.values()];
    pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), z: st.zoom };
    pan = null; return;
  }
  if (e.button !== 0) return;
  if (e.target.closest(".fi, .fc")) {
    // touch: a drag that starts on a field moves the page once it has moved a little; a tap still picks the field
    if (e.pointerType === "touch") pan = { x: e.clientX, y: e.clientY, sl: left.scrollLeft, st: left.scrollTop, id: e.pointerId, maybe: true };
    return;
  }
  pan = { x: e.clientX, y: e.clientY, sl: left.scrollLeft, st: left.scrollTop, id: e.pointerId };
  left.setPointerCapture(e.pointerId);
  left.classList.add("panning");
  if (document.activeElement?.classList?.contains("fi")) document.activeElement.blur();
  e.preventDefault();
});
left.addEventListener("pointermove", (e) => {
  if (touches.has(e.pointerId)) touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pinch && touches.size === 2) {
    const [a, b] = [...touches.values()];
    setZoom(pinch.z * Math.hypot(a.x - b.x, a.y - b.y) / pinch.d, (a.x + b.x) / 2, (a.y + b.y) / 2);
    return;
  }
  if (!pan || e.pointerId !== pan.id) return;
  if (pan.maybe) {
    if (Math.hypot(e.clientX - pan.x, e.clientY - pan.y) < 10) return;
    pan.maybe = false; left.setPointerCapture(pan.id); left.classList.add("panning"); document.activeElement?.blur?.();
  }
  left.scrollLeft = pan.sl - (e.clientX - pan.x);
  left.scrollTop = pan.st - (e.clientY - pan.y);
});
const endPan = (e) => {
  touches.delete(e.pointerId);
  if (touches.size < 2) pinch = null;
  if (!pan || e.pointerId !== pan.id) return;
  if (left.hasPointerCapture(pan.id)) left.releasePointerCapture(pan.id);
  left.classList.remove("panning");
  pan = null;
};
left.addEventListener("pointerup", endPan);
left.addEventListener("pointercancel", endPan);

const curPage = () => D() && D().pages.find((p) => p.no === st.page);
const htmlView = () => st.view === "sheet" || st.view === "list";
const fieldsOfPage = () => Object.entries(D().fields).filter(([, f]) => f.page === st.page);

// ---------------------------------------------------------------- form rendering
// The page is the PDF itself (rendered with the editable values erased); each value is an input laid exactly
// where the value was printed, in the printed font and size.
function pdfFont(name) {
  const n = (name || "").toLowerCase();
  if (n.includes("malgun")) return '"Malgun Gothic", "맑은 고딕", sans-serif';
  if (n.includes("arialunicode")) return '"Arial Unicode MS", Arial, "Malgun Gothic", sans-serif';
  if (n.includes("arial")) return 'Arial, "Malgun Gothic", sans-serif';
  if (n.includes("gulim")) return 'Gulim, "Malgun Gothic", sans-serif';
  if (n.includes("dotum")) return 'Dotum, "Malgun Gothic", sans-serif';
  return '"Malgun Gothic", Arial, sans-serif';
}
function render() {
  if (!D()) return;
  const p = curPage();
  sheet.innerHTML = "";
  if (st.view === "list") { sheet.classList.add("html"); renderFieldList(); $("#zval").textContent = "-"; return; }
  sheet.classList.remove("split");
  if (st.view === "sheet") {
    sheet.classList.add("html");
    const pv = el("section", "reflect-pv"); pv.id = "reflect-pv";
    pv.innerHTML = `<h3>사전검토 반영본 <span class="hint">제출 PDF의 앞부분 · 파란 글씨(①…)가 반영한 칸 · 업로드한 원본 파일은 그대로</span></h3><div class="reflect-pages"><p class="hint">반영본을 그리는 중…</p></div>`;
    sheet.appendChild(pv); reflectPreview();
    for (const [, h] of (st.aug ? st.aug.sheets : [])) { const d = el("div", "addendum"); d.innerHTML = h; sheet.appendChild(d); }
    if (!st.aug) sheet.appendChild(el("div", "addendum", "추가검토서를 만드는 중입니다…"));
    $("#zval").textContent = "-";
    return;
  }
  sheet.classList.remove("html");
  const img = new Image();
  img.src = st.view === "orig" ? p.image : p.background;
  img.className = "pageimg"; img.alt = st.view === "orig" ? `${p.no}쪽 원본` : ""; img.draggable = false;
  sheet.appendChild(img);
  const mk = st.view === "orig" && st.origMark && D().fields[st.origMark];
  if (mk && mk.layout && mk.page === st.page) { const m = el("div", "orig-mark"); m.dataset.key = st.origMark; m.setAttribute("aria-hidden", "true"); sheet.appendChild(m); }
  if (st.view !== "orig") {
    const flagged = st.di === 0 ? flagMap() : {};
    for (const [key, f] of fieldsOfPage()) {
      if (!f.layout) continue;
      const node = f.type === "check" ? checkInput(key, f) : fieldInput(key, f);
      decorate(node, f, flagged[key]);
      sheet.appendChild(node);
    }
  }
  applyScale();
}
// 칸 목록: every field of the document as a large labelled control (glove- and screen-reader-friendly, follows the
// 글자 크기 setting); edits are the same values as on the page
const SPLIT_W = 1080;                     // the document pane's width from which the 칸 목록 is split (QA #36)
const splitList = () => left.clientWidth >= SPLIT_W && D().pages.some((pg) => pg.image);
function renderFieldList() {
  if (splitList()) return renderFieldSplit();
  sheet.classList.remove("split");
  const box = el("div", "fieldlist");
  box.appendChild(el("p", "fl-intro", "읽어 낸 칸의 값만 모았습니다. 원본의 안내문과 표 모양은 「원본」 보기에서 볼 수 있습니다."));
  const flagged = st.di === 0 ? flagMap() : {};
  const asked = st.di === 0 && st.asked ? new Set(st.asked.keys || []) : new Set();
  const seen = new Set();
  for (const pg of D().pages) {
    const rows = Object.entries(D().fields).filter(([k, f]) => f.page === pg.no && f.type !== "image" && !seen.has(k));
    if (!rows.length) continue;
    const h = el("h3", "fl-page", `${pg.no}쪽`); h.id = `fl-page-${pg.no}`; box.appendChild(h);
    for (const [key, f] of rows) {
      for (const o of f.same || []) seen.add(o);
      const row = el("div", "fl-row"); row.dataset.key = key;
      const id = "fl-" + key.replace(/[^\w-]/g, "_");
      const lab = el("label", "fl-label"); lab.htmlFor = id;
      lab.innerHTML = `<b>${esc(f.name)}</b>` + (["text", "check"].includes(f.type) ? "" : `<span class="fl-type">${esc(TYPE_KO[f.type] || f.type)}</span>`);
      row.appendChild(lab);
      const fx = fmtLine(key, f), bc = bigControl(key, f, id); fmtTie(fx, bc);
      row.appendChild(bc);
      if (fx) row.appendChild(fx);
      const notes = el("div", "fl-notes");
      paintNotes(notes, key, f, flagged[key], asked.has(key));
      row.appendChild(notes);
      box.appendChild(row);
    }
  }
  sheet.appendChild(box);
}
// the fields in reading order, one per printed copy (as in the long list)
function listFields() {
  const out = [], seen = new Set();
  for (const pg of D().pages) {
    for (const [k, f] of Object.entries(D().fields)) {
      if (f.page !== pg.no || f.type === "image" || seen.has(k)) continue;
      for (const o of f.same || []) seen.add(o);
      out.push([k, f]);
    }
  }
  return out;
}
const pickVal = (f) => f.type === "check" ? (f.value ? "체크함" : "빈칸") : (String(f.value).trim() || "(빈칸)");
// QA #36: original page | short list (top) + the picked field's input (bottom)
function renderFieldSplit() {
  sheet.classList.add("split");
  const wrap = el("div", "fl-split"), fig = el("figure", "fl-orig"), side = el("div", "fl-side");
  wrap.style.setProperty("--fl-h", `${Math.max(420, left.clientHeight - 40)}px`);
  fig.innerHTML = `<figcaption class="hint"></figcaption><div class="fl-orig-in"><img alt="" draggable="false"><i class="orig-mark" hidden></i></div>`;
  const list = el("div", "fl-picks"); list.setAttribute("role", "listbox"); list.setAttribute("aria-label", "칸 목록");
  const flagged = st.di === 0 ? flagMap() : {}, rmap = reflectMap();
  let page = null;
  for (const [k, f] of listFields()) {
    if (f.page !== page) { page = f.page; list.appendChild(el("p", "fl-pick-page", `${page}쪽`)); }
    const b = el("button", "fl-pick"); b.type = "button"; b.dataset.key = k; b.setAttribute("role", "option");
    b.innerHTML = `<b>${esc(f.name)}</b><span class="v">${esc(pickVal(f))}</span><i class="st"></i>`;
    list.appendChild(b);
  }
  const edit = el("div", "fl-edit"); edit.setAttribute("aria-live", "polite");
  // QA #40·#41: on the permit the picked field is edited in the chat's box on the right, not under the list
  if (st.di === 0) side.append(el("p", "fl-intro", "칸을 고르면 오른쪽 입력창에서 고치고, 왼쪽 원본에서 위치를 봅니다. 「적용」하면 다음 빈칸으로 갑니다."), list);
  else side.append(el("p", "fl-intro", "칸을 고르면 아래에서 고치고, 왼쪽 원본에서 위치를 봅니다."), list, edit);
  wrap.append(fig, side); sheet.appendChild(wrap);
  list.addEventListener("click", (e) => { const b = e.target.closest(".fl-pick"); if (b) listSelect(b.dataset.key, true); });
  list.addEventListener("keydown", (e) => {             // ↑ ↓ move between fields
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    const bs = [...list.querySelectorAll(".fl-pick")], i = bs.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    const n = bs[Math.max(0, Math.min(bs.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    n.focus(); listSelect(n.dataset.key, false);
  });
  for (const [k, f] of listFields()) pickState(k, f, flagged[k], rmap[k]);
  const first = (st.sel && D().fields[st.sel] && st.sel) || (st.asked && (st.asked.keys || []).find((k) => D().fields[k])) || (listFields()[0] || [])[0];
  if (st.di === 0 && chatEdit()) { if (st.fedit) listMark(st.fedit); else if (first) { listMark(first); listOrig(first); } }
  else if (first) listSelect(first, false);
}
// a row's small marks: format problem, a croScan note, what the 반영본 writes
function pickState(key, f, fl, rf) {
  const b = sheet.querySelector(`.fl-pick[data-key="${CSS.escape(key)}"]`);
  if (!b) return;
  const fillv = rf && rf.mode === "fill" && !String(f.value).trim() ? `${rf.mark} ${rf.text}` : "";
  b.querySelector(".v").textContent = fillv || pickVal(f);
  b.classList.toggle("answered", !!fillv);
  const bad = !valid(f, f.value), note = fl && fl.length;
  b.classList.toggle("bad", bad); b.classList.toggle("flag", !bad && !!note); b.classList.toggle("changed", String(f.value) !== String(f.original));
  b.querySelector(".st").textContent = bad ? "형식" : rf ? rf.mark : note ? "확인" : "";
}
function listMark(key) {
  sheet.querySelectorAll(".fl-pick").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.key === key)));
  const cur = sheet.querySelector(`.fl-pick[data-key="${CSS.escape(key)}"]`);
  if (cur) cur.scrollIntoView({ block: "nearest" });
}
function listSelect(key, focus) {
  const f = D().fields[key];
  if (!f) return;
  if (st.di === 0 && chatEdit()) { selectField(key, focus ? "list" : "listkey"); return; }
  st.sel = key;
  listMark(key);
  const edit = sheet.querySelector(".fl-edit");
  edit.innerHTML = "";
  const row = el("div", "fl-row"); row.dataset.key = key;
  const id = "fl-" + key.replace(/[^\w-]/g, "_");
  const lab = el("label", "fl-label"); lab.htmlFor = id;
  lab.innerHTML = `<b>${esc(f.name)}</b>` + (["text", "check"].includes(f.type) ? "" : `<span class="fl-type">${esc(TYPE_KO[f.type] || f.type)}</span>`) + `<span class="fl-pg">${f.page}쪽</span>`;
  const fx = fmtLine(key, f), bc = bigControl(key, f, id); fmtTie(fx, bc);
  const notes = el("div", "fl-notes");
  row.append(lab, bc); if (fx) row.appendChild(fx); row.appendChild(notes);
  paintNotes(notes, key, f, st.di === 0 ? flagMap()[key] : null, st.di === 0 && st.asked && (st.asked.keys || []).includes(key));
  edit.appendChild(row);
  listOrig(key);
  if (focus) bc.focus({ preventScroll: true });
}
// the original page beside the 칸 목록: the page of the field in use (else the current page), its place outlined
function listOrig(key) {
  const fig = sheet.querySelector(".fl-orig");
  if (!fig) return;
  const f = key && D().fields[key], no = f && f.page ? f.page : st.page, pg = D().pages.find((x) => x.no === no) || D().pages[0];
  const img = fig.querySelector("img"), mk = fig.querySelector(".orig-mark");
  if (img.dataset.no !== String(pg.no)) { img.src = pg.image; img.dataset.no = pg.no; img.alt = `${pg.no}쪽 원본`; }
  const b = f && f.layout && f.layout.box;
  mk.hidden = !b;
  if (b) Object.assign(mk.style, { left: `${b[0] / pg.width * 100}%`, top: `${b[1] / pg.height * 100}%`, width: `${(b[2] - b[0]) / pg.width * 100}%`, height: `${(b[3] - b[1]) / pg.height * 100}%` });
  fig.querySelector("figcaption").textContent = f ? `원본 ${pg.no}쪽 · 「${f.name}」 위치` : `원본 ${pg.no}쪽 · 칸을 고르면 원본에 위치가 표시됩니다`;
  // the place stays in view in its own panel (the panel scrolls, not the page: QA #38)
  if (b) requestAnimationFrame(() => { const r = mk.getBoundingClientRect(), o = fig.getBoundingClientRect();
    if (r.top < o.top || r.bottom > o.bottom) fig.scrollTop += r.top - o.top - (o.height - r.height) / 2; });
}
// one large control for a field, used by the 칸 목록 and the 선택한 칸 card
function bigControl(key, f, id) {
  if (f.type === "check") {
    const b = el("button", "btn check-toggle"); b.type = "button"; b.id = id;
    const paint = () => { b.setAttribute("aria-pressed", !!f.value); b.innerHTML = f.value ? `${icon("i-check")}체크함` : "빈칸 (누르면 체크)"; };
    b.onclick = () => { f.value = !f.value; paint(); syncNode(key, f); edited(key, f); refreshNotes(key, f); };
    paint(); return b;
  }
  const multi = f.layout && f.layout.multi;
  const inp = el(multi ? "textarea" : "input", "big-input" + (f.type === "code" ? " code" : "")); inp.id = id; inp.dataset.fkey = key;
  if (!multi) inp.type = "text"; else inp.rows = 3;
  inp.value = f.value; inp.spellcheck = false;
  if (["count", "date", "time"].includes(f.type)) inp.inputMode = "numeric";
  if (f.type === "number") inp.inputMode = "decimal";
  if (f.type === "phone") inp.inputMode = "tel";
  if (hintFor(key, f)) inp.placeholder = hintFor(key, f);
  inp.setAttribute("aria-invalid", badShown(key, f));
  watchErr(inp, key, f, () => inp.setAttribute("aria-invalid", badShown(key, f)));
  inp.addEventListener("input", () => {
    if (CLEAN[f.type]) { const c = CLEAN[f.type](inp.value); if (c !== inp.value) { const at = inp.selectionStart; inp.value = c; inp.setSelectionRange(at, at); } }
    f.value = inp.value; inp.setAttribute("aria-invalid", badShown(key, f));
    syncNode(key, f); edited(key, f); refreshNotes(key, f);
  });
  return inp;
}
// the same value on the page (if it is drawn) follows the big control
function syncNode(key, f) {
  const n = sheet.querySelector(`.fi[data-key="${CSS.escape(key)}"], .fc[data-key="${CSS.escape(key)}"]`);
  if (!n) return;
  if (n.classList.contains("fc")) setCheck(n, f); else n.value = f.value;
  decorate(n, f, null);
}
function paintNotes(box, key, f, fl, asked) {
  const changed = String(f.value) !== String(f.original);
  const show = (v) => f.type === "check" ? (v ? "체크함" : "빈칸") : (String(v).trim() ? v : "(빈칸)");
  let h = "";
  if (changed) h += `<p class="ins-note was">원래 값: <s>${esc(show(f.original))}</s> <button type="button" class="btn small ghost" data-revert="${esc(key)}">${icon("i-undo")}되돌리기</button></p>`;
  if (badShown(key, f)) h += `<p class="ins-note bad">${icon("i-alert")}${esc(badMsg(f))}</p>`;
  else if (RULE_OF.get(f) && String(f.value).trim() && valid(f, f.value)) h += `<p class="ins-note fmt-ok">${icon("i-check")}형식 확인 <span>(번호 형식만 맞음 · 원본·실제 번호 대조는 아님)</span></p>`;
  const fmtMsgs = new Set(st.findings.filter((x) => x.kind === "format" && x.keys.includes(key)).map((x) => x.msg));
  for (const m of fl || []) if (!fmtMsgs.has(m)) h += `<p class="ins-note warn">${icon("i-alert")}${esc(m)}</p>`;
  if (asked) h += `<p class="ins-note ask">${icon("i-message")}오른쪽 질문이 이 칸에 대한 것입니다.</p>`;
  const rf = reflectMap()[key];
  if (rf) h += `<p class="ins-note ans">${icon("i-message")}반영본 ${rf.mark} (${MODE_KO[rf.mode]}): <b>${esc(rf.text)}</b> — ${esc(rf.src.join(", "))}. 업로드한 원본 파일은 그대로입니다.`
    + ` <button type="button" class="linkbtn x-why" data-xwhy="${esc(JSON.stringify({ kind: "change", key }))}" aria-expanded="false">왜?</button></p>`;
  box.innerHTML = h;
}
function refreshNotes(key, f) {
  const fl = st.di === 0 ? flagMap()[key] : null, asked = st.di === 0 && st.asked && (st.asked.keys || []).includes(key);
  pickState(key, f, fl, reflectMap()[key]);
  document.querySelectorAll(`.fl-row[data-key="${CSS.escape(key)}"] .fl-notes, #inspector .fl-notes`).forEach((b) => {
    if (b.closest("#inspector") && st.sel !== key) return;
    paintNotes(b, key, f, fl, asked);
  });
}
function focusField(key) {
  errUi.shown.add(key);
  if (st.di === 0 && chatEdit()) { requestAnimationFrame(() => selectField(key, "next")); return; }
  phonePane("doc");
  if (sheet.querySelector(".fl-split")) listSelect(key, false);
  requestAnimationFrame(() => requestAnimationFrame(() => { const n = document.getElementById("fl-" + key.replace(/[^\w-]/g, "_")); if (n) { n.scrollIntoView({ block: "center" }); n.focus({ preventScroll: true }); refreshNotes(key, D().fields[key]); n.setAttribute("aria-invalid", "true"); } }));
}
function revertField(key) {
  const f = D().fields[key];
  f.value = f.original;
  syncNode(key, f);
  edited(key, f); f.editedBy = "";
  if (st.view === "list") render(); else if (st.sel === key) fillInspector(key);
  if (st.fedit === key) { delete st.fdrafts[key]; input.value = String(f.value ?? ""); paintFedit(); }
  toast(`「${f.name}」${pp(f.name, "을", "를")} 원래 값으로 되돌렸습니다.`);
}
document.addEventListener("click", (e) => { const b = e.target.closest("[data-revert]"); if (b) revertField(b.dataset.revert); });

// size of the page and every input at the current zoom (1 pt = u px)
function applyScale() {
  if (!D() || htmlView() || !curPage()) return;
  const p = curPage(), u = BASE * st.zoom;
  sheet.style.width = p.width * u + "px";
  sheet.style.height = p.height * u + "px";
  sheet.querySelectorAll("[data-key]").forEach((n) => scaleNode(n, D().fields[n.dataset.key], u));
  $("#zval").textContent = Math.round(st.zoom * 100) + "%";
}
function scaleNode(n, f, u) {
  const L = f.layout, s = n.style;
  place(n, L.box, u);
  s.fontSize = L.size * u + "px";
  if (f.type === "check") { s.lineHeight = (L.box[3] - L.box[1]) * u + "px"; return; }
  s.paddingLeft = s.paddingRight = (L.pad || 1) * u + "px";
  if (L.multi) {
    s.lineHeight = (L.lh || L.size * 1.3) * u + "px";
    s.paddingTop = (L.top || 0) * u + "px";
    if (L.indent) s.textIndent = L.indent * u + "px";
  } else {
    s.lineHeight = (L.box[3] - L.box[1]) * u + "px";
  }
}
function place(d, b, u) {
  d.style.left = b[0] * u + "px"; d.style.top = b[1] * u + "px";
  d.style.width = (b[2] - b[0]) * u + "px"; d.style.height = (b[3] - b[1]) * u + "px";
}
function flagMap() {
  const m = {};
  for (const f of st.findings) for (const k of f.keys) (m[k] = m[k] || []).push(f.msg);
  return m;
}

// typed input: the browser never gets a value that does not fit the field type
const CLEAN = {
  code: (v) => v.toUpperCase(),
  phone: (v) => v.toUpperCase().replace(/[^\dX-]/g, ""),
  count: (v) => v.replace(/[^\d.-]/g, ""),
  number: (v) => v.replace(/[^\d.-]/g, "").replace(/(?!^)-/g, "").replace(/(\..*)\./g, "$1"),
  yn: (v) => v.toUpperCase().replace(/[^YN]/g, "").slice(0, 1),
  date: (v) => {
    const d = v.replace(/\D/g, "").slice(0, 8);
    return d.length > 6 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}` : d.length > 4 ? `${d.slice(0, 4)}-${d.slice(4)}` : d;
  },
  time: (v) => {
    const d = v.replace(/\D/g, "").slice(0, 4);
    return d.length > 2 ? `${d.slice(0, 2)}:${d.slice(2)}` : d;
  },
};
// 34·35. an example of the right format per field, always shown under the box in 칸 목록 and the field panel
const FMT_TYPE = { phone: "010-1234-5678", date: "2026-10-29", time: "08:00", count: "4", number: "4.5", yn: "Y 또는 N" };
const fmtLine = (key, f) => {
  const r = RULE_OF.get(f), ex = (r && r.ex) || FMT_TYPE[f.type];
  if (!ex) return null;
  const box = el("div", "fl-fmt"), line = el("p", "", "");
  line.append(el("span", "", "예:"), el("span", "fl-fmt-ex", ex));
  if (r) {
    const more = el("p", "fl-fmt-more", r.help); more.hidden = true; more.id = `fmt-more-${key.replace(/[^\w-]/g, "_")}-${Math.random().toString(36).slice(2, 7)}`;
    const b = el("button", "linkbtn", "형식 보기"); b.type = "button"; b.setAttribute("aria-expanded", "false"); b.setAttribute("aria-controls", more.id);
    b.onclick = () => { more.hidden = !more.hidden; b.setAttribute("aria-expanded", String(!more.hidden)); b.textContent = more.hidden ? "형식 보기" : "형식 닫기"; };
    line.append(b); box.append(line, more);
  } else box.append(line);
  if (f.layout && f.page) {
    const o = el("button", "linkbtn", "원본에서 보기"); o.type = "button"; o.onclick = () => showInOriginal(key, f); line.append(o);
  }
  return box;
};
const fmtTie = (fx, inp) => { if (fx && inp.setAttribute) { fx.id = `${inp.id}-fmt`; inp.setAttribute("aria-describedby", fx.id); } };
// 「원본에서 보기」: the same document and page in the 원본 view, the field's place marked; what was typed stays (it is in the field)
function showInOriginal(key, f) {
  st.origMark = key;
  if (f.page !== st.page) { st.page = f.page; renderTabs(); }
  setView("orig"); phonePane("doc");
  requestAnimationFrame(() => requestAnimationFrame(() => sheet.querySelector(".orig-mark")?.scrollIntoView({ block: "center", inline: "center" })));
}
// the box's own hint: a code field shows its own pattern (호선 is not an 승인번호)
const hintFor = (key, f) => f.type === "code" ? "" : HINT[f.type];     // QA #35: nothing needed only in a placeholder
const HINT = { code: "AC00-IH-…", phone: "010-0000-0000", count: "0", number: "0", yn: "Y/N", date: "YYYY-MM-DD", time: "HH:MM" };

// a value changed on the form: the same value printed on other pages follows; the review or the plan save runs
function edited(key, f) {
  f.editedBy = "직접 수정";
  for (const k of f.same || []) Object.assign(D().fields[k], { value: f.value, editedBy: f.editedBy });   // 작업명 on both pages
  if (st.di === 0 && baseKey(key) === "permit_no") relinkPermit(key, f);
  updateChanges();
  if (st.di === 0) { bump(); if (st.reviewed) { st.reviewPending = true; paintStepper(); } scheduleReview(); scheduleDelta(); }
  else {
    const was = st.checked.delete(st.di - 1); bump();              // the 확인 goes first, then the 임시저장 is written
    if (was) toast("고친 계획서는 다시 확인이 필요합니다. 다 보면 「확인」을 눌러 주세요.");
    syncPlan(shownPlan()); scheduleSave();
  }
  if (st.sel === key && !ins.contains(document.activeElement)) fillInspector(key);
}
function fieldInput(key, f) {
  const L = f.layout;
  const inp = el(L.multi ? "textarea" : "input", "fi");
  if (!L.multi) inp.type = "text";
  inp.value = f.value;
  inp.dataset.key = key;
  inp.spellcheck = false;
  inp.setAttribute("aria-label", f.name);
  if (["count", "date", "time"].includes(f.type)) inp.inputMode = "numeric";
  if (f.type === "number") inp.inputMode = "decimal";
  if (f.type === "phone") inp.inputMode = "tel";
  if (hintFor(key, f)) inp.placeholder = hintFor(key, f);
  if (f.type === "date") inp.maxLength = 10;
  if (f.type === "time") inp.maxLength = 5;
  const s = inp.style;
  s.fontFamily = pdfFont(L.font); s.fontWeight = L.bold ? "700" : "400"; s.textAlign = L.align;
  inp.addEventListener("input", () => {
    if (CLEAN[f.type]) {
      const c = CLEAN[f.type](inp.value);
      if (c !== inp.value) { const at = inp.selectionStart + (c.length - inp.value.length); inp.value = c; inp.setSelectionRange(at, at); }
    }
    f.value = inp.value;
    decorate(inp, f, st.di ? [] : null);
    edited(key, f);
  });
  // QA #41: on the permit (desktop) the form is not typed in; picking a field puts it in the chat's box
  if (chatEdit()) {
    inp.readOnly = true; inp.classList.add("pickable");
    inp.addEventListener("click", () => selectField(key, "click"));
    inp.addEventListener("focus", () => { if (st.fedit !== key) selectField(key, "focus"); });
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); selectField(key, "click"); } });
  } else inp.addEventListener("focus", () => openInspector(key));
  watchErr(inp, key, f, () => decorate(inp, f, st.di ? [] : null));
  return inp;
}
function checkInput(key, f) {
  const L = f.layout;
  const b = el("span", "fc");
  b.dataset.key = key;
  b.setAttribute("role", "checkbox"); b.tabIndex = 0;
  b.setAttribute("aria-label", f.name);
  b.style.fontFamily = pdfFont(L.font);
  const paint = () => setCheck(b, f);
  const toggle = () => { f.value = !f.value; paint(); decorate(b, f, null); edited(key, f); };
  b.addEventListener("click", toggle);
  b.addEventListener("keydown", (e) => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); toggle(); } });
  b.addEventListener("focus", () => { if (!chatEdit()) openInspector(key); });
  paint();
  return b;
}
function setCheck(b, f) { b.textContent = f.value ? "■" : "☐"; b.setAttribute("aria-checked", f.value ? "true" : "false"); }
// the answers to questions about a blank field of the permit: key -> ["없음", …] (shown over the blank, never written in)
// the 반영본 pages, drawn by the server from the same plan as the PDF (one request per change; the newest wins)
let pvSeq = 0, pvKey = "", pvPages = null;
async function reflectPreview() {
  const box = document.querySelector("#reflect-pv .reflect-pages");
  if (!box || !st.src) return;
  const key = `${st.rev}|${st.answers.length}|${st.src.hash}`;
  const paint = (pages) => { box.innerHTML = ""; pages.forEach((u, i) => { const im = new Image(); im.src = u; im.alt = `반영본 ${i + 1}쪽`; im.className = "reflect-page"; box.appendChild(im); }); };
  if (key === pvKey && pvPages) { paint(pvPages); return; }
  const seq = ++pvSeq;
  try {
    const r = await sessionRead(() => ["/api/reflect/preview", { method: "POST", body: sessionForm() }]);
    if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
    const j = await r.json();
    if (seq !== pvSeq) return;
    pvKey = key; pvPages = j.pages;
    if (document.getElementById("reflect-pv")) paint(j.pages);
  } catch (e) { if (seq === pvSeq) box.innerHTML = `<p class="hint">반영본을 그리지 못했습니다: ${esc(e.message)} (제출 PDF에는 그대로 들어갑니다)</p>`; }
}
// a new plan: the marks on the form, the short list and the notes of the picked field follow it
function repaintReflect() {
  sheet.querySelectorAll(".fi").forEach((n) => { const f = st.doc.fields[n.dataset.key]; if (f) decorate(n, f, null); });
  const fl = flagMap(), rm = reflectMap();
  const was = st.rmSeen; st.rmSeen = Object.fromEntries(Object.entries(rm).map(([k, x]) => [k, x.text]));
  if (was) for (const k of Object.keys(st.rmSeen)) if (was[k] !== st.rmSeen[k]) flash(k);
  if (st.fedit) paintFedit();
  sheet.querySelectorAll(".fl-pick").forEach((b) => { const f = st.doc.fields[b.dataset.key]; if (f) pickState(b.dataset.key, f, fl[b.dataset.key], rm[b.dataset.key]); });
  for (const k of new Set([st.sel, ...[...document.querySelectorAll(".fl-row")].map((r) => r.dataset.key)])) if (k && st.doc.fields[k]) refreshNotes(k, st.doc.fields[k]);
}
// QA #37: what the 사전검토 반영본 writes in each field (page key -> the planned fill), from the server's plan
function reflectMap() {
  const m = {};
  if (st.di !== 0 || !st.aug || !st.aug.reflect) return m;
  for (const R of Object.values(st.aug.reflect)) for (const x of R.fills || []) for (const k of x.keys) m[k] = x;
  return m;
}
const MODE_KO = { fill: "빈칸에 기입", append: "덧붙임", replace: "바꿈" };
function decorate(node, f, flags) {
  const changed = String(f.value) !== String(f.original);
  node.classList.toggle("changed", changed);
  node.classList.toggle("bad", badShown(node.dataset.key, f));
  node.setAttribute("aria-invalid", badShown(node.dataset.key, f));
  const fl = flags !== null ? flags : st.di ? null : flagMap()[node.dataset.key];
  node.classList.toggle("flag", !changed && !!(fl && fl.length));
  if (node.classList.contains("fi")) {
    const rf = reflectMap()[node.dataset.key], fill = rf && rf.mode === "fill" && !String(f.value).trim() ? rf : null;
    node.classList.toggle("answered", !!rf);
    node.title = rf ? `반영본 ${rf.mark} ${MODE_KO[rf.mode]}: ${rf.text} (${rf.src.join(", ")})` : "";
    if (fill) node.placeholder = `${rf.mark} ${rf.text}`;
    else if (/^[①-⑳(]/.test(node.placeholder)) node.placeholder = hintFor(node.dataset.key || "", f) || "";
  }
}

// ---------------------------------------------------------------- the picked field: one fixed card, not a hover tooltip
const ins = $("#inspector");
function openInspector(key) {
  if (st.sel) sheet.querySelector(`[data-key="${st.sel}"]`)?.classList.remove("sel");
  st.sel = key;
  sheet.querySelector(`[data-key="${key}"]`)?.classList.add("sel");
  fillInspector(key);
}
function closeInspector() {
  if (st.sel) sheet.querySelector(`[data-key="${st.sel}"]`)?.classList.remove("sel");
  st.sel = null; ins.hidden = true;
}
function fillInspector(key) {
  const f = D().fields[key];
  if (!f) return closeInspector();
  if (chatEdit()) { ins.hidden = true; return; }             // QA #41: the chat's box is the editor
  ins.innerHTML = `<div class="ins-head"><label for="ins-input"><b>${esc(f.name)}</b></label><span class="chip">${esc(TYPE_KO[f.type] || f.type)}</span>`
    + `<button class="btn icon small" data-ins="close" aria-label="선택한 칸 닫기">${icon("i-x")}</button></div>`;
  const fx = fmtLine(key, f), bc = bigControl(key, f, "ins-input"); fmtTie(fx, bc);
  ins.appendChild(bc);
  if (fx) ins.appendChild(fx);
  const notes = el("div", "fl-notes"); ins.appendChild(notes);
  paintNotes(notes, key, f, st.di ? null : flagMap()[key], st.di === 0 && st.asked && (st.asked.keys || []).includes(key));
  ins.hidden = false;
  // the picked field stays in view above the card
  const n = sheet.querySelector(`[data-key="${CSS.escape(key)}"]`);
  if (n) requestAnimationFrame(() => n.scrollIntoView({ block: "nearest", inline: "nearest" }));
}
ins.addEventListener("click", (e) => { if (e.target.closest("[data-ins='close']")) closeInspector(); });

// changed values; a value printed on several pages (작업명, header) counts once
function editCount(doc) {
  const seen = new Set();
  let n = 0;
  for (const [k, f] of Object.entries(doc.fields)) {
    if (seen.has(k) || String(f.value) === String(f.original)) continue;
    n++; seen.add(k); for (const o of f.same || []) seen.add(o);
  }
  return n;
}
function updateChanges() {
  const n = D() ? editCount(D()) : 0;
  const c = $("#changes"); c.textContent = `${st.di ? "이 계획서 " : ""}고친 칸 ${n}개`; c.classList.toggle("has", n > 0);
}
let reviewTimer = null;
// 변경 구역 재분석 (design §1.4 DISCOVER_DELTA): only the fields whose words changed, behind; what it finds comes in as
// questions on the next step (never over the one on screen), within the same limits
let deltaTimer = null;
function scheduleDelta() {
  clearTimeout(deltaTimer);
  if (!st.sid || st.closing || st.reviewed) return;
  const sid = st.sid, gen = st.gen;
  deltaTimer = setTimeout(async () => {
    if (sid !== st.sid || gen !== st.gen) return;
    try {
      const r = await fetch("/api/analyze/delta", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fields: st.doc.fields, session_id: sid, plans: st.wp && st.wp.token ? { token: st.wp.token, idx: [...st.checked] } : {} }) });
      const j = r.ok ? await r.json() : {};
      if (sid !== st.sid || gen !== st.gen || !j.found) return;
      bubble("assistant", `고친 칸을 AI가 다시 읽어 확인할 것 ${j.found}건을 질문에 더했습니다.`).classList.add("note", "ai-status");
      if (!st.closing && !st.reviewed && !st.busy) await refreshAug();
    } catch (e) { /* not read again: the questions stay as they are */ }
  }, 4000);
}
function scheduleReview() {
  clearTimeout(reviewTimer);
  reviewTimer = setTimeout(async () => {
    try {
      const r = await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fields: st.doc.fields }) });
      if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
      st.findings = await r.json();
      if (st.di === 0) {
        document.querySelectorAll("#sheet [data-key]").forEach((n) => n.classList.contains("fl-row") || decorate(n, st.doc.fields[n.dataset.key], null));
        // what the 선택한 칸 card and the 칸 목록 say follows the new check
        for (const k of new Set([st.sel, ...[...document.querySelectorAll(".fl-row")].map((r) => r.dataset.key)])) if (k && st.doc.fields[k]) refreshNotes(k, st.doc.fields[k]);
      }
      await refreshAug();                    // on-screen edits also go to page 2
      if (!st.reviewed && st.asked && !st.busy && !st.aug.questions.some((q) => q.qid === st.asked.qid)
          && !st.answers.some((a) => a.qid === st.asked.qid)) moveOn();
      // a value changed after the review was finished can raise a new question: the chat opens again for it
      if (st.reviewed && st.aug.questions.length && !st.busy) reopenReview("허가서에서 고친 값 때문에 확인할 것이 새로 생겼습니다.");
      st.reviewPending = false; paintStepper();
      if (!$("#presub").hidden) openPreSubmit(true);   // the window shows the values as they now are
    } catch (e) {
      toast("고친 값을 서버에 반영하지 못했습니다. 연결을 확인해 주세요. 다음에 고치거나 답할 때 다시 반영합니다.");
    }
  }, 400);
}

// ---------------------------------------------------------------- 2. 확인 질문 (follow-up questions → 추가검토서 page 2)
// The rules ask only what is needed and missing, unclear or contradictory (server/augment.py, 작업반장 view).
// Each answer goes to the 추가검토서; the permit itself is never changed. When no question is left the chat always
// ends with 「추가로 말씀하실 것이 있나요? 없으면 「없음 · 검토 마치기」를 눌러 주세요.」: a typed answer is read for values (FREE:n) and may open
// new questions; 「없음」 ends the permit review and leads to the 작업계획서 step. An item is asked once; 「모름」 closes it.
const msgs = $("#msgs"), input = $("#input"), send = $("#send");
st.answers = []; st.aug = null; st.cur = null; st.asked = null; st.closing = false; st.fails = {};
// 「없어요」「아니요, 없습니다」「제출」「이상 없음 제출할게요」「끝」: nothing more (spaces and punctuation ignored).
// A sentence that says something ('다른 작업 없음') is not this: it is kept and read.
const NO_MORE = /^(아니(요|오|에요)?)?(더|추가로?|이상|특별히|따로)?(없(음|어요?|습니다|다|네요)|괜찮(아요|습니다)|됐(어요|습니다))?(그냥)?(제출(할게요|해주세요|합니다|요|해)?)?(끝)?$/i;
const DONT_KNOW = /^(모름|몰라(요)?|모르(겠(어요|습니다|음)?|ㅁ)|잘몰라요?|모릅니다)$/;
const NO_ONLY = /^(없(음|어요?|습니다|다)|아니(요|오|에요)?|안(해요|함|씀|써요)|해당없(음|어요|습니다))$/;
const YES_ONLY = /^(네|예|응|ㅇㅇ|맞(아요|습니다|음)|그래요|있(음|어요|습니다))$/;
const noMore = (t) => { const x = t.replace(/[\s.,!~·?]+/g, ""); return x.length > 0 && (NO_MORE.test(x) || /^no$/i.test(x)); };
function composerOn(on) {
  const lock = st.fedit && D() && D().fields[st.fedit] && isProtected(st.fedit, D().fields[st.fedit]);
  input.disabled = !on || !!lock; send.disabled = !on || !!lock;
}
// what to type for the picked answer stays above the box while typing (a placeholder goes away at the first letter: QA #3·#12)
function setAsk(ask) {
  const h = $("#input-hint");
  h.hidden = !ask; h.textContent = ask ? `적을 내용 · ${ask}` : "";
  input.placeholder = ask ? "여기에 적어 주세요" : "버튼 또는 직접 입력";
  toBottom();
}
// the newest message stays in view (after layout: buttons and the next-step bar change the height)
function toBottom() { requestAnimationFrame(() => { msgs.scrollTop = msgs.scrollHeight; }); }
function bubble(role, text, sig) {
  const ai = role === "assistant";
  const row = el("div", "msgrow " + (ai ? "ai" : "user"));
  const b = el("div", "msg " + (ai ? "ai" : "user"), text);
  if (sig) b.appendChild(el("span", "sig", sig));
  row.appendChild(b); msgs.appendChild(row); toBottom();
  return b;
}
function qProgress() {
  const left = st.aug ? st.aug.questions.length : 0, done = st.answers.filter((a) => !a.qid.startsWith("FREE:")).length;
  const total = left + done;
  $("#qprogress b").style.width = (total ? (done / total) * 100 : 100) + "%";
  const b = st.aug && st.aug.budget;
  $("#qcount").textContent = (st.reviewed ? "검토 마침" : left ? `남은 확인 ${left}개` : "질문 없음") + (b ? ` · 질문 ${b.used}/${b.max}` : "");
  paintStepper(); paintFillbar();
}
// the review session (design §2): the server keeps the foreman's answers and what was read from them; only what he
// confirmed comes back as answers (adopted). The client sends its own typed answers; a derived one is never sent.
const typedAnswers = () => st.answers.filter((a) => !a.by && !a.ai);
async function ensureSession() {
  if (st.sid) return st.sid;
  const r = await fetch("/api/dialogues", { method: "POST" });
  if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
  st.sid = (await r.json()).session_id; st.srev = 0; st.sent = {}; saveDraft();
  return st.sid;
}
// the revision last seen: taken only from a reply to this session, and never back to an older one
const seeRev = (sid, rev) => { if (sid === st.sid && rev != null) st.srev = Math.max(st.srev ?? 0, rev); };
// the server's answers for this review (another tab or a late request changed them): they replace ours, with the
// readings waiting for a confirmation
async function serverState() {
  const sid = st.sid, gen = st.gen;
  const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/state`, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields: st.doc.fields }) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error((j.detail && j.detail.message) || `서버 오류 ${r.status}`); e.code = j.detail && j.detail.code; throw e; }
  if (sid !== st.sid || gen !== st.gen) return j;             // another review meanwhile
  // A1: what was done here and not yet sent (an answer typed or taken back) is put on the server's answers again
  const m = mergeState(j.typed, j.adopted, typedAnswers(), st.sent), was = ansSig(st.answers);
  st.srev = j.revision; st.sent = sentOf(j.typed);
  st.answers = m.answers; st.props = j.proposals || [];
  markDropped(j.dropped);
  if (ansSig(st.answers) !== was) bump(); else saveDraft();   // A11: nothing changed, nothing to submit again
  pruneReadings();
  if (m.clash.length) clashNote(m.clash);
  return j;
}
// what was said for a question (its choice and value), and what the server last had of each typed answer (st.sent:
// qid -> said; null when not known, as in an older 임시저장: then the server's answers are taken as they are)
const saidKey = (a) => `${a.choice ?? ""}\u001f${String(a.value ?? "").trim()}`;
const sentOf = (list) => Object.fromEntries(list.map((a) => [a.qid, saidKey(a)]));
const ansSig = (list) => list.map((a) => `${a.qid}|${a.pid || ""}|${saidKey(a)}`).join("\u001e");
// the server's answers (another screen or a card confirmed meanwhile) with the changes made here it has not had: an
// answer typed or changed here goes on them, one taken back here goes from them. An answer the server has otherwise
// for the same question (changed elsewhere, or a confirmed reading) is not sent over it: it comes back in clash.
function mergeState(typed, adopted, local, sent) {
  const out = typed.slice(), clash = [];
  if (sent) {
    const at = (qid) => out.findIndex((a) => a.qid === qid), mine = new Set(local.map((a) => a.qid));
    for (const [qid, k] of Object.entries(sent)) {          // taken back here, and not changed there since
      const i = at(qid);
      if (!mine.has(qid) && i >= 0 && saidKey(out[i]) === k) out.splice(i, 1);
    }
    for (const a of local) {
      if (sent[a.qid] === saidKey(a)) continue;             // the server had it as it is here
      const i = at(a.qid), there = i >= 0 ? out[i] : adopted.find((x) => x.qid === a.qid);
      if (!there) out.push(a);
      else if (saidKey(there) === saidKey(a)) continue;
      else if (i >= 0 && saidKey(there) === sent[a.qid]) out[i] = a;     // changed here only
      else clash.push(a);
    }
  }
  const have = new Set(out.map((a) => a.qid));
  return { answers: out.concat(adopted.filter((a) => !have.has(a.qid))), clash };
}
// A1: an answer typed here that the server already has another answer for: not sent; his words go back into the box
// (when it is empty) for him to see, and the box remembers which question they were written for
function clashNote(list) {
  for (const a of list) document.querySelectorAll(`#msgs .msg.user[data-qid="${CSS.escape(a.qid)}"]`).forEach((u) => {
    if (!u.parentNode.classList.contains("undone")) { u.parentNode.classList.add("undone"); u.parentNode.querySelector(".fix")?.remove(); }
  });
  const back = list.find((a) => String(a.value || "").trim()), put = !!back && !st.fedit && !input.value.trim();
  if (put) { input.value = back.value; st.draftQ = back.qid; }
  bubble("assistant", `「${list.map((a) => slotOf(a.qid)).join("」 「")}」 질문은 다른 확인으로 이미 답이 있어 보낸 답을 넣지 않았습니다.`
    + (put ? " 적던 내용은 입력칸에 그대로 있습니다." : back ? " 적으신 내용은 위 대화에 그대로 있습니다." : "")).classList.add("note");
}
// checking answers whose base changed (the server no longer counts them): they go, and are asked again
function markDropped(ids) {
  const drop = new Set(ids || []);
  if (!drop.size) return;
  st.answers = st.answers.filter((a) => !drop.has(a.qid)); pruneReadings();
  document.querySelectorAll("#msgs .msg.user[data-qid]").forEach((u) => {
    if (drop.has(u.dataset.qid) && !u.parentNode.classList.contains("undone")) { u.parentNode.classList.add("undone"); u.parentNode.querySelector(".fix")?.remove(); }
  });
}
// the checklist, the preview and the submission read the session as of the revision last seen; when it moved on
// elsewhere (409) the server's answers are taken and the request made again once. make() gives [url, init].
async function sessionRead(make) {
  let r = await fetch(...make());
  if ((r.status === 409 || r.status === 428) && st.sid) {
    const j = await r.clone().json().catch(() => ({}));
    if (j.detail && ["stale_revision", "revision_required"].includes(j.detail.code)) { await serverState(); r = await fetch(...make()); }
  }
  return r;
}
// a POST with the session and the revision last seen; a session the server no longer has is made again once (what
// was confirmed in it is gone); answers changed elsewhere (409) are taken from the server and the request sent again
async function sessionPost(url, body, opts = {}) {
  for (let i = 0; i < 3; i++) {
    const sid = await ensureSession();
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, ...opts,
      body: JSON.stringify({ ...body, session_id: sid, expected_revision: st.srev ?? null }) });
    r.sid = sid;
    if ((r.status === 404 || r.status === 409) && i < 2) {
      const j = await r.clone().json().catch(() => ({})), code = j.detail && j.detail.code;
      if (code === "session_missing") { st.sid = null; st.srev = null; st.sent = {}; st.answers = typedAnswers(); continue; }
      if (code === "stale_revision") {
        await serverState(); toast("다른 화면에서 바뀐 내용으로 맞췄습니다");
        if (body.answers) body = { ...body, answers: typedAnswers() };
        continue;
      }
    }
    if (r.ok && body.answers && sid === st.sid) st.sent = sentOf(body.answers);   // the server has these now
    return r;
  }
}
// the answers as the server keeps them: ours as typed, and the confirmed readings with their ids
function takeAdopted(adopted) {
  const typed = typedAnswers(), have = new Set(typed.map((a) => a.qid));
  const next = typed.concat((adopted || []).filter((a) => !have.has(a.qid)));
  const sig = (l) => l.map((a) => `${a.qid}|${a.pid || ""}`).join(",");
  if (sig(next) !== sig(st.answers)) { st.answers = next; bump(); }
}
// requests can overlap (an on-screen edit while answering): a reply older than the one shown is dropped
let augSent = 0, augShown = 0;
async function refreshAug() {
  const seq = ++augSent, gen = st.gen, spilled = st.answers.filter((a) => a.spill).map((a) => a.qid);
  const r = await sessionPost("/api/augment", { fields: st.doc.fields, answers: typedAnswers() });
  if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
  const s = await r.json();
  if (gen !== st.gen) return st.aug;                      // the review was started again meanwhile
  seeRev(r.sid, s.revision);
  if (seq > augShown) {
    augShown = seq; st.aug = s;
    takeDerived(s, spilled);
    if (st.view === "sheet" && st.di === 0) render();
    else if (st.di === 0) repaintReflect();
    qProgress();
  }
  return st.aug;
}
// QA #39: what a long answer also said (derived: answers to other open questions, with the clause each came from; read:
// the answer's own part). The answer is read once: after this it is sent as it is, with the derived answers beside it.
function takeDerived(s, sent) {
  const rd = s.read || {};
  for (const a of st.answers) if (a.spill && sent.includes(a.qid)) { a.spill = false; if (rd[a.qid]) a.read = rd[a.qid]; }
  markDropped(s.dropped);
  if (s.expired) expiryNote(s.expired);
  takeAdopted(s.adopted);
  st.props = (s.proposals || []).filter((p) => p.pid);           // waiting for the foreman's confirmation, by answer
}
const SLOT_KO = { L1: "작업장소", L7: "실제 작업 위치", T0: "작업일시", T1: "실제 작업시간", "B1.workers": "작업인원", "B2.workers": "작업인원", W1: "감시·입회 인원 (별지)" };
const slotOf = (qid) => { const it = qid.split(":")[0]; return SLOT_KO[it] || SLOT_KO[it.split(".")[0]] || it; };
// the chat's own refresh: while it runs the composer is locked (no second answer to the same question); when the
// network or the server fails nothing is lost: the answers stay, and 「다시 시도」 runs the same step again
async function chatRefresh(again) {
  st.busy = true; composerOn(false);
  try {
    return await refreshAug();
  } catch (e) {
    bubble("assistant", `서버와 연결이 잠시 끊겼습니다 (${e.message || "네트워크"}). 적으신 답은 그대로 있습니다. 「다시 시도」를 눌러 주세요.`).classList.add("note");
    const box = el("div", "choices"), b = el("button", "", "다시 시도"); b.type = "button";
    b.onclick = () => {
      if (box.getAttribute("aria-disabled") === "true") return;
      box.setAttribute("aria-disabled", "true"); b.classList.add("picked"); again();
    };
    box.appendChild(b); msgs.appendChild(box); toBottom(); b.focus();
    return null;
  } finally {
    st.busy = false;
  }
}
// bring a field of the permit into view: its page, the form view, the document pane, centred and picked
function showField(page, keys) {
  if (st.di !== 0) showDoc(0);
  if (st.view === "list" && chatEdit() && sheet.querySelector(".fl-split")) {      // QA #40: the list keeps its place
    const k = keys.find((x) => D().fields[x]);
    if (k) { listMark(k); listOrig(k); markRel(k); }
    return;
  }
  if (st.view !== "form") setView("form");
  if (page && page !== st.page) { st.page = page; renderTabs(); render(); }
  phonePane("doc");
  markAsk(keys);
  requestAnimationFrame(() => requestAnimationFrame(() => {
    const n = keys.map((k) => sheet.querySelector(`[data-key="${k}"]`)).find(Boolean);
    if (!n) { toast("이 칸은 문서 위에 그려지지 않았습니다. 「칸 목록」에서 찾아 주세요."); return; }
    n.scrollIntoView({ block: "center", inline: "center" });
    if (chatEdit()) { sheet.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel")); n.classList.add("sel"); markRel(n.dataset.key); return; }
    n.focus({ preventScroll: true }); openInspector(n.dataset.key);
  }));
}
function markAsk(keys) {
  document.querySelectorAll("#sheet .ask").forEach((n) => n.classList.remove("ask"));
  if (st.di) return;                                          // a 작업계획서 is on screen: the question is about the permit
  for (const k of keys || []) document.querySelector(`#sheet [data-key="${k}"]`)?.classList.add("ask");
}
const leftLine = () => {
  const n = new Set(((st.aug && st.aug.unresolved) || []).map((x) => x.key)).size;
  return n ? `대화 완료 · 담당 확인 ${n}건` : "대화 완료 · 미확인 없음";
};
async function closing() {
  const sid = st.sid, gen = st.gen;
  const r = await issueAsk("close");
  if (sid !== st.sid || gen !== st.gen || r.gone) return;    // a new review started meanwhile
  if (r.offline) { askRetry(closing); return; }
  if (!r.ok || r.again) {                                   // asked once already, or no request left: the end
    st.asked = null; st.cur = null; st.closing = true; markAsk([]); composerOn(false);
    bubble("assistant", `${leftLine()}. ${r.code === "budget" ? `질문 한도(${(st.aug.budget || {}).max || 12}회)를 다 써서 남은 것은 추가검토서의 「안전팀 확인 필요」에 넣었습니다.` : "남은 것은 추가검토서의 「안전팀 확인 필요」에 있습니다."}`).classList.add("note");
    const box = el("div", "choices"), b = el("button", "", "검토 마치기"); b.type = "button";
    b.onclick = () => { if (box.getAttribute("aria-disabled") === "true") return; box.setAttribute("aria-disabled", "true"); b.classList.add("picked"); finish(); };
    box.appendChild(b); msgs.appendChild(box); toBottom();
    return;
  }
  // nothing left to ask: always this line; type more, or 「없음」
  st.asked = null; st.cur = null; st.closing = true; markAsk([]);
  composerOn(true);
  setAsk(null); input.placeholder = "더 알려 주실 내용을 적어 주세요 · 없으면 아래 「없음」";
  bubble("assistant", st.aug.closing || "추가로 말씀하실 것이 있나요? 없으면 「없음 · 검토 마치기」를 눌러 주세요.",
    `「없음 · 검토 마치기」를 누르면 허가서 검토를 마치고 ${st.wp ? "위험 체크리스트로" : "작업계획서 올리기로"} 넘어갑니다 (제출은 5단계)`);
  const box = el("div", "choices");
  const b = el("button", "", "없음 · 검토 마치기"); b.type = "button";
  b.onclick = () => {
    if (box.getAttribute("aria-disabled") === "true") return;
    if (st.fedit) exitEdit(false);
    box.setAttribute("aria-disabled", "true"); b.classList.add("picked");
    bubble("user", "없음"); finish();
  };
  box.appendChild(b); msgs.appendChild(box); toBottom();
}
function finish() {
  st.closing = false; st.reviewed = true; composerOn(false); saveDraft();
  ckAiAhead();
  const n = st.answers.length;
  bubble("assistant", `${leftLine()}. ` + (n ? `답변 ${n}건을 정리했습니다. 양식 칸에 맞는 것은 반영본에, 나머지는 별지에 넣었습니다.` : "더 확인할 것이 없습니다.") +
    " 문서 위 「추가검토서」에서 반영본과 별지를 볼 수 있습니다. 작업 승인이 아닙니다.").classList.add("note");
  $("#to-plans").hidden = false; $("#composer").hidden = true;
  qProgress(); toBottom();
  $("#go-plans").focus();
  checkLinks();
}
$("#go-plans").onclick = () => goStep(st.wp ? 4 : 3);
// the 작업반장's answer, with a way to take it back
function answerBubble(qid, text) {
  const ub = bubble("user", text);
  ub.dataset.qid = qid;
  const free = qid.startsWith("FREE:");
  const fix = el("button", "btn small ghost fix"); fix.type = "button";
  fix.innerHTML = `${icon("i-undo")}${free ? "이 말 지우기" : "답 고치기"}`;
  fix.setAttribute("aria-label", `「${text.slice(0, 30)}」 ${free ? "지우기" : "답 고치기"}`);
  fix.onclick = () => editAnswer(ub.dataset.qid || qid, ub, fix);
  ub.parentNode.appendChild(fix);
  return ub;
}
async function freeAnswer(text) {
  // the closing answer: kept word for word (FREE:n) and read for values; new questions may follow
  document.querySelectorAll(".choices:not([aria-disabled])").forEach((b) => b.setAttribute("aria-disabled", "true"));
  input.value = ""; st.draftQ = null;
  if (noMore(text)) { bubble("user", text); finish(); return; }
  const qid = `FREE:${Math.max(0, ...st.answers.filter((a) => a.qid.startsWith("FREE:")).map((a) => +a.qid.split(":")[1])) + 1}`;
  answerBubble(qid, text);
  st.answers.push({ qid, choice: "text", value: text, at: Date.now() }); bump();
  st.closing = false;
  await afterFree(qid);
}
async function afterFree(qid) {
  if (!(await chatRefresh(() => afterFree(qid)))) return;
  const asksBack = (st.aug.questions[0] || {}).item?.startsWith("U1.");
  // design §2: the words are kept on the 추가검토서 as said; what they say for a question is shown to confirm first
  bubble("assistant", asksBack ? "추가검토서에 원문 그대로 적었습니다. 어떤 내용인지 확실히 알아듣지 못해 한 가지만 여쭙겠습니다."
    : "추가검토서에 원문 그대로 적었습니다.").classList.add("note");
  st.before = null;
  const r = await readCard({ qid });
  if (r === "stale") return;
  if (r) { await again(); return; }
  askNext();
}
let whySeq = 0;
// shown to the foreman now: the server counts it (once; a reload or the same question again is not counted again)
// -> {ok, again, used, max, code}. A network failure does not stop the review (the next step reports it).
async function issueAsk(what, q) {
  const sid = st.sid;
  if (!sid) return { ok: false, offline: true };
  try {
    const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/ask`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ what, qid: q ? q.qid : "", q: q || {}, fields: st.doc.fields }) });
    const j = await r.json().catch(() => ({}));
    if (sid !== st.sid) return { ok: false, gone: true };              // another review meanwhile: nothing of it here
    if (r.ok) { if (st.aug && st.aug.budget) st.aug.budget.used = j.used; qProgress(); return { ok: true, ...j }; }
    if (r.status >= 500) return { ok: false, offline: true };
    return { ok: false, code: j.detail && j.detail.code, message: j.detail && j.detail.message };
  } catch (e) { return { ok: false, offline: true }; }        // not issued: not shown, the step is tried again
}
// the server could not be reached: the step waits for 「다시 시도」 (nothing is shown before it is counted)
function askRetry(again) {
  bubble("assistant", "서버와 연결이 잠시 끊겼습니다. 적으신 답은 그대로 있습니다. 「다시 시도」를 눌러 주세요.").classList.add("note");
  const box = el("div", "choices"), b = el("button", "", "다시 시도"); b.type = "button";
  b.onclick = () => { if (box.getAttribute("aria-disabled") === "true") return; box.setAttribute("aria-disabled", "true"); b.classList.add("picked"); again(); };
  box.appendChild(b); msgs.appendChild(box); toBottom(); b.focus();
}
let askSeq = 0;
// design §10.7 (2026-10-31): the next question does not wait for the last answer to be read. While a reading runs,
// the questions its words may already answer (a choice or the slot named in them) go to the end of the queue, so the
// reading can take them before they are asked; when it is confirmed, a question it answered is taken off the screen
const READING = new Map();                                   // question -> the words being read
// A2: the readings whose answer was taken back or changed (said = its value, choice = its choice when read)
const staleReadings = (readings, answers) => [...readings].filter(([qid, x]) => !answers.some((a) => a.qid === qid && !a.pid && !a.by
  && String(a.value || "").trim() === String(x.said || "").trim() && (x.choice == null || a.choice === x.choice))).map(([qid]) => qid);
// a reading ends with its answer: taken off the waiting list, its card says it is not used
function pruneReadings() {
  for (const qid of staleReadings(READING, st.answers)) { const x = READING.get(qid); READING.delete(qid); x.tok.cancel?.(); }
}
// the end waiting for the readings goes on when the last one has ended (a refresh running now first: it may ask next)
function resumeClose() {
  if (!st.waitClose || READING.size) return;
  if (st.busy) { setTimeout(resumeClose, 300); return; }
  st.waitClose = false; again();
}
const GENERIC = new Set(["있음", "없음", "해당없음", "모름", "미정", "예", "아니오", "네", "아니요", "전체", "일부", "입력", "작업", "시간", "여부", "내용", "방법", "위치", "인원"]);
const sq = (s) => String(s || "").replace(/\s+/g, "");
function mayCover(x, said) {
  if (!said) return false;
  const words = [...x.choices.filter((c) => c.id !== "unknown").map((c) => sq(c.label)), ...String(slotOf(x.qid) || "").split(/[\s·/(),]+/).map(sq)];
  return words.some((w) => w.length >= 2 && !GENERIC.has(w) && said.includes(w));
}
// design §19.3·§19.5: the state words of an AI reading (no percentages, no 「AI가 판단」)
const AI_CHIP = { read: "AI 읽음", done: "확인함 → 반영본에 기입", prop: "AI 제안", draft: "AI 초안", taken: "문안 채택", fail: "AI 결과를 준비하지 못함" };
// design §5.1: what a reading did not say of its question (「가스절단으로 읽음 · 러그 개수 미확인」)
const AI_UNREAD = (p) => (p && (p.unread || []).length ? `<span class="ai-when ai-unread">미확인: ${esc(p.unread.join(", "))}</span>` : "");
// design §19.4: the step a reading is at, from the server (대기 중 / 답 해석 중 / 결과 검사 중)
const AI_STAGE = {};
// PHRASE (design §10.5): wordings prepared for the next questions; shown only while the question is the same
st.phrased = st.phrased || {};
const qText = (q) => { const p = st.phrased[q.qid]; return p && p.base === q.text ? p.text : q.text; };
// prepared-ahead calls hold a browser connection while the model works (a browser opens 6 per server): one of each kind,
// the one for an earlier question cut off, none while answers are being read — the next question's own requests never wait
const AHEAD = { phrase: null, warm: null };
// none: nothing to prepare this time (no next question, no typed choice, AI off): the earlier one is cut off all the same
function aheadSignal(kind, none) {
  if (AHEAD[kind]) AHEAD[kind].abort();
  AHEAD[kind] = none || READING.size >= 2 ? null : new AbortController();
  return AHEAD[kind] && AHEAD[kind].signal;
}
// Codex QA2 #5: the moment two answers are being read, both prepared-ahead calls let their connections go
function aheadCap() {
  if (READING.size < 2) return;
  for (const k of Object.keys(AHEAD)) if (AHEAD[k]) { AHEAD[k].abort(); AHEAD[k] = null; }
}
function phraseAhead(q) {
  const on = !!st.sid && Date.now() >= AI.offUntil;
  const next = on ? st.aug.questions.filter((x) => x.qid !== q.qid && x.qid !== q.with && !st.answers.some((a) => a.qid === x.qid)).slice(0, 2).map((x) => x.qid) : [];
  const sid = st.sid, signal = aheadSignal("phrase", !next.length);
  if (!signal) return;
  fetch("/api/understand/phrase", { method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ fields: st.doc.fields, session_id: sid, qids: next }) })
    .then((r) => (r.ok ? r.json() : {})).then((j) => { if (sid === st.sid) Object.assign(st.phrased, j.phrased || {}); }).catch(() => {});
}
function warmAsk(q) {                                        // the question's list read into the model's cache now
  const signal = aheadSignal("warm", !st.sid || !(q.choices || []).some((c) => c.ask) || Date.now() < AI.offUntil);
  if (!signal) return;
  fetch("/api/understand/warm", { method: "POST", headers: { "Content-Type": "application/json" }, signal,
    body: JSON.stringify({ fields: st.doc.fields, qid: q.qid, session_id: st.sid }) }).catch(() => {});
}
async function askNext() {
  const seq = ++askSeq, gen = st.gen;
  st.refused = st.refused || new Set();
  const pq = st.pairQ;
  if (pq && st.aug.questions.some((x) => x.qid === pq.q.qid) && !st.answers.some((a) => a.qid === pq.q.qid) && pq.box.getAttribute("aria-disabled") !== "true") {
    st.asked = pq.q; st.cur = null; composerOn(true); warmAsk(pq.q); return;      // its own choices are on screen already
  }
  st.pairQ = null;
  let q = null;
  const open = st.aug.questions.filter((x) => !x.unasked && !st.refused.has(x.qid));
  // deferred only while every open question still fits in the asks left: the order never pushes one past the limit
  const B = st.aug.budget || {}, roomy = B.max == null || (B.max - (B.used || 0)) >= open.length;
  const said = roomy ? sq([...READING.values()].filter((x) => x.gen === st.gen).map((x) => x.said).join(" ")) : "";
  for (const x of [...open.filter((x) => !mayCover(x, said)), ...open.filter((x) => mayCover(x, said))]) {
    const r = await issueAsk("question", x);
    if (seq !== askSeq || gen !== st.gen || r.gone) return;  // another step asked meanwhile
    if (r.offline) { askRetry(askNext); return; }
    if (r.ok) { q = x; break; }
    if (r.code === "clarify" || r.code === "reserved") { st.refused.add(x.qid); continue; }   // 다시 묻기 한도 / 규칙 질문 몫: the next question
    break;                                                    // 질문 한도: nothing more is asked
  }
  st.asked = q || null; st.cur = null;
  if (!q && READING.size) {                                   // the end waits for the answers still being read
    if (!st.waitNote) { st.waitNote = bubble("assistant", "앞 답을 읽고 있습니다. 끝나면 이어서 마무리합니다."); st.waitNote.classList.add("note"); }
    st.waitClose = true; composerOn(false); return;
  }
  st.waitNote = null; st.waitClose = false;
  if (!input.value.trim()) st.draftQ = null;                  // the box is empty: nothing in it was written for another question
  if (!q) { await closing(); return; }
  composerOn(true);
  warmAsk(q);
  if (!st.di && q.page !== st.page && st.view !== "sheet" && !st.fedit) { st.page = q.page; renderTabs(); render(); }
  if (st.view !== "sheet") markAsk(q.keys);
  phraseAhead(q);
  const qb = bubble("assistant", `${st.aug.effective.length > 1 ? `[${q.who}] ` : ""}${qText(q)}`, `관측: ${q.signal}`);
  qb.dataset.qid = q.qid;
  if (q.why) {                                  // 「왜 묻나요?」 (design §3.3·§19.2): stored, opens at once, no model call
    const w = el("button", "linkbtn why-btn", "왜 묻나요?"), id = `why-${++whySeq}`;
    w.type = "button"; w.setAttribute("aria-expanded", "false"); w.setAttribute("aria-controls", id);
    const box = el("div", "why-box"); box.hidden = true; box.id = id;
    // [등급] 짧은 출처·조 on its own line; what the article is, which croScan rule reads the answer and the text it
    // was checked against below it (design §19.2·§19.3: grade, check and rank are not one badge)
    box.innerHTML = `<p class="why-need">${esc(q.why.need)}</p>` + (q.why.basis.length ? `<ul class="why-basis">${q.why.basis.map((x) =>
      `<li><span class="why-ref"><span class="why-grade${x.grade === "예시" ? " eg" : ""}">${esc(x.grade)}</span>${esc(x.ref)}</span>`
      + `<small>${esc([x.title, x.rule && `croScan 규칙 「${x.rule}」에서 씀`, x.rev].filter(Boolean).join(" · "))}</small></li>`).join("")}</ul>` : "")
      + ((q.why.refs || []).length ? `<p class="why-refs-h">관련 자료 · 검색 후보(근거 확정 아님)</p><ul class="why-basis why-refs">${q.why.refs.map((x) =>
        `<li><span class="why-ref"><span class="why-grade">${esc(x.grade)}</span>${esc(x.ref)}${x.reviewed ? "" : " · 검수 전"}</span>`
        + `<small>${esc(x.text)}…</small></li>`).join("")}</ul>` : "");
    w.onclick = () => { box.hidden = !box.hidden; w.setAttribute("aria-expanded", String(!box.hidden)); };
    qb.append(w, box);
  }
  if ((q.keys || []).length) {                                   // show the field the question is about
    const see = el("button", "btn small ghost see");
    see.type = "button"; see.innerHTML = `${icon("i-file")}허가서에서 이 칸 보기`;
    see.onclick = () => showField(q.page, q.keys);
    qb.appendChild(see);
  }
  const box = choicesFor(q);
  st.askBox = box;
  msgs.appendChild(box); toBottom();
  // design §3.2 step 9: a related question of the same work goes in the same bubble, with its own choices (one 「예」
  // never settles both); it is an ask of its own (counted, refused like any other)
  const mate = q.with && st.aug.questions.find((x) => x.qid === q.with);
  if (mate) {
    const r = await issueAsk("question", mate);
    if (seq !== askSeq || gen !== st.gen || r.gone || !r.ok) return;
    const sub = el("p", "ask2"); sub.innerHTML = `<b>함께 여쭙니다</b> ${esc(qText(mate))}`; qb.appendChild(sub);
    const box2 = choicesFor(mate); box2.classList.add("choices2"); msgs.appendChild(box2); toBottom();
    st.pairQ = { q: mate, box: box2 };
  }
}
// one question's answer buttons (a choice with something to type opens the composer for it)
function choicesFor(q) {
  const box = el("div", "choices"); box.setAttribute("role", "group"); box.setAttribute("aria-label", `답 고르기: ${slotOf(q.qid)}`);
  box.dataset.qid = q.qid;
  for (const c of q.choices) {
    const b = el("button", c.id === "unknown" ? "soft" : "", c.label); b.type = "button";
    b.onclick = () => {
      if (box.getAttribute("aria-disabled") === "true") return;
      if (st.fedit) exitEdit(false);                 // answering the question ends the field editing
      if (box.getAttribute("aria-disabled") === "true") return;      // (the editing answered this question meanwhile)
      box.querySelectorAll("button").forEach((x) => x.classList.toggle("picked", x === b));
      st.asked = q;
      if (c.ask) { st.cur = { q, c, box }; setAsk(c.ask); composerOn(true); input.focus(); }
      else answer(q, c, "", box);
    };
    box.appendChild(b);
  }
  return box;
}
// a button answer leaves a draft written for another question where it is (A1); a typed answer came from the box
const draftStays = (draftQ, qid, value) => !value && draftQ != null && draftQ !== qid;
async function answer(q, c, value, box) {
  if (st.busy || st.answers.some((a) => a.qid === q.qid)) return;     // one answer per question
  if (box) box.setAttribute("aria-disabled", "true");
  answerBubble(q.qid, value ? `${c.label}: ${value}` : c.label);
  st.before = new Set((st.aug ? st.aug.questions : []).map((x) => x.qid));
  st.answers.push({ qid: q.qid, choice: c.id, value, q, at: Date.now(), ...(value.length >= 8 ? { spill: true } : {}) }); bump();
  if (!draftStays(st.draftQ, q.qid, value)) { input.value = ""; st.draftQ = null; }
  setAsk(null);
  await afterAnswer(q, c, value);
}
async function afterAnswer(q, c, value) {
  if (!(await chatRefresh(() => afterAnswer(q, c, value)))) return;
  if (!st.answers.some((a) => a.qid === q.qid && !a.pid && !a.by)) { askNext(); return; }   // not taken: answered otherwise meanwhile (clashNote)
  if (st.aug.errors && st.aug.errors[q.qid]) {
    st.answers = st.answers.filter((a) => a.qid !== q.qid); bump();
    st.fails[q.qid] = (st.fails[q.qid] || 0) + 1;
    saveDraft();                                              // the count survives a reload
    const retry = st.fails[q.qid] < 2 ? await issueAsk("retry", q) : { ok: false };
    if (retry.gone) return;
    if (retry.offline) { st.fails[q.qid]--; askRetry(() => afterAnswer(q, c, value)); return; }
    if (!retry.ok) {
      // asked again once already: keep what was typed and leave it to the safety team
      st.answers.push({ qid: q.qid, choice: "unknown", value, q, at: Date.now() }); bump();
      bubble("assistant", `${st.aug.errors[q.qid]}. 적으신 그대로 남기고, 안전팀 확인으로 넘기겠습니다.`).classList.add("note");
    } else {
      bubble("assistant", `${st.aug.errors[q.qid]}. 한 번만 다시 답해 주세요.`).classList.add("note");
    }
    await again();
    return;
  } else if (c.id === "unknown") {
    bubble("assistant", "미정으로 남기겠습니다. 추가검토서의 '안전팀 확인'에 넣었습니다.").classList.add("note");
  } else {
    const me = st.answers.find((a) => a.qid === q.qid && !a.pid && !a.by), gen = st.gen, tok = {};
    READING.get(q.qid)?.tok.cancel?.();                        // an earlier reading of this question no longer holds
    READING.set(q.qid, { said: (me && me.value) || "", choice: me && me.choice, tok, gen, at: Date.now() });
    aheadCap();
    setTimeout(aiTick, 300);
    readCard(q, null, tok).then(async (r) => {
      if (READING.get(q.qid)?.tok === tok) READING.delete(q.qid);
      if (gen !== st.gen) return;
      if (r === true) { await afterConfirm(); return; }       // confirmed readings answered more
      resumeClose();                                          // A2: done, stale, failed or cancelled: the end goes on
    });
  }
  askNext();
}
// a card confirmed while another question is on screen: from the new state, the question on screen goes when the
// confirmed reading answered it; the end that was waiting goes on
async function afterConfirm() {
  const cur = st.asked, box = st.askBox;
  if (!(await chatRefresh(afterConfirm))) return;
  // answered by the confirmed reading (an adopted answer, pid), not by his own typing, and no longer asked
  const answered = cur && st.answers.some((a) => a.qid === cur.qid && a.pid) && !st.answers.some((a) => a.qid === cur.qid && !a.pid)
    && !st.aug.questions.some((x) => x.qid === cur.qid);
  if (answered && st.asked === cur) {
    if (box) box.setAttribute("aria-disabled", "true");
    if (st.cur && st.cur.q === cur) { st.cur = null; setAsk(null); }
    const nm = ((st.props || []).find((p) => p.qid === cur.qid) || {}).slot || SLOT_KO[cur.item] || String(cur.text || "").slice(0, 24);
    // A1: what he was writing for it stays in the box, tied to that question (not sent to the next one unseen)
    const typing = !!input.value.trim() && st.draftQ === cur.qid;
    bubble("assistant", typing ? `앞 카드로 「${nm}」 질문이 답해졌습니다. 적던 내용은 입력칸에 그대로 있습니다.`
      : `「${nm}」 질문은 앞 답을 확인해 답이 됐습니다.`).classList.add("note");
    askNext();
  } else if (!cur || (st.waitClose && !READING.size)) { st.waitClose = false; askNext(); }
  else composerOn(true);
}
// 「이 답을 이렇게 읽었습니다」 (QA #39 → design §2·§4.2·§19.1, 2026-10-31): one card for one answer. Its own value is the
// answer. What it also says for other open questions is proposed with its words: by the rules at once, by the AI
// (the on-premise model) when it comes. Nothing of it is an answer until 「N건 확인」: the server adopts those ids.
// The questions the answer itself already covered are listed (not asked). A changed answer makes the card stale.
const AI = { offUntil: 0 };
const AI_WHEN = { plan: "예정", done: "했다고 답함", none: "시점 미확인" };
const nearBottom = () => msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 80;
// what a card showed (design §2.3 displayed_digest): FNV-1a 32 over its proposals' ids, choices and values — the same
// as store.digest (plain http has no crypto.subtle)
const fnv = (s) => { let h = 0x811c9dc5; for (const x of new TextEncoder().encode(s)) { h ^= x; h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(16).padStart(8, "0"); };
const shownDigest = (ps) => fnv([...ps].sort((a, b) => (a.pid < b.pid ? -1 : a.pid > b.pid ? 1 : 0))
  .map((p) => `${p.pid}\u001f${p.choice || ""}\u001f${p.value || ""}`).join("\u001e"));
// 「들어갈 곳(전→후)」 (design §4.3·§19.2): the form field with its value before and after, or the 별지
const destLine = (p) => !(p.dest || []).length ? "" : `<span class="ai-dest">들어갈 곳: ${p.dest.slice(0, 3).map((d) => d.kind === "field"
  ? `${esc(d.where)} ${d.before ? `「${esc(d.before)}」 → ` : ""}「${esc(d.after)}」` : `${esc(d.where)} 「${esc(d.after)}」`).join(" · ")}</span>`;
// 개정 만료 (design §19.2): one notice per change — what changed (before → after), how many results it expired, and
// [변경 내용 보기]; once per revision
const EXPIRED = new Set();
function expiryNote(x) {
  const key = `${st.sid}:${x && x.rev}`;
  if (!x || EXPIRED.has(key) || !(x.lost || []).length) return;
  EXPIRED.add(key);
  const ch = x.changes || [], nm = (q) => slotOf(q || "");
  const what = x.plan ? "작업계획서 수정" : ch.length === 1 ? `「${nm(ch[0].qid)}」 답` : ch.length > 1 ? `답 ${ch.length}개` : x.form ? "허가서 내용" : "답";
  const was = { adopted: "확인했던 읽기", proposed: "확인 전 읽기", check: "확인 질문의 답", link: "작업계획서에서 가져온 값" };
  const b = bubble("assistant", ""); b.classList.add("note", "expiry"); b.setAttribute("role", "status");
  b.innerHTML = `<p><b>${esc(what)} 때문에 다시 확인이 필요합니다</b></p>`
    + (ch.length === 1 ? `<p class="hint">「${esc(ch[0].before || "없음")}」 → 「${esc(ch[0].after || "지움")}」</p>` : "")
    + `<p class="hint">영향 ${x.lost.length}건${x.lost.length > 1 ? " · 관련 결과를 한 번에 다시 확인합니다" : ""}</p>`
    + `<details><summary>변경 내용 보기</summary><ul class="spill-list">`
    + ch.map((c) => `<li><b>${esc(nm(c.qid))}</b><span class="q">「${esc(c.before || "")}」 → 「${esc(c.after || "지움")}」</span></li>`).join("")
    + x.lost.map((l) => `<li class="gone"><b>${esc(l.slot || nm(l.qid))}</b><span class="q">${esc(was[l.was] || "이전 결과")} · ${esc(l.why || "")}</span></li>`).join("")
    + `</ul></details>`;
}
function readCard(q, restore, tok) {
  const me = st.answers.find((a) => a.qid === q.qid);
  const rule = restore ? restore.props : (st.props || []).filter((p) => p.by === q.qid && !st.answers.some((a) => a.qid === p.qid));
  const gone = restore ? [] : [...(st.before || [])].filter((id) => id !== q.qid && !st.aug.questions.some((x) => x.qid === id) && !rule.some((d) => d.qid === id)
    && !st.answers.some((a) => a.qid === id && a !== me)); st.before = null;
  const full = !!(st.aug && st.aug.budget && st.aug.budget.used >= st.aug.budget.max);   // no card can be shown: the AI is not asked
  const aiOk = !restore && !full && !!me && Date.now() >= AI.offUntil && (me.value || "").trim().length >= 8 && me.choice !== "unknown";
  if (!rule.length && !gone.length && !(me && me.read) && !aiOk) return Promise.resolve(false);
  const gen = st.gen, rev = st.rev, source = me;
  const current = () => gen === st.gen && !!source && st.answers.some((a) => a.qid === source.qid && a.choice === source.choice && a.value === source.value);
  void rev;
  const props = rule.map((p) => ({ ...p, origin: p.origin || "rule", taken: restore ? !!restore.used : p.taken })), keep = new Set(props.filter((p) => !p.weak).map((p) => p.pid)), apart = [];
  let ai = aiOk ? "reading" : "off", slow = false, used = !!(restore && restore.used), finished = false, done = null, dropped = false;
  // A2: its answer was taken back or changed (pruneReadings): the card stops and is not used
  if (tok) tok.cancel = () => { if (finished) return; dropped = true; if (ai === "reading") ai = "off"; draw(); end("stale"); };
  let card = used ? "ok" : null;                           // the confirmation request: null not yet, ok shown, no over budget
  const askCard = async () => {
    if (card || used || dropped) return;
    card = "wait"; const r = await issueAsk("card", q);
    if (r.gone || gen !== st.gen) return;
    if (r.offline) { card = null; b.insertAdjacentHTML("beforeend", `<p class="hint">서버에 연결하지 못해 확인 버튼을 아직 보이지 않습니다. 잠시 뒤 다시 그립니다.</p>`); setTimeout(() => !finished && draw(), 5000); return; }
    card = r.ok ? "ok" : "no";
    if (card === "no") { if (ai === "reading") { ai = "off"; ctl.abort(); } draw(); end(false); } else draw();
  };
  const b = bubble("assistant", ""); b.classList.add("note", "spill", "ai-card"); b.dataset.src = q.qid;
  const ctl = new AbortController();
  const timers = aiOk ? [setTimeout(() => { slow = true; draw(); }, 30000), setTimeout(() => ctl.abort(), 65000)] : [];
  const stop = () => timers.forEach(clearTimeout);
  const end = (r) => { if (finished) return; finished = true; stop(); if (ai === "reading") { ctl.abort(); ai = "stopped"; } done(r); };
  // the choice the server adopts and its value together (「가스절단 · 6개」, not 「6」); a typed-only choice shows its value
  const shown = (p) => { const ch = ((p.q && p.q.choices) || []).filter((c) => c.id !== "unknown"), lab = p.label || (ch.find((c) => c.id === p.choice) || {}).label || "";
    return ch.length > 1 && lab && p.value && !p.value.includes(lab) ? `${lab} · ${p.value}` : (p.value || lab); };
  const row = (p) => `<li class="${used ? "" : keep.has(p.pid) ? "" : "undone"}"><b>${esc(p.slot || slotOf(p.qid))}: ${esc(shown(p))}</b>`
    + (p.origin === "ai" ? `<span class="ai-chip">${used && p.taken ? AI_CHIP.done : AI_CHIP.read}</span>` : "") + AI_UNREAD(p)
    + (p.origin === "ai" ? `<span class="ai-when">${esc((p.who === "other" ? "다른 작업 · " : "") + (AI_WHEN[p.when] || "시점 미확인"))}</span>` : "")
    + (p.verbatim ? `<span class="ai-when">원문 그대로</span>` : "") + (p.weak ? `<span class="ai-when ai-unread">${esc(p.weak)}</span>` : "")
    + `<span class="q">← 「${esc(p.quote || "")}」</span>`
    + destLine(p)
    + (used ? (p.taken ? `<button type="button" class="linkbtn" data-rd-back="${esc(p.pid)}">이것 빼기</button>` : "")
      : `<button type="button" class="linkbtn" data-rd-fix="${esc(p.pid)}">항목 고치기</button><button type="button" class="linkbtn" data-rd-tog="${esc(p.pid)}">${keep.has(p.pid) ? "이것 빼기" : "다시 넣기"}</button>`) + `</li>`;
  // 「항목 고치기」 (design §4.3): the foreman writes the value himself — it becomes his own answer to that question
  // (a typed answer wins over a reading) and the reading leaves this card
  function fixRow(pid) {
    const p = props.find((x) => x.pid === pid); if (!p) return;
    b.querySelector(".rd-fix")?.remove();
    const li = b.querySelector(`[data-rd-fix="${CSS.escape(pid)}"]`)?.closest("li"); if (!li) return;
    li.insertAdjacentHTML("afterend", `<li class="rd-fix"><label>${esc(p.slot || slotOf(p.qid))} <input type="text" maxlength="120" value="${esc(p.value || "")}"></label>`
      + `<button type="button" class="btn small primary" data-rd-fixsave="${esc(pid)}">이 값으로 답하기</button><button type="button" class="btn small" data-rd-fixno>취소</button></li>`);
    b.querySelector(".rd-fix input")?.focus();
  }
  async function saveFix(pid) {
    const p = props.find((x) => x.pid === pid), inp = b.querySelector(".rd-fix input"), v = inp ? inp.value.trim() : "";
    if (!p || !v || st.busy) return;
    const q2 = p.q || {}, ch = (q2.choices || []).find((c) => c.id === p.choice);
    if (ch && !ch.ask) { toast("이 항목은 값을 적는 보기가 아닙니다. 그 질문에서 보기로 골라 주세요"); return; }
    const mine = { qid: p.qid, choice: p.choice, value: v, q: q2, at: Date.now() };
    st.answers = st.answers.filter((a) => a.qid !== p.qid).concat([mine]); bump(); pruneReadings();
    keep.delete(pid); props.splice(props.indexOf(p), 1); draw();
    if (!(await chatRefresh(() => saveFix(pid)))) return;
    if (st.aug.errors && st.aug.errors[p.qid]) {              // a value that question does not take: not kept
      st.answers = st.answers.filter((a) => a !== mine); bump();
      toast(`고친 값을 받지 못했습니다: ${st.aug.errors[p.qid]}`); await chatRefresh(() => {}); return;
    }
    answerBubble(p.qid, `${(ch && ch.label) || slotOf(p.qid)}: ${v}`);
    if (st.asked && st.asked.qid === p.qid) { if (st.askBox) st.askBox.setAttribute("aria-disabled", "true"); askNext(); }
    if (!props.length && !used) { used = true; draw(); end(false); }
  }
  function draw() {
    if (props.length && !card && !used && !dropped) askCard();          // the first time there is something to confirm
    const n = keep.size, waiting = !used && (props.length || ai !== "reading");
    if (dropped) {                                           // design §19.3 만료: 이전 내용 · 다시 확인
      b.innerHTML = `<p class="ai-h"><span class="ai-chip">이전 내용</span>원래 답이 바뀌어 이 읽기는 쓰지 않습니다 · 다시 확인</p>`
        + `<ul class="spill-list">${props.map((p) => `<li class="undone"><b>${esc(p.slot || slotOf(p.qid))}: ${esc(shown(p))}</b><span class="q">← 「${esc(p.quote || "")}」</span></li>`).join("")}</ul>`;
      return;
    }
    let h = `<p class="spill-h">${props.length ? (used ? `확인한 우리 작업 정보` : `우리 작업 정보 <b>${props.length}건</b>을 확인해 주세요`) : "이 답을 이렇게 읽었습니다"}</p><ul class="spill-list">`;
    if (me && me.read) h += `<li><b>${esc(slotOf(q.qid))}: ${esc(me.read)}</b><span class="q">이 질문의 답</span></li>`;
    h += props.map(row).join("");
    h += gone.map((id) => `<li class="gone"><b>${esc(slotOf(id))}</b><span class="q">이미 답에 있어 따로 묻지 않음</span></li>`).join("") + `</ul>`;
    if (ai === "reading") h += `<p class="ai-h"><span class="ai-chip">AI</span>답을 받았습니다 · ${esc(AI_STAGE[q.qid] || "대기 중")}${slow ? " · 평소보다 오래 걸립니다" : ""}</p>`
      + (slow && !props.length ? `<button type="button" class="btn small" data-rd-skip>기다리지 않고 다음 질문</button>` : "");
    if (ai === "fail") h += `<p class="hint ai-fail">${AI_CHIP.fail} · 적으신 말은 그대로 남겼습니다.</p>`;
    if (ai === "down") h += `<p class="hint ai-fail">${AI_CHIP.fail} · AI를 지금 쓸 수 없어 규칙으로만 읽었습니다.</p>`;
    if (apart.length) h += `<p class="ai-apart-h">따로 남김 · 우리 작업 답에 넣지 않음</p><ul class="spill-list ai-apart">${apart.map((x) => `<li><b>${esc(x.slot)}</b><span class="q">「${esc(x.quote)}」 · ${esc(x.why)}</span></li>`).join("")}</ul>`;
    if (!used && props.length && card === "ok") h += `<div class="ai-act"><button type="button" class="btn small primary" data-rd-ok ${n ? "" : "disabled"}>확인 (${n}건)</button><button type="button" class="btn small" data-rd-no>해석 취소</button></div>`;
    if (!used && props.length && card === "no") h += `<p class="hint">질문 한도(${st.aug.budget ? st.aug.budget.max : 12}회)에 닿았거나 이미 마무리한 검토라 이 읽기는 확인하지 않습니다. 적으신 말은 원문 그대로 남고 안전팀 확인으로 넘어갑니다.</p>`;
    if (used || !props.length) h += `<p class="hint">양식 칸에 맞는 것은 반영본에 파란 글씨로, 칸이 없는 것은 별지에 들어갑니다. 적으신 말은 원문 그대로 남습니다.</p>`;
    b.innerHTML = h;
    void waiting;
  }
  // the decision being sent: made once (its id, session and body), sent again as it is when the reply was lost
  let act = null;
  async function decide(adopt, reject, withdraw) {
    const key = JSON.stringify([adopt, reject, withdraw]);
    const shownNow = props.filter((p) => adopt.includes(p.pid) || reject.includes(p.pid)), confirm = shownNow.length > 0;
    if (!act || act.key !== key) act = { key, sid: st.sid, url: `/api/dialogues/${encodeURIComponent(st.sid || "")}/${confirm ? "confirm" : "decide"}`,
      body: JSON.stringify({ action_id: `${q.qid}:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`, adopt, reject, withdraw, fields: st.doc.fields,
        ...(confirm ? { displayed_digest: shownDigest(shownNow), expected_revision: st.srev ?? null } : {}) }) };
    const r = await fetch(act.url, { method: "POST", headers: { "Content-Type": "application/json" }, body: act.body });
    if (!r.ok) {
      const j = await r.json().catch(() => ({})), e = new Error((j.detail && j.detail.message) || `서버 오류 ${r.status}`);
      e.stale = r.status === 404 || r.status === 409; if (e.stale) act = null; throw e;
    }
    const j = await r.json(), sid = act.sid;
    act = null; seeRev(sid, j.revision);
    return j;
  }
  return new Promise((resolve) => {
    done = resolve;
    draw();
    if (aiOk) {
      sessionPost("/api/understand", { fields: st.doc.fields, answers: typedAnswers(), qid: q.qid }, { signal: ctl.signal })
        .then(async (r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const j = await r.json();
          if (!["ok", "none", "fail"].includes(j.status)) throw new Error("bad response");
          seeRev(r.sid, j.revision);
          return j;
        })
        .catch(() => ({ status: "fail", why: ctl.signal.aborted ? "abort" : "client" }))
        .then((j) => {
          stop();
          if (finished || ai !== "reading") return;
          if (!current()) { ai = "off"; b.insertAdjacentHTML("beforeend", `<p class="hint">답이 바뀌어 이 읽기는 쓰지 않았습니다.</p>`); end("stale"); return; }
          if (j.status === "fail") { ai = j.why === "down" ? "down" : "fail"; if (j.why === "down") AI.offUntil = Date.now() + 60000; }
          else ai = "done";
          for (const p of (j.props || []).filter((p) => p.pid && !props.some((x) => x.qid === p.qid) && !st.answers.some((a) => a.qid === p.qid))) {
            props.push({ ...p, origin: "ai" }); if (!p.weak) keep.add(p.pid);        // a reading marked weak waits for the foreman
          }
          apart.push(...(j.apart || []));
          draw();
          if (!props.length && !apart.length && !gone.length && !(me && me.read) && ai !== "fail" && ai !== "down") b.closest(".msgrow")?.remove();   // nothing was read: no card
          if (!props.length) end(false);                    // nothing to confirm: the review goes on
          else if (nearBottom()) toBottom();
        });
    } else if (!props.length || used) end(false);         // a confirmed card brought back: nothing to wait for
    b.addEventListener("click", async (e) => {
      if (dropped) return;
      const fx = e.target.closest("[data-rd-fix]");
      if (fx && !used) { fixRow(fx.dataset.rdFix); return; }
      const sv = e.target.closest("[data-rd-fixsave]");
      if (sv && !used) { await saveFix(sv.dataset.rdFixsave); return; }
      if (e.target.closest("[data-rd-fixno]")) { b.querySelector(".rd-fix")?.remove(); return; }
      const t = e.target.closest("[data-rd-tog]");
      if (t && !used) { const k = t.dataset.rdTog; if (keep.has(k)) keep.delete(k); else keep.add(k); draw(); return; }
      if (e.target.closest("[data-rd-skip]") && !finished) { ai = "off"; ctl.abort(); draw(); end(current() ? false : "stale"); return; }
      const back = e.target.closest("[data-rd-back]");
      if (back) {                                          // a confirmed one taken back alone: asked again later
        if (st.busy) return;
        const p = props.find((x) => x.pid === back.dataset.rdBack);
        try {
          const j = await decide([], [], [p.pid]); p.taken = false; takeAdopted(j.adopted); draw();
          document.querySelectorAll(".choices:not([aria-disabled])").forEach((x) => x.setAttribute("aria-disabled", "true"));   // asked again below
          bubble("assistant", `「${p.slot || slotOf(p.qid)}」은 빼고, 따로 여쭙겠습니다.`).classList.add("note"); await again();
        }
        catch (err) {
          if (!err.stale) { toast(`빼지 못했습니다: ${err.message}`); return; }
          p.taken = false; draw(); b.insertAdjacentHTML("beforeend", `<p class="hint">${esc(err.message)} 이 카드는 쓰지 않습니다.</p>`);
          await serverState().catch(() => {}); await again();
        }
        return;
      }
      const ok = e.target.closest("[data-rd-ok]"), no = e.target.closest("[data-rd-no]");
      if ((!ok && !no) || used) return;
      if (!current()) { used = true; draw(); end("stale"); return; }
      used = true; if (ai === "reading") { ai = "off"; ctl.abort(); }
      const adopt = ok ? props.filter((p) => keep.has(p.pid)).map((p) => p.pid) : [], reject = props.filter((p) => !adopt.includes(p.pid)).map((p) => p.pid);
      try {
        const j = await decide(adopt, reject, []);
        for (const p of props) p.taken = adopt.includes(p.pid);
        takeAdopted(j.adopted); draw();
        if (nearBottom()) toBottom();
        end(adopt.length > 0);
      } catch (err) {
        if (err.stale) {                                   // the answers changed meanwhile: this card no longer holds
          b.querySelector(".ai-act")?.remove(); b.insertAdjacentHTML("beforeend", `<p class="hint">${esc(err.message)} 이 카드는 쓰지 않습니다.</p>`);
          await serverState().catch(() => {}); end("stale"); await again(); return;
        }
        used = false; draw(); toast(`확인하지 못했습니다: ${err.message}. 다시 눌러 주세요`);
      }
    });
    if (nearBottom()) toBottom();
  });
}
async function again() {                      // refresh after the answers changed, then the next question
  if (await chatRefresh(again)) askNext();
}
// one wrong tap is undone alone: that answer (and the check questions about it) goes, the others stay, and the
// question is asked again
// the check questions (A1~A3, U1) asked about an item
const aboutOf = (qid) => { const item = qid.startsWith("FREE:") ? `F${qid.split(":")[1]}` : qid.split(":")[0];
  return (a) => { if (!qid.startsWith("FREE:") && a.qid.split(":")[1] !== qid.split(":")[1]) return false;     // this permit's only
    const it = a.qid.split(":")[0].split("."); return ["A1", "A2", "A3", "U1"].includes(it[0]) && [item, ...[1, 2, 3, 4, 5].map((k) => `${item}.${k}`)].includes(it.slice(1).join(".")); }; };
async function editAnswer(qid, ub, fix) {
  if (st.busy) return;
  const item = qid.startsWith("FREE:") ? `F${qid.split(":")[1]}` : qid.split(":")[0];
  const about = aboutOf(qid);
  // what came from this answer goes with it, and what came from those in turn (AI readings, their check questions)
  const gone = new Set([qid]);
  for (let grew = true; grew;) {
    grew = false;
    for (const a of st.answers) if (!gone.has(a.qid) && (a.by && gone.has(a.by) || (a.qid === qid || about(a)) || [...gone].some((g) => aboutOf(g)(a)))) { gone.add(a.qid); grew = true; }
  }
  st.answers = st.answers.filter((a) => !gone.has(a.qid));
  st.waitClose = false; pruneReadings();                     // A2: their readings end with them (again() below asks on)
  document.querySelectorAll("#msgs .ai-card").forEach((c) => { if (gone.has(c.dataset.src) && c.querySelector(".ai-chip.ok")) c.querySelector(".ai-h").innerHTML = `<span class="ai-chip">이전 내용</span>원래 답을 지워 이 읽기도 뺐습니다 · 다시 확인`; });
  st.fails[qid] = 0; bump();
  ub.parentNode.classList.add("undone"); fix.remove();
  document.querySelectorAll(".choices:not([aria-disabled])").forEach((b) => b.setAttribute("aria-disabled", "true"));
  st.reviewed = false; st.closing = false; st.cur = null;
  $("#to-plans").hidden = true; $("#composer").hidden = false;
  bubble("assistant", qid.startsWith("FREE:") ? "그 말을 지웠습니다. 다른 답은 그대로 있습니다." : "그 답을 지웠습니다. 다시 여쭙겠습니다. 다른 답은 그대로 있습니다.").classList.add("note");
  await again();
}
function reopenReview(msg) {
  st.reviewed = false; st.closing = false;
  $("#to-plans").hidden = true; $("#composer").hidden = false;
  bubble("assistant", msg).classList.add("note");
  askNext();
}
// ---------------------------------------------------------------- 칸 고치기 (QA #38·#40·#41): the chat's box edits a field
// A field picked on the form or in the 칸 목록 is shown above the chat's box (「수정할 칸: 작업장소」, its format, its notes,
// the questions and answers about it); its value is in the box. 「적용」 checks the format, writes it, and goes to the next
// blank below (page, then top, then left). The question being answered waits with what was typed for it, and comes back
// with 「질문으로 돌아가기」. Fields croScan never writes (허가구분·2중점검·서명·승인·당일 칸) are shown, not edited.
st.fedit = null; st.qdraft = null; st.fdrafts = {};
const baseKey = (k) => k.replace(/^p\d+\./, "");
const isProtected = (key, f) => f.type === "check" || f.type === "image" || ((st.aug && st.aug.protected) || []).includes(baseKey(key));
function formPos(k) {
  const f = D().fields[k], b = f && f.layout && f.layout.box;
  return [f ? f.page || 99 : 99, b ? Math.round(b[1] / 4) : 1e6, b ? b[0] : 0];
}
const formOrder = (keys) => [...keys].sort((a, b) => { const x = formPos(a), y = formPos(b); return x[0] - y[0] || x[1] - y[1] || x[2] - y[2] || (a < b ? -1 : 1); });
// the blanks croScan asks for: an open question's empty field, not one the 반영본 already fills from an answer
function blanks() {
  if (!st.aug || st.di !== 0 || !st.doc) return [];
  const rm = reflectMap(), ks = new Set();
  for (const q of st.aug.questions) for (const k of q.keys || []) {
    const f = st.doc.fields[k];
    if (f && !String(f.value).trim() && !isProtected(k, f) && !rm[k]) ks.add(k);
  }
  return formOrder(ks);
}
function nextBlank(key) {
  const all = blanks().filter((k) => k !== key);
  if (!all.length) return null;
  const at = formPos(key), after = all.find((k) => { const p = formPos(k); return p[0] > at[0] || (p[0] === at[0] && (p[1] > at[1] || (p[1] === at[1] && p[2] > at[2]))); });
  return after || all[0];
}
function paintFillbar() {
  const bar = $("#fillbar"), n = blanks().length;
  bar.hidden = !n || !!st.fedit || !chatEdit() || $("#p-chat").hidden || st.reviewed;
  if (bar.hidden) return;
  bar.innerHTML = `<span>채울 빈칸 <b>${n}개</b> · 양식 위에서 아래로</span>`;
  const b = el("button", "btn small", "위에서부터 채우기"); b.type = "button";
  b.onclick = () => { const k = blanks()[0]; if (k) selectField(k, "next"); };
  bar.appendChild(b);
}
// what was asked and answered about a field: the question cards and answers in the chat
function relatedOf(key) {
  const out = [];
  if (st.asked && (st.asked.keys || []).includes(key)) out.push({ qid: st.asked.qid, kind: "질문", text: st.asked.text });
  for (const a of st.answers) {
    const q = a.q || {};
    if (!(q.keys || []).includes(key)) continue;
    const c = (q.choices || []).find((x) => x.id === a.choice);
    out.push({ qid: a.by || a.qid, kind: "답", text: `${c ? c.label : a.choice}${a.value ? `: ${a.read || a.value}` : ""}${a.quote ? ` ← 「${a.quote}」` : ""}` });
  }
  return out;
}
function markRel(key) {
  msgs.querySelectorAll(".rel").forEach((x) => x.classList.remove("rel"));
  if (!key) return;
  for (const r of relatedOf(key)) msgs.querySelectorAll(`[data-qid="${CSS.escape(r.qid)}"]`).forEach((x) => x.classList.add("rel"));
}
function selectField(key, how) {
  const f = D() && D().fields[key];
  if (!f || !chatEdit()) return;
  sheet.querySelectorAll(".fi.sel, .fc.sel").forEach((x) => x.classList.remove("sel"));
  st.sel = key;
  if (how === "next" || how === "list" || how === "listkey") revealField(key);
  sheet.querySelector(`.fi[data-key="${CSS.escape(key)}"], .fc[data-key="${CSS.escape(key)}"]`)?.classList.add("sel");
  if (sheet.querySelector(".fl-split")) { listMark(key); listOrig(key); }
  editField(key, how === "click" || how === "list" || how === "next");
}
// only as much moving as it takes to see the field: the zoom and the pane size stay (QA #41)
function revealField(key) {
  const f = D().fields[key];
  if (st.view === "list") return;
  if (st.view !== "form") setView("form");
  if (f.page !== st.page) { st.page = f.page; renderTabs(); render(); }
  requestAnimationFrame(() => sheet.querySelector(`[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({ block: "nearest", inline: "nearest" }));
}
function editField(key, focus) {
  const f = D().fields[key];
  if (!st.fedit) st.qdraft = { text: input.value, qid: st.draftQ ?? null };
  else if (st.fedit !== key) { const g = D().fields[st.fedit]; if (g && input.value !== String(g.value ?? "")) st.fdrafts[st.fedit] = input.value; }
  if (st.fresKey !== key) st.fres = st.fresKey = null;
  st.fedit = key;
  $("#composer").hidden = false; $("#composer").classList.add("editing");
  $("#input-hint").hidden = true;
  const prot = isProtected(key, f);
  input.value = prot ? "" : (st.fdrafts[key] ?? String(f.value ?? ""));
  input.placeholder = prot ? "이 칸은 croScan에서 고치지 않습니다" : `「${f.name}」 값을 적고 「적용」 (Enter)`;
  send.querySelector("span").textContent = "적용";
  composerOn(true);
  paintFedit(); paintFillbar(); markRel(key);
  if (focus && !prot) { input.focus({ preventScroll: true }); input.setSelectionRange(input.value.length, input.value.length); }
}
function paintFedit(res) {
  const key = st.fedit, f = key && D() && D().fields[key], box = $("#fedit");
  if (!f) { box.hidden = true; return; }
  if (res) { st.fres = res; st.fresKey = key; } else if (st.fresKey === key) res = st.fres;     // the last 적용 stays said
  box.hidden = false; box.innerHTML = "";
  const head = el("div", "fedit-head");
  const left = blanks().filter((k) => k !== key).length;
  head.innerHTML = `<span class="fedit-lab">수정할 칸</span><b>${esc(f.name)}</b><span class="fedit-meta">${f.page}쪽${["text", "check"].includes(f.type) ? "" : ` · ${esc(TYPE_KO[f.type] || f.type)}`}${left ? ` · 남은 빈칸 ${left}개` : ""}</span>`;
  const x = el("button", "btn ghost small fedit-x"); x.type = "button";
  x.innerHTML = `${icon("i-x")}<span>${st.asked || st.closing || st.askLater ? "질문으로 돌아가기" : "칸 고치기 닫기"}</span>`;
  x.onclick = () => exitEdit(true);
  head.appendChild(x); box.appendChild(head);
  if (res) box.appendChild(res);
  if (isProtected(key, f)) box.appendChild(el("p", "ins-note warn", f.type === "check" ? "체크 칸은 문서에서 눌러 바꿉니다. 당일 확인 칸이라 반영본에는 넣지 않습니다."
    : `「${f.name}」${pp(f.name, "은", "는")} 전산·당일·서명·승인 칸이라 croScan이 고치지 않습니다. 원본 그대로 제출됩니다.`));
  else { const fx = fmtLine(key, f); if (fx) box.appendChild(fx); }
  const notes = el("div", "fl-notes");
  paintNotes(notes, key, f, flagMap()[key], false); box.appendChild(notes);
  const rel = relatedOf(key);
  if (rel.length) {
    const ul = el("ul", "fedit-rel");
    for (const r of rel.slice(-3)) {
      const li = el("li"); li.append(el("span", "k", r.kind), el("span", "t", r.text));
      const go = el("button", "linkbtn", "대화에서 보기"); go.type = "button";
      go.onclick = () => { const m = msgs.querySelector(`[data-qid="${CSS.escape(r.qid)}"]`); if (m) { m.scrollIntoView({ block: "center" }); m.classList.add("rel"); } };
      li.appendChild(go); ul.appendChild(li);
    }
    box.appendChild(ul);
  }
}
const resLine = (cls, text) => { const p = el("p", `ins-note fedit-res ${cls}`); p.innerHTML = `${icon(cls === "bad" ? "i-alert" : "i-check")}${esc(text)}`; return p; };
function applyEdit() {
  const key = st.fedit, f = D().fields[key];
  if (!f || isProtected(key, f)) return;
  let v = input.value.replace(/\s+$/, "");
  if (!(f.layout && f.layout.multi)) v = v.replace(/\s*\n\s*/g, " ").trim();
  if (CLEAN[f.type]) v = CLEAN[f.type](v);
  const before = String(f.value ?? "");
  if (v.trim() && !valid(f, v)) {                      // not written; said in the same place, the box keeps the words
    f.value = v; const msg = badMsg(f); f.value = before;
    paintFedit(resLine("bad", `적용하지 않았습니다 · ${msg}`)); input.focus(); return;
  }
  delete st.fdrafts[key];
  if (v !== before) {
    f.value = v; syncNode(key, f); edited(key, f);
    pickState(key, f, flagMap()[key], reflectMap()[key]); flash(key);
    bubble("assistant", `「${f.name}」 ${before.trim() ? `'${before}' → '${v || "(빈칸)"}'` : `빈칸에 '${v}'`} 적용 · 화면 수정 (업로드한 원본 파일은 그대로)`).classList.add("note", "edit");
  }
  const done = v !== before ? `「${f.name}」에 적용했습니다` : `「${f.name}」${pp(f.name, "은", "는")} 그대로 둡니다`;
  const nx = nextBlank(key);
  if (nx) { selectField(nx, "next"); paintFedit(resLine("ok", `${done} → 다음 빈칸`)); }
  else { exitEdit(false); toast(`${done}. 채울 빈칸이 더 없습니다.`); }
}
function exitEdit(user) {
  if (!st.fedit) return;
  const f = D() && D().fields[st.fedit];
  if (f && input.value !== String(f.value ?? "") && !isProtected(st.fedit, f)) st.fdrafts[st.fedit] = input.value;
  sheet.querySelectorAll(".fi.sel, .fc.sel").forEach((x) => x.classList.remove("sel"));
  st.fedit = null; st.sel = null;
  $("#fedit").hidden = true; $("#composer").classList.remove("editing");
  send.querySelector("span").textContent = "보내기";
  const d = st.qdraft; st.qdraft = null;
  input.value = d ? d.text : ""; st.draftQ = d && d.text.trim() ? d.qid : null;
  setAsk(st.cur && st.cur.c.ask ? st.cur.c.ask : null);
  if (st.closing) input.placeholder = "더 알려 주실 내용을 적어 주세요 · 없으면 아래 「없음」";
  composerOn(!!(st.asked || st.closing) && !st.busy);
  if (st.reviewed) $("#composer").hidden = true;
  markRel(null); paintFillbar();
  if (st.askLater) { st.askLater = false; askNext(); if (user) input.focus({ preventScroll: true }); }
  else if (st.asked && st.aug && !st.busy && !st.aug.questions.some((q) => q.qid === st.asked.qid)) moveOn();
  else if (user && (st.asked || st.closing)) input.focus({ preventScroll: true });
}
// the question being waited on was answered by an edit (its field is filled now): said, and the next one asked
// (while a field is being edited the next question waits until the box is back: it never takes the box)
function moveOn() {
  msgs.querySelectorAll(".choices:not([aria-disabled])").forEach((b) => b.setAttribute("aria-disabled", "true"));
  bubble("assistant", `고친 칸으로 이 질문은 답이 되었습니다.${st.fedit ? " 칸 고치기를 마치면 다음 질문으로 갑니다." : " 다음으로 넘어갑니다."}`).classList.add("note");
  st.cur = null;
  if (st.fedit) { st.asked = null; st.askLater = true; paintFedit(); return; }
  setAsk(null); askNext();
}
// a value just written into a field by an answer or an edit: the field and its row light up for a moment
function flash(key) {
  for (const n of document.querySelectorAll(`#sheet .fi[data-key="${CSS.escape(key)}"], #sheet .fl-pick[data-key="${CSS.escape(key)}"]`)) {
    n.classList.remove("just"); void n.offsetWidth; n.classList.add("just");
  }
}
// 승인번호 is in every question's id: when it is changed on screen the answers given so far follow it
const pidOf = (f) => String(f.value ?? "").trim().toUpperCase() || `#${f.page}`;
function relinkPermit(key, f) {
  const was = f._pid || (String(f.original ?? "").trim().toUpperCase() || `#${f.page}`), now = pidOf(f);
  f._pid = now;
  if (was === now) return;
  const swap = (id) => {
    const i = id ? id.indexOf(":") : -1;
    if (i < 0) return id;
    const [a, b] = id.slice(i + 1).split(">");
    return `${id.slice(0, i)}:${a === was ? now : a}${b != null ? `>${b === was ? now : b}` : ""}`;
  };
  for (const a of st.answers) {
    a.qid = swap(a.qid); if (a.by) a.by = swap(a.by);
    if (a.q && a.q.permit_no === was) Object.assign(a.q, { permit_no: now, qid: swap(a.q.qid) });
  }
  for (const k of Object.keys(st.fails)) { const n = swap(k); if (n !== k) { st.fails[n] = st.fails[k]; delete st.fails[k]; } }
  // the readings, what the server last had and the box's question follow too (A1·A2: not taken as changed answers)
  for (const [k, x] of [...READING]) { const n = swap(k); if (n !== k) { READING.delete(k); READING.set(n, x); } }
  if (st.sent) st.sent = Object.fromEntries(Object.entries(st.sent).map(([k, v]) => [swap(k), v]));
  if (st.draftQ) st.draftQ = swap(st.draftQ);
  msgs.querySelectorAll("[data-qid]").forEach((m) => { m.dataset.qid = swap(m.dataset.qid); });
  // the question on screen is the same object its buttons answer: changed in place
  if (st.asked && st.asked.permit_no === was) Object.assign(st.asked, { permit_no: now, qid: swap(st.asked.qid) });
}
NARROW.addEventListener("change", () => { if (NARROW.matches) exitEdit(false); if (st.doc && !$("#s-edit").hidden) render(); paintFillbar(); });

// ---------------------------------------------------------------- 임시저장: answers and edits stay on this device
const DRAFT_V = 2;
const draftKey = (src = st.src) => src && `croscan.draft.v${DRAFT_V}.${src.kind}.${src.hash}`;
const changedFields = (doc) => Object.fromEntries(Object.entries(doc.fields).filter(([, f]) => String(f.value) !== String(f.original)).map(([k, f]) => [k, f.value]));
function saveDraft() {
  if (!st.doc || !st.src || !st.live) return;
  const plans = { ...(st.draftPlans || {}) };      // plans of an earlier visit not uploaded again stay as they were
  (st.wp ? st.wp.plans : []).forEach((p, i) => {
    const e = p.doc ? changedFields(p.doc) : {}, id = planId(p);
    if (st.checked.has(i) || Object.keys(e).length) plans[id] = { checked: st.checked.has(i), edits: e }; else delete plans[id];
  });
  const d = { v: DRAFT_V, t: Date.now(), permit: [...new Set(st.doc.pages.map((p) => p.permit_no).filter(Boolean))].join(", "),
              answers: st.answers, sid: st.sid || null, sent: st.sent || null, fails: st.fails || {}, edits: changedFields(st.doc), reviewed: st.reviewed, plans, step: st.step, page: st.page,
              ck: st.ck ? ckPayload(true) : st.draftCk || null };
  try {
    localStorage.setItem(draftKey(), JSON.stringify(d));
    $("#autosave").textContent = `· 이 기기에 저장됨 ${new Date().toTimeString().slice(0, 5)}`; $("#autosave").classList.remove("bad");
  } catch (e) {
    $("#autosave").textContent = "· 이 기기에 저장 못 함 (저장 공간)"; $("#autosave").classList.add("bad");
  }
}
function loadDraft() { try { return JSON.parse(localStorage.getItem(draftKey()) || "null"); } catch (e) { return null; } }
function dropDraft() { try { localStorage.removeItem(draftKey()); } catch (e) { /* blocked */ } }
// the same permit read again on this device: offer to go on from where it was left
function offerResume() {
  const d = loadDraft();
  const n = d ? d.answers.length : 0, m = d ? Object.keys(d.edits || {}).length : 0, pl = d ? Object.keys(d.plans || {}).length : 0;
  const ckn = d && d.ck ? d.ck.permits.reduce((a, P) => a + P.items.filter((it) => it.touched || it.memo).length, 0) : 0;
  if (!n && !m && !pl && !ckn) return startReview();
  msgs.innerHTML = "";
  const when = new Date(d.t).toLocaleString("ko-KR", { month: "long", day: "numeric", hour: "numeric", minute: "2-digit" });
  bubble("assistant", `이 허가서(승인번호 ${d.permit || "없음"})를 ${when}에 검토하던 내용이 이 기기에 남아 있습니다. `
    + `답 ${n}건, 고친 칸 ${m}개${pl ? `, 작업계획서 확인·수정 ${pl}건` : ""}${ckn ? `, 위험 체크리스트 확인 ${ckn}개` : ""}`
    + `. 이어서 할까요?`).classList.add("note");
  const box = el("div", "choices");
  const go = el("button", "", "이어서 하기"), fresh = el("button", "soft", "새로 시작");
  go.type = fresh.type = "button";
  const close = (b) => { box.setAttribute("aria-disabled", "true"); go.disabled = fresh.disabled = true; b.classList.add("picked"); };
  const resume = async () => {
    if (st.sid) {
      try { await serverState(); }
      catch (e) { if (e.code === "session_missing") { st.sid = null; st.srev = null; st.sent = {}; st.answers = typedAnswers(); } }   // else: the retry below
    }
    if (!(await chatRefresh(resume))) return;
    bubble("assistant", `이어서 합니다. 답 ${n}건과 고친 칸 ${m}개를 되살렸습니다.` + (pl ? (st.wp ? " 이미 올린 작업계획서 중 같은 파일의 확인·수정한 내용도 되살렸습니다." : " 작업계획서는 1단계에서 같은 파일을 올리면 확인·수정한 내용이 되살아납니다.") : "")).classList.add("note");
    const group = (list) => list.reduce((m, p) => m.set(p.by, [...(m.get(p.by) || []), p]), new Map());
    const srcQ = (id) => { const a = st.answers.find((x) => x.qid === id); return { ...((a && a.q) || {}), qid: id }; };   // the card's own question
    for (const [src, list] of group(st.answers.filter((a) => a.pid))) readCard(srcQ(src), { props: list, used: true });
    for (const [src, list] of group(st.props || [])) {
      if (!st.answers.some((a) => a.qid === src)) continue;
      const r = await readCard(srcQ(src), { props: list });
      if (r === "stale") return;
      if (r) { if (!(await chatRefresh(resume))) return; }
    }
    if (d.reviewed && !st.aug.questions.length) finish(); else askNext();
  };
  go.onclick = () => {                             // once only: the buttons are off from here on
    if (go.disabled) return;
    close(go); st.live = true;
    for (const [k, v] of Object.entries(d.edits || {})) if (st.doc.fields[k]) { st.doc.fields[k].value = v; st.doc.fields[k].editedBy = "직접 수정"; }
    // the session's confirmations come from the server; without it only the typed answers come back
    st.sid = d.sid || null; st.sent = d.sent || null; st.answers = d.answers; st.fails = d.fails || {}; st.draftPlans = d.plans || null; st.draftCk = d.ck || null;
    if (st.wp && st.draftPlans) applyDraftPlans();
    if (d.page && st.doc.pages.some((p) => p.no === d.page)) st.page = d.page;
    renderTabs(); render(); updateChanges();
    for (const f of Object.values(st.doc.fields)) if (f.key === "permit_no") f._pid = pidOf(f);
    for (const a of st.answers.filter((x) => !x.by)) answerBubble(a.qid, a.qid.startsWith("FREE:") ? a.value : (() => {
      const c = ((a.q && a.q.choices) || []).find((x) => x.id === a.choice);
      return `${c ? c.label : a.choice}${a.value ? `: ${a.value}` : ""}`;
    })());
    resume();
  };
  fresh.onclick = () => { if (fresh.disabled) return; close(fresh); dropDraft(); startReview(); };
  box.append(go, fresh); msgs.appendChild(box); toBottom();
}
// design §1.3: the AI reads the permit and the confirmed 작업계획서 that goes with it while the foreman answers; what
// it finds comes in as questions on the next step (never over the one on screen); a failure is said, not hidden
async function startAnalyze() {
  const sid = st.sid, gen = st.gen;
  if (!sid) return;
  const line = bubble("assistant", "AI가 허가서" + (st.wp && st.wp.token ? "와 작업계획서" : "") + "를 읽는 중입니다. 질문은 그대로 이어집니다.");
  line.classList.add("note", "ai-status"); line.setAttribute("role", "status");
  const plans = st.wp && st.wp.token ? { token: st.wp.token, idx: [...st.checked] } : {};
  let j = {};
  try {
    const r = await sessionRead(() => ["/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: st.doc.fields, answers: typedAnswers(), session_id: sid, expected_revision: st.srev ?? null, plans }) }]);
    j = await r.json().catch(() => ({}));
    if (!r.ok) j = { status: "fail" };
  } catch (e) { j = { status: "fail" }; }
  if (gen !== st.gen || sid !== st.sid) return;
  const plan = j.plan && j.plan.title ? ` (작업계획서 「${j.plan.title}」 함께 읽음)` : "";
  line.textContent = ["ok", "none", "done"].includes(j.status) || (j.status === "done_before" && j.found != null)
    ? (j.found ? `AI가 서류에서 확인할 것 ${j.found}건을 찾아 질문에 더했습니다${plan}.` : `AI 분석 완료 · 더할 질문 없음${plan}.`)
    : j.status === "late" ? "AI 분석이 대화를 마친 뒤 끝나 묻지 않았습니다."
    : j.status === "stale" ? "AI가 읽는 동안 허가서가 바뀌어 그 결과는 쓰지 않았습니다."
    : "AI 미분석 · 규칙 질문으로 진행합니다.";
  if (j.found && !st.closing && !st.reviewed && !st.busy) { try { await refreshAug(); } catch (e) { /* the next step refreshes */ } }
  if (plans.token) suggestLinks(plans, sid, gen);
}
// 계획서 연결 제안 (design §6.3, LINK): after the analysis, the AI says which confirmed 작업계획서 is the same work, with a
// row of each as evidence; nothing is linked until the foreman says so (「아님」 keeps it apart from this permit)
// 계획서 연결 제안 (design §6.3·§19.1, LINK): which confirmed 작업계획서 is the same work as this permit (or contains it, or
// is one of its steps), with a row of each as evidence, the range of that plan, and the values it may bring — where
// each would go and what is there now. Nothing is linked and no value is taken until the foreman says so; only the
// values he ticks become his answers.
async function suggestLinks(plans, sid, gen) {
  let j = {};
  try {
    const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/link`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: st.doc.fields, plans }) });
    j = r.ok ? await r.json() : {};
  } catch (e) { j = {}; }
  if (gen !== st.gen || sid !== st.sid || j.status !== "ok" || !(j.links || []).length) return;
  for (const L of j.links) {
    const a = await issueAsk("link", { qid: String(L.plan) });
    if (!a.ok) continue;                                     // no ask left for it: the plan is read as before, not linked
    const b = bubble("assistant", ""); b.classList.add("note", "ai-card");
    const ev = { permit: `${L.permit.name}: ${L.permit.value}`, plan: `${L.plan_row.name}: ${L.plan_row.value}` };
    const imp = (L.imports || []).filter((x) => st.aug && st.aug.questions.some((q) => q.qid === x.qid));
    const sc = L.scope || {};
    b.innerHTML = `<p class="spill-h"><span class="ai-chip">AI 제안</span>작업계획서 「${esc(L.title || `#${L.plan + 1}`)}」이 이 허가서와 <b>${esc(L.rel_ko || L.rel)}</b>으로 보입니다. 맞나요?</p>`
      + `<ul class="spill-list"><li><b>허가서</b><span class="q">「${esc(ev.permit)}」</span></li><li><b>계획서</b><span class="q">「${esc(ev.plan)}」</span></li>`
      + `<li><b>계획서 작업 범위</b><span class="q">${esc(sc.when || "")}${sc.where ? ` · ${esc(sc.where)}` : ""}${(sc.steps || []).length ? ` · 단계 ${sc.steps.length}개` : ""}</span></li></ul>`
      + (imp.length ? `<p class="ai-apart-h">가져올 값 · 고른 것만 반장 답으로 넣습니다</p><ul class="spill-list lk-imp">` + imp.map((x, k) =>
        `<li><label><input type="checkbox" data-imp="${k}" checked> <b>${esc(x.slot)} (${esc(x.kind)})</b></label><span class="q">들어갈 곳: ${esc(x.dest)} · ${esc(x.before)} → ${esc(x.value)}</span></li>`).join("") + `</ul>` : "")
      + ((L.not_imported || []).length ? `<p class="hint">${L.not_imported.map(esc).join("<br>")}</p>` : "")
      + `<div class="ai-act"><button type="button" class="btn small primary" data-lk="1">같은 작업으로 연결</button><button type="button" class="btn small" data-lk="0">아님</button></div>`
      + `<p class="hint">연결은 서류를 함께 읽는 데와 고른 값에만 씁니다. 서명·승인·책임자 칸은 옮기지 않습니다.</p>`;
    b.addEventListener("click", async (e) => {
      const t = e.target.closest("[data-lk]"); if (!t || b.dataset.done) return;
      b.dataset.done = "1";
      const yes = t.dataset.lk === "1", at = Date.now(), chosen = yes ? imp.filter((x, k) => b.querySelector(`[data-imp="${k}"]`)?.checked).map((x) => ({ ...x, at })) : [];
      try {
        const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/link/confirm`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan: L.plan, token: plans.token, title: L.title || "", rel: L.rel, accept: yes, evidence: ev, digest: L.digest || "",
            imports: chosen.map(({ qid, choice, value, at }) => ({ qid, choice, value, at })) }) });
        if (!r.ok) throw new Error(String(r.status));
        b.querySelectorAll("input[data-imp]").forEach((x) => { x.disabled = true; });
        b.querySelector(".ai-act").outerHTML = `<p class="hint">${yes ? `연결했습니다.${chosen.length ? ` 고른 값 ${chosen.length}개를 답으로 넣었습니다.` : ""}` : "이 허가서와 따로 둡니다. 이 계획서에서 나온 질문은 묻지 않습니다."}</p>`;
        if (yes && chosen.length) await takeImports(chosen);
        else if (!yes && !st.closing && !st.busy) { try { await refreshAug(); } catch (err) { /* the next step refreshes */ } }
      } catch (err) { delete b.dataset.done; toast("저장하지 못했습니다. 다시 눌러 주세요"); }
    });
  }
}
// the values the foreman ticked on a link card: his answers to those open questions (as if typed), said as such
async function takeImports(list) {
  const now = Date.now(), cur = st.asked; let n = 0;
  for (const x of list) {
    if (st.answers.some((a) => a.qid === x.qid)) continue;
    const q = st.aug.questions.find((y) => y.qid === x.qid); if (!q) continue;
    st.answers.push({ qid: x.qid, choice: x.choice, value: x.value, q, at: x.at || now }); n++;
    answerBubble(x.qid, `${(q.choices.find((c) => c.id === x.choice) || {}).label || ""}: ${x.value} (작업계획서에서 가져옴)`);
  }
  if (!n) return;
  bump(); saveDraft();
  if (cur && list.some((x) => x.qid === cur.qid)) {         // the question on screen was answered by it: the next one
    if (st.askBox) st.askBox.setAttribute("aria-disabled", "true");
    if (st.cur && st.cur.q === cur) { st.cur = null; setAsk(null); }
    if (input.value.trim() && st.draftQ === cur.qid)          // A1: his words stay, tied to that question
      bubble("assistant", `작업계획서에서 가져온 값으로 「${slotOf(cur.qid)}」 질문이 답해졌습니다. 적던 내용은 입력칸에 그대로 있습니다.`).classList.add("note");
    await again();
  } else if (!st.busy) { try { await refreshAug(); } catch (e) { /* the next step refreshes */ } }
}
// a linked plan changed since it was linked (design §2.3): the link and the values it brought are checked again
async function checkLinks() {
  const sid = st.sid; if (!sid || !(st.wp && st.wp.token)) return;
  let j = {};
  try { const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/links/check`, { method: "POST" }); j = r.ok ? await r.json() : {}; } catch (e) { return; }
  if (sid !== st.sid) return;
  for (const L of (j.links || []).filter((x) => x.status === "confirmed" && (x.expired || x.gone))) {
    const vals = L.imports || [];
    const b = bubble("assistant", ""); b.classList.add("note", "ai-card");
    b.innerHTML = `<p class="spill-h"><b>작업계획서 「${esc(L.title || "")}」이 바뀌어 다시 확인이 필요합니다</b></p>`
      + `<p class="hint">연결한 뒤 계획서가 ${L.gone ? "보관 기간이 지나 없어졌습니다" : "고쳐졌습니다"} · 가져온 값 ${vals.length}건</p>`
      + (vals.length ? `<ul class="spill-list">${vals.map((x) => `<li><b>${esc(slotOf(x.qid))}</b><span class="q">${esc(x.value)}</span></li>`).join("")}</ul>` : "")
      + `<div class="ai-act"><button type="button" class="btn small" data-lx="drop">가져온 값 빼기</button>${L.gone ? "" : `<button type="button" class="btn small" data-lx="keep">그대로 둠</button>`}</div>`;
    b.addEventListener("click", async (e) => {
      const t = e.target.closest("[data-lx]"); if (!t || b.dataset.done) return;
      b.dataset.done = "1";
      const keep = t.dataset.lx === "keep";
      try {
        const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/link/confirm`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan: L.plan, token: L.token, title: L.title || "", rel: L.rel, accept: keep, evidence: L.evidence || {},
            digest: keep ? (L.digest_now || "") : "", imports: keep ? L.imports || [] : [] }) });
        if (!r.ok) throw new Error(String(r.status));
        if (!keep && vals.length) {
          st.answers = st.answers.filter((a) => a.pid || !vals.some((v) => v.qid === a.qid && v.value === a.value)); bump(); saveDraft(); pruneReadings();
          try { await refreshAug(); } catch (err) { /* the next step refreshes */ }
        }
        if (keep && vals.length) await takeImports(vals);
        b.querySelector(".ai-act").outerHTML = `<p class="hint">${keep ? "바뀐 계획서로 다시 연결했습니다." : "연결을 풀고 가져온 값을 뺐습니다. 그 질문은 안전팀 확인으로 남습니다."}</p>`;
      } catch (err) { delete b.dataset.done; toast("저장하지 못했습니다. 다시 눌러 주세요"); }
    });
  }
}
async function startReview() {
  st.live = true; st.gen = (st.gen || 0) + 1;
  if (st.fedit) exitEdit(false);
  st.askLater = false; st.fdrafts = {};
  msgs.innerHTML = ""; const had = st.answers.length; st.answers = []; st.cur = null; st.closing = false; st.fails = {}; st.reviewed = false;
  st.sid = null; st.srev = null; st.sent = {}; st.draftQ = null; st.props = []; st.refused = new Set();   // a new review: a new session (nothing confirmed before comes back)
  READING.clear(); st.waitClose = false; st.waitNote = null;              // nothing of the last review is still awaited
  if (had) bump();
  $("#to-plans").hidden = true; $("#composer").hidden = false;
  if (!(await chatRefresh(startReview))) return;
  startAnalyze();
  const n = st.aug.questions.length;
  bubble("assistant", (n ? `허가서를 먼저 살펴봤습니다. 확인할 것이 ${n}가지 있습니다.` : "허가서를 먼저 살펴봤습니다. 따로 확인할 것은 없습니다.") +
    "\n양식 칸에 맞는 답은 반영본의 그 칸에 파란 글씨로 들어가고, 나머지는 별지에 들어갑니다. 원본 파일은 바뀌지 않습니다. 모르면 「모름」을 누르세요.").classList.add("note");
  askNext();
}
$("#restart").onclick = () => {
  if (!st.doc) return;
  if (st.answers.length && !confirm("지금까지 한 답을 지우고 질문을 처음부터 다시 할까요?")) return;
  startReview();
};
$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  if (st.fedit) { applyEdit(); return; }               // a field is being edited: never an answer (「없음」「끝」 too)
  if (st.busy) return;
  const t = input.value.trim();
  if (!st.doc) return;
  if (!t) {
    if (st.cur) bubble("assistant", `「${st.cur.c.label}」${pp(st.cur.c.label, "을", "를")} 고르셨습니다. 아래 칸에 내용을 적고 「보내기」를 눌러 주세요.${st.cur.c.ask ? ` 적을 내용: ${st.cur.c.ask}.` : ""} 모르면 「모름」을 누르세요.`).classList.add("note");
    else if (st.asked) bubble("assistant", "위 버튼으로 답하거나, 내용을 적고 보내기를 눌러 주세요.").classList.add("note");
    input.focus();
    return;
  }
  const owner = draftOwner(), was = st.draftQ;
  if (was != null && owner != null && was !== owner) {      // A1: written for a question answered meanwhile
    st.draftQ = owner;
    bubble("assistant", `입력칸의 내용은 ${was ? `「${slotOf(was)}」 질문에` : "마무리 말로"} 적던 것입니다. 지금 ${owner ? "질문" : "마무리"}의 답이 맞으면 「보내기」를 한 번 더 눌러 주세요.`).classList.add("note");
    input.focus();
    return;
  }
  if (st.closing) {
    if (YES_ONLY.test(t.replace(/[\s.,!~?]+/g, ""))) {             // 「네」 alone: more to say, or nothing? not guessed
      bubble("user", t); input.value = ""; st.draftQ = null;
      bubble("assistant", "더 알려 주실 내용을 적어 주세요. 없으면 「없음 · 검토 마치기」를 눌러 주세요.").classList.add("note");
      return;
    }
    freeAnswer(t); return;
  }
  if (!st.asked) return;
  // a short 「없어요」「몰라요」「네」 is that button, never text put into another choice ('없어요' must not become
  // 「있음: 없어요」, even after 「있음」 was picked); a longer answer goes to the picked choice, or to the only choice
  // that takes text. With two such choices of different meaning (보수 / 교체) croScan does not pick one.
  const short = t.replace(/[\s.,!~?]+/g, ""), byId = (...ids) => st.asked.choices.find((x) => ids.includes(x.id));
  const kind = DONT_KNOW.test(short) ? "unknown" : NO_ONLY.test(short) ? "no" : YES_ONLY.test(short) ? "yes" : null;
  const said = kind === "unknown" ? byId("unknown") : kind === "no" ? byId("none", "no", "na") : kind === "yes" ? byId("yes") : null;
  // the buttons of the question on screen (a note after them must not lose the answer)
  const box = st.cur ? st.cur.box : [st.askBox, st.pairQ && st.pairQ.box].find((b) => b && b.dataset.qid === st.asked.qid) || null;
  const mark = (c) => box && box.querySelectorAll("button").forEach((x) => x.classList.toggle("picked", x.textContent === c.label));
  if (said && !(st.cur && st.cur.c.id === said.id)) {
    mark(said);
    if (said.ask) {                                             // 「있어요」 for 「있음」: ask what, as the button does
      st.cur = { q: st.asked, c: said, box }; input.value = ""; st.draftQ = null; setAsk(said.ask);
      bubble("assistant", `「${said.label}」으로 받았습니다. ${said.ask}`).classList.add("note");
      return;
    }
    st.cur = null;
    answer(st.asked, said, "", box);
    return;
  }
  if (kind) {                                                    // 「네」「없어요」 with no such button: not guessed
    bubble("assistant", st.cur ? `「${st.cur.c.label}」의 내용을 적어 주세요. 다른 답이면 위 버튼을 다시 골라 주세요.`
      : "이 질문은 위 버튼 중에서 골라 주세요.").classList.add("note");
    return;
  }
  const typed = st.asked.choices.filter((x) => x.ask);
  const cur = st.cur || (typed.length === 1 ? { q: st.asked, c: typed[0], box } : null);
  if (!cur) {
    bubble("assistant", typed.length ? "어느 쪽인지 위 버튼을 먼저 골라 주세요. 적으신 내용은 입력칸에 그대로 있으니, 고른 뒤 보내기만 누르면 됩니다."
      : "이 질문은 위 버튼으로 답해 주세요.").classList.add("note");
    return;
  }
  if (!st.cur) mark(cur.c);
  answer(cur.q, cur.c, t, cur.box);
});
// A1: what is in the box was written for the question on screen then (or for the closing line: ""); it stays tied to it
const draftOwner = () => (st.closing ? "" : st.asked ? st.asked.qid : null);
input.addEventListener("input", () => {
  if (st.fedit) return;                                        // a field's value, not an answer
  if (!input.value.trim()) st.draftQ = null; else if (st.draftQ == null) st.draftQ = draftOwner();
});
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); }
});

// ---------------------------------------------------------------- 3. 작업계획서 목록: one at a time, each one checked off
const when = (a, b) => a ? `${a.replace("T", " ")} ~ ${b ? (b.slice(0, 10) === a.slice(0, 10) ? b.slice(11) : b.replace("T", " ")) : "?"}` : "시간 없음";
function renderPlanList() {
  if (!st.wp) return;
  const had = document.activeElement && document.activeElement.closest("#plan-list") ? [document.activeElement.closest("li")?.dataset.i, document.activeElement.className] : null;
  const ul = $("#plan-list"), q = ($("#plan-q").value || "").trim().toLowerCase();
  ul.innerHTML = "";
  const bad = st.wp.files.filter((f) => f.error);
  st.wp.plans.forEach((p, i) => {
    const text = [p.doc_no, p.work_no, p.company, p.title, p.location, p.target, ...p.items.map((x) => x.value)].join(" ").toLowerCase();
    if (q && !text.includes(q)) return;
    const li = el("li", "plan" + (st.di === i + 1 ? " on" : "") + (st.checked.has(i) ? " checked" : "")); li.dataset.i = i;
    const edited = p.doc ? editCount(p.doc) : 0;
    const open = el("button", "plan-open");
    open.type = "button";
    open.innerHTML = `<span class="plan-no">${i + 1}</span><span class="plan-body"><b>${esc(p.title || "(작업명 없음)")}</b>`
      + `<span>${esc(p.company || "업체 없음")} · ${esc(when(p.start, p.end))}</span><span>${esc(p.location || "위치 없음")}</span>`
      + (p.warnings.length ? `<span class="warn">${icon("i-alert")}${esc(p.warnings.join(" · "))}</span>` : "")
      + (edited ? `<span class="edited">고친 칸 ${edited}개</span>` : "") + "</span>";
    open.setAttribute("aria-current", st.di === i + 1 ? "true" : "false");
    open.onclick = () => { if (p.doc) { showDoc(i + 1); phonePane("doc"); } else { st.planOpen = st.planOpen === i ? null : i; renderPlanList(); } };
    const chk = el("button", "plan-check");
    chk.type = "button"; chk.setAttribute("aria-pressed", st.checked.has(i));
    chk.innerHTML = `${icon("i-check")}<span>${st.checked.has(i) ? "확인함" : "확인"}</span>`;
    chk.setAttribute("aria-label", `${i + 1}번 ${p.title || ""} ${st.checked.has(i) ? "확인 취소" : "확인 표시"}`);
    chk.onclick = () => {
      if (st.checked.has(i)) st.checked.delete(i); else st.checked.add(i);
      bump();
      renderPlanList();
      // checked: go on to the next one not yet checked
      const nx = st.wp.plans.findIndex((x, k) => !st.checked.has(k) && x.doc);
      if (st.checked.has(i) && nx >= 0 && st.di === i + 1) {
        showDoc(nx + 1);
        toast(`${i + 1}번 확인. 다음은 ${nx + 1}번 「${st.wp.plans[nx].title || ""}」입니다. (확인 ${st.checked.size}/${st.wp.plans.length})`);
      } else if (st.checked.has(i) && nx < 0) toast(`작업계획서를 모두 확인했습니다. 「${$("#go-submit").textContent.trim()}」 버튼을 눌러 주세요.`);
    };
    li.append(open, chk);
    if (st.planOpen === i || !p.doc) li.appendChild(planDetail(p));
    const mp = wpMapBox(i); if (mp) li.appendChild(mp);
    ul.appendChild(li);
  });
  for (const f of bad) ul.appendChild(el("li", "plan-bad", `읽지 못한 파일: ${f.name} · ${f.error}`));
  const n = st.wp.plans.length, c = st.checked.size;
  $("#pcount").textContent = `${n}건 · 확인 ${c}건`;
  $("#pprogress b").style.width = (n ? c / n * 100 : 0) + "%";
  $("#plans-left").textContent = c === n ? "모두 확인했습니다." : `아직 확인하지 않은 계획서가 ${n - c}건 있습니다. 모두 확인하면 다음으로 넘어갑니다.`;
  nextFromPlans(); paintStepper();
  if (had) ul.querySelector(`li[data-i="${had[0]}"] > .${had[1].split(" ")[0]}`)?.focus();
}
$("#plan-q").addEventListener("input", renderPlanList);
// design §1.3(1)·§6.4: while the plans are checked, each is read ahead on the server (behind any answer being read);
// labels croScan could not read come back as reading links to confirm — a reading corrected, not a value edited
async function wpPrepare() {
  const tok = st.wp && st.wp.token; if (!tok) return;
  try {
    const r = await fetch(`/api/workplans/${tok}/prepare`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idx: [], session_id: st.sid || "" }) });
    const j = r.ok ? await r.json() : {};
    if (!st.wp || st.wp.token !== tok) return;
    st.wpPrep = j.plans || {}; renderPlanList();
  } catch (e) { /* read later; nothing is offered */ }
}
function wpMapBox(i) {
  const prep = st.wpPrep && st.wpPrep[String(i)], maps = prep ? prep.maps : [];
  if (!maps || !maps.length) return null;
  const box = el("div", "wp-map");
  box.innerHTML = `<p><span class="ai-chip">AI 제안</span><b>읽지 못한 칸 ${maps.length}개의 뜻</b></p><ul>` + maps.map((m, k) =>
    `<li><span>${esc(m.page ? `${m.page}쪽 ` : "")}「${esc(m.label)}: ${esc(m.value)}」</span><span class="hint">연결 전: 알 수 없는 칸 → 연결 후: ${esc(m.key_label)}</span>`
    + `<span class="wp-map-act"><button type="button" class="btn small" data-wpm="${k}" data-ok="1">연결</button><button type="button" class="btn small ghost" data-wpm="${k}" data-ok="0">아님</button></span></li>`).join("")
    + `</ul><p class="hint">계획서의 값은 바꾸지 않습니다. croScan이 이 칸을 어느 항목으로 읽을지만 정합니다.</p>`;
  box.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-wpm]"); if (!b || b.disabled) return;
    const m = maps[+b.dataset.wpm]; b.disabled = true;
    try {
      const r = await fetch(`/api/workplans/${st.wp.token}/maps`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: i, label: m.label, key: m.key, accept: b.dataset.ok === "1" }) });
      if (!r.ok) throw new Error(String(r.status));
      const j = await r.json();
      if (b.dataset.ok === "1" && j.plan) Object.assign(st.wp.plans[i], Object.fromEntries(Object.entries(j.plan).filter(([, v]) => v)));
      st.wpPrep[String(i)].maps = maps.filter((x) => x !== m);
      toast(b.dataset.ok === "1" ? `「${m.label}」을 ${m.key_label}(으)로 읽습니다` : `「${m.label}」은 연결하지 않습니다`);
      renderPlanList();
    } catch (err) { b.disabled = false; toast("저장하지 못했습니다. 다시 눌러 주세요"); }
  });
  return box;
}
function nextFromPlans() {
  const b = $("#go-submit"), on = !!(st.doc && sameSource());
  b.innerHTML = `${on ? "다음: 허가서 검토" : "다음: 허가서 올리기"}${icon("i-right")}`;
  b.disabled = !plansOk();
  b.onclick = () => goStep(on ? 2 : 1);
  $("#wp-back").hidden = !st.wp;
}
function pageText(pages) {        // "a.pdf 1–2쪽, b.pdf 3쪽"
  const by = new Map();
  for (const x of pages) { if (!by.has(x.file)) by.set(x.file, []); by.get(x.file).push(x.page); }
  return [...by].map(([f, ns]) => `${f} ${ns.length > 1 && ns.every((n, i) => !i || n === ns[i - 1] + 1) ? `${ns[0]}–${ns[ns.length - 1]}` : ns.join(",")}쪽`).join(", ");
}
function planDetail(p) {
  const d = el("div", "plan-detail");
  const headKV = [["문서번호", p.doc_no], ["작업번호", p.work_no], ["개정", p.rev], ["작성·발행", p.issued], ["계획일", p.plan_date], ["도면 배치 기준", p.drawing_basis]];
  const kv = (rows) => { const g = el("dl", "pd-kv"); for (const [k, v] of rows) { g.appendChild(el("dt", "", k)); g.appendChild(el("dd", "", v || "(빈칸)")); } return g; };
  const secs = new Map([["머리", headKV]]);
  for (const x of p.items) { const s = x.section || "머리"; if (!secs.has(s)) secs.set(s, []); secs.get(s).push([x.label, x.value]); }
  for (const [s, rows] of secs) {
    d.appendChild(el("p", "pd-sec", s));
    d.appendChild(kv(rows));
  }
  d.appendChild(el("p", "pd-src", `원본: ${pageText(p.pages)}`));
  return d;
}

// an edit on a plan's form goes back into its record (the list, the search, later steps)
function syncPlan(p) {
  if (!p || !p.doc) return;
  const F = p.doc.fields, v = (fk) => (fk && F[fk] ? String(F[fk].value) : null);
  for (const x of p.items) { const nv = v(x.fk); if (nv != null) x.value = nv; }
  for (const [k, fk] of Object.entries(p.head_fk || {})) { const nv = v(fk); if (nv != null) p[k] = nv; }
  const by = Object.fromEntries(p.items.filter((x) => x.key).map((x) => [x.key, x.value]));
  const iso = (s) => { const m = /(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/.exec(s || ""); return m ? `${m[1]}-${m[2]}-${m[3]}${m[4] ? `T${m[4].padStart(2, "0")}:${m[5]}` : ""}` : ""; };
  p.title = by.title || ""; p.company = (by.company || "").split(" / ")[0].trim();
  p.start = iso(by.start); p.end = iso(by.end); p.location = by.location || ""; p.target = by.target || "";
  if (p.grid && p.grid.fks) p.grid.rows.forEach((r, ri) => r.forEach((_, ci) => { const nv = ci ? v(p.grid.fks[`${ri}_${ci}`]) : null; if (nv != null) r[ci] = nv; }));
  renderNav(); renderPlanList();
}

// 작업계획서 edits: saved on the server (the 수정본 PDF is made from them)
function planEdits() {
  const out = {};
  (st.wp ? st.wp.plans : []).forEach((p, i) => {
    if (!p.doc) return;
    const ch = Object.fromEntries(Object.entries(p.doc.fields).filter(([, f]) => String(f.value) !== String(f.original)).map(([k, f]) => [k, String(f.value)]));
    if (Object.keys(ch).length) out[i] = ch;
  });
  return out;
}
let saveTimer = null;
st.editVer = 0;
function scheduleSave() {
  st.editVer++;
  clearTimeout(saveTimer);
  st.wpSaving = true; showSave("저장 중…");
  saveTimer = setTimeout(savePlans, 800);
}
function showSave(t, bad) {
  const s = $("#wpsave"); s.hidden = st.di === 0; s.textContent = bad ? `${t} · 눌러서 다시 저장` : t; s.classList.toggle("bad", !!bad);
  s.disabled = !bad;
}
$("#wpsave").onclick = () => { showSave("저장 중…"); savePlans(); };
// saves go out one after another: each sends every change, so a late older one must never land after a newer one
let saveChain = Promise.resolve(true);
function savePlans() {
  clearTimeout(saveTimer);
  saveChain = saveChain.then(saveNow, saveNow);
  return saveChain;
}
async function saveNow() {
  if (!st.wp || !st.wp.token) return false;
  const ver = st.editVer;                       // what this request carries; a newer edit keeps "저장 중…"
  try {
    const r = await fetch(`/api/workplans/${st.wp.token}/edits`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ edits: planEdits() }) });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || `서버 오류 ${r.status}`);
    st.wpSaved = j.saved;
    if (ver === st.editVer) { st.wpSaving = false; showSave(`저장됨 ${j.saved.slice(11, 16)}`); }
    return true;
  } catch (e) {
    st.wpSaving = false; showSave(`저장하지 못했습니다: ${e.message}`, true);
    return false;
  }
}
async function downloadPlans(path) {
  if (!(await savePlans())) return;
  const a = document.createElement("a");
  a.href = `/api/workplans/${st.wp.token}/${path}`;
  document.body.appendChild(a); a.click(); a.remove();
}

// ---------------------------------------------------------------- 4. 제출: check before the PDF is made
function renderSummary() {
  const dl = $("#summary"); dl.innerHTML = "";
  const aug = st.aug || { questions: [], records: [] };
  const unknown = st.answers.filter((a) => a.choice === "unknown");
  const permitNos = [...new Set(st.doc.pages.map((p) => p.permit_no).filter(Boolean))].join(", ") || "(없음)";
  const plans = st.wp ? st.wp.plans : [], bad = st.wp ? st.wp.files.filter((f) => f.error) : [];
  const changedIn = (doc) => { const seen = new Set(); return Object.entries(doc.fields).filter(([k, f]) => {
    if (seen.has(k) || String(f.value) === String(f.original)) return false; seen.add(k); (f.same || []).forEach((o) => seen.add(o)); return true; }); };
  const invalidIn = (doc) => Object.entries(doc.fields).filter(([, f]) => !valid(f, f.value));
  const show = (f, v) => f.type === "check" ? (v ? "체크" : "빈칸") : (String(v).trim() ? v : "(빈칸)");
  const permitEd = changedIn(st.doc), permitBad = invalidIn(st.doc);
  const planEd = plans.flatMap((p, i) => p.doc ? changedIn(p.doc).map(([, f]) => [i, f]) : []);
  const planBad = plans.flatMap((p, i) => p.doc ? invalidIn(p.doc).map(([k, f]) => [i, f, k]) : []);
  const unchecked = plans.map((p, i) => [i, p]).filter(([i]) => !st.checked.has(i));
  const first = unchecked.find(([, p]) => p.doc);
  const go = (step, then) => () => { st.fromSummary = true; goStep(step); if (then) then(); $("#back-sum").hidden = false; };
  // [title, summary, where 바꾸기 goes, warn?, detail lines]
  const rows = [                                  // in the order of the steps (QA #33: 작업계획서 first)
    ["작업계획서", [`${plans.length}건 · 확인 ${st.checked.size}건`, unchecked.length ? `확인 안 함 ${unchecked.length}건` : ""],
      go(3, () => first && showDoc(first[0] + 1)), unchecked.length, unchecked.map(([i, p]) => `${i + 1}. ${p.title || p.doc_no || ""}`)],
    ...(bad.length ? [["읽지 못한 파일", `${bad.length}개 (제출본에 들어가지 않음)`, go(3, () => { show("s-plans"); renderPlanFiles(); }), 1, bad.map((f) => `${f.name}: ${f.error}`)]] : []),
    ["작업계획서에서 고친 칸", `${planEd.length}개`, go(3), 0, planEd.map(([i, f]) => `${i + 1}번 ${f.name}: ${show(f, f.original)} → ${show(f, f.value)}`)],
    ["허가서", `${st.doc.pages[0].kind_label || ""} · 승인번호 ${permitNos} · ${st.src.file.name}`, go(1), 0, []],
    ["확인 질문", `답 ${st.answers.length}건` + (unknown.length ? ` · 모름 ${unknown.length}건` : "") + (aug.questions.length ? ` · 답하지 않음 ${aug.questions.length}건` : "")
      + ((aug.proposals || []).length ? ` · 해석 확인 전 ${aug.proposals.length}` : "") + (aug.analysis_note ? " · AI 미완료 1" : "")
      + (st.reviewPending ? " · 고친 값 다시 살펴보는 중" : ""),
      go(2, () => setView("form")), unknown.length || aug.questions.length || (aug.proposals || []).length || aug.analysis_note || st.reviewPending,
      [...unknown.map((a) => `모름: ${(a.q && a.q.text) || a.qid}`), ...aug.questions.map((q) => `${q.unasked || "답하지 않음"}: ${q.text}`),
        ...(aug.proposals || []).map((p) => `해석 확인 전: ${p.slot || p.qid} ← 「${p.quote || ""}」`), ...(aug.analysis_note ? [`AI 분석: ${aug.analysis_note}`] : [])]],
    ["허가서에서 고친 칸", `${permitEd.length}개 · 원본 파일은 그대로`, go(2, () => setView("list")), 0,
      permitEd.map(([, f]) => `${f.name}: ${show(f, f.original)} → ${show(f, f.value)}`)],
    ...(permitBad.length || planBad.length ? [["형식이 맞지 않는 칸", `${permitBad.length + planBad.length}개 (고치거나, 그대로 두면 안전팀이 확인)`,
      permitBad.length ? go(2, () => { setView("list"); focusField(permitBad[0][0]); })
        : go(3, () => { showDoc(planBad[0][0] + 1); setView("list"); focusField(planBad[0][2]); }), 1,
      [...permitBad.map(([, f]) => `허가서 ${f.name}: ${show(f, f.value)} (${TYPE_KO[f.type]})`), ...planBad.map(([i, f]) => `${i + 1}번 계획서 ${f.name}: ${show(f, f.value)} (${TYPE_KO[f.type]})`)]]] : []),
    ...(() => {
      if (!st.ck) return [["위험 체크리스트", "아직 열지 않음", go(4), 1, []]];
      const c = ckCount(), all = st.ck.permits.flatMap((P) => P.items);
      // QA #23: the three answers on one line, what is left on its own line under them
      return [["위험 체크리스트", [`해당 ${c.yes} · 안전팀 확인 ${c.check} · 해당 없음 ${c.no}`, c.left ? `확인 안 함 ${c.left}개 (위 숫자에 포함)` : ""],
        go(4), c.left || c.check, [...all.filter((it) => !it.touched).map((it) => `확인 안 함: ${it.title} (croScan: ${CK_STATE[it.state]})`),
          ...all.filter((it) => it.touched && it.state === "check").map((it) => `안전팀 확인: ${it.title}`)]]];
    })(),
  ];
  rows.forEach(([k, v, act, warn, lines], ri) => {
    const wrap = el("div", "sum-row" + (warn ? " warn" : ""));
    const dd = el("dd", "sum-val");
    if (Array.isArray(v)) { dd.appendChild(el("span", "sum-line", v[0])); if (v[1]) dd.appendChild(el("span", "sum-line left", v[1])); }
    else dd.appendChild(el("span", "", v));
    wrap.append(el("dt", "", k), dd);
    const b = el("button", "btn small ghost", "바꾸기"); b.type = "button";
    b.setAttribute("aria-label", `${k} 바꾸기`); b.onclick = act;
    const dd2 = el("dd", "sum-act"); dd2.appendChild(b); wrap.appendChild(dd2);
    if (lines.length) {
      const more = el("dd", "sum-more"); more.id = `sum-more-${ri}`; more.hidden = !warn;
      const ul = el("ul"); lines.forEach((t, i) => { const li = el("li", i >= 3 && lines.length > 5 ? "extra" : "", t); li.hidden = i >= 3 && lines.length > 5; ul.appendChild(li); }); more.appendChild(ul);
      if (lines.length > 5) {
        const all = el("button", "linkbtn", `${lines.length}건 모두 보기`); all.type = "button";
        all.onclick = () => { const open = all.dataset.open !== "1"; ul.querySelectorAll("li.extra").forEach((li) => { li.hidden = !open; }); all.dataset.open = open ? "1" : ""; all.textContent = open ? "3건만 보기" : `${lines.length}건 모두 보기`; };
        more.appendChild(all);
      }
      const t = el("button", "linkbtn", warn ? "접기" : "자세히"); t.type = "button";
      t.setAttribute("aria-expanded", String(!more.hidden)); t.setAttribute("aria-controls", more.id);
      t.onclick = () => { more.hidden = !more.hidden; t.textContent = more.hidden ? "자세히" : "접기"; t.setAttribute("aria-expanded", String(!more.hidden)); };
      dd.appendChild(t); wrap.appendChild(more);
    }
    dl.appendChild(wrap);
  });
  $("#wpdl-all").hidden = !(st.wp && st.wp.token && planEd.length);
  $("#sub-docs").hidden = !exported();                   // the documents shown are of what was submitted
  $("#sub-msg").textContent = exported() ? "지금 내용으로 이미 제출했습니다 (시연)." : st.exportedRev >= 0 ? "제출한 뒤에 바뀐 내용이 있습니다. 다시 제출해 주세요." : "";
  if ($("#wpsave").classList.contains("bad")) $("#sub-msg").textContent += " 작업계획서에서 고친 값이 아직 서버에 저장되지 않았습니다. 1단계에서 「다시 저장」을 눌러 주세요.";
}
$("#sub-back").onclick = () => goStep(4);
$("#back-sum").onclick = () => goStep(ckDone() ? 5 : 4);
$("#wpdl-all").onclick = () => downloadPlans("all.pdf");

// ---------------------------------------------------------------- 제출 직전 확인 창 (팀장 요청 2026-10-31)
// Only the key items a foreman often gets wrong, with the values as they are submitted: the work time and place from the
// review (st.aug.effective, the same the server keeps), the form values from the 반영본 plan (st.aug.reflect: the fills,
// and what did not fit and goes to the 별지), the answers as they stand after a correction (C5 「추가로 적은 내용이
// 맞음」 withdraws the earlier answer). What is still open is shown first.
// Codex review 2026-11-01: what the window showed is what is sent — a change after it opened (a review coming back, the
// answers changed on another screen) shows the window again before anything is sent; nothing is cut that can change a
// risk (times, counts, IDs); a choice keeps its meaning beside what was typed with it.
const PS_KIND = { "화기": "hot", "밀폐": "confined", "고소": "height", "중량물인양": "lifting", "정전·LOTO": "loto" };
const PS_EXTRA = {                                     // [row title, question items whose answers it shows]
  hot: [["절단·용접 방법·가스", ["H2", "D3"]], ["분리물 지지·회수", ["H3"]], ["상하 위치·높이", ["L3"]], ["작업 중 통제 범위", ["L6"]]],
  loto: [["차단·복구·시험 시각", ["LO3", "D4"]], ["접근 위치(거더·상부)", ["LO4"]], ["통전 상태 측정", ["LO5"]], ["같은 주행로·다른 팀", ["LO6"]]],
  confined: [["진입·내부 작업", ["CF1"]], ["가스·공기 계통", ["CF2", "D5"]], ["환기·송기·조명 전원", ["CF3"]], ["밀폐 안 화기", ["CF4"]]],
  lifting: [["크레인·이동 경로", ["LI1", "D2", "L5"]], ["중량·정격하중", ["C4"]], ["블록 안·위 작업·부착물", ["LI2"]], ["크레인 정비·같은 주행로", ["LI3"]]],
  height: [["높이·위치", ["L3"]], ["러그 수량·절단 방법", ["HT1"]], ["회수·하부 통제", ["HT2"]]],
};
// any kind: the night or shift support (T8, asked for hot work at night) and what is kept during a wait or stop (T9)
const PS_COMMON = [["야간·교대 지원·인계", ["T8"]], ["대기·중단 중 유지", ["T9"]], ["수전구역 통전·시운전", ["D6"]],
  ["압력시험 매체·가압·감압", ["D7"]]];
const PS_INPUT_LABEL = /직접|기타|입력|추가로 적은 내용이 맞음/;      // a choice that only opens a text box says nothing itself
function preSubmitView(aug, fields, answers, ckLeft, pending) {
  const NOVAL = /^\s*(?:모름|몰라요?|미정|미상|확인\s*중|나중에|-|—|\?+)\s*$/;
  const cut = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);
  const md = (d) => `${+d.slice(5, 7)}/${+d.slice(8, 10)}`;
  const nextDay = (d) => { const t = new Date(d + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() + 1); return t.toISOString().slice(0, 10); };
  // days with the same times one after another on one line
  const runsOf = (wins) => {
    const runs = [];
    for (const d of Object.keys(wins || {}).sort()) {
      const w = (wins[d] || []).join(", "), last = runs[runs.length - 1];
      if (!w) continue;
      if (last && last.w === w && nextDay(last.to) === d) last.to = d; else runs.push({ from: d, to: d, w });
    }
    return runs.map((r) => (r.from === r.to ? `${md(r.from)} ${r.w}` : `${md(r.from)}~${md(r.to)} 매일 ${r.w}`)).join(" · ");
  };
  const perms = (aug && aug.effective) || [], out = { open: [], permits: [], none: !perms.length };
  for (const P of perms) {
    const pno = P.permit_no, kind = PS_KIND[P.label] || "", R = (aug.reflect || {})[pno] || {};
    // a form value as submitted: the 반영본 fill, else what did not fit (written on the 별지), else the field now
    const fv = (base) => {
      const x = (R.fills || []).find((y) => y.base === base);
      if (x) return { v: String(x.final || "").trim(), note: "" };
      const f = fields[`p${P.no}.${base}`], e = f && f.name && (R.extra || []).find((y) => y[0] === f.name);
      if (e) return { v: String(e[1]).replace(/\s*\([^()]*\)\s*$/, "").trim(), note: "별지에 기록" };
      return { v: f ? String(f.value == null ? "" : f.value).trim() : "", note: "" };
    };
    const item = (qid) => String(qid).split(":")[0];
    const mine = (qid) => (String(qid).split(":")[1] || "").split(">")[0] === pno;
    const rx = (codes) => new RegExp(`^(?:${codes.join("|")})(?:\\.|$)`);
    const mineAll = (answers || []).filter((a) => mine(a.qid));
    const gone = new Set(mineAll.filter((a) => item(a.qid).startsWith("C6.") && a.choice === "doc")
      .map((a) => `${item(a.qid).slice(3).split("~")[0]}:${String(a.qid).split(":").slice(1).join(":")}`));
    const own = mineAll.filter((a) => !gone.has(a.qid));
    const text = (a) => String(a.read || a.value || "").trim();
    const unknown = (a) => a.choice === "unknown" || NOVAL.test(text(a));
    // the answers to these items as they stand: an answer a later C5 「추가로 적은 내용이 맞음」 withdrew is replaced by it,
    // a C5 「모름」 leaves the two apart unresolved
    const said = (codes) => {
      const m = new Map();
      for (const a of own) {
        const it = item(a.qid);
        if (!rx(codes).test(it)) continue;
        const c = it.startsWith("C5.") ? null : own.find((y) => item(y.qid) === `C5.${it}`);
        if (c && c.choice === "free") m.set(c.qid, { ...c, fixed: true });
        else if (c && unknown(c)) m.set(c.qid, c);
        else m.set(a.qid, a);
      }
      return [...m.values()];
    };
    const label = (a) => (((a.q || {}).choices || []).find((c) => c.id === a.choice) || {}).label || "";
    const valOf = (a) => {
      const t = text(a), l = label(a), lab = l && !PS_INPUT_LABEL.test(l) && !t.includes(l) ? l : "";
      return [lab, t].filter(Boolean).join(" · ") + (a.fixed ? " (정정)" : "");
    };
    const known = (codes) => said(codes).filter((a) => !unknown(a)).map(valOf).filter(Boolean);
    // an answer to these items taken back (C6 「서류가 맞음」): the document stands, said so
    const back = (codes) => ([...gone].some((g) => rx(codes).test(g.split(":")[0])) ? "앞 답 철회 · 서류 값을 따름" : "");
    // 「모름」 answered, a question about it not answered, or an earlier answer and a later message that disagree
    const gap = (codes) => {
      if (said(codes).some(unknown)) return "모름";
      const qs = (aug.questions || []).filter((q) => q.permit_no === pno);
      if (qs.some((q) => rx(codes).test(q.item || item(q.qid)))) return "답하지 않음";
      if (qs.some((q) => rx(codes).test(String(q.item || item(q.qid)).replace(/^C5\./, "")))) return "앞 답과 추가 전달이 다름 (답하지 않음)";
      return "";
    };
    const rows = [];
    const row = (k, v, warn, flag, note) => rows.push({ k, v: v || "(비어 있음)", warn: warn || "", flag: flag || "", note: note || "" });

    // 1. 작업일·작업시간: the times of the work itself (the residual-hazard watch apart), a stage written apart from the whole
    const wins = P.windows_work || P.windows || {}, tv = runsOf(wins);
    const src = P.windows_src === "원본" ? "허가서에 적힌 시간" : P.windows_src || "";
    const stretched = !P.windows_work && P.residual ? "마지막 시각은 잔불·잔류 확인 끝까지 포함" : "";
    row("작업일·작업시간", tv, gap(["T[0-35-7]", "A[1-3]"]) || (tv ? "" : "비어 있음"), /익일/.test(tv) ? "다음 날까지 이어짐" : "",
      tv ? [src, stretched].filter(Boolean).join(" · ") : "");
    const WS = P.windows_stage || {}, move = runsOf(WS.move), written = runsOf(WS.written);
    if (move) row("인양 이동 단계", move, "", "", "블록이 실제 움직이는 시간");
    if (written && P.time_meaning === "full") row("적은 시간(일부 단계)", written, "", "", "위 작업시간이 전체");
    // the end of the ember check (T4, A5.T4) is its own line: 「모름」 to it is not 「작업시간을 모름」 (staging check 2026-11-01)
    const rg = gap(["T4", "A5\.T4"]), ra = P.residual_at || {};
    const rv = Object.keys(ra).length > 1 && new Set(Object.values(ra)).size > 1 ? Object.entries(ra).map(([d, x]) => `${md(d)} ${x}`).join(" · ") : P.residual;
    if ((P.residual && P.windows_work) || rg) row("잔불·잔류 확인 끝", rv ? `${rv}까지` : "", rg, "", "작업시간과 따로");

    // 2. 작업 위치: BAY·칼럼·블록
    const pl = P.place || {}, ptext = String(pl.text || "").trim() || fv("location").v;
    // block numbers as the real form writes them: E41P, B11, E170, B-01 (one letter); cranes and panels have more letters
    const blocks = (P.targets || []).filter((t) => /^[A-Z]-?\d{2,3}[A-Z]?$/.test(t) && !ptext.includes(t));
    const pv = [ptext, blocks.length ? `블록 ${blocks.join(", ")}` : ""].filter(Boolean).join(" · ");
    const pw = !ptext ? "비어 있음" : pl.whole ? "" : pl.level === "L0" ? "부서·팀 이름처럼 보임 (BAY·칼럼 없음)"
      : !(pl.bays || []).length ? "BAY·칼럼 없음" : !pl.cols ? "칼럼 없음" : "";
    row("작업 위치", pv, gap(["L1", "L7", "L2"]) || pw, "", pl.whole ? "작업장 전체" : "");

    // 3. 작업 내용 · 허가 종류 (작업내용, else 작업내용 상세)
    const J = fv("job"), JD = fv("job_detail"), job = J.v || JD.v;
    const detail = J.v && JD.v && JD.v !== J.v ? ` / 상세: ${JD.v}` : "";
    rows.push({ k: "작업 내용", v: `${P.label} 허가서 · ${job || "(작업내용 비어 있음)"}${detail}`,
      warn: gap(["B1\\.job", "D1", "LO1"]) || (job ? "" : "비어 있음"), flag: "", note: [J.note, JD.note].filter(Boolean)[0] || "" });
    // the repair scope is its own line: 「모름」 to it is not 「작업 내용을 모름」 (staging check 2026-10-31)
    const scope = known(["H1"]), sg = gap(["H1"]);
    if (scope.length || sg || back(["H1"])) row("작업 범위(보수·교체)", scope.join(" · ") || back(["H1"]), sg);

    // 4. 작업 인원 (감시인은 답에 있을 때만)
    const W = fv("workers"), wv = W.v, watch = known(["W1"]);
    const wd = [wv ? (/^\d+$/.test(wv) ? `${wv}명` : wv) : "", ...watch].filter(Boolean).join(" · ");
    row("작업 인원", wv ? wd : watch.length ? `작업 인원 비어 있음 · ${watch.join(" · ")}` : "",
      gap(["B1\\.workers", "B2\\.workers"]) || (wv ? "" : "비어 있음"), "", W.note);

    // 5. 병행작업: 있음(무엇) / 없음 / 미확인
    const C = fv("concurrent"), cv = C.v.toUpperCase(), cc = ["B3", "C5\\.B3", "C5\\.concurrent"];
    const what = said(cc).filter((a) => a.choice !== "no" && !unknown(a)).map(text).filter(Boolean);
    const yes = /^(?:Y|YES|O|유|있음)$/.test(cv), no = /^(?:N|NO|X|무|없음)$/.test(cv);
    row("병행작업", yes ? `있음 · ${what.length ? what.join(" · ") : "무엇인지 적지 않음"}` : no ? "없음" : cv || "미확인",
      gap(cc) || (yes || no || cv ? "" : "미확인"), "", C.note);

    // 6. what this kind of work most often gets wrong: answered, or asked and left open
    for (const [k, codes] of [...(PS_EXTRA[kind] || []), ...PS_COMMON]) {
      const vals = known(codes);
      for (const [it, f] of Object.entries(P.facts || {})) {
        const v = String((f && f.value) || "").trim();
        if (rx(codes).test(it) && v && !vals.some((x) => x.includes(v))) vals.push(f.src === "doc" ? `${v} (서류)` : v);
      }
      if (!vals.length && back(codes)) vals.push(back(codes));
      if (kind === "lifting" && k.startsWith("크레인") && (P.cranes || []).length && !vals.some((v) => P.cranes.some((c) => v.includes(c)))) vals.unshift(`크레인 ${P.cranes.join(", ")}`);
      if (kind === "lifting" && k.startsWith("중량")) {
        const lw = fv("load_weight").v, swl = fv("crane_swl").v;
        if (swl) vals.unshift(`정격 ${swl}${/t$/i.test(swl) ? "" : "t"}`);
        if (lw) vals.unshift(`중량 ${lw}${/t$/i.test(lw) ? "" : "t"}`);
      }
      if ((kind === "height" || kind === "hot") && k.includes("높이") && P.height) vals.unshift(`높이 ${P.height}m`);
      const g = gap(codes);
      if (vals.length || g) row(k, vals.join(" · "), g);
    }
    const tag = perms.length > 1 ? `${pno} ` : "";
    for (const r of rows) if (r.warn) out.open.push(`${tag}${r.k}: ${r.warn}`);
    // what the 추가검토서 already sends to the safety team to check (문서와 다름, 사본 차이 …): seen before sending
    const pend = R.pending || [];
    if (pend.length) out.open.push(`${tag}안전팀 확인으로 넘어가는 것 ${pend.length}개: ` + pend.slice(0, 3).map((p) => cut(`${p[0]} — ${p[1]}`, 80)).join(" / ") + (pend.length > 3 ? ` 외 ${pend.length - 3}개` : ""));
    out.permits.push({ title: `${P.label} 허가서 · 승인번호 ${pno}`, rows });
  }
  if (ckLeft > 0) out.open.push(`위험 체크리스트: 확인 안 함 ${ckLeft}개`);
  if (pending) out.open.unshift("고친 값을 다시 살펴보는 중입니다. 끝나면 이 창이 새 값으로 바뀝니다");
  return out;
}
// what the window showed, to compare with what would be sent (the checklist count apart: sendFinal checks it itself)
const psPrint = (v) => JSON.stringify([v.permits, v.open.filter((t) => !t.startsWith("위험 체크리스트"))]);
const psNow = () => preSubmitView(st.aug, st.doc.fields, st.answers, ckCount().left, !!st.reviewPending);
// changed: opened again because something changed; said only when what it shows did change
function openPreSubmit(changed) {
  const v = psNow(), print = psPrint(v), was = st.psSeen;
  const wait = !!st.reviewPending || v.none;
  st.psSeen = wait ? null : print;
  const body = $("#ps-body"); body.innerHTML = "";
  if (v.none) body.appendChild(el("p", "ps-open", "검토 내용을 아직 받지 못해 핵심 정보를 모으지 못했습니다. 잠시 뒤 다시 눌러 주세요."));
  else if (v.open.length) {
    const box = el("div", "ps-open");
    box.appendChild(el("b", "", `먼저 확인할 것 ${v.open.length}가지 (모름·미확인·비어 있음·안전팀 확인)`));
    const ul = el("ul"); v.open.forEach((t) => ul.appendChild(el("li", "", t))); box.appendChild(ul);
    body.appendChild(box);
  } else body.appendChild(el("p", "ps-clear", "「모름」이나 빈칸으로 남은 핵심 항목은 찾지 못했습니다. 아래 값이 맞는지 한 번 더 봐 주세요."));
  for (const P of v.permits) {
    const sec = el("section", "ps-permit");
    sec.appendChild(el("h3", "", P.title));
    const dl = el("dl", "ps-list");
    for (const r of P.rows) {
      const w = el("div", r.warn ? "warn" : ""), dd = el("dd");
      dd.appendChild(el("span", "", r.v));
      if (r.note) dd.appendChild(el("span", "ps-note", r.note));
      for (const f of [r.warn, r.flag]) if (f) dd.appendChild(el("span", "ps-flag", f));
      w.append(el("dt", "", r.k), dd); dl.appendChild(w);
    }
    sec.appendChild(dl); body.appendChild(sec);
  }
  const ok = $("#ps-ok");
  ok.disabled = wait;
  ok.title = wait ? "검토가 끝나면 누를 수 있습니다" : "";
  if (changed && was && print !== was) toast("내용이 바뀌어 확인 창을 다시 보여드립니다. 바뀐 값을 확인해 주세요.");
  if ($("#presub").hidden) openDialog("presub");
  body.scrollTop = 0;
}
$("#ps-ok").onclick = () => {
  if (st.submitting) return;
  const v = psNow();
  if (st.reviewPending || v.none || psPrint(v) !== st.psSeen) { openPreSubmit(true); return; }
  closeDialogs(); sendFinal();
};
// 「안전팀에 제출」: the key items first (one added step); 「확인하고 제출」 submits as before
$("#sendfinal").onclick = () => { if (!st.doc || !sameSource() || !st.ck || st.submitting) return; st.psSeen = null; openPreSubmit(); };
// 제출본: original pages + 추가검토서 as one PDF (the original pages are not changed)
// one submission at a time (the button can be pressed again while one is on its way)
async function sendFinal() {
  if (!st.doc || !sameSource() || !st.ck || st.submitting) return;
  st.submitting = true;
  try { await sendFinalOnce(); } finally { st.submitting = false; }
}
async function sendFinalOnce() {
  // the checklist is drafted again from the permit and the answers as they are now; an item whose basis changed
  // waits for the 작업반장 again
  if (!(await openChecklist(true))) {                // not checked against what is there now: not sent
    $("#sub-msg").textContent = `위험 체크리스트를 지금 내용으로 다시 확인하지 못해 제출하지 않았습니다: ${st.ckError || "연결 오류"}. 다시 눌러 주세요.`;
    return;
  }
  const changed = st.ck.permits.flatMap((P) => P.items).filter((it) => it.changed && !it.touched);
  if (changed.length) {
    toast(`허가서나 답이 바뀌어 위험 체크리스트 ${changed.length}개 항목을 다시 확인해야 합니다.`);
    goStep(4); document.getElementById(`ck-${changed[0].id}`)?.scrollIntoView({ block: "center" }); return;
  }
  if (!sameSource() || !plansOk() || !ckDone()) { toast("바뀐 내용을 다시 확인해 주세요"); goStep(4); return; }
  const c = ckCount();
  if (c.left) { toast(`위험 체크리스트에 확인하지 않은 항목이 ${c.left}개 있습니다. 모두 확인한 뒤 제출합니다.`); goStep(4); return; }
  // the plan edits go first, every time (also an edit put back to the original): the 작업계획서 PDF is drawn from the saved edits
  if (st.wp && st.wp.token && !(await savePlans())) {
    $("#sub-msg").textContent = "작업계획서에서 고친 값을 저장하지 못해 제출하지 않았습니다. 연결을 확인하고 다시 눌러 주세요."; return;
  }
  // design §2.3: the server keeps the review as it is now (a snapshot, made once); the documents are drawn from it.
  // Demo: nothing goes to 전산·결재.
  let sub;
  try {
    // Codex 2026-11-01: what is sent is what the window showed (the checklist drawn again, a review back meanwhile)
    if (st.psSeen) {
      await refreshAug();
      if (psPrint(psNow()) !== st.psSeen) { openPreSubmit(true); return; }
    }
    const r = await fetch("/api/submissions", { method: "POST", body: submitForm() });
    const j = await r.json().catch(() => ({}));
    // the answers changed on another screen: taken from the server and shown again, not sent unseen
    if ((r.status === 409 || r.status === 428) && j.detail && ["stale_revision", "revision_required"].includes(j.detail.code)) {
      await serverState(); await refreshAug(); openPreSubmit(true); return;
    }
    if (r.status === 409 && j.detail && /^checklist_/.test(j.detail.code || "")) { toast(j.detail.message); await openChecklist(true); goStep(4); return; }
    if (!r.ok) throw new Error((j.detail && j.detail.message) || (typeof j.detail === "string" ? j.detail : "") || `서버 오류 ${r.status}`);
    sub = j;
  } catch (e) { $("#sub-msg").textContent = `제출하지 못했습니다: ${e.message}. 다시 눌러 주세요.`; return; }
  st.submission = { id: sub.id, at: sub.created, summary: sub.summary };
  st.exportedRev = st.rev; saveDraft();
  const ck = ckCount(), plans = st.wp ? st.wp.plans.length : 0;
  const docs = [
    ["허가서(원본+추가검토서)", `원본 ${st.doc.pages.length}쪽 + 추가검토서 · 답 ${st.answers.length}건`, "_추가검토", permitPdf],
    ...(st.wp && st.wp.token ? [["작업계획서", `${plans}건 · 확인 ${st.checked.size}건`, "_작업계획서", () => fetchPdf(`/api/submissions/${encodeURIComponent(sub.id)}/plans.pdf`)]] : []),
    ["위험 체크리스트", `해당 ${ck.yes} · 안전팀 확인 ${ck.check} · 해당 없음 ${ck.no}`, "_위험체크리스트", checklistPdf],
  ];
  $("#sub-id").textContent = `${subWhere(sub.manager)} · 제출본 ${sub.id.slice(0, 6)} · ${kstHM(sub.created)}`
    + ` · 담당 확인 ${sub.summary.unresolved}건 (시연: 전산·결재로 보내지 않음)`;
  $("#doc-list").innerHTML = "";
  for (const [title, note, suffix, make] of docs) {
    const li = el("li", "doc");
    li.innerHTML = `${icon("i-pdf")}<span><b>${esc(title)}</b><small>${esc(note)}</small></span>`;
    const b = el("button", "btn small", ""); b.type = "button"; b.innerHTML = `${icon("i-download")}PDF`;
    b.setAttribute("aria-label", `${title} PDF 받기`);
    b.onclick = async () => {
      const label = b.innerHTML; b.disabled = true; b.textContent = "만드는 중…";
      try { saveBlob(await make(), st.src.file.name.replace(/\.pdf$/i, "") + suffix + ".pdf"); }
      catch (e) { toast(`PDF를 만들지 못했습니다: ${e.message}`); }
      b.disabled = false; b.innerHTML = label;
    };
    li.appendChild(b); $("#doc-list").appendChild(li);
  }
  $("#sub-docs").hidden = false;
  $("#sub-msg").textContent = "";
  toast(sub.manager && !sub.manager.listed ? "제출본을 저장했습니다 (시연). 안전관리자 작업 목록에는 연결되지 않았습니다." : "안전팀에 제출했습니다 (시연).");
  paintStepper();
}
// Codex A6: where a submission shows on the safety manager's side (the server says it; nothing is claimed beyond it)
function subWhere(m) {
  if (m === undefined) return "안전팀에 제출했습니다";
  if (!m) return "제출본을 저장했습니다 · 안전관리자 화면에 연결할 작업일 자료가 없습니다";
  return m.listed ? `안전팀에 제출했습니다 · 안전관리자 화면 ${m.day} 작업 목록에 연결`
    : `제출본을 저장했습니다 · 안전관리자 화면의 ${m.day} 작업 목록에는 연결되지 않아 「이 날 작업 목록에 없는 제출」로 따로 보입니다`;
}
async function fetchPdf(url, init) {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `서버 오류 ${r.status}`);
  return r.blob();
}
// the permit and what the review made of it, as the session has it now
function sessionForm() {
  const fd = new FormData();
  fd.append("file", st.src.file);
  fd.append("payload", JSON.stringify({ fields: st.doc.fields, answers: typedAnswers(), session_id: st.sid || "", expected_revision: st.srev ?? null }));
  return fd;
}
// what is submitted: the permit file and the review (the server takes the answers from the session)
function submitForm() {
  const fd = new FormData();
  fd.append("file", st.src.file);
  fd.append("payload", JSON.stringify({ fields: st.doc.fields, session_id: st.sid || "", expected_revision: st.srev ?? null, checklist: ckPayload(),
    plans: st.wp && st.wp.token ? { token: st.wp.token, checked: [...st.checked] } : {} }));
  return fd;
}
// a server time (seconds) as HH:MM in Korea, whatever the device's zone
const kstHM = (sec) => new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(sec * 1000));
// the documents of the submission: drawn from the snapshot (the same every time, whatever the session does later)
function permitPdf() { return fetchPdf(`/api/submissions/${encodeURIComponent(st.submission.id)}/permit.pdf`); }
function checklistPdf() { return fetchPdf(`/api/submissions/${encodeURIComponent(st.submission.id)}/checklist.pdf`); }
function saveBlob(blob, name) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
$("#newpdf").onclick = async () => {
  // a plan edit still waiting for its save must reach the server before the work is cleared
  if (st.wp && st.wp.token && Object.keys(planEdits()).length && !(await savePlans())) return;   // failed: keep everything
  if (!exported() && !confirm("아직 안전팀에 제출하지 않았습니다. 지금 작업을 지우고 새 허가서를 검토할까요?")) return;
  st.doc = null; st.aug = null; st.answers = []; st.wp = null; st.docs = null; st.di = 0; st.reviewed = false; st.ck = null; st.submission = null;
  // the plans are the first step now: everything of the last work goes, the plans' state and 임시저장 links too
  st.checked = new Set(); st.planOpen = null; st.draftPlans = null; st.draftCk = null; st.fromSummary = false;
  st.wpSaved = null; st.wpSaving = false; st.src = null; $("#plan-q").value = ""; $("#wpsave").classList.remove("bad");
  $("#sub-docs").hidden = true;
  clearFile(); pick.plans = []; goStep(3);
};
// leaving with unsaved work asks first
window.addEventListener("beforeunload", (e) => { if ((st.doc && !exported()) || (!st.doc && st.wp)) { e.preventDefault(); e.returnValue = ""; } });

// ---------------------------------------------------------------- 4단계: 위험 체크리스트 (작업반장, 작업 전날)
// croScan drafts it on the server from the permit alone: its values and the answers (server/checklist.py); the 작업반장 taps
// every item once (해당 / 해당 없음 / 안전팀 확인) and picks the safety measures to prepare. An item the 작업반장 has
// touched keeps its choice when croScan drafts again (after a permit edit or a new answer).
const CK_STATE = { yes: "해당", no: "해당 없음", check: "안전팀 확인" };
// design §7: an item that is 해당 needs its safety measures confirmed too (an item he wrote himself has his own)
const ckNeedCtl = (it) => it.state === "yes" && !it.ctl_touched && !String(it.id).startsWith("U");
// design §7 table: what the AI's reading of a base item means next to croScan's proposal (it never changes the state)
function ckMarkText(it, m) {
  const q = `「${m.quote}」(${m.src || "서류"})`;
  if (m.m === "support") return it.auto === "yes" ? `같은 근거 ${q}`
    : it.auto === "no" ? `상충: croScan 제안은 「해당 없음」이지만 작업 내용 ${q}에 해당 근거가 있습니다. 해당 여부를 다시 골라 주세요.`
    : `해당 근거 ${q}가 있습니다. 해당이면 「해당」을 골라 주세요.`;
  return it.auto === "yes" ? `상충: croScan 제안은 「해당」이지만 ${q}는 하지 않는다는 말입니다. 누구의 어떤 작업인지 확인해 판단해 주세요. 「해당」이 기본입니다.`
    : `하지 않는다는 말 ${q}이 있습니다. 누구의 어떤 작업인지 확인해 판단해 주세요.`;
}
const ckMark = (it) => (st.ckAi && st.ckAi.marks && st.ckAi.marks[it.id]) || null;
function ckCount() {
  const all = st.ck ? st.ck.permits.flatMap((P) => P.items) : [];
  const n = { yes: 0, no: 0, check: 0, left: 0, all: all.length };
  for (const it of all) { n[it.state]++; if (!it.touched || ckNeedCtl(it)) n.left++; }
  return n;
}
// what is kept (draft) and sent (package): the 작업반장's choices, not croScan's texts
function ckPayload(small) {
  return { permits: st.ck.permits.map((P) => ({ permit_no: P.permit_no, kind: P.kind, items: P.items.map((it) => ({
    id: it.id, state: it.state, auto: it.auto, basis: it.basis, basis_ctl: it.basis_ctl, touched: !!it.touched, ctl_touched: !!it.ctl_touched,
    ...(it.ai_ack ? { ai_ack: it.ai_ack } : {}), ...(it.id.startsWith("A:") ? { quote: it.quote || "" } : {}), memo: it.memo || "",
    controls: it.controls.filter((k) => k.on).map((k) => small && !k.id.startsWith("u") ? { id: k.id } : { id: k.id, text: k.text, on: true }),
    ...(it.id.startsWith("U") ? { title: it.title } : {}), ...(small ? {} : { reasons: it.reasons, sources: it.sources || [], title: it.title }) })) })) };
}
let ckSeq = 0;
async function openChecklist(quiet) {
  const seq = ++ckSeq, source = st.doc;
  let basis = ckBasis();
  st.ckLoading = true; st.ckError = "";
  if (!st.ck && !quiet) $("#ck-list").innerHTML = `<p class="hint">croScan이 체크리스트를 채우는 중…</p>`;
  $("#ck-back-sum")?.remove();
  if (st.ck) { renderCkBar(); paintStepper(); }
  try {
    // from the permit alone: its values and the answers about it (the 작업계획서 are not a basis)
    const r = await sessionRead(() => ["/api/checklist", { method: "POST", headers: { "Content-Type": "application/json" }, body: (basis = ckBasis()) }]);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error((j.detail && j.detail.message) || j.detail || `서버 오류 ${r.status}`);
    if (!Array.isArray(j.permits) || j.permits.some((P) => !Array.isArray(P.items))) throw new Error("체크리스트 응답을 확인하지 못했습니다");
    if (seq !== ckSeq) return false;
    if (source !== st.doc || basis !== ckBasis()) throw new Error("허가서나 답이 바뀌었습니다. 다시 열어 주세요");
    st.ck = ckMerge(j, st.ck || ckFromDraft(st.draftCk));
    st.draftCk = null; st.ckBasis = basis;
    $("#ck-msg").textContent = "";
  } catch (e) {
    if (seq !== ckSeq) return false;
    st.ckError = e.message;
    $("#ck-msg").textContent = `체크리스트를 채우지 못했습니다: ${e.message}. ` + (st.ck ? "지금 화면의 내용은 그대로입니다." : "다시 열어 주세요.");
    if (!st.ck) $("#ck-list").innerHTML = "";
    return false;
  } finally {
    if (seq === ckSeq) { st.ckLoading = false; if (st.ck) renderCkBar(); paintStepper(); }
  }
  renderChecklist(); paintStepper();
  ckAiLoad();                                        // the AI suggestions below the list (made ahead, or now)
  return true;                                       // drafted from what is there now
}
function ckFromDraft(d) {
  return d ? { permits: d.permits.map((P) => ({ ...P, items: P.items.map((it) => ({ ...it, controls: it.controls.map((k) => ({ ...k, on: true })) })) })) } : null;
}
// the new draft from croScan, with every item the 작업반장 touched kept as it was chosen
function ckMerge(fresh, old) {
  const was = new Map();
  for (const P of (old && old.permits) || []) for (const it of P.items) was.set(`${P.permit_no}|${it.id}`, it);
  for (const P of fresh.permits) {
    P.items = P.items.map((it) => {
      const o = was.get(`${P.permit_no}|${it.id}`);
      if (!o || !o.touched) return o ? { ...it, memo: o.memo || "", ...(o.changed ? { changed: o.changed } : {}) } : it;   // the note and a memo stay until it is confirmed
      const on = new Set(o.controls.filter((k) => k.on).map((k) => k.id));
      const keep = { ...it, memo: o.memo || "", controls: it.controls.map((k) => ({ ...k, on: on.has(k.id) })) };
      // the permit or an answer changed what croScan sees: the earlier choice is not confirmed any more
      if (o.auto && o.auto !== it.auto) return { ...keep, touched: false, changed: `croScan 제안이 「${CK_STATE[o.auto]}」에서 「${CK_STATE[it.auto]}」${pp(CK_STATE[it.auto], "으로", "로")} 바뀌었습니다. 다시 확인해 주세요.` };
      if (o.basis && it.basis && o.basis !== it.basis) return { ...keep, touched: false, changed: "허가서나 답이 바뀌어 이 항목의 근거가 달라졌습니다. 다시 확인해 주세요." };
      const ctlSame = !o.basis_ctl || !it.basis_ctl || o.basis_ctl === it.basis_ctl;
      return { ...keep, state: o.state, touched: true, ai_ack: o.ai_ack, ctl_touched: !!o.ctl_touched && ctlSame,
        ...(!ctlSame && o.ctl_touched && o.state === "yes" ? { changed: "작업 방법·장비가 바뀌어 준비할 안전조치를 다시 확인해 주세요." } : {}) };
    });
    for (const [key, o] of was) if (key.startsWith(P.permit_no + "|") && (o.id.startsWith("U") || o.id.startsWith("A:"))) P.items.push(o);   // added by hand or put in from the AI suggestions
  }
  return fresh;
}
function ckChanged() { bump(); renderCkBar(); paintStepper(); }
function renderCkBar() {
  const c = ckCount();
  $("#ck-next").disabled = !ckDone();
  $("#ck-need").textContent = !st.ck ? "" : st.ckLoading ? "체크리스트를 지금 내용으로 다시 확인하는 중입니다." : st.ckError ? "체크리스트를 다시 확인하지 못했습니다. 다시 열어 주세요." : st.ckBasis !== ckBasis() ? "허가서나 답이 바뀌었습니다. 이 단계를 다시 열면 바뀐 내용으로 다시 채웁니다." : c.left ? `확인할 위험요인 ${c.left}개가 남았습니다. 모두 확인하면 제출 확인으로 넘어갈 수 있습니다.` : "";
  $("#ck-bar").innerHTML = `<span class="ck-prog"><b>${c.all - c.left}</b> / ${c.all} 확인 완료</span>`
    + `<span class="ck-n yes">해당 ${c.yes}</span><span class="ck-n no">해당 없음 ${c.no}</span><span class="ck-n check">안전팀 확인 ${c.check}</span>`
    + `<span class="progress ck-progress" aria-hidden="true"><b style="width:${c.all ? (c.all - c.left) / c.all * 100 : 0}%"></b></span>`;
}
function renderChecklist() {
  const box = $("#ck-list"), had = box.contains(document.activeElement) ? document.activeElement.dataset.ckFocus : null;
  box.innerHTML = "";
  const many = st.ck.permits.length > 1;
  for (const P of st.ck.permits) {
    if (many) box.appendChild(el("h2", "ck-permit", `${P.label} · 승인번호 ${P.permit_no}`));
    // QA #21: what belongs to this work only and what every work shares are two framed parts, each with its own head
    let no = 0;                // QA #90: 01, 02, … through both groups of this permit (as in the PDF)
    for (const [cls, title, sub, items] of [["own", `${P.label} 작업 위험요인`, "이 허가서의 작업 유형에서 확인할 위험요인입니다", P.items.filter((it) => !it.common)],
                                           ["common", "모든 작업 공통", "작업 종류와 관계없이 해당 여부를 확인할 위험요인입니다", P.items.filter((it) => it.common)]]) {
      if (!items.length) continue;
      const sec = el("section", `ck-sec ${cls}`), hid = `ckh-${cls}-${P.permit_no}`.replace(/[^\w-]/g, "_");
      sec.setAttribute("aria-labelledby", hid);
      const h = el("h3", "ck-group"); h.id = hid;
      h.append(el("b", "", title), el("span", "ck-gn", `: ${items.length}개`), el("small", "", sub));
      const ul = el("ul", "ck-items");
      for (const it of items) ul.appendChild(ckItem(P, it, ++no));
      if (cls === "own" && !many) for (const row of ckCandRows(P)) ul.appendChild(row);
      sec.append(h, ul); box.appendChild(sec);
    }
    if (many) {
      const add = el("button", "btn small", `${P.label}(${P.permit_no.slice(-4)})에 위험요인 추가`); add.type = "button";
      add.onclick = () => ckAdd(P); box.appendChild(add);
    }
  }
  $("#ck-add").hidden = many;
  if (!st.ck.permits.length) box.appendChild(el("p", "hint", "이 허가서 종류에는 체크리스트가 없습니다."));
  renderCkBar(); renderCkAi();
  if (had) box.querySelector(`[data-ck-focus="${had}"]`)?.focus();
}
function ckItem(P, it, no) {
  const key = `${P.permit_no}|${it.id}`;
  const li = el("li", `ck-item s-${it.state}${it.touched ? " touched" : ""}`);
  li.id = `ck-${it.id}`;
  const head = el("div", "ck-head");
  const tt = el("b", "ck-title"); tt.append(el("span", "ck-no", String(no).padStart(2, "0")), it.title); head.appendChild(tt);
  if (it.id.startsWith("A:")) tt.appendChild(el("span", "ai-chip", "AI 제안 · 채택함"));
  head.appendChild(el("span", "ck-done", !it.touched ? "확인 전" : ckNeedCtl(it) ? "조치 확인 전" : "확인 완료"));
  li.appendChild(head);
  if (it.why) li.appendChild(el("p", "ck-why", it.why));
  if (!String(it.id).startsWith("A:") && !String(it.id).startsWith("U")) li.appendChild(xWhyBtn(() => ({ kind: "checklist", permit: P.permit_no, item: it.id,
    now: { state: it.state, touched: !!it.touched, on: (it.controls || []).filter((k) => k.on).map((k) => k.id) } })));
  if (it.changed && (!it.touched || ckNeedCtl(it))) li.appendChild(el("p", "ck-changed", it.changed));
  const mk = ckMark(it);
  if (mk) {
    const m = el("p", `ck-mark ${mk.m}`);
    m.innerHTML = `<span class="ai-chip">AI 제안</span><span>${esc(ckMarkText(it, mk))}</span>`
      + (mk.controls && mk.controls.length ? `<small>맞는 조치: ${esc(mk.controls.map((id) => (it.controls.find((k) => k.id === id) || {}).text || id).join(" · "))}</small>` : "");
    li.appendChild(m);
  }
  if (it.recheck) {
    const row = el("div", "ck-memo");
    const del = el("button", "btn small ghost", "이 항목 빼기"); del.type = "button";
    del.onclick = () => { P.items = P.items.filter((x) => x !== it); ckChanged(); renderChecklist(); };
    const mine = el("button", "btn small", "반장 항목으로 유지"); mine.type = "button";
    mine.onclick = () => {
      const i = P.items.indexOf(it); if (i < 0) return;
      P.items[i] = { id: `U${Date.now().toString(36)}`, title: it.title, why: "AI 추가 후보였던 항목 · 작업반장이 유지", common: false, state: it.state === "no" ? "yes" : it.state,
        auto: null, touched: false, reasons: [], controls: (it.controls || []).filter((k) => k.on).map((k, j) => ({ id: `u${j + 1}`, text: k.text, on: true })), memo: it.memo || "" };
      ckChanged(); renderChecklist();
    };
    row.append(del, mine); li.appendChild(row);
    return li;
  }
  if (it.reasons && it.reasons.length) {
    const r = el("p", "ck-reason");
    const src = it.sources || [];
    r.innerHTML = `${icon("i-info")}<span>croScan 제안 「${esc(CK_STATE[it.auto] || "")}」 · 근거: ${esc(it.reasons.map((x, i) => src[i] ? `${x} (${src[i]})` : x).join(" · "))}</span>`;
    li.appendChild(r);
  }
  const seg = el("div", "ck-seg"); seg.setAttribute("role", "radiogroup"); seg.setAttribute("aria-label", `${it.title} 해당 여부`);
  for (const s of ["yes", "no", "check"]) {
    // QA #58: 해당 = dark red + warning triangle, 해당 없음 = light blue + check, 안전팀 확인 = yellow + person with "?"
    const b = el("button", `ck-opt o-${s}`); b.type = "button";
    b.innerHTML = `${icon({ yes: "i-alert", no: "i-check", check: "i-user-q" }[s])}<span>${CK_STATE[s]}</span>`;
    b.setAttribute("role", "radio"); b.setAttribute("aria-checked", String(it.state === s)); b.dataset.ckFocus = `${key}|${s}`;
    b.onclick = () => {
      const first = !it.touched;
      it.state = s; it.touched = true; it.changed = null;
      if (mk) it.ai_ack = mk.id;                     // chosen with the AI's reading in view
      if (s === "yes" && first && !it.controls.some((k) => k.on)) it.controls.forEach((k) => { k.on = !!k.pre; });
      ckChanged(); renderChecklist();
    };
    seg.appendChild(b);
  }
  li.appendChild(seg);
  // QA #22: croScan's choice is confirmed with a control of its own (확인 전 → 확인 완료), not by pressing the same choice again.
  // QA #61: it is an empty box to tick (it looked already checked); ticked it says so and can be unticked while the answer is croScan's own
  if (!it.touched || it.state === it.auto) {
    const on = !!it.touched, ok = el("button", `ck-ok${on ? " on" : ""}`); ok.type = "button"; ok.dataset.ckFocus = `${key}|ok`;
    ok.setAttribute("role", "checkbox"); ok.setAttribute("aria-checked", String(on));
    ok.innerHTML = `<span class="ck-box" aria-hidden="true">${on ? icon("i-check") : ""}</span><span class="ck-ok-t"><b>「${esc(CK_STATE[it.state])}」 ${on ? "확인함" : "그대로 확인"}</b>`
      + `<small>${on ? "다시 누르면 확인을 취소합니다" : "croScan이 고른 답이 맞으면 체크해 주세요"}</small></span>`;
    ok.setAttribute("aria-label", `${it.title}: croScan이 고른 「${CK_STATE[it.state]}」 그대로 확인`);
    ok.onclick = () => {
      it.touched = !on; it.changed = null;
      if (mk && !on) it.ai_ack = mk.id;
      ckChanged(); renderChecklist();
      document.querySelector(`[data-ck-focus="${CSS.escape(`${key}|ok`)}"]`)?.focus({ preventScroll: true });
    };
    li.appendChild(ok);
  }
  if (it.state !== "no") {
    const fs = el("fieldset", "ck-ctrls");
    fs.appendChild(el("legend", "", it.state === "yes" ? "준비할 안전조치" : "해당하면 준비할 안전조치"));
    for (const k of it.controls) {
      const lab = el("label", "ck-ctrl");
      const cb = el("input"); cb.type = "checkbox"; cb.checked = !!k.on; cb.dataset.ckFocus = `${key}|c|${k.id}`;
      // a measure ticked or unticked is the measures' confirmation, not the 해당 여부 (design §7)
      cb.onchange = () => { const first = !it.ctl_touched; k.on = cb.checked; it.ctl_touched = true; it.changed = null; ckChanged(); if (first) renderChecklist(); };
      const tx = el("span", "ck-ctext", k.text);
      if (k.permit_key) tx.appendChild(el("small", "ck-day", "당일 허가서 5번에서 확인"));
      lab.append(cb, tx);
      fs.appendChild(lab);
    }
    li.appendChild(fs);
    if (it.state === "yes" && !it.id.startsWith("U")) {
      const on = !!it.ctl_touched, ok = el("button", `ck-ok ck-ctl-ok${on ? " on" : ""}`); ok.type = "button"; ok.dataset.ckFocus = `${key}|ctl`;
      ok.setAttribute("role", "checkbox"); ok.setAttribute("aria-checked", String(on));
      ok.innerHTML = `<span class="ck-box" aria-hidden="true">${on ? icon("i-check") : ""}</span><span class="ck-ok-t"><b>준비할 안전조치 ${on ? "확인함" : "그대로 확인"}</b>`
        + `<small>${on ? "다시 누르면 확인을 취소합니다" : "고른 안전조치가 맞으면 체크해 주세요"}</small></span>`;
      ok.setAttribute("aria-label", `${it.title}: 준비할 안전조치 확인`);
      ok.onclick = () => {
        it.ctl_touched = !on; it.changed = null; ckChanged(); renderChecklist();
        document.querySelector(`[data-ck-focus="${CSS.escape(`${key}|ctl`)}"]`)?.focus({ preventScroll: true });
      };
      li.appendChild(ok);
    }
  }
  const memo = el("div", "ck-memo");
  const ml = el("label", "sr", `${it.title} 메모`); const mid = `ckm-${it.id}-${P.permit_no}`.replace(/[^\w-]/g, "_"); ml.htmlFor = mid;
  const mi = el("input"); mi.id = mid; mi.type = "text"; mi.placeholder = "메모 (선택) 예: 하부 통행로는 2B 쪽으로 돌림"; mi.value = it.memo || ""; mi.maxLength = 200;
  mi.dataset.ckFocus = `${key}|memo`;
  mi.oninput = () => { it.memo = mi.value; ckChanged(); };
  memo.append(ml, mi);
  if (it.id.startsWith("U") || it.id.startsWith("A:")) {
    const del = el("button", "btn small ghost", "이 항목 빼기"); del.type = "button";
    del.onclick = () => { P.items = P.items.filter((x) => x !== it); ckChanged(); renderChecklist(); };
    memo.appendChild(del);
  }
  li.appendChild(memo);
  return li;
}
$("#ck-add").onclick = () => st.ck && st.ck.permits.length === 1 && ckAdd(st.ck.permits[0]);
// 체크리스트 AI 추가 검토 후보 (design §7·§19.1): items of other kinds of work whose words are in this work (server/checkai).
// None is in the checklist until 「넣기」; put in, it is confirmed like the others. Made ahead when the dialogue ends.
let ckAiSeq = 0;
function ckAiAhead() {
  if (!st.sid || !st.doc) return;
  fetch("/api/checklist/ai-suggest", { method: "POST", headers: { "Content-Type": "application/json" }, body: ckBasis() }).catch(() => {});
}
async function ckAiLoad(tries = 0) {
  if (!st.sid || !st.ck || st.ck.permits.length !== 1) { st.ckAi = null; renderCkAi(); return; }
  const seq = ++ckAiSeq;
  st.ckAi = { status: "loading", items: [], kept: {}, marks: {} }; renderChecklist();
  // made again on every try (a revision that moved on: the newest answers), with the AI items he put in
  let sent = null;
  const make = () => {
    sent = ckBasis();
    const keep = st.ck.permits.flatMap((P) => P.items).filter((it) => it.id.startsWith("A:")).map((it) => ({ id: it.id, quote: it.quote || "" }));
    return ["/api/checklist/ai-suggest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...JSON.parse(sent), keep }) }];
  };
  let got;
  try {
    const r = await sessionRead(make);
    const j = await r.json().catch(() => ({}));
    got = r.ok && Array.isArray(j.items) ? { status: j.status, items: j.items, kept: j.kept || {}, marks: j.marks || {} } : { status: "fail", items: [], kept: {}, marks: {} };
  } catch { got = { status: "fail", items: [], kept: {}, marks: {} }; }
  if (seq !== ckAiSeq || !st.ck) return;
  if (sent !== ckBasis()) {                              // the answers moved on while it was asked: asked again, at most twice
    if (tries < 2) { ckAiLoad(tries + 1); return; }
    got = { status: "fail", items: [], kept: {}, marks: {} };
  }
  st.ckAi = got;
  // A11: the submission is out of date only when what he chose, or the items shown to him, changed; an empty or
  // failed result that comes back late (after the submission) changes nothing
  const before = ckSig(st.ck), n = ckTakeAi(st.ck, got);
  if (n.again) toast(`AI가 해당 근거를 찾은 항목 ${n.again}개를 다시 골라야 합니다. 고른 답은 바꾸지 않았습니다.`);
  if (n.re) toast(`작업 내용이 바뀌어 넣은 AI 추가 항목 ${n.re}개를 다시 확인해야 합니다. 체크리스트에서 빼지는 않았습니다.`);
  if (ckSig(st.ck) !== before) ckChanged(); else { renderCkBar(); paintStepper(); }
  renderChecklist();
}
// what the 작업반장 chose and what is shown to him for each item (the submission is made of it)
const ckSig = (ck) => JSON.stringify(ck.permits.map((P) => [P.permit_no, P.items.map((it) => [it.id, it.title, it.state, it.auto, it.basis, it.basis_ctl,
  !!it.touched, !!it.ctl_touched, it.ai_ack || null, it.quote || "", it.memo || "", it.changed || "", it.recheck || "",
  (it.controls || []).map((k) => `${k.id}${k.on ? "+" : ""}`)])]));
// an AI result on the checklist (design §7): the items it asks to choose again, and the AI items he put in as they
// are for the work now -> how many of each
function ckTakeAi(ck, got) {
  // a 「해당 없음」 chosen before the AI found words that the hazard is there: chosen again (design §7 「확인 필요」);
  // the state itself is never changed by the reading
  let again = 0;
  for (const P of ck.permits) for (const it of P.items) {
    const m = got.marks && got.marks[it.id];
    if (m && m.m === "support" && it.state === "no" && it.touched && it.ai_ack !== m.id) {
      it.touched = false; it.changed = `작업 내용 「${m.quote}」(${m.src || "서류"})에 해당 근거가 있습니다. 「해당 없음」이 맞는지 다시 골라 주세요.`; again++;
    }
  }
  // never taken out by a new result: each one he put in, as it is for the work now (server/checkai.recheck)
  let re = 0;
  for (const P of ck.permits) P.items = P.items.map((it) => {
    const k = it.id.startsWith("A:") ? got.kept[it.id] : null;
    if (!k) return it;                                   // not checked this time (a failure): as it is; the submission checks it
    if (!k.ok) {
      if (it.recheck === k.why) return it;
      re++;
      return { ...it, touched: false, recheck: k.why, changed: `근거 「${it.quote || ""}」가 지금 작업 내용과 맞지 않습니다(${k.why}). 「이 항목 빼기」 또는 「반장 항목으로 유지」를 골라 주세요.` };
    }
    if (k.item.basis === it.basis && !it.recheck) return it;
    re++;
    const { spec, kind, origin, ...fresh } = k.item; void spec; void kind; void origin;
    const on = new Set((it.controls || []).filter((c) => c.on).map((c) => c.id));
    return { ...fresh, state: it.state, memo: it.memo || "", controls: fresh.controls.map((c) => ({ ...c, on: on.has(c.id) })), touched: false,
      changed: "작업 내용이 바뀌어 넣은 AI 추가 항목을 다시 확인해 주세요." };
  });
  return { again, re };
}
// design §19.1: an AI candidate is a row shaped like the items at the end of this kind's group, with 「AI 제안」 and
// [채택][제외]; the base items' readings are shown on their own rows (ckMark)
function ckCandRows(P) {
  const A = st.ckAi, out = [];
  if (!A) return out;
  st.ckAiNo = st.ckAiNo || new Set();
  if (A.status === "loading") { out.push(el("li", "ck-cand-status hint", "AI가 다른 작업 종류의 위험요인 중 이 작업과 맞는 것을 찾는 중입니다. 위 항목은 먼저 확인해도 됩니다.")); return out; }
  if (A.status === "fail") { out.push(el("li", "ck-cand-status hint", "AI 결과를 준비하지 못함 · 체크리스트는 그대로입니다.")); return out; }
  const inList = new Set(P.items.map((it) => it.id));
  for (const x of A.items.filter((i) => !inList.has(i.id) && !st.ckAiNo.has(i.id))) {
    const li = el("li", "ck-item ck-cand"); li.id = `ckc-${x.id}`.replace(/[^\w-]/g, "_");
    li.innerHTML = `<div class="ck-head"><b class="ck-title">${esc(x.title)}<span class="ai-chip">AI 제안</span></b><span class="ck-done">채택 전</span></div>`
      + (x.why ? `<p class="ck-why">${esc(x.why)}</p>` : "")
      + `<p class="ck-reason">${icon("i-info")}<span>근거: 「${esc(x.quote || "")}」 (${esc(x.quote_src || "서류")}) · 채택하면 다른 항목처럼 해당 여부를 고릅니다</span></p>`
      + `<div class="ck-memo"><button type="button" class="btn small" data-ckai-put="${esc(x.id)}">채택</button>`
      + `<button type="button" class="btn small ghost" data-ckai-no="${esc(x.id)}">제외</button></div>`;
    out.push(li);
  }
  return out;
}
function renderCkAi() {
  const old = $("#ck-ai"); if (old) old.hidden = true;         // the candidates are rows in the list now (ckCandRows)
}
document.addEventListener("click", (e) => {
  const no = e.target.closest("[data-ckai-no]");
  if (no && st.ck) { (st.ckAiNo = st.ckAiNo || new Set()).add(no.dataset.ckaiNo); renderChecklist(); return; }
  const put = e.target.closest("[data-ckai-put]"), out = e.target.closest("[data-ckai-out]");
  if ((!put && !out) || !st.ck || !st.ckAi || st.ck.permits.length !== 1) return;
  const P = st.ck.permits[0];
  if (out) { P.items = P.items.filter((it) => it.id !== out.dataset.ckaiOut); ckChanged(); renderChecklist(); return; }
  const x = st.ckAi.items.find((i) => i.id === put.dataset.ckaiPut);
  if (!x || P.items.some((it) => it.id === x.id)) return;
  if (P.items.length >= CK_MAX) { toast(`위험요인은 허가서 1건에 ${CK_MAX}개까지입니다.`); return; }
  const { spec, kind, origin, ...item } = x; void spec; void kind; void origin;
  P.items.push({ ...item, controls: item.controls.map((k) => ({ ...k })), touched: false });
  ckChanged(); renderChecklist();
  document.getElementById(`ck-${x.id}`)?.scrollIntoView({ block: "center" });
});
const CK_MAX = 40;                                    // the server's limit per permit (server/checklist.py MAX_ITEMS)
function ckAdd(P) {
  if (P.items.length >= CK_MAX) { toast(`위험요인은 허가서 1건에 ${CK_MAX}개까지입니다. 비슷한 항목은 메모로 합쳐 주세요.`); return; }
  const t = prompt("추가할 위험요인을 적어 주세요. 예: 인접 BAY 도장 작업의 유기용제");
  if (!t || !t.trim()) return;
  const c = prompt("준비할 안전조치를 적어 주세요 (없으면 비워 두기).") || "";
  const id = `U${Date.now().toString(36)}`;
  P.items.push({ id, title: t.trim().slice(0, 80), why: "작업반장이 직접 추가", common: false, state: "yes", auto: null, touched: true, reasons: [],
    controls: c.trim() ? [{ id: "u1", text: c.trim().slice(0, 120), on: true }] : [], memo: "" });
  ckChanged(); renderChecklist();
  document.getElementById(`ck-${id}`)?.scrollIntoView({ block: "center" });
}
$("#ck-pdf").onclick = async () => {
  const w = window.open("", "_blank");
  try {
    const r = await fetch("/api/checklist/pdf", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: st.doc.fields, checklist: ckPayload(), answers: typedAnswers(), session_id: st.sid || "", expected_revision: st.srev ?? null }) });
    if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
    const url = URL.createObjectURL(await r.blob());
    if (w) w.location = url; else location.assign(url);
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { if (w) w.close(); toast(`PDF를 만들지 못했습니다: ${e.message}`); }
};
$("#ck-back").onclick = () => goStep(2);
$("#ck-next").onclick = () => goStep(5);

// ---------------------------------------------------------------- dialogs: 보기 설정, 도움말, 의견 보내기
let lastFocus = null;
function openDialog(id) {
  lastFocus = document.activeElement;
  const d = $("#" + id); d.hidden = false;
  (d.querySelector("[autofocus], .seg button[aria-pressed='true'], textarea, button") || d).focus();
}
function closeDialogs() {
  const open = [...document.querySelectorAll(".sheet-modal:not([hidden])")];
  if (!open.length) return false;
  for (const d of open) { d.hidden = true; if (d.id === "qa") qaReset(); }
  lastFocus?.focus?.();
  return true;
}
document.querySelectorAll(".sheet-modal").forEach((m) => {
  m.addEventListener("mousedown", (e) => { if (e.target === m) closeDialogs(); });
  m.addEventListener("click", (e) => { if (e.target.closest("[data-close]")) closeDialogs(); });
  // keep Tab inside the open dialog
  m.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    const f = [...m.querySelectorAll("button, input, textarea, [tabindex='0']")].filter((x) => !x.disabled && x.offsetParent);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });
});

// 보기 설정: saved on this device; applied as data-* on <html> (style.css does the rest)
const VIEW_DEFAULT = { text: "m", contrast: "normal", theme: "auto", target: "normal", motion: "auto" };
function viewGet() { try { return { ...VIEW_DEFAULT, ...JSON.parse(localStorage.getItem("croscan.view") || "{}") }; } catch (e) { return { ...VIEW_DEFAULT }; } }
const darkQ = matchMedia("(prefers-color-scheme: dark)");
function viewSet(v) {
  const r = document.documentElement;
  for (const k of Object.keys(VIEW_DEFAULT)) r.dataset[k] = v[k];
  r.dataset.mode = v.theme === "auto" ? (darkQ.matches ? "dark" : "light") : v.theme;
  try { localStorage.setItem("croscan.view", JSON.stringify(v)); } catch (e) { /* storage blocked: this visit only */ }
  document.querySelectorAll("#viewset [data-set]").forEach((g) => g.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.v === v[g.dataset.set])));
  if (D() && st.fitMode) requestAnimationFrame(fit);
  requestAnimationFrame(fitAppbar);
  if (typeof msgs !== "undefined" && st.doc) toBottom();             // a new text size: the latest question stays in view
}
document.querySelectorAll("#viewset [data-set]").forEach((g) => g.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  viewSet({ ...viewGet(), [g.dataset.set]: b.dataset.v });
}));
$("#vs-reset").onclick = () => viewSet({ ...VIEW_DEFAULT });
$("#view-open").onclick = () => openDialog("viewset");
// 글자 크기 bar under the header button (QA #14): the same setting as 보기 설정 → 글자 크기
const TEXT_STEPS = ["s", "m", "l", "xl"], TEXT_KO = ["작게", "보통", "크게", "아주 크게"];
function textPaint() {
  const i = Math.max(0, TEXT_STEPS.indexOf(viewGet().text)), r = $("#text-range");
  r.value = i; r.setAttribute("aria-valuetext", TEXT_KO[i]);
  $("#text-down").disabled = i === 0; $("#text-up").disabled = i === TEXT_STEPS.length - 1;
}
function textTo(i) { i = Math.max(0, Math.min(TEXT_STEPS.length - 1, i)); viewSet({ ...viewGet(), text: TEXT_STEPS[i] }); textPaint(); }
function textPop(open) {
  $("#textpop").hidden = !open; $("#text-open").setAttribute("aria-expanded", String(open));
  if (open) { textPaint(); $("#text-range").focus(); }
}
$("#text-open").onclick = () => textPop($("#textpop").hidden);
$("#text-range").oninput = (e) => textTo(+e.target.value);
$("#text-down").onclick = () => textTo(+$("#text-range").value - 1);
$("#text-up").onclick = () => textTo(+$("#text-range").value + 1);
document.addEventListener("click", (e) => { if (!$("#textpop").hidden && !e.target.closest(".textpop-wrap")) textPop(false); });
$("#textpop").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); textPop(false); $("#text-open").focus(); } });
viewSet(viewGet());
darkQ.addEventListener("change", () => viewSet(viewGet()));          // the device switched light/dark

// 도움말: what this step is for, in one place (instead of tooltips everywhere)
// design §19.5: three lines on checking what the AI read (the same in every step)
const HELP_AI = ["「AI 읽음」 줄은 적으신 답에서 다른 질문의 답으로 읽은 것입니다. 맞는 줄만 남기고 「확인」을 눌러야 답이 됩니다.",
  "확인은 「이렇게 읽은 것이 맞다」는 뜻이고 작업 승인이 아닙니다. 「미확인」은 그 질문에서 아직 말하지 않은 것입니다.",
  "틀린 줄은 「이것 빼기」, 전부 틀리면 「해석 취소」를 누르세요. 빼거나 미확인인 것은 따로 여쭙거나 안전팀 확인으로 넘어갑니다."];
const HELP = {
  1: ["허가서 올리기", ["허가서 종류(밀폐·화기·고소·중량물인양·정전/LOTO)를 고릅니다.", "전산에서 내려받은 허가서 PDF 1개를 올립니다. 끌어 놓거나 눌러서 고를 수 있습니다.", "「검토 시작」을 누르면 양식 칸을 읽습니다. 작업계획서는 1단계에서 먼저 올립니다."]],
  2: ["허가서 검토", ["왼쪽은 허가서입니다. 칸을 누르면 문서 아래에 그 칸이 크게 나옵니다. 거기서 값을 고치거나 「되돌리기」를 누를 수 있습니다.", "「칸 목록」 보기는 모든 칸을 큰 입력칸으로 보여 줍니다. 장갑을 끼었거나 글자가 작을 때 편합니다.", "주황색 테두리 칸은 지금 질문하는 칸입니다. 질문 아래 「허가서에서 이 칸 보기」를 누르면 그 칸으로 갑니다.", "오른쪽 질문은 버튼으로 답하면 됩니다. 모르면 「모름」을 누르세요. 잘못 눌렀으면 그 답 아래 「답 고치기」를 누르면 그 질문만 다시 여쭙겠습니다.", "답과 고친 칸은 이 기기에 저장됩니다. 창을 닫았다가 같은 허가서를 다시 올리면 이어서 할 수 있습니다.", "「추가검토서」 보기에서 답이 정리된 2쪽을 볼 수 있습니다. 원본 허가서는 바뀌지 않습니다."]],
  3: ["작업계획서 확인", ["첫 단계입니다. 작업할 날의 작업계획서 PDF를 올립니다(여러 파일·묶음·폴더).", "오른쪽 목록에서 계획서를 누르면 왼쪽에 양식이 나옵니다. 잘못 읽힌 값은 고칠 수 있고, 자동으로 저장됩니다.", "계획서마다 날짜·시간·위치를 보고, 그날 할 작업이 맞으면 「확인」을 누르세요. 확인하지 않은 계획서가 남아 있으면 그 계획서가 이어서 열립니다.", "모두 확인해야 다음 단계(허가서 올리기)로 넘어갈 수 있습니다."]],
  4: ["위험 체크리스트", ["croScan이 먼저 골라 둔 답이 맞으면 그 아래 「그대로 확인」 칸만 체크하면 「확인 완료」가 됩니다.", "다르면 「해당 / 해당 없음 / 안전팀 확인」 중 하나를 고르세요. 고른 것도 확인으로 칩니다.", "이 목록은 허가서와 확인 질문의 답만 보고 만들었고, 작업계획서는 보지 않았습니다.", "해당하는 위험은 준비할 안전조치를 고릅니다. 법에서 꼭 하라는 조치는 미리 골라 두었습니다.", "작업 전날의 계획입니다. 당일 작업 시작 전 확인은 허가서의 현장 안전조치 칸에 따로 합니다.", "목록에 없는 위험은 「위험요인 직접 추가」로 넣습니다. 「PDF 미리 보기」로 안전팀이 받을 모양을 볼 수 있습니다.", "모든 위험요인을 확인해야 다음 단계(제출 확인)로 넘어갈 수 있습니다."]],
  5: ["제출", ["확인한 내용을 한눈에 봅니다. 고칠 것이 있으면 「바꾸기」로 그 단계로 돌아갑니다.", "「안전팀에 제출」은 시연용입니다. 안전팀에 실제로 보내거나 제출 기록을 남기지 않고, 허가서(원본+추가검토서)·작업계획서·위험 체크리스트 PDF를 그 자리에서 만들어 받을 수 있습니다.", "하이세스(Hi-SEs) 신청, 생산부서 승인권한자의 전산승인, 작업 당일 현장 확인, 2중점검 Y 작업의 아침 대면허가는 기존과 동일합니다. croScan은 Y/N을 정하지 않습니다."]],
};
$("#help-open").onclick = () => {
  const [t, items] = HELP[st.step] || HELP[3];
  $("#help-body").innerHTML = `<h3>지금 단계: ${esc(t)}</h3><ul>${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    + `<h3>AI가 읽은 내용 확인하기</h3><ul>${HELP_AI.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  openDialog("help");
};

// 의견 보내기 (QA): any files (captures, PDF, Word, Excel …) + what is wrong, with the screen state so the team can reproduce it
const qa = { files: [] };
const docTag = (name) => {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const cls = ext === "pdf" ? "pdf" : /^docx?$/.test(ext) ? "doc" : /^(xlsx?|csv)$/.test(ext) ? "xls" : /^hwpx?$/.test(ext) ? "hwp" : "";
  return [cls, ext.toUpperCase().slice(0, 5) || "FILE"];
};
const qaMsg = $("#qa-msg");
const qaSay = (t, cls = "") => { qaMsg.textContent = t; qaMsg.className = "qa-msg " + cls; };
function qaThumbs() {
  const box = $("#qa-thumbs"); box.innerHTML = "";
  qa.files.forEach((f, i) => {
    const fig = document.createElement("figure"), x = el("button", "btn icon small");
    if (f.url) {
      const img = document.createElement("img"); img.src = f.url; img.alt = f.file.name; fig.appendChild(img);
    } else {
      const [cls, tag] = docTag(f.file.name), d = el("div", "qa-doc"), b = el("b", cls, tag), s = el("span", "", f.file.name);
      d.append(b, s); fig.appendChild(d);
    }
    x.type = "button"; x.innerHTML = icon("i-x"); x.setAttribute("aria-label", `${f.file.name} 빼기`);
    x.onclick = () => { if (f.url) URL.revokeObjectURL(f.url); qa.files.splice(i, 1); qaThumbs(); };
    fig.appendChild(x); box.appendChild(fig);
  });
}
function qaAdd(files) {
  for (const f of files) qa.files.push({ file: f, url: f.type.startsWith("image/") ? URL.createObjectURL(f) : null });
  qaThumbs();
}
function qaReset() {
  qa.files.forEach((f) => f.url && URL.revokeObjectURL(f.url)); qa.files = []; qaThumbs(); $("#qa-text").value = ""; qaSay("");
}
function qaContext() {
  return {
    url: location.href, step: st.step, screen: SCREENS.find((s) => !$("#" + s).hidden),
    file: pick.file ? pick.file.name : null, kind: pick.kind, view: st.view, page: st.page, shown_doc: st.di || 0,
    plan_files: pick.plans.map((f) => f.name), plans: st.wp ? st.wp.plans.map((p) => p.doc_no || p.files.join(",")) : null,
    window: `${innerWidth}x${innerHeight}`, ua: navigator.userAgent, assets: ($("script[src*='app.js']").src.split("?v=")[1] || ""),
    view_settings: viewGet(), fields: st.doc ? st.doc.fields : null, answers: st.answers || [],
    open_questions: st.aug ? st.aug.questions.map((q) => q.qid) : null,
  };
}
$("#qa-open").onclick = () => {
  qaSay("");
  try { $("#qa-author").value = localStorage.getItem("croscan.qa.author") || ""; } catch (e) { /* storage blocked */ }
  openDialog("qa"); $("#qa-text").focus();
};
$("#qa-close").onclick = closeDialogs;
$("#qa-file").onchange = (e) => { qaAdd(e.target.files); e.target.value = ""; };
$("#qa").addEventListener("paste", (e) => {
  const files = [...e.clipboardData.items].filter((x) => x.kind === "file").map((x) => x.getAsFile()).filter(Boolean);
  if (files.length) { e.preventDefault(); qaAdd(files); }
});
const qaDrop = $("#qa-drop");
// drop anywhere on the overlay; stopPropagation keeps the upload screen's drop (on body) from taking the file too
$("#qa").addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); qaDrop.classList.add("drag"); });
$("#qa").addEventListener("dragleave", (e) => { e.stopPropagation(); if (e.target === $("#qa")) qaDrop.classList.remove("drag"); });
$("#qa").addEventListener("drop", (e) => { e.preventDefault(); e.stopPropagation(); qaDrop.classList.remove("drag"); qaAdd(e.dataTransfer.files); });
qaDrop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#qa-file").click(); } });
$("#qa-form").onsubmit = async (e) => {
  e.preventDefault();
  const text = $("#qa-text").value.trim(), author = $("#qa-author").value.trim();
  if (!text && !qa.files.length) { qaSay("파일이나 설명 중 하나는 넣어 주세요.", "bad"); $("#qa-text").focus(); return; }
  const btn = $("#qa-send"); btn.disabled = true; qaSay("보내는 중…");
  try {
    const fd = new FormData();
    fd.append("text", text); fd.append("author", author); fd.append("context", JSON.stringify(qaContext()));
    qa.files.forEach((f, i) => fd.append("files", f.file, f.file.name && f.file.name !== "image.png" ? f.file.name : `capture_${i + 1}.png`));
    const r = await fetch("/api/qa", { method: "POST", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `서버 오류 ${r.status}`);
    try { localStorage.setItem("croscan.qa.author", author); } catch (e2) { /* storage blocked */ }
    closeDialogs();
    toast(`의견 #${j.id}을 받았습니다. 고맙습니다!`);
  } catch (err) {
    qaSay(`보내지 못했습니다: ${err.message}`, "bad");
  }
  btn.disabled = false;
};

// ---------------------------------------------------------------- 안전관리자: the documents of one work day
// Everything the 생산부서 and the 협력사 sent in (demo DB, read-only), one row per work, the day's counts as filter
// shortcuts, a 계획 배치도 / 하루 일정 of where and when the works are planned, and tomorrow's 대면허가 and 정전·격리.
// Nothing here judges pairs: that is 「쌍작업 위험탐지」 (next step).
const sf = { data: null, docs: [], tab: "all", q: "", f: {}, sort: "bay", t: 540, view: "map", side: "face", open: null, part: 0, fold: new Set(),
  pick: null, seen: {}, stored: true, loaded: null, req: 0, last: null, mode: "pairs" };
// QA #42: wide screens show the picked pair beside the list; narrower ones open it over the page as before
const SF_WIDE = matchMedia("(min-width: 1181px)");
const sfInline = () => SF_WIDE.matches && sf.mode === "pairs";
const SF_KEY = "croscan.safety.checked", SF_VIEW = "croscan.safety.view";
const SF_PARTS = { permit: [["permit", "허가서"], ["addendum", "추가검토서"], ["checklist", "위험 체크리스트"]], plan: [["plan", "작업계획서"]] };
const SF_KINDS = ["hot", "confined", "height", "lifting", "loto"];
const T0 = 450, T1 = 1260;                                  // the day shown: 07:30–21:00
const hm2m = (s) => { const [h, m] = (s || "").replace("(+1)", "").split(":").map(Number); return h * 60 + m + (/\(\+1\)/.test(s || "") ? 1440 : 0); };
const m2hm = (m) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const sfDoc = (id) => sf.docs.find((x) => x.id === id);
// a work may have several time windows in the day: every check uses all of them
const sfWins = (d) => d.windows || [];
const wEnd = (w) => hm2m(w.end) + (w.next_day ? 1440 : 0);     // a night window ends the next day
const sfActive = (d, t) => sfWins(d).some((w) => hm2m(w.start) <= t && t < wEnd(w));
const sfOverlap = (d, a, b) => sfWins(d).some((w) => hm2m(w.start) < b && a < wEnd(w));
const sfTimes = (d) => sfWins(d).map((w) => `${w.start}–${w.end}${w.next_day ? "(다음 날)" : ""}`).join(", ") || "시간 미지정";
const sfFirst = (d) => sfWins(d).length ? hm2m(sfWins(d)[0].start) : 9999;
const sfBay = (d) => d.spans.length ? d.spans[0].bay : 9;
const sfWho = (d) => d.type === "permit" ? d.dept : d.company;
const sfNo = (d) => d.type === "permit" ? d.id : "WP-" + d.id.slice(-2);
const sfTag = (d) => d.type === "permit" ? d.label : "계획";
const sfTagHtml = (d) => `<span class="sf-tag ${d.type === "permit" ? "k-" + d.kind : "plan"}">${esc(sfTag(d))}</span>`;
function sfWhere(d) {
  if (!d.spans.length) return d.place.replace(/^대조립21공장\s*/, "") || "위치 미지정";
  const b = d.spans[0].bay, cols = d.spans.filter((s) => s.c0);
  if (!cols.length) return `${b}BAY · 칼럼 미지정`;
  const c = (s) => s.c0 === s.c1 ? String(s.c0).padStart(2, "0") : `${String(s.c0).padStart(2, "0")}–${String(s.c1).padStart(2, "0")}`;
  return `${b}BAY ` + (d.is_route ? cols.map(c).join(" → ") : c(cols[0]));
}
const sfBlock = (d) => (d.place.match(/\b[A-Z]\d{2}[A-Z]\b/) || d.place.match(/\b(?:OH|MCC|CP|MEWP)-[\w-]+/) || [""])[0];

// 자료 확인 marks: this browser only, per document and the server's hash of its content (values, answers, checklist)
function sfReadSeen() { try { const s = JSON.parse(localStorage.getItem(SF_KEY) || "{}"); sf.stored = true; return s; } catch (e) { sf.stored = false; return null; } }
function sfLoadSeen() { const s = sfReadSeen(); if (s) sf.seen = s; }
function sfSaveMark(key, rec) {
  const cur = sfReadSeen(); if (cur) sf.seen = cur;          // another window may have marked other documents meanwhile
  for (const k of Object.keys(sf.seen)) if (!k.includes("|")) delete sf.seen[k];   // marks of before the work day was kept
  if (rec) sf.seen[key] = rec; else delete sf.seen[key];
  try { localStorage.setItem(SF_KEY, JSON.stringify(sf.seen)); sf.stored = true; } catch (e) { sf.stored = false; }
}
// Codex QA2 #2·#4: a mark holds for one work day, the content it was made on (the server's hash) and the foreman's
// submission it was made on; a 7-day permit is checked again each day, a new submission drops the mark
const sfSeenKey = (day, id) => `${day}|${id}`;
// the latest submission of the day for a permit: its id, null when there is none, undefined while not known yet
const sfSubId = (d) => d.type !== "permit" || !sf.subs ? (d.type !== "permit" ? null : undefined) : (sf.subs[d.permit_no] || {}).id || null;
const markHolds = (s, rev, sub) => !!s && s.h === rev && (sub === undefined || (s.sub || null) === sub);
const sfSeenOf = (d) => (sf.data ? sf.seen[sfSeenKey(sf.data.date, d.id)] : null);
function sfMarks(d) { const s = sfSeenOf(d); return markHolds(s, d.rev, sfSubId(d)) ? s.parts : {}; }
function sfState(d) {
  const s = sfSeenOf(d);
  if (s && !markHolds(s, d.rev, sfSubId(d)) && Object.values(s.parts || {}).some(Boolean)) return "changed";   // marked, then the document changed
  const parts = SF_PARTS[d.type], m = sfMarks(d), n = parts.filter(([k]) => m[k]).length;
  return n === parts.length ? "done" : n ? "part" : "todo";
}
function sfStateHtml(d) {
  const s = sfState(d), parts = SF_PARTS[d.type], n = parts.filter(([k]) => sfMarks(d)[k]).length;
  const t = { todo: "확인 전", part: `${n}/${parts.length}`, done: "확인", changed: "변경됨" }[s];
  return `<span class="sf-state ${s}">${s === "done" ? icon("i-check") : s === "changed" ? icon("i-alert") : ""}${t}</span>`;
}
function sfMark(d, k, on) {
  const key = sfSeenKey(sf.data.date, d.id), s = sf.seen[key], sub = sfSubId(d);
  const rec = markHolds(s, d.rev, sub) ? { ...s, parts: { ...s.parts } } : { h: d.rev, sub: sub ?? null, day: sf.data.date, parts: {} };
  rec.parts[k] = on;
  sfSaveMark(key, Object.values(rec.parts).some(Boolean) ? rec : null);
}
// what the list was showing (per work day) and the sort (per browser): back where it was after a reload
function sfSaveView() {
  if (!sf.data) return;
  const f = Object.fromEntries(Object.entries(sf.f).map(([k, v]) => [k, [...v]]));
  try {
    localStorage.setItem(`${SF_VIEW}.${sf.data.date}`, JSON.stringify({ tab: sf.tab, q: sf.q, f, t: sf.t, view: sf.view, side: sf.side, open: sf.open, part: sf.part,
      det: !!(sf.det), mode: sf.mode, ptab: sf.ptab, pkind: sf.pkind, pair: sf.pair ? sf.pair.key : (sf.restoreKey || null), navOpen: sf.navOpen, near: sf.nearKey || null }));
    localStorage.setItem(SF_VIEW, JSON.stringify({ sort: sf.sort }));
  } catch (e) { /* storage blocked: this visit only */ }
}
function sfLoadView() {
  try {
    const g = JSON.parse(localStorage.getItem(SF_VIEW) || "{}"), v = JSON.parse(localStorage.getItem(`${SF_VIEW}.${sf.data.date}`) || "{}");
    if (["bay", "time", "todo"].includes(g.sort)) sf.sort = g.sort;
    if (["all", "permit", "plan"].includes(v.tab)) sf.tab = v.tab;
    sf.q = typeof v.q === "string" ? v.q : "";
    sf.f = Object.fromEntries(Object.entries(v.f || {}).filter(([k]) => SF_FACETS.some((F) => F.k === k)).map(([k, a]) => [k, new Set(a)]));
    if (v.t >= T0 && v.t <= T1) sf.t = v.t;
    if (v.view === "day") sf.view = "day";
    if (v.side === "iso") sf.side = "iso";
    sf.wasDetected = !!v.det; if (["pairs", "map", "docs"].includes(v.mode)) sf.mode = v.mode;
    if (["all", "1", "2", "3", "near", "ai"].includes(v.ptab)) sf.ptab = v.ptab;
    if (["all", "RN", "NN"].includes(v.pkind)) sf.pkind = v.pkind;
    if (typeof v.pair === "string") sf.restoreKey = v.pair;
    if (v.navOpen === false) sf.navOpen = false;
    if (typeof v.near === "string") sf.nearKey = v.near;
    return v.open && sfDoc(v.open) ? { id: v.open, part: v.part || 0 } : null;
  } catch (e) { return null; }
}

// 필터: OR inside a group, AND between groups; a count says what picking that option would show
const SF_FACETS = [
  { k: "kind", l: "허가서 종류", opts: () => SF_KINDS.filter((k) => sf.data.permits.some((p) => p.kind === k)).map((k) => [k, sf.data.permits.find((p) => p.kind === k).label]),
    test: (d, v) => d.type === "permit" && d.kind === v },
  { k: "bay", l: "BAY (걸친 BAY 모두)", opts: () => [1, 2, 3, 4].map((b) => [String(b), `${b}BAY`]).concat([["9", "BAY 밖"]]),
    test: (d, v) => v === "9" ? !d.spans.length : d.spans.some((s) => s.bay === +v) },
  { k: "time", l: "시간대 (작업 시간이 걸치면 포함)", opts: () => [["am", "12시 전"], ["pm", "12–17시"], ["eve", "17시 이후"], ["at", `선택 시각 ${m2hm(sf.t)}에 작업 중`]],
    test: (d, v) => v === "am" ? sfOverlap(d, 0, 720) : v === "pm" ? sfOverlap(d, 720, 1020) : v === "eve" ? sfOverlap(d, 1020, 1440) : sfActive(d, sf.t) },
  { k: "state", l: "자료 확인", opts: () => [["todo", "확인 전"], ["part", "일부 확인"], ["done", "확인"], ["changed", "변경됨"]], test: (d, v) => sfState(d) === v },
  // 아침 안전대면허가 대상 = PTW 스캔 때 정해진 2중점검 Y (정하는 주체·기준은 미확인) (인터뷰 2026-10-29); 허가 구분과는 따로 둔다
  { k: "ptw", l: "PTW 2중점검 (Y = 작업일 아침 대면허가)", opts: () => [["Y", "Y · 대면허가 대상"], ["N", "N"], ["", "값 없음"]],
    test: (d, v) => d.type === "permit" && (d.double_check || "") === v },
  { k: "period", l: "신청", opts: () => [["new", "이번 접수 (첫 작업일)"], ["running", "진행 중 허가 (7일 단위)"]],
    test: (d, v) => d.type === "permit" && (v === "running" ? d.running : !d.running) },
  { k: "ptype", l: "허가 구분", opts: () => [["안전현장허가", "안전현장허가"], ["전산허가", "전산허가"]], test: (d, v) => d.permit_type === v },
  { k: "point", l: "검토 포인트", opts: () => [["unconf", "미확인 답변 있음"], ["check", "안전팀 확인 항목 있음"]],
    test: (d, v) => d.type === "permit" && (v === "unconf" ? d.unconfirmed > 0 : d.checklist.check > 0) },
  { k: "org", l: "부서 · 협력사", wide: true, opts: () => {
    const p = [...new Set(sf.data.permits.map(sfWho))].sort(), c = [...new Set(sf.data.plans.map(sfWho))].sort();
    return [...p, ...c].map((w) => [w, w]);
  }, test: (d, v) => sfWho(d) === v },
];
const sfOn = (k) => sf.f[k] && sf.f[k].size > 0;
function sfMatch(d, skip, noTab) {
  if (!noTab && sf.tab !== "all" && d.type !== sf.tab) return false;
  if (sf.q) {
    const q = sf.q.toLowerCase();
    if (![d.title, d.id, d.permit_no, d.company, d.dept, d.place, d.route, d.target, d.equipment, d.label, d.isolation].join(" ").toLowerCase().includes(q)) return false;
  }
  return SF_FACETS.every((F) => F.k === skip || !sfOn(F.k) || [...sf.f[F.k]].some((v) => F.test(d, v)));
}
const sfFiltering = () => sf.tab !== "all" || !!sf.q || SF_FACETS.some((F) => sfOn(F.k));
function sfVisible() {
  const key = { bay: (d) => [sfBay(d), sfFirst(d), d.id], time: (d) => [sfFirst(d), sfBay(d), d.id],
    todo: (d) => [{ changed: 0, todo: 1, part: 2, done: 3 }[sfState(d)], sfBay(d), sfFirst(d), d.id] }[sf.sort];
  return sf.docs.filter((d) => sfMatch(d)).sort((a, b) => {
    const x = key(a), y = key(b);
    for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
    return 0;
  });
}
function sfToggle(k, v, only) {
  const s = sf.f[k] || (sf.f[k] = new Set());
  if (only) { const was = s.size === 1 && s.has(v); s.clear(); if (!was) s.add(v); } else s.has(v) ? s.delete(v) : s.add(v);
}
function sfClear() {
  sf.tab = "all"; sf.q = ""; sf.f = {}; $("#sf-q").value = "";
}

// the foremen's latest submissions: fetched every time the view opens (a submission made meanwhile shows)
async function sfSubs() {
  const was = subIds(sf.subs);
  sf.subs = await fetch("/api/safety/submissions").then((x) => x.ok ? x.json() : {}).catch(() => sf.subs || {});
  sfOutside();
  if (sf.data && subIds(sf.subs) !== was) { sfRefresh(); if (sf.post && sf.mode === "post") postRender(); }   // a new submission drops its 자료 확인
  else if (sf.docs && sf.docPick) sfDocSummary();
}
const subIds = (S) => (S ? JSON.stringify(Object.entries(S).filter(([k]) => !k.startsWith("_")).map(([k, v]) => [k, v && v.id]).sort()) : "");
// Codex A6: a submission whose number is not in the day's list (or of another work day) is listed apart with its
// documents, never dropped; it adds nothing to the day's judgement
function sfOutside() {
  const xs = (sf.subs && sf.subs._outside) || [], foot = $("#sf-foot"); let box = $("#sf-outside");
  if (!foot || !xs.length) { if (box) box.remove(); return; }
  if (!box) { box = el("div", "sf-sub sf-outside"); box.id = "sf-outside"; foot.before(box); }
  const link = (s, n, l) => (s.files || []).includes(n) ? `<a class="btn small" href="/api/submissions/${encodeURIComponent(s.id)}/${n}.pdf" target="_blank" rel="noopener">${icon("i-pdf")}${l}</a>` : "";
  box.innerHTML = `<p><b>이 날 작업 목록에 없는 제출 ${xs.length}건</b> <span class="hint">이 날 위험 쌍 판정에는 들어가지 않았습니다. 허가번호·작업일을 확인해 주세요.</span></p><ul>`
    + xs.map((s) => `<li><p><b>${esc(s.permit_no)}</b> ${esc(s.label || "")} · ${esc(s.who || "")} · ${esc(s.why)}${(s.dates || []).length ? ` · 작업일 ${esc(s.dates.join(", "))}` : ""} · ${esc(kstHM(s.created))} 제출</p>`
      + `<p class="sf-sub-act">${link(s, "permit", "제출본 추가검토서")}${link(s, "checklist", "제출본 체크리스트")}${link(s, "plans", "제출본 작업계획서")}</p></li>`).join("") + `</ul>`;
}
// a submission of this permit (design §12.2), as one line and its documents
// design §6.5·§19.1: what to read first for a document (시간·장소·대상·공유 설비·단계·상충·미확인), what croScan's AI
// did with it, and a plan's 허가 검토 신호 — beside the summary, the one-line list stays as it is
async function sfSumLoad() {
  sf.summ = await fetch("/api/safety/doc-summaries").then((r) => r.ok ? r.json() : null).catch(() => sf.summ || null);
  if (sf.docPick) sfDocSummary();
}
function sfSumHtml(d) {
  const s = sf.summ && sf.summ[d.id]; if (!s) return "";
  return `<div class="sf-sum"><h4>먼저 볼 것</h4><table class="sf-ds">${s.rows.map(([k, v, f]) => `<tr${f ? ` class="warn"` : ""}><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</table>`
    + (s.ai && s.ai.lines && s.ai.lines.length ? `<p class="sf-sum-ai"><span class="ai-chip">AI 읽기 결과</span>${s.ai.lines.map(esc).join(" · ")}</p>` : "") + `</div>`;
}
function sfSignalHtml(d) {
  const s = sf.summ && sf.summ[d.id]; if (!s || !(s.signals || []).length) return "";
  return s.signals.map((x) => `<div class="sf-signal" role="note"><p><b>${esc(x.title)}</b>${x.ai ? ` <span class="ai-chip">AI 제안</span>` : ""}</p>`
    + `<p>계획서 “${esc(x.quote)}” <span class="hint">(${esc(x.label)})</span></p><p class="hint">조회 범위: ${esc(x.scope)}</p><p class="hint">${esc(x.found)}</p></div>`).join("");
}
function sfSubHtml(d) {
  const sub = d.type === "permit" && sf.subs && sf.subs[d.permit_no];
  const ver = sfVerLine([d.id]);                  // Codex A6: 서류 기준 / 제출본 반영
  if (!sub) return ver;
  const link = (n, l) => (sub.files || []).includes(n) ? `<a class="btn small" href="/api/submissions/${encodeURIComponent(sub.id)}/${n}.pdf" target="_blank" rel="noopener">${icon("i-pdf")}${l}</a>` : "";
  return `<div class="sf-sub"><p><b>croScan 제출본</b> ${esc(kstHM(sub.created))} 제출 · 답변 ${sub.answers}건${sub.adopted ? ` (+확인한 읽기 ${sub.adopted}건)` : ""}`
    + ` · 담당 확인 ${sub.unresolved}건 · 체크리스트 해당 ${sub.checklist.yes} · 안전팀 확인 ${sub.checklist.check} · 해당 없음 ${sub.checklist.no}${sub.after_close ? ` · <b>마감 뒤 수정 ${sub.after_close}건</b>` : ""}</p>`
    + ver + `<p class="sf-sub-act">${link("permit", "제출본 추가검토서")}${link("checklist", "제출본 체크리스트")}${link("plans", "제출본 작업계획서")}</p></div>`;
}
async function sfLoad() {
  sfSubs(); sfSumLoad();
  if (sf.data) return;
  sfLoadSeen();
  try {
    const r = await fetch("/api/safety/overview");
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `서버 오류 ${r.status}`);
    sf.data = j;
  } catch (err) {
    const e = $("#sf-err"); e.textContent = `수집 문서를 불러오지 못했습니다: ${err.message}`; e.hidden = false; return;
  }
  const D = sf.data;
  sf.docs = [...D.permits, ...D.plans];
  const [y, mo, da] = D.date.split("-").map(Number), wd = (dt) => "일월화수목금토"[dt.getDay()];
  const day = new Date(y, mo - 1, da), prev = new Date(y, mo - 1, da - 1);
  $("#sf-title").textContent = `${y}.${mo}.${da}(${wd(day)}) 작업 서류`;
  const run = D.permits.filter((p) => p.running).length;
  $("#sf-sub").innerHTML = `<span>${esc(D.factory)} · 접수 기준 ${prev.getMonth() + 1}.${prev.getDate()}(${wd(prev)}) 15:00 · 작업 허가서 ${D.permits.length}건 · 작업계획서 ${D.plans.length}건</span>`
    + (run ? `<small>허가서 구성: 이번 접수 ${D.permits.length - run}건 · 진행 중 허가 ${run}건</small>` : "");
  $("#sf-clock-label").textContent = `선택 시각 · ${mo}.${da}`;
  $("#sf-detect").disabled = false;
  $("#sf-detect-note").textContent = `전체 ${sf.docs.length}건 대상 · 분석 기능 준비 중`;
  const resume = sfLoadView();
  $("#sf-q").value = sf.q; $("#sf-sort").value = sf.sort;
  const link = location.hash.split("/");                     // #safety/2026-10-29/0737
  sfProfile(); sfSetTime(sf.t, true); sfRefresh();
  const linked = link[2] && decodeURIComponent(link[2]);
  // detection is rerun (it is cheap and the documents may have changed) when it had been run, or a pair is linked
  { const keep = sf.mode, kt = sf.t; await sfDetect(true); sf.mode = keep; sfSetTime(kt, true); sfPairsView(); if (keep === "map") sfMapView(); }
  if (document.body.dataset.role !== "safety") return;          // left for the first screen while it was detecting
  const restoreKey = sf.restoreKey; sf.restoreKey = null;
  // a reload opens the pair saved by key (its P번호 may have changed), and only inside the saved filter; a P번호 alone is a shared link
  const saved = restoreKey && sf.det && sf.det.pairs.find((x) => x.key === restoreKey);
  if (saved && sfPairVisible().some((x) => x.id === saved.id)) sfOpenPair(saved.id, true);
  else if (saved) sfPairsView();
  else if (link[1] === D.date && /^P\d+$/.test(linked || "")) sfOpenPair(linked);
  else if (sfInline() && sf.det && sf.ptab !== "near" && sfPairVisible()[0] && !(link[1] === D.date && sfDoc(linked))) {
    // the pair seen last (else the first shown) beside the list: shown, but the time and the address stay as they were
    const vis = sfPairVisible(), back = restoreKey && vis.find((x) => x.key === restoreKey);
    const kt = sf.t; sfOpenPair((back || vis[0]).id, true); sfSetTime(kt, true); history.replaceState(null, "", "#safety");
  }
  else if (link[1] === D.date && sfDoc(linked)) sfOpen(linked);
  else if (resume) {
    const d = sfDoc(resume.id), parts = SF_PARTS[d.type];
    $("#sf-resume-text").textContent = `「${d.title}」 · ${parts[Math.min(resume.part, parts.length - 1)][1]}`;
    $("#sf-resume").hidden = false;
    $("#sf-resume-go").onclick = () => { $("#sf-resume").hidden = true; sfOpen(resume.id, Math.min(resume.part, parts.length - 1)); };
  }
  sfSaveView();
}
// everything that depends on the filters, the marks or the time
function sfRefresh() {
  sfTiles(); sfTabs(); if (!$("#sf-filter").hidden) sfFilterPanel(); sfActiveBar(); sfRows(); sfMapView(); sfSched(); sfProgress(); sfPairsView();
  const d = sf.open && sfDoc(sf.open); if (d) sfPanelChrome(d);
  sfSaveView();
}
function sfProgress() {
  const done = (list) => list.filter((d) => sfState(d) === "done").length, n = sf.docs.length, k = done(sf.docs);
  $("#sf-prog-n").textContent = `${k}/${n}건`;
  $("#sf-prog-fill").style.width = `${n ? (k / n) * 100 : 0}%`;
  $("#sf-prog-sub").textContent = `허가서 ${done(sf.data.permits)}/${sf.data.permits.length} · 계획서 ${done(sf.data.plans)}/${sf.data.plans.length} · `
    + (sf.stored ? "이 브라우저 기록" : "저장 안 됨") + " · 승인 아님";
}
// 아침 대면허가 대상: 이날 작업이 있고 PTW 2중점검이 Y인 허가 (새로 접수한 것과 진행 중인 7일 허가 모두)
const sfFace = () => sf.data.permits.filter((p) => p.works_today !== false && p.double_check === "Y");
const sfPeriod = (d) => d.type === "permit" && d.days && d.days.length > 1
  ? `${d.running ? "진행 중 " : ""}${d.days[0].slice(5).replace("-", "/")}~${d.days[d.days.length - 1].slice(5).replace("-", "/")} 중 ${d.days.indexOf(sf.data.date) + 1}/${d.days.length}일째` : "";
// 요약 타일: the day's totals (they do not shrink with the filters); pressing one sets that filter alone
function sfTiles() {
  const P = sf.data.permits, kinds = SF_KINDS.map((k) => [P.filter((p) => p.kind === k), k]).filter(([l]) => l.length);
  const face = sfFace(), unc = P.filter((p) => p.unconfirmed > 0), chk = P.filter((p) => p.checklist.check > 0);
  const loto = P.filter((p) => p.kind === "loto");
  const only = (k, v) => sfOn(k) && sf.f[k].size === 1 && sf.f[k].has(v);
  const tiles = [
    ["tab:permit", "허가서", `${P.length}묶음`, kinds.map(([l]) => `${l[0].label} ${l.length}`).join(" · "), sf.tab === "permit"],
    ["tab:plan", "작업계획서", `${sf.data.plans.length}건`, `협력사 ${new Set(sf.data.plans.map(sfWho)).size}곳`, sf.tab === "plan"],
    ["ptw:Y", "아침 대면허가", `${face.length}건`, `작업일 아침 대면허가 대상 · 진행 중 허가 포함`, only("ptw", "Y")],
    ["point:unconf", "미확인 답변", `${unc.reduce((a, p) => a + p.unconfirmed, 0)}개`, `허가서 ${unc.length}건`, only("point", "unconf"), unc.length > 0],
    ["point:check", "안전팀 확인 항목", `${chk.reduce((a, p) => a + p.checklist.check, 0)}개`, `허가서 ${chk.length}건 · 체크리스트`, only("point", "check")],
    ["kind:loto", "정전·격리", `${loto.length}건`, loto.map(sfBlock).filter(Boolean).join(" · "), only("kind", "loto")],
  ];
  $("#sf-tiles").innerHTML = tiles.map(([key, l, n, sub, on, warn]) =>
    `<button type="button" class="sf-tile${warn ? " warn" : ""}" data-tile="${esc(key)}" aria-pressed="${!!on}"><span class="sf-tile-l">${esc(l)}</span><b>${esc(n)}</b><span class="sf-tile-s">${esc(sub)}</span></button>`).join("");
}
function sfTabs() {
  const n = (t) => sf.docs.filter((d) => (t === "all" || d.type === t) && sfMatch(d, null, true)).length;
  $("#sf-tabs").innerHTML = [["all", "전체"], ["permit", "허가서"], ["plan", "작업계획서"]]
    .map(([k, l]) => `<button type="button" data-tab="${k}" aria-pressed="${sf.tab === k}">${l} ${n(k)}</button>`).join("");
}
function sfFilterPanel() {
  $("#sf-filter").innerHTML = `<div class="sf-fgrid">` + SF_FACETS.map((F) => {
    const opts = F.opts().map(([v, l]) => {
      const on = sfOn(F.k) && sf.f[F.k].has(v);
      const n = sf.docs.filter((d) => sfMatch(d, F.k) && F.test(d, v)).length;
      const ic = F.k === "kind" ? icon(KIND_ICON[v]) : "";
      return `<button type="button" class="sf-opt" data-f="${F.k}" data-v="${esc(v)}" aria-pressed="${on}" ${!n && !on ? "disabled" : ""}>${ic}<span>${esc(l)}</span><i>${n}</i></button>`;
    }).join("");
    return `<fieldset class="sf-fgroup${F.wide ? " wide" : ""}"><legend>${esc(F.l)}</legend><div class="sf-opts">${opts}</div></fieldset>`;
  }).join("") + `</div><div class="sf-ffoot"><span class="hint">같은 묶음 안은 '또는', 묶음끼리는 '그리고'로 좁힙니다. 숫자는 그 항목을 더했을 때의 건수입니다.</span>`
    + `<button type="button" class="btn small" data-unfilter>필터 초기화</button><button type="button" class="btn small primary" id="sf-fdone">닫기</button></div>`;
}
function sfActiveBar() {
  const chips = [];
  if (sf.q) chips.push(["q", "", `검색: ${sf.q}`]);
  for (const F of SF_FACETS) if (sfOn(F.k)) {
    const lab = Object.fromEntries(F.opts());
    for (const v of sf.f[F.k]) chips.push([F.k, v, `${F.l.split(" (")[0]}: ${lab[v] || v}`]);
  }
  const n = SF_FACETS.reduce((a, F) => a + (sfOn(F.k) ? sf.f[F.k].size : 0), 0);
  $("#sf-fcount").hidden = !n; $("#sf-fcount").textContent = n;
  const shown = sfVisible().length;
  $("#sf-active").innerHTML = `<span class="sf-shown"><b>${shown}</b>/${sf.docs.length}건 표시</span>`
    + chips.map(([k, v, l]) => `<button type="button" class="sf-chipx" data-rm="${esc(k)}" data-v="${esc(v)}" aria-label="${esc(l)} 조건 지우기">${esc(l)}${icon("i-x")}</button>`).join("")
    + (sfFiltering() ? `<button type="button" class="linkbtn" data-unfilter>필터 초기화</button>` : "");
}
function sfRows() {
  const list = sfVisible(), total = {};
  for (const d of sf.docs) total[sfBay(d)] = (total[sfBay(d)] || 0) + 1;
  const shown = {}; for (const d of list) shown[sfBay(d)] = (shown[sfBay(d)] || 0) + 1;
  let h = "", grp = null;
  for (const d of list) {
    if (sf.sort === "bay" && sfBay(d) !== grp) {
      grp = sfBay(d);
      const fold = sf.fold.has(grp);
      h += `<tr class="sf-grp${fold ? " folded" : ""}"><th colspan="5" scope="colgroup"><button type="button" class="sf-fold" data-fold="${grp}" aria-expanded="${!fold}">`
        + `${icon("i-right")}${grp === 9 ? "BAY 밖" : grp + "BAY"} <span>${shown[grp]}/${total[grp]}건${fold ? " · 접힘" : ""}</span></button></th></tr>`;
    }
    if (sf.sort === "bay" && sf.fold.has(grp)) continue;
    h += `<tr data-id="${esc(d.id)}" class="${sf.pick === d.id ? "picked" : ""}">
      <td class="sf-doc"><button type="button" class="sf-open sf-open1" data-open="${esc(d.id)}" title="${esc(d.title)}">${sfCls(d)}${d.type === "permit" ? sfTagHtml(d) : ""}`
      + `<span class="sf-name">${esc(d.title)}</span><span class="sf-no1">${esc(sfNo(d))}</span></button></td>
      <td class="sf-who">${esc(sfWho(d))}</td><td class="sf-where">${esc(sfWhere(d))}</td><td class="sf-when">${esc(sfTimes(d))}</td><td>${sfStateHtml(d)}</td></tr>`;
  }
  $("#sf-rows").innerHTML = h;
  $("#sf-empty").hidden = list.length > 0;
  if (!list.some((d) => d.id === sf.docPick)) sf.docPick = list.length ? list[0].id : null;
  sfDocSummary();
  $("#sf-foot").textContent = `자료 확인은 이 브라우저에만 남는 개인 표시이며 승인이 아닙니다.`;
}
// QA #45: the picked document in short, beside the list (wide screens). Picking only shows it: the 자료 확인 marks
// are made in the document itself (「문서 열기」), never by looking at a summary.
const SF_KIND_TITLE = { hot: "기타위험(화기작업)작업 허가서", confined: "밀폐공간 작업 허가서", height: "고소작업 허가서", lifting: "중량물 인양작업 허가서", loto: "정전·LOTO 작업 허가서" };
function sfDocSummary() {
  const box = $("#sf-doc-sum"), d = sf.docPick && sfDoc(sf.docPick);
  // beside the summary only the summarized one is marked (a map pick's mark is not a second selection here)
  document.querySelectorAll("#sf-rows tr[data-id]").forEach((tr) => { tr.classList.toggle("doc-picked", tr.dataset.id === sf.docPick); if (sfDocSplit()) tr.classList.toggle("picked", false); });
  if (!d) { box.innerHTML = `<p class="hint">왼쪽 목록에서 문서를 고르면 여기에서 요약을 봅니다.</p>`; return; }
  const P = d.type === "permit", [title, paren] = sfTitleParts(d.title), [where, whereSub] = sfPlaceParts(d);
  const crew = P && /\d\s*명/.test(d.detail || "");                     // 「진입 2명, 감시 1명」 goes beside the head count
  const sub = [paren, crew ? "" : d.detail].filter(Boolean).join(" · ");
  const days = (d.days || []).map((x) => x.slice(5).replace("-", "/")), md = (sf.data.date || "").slice(5).replace("-", "/");
  const span = days.length > 1 ? `${days[0]}–${days[days.length - 1]} 중 ${days.length}일` : days.length ? `${days[0]} 하루` : "";
  const row = (k, main, small, more) => `<div class="sf-dsr"><span class="sf-dsk">${k}</span><div><b>${esc(main)}</b>${small ? `<small>${esc(small)}</small>` : ""}${more || ""}</div></div>`;
  const dayList = days.length > 1 ? `<button type="button" class="linkbtn sf-ds-days" data-dsdays aria-expanded="${!!sf.dsDays}">작업일 ${sf.dsDays ? "접기" : "보기"}</button>`
    + (sf.dsDays ? `<small class="sf-ds-daylist">${days.map((x) => x === md ? `<b>${esc(x)} 오늘</b>` : esc(x)).join(" · ")}</small>` : "") : "";
  const chips = (P ? [d.permit_type, d.double_check && `PTW 2중점검 ${d.double_check}`, d.running && "진행 중 허가"]
    : [d.equipment, d.height && `높이 ${d.height}`]).filter(Boolean);
  // the sections stay folded: the card fits one screen; what is in them is what the long table showed
  const sec = (k, label, count, body) => body ? `<details class="sf-dsd" data-dssec="${k}"${sf.dsOpen.has(k) ? " open" : ""}><summary><b>${label}</b><span>${esc(count)}</span></summary><div>${body}</div></details>` : "";
  const kv = (rows) => `<table class="sf-ds">${rows.filter(([, v]) => v).map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join("")}</table>`;
  const ps = sfPairsOf(d.id), S = sf.summ && sf.summ[d.id], st = d.answer_status || {};
  const pairs = ps.length ? `<ul class="sf-ds-pairs">${ps.slice().sort((a, b) => a.priority - b.priority).map((p) => { const o = sfDoc(p.a === d.id ? p.b : p.a);
    return `<li><button type="button" class="linkbtn" data-dspair="${esc(p.id)}"><span class="sf-pbadge sm p${p.priority}">${PRI[p.priority][0]}</span> ${esc(p.id)} ${esc(p.title)}</button><small>상대 ${esc(o ? `${sfNo(o)} ${o.title}` : "")}</small></li>`; }).join("")}</ul>` : "";
  box.innerHTML = `<div class="sf-ds-head">${sfTagHtml(d)}<div><h3>${esc(title)}</h3>${sub ? `<p class="sf-ds-sub">${esc(sub)}</p>` : ""}<p class="hint">${esc(sfNo(d))} · ${esc(sfWho(d))}</p></div>${sfDsState(d)}</div>`
    + `<div class="sf-dsrows">${row("장소", where, whereSub)}${row("시간", sfTimes(d), span, dayList)}${row("인원", d.workers ? `${d.workers}명` : "인원 미기재", crew ? d.detail : "")}</div>`
    + (chips.length ? `<p class="sf-ds-chips">${chips.map(esc).join(" · ")}</p>` : "")
    + `<div class="sf-dsds">`
    + (P ? sec("check", "안전팀 확인 필요", `${d.checklist.check}건`, `<p>위험 체크리스트에서 반장이 「안전팀 확인」으로 둔 항목 ${d.checklist.check}개 · 해당 ${d.checklist.yes}개 · 해당 없음 ${d.checklist.no}개</p>`
        + `<p class="hint">항목은 「문서 열기」의 위험 체크리스트에서 봅니다.</p>`) : "")
    + (P ? sec("ans", "추가 답변", `${d.answers}건`, `<p>${Object.entries(st).map(([k, n]) => `${esc(k)} ${n}건`).join(" · ") || "답변 없음"}${d.unconfirmed ? ` · <b>미확인 답변 ${d.unconfirmed}건</b>` : ""}</p>` + sfSubHtml(d)) : "")
    + sec("first", P ? "먼저 볼 것" : "먼저 볼 것·허가 검토 신호", S ? `${(S.rows || []).length + (S.signals || []).length}건` : "", S ? sfSumHtml(d) + sfSignalHtml(d) : "")
    + sec("pairs", "관련 위험쌍", `${ps.length}건`, pairs || `<p class="hint">${sf.det ? "이 문서가 든 위험 쌍이 없습니다." : "위험 쌍 찾기 전입니다."}</p>`)
    + sec("info", "문서 정보", P ? "승인번호·신청내역" : "문서번호·책임자", kv(P ? [["승인번호", d.permit_no], ["신청", [d.applicant, d.applied].filter(Boolean).join(" · ")], ["신청 구분", sfPeriod(d) || "이번 접수"],
        ["작업장소 원문", d.place], ["작업 일시", `${(d.days || []).join(", ")} ${sfTimes(d)}`.trim()], ["작업부서", d.dept], ["유해위험요소", d.hazards]]
      : [["문서번호", d.doc_no || d.id], ["수행 부서·협력사", d.company], ["책임자", d.boss], ["작업장소 원문", d.place], ["장비", d.equipment], ["자재", d.materials], ["작업 높이", d.height]])
      + (P ? "" : sfSubHtml(d)))
    + `</div><div class="sf-ds-act"><button type="button" class="btn primary" data-open="${esc(d.id)}">${icon("i-file")}문서 열기</button>`
    + `<button type="button" class="btn" data-pickmap="${esc(d.id)}">${icon("i-search")}배치도에서 보기</button></div>`;
}
// QA #102: the work's title without its note in brackets, and the note (「아르곤 퍼지 … (용접부 비드 확인)」)
const sfTitleParts = (t) => { const m = String(t || "").match(/^(.+?)\s*\(([^()]+)\)\s*$/); return m ? [m[1], m[2]] : [t || "", ""]; };
// the place in short (공장 · BAY 칼럼 · 블록) and the rest of the written place under it
function sfPlaceParts(d) {
  const place = d.place || "", fac = (place.match(/^대조립\d+공장/) || [""])[0], blk = sfBlock(d);
  if (!d.spans.length && !blk) return [place || "위치 미지정", ""];
  const rest = blk ? place.slice(place.indexOf(blk) + blk.length).replace(/^\s*블록\s*/, "").trim() : place.replace(/^대조립\d+공장\s*/, "");
  return [[fac, d.spans.length ? sfWhere(d) : "", blk].filter(Boolean).join(" · "), rest];
}
function sfDsState(d) {
  const s = sfState(d), parts = SF_PARTS[d.type], n = parts.filter(([k]) => sfMarks(d)[k]).length;
  const t = { todo: "자료 확인 전", part: `자료 확인 ${n}/${parts.length}`, done: "자료 확인 완료", changed: "변경됨 · 다시 확인" }[s];
  return `<span class="sf-state ${s}">${s === "done" ? icon("i-check") : s === "changed" ? icon("i-alert") : ""}${t}</span>`;
}
// the folded sections and the work days stay as they were when the card is drawn again
Object.assign(sf, { dsOpen: new Set(), dsDays: false });
$("#sf-doc-sum").addEventListener("toggle", (e) => { const x = e.target.closest && e.target.closest("[data-dssec]"); if (x) sf.dsOpen[x.open ? "add" : "delete"](x.dataset.dssec); }, true);
$("#sf-doc-sum").addEventListener("click", (e) => {
  if (e.target.closest("[data-dsdays]")) { sf.dsDays = !sf.dsDays; sfDocSummary(); const b = $("#sf-doc-sum [data-dsdays]"); if (b) b.focus(); return; }
  const p = e.target.closest("[data-dspair]"); if (p) { sfMain("pairs"); sfOpenPair(p.dataset.dspair); }
});
const sfDocSplit = () => SF_WIDE.matches && sf.mode === "docs";
// 계획 배치도 / 하루 일정 -------------------------------------------------
function sfProfile() {            // works planned per 15-min slot over the day: where the busy hours are
  const slots = [];
  for (let t = T0; t < T1; t += 15) slots.push(sf.docs.filter((d) => sfActive(d, t)).length);
  const max = Math.max(1, ...slots);
  $("#sf-prof-bars").innerHTML = slots.map((n) => `<i style="height:${Math.round((n / max) * 100)}%"></i>`).join("");
}
function sfSetTime(t, quiet) {
  sf.t = Math.max(T0, Math.min(T1, Math.round(t)));
  $("#sf-t").value = sf.t;
  $("#sf-clock").value = m2hm(sf.t);
  $("#sf-prof-mark").style.left = `${((sf.t - T0) / (T1 - T0)) * 100}%`;
  if (quiet) return;
  if (sfOn("time") && sf.f.time.has("at")) sfRefresh(); else { sfMapView(); sfSaveView(); }
  if (!$("#sf-filter").hidden) sfFilterPanel();
}
function sfMapView() {
  // keep the keyboard on the same work when its button is drawn again
  const a = document.activeElement, fid = a && a.closest && a.closest("#sf-grid [data-pick], #sf-day [data-pick], #sf-off [data-pick]") ? a.dataset.pick : null;
  // QA #24: drawing again keeps the place the user was looking at (the map's sideways scroll and the page's)
  const keep = [$("#sf-grid"), $("#sf-day"), $("#s-safety")].map((n) => [n, n.scrollLeft, n.scrollTop]);
  const on = sf.docs.filter((d) => sfActive(d, sf.t)), match = new Set(sfVisible().map((d) => d.id)), filt = sfFiltering();
  const k = on.filter((d) => match.has(d.id)).length, np = on.filter((d) => d.type === "permit").length;
  $("#sf-now").textContent = sf.view === "day" ? `하루 작업 ${sf.docs.length}건` + (filt ? ` · 조건 일치 ${match.size}건` : "")
    : on.length ? `${m2hm(sf.t)} 일상 작업 ${on.length - np}건 · 비일상 작업 ${np}건` + (filt ? ` · 조건 일치 ${k}건` : "") : `${m2hm(sf.t)}에 계획된 작업 없음`;      // QA #82
  $("#sf-map-title").textContent = sf.view === "day" ? "하루 일정" : "계획 배치도";
  $(".sf-swipe").textContent = sf.view === "day" ? "← 좌우로 밀어 07:30–21:00 시간대를 봅니다 →" : "← 좌우로 밀어 칼럼 01–20을 봅니다 →";
  $("#sf-grid-h").innerHTML = sf.view === "day" ? `<b>BAY별 하루 일정</b><span>가로 = 시각 07:30–21:00 · 세로선 = 고른 시각 ${m2hm(sf.t)}</span>`
    : `<b>${m2hm(sf.t)} 기준 작업 배치현황</b><span>가로축: 칼럼 01–${sf.data.cols} · 칼럼 간격 12m</span>`;      // QA #80
  document.querySelectorAll("#sf-view button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === sf.view)));
  $("#sf-grid").hidden = sf.view !== "map"; $("#sf-day").hidden = sf.view !== "day";
  // QA #42: the time picker stays over the 하루 일정 too (its vertical line is the picked time)
  $("#sf-profile").hidden = $("#sf-t").hidden = document.querySelector(".sf-ticks").hidden = false;
  if (sf.view === "map") sfMap(on, match, filt); else sfDay(match, filt);
  const off = (sf.view === "map" ? on : []).filter((d) => !d.spans.length), notime = sf.docs.filter((d) => !sfWins(d).length);
  const links = (list) => list.map((d) => `<button type="button" class="linkbtn${filt && !match.has(d.id) ? " dim" : ""}" data-pick="${esc(d.id)}">${esc(d.title)} (${esc(sfWhere(d))})</button>`).join(" ");
  $("#sf-off").hidden = !off.length && !notime.length;
  $("#sf-off").innerHTML = (off.length ? `<span>BAY 밖: ${links(off)}</span> ` : "") + (notime.length ? `<span>시간 미지정 ${notime.length}건: ${links(notime)}</span>` : "");
  const L = [["lg-permit", "허가서 작업"], ["lg-plan", "작업계획서 작업"]];
  if (sf.view === "map") L.push(["lg-route", "이동 경로 개략"], ["lg-band", "칼럼 미지정"]);
  if (filt) L.push(["lg-dim", "조건 밖 (흐리게)"]);
  $("#sf-legend").innerHTML = L.map(([c, l]) => `<span><i class="${c}"></i>${l}</span>`).join("") + `<span class="sf-legend-note">시연용 배치도입니다. 실제 거리와 작업 점유 범위를 나타내지는 않습니다.</span>`;
  sfPickCard();
  if (fid) { const b = document.querySelector(`#sf-grid [data-pick="${CSS.escape(fid)}"], #sf-day [data-pick="${CSS.escape(fid)}"], #sf-off [data-pick="${CSS.escape(fid)}"]`); if (b) b.focus({ preventScroll: true }); }
  for (const [n, x, y] of keep) { if (!n.hidden) { n.scrollLeft = x; n.scrollTop = y; } }
}
const sfBarCls = (d, match, filt) => {
  // a pair shown on the map: from a pair (over the page, or 「계획 배치도에서 보기」), not when the map tab is just opened
  const pr = sf.mode !== "map" || sf.pairOnMap ? sf.pair : null, role = pr ? (pr.reasons[0].cause === d.id ? " pa" : (pr.a === d.id || pr.b === d.id) ? " pb" : " dim") : "";
  return `${d.type === "permit" ? " k-" + d.kind : ""}${sf.pick === d.id ? " picked" : ""}${!pr && filt && !match.has(d.id) ? " dim" : ""}${role}`;
};
const sfBarLabel = (d) => d.type === "permit" ? `${d.label} · ${d.title}` : d.title;
function sfMap(on, match, filt) {
  const D = sf.data, pct = (c) => ((c - 1) / D.cols) * 100;
  let html = `<div class="sf-cols" aria-hidden="true"><span class="sf-axis-name">칼럼</span><div>${Array.from({ length: D.cols }, (_, i) => i + 1).map((c) => `<b style="left:${pct(c) + 50 / D.cols}%">${String(c).padStart(2, "0")}</b>`).join("")}</div></div>`;
  for (let b = 1; b <= D.bays; b++) {
    const lanes = [], bars = [];
    // a work keeps its own lane when it shares columns with another: nothing is coloured for sharing
    const placed = on.filter((d) => d.spans.some((s) => s.bay === b)).map((d) => {
      const cols = d.spans.filter((s) => s.bay === b && s.c0);
      return { d, band: !cols.length, c0: cols.length ? Math.min(...cols.map((s) => s.c0)) : 1, c1: cols.length ? Math.max(...cols.map((s) => s.c1)) : D.cols };
    }).sort((x, y) => x.c0 - y.c0 || x.c1 - y.c1);
    const unk = placed.filter((p) => p.band).map((p) => `<button type="button" class="sf-unk${sfBarCls(p.d, match, filt)}" data-pick="${esc(p.d.id)}">${esc(sfBarLabel(p.d))}</button>`);
    for (const p of placed.filter((x) => !x.band)) {
      let lane = lanes.findIndex((end) => end < p.c0);
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = p.c1;
      const d = p.d, moving = d.is_route && (!d.move || (hm2m(d.move.start) <= sf.t && sf.t < hm2m(d.move.end)));
      const label = d.is_route ? `${d.label} · ` + (moving ? "이동 경로 개략" : `이동 ${d.move.start}–${d.move.end}`) : sfBarLabel(d);
      bars.push(`<button type="button" class="sf-bar ${d.is_route ? "route" + (moving ? "" : " idle") : d.type}${sfBarCls(d, match, filt)}" data-pick="${esc(d.id)}"`
        + ` style="left:${pct(p.c0)}%;width:${((p.c1 - p.c0 + 1) / D.cols) * 100}%;top:${lane * 3.6 + .4}rem" aria-label="${esc(`${sfTag(d)} ${d.title}, ${sfWhere(d)}, ${sfTimes(d)}`)}"><span>${esc(label)}</span></button>`);
    }
    html += `<div class="sf-bay"><span class="sf-bay-name">${b}BAY</span><div class="sf-track" style="height:${Math.max(1, lanes.length) * 3.6 + .8}rem">${bars.join("")}</div>`
      + (unk.length ? `<p class="sf-unks"><span>상세 위치 미지정</span>${unk.join("")}</p>` : "") + `</div>`;
  }
  $("#sf-grid").innerHTML = html;
}
// 하루 일정: per BAY, every work on a 07:30–21:00 axis, packed into lanes; the line is the chosen time
function sfDay(match, filt) {
  const x = (m) => ((Math.max(T0, Math.min(T1, m)) - T0) / (T1 - T0)) * 100;
  const ticks = [450, 540, 720, 900, 1080, 1260];
  let html = `<div class="sf-day-axis" aria-hidden="true"><span class="sf-axis-name">시각</span><div>${ticks.map((m) => `<b style="left:${x(m)}%">${m2hm(m)}</b>`).join("")}</div></div>`;
  for (const b of [1, 2, 3, 4, 9]) {
    const items = [];
    const inBay = (d) => b === 9 ? !d.spans.length : d.spans.some((s) => s.bay === b);
    for (const d of sf.docs.filter(inBay)) for (const w of sfWins(d)) items.push({ d, a: hm2m(w.start), z: wEnd(w) });
    if (!items.length) continue;
    items.sort((p, q) => p.a - q.a || q.z - p.z);
    const lanes = [];
    const bars = items.map((it) => {
      let lane = lanes.findIndex((end) => end <= it.a);
      if (lane < 0) { lane = lanes.length; lanes.push(0); }
      lanes[lane] = it.z;
      const d = it.d;
      return `<button type="button" class="sf-bar ${d.type}${sfBarCls(d, match, filt)}" data-pick="${esc(d.id)}" style="left:${x(it.a)}%;width:${x(it.z) - x(it.a)}%;top:${lane * 3.2 + .4}rem"`
        + ` aria-label="${esc(`${sfTag(d)} ${d.title}, ${sfWhere(d)}, ${m2hm(it.a)}–${m2hm(it.z)}`)}"><span>${esc(sfBarLabel(d))}</span></button>`;
    }).join("");
    html += `<div class="sf-bay"><span class="sf-bay-name">${b === 9 ? "밖" : b + "BAY"}</span><div class="sf-track sf-day-track" data-axis style="height:${lanes.length * 3.2 + .8}rem">${bars}<i class="sf-day-now" style="left:${x(sf.t)}%"></i></div></div>`;
  }
  $("#sf-day").innerHTML = html;
}
function sfPickCard() {
  const d = sf.pick && sfDoc(sf.pick), box = $("#sf-pick");
  box.hidden = !d;
  if (!d) return;
  const note = (sf.view === "map" && !sfActive(d, sf.t) ? `<p class="hint">${m2hm(sf.t)}에는 계획돼 있지 않습니다.</p>` : "")
    + (sfVisible().some((x) => x.id === d.id) ? "" : `<p class="hint">목록 조건 밖이라 목록에는 보이지 않습니다. <button type="button" class="linkbtn" data-unfilter>필터 초기화</button></p>`);
  box.innerHTML = `<div>${sfTagHtml(d)} <b>${esc(d.title)}</b>`
    + `<p class="hint">${esc(d.type === "permit" ? d.permit_no : d.id)} · ${esc(sfWho(d))} · ${esc(sfWhere(d))} · ${esc(sfTimes(d))}${d.workers ? ` · ${d.workers}명` : ""}</p>${note}</div>`
    + `<button type="button" class="btn small" data-open="${esc(d.id)}">${icon("i-file")}문서 열기</button>`;
}
function sfSelect(id, moveTime, quiet) {
  sf.pick = id; sf.pair = null;
  const d = sfDoc(id), map = $(".sf-map"), top0 = map.getBoundingClientRect().top;
  if (d && sf.fold.has(sfBay(d))) {                                              // a work picked on the map: its folded BAY opens
    sf.fold.delete(sfBay(d)); sfRows();
    $("#s-safety").scrollTop += map.getBoundingClientRect().top - top0;          // ...and the map does not move (QA #24)
  }
  if (d && moveTime && sfWins(d).length && !sfActive(d, sf.t)) {
    // the next of its windows from the chosen time, else its first one
    const s = sfWins(d).map((w) => hm2m(w.start)), to = s.find((m) => m >= sf.t) ?? s[0];
    sfSetTime(to); if (!quiet) toast(`배치도 시각을 ${m2hm(to)}로 옮겼습니다`);
  } else sfMapView();
  document.querySelectorAll("#sf-rows tr[data-id]").forEach((tr) => tr.classList.toggle("picked", tr.dataset.id === id));
}
// 현장 확인 일정: 대면허가 (PTW 2중점검 Y, by start) and 정전·격리 (LOTO permits with the foreman's off/on plan)
function sfSched() {
  const P = sf.data.permits, face = sfFace(), iso = P.filter((p) => p.kind === "loto");
  $("#sf-schedtabs").innerHTML = [["face", `대면허가 ${face.length}`], ["iso", `정전·격리 ${iso.length}`]]
    .map(([k, l]) => `<button type="button" data-side="${k}" aria-pressed="${sf.side === k}">${l}</button>`).join("");
  const list = (sf.side === "face" ? face : iso).slice().sort((a, b) => sfFirst(a) - sfFirst(b));
  $("#sf-sched-note").textContent = sf.side === "face" ? "허가서에 PTW 2중점검 Y로 적힌 작업입니다. 허가 기간 중 실제 작업일마다 아침 대면허가 대상입니다. 작업 시작 시간순으로 표시했습니다."
    : "정전·격리 대상 설비와 작업반장이 제출한 차단·복구 계획입니다. 작업 시작 시간순으로 표시했습니다.";
  $("#sf-sched-list").innerHTML = list.map((d) => `<li><button type="button" class="sf-srow${sf.pick === d.id ? " picked" : ""}" data-open="${esc(d.id)}">`
    + `<span class="sf-stime">${esc(sfWins(d)[0] ? sfWins(d)[0].start : "—")}</span><span class="sf-sbody">${sfTagHtml(d)} <b>${esc(d.title)}</b>`
    + `<span class="hint">${esc(sf.side === "face" ? `${sfWhere(d)} · ${sfWho(d)} · ${sfTimes(d)}${sfPeriod(d) ? ` · ${sfPeriod(d)}` : ""}` : `${d.place} · ${sfTimes(d)}${d.isolation ? ` · 계획: ${d.isolation}` : ""}`)}</span></span>`
    + `${sfStateHtml(d)}</button></li>`).join("") || `<li class="hint">해당 작업이 없습니다.</li>`;
}
// 쌍작업 위험탐지 ------------------------------------------------------
// The rules (server/pairs.py, pair_rules.json) judge every 일상×비일상 and 비일상×비일상 pair; this shows the result:
// priority = 강도 S × 노출 E, each pair with why (조건 → 원인 → 사고), the facts it stands on, what to do, and the
// pairs that look close but were not raised, with the reason.
const PRI = { 1: ["1순위", "즉시 조정"], 2: ["2순위", "조건부 병행"], 3: ["3순위", "확인 필요"] };
Object.assign(sf, { det: null, mode: "pairs", ptab: "all", pkind: "all", openPair: null, pair: null });
const sfPairsOf = (id) => sf.det ? sf.det.pairs.filter((p) => p.a === id || p.b === id) : [];
const sfPairDocs = (p) => [sfDoc(p.a), sfDoc(p.b)];
const sfWhen = (w) => w.kind === "overlap" ? `${w.start}–${w.end} 겹침 ${w.min}분` : w.kind === "sequence" ? `${w.start} 끝 → ${w.gap}분 뒤 시작(겹치지 않음)` : "시간 미상";
function sfPairVisible() {
  if (sf.ptab === "near" || sf.ptab === "ai") return [];
  return sf.det.pairs.filter((p) => (sf.ptab === "all" || p.priority === +sf.ptab) && (sf.pkind === "all" || p.kind === sf.pkind));
}
async function sfDetect(auto) {
  const b = $("#sf-detect"), oldKey = sf.pair && sf.pair.key; b.disabled = true; b.innerHTML = `분석 중…`; $("#sfn-detect").disabled = true;
  try {
    const r = await fetch("/api/safety/detect", { method: "POST" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.detail || `서버 오류 ${r.status}`);
    sf.det = j; sf.mode = "pairs"; sf.post = null; postLoad();
    b.innerHTML = `${icon("i-restart")}다시 찾기`;
    $("#sf-detect-note").textContent = `${new Date().toTimeString().slice(0, 5)} 탐지 · 전체 ${sf.docs.length}건 대상`;
    sfResults(); sfRefresh(); sf.rv = null; sfRvLoad();
    sf.pair = null; sf.openPair = null;
    if (sf.nearKey && !j.near.some((n) => sfNearKey(n) === sf.nearKey)) {
      sf.nearKey = null; if ($("#sf-panel").dataset.mode === "near") { $("#sf-panel").hidden = true; $("#sf-panel").dataset.mode = ""; }
    } else if (sf.nearKey && $("#sf-panel").dataset.mode === "near" && !$("#sf-panel").hidden) $("#sf-p-body").innerHTML = sfNearBody(j.near.find((n) => sfNearKey(n) === sf.nearKey));
    if (sfInline() && !auto) { const vis = sfPairVisible(), same = vis.find((x) => x.key === oldKey), id = (same || vis[0] || {}).id; if (id) sfOpenPair(id, true); else sfPairsView(); }
    if (!auto) $("#sf-res").focus?.();
  } catch (err) {
    b.innerHTML = `위험 쌍 찾기${icon("i-search")}`;
    toast(`탐지하지 못했습니다: ${err.message}`);
  }
  b.disabled = false; $("#sfn-detect").disabled = false; sfNav();
}
const sfDayLabel = (shift = 0) => { const [y, m, d] = sf.data.date.split("-").map(Number), t = new Date(y, m - 1, d + shift);
  return `${t.getFullYear()}.${String(t.getMonth() + 1).padStart(2, "0")}.${String(t.getDate()).padStart(2, "0")}(${"일월화수목금토"[t.getDay()]})`; };
// QA #83: the time now in Korea, kept current each minute (only its text: the menu is not drawn again)
const sfClockNow = () => new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date());
(function sfClockTick() { const c = document.getElementById("sfn-clock"); if (c) c.textContent = sfClockNow(); setTimeout(sfClockTick, 60000 - (Date.now() % 60000) + 50); })();
document.addEventListener("visibilitychange", () => { const c = document.getElementById("sfn-clock"); if (c && !document.hidden) c.textContent = sfClockNow(); });
// QA #75–#77: 검토 통과 인접 작업 — pairs near each other that the rules looked at and did not alarm (not "safe": the note says so).
// A row is one line (일상/비일상 + the two titles); picking it shows why there is no alarm and the two documents.
const SF_NEAR = "검토 통과 인접 작업", SF_NEAR_NOTE = "서류의 시간·위치·설비를 규칙으로 검토했을 때 경보 조건에 해당하지 않은 작업쌍입니다. 안전 확인이나 작업 승인을 뜻하지 않습니다.";
const sfNearKey = (x) => [x.a, x.b].sort().join("|");
const sfNearKind = (x) => sfDoc(x.a).type === "permit" && sfDoc(x.b).type === "permit" ? "NN" : "RN";
const sfNearVisible = () => sf.det ? sf.det.near.filter((x) => sf.pkind === "all" || sfNearKind(x) === sf.pkind) : [];
// 일상 (작업계획서) / 비일상 (허가서): a badge of its own (the kind badge sfTagHtml stays as it is elsewhere)
const sfCls = (d) => `<span class="sf-cls ${d.type === "permit" ? "non" : "rt"}">${d.type === "permit" ? "비일상" : "일상"}</span>`;
function sfNearRow(x) {
  const A = sfDoc(x.a), B = sfDoc(x.b), k = sfNearKey(x), on = sf.nearKey === k;
  return `<li><button type="button" class="sf-nrow${on ? " picked" : ""}" data-near="${esc(k)}"${on ? ' aria-current="true"' : ""} title="${esc(`${sfNo(A)} ${A.title} × ${sfNo(B)} ${B.title}`)}">`
    + `${sfCls(A)}<span class="sf-nt">${esc(A.title)}</span><em aria-hidden="true">×</em>${sfCls(B)}<span class="sf-nt">${esc(B.title)}</span></button></li>`;
}
function sfNearBody(x) {
  const A = sfDoc(x.a), B = sfDoc(x.b);
  const side = (d) => `<div class="sf-pdoc"><p>${sfCls(d)} ${d.type === "permit" ? sfTagHtml(d) : ""} <b>${esc(d.title)}</b></p>`
    + `<p class="hint">${esc(sfNo(d))} · ${esc(sfWho(d))}<br>${esc(sfWhere(d))} · ${esc(sfTimes(d))}</p>`
    + `<button type="button" class="btn small" data-open="${esc(d.id)}">${icon("i-file")}문서 열기</button></div>`;
  return `<div class="sf-pc-head"><div class="sf-pc-top"><p class="sf-pc-crumb">${SF_NEAR}</p><span class="sf-pc-pill near">경보 없음</span></div>`
    + `<h3>${esc(A.title)} × ${esc(B.title)}</h3><p class="sf-pc-docs">${esc(sfNo(A))} × ${esc(sfNo(B))}</p></div>`
    + `<h4 class="sf-pc-h">검토 통과 근거</h4><p class="sf-near-why">${esc(x.why.text)}</p>` + sfAiState(sfNearKey(x))
    + `<div class="sf-pdocs2">${side(A)}${side(B)}</div><p class="hint sf-near-note">${SF_NEAR_NOTE}</p>`
    + `<div class="sf-ai-review" data-rv-a="${esc(x.a)}" data-rv-b="${esc(x.b)}"><h4 class="sf-pc-h">AI 검토 권장 <small>규칙 판정 아님</small></h4>`
    + `<p class="hint">규칙이 다루지 않는 관계가 있는지 AI에게 이 쌍만 한 번 물어봅니다. 결과는 위험 쌍 목록·순위·점수에 들어가지 않습니다.</p>`
    + `<button type="button" class="btn small" data-rvgo>AI 검토 요청</button><div class="sf-rv-out" role="status" aria-live="polite">${sfRvKept(sfNearKey(x))}</div></div>`;
}
function sfOpenNear(k, quiet) {
  const x = sf.det && sf.det.near.find((n) => sfNearKey(n) === k); if (!x) return;
  sf.nearKey = k; sf.open = null; sf.req++;
  if (sfInline() && (sf.ptab === "near" || sf.ptab === "ai")) {
    $("#sf-panel").hidden = true;
    sfPairsView(); const d = $("#sf-pdetail"); d.scrollTop = 0; if (!quiet) d.focus({ preventScroll: true });
  } else {
    const P = $("#sf-panel"), A = sfDoc(x.a), B = sfDoc(x.b); P.hidden = false; P.dataset.mode = "near";
    $("#sf-p-kind").textContent = SF_NEAR; $("#sf-p-kind").className = "eyebrow";
    $("#sf-p-title").textContent = `${A.title} × ${B.title}`; $("#sf-p-meta").textContent = `${sfNo(A)} × ${sfNo(B)}`;
    $("#sf-p-tabs").hidden = true; $("#sf-p-note").hidden = true; $("#sf-p-pos").textContent = "";
    $("#sf-p-prev").disabled = true; $("#sf-p-next").disabled = true;
    $("#sf-p-body").innerHTML = sfNearBody(x); $("#sf-p-body").scrollTop = 0;
    $("#sf-p-close").focus({ preventScroll: true });
    sfPairsView();
  }
  sfSaveView();
}
// the pairs counted for the donut, the menu and the 순위 tabs: those of the 작업 조합 picked (근접 apart)
const sfKin = () => sf.det ? sf.det.pairs.filter((p) => sf.pkind === "all" || p.kind === sf.pkind) : [];
function sfDonut() {
  if (!sf.det) return;
  const kin = sfKin(), n = [1, 2, 3].map((k) => kin.filter((p) => p.priority === k).length), all = kin.length;
  const R0 = 46, C = 2 * Math.PI * R0, col = ["var(--ch1)", "var(--ch2)", "var(--ch3)"], ink = ["#fff", "#2B2400", "#0B2347"];
  let at = 0, arcs = "", labels = "";
  n.forEach((v, i) => {
    if (!v) return;
    const f = v / all, len = f * C;
    arcs += `<circle r="${R0}" cx="60" cy="60" fill="none" stroke="${col[i]}" stroke-width="24" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-at * C}" transform="rotate(-90 60 60)"/>`;
    const mid = (at + f / 2) * 2 * Math.PI - Math.PI / 2;
    if (f >= 0.09) labels += `<text x="${60 + R0 * Math.cos(mid)}" y="${60 + R0 * Math.sin(mid)}" fill="${ink[i]}" class="sf-dn-lab">${v}쌍</text>`;
    at += f;
  });
  const sum = n.map((v, i) => `${PRI[i + 1][0]} ${v}쌍`).join(", ");
  $("#sf-res-pri").innerHTML = `<svg class="sf-donut" viewBox="0 0 120 120" role="img" aria-label="${sf.pkind === "all" ? "전체" : "고른 작업 조합의"} 위험 쌍 ${all}쌍: ${sum}">`
    + `<circle r="${R0}" cx="60" cy="60" fill="none" stroke="var(--surface-2)" stroke-width="24"/>${arcs}${labels}`
    + `<text x="60" y="53" class="sf-dn-c1">${sf.pkind === "all" ? "전체 위험 쌍" : "고른 조합"}</text><text x="60" y="73" class="sf-dn-c2">${all}<tspan class="sf-dn-u">쌍</tspan></text></svg>`
    + `<ul class="sf-dn-leg">${[1, 2, 3].map((k) => `<li><button type="button" class="sf-dn-row p${k}" data-ptab="${k}" aria-pressed="${sf.ptab === String(k)}">`
      + `<i class="sf-dn-dot" aria-hidden="true"></i><span><small>${PRI[k][0]}</small><b>${PRI[k][1]}</b></span><em>${n[k - 1]}<small>쌍</small></em></button></li>`).join("")}</ul>`;
}
// 쌍 하이브리드 (design §8.1·§19.1): what the foremen's confirmed answers changed — new, changed and gone alarms
const sfHy = () => (sf.det && sf.det.hybrid) || { permits: [], answers: 0, changes: { new: [], kept: [], gone: [] } };
// Codex A6: which version of a document the day's judgement used (서류 기준 / 제출본 반영) and what went in
const sfVer = (id) => (sf.det && sf.det.hybrid && (sf.det.hybrid.versions || {})[id]) || (sf.subs && (sf.subs._versions || {})[id]) || null;
const sfVerText = (id) => { const v = sfVer(id); return v && v.version === "제출본 반영" ? `제출본 반영(${v.used.join("·")})` : "서류 기준"; };
const sfVerVals = (id) => { const v = sfVer(id); return v && v.version === "제출본 반영" ? Object.entries(v.values || {}).map(([k, x]) => ` · ${k} ${x}`).join("") + (v.by ? ` · ${v.by} 제출본` : "") : ""; };
const sfVerLine = (ids) => `<p class="hint sf-ver">판정 자료: ${ids.filter((i) => sfDoc(i)).map((i) => esc(`${sfNo(sfDoc(i))} ${sfVerText(i)}${sfVerVals(i)}`)).join(" / ")}</p>`;
function sfVerNote(ids) {
  const sub = [...new Set(ids)].filter((i) => sfDoc(i) && sfVerText(i) !== "서류 기준");
  return sub.length ? `판정 자료: ${sub.map((i) => `${sfNo(sfDoc(i))} ${sfVerText(i)}`).join(" · ")}, 나머지는 서류 기준. ` : "판정 자료: 서류 기준. ";
}
const sfHyPri = (v) => v ? `${PRI[v.priority] ? PRI[v.priority][0] : "-"} ${v.score}점` : "없음";
const sfHyRow = (x) => `<li><b>${esc(x.cause)} × ${esc(x.exposed)}</b> ${esc(x.name)} · ${sfHyPri(x.before)} → ${sfHyPri(x.after)}${x.moved ? " (바뀜)" : ""}`
  + (x.from.length ? `<br><span class="hint">확인 사실: ${x.from.map((e) => `${esc(e.doc)} 「${esc(e.value)}」`).join(" · ")} (작업반장 답변 · 반장 답변 확인)</span>` : "") + `</li>`;
// the three columns (design §19.8): 새 경보 / 유지·변경 / 답만으로는 사라질 경보 — the last stays in the current list on the
// documents' word (pairs.floor): a reading never lifts an alarm, the safety manager does
function sfHyTable(c) {
  const col = (k, h) => `<section><h4>${h} <em>${c[k].length}</em></h4>${c[k].length ? `<ul class="sf-hy">${c[k].map(sfHyRow).join("")}</ul>` : `<p class="hint">없음</p>`}</section>`;
  return `<div class="sf-hy3">${col("new", "새 경보")}${col("kept", "유지·변경")}${col("gone", "답으로는 해소 · 문서 기준 유지")}</div>`;
}
function sfHybridPair(p) {
  const c = sfHy().changes, f = (xs) => xs.filter((x) => x.key === p.key), mine = { new: f(c.new), kept: f(c.kept), gone: f(c.gone) };
  if (!mine.new.length && !mine.kept.length && !mine.gone.length) return "";
  return `<details class="sf-pc-d"><summary>입력 보강 전후</summary><p class="hint">작업반장이 확인한 답(제출본)을 규칙 입력에 더하기 전과 뒤입니다. 점수·순위는 규칙이 냅니다.</p>`
    + sfHyTable(mine) + `</details>`;
}
function sfHybridHow() {
  const h = sfHy(), c = h.changes;
  const sub = h.submitted || [];
  if (!h.permits.length && !sub.length) return `<p class="hint">이 작업일의 작업반장 제출본에 판정에 넣을 확인 값이 아직 없어, 서류 기준으로 판정했습니다.</p>`;
  return `<p>작업반장 제출본 ${h.permits.length}건의 확인 사실 ${h.answers}개${sub.length ? `와 제출본에서 고친 위치·시간(${esc(sub.map((i) => sfNo(sfDoc(i))).join(", "))})` : ""}를 규칙 입력에 더했습니다(제출본 반영). 나머지 문서는 서류 기준입니다.</p>` + sfHyTable(c)
    + `<p class="hint">반장 답만으로는 경보를 내리거나 없애지 않습니다. 셋째 칸의 경보도 문서 기준으로 현재 목록에 그대로 있고, 해제는 안전관리자가 판단합니다.</p>`;
}
function sfResults() {
  const R = sf.det, st = R.stats, n = (k) => st.by_priority[k] || 0;
  $("#sf-res").hidden = false;
  $("#sf-res-title").textContent = `${sfDayLabel()} 작업 현황 기준`;      // QA #74: the work day, not the counts (they are in the donut and the menu)
  // QA #84: four steps, each a plain sentence and its count. ③ counts the pairs whose place has to be checked too (no
  // column or no place written); ④ is not a narrowing of ③ (a shared crane or power line has no BAY), so no arrows
  const conf = R.pairs.filter((p) => p.reasons[0].when.kind === "overlap" && p.E > 1).length, rest = R.pairs.length - conf;
  const why = (k) => R.pairs.filter((p) => !(p.reasons[0].when.kind === "overlap" && p.E > 1) && (k === "other" ? !["sequence", "unknown"].includes(p.reasons[0].when.kind) : p.reasons[0].when.kind === k)).length;
  const sub4 = [conf && `작업시간이 겹쳐 위험이 전달될 수 있는 조합 ${conf}쌍`, why("sequence") && `앞 작업이 끝난 뒤 확인이 필요한 조합 ${why("sequence")}쌍`,
    why("unknown") && `작업 시간이 없어 확인이 필요한 조합 ${why("unknown")}쌍`, why("other") && `위치·설비 정보가 부족해 확인이 필요한 조합 ${why("other")}쌍`].filter(Boolean);
  void rest;
  $("#sf-funnel").innerHTML = [["① 전체 작업 조합", st.candidates, `비일상 작업 간 ${st.nn}쌍 · 일상–비일상 작업 간 ${st.rn}쌍`], ["② 작업시간이 겹치는 조합", st.time, ""],
    ["③ 같은 BAY 또는 위치 확인이 필요한 조합", st.time_bay + st.unknown_place, st.unknown_place ? `위치가 적히지 않았거나 칼럼이 없어 확인이 필요한 조합 ${st.unknown_place}쌍 포함` : ""],
    ["④ 조정·확인이 필요한 조합", R.pairs.length, sub4.join(" · ")]]
    .map(([a, n, b]) => `<li><p><b>${a}</b><em>${n}쌍</em></p>${b ? `<small>${b}</small>` : ""}</li>`).join("");
  const hy = $("#sf-hybrid"); if (hy) hy.innerHTML = `<h3>입력 보강 전후</h3>${sfHybridHow()}`;
  void n; sfDonut(); sfNav();
}
// #66 the menu: 위험 쌍 (all) and its 순위 + 근접, 계획 배치도, 문서 목록, 현장 게시; the toggle only folds the sub-items
Object.assign(sf, { navOpen: true, restoreKey: null });
function sfNav() {
  if (!sf.data) return;
  const D = sf.data, kin = sfKin(), on = (m) => sf.mode === m;
  // QA #72: the day, what it is, where, a greeting, and how many documents came in
  const run = D.permits.filter((p) => p.running).length;
  // QA #83: the day before the work day (the review is done then), the time now (KST), a greeting, the work day's counts
  void run;
  $("#sfn-day").innerHTML = `<b class="sf-nd-date">${esc(sfDayLabel(-1))}</b><span class="sf-nd-now">현재 시각 <b id="sfn-clock">${sfClockNow()}</b></span>`
    + `<p class="sf-nd-hi">안녕하세요.<br><b>${esc(String(D.factory || "").replace(/([가-힣])(\d)/, "$1 $2"))} 안전관리자님</b></p>`
    + `<dl class="sf-nd-n"><dt>비일상 작업</dt><dd>${D.permits.length}건</dd><dt>일상 작업</dt><dd>${D.plans.length}건</dd><dt>총 작업</dt><dd>${D.permits.length + D.plans.length}건</dd></dl>`;
  $("#sfn-note").textContent = $("#sf-detect-note").textContent;
  const sub = [["1", PRI[1].join(" · ")], ["2", PRI[2].join(" · ")], ["3", PRI[3].join(" · ")], ["near", SF_NEAR], ["ai", "AI 검토 권장"]]
    .map(([k, l]) => `<li><button type="button" class="sf-nav-sub k${k}" data-ptab="${k}" aria-pressed="${on("pairs") && sf.ptab === k}"><i aria-hidden="true"></i><span>${l}</span>`
      + `<em>${sf.det ? (k === "ai" ? sfAiCount() : k === "near" ? sfNearVisible().length : kin.filter((p) => p.priority === +k).length) : "–"}</em></button></li>`).join("");
  const ae = document.activeElement, keep = ae && ae.closest && ae.closest("#sfn-list")
    ? ["data-ptab", "data-navall", "data-navtg", "data-navmain", "data-navpost"].map((a) => ae.hasAttribute(a) ? `[${a}${ae.getAttribute(a) ? `="${ae.getAttribute(a)}"` : ""}]` : "").find(Boolean) : null;
  $("#sfn-list").innerHTML = `<li class="sf-nav-pairs"><div class="sf-nav-row"><button type="button" class="sf-nav-btn" data-navall aria-pressed="${on("pairs") && sf.ptab === "all"}">위험 쌍<em>${sf.det ? kin.length : "–"}</em></button>`
    + `<button type="button" class="sf-nav-tg" data-navtg aria-expanded="${sf.navOpen}" aria-controls="sfn-pri" aria-label="위험 쌍 순위 ${sf.navOpen ? "접기" : "펼치기"}">${icon("i-right")}</button></div>`
    + `<ul class="sf-nav-pri" id="sfn-pri"${sf.navOpen ? "" : " hidden"}>${sub}</ul></li>`
    + `<li><button type="button" class="sf-nav-btn" data-navmain="map" aria-pressed="${on("map")}">계획 배치도</button></li>`
    + `<li><button type="button" class="sf-nav-btn" data-navmain="docs" aria-pressed="${on("docs")}">문서 목록<em>${sf.docs.length}</em></button></li>`
    + `<li><button type="button" class="sf-nav-btn" data-navpost aria-pressed="${sf.mode === "post"}"${sf.det ? "" : " disabled"}>현장 게시 서류</button></li>`;
  if (keep) $(`#sfn-list ${keep}`)?.focus();
}
function sfModeView() {
  $("#sf-body").dataset.mode = sf.mode; $(".sf-wrap").dataset.main = sf.mode; sfNav();
  document.querySelectorAll("#sf-jump [data-main]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.main === (sf.mode === "post" ? "pairs" : sf.mode))));
}
function sfMain(k) {
  if (k === "post" && !sf.det) return;
  sf.mode = k; sfModeView(); sfPairsView();
  if (k === "map") sfMapView();
  if (k === "pairs" && sfInline() && sf.det) {                 // the pair seen last comes back beside the list
    const vis = sfPairVisible(), last = [sf.openPair, sf.lastPair].find((x) => sf.det.pairs.some((p) => p.id === x));
    const id = sf.ptab === "near" || sf.ptab === "ai" ? null : last ? (vis.some((p) => p.id === last) ? last : null) : (vis[0] || {}).id;
    if (id) sfOpenPair(id, true);
  }
  sfSaveView(); requestAnimationFrame(sfMoreHint);
}
// QA #42: the list scrolls inside; while 2·3순위 are further down, a line under it says so
function sfMoreHint() {
  const L = $("#sf-plist"), m = $("#sf-more");
  if (sf.mode !== "pairs" || !sf.det || L.scrollHeight <= L.clientHeight + 4) { m.hidden = true; return; }
  const bottom = L.scrollTop + L.clientHeight, rows = [...L.querySelectorAll(".sf-prow, .sf-nrow")].filter((r) => r.offsetTop + r.offsetHeight > bottom + 2);
  m.hidden = bottom >= L.scrollHeight - 4;
  m.textContent = rows.length ? `↓ 아래로 ${rows.length}${sf.ptab === "near" ? "건" : "쌍"} 더 있습니다` : "↓ 아래로 스크롤하여 더 보기";
}
function sfPairsView() {
  sfModeView();
  if (!sf.det) { $("#sf-plist").innerHTML = `<li class="sf-empty">쌍작업 위험을 탐지하는 중입니다…</li>`; return; }
  const all = sf.det.pairs, list = sfPairVisible(), kin = all.filter((p) => sf.pkind === "all" || p.kind === sf.pkind);   // counts follow the kind filter (#53)
  if ((sf.ptab === "near" || sf.ptab === "ai") && sfInline()) {
    const x = (sf.ptab === "ai" ? sf.det.near : sfNearVisible()).find((n) => sfNearKey(n) === sf.nearKey);
    $("#sf-pdetail").innerHTML = x ? `<div class="sf-pd-body">${sfNearBody(x)}</div>` : `<p class="sf-pd-empty hint">목록에서 인접 작업을 선택하세요.</p>`;
    if (sf.pair) { sf.pair = null; sf.openPair = null; history.replaceState(null, "", `#safety/${sf.data.date}`); }
  } else if (sfInline() && sf.pair && !list.some((p) => p.id === sf.pair.id)) {
    $("#sf-pdetail").innerHTML = `<p class="sf-pd-empty hint">고른 위험 쌍(${esc(sf.pair.id)})이 지금 목록 조건에 없습니다.<br>목록에서 위험 쌍을 다시 고르세요.</p>`;
    sf.pair = null; sf.openPair = null;
    history.replaceState(null, "", `#safety/${sf.data.date}`);
  }
  $("#sf-post-btn").closest("div").hidden = sf.mode === "post";
  if (sf.mode === "post") { if (!sf.post) postLoad(); postRender(); }
  document.querySelectorAll("#sf-mode button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.mode === sf.mode)));
  document.querySelectorAll("#sf-res-pri [data-ptab]").forEach((x) => x.setAttribute("aria-pressed", String(sf.ptab === x.dataset.ptab)));
  const ae = document.activeElement, fz = ae && ae.closest && ae.closest("#sf-ptabs, #sf-res-pri, #sfn-list");
  const refocus = fz ? `#${fz.id} ${ae.dataset.ptab ? `[data-ptab="${ae.dataset.ptab}"]` : ae.matches("[data-navall]") ? "[data-navall]" : ae.matches("[data-navtg]") ? "[data-navtg]" : "button"}` : null;
  $("#sf-ptabs").innerHTML = [["all", "전체"], ["1", "1순위"], ["2", "2순위"], ["3", "3순위"]]
    .map(([k, l]) => `<button type="button" data-ptab="${k}" aria-pressed="${sf.ptab === k}">${l} ${kin.filter((p) => k === "all" || p.priority === +k).length}</button>`).join("");
  $("#sf-pkind").value = sf.pkind;
  sfDonut();
  if (refocus) document.querySelector(refocus)?.focus();
  $("#sf-near").hidden = sf.ptab === "near" || sf.ptab === "ai";
  // #69 one short row per pair: 순위 · P번호 · 위험 조합, and the two document numbers (several pairs share a title)
  $("#sf-plist").innerHTML = sf.ptab === "ai" ? sfAiList() : sf.ptab === "near" ? `<li class="sf-near-head hint">${SF_NEAR_NOTE}</li>` + (sfNearVisible().map(sfNearRow).join("")
    || `<li class="sf-empty">해당하는 인접 작업이 없습니다.</li>`) : list.map((p) => {
    const [A, B] = sfPairDocs(p), on = sf.pair && sf.pair.id === p.id;
    return `<li><button type="button" class="sf-prow p${p.priority}${on ? " picked" : ""}" data-pair="${p.id}"${on ? ` aria-current="true"` : ""}`
      + ` title="${esc(`${sfNo(A)} ${A.title} × ${sfNo(B)} ${B.title}`)}">`
      + `<span class="sf-pbadge sm p${p.priority}">${PRI[p.priority][0]}</span><span class="sf-pid">${p.id}</span>`
      + `<span class="sf-ptitle">${esc(p.title)}${p.judgement === "판정보류" ? `<span class="sf-gap">정보 부족</span>` : ""}</span>`
      + `<span class="sf-pnos">${esc(sfNo(A))} × ${esc(sfNo(B))}</span></button></li>`;
  }).join("") || `<li class="sf-empty">이 조건의 위험 쌍이 없습니다.</li>`;
  if (sf.ptab !== "near" && sf.ptab !== "ai") $("#sf-plist").insertAdjacentHTML("beforeend", sfAiEntry());   // narrow screens: the entry at the list's end
  requestAnimationFrame(sfMoreHint);
  $("#sf-near-sum").textContent = `${SF_NEAR} ${sfNearVisible().length}쌍`;
  $("#sf-near-list").innerHTML = sfNearVisible().map(sfNearRow).join("");
}
function sfOpenPair(id, quiet) {
  const p = sf.det && sf.det.pairs.find((x) => x.id === id); if (!p) return;
  sf.openPair = sf.lastPair = id; sf.open = null; sf.req++; sf.pair = p; sf.pick = null;
  if (!sfPairVisible().some((x) => x.id === id)) { sf.ptab = "all"; sf.pkind = "all"; }
  const r = p.reasons[0];
  if (r.when.start) sfSetTime(hm2m(r.when.kind === "sequence" ? r.when.end : r.when.start));   // the map shows the two works when they meet
  history.replaceState(null, "", `#safety/${sf.data.date}/${id}`);
  if (sfInline()) {
    const [A, B] = sfPairDocs(p), d = $("#sf-pdetail");
    $("#sf-panel").hidden = true;
    void A; void B;
    d.innerHTML = sfPairHead(p) + `<div class="sf-pd-body">${sfPairBody(p)}</div>`;
    d.scrollTop = 0;
    if (!quiet) d.focus({ preventScroll: true });
    sfPairsView(); sfMapView(); sfSaveView();
    return;
  }
  const P = $("#sf-panel"); P.hidden = false; P.dataset.mode = "pair";
  $("#sf-p-kind").textContent = `${PRI[p.priority][0]} · ${PRI[p.priority][1]} · ${p.judgement}`;
  $("#sf-p-kind").className = `eyebrow sf-pk p${p.priority}`;
  $("#sf-p-title").textContent = r.headline || p.title;
  const [A, B] = sfPairDocs(p);
  $("#sf-p-meta").textContent = `${p.id} · ${sfNo(A)} × ${sfNo(B)} · ${sfWhen(r.when)} · ${p.kind === "NN" ? "비일상작업끼리" : "일상작업 × 비일상작업"}`;
  $("#sf-p-tabs").hidden = true; $("#sf-p-note").hidden = true;
  const list = sfPairVisible(), i = list.findIndex((x) => x.id === id);
  $("#sf-p-pos").textContent = i < 0 ? "목록 밖" : `${i + 1} / ${list.length}`;
  $("#sf-p-prev").disabled = i <= 0; $("#sf-p-next").disabled = i < 0 || i >= list.length - 1;
  $("#sf-p-body").innerHTML = `<p class="sf-pc-docs">${esc(sfNo(sfDoc(r.cause)))} ${esc(sfDoc(r.cause).title)} <em>×</em> ${esc(sfNo(sfDoc(r.exposed)))} ${esc(sfDoc(r.exposed).title)}</p>`
    + `<p class="sf-pc-rule">${esc(p.title)}</p>` + sfPairBody(p);
  $("#sf-p-body").scrollTop = 0;
  $("#sf-p-close").focus({ preventScroll: true });
  sfPairsView(); sfMapView();
}
// QA #70: a pair as a short card — what it is, where and when, why (who gives and who takes the risk), what to check and do;
// the grounds, similar accidents and the other reasons fold away. The same body beside the list and in the narrow panel.
const sfRoles = (R) => R.roles || ["위험을 주는 작업", "위험을 받는 작업"];
const sfRolesS = (R) => R.roles_short || ["주는 쪽", "받는 쪽"];
const sfSegs = (w) => w.segments || (w.start ? [[w.start, w.end]] : []);
function sfPairHead(p) {
  const R = p.reasons[0], C = sfDoc(R.cause), X = sfDoc(R.exposed);
  return `<div class="sf-pc-head"><div class="sf-pc-top"><p class="sf-pc-crumb">작업쌍 상세 / <b>${p.id}</b></p>`
    + `<span class="sf-pc-pill p${p.priority}">${PRI[p.priority][0]} · ${PRI[p.priority][1]}</span></div>`
    + `<h3>${esc(R.headline || p.title)}</h3>`
    + `<p class="sf-pc-docs">${esc(sfNo(C))} ${esc(C.title)} <em>×</em> ${esc(sfNo(X))} ${esc(X.title)}</p>`
    + `<p class="sf-pc-rule">${esc(p.title)} · ${p.kind === "NN" ? "비일상작업끼리" : "일상작업 × 비일상작업"}${p.judgement === "판정보류" ? " · 정보 부족" : ""}</p></div>`;
}
const mvEnd = (mv) => hm2m(mv.end) < hm2m(mv.start) ? hm2m(mv.end) + 1440 : hm2m(mv.end);
// the two works on a time axis zoomed to them: overlap shaded (a sequence's gap hatched), ticks at the real times
function sfPairTime(p) {
  const R = p.reasons[0], C = sfDoc(R.cause), X = sfDoc(R.exposed), w = R.when, short = sfRolesS(R), segs = sfSegs(w);
  const spans = [C, X].flatMap((d) => sfWins(d).map((x) => [hm2m(x.start), wEnd(x)]));
  const head = `<div class="sf-pc-th"><h4>겹치는 시간</h4><b class="${w.kind}">${w.kind === "overlap" ? `${segs.map(([a, b]) => `${a}–${b}`).join(", ")} · ${w.min}분`
    : w.kind === "sequence" ? (w.touch ? `맞닿음 · 늦어지면 겹침${w.residual ? " · 잔류 확인" : ""}` : `겹치지 않음 · ${w.gap}분 간격`) : "시간 미상"}</b></div>`;
  if (!spans.length) return head + `<p class="hint">두 작업 모두 시간이 적혀 있지 않아 그릴 수 없습니다.</p>`;
  const lo = Math.floor((Math.min(...spans.map((a) => a[0])) - 30) / 60) * 60, hi = Math.ceil((Math.max(...spans.map((a) => a[1])) + 30) / 60) * 60;
  const x = (m) => ((Math.max(lo, Math.min(hi, m)) - lo) / (hi - lo)) * 100;
  const row = (d, role) => `<div class="sf-tl-row"><span><b>${esc(role)}</b> ${esc(sfNo(d))}</span><div class="sf-tl-track">`
    + sfWins(d).map((v) => `<b class="${d.type}" style="left:${x(hm2m(v.start))}%;width:${x(wEnd(v)) - x(hm2m(v.start))}%"></b>`).join("")
    + (d.move ? `<b class="move" style="left:${x(hm2m(d.move.start))}%;width:${x(mvEnd(d.move)) - x(hm2m(d.move.start))}%"></b>` : "") + `</div></div>`;
  const ov = segs.map(([a, b]) => `<i class="sf-tl-ov${w.kind === "sequence" ? " seq" : ""}" style="left:${x(hm2m(a))}%;width:${Math.max(.6, x(hm2m(b)) - x(hm2m(a)))}%"></i>`).join("");
  const kept = [];
  for (const m of [...segs.flat().map(hm2m), lo, hi]) if (m >= lo && m <= hi && kept.every((k) => Math.abs(x(k) - x(m)) > 8)) kept.push(m);
  const ticks = kept.map((m) => `<em style="left:${x(m)}%">${m2hm(m % 1440)}${m >= 1440 ? "(+1)" : ""}</em>`).join("");
  return head + `<div class="sf-tl sf-pc-tl">${row(C, short[0])}${row(X, short[1])}<div class="sf-tl-axis"><span></span><div>${ov}${ticks}</div></div></div>`
    + `<p class="hint">서류 기준 시간입니다${w.kind === "sequence" ? ` · 앞 작업이 ${w.start}에 끝나고 ${w.gap}분 뒤 다음 작업 시작(빗금 = 잔류위험 확인 구간)` : ""}`
    + `${segs.length > 1 ? ` · 겹침 ${segs.length}조각` : ""}${R.estimated ? " · 크레인 인양은 시작 시각만 적혀 있어 계획 끝까지로 봄(점선)" : ""}</p>`;
}
// S × E: the 3×3 matrix with this pair's cell, and how a priority is given (QA #71: folded under 평가 기준 보기)
function sfMatrix(p, R) {
  const L = sf.det.levels;
  // QA #65: column 1 the 강도 title (centred on the 3 rows), column 2 its ticks, row 4 the 노출 ticks, row 5 its title
  let h = `<div class="sf-mx" role="img" aria-label="강도 ${R.S} × 노출 ${R.E} = ${R.S * R.E}"><span class="sf-mx-y">강도 S</span><span class="sf-mx-x">노출 E</span>`;
  for (let s = 3; s >= 1; s--) for (let e = 1; e <= 3; e++) {
    // 9 is 1순위 only for a forbidden combination; otherwise 6 and more is 2순위
    const v = s * e, pr = v >= 9 && R.forbidden ? 1 : v >= 6 ? 2 : v >= 3 ? 3 : 0;
    h += `<i class="c p${pr}${s === R.S && e === R.E ? " on" : ""}" style="grid-row:${4 - s};grid-column:${e + 2}">${v}</i>`;
  }
  h += [3, 2, 1].map((s, k) => `<em style="grid-row:${k + 1};grid-column:2">${s}</em>`).join("") + [1, 2, 3].map((e) => `<em style="grid-row:4;grid-column:${e + 2}">${e}</em>`).join("") + `</div>`;
  return `<div class="sf-risk-box">${h}<div class="sf-risk-txt">`
    + `<p><b>강도</b> ${[3, 2, 1].filter((s) => L.severity[s]).map((s) => `${s} ${esc(L.severity[s])}`).join(" · ")}</p>`
    + `<p><b>노출</b> ${[3, 2, 1].filter((e) => L.exposure[e]).map((e) => `${e} ${esc(L.exposure[e])}`).join(" · ")}</p>`
    + `<p class="hint">1순위: 동시에 하면 안 되는 조합이 서류로 확인됨(노출 3) · 2순위: 강도×노출 6 이상 · 3순위: 3~5, 또는 점수와 관계없이 시간·위치·잔류위험 정보가 부족한 경우(판정보류)</p></div></div>`;
}
// QA #71: 판단 결과 → 판단 사유 → 근거. The labels stay 강도 / 노출 (노출 is not a probability: QA #62)
function sfJudgement(p) {
  const R = p.reasons[0], C = sfDoc(R.cause), X = sfDoc(R.exposed), w = R.when, L = sf.det.levels, segs = sfSegs(w);
  const seg = segs.map(([a, b]) => `${a}–${b}`).join(", ");
  const concl = R.priority === 1 && R.forbidden && R.E === 3 ? "서류상 동시에 하면 안 되는 조합이 확인됐습니다. 두 작업반장이 시간을 나누거나 한쪽 작업을 멈추도록 협의가 필요합니다."
    : w.kind === "sequence" && w.touch && !w.residual ? "앞 작업이 끝나는 시각에 다음 작업이 바로 시작합니다. 앞 작업이 늦어지면 겹치니 실제 종료를 확인해야 합니다."
    : w.kind === "sequence" && w.touch ? "앞 작업이 끝나는 시각에 바로 이어져, 늦어지면 겹치고 앞 작업의 잔류위험도 확인해야 합니다."
    : w.kind === "sequence" ? "작업시간은 겹치지 않지만, 앞 작업의 잔류위험이 없어졌는지 확인이 필요합니다."
    : w.kind === "unknown" ? "한쪽 작업 시간이 없어 겹침을 확정할 정보가 부족합니다."
    : R.priority === 2 ? "필요한 통제·차단 조치를 확인한 뒤 함께 할지 두 작업반장이 협의합니다."
    : "작업 관계와 추가 조건을 확인한 뒤 판단합니다.";
  const who = `${sfNo(C)} ${C.title}${pp(C.title, "과", "와")} ${sfNo(X)} ${X.title}${pp(X.title, "이", "가")}`;
  const expo = w.kind === "overlap" ? `${who} ${sfWhere(X)}에서 서류상 ${seg}(${w.min}분) 겹칩니다.`
    : w.kind === "sequence" ? `${who} ${sfWhere(X)}에서 이어집니다: ${w.start}에 앞 작업이 끝나고 ${w.gap}분 뒤 다음 작업이 시작됩니다.`
    : `${who} ${sfWhere(X)}에 있지만 한쪽 작업 시간이 없어 겹치는지 확인할 수 없습니다.`;
  const card = (d, role) => `<div class="sf-pdoc"><p class="sf-role">${esc(role)}</p><p>${sfTagHtml(d)} <b>${esc(d.title)}</b></p>`
    + `<p class="hint">${esc(d.type === "permit" ? d.permit_no : d.id)} · ${esc(sfWho(d))}<br>${esc(sfWhere(d))} · ${esc(sfTimes(d))}${d.workers ? ` · ${d.workers}명` : ""}</p>`
    + `<button type="button" class="btn small" data-open="${esc(d.id)}">${icon("i-file")}문서 열기</button></div>`;
  const ev = (R.evidence || []).filter((e) => e.field !== "시간").map((e) => {
    const d = sfDoc(e.doc), no = d ? sfNo(d) : e.doc;
    if (e.confirmed) return `<li><b>${esc(no)} · 작업반장 답변 · 반장 답변 확인</b> 「${esc(e.value)}」</li>`;
    return e.quote ? `<li><b>${esc(no)} · 작업반장 답변</b> 「${esc(e.value)}」</li>` : `<li><b>${esc(no)} · ${esc(e.field)}</b> ${esc(e.value)}</li>`;
  }).join("");
  return `<div class="sf-jd"><p class="sf-jd-top"><b>${R.S * R.E}점 · ${PRI[R.priority][0]} ${PRI[R.priority][1]}</b></p><p>${esc(concl)}</p>`
    + `<ul class="sf-jd-why"><li><b>강도 ${R.S}</b> · ${esc(L.severity[R.S])} — ${esc(R.accident || "")}</li>`
    + `<li><b>노출 ${R.E}</b> · ${esc(expo)}${R.why_E.length ? `<span class="hint"> ${esc(R.why_E.join(" · "))}</span>` : ""}</li></ul>`
    + `<p class="sf-jd-time"><b>서류 기준 겹침</b> ${esc(w.kind === "overlap" ? `${seg} (${w.min}분)` : w.kind === "sequence" ? `겹치지 않음 · ${w.start}에 끝나고 ${w.gap}분 간격` : "확인 불가 (한쪽 시간 없음)")}<br><b>문서에 적힌 작업시간</b> ${esc(sfNo(C))} ${esc(sfTimes(C))} · ${esc(sfNo(X))} ${esc(sfTimes(X))}</p>`
    + (ev ? `<h5>근거 (서류에서 읽은 값·답변)</h5><ul class="sf-jd-ev">${ev}</ul>` : "")
    + `<div class="sf-pdocs2">${card(C, sfRoles(R)[0])}${card(X, sfRoles(R)[1])}</div>`
    + `<details class="sf-jd-crit"><summary>평가 기준 보기</summary>${sfMatrix(p, R)}</details>`
    + `<div class="sf-why" data-whykey="${esc(p.key)}"><h5>이 판정에 대해 묻기</h5><div class="sf-why-qs">`
    + sfWhyQs(p).map(([k, t]) => `<button type="button" class="btn small" data-why="${k}">${esc(t)}</button>`).join("")
    + `</div><form class="sf-why-ask"><input maxlength="200" aria-label="이 판정에 대한 질문" placeholder="다른 말로 묻기 (예: 반장 답의 어느 부분을 썼나요?)">`
    + `<button type="submit" class="btn small">묻기</button></form><div class="sf-why-out" role="status" aria-live="polite"></div></div></div>`;
}
// the questions phase 1 answers from the rule result itself (design §5.5); the same list as the server's
function sfWhyQs(p) {
  const R = p.reasons[0], out = [["used", "어떤 서류 값·반장 답을 썼나요?"]];
  if (R.when.kind === "sequence") out.unshift(["seq", "겹치지 않는데 왜 확인이 필요한가요?"]);
  if (p.judgement === "판정보류" || R.E === 1) out.push(["defer", "무엇이 부족해 판정보류인가요?"]);
  return out;
}
// the answer in the fixed frame (§19.2): 판단 한 줄 → 사용한 사실 → 적용한 규칙 → 아직 확인할 것 → 근거 보기
function sfWhyFrame(j) {
  const f = j.frame, li = (xs) => xs.map((x) => `<li>${esc(x.text)}</li>`).join("");
  return `<p class="sf-why-q">${esc(j.question)}</p><p class="sf-why-judge"><b>${esc(f.judge)}</b>`
    + (j.status === "ok" ? ` <span class="ai-chip">AI가 질문을 이 설명으로 읽음</span>` : "") + `</p>`
    + `<h6>사용한 사실</h6><ul>${li(f.facts)}</ul><h6>적용한 규칙</h6><ul>${li(f.rules)}</ul>`
    + `<h6>아직 확인할 것</h6>${f.left.length ? `<ul class="sf-why-left">${li(f.left)}</ul>` : `<p class="hint">서류 기준으로 더 확인할 것이 적혀 있지 않습니다. 현장 확인은 별도입니다.</p>`}`
    + `<details><summary>근거 보기</summary><p>${f.refs.map((r) => `<button type="button" class="linkbtn" data-open="${esc(r.doc)}">${esc(r.no)} ${esc(r.title)}</button>`).join(" · ")}</p></details>`
    + (j.status === "fail" ? `<p class="hint">AI가 질문을 읽지 못해 「쓴 서류 값」 설명을 보여 드립니다.</p>` : "")
    + (j.why === "what_if" ? `<p class="hint">일정을 바꾸는 가정은 계산하지 않습니다.</p>` : "");
}
let whyReq = 0;
async function sfWhyAsk(box, body) {
  const out = box.querySelector(".sf-why-out"), seq = ++whyReq;
  out.innerHTML = `<p class="hint">${body.question ? "AI가 판정 근거에서 답을 고르는 중입니다 (최대 30초)…" : "정리하는 중…"}</p>`;
  try {
    const r = await fetch("/api/safety/explain", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: box.dataset.whykey, ...body }) });
    const j = await r.json().catch(() => ({}));
    if (seq !== whyReq || !out.isConnected) return;
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `서버 오류 ${r.status}`);
    out.innerHTML = sfWhyFrame(j);
  } catch (e) { if (seq === whyReq) out.innerHTML = `<p class="hint">답을 만들지 못했습니다: ${esc(e.message)}</p>`; }
}
// 규칙 밖 「AI 검토 권장」 (design §8.2): asked by the manager for this one pair; a separate result that never changes
// the rule pairs, their priority or their score
let rvReq = 0;
async function sfReview(box) {
  const out = box.querySelector(".sf-rv-out"), btn = box.querySelector("[data-rvgo]"), seq = ++rvReq;
  btn.disabled = true; out.innerHTML = `<p class="hint">AI가 두 작업의 서류 사실을 읽고 대조하는 중입니다 (모두 합쳐 최대 60초)…</p>`;
  try {
    const r = await fetch("/api/safety/pair-review", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ a: box.dataset.rvA, b: box.dataset.rvB }) });
    const j = await r.json().catch(() => ({}));
    if (seq !== rvReq || !out.isConnected) return;
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `서버 오류 ${r.status}`);
    sfRvLoad();
    out.innerHTML = j.status === "ok"
      ? `<p><span class="ai-chip">AI 제안</span><b>${esc(j.rel_text)}를 확인해 주세요</b></p><p class="hint">${esc(j.label)}</p>`
        + `<ul class="sf-rv-ev">${j.evidence.map((e) => `<li><b>${esc(e.no)} · ${esc(e.field)}</b> 「${esc(e.value)}」</li>`).join("")}</ul>`
        + `<p class="sf-pc-ask"><b>확인할 것</b> ${esc(j.question)}</p>`
        + `<p class="hint">검토 대상이 된 까닭: ${esc((j.close || []).join(" · "))}. 위험 쌍 목록·순위·점수는 바뀌지 않고, 채택해도 새 규칙이 되지 않습니다.</p>`
      : j.status === "held" ? `<p class="hint"><b>${esc(j.why)}</b> · ${j.critique === "late" ? "60초 안에 관계를 두 서류의 행과 대조하지 못해 권장하지 않습니다. 다시 요청할 수 있습니다" : `AI가 고른 관계(${esc(j.rel_text)})를 두 서류의 행이 분명히 보여 주지 않아 권장하지 않습니다`}. 규칙 판정은 그대로입니다.</p>`
        + `<ul class="sf-rv-ev">${(j.evidence || []).map((e) => `<li><b>${esc(e.no)} · ${esc(e.field)}</b> 「${esc(e.value)}」</li>`).join("")}</ul>`
      : j.status === "none" ? `<p class="hint">${esc(j.why || "AI가 규칙 밖 관계를 찾지 못했습니다")}.</p>`
      : `<p class="hint">AI 검토를 마치지 못했습니다. 규칙 판정은 그대로입니다.</p>`;
  } catch (e) { if (seq === rvReq && out.isConnected) out.innerHTML = `<p class="hint">${esc(e.message)}</p>`; }
  finally { if (btn.isConnected) btn.disabled = false; }
}
// 판정보류 쌍의 담당별 확인 문안 (design §8.3): each foreman is asked about his own work only (never to confirm the
// other's); a fact several pairs need is asked once. croScan sends nothing: the manager copies the 문안 and marks it
const HQ_CLS = { "미전달": "no", "전달함": "sent", "응답 받음": "done" };
const HQ_KO = { "미전달": "미전달", "전달함": "답변 대기", "응답 받음": "답변 받음" };     // §19.1: 미전달/답변 대기/답변 받음
const sfHoldInline = (p) => !p.reasons.some((r) => r.E === 1) ? "" : `<div class="sf-hq sf-hq-inline" data-hqpair="${esc(p.key)}">`
  + `<p class="sf-hq-h"><b>담당별 확인</b> <span class="hint">규칙 확인사항을 각 반장이 답할 수 있는 자기 작업 질문으로 나눴습니다</span></p>`
  + `<div class="sf-hq-body"><p class="hint">정리하는 중…</p></div></div>`;
function sfHoldAuto() { document.querySelectorAll(".sf-hq-inline:not([data-loaded])").forEach((b) => { b.dataset.loaded = "1"; sfHoldLoad(b); }); }
const sfHoldBox = (p) => !p.reasons.some((r) => r.E === 1) ? "" : `<details class="sf-pc-d sf-hq" data-hqpair="${esc(p.key)}"><summary>담당별 확인 문안</summary>`
  + `<div class="sf-hq-body"><button type="button" class="btn small" data-hqgo>문안 만들기</button></div></details>`;
async function sfHoldLoad(box) {
  const body = box.querySelector(".sf-hq-body");
  body.innerHTML = `<p class="hint">정리하는 중…</p>`;
  try {
    const r = await fetch("/api/safety/hold-questions"), j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : `서버 오류 ${r.status}`);
    if (body.isConnected) sfHoldRender(box, j);
  } catch (e) { if (body.isConnected) body.innerHTML = `<p class="hint">문안을 만들지 못했습니다: ${esc(e.message)}</p>`; }
}
function sfHoldRender(box, j) {
  const key = box.dataset.hqpair, docs = j.docs.filter((d) => d.questions.some((q) => q.pairs.includes(key)));
  const btn = (q, s, t) => `<button type="button" class="linkbtn" data-hqmark="${esc(q.key)}" data-hqstate="${esc(s)}">${t}</button>`;
  box.querySelector(".sf-hq-body").innerHTML = !docs.length ? `<p class="hint">이 쌍에서 반장에게 물을 것이 없습니다.</p>`
    : `<p class="hint">각 반장에게 자기 작업만 묻습니다. croScan은 보내지 않습니다. 복사해 기존 연락 방법으로 보낸 뒤 「전달함 표시」를 누르세요(복사만으로는 상태가 바뀌지 않습니다). 「답변 받음」은 해석 확인이 아닙니다. 여러 쌍에 같은 질문은 한 번만 나옵니다.</p>`
    + docs.map((d) => `<div class="sf-hq-doc"><p class="sf-hq-row"><b>${esc(d.no)} ${esc(d.who || d.title)}</b> → ${esc(d.questions.filter((q) => q.pairs.includes(key)).map((q) => q.text).join(" · "))}`
      + ` → <span class="sf-hq-st ${HQ_CLS[sfHqWorst(d)] || "no"}">${esc(HQ_KO[sfHqWorst(d)] || sfHqWorst(d))}</span></p><ol>`
      + d.questions.map((q) => `<li>${esc(q.text)} <span class="sf-hq-st ${HQ_CLS[q.state] || "no"}">${esc(HQ_KO[q.state] || q.state)}</span> `
        + (q.flag ? `<span class="sf-hq-flag">${esc(q.flag)}</span> ` : "")
        + ((q.history || []).length ? `<small class="hint">작업 내용이 바뀌기 전: ${q.history.map((h) => esc(h.state + (h.flag ? ` · ${h.flag}` : ""))).join(", ")}</small> ` : "")
        + (q.state === "미전달" ? btn(q, "전달함", "전달함 표시") : q.state === "전달함" ? `${btn(q, "응답 받음", "답변 받음 표시")} · ${btn(q, "미전달", "되돌리기")}` : btn(q, "전달함", "되돌리기")) + `</li>`).join("")
      + `</ol><textarea class="sf-hq-msg" rows="5" readonly aria-label="${esc(d.no)} 반장에게 보낼 전달문">${esc(d.message)}</textarea>`
      + `<button type="button" class="btn small" data-hqcopy>전달문 복사</button></div>`).join("");
}
// a foreman's row state: the least advanced of his questions (미전달 before 답변 대기 before 답변 받음)
const sfHqWorst = (d) => ["미전달", "전달함", "응답 받음"].find((s) => d.questions.some((q) => q.state === s)) || "미전달";

// 서류상 선후 계획 · 남은 확인 (design §8.4·§19.1): the documents plan one work after the other; nothing of it is confirmed,
// and it changes no alarm, priority or tick (display only, from the server's annotate)
function sfSeqPlan(p) {
  const s = p.seq_plan; if (!s) return "";
  const nm = (i) => `${esc(sfNo(sfDoc(i)))} ${esc(sfDoc(i).title || "")}`;
  return `<div class="sf-seq"><p class="sf-seq-h"><b>${esc(s.title)}</b></p><p>${esc(s.text)}</p>`
    + (s.plan.length ? `<ul>${s.plan.map((x) => `<li>서류상: ${nm(x.first)} ${esc(x.end)} 끝 → ${x.gap != null ? `${esc(String(x.gap))}분 뒤 ` : ""}${nm(x.later)} ${esc(x.start)} 시작</li>`).join("")}</ul>` : "")
    + (s.said.length ? `<ul>${s.said.map((x) => `<li>${esc(sfNo(sfDoc(x.doc)))} 기재 「${esc(x.text)}」</li>`).join("")}</ul>` : "")
    + `<p class="sf-seq-left"><b>남은 확인</b> ${esc(s.left.join(" · "))}</p></div>`;
}

// 규칙 밖 「AI 검토 권장」 목록 (design §8.2·§19.1·§19.2): a tab of its own at the end of 위험 쌍; 검토 완료 N / 대상 M, the
// recommendations first, waiting·failed·not analysed folded; never counted in the rule lists, the donut or the priorities
Object.assign(sf, { rv: null, aiPrev: null });
async function sfRvLoad() {
  try {
    const r = await fetch("/api/safety/pair-reviews"), j = await r.json().catch(() => ({}));
    if (r.ok) { sf.rv = j; sfNav(); if (sf.ptab === "ai") sfPairsView(); }
  } catch (e) { /* the list says 미분석 */ }
}
const sfRvCount = () => (sf.rv && sf.rv.count) || { done: 0, targets: 0, ok: 0, not_run: 0, waiting: 0, running: 0, fail: 0 };
const sfAiCount = () => { const c = sfRvCount(); return `${c.done}/${c.targets}`; };
const sfRvItem = (k) => sf.rv && (sf.rv.items || []).find((x) => x.key === k);
function sfAiState(k) {
  const s = sf.rv && sf.rv.states && sf.rv.states[k];
  return `<p class="sf-ai-state"><span class="${s && s.state === "fail" ? "bad" : ""}">AI 관계 검토: <b>${esc(s ? s.ko : "미분석")}</b></span>`
    + (s && s.state === "done" ? ` <span class="hint">아래에 결과가 있습니다</span>` : "") + `</p>`;
}
function sfRvKept(k) {
  const j = sfRvItem(k); if (!j) return "";
  return j.status === "ok" ? `<p><span class="ai-chip">AI 제안</span><b>${esc(j.rel_text)}를 확인해 주세요</b></p>`
      + `<ul class="sf-rv-ev">${(j.evidence || []).map((e) => `<li><b>${esc(e.no)} · ${esc(e.field)}</b> 「${esc(e.value)}」</li>`).join("")}</ul>`
      + `<p class="sf-pc-ask"><b>확인할 것</b> ${esc(j.question)}</p><p class="hint">${esc(j.label)}. 위험 쌍 목록·순위·점수는 바뀌지 않습니다.</p>`
    : j.status === "held" ? `<p class="hint"><b>${esc(j.why)}</b> · 규칙 판정은 그대로입니다.</p>`
    : `<p class="hint">${esc(j.why || "AI가 규칙 밖 관계를 찾지 못했습니다")}.</p>`;
}
function sfAiEntry() {
  const c = sfRvCount();
  return `<li class="sf-ai-entry"><button type="button" class="sf-nrow" data-ptab="ai"><span class="ai-chip">AI 제안</span>`
    + `<span class="sf-nt">AI 검토 권장 · ${sf.rv ? `검토 완료 ${c.done} / 대상 ${c.targets}` : "불러오는 중"}</span></button></li>`;
}
function sfAiList() {
  if (!sf.rv) { sfRvLoad(); return `<li class="sf-empty">AI 검토 권장 목록을 불러오는 중…</li>`; }
  const c = sfRvCount(), ok = (sf.rv.items || []).filter((x) => x.status === "ok");
  const head = `<li class="sf-near-head sf-ai-head"><p><b>AI 검토 권장 · 규칙 판정 아님</b></p>`
    + `<p>검토 완료 ${c.done} / 대상 ${c.targets} · 권장 ${ok.length}건</p>`
    + `<p class="hint">${c.done ? (ok.length ? "AI가 규칙 밖 관계 가설을 낸 쌍입니다. 위험 쌍 순위·건수에 들어가지 않습니다." : `검토한 ${c.done}쌍에서 권장할 관계를 찾지 못했습니다(찾지 못한 것이 관계가 없다는 뜻은 아님).`) : "아직 AI가 검토한 쌍이 없습니다(미분석)."}</p>`
    + `<button type="button" class="btn small" data-aiclose>규칙 목록으로 돌아가기</button></li>`;
  const rows = ok.map((x) => { const A = sfDoc(x.a), B = sfDoc(x.b), on = sf.nearKey === x.key;
    return `<li><button type="button" class="sf-nrow sf-airow${on ? " picked" : ""}" data-near="${esc(x.key)}"${on ? ' aria-current="true"' : ""}>`
      + `<span class="ai-chip">AI 제안</span><span class="sf-nt">${esc(sfNo(A))} × ${esc(sfNo(B))} · ${esc(x.rel_text)}</span></button></li>`; }).join("");
  const rest = Object.entries((sf.rv && sf.rv.states) || {}).filter(([k, s]) => s.state !== "done" || !ok.some((x) => x.key === k));
  const fold = rest.length ? `<li><details class="sf-ai-rest"><summary>대기·실패·미분석·관계 없음 ${rest.length}쌍</summary><ul>`
    + rest.map(([k, s]) => { const [a, b] = k.split("|"), it = sfRvItem(k);
      return `<li><button type="button" class="linkbtn" data-near="${esc(k)}">${esc(sfNo(sfDoc(a)))} × ${esc(sfNo(sfDoc(b)))}</button> · ${esc(it && it.status === "none" ? "검토 완료 · 권장 없음" : it && it.status === "held" ? "검토 완료 · 근거 부족으로 보류" : s.ko)}</li>`; }).join("")
    + `</ul></details></li>` : "";
  return head + (rows || "") + fold;
}

// 근거 지도 (design §3.4.1·§19.1·§19.8): from 「검토 과정 보기」, in the side panel; 구축 과정 folded. A hatched cell is
// 「근거 보강 필요」; 「—」 is 「연결 없음」, not 「법령 미적용」
async function sfEvidence() {
  const P = $("#sf-panel"); P.hidden = false; P.dataset.mode = "emap"; sf.req++;
  $("#sf-p-kind").textContent = "근거 지도"; $("#sf-p-kind").className = "eyebrow";
  $("#sf-p-title").textContent = "체크리스트 항목·쌍 규칙의 근거"; $("#sf-p-meta").textContent = "검토 과정 보기에서 열림 · 판정에 쓰이지 않음";
  $("#sf-p-tabs").hidden = true; $("#sf-p-note").hidden = true; $("#sf-p-pos").textContent = "";
  $("#sf-p-prev").disabled = true; $("#sf-p-next").disabled = true;
  $("#sf-p-body").innerHTML = `<p class="hint">불러오는 중…</p>`;
  try {
    const r = await fetch("/api/knowledge/map"), m = await r.json();
    if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
    if (P.dataset.mode !== "emap") return;
    const f = m.flow, cell = (xs) => xs && xs.length ? `<td>후보 ${xs.length}</td>` : `<td class="sf-em-none">—</td>`;
    const law = (c) => c ? `<td>${esc(c.links.map((x) => x.ref).join(", "))} <small>· ${c.confirmed ? "검수 맞음 · 확인된 근거" : c.fit ? `검수 ${esc(c.fit)} · 인용만` : "검수 기록 없음 · 인용만"}${c.links.some((x) => !x.in_corpus) ? " · 원문 미수집" : ""}</small></td>` : `<td class="sf-em-gap">근거 보강 필요</td>`;
    $("#sf-p-body").innerHTML = `<p class="hint">[법령] 칸은 원문 수집·인용·규칙 적합성 검수를 따로 표시합니다. 확인된 근거는 적합성 검수 「맞음」인 조문뿐이고, 「약함」·「검수 기록 없음」은 인용만 있는 것입니다. 다른 칸은 검색 후보(검수 전)입니다. 빗금 칸은 「근거 보강 필요」, 「—」는 「연결 없음」이며 법령 미적용이 아닙니다.</p>`
      + `<details class="sf-pc-d"><summary>구축 과정</summary><p>수집 ${f.sources}건 → 조각 ${f.chunks}개 → 분류 ${Object.entries(f.by_authority).map(([k, v]) => `${esc(k)} ${v}`).join(" · ")}`
      + ` (가상 표시 ${f.synthetic}) → 연결: 조문 인용 ${f.with_law}항목(원문 수집 ${f.law_collected} · 적합성 검수 맞음 ${f.law_fit_ok} · 약함 ${f.law_weak} · 검수 기록 없음 ${f.law_unchecked}) · 확인된 조문 ${f.law_confirmed}항목 · 근거 보강 필요 ${f.empty}항목</p><p class="hint">일상 위험 쌍 탐지 건수와는 따로 셉니다.</p></details>`
      + `<div class="sf-em-wrap"><table class="sf-em"><thead><tr><th>항목</th><th>법령</th><th>공공</th><th>조선사</th><th>팀</th><th>예시</th></tr></thead><tbody>`
      + m.rows.map((x) => `<tr><td><b>${esc(x.title)}</b><br><small>${esc(x.kind)}</small></td>${law(x["법령"])}${cell(x["공공"])}${cell(x["조선사"])}${cell(x["팀"] && x["팀"].candidates)}${cell(x["예시"])}</tr>`).join("")
      + `</tbody></table></div><p><a href="/static/evidence.html" target="_blank" rel="noopener">근거 지도 전체 화면(구절 보기)</a></p>`;
  } catch (e) { if (P.dataset.mode === "emap") $("#sf-p-body").innerHTML = `<p class="hint">근거 지도를 불러오지 못했습니다: ${esc(e.message)}</p>`; }
}

// 설명 질의 (design §5.2·§12.1): the 「왜?」 of a checklist item or a change in the 반영본, from the server's own data,
// verified before it is shown (§5.4); the same frame as the pair's
function xFrame(j) {
  const f = j.frame, li = (xs) => xs.map((x) => `<li>${esc(x.text)}</li>`).join("");
  return `<p class="sf-why-judge"><b>${esc(f.judge)}</b></p>`
    + (f.facts.length ? `<h6>사용한 사실</h6><ul>${li(f.facts)}</ul>` : "") + (f.rules.length ? `<h6>적용한 기준</h6><ul>${li(f.rules)}</ul>` : "")
    + `<h6>아직 확인할 것</h6>${f.left.length ? `<ul class="sf-why-left">${li(f.left)}</ul>` : `<p class="hint">적힌 것이 없습니다. 현장 확인은 별도입니다.</p>`}`
    + (f.fallback ? `<p class="hint">설명 검사를 통과하지 못해 근거 표만 보여 드립니다.</p>` : "");
}
async function xWhy(btn, target) {
  let out = btn.nextElementSibling;
  if (out && out.classList.contains("x-why-out")) { out.remove(); btn.setAttribute("aria-expanded", "false"); return; }
  out = el("div", "x-why-out sf-why-out"); out.setAttribute("role", "status"); btn.after(out); btn.setAttribute("aria-expanded", "true");
  out.innerHTML = `<p class="hint">정리하는 중…</p>`;
  try {
    const r = await fetch("/api/explanations/query", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: typeof target === "function" ? target() : target, fields: st.doc ? st.doc.fields : {}, session_id: st.sid || "" }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : (j.detail && j.detail.message) || `서버 오류 ${r.status}`);
    if (out.isConnected) out.innerHTML = xFrame(j);
  } catch (e) { if (out.isConnected) out.innerHTML = `<p class="hint">설명을 만들지 못했습니다: ${esc(e.message)}</p>`; }
}
function xWhyBtn(target) {
  const b = el("button", "linkbtn x-why", "왜?"); b.type = "button"; b.setAttribute("aria-expanded", "false");
  b.onclick = (e) => { e.stopPropagation(); xWhy(b, target); };
  return b;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-xwhy]"); if (!b) return;
  let t = null; try { t = JSON.parse(b.dataset.xwhy); } catch (err) { return; }
  xWhy(b, t);
});
async function sfHoldMark(b) {
  const box = b.closest(".sf-hq");
  try {
    const r = await fetch("/api/safety/hold-questions/mark", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key: b.dataset.hqmark, state: b.dataset.hqstate }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { toast(typeof j.detail === "string" ? j.detail : `서버 오류 ${r.status}`); return; }
    if (box && box.isConnected) sfHoldLoad(box);
  } catch (e) { toast(`표시하지 못했습니다: ${e.message}`); }
}
function sfPairBody(p) {
  const R = p.reasons[0], C = sfDoc(R.cause), X = sfDoc(R.exposed), role = sfRoles(R);
  let h = `<div class="sf-pc-where"><span><i>위치</i>${esc(sfWhere(X))}</span><span class="sf-pc-rel">${esc(R.relation.split(":")[0])}</span>`
    + `<button type="button" class="linkbtn" data-tomap>배치도에서 보기</button></div>`
    + sfPairTime(p) + sfVerLine([p.a, p.b])
    + `<h4 class="sf-pc-h">왜 위험한가요?</h4><div class="sf-pc-why"><div class="sf-pc-flow">`
    + `<div class="sf-pc-box give"><span>${esc(role[0])}</span><b>${esc(C.title)}</b></div>`
    + `<p class="sf-pc-arrow"><span aria-hidden="true">↓</span>${esc(R.mechanism || R.chain[1] || "")}</p>`
    + `<div class="sf-pc-box take"><span>${esc(role[1])}</span><b>${esc(X.title)}</b></div></div>`
    + `<div class="sf-pc-acc"><b>${esc(R.accident || R.chain[R.chain.length - 1])}</b><p>${esc(R.story || R.chain.join(" → "))}</p></div></div>`
    + `<p class="sf-pc-ask"><b>확인 필요</b> ${esc(R.ask)}</p>` + sfSeqPlan(p) + sfHoldInline(p)
    + (p.reasons.some((x) => x.floor) ? `<p class="hint sf-floor">작업반장 확인 답만 보면 이 경보가 낮아지거나 없어질 수 있지만, 서류 기준으로 그대로 둡니다. 해제는 안전관리자가 판단합니다.</p>` : "")
    + `<h4 class="sf-pc-h">필요한 조치</h4><ul class="sf-pc-do">${R.measures.map((m) => `<li>${esc(m)}</li>`).join("")}</ul>`
    + `<div class="sf-pc-more"><details class="sf-pc-d"><summary>판정 근거·원문</summary>${sfJudgement(p)}</details>` + sfHybridPair(p)
    + `<details class="sf-pc-d"><summary>유사사고·기준</summary><ul class="sf-cases">${R.cases.map((c) => `<li>${esc(c)}</li>`).join("")}<li class="law">${esc(R.law)}</li></ul></details>`;
  if (p.reasons.length > 1) {
    h += `<details class="sf-pc-d"><summary>추가 위험 ${p.reasons.length - 1}가지</summary>` + p.reasons.slice(1).map((x) =>
      `<div class="sf-more2"><p><span class="sf-pbadge sm p${x.priority}">${PRI[x.priority][0]}</span> <b>${esc(x.headline || x.name)}</b></p>`
      + `<p class="hint">${esc(x.accident || "")} · 강도 ${x.S} × 노출 ${x.E} = ${x.score} · ${esc(sfWhen(x.when))}</p>`
      + `<p>${esc(x.story || x.chain.join(" → "))}</p><p class="hint"><b>조치</b> ${esc(x.measures.join(" · "))}</p><p class="hint"><b>확인할 것</b> ${esc(x.ask)}</p></div>`).join("") + `</details>`;
  }
  setTimeout(sfHoldAuto, 0);                                   // the hold questions load into the box just drawn
  return h + `</div><div class="sf-pc-foot"><button type="button" class="btn" data-tomap>${icon("i-search")}배치도에서 확인</button>`
    + `<button type="button" class="btn primary" data-postgo>작업 조정 문자 작성${icon("i-right")}</button></div>`
    + `<p class="sf-disclaim hint">croScan 규칙 판정입니다. 안전관리자가 위험을 검토하고, 작업 시간·순서는 각 작업반장이 협의해 정합니다.</p>`;
}
function sfPairStep(n) {
  const list = sfPairVisible(), i = list.findIndex((x) => x.id === sf.openPair), to = i < 0 ? list[0] : list[i + n];
  if (to) sfOpenPair(to.id);
}

// 현장 게시용 서류 -------------------------------------------------------
// QA #87·#91·#98 (2026-10-31): the safety manager has no say over the schedule (the two foremen settle how their works
// go: a fact of the yard), so croScan changes no times, confirms no coordination and keeps no day-of checks.
// ① 작업 조정: for each pair, the 「일정 조율 협조 메시지」 to one foreman about the other, filled from the submitted
// documents. ② 서류 발행: the posting sheet (permit) and the routine-work notice from the rules' wording, issued as a
// revision. Demo: kept in this browser; no text message is sent.
const POST_STEPS = [["coord", "① 작업 조정"], ["issue", "② 서류 발행"]];
Object.assign(sf, { post: null, pstep: "coord", sheetDoc: null, coordKey: null, mgEdit: false, outOpen: new Set() });
const ruleOf = (id) => sf.det.rules.find((r) => r.id === id) || {};
function postKey() {
  let h = 0; for (const c of JSON.stringify(sf.docs.map((d) => [d.id, d.rev]).sort())) h = (h * 31 + c.charCodeAt(0)) | 0;
  // post2: the store of the 조정 확정·당일 확인 days is left as it was, not read into this one
  return `croscan.safety.post2.${sf.data.date}.${(h >>> 0).toString(36)}`;    // per work day and per set of documents
}
function postLoad() {
  try { sf.post = JSON.parse(localStorage.getItem(postKey()) || "null"); } catch (e) { sf.post = null; }
  sf.post = Object.assign({ edits: {}, issues: {}, lines: {}, reopen: {}, fill: {}, msgs: {}, log: [], ai: {} }, sf.post || {});
}
function postSave() {
  try { localStorage.setItem(postKey(), JSON.stringify(sf.post)); return true; }
  catch (e) { toast("이 기기에 저장하지 못했습니다. 화면을 닫으면 바뀐 내용이 사라질 수 있습니다"); return false; }
}
// a record (issue, take-down, delivery, message) counts only once it is stored: otherwise it is put back as it was
function postCommit(change) {
  const before = JSON.parse(JSON.stringify(sf.post)); change();
  if (postSave()) return true;
  sf.post = before; toast("저장하지 못해 기록을 바꾸지 않았습니다"); return false;
}
const nowHM = () => sfClockNow();                // the time in Korea, whatever the browser's zone
const postPairs = () => sf.det.pairs.map((p) => ({ key: p.key, base: p }));     // in the detection's order (P01 first)
const pairLabel = (p) => p.base.id;
function pairDocs(p) { return [sfDoc(p.base.a), sfDoc(p.base.b)]; }
// the rule's wording for the two sides (the sheet's draft)
function draftOf(p) {
  const r = p.base.reasons[0], rule = ruleOf(r.rule), post = rule.post || {};
  const [A, B] = pairDocs(p), cause = sfDoc(r.cause), exposed = r.cause === A.id ? B : A;
  const contact = (d) => d.type === "permit" ? `${d.supervisor || "작업책임자"} · ${d.dept}` + (d.phone ? ` · ${d.phone}` : " · 연락처 없음")
    : `${(d.boss || "책임자").split(" /")[0]} · ${d.company} · 연락처: 작업계획서에 없음(생산 담당자 확인)`;
  return { risk: r.chain.join(" → "), cause_do: post.cause || r.measures[0], exposed_do: post.exposed || r.measures[1] || "",
    start: post.start || r.measures[0], stop: post.stop || "이상이 보이면 양쪽 모두 중지하고 안전관리자에게 연락",
    keep: p.base.priority === 2 ? `조치 유지: ${r.when.start}–${r.when.end} 동안 · 효과 확인: ${r.ask}` : "",
    handoff: r.when.kind === "sequence" ? (post.start || "앞 작업의 위험이 없어졌음을 확인한 뒤 착수") : "",
    contact_cause: contact(cause), contact_exposed: contact(exposed), cause: cause.id, exposed: exposed.id };
}

// ① 작업 조정: 일정 조율 협조 메시지 (QA #98) ----------------------------------------
const SENDER_KEY = "croscan.safety.sender";
let senderMemory = null;               // kept for this visit even when the device does not store it
function senderGet() {
  if (!senderMemory) {
    try { const v = JSON.parse(localStorage.getItem(SENDER_KEY) || "{}") || {}; senderMemory = { name: v.name || "", phone: v.phone || "" }; }
    catch (e) { senderMemory = { name: "", phone: "" }; }
  }
  return { ...senderMemory };
}
function senderSet(v) {
  senderMemory = { ...v };
  try { localStorage.setItem(SENDER_KEY, JSON.stringify(v)); } catch (e) { toast("보내는 사람 정보는 지금 화면에서만 유지됩니다"); }
}
const bossOf = (d) => String((d.type === "permit" ? d.supervisor : d.boss) || "").split(" /")[0].trim();
const orgOf = (d) => (d.type === "permit" ? d.dept : d.company) || "";
const workOf = (d) => d.type === "permit" ? `${d.label}작업` : d.title;
const placeOf = (d) => String(d.place || "").replace(/^\S*공장\s*/, "").trim();
const dayKo = (iso) => { const [y, m, d] = iso.split("-").map(Number); return `${m}월 ${d}일 (${"일월화수목금토"[new Date(y, m - 1, d).getDay()]})`; };
const msgsOf = (key) => (sf.post.msgs[key] || []);
function mgFill(key) { return (sf.post.fill[key] = sf.post.fill[key] || { phone: {}, text: {} }); }
// everything the message needs, from the documents and what was typed for this pair (the documents are not written to)
function mgModel(p) {
  const r = p.base.reasons[0], C = sfDoc(r.cause), X = sfDoc(r.exposed), f = mgFill(p.key), me = senderGet();
  const to = f.to === X.id ? X : C, other = to === C ? X : C;          // the work that gives the risk is asked first
  const name = (d) => (f.name && f.name[d.id] != null ? f.name[d.id] : bossOf(d));
  const phone = (d) => (f.phone[d.id] != null ? f.phone[d.id] : d.type === "permit" ? d.phone || "" : "");
  // one place when both works are at it; otherwise each work's own, with its number (one is not the other's place)
  const pc = placeOf(C), px = placeOf(X);
  const place = f.place != null ? f.place : pc && px ? (pc === px ? pc : `${sfNo(C)} ${pc}, ${sfNo(X)} ${px}`) : pc || px;
  const w = r.when, segs = w.kind === "overlap" ? sfSegs(w).map(([a, b]) => `${a}~${b}`).join(", ") : "";
  const first = w.kind === "sequence" && r.sequence ? (r.sequence.first === "A" ? C : X) : null, second = first ? (first === C ? X : C) : null;
  return { p, r, C, X, to, other, name, phone, place, me, w, segs, first, second, rule: ruleOf(r.rule) };
}
// the message as parts: a value the user filled is {v}, one still missing is {miss: its name}
function mgParts(m) {
  const day = dayKo(sf.data.date), V = (v, miss) => (String(v || "").trim() ? { v: String(v).trim() } : { miss });
  const toN = m.name(m.to), otN = m.name(m.other), L = [];
  L.push([V(toN, "받는 반장 이름"), { t: " 반장님, 안전관리자입니다." }]);
  const where = [{ v: day }, { t: " " }, V(m.place, "작업구역"), { t: "에서 " }], su = (w, x, y) => `${w}${pp(w, x, y)}`;
  if (m.w.kind === "overlap") L.push([...where, { v: m.segs }, { t: `에 ${sfSegs(m.w).length > 1 ? `모두 ${m.w.min}분 ` : ""}작업이 겹칠 예정입니다.` }]);
  else if (m.w.kind === "sequence") L.push([...where, { t: `서류상 ${su(workOf(m.first), "은", "는")} ` }, { v: m.w.start },
    { t: `에 끝날 예정이고, ${m.w.gap}분 뒤 ` }, { v: m.w.end }, { t: `에 ${su(workOf(m.second), "이", "가")} 시작될 예정입니다.` }]);
  else L.push([...where, { t: "두 작업이 함께 잡혀 있지만, 한쪽 작업 시간이 서류에 없어 겹치는지 확인되지 않았습니다." }]);
  L.push([{ t: `${m.r.headline || m.p.base.title}. ${m.r.accident || "사고"}${pp(m.r.accident || "사고", "이", "가")} 있습니다.` }]);
  L.push([V(otN, "협의 상대 이름"), { t: " 반장님(" }, V(m.phone(m.other), `${otN || "협의 상대"} 반장 번호`),
    { t: ")과 시간과 순서를 협의해, 바뀌는 일정이 있으면 회신해 주세요." }]);
  // what to tell the other side afterwards: only when the work that leaves the risk goes first (or the order is open)
  const res = m.rule.residual, causeFirst = !m.first || m.first === m.C;
  if (res && causeFirst) L.push(m.to === m.C ? [{ t: `${workOf(m.C)}${pp(workOf(m.C), "이", "가")} 끝나면 ${res} 확인 결과도 ` }, V(otN, "협의 상대 이름"), { t: " 반장님께 알려 주세요." }]
    : [{ t: `${workOf(m.C)}${pp(workOf(m.C), "이", "가")} 끝난 뒤 ${res} 확인 결과를 받고 시작해 주세요.` }]);
  L.push([{ t: "안전관리자 " }, V(m.me.name, "보내는 사람 이름"), { t: ", " }, V(m.me.phone, "보내는 사람 번호")]);
  return L;
}
const mgPlain = (L) => L.map((ln) => ln.map((x) => x.v != null ? x.v : x.t != null ? x.t : `[${x.miss}]`).join("")).join("\n");
// what has to be there before it can go: both foremen (name, number), the place, the sender, and some text
function mgMissing(m, text) {
  return [["받는 반장 이름", m.name(m.to)], ["받는 반장 번호", m.phone(m.to)], ["협의 상대 이름", m.name(m.other)], ["협의 상대 번호", m.phone(m.other)],
    ["작업구역", m.place], ["보내는 사람 이름", m.me.name], ["보내는 사람 번호", m.me.phone], ["문자 본문", text]]
    .filter(([, v]) => !String(v == null ? "" : v).trim()).map(([k]) => k);
}
function mgText(m) {
  const man = mgFill(m.p.key).text[m.to.id];
  return sf.mgEdit && $("#mg-area") ? $("#mg-area").value : man ? man.v : mgPlain(mgParts(m));
}
function mgStatus(key) {
  const last = msgsOf(key).slice(-1)[0];
  return last ? ["ok", `복사·기록 완료 · ${last.toName} ${last.at}`] : ["", "복사 전"];
}
function postCoordList() {
  const ps = postPairs();
  let h = `<div class="sf-pbar"><b>작업 조정</b> <span class="hint">쌍을 누르면 반장 한 명씩 받을 일정 조율 협조 문자를 씁니다(받는 사람을 바꾸면 상대 반장에게 보낼 문자가 됩니다). 일정은 반장들이 협의해 정합니다.</span></div>`;
  // QA #81: a pair is one line: 순위, P번호, what the risk is; the two works are in the message window
  h += `<ol class="sf-clist">` + ps.map((p) => {
    const b = p.base, [st, stt] = mgStatus(p.key);
    return `<li><button type="button" class="sf-crow sf-crow1" data-coord="${esc(p.key)}" aria-label="${esc(`${PRI[b.priority][0]} ${b.id} ${b.title}, ${stt}`)}"><span class="sf-pbadge sm p${b.priority}">${PRI[b.priority][0]}</span>`
      + `<span class="sf-cid">${esc(b.id)}</span><b class="sf-ctitle">${esc(b.title)}</b><span class="sf-cst ${st}">${esc(stt)}</span></button></li>`;
  }).join("") + `</ol>`;
  const sent = ps.filter((p) => msgsOf(p.key).length).length;
  return h + `<div class="sf-pfoot"><span>복사·기록 ${sent}/${ps.length}쌍</span><button class="btn primary" data-pstep="issue">② 서류 발행으로${icon("i-right")}</button></div>`;
}
function postCoordOpen(key) {
  const p = postPairs().find((x) => x.key === key); if (!p) return;
  sf.coordKey = key; sf.openPair = null; sf.open = null; sf.mgEdit = false; sf.req++;
  const P = $("#sf-panel"); P.hidden = false; P.dataset.mode = "coord";
  const b = p.base, m = mgModel(p);
  $("#sf-p-kind").textContent = `작업 조정 · ${b.id} · ${PRI[b.priority][0]}`; $("#sf-p-kind").className = `eyebrow sf-pk p${b.priority}`;
  $("#sf-p-title").textContent = "일정 조율 협조 메시지 작성";
  $("#sf-p-meta").innerHTML = `${esc(b.title)}: ` + (m.w.kind === "overlap" ? `<b class="mg-t">${esc(m.segs)}</b>에 ${m.w.min}분 동안 겹칠 예정입니다.`
    : m.w.kind === "sequence" ? `앞 작업 <b class="mg-t">${esc(m.w.start)}</b> 종료 예정 · ${m.w.gap}분 뒤 ${esc(m.w.end)} 다음 작업 시작 예정` : "한쪽 작업 시간이 서류에 없습니다.");
  $("#sf-p-tabs").hidden = true; $("#sf-p-note").hidden = true;
  $("#sf-p-pos").textContent = ""; $("#sf-p-prev").disabled = $("#sf-p-next").disabled = true;
  const card = (d) => { const on = d === m.to;
    return `<div class="mg-card${on ? " on" : ""}"><button type="button" class="mg-pick" data-mgto="${esc(d.id)}" aria-pressed="${on}">`
      + `<span class="mg-role">${on ? "받는 사람" : "협의 상대"}</span><b>${esc(m.name(d) || "이름 없음")} 반장</b><span class="mg-org">${esc(orgOf(d))}</span><span class="mg-work">${esc(sfNo(d))} · ${esc(d.title)}</span></button>`
      + (m.name(d) ? "" : `<label class="mg-in"><span>이름</span><input data-mg="name:${esc(d.id)}" autocomplete="off" placeholder="반장 이름"></label>`)
      + `<label class="mg-in"><span>번호</span><input data-mg="phone:${esc(d.id)}" value="${esc(m.phone(d))}" inputmode="tel" autocomplete="off" placeholder="번호 입력"></label></div>`; };
  const h = `<div class="mg"><h3>누구에게 보낼까요</h3><div class="mg-who">${card(m.to)}${card(m.other)}</div>`
    + `<p class="hint mg-swap">반장을 누르면 받는 사람과 협의 상대가 바뀝니다. <button type="button" class="linkbtn" data-mgswap>바꾸기</button></p>`
    + `<h3>작업 정보</h3><div class="mg-row"><label class="mg-in"><span>작업일</span><input value="${esc(dayKo(sf.data.date))}" readonly></label>`
    + `<label class="mg-in"><span>작업구역</span><input data-mg="place" value="${esc(m.place)}" autocomplete="off" placeholder="예: 3BAY 08-10 칼럼 E42P 블록"></label></div>`
    + `<h3>보내는 사람 <small class="hint">이 기기에 기억합니다</small></h3><div class="mg-row"><label class="mg-in"><span>이름</span><input data-mg="me.name" value="${esc(m.me.name)}" autocomplete="name" placeholder="안전관리자 이름"></label>`
    + `<label class="mg-in"><span>번호</span><input data-mg="me.phone" value="${esc(m.me.phone)}" inputmode="tel" autocomplete="tel" placeholder="회신 받을 번호"></label></div>`
    + `<div class="mg-th"><h3>보낼 문자</h3><button type="button" class="btn small" id="mg-edit" aria-pressed="false">직접 수정</button></div>`
    + `<div class="mg-text" id="mg-text"></div><p class="hint mg-stale" id="mg-stale" hidden></p><div class="mg-note" id="mg-note" role="status"></div><div id="mg-log"></div>`
    + `<div class="mg-foot"><p id="mg-need" aria-live="polite"></p><button type="button" class="btn primary" id="mg-send"></button></div></div>`;
  $("#sf-p-body").innerHTML = h; $("#sf-p-body").scrollTop = 0;
  mgRefresh(); mgNote(key);
  $("#sf-p-close").focus({ preventScroll: true });
}
// 「협의할 점」 (design §6.5·§19.1): from a foreman's confirmed answer about this pair, one sentence offered under the
// message with where it came from; it goes into the message only when the manager presses 「문자에 넣기」
let mgNoteSeq = 0;
async function mgNote(key) {
  const box = $("#mg-note"); if (!box) return;
  const seq = ++mgNoteSeq, det = sf.det;
  sf.mgNote = null;
  box.innerHTML = `<p class="hint">작업반장 확인 답에서 협의할 점을 찾는 중…</p>`;
  let j = {};
  try { const r = await fetch("/api/safety/coord-note", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }) }); j = r.ok ? await r.json() : {}; } catch (e) { j = {}; }
  // only the latest request, for the pair still open, on the same judgement, into the box it was asked for
  if (seq !== mgNoteSeq || sf.coordKey !== key || sf.det !== det || $("#mg-note") !== box) return;
  if (!j.text) { box.innerHTML = j.status === "none" ? "" : `<p class="hint">협의할 점 제안을 만들지 못했습니다. 문자는 그대로 보낼 수 있습니다.</p>`; return; }
  sf.mgNote = { seq, key, det, text: j.text };
  box.innerHTML = `<p><b>협의할 점 (제안)</b> ${j.status === "ok" ? `<span class="ai-chip">AI 초안</span> ` : ""}${esc(j.text)}</p>`
    + `<p class="hint">출처: ${j.sources.map((x) => `${esc(x.no)} 작업반장 답변 · 반장 답변 확인 「${esc(x.value)}」`).join(" · ")}</p>`
    + `<button type="button" class="btn small" data-mgnote="${seq}">문자에 넣기</button>`;
}
// after a field changes: the preview, what is missing and the button (the inputs themselves keep the focus)
function mgRefresh() {
  const p = postPairs().find((x) => x.key === sf.coordKey); if (!p || $("#sf-panel").dataset.mode !== "coord") return;
  const m = mgModel(p), L = mgParts(m), auto = mgPlain(L), man = mgFill(p.key).text[m.to.id], miss = mgMissing(m, mgText(m));
  for (const d of [m.C, m.X]) { const nb = document.querySelector(`[data-mgto="${CSS.escape(d.id)}"] b`); if (nb) nb.textContent = `${m.name(d) || "이름 없음"} 반장`; }
  const box = $("#mg-text");
  if (sf.mgEdit) { if (!box.querySelector("textarea")) box.innerHTML = `<textarea id="mg-area" rows="8" aria-label="보낼 문자 직접 수정">${esc(man ? man.v : auto)}</textarea>`; }
  else if (man) box.innerHTML = `<p class="mg-man">${esc(man.v).replace(/\n/g, "<br>")}</p>`;
  else box.innerHTML = L.map((ln, i) => `<p${i === L.length - 1 ? ' class="mg-sign"' : ""}>${ln.map((x) => x.v != null ? `<b class="mg-v">${esc(x.v)}</b>` : x.t != null ? esc(x.t) : `<span class="mg-miss">${esc(x.miss)}</span>`).join("")}</p>`).join("");
  $("#mg-edit").textContent = sf.mgEdit ? "미리 보기" : man ? "직접 고친 문자 수정" : "직접 수정"; $("#mg-edit").setAttribute("aria-pressed", String(sf.mgEdit));
  const st = $("#mg-stale"); st.hidden = !(man && man.base !== auto);
  if (!st.hidden) st.innerHTML = `직접 고친 뒤 입력한 정보가 바뀌었습니다. <button type="button" class="linkbtn" data-mgregen>지금 정보로 다시 만들기</button>`;
  else if (man) { st.hidden = false; st.innerHTML = `직접 고친 문자를 복사합니다. <button type="button" class="linkbtn" data-mgregen>자동 문장으로 되돌리기</button>`; }
  const log = msgsOf(p.key);
  $("#mg-log").innerHTML = log.length ? `<ul class="mg-sent">${log.slice().reverse().map((x) => `<li>${icon("i-check")}<span><b>복사·기록 완료 ${esc(x.at)}</b> · ${esc(x.toName)} 반장에게 보낼 문자 (협의 상대 ${esc(x.otherName)} 반장)</span></li>`).join("")}</ul>` : "";
  $("#mg-need").innerHTML = miss.length ? `<b>${miss.length}개를 더 입력하세요</b><span>${esc(miss.join(", "))}</span>` : `<b class="ok">복사할 수 있습니다</b><span>누르면 문자를 복사하고 기록합니다. croScan은 문자를 보내지 않습니다</span>`;
  const btn = $("#mg-send"); btn.disabled = !!miss.length || !!sf.mgSending; btn.textContent = "문자 복사";
}
// copy the text: the clipboard API (https) or, on a plain http page, a selected textarea
async function copyText(text) {
  try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(text); return true; } } catch (e) { /* try the other way */ }
  const ta = el("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.cssText = "position:fixed;left:-9999px;top:0";
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove(); return ok;
}
// 「문자 복사」 (D35): the text is copied and that recorded (복사·기록 완료); croScan sends nothing. Nothing is recorded when the copy or the store fails
async function mgSend() {
  if (sf.mgSending) return;
  const p = postPairs().find((x) => x.key === sf.coordKey); if (!p) return;
  const m = mgModel(p), text = mgText(m); if (mgMissing(m, text).length) return;
  const post = sf.post, key = postKey();
  const rec = { pairKey: p.key, to: m.to.id, toName: m.name(m.to), toPhone: m.phone(m.to), other: m.other.id, otherName: m.name(m.other), otherPhone: m.phone(m.other),
    from: `${m.me.name} ${m.me.phone}`, at: nowHM(), iso: new Date().toISOString(), text, revs: [m.C.rev, m.X.rev], demo: true };
  sf.mgSending = true; mgRefresh();
  try {
    if (!(await copyText(text))) { toast("문자를 복사하지 못해 기록을 남기지 않았습니다. 다시 눌러 주세요"); return; }
    if (sf.post !== post || postKey() !== key) { toast("문자는 복사했지만 검토 자료가 바뀌어 기록하지 않았습니다"); return; }
    if (!postCommit(() => { (sf.post.msgs[p.key] = sf.post.msgs[p.key] || []).push(rec); })) return;
    sf.mgEdit = false;
    toast(`${rec.toName} 반장에게 보낼 문자를 복사하고 기록했습니다(복사·기록 완료). croScan은 문자를 보내지 않습니다. 기존 연락 방법으로 보내 주세요`);
  } finally { sf.mgSending = false; mgRefresh(); postRender(); }
}
$("#sf-p-body").addEventListener("input", (e) => {
  if ($("#sf-panel").dataset.mode !== "coord") return;
  const t = e.target, k = t.dataset && t.dataset.mg, f = mgFill(sf.coordKey);
  if (t.id === "mg-area") {
    const p = postPairs().find((x) => x.key === sf.coordKey), m = mgModel(p);
    f.text[m.to.id] = { v: t.value, base: f.text[m.to.id] && f.text[m.to.id].base != null ? f.text[m.to.id].base : mgPlain(mgParts(m)) };
    postSave(); mgRefresh(); return;
  }
  if (!k) return;
  if (k === "place") f.place = t.value;
  else if (k.startsWith("phone:")) f.phone[k.slice(6)] = t.value;
  else if (k.startsWith("name:")) (f.name = f.name || {})[k.slice(5)] = t.value;
  else if (k.startsWith("me.")) { const me = senderGet(); me[k.slice(3)] = t.value; senderSet(me); }
  postSave(); mgRefresh();
});
$("#sf-p-body").addEventListener("click", (e) => {
  if ($("#sf-panel").dataset.mode !== "coord") return;
  const f = sf.coordKey && mgFill(sf.coordKey), p = postPairs().find((x) => x.key === sf.coordKey); if (!p) return;
  const pick = e.target.closest("[data-mgto]");
  if (pick || e.target.closest("[data-mgswap]")) {          // the other foreman becomes the one the message goes to
    const m = mgModel(p); if (pick && pick.dataset.mgto === m.to.id) return;
    f.to = m.other.id; postSave(); postCoordOpen(p.key); $(`[data-mgto="${CSS.escape(f.to)}"]`)?.focus(); return;
  }
  if (e.target.closest("#mg-edit")) {
    const m = mgModel(p), auto = mgPlain(mgParts(m));
    if (!sf.mgEdit && !f.text[m.to.id]) f.text[m.to.id] = { v: auto, base: auto };      // the hand-written text starts from this one
    sf.mgEdit = !sf.mgEdit; postSave(); mgRefresh(); if (sf.mgEdit) $("#mg-area")?.focus(); return;
  }
  if (e.target.closest("[data-mgregen]")) { delete f.text[mgModel(p).to.id]; sf.mgEdit = false; postSave(); mgRefresh(); return; }
  const nb = e.target.closest("[data-mgnote]");
  if (nb) {                                                       // put in by the manager: the message becomes his text
    const n = sf.mgNote;
    if (!n || String(n.seq) !== nb.dataset.mgnote || n.key !== sf.coordKey || n.det !== sf.det) { toast("제안이 바뀌었습니다. 다시 확인해 주세요"); mgNote(sf.coordKey); return; }
    const m = mgModel(p), auto = mgPlain(mgParts(m)), cur = mgText(m), line = `협의할 점: ${n.text}`;
    if (!cur.includes(line)) {
      const lines = cur.split("\n");
      let at = -1;
      for (let i = lines.length - 1; i >= 0; i--) if (/^\s*안전관리자[\s,]/.test(lines[i])) { at = i; break; }   // the sender's block
      let v;
      if (at >= 0) { lines.splice(at, 0, line); v = lines.join("\n"); }
      else if (sf.mgEdit && $("#mg-area")) { const a = $("#mg-area"), pos = a.selectionStart ?? a.value.length; v = a.value.slice(0, pos) + (pos && a.value[pos - 1] !== "\n" ? "\n" : "") + line + "\n" + a.value.slice(pos); }
      else v = cur.replace(/\s*$/, "") + "\n" + line;
      f.text[m.to.id] = { v, base: f.text[m.to.id] && f.text[m.to.id].base != null ? f.text[m.to.id].base : auto };
      if (sf.mgEdit && $("#mg-area")) $("#mg-area").value = v;
      postSave(); mgRefresh(); toast("협의할 점을 문자에 넣었습니다. 복사하기 전에 확인해 주세요");
    }
    return;
  }
  if (e.target.closest("#mg-send")) mgSend();
});

// ② 서류 발행: the sheet is built from the rules' wording; the safety manager's edits are kept per cell ----------
// the documents a posting sheet (별지·전달문) is for: those in a pair, and those with a revision still out
const postIds = (pairIds, issues) => {
  const ids = new Set(pairIds);
  for (const [id, iss] of Object.entries(issues)) if (iss.some((x) => x.status === "valid" || !x.taken)) ids.add(id);
  return ids;
};
const docOrder = (a, b) => (a.type === b.type ? a.id.localeCompare(b.id) : a.type === "permit" ? -1 : 1);
function postDocsToIssue() {
  return [...postIds(postPairs().flatMap((p) => pairDocs(p).map((d) => d.id)), sf.post.issues)].map(sfDoc).filter(Boolean).sort(docOrder);
}
// Codex QA2 #1: the final output is of every document of the day (a permit in no pair too); only the 별지 part is for
// the documents of postDocsToIssue
const outDocs = (docs) => docs.slice().sort(docOrder);
const sheetNo = (d, rev) => `${d.type === "permit" ? "S-" + d.id : "N-" + sfNo(d).replace("-", "")}/R${rev}`;
function nextRev(d) { return (sf.post.issues[d.id] || []).length + 1; }
function sheetFor(d) {
  const ps = postPairs().filter((p) => pairDocs(p).some((x) => x.id === d.id));
  const rev = nextRev(d);
  const sections = ps.map((p) => {
    const b = p.base, [A, B] = pairDocs(p), other = A.id === d.id ? B : A, t = draftOf(p);
    const mine = t.cause === d.id ? t.cause_do : t.exposed_do, myC = t.cause === d.id ? t.contact_exposed : t.contact_cause;
    const oi = (sf.post.issues[other.id] || []).filter((x) => x.status === "valid").slice(-1)[0];
    const k = p.key;
    return { id: k, title: `${pairLabel(p)} · ${PRI[b.priority][0]} · 상대: ${sfNo(other)} ${other.title}`,
      rows: [[`${k}.do`, "우리 반이 할 일", mine, 1], [`${k}.start`, "착수조건", t.start + (t.handoff ? ` / 인계: ${t.handoff}` : "")],
        [`${k}.other`, "상대 작업", `${sfNo(other)} · ${other.type === "permit" ? other.dept : other.company} · ${sfWhere(other)} · ${sfTimes(other)}`],
        [`${k}.mine`, "우리 작업 일정", sfTimes(d)], [`${k}.risk`, "위험", t.risk], [`${k}.stop`, "중지·해제 조건", t.stop]]
        .concat(t.keep ? [[`${k}.keep`, "조치 유지·효과 확인", t.keep]] : [])
        .concat([[`${k}.contact`, "상대 반장·연락처", myC], [`${k}.ref`, "대응 서류(상대 쪽)", oi ? oi.no : `${sheetNo(other, nextRev(other))} (발행 예정)`]]) };
  });
  const head = d.type === "permit"
    ? [["별지 번호", `${sheetNo(d, rev)} · 쌍 ${ps.length}건`], ["허가번호", d.permit_no], ["작업일", sf.data.date]]
    : [["전달문 번호", `${sheetNo(d, rev)} · 쌍 ${ps.length}건`], ["작업계획서", `${d.id} · ${d.company}`], ["작업일", sf.data.date]];
  return { title: d.type === "permit" ? "병행작업 조정·착수조건 (별지)" : "일상작업반 전달문 (병행작업 조정·착수조건)", head,
    note: sfVerNote([d.id, ...ps.flatMap((p) => [p.base.a, p.base.b])]) + (d.type === "permit" ? "원본 허가서는 바꾸지 않았습니다. 이 별지의 최신 개정본만 유효합니다."
      : "이 작업은 허가서·게시물이 없어 이 전달문으로 알립니다. 생산 담당자가 작업지시·TBM 자료로 전달합니다. 최신 개정본만 유효합니다."),
    sections, foot: "착수조건을 확인하기 전에는 해당 단계를 시작하지 않습니다 · 개정되면 이전 판은 효력이 없습니다" };
}
// the same sheet with the safety manager's edits on top (cell ids are stable: pair key + row)
const CELL_MAX = 2000, LOCKED = new Set(["head.0"]);       // the sheet number and revision are made at issue
const edOf = (e) => (typeof e === "string" ? { v: e, base: null } : e);
// QA #62 changed the DROP_BELOW wording; a base saved with the old wording still matches its draft
const sheetNorm = (t) => String(t).replace(" 작업자 사고 (사고 유형: 맞음, 깔림/뒤집힘)", " 작업자 맞음·깔림").replace(/( 작업자가|이|가) 높은 곳\(/g, "_높은 곳(");
function sheetState(d) {        // edits whose draft changed since (stale) and over-long cells
  const s = sheetFor(d), ed = sf.post.edits[d.id] || {}, draft = {};
  s.head.forEach(([, v], i) => { draft[`head.${i}`] = v; }); draft.note = s.note;
  s.sections.forEach((x) => { draft[`${x.id}.title`] = x.title; x.rows.forEach(([id, , v]) => { draft[id] = v; }); });
  const stale = Object.entries(ed).filter(([id, e]) => !(id in draft) || (edOf(e).base != null && sheetNorm(edOf(e).base) !== sheetNorm(draft[id]))).map(([id]) => id);
  const long = Object.values(ed).some((e) => edOf(e).v.length > CELL_MAX);
  return { draft, stale, long };
}
function sheetEdited(d) {
  const s = sheetFor(d), ed = sf.post.edits[d.id] || {}, { stale } = sheetState(d);
  const put = (id, v) => (id in ed && !stale.includes(id) && !LOCKED.has(id) ? edOf(ed[id]).v : v);
  return { ...s, head: s.head.map(([k, v], i) => [k, put(`head.${i}`, v)]), note: put("note", s.note), foot: s.foot,
    sections: s.sections.map((sec) => ({ ...sec, title: put(`${sec.id}.title`, sec.title), rows: sec.rows.map(([id, l, v, st]) => [id, l, put(id, v), st]) })) };
}
const toPdfSheet = (s) => ({ ...s, sections: s.sections.map((x) => ({ title: x.title, rows: x.rows.map(([, l, v, st]) => [l, v, !!st]) })) });
function linesFor(d) {           // 추가조치 요청사항 칸 3줄 초안
  const ps = postPairs().filter((p) => pairDocs(p).some((x) => x.id === d.id));
  const others = ps.map((p) => { const [A, B] = pairDocs(p), o = A.id === d.id ? B : A; return `${pairLabel(p)} ${sfNo(o)}`; });
  return [`${others.join(", ")}과 병행작업 조정: 별지 ${sheetNo(d, nextRev(d))} 조건 적용.`, "상대 반장과 착수조건을 확인하기 전 해당 단계 착수 금지.", "시간·위치·공법이 바뀌면 그 단계 보류 후 재조정 요청."].join("\n");
}
function linesOf(d) {             // the safety manager's text, unless it was written for another revision of the sheet
  const l = sf.post.lines[d.id], cur = linesFor(d);
  return l && typeof l === "object" && l.base === cur ? l.v : cur;
}
const validIssue = (id) => (sf.post.issues[id] || []).filter((x) => x.status === "valid").slice(-1)[0];
// QA #99: 최종 서류 출력 opens once the safety manager has marked the document 확인 in 문서 목록 (the 자료 확인 mark of
// every part, kept in this browser). Never called 승인 here: the 전산승인 is the production department's authorised person's.
const outGate = (state) => state === "done" ? { ok: true, label: "확인" }
  : { ok: false, label: state === "changed" ? "변경됨 · 다시 확인" : state === "part" ? "확인 중" : "확인 전" };
// what one output gives: the permit (원본+별지 once a 별지 is issued, else 허가서+추가검토서) and its 위험 체크리스트;
// a 작업계획서 with its 전달문 once one is issued
// Codex QA2 #4: when the foreman submitted through croScan, the output is that submission's 추가검토서·체크리스트 (drawn
// once at 제출: the bytes of the submission the safety manager checked); else the documents as collected
function outFiles(d, is, sub) {
  const id = encodeURIComponent(d.id), no = sfNo(d), P = d.type === "permit";
  const sheet = is && { url: "/api/safety/sheet.pdf", name: `${is.no.replace("/", "_")}_${P ? "현장게시용_원본+별지" : "일상작업반_전달문"}.pdf`,
    body: { doc_id: d.id, kind: P ? "post" : "notice", sheet: is.sheet } };
  if (!P) return [{ url: `/api/safety/pdf/${id}/original.pdf`, name: `${no}_작업계획서.pdf` }].concat(sheet ? [sheet] : []);
  const S = (n) => `/api/submissions/${encodeURIComponent(sub)}/${n}.pdf`;
  return [sheet || (sub ? { url: S("permit"), name: `${no}_허가서+추가검토서_제출본.pdf` } : { url: `/api/safety/pdf/${id}/full.pdf`, name: `${no}_허가서+추가검토서.pdf` }),
    sub ? { url: S("checklist"), name: `${no}_위험체크리스트_제출본.pdf` } : { url: `/api/safety/pdf/${id}/checklist.pdf`, name: `${no}_위험체크리스트.pdf` }];
}
// Codex QA2 #2·#3·#4: what the server has now against the mark: the work day, the content, the latest submission
// rec: the mark; day: the day on screen; now: {day, rev, sub} read from the server just now; parts: what has to be marked
function outVerdict(rec, day, now, parts) {
  if (!rec || !parts.every(([k]) => rec.parts && rec.parts[k])) return "todo";
  if (now.day !== day || (rec.day && rec.day !== day)) return "day";
  if (rec.h !== now.rev) return "rev";
  if ((rec.sub || null) !== (now.sub || null)) return "sub";
  return "ok";
}
const OUT_WHY = { todo: "안전관리자 확인 뒤 출력합니다. 문서 목록에서 자료 확인을 마쳐 주세요",
  day: "서버의 작업일이 화면과 다릅니다. 화면을 새로 불러온 뒤 문서 목록에서 다시 확인해 주세요",
  rev: "확인한 뒤 서류 내용이 바뀌었습니다. 문서 목록에서 다시 확인해 주세요",
  sub: "확인한 뒤 작업반장이 새로 제출했습니다. 문서 목록에서 다시 확인해 주세요" };
async function outNow(d) {             // the document and the day's submissions as the server has them now
  const get = (u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(`서버 오류 ${r.status}`))));
  const [doc, subs] = await Promise.all([get(`/api/safety/doc/${encodeURIComponent(d.id)}`), get("/api/safety/submissions")]);
  return { doc, subs, day: subs._day, rev: doc.rev, sub: d.type === "permit" ? ((subs[d.permit_no] || {}).id || null) : null };
}
async function pdfFetch(f) {
  const r = await fetch(f.url, { cache: "no-store", ...(f.body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(f.body) } : {}) });
  if (!r.ok) { let m = `서버 오류 ${r.status}`; try { m = (await r.json()).detail || m; } catch (e) { /* not json */ } throw new Error(m); }
  return r.blob();
}
function blobSave(blob, name) {
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = name; a.rel = "noopener"; a.style.display = "none";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 120000);
}
async function pdfSave(f) { blobSave(await pdfFetch(f), f.name); }
// 「다시 확인」: what the server has now is taken in, so the lists say 변경됨 and the mark is made again on it
function outTakeNow(d, now) {
  const { form, records, checklist_items, items, kind_title, ...meta } = now.doc;
  if (now.day === sf.data.date) { Object.assign(d, meta); sfCache[d.id] = now.doc; sf.subs = now.subs; }
  sfRefresh(); postRender();
}
async function outPrint(id, btn) {
  const d = sfDoc(id); if (!d) return;
  if (!outGate(sfState(d)).ok) { toast(OUT_WHY.todo); return; }
  const rec = sfSeenOf(d), parts = SF_PARTS[d.type], day = sf.data.date;
  if (btn) btn.disabled = true;
  try {
    let now = await outNow(d), v = outVerdict(rec, day, now, parts);
    if (v !== "ok") { outTakeNow(d, now); toast(OUT_WHY[v]); return; }
    const fs = outFiles(d, validIssue(id), rec.sub || null);
    toast(`${sfNo(d)} 서류 ${fs.length}개 만드는 중…`);
    const blobs = [];
    for (const f of fs) blobs.push(await pdfFetch(f));
    // the server may have changed while they were drawn: they are saved only when it still has what was checked
    now = await outNow(d); v = outVerdict(rec, day, now, parts);
    if (v !== "ok") { outTakeNow(d, now); toast(OUT_WHY[v]); return; }
    fs.forEach((f, i) => blobSave(blobs[i], f.name));
    toast(`${fs.map((f) => f.name).join(", ")} 내려받기`);
  } catch (err) { toast(`PDF를 만들지 못했습니다: ${err.message}`); }
  finally { const b = btn && btn.isConnected ? btn : document.querySelector(`#sf-post-body [data-out="${CSS.escape(id)}"]`); if (b) b.disabled = !outGate(sfState(d)).ok; }
}
// Codex QA2 #7: every revision of the posting sheet with what was recorded of it (발행·전달·수신·게시·효력 없음·회수),
// the withdrawn ones too
function postRevLog(d) {
  const iss = sf.post.issues[d.id] || [];
  if (!iss.length) return "";
  const D = { sent: "전달", recv: "수신 확인", posted: d.type === "permit" ? "게시(교체) 완료" : "작업지시 첨부 완료" };
  return `<div class="sf-revlog"><b>개정별 기록</b><ol>` + iss.slice().reverse().map((x) => {
    const ev = [`발행 ${x.at}`, ...Object.entries(x.delivery || {}).map(([k, v]) => `${D[k] || k} ${v.by} ${v.at}`),
      ...(x.status === "void" ? [`효력 없음 ${x.voidAt || ""}${x.voidWhy ? ` (${x.voidWhy})` : ""}`.trim()] : []), ...(x.taken ? [`회수 확인 ${x.taken}`] : [])];
    return `<li class="${x.status === "valid" ? "ok" : "void"}"><span class="sf-revno">${esc(x.no)} · ${x.status === "valid" ? "유효" : x.taken ? "회수됨" : "회수 대상"}</span>`
      + `<span>${ev.map(esc).join(" · ")}</span></li>`;
  }).join("") + `</ol></div>`;
}
function postIssueList() {
  const docs = outDocs(sf.docs), postable = new Set(postDocsToIssue().map((d) => d.id));
  const ready = docs.filter((d) => outGate(sfState(d)).ok).length, issued = docs.filter((d) => validIssue(d.id)).length;
  return `<div class="sf-out-head"><h3>최종 서류 출력</h3><b>총 ${docs.length}건</b></div>`
    + `<p class="hint sf-out-note">문서 목록에서 자료 확인(확인)을 마친 서류만 출력됩니다 · 출력 직전에 확인한 판인지 다시 봅니다 · 확인 표시는 이 브라우저 기록이며 전산승인이 아닙니다</p>`
    + `<ol class="sf-olist">` + docs.map((d) => {
    const iss = sf.post.issues[d.id] || [], cur = validIssue(d.id), voids = iss.filter((x) => x.status === "void" && !x.taken);
    const edits = Object.keys(sf.post.edits[d.id] || {}).length, re = cur && sf.post.reopen[d.id], g = outGate(sfState(d)), P = d.type === "permit";
    const rev = cur ? cur.no.split("/")[1] : "", sub = P && sfSubId(d);
    const what = P ? (cur ? `허가서+별지 ${rev} · 위험 체크리스트` : "허가서+추가검토서 · 위험 체크리스트") + (sub ? " (제출본)" : "") : (cur ? `작업계획서 · 전달문 ${rev}` : "작업계획서");
    return `<li class="sf-orow"><div class="sf-oline">${sfTagHtml(d)}<div class="sf-omain"><b>${esc(d.title)}</b><span class="hint">${esc(sfNo(d))} · 출력: ${esc(what)}</span></div>`
      + `<span class="sf-ostate${g.ok ? " ok" : ""}">${g.ok ? icon("i-check") : ""}${esc(g.label)}</span>`
      + `<button type="button" class="btn small${g.ok ? " primary" : ""}" data-out="${esc(d.id)}"${g.ok ? "" : ` disabled title="안전관리자 확인 뒤 출력"`}>${P ? "허가서/체크리스트 출력" : "계획서/전달문 출력"}</button></div>`
      + voids.map((v) => `<span class="sf-iss void">${esc(v.no)} 효력 없음·회수 대상 (${esc(v.voidWhy || "")}) <button type="button" class="linkbtn" data-taken="${esc(d.id)}|${esc(v.no)}">회수 확인</button></span>`).join("")
      // the posting sheet (별지·전달문) as before, for the documents in a pair: issued as a revision, delivered, kept apart from the output
      + (postable.has(d.id) ? `<details class="sf-omore" data-omore="${esc(d.id)}"${sf.outOpen.has(d.id) ? " open" : ""}><summary>${P ? "현장 게시 별지" : "일상작업반 전달문"} · `
      + (cur ? `<span class="sf-iss ok">${esc(cur.no)} 발행 ${esc(cur.at)}${re ? " · 새 개정본 작성 중" : ""}</span>` : `<span class="sf-iss">미발행${edits ? ` · 고친 칸 ${edits}` : ""}</span>`) + `</summary>`
      + `<p class="hint">${P ? "현장 게시용 = 허가서 원본 + 별지" : "일상작업반 전달문 (발췌본)"}</p>` + (cur ? postDelivery(d, cur) : "")
      + `<div class="sf-dact"><button class="btn small" data-sheet="${esc(d.id)}">${cur && !re ? "보기" : "미리 보기·편집"}</button>`
      // the issued sheet is an output too: only after the check (QA #99); the separate PDFs come from the 출력 button
      + (cur && !re ? `<button class="btn small" data-pdf="${esc(d.id)}"${g.ok ? "" : ` disabled title="안전관리자 확인 뒤 출력"`}>${icon("i-pdf")}PDF ${esc(rev)}</button>`
        : `<button class="btn small primary" data-issue="${esc(d.id)}">발행</button>`) + `</div>`
      + postRevLog(d) + `</details>` : "") + `</li>`;
  }).join("") + `</ol><div class="sf-pfoot"><span>출력 가능 ${ready}/${docs.length} · 별지·전달문 발행 ${issued}/${postable.size}</span></div>`;
}
function postDelivery(d, is) {
  const st = is.delivery || {}, step = (k, l) => st[k] ? `<span class="sf-dl ok">${l} ${esc(st[k].by)} ${esc(st[k].at)}</span>` : `<button type="button" class="sf-dl" data-deliver="${esc(d.id)}|${k}">${l}</button>`;
  return `<span class="sf-dels">${step("sent", "전달")}${step("recv", "수신 확인")}${step("posted", d.type === "permit" ? "게시(교체) 완료" : "작업지시 첨부 완료")}</span>`;
}
function postIssue(id) {
  const d = sfDoc(id), st = sheetState(d);
  if (validIssue(id) && !sf.post.reopen[id]) return;
  if (st.stale.length || st.long) { toast(st.long ? `한 칸은 ${CELL_MAX}자까지입니다` : `초안이 바뀐 칸 ${st.stale.length}개를 먼저 확인하세요`); return; }
  const s = sheetEdited(d), rev = nextRev(d), no = sheetNo(d, rev), lines = d.type === "permit" ? linesOf(d) : "";
  // a new revision replaces the one on the wall: the old one is to be taken down
  if (!postCommit(() => {
    for (const is of sf.post.issues[id] || []) if (is.status === "valid") Object.assign(is, { status: "void", voidWhy: `${no} 발행`, voidAt: nowHM() });
    (sf.post.issues[id] = sf.post.issues[id] || []).push({ rev, no, at: nowHM(), sheet: { ...toPdfSheet(s), ...postAiOf(d, rev) }, status: "valid", lines });
    delete sf.post.reopen[id]; sf.post.log.push(`${nowHM()} ${no} 발행`);
  })) return;
  postRender(); toast(`${no} 발행`);
}
async function postPdf(id, btn) {
  const d = sfDoc(id), is = validIssue(id);
  const sheet = is ? is.sheet : { ...toPdfSheet(sheetEdited(d)), ...postAiOf(d, nextRev(d)) };
  const name = `${(is ? is.no : sheetNo(d, nextRev(d)) + "_미발행").replace("/", "_")}_${d.type === "permit" ? "현장게시용_원본+별지" : "일상작업반_전달문"}.pdf`;
  if (btn) btn.disabled = true;
  toast(`${name} 만드는 중…`);
  try {
    await pdfSave({ url: "/api/safety/sheet.pdf", name, body: { doc_id: id, kind: d.type === "permit" ? "post" : "notice", sheet } });
    toast(`${name} 내려받기`);
  } catch (err) { toast(`PDF를 만들지 못했습니다: ${err.message}`); }
  finally { if (btn) btn.disabled = false; }
}
// the document editor: the sheet as it will print; a value cell is edited in place (like the 작업계획서 editor)
function postSheetOpen(id) {
  const d = sfDoc(id), cur = validIssue(id), iss = sf.post.reopen[id] ? null : cur;
  sf.sheetDoc = id; sf.openPair = null; sf.open = null; sf.req++;
  const P = $("#sf-panel"); P.hidden = false; P.dataset.mode = "sheet";
  $("#sf-p-kind").textContent = d.type === "permit" ? "현장 게시용 별지" : "일상작업반 전달문"; $("#sf-p-kind").className = "eyebrow";
  $("#sf-p-title").textContent = `${sfNo(d)} ${d.title}`;
  $("#sf-p-meta").textContent = iss ? `${iss.no} 발행본 · 고치려면 「새 개정본 작성」` : cur ? `${cur.no}의 새 개정본 · 칸을 눌러 고칠 수 있습니다` : "미발행 · 칸을 눌러 고칠 수 있습니다";
  $("#sf-p-tabs").hidden = true; $("#sf-p-note").hidden = true;
  $("#sf-p-pos").textContent = ""; $("#sf-p-prev").disabled = $("#sf-p-next").disabled = true;
  const s = iss ? null : sheetEdited(d), ed = sf.post.edits[id] || {}, st = iss ? { stale: [] } : sheetState(d);
  const cell = (cid, v, cls = "") => iss || LOCKED.has(cid) ? `<div class="sh-v ${cls}">${esc(v)}</div>`
    : st.stale.includes(cid) ? `<div class="sh-v ${cls} stale" contenteditable="true" spellcheck="false" data-cell="${esc(cid)}" title="${esc("전에 고친 내용: " + edOf(ed[cid]).v)}">${esc(v)}</div>`
    : `<div class="sh-v ${cls}${cid in ed ? " edited" : ""}" contenteditable="true" spellcheck="false" data-cell="${esc(cid)}">${esc(v)}</div>`;
  const src = iss ? { ...iss.sheet, sections: iss.sheet.sections.map((x, i) => ({ ...x, id: "s" + i, rows: x.rows.map(([l, v, st], j) => ["r" + j, l, v, st]) })) } : s;
  let h = `<div class="sh-page"><div class="sh-top"><div class="sh-title">${esc(src.title)}</div><div class="sh-head">`
    + src.head.map(([k, v], i) => `<span>${esc(k)}</span>${cell(`head.${i}`, v)}`).join("") + `</div></div>`
    + (src.note ? cell("note", src.note, "sh-note") : "")
    + src.sections.map((sec) => cell(`${sec.id}.title`, sec.title, "sh-bar") + `<div class="sh-kv">` + sec.rows.map(([cid, l, v, st]) => `<span>${esc(l)}</span>${cell(cid, v, st ? "strong" : "")}`).join("") + `</div>`
      + (iss ? "" : postAiBox(id, sec.id))).join("")
    + `<div class="sh-foot">${esc(src.foot || "")}</div></div>`;
  const tbm = Object.entries(sf.postDraft).filter(([k, v]) => k.startsWith(`${id}|`) && v && v.tbm).map(([, v]) => v.tbm)[0];
  if (tbm && d.type !== "permit") h += `<h3>TBM 전달 초안 <span class="ai-chip">AI 초안</span></h3><p class="hint">기존 작업지시·TBM 자료에 옮길 때 쓰는 초안입니다. 전달·TBM 실시 기록이 아닙니다.</p>`
    + `<textarea class="sf-lines" rows="3" readonly>${esc(tbm.join("\n"))}</textarea>`;
  if (d.type === "permit") h += `<h3>허가서 「작업허가 전 추가조치 요청사항」 칸 3줄 초안</h3><p class="hint">원본에 찍지 않습니다. 안전요원·안전관리자가 기존 방식(전산 입력 또는 수기)으로 적을 때 쓰는 초안입니다.</p>`
    + `<textarea class="sf-lines" id="sf-lines" rows="3" ${iss ? "readonly" : ""}>${esc(iss ? iss.lines : linesOf(d))}</textarea><button class="btn small" id="sf-lines-copy">${icon("i-file")}복사</button>`;
  const n = Object.keys(ed).length - st.stale.length;
  if (!iss && st.stale.length) h += `<p class="sf-pblock">초안이 달라진 칸 ${st.stale.length}개(주황)는 전에 고친 내용을 적용하지 않았습니다. 칸에 마우스를 올리면 전 내용이 보입니다. 다시 고치거나 「바뀐 칸에 새 초안 적용」을 누르세요. <button class="btn small" id="sh-stale">바뀐 칸에 새 초안 적용</button></p>`;
  h += iss ? `<div class="sf-cact"><button class="btn" id="sh-reopen">새 개정본 작성</button><button class="btn primary" id="sh-pdf2">${icon("i-pdf")}PDF ${esc(iss.no)}</button></div>`
    : `<div class="sf-cact"><span class="hint">${n ? `고친 칸 ${n}개 (노란 표시)` : "고친 칸 없음"}</span>${cur ? `<button class="btn" id="sh-cancel">새 개정본 취소</button>` : ""}<button class="btn" id="sh-reset" ${n ? "" : "disabled"}>고친 칸 모두 초안으로 되돌리기</button><button class="btn primary" id="sh-issue" ${st.stale.length ? "disabled" : ""}>${st.stale.length ? "바뀐 칸 확인 후 발행" : cur ? `${sheetNo(d, nextRev(d)).split("/")[1]}로 발행` : "이 내용으로 발행"}</button></div>`;
  $("#sf-p-body").innerHTML = h;
  $("#sf-p-close").focus({ preventScroll: true });
  if (!iss) {
    $("#sh-reset").onclick = () => { delete sf.post.edits[id]; postSave(); postSheetOpen(id); };
    if ($("#sh-cancel")) $("#sh-cancel").onclick = () => { delete sf.post.reopen[id]; postSave(); postRender(); postSheetOpen(id); };
    if ($("#sh-stale")) $("#sh-stale").onclick = () => { for (const k of st.stale) delete sf.post.edits[id][k]; postSave(); postSheetOpen(id); };
    $("#sh-issue").onclick = () => { if (document.activeElement && document.activeElement.blur) document.activeElement.blur(); setTimeout(() => { postIssue(id); postSheetOpen(id); }, 0); };
    if ($("#sf-lines")) $("#sf-lines").oninput = (e) => { sf.post.lines[id] = { v: e.target.value, base: linesFor(d) }; postSave(); };
  } else $("#sh-reopen").onclick = () => { sf.post.reopen[id] = true; postSave(); postRender(); postSheetOpen(id); };
  if ($("#sh-pdf2")) $("#sh-pdf2").onclick = (e) => postPdf(id, e.currentTarget);
  if ($("#sf-lines-copy")) $("#sf-lines-copy").onclick = () => { navigator.clipboard?.writeText($("#sf-lines").value).then(() => toast("복사했습니다"), () => toast("복사하지 못했습니다")); };
}
// 게시 서류 AI 보충 (design §6.5·§19.2): 「우리 반은 {시점·대상}에 {할 일}」 → 착수조건 → 중지·변경 시 연락, from the
// rule's wording and the work's confirmed answers (the model picks, the server writes); [AI 초안 → 문안 채택]. Adopting
// fills the unissued sheet's cells as the manager's own edits; it is not sending, not a TBM held, not a start allowed.
sf.postDraft = {};
function postAiBox(id, key) {
  const dr = sf.postDraft[`${id}|${key}`];
  if (!dr) return `<div class="sh-ai"><button type="button" class="linkbtn" data-shai-go="${esc(key)}">AI 문안 보충 보기</button></div>`;
  if (dr.loading) return `<div class="sh-ai" role="status"><span class="ai-chip">AI</span>문안을 준비하는 중</div>`;
  if (!dr.lines || !dr.lines.length) return `<div class="sh-ai"><p class="hint">AI 결과를 준비하지 못함 · 규칙 문안 그대로 씁니다</p></div>`;
  const taken = ((sf.post.ai[id] || {}).taken || {})[key];
  return `<div class="sh-ai sh-ai-d"><p><span class="ai-chip">${taken ? "문안 채택" : "AI 초안"}</span></p><ol>${dr.lines.map((l) => `<li>${esc(l)}</li>`).join("")}</ol>`
    + `<p class="hint">근거: ${dr.sources.map((s) => `${esc(s.kind)} 「${esc(s.text)}」`).join(" · ")}</p>`
    + (taken ? `<p class="hint">「우리 반이 할 일」·「착수조건」 칸에 넣었습니다(발행 전 고칠 수 있음).</p>`
      : `<div class="sf-cact"><button type="button" class="btn small primary" data-shai-take="${esc(key)}">문안 채택</button></div>`) + `</div>`;
}
const postAiOf = (d, rev) => {
  const a = sf.post.ai[d.id], off = Object.keys((a || {}).offered || {}), tk = Object.keys((a || {}).taken || {});
  return tk.length ? { ai: { state: tk.length >= off.length ? "채택" : "일부 채택", rev: `R${rev}` } } : {};
};
async function postAiGo(id, key) {
  const k = `${id}|${key}`; sf.postDraft[k] = { loading: true }; postSheetOpen(id);
  let j = {};
  try {
    const r = await fetch("/api/safety/post-draft", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key, doc: id }) });
    j = r.ok ? await r.json() : {};
  } catch (e) { j = {}; }
  sf.postDraft[k] = j;
  if (j.lines && j.lines.length) { const a = (sf.post.ai[id] = sf.post.ai[id] || { offered: {}, taken: {} }); a.offered[key] = true; postSave(); }
  if (sf.sheetDoc === id && $("#sf-panel").dataset.mode === "sheet") postSheetOpen(id);
}
function postAiTake(id, key) {
  const dr = sf.postDraft[`${id}|${key}`], d = sfDoc(id);
  if (!dr || !dr.lines || validIssue(id) && !sf.post.reopen[id]) return;      // an issued sheet is not changed
  const draft = sheetState(d).draft, eds = (sf.post.edits[id] = sf.post.edits[id] || {});
  eds[`${key}.do`] = { v: dr.lines[0], base: draft[`${key}.do`] ?? null };
  eds[`${key}.start`] = { v: dr.lines[1].replace(/^착수조건:\s*/, ""), base: draft[`${key}.start`] ?? null };
  const a = (sf.post.ai[id] = sf.post.ai[id] || { offered: {}, taken: {} }); a.offered[key] = true; a.taken[key] = true;
  if (d.type === "permit" && dr.extra) sf.post.lines[id] = { v: dr.extra.join("\n"), base: linesFor(d) };
  postSave(); postSheetOpen(id); toast("AI 문안을 미발행 서류에 넣었습니다. 발행 전에 확인해 주세요");
}
$("#sf-p-body").addEventListener("click", (e) => {
  if ($("#sf-panel").dataset.mode !== "sheet" || !sf.sheetDoc) return;
  const go = e.target.closest("[data-shai-go]"); if (go) { postAiGo(sf.sheetDoc, go.dataset.shaiGo); return; }
  const tk = e.target.closest("[data-shai-take]"); if (tk) postAiTake(sf.sheetDoc, tk.dataset.shaiTake);
});
function postRender() {
  if (!sf.det || !sf.post) return;
  if (!POST_STEPS.some(([k]) => k === sf.pstep)) sf.pstep = "coord";
  const ps = postPairs(), sent = ps.filter((p) => msgsOf(p.key).length).length, docs = postDocsToIssue();
  const issued = docs.filter((d) => validIssue(d.id)).length;
  $("#sf-psteps").innerHTML = POST_STEPS.map(([k, l]) => `<li><button type="button" data-pstep="${k}" aria-pressed="${sf.pstep === k}">${l}<i>${k === "coord" ? `${sent}/${ps.length}` : `${issued}/${docs.length}`}</i></button></li>`).join("");
  $("#sf-post-body").innerHTML = sf.pstep === "coord" ? postCoordList() : postIssueList();
}
$("#sf-post-btn").onclick = () => { if (!sf.det) return; if (!sf.post) postLoad(); sfMain("post"); postRender(); sfJumpTo(".sf-post"); };
$("#sf-post-back").onclick = () => sfMain("pairs");
$("#sf-plist").addEventListener("scroll", sfMoreHint, { passive: true });
$("#sf-more").onclick = () => { const L = $("#sf-plist"); L.scrollBy({ top: L.clientHeight * .8, behavior: "smooth" }); };
SF_WIDE.addEventListener("change", () => { if (!sf.data) return; if (sfInline() && sf.openPair) { const id = sf.openPair; sfOpenPair(id, true); } sfPairsView(); });
// a cell of the sheet being edited: compared with croScan's draft, kept only when it differs
// (one delegated listener: onfocusout is not an element property in every browser)
$("#sf-p-body").addEventListener("focusout", (e) => {
  if ($("#sf-panel").dataset.mode !== "sheet" || !sf.sheetDoc) return;
  const c = e.target.closest("[data-cell]"); if (!c || c.getAttribute("contenteditable") !== "true") return;
  const id = sf.sheetDoc, v = c.innerText.replace(/\n$/, ""), cid = c.dataset.cell, eds = (sf.post.edits[id] = sf.post.edits[id] || {});
  const dv = sheetState(sfDoc(id)).draft[cid], wasStale = c.classList.contains("stale");
  if (v.length > CELL_MAX) toast(`한 칸은 ${CELL_MAX}자까지입니다. 줄이지 않으면 발행되지 않습니다`);
  if (v === dv) delete eds[cid]; else eds[cid] = { v, base: dv };
  if (wasStale && v === dv) delete eds[cid];                 // looked at again and the draft kept
  c.classList.remove("stale"); c.classList.toggle("edited", cid in eds); postSave();
  if (wasStale) { postSheetOpen(id); return; }
  const k = Object.keys(eds).length, hint = document.querySelector("#sf-p-body .sf-cact .hint");
  if (hint) hint.textContent = k ? `고친 칸 ${k}개 (노란 표시)` : "고친 칸 없음";
  if ($("#sh-reset")) $("#sh-reset").disabled = !k;
});
// the posting sheet details stay open over a redraw (an issue or a 확인 mark draws the list again)
$("#sf-post-body").addEventListener("toggle", (e) => { const x = e.target.closest && e.target.closest("[data-omore]"); if (x) sf.outOpen[x.open ? "add" : "delete"](x.dataset.omore); }, true);
$("#sf-psteps").onclick = (e) => { const b = e.target.closest("[data-pstep]"); if (b) { sf.pstep = b.dataset.pstep; postRender(); } };
$("#sf-post-body").addEventListener("click", (e) => {
  const t = (s) => e.target.closest(s);
  let b;
  if ((b = t("[data-coord]"))) { postCoordOpen(b.dataset.coord); return; }
  if ((b = t("[data-pstep]"))) { sf.pstep = b.dataset.pstep; postRender(); return; }
  if ((b = t("[data-out]"))) { outPrint(b.dataset.out, b); return; }
  if ((b = t("[data-sheet]"))) { postSheetOpen(b.dataset.sheet); return; }
  if ((b = t("[data-issue]"))) { postIssue(b.dataset.issue); return; }
  if ((b = t("[data-pdf]"))) { postPdf(b.dataset.pdf, b); return; }
  if ((b = t("[data-taken]"))) { const [id, no] = b.dataset.taken.split("|"); const is = (sf.post.issues[id] || []).find((x) => x.no === no); if (is && postCommit(() => { is.taken = nowHM(); sf.post.log.push(`${nowHM()} ${no} 회수 확인`); })) postRender(); return; }
  if ((b = t("[data-deliver]"))) {
    const [id, k] = b.dataset.deliver.split("|"), who = prompt({ sent: "전달한 사람(배포 담당)", recv: "받은 사람(반장)", posted: "게시·첨부한 사람" }[k] + " 이름");
    if (!who) return;
    const is = validIssue(id);
    if (is && postCommit(() => { is.delivery = is.delivery || {}; is.delivery[k] = { by: who.trim(), at: nowHM() }; sf.post.log.push(`${nowHM()} ${is.no} ${b.textContent} ${who.trim()}`); })) postRender();
  }
});

// one document ----------------------------------------------------------
const sfCache = {};
async function sfOpen(id, part = 0) {
  const d = sfDoc(id);
  if (!d) return;
  const token = ++sf.req;                      // only the latest request may fill the panel
  sf.open = id; sf.part = part; sf.loaded = null; sf.openPair = null; sf.pair = null;
  $("#sf-panel").dataset.mode = "doc"; $("#sf-p-kind").className = "eyebrow";
  $("#sf-resume").hidden = true;
  sfSelect(id, true, true);                    // the panel says when it is; no toast over its buttons
  history.replaceState(null, "", `#safety/${sf.data.date}/${encodeURIComponent(id)}`);
  const P = $("#sf-panel"); P.hidden = false;
  sfPanelHead(d);
  $("#sf-p-body").innerHTML = `<p class="hint">불러오는 중…</p>`;
  sfPanelChrome(d);
  $("#sf-p-close").focus({ preventScroll: true });            // inside the panel, so Tab / Shift+Tab stay in it
  sfSaveView();
  try {
    let x = sfCache[id];
    if (!x || x.rev !== d.rev) {
      const r = await fetch(`/api/safety/doc/${encodeURIComponent(id)}`);
      if (!r.ok) throw new Error(`서버 오류 ${r.status}`);
      x = await r.json();
      sfCache[id] = x;
    }
    if (token !== sf.req) return;
    if (x.rev !== d.rev) {                                 // changed since the list was read: show and mark the new version only
      const { form, records, checklist_items, items, kind_title, ...meta } = x;
      Object.assign(d, meta); sfPanelHead(d); sfProfile(); sfRefresh();
    }
    sf.loaded = id;
    sfPanelChrome(d); sfPanelBody(d, x);
  } catch (err) {
    if (token !== sf.req) return;
    $("#sf-p-body").innerHTML = `<div class="alert bad">자료를 불러오지 못했습니다: ${esc(err.message)}</div>`;
    sfPanelChrome(d);
  }
}
function sfPanelHead(d) {
  $("#sf-p-kind").textContent = d.type === "permit" ? `${d.label} 허가서 · ${d.permit_type || "허가 구분 없음"}` : `작업계획서 · ${d.company}`;
  $("#sf-p-title").textContent = d.title;
  $("#sf-p-meta").textContent = `${d.type === "permit" ? d.permit_no : d.id} · ${sfWhere(d)} · ${sfTimes(d)}${d.workers ? ` · ${d.workers}명` : ""}`;
}
// where 「확인하고 …」 goes: decided before marking, so a 미확인 filter cannot drop the next work from under it
function sfNextTarget(d) {
  const parts = SF_PARTS[d.type];
  if (sf.part < parts.length - 1) return { part: sf.part + 1 };
  const list = sfVisible(), i = list.findIndex((x) => x.id === d.id);
  const order = i < 0 ? list : [...list.slice(i + 1), ...list.slice(0, i)];
  const nx = order.find((x) => x.id !== d.id && sfState(x) !== "done");
  return nx ? { id: nx.id } : null;
}
function sfPanelChrome(d) {
  const m = sfMarks(d), parts = SF_PARTS[d.type], [k, l] = parts[sf.part], on = !!m[k], ready = sf.loaded === d.id;
  $("#sf-p-tabs").hidden = parts.length < 2;
  $("#sf-p-tabs").innerHTML = parts.map(([pk, pl], i) => `<button type="button" data-part="${i}" aria-pressed="${sf.part === i}">${m[pk] ? icon("i-check") : ""}${pl}</button>`).join("");
  const notes = [];
  if (sfState(d) === "changed") notes.push("내용이 바뀌어 이전 확인 표시를 지웠습니다. 다시 확인해 주세요.");
  if (!sfVisible().some((x) => x.id === d.id)) notes.push("이 작업은 지금 목록 조건 밖에 있습니다.");
  $("#sf-p-note").hidden = !notes.length; $("#sf-p-note").textContent = notes.join(" ");
  const list = sfVisible(), i = list.findIndex((x) => x.id === d.id);
  $("#sf-p-pos").textContent = i < 0 ? `목록 밖 · ${list.length}건` : `${i + 1} / ${list.length}`;
  $("#sf-p-prev").disabled = i <= 0; $("#sf-p-next").disabled = !list.length || i >= list.length - 1;
  const tg = sfNextTarget(d), where = !tg ? "" : tg.part != null ? `${parts[tg.part][1]}로` : "다음 작업으로";
  const go = $("#sf-p-go");
  go.disabled = !ready;
  go.innerHTML = on ? (tg ? `${where}${icon("i-right")}` : "닫기") : `${icon("i-check")}${l} 확인` + (tg ? `하고 ${where}` : "");
  const undo = $("#sf-p-undo"), last = sf.last && sfDoc(sf.last.id);
  if (on) { undo.hidden = false; undo.textContent = "확인 취소"; undo.disabled = !ready; }
  else if (last && !(last.id === d.id && sf.last.k === k)) { undo.hidden = false; undo.disabled = false; undo.textContent = `직전 확인 취소 (${sfNo(last)} ${SF_PARTS[last.type].find(([x]) => x === sf.last.k)[1]})`; }
  else undo.hidden = true;
  $("#sf-p-save").textContent = sf.stored ? "자료 확인 표시는 이 브라우저에만 저장됩니다 · 승인 아님" : "저장할 수 없는 브라우저입니다: 확인 표시는 이 화면을 닫으면 사라집니다";
}
const sfPdf = (id, part, label) => `<a class="btn small" href="/api/safety/pdf/${encodeURIComponent(id)}/${part}.pdf" target="_blank" rel="noopener">${icon("i-pdf")}${label}</a>`;
function sfPanelBody(d, x) {
  const kv = (rows) => `<dl class="sf-kv">${rows.filter(([, v]) => v !== "" && v != null).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  let h = "";
  if (d.type === "plan") {
    let sec;
    h = `<div class="sf-p-act">${sfPdf(d.id, "original", "원본 PDF")}</div>` + sfSignalHtml(d) + sfSumHtml(d);
    for (const i of x.items.filter((i) => i.value)) {
      if (i.section !== sec) { h += (sec !== undefined ? "</dl>" : "") + `<h3>${esc(i.section || "작업")}</h3><dl class="sf-kv">`; sec = i.section; }
      h += `<dt>${esc(i.label)}</dt><dd>${esc(i.value)}</dd>`;
    }
    h += "</dl>";
  } else if (sf.part === 0) {
    const orig = (x.form.find((f) => f.name.startsWith("작업장소")) || {}).value;
    h = `<div class="sf-p-act">${sfPdf(d.id, "original", "원본 PDF")}</div>`
      + sfSumHtml(d) + `<h3>작업</h3>` + kv([["작업명", d.title], ["상세", d.detail], ["작업 장소 (허가서)", orig], ["위치 (답변 반영)", d.place], ["이동 경로", d.route],
        ["작업 시간 (답변 반영)", sfTimes(d)], ["작업 인원", d.workers ? `${d.workers}명` : ""], ["유해위험요소", d.hazards], ["병행여부 (허가서)", d.concurrent || "(빈칸)"]])
      + `<h3>신청</h3>` + kv([["작업부서", d.dept], ["작업책임자", d.supervisor], ["허가신청자", d.applicant], ["신청일", d.applied], ["허가 구분", d.permit_type], ["PTW 2중점검", d.double_check ? `${d.double_check} (PTW 스캔 때 정해진 값 · croScan은 판정하지 않음${d.double_check === "Y" ? " · 작업일 아침 대면허가 대상" : ""})` : "값 없음"], ["허가기간", sfPeriod(d) || (d.days || []).join(", ")]])
      + `<details class="sf-more"><summary>허가서에서 읽은 칸 ${x.form.length}개 모두 보기</summary>` + kv(x.form.map((f) => [f.name, f.type === "check" ? "체크" : f.value])) + "</details>";
  } else if (sf.part === 1) {
    h = sfSubHtml(d) + `<div class="sf-p-act">${sfPdf(d.id, "full", "허가서 + 추가검토서 PDF")}</div>`
      + `<p class="hint">작업반장이 croScan 확인 질문에 답한 내용입니다. 원래 허가서는 고치지 않았습니다.</p>`
      + (x.records.length ? `<table class="sf-rec"><thead><tr><th>항목</th><th>원래 값 → 답</th><th>상태</th></tr></thead><tbody>` + x.records.map((r) =>
        `<tr${r.status === "미확인" ? ` class="unc"` : ""}><td>${esc(r.item)}</td><td><span class="was">${esc(r.original || "(빈칸)")}</span> → <b>${esc(r.value || r.answer)}</b>`
        + `<details><summary>질문 보기</summary>${esc(r.question)}</details></td><td><span class="sf-st st-${esc(r.status)}">${esc(r.status)}</span></td></tr>`).join("") + "</tbody></table>"
        : `<p>추가 답변이 없습니다.</p>`);
  } else {
    const groups = [["check", "안전팀 확인"], ["yes", "해당"], ["no", "해당 없음"]];
    h = `<div class="sf-p-act">${sfPdf(d.id, "checklist", "위험 체크리스트 PDF")}</div>`
      + `<p class="hint">허가서와 답변만으로 croScan이 채우고 작업반장이 항목마다 확인한 목록입니다(작업반장 응답). 「해당 없음」은 반장의 답이며, 다른 작업과의 겹침을 본 결과가 아닙니다.</p>`
      + groups.map(([s, l]) => {
        const its = x.checklist_items.filter((i) => i.state === s);
        return its.length ? `<h3>${l} <span class="hint">${its.length}</span></h3><ul class="sf-ck">` + its.map((i) =>
          `<li><b>${esc(i.title)}</b><span class="hint">${esc(i.why || "")}</span>${i.controls.length ? `<ul>${i.controls.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}${i.memo ? `<p class="sf-memo">메모: ${esc(i.memo)}</p>` : ""}</li>`).join("") + "</ul>" : "";
      }).join("");
  }
  $("#sf-p-body").innerHTML = h;
  $("#sf-p-body").scrollTop = 0;
}
function sfClose() {
  $("#sf-panel").hidden = true;
  const pm = $("#sf-panel").dataset.mode;
  if (pm === "coord" || pm === "sheet") {                // back to the row the window was opened from
    const sel = pm === "coord" ? `[data-coord="${CSS.escape(sf.coordKey || "")}"]` : `[data-sheet="${CSS.escape(sf.sheetDoc || "")}"]`;
    $("#sf-panel").dataset.mode = ""; sf.req++;
    const r = document.querySelector(sel); (r && r.offsetParent ? r : $("#sf-post-back")).focus(); return;
  }
  if ($("#sf-panel").dataset.mode === "near") {
    $("#sf-panel").dataset.mode = ""; const r = document.querySelector(`[data-near="${CSS.escape(sf.nearKey || "")}"]`);
    if (r && r.offsetParent) r.focus(); return;
  }
  if (sf.openPair) {                         // back to the pair's row; the map keeps the pair until another pick
    const pid = sf.openPair; sf.openPair = null;
    history.replaceState(null, "", "#safety"); sfSaveView();
    const r = document.querySelector(`#sf-plist [data-pair="${pid}"]`);
    (r && r.offsetParent ? r : $("#sf-detect")).focus();
    return;
  }
  const id = sf.open; sf.open = null; sf.req++;
  history.replaceState(null, "", "#safety");
  sfSaveView();
  // back to where it was opened from, if that is on screen: its row, its bar, its 일정 line, else the search box
  const vis = (e) => e && e.offsetParent !== null;
  const c = [...(sfDocSplit() ? [`#sf-doc-sum [data-open="${CSS.escape(id || "")}"]`] : []), `#sf-rows [data-open="${CSS.escape(id || "")}"]`, `#sf-grid [data-pick="${CSS.escape(id || "")}"]`, `#sf-day [data-pick="${CSS.escape(id || "")}"]`, `#sf-sched-list [data-open="${CSS.escape(id || "")}"]`]
    .map((s) => document.querySelector(s)).find(vis);
  (c || $("#sf-q")).focus();
}
function sfStep(n) {
  const list = sfVisible(), i = list.findIndex((x) => x.id === sf.open), to = i < 0 ? list[0] : list[i + n];
  if (to) sfOpen(to.id);
}
$("#sf-p-close").onclick = sfClose;
$("#sf-p-prev").onclick = () => sf.openPair ? sfPairStep(-1) : sfStep(-1);
$("#sf-p-next").onclick = () => sf.openPair ? sfPairStep(1) : sfStep(1);
$("#sf-p-tabs").onclick = (e) => {
  const b = e.target.closest("[data-part]"), d = sf.open && sfDoc(sf.open); if (!b || !d) return;
  sf.part = +b.dataset.part; sfSaveView();
  sfPanelChrome(d); if (sf.loaded === d.id && sfCache[d.id]) sfPanelBody(d, sfCache[d.id]);
};
$("#sf-p-go").onclick = () => {
  const d = sf.open && sfDoc(sf.open); if (!d || sf.loaded !== d.id) return;     // nothing is marked unseen
  const [k, l] = SF_PARTS[d.type][sf.part], tg = sfNextTarget(d);
  if (!sfMarks(d)[k]) { sfMark(d, k, true); sf.last = { id: d.id, k }; toast(`${sfNo(d)} ${l} 확인`); }
  if (!tg) { sfRefresh(); toast(`이 목록의 ${sfVisible().length}건을 모두 확인했습니다`); sfClose(); return; }
  if (tg.part != null) { sf.part = tg.part; sfRefresh(); sfPanelBody(d, sfCache[d.id]); }
  else { sfRefresh(); sfOpen(tg.id); }
};
$("#sf-p-undo").onclick = () => {
  const d = sf.open && sfDoc(sf.open); if (!d) return;
  const [k] = SF_PARTS[d.type][sf.part];
  if (sfMarks(d)[k]) sfMark(d, k, false);
  else if (sf.last && sfDoc(sf.last.id)) { sfMark(sfDoc(sf.last.id), sf.last.k, false); sf.last = null; }
  sfRefresh();
};
window.addEventListener("storage", (e) => { if (e.key === SF_KEY && sf.data) { sfLoadSeen(); sfRefresh(); } });
document.addEventListener("keydown", (e) => {
  if ($("#s-safety").hidden || document.querySelector(".sheet-modal:not([hidden])")) return;
  const P = $("#sf-panel");
  if (e.key === "Escape") {
    if (!P.hidden) sfClose();
    else if (!$("#sf-filter").hidden) { sfFilterShow(false); $("#sf-fbtn").focus(); }
    return;
  }
  // a full-screen panel keeps Tab inside it
  if (e.key === "Tab" && !P.hidden && P.offsetWidth >= window.innerWidth - 2) {
    const f = [...P.querySelectorAll("button:not([disabled]):not([hidden]), a[href], summary")].filter((x) => x.offsetParent !== null);
    if (f.length && e.shiftKey && (document.activeElement === f[0] || document.activeElement === P)) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (f.length && !e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  }
  // '/' goes to the search box (not while typing somewhere)
  if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && P.hidden) {
    e.preventDefault(); $("#sf-q").focus();
  }
});
// controls ---------------------------------------------------------------
function sfFilterShow(on) {
  $("#sf-filter").hidden = !on; $("#sf-fbtn").setAttribute("aria-expanded", String(on));
  if (on) sfFilterPanel();
}
$("#sf-fbtn").onclick = () => sfFilterShow($("#sf-filter").hidden);
$("#sf-tabs").onclick = (e) => { const b = e.target.closest("[data-tab]"); if (!b) return; sf.tab = b.dataset.tab; sfRefresh(); };
$("#sf-sort").onchange = (e) => { sf.sort = e.target.value; sfRefresh(); };
$("#sf-q").oninput = (e) => { sf.q = e.target.value.trim(); sfRefresh(); };
$("#sf-t").oninput = (e) => sfSetTime(+e.target.value);
// 24-hour times everywhere ("13:40", also typed as "1340"); anything else puts the time back
$("#sf-clock").onchange = (e) => {
  const m = e.target.value.trim().match(/^(\d{1,2}):?(\d{2})$/);
  if (m && +m[1] < 24 && +m[2] < 60) sfSetTime(+m[1] * 60 + +m[2]); else e.target.value = m2hm(sf.t);
};
$("#sf-clock").onkeydown = (e) => { if (e.key === "Enter") e.target.blur(); };
// ‹ › go to the previous / next quarter hour (from 15:40: 15:30 and 15:45)
$("#sf-t-prev").onclick = () => sfSetTime(Math.ceil(sf.t / 15) * 15 - 15);
$("#sf-t-next").onclick = () => sfSetTime(Math.floor(sf.t / 15) * 15 + 15);
// the busy-hours strip and the 하루 일정 tracks: a click there picks that time
$("#s-safety").addEventListener("submit", (e) => {
  const f = e.target.closest(".sf-why-ask"); if (!f) return;
  e.preventDefault();
  const q = f.querySelector("input").value.trim();
  if (q) sfWhyAsk(f.closest(".sf-why"), { question: q });
});
$("#sf-profile").onclick = (e) => { const r = $("#sf-profile").getBoundingClientRect(); sfSetTime(Math.round((T0 + ((e.clientX - r.left) / r.width) * (T1 - T0)) / 5) * 5); };
$("#s-safety").addEventListener("click", (e) => {
  if (e.target.closest("[data-unfilter]")) { sfClear(); sfRefresh(); return; }
  const wq = e.target.closest("[data-why]"); if (wq) { sfWhyAsk(wq.closest(".sf-why"), { which: wq.dataset.why }); return; }
  const rv = e.target.closest("[data-rvgo]"); if (rv) { sfReview(rv.closest(".sf-ai-review")); return; }
  const hq = e.target.closest("[data-hqgo]"); if (hq) { sfHoldLoad(hq.closest(".sf-hq")); return; }
  const hm = e.target.closest("[data-hqmark]"); if (hm) { sfHoldMark(hm); return; }
  const hc = e.target.closest("[data-hqcopy]");
  if (hc) {                                                     // copied here only: sending is the yard's own contact
    const ta = hc.previousElementSibling;
    (navigator.clipboard ? navigator.clipboard.writeText(ta.value) : Promise.reject(new Error("no clipboard")))
      .then(() => toast("문안을 복사했습니다. 보내기는 기존 연락 방법으로 해 주세요"))
      .catch(() => { ta.focus(); ta.select(); toast("문안을 선택했습니다. 복사해 보내 주세요"); });
    return;
  }
  const pp = e.target.closest("[data-pair]"); if (pp) { sfOpenPair(pp.dataset.pair); return; }
  const nr = e.target.closest("[data-near]"); if (nr) { sfOpenNear(nr.dataset.near); return; }
  if (e.target.closest("[data-emap]")) { sfEvidence(); return; }
  if (e.target.closest("[data-aiclose]")) {                     // back to the rule list as it was (tab, pick, scroll)
    const pv = sf.aiPrev || { ptab: "all", scroll: 0, pair: null }; sf.aiPrev = null; sf.ptab = pv.ptab; sf.nearKey = null; sfMain("pairs");
    if (pv.pair && sf.det.pairs.some((x) => x.id === pv.pair)) sfOpenPair(pv.pair, true);
    requestAnimationFrame(() => { $("#sf-plist").scrollTop = pv.scroll || 0; sfMoreHint(); }); return;
  }
  const ain = e.target.closest('[data-ptab="ai"]');
  if (ain && sf.ptab !== "ai") { sf.aiPrev = { ptab: sf.ptab, scroll: $("#sf-plist").scrollTop, pair: sf.openPair }; sfRvLoad(); }
  const pt = e.target.closest("[data-ptab]"); if (pt) { sf.ptab = sf.ptab === pt.dataset.ptab && pt.closest("#sf-res-pri, #sfn-list") ? "all" : pt.dataset.ptab; sfMain("pairs"); $("#sf-plist").scrollTop = 0; requestAnimationFrame(sfMoreHint); return; }
  if (e.target.closest("[data-postgo]")) { const k = (sf.det.pairs.find((x) => x.id === sf.openPair) || {}).key; $("#sf-panel").hidden = true; sf.pstep = "coord"; $("#sf-post-btn").click(); if (k) postCoordOpen(k); return; }
  if (e.target.closest("[data-tomap]")) { sfPairToMap(); return; }
  const pk = e.target.closest("[data-pkind]"); if (pk) { sf.pkind = pk.dataset.pkind; sfPairsView(); return; }
  const o = e.target.closest("[data-open]");
  if (o && sfDocSplit() && o.closest("#sf-rows")) { sf.docPick = o.dataset.open; sfDocSummary(); return; }
  if (o) { sfOpen(o.dataset.open); return; }
  const pm = e.target.closest("[data-pickmap]"); if (pm) { sf.pairOnMap = false; sfMain("map"); sfSelect(pm.dataset.pickmap, true); return; }
  const p = e.target.closest("[data-pick]"); if (p) { sfSelect(p.dataset.pick, false); return; }
  const t = e.target.closest("[data-tile]");
  if (t) {
    const [k, v] = t.dataset.tile.split(":"), was = t.getAttribute("aria-pressed") === "true";
    sfClear();
    if (!was) { if (k === "tab") sf.tab = v; else sfToggle(k, v, true); }
    sfRefresh(); return;
  }
  const opt = e.target.closest(".sf-opt");
  if (opt) { sfToggle(opt.dataset.f, opt.dataset.v); sfRefresh(); const again = document.querySelector(`.sf-opt[data-f="${opt.dataset.f}"][data-v="${CSS.escape(opt.dataset.v)}"]`); if (again) again.focus(); return; }
  if (e.target.closest("#sf-fdone")) { sfFilterShow(false); $("#sf-fbtn").focus(); return; }
  const rm = e.target.closest("[data-rm]");
  if (rm) {
    if (rm.dataset.rm === "q") { sf.q = ""; $("#sf-q").value = ""; } else sfToggle(rm.dataset.rm, rm.dataset.v);
    sfRefresh(); return;
  }
  const v = e.target.closest("[data-view]"); if (v) { sf.view = v.dataset.view; sfMapView(); sfSaveView(); return; }
  const sd = e.target.closest("[data-side]"); if (sd) { sf.side = sd.dataset.side; sfSched(); sfSaveView(); return; }
  const tr = e.target.closest(".sf-day-track");
  if (tr) { const r = tr.getBoundingClientRect(); sfSetTime(Math.round((T0 + ((e.clientX - r.left) / r.width) * (T1 - T0)) / 5) * 5); }
});
$("#sf-rows").addEventListener("mouseover", (e) => {
  const tr = e.target.closest("tr[data-id]");
  document.querySelectorAll("#sf-grid .sf-bar, #sf-day .sf-bar").forEach((b) => b.classList.toggle("hover", !!tr && b.dataset.pick === tr.dataset.id));
});
$("#sf-rows").addEventListener("mouseleave", () => document.querySelectorAll(".sf-bar.hover").forEach((b) => b.classList.remove("hover")));
// the sticky table head sits right under the sticky jump bar, whatever its height (text size, wrapping)
// (the bar sticks over the screen's top padding: its top is negative, so the head goes under its bottom edge)
new ResizeObserver(() => { const j = $("#sf-jump"); $("#s-safety").style.setProperty("--sf-jump-h", j.offsetParent ? `${j.offsetHeight + parseFloat(getComputedStyle(j).top || 0)}px` : "0px"); }).observe($("#sf-jump"));
// Codex QA2 #6: 「배치도에서 확인」 shows the pair on the 계획 배치도 itself: the card over the page (narrow screens) closes,
// a 하루 일정 or a work picked before gives way, and the keyboard goes to the pair's first work on the map
function sfPairToMap() {
  const P = $("#sf-panel");
  if (!P.hidden && P.dataset.mode === "pair") { P.hidden = true; P.dataset.mode = ""; sf.openPair = null; sf.req++; history.replaceState(null, "", "#safety"); }
  sf.pairOnMap = true; sf.pick = null; sf.view = "map";
  sfMain("map"); sfJumpTo(".sf-map");
  const pr = sf.pair, first = pr && pr.reasons[0].cause;
  const bar = (first && document.querySelector(`#sf-grid [data-pick="${CSS.escape(first)}"], #sf-off [data-pick="${CSS.escape(first)}"]`))
    || document.querySelector("#sf-grid .sf-bar.pa, #sf-grid .sf-bar.pb, #sf-grid .sf-unk.pa, #sf-grid .sf-unk.pb");
  if (bar) bar.focus({ preventScroll: true });
  else { const g = $("#sf-grid"); if (!g.hasAttribute("tabindex")) g.setAttribute("tabindex", "-1"); g.focus({ preventScroll: true }); }
}
function sfJumpTo(sel) {
  const el2 = $(sel); if (!el2) return;
  const top = el2.getBoundingClientRect().top - $("#s-safety").getBoundingClientRect().top + $("#s-safety").scrollTop - (sel === ".sf-head" ? 24 : $("#sf-jump").offsetHeight + 8);
  $("#s-safety").scrollTo({ top, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
}
$("#sf-jump").onclick = (e) => { const b = e.target.closest("[data-main]"); if (b) { sf.pairOnMap = false; sfMain(b.dataset.main); } };
// a BAY of the 문서 목록 folds to its header (the count stays); a work picked elsewhere opens its BAY again
$("#sf-rows").addEventListener("click", (e) => {
  const b = e.target.closest("[data-fold]"); if (!b) return;
  const k = +b.dataset.fold; sf.fold.has(k) ? sf.fold.delete(k) : sf.fold.add(k); sfRows();
  $(`#sf-rows [data-fold="${k}"]`)?.focus();
});
$("#sf-detect").onclick = () => sfDetect(false);
$("#sfn-detect").onclick = () => { if (!$("#sf-detect").disabled) sfDetect(false); };
$("#sf-pkind").onchange = (e) => { sf.pkind = e.target.value; sfPairsView(); sfNav(); sfSaveView(); };
$("#sfn-list").addEventListener("click", (e) => {
  if (e.target.closest("[data-navtg]")) { sf.navOpen = !sf.navOpen; sfNav(); $("#sfn-list [data-navtg]").focus(); sfSaveView(); return; }
  if (e.target.closest("[data-navall]")) { sf.ptab = "all"; sfMain("pairs"); $("#sfn-list [data-navall]").focus(); return; }
  const m = e.target.closest("[data-navmain]"); if (m) { sf.pairOnMap = false; sfMain(m.dataset.navmain); $(`#sfn-list [data-navmain="${m.dataset.navmain}"]`)?.focus(); return; }
  if (e.target.closest("[data-navpost]")) { $("#sf-panel").hidden = true; $("#sf-post-btn").click(); }
});
$("#sf-mode").onclick = (e) => { const b = e.target.closest("[data-mode]"); if (b) sfMain(b.dataset.mode); };
$("#sf-resume-close").onclick = () => { $("#sf-resume").hidden = true; };

if (location.hash.startsWith("#safety")) setRole("safety"); else showLogin();     // a #safety link opens that view straight away
// a link or the address bar changing only the #part: follow it (#safety, #safety/<day>/<doc>, or back to the foreman)
window.addEventListener("hashchange", () => {
  const safety = location.hash.startsWith("#safety"), [, day, id] = location.hash.split("/");
  if (safety && document.body.dataset.role !== "safety") setRole("safety");
  else if (!safety && document.body.dataset.role === "safety") showLogin();
  if (safety && sf.data && day === sf.data.date && id && sfDoc(decodeURIComponent(id)) && sf.open !== decodeURIComponent(id)) sfOpen(decodeURIComponent(id));
});

// 사용자 시험 모드 (design §11.3·§19.10, ?usertest=1): for the facilitator — the task cards of
// croScan_사용자시험_준비물_2026-10-31.md, the time each takes, the clicks made, and what the participant misread, kept
// in this browser only and saved as a JSON file (tools/usertest_report.py adds them up). Nothing is sent.
(function usertest() {
  if (!/[?&]usertest=1(?:&|$)/.test(location.search)) return;
  const TASKS = [["R1", "허가서 올리고 첫 질문에 답하기(13~15시, 러그 6개 가스절단)"], ["R2", "카드에서 우리 작업 값과 예정 여부 말하기"],
    ["R3", "「N건 확인」을 누르면 무슨 일이 생기는지 말하기"], ["R4", "옆 팀 이야기를 섞어 답하고 카드 확인"], ["R5", "「4개가 아니라 6개」처럼 고쳐 말하기"],
    ["R6", "카드가 오기 전에 다음 질문에 답하기"], ["R7", "「왜 묻나요?」를 열어 근거 말하기"], ["R8", "AI 추가 검토 후보를 넣을지 정하기"],
    ["R9", "계획서 연결 제안에 「아님」 누르기"], ["R10", "종이에서 우리 반 할 일·개정 번호 찾기"], ["R11", "다음 날: 확인·고치기·근거 열기"],
    ["M1", "1순위 쌍의 「왜 위험한가요」 설명"], ["M2", "입력 보강 전후 셋째 칸의 뜻 말하기"], ["M3", "근접 쌍 AI 검토 요청이 순위를 바꾸는지"],
    ["M4", "판정보류 문안 복사·「전달함 표시」"], ["M5", "협의할 점 넣었다 빼기"], ["M6", "근거 지도에서 「근거 보강 필요」 수"], ["M7", "같은 쌍을 기존 화면과 찾기"]];
  const KEY = "croscan-usertest";
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } };
  let S = load() || { who: "", role: "반장", device: "", runs: [] };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* kept in memory only */ } };
  let run = null;
  const box = document.createElement("aside");
  box.setAttribute("aria-label", "사용자 시험 진행");
  box.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:9999;width:min(320px,calc(100vw - 16px));background:var(--surface);border:2px solid var(--primary);"
    + "border-radius:8px;padding:8px;font-size:1.3rem;box-shadow:0 2px 8px rgba(0,0,0,.2)";
  box.innerHTML = `<b>사용자 시험 진행</b> <small>(이 브라우저에만 기록)</small>
    <p><label>참여자 <input data-ut="who" style="width:8em"></label> <label>역할 <select data-ut="role"><option>반장</option><option>안전관리자</option></select></label></p>
    <p><label>기기·설정 <input data-ut="device" style="width:14em" placeholder="노트북 · 큰 글씨"></label></p>
    <p><select data-ut="task" style="max-width:100%">${TASKS.map(([k, t]) => `<option value="${k}">${k} ${esc(t)}</option>`).join("")}</select></p>
    <p data-ut="now" class="hint">과제 시작 전</p>
    <p><button type="button" class="btn small" data-ut="start">시작</button> <button type="button" class="btn small" data-ut="ok">성공</button>
       <button type="button" class="btn small" data-ut="fail">실패</button></p>
    <p><textarea data-ut="note" rows="2" style="width:100%" placeholder="들은 그대로(오해한 말)"></textarea><button type="button" class="btn small" data-ut="addnote">오해 기록</button></p>
    <p><button type="button" class="btn small" data-ut="export">파일로 저장</button> <button type="button" class="btn small ghost" data-ut="clear">기록 지우기</button>
       <small data-ut="count"></small></p>`;
  document.body.appendChild(box);
  const q = (k) => box.querySelector(`[data-ut="${k}"]`);
  ["who", "role", "device"].forEach((k) => { q(k).value = S[k] || q(k).value; q(k).onchange = () => { S[k] = q(k).value; save(); }; });
  const count = () => { q("count").textContent = ` 과제 ${S.runs.length}건 기록`; };
  count();
  q("start").onclick = () => {
    run = { task: q("task").value, start: Date.now(), clicks: [], notes: [], who: S.who, role: S.role, device: S.device };
    q("now").textContent = `${run.task} 진행 중`;
  };
  const end = (ok) => {
    if (!run) return;
    S.runs.push({ ...run, ok, ms: Date.now() - run.start });
    run = null; save(); count(); q("now").textContent = "과제 시작 전";
  };
  q("ok").onclick = () => end(true);
  q("fail").onclick = () => end(false);
  q("addnote").onclick = () => {
    const t = q("note").value.trim();
    if (!t) return;
    (run ? run.notes : (S.runs[S.runs.length - 1] || { notes: [] }).notes).push({ at: Date.now(), text: t });
    q("note").value = ""; save();
  };
  q("export").onclick = () => {
    const blob = new Blob([JSON.stringify(S, null, 1)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `usertest_${(S.who || "참여자").replace(/[^\w가-힣-]/g, "")}_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  q("clear").onclick = () => { if (confirm("이 브라우저의 시험 기록을 지울까요?")) { S = { who: "", role: "반장", device: "", runs: [] }; save(); count(); } };
  document.addEventListener("click", (e) => {
    if (!run || box.contains(e.target)) return;
    const t = e.target.closest("button, a, input, select, summary, [role=button]") || e.target;
    run.clicks.push({ at: Date.now() - run.start, what: (t.textContent || t.getAttribute("aria-label") || t.tagName).trim().slice(0, 30) });
  }, true);
})();
// 시연 모드 표시 (접근 통제의 자리): without the company's sign-in gateway in front, anyone who reaches the server sees
// the manager's side; the screen says so
fetch("/api/health").then((r) => r.json()).then((j) => {
  if (j.auth !== "demo") return;
  const t = document.querySelector("#sf-title");
  if (t && !document.querySelector(".demo-auth")) t.insertAdjacentHTML("afterend", `<p class="hint demo-auth">시연 모드 · 인증 없음 — 현장에서는 사내 로그인 뒤에서만 엽니다</p>`);
}).catch(() => {});

// ---------------------------------------------------------------- AI 상태 줄 (design §19.4)
// One line above the composer for the readings still running: 「답을 받았습니다」 and the server's real step; after
// 30 s [직접 입력·보기 선택][취소], after a failure [다시 시도]; a card that got readings out of sight says 「새 AI 제안
// N건 · 보기」. A late result only changes this line (nothing moves the row being read or the focus).
let aiLineTimer = 0;
function aiLine() {
  let line = document.querySelector("#ai-line");
  if (!line) {
    line = el("div", "ai-line"); line.id = "ai-line"; line.setAttribute("role", "status"); line.hidden = true;
    const comp = document.querySelector("#composer"); if (!comp) return null;
    comp.parentNode.insertBefore(line, comp);
    line.addEventListener("click", aiLineClick);
  }
  return line;
}
function aiLineClick(e) {
  const t = e.target.closest("[data-ail]"); if (!t) return;
  const k = t.dataset.ail, qid = t.dataset.qid;
  const card = qid && document.querySelector(`#msgs .ai-card[data-src="${CSS.escape(qid)}"]`);
  if (k === "see" && card) { card.scrollIntoView({ block: "center", behavior: "smooth" }); card.dataset.aiSeen = card.querySelectorAll(".ai-chip").length; }
  if (k === "direct") { const box = st.askBox; if (box) { box.scrollIntoView({ block: "center" }); const b = box.querySelector("button:not(.soft)"); if (b) b.focus(); } }
  if (k === "cancel" && card) { const s = card.querySelector("[data-rd-skip]"); if (s) s.click(); }
  if (k === "retry") { const q = (st.aug.questions || []).concat(st.answers.map((a) => a.q)).find((x) => x && x.qid === qid); if (q && card) { card.remove(); readCard(q); } }
  aiTick();
}
async function aiTick() {
  const line = aiLine(); if (!line) return;
  const sid = st.sid, now = Date.now();
  const live = [...READING.entries()].filter(([, x]) => x.gen === st.gen);
  for (const [qid] of live) {                                       // the server's real step for each reading
    try { const r = await fetch(`/api/dialogues/${encodeURIComponent(sid)}/stage?qid=${encodeURIComponent(qid)}`); if (r.ok) { const j = await r.json(); if (j.stage && j.stage !== "끝") AI_STAGE[qid] = j.stage; } } catch (e) { /* the line keeps the last step */ }
    const h = document.querySelector(`#msgs .ai-card[data-src="${CSS.escape(qid)}"] .ai-h`);
    if (h && AI_STAGE[qid]) h.lastChild.textContent = h.lastChild.textContent.replace(/(답을 받았습니다 · )[^·]+/, `$1${AI_STAGE[qid]} `);
  }
  let html = "";
  if (live.length) {
    const [qid, x] = live.sort((a, b) => (a[1].at || 0) - (b[1].at || 0))[0], waited = now - (x.at || now);
    html = `<span class="ai-chip">AI</span>답을 받았습니다 · ${esc(AI_STAGE[qid] || "대기 중")}${live.length > 1 ? ` (${live.length}건)` : ""}`;
    if (waited >= 30000) html += ` · 평소보다 오래 걸립니다 <button type="button" class="linkbtn" data-ail="direct" data-qid="${esc(qid)}">직접 입력·보기 선택</button> <button type="button" class="linkbtn" data-ail="cancel" data-qid="${esc(qid)}">취소</button>`;
  } else {
    const failed = [...document.querySelectorAll("#msgs .ai-card")].find((c) => c.querySelector(".ai-fail") && !c.dataset.aiRetried);
    if (failed) html = `<span class="ai-chip">${AI_CHIP.fail}</span> <button type="button" class="linkbtn" data-ail="retry" data-qid="${esc(failed.dataset.src)}">다시 시도</button>`;
  }
  // readings that arrived on a card out of sight
  const msgsBox = document.querySelector("#msgs"), top = msgsBox ? msgsBox.getBoundingClientRect() : null;
  for (const c of document.querySelectorAll("#msgs .ai-card")) {
    const n = c.querySelectorAll(".ai-chip").length, seen = +(c.dataset.aiSeen || 0), r = c.getBoundingClientRect();
    const away = top && (r.bottom < top.top || r.top > top.bottom);
    if (n > seen && away && c.querySelector("[data-rd-ok]")) { html += `${html ? " · " : ""}새 AI 제안 ${n - seen}건 · <button type="button" class="linkbtn" data-ail="see" data-qid="${esc(c.dataset.src)}">보기</button>`; break; }
    if (!away) c.dataset.aiSeen = n;
  }
  line.innerHTML = html; line.hidden = !html;
  clearTimeout(aiLineTimer);
  if (html || READING.size) aiLineTimer = setTimeout(aiTick, 1500);
}
