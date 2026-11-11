// croScan safety-manager flow on staging for the final 19-clip set: V12–V19 (captions 30–51). Shots for PRAI + a log of every
// real input and app answer. Based on work/safety.mjs. Only data-cap attributes are added to the page (never the app's ids).
import fs from "node:fs";
import path from "node:path";

const BASE = "http://localhost:8776/";
const QUESTION = "왜 1순위인가요?";
const NEAR_PREF = ["0738|WP-1029-22", "0735|WP-1029-15", "0736|WP-1029-33", "0740|WP-1029-12", "0737|WP-1029-26"];
const EXAMPLE_PAIR = "0735|WP-1029-08";          // P22: a pair whose foreman answer was confirmed (P02 has none, see probe)

// 21-clip conti (2026-11-02 15h): phase "1" = V12–V14 + V14B (manager asks 0735), then the foreman resubmits 0735 (foreman0735.mjs),
// phase "2" = V14B (manager sees the resubmission used) + V15–V19. Each phase is its own browser, so phase 2 confirms the 0731 documents itself.
const HQ_PAIR = "0732|0735", HQ_LABEL = "0732 × 0735", HQ_DOC = "AC00-IH-20261029-0735";
export async function safety21({ page, shot }, outDir, phase) {
  const logFile = path.join(outDir, `log_S21_${phase}.json`), log = { phase, events: [] };
  const ev = (k, v) => { log.events.push({ k, v, at: new Date().toISOString() }); fs.writeFileSync(logFile, JSON.stringify(log, null, 1)); console.log(`  [S] ${k}:`, typeof v === "string" ? v.slice(0, 200) : JSON.stringify(v).slice(0, 200)); };
  const sleep = (ms) => page.waitForTimeout(ms);
  const tag = (js, id) => page.evaluate(`(() => { document.querySelectorAll('[data-cap=${JSON.stringify(id)}]').forEach(x => x.removeAttribute('data-cap')); const e = (${js}); if (e) e.setAttribute('data-cap', ${JSON.stringify(id)}); return !!e; })()`);
  const area = `(a, b) => a.offsetWidth * a.offsetHeight - b.offsetWidth * b.offsetHeight`;
  // smallest visible element inside scope whose text starts with `label` and contains `val`, wide enough to be a row
  const row = (scope, label, val = "", minW = 400) => `[...document.querySelectorAll(${JSON.stringify(scope + " *")})].filter(e => e.offsetParent && e.offsetWidth > ${minW} && e.offsetHeight < 120 && (e.innerText || '').trim().startsWith(${JSON.stringify(label)}) && (e.innerText || '').includes(${JSON.stringify(val)})).sort(${area})[0]`;
  const txt = (sel) => page.innerText(sel).catch(() => "");
  const waitGone = (sel, re, ms) => page.waitForFunction(`(() => { const o = document.querySelector(${JSON.stringify(sel)}); return o && !${re}.test(o.innerText) && o.innerText.trim().length > 0; })()`, null, { timeout: ms }).then(() => true, () => false);
  const api = (u, body) => page.evaluate(`fetch(${JSON.stringify(u)}, ${body ? `{ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: ${JSON.stringify(JSON.stringify(body))} }` : "{}"}).then(r => r.json()).catch(e => ({ error: String(e) }))`);
  page.setDefaultTimeout(120000);
  page.on("dialog", (d) => { ev("js_dialog", d.message()); d.accept(); });
  const pickPair = async (tab, label) => {
    await page.locator(`#sfn-list [data-ptab="${tab}"]`).first().click(); await sleep(1800);
    await tag(`[...document.querySelectorAll('#sf-plist .sf-prow')].find(r => r.innerText.replace(/\\s+/g, ' ').includes(${JSON.stringify(label)}))`, "cap-pair");
    await page.click("[data-cap=cap-pair]"); await sleep(4000);
  };

  const login = async (name) => {
    await page.goto(BASE); await page.waitForSelector("#s-login:not([hidden])");
    await page.click('[data-login="safety"]'); await sleep(600);
    if (name) await shot(name, { roles: "#login-roles", go: ".login-go", safety: '[data-login="safety"]' });
    await page.click(".login-go"); await page.waitForSelector("#s-safety:not([hidden])"); await sleep(4500);
    if (await page.isVisible("#sf-resume-close")) await page.click("#sf-resume-close");
  };
  const subs = async (k) => { const s = await api("/api/safety/submissions"); ev(k, { "0731": s["AC00-IH-20261029-0731"] || null, "0735": s[HQ_DOC] || null }); return s; };
  const hybrid = async (k) => { const d = await api("/api/safety/detect", {}); ev(k, { versions: d.hybrid?.versions, p21: d.pairs?.find((p) => p.key === HQ_PAIR), p02: d.pairs?.find((p) => p.key === "0731|WP-1029-01")?.id,
    changes_0735: ["new", "kept", "gone"].map((c) => [c, (d.hybrid?.changes?.[c] || []).filter((x) => x.cause === "0735" || x.exposed === "0735")]) }); return d; };
  const verTags = async (pre) => {
    await tag(`document.querySelector('#sf-pdetail .sf-ver')`, `cap-${pre}ver`);
    await tag(`[...document.querySelectorAll('#sf-pdetail details.sf-pc-d')].find(d => /입력 보강 전후/.test(d.querySelector('summary')?.innerText || ''))`, `cap-${pre}hy`);
  };
  const openHy = async (pre) => {
    const ok = await page.evaluate(`(() => { const d = document.querySelector('[data-cap=cap-${pre}hy]'); if (!d) return false; d.open = true; d.scrollIntoView({ block: 'start' }); return true; })()`); await sleep(1200);
    return ok;
  };

  if (phase === "1") {
  // ---------- V12 ----------
  await login("V12_login");
  ev("nav", await txt("#sf-nav"));
  await subs("submissions_api_start");
  await page.click('#sfn-list [data-navmain="docs"]'); await sleep(3500);
  await tag(`[...document.querySelectorAll('#sf-rows tr')].find(r => /0731/.test(r.innerText))`, "cap-0731");
  await page.click("[data-cap=cap-0731]"); await sleep(3500);
  await tag(`[...document.querySelectorAll('#sf-nav *')].filter(e => e.offsetParent && /비일상 작업/.test(e.innerText) && /총 작업/.test(e.innerText)).sort(${area})[0]`, "cap-counts");
  // the same 0731: what the foreman confirmed (place · time) and how many extra answers came with the submission
  const sumRow = (label) => `[...document.querySelectorAll('#sf-doc-sum *')].filter(e => e.offsetParent && e.offsetWidth > 120 && e.offsetHeight < 90 && (e.innerText || '').trim().startsWith(${JSON.stringify(label)})).sort(${area})[0]`;
  await tag(sumRow("장소"), "cap-sloc"); await tag(sumRow("시간"), "cap-stime"); await tag(sumRow("추가 답변"), "cap-sans");
  ev("docs_row_0731", await txt("[data-cap=cap-0731]"));
  ev("doc_sum_0731", await txt("#sf-doc-sum"));
  await shot("V12_docs", { nav: "#sf-nav", counts: "[data-cap=cap-counts]", row: "[data-cap=cap-0731]", sum: "#sf-doc-sum", table: "#sf-table-wrap",
    sloc: "[data-cap=cap-sloc]", stime: "[data-cap=cap-stime]", sans: "[data-cap=cap-sans]", locTime: ["[data-cap=cap-sloc]", "[data-cap=cap-stime]"] });

  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  if (!(await page.isVisible("#sf-res"))) await page.click((await page.isVisible("#sfn-detect")) ? "#sfn-detect" : "#sf-detect");
  await page.waitForSelector("#sf-res:not([hidden])"); await sleep(3500);
  ev("res", await txt("#sf-res"));
  await shot("V12_home", { res: "#sf-res", donut: "#sf-res svg", pri: "#sf-res-pri", list: "#sf-plist", nav: "#sf-nav", p1tab: '#sfn-list [data-ptab="1"]' });
  await page.locator('#sfn-list [data-ptab="1"]').first().click(); await sleep(2500);
  ev("p1_rows", await page.evaluate(`[...document.querySelectorAll('#sf-plist .sf-prow')].map(r => r.innerText.replace(/\\s+/g, ' '))`));
  await tag(`[...document.querySelectorAll('#sf-plist .sf-prow')].find(r => r.innerText.replace(/\\s+/g, ' ').includes('0731 × WP-01'))`, "cap-pair");
  await shot("V12_p1", { list: "#sf-plist", tab: '#sfn-list [data-ptab="1"]', pri1: "#sf-res-pri", pair: "[data-cap=cap-pair]" });
  await page.click("[data-cap=cap-pair]"); await sleep(5000);
  await tag(`[...document.querySelectorAll('#sf-plist .sf-prow')].find(r => r.innerText.replace(/\\s+/g, ' ').includes('0731 × WP-01'))`, "cap-pair");
  await tag(`[...document.querySelectorAll('#sf-pdetail .sf-pc-tl *')].filter(e => e.offsetParent && /13:30.15:00/.test(e.innerText) && /90분/.test(e.innerText)).sort(${area})[0]`, "cap-ovl");
  ev("pair_detail", await txt("#sf-pdetail"));
  await verTags("p02");
  ev("pair_ver_line", await txt("[data-cap=cap-p02ver]"));
  await shot("V12_pair", { row: "[data-cap=cap-pair]", detail: "#sf-pdetail", head: "#sf-pdetail .sf-pc-head", where: "#sf-pdetail .sf-pc-where", tl: "#sf-pdetail .sf-pc-tl",
    ovl: "[data-cap=cap-ovl]", why: "#sf-pdetail .sf-pc-why", flow: "#sf-pdetail .sf-pc-flow", acc: "#sf-pdetail .sf-pc-acc", ver: "[data-cap=cap-p02ver]", tlver: ["#sf-pdetail .sf-pc-tl", "[data-cap=cap-p02ver]"] });
  // the foreman's confirmed answers in the rules' input: before → after for this pair (the 90 minutes are on the documents too)
  if (await openHy("p02")) {
    ev("pair_hybrid_p02", await txt("[data-cap=cap-p02hy]"));
    await tag(`[...document.querySelectorAll('[data-cap=cap-p02hy] .sf-hy li')].find(l => /화기 불티/.test(l.innerText))`, "cap-p02hyrow");
    await shot("V12_hy", { hy: "[data-cap=cap-p02hy]", row: "[data-cap=cap-p02hyrow]", detail: "#sf-pdetail" });
    await page.evaluate(`document.querySelector('[data-cap=cap-p02hy]').open = false`); await sleep(600);
  } else ev("pair_hybrid_p02", "(none)");
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollTop = 0`); await sleep(600);

  // ---------- V13 ----------
  await page.evaluate(`document.querySelector('#sf-pdetail details.sf-pc-d').open = true`); await sleep(1200);
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-pc-d > summary').scrollIntoView({ block: 'start' })`); await sleep(1000);
  await tag(`[...document.querySelectorAll('#sf-pdetail .sf-jd-ev li')].find(l => /0731/.test(l.innerText) && /위치/.test(l.innerText))`, "cap-ev1");
  await tag(`[...document.querySelectorAll('#sf-pdetail .sf-jd-ev li')].find(l => /WP-01/.test(l.innerText) && /위치/.test(l.innerText))`, "cap-ev2");
  ev("judgement", await txt("#sf-pdetail .sf-jd"));
  await shot("V13_jd", { sum: "#sf-pdetail .sf-pc-d > summary", jd: "#sf-pdetail .sf-jd", top: "#sf-pdetail .sf-jd-top", time: "#sf-pdetail .sf-jd-time", ev: "#sf-pdetail .sf-jd-ev",
    ev1: "[data-cap=cap-ev1]", ev2: "[data-cap=cap-ev2]", evs: ["[data-cap=cap-ev1]", "[data-cap=cap-ev2]", "#sf-pdetail .sf-jd-time"], docs: "#sf-pdetail .sf-pdocs2" });
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-jd [data-open="WP-1029-01"]').click()`); await sleep(5000);
  await tag(row("#sf-panel", "시간", "13:30"), "cap-r1"); await tag(row("#sf-panel", "장소", "3BAY"), "cap-r2");
  ev("doc_panel_WP-1029-01", (await txt("#sf-panel")).slice(0, 900));
  await shot("V13_docWP", { panel: "#sf-panel", head: "#sf-p-title", time: "[data-cap=cap-r1]", place: "[data-cap=cap-r2]", both: ["[data-cap=cap-r1]", "[data-cap=cap-r2]"] });
  await page.keyboard.press("Escape"); await sleep(1500);
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-jd [data-open="0731"]').click()`); await sleep(5000);
  await tag(row("#sf-panel", "위치 (답변 반영)"), "cap-r1"); await tag(row("#sf-panel", "작업 시간 (답변 반영)"), "cap-r2"); await tag(row("#sf-panel", "작업 장소 (허가서)"), "cap-r3");
  ev("doc_panel_0731", (await txt("#sf-panel")).slice(0, 900));
  await shot("V13_doc0731", { panel: "#sf-panel", head: "#sf-p-title", loc: "[data-cap=cap-r1]", time: "[data-cap=cap-r2]", orig: "[data-cap=cap-r3]",
    both: ["[data-cap=cap-r3]", "[data-cap=cap-r1]", "[data-cap=cap-r2]"] });
  await page.keyboard.press("Escape"); await sleep(1500);

  // ---------- V14 ----------
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-why').scrollIntoView({ block: 'start' })`); await sleep(800);
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollBy(0, -60)`); await sleep(500);
  await shot("V14_ask0", { why: "#sf-pdetail .sf-why", qs: "#sf-pdetail .sf-why-qs", input: "#sf-pdetail .sf-why-ask input", form: "#sf-pdetail .sf-why-ask" });
  await page.click("#sf-pdetail .sf-why-ask input");
  await page.locator("#sf-pdetail .sf-why-ask input").pressSequentially(QUESTION, { delay: 120 });
  ev("free_question_typed", await page.inputValue("#sf-pdetail .sf-why-ask input"));
  await shot("V14_typed", { input: "#sf-pdetail .sf-why-ask input", form: "#sf-pdetail .sf-why-ask", ask: "#sf-pdetail .sf-why-ask button[type=submit]" });
  const explainResp = page.waitForResponse((r) => r.url().includes("/api/safety/explain"), { timeout: 120000 }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  const t0 = Date.now();
  await page.click("#sf-pdetail .sf-why-ask button[type=submit]"); await sleep(1500);
  ev("explain_wait_text", await txt("#sf-pdetail .sf-why-out"));
  await shot("V14_wait", { out: "#sf-pdetail .sf-why-out", form: "#sf-pdetail .sf-why-ask" });
  const okWhy = await waitGone("#sf-pdetail .sf-why-out", "/고르는 중|정리하는 중/", 120000);
  ev("explain_seconds", { secs: (Date.now() - t0) / 1000, finished: okWhy });
  ev("explain_api", await explainResp);
  ev("explain_screen", await txt("#sf-pdetail .sf-why-out"));
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-why-ask').scrollIntoView({ block: 'start' })`); await sleep(800);
  await tag(`[...document.querySelectorAll('#sf-pdetail .sf-why-out h6')].find(h => /사용한 사실/.test(h.innerText))?.nextElementSibling`, "cap-facts");
  await tag(`[...document.querySelectorAll('#sf-pdetail .sf-why-out h6')].find(h => /적용한 규칙/.test(h.innerText))?.nextElementSibling`, "cap-rules");
  await shot("V14_done", { out: "#sf-pdetail .sf-why-out", q: "#sf-pdetail .sf-why-q", judge: "#sf-pdetail .sf-why-judge", chip: "#sf-pdetail .sf-why-judge .ai-chip",
    facts: "[data-cap=cap-facts]", rules: "[data-cap=cap-rules]", left: "#sf-pdetail .sf-why-left", form: "#sf-pdetail .sf-why-ask" });

  // ---------- V14B (1): a pair with a real open question → 담당별 확인 → copy one question ----------
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: BASE.replace(/\/$/, "") }).catch((e) => ev("clip_perm_error", String(e)));
  await hybrid("detect_before_resubmit");
  ev("hold_questions_0735_before", (await api("/api/safety/hold-questions")).docs?.find((d) => d.doc === "0735") || null);
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  const p21 = (await api("/api/safety/detect", {})).pairs?.find((p) => p.key === HQ_PAIR);
  await pickPair(String((p21 && p21.priority) || 3), HQ_LABEL);
  ev("hq_pair_detail_before", await txt("#sf-pdetail"));
  await verTags("p21");
  ev("hq_pair_ver_before", await txt("[data-cap=cap-p21ver]"));
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollTop = 0`); await sleep(500);
  await shot("V14B_pair", { row: "[data-cap=cap-pair]", detail: "#sf-pdetail", head: "#sf-pdetail .sf-pc-head", ver: "[data-cap=cap-p21ver]", ask: "#sf-pdetail .sf-pc-ask" });
  const HQ = `#sf-pdetail .sf-hq-inline[data-hqpair="${HQ_PAIR}"]`;
  await page.waitForFunction(`!!document.querySelector(${JSON.stringify(HQ + " .sf-hq-doc")}) || /물을 것이 없|만들지 못했/.test(document.querySelector(${JSON.stringify(HQ)})?.innerText || '')`, null, { timeout: 60000 }).catch(() => {});
  await sleep(800);
  await tag(`[...document.querySelectorAll(${JSON.stringify(HQ + " .sf-hq-doc")})].find(d => d.querySelector('.sf-hq-who b')?.innerText.trim() === ${JSON.stringify(HQ_DOC)})`, "cap-hqdoc");
  await tag(`document.querySelector('[data-cap=cap-hqdoc] .sf-hq-ask')`, "cap-hqask");
  await tag(`document.querySelector('[data-cap=cap-hqdoc] [data-hqq]')`, "cap-hqcopy");
  await page.evaluate(`document.querySelector(${JSON.stringify(HQ)})?.scrollIntoView({ block: 'start' })`); await sleep(400);
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollBy(0, -40)`); await sleep(600);
  ev("hq_box", await txt(HQ));
  ev("hq_card_0735", await txt("[data-cap=cap-hqdoc]"));
  await shot("V14B_hq", { box: HQ, head: `${HQ} .sf-hq-h`, doc: "[data-cap=cap-hqdoc]", who: "[data-cap=cap-hqdoc] .sf-hq-who", ask: "[data-cap=cap-hqask]", copy: "[data-cap=cap-hqcopy]",
    foot: `${HQ} .sf-hq-foot` });
  await page.click("[data-cap=cap-hqcopy]").catch((e) => ev("hq_copy_click_error", String(e))); await sleep(500);
  ev("hq_copy_button", await txt("[data-cap=cap-hqcopy]"));
  ev("hq_clipboard", await page.evaluate("navigator.clipboard.readText().catch(e => 'read error: ' + e)"));
  await shot("V14B_copied", { box: HQ, doc: "[data-cap=cap-hqdoc]", ask: "[data-cap=cap-hqask]", copy: "[data-cap=cap-hqcopy]", foot: `${HQ} .sf-hq-foot` });
  await subs("submissions_api_phase1_end");
  ev("done", true);
  return;
  }

  // ================= phase 2 =================
  await login(null);
  await subs("submissions_api_phase2_start");
  // off screen (as before): confirm the 0731 documents in this browser so that the sheet can be issued in V19
  await page.click('#sfn-list [data-navmain="docs"]'); await sleep(3500);
  await tag(`[...document.querySelectorAll('#sf-rows tr')].find(r => /0731/.test(r.innerText))`, "cap-0731");
  await page.click("[data-cap=cap-0731]"); await sleep(3500);
  await page.locator("#sf-doc-sum button:has-text('문서 열기')").first().click().catch(() => {}); await sleep(4000);
  const confirmed = [];
  for (let i = 0; i < 3; i++) {
    const bt = page.locator("button:has-text('확인하고')").first();
    if (!(await bt.count())) break;
    confirmed.push((await bt.innerText()).trim()); await bt.click(); await sleep(2500);
  }
  ev("docs_confirmed_before_issue_offscreen", confirmed);
  await page.keyboard.press("Escape"); await sleep(1000);
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  if (!(await page.isVisible("#sf-res"))) await page.click((await page.isVisible("#sfn-detect")) ? "#sfn-detect" : "#sf-detect").catch(() => {});
  await sleep(3000);
  // ---------- V14B (2): the same pair after the foreman's resubmission ----------
  const d2 = await hybrid("detect_after_resubmit");
  ev("hold_questions_0735_after", (await api("/api/safety/hold-questions")).docs?.find((d) => d.doc === "0735") || null);
  const p21b = d2.pairs?.find((p) => p.key === HQ_PAIR);
  await pickPair(String((p21b && p21b.priority) || 3), HQ_LABEL);
  ev("hq_pair_detail_after", await txt("#sf-pdetail"));
  await verTags("p21");
  ev("hq_pair_ver_after", await txt("[data-cap=cap-p21ver]"));
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollTop = 0`); await sleep(500);
  await shot("V14B_after", { row: "[data-cap=cap-pair]", detail: "#sf-pdetail", head: "#sf-pdetail .sf-pc-head", ver: "[data-cap=cap-p21ver]", where: "#sf-pdetail .sf-pc-where", tl: "#sf-pdetail .sf-pc-tl",
    tlver: ["#sf-pdetail .sf-pc-tl", "[data-cap=cap-p21ver]"] });
  if (await openHy("p21")) {
    ev("hq_pair_hybrid_after", await txt("[data-cap=cap-p21hy]"));
    await tag(`[...document.querySelectorAll('[data-cap=cap-p21hy] .sf-hy li')].find(l => /0735/.test(l.innerText))`, "cap-p21hyrow");
    await tag(`[...document.querySelectorAll('[data-cap=cap-p21hy] .sf-hy li .hint')].find(l => /0735/.test(l.innerText))`, "cap-p21hysrc");
    await shot("V14B_hy", { hy: "[data-cap=cap-p21hy]", row: "[data-cap=cap-p21hyrow]", src: "[data-cap=cap-p21hysrc]", detail: "#sf-pdetail" });
  } else ev("hq_pair_hybrid_after", "(none)");
  // back to the main case 0731 × WP-01
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  await pickPair("1", "0731 × WP-01");
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollTop = 0`); await sleep(500);
  await shot("V14B_back", { row: "[data-cap=cap-pair]", detail: "#sf-pdetail", head: "#sf-pdetail .sf-pc-head", list: "#sf-plist" });

  // ---------- V15 (a separate near pair: the optional AI review) ----------
  const rv0 = await api("/api/safety/pair-reviews");
  const notRun = Object.entries(rv0.states || {}).filter(([, s]) => s.state === "not_run").map(([k]) => k);
  const nk = NEAR_PREF.find((k) => notRun.includes(k)) || notRun[0] || NEAR_PREF[0];
  ev("pair_review_before", { count: rv0.count, not_run: notRun, chosen: nk });
  await page.locator('#sfn-list [data-ptab="near"]').first().click(); await sleep(2500);
  await tag(`document.querySelector('#sf-plist [data-near=${JSON.stringify(nk)}]')`, "cap-near");
  await page.evaluate(`document.querySelector('[data-cap=cap-near]')?.scrollIntoView({ block: 'center' })`); await sleep(600);
  await shot("V15_near", { list: "#sf-plist", tab: '#sfn-list [data-ptab="near"]', row: "[data-cap=cap-near]" });
  await page.click("[data-cap=cap-near]"); await sleep(3000);
  await tag(`document.querySelector('#sf-plist [data-near=${JSON.stringify(nk)}]')`, "cap-near");
  ev("near_detail", await txt("#sf-pdetail"));
  await page.evaluate(`document.querySelector('#sf-pdetail').scrollTop = 0`); await sleep(500);
  await shot("V15_pair", { row: "[data-cap=cap-near]", detail: "#sf-pdetail", head: "#sf-pdetail .sf-pc-head", why: "#sf-pdetail .sf-near-why", state: "#sf-pdetail .sf-ai-state",
    docs: "#sf-pdetail .sf-pdocs2", rv: "#sf-pdetail .sf-ai-review", btn: "#sf-pdetail [data-rvgo]" });
  const rvResp = page.waitForResponse((r) => r.url().includes("/api/safety/pair-review") && r.request().method() === "POST", { timeout: 150000 }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  const t1 = Date.now();
  await page.click("#sf-pdetail [data-rvgo]"); await sleep(1500);
  ev("pair_review_wait_text", await txt("#sf-pdetail .sf-rv-out"));
  await shot("V15_wait", { rv: "#sf-pdetail .sf-ai-review", out: "#sf-pdetail .sf-rv-out", btn: "#sf-pdetail [data-rvgo]" });
  const okRv = await waitGone("#sf-pdetail .sf-rv-out", "/대조하는 중/", 150000);
  ev("pair_review_seconds", { secs: (Date.now() - t1) / 1000, finished: okRv });
  ev("pair_review_api", await rvResp);
  await sleep(2500);
  ev("pair_review_screen", await txt("#sf-pdetail .sf-ai-review"));
  await page.evaluate(`document.querySelector('#sf-pdetail .sf-ai-review').scrollIntoView({ block: 'end' })`); await sleep(800);
  await shot("V15_done", { row: "[data-cap=cap-near]", rv: "#sf-pdetail .sf-ai-review", out: "#sf-pdetail .sf-rv-out", ev: "#sf-pdetail .sf-rv-ev", ask: "#sf-pdetail .sf-rv-out .sf-pc-ask",
    docs: "#sf-pdetail .sf-pdocs2", state: "#sf-pdetail .sf-ai-state" });
  ev("pair_review_after", (await api("/api/safety/pair-reviews")).count);

  // ---------- V16 ----------
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  await pickPair("1", "0731 × WP-01");
  await tag(`[...document.querySelectorAll('#sf-pdetail button, #sf-pdetail a')].find(b => /배치도에서/.test(b.innerText) && b.getBoundingClientRect().top > 0 && b.getBoundingClientRect().bottom < 1080)`, "cap-tomap");
  await shot("V16_pair", { row: "[data-cap=cap-pair]", detail: "#sf-pdetail", where: "#sf-pdetail .sf-pc-where", tomap: "[data-cap=cap-tomap]" });
  await page.click("[data-cap=cap-tomap]"); await sleep(4000);
  ev("map_time_on_open", await txt("#sf-time-h"));
  await shot("V16_map0", { grid: "#sf-grid", time: "#sf-time-h", slider: "#sf-t" });
  await page.evaluate("typeof sfSetTime === 'function' && sfSetTime(hm2m('13:30'))"); await sleep(2500);
  ev("map_time", await txt("#sf-time-h"));
  ev("map_now", await txt("#sf-now"));
  ev("map_bars", await page.evaluate(`[...document.querySelectorAll('#sf-grid .sf-bar.pa, #sf-grid .sf-bar.pb')].map(e => e.className + ' | ' + e.innerText.replace(/\\s+/g, ' '))`));
  await shot("V16_map", { grid: "#sf-grid", time: "#sf-time-h", slider: "#sf-t", now: "#sf-now", pair: ["#sf-grid .sf-bar.pa", "#sf-grid .sf-bar.pb"], pa: "#sf-grid .sf-bar.pa", pb: "#sf-grid .sf-bar.pb", legend: "#sf-legend" });

  // ---------- V17 ----------
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(2000);
  await pickPair("1", "0731 × WP-01");
  const noteResp = page.waitForResponse((r) => r.url().includes("/api/safety/coord-note"), { timeout: 120000 }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  await page.locator("#sf-pdetail button:has-text('작업 조정 문자 작성')").first().click(); await sleep(6000);
  ev("coord_note_api_P02", await noteResp);
  ev("coord_note_screen_P02", await txt("#mg-note"));
  const panelSel = `(() => { const h = [...document.querySelectorAll('h2,h3')].find(x => x.innerText.includes('일정 조율 협조')); let e = h; while (e && !(e.offsetWidth > 500 && e.offsetHeight > 700)) e = e.parentElement; return e; })()`;
  await tag(panelSel, "cap-panel");
  ev("post_panel_P02", await txt("[data-cap=cap-panel]"));
  await shot("V17_post", { panel: "[data-cap=cap-panel]", who: "[data-cap=cap-panel] .sf-who, [data-cap=cap-panel] [class*=who]" });
  await page.locator("input[placeholder='번호 입력']").nth(1).fill("010-XXXX-XXXX");
  await page.locator("input[placeholder='안전관리자 이름']").fill("이XX");
  await page.locator("input[placeholder='회신 받을 번호']").fill("010-XXXX-XXXX");
  await sleep(1200);
  await tag(`[...document.querySelectorAll('[data-cap=cap-panel] *')].find(e => e.innerText && e.innerText.startsWith('보낼 문자') && e.children.length < 4)?.parentElement`, "cap-msg");
  await shot("V17_filled", { panel: "[data-cap=cap-panel]", msg: "[data-cap=cap-msg]", who: "[data-cap=cap-panel] .sf-who, [data-cap=cap-panel] [class*=who]" });
  // the example pair whose 「협의할 점」 exists (P02 has no confirmed foreman answer)
  await page.keyboard.press("Escape"); await sleep(1500);
  await page.click('#sfn-list [data-navall]').catch(() => {}); await sleep(1500);
  const ex = (await api("/api/safety/detect", {})).pairs?.find((p) => p.key === EXAMPLE_PAIR);
  const exNo = ex ? ex.id : "P22", exLabel = EXAMPLE_PAIR.replace("|WP-1029-", " × WP-");
  ev("example_pair", { id: exNo, key: EXAMPLE_PAIR, priority: ex && ex.priority });
  await pickPair(String((ex && ex.priority) || 3), exLabel);
  const noteResp2 = page.waitForResponse((r) => r.url().includes("/api/safety/coord-note"), { timeout: 120000 }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  await page.locator("#sf-pdetail button:has-text('작업 조정 문자 작성')").first().click(); await sleep(2000);
  await waitGone("#mg-note", "/찾는 중/", 120000);
  ev("coord_note_api_example", await noteResp2);
  ev("coord_note_screen_example", await txt("#mg-note"));
  await page.locator("input[placeholder='번호 입력']").nth(1).fill("010-XXXX-XXXX").catch(() => {});
  if (await page.locator("input[placeholder='안전관리자 이름']").inputValue().catch(() => "x") === "") await page.locator("input[placeholder='안전관리자 이름']").fill("이XX");
  if (await page.locator("input[placeholder='회신 받을 번호']").inputValue().catch(() => "x") === "") await page.locator("input[placeholder='회신 받을 번호']").fill("010-XXXX-XXXX");
  await sleep(1200);
  await tag(panelSel, "cap-panel");
  await tag(`[...document.querySelectorAll('[data-cap=cap-panel] *')].find(e => e.innerText && e.innerText.startsWith('보낼 문자') && e.children.length < 4)?.parentElement`, "cap-msg");
  ev("post_panel_example_before", await txt("[data-cap=cap-panel]"));
  await page.evaluate(`document.querySelector('#mg-note')?.scrollIntoView({ block: 'center' })`); await sleep(800);
  await shot("V17_ex_note", { panel: "[data-cap=cap-panel]", msg: "[data-cap=cap-msg]", note: "#mg-note", src: "#mg-note .hint", put: "#mg-note [data-mgnote]",
    who: "[data-cap=cap-panel] .sf-who, [data-cap=cap-panel] [class*=who]" });
  await page.click("#mg-note [data-mgnote]").catch((e) => ev("mgnote_click_error", String(e))); await sleep(1800);
  await tag(`[...document.querySelectorAll('[data-cap=cap-panel] *')].filter(e => e.offsetParent && /협의할 점:/.test(e.innerText || '') && !/\\(제안\\)/.test(e.innerText || '')).sort(${area})[0]`, "cap-added");
  ev("post_panel_example_after", await txt("[data-cap=cap-panel]"));
  await page.evaluate(`document.querySelector('[data-cap=cap-added]')?.scrollIntoView({ block: 'center' })`); await sleep(800);
  await tag(`[...document.querySelectorAll('[data-cap=cap-panel] button')].find(b => b.innerText.includes('문자 복사'))`, "cap-copy");
  ev("copy_enabled", await page.isEnabled("[data-cap=cap-copy]").catch(() => false));
  await shot("V17_ex_added", { panel: "[data-cap=cap-panel]", msg: "[data-cap=cap-msg]", added: "[data-cap=cap-added]", note: "#mg-note", copy: "[data-cap=cap-copy]" });
  await page.click("[data-cap=cap-copy]", { timeout: 20000 }).catch((e) => ev("copy_click_error", String(e))); await sleep(1200);
  ev("toast", await txt("#toast"));
  await shot("V17_ex_copied", { panel: "[data-cap=cap-panel]", copy: "[data-cap=cap-copy]", toast: "#toast", added: "[data-cap=cap-added]" });

  // ---------- V18 ----------
  const close = page.locator("[data-cap=cap-panel] button[aria-label*='닫'], [data-cap=cap-panel] .close, [data-cap=cap-panel] [data-close]").first();
  if (await close.count()) await close.click().catch(() => {}); else await page.keyboard.press("Escape");
  await sleep(1500);
  await page.locator('[data-pstep="issue"]').first().click(); await sleep(4000);
  const card = `[...document.querySelectorAll('#sf-post-body details')].find(d => /0731/.test(d.closest('li,article,div').innerText))?.closest('li,article,div')`;
  await page.evaluate(`(${card})?.querySelector('details')?.setAttribute('open', '')`); await sleep(2000);
  await tag(card, "cap-icard");
  await tag(`[...document.querySelectorAll('[data-cap=cap-icard] button')].find(b => b.innerText.trim() === '발행')`, "cap-pub");
  await tag(`[...document.querySelectorAll('[data-cap=cap-icard] button')].find(b => /미리 보기/.test(b.innerText))`, "cap-prev");
  ev("issue_card", await txt("[data-cap=cap-icard]"));
  await shot("V18_issue", { body: "#sf-post-body", steps: "#sf-psteps", card: "[data-cap=cap-icard]", pub: "[data-cap=cap-pub]", prev: "[data-cap=cap-prev]" });
  await page.click("[data-cap=cap-prev]"); await sleep(4000);
  const sheetSel = `(() => { const h = [...document.querySelectorAll('*')].find(x => x.offsetParent && x.children.length === 0 && x.innerText && x.innerText.trim() === '현장 게시용 별지'); let e = h; while (e && !(e.offsetWidth > 700 && e.offsetHeight > 900)) e = e.parentElement; return e; })()`;
  const p02rows = async () => {
    await tag(sheetSel, "cap-sheet");
    // the first (P02) row of a label: its <tr>, or a narrow-enough parent, or the label cell with the value cell next to it
    const lab = (label) => `[...document.querySelectorAll('[data-cap=cap-sheet] *')].find(e => e.offsetParent && (e.innerText || '').trim() === ${JSON.stringify(label)} && e.children.length <= 1)`;
    const rowOf = async (label, id) => {
      const how = await page.evaluate(`(() => { const L = ${lab(label)}; if (!L) return 'none';
        const tr = L.closest('tr'); const p = L.parentElement;
        const row = tr && tr.offsetHeight < 300 ? tr : (p && p.offsetWidth > 500 && p.offsetHeight < 300 ? p : null);
        document.querySelectorAll('[data-cap=${id}],[data-cap=${id}v]').forEach(x => x.removeAttribute('data-cap'));
        if (row) { row.setAttribute('data-cap', '${id}'); return 'row'; }
        L.setAttribute('data-cap', '${id}'); if (L.nextElementSibling) L.nextElementSibling.setAttribute('data-cap', '${id}v'); return 'cell'; })()`);
      return how;
    };
    await tag(`[...document.querySelectorAll('[data-cap=cap-sheet] *')].filter(e => e.offsetParent && /^P02 · 1순위/.test((e.innerText || '').trim()) && e.offsetHeight < 60).sort(${area})[0]`, "cap-p02h");
    const how = {};
    for (const [l, id] of [["우리 반이 할 일", "cap-todo"], ["착수조건", "cap-start"], ["중지·해제 조건", "cap-stop"], ["예상 사고 경로", "cap-path"], ["우리 작업 일정", "cap-sched"], ["상대 반장·연락처", "cap-who"]]) how[id] = await rowOf(l, id);
    return how;
  };
  const R = (id) => [`[data-cap=${id}]`, `[data-cap=${id}v]`];
  ev("rows_how_sheet", await p02rows());
  await tag(`document.querySelector('[data-shai-go="0731|WP-1029-01"]')`, "cap-aigo");
  ev("sheet_before_ai", await txt("[data-cap=cap-sheet]"));
  await page.evaluate(`document.querySelector('[data-cap=cap-p02h]')?.scrollIntoView({ block: 'start' })`); await sleep(800);
  await shot("V18_sheet", { sheet: "[data-cap=cap-sheet]", p02: "[data-cap=cap-p02h]", todo: R("cap-todo"), start: R("cap-start"), aigo: "[data-cap=cap-aigo]" });
  const draftResp = page.waitForResponse((r) => r.url().includes("/api/safety/post-draft"), { timeout: 150000 }).then((r) => r.json()).catch((e) => ({ error: String(e) }));
  const t2 = Date.now();
  await page.click("[data-cap=cap-aigo]"); await sleep(1200);
  await shot("V18_wait", { ai: ".sh-ai[role=status]", sheet: "[data-cap=cap-sheet]" });
  const okDraft = await page.waitForFunction(`!document.querySelector('.sh-ai[role=status]')`, null, { timeout: 150000 }).then(() => true, () => false);
  ev("post_draft_seconds", { secs: (Date.now() - t2) / 1000, finished: okDraft });
  ev("post_draft_api", await draftResp);
  await sleep(1000);
  await p02rows();
  ev("post_draft_screen", await page.evaluate(`[...document.querySelectorAll('.sh-ai')].map(x => x.innerText)`));
  await page.evaluate(`document.querySelector('[data-cap=cap-todo]')?.scrollIntoView({ block: 'start' })`); await sleep(300);
  await page.evaluate(`(() => { const s = document.querySelector('.sh-ai-d'); if (s) { const r = s.getBoundingClientRect(); if (r.bottom > 1060) s.scrollIntoView({ block: 'end' }); } })()`); await sleep(800);
  await shot("V18_draft", { sheet: "[data-cap=cap-sheet]", ai: ".sh-ai-d", lines: ".sh-ai-d ol", src: ".sh-ai-d .hint", take: "[data-shai-take]", todo: R("cap-todo"), start: R("cap-start") });
  await page.click("[data-shai-take]").catch((e) => ev("take_click_error", String(e))); await sleep(2500);
  ev("toast_take", await txt("#toast"));
  await p02rows();
  ev("sheet_after_take", await txt("[data-cap=cap-sheet]"));
  await page.evaluate(`document.querySelector('[data-cap=cap-p02h]')?.scrollIntoView({ block: 'start' })`); await sleep(800);
  await shot("V18_taken", { sheet: "[data-cap=cap-sheet]", p02: "[data-cap=cap-p02h]", todo: R("cap-todo"), start: R("cap-start"), both: [...R("cap-todo"), ...R("cap-start")],
    ai: ".sh-ai-d", toast: "#toast" });

  // ---------- V19 ----------
  const x = page.locator("[data-cap=cap-sheet] button[aria-label*='닫'], [data-cap=cap-sheet] [data-close], #sf-p-close").first();
  if (await x.count()) await x.click().catch(() => {}); else await page.keyboard.press("Escape");
  await sleep(1500);
  await tag(card, "cap-icard");
  await tag(`[...document.querySelectorAll('[data-cap=cap-icard] button')].find(b => b.innerText.trim() === '발행')`, "cap-pub");
  ev("issue_card_before", await txt("[data-cap=cap-icard]"));
  await shot("V19_before", { card: "[data-cap=cap-icard]", pub: "[data-cap=cap-pub]", body: "#sf-post-body" });
  await page.click("[data-cap=cap-pub]"); await sleep(5000);
  ev("publish_dialog", await page.evaluate(`[...document.querySelectorAll('[role=dialog], dialog, .dialog')].filter(d => d.offsetParent || d.open).map(d => d.innerText.slice(0, 600))`));
  ev("toast_publish", await txt("#toast"));
  await tag(card, "cap-icard");
  await tag(`[...document.querySelectorAll('[data-cap=cap-icard] *')].filter(x => x.offsetParent && /발행/.test(x.innerText || '') && /R\\d/.test(x.innerText || '') && (x.innerText || '').length < 80).sort(${area})[0]`, "cap-issued");
  ev("issued_card", await txt("[data-cap=cap-icard]"));
  await shot("V19_issued", { body: "#sf-post-body", card: "[data-cap=cap-icard]", issued: "[data-cap=cap-issued]", steps: "#sf-psteps" });
  await page.evaluate(`[...document.querySelectorAll('[data-cap=cap-icard] button, [data-cap=cap-icard] a')].find(b => b.innerText.trim() === '보기')?.click()`); await sleep(4000);
  await p02rows();
  ev("issued_view", await txt("[data-cap=cap-sheet]"));
  await page.evaluate(`document.querySelector('[data-cap=cap-p02h]')?.scrollIntoView({ block: 'start' })`); await sleep(800);
  await tag(`[...document.querySelectorAll('[data-cap=cap-sheet] *')].filter(e => e.offsetParent && /S-0731\\/R\\d/.test(e.innerText || '') && (e.innerText || '').length < 60).sort(${area})[0]`, "cap-rev");
  await shot("V19_view", { sheet: "[data-cap=cap-sheet]", p02: "[data-cap=cap-p02h]", todo: R("cap-todo"), start: R("cap-start"), stop: R("cap-stop"), who: R("cap-who"), rev: "[data-cap=cap-rev]",
    three: [...R("cap-todo"), ...R("cap-start"), ...R("cap-stop")] });
  // the whole P02 part of the sheet: where the three items sit (head of the sheet to the counterpart row)
  await page.evaluate(`(() => { const s = document.querySelector("[data-cap=cap-sheet]"); s.scrollIntoView({ block: "start" }); let p = s; while (p && p !== document.body) { if (p.scrollHeight > p.clientHeight + 20) p.scrollTop = Math.max(0, p.scrollTop - 4000); p = p.parentElement; } })()`); await sleep(900);
  ev("rows_how_view", await p02rows());
  await shot("V19_full", { sheet: "[data-cap=cap-sheet]", p02: "[data-cap=cap-p02h]", todo: R("cap-todo"), start: R("cap-start"), stop: R("cap-stop"), rev: "[data-cap=cap-rev]",
    three: [...R("cap-todo"), ...R("cap-start"), ...R("cap-stop")] });
  ev("submission_links", await page.evaluate(`[...new Set([...document.querySelectorAll('a[href*="/api/submissions/"]')].map(a => a.href))]`));
  await subs("submissions_api_end");
  ev("done", true);
}
