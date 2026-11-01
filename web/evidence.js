// 근거 지도 (design §3.4.1): read-only; nothing here is used by any judgement
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let M = null;
const cand = (xs) => xs && xs.length ? xs.map((x) => `<div class="cand">${esc(x.ref)}<small>${esc(x.text.slice(0, 90))}…</small></div>`).join("") : "";
function law(c) {
  if (!c) return `${blank("")}<span class="empty">근거 보강 필요</span>`;
  return c.links.map((x) => `<details><summary>${esc(x.ref)}${x.in_corpus ? "" : " (원문 미수집)"}</summary><small>${esc(x.text)}</small></details>`).join("")
    + `<small class="fit-${esc(c.fit || "none")}">${c.fit ? `규칙 적합성 검수: ${esc(c.fit)}` : "규칙 적합성 검수 기록 없음"}${c.checked ? ` · ${esc(c.checked)} 현행본 대조` : ""}`
    + `${c.confirmed ? " · 확인된 근거" : " · 인용만(확인된 근거 아님)"}</small>`
    + (c.articles ? `<ul class="arts">${c.articles.map((a) => `<li class="fit-${esc(a.fit)}">${esc(a.ref)} · ${esc(a.fit)}<small>${esc(a.note || "")}</small></li>`).join("")}</ul>` : "");
}
// a research reference: linked to the team's words only when written there; otherwise 미연결 (not cited), with the
// passage that comes closest as a candidate (검수 전)
function research(t) {
  if (!t.research) return "";
  const L = t.research_link || {};
  if (L.status === "연결") return `<div class="cand">연구 ref ${esc(t.research)} · ${esc(L.ref)}<small>「${esc(L.quote)}」`
    + `${L.rest ? ` · ${esc(L.rest.join("·"))}은 조사본 코드가 아니어서 미연결` : ""}</small></div>`;
  return `<div class="cand none">연구 ref ${esc(t.research)} · 원문 미연결<small>${esc(L.why || "원문에 같은 ref 없음")}${L.candidate ? ` · 가까운 구절(검수 전): ${esc(L.candidate.ref)}` : ""}</small></div>`;
}
const blank = (t) => `<span class="hatch" title="연결 없음 — 근거가 없다는 뜻이 아님">—</span>${t ? `<small>${esc(t)}</small>` : ""}`;
function draw() {
  const q = $("#q").value.trim(), only = $("#only").value;
  const rows = M.rows.filter((r) => (!only || (only === "empty" ? !r["법령"] : only === "rule" ? r.kind === "쌍 규칙" : r.kind !== "쌍 규칙"))
    && (!q || (r.title + r.why + r.id).includes(q)));
  $("#rows").innerHTML = rows.map((r) => `<tr><td class="t"><b>${esc(r.title)}</b><small>${esc(r.kind)} · ${esc(r.id)}</small></td>`
    + `<td class="${r["법령"] ? "" : "nil"}">${law(r["법령"])}</td><td class="${r["공공"].length ? "" : "nil"}">${cand(r["공공"]) || blank("근거 보강 필요")}</td>`
    + `<td class="${r["조선사"].length ? "" : "nil"}">${cand(r["조선사"]) || blank("")}</td>`
    + `<td>${research(r["팀"])}${cand(r["팀"].candidates) || "<small>후보 없음</small>"}</td>`
    + `<td>${r["예시"].length ? r["예시"].map((x) => `<div class="cand">${esc(x.ref)}<small>${esc(x.why || "가상 자료")}</small></div>`).join("") : "<small>없음</small>"}</td></tr>`).join("") || `<tr><td colspan="6">조건에 맞는 항목이 없습니다.</td></tr>`;
}
fetch("/api/knowledge/map").then((r) => r.json()).then((m) => {
  M = m; const f = m.flow;
  $("#flow").innerHTML = [["수집 출처", f.sources], ["청크", f.chunks], ["법령 청크", f.by_authority["법령"] || 0], ["팀 청크", f.by_authority["팀"] || 0],
    ["조선사 청크", f.by_authority["조선사"] || 0], ["가상 표시", f.synthetic], ["항목", f.rows], ["조문 인용 있음", f.with_law],
    ["원문 수집됨", f.law_collected], ["규칙 적합성 검수됨(맞음)", f.law_fit_ok], ["확인된 조문(검수 맞음·원문 수집)", f.law_confirmed], ["검수됨(약함)", f.law_weak], ["인용 있음·검수 기록 없음", f.law_unchecked], ["근거 보강 필요(인용 없음)", f.empty],
    ["공공 청크", f.by_authority["공공"] || 0], ["연구 ref", f.research], ["연구 ref 원문 연결", f.research_linked]]
    .map(([a, n]) => `<li>${esc(a)}<b>${n}</b></li>`).join("");
  $("#src").innerHTML = m.sources.map((s) => `<li><span class="g">${esc(s.authority)}</span>${esc(s.title)} · ${esc(s.revision)} · 수집 ${esc(s.fetched)} · 해시 ${esc(s.hash)}${s.url ? ` · <a href="${esc(s.url)}" rel="noopener">원문</a>` : ""}</li>`).join("");
  draw();
}).catch(() => { $("#rows").innerHTML = `<tr><td colspan="6">근거 지도를 불러오지 못했습니다.</td></tr>`; });
$("#q").oninput = () => M && draw();
$("#only").onchange = () => M && draw();
